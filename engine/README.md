# yap-engine

`camera → motion gate (T0) → detect+track (T1) → JSON lines on stdout`. T2
(deep look) and T3 (respond) exist as wired stubs (`tiers.py`) with no
behavior yet. No HUD, no WebSocket — that's Day 9. See
`.claude/day8-prompt.md` and `decisions.md` D28-D32.

## Run it

```
cd engine
uv run main.py --seconds 60                  # real camera, detection on
uv run main.py --synthetic                   # no camera needed — generated frame
uv run main.py --no-detect                   # T0 only (Day 7 behavior) — isolates gate cost
uv run main.py --synthetic-intermittent --seconds 35   # staged enter/hold-still-20s/move-again clip

uv run main.py --seconds 60 | uv run debug_window.py   # filmable cv2.imshow overlay
```

Add `--camera-index N` to pick a different camera. Drop `--seconds` to run
until Ctrl+C.

## Prompts (open-vocabulary detection)

`prompts.txt` is a plain list, one term per line, `#`-comments allowed.
Edit it while `main.py` is running — it's picked up on the next detection
pass, no restart needed (checked via file mtime each time T1 is about to
run; the check itself is a stat() call, not a re-read, so it's cheap even
at 8Hz). This is the actual fix for the browser build's fixed-80-class
ceiling (decisions.md D2/D30): add a word here and the model can name it,
no threshold or voting scheme required.

## JSONL shape

```
{
  "t": <unix seconds>,
  "motion": <0..1>,
  "gated": <bool>,
  "captureMs": <float>,
  "gateMs": <float>,
  "detections": [{"label": str, "score": 0..1, "bbox": [x, y, w, h]}, ...],
  "tracks": [{"id": int, "label": str, "score": float, "bbox": [x,y,w,h],
              "ageMs": float, "missedFrames": int, "labelConfidence": 0..1,
              "runnerUpLabel": str|null, "labelVotes": {label: count}}, ...],
  "inferenceMs": <float|null>   // null on frames T1 didn't run this tick
}
```

`tracks`/`detections` are **re-emitted unchanged** on frames where T1 was
gated or rate-limited — a still scene keeps showing what was last seen
instead of going empty (the correctness trap day8-prompt.md calls out
explicitly). `inferenceMs` being `null` is how a consumer tells "T1 ran
this frame" from "T1 didn't, this is a repeat."

A `[gated-fraction] ...` line lands on **stderr** every 30 frames — keep
stdout pure JSONL if you're piping it anywhere (`debug_window.py` does).

The first real-camera run on a fresh macOS install will trigger the system
camera-permission prompt for whatever process hosts this shell — grant it
once in System Settings → Privacy & Security → Camera, then re-run.

## Model weights (not in the repo)

YOLOE's detector weights (`yoloe-11s-seg.pt`, ~28MB) and its MobileCLIP
text-prompt encoder (`mobileclip_blt.ts`, ~570MB) download on first use to
`~/.cache/yap-engine/weights` — outside the repo, per the boundary in
day8-prompt.md ("nothing large or generated belongs in git"; the HuggingFace
cache dir exception in that doc applies the same way here, just a different
cache root since these come from Ultralytics' own asset host, not HF).
`detector.py`'s `configure_weights_cache()` points Ultralytics' settings at
that directory and `chdir`s into it before the first load, because
Ultralytics' downloader falls back to the current working directory for
anything not already found at an absolute path or in its settings dir —
without this, weights land back in `engine/` (this was caught and fixed
this session; see D30). Day 15's packaging should point this at wherever
the shipped app's model cache lives.
