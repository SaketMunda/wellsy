"""Open-air audio: the echo-regression fixes (step 4c).

The pre-rebuild build worked on laptop speakers because the mic thread
hard-muted itself for the whole duration of its own speech — half-duplex by
construction, and it logged the transition so a dropped follow-up was
diagnosable. Step 4 shipped real barge-in (mic open during playback) and nothing
replaced the mute, so the assistant heard itself: VAD read the playback as
barge-in and cancelled its own sentence, STT transcribed its own words as the
user, the LLM answered itself. See `.claude/rebuild/step4c-echo-and-duplex.md`.

Three defence layers live here; a fourth (acoustic echo cancellation) is
`engine/voice/aec.py`.

1. **HalfDuplexGate** — `build_half_duplex_gate`. Placed immediately after
   `transport.input()`. While the bot is speaking (plus a short room-decay
   tail) it drops `InputAudioRawFrame`s so the downstream VAD/turn detector and
   the segmented STT never see the playback. `InterruptionFrame` (ESC, the
   deterministic stop, INVARIANTS #3) is *never* dropped. The mute/unmute
   transition is logged exactly once, never per frame (INVARIANTS #13). Default
   on.

2. **SelfEchoFilter** — `build_self_echo_filter` + `build_echo_text_tap`. We
   handed every spoken sentence to the TTS, so we know what we just said. The
   tap (after the TTS service) records it into a short rolling window; the
   filter (after STT) fuzzy-matches every `TranscriptionFrame` against that
   window and drops + logs the ones that are the bot hearing itself. Not echo
   cancellation and no substitute for it — the last line of defence, works on
   any hardware, and would have killed every loop in the 2026-09-02 log.

3. **wake-word-gated barge-in** — `mode="wake_gated"` on the gate, with an
   `AsrWakeProbe`. Instead of going fully deaf during playback, run the wake
   phrase detector *only* on the muted audio; "Wellsy, stop" cuts the bot off,
   a cough does not. Strictly better than the old build (fully deaf while
   speaking). EXPERIMENTAL until the wake fixtures + threshold tune that step 4
   still owes land — default stays `mode="mute"`.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from loguru import logger

_PUNCT_KEEP = str.maketrans({c: " " for c in "\"'.,!?;:()[]{}—–-…"})


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return " ".join(text.lower().translate(_PUNCT_KEEP).split())


def echo_match_score(spoken: str, transcript: str) -> float:
    """How well `transcript` matches some span of `spoken`, 0..1.

    `transcript` is typically a *fragment* of a longer bot sentence — the STT
    catches only the first few words before the barge-in logic cancels the rest
    ("I can't share deep." out of "I can't share deeds as I don't have physical
    access…"). So: the best `SequenceMatcher` ratio of the whole transcript
    against any word-window of the spoken sentence the same length as the
    transcript, max-combined with the whole-string ratio.
    """
    s = normalize(spoken)
    t = normalize(transcript)
    if not s or not t:
        return 0.0
    best = SequenceMatcher(None, s, t).ratio()
    sw = s.split()
    n = len(t.split())
    if 0 < n <= len(sw):
        for i in range(0, len(sw) - n + 1):
            window = " ".join(sw[i : i + n])
            best = max(best, SequenceMatcher(None, window, t).ratio())
    return best


def is_self_echo(
    transcript: str,
    spoken_texts: list[str],
    *,
    threshold: float = 0.8,
    min_words: int = 2,
) -> tuple[bool, float, str]:
    """`(is_echo, score, matched_spoken)` — does `transcript` fuzzy-match
    anything the bot recently said?

    A one-word transcript is only ever treated as an echo on an *exact* word
    match against a spoken span — fuzzy-suppressing a lone "stop"/"yes" risks
    eating a real user reply, and the loops we are killing are all >= 3 words.
    """
    t = normalize(transcript)
    if not t:
        return (False, 0.0, "")
    words = t.split()
    best_score = 0.0
    best_text = ""
    for spoken in spoken_texts:
        sc = echo_match_score(spoken, transcript)
        if sc > best_score:
            best_score, best_text = sc, spoken
    if len(words) < min_words:
        exact = any(t in normalize(s).split(" ") or f" {t} " in f" {normalize(s)} "
                    for s in spoken_texts)
        return (exact, best_score, best_text if exact else "")
    return (best_score >= threshold, best_score, best_text if best_score >= threshold else "")


# --------------------------------------------------------------------------- #
# self-echo rolling window + the two processors that share it                  #
# --------------------------------------------------------------------------- #


@dataclass
class SelfEchoWindow:
    """Recent bot utterances, newest last. Shared by the tap and the filter."""

    ttl_s: float = 12.0
    maxlen: int = 12
    _items: deque = field(default_factory=lambda: deque(maxlen=12))

    def add(self, text: str, *, now: float | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._items.append((text, now if now is not None else time.monotonic()))

    def recent(self, *, now: float | None = None) -> list[str]:
        now = now if now is not None else time.monotonic()
        return [txt for txt, ts in self._items if now - ts <= self.ttl_s]

    def clear(self) -> None:
        self._items.clear()


def build_echo_text_tap(window: SelfEchoWindow):
    """FrameProcessor placed just after the TTS service: it copies the text of
    every sentence the bot speaks into `window`, then forwards the frame
    untouched. `TTSTextFrame` covers streamed LLM answers; `TTSSpeakFrame`
    covers the canned IntentGate / WakeGate replies."""

    from pipecat.frames.frames import Frame, TTSSpeakFrame, TTSTextFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class EchoTextTap(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, (TTSTextFrame, TTSSpeakFrame)):
                window.add(getattr(frame, "text", "") or "")
            await self.push_frame(frame, direction)

    return EchoTextTap()


def build_self_echo_filter(window: SelfEchoWindow, *, threshold: float = 0.8,
                           min_words: int = 2, on_suppress=None):
    """FrameProcessor placed just after STT and before WakeGate. Drops any
    `TranscriptionFrame` that fuzzy-matches something in `window` — the bot
    hearing itself — and logs the suppression with its score (INVARIANTS #13).
    `on_suppress(text, score, matched)` is an optional test/metrics hook."""

    from pipecat.frames.frames import Frame, TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class SelfEchoFilter(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                spoken = window.recent()
                if spoken:
                    echo, score, matched = is_self_echo(
                        frame.text, spoken, threshold=threshold, min_words=min_words
                    )
                    if echo:
                        logger.info(
                            "self-echo suppressed: {!r} ~ {!r} (score {:.2f} >= {:.2f})",
                            frame.text, matched, score, threshold,
                        )
                        if on_suppress is not None:
                            try:
                                on_suppress(frame.text, score, matched)
                            except Exception:
                                pass
                        return  # drop — nothing reaches WakeGate / IntentGate / LLM

            await self.push_frame(frame, direction)

    return SelfEchoFilter()


# --------------------------------------------------------------------------- #
# half-duplex gate (+ optional wake-gated barge-in)                            #
# --------------------------------------------------------------------------- #


class AsrWakeProbe:
    """Wake-phrase detector for the muted audio during playback (Deliverable 3).

    Fed the raw int16 PCM frames the gate would otherwise drop; every
    `hop_ms` of accumulated audio it transcribes the last `window_s` seconds
    through the same ASR backend the pipeline uses and scores the transcript
    against the wake phrases. `threshold` is deliberately stricter than the
    wake gate's asleep threshold — a false accept here cuts the bot off
    mid-sentence.

    EXPERIMENTAL: the threshold is a guess until `wellsy tune-wake` runs
    against fixtures recorded *with speakers playing* (step 4 owes the
    fixtures; step 4c owes the during-playback false-accept measurement).
    """

    def __init__(self, asr, phrases: list[str], *, sample_rate: int = 16000,
                 threshold: float = 0.85, window_s: float = 1.6, hop_ms: int = 320):
        self._asr = asr
        self._phrases = phrases
        self._sr = sample_rate
        self._threshold = threshold
        self._window = int(window_s * sample_rate)
        self._hop = int(hop_ms / 1000 * sample_rate)
        self._buf = bytearray()
        self._since_hop = 0

    def reset(self) -> None:
        self._buf.clear()
        self._since_hop = 0

    def feed(self, pcm_bytes: bytes) -> bool:
        """Returns True when a wake phrase is detected in the recent audio."""
        import numpy as np

        from engine.voice.wake import is_wake

        self._buf.extend(pcm_bytes)
        self._since_hop += len(pcm_bytes) // 2
        keep = self._window * 2
        if len(self._buf) > keep:
            del self._buf[: len(self._buf) - keep]
        if self._since_hop < self._hop or len(self._buf) < self._sr:  # need >= ~0.5 s
            return False
        self._since_hop = 0

        pcm = np.frombuffer(bytes(self._buf), dtype=np.int16).astype(np.float32) / 32768.0
        text = ""
        try:
            for out in self._asr.stream(iter([pcm])):
                text = out.text or text
        except Exception:
            return False
        return bool(text) and is_wake(text, self._phrases, self._threshold)


def build_half_duplex_gate(*, tail_ms: int = 400, mode: str = "mute",
                           wake_probe: AsrWakeProbe | None = None, on_transition=None):
    """Return the HalfDuplexGate FrameProcessor. Place it immediately after
    `transport.input()`.

    `mode`:
      * ``"mute"``  (default) — drop mic audio while the bot speaks + `tail_ms`.
        Restores the pre-rebuild parity; open-air usable today.
      * ``"wake_gated"`` — same, but run `wake_probe` on the dropped audio and
        emit an `InterruptionFrame` if it hears the wake phrase. EXPERIMENTAL.
      * ``"full"`` — never mute (the step-4 behaviour; known to loop on
        speakers without AEC). For A/B measurement only.

    `tail_ms` covers the room's reverb decay after the last output sample.
    `on_transition(muted: bool)` is an optional test/metrics hook. The
    transition is logged once per edge, never per frame (INVARIANTS #13).
    """

    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        Frame,
        InputAudioRawFrame,
        InterruptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    _DROP_WHILE_MUTED = (InputAudioRawFrame,)

    class HalfDuplexGate(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._muted = False
            self._bot_speaking = False
            self._unmute_handle = None

        async def cleanup(self) -> None:
            if self._unmute_handle is not None:
                self._unmute_handle.cancel()
                self._unmute_handle = None
            await super().cleanup()

        def _set_muted(self, value: bool) -> None:
            if value == self._muted:
                return
            self._muted = value
            logger.info("half-duplex: mic {}", "MUTED (bot speaking)" if value else "unmuted")
            if on_transition is not None:
                try:
                    on_transition(value)
                except Exception:
                    pass

        def _cancel_unmute(self) -> None:
            if self._unmute_handle is not None:
                self._unmute_handle.cancel()
                self._unmute_handle = None

        def _schedule_unmute(self) -> None:
            self._cancel_unmute()
            if tail_ms <= 0:
                self._set_muted(False)
                return
            loop = self.get_event_loop()
            self._unmute_handle = loop.call_later(tail_ms / 1000.0, self._on_tail_elapsed)

        def _on_tail_elapsed(self) -> None:
            self._unmute_handle = None
            if not self._bot_speaking:
                self._set_muted(False)
                if wake_probe is not None:
                    wake_probe.reset()

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, BotStartedSpeakingFrame):
                self._bot_speaking = True
                self._cancel_unmute()
                if mode != "full":
                    self._set_muted(True)
                await self.push_frame(frame, direction)
                return

            if isinstance(frame, (BotStoppedSpeakingFrame, InterruptionFrame)):
                self._bot_speaking = False
                if self._muted:
                    self._schedule_unmute()
                await self.push_frame(frame, direction)  # never swallow the stop path
                return

            if self._muted and isinstance(frame, _DROP_WHILE_MUTED):
                if mode == "wake_gated" and wake_probe is not None:
                    try:
                        if wake_probe.feed(frame.audio):
                            logger.info("half-duplex: wake phrase heard during playback -> interrupt")
                            wake_probe.reset()
                            await self.push_frame(InterruptionFrame(), direction)
                    except Exception:
                        pass
                return  # drop the mic frame — VAD/STT never see the playback

            await self.push_frame(frame, direction)

    return HalfDuplexGate()
