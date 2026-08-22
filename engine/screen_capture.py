"""On-demand screen capture — day11-prompt.md Part 2, the first genuinely
new perception source since Day 1 (spec §23, previously at zero).

**Never continuous.** This is called exactly once, synchronously, when a
question is routed to the screen instead of the camera — see
`query_loop.py`'s `_SCREEN_KEYWORDS` routing. There is no loop, no timer, no
background thread here; the whole module is one function.

**Privacy, stated plainly (day11-prompt.md's own instruction: say it, don't
just do it):** the screen is captured only on an explicit request that
routes here, the resulting image is held in memory only for the one VLM call
that answers the question, and it is never written anywhere durable — the
brief second on disk (below) is deleted before this function returns, and
nothing about the screen's content is retained beyond the JSONL provenance
line's minimal, purely factual reference (`frameSource: "screen"`), same
policy as every other answer.

**Why a temp file at all, and why it lives in `engine/clips/` and not
`/tmp`:** macOS's `screencapture -x` (silent, no shutter sound, no user
interaction) writes to a path, not stdout — there is no in-memory capture
API exposed to a plain CLI call. day11-prompt.md's boundary rule is explicit
that nothing routes through `/tmp` in this project, so the scratch file
lands inside the repo's already-gitignored `clips/` directory (same as
every other per-run artifact this project writes) and is deleted
immediately after `cv2.imread` loads it into memory.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

CLIPS_DIR = Path(__file__).parent / "clips"
_SCRATCH_PATH = CLIPS_DIR / "_screen_capture_scratch.png"


class ScreenCaptureError(RuntimeError):
    pass


def capture_screen() -> np.ndarray:
    """Runs `screencapture -x` (silent, whole main display) and returns a
    BGR frame, same shape/dtype as `capture.py`'s camera frames so the VLM
    call site doesn't need to know which source it got. Raises
    `ScreenCaptureError` on failure (e.g. Screen Recording permission not
    yet granted for this process — a separate macOS TCC grant from the
    camera/mic ones already tracked in decisions.md) rather than returning
    a blank frame, so a caller never silently answers about a black screen."""
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["screencapture", "-x", str(_SCRATCH_PATH)],
        capture_output=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise ScreenCaptureError(
            f"screencapture exited {result.returncode}: {result.stderr.decode(errors='replace')}"
        )
    if not _SCRATCH_PATH.exists():
        raise ScreenCaptureError(
            "screencapture reported success but wrote no file -- check Screen "
            "Recording permission (System Settings -> Privacy & Security -> "
            "Screen Recording) for whichever process is running the engine."
        )
    try:
        frame = cv2.imread(str(_SCRATCH_PATH))
        if frame is None:
            raise ScreenCaptureError(f"cv2 could not decode {_SCRATCH_PATH}")
        return frame
    finally:
        _SCRATCH_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    t0 = time.monotonic()
    f = capture_screen()
    print(f"captured {f.shape[1]}x{f.shape[0]} in {(time.monotonic() - t0) * 1000:.1f}ms")
