# Day 8 results

Detector: YOLOE (`yoloe-11s-seg.pt`) via Ultralytics on PyTorch/MPS — see
`decisions.md` D30 for why MLX was dropped (no PyPI package implements an
open-vocabulary detector on MLX; checked, not assumed) and D31 for the
tracker (ByteTrack via `supervision`). Machine: same Apple Silicon (M-series)
machine as `day7-baseline.md`.

**No camera access in this session** (sandboxed environment, no display, no
hardware camera). Everything below the fold that needed real footage —
the intermittent-motion test, the bed/microphone shot — used a staged
synthetic clip (`engine/capture.py`'s `make_intermittent_synthetic_frame`)
instead. That's flagged inline everywhere it applies; it is explicitly not
the same evidence a real clip would produce, per D32.

## Measurement table

| # | Metric | Result | vs. baseline |
|---|--------|--------|---------------|
| 1 | Unthrottled detection FPS | **76.4 FPS** (mean 13.1ms/frame, p50 12.8ms, p95 16.3ms, 640×480, warm model, MPS) | `v2-architecture-research.md`'s 124.9 FPS was never measured against this model variant/input size/machine — **superseded, not confirmed**, and lower |
| 2 | Detection ms/frame at 8Hz (in-loop, incl. tracker) | p50 **36.3ms**, p95 **45.2ms** (n=85, first-frame 347ms warmup spike excluded) | Higher than isolated unthrottled inference (12.8ms p50) — the gap is real pipeline overhead (ByteTrack update, prompt-reload stat() check, process contention with the capture worker), not just the model. Well inside the 125ms/frame budget for 8Hz either way |
| 3 | Idle CPU, gate **on** (T1 present, motion gate closed) | **~6-8%** (summed across main + capture process, `ps %cpu`) | Day 7's browser-build floor was **72.4-72.7%** of one core (scenarios A/E, `day7-baseline.md`) — different runtime and measurement method, not a controlled A/B, but the gap is large enough to be the headline anyway |
| 4 | Idle CPU, gate **forced off** (T1 runs every frame regardless of motion) | **~18-23%** | Isolates what the gate itself buys on this pipeline: roughly 3x lower CPU during a still period with the gate on vs off |
| 5 | Gated fraction + missed-motion frames, intermittent clip | Gated **71.8%** over 912 frames (35s: 3s enter, 20s frozen, 12s move-again). 130 frames inside the nominal "moving" windows were still gated | Almost all 130 cluster at the synthetic sine wave's zero-velocity turning points (true frame-to-frame pixel displacement is genuinely ~0 there even though the object is nominally "moving") — an artifact of a sinusoidal test signal, not a demonstrated gate defect. **Not equivalent to a real missed-motion measurement** — see D32 |
| 6 | Motion gate cost after capture-resolution change | **Not attempted** (build-order item 8, cut for time) | Still Day 7's numbers: synthetic p50 0.25ms / real-camera p50 1.31ms — unchanged, still borrowed from Day 7, not re-measured |
| 7 | End-to-end capture→track latency | p50 **74.8ms**, p95 **84.5ms** (captureMs + gateMs + inferenceMs, synthetic clip, n=86) | This is what Day 9's WebSocket bridge inherits as its floor before any network/render latency on top |

## Other checks

- **Memory over a long run:** `uv run main.py --synthetic --seconds 300`
  (5 minutes). RSS held at **~1.18GB** from shortly after model load through
  the full run (1,186,064 KB at ~3s in, 1,205,600-1,206,208 KB from ~3.5min
  onward) — the ~20MB early rise is allocator warmup, not a leak; flat
  after that. Most of the 1.18GB is the loaded model + MobileCLIP text
  encoder, not accumulated per-frame state.
- **Kill-capture-process test:** killed the `multiprocessing` capture
  worker (SIGKILL) mid-run. `main.py` did not hang or crash — it logged
  `[warn] no frame in 2s` on the expected 2s cadence and stayed alive for
  the rest of its `--seconds` budget (D29's queue-timeout path, now
  actually exercised with a genuinely slow/dead producer for the first
  time since T1 exists). One caveat found and fixed procedurally, not in
  code: killing the *wrong* PID (`main.py` itself, not its child) leaves
  the capture subprocess **orphaned and still running** — SIGKILL to a
  parent can't trigger any cleanup path in any language, so this isn't a
  code bug, but it's worth knowing for Day 9+ testing: always kill the
  capture child, not the parent, or you'll leak a background process.
- **`--synthetic` headless run:** works, unchanged interface.
- **`git status`:** confined to `engine/` and `.claude/` (see final report).

## Bed / microphone shot

**Not shot.** No camera access in this session — `engine/debug_window.py`
(the `cv2.imshow` overlay) is written but untested against a live camera or
display, both of which this sandboxed session lacks. The prompt-list
mechanism it depends on (`prompts.txt` → `detector.set_prompts()`) is
exercised and confirmed working on synthetic frames (see `main.py --synthetic`
runs above, where `microphone`, `bed`, etc. are live prompt classes for
every predict call) — the missing piece is a real bed and a real microphone
in front of a real camera, which needs to happen in a follow-up session on
hardware, or be handed to the person actually holding the camera.
