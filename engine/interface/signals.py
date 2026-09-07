"""The SignalBus — the interface's single source of animated truth.

Every quantity the orb renders traces to a real runtime value pushed onto a
`Channel` here: VAD amplitude, output PCM amplitude, the agent's graph phase,
the policy gate's decision, the wake latch. Nothing is generated.

Design, matching INVARIANTS #4 (drop frames, never buffer): each `Channel` is
**depth-1, latest-wins**. A reader gets the most recent sample or nothing. A
slow reader misses intermediate samples; it never drains a backlog.

Staleness is a first-class concept. A `Channel` created with `stale_after`
reports `fresh()` only while its last sample is recent. `value_or(default)`
returns the default once stale — so "the mic stopped producing VAD frames"
becomes "amplitude decays to 0" becomes "not Listening", with no special-casing
at the call site and no way to fake liveness.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Generic, Iterator, TypeVar

T = TypeVar("T")

# Monotonic clock so samples are immune to wall-clock jumps. Injectable for
# tests via `SignalBus(clock=...)`.
Clock = "typing.Callable[[], float]"


@dataclass(frozen=True)
class Sample(Generic[T]):
    value: T
    ts: float  # monotonic seconds


class Channel(Generic[T]):
    """One depth-1 latest-wins signal.

    `stale_after` is seconds; `None` means the channel never goes stale (used
    for level latches like the wake state, which stay true until explicitly
    changed).
    """

    __slots__ = ("name", "stale_after", "_sample", "_lock", "_clock")

    def __init__(self, name: str, *, stale_after: float | None, clock=time.monotonic):
        self.name = name
        self.stale_after = stale_after
        self._sample: Sample[T] | None = None
        self._lock = threading.Lock()
        self._clock = clock

    def push(self, value: T, ts: float | None = None) -> None:
        s = Sample(value, self._clock() if ts is None else ts)
        with self._lock:
            self._sample = s

    def clear(self) -> None:
        with self._lock:
            self._sample = None

    def latest(self) -> Sample[T] | None:
        with self._lock:
            return self._sample

    def age(self, now: float | None = None) -> float | None:
        s = self.latest()
        if s is None:
            return None
        return (self._clock() if now is None else now) - s.ts

    def fresh(self, now: float | None = None) -> bool:
        a = self.age(now)
        if a is None:
            return False
        if self.stale_after is None:
            return True
        return 0.0 <= a <= self.stale_after

    def value_or(self, default: T, now: float | None = None) -> T:
        s = self.latest()
        if s is None or not self.fresh(now):
            return default
        return s.value


class SignalBus:
    """A named set of channels. Channels are declared up front so a typo at a
    push site is a `KeyError`, not a silently-ignored signal."""

    # (name, stale_after_seconds). Tuned against logs, not intuition (INVARIANTS
    # #13); these are the starting points recorded in step6-results.md.
    _SPEC: dict[str, float | None] = {
        # reactive amplitudes — short windows: one frame late and we are no
        # longer "listening"/"speaking". 120 ms ~ a few audio buffers.
        "vad_amplitude": 0.12,
        "tts_amplitude": 0.12,
        # agent graph phase: "idle" | "planning" | "acting". Held between node
        # transitions, so a longer window; the graph pushes on every change.
        "agent_phase": 8.0,
        # approval gate: "pending" while interrupt() is unanswered, cleared on
        # answer. Never auto-expires while genuinely blocked -> None.
        "approval": None,
        # a refusal just happened (denied tool / failed capture verification).
        # A brief latch so the orb can show it and settle.
        "refusal": 4.0,
        # wake latch: True/False. Level, not an event -> never stale.
        "wake": None,
        # last intent-gate decision action, for the HUD; not a state driver.
        "intent": 6.0,
    }

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._channels: dict[str, Channel[Any]] = {
            name: Channel(name, stale_after=sa, clock=clock)
            for name, sa in self._SPEC.items()
        }

    @property
    def clock(self):
        return self._clock

    def channel(self, name: str) -> Channel[Any]:
        return self._channels[name]

    def __iter__(self) -> Iterator[Channel[Any]]:
        return iter(self._channels.values())

    # ergonomic push helpers -------------------------------------------------- #

    def push_vad_amplitude(self, amplitude: float, ts: float | None = None) -> None:
        """The ONLY entry point for a listening amplitude. Called per live VAD
        frame with its RMS/energy. If this is not called, the orb cannot be in
        the Listening state — that is the honesty guarantee, enforced by test."""
        self._channels["vad_amplitude"].push(float(amplitude), ts)

    def push_tts_amplitude(self, amplitude: float, ts: float | None = None) -> None:
        """The ONLY entry point for a speaking amplitude — per output PCM
        chunk written to the device."""
        self._channels["tts_amplitude"].push(float(amplitude), ts)

    def set_agent_phase(self, phase: str, ts: float | None = None) -> None:
        assert phase in ("idle", "planning", "acting")
        self._channels["agent_phase"].push(phase, ts)

    def set_approval_pending(self, pending: bool, ts: float | None = None) -> None:
        if pending:
            self._channels["approval"].push("pending", ts)
        else:
            self._channels["approval"].clear()

    def mark_refusal(self, reason: str, ts: float | None = None) -> None:
        self._channels["refusal"].push(reason, ts)

    def set_wake(self, awake: bool, ts: float | None = None) -> None:
        self._channels["wake"].push(bool(awake), ts)

    def set_intent(self, action: str, ts: float | None = None) -> None:
        self._channels["intent"].push(action, ts)
