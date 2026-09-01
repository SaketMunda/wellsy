# WELLSY

A local, private, agentic assistant. Runs on your own hardware; no third-party
cloud service ever receives pixels, audio, or raw personal files.

It began as a browser-based perception HUD under a different name and is being
rebuilt (`~70%` rewrite) around a preserved perception core — see
`.claude/stack-teardown.md` for the audit and `.claude/rebuild/` for the
step-by-step plan. The `.claude/` day 1–11 documents describe that earlier
build and deliberately still refer to it by its old name.

## Status

**Step 1 of 6 — repo reset + perception core port.** What runs today:

```
camera → motion gate (T0) → open-vocab detect + track (T1) → JSON lines on stdout
```

The voice path, screen capture, native interface, and agent runtime are rebuilt
in later steps as clients of the runtime, not part of it.

## Run it

```bash
uv sync
uv run wellsy --help
uv run wellsy --seconds 60          # real camera, perception loop, exits cleanly
uv run wellsy --synthetic --seconds 20 --debug   # no camera; per-frame JSONL
```

First real-camera run on macOS triggers the system camera-permission prompt for
whatever process hosts the shell — grant it once in
System Settings → Privacy & Security → Camera.

## Layout

```
engine/           the import package (runtime core); `pip install wellsy` → `import engine`
  perception/     motion.py  detector.py  tracker.py  capture.py
  runtime/        tiers.py           # T0–T3 scheduler + PreemptionSeam
  honesty/        provenance.py  intent.py
  config/         prompts.txt  wake_phrases.txt
  cli.py                            # the `wellsy` console entry point
tests/            one module per surviving unit
bench/            detector_bench.py  # perception no-regression benchmark
spec/             phase1-acceptance.md — the definition of done
.claude/          planning docs, rebuild steps, and the pre-rebuild build log
```

## Model weights (not in the repo)

YOLOE's detector (`yoloe-11s-seg.pt`, ~28 MB) and its MobileCLIP text-prompt
encoder (`mobileclip_blt.ts`, ~570 MB) live at `~/.cache/wellsy/weights`,
outside the repo. `detector.py` points Ultralytics' settings there and `chdir`s
into it before the first load.

## Open-vocabulary prompts

`engine/config/prompts.txt` is a plain list, one term per line, `#`-comments
allowed. Edit it while `wellsy` is running — it's picked up on the next
detection pass via an mtime check, no restart needed.
