# Step 5 — Agent runtime: LangGraph, MCP tools, policy gate, audit log

**Read first:** `.claude/rebuild/INVARIANTS.md` (#9, #12, #15 and the autonomy
rule), `.claude/stack-teardown.md` §12.1, §12.3, §12.5,
`spec/phase1-acceptance.md` **A3–A6, A9–A12**. **Depends on step 2.**
Can run in parallel with step 4 — it is driven by typed text, not voice.

## What WELLSY actually is

Not a camera demo and not a chatbot. An autonomous agent that schedules
meetings, researches, makes bookings, browses, and has broad access to the
machine. The stated endgame is a humanoid body running Jetson-class compute.
This step builds the part that *acts*.

Zero of this exists today. There is no tool layer, no permission check anywhere,
no agent loop, and no audit log.

## Deliverable 1 — MCP tool layer

Add an MCP client. **Do not write a tool registry** — MCP is the standard, it
exists, and it has a large local server ecosystem.

- Local servers for Calendar, Reminders, Mail, Notes, Contacts, Files.
- A filesystem server scoped to **explicit allowed roots**. Not `/`.
- **Invariant #8 applies hard here:** verify the current server, its protocol
  revision, and its safety-mode flags before adopting. Do not install a server
  from a name recalled from a planning document.
