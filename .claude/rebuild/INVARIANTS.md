# WELLSY — Standing Invariants

**Every rebuild session MUST read this file before writing code.**
These are not guidelines. A change that violates one is reverted, not debated.

---

### Project boundary

1. **All project files live inside this repository.** Never `/tmp`, never a
   session scratchpad, never a path outside the repo. The sole exception on
   record is model weights at `~/.cache/wellsy/weights` (formerly
   `~/.cache/wellsy/weights`).

2. **Local-first.** No third-party cloud service receives pixels, audio, or raw
   personal files — ever. A private server the owner controls is acceptable.
   Text intents and tool schemas may leave only if a brain-router fork is
   explicitly decided and recorded; it has not been as of 2026-09-01.

3. **`parse_intent` owns the safety path.** `stop`, `wake`, and `sleep` are
   resolved deterministically by regex. An LLM must never decide whether "stop"
   stops. This survives every framework migration; if a framework cannot
   accommodate it, the framework is wrong.

4. **Drop frames, never buffer.** Depth-1 latest-wins queues at every stage —
   the frame queue, the WebSocket/IPC boundary, the event bus. A slow consumer
   is dropped, never buffered into. Maps onto ROS 2 `KEEP_LAST(1)`.

5. **T0 is never gated.** The always-on motion gate runs unconditionally. Every
   other tier may be scheduled, throttled, or preempted.

6. **Never fabricate a number or a label.** Below the confidence floor it is
   `UNIDENTIFIED`. No invented distances, counts, or readings. A field with no
   real source is `null`, never guessed.

7. **The preemption seam always releases.** Any hand-off between the perception
   loop and a query path uses `try/except/finally` with release in `finally`. A
   leaked exception that leaves the seam held freezes ambient sensing.

8. **Verify a model or library is current before adopting it.** Check the
   release, the protocol revision, and the flags. Do not install from a name
   recalled from memory or copied out of a planning document. Record the pinned
   version and the date it was verified.

### Added 2026-09-01 for the agent rebuild

9. **No tool executes without a policy decision.** Unannotated tools default to
   risk 3 and fail closed.

10. **Memory is inspectable and hand-editable.** Semantic memory is markdown a
    human can open and correct. Editing it by hand must change behaviour.

11. **An inference is never auto-promoted to a fact.** Promotion requires a
    second independent observation or explicit user confirmation.

12. **Every consequential action writes its audit line before it returns.**
    Not after. Not on success only.

13. **Every proactive suppression is logged with its score.** Thresholds are
    tuned against logs, never intuition.

14. **No platform-exclusive API in the core.** The engine must run on macOS,
    Linux, and Windows from one codebase. Platform acceleration is permitted
    only as a swappable backend behind a portable interface, selected at
    runtime, with a portable fallback tested on every platform. A component with
    no portable path does not enter the core.
    **Specifically banned from the core:** MLX, CoreML, ScreenCaptureKit as an
    interface (permitted as the macOS backend), `speech-swift`, DXcam,
    Apple-only Ollama backends.

15. **Never report success a read-back does not confirm.** A tool's own return
    value is a claim, not evidence.

---

### Autonomy rule

Autonomy is a **level that rises against the audit log**, not a switch.
Reversible risk-0/1 actions run silently from the start. Risk-2 requires
approval until the audit log shows a clean run of that action class. Risk-3
(delete, shell, writes outside allowed roots) stays gated by default.

---

### Measurement rule

**Measured, not estimated.** p50 and p95 over ≥ 20 trials. Cold start and warm
reported separately. If a number appears in a document, the method that produced
it appears next to it. "Roughly", "should be", and "approximately" are not
results.
