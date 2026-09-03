# Step 4c — Open-air audio: fix the echo regression, then earn full duplex back

**Read first:** `.claude/rebuild/INVARIANTS.md` (#3, #13, #15),
`.claude/rebuild/step4-results.md`, and the git history of the deleted
`engine/query_loop.py` at `7aae9c5^` — specifically the `_speaking()` mute in
the mic thread. **Depends on step 4. Blocks any speaker-based demo and blocks
the robot.** Run this before step 6 — an interface that pulses at its own voice
is worse than no interface.

## The regression, stated plainly

The pre-rebuild build worked open-air on laptop speakers. It worked because the
mic thread hard-muted itself for the whole duration of its own speech:

> `# Not removing the mute — it's the real fix for the mic hearing its own`
> `# voice through the speakers, no AEC on this hardware`

It was **half-duplex by construction**, and it knew it: it logged the transition
so a dropped follow-up was diagnosable rather than looking like flakiness.

Step 4 shipped real barge-in, which requires the mic open during playback. The
mute was removed and nothing took its place. The result, from a live session
2026-09-02:

- bot says *"What can I do for you?"* → STT transcribes user speech as
  **"What can I do for?"**
- bot says *"I can't share deeds as I don't have physical access…"* → STT then
  produces **"I can't share deep."** → **"I can't share her."** → **"I can't
  share."**
- every interruption fires 0.5-0.9 s after `Bot started speaking`

Self-sustaining loop: speak → mic hears it → VAD reads it as barge-in → cancels
its own sentence mid-word → STT transcribes its own words as the user → LLM
answers itself. The reported symptoms — "stops midway then continues", "repeats
the same lines" — are both this.

Nothing in the suite caught it because every step-4 number came from a
file-injection harness. There was no speaker in the room.

## Deliverable 1 — restore parity, immediately

Half-duplex gate: suppress mic input while the bot is speaking, plus a short
tail for the room's decay. Default it **on**. This is what the old build did and
it makes open-air usable today.

Two requirements the old build already got right and this must keep:
- The deterministic stop path (`Esc`, invariant #3) stays live while muted.
- **Log the transition once** — muted / unmuted — not per frame. A dropped
  follow-up must be diagnosable (invariant #13).

## Deliverable 2 — reject its own words

We know exactly what we just spoke, because we handed it to the TTS. Keep a
short rolling window of recent TTS text; if a transcript fuzzy-matches it,
discard it and log the suppression. Reuse the matcher in `engine/voice/wake.py`.

This is not echo cancellation and never substitutes for it. It is the last line
of defence, it works on any hardware, and it would have killed every loop in the
log above. Cheap. Build it anyway, and keep it forever.

## Deliverable 3 — wake-word-gated barge-in

This is what Echo devices actually do, and it is the finding that reframes the
step: **they do not run open-mic VAD barge-in during playback.** They listen for
the wake word only. Detecting one fixed phrase in an echo-contaminated signal is
a far easier and more robust problem than detecting arbitrary speech.

So: while speaking, drop from full VAD to wake-word-only. "Wellsy, stop" cuts it
off; a cough does not. This is **strictly better than the old build**, which was
fully deaf while speaking, and it restores most of what barge-in was for without
needing AEC to work first.

Depends on the wake fixtures + threshold tune that step 4 still owes — the
bootstrap 0.72 threshold is not good enough to gate on. Do that here.

## Deliverable 4 — acoustic echo cancellation

The real fix, and what buys back true full-duplex barge-in.

You have the reference signal: what was sent to the speaker. An adaptive filter
estimates the room's echo path and subtracts the predicted echo from the mic.
The standard open implementation is **WebRTC AEC3**, with residual echo
suppression and double-talk detection on top (the filter must freeze adaptation
during double-talk or it diverges).

Invariant #8 applies: `webrtc-audio-processing` on PyPI has been dead since
2018; `pywebrtc-audio` looked current at the time of writing. **Verify before
adopting, and record what you rejected.** macOS `VoiceProcessingIO` does system
AEC and is a legitimate platform backend behind a portable interface (invariant
#14) — but the portable WebRTC path must exist, because the robot is Linux.

Success is measured, not asserted: with speakers at normal volume, ERLE (echo
return loss enhancement) in dB, plus a live session where the assistant speaks a
long answer and **no transcript containing its own words is produced**.

## Deliverable 5 — the audio hardware requirement, written down

Software AEC quality is capped by hardware choices, so these are requirements
for the robot's audio front-end even though nothing is being bought yet:

- **One codec for input and output, one clock domain.** AEC needs the reference
  and the capture sample-aligned; separate USB devices or anything Bluetooth
  drift apart and the adaptive filter never converges. This rules out a lot of
  otherwise convenient hardware.
- **A mic array of ≥4 mics with known geometry, and beamforming.** Echo devices
  use a 7-mic circular array to steer a beam at the talker and spatially null
  other directions, including the speaker's. That is suppression AEC cannot do,
  because it is geometric rather than temporal.
- **Speaker gain limited to stay out of clipping.** AEC assumes a linear echo
  path; a small speaker driven loud distorts non-linearly and the filter cannot
  model what it cannot predict.
- **Prefer a front-end that does AEC in hardware, ahead of the application** —
  that is how Echo devices are built, and it is the model to copy.
- Note for the robot specifically: **fans and servos are continuous noise
  sources inches from the mics.** Same front-end has to handle that.

Write this into `spec/` as a hardware requirement, not into a results doc.

## Acceptance

1. A live open-air session on laptop speakers, no headphones, ≥ 10 turns: no
   self-transcription, no self-interruption, no repeat loop. Recorded.
2. Half-duplex gate default on; `Esc` still stops instantly while muted;
   mute/unmute logged once per transition.
3. Self-transcript rejection unit-tested against the actual strings from the
   2026-09-02 log ("I can't share deep." vs "I can't share deeds…").
4. Wake fixtures recorded, threshold tuned, wake-word barge-in works during
   playback and is measured for false-accept during the bot's own speech.
5. AEC integrated, ERLE measured, and full-duplex barge-in re-measured against
   the §1 budget (< 200 / < 350 ms onset → silent) **acoustically**, not by
   injection.
6. A regression test that would have caught this: playback routed back into the
   input path, asserting no self-transcript reaches the LLM.
7. `spec/` carries the audio hardware requirement.

## Report back

Whether it holds a real conversation in a room with speakers, and what the
false-accept rate is for wake-during-playback. And say which of the four layers
is actually carrying the load — if AEC lands well, deliverable 1 should become
unnecessary; if it doesn't, say so rather than leaving the gate on and calling
it full duplex.
