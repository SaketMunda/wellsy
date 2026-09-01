# WELLSY

A local, private, agentic assistant. Runs on your own hardware; no third-party
cloud service ever receives pixels, audio, or raw personal files.

It began as a browser-based perception HUD under a different name and is being
rebuilt (`~70%` rewrite) around a preserved perception core — see
`.claude/stack-teardown.md` for the audit and `.claude/rebuild/` for the
step-by-step plan. The `.claude/` day 1–11 documents describe that earlier
build and deliberately still refer to it by its old name.

## Status

**Step 4 of 6 — streaming voice path.** What runs today:

```
camera → motion gate (T0) → open-vocab detect + track (T1) → JSON lines on stdout
mic → VAD → ASR → deterministic intent gate → LLM → sentence-chunked TTS → speaker
```

The native interface and agent runtime are rebuilt in later steps as clients of
the runtime, not part of it.

## Run it

```bash
uv sync
uv run wellsy --help
uv run wellsy --seconds 60          # real camera, perception loop, exits cleanly
uv run wellsy --synthetic --seconds 20 --debug   # no camera; per-frame JSONL
uv run wellsy voice                 # streaming voice conversation (say "wellsy" to start)
uv run wellsy voice --measure       # the spec/phase1-acceptance.md §1 latency harness
```

First real-camera / real-mic run on macOS triggers the system permission prompt
for whatever process hosts the shell — grant it once in
System Settings → Privacy & Security. `wellsy doctor` reports which permissions
this process tree already has.

### System packages for the voice path

Two non-Python dependencies, installed once:

```bash
brew install portaudio espeak-ng      # macOS
# apt-get install portaudio19-dev espeak-ng   # Debian/Ubuntu
```

`portaudio` backs the cross-platform audio device (`LocalAudioTransport`);
`espeak-ng` is Kokoro's phonemiser. Silero VAD and Smart Turn v3 ship inside the
`pipecat-ai` wheel — no download.

## Layout

```
engine/           the import package (runtime core); `pip install wellsy` → `import engine`
  perception/     motion.py  detector.py  tracker.py  capture.py
  runtime/        tiers.py           # T0–T3 scheduler + PreemptionSeam
  honesty/        provenance.py  intent.py
  inference/      base.py registry.py  backends/   # portable ASR/TTS/LLM/VAD seam
  voice/          pipeline.py intent_gate.py wake.py adapters.py metrics.py
  config/         prompts.txt  wake_phrases.txt  voice.json
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

The voice path adds, in the same directory: `silero_vad.onnx` (standalone VAD /
bench), `kokoro-v1.0.onnx` + `voices-v1.0.bin` (TTS), and a `faster-whisper/`
subdir (ASR, auto-fetched on first use). `$WELLSY_WEIGHTS_DIR` overrides the
location. The NLTK `punkt_tab` sentence data lives at `~/.cache/wellsy/nltk_data`.

## Open-vocabulary prompts

`engine/config/prompts.txt` is a plain list, one term per line, `#`-comments
allowed. Edit it while `wellsy` is running — it's picked up on the next
detection pass via an mtime check, no restart needed.
