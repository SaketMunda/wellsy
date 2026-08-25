"""On-demand screen capture — day11-prompt.md Part 2, the first genuinely
new perception source since Day 1 (spec §23, previously at zero).

**Never continuous.** This is called exactly once, synchronously, when a
question is routed to the screen instead of the camera — see
`query_loop.py`'s `_SCREEN_KEYWORDS` routing. There is no loop, no timer, no
background thread here; the whole module is one function.

**Privacy, stated plainly (day11-prompt.md's own instruction: say it, don't
just do it):** the screen is captured only on an explicit request that
routes here, the resulting image(s) are held in memory only for the one VLM
call that answers the question, and they are never written anywhere durable
— the brief second on disk (below) is deleted before this function returns,
and nothing about the screen's content is retained beyond the JSONL
provenance line's minimal, purely factual reference (`frameSource:
"screen"`), same policy as every other answer.

**Real bug, found from a live report: it captured the wrong monitor.**
Asked to read a document open on a second display, this returned a shot of
the primary display's desktop wallpaper instead — a real screen, correctly
captured (the menu bar was visibly present), just not the one anything was
actually happening on. Root cause, from `man screencapture` itself, not
assumed: the tool's `files` argument is documented as **"1 file per
screen"** — passing a single output path, as the original version of this
function did, only ever captures the primary display. On any multi-monitor
setup this silently answers about the wrong screen every time.

**Fix: capture every attached display, hand all of them to the VLM.**
Rather than guess which display has the relevant window (fragile without
querying window-server state this project doesn't otherwise touch), this
now passes several candidate output paths to one `screencapture -x` call —
matching the tool's own documented multi-file behavior — and returns
whichever paths actually got written, in display order (1 = main, per
`-D`'s own numbering). `llm.py` sends all of them as separate images in the
same Ollama message; Qwen3-VL is told explicitly it may be seeing more than
one display. A single-monitor machine gets exactly one frame back, same as
before.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

CLIPS_DIR = Path(__file__).parent / "clips"

# Generous upper bound, not a real display-count detection -- macOS setups
# beyond 6 displays are rare enough that this is a reasonable ceiling
# rather than a hard limit worth the complexity of querying the real count
# first (e.g. via `system_profiler`, which is slow -- often 1s+).
MAX_DISPLAYS = 6
_SCRATCH_PATHS = [CLIPS_DIR / f"_screen_capture_scratch_{i}.png" for i in range(1, MAX_DISPLAYS + 1)]


class ScreenCaptureError(RuntimeError):
    pass


def capture_screen() -> list[np.ndarray]:
    """Runs one `screencapture -x` call with a file argument per possible
    display and returns a BGR frame per display that actually exists, in
    order (index 0 = main display). Same BGR/dtype shape as `capture.py`'s
    camera frames per element. Raises `ScreenCaptureError` if not even the
    main display could be captured (e.g. Screen Recording permission not
    yet granted for this process — a separate macOS TCC grant from the
    camera/mic ones already tracked in decisions.md) rather than returning
    an empty list, so a caller never silently answers about nothing."""
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["screencapture", "-x", *[str(p) for p in _SCRATCH_PATHS]],
        capture_output=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise ScreenCaptureError(
            f"screencapture exited {result.returncode}: {result.stderr.decode(errors='replace')}"
        )
    try:
        frames: list[np.ndarray] = []
        for path in _SCRATCH_PATHS:
            if not path.exists():
                break  # screencapture stops writing once it runs out of real displays
            frame = cv2.imread(str(path))
            if frame is not None:
                frames.append(frame)
        if not frames:
            raise ScreenCaptureError(
                "screencapture reported success but wrote no usable file -- check Screen "
                "Recording permission (System Settings -> Privacy & Security -> "
                "Screen Recording) for whichever process is running the engine."
            )
        return frames
    finally:
        for path in _SCRATCH_PATHS:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    t0 = time.monotonic()
    frames = capture_screen()
    elapsed = (time.monotonic() - t0) * 1000
    for i, f in enumerate(frames, start=1):
        print(f"display {i}: captured {f.shape[1]}x{f.shape[0]}")
    print(f"{len(frames)} display(s) in {elapsed:.1f}ms")
