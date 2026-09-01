# Step 1 — Repo reset, rename, and perception core port

**Read first, in order:** `.claude/rebuild/INVARIANTS.md`,
`.claude/stack-teardown.md` §8 and §12.6, `spec/phase1-acceptance.md`.

## Context you need (this session has no memory of the master session)

This project was called **YAP**. It is now **WELLSY**. It is a local, private,
agentic assistant — not a camera demo. The previous build reached Day 11 and
failed on fluency: three fully-buffered stages in series (batch STT → non-
streaming LLM → whole-clip TTS), so latencies added instead of overlapping.
The decision is a ~70% rewrite around a preserved perception core.

**This step writes almost no new logic.** It is a careful port plus deletions.
Resist the urge to improve the ported code. Later steps replace what needs
replacing; unnecessary changes here destroy the ability to prove no regression.

## What survives, and why

These ~680 lines are measurably good — 16.81 ms p50 perception fast path — and
they survive into the eventual robot as well as the desktop:

| File | Lines | Role |
|---|---|---|
| `engine/motion.py` | 48 | T0 always-on frame-difference motion gate, ~1 ms |
| `engine/detector.py` | 100 | YOLOE open-vocabulary detection (portable PyTorch) |
| `engine/tracker.py` | 108 | ByteTrack, stable track IDs |
| `engine/capture.py` | 126 | Process-per-workload, depth-1 latest-wins frame queue |
| `engine/tiers.py` | 103 | T0–T3 tier scheduler + `PreemptionSeam` |
| `engine/provenance.py` | 97 | The honesty layer — one JSONL line per spoken claim |
| `engine/intent.py` | 101 | Deterministic `stop`/`wake`/`sleep` (invariant #3) |

Their tests come with them: `test_intent.py`, `test_scene.py`, `test_greeting.py`,
`test_query_loop.py` — port the ones whose subject survives; delete the rest.

## What is deleted

| Path | Lines | Reason |
|---|---|---|
| `src/` (entire tree) | 5,264 | Browser HUD. Not the product. The interface will be native and is a *client* of the runtime, built in a later step. |
| `engine/query_loop.py` | 777 | Hand-rolled thread orchestration. Replaced by Pipecat in step 4. |
| `engine/vad.py` | 85 | Energy VAD with a noise floor that could latch. Replaced by Silero. |
| `engine/stt.py` | 79 | Batch Moonshine. Replaced by streaming ASR. |
| `engine/tts.py` | 227 | Chatterbox Turbo, measured RTF 1.1x–3.3x — slower than realtime. Replaced. |
| `engine/screen_capture.py` | 108 | Wrong API, and returns garbage silently. Rebuilt in step 3. |
| `engine/llm.py` | 160 | Ollama-coupled and non-streaming. Replaced in step 2. |
| `engine/bridge.py` | 77 | WebSocket bridge to the deleted HUD. |
| `engine/ambient.py`, `scene.py`, `greeting.py`, `debug_window.py` | ~450 | Depend on the deleted voice path. Greeting behaviour returns in a later step, driven by the agent runtime. |
| `index.html`, `package.json`, `package-lock.json`, `vite`/node config, `scripts/*.mjs` | — | Browser build. |

Delete via `git rm` so the history records it. Do not leave a `legacy/` folder;
the git history is the archive.

## Target layout

```
wellsy/
  __init__.py
  perception/       motion.py detector.py tracker.py capture.py
  runtime/          tiers.py           # scheduler + PreemptionSeam
  honesty/          provenance.py intent.py
  config/           prompts.txt wake_phrases.txt
tests/              one test module per surviving module
spec/               phase1-acceptance.md  (exists)
.claude/            planning docs (exists)
```

- `pyproject.toml` at the repo root, package name `wellsy`.
- Console entry point `wellsy`.
- Python 3.13, the existing venv is fine to reuse but **remove `chatterbox-tts`,
  `moonshine-onnx`, `perth`, and the `torch==2.6.0` pin it forced.** Let torch
  float to current; re-run the detector benchmark after (see acceptance).

## Rename YAP → WELLSY

238 occurrences across ~38 files. Mechanical, but do it attentively:

- Code identifiers, module paths, package name.
- `~/.cache/yap-engine/weights` → `~/.cache/wellsy/weights`. **Move the existing
  weights rather than re-downloading** (~570 MB of MobileCLIP-BLT + YOLOE).
- `engine/wake_phrases.txt`: replace `hey yap` / `yappy` / `hey yo` with
  `wellsy` / `hey wellsy`. The old wake word failed because "yap" transcribes as
  "app". "Wellsy" has a soft `/w/` onset, so the difflib fuzzy-match threshold
  (was `0.72`) **will need retuning in step 4** — leave a `TODO(step4)` marking
  it rather than guessing a new value now.
- `.claude/` documents: rename references but **do not rewrite history**. Day
  1–11 documents describe what was built as YAP and should keep saying so; add a
  one-line header noting the rename where it matters.

## Acceptance

This step passes only when all of the following hold:

1. `wellsy --help` runs from a clean checkout and a fresh install.
2. `wellsy --seconds 60` runs the perception loop with camera and detector, no
   voice path, and exits cleanly.
3. **No perception regression.** Re-run the detector benchmark and report p50/p95
   over ≥ 20 trials against the recorded baseline of **16.81 ms p50** fast path
   and **21.8–22.2 ms** steady-state YOLOE inference. A regression beyond the
   `spec/phase1-acceptance.md` §1 budget (20 ms p50 / 35 ms p95) fails this step.
   Report the torch version the number was taken on.
4. All ported tests green. Report the count; do not silently drop tests.
5. `grep -ri "yap" --exclude-dir=.git .` returns only intentional historical
   references in `.claude/` day documents. Zero in code.
6. `git status` clean, one commit, message describing the reset honestly.

## Do not

- Do not add features, refactor the surviving modules, or "clean up" their
  comments. A port that changes behaviour cannot prove criterion 3.
- Do not introduce any inference framework yet — that is step 2.
- Do not add MLX, CoreML, or any Apple-only package (invariant #14).
- Do not write to `/tmp` or a scratchpad (invariant #1).

## Report back to the master session

Benchmark table (before/after, with torch versions), test count, LOC deleted vs
kept, and anything the port revealed that the audit missed.
