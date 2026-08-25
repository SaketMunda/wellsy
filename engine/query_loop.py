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
import wave
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd

from intent import HELP_TEXT, Intent, parse_intent
from provenance import log_answer
from scene import describe_scene, query_object
from screen_capture import ScreenCaptureError, capture_screen
from stt import Stt
from tiers import PreemptionSeam
from tts import SpeechHandle, speak
from vad import EnergyVad, FRAME_SAMPLES, SAMPLE_RATE

# day11-prompt.md Part 2: routing an ambiguous "what's this?" is a real
# product question with no universally-right answer -- the default here is
# the camera (holding something up to be seen is this project's whole
# premise), overridable only by explicitly naming the screen. Keyword-only,
# same "pattern-matching, not language understanding" honesty as
# parse_intent itself (D23) -- this is deliberately NOT folded into
# parse_intent.py, which day11-prompt.md's boundary keeps untouched for the
# safety-critical intents only; this list lives here because it only
# affects which frame gets handed to the VLM, never whether a command runs.
SCREEN_KEYWORDS = (
    "my screen",
    "the screen",
    "on screen",
    "this screen",
    "my monitor",
    "my display",
    "on my computer",
    "on the computer",
)


def _wants_screen(transcript: str) -> bool:
    text = transcript.lower()
    return any(kw in text for kw in SCREEN_KEYWORDS)

WAKE_PHRASES_PATH = Path(__file__).parent / "wake_phrases.txt"
WAKE_MATCH_THRESHOLD = 0.72
# Real bug #1, found from a live log: a fixed WAKE_WINDOW_SECONDS=1.5s
# rolling buffer clipped the front of longer phrases (superseded below).
#
# Real bug #2, found immediately after widening it (still 100% "transcribed
# nothing" on real speech, per a live report): a rolling window is the
# wrong shape of fix regardless of size. It's appended to on *every* frame,
# speech or silence, so whatever length it is, most of its content is room
# silence before the utterance -- the actual speech sits in a small window
# near the end. `_record_utterance` (below), which DOES work in production
# (real transcripts like 'Yeah.' logged from it), never has this problem
# because it starts capturing at the exact frame speech begins, not on a
# timer. `_wake_thread` now does the same: a short pre-roll catches the
# onset the VAD's noise floor takes a beat to react to, then real capture
# starts exactly when `EnergyVad.is_speech()` first flips true and ends at
# the same trailing-silence pause the old ring's phrase-boundary used.
PREROLL_SECONDS = 0.3
WAKE_MAX_CAPTURE_SECONDS = 6.0  # safety cap if speech never pauses -- same role as MAX_UTTERANCE_SECONDS below
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

# Where empty-transcript wake-window buffers get dumped for real inspection
# (see `_log_and_save_wake_debug`) -- a ring of the last N, not unbounded,
# since a bad session could otherwise produce hundreds of these.
WAKE_DEBUG_DIR = Path(__file__).parent / "clips" / "wake_debug"
WAKE_DEBUG_KEEP = 20

# How many leftover words after the matched wake phrase count as "a real
# inline command" vs. noise/filler worth ignoring (e.g. a trailing "um").
# First-guess constant, unverified against real phrasing variety.
MIN_INLINE_COMMAND_WORDS = 2

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


