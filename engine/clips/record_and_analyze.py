"""One-off: record a real clip from the real camera and replay motion.py's
gate against it directly, printing the mean-diff distribution — the actual
day8/day9-prompt.md ask, done for real this time. Not part of the shipped
engine.

Usage: uv run python clips/record_and_analyze.py [seconds]
"""
import sys
import time

sys.path.insert(0, "..")
import cv2
import numpy as np

sys.path.insert(0, ".")
from motion import motion_gate, to_gate_gray, MOTION_THRESHOLD

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
if not cap.isOpened():
    print("camera did not open")
    sys.exit(1)

ok, frame = cap.read()
h, w = frame.shape[:2]
writer = cv2.VideoWriter("real_clip.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))

prev_gray = None
diffs = []
t0 = time.monotonic()
n = 0
while time.monotonic() - t0 < seconds:
    ok, frame = cap.read()
    if not ok:
        continue
    writer.write(frame)
    gray = to_gate_gray(frame)
    if prev_gray is not None:
        raw_mean_diff = float(np.mean(cv2.absdiff(prev_gray, gray)))
        diffs.append(raw_mean_diff)
    prev_gray = gray
    n += 1

cap.release()
writer.release()

diffs = np.array(diffs)
gated_frac = float(np.mean(diffs < MOTION_THRESHOLD))
print(f"frames={n} duration={seconds}s")
print(f"raw mean-diff (0..255 scale): min={diffs.min():.3f} p50={np.percentile(diffs,50):.3f} "
      f"p95={np.percentile(diffs,95):.3f} max={diffs.max():.3f} mean={diffs.mean():.3f}")
print(f"current MOTION_THRESHOLD={MOTION_THRESHOLD}: gated_fraction={gated_frac:.1%}")
print("saved: engine/clips/real_clip.mp4")
