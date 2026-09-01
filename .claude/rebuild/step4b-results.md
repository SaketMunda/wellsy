# Step 4b — results

**Machine:** M4 Pro, 24 GB, macOS 15.5 (Darwin 24.5.0). Branch
`rebuild/step4b-vlm-wiring` off `master`. 121 tests green.

## Scope taken this session

The **code prerequisite** and the **VLM wiring proof**. The formal §1
measurement campaign (n ≥ 20 p50/p95 for every row, A8-granted, wake FA/FR
curve) is **carried forward** — see *Owed* below.

## What shipped

```
engine/voice/vision.py       route(screen|camera) + capture_for_intent() ->
                             verified CaptureResult -> JPEGs; VisionPending
                             hand-off; unverified never returns
                             (capture downscale is commit 2fde88e, branch only —
                              see VLM latency section)
engine/voice/intent_gate.py  decide() gains action "vision"; IntentGate captures,
                             attaches the image to LLMContext, emits LLMRunFrame;
                             CaptureError -> spoken remedy + source:"refused"
                             audit line, nothing forwarded.
                             build_provenance_logger(): one log_answer line per
                             vision answer, capture provenance folded in, image
                             dropped from context afterwards.
engine/voice/acoustic.py     LatencyObserver + `wellsy voice --measure-acoustic`
honesty/provenance.py        log_answer(capture=...) fold; source "refused"
honesty/intent.py            narrow _SCREEN pattern -> describe_scene
engine/voice/pipeline.py     _warm() ASR+TTS on build; default LLM qwen3:4b->qwen2.5:3b
tests/test_voice_vision.py   route, verified-only capture, provenance fold,
                             "unverified never reaches the model" (pipecat run_test)
```

## A8 — screen grounding

| Half | Result | Evidence |
|---|---|---|
| **Revoked** | **PASS** | Through the new voice wiring: `capture_for_intent("what's on my screen")` raises `CaptureError`; spoken *"I can't see your screen — screen recording permission isn't granted for this process."* No wallpaper/menu-bar description. `source:"refused"` audit line written. Verified live 2026-09-01 (Screen Recording missing for the VS Code process tree). |
| **Granted** | **OWED** | Needs Screen Recording granted to "Code" + a full VS Code restart (kills the granting session). Not run. |
| ScreenCaptureKit latency | **OWED** | `bench/capture_bench.py` will produce it once the grant is in place; unmeasurable now (backend refuses). |

## VLM wiring — proven

Live run 2026-09-01, `WELLSY_LLM_MODEL=qwen2.5vl:3b`, real camera:

- Image reached the model: `prompt tokens: 2757`, `image_url` in context,
  **`0.000s thinking`** (reasoning tax gone with a non-reasoning VLM).
- Answer returned, provenance line written, image dropped from context after.
- Camera→`qwen2.5vl:3b` and the screen-refusal path both exercised end to end.

## VLM §1 latency — measured MISS (not a bug)

Budget: wake → first audible word **< 2500 / < 3500 ms**.

| | camera VLM TTFT | note |
|---|---|---|
| 1920×1080 frame (as first run) | **9.4 s** | ~2757 vision tokens; prompt-processing bound, not generation, not reasoning |
| downscaled longest side 1024 (`vision._downscale`) | **3.2 s cold / ~3.0 s warm** | measured, n=4 |

Add STT (~0.3 s warm) + TTS TTFA (~0.05 s) + endpoint → wake→first-word ≈
**3.5–4 s**. p95 near budget; **p50 ~0.5–1 s over**. `qwen2.5vl:3b` on
Ollama/Metal has a ~3 s image prompt-eval floor on this machine.

**Disposition (owner, 2026-09-01):** accept the miss for now, revisit if/when
latency is optimised — see `[[wellsy-vlm-latency-deferred]]`. Levers not taken:
`moondream` (1.8B), an MLX vision backend (Apple-only, opt-in per INVARIANTS
#14). Screen/camera max px is env-tunable (`WELLSY_VLM_MAX_CAMERA_PX` /
`_SCREEN_PX`).

## LLM default flipped: qwen3:4b → qwen2.5:3b

Re-confirmed by curl 2026-09-01: every `qwen3` / `qwen3-vl` build on Ollama
0.33.2 ignores `think:false` and burns 8–22 s/turn on a reasoning pass ("say hi
in 3 words" → 4082 thinking tokens). A live session measured LLM turns at 8.7 s
and 22 s to first audio. `qwen2.5:3b`: ~50 ms TTFT, composed §1 LLM row 614 ms.
Owner approved the flip. `qwen3:4b` still reachable via `WELLSY_LLM_MODEL`. The
step-5 "two model roles" design (non-reasoning hot path + reasoning planner) is
still the intended endgame; this is the interim default. `model-inventory.md`
updated.

## Owed — the formal measurement campaign

Blocked only on the owner at the machine, not on code. Runbook:
`.claude/rebuild/step4b-runbook.md`.

1. **A8 granted half + ScreenCaptureKit latency** — needs the grant + restart.
2. **Acoustic §1 table** (deterministic / LLM / VLM), n ≥ 20, cold vs warm, at
   the device — `wellsy voice --measure-acoustic` (rig built, not run to n≥20).
3. **A14 barge-in** wall number + "interrupted, not delivered" check.
4. **`stop`** wall-clock at the device.
5. **Wake fixtures** (≥ 30 wake + ≥ 30 non-wake) + `tune-wake --write` from the
   measured FA/FR curve; commit `spec/fixtures/wake/`.
6. Then `spec/results/` + `.claude/system-state.md` acoustic table.

## Known rough edges from the live run

- Startup `_warm()` did not prevent a 1.2 s cold STT on turn 1 — warm may not be
  biting; not chased.
- Smart Turn returns `INCOMPLETE` on short utterances → ~3 s `stop_secs` fallback
  tail. Tunable via `SmartTurnParams(stop_secs=…)`; not changed.
- `qwen2.5vl:3b` as the *text* model is verbose and does not hold "one or two
  short sentences" well — fine for latency measurement, a UX gap for real use.
