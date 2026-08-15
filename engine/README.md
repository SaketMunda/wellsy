# yap-engine

Day 7 skeleton: `camera → motion gate → JSON lines on stdout`. No model, no
tracker, no HUD, no WebSocket yet — see `.claude/day7-prompt.md` and
`decisions.md` D28/D29.

## Run it

```
cd engine
uv run main.py --seconds 60        # real camera
uv run main.py --synthetic         # no camera needed — generated frame
```

Add `--camera-index N` to pick a different camera. Drop `--seconds` to run
until Ctrl+C.

Each line on stdout is one JSON record:
`{"t": <unix seconds>, "motion": <0..1>, "gated": <bool>, "captureMs": <float>, "gateMs": <float>}`.
A `[gated-fraction] ...` line lands on **stderr** every 30 frames — keep
stdout pure JSONL if you're piping it anywhere.

The first real-camera run on a fresh macOS install will trigger the system
camera-permission prompt for whatever process hosts this shell — grant it
once in System Settings → Privacy & Security → Camera, then re-run.
