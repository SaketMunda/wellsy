"""One-off probe, not part of the shipped engine: connects to the bridge and
reports message rate + payload size + a sample. Used to verify day9-prompt.md
Part 2 row 2 without a browser in the loop.
"""

import json
import socket
import sys
import time

from websockets.sync.client import connect

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

# Confirm the port refuses non-localhost first — bind check for D35.
try:
    s = socket.create_connection(("0.0.0.0", port), timeout=0.5)
    s.close()
    print("[probe] WARNING: bound on 0.0.0.0 too?", file=sys.stderr)
except Exception as e:
    print(f"[probe] 0.0.0.0 connect failed as expected: {e}", file=sys.stderr)

with connect(f"ws://127.0.0.1:{port}") as ws:
    n = 0
    sizes = []
    t0 = time.monotonic()
    sample = None
    while time.monotonic() - t0 < duration:
        msg = ws.recv(timeout=2.0)
        sizes.append(len(msg))
        if sample is None:
            sample = json.loads(msg)
        n += 1
    elapsed = time.monotonic() - t0
    print(f"[probe] {n} messages in {elapsed:.2f}s = {n / elapsed:.2f} msg/s")
    print(f"[probe] payload bytes: mean={sum(sizes) / len(sizes):.0f} min={min(sizes)} max={max(sizes)}")
    print(f"[probe] sample keys: {sorted(sample.keys())}")
    print(f"[probe] sample sourceWidth/Height: {sample.get('sourceWidth')}x{sample.get('sourceHeight')}")
