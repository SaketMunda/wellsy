# Audio front-end — hardware requirements

**Status:** requirement, not a purchase. Nothing is being bought yet (see
`.claude/rebuild/README.md` — hardware is the last step). This exists because
**software AEC quality is capped by hardware choices**, and the robot's audio
front-end has to be chosen against these constraints, not convenience.

Origin: `.claude/rebuild/step4c-echo-and-duplex.md` Deliverable 5. The
reference design is an Amazon Echo-class smart speaker — the thing that
actually holds a full-duplex conversation in a room with its own speaker
playing.

---

## R1 — One codec, one clock domain for capture and playback

AEC needs the far-end reference (what was sent to the speaker) and the mic
capture **sample-aligned**. Two separate USB audio devices, or anything
Bluetooth, run on independent clocks that drift; the adaptive filter chases a
moving target and never converges.

- Input and output MUST share a single audio codec / DAC-ADC on one clock.
- No Bluetooth in the capture or playback path.
- No "USB mic + USB speaker" pairing. A single multi-channel USB audio
  interface that does both is acceptable; two devices are not.

This rules out a lot of otherwise convenient hardware and must be checked
first, before anything else about the audio parts.

## R2 — Mic array: ≥ 4 mics, known fixed geometry, beamforming

Echo devices use a 6–7 mic circular array to steer a receive beam at the
talker and spatially null other directions — including the direction of their
own speaker. That is **spatial** suppression; temporal AEC (an adaptive filter
on the reference signal) cannot do it, and the two are complementary, not
alternatives.

- ≥ 4 mics (6–7 preferred), rigidly mounted, geometry known to the software.
- Beamforming / direction-of-arrival in the front-end.
- The array geometry is a fixed input to the DSP — it cannot move relative to
  the mics after calibration.

## R3 — Speaker gain stays out of clipping

AEC assumes a **linear** echo path. A small speaker driven loud distorts
non-linearly; the filter cannot model what it cannot predict, and residual
echo leaks through exactly when the bot is loudest.

- Playback gain limited (in hardware or a fixed software ceiling) so the
  speaker never clips at maximum assistant volume.
- Prefer a speaker with headroom over a small one run hot.
- `auto_gain_control` on the *capture* side stays off or bounded — a large AGC
  step changes the echo-path gain out from under the filter.

## R4 — Prefer hardware AEC ahead of the application

Echo devices do AEC in a dedicated front-end DSP, before the audio ever
reaches application code. That is the model to copy: a front-end module
(e.g. an XMOS / DSP-based array board, or a SoC audio subsystem with a
hardware AEC block) that presents an already-cleaned capture stream.

- First choice: a mic-array front-end that does AEC + beamforming +
  noise-suppression in hardware and exposes one clean mono capture channel
  plus a loopback reference.
- The portable WebRTC AEC3 path in `engine/voice/aec.py` remains the
  **fallback and the cross-platform reference**, and the only path on
  hardware without a DSP front-end. It must keep working; it is not the
  reason to skip R4.

## R5 — Continuous self-noise: fans and servos

On a humanoid body the mics are inches from cooling fans and actuator servos —
continuous and impulsive noise sources that move. The same front-end that does
R2/R4 has to handle this:

- Noise suppression tuned for broadband fan noise and servo whine, not just
  "room tone".
- Mic placement as far from fans/servos as the industrial design allows, and
  mechanically isolated (compliant mounts) so structure-borne vibration does
  not couple in.
- Validate with the body's own fans and servos running, not in a quiet room.

---

## Acceptance for the eventual hardware

Measured, per `.claude/rebuild/step4c-echo-and-duplex.md` §Acceptance:

- ERLE (echo return loss enhancement) in dB with the speaker at normal volume,
  reported from `engine.voice.aec.erle_db` on echo-only segments.
- A live session: the assistant speaks a long answer and **no transcript
  containing its own words is produced** (the 2026-09-02 regression, gone).
- Full-duplex barge-in re-measured **acoustically** against the §1 budget
  (< 200 / < 350 ms speech-onset → output silent), not by file injection.