def best_wake_match(transcript: str, phrases: list[str]) -> tuple[str, float, str] | None:
    """Slides a same-length word window over `transcript` for each phrase
    and returns the best (phrase, ratio, remainder) across all of them, or
    None if `transcript` has too few words to try. `remainder` is whatever
    words come after the matched window, joined back into text -- e.g. for
    transcript "hey apple what do you see in my screen" matching "hey yap"
    at word 0-1, remainder is "what do you see in my screen". Real gap,
    found from a live log: someone asking their whole question in one
    breath ("hey yap, what's on my screen") had that entire sentence
    consumed as "the phrase to fuzzy-match" and then thrown away, leaving
    nothing for the follow-up recording to catch ("heard nothing after
    wake") -- this lets the caller use the remainder directly instead of
    always demanding a second, separate utterance."""
    words = _normalize_words(transcript)
    if not words:
        return None
    best: tuple[str, float, str] | None = None
    for phrase in phrases:
        plen = len(phrase.split())
        for i in range(0, max(1, len(words) - plen + 1)):
            window = " ".join(words[i : i + plen])
            ratio = difflib.SequenceMatcher(None, window, phrase).ratio()
            if best is None or ratio > best[1]:
                remainder = " ".join(words[i + plen :])
                best = (phrase, ratio, remainder)
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
        self._wake_debug_count = 0
        self.transcript_log: list[str] = []  # every real STT output, for the wake-phrase evidence table
        self.query_log: list[dict] = []  # per-query latency breakdowns, day10-results.md's table
        self._conversation_deadline = 0.0  # monotonic time; while now < this, skip the wake-phrase requirement
        self.last_exchange: dict | None = None  # latest {transcript, answer, at} — main.py broadcasts this for browser captions

    # ---- shared plumbing ----

    def _log(self, msg: str) -> None:
        print(f"[t3] {msg}", file=sys.stderr, flush=True)

    def _log_and_save_wake_debug(self, buffer: np.ndarray) -> None:
        """`buffer`: float32 mono 16kHz, the exact audio just handed to STT
        that came back empty. Logs real, measured stats (not a guess) and
        saves the actual samples as a WAV under clips/wake_debug/ so this
        can be listened to or inspected directly instead of theorized
        about from a log line alone."""
        duration_s = len(buffer) / SAMPLE_RATE
        peak = float(np.max(np.abs(buffer))) if len(buffer) else 0.0
        rms = float(np.sqrt(np.mean(buffer.astype(np.float64) ** 2))) if len(buffer) else 0.0
        path = WAKE_DEBUG_DIR / f"empty_{time.strftime('%Y%m%d_%H%M%S')}_{self._wake_debug_count % WAKE_DEBUG_KEEP}.wav"
        self._wake_debug_count += 1
        try:
            WAKE_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            pcm16 = np.clip(buffer * 32768.0, -32768, 32767).astype(np.int16)
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm16.tobytes())
            saved = str(path)
        except Exception as e:
            saved = f"<failed to save: {e!r}>"
        self._log(
            f"wake-window: speech detected but transcribed nothing "
            f"(duration={duration_s:.2f}s peak={peak:.3f} rms={rms:.4f} saved={saved})"
        )

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

    def speak_ambient(self, text: str) -> SpeechHandle | None:
        """Part 2 (decisions.md D38): the one other case YAP is allowed to
        speak unprompted, gated by `ambient_enabled` at the call site
        (engine/ambient.py). Routes through the same `_speak` the wake
        matcher already knows to mute against, so an ambient line can't
        wake YAP up hearing itself say it. Returns the handle (or None if
        declined) so a caller like `greeting.py` can confirm what actually
        happened instead of firing blind."""
        if self.preemption.active:
            return None  # a query is in flight — ambient stays quiet, T3 has the floor
        return self._speak(text)

    def _extend_conversation(self) -> None:
        """Called after any handled command except `stop`/`sleep` — keeps
        the wake thread in "no wake phrase needed" mode for
        CONVERSATION_WINDOW_SECONDS so a back-and-forth doesn't need "hey
        yap" repeated before every follow-up question.

        Real bug, found from a live report ("works once, then stops"): this
        starts the 10s countdown the instant `_speak()` is *called*, not
        when the answer actually finishes playing. Chatterbox is
        non-blocking and real generation alone is 1.6-3.2s (tts.py) before
        any audio starts, plus however long the spoken answer runs -- a
        real user hears the deadline already half (or fully) burned away
        before they've even finished hearing the answer, let alone thought
        of and spoken a follow-up. Re-arming the deadline again once the
        in-flight speech handle actually finishes gives a full
        CONVERSATION_WINDOW_SECONDS of real post-answer thinking time on
        top of this immediate one (which still matters for a fast
        responder mid-generation)."""
        self._conversation_deadline = time.monotonic() + CONVERSATION_WINDOW_SECONDS
        handle = self._current_speech
        if handle is not None and handle.speaking:
            threading.Thread(target=self._reextend_after_speech, args=(handle,), daemon=True).start()

    def _reextend_after_speech(self, handle: SpeechHandle) -> None:
        handle.wait()
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

        # Real bug, found in a live log: "can you see my screen?" matches
        # parse_intent's own `_QUERY` pattern ("can you see " + object) and
        # comes back as `query_object(object="my screen")` -- a fixed-
        # grammar match that answers from the camera's tracked-object list
        # ("no. no my screen in view.") and never reaches the `unknown`
        # branch below, where `_wants_screen()` and the actual screen-
        # capture/VLM path live. `intent.py` stays untouched (the boundary
        # rule for the fixed grammar) -- this reroutes at the one call site
        # that already owns the screen-vs-camera decision, before that
        # grammar gets a chance to answer the wrong question correctly.
        if intent.type == "query_object" and _wants_screen(transcript):
            intent = Intent("unknown", transcript=transcript)
            record["intent"] = intent.type
            record["intentRerouted"] = "query_object -> unknown (screen keyword)"

        if intent.type == "unknown":
            # decisions.md D40: parse_intent only covers the fixed command
            # grammar (stop/wake/sleep/describe_scene/query_object/help) —
            # anything a question-shaped or off-script phrasing was never
            # going to match falls here. Whatever isn't safety- or
            # reliability-critical gets routed to a real local LLM instead
            # of a canned "I didn't understand" — that canned line still
            # exists as the fallback if no LLM was wired in (llm=None).
            if self.llm is not None:
                # Day 11 (day11-prompt.md Part 1.2): "unknown" now goes to
                # the VLM with the actual frame, not a blind text model
                # reading a word list off describeScene. Tracks still ride
                # along as corroboration (Part 1.3), not as the source of
                # the answer -- see llm.py's docstring for why the old
                # few-shot grounding hack is gone rather than carried
                # forward.
                #
                # try/finally is load-bearing here, not defensive style: an
                # Ollama call is a network call to another process this
                # project doesn't manage, and a real retest found that an
                # unhandled exception here did two bad things at once --
                # (1) killed `_wake_thread` permanently and silently (the
                # thread just dies; capture/detection keep running fine,
                # since they're a separate thread/process, which is exactly
                # what "the engine is still running but nothing wakes up"
                # looks like from outside), and (2) left `preemption` stuck
                # `active` forever since `release()` was never reached,
                # freezing ambient T1 too. Neither failure mode is
                # acceptable for an always-on listener thread. Unchanged
                # from D40's shape; day11-prompt.md Part 1.4 asks for a
                # regression test proving it still holds with the new
                # (image-carrying) call in place -- see test_query_loop.py.
                self.preemption.request()
                try:
                    frame_source = "screen" if _wants_screen(transcript) else "camera"
                    t_frame = time.monotonic()
                    tracks: list[dict] = []
                    frame_bgr = None

                    if frame_source == "screen":
                        try:
                            frame_bgr = capture_screen()
                        except ScreenCaptureError as e:
                            self._log(f"screen capture failed: {e!r} -- falling back to camera frame")
                            frame_source = "camera"

                    if frame_source == "camera":
                        result = self.preemption.request_fresh_look()
                        tracks = result[0] if result else []
                        frame_bgr = result[2] if result else None

                    record["frameSource"] = frame_source
                    if frame_source == "screen":
                        # Real gap, found from a live report of "it can't
                        # see my VS Code / browser window": there was no
                        # way to tell, from the log alone, whether that was
                        # a capture problem (wrong/missing display) or a
                        # visibility problem (the window just wasn't on
                        # top when the question fired -- a screenshot can
                        # only ever show what's actually rendered, same as
                        # capture_screen()'s own docstring says). This
                        # makes the display count real and checkable
                        # instead of assumed.
                        record["displaysCaptured"] = len(frame_bgr) if frame_bgr else 0
                    record["frameMs"] = round((time.monotonic() - t_frame) * 1000, 2)
                    scene = describe_scene(tracks) if tracks else None

                    t_llm = time.monotonic()
                    answer = self.llm.respond(transcript, frame_bgr=frame_bgr, scene=scene)
                    llm_ms = round((time.monotonic() - t_llm) * 1000, 1)
                    record["llmMs"] = llm_ms
                    record["answer"] = answer
                    self._speak_and_log(transcript, answer)
                    log_answer(
                        transcript=transcript,
                        answer=answer,
                        source="vlm+tracks" if tracks else "vlm",
                        frame_source=frame_source,
                        tracks=tracks,
                        frame_age_ms=record["frameMs"],
                        llm_ms=llm_ms,
                    )
                except Exception as e:
                    self._log(f"LLM error: {e!r} -- falling back to a canned response")
                    record["llmError"] = repr(e)
                    self._speak_and_log(transcript, "i had trouble reaching my language model just now.")
                finally:
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
            try:
                record = self.handle_command(transcript, source="push-to-talk")
                record["pressToAnswerMs"] = round((time.monotonic() - t_press) * 1000, 1)
                self._log(f"press-to-answer breakdown: {record}")
            except Exception as e:
                # Defense in depth alongside the try/finally inside
                # handle_command's LLM branch: nothing should be able to
                # kill this always-on thread for the rest of the session.
                self._log(f"press-to-talk error: {e!r}")

    # ---- wake phrase: always-on rolling listen ----

    def _wake_thread(self) -> None:
        self._log(f"wake-phrase listening ready — phrases: {self.wake_phrases}")
        preroll_frames = int(PREROLL_SECONDS * SAMPLE_RATE / FRAME_SAMPLES)
        frame_seconds = FRAME_SAMPLES / SAMPLE_RATE
        preroll: deque[np.ndarray] = deque(maxlen=preroll_frames)
        vad = EnergyVad()

        capturing = False
        chunks: list[np.ndarray] = []
        capture_seconds = 0.0
        silence_since_speech = 0.0
        last_transcribe_at = 0.0
        was_speech = False
        was_muted = False  # for the one-line transition log below, not per-frame spam

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=self.device) as stream:
            while not self._stop_flag.is_set():
                frame, _ = stream.read(FRAME_SAMPLES)
                frame = frame[:, 0]
                preroll.append(frame)

                self._reload_wake_phrases_if_changed()

                if self._speaking():
                    # Feedback trap #1 (day10-prompt.md Part 3): suppress
                    # wake matching against YAP's own voice. Push-to-talk
                    # (stdin) is a separate thread and is NOT gated by
                    # this, so "stop" still works mid-word — feedback trap #2.
                    #
                    # Real cost, made visible rather than silent (reported
                    # live: "sometimes it responds sometimes not"): anything
                    # you say while YAP is still talking is dropped here,
                    # completely, with zero signal that it happened. With
                    # `say`, that window was near-instant; Chatterbox's real
                    # generation time (1.6-3.2s+, D44) makes it a window big
                    # enough to actually talk over. Not removing the mute —
                    # it's the real fix for the mic hearing its own voice
                    # through the speakers, no AEC on this hardware — just
                    # logging the transition once (not per frame) so a
                    # dropped follow-up is diagnosable instead of looking
                    # like random flakiness.
                    if not was_muted:
                        self._log("muted (speaking) — anything said now won't be heard until it finishes")
                        was_muted = True
                    continue
                was_muted = False

                is_speech = vad.is_speech(frame)

                # Conversation mode (issue #1): once a command has been
                # answered, skip the wake-phrase requirement entirely for
                # CONVERSATION_WINDOW_SECONDS — go straight to recording a
                # full follow-up utterance the moment speech starts, using
                # `_record_utterance`'s own proper silence-tail logic
                # rather than the wake-window capture below (a real
                # question can run longer than a wake phrase).
                if self.in_conversation and is_speech and not was_speech and not capturing:
                    was_speech = True
                    audio = self._record_utterance(prefill=frame, stream=stream)
                    silence_since_speech = 0.0
                    t_follow = time.monotonic()
                    transcript = self.stt.transcribe(audio)
                    self.transcript_log.append(transcript)
                    if not transcript:
                        self._log("heard nothing (conversation mode).")
                        continue
                    try:
                        record = self.handle_command(transcript, source="wake-followup")
                        record["followUpMs"] = round((time.monotonic() - t_follow) * 1000, 1)
                        self._log(f"conversation breakdown: {record}")
                    except Exception as e:
                        self._log(f"wake-followup error: {e!r}")
                    continue

                was_speech = is_speech
                cooldown_ok = (time.monotonic() - last_transcribe_at) >= WAKE_TRANSCRIBE_COOLDOWN_SECONDS

                if not capturing:
                    if is_speech and cooldown_ok:
                        # Onset, not a timer: start the capture from the
                        # pre-roll (covers the syllable the VAD's adaptive
                        # noise floor needed a frame or two to react to)
                        # plus this frame — same prefill shape
                        # `_record_utterance` already uses successfully.
                        capturing = True
                        chunks = list(preroll)
                        capture_seconds = len(chunks) * frame_seconds
                        silence_since_speech = 0.0
                    continue

                # Mid-capture: keep appending real audio (speech and any
                # short pauses inside the phrase) until a trailing silence
                # ends it, or the safety cap fires.
                chunks.append(frame)
                capture_seconds += frame_seconds
                silence_since_speech = 0.0 if is_speech else silence_since_speech + frame_seconds

                if not (silence_since_speech >= WAKE_PHRASE_PAUSE_SECONDS or capture_seconds >= WAKE_MAX_CAPTURE_SECONDS):
                    continue

                capturing = False
                last_transcribe_at = time.monotonic()
                buffer = np.concatenate(chunks).astype(np.float32) / 32768.0
                chunks = []
                capture_seconds = 0.0
                silence_since_speech = 0.0

                transcript = self.stt.transcribe(buffer)
                if not transcript:
                    # Real gap, found from a live report of "I said hey yap
                    # 5-10 times, nothing happened": this branch had no log
                    # line at all, unlike the post-wake-match "heard
                    # nothing after wake." A failed local-STT attempt here
                    # (VAD triggered, but Moonshine transcribed nothing
                    # usable) was completely invisible -- indistinguishable
                    # from never having spoken at all.
                    #
                    # Real gap #2, found after a floor-lockout fix (vad.py)
                    # did NOT stop this from repeating for an entire live
                    # session: without knowing what was actually IN the
                    # buffer handed to STT, every theory here is a guess.
                    # This logs the buffer's real duration/peak/RMS and
                    # saves it as a WAV so the next round is diagnosis from
                    # evidence, not another blind theory.
                    self._log_and_save_wake_debug(buffer)
                    continue
                self.transcript_log.append(transcript)

                match = best_wake_match(transcript, self.wake_phrases)
                if match is None or match[1] < WAKE_MATCH_THRESHOLD:
                    # Same visibility gap as above, one step later: local
                    # STT produced *something*, but it didn't score high
                    # enough against the wake phrase list to count. Two of
                    # a real ~8-attempt run scored 0.77/0.86 and passed
                    # (threshold is 0.72) -- worth seeing what the ones
                    # that didn't pass actually transcribed as, since a
                    # persistent mishearing pattern would be a real,
                    # fixable wake-phrase-list problem, not noise.
                    if match is not None:
                        self._log(f"wake-window: '{transcript}' ~ '{match[0]}' ({match[1]:.2f}) -- below {WAKE_MATCH_THRESHOLD} threshold")
                    else:
                        self._log(f"wake-window: '{transcript}' -- no match against {self.wake_phrases}")
                    continue

                self._log(f"wake match: '{transcript}' ~ '{match[0]}' ({match[1]:.2f})")
                t_wake = time.monotonic()

                remainder = match[2].strip()
                if len(remainder.split()) >= MIN_INLINE_COMMAND_WORDS:
                    # Said in one breath, e.g. "hey yap, what's on my
                    # screen" -- the command is already in `transcript`,
                    # right after the matched wake words. Use it directly
                    # instead of opening a second recording that would
                    # just catch silence (the exact "heard nothing after
                    # wake" bug this was added to fix).
                    self._log(f"wake: using inline remainder as command: '{remainder}'")
                    command_transcript = remainder
                else:
                    audio = self._record_utterance(stream=stream)
                    command_transcript = self.stt.transcribe(audio)
                    self.transcript_log.append(command_transcript)
                    if not command_transcript:
                        self._log("heard nothing after wake.")
                        continue
                try:
                    record = self.handle_command(command_transcript, source="wake")
                    record["wakeToAnswerMs"] = round((time.monotonic() - t_wake) * 1000, 1)
                    self._log(f"wake-to-answer breakdown: {record}")
                except Exception as e:
                    self._log(f"wake error: {e!r}")

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
