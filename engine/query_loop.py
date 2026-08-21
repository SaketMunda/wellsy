"""T3: the query loop — mic -> VAD -> Moonshine STT -> parseIntent ->
[PreemptionSeam.request() -> forced fresh T1 -> describeScene] -> TTS ->
speakers -> PreemptionSeam.release(). day10-prompt.md Part 1/3.

Two independent triggers converge on the same `handle_command()`:
- **Wake phrase** (`_wake_thread`): always-on, VAD-gated rolling transcription
  of a ~1.5s buffer, fuzzy-matched against `wake_phrases.txt`. Transcribe-
  then-match, not a trained keyword spotter — say that plainly on camera.
- **Push-to-talk** (`_ptt_thread`): press Enter in the terminal running
  `main.py`, speak, a brief VAD silence-tail ends the recording. This is the
  filming fallback the brief asks for; a true hold-a-hardware-button UX
  needs a global-hotkey library with its own OS permission gate (Accessibility)
  that this session did not chase, since stdin Enter is a strictly simpler,
  equally reliable substitute for "press a button, then speak."

`unknown` is a shipped answer — see `intent.py`; this loop never falls back
to a model when parseIntent can't classify a transcript.
"""

from __future__ import annotations

import difflib
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

from intent import HELP_TEXT, parse_intent
from scene import describe_scene, query_object
from stt import Stt
from tiers import PreemptionSeam
from tts import SpeechHandle, speak
from vad import EnergyVad, FRAME_SAMPLES, SAMPLE_RATE

WAKE_PHRASES_PATH = Path(__file__).parent / "wake_phrases.txt"
WAKE_MATCH_THRESHOLD = 0.72
WAKE_WINDOW_SECONDS = 1.5
SILENCE_TAIL_SECONDS = 0.6
MAX_UTTERANCE_SECONDS = 8.0

# Real-usage bug found post-Day-10 (decisions.md D39 amendment): the wake
# thread was calling transcribe() on every ~30ms VAD-positive frame — i.e.
# dozens of times per second while someone was mid-phrase, each call
# competing with the detector for CPU. That's what made responses feel
# "so late" and is the likely cause of a real question ("do you see a
# cellphone") garbling into something that pattern-matched as
# describe_scene instead of query_object. Fix: only attempt a wake-window
# transcription once per detected phrase boundary (speech -> a short
# pause), gated additionally by a minimum cooldown between attempts.
WAKE_PHRASE_PAUSE_SECONDS = 0.35
WAKE_TRANSCRIBE_COOLDOWN_SECONDS = 0.5

# How long after a handled command YAP keeps listening for a follow-up
# without needing the wake phrase again — a real usability gap Day 10
# shipped without: every question needed "hey yap" repeated. Reset on each
# handled command, so a back-and-forth conversation never needs to re-wake.
CONVERSATION_WINDOW_SECONDS = 10.0

STOP_WORDS_RE = re.compile(r"\bstop\b", re.IGNORECASE)


def load_wake_phrases(enable_yo: bool) -> list[str]:
    if not WAKE_PHRASES_PATH.exists():
        phrases = []
    else:
        phrases = [
            line.strip().lower()
            for line in WAKE_PHRASES_PATH.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if enable_yo and "yo" not in phrases:
        phrases.append("yo")
    return phrases


def _normalize_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).split()


def best_wake_match(transcript: str, phrases: list[str]) -> tuple[str, float] | None:
    """Slides a same-length word window over `transcript` for each phrase
    and returns the best (phrase, ratio) across all of them, or None if
    `transcript` has too few words to try."""
    words = _normalize_words(transcript)
    if not words:
        return None
    best: tuple[str, float] | None = None
    for phrase in phrases:
        plen = len(phrase.split())
        for i in range(0, max(1, len(words) - plen + 1)):
            window = " ".join(words[i : i + plen])
            ratio = difflib.SequenceMatcher(None, window, phrase).ratio()
            if best is None or ratio > best[1]:
                best = (phrase, ratio)
    return best


