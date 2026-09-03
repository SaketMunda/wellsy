# Step 4c — open-air audio: results

**Machine:** M4 Pro, 24 GB, macOS 15.5 (Darwin 24.5.0). Work off `master` @
`065970c`. **Non-acoustic session** — no speaker in the room this pass; the
live-session acceptance items are listed as owed, same pattern as step 4 / 4b.

## What shipped

```
engine/voice/
  duplex.py    HalfDuplexGate (D1) + SelfEchoWindow/EchoTextTap/SelfEchoFilter
               (D2) + AsrWakeProbe / mode="wake_gated" (D3, experimental);
               pure helpers echo_match_score / is_self_echo for the tests
  aec.py       portable EchoCanceller seam (D4): NullEchoCanceller (tested
               fallback), WebRtcEchoCanceller (guarded import of pywebrtc-audio,
               NOT in pyproject yet), get_echo_canceller(), erle_db()
  config.py    half_duplex / half_duplex_tail_ms / barge_in_mode /
               self_echo_reject / self_echo_threshold / self_echo_ttl_s —
               voice.json + WELLSY_* env overrides
  pipeline.py  transport.input -> HalfDuplexGate -> stt -> SelfEchoFilter ->
               wake_gate -> ... -> tts -> EchoTextTap -> transport.output
spec/audio-hardware-requirements.md   D5
tests/test_duplex.py           D1 + D2, incl. the actual 2026-09-02 strings
tests/test_echo_regression.py  acceptance #6 — playback looped into the input
tests/test_aec.py              the seam contract + ERLE metric
```

Full suite: **162 → 178 passed** (16 new), 28 s.

## Deliverable status

| # | Deliverable | State |
|---|---|---|
| 1 | Half-duplex gate, default **on**, ESC stays live, one log line per transition | **done + tested** |
| 2 | Self-transcript rejection, rolling TTS window, reuses fuzzy matcher | **done + tested** against the real log strings |
| 3 | Wake-word-gated barge-in during playback | **scaffolded, experimental** — `mode="wake_gated"` + `AsrWakeProbe` wired; default stays `"mute"`. Blocked on the wake fixtures + tune step 4 owes; during-playback false-accept **not measured** |
| 4 | Acoustic echo cancellation | **seam only** — portable interface + null fallback + guarded WebRTC backend. Not routed into the live transport; no ERLE run |
| 5 | Audio hardware requirement written into `spec/` | **done** |

## Acceptance

| # | Criterion | State |
|---|---|---|
| 1 | Live open-air ≥ 10 turns, no self-transcription / self-interruption / repeat loop, recorded | **owed — needs the owner at the mic** |
| 2 | Half-duplex gate default on; ESC stops while muted; mute/unmute logged once | **met** — `test_duplex.py::test_gate_*` |
| 3 | Self-transcript rejection unit-tested against the 2026-09-02 strings | **met** — `test_duplex.py::test_self_echo_*` ("I can't share deep." vs "I can't share deeds…" is the explicit case) |
| 4 | Wake fixtures recorded, threshold tuned, wake-word barge-in works during playback, false-accept measured | **owed** — `wellsy record-wake` + `wellsy tune-wake` still un-run; `spec/fixtures/wake/` empty |
| 5 | AEC integrated, ERLE measured, full-duplex barge-in re-measured acoustically | **owed** |
| 6 | Regression test: playback routed into the input path, no self-transcript reaches the LLM | **met** — `test_echo_regression.py`; both layers shown to stop the loop independently, and `test_both_layers_off_the_loop_is_reproduced` fails-open to prove the harness bites |
| 7 | `spec/` carries the audio hardware requirement | **met** — `spec/audio-hardware-requirements.md` |

## AEC library survey (INVARIANTS #8, verified 2026-09-02)

| Package | Verdict | Why |
|---|---|---|
| `webrtc-audio-processing` (xiongyihui) | **rejected** | last release 0.1.3, 2018-07-17 — dead since 2018, exactly the #8 trap |
| `aec-audio-processing` 1.0.1 (2025-09-01) | **rejected for core** | Windows-x86_64 wheels only; no Linux, no macOS, no aarch64 |
| `pywebrtc-audio` 0.1.0 (2026-05-19, Apache-2.0) | **candidate, not adopted** | wraps WebRTC APM (AEC3); wheels cp310–cp314 manylinux/musllinux x86_64+aarch64, macOS x86_64+arm64, win_amd64 — covers the M-series box and a Jetson Orin. But v0.1.0, 2-commit repo. Pin exact, keep `NullEchoCanceller` as the fallback, add to `pyproject.toml` only after a live ERLE run justifies it (INVARIANTS #15) |
| macOS `AUVoiceProcessingIO` | **backend only** | system AEC; legitimate as a swappable backend behind `aec.py`, banned as an interface (INVARIANTS #14). `CoreAudioEchoCanceller` is a TODO |

## Which layer is carrying the load

Today: **Deliverable 1 (the half-duplex gate) carries open-air entirely**, with
Deliverable 2 as the always-on backstop that also covers the tail-window edge
and any hardware where the gate's timing is loose. That is a deliberate
half-duplex posture — "Wellsy, stop" during a long answer does **not** work yet
(the deterministic ESC key does; spoken barge-in during playback does not).

Deliverables 3 and 4 are what buy spoken barge-in back. Per the step's
"report back": with AEC unproven, the gate stays on and this is **not** full
duplex — stated plainly rather than left ambiguous.

## Owed — needs the owner at the machine

1. `wellsy record-wake` (≥ 30 wake + ≥ 30 non-wake, **with speakers playing**
   for a subset) then `wellsy tune-wake --write`. Unblocks D3 and acceptance #4.
2. Live ≥ 10-turn open-air session on laptop speakers, recorded — acceptance #1.
3. Route `transport.output()`'s render stream into `aec.get_echo_canceller()`
   ahead of the VAD, sample-aligned; measure ERLE with `aec.erle_db`; re-run
   the acoustic barge-in table from `engine/voice/acoustic.py`. If ERLE lands
   well, flip `barge_in_mode` default and retire the gate; if not, say so.
4. During-playback wake false-accept rate for `mode="wake_gated"`.

## A/B knobs

`WELLSY_HALF_DUPLEX=0` disables the gate (step-4 behaviour, loops on speakers).
`WELLSY_BARGE_IN_MODE=wake_gated|full|mute`. `WELLSY_SELF_ECHO_REJECT=0`,
`WELLSY_SELF_ECHO_THRESHOLD`, `WELLSY_HALF_DUPLEX_TAIL_MS`.
