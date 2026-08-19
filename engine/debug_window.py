"""Filmable debug window: reads the engine's own JSONL output (main.py's
stdout) and draws boxes/labels on top of the live camera feed.

Deliberately ugly — day8-prompt.md calls this scaffolding, not product.
The point is provenance: every box on screen came from the same JSONL a
future WebSocket client (Day 9) will consume, not a separate drawing path.

This does NOT re-run the model — it duplicates the camera open (a second
`cv2.VideoCapture`) so the window can show frames at native rate while
`main.py`'s detections stream in asynchronously over stdin, matched by
nearest timestamp. Two opens of the same camera index works on macOS
AVFoundation for read-only preview; if it doesn't on your hardware, run
main.py first to confirm it detects, then treat this purely as a labeled
recording of that JSONL against a screen-recorded window instead.

Usage:
    uv run main.py --seconds 60 | uv run debug_window.py
"""

from __future__ import annotations

import json
import sys
import threading
import time

import cv2

latest_record: dict | None = None
lock = threading.Lock()


def read_stdin_loop() -> None:
    global latest_record
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        with lock:
            latest_record = record


def main() -> None:
    reader = threading.Thread(target=read_stdin_loop, daemon=True)
    reader.start()

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("[debug_window] could not open camera for preview — is main.py already holding it?", file=sys.stderr)
        return

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            with lock:
                record = latest_record

            if record is not None:
                for t in record.get("tracks", []):
                    x, y, w, h = t["bbox"]
                    x, y, w, h = int(x), int(y), int(w), int(h)
                    color = (0, 200, 255) if t["label"] != "UNIDENTIFIED" else (0, 0, 255)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    label = f"{t['label']} #{t['id']} score={t['score']:.2f} votes={t['labelConfidence']:.0%}"
                    cv2.putText(frame, label, (x, max(0, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
                status = f"gated={record.get('gated')} motion={record.get('motion'):.3f} inferMs={record.get('inferenceMs')}"
                cv2.putText(frame, status, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.imshow("yap-engine debug (ugly on purpose)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