- Servers are per-platform in practice (macOS today, Linux later). Keep the
  tool-facing interface platform-neutral so the Linux set drops in without
  touching the agent (invariant #14).

## Deliverable 2 — policy gate

Every tool annotated with: capability, risk level 0–3, reversibility,
requires_approval. Store as a **YAML sidecar keyed by `server.tool_name`**, not
in code, so it is auditable and diffable.

**Unannotated tools default to risk 3 and fail closed** (invariant #9).

Starting risk map:

| Risk | Actions |
|---|---|
| 0 | all reads |
| 1 | create draft, create reminder, write to scratch |
| 2 | send mail, create or move a calendar event |
| 3 | delete anything, shell, write outside allowed roots |

`PolicyGate.check(tool, args, context) -> Allow | Confirm | Deny`. Roughly 150
lines. **Do not build a policy engine and do not adopt OPA.**

### The autonomy rule — implement it as written

Autonomy is a level that rises **against the audit log**, not a switch the user
flips. Risk-0/1 reversible actions run silently from the start. Risk-2 requires
approval until the audit log shows a clean run of that action class. Risk-3
stays gated by default.

The owner's goal is full autonomy with full compute access. The audit log and
the policy gate are the mechanism that *gets there* — they are the only evidence
that a class of action can be trusted unsupervised. An agent that destroys
something once, silently, with no way to report it is not robust; it is
single-shot.

## Deliverable 2b — two model roles, not one model (added 2026-09-01)

Step 4 measured the LLM row at **3957 ms p50 against a 1500 ms target** with
`qwen3:4b`, because that build runs a reasoning pass on every turn and no
documented flag disables it (verified by direct `curl` against every option).
The same root cause sits in the VLM row: `qwen3-vl:4b` TTFT **p95 8081 ms**.

**Do not resolve this by picking one faster model.** Reasoning is poison on the
conversational hot path and genuinely valuable in the planner — decomposing an
outcome into <= 6 tool calls is exactly what a reasoning pass is for.

Split by role:

| Role | Model class | Budget |
|---|---|---|
| **Fast path** — conversation, simple lookups, acknowledgements | non-reasoning instruct | §1 budget applies: < 1500 ms p50 to first word |
| **Planner** — decompose, verify, multi-step | reasoning | 3–4 s acceptable **only because the fast path speaks first** |

**The acknowledge-then-deliver rule:** when a request routes to the planner, the
fast path emits an acknowledgement ("let me check your calendar") within the §1
budget while the planner runs behind it. This is what makes an assistant feel
fluent rather than slow, and it converts the measured miss into a non-issue.

**Do not settle on `qwen2.5:3b`** because it cleared the number in step 4's
control run. It is a 2024-era model and adopting it because it happened to be
installed is the stale-tech failure mode this project has an invariant against
(#8). Benchmark current non-reasoning instruct models for the fast slot through
`wellsy bench`, and record the losing numbers.

Also resolve the VLM reasoning pass, or route vision through a non-reasoning
VLM. An 8-second p95 fails A7 and A8 regardless of how good the answer is.

## Deliverable 3 — LangGraph agent loop

**LangGraph, decided (D53).** The decisive property is that its `interrupt()`
primitive **is** the approval gate — human-in-the-loop maps 1:1 onto the policy
gate's `Confirm` and onto autonomy levels, rather than being bolted alongside.
Durable checkpointing at every node is what makes A11 (partial progress
preserved through a mid-plan failure) achievable at all.

Verify the current version before pinning (invariant #8).

Implement as an explicit state machine:

- **Plan** — decompose an outcome into ≤ 6 tool calls before executing any.
- **Policy check** — every call, no exceptions.
- **Act.**
- **Verify by read-back** — did the tool actually do the thing? Invariant #15:
  a tool's own return value is a claim, not evidence.
- **Checkpoint** after each step so partial progress survives failure.
- Retry limit **2**. Escalate on ambiguity rather than guessing — exactly one
  clarifying question (A10), never an interrogation.

## Deliverable 4 — audit log, from day one

One JSONL line per consequential action, **written before the action returns**
(invariant #12), not after and not on success only.

Reuse `provenance.py`'s discipline — extend it, do not fork it. The honesty
layer is this project's actual differentiator and it must reach into agency, not
stop at perception.

Fields at minimum: timestamp, actor, tool, arguments (with secrets redacted),
risk level, policy decision, approval source, outcome, read-back result, and the
plan/step id it belongs to.

## Deliverable 5 — approval surface (minimal)

Step 4 may not be finished, so **drive this by typed text**. The approval
surface for now is CLI. The native UI is a later step and is a *client* of this
runtime, not part of it (D54).

## Acceptance

Scenarios **A3, A4, A5, A6, A9, A10, A11, A12** from
`spec/phase1-acceptance.md`, all driven by typed text input. Specifically:

1. `list_tools()` returns ≥ 15 tools with full schemas.
2. A scripted attempt to send mail is **blocked pending approval**. Approving
   sends. Denying does not send, reports honestly, does not retry, and writes an
   audit line for the denial.
3. Asking twice without approval does not execute a risk-3 tool.
4. A4 passes **with independent read-back verification** — not the tool's own
   success return.
5. A11 passes with a deliberately broken tool injected at step 2 of a 4-step
   plan: partial progress preserved, honest report, no fabricated success.
6. A12 reads back from the audit log itself, not from conversation memory.
7. Every tool has a YAML annotation, and a deliberately unannotated tool is
   demonstrably treated as risk 3 (write that negative test).

## Do not

- Do not write a tool registry, a policy engine, or a workflow DSL.
- Do not let the agent loop touch `stop`/`wake`/`sleep` (invariant #3).
- Do not defer the audit log to a later step. It is load-bearing for the
  autonomy rule and retrofitting it produces gaps.
- Do not grant filesystem or shell access beyond the declared roots to make a
  scenario pass.

## Report back — and this unblocks the hardware purchase

The owner will buy a Linux/NVIDIA box once requirements are known, and **this
step is where they become knowable.** With the agent running, report:

- final model sizes and whether the brain is resident or loaded on demand,
- **measured** peak and steady resident memory with the full stack warm —
  including **both** model roles from Deliverable 2b, resident or swapped,
- tokens/sec needed to hold the §1 latency budget under real tool-calling load,
- whether the Jetson Orin NX class target (~16 GB, 100 TOPS — **less headroom
  than the 24 GB M4 Pro this was developed on**) constrains the desktop build.

Measured numbers only. Sizing a box against guesses is how the previous stack
ended up wrong.