class QueryLoop:
    def __init__(
        self,
        preemption: PreemptionSeam,
        stt: Stt,
        llm: object | None = None,
        enable_yo: bool = False,
        device: int | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.preemption = preemption
        self.stt = stt
        self.llm = llm
        self.enable_yo = enable_yo
        self.device = device
        self.wake_phrases = load_wake_phrases(enable_yo)
        self._wake_phrases_mtime = WAKE_PHRASES_PATH.stat().st_mtime if WAKE_PHRASES_PATH.exists() else None
        self.ambient_enabled = False  # Part 2: silence is the default (decisions.md D38)
        self._current_speech: SpeechHandle | None = None
        self._stop_flag = threading.Event()
        self._log_path = log_path
        self._log_lock = threading.Lock()
        self.transcript_log: list[str] = []  # every real STT output, for the wake-phrase evidence table
        self.query_log: list[dict] = []  # per-query latency breakdowns, day10-results.md's table
        self._conversation_deadline = 0.0  # monotonic time; while now < this, skip the wake-phrase requirement
        self.last_exchange: dict | None = None  # latest {transcript, answer, at} — main.py broadcasts this for browser captions

    # ---- shared plumbing ----

    def _log(self, msg: str) -> None:
        print(f"[t3] {msg}", file=sys.stderr, flush=True)

    def _speaking(self) -> bool:
        return self._current_speech is not None and self._current_speech.speaking

    def _speak(self, text: str) -> SpeechHandle:
        handle = speak(text)
        self._current_speech = handle
        return handle

    def _speak_and_log(self, transcript: str, text: str) -> SpeechHandle:
        """Same as `_speak`, plus recording the exchange for the bridge to
        broadcast (main.py) so the browser HUD can show captions for what
        the engine's own mic/speakers are doing — day10 shipped voice with
        zero visibility in the browser (decisions.md D40's ecosystem
        follow-up); this is what main.py reads to fix that."""
        handle = self._speak(text)
        self.last_exchange = {"transcript": transcript, "answer": text, "at": time.time()}
        return handle

    def stop_speaking(self) -> None:
        if self._current_speech is not None:
            self._current_speech.stop()

    def speak_ambient(self, text: str) -> None:
        """Part 2 (decisions.md D38): the one other case YAP is allowed to
        speak unprompted, gated by `ambient_enabled` at the call site
        (engine/ambient.py). Routes through the same `_speak` the wake
        matcher already knows to mute against, so an ambient line can't
        wake YAP up hearing itself say it."""
        if self.preemption.active:
            return  # a query is in flight — ambient stays quiet, T3 has the floor
        self._speak(text)

    def _extend_conversation(self) -> None:
        """Called after any handled command except `stop`/`sleep` — keeps
        the wake thread in "no wake phrase needed" mode for
        CONVERSATION_WINDOW_SECONDS so a back-and-forth doesn't need "hey
        yap" repeated before every follow-up question."""
        self._conversation_deadline = time.monotonic() + CONVERSATION_WINDOW_SECONDS

    @property
    def in_conversation(self) -> bool:
        return time.monotonic() < self._conversation_deadline

    def _reload_wake_phrases_if_changed(self) -> None:
        if not WAKE_PHRASES_PATH.exists():
            return
        mtime = WAKE_PHRASES_PATH.stat().st_mtime
        if mtime != self._wake_phrases_mtime:
            self.wake_phrases = load_wake_phrases(self.enable_yo)
            self._wake_phrases_mtime = mtime
            self._log(f"wake phrases reloaded: {self.wake_phrases}")

    # ---- the actual query loop, once we have a full utterance's audio ----

    def handle_command(self, transcript: str, source: str) -> dict:
        """Runs one full T3 pass and returns the latency breakdown, logged
        to day10-results.md's table. `source` is 'wake' or 'push-to-talk',
        recorded for the report."""
        t_start = time.monotonic()
        record: dict = {"source": source, "transcript": transcript}

        if STOP_WORDS_RE.search(transcript):
            self.stop_speaking()
            record["intent"] = "stop"
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        t_intent = time.monotonic()
        intent = parse_intent(transcript)
        record["intentMs"] = round((time.monotonic() - t_intent) * 1000, 2)
        record["intent"] = intent.type

        if intent.type == "unknown":
            # decisions.md D40: parse_intent only covers the fixed command
            # grammar (stop/wake/sleep/describe_scene/query_object/help) —
            # anything a question-shaped or off-script phrasing was never
            # going to match falls here. Whatever isn't safety- or
            # reliability-critical gets routed to a real local LLM instead
            # of a canned "I didn't understand" — that canned line still
            # exists as the fallback if no LLM was wired in (llm=None).
            if self.llm is not None:
                # Ground the LLM in what's actually in frame right now --
                # found necessary from a real retest (decisions.md D40
                # amendment): without it, any scene-shaped question got a
                # fluent, entirely invented answer instead of a grounded
                # one. Same forced-fresh-look mechanism describe_scene/
                # query_object use, so "unknown" gets the same freshness
                # guarantee as an explicit command.
                self.preemption.request()
                t_freshlook = time.monotonic()
                result = self.preemption.request_fresh_look()
                record["freshLookMs"] = round((time.monotonic() - t_freshlook) * 1000, 2)
                tracks = result[0] if result else []
                scene = describe_scene(tracks)

                t_llm = time.monotonic()
                answer = self.llm.respond(transcript, scene=scene)
                record["llmMs"] = round((time.monotonic() - t_llm) * 1000, 1)
                record["answer"] = answer
                self._speak_and_log(transcript, answer)
                self.preemption.release()
            else:
                self._speak_and_log(transcript, "i didn't understand that. say help for what i handle.")
            self._extend_conversation()
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        if intent.type == "help":
            self._speak_and_log(transcript, HELP_TEXT)
            self._extend_conversation()
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        if intent.type == "presence":
            self._speak_and_log(transcript, "yeah, i'm here.")
            self._extend_conversation()
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        if intent.type == "thanks":
            self._speak_and_log(transcript, "you're welcome.")
            self._extend_conversation()
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        if intent.type == "sleep":
            self.ambient_enabled = False
            self._speak_and_log(transcript, "okay.")
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        if intent.type == "wake":
            # Mirrors the browser build's original wake/sleep semantics
            # (D6/D26): "wake" turns ambient narration on, "sleep" turns it
            # off. This is the one voice-driven way to leave the Part 2
            # off-by-default state — everything else stays silent until
            # asked. See decisions.md D38.
            self.ambient_enabled = True
            self._speak_and_log(transcript, "i'm listening.")
            self._extend_conversation()
            record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
            self.query_log.append(record)
            return record

        # describe_scene / query_object both need real, fresh tracks —
        # day10-prompt.md Part 0.1: a question forces a fresh T1 look
        # rather than reading whatever ambient sensing last happened to see.
        self.preemption.request()
        t_freshlook = time.monotonic()
        result = self.preemption.request_fresh_look()
        record["freshLookMs"] = round((time.monotonic() - t_freshlook) * 1000, 2)
        tracks = result[0] if result else []
        record["inferenceMs"] = result[1] if result else None

        t_describe = time.monotonic()
        if intent.type == "describe_scene":
            answer = describe_scene(tracks)
        else:
            answer = query_object(tracks, intent.object or "")
        record["describeMs"] = round((time.monotonic() - t_describe) * 1000, 2)
        record["answer"] = answer

        handle = self._speak_and_log(transcript, answer)
        record["ttsFirstAudioMs"] = round((handle.started_at - t_start) * 1000, 1)
        self.preemption.release()
        self._extend_conversation()

        record["totalMs"] = round((time.monotonic() - t_start) * 1000, 1)
        self.query_log.append(record)
        self._log(f"{source}: '{transcript}' -> {intent.type} -> '{answer}' ({record['totalMs']}ms)")
        return record

    # ---- capture: shared VAD-gated utterance recorder ----

    def _record_utterance(self, prefill: np.ndarray | None = None, stream: sd.InputStream | None = None) -> np.ndarray:
        """Records until `SILENCE_TAIL_SECONDS` of quiet after speech, or
        `MAX_UTTERANCE_SECONDS` total.

        `stream`: an already-open `InputStream` to read from (the
        wake-listener's own stream), so this never opens a second,
        simultaneous stream on the same input device. Two concurrent
        `sd.InputStream`s on one device is exactly the kind of contention
        that could plausibly explain real-usage garbling — found and fixed
        after Day 10 shipped a version that nested them (decisions.md D39
        amendment). Push-to-talk (`_ptt_thread`) has no wake listener
        running concurrently against the same device, so it still opens
        its own short-lived stream, passed as `None` here."""
        vad = EnergyVad()
        chunks: list[np.ndarray] = [prefill] if prefill is not None else []
        silence_run = 0.0
        spoke_yet = prefill is not None

        def _read_loop(s: sd.InputStream) -> None:
            nonlocal silence_run, spoke_yet
            start = time.monotonic()
            while time.monotonic() - start < MAX_UTTERANCE_SECONDS and not self._stop_flag.is_set():
                frame, _ = s.read(FRAME_SAMPLES)
                frame = frame[:, 0]
                chunks.append(frame)
                if vad.is_speech(frame):
                    spoke_yet = True
                    silence_run = 0.0
                elif spoke_yet:
                    silence_run += FRAME_SAMPLES / SAMPLE_RATE
                    if silence_run >= SILENCE_TAIL_SECONDS:
                        break

        if stream is not None:
            _read_loop(stream)
        else:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=self.device) as s:
                _read_loop(s)

        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        return audio

    # ---- push-to-talk: Enter key in the terminal ----

    def _ptt_thread(self) -> None:
        self._log("push-to-talk ready — press Enter, then speak (filming fallback).")
        while not self._stop_flag.is_set():
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if not line:
                return
            self._log("recording...")
            t_press = time.monotonic()
            audio = self._record_utterance()
            transcript = self.stt.transcribe(audio)
            self.transcript_log.append(transcript)
            if not transcript:
                self._log("heard nothing.")
                continue
            record = self.handle_command(transcript, source="push-to-talk")
            record["pressToAnswerMs"] = round((time.monotonic() - t_press) * 1000, 1)
            self._log(f"press-to-answer breakdown: {record}")

    # ---- wake phrase: always-on rolling listen ----

    def _wake_thread(self) -> None:
        self._log(f"wake-phrase listening ready — phrases: {self.wake_phrases}")
        window_frames = int(WAKE_WINDOW_SECONDS * SAMPLE_RATE / FRAME_SAMPLES)
        frame_seconds = FRAME_SAMPLES / SAMPLE_RATE
        ring: deque[np.ndarray] = deque(maxlen=window_frames)
        vad = EnergyVad()

        speech_run = 0.0  # seconds of continuous speech seen since the last reset
        silence_since_speech = 0.0
        last_transcribe_at = 0.0
        was_speech = False

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=self.device) as stream:
            while not self._stop_flag.is_set():
                frame, _ = stream.read(FRAME_SAMPLES)
                frame = frame[:, 0]
                ring.append(frame)

                self._reload_wake_phrases_if_changed()

                if self._speaking():
                    # Feedback trap #1 (day10-prompt.md Part 3): suppress
                    # wake matching against YAP's own voice. Push-to-talk
                    # (stdin) is a separate thread and is NOT gated by
                    # this, so "stop" still works mid-word — feedback trap #2.
                    continue

                is_speech = vad.is_speech(frame)

                # Real usage bug (decisions.md D39 amendment): this used to
                # call transcribe() on every VAD-positive frame — dozens of
                # calls per second while someone spoke, fighting the
                # detector for CPU and mangling transcripts. Now it waits
                # for a phrase boundary (speech, then a short pause) before
                # transcribing once, plus a hard cooldown as a backstop.
                if is_speech:
                    speech_run += frame_seconds
                    silence_since_speech = 0.0
                elif speech_run > 0:
                    silence_since_speech += frame_seconds

                # Conversation mode (issue #1): once a command has been
                # answered, skip the wake-phrase requirement entirely for
                # CONVERSATION_WINDOW_SECONDS — go straight to recording a
                # full follow-up utterance the moment speech starts, using
                # `_record_utterance`'s own proper silence-tail logic
                # rather than the fixed 1.5s wake window (a real question
                # can run longer than that).
                if self.in_conversation and is_speech and not was_speech:
                    was_speech = True
                    audio = self._record_utterance(prefill=frame, stream=stream)
                    ring.clear()
                    speech_run = 0.0
                    silence_since_speech = 0.0
                    t_follow = time.monotonic()
                    transcript = self.stt.transcribe(audio)
                    self.transcript_log.append(transcript)
                    if not transcript:
                        self._log("heard nothing (conversation mode).")
                        continue
                    record = self.handle_command(transcript, source="wake-followup")
                    record["followUpMs"] = round((time.monotonic() - t_follow) * 1000, 1)
                    self._log(f"conversation breakdown: {record}")
                    continue

                was_speech = is_speech

                phrase_boundary = speech_run > 0 and silence_since_speech >= WAKE_PHRASE_PAUSE_SECONDS
                cooldown_ok = (time.monotonic() - last_transcribe_at) >= WAKE_TRANSCRIBE_COOLDOWN_SECONDS
                if not (phrase_boundary and cooldown_ok and len(ring) == window_frames):
                    continue

                last_transcribe_at = time.monotonic()
                speech_run = 0.0
                silence_since_speech = 0.0

                buffer = np.concatenate(list(ring)).astype(np.float32) / 32768.0
                transcript = self.stt.transcribe(buffer)
                if not transcript:
                    continue
                self.transcript_log.append(transcript)

                match = best_wake_match(transcript, self.wake_phrases)
                if match is None or match[1] < WAKE_MATCH_THRESHOLD:
                    continue

                self._log(f"wake match: '{transcript}' ~ '{match[0]}' ({match[1]:.2f})")
                t_wake = time.monotonic()
                ring.clear()
                audio = self._record_utterance(stream=stream)
                command_transcript = self.stt.transcribe(audio)
                self.transcript_log.append(command_transcript)
                if not command_transcript:
                    self._log("heard nothing after wake.")
                    continue
                record = self.handle_command(command_transcript, source="wake")
                record["wakeToAnswerMs"] = round((time.monotonic() - t_wake) * 1000, 1)
                self._log(f"wake-to-answer breakdown: {record}")

    def start(self) -> None:
        # Real crash found post-Day-10 (SIGSEGV in cffi/ffi_call, inside
        # PortAudio's real-time callback thread): the wake thread's
        # `sd.InputStream` was still open when the process began shutting
        # down, and daemon threads get killed abruptly rather than given a
        # chance to close their stream. If Py_Finalize starts freeing
        # Python objects while CoreAudio's callback thread is still mid-
        # callback into one of them, that's a use-after-free -> segfault,
        # not a Python-level bug `try`/`except` can catch. Fix: the wake
        # thread is NOT daemon, and `stop()` joins it — this forces the
        # process to wait for `_wake_thread`'s `with sd.InputStream(...)`
        # block to actually exit (closing the stream cleanly) before the
        # interpreter is allowed to proceed toward shutdown.
        self._wake_thread_handle = threading.Thread(target=self._wake_thread, daemon=False, name="t3-wake")
        self._wake_thread_handle.start()
        # push-to-talk stays daemon: it blocks on `sys.stdin.readline()`,
        # which has no clean way to be interrupted from another thread
        # (unlike the wake thread's frame-at-a-time read loop), so joining
        # it here could hang shutdown forever waiting for an Enter that
        # will never come. It only opens its own InputStream for the brief
        # window an actual recording is in progress, which narrows but
        # does not eliminate this same crash's window for push-to-talk —
        # see decisions.md D39's amendment for the honest caveat.
        threading.Thread(target=self._ptt_thread, daemon=True, name="t3-ptt").start()

    def stop(self) -> None:
        self._stop_flag.set()
        handle = getattr(self, "_wake_thread_handle", None)
        if handle is not None:
            handle.join(timeout=3.0)
