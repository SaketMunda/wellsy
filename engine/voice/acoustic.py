"""`wellsy voice --measure-acoustic` — the numbers step 4b owes that can only
come from a live session: **at the audio device, from speech onset**, not
composed from component stages (that is `metrics.py --measure`).

What it measures, per real spoken turn, all on the Pipecat pipeline clock:

  * **wake / speech onset -> first bot PCM at the output** — the first
    `TTSAudioRawFrame` handed to `transport.output()` for the device write
    (sub-audio-buffer ahead of the PortAudio write itself, ~10-20 ms; stated,
    not hidden). Split by path: deterministic / LLM / VLM, via the IntentGate
    decision. Cold (first of each path) is reported separately from warm.
  * **A14 barge-in** — a second speech onset while the bot is speaking ->
    output silent (`BotStoppedSpeakingFrame` / `InterruptionFrame`). The
    interrupted turn is recorded `interrupted: true`, never as delivered.
  * **`stop` -> output ceased** — the deterministic InterruptionFrame path:
    the "stop" transcript -> output silent, wall time at the device.

Run it, speak the runbook's utterances, then Ctrl+C: a summary table prints and
`spec/results/voice-acoustic-<date>.json` is written with every raw sample so
p50/p95 are reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    LLMRunFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

from engine.honesty.intent import parse_intent

RESULTS_DIR = Path(__file__).resolve().parents[2] / "spec" / "results"
_NS = 1_000_000_000


def _ns_to_ms(ns: int | None) -> float | None:
    return None if ns is None else round(ns / 1_000_000, 1)


@dataclass
class Turn:
    onset_ns: int
    path: str = "unknown"          # "deterministic" | "llm" | "vlm"
    transcript: str = ""
    first_audio_ns: int | None = None
    bot_stopped_ns: int | None = None
    interrupted: bool = False
    # barge-in: this turn's speech onset landed while a previous turn's bot
    # audio was still playing
    is_bargein: bool = False
    prev_silence_ns: int | None = None   # when the interrupted output went silent

    @property
    def first_word_ms(self) -> float | None:
        if self.first_audio_ns is None:
            return None
        return _ns_to_ms(self.first_audio_ns - self.onset_ns)

    @property
    def bargein_ms(self) -> float | None:
        if not self.is_bargein or self.prev_silence_ns is None:
            return None
        return _ns_to_ms(self.prev_silence_ns - self.onset_ns)


class LatencyObserver(BaseObserver):
    """Timestamps the live pipeline. Attach via `PipelineWorker(observers=[...])`."""

    def __init__(self) -> None:
        super().__init__()
        self.turns: list[Turn] = []
        self._open: Turn | None = None
        self._bot_speaking: bool = False
        self._last_decision_path: str | None = None

    # IntentGate calls this (pipeline `on_decision` hook) before the model runs.
    def on_decision(self, decision, transcript: str) -> None:
        self._last_decision_path = {
            "canned": "deterministic",
            "sleep": "deterministic",
            "vision": "vlm",
            "forward": "llm",
        }.get(decision.action, decision.action)

    async def on_push_frame(self, data: FramePushed) -> None:
        f = data.frame
        ts = data.timestamp  # pipeline clock, ns

        if isinstance(f, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            # New user turn. If the bot is still speaking, this is a barge-in.
            if self._open is not None and self._open.first_audio_ns is not None:
                # previous turn already producing audio and not yet closed
                pass
            t = Turn(onset_ns=ts)
            if self._bot_speaking and self.turns:
                t.is_bargein = True
                self.turns[-1].interrupted = True
            self._open = t
            self.turns.append(t)
            return

        if isinstance(f, TranscriptionFrame) and data.direction == FrameDirection.DOWNSTREAM:
            if self._open is not None and not self._open.transcript:
                self._open.transcript = f.text or ""
                self._open.path = self._last_decision_path or _classify(f.text)
                self._last_decision_path = None
            return

        if isinstance(f, LLMRunFrame) and self._open is not None:
            # IntentGate emits this for a verified vision turn.
            self._open.path = "vlm"
            return

        if isinstance(f, TTSSpeakFrame) and self._open is not None and not self._open.transcript:
            # canned reply straight from IntentGate (help / presence / thanks / sleep)
            self._open.path = "deterministic"
            return

        if isinstance(f, TTSAudioRawFrame) and data.direction == FrameDirection.DOWNSTREAM:
            if self._open is not None and self._open.first_audio_ns is None:
                self._open.first_audio_ns = ts
            return

        if isinstance(f, BotStartedSpeakingFrame):
            self._bot_speaking = True
            return

        if isinstance(f, (BotStoppedSpeakingFrame, InterruptionFrame)):
            was_speaking = self._bot_speaking
            self._bot_speaking = False
            # close the most recent turn that had audio
            for t in reversed(self.turns):
                if t.first_audio_ns is not None and t.bot_stopped_ns is None:
                    t.bot_stopped_ns = ts
                    break
            # a barge-in / stop turn: record when the *interrupted* output silenced
            if was_speaking:
                for t in reversed(self.turns):
                    if (t.is_bargein or _is_stop(t.transcript)) and t.prev_silence_ns is None:
                        t.prev_silence_ns = ts
                        break
            return


def _classify(transcript: str) -> str:
    it = parse_intent(transcript).type
    if it in ("help", "presence", "thanks", "sleep"):
        return "deterministic"
    if it in ("describe_scene", "query_object"):
        return "vlm"
    return "llm"


def _is_stop(transcript: str) -> bool:
    return parse_intent(transcript).type == "stop"


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))], 1)


def _summary(turns: list[Turn]) -> dict:
    by_path: dict[str, list[Turn]] = {}
    for t in turns:
        by_path.setdefault(t.path, []).append(t)

    first_word = {}
    for path, ts in by_path.items():
        warm = [t.first_word_ms for t in ts[1:] if t.first_word_ms is not None]
        cold = ts[0].first_word_ms if ts else None
        first_word[path] = {
            "n_warm": len(warm),
            "cold_ms": cold,
            "p50_ms": _pct(warm, 50),
            "p95_ms": _pct(warm, 95),
        }

    bargein = [t.bargein_ms for t in turns if t.bargein_ms is not None]
    stop_ms = [
        _ns_to_ms(t.prev_silence_ns - t.onset_ns)
        for t in turns
        if _is_stop(t.transcript) and t.prev_silence_ns is not None
    ]
    interrupted = [t for t in turns if t.interrupted]

    return {
        "wake_to_first_word": first_word,
        "barge_in": {
            "n": len(bargein),
            "p50_ms": _pct(bargein, 50),
            "p95_ms": _pct(bargein, 95),
            "target_ms": {"p50": 200, "p95": 350},
            "interrupted_turns_recorded": len(interrupted),
        },
        "stop": {
            "n": len(stop_ms),
            "p50_ms": _pct([x for x in stop_ms if x is not None], 50),
            "p95_ms": _pct([x for x in stop_ms if x is not None], 95),
            "target_ms": {"p50": 150, "p95": 250},
        },
        "method": (
            "pipeline-clock timestamps; first-word = first TTSAudioRawFrame into "
            "transport.output() (sub-buffer ahead of the PortAudio write, ~10-20 ms); "
            "onset = VAD/UserStartedSpeakingFrame; cold = first turn of each path"
        ),
    }


def write_results(obs: LatencyObserver) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"voice-acoustic-{date.today().isoformat()}.json"
    payload = {
        "date": date.today().isoformat(),
        "n_turns": len(obs.turns),
        "summary": _summary(obs.turns),
        "turns": [
            {
                "path": t.path,
                "transcript": t.transcript,
                "first_word_ms": t.first_word_ms,
                "is_bargein": t.is_bargein,
                "bargein_ms": t.bargein_ms,
                "interrupted": t.interrupted,
            }
            for t in obs.turns
        ],
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return out


def print_summary(obs: LatencyObserver) -> None:
    s = _summary(obs.turns)
    print("\n=== acoustic §1 (live, at the device) ===")
    print(f"{'path':<14} {'n':>3} {'cold ms':>9} {'p50 ms':>8} {'p95 ms':>8}")
    for path, r in s["wake_to_first_word"].items():
        print(f"{path:<14} {r['n_warm']:>3} {str(r['cold_ms']):>9} "
              f"{str(r['p50_ms']):>8} {str(r['p95_ms']):>8}")
    b = s["barge_in"]
    print(f"\nbarge-in: n={b['n']}  p50={b['p50_ms']} ms  p95={b['p95_ms']} ms  "
          f"(target {b['target_ms']['p50']}/{b['target_ms']['p95']})  "
          f"interrupted turns recorded: {b['interrupted_turns_recorded']}")
    st = s["stop"]
    print(f"stop:     n={st['n']}  p50={st['p50_ms']} ms  p95={st['p95_ms']} ms  "
          f"(target {st['target_ms']['p50']}/{st['target_ms']['p95']})")
    print(f"\nmethod: {s['method']}")
