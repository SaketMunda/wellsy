"""Capture-in-the-voice-loop — turn a routed vision intent into pixels the VLM
can actually receive.

`describe_scene` / `query_object` transcripts (from `honesty/intent.py`) reach
here via `IntentGate`. This module decides *which* surface the question is about
— the room, through the camera; or the screen — captures it once through the
step-3 capture layer, and returns a verified frame plus its provenance.

**INVARIANTS #6 / #15 — an unverified capture never reaches the model.** Both
`capture_screen()` and `capture_camera()` already `raise CaptureError` (with a
spoken remedy) instead of returning a degenerate frame; nothing here softens
that. `IntentGate` catches the error, speaks the remedy, and forwards nothing.

Screen-vs-camera routing lives here, not in `honesty/intent.py`. `intent.py`
stays a safety-only grammar (`stop` / `wake` / `sleep`); routing the wrong
capture surface is a wrong-but-harmless answer, not a safety event
(`.claude/system-state.md` §4.3, `decisions.md` D39).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from engine.capture import CaptureError, CaptureResult, capture_camera, capture_screen

# Phrases that mean "the screen", checked before any capture runs. Plain
# "what do you see" with no screen cue defaults to the camera (the room).
_SCREEN_CUES = re.compile(
    r"\bon[ -]?screen\b"
    r"|\b(my|the|this|your) (screen|monitor|display|desktop)\b"
    r"|\b(screen|monitor|display|desktop)\b"
    r"|\bon (my|the|this) (computer|laptop|mac|macbook|pc)\b"
)

JPEG_QUALITY = 85


def route(transcript: str) -> str:
    """`"screen"` or `"camera"` — which surface the question is about."""
    return "screen" if _SCREEN_CUES.search((transcript or "").lower()) else "camera"


@dataclass(frozen=True)
class VisionCapture:
    """A verified capture, ready to hand to the VLM."""

    result: CaptureResult
    frame_source: str            # "camera" | "screen"
    jpegs: list[bytes]           # one per display (screen) or one (camera), JPEG q85
    size: tuple[int, int]        # (w, h) of the primary frame
    captured_at: float

    def provenance(self) -> dict:
        """`CaptureResult.provenance()` — folded into the per-answer line by
        `honesty/provenance.log_answer(capture=...)`."""
        return self.result.provenance()


@dataclass
class VisionPending:
    """Shared hand-off between `IntentGate` (which captured the frame) and the
    provenance logger (which sees the VLM's answer). `IntentGate` arms it after
    a verified capture; the logger writes one `provenance.log_answer` line when
    the LLM response ends, then disarms. Also carries the context message that
    holds the image so the logger can drop it afterwards — screen/camera
    content is retained only as a provenance line, never kept in context
    (step 3 "on-demand only", `system-state.md` §4.3)."""

    transcript: str = ""
    frame_source: str = ""
    capture_provenance: dict | None = None
    captured_at: float = 0.0
    armed_at: float = 0.0
    image_message: object | None = None

    @property
    def armed(self) -> bool:
        return self.capture_provenance is not None

    def arm(self, cap: "VisionCapture", transcript: str, image_message: object) -> None:
        self.transcript = transcript
        self.frame_source = cap.frame_source
        self.capture_provenance = cap.provenance()
        self.captured_at = cap.captured_at
        self.armed_at = time.time()
        self.image_message = image_message

    def disarm(self) -> None:
        self.transcript = ""
        self.frame_source = ""
        self.capture_provenance = None
        self.captured_at = 0.0
        self.armed_at = 0.0
        self.image_message = None


def _to_jpeg(frame_bgr) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        raise CaptureError(
            "Could not JPEG-encode a verified frame.",
            remedy="cv2.imencode failed on an already-verified frame — a bug, not a permission problem.",
            spoken="Something went wrong preparing what I saw.",
        )
    return bytes(buf)


def capture_for_intent(transcript: str) -> VisionCapture:
    """Capture the surface `transcript` asks about. Raises `CaptureError`
    (never returns a degenerate frame) — the caller speaks `err.spoken`."""
    frame_source = route(transcript)
    result: CaptureResult = capture_screen() if frame_source == "screen" else capture_camera()
    # Multi-monitor: every verified display goes to the model, primary first
    # (step 3 "real multi-monitor fix"). A camera capture has exactly one frame.
    frames = result.frames or [result.primary]
    primary = result.primary
    return VisionCapture(
        result=result,
        frame_source=frame_source,
        jpegs=[_to_jpeg(f.image) for f in frames],
        size=(primary.width, primary.height),
        captured_at=time.time(),
    )
