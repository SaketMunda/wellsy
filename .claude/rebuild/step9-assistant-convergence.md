# Step 9 — Assistant convergence: the agent becomes the brain of the voice loop

**Read first:** `.claude/rebuild/step5c-results.md` (**the model set this is
built on — read it before planning anything**), `step5-results.md` (the agent
runtime, policy gate, audit log, read-back), `step6-results.md` increment 5
§"What this does NOT yet do" (this step is that section),
`step6c-results.md` (what the live run actually found),
`.claude/rebuild/INVARIANTS.md` (**#3, #6, #10, #15**),
`spec/phase1-acceptance.md` A3–A6, A9, A14.
**Depends on 5c, 6c. This is the shipping blocker.**

## Why this step exists

**The voice path and the agent are two separate programs that cannot see each
other.**

- `wellsy voice` / `wellsy run` — real-time loop: VAD, Smart Turn, streaming
  ASR/TTS, wake gating, half-duplex, the orb. Its brain is a **bare chat LLM
  with no tools.** This is why the owner asked it about the calendar and it
  replied that it couldn't reach one. It was telling the truth.
- `wellsy agent` — LangGraph runtime holding **24 tools**, the policy gate,
  `interrupt()` approvals, the audit log and read-back verification. It accepts
  **typed text only.**

Everything that makes WELLSY an agent is unreachable by voice, and everything
that makes it feel alive has no capability behind it. Step 6 increment 5 named
this as the real architectural ask and shipped `move_orb` plus an identity
prompt as stopgaps.

**Until this lands there is no product to ship** — there is a good voice demo
and a good agent demo in one repo.

## Read 5c first, then plan

5c may have changed the ground under this step. Specifically:

- **If one multimodal model won the collapse test**, `SeamLLMService`'s
  two-model switch (step 6 increment 6) becomes dead weight. 5c was told to
  measure and recommend but **not** to touch the code. **Removing it is this
  step's job** — and it is a simplification, so take it.
- **The planner's context window and tool-calling accuracy set this step's
  whole design.** 5b's planner was 4 s to a schema-valid plan at ctx 4096. If
  5c's winner is materially faster or has 262K context, the routing strategy
  below changes shape. Do not inherit the numbers in this prompt — read 5c's.

## Deliverable 1 — one runtime, one brain

The LangGraph graph becomes the voice loop's LLM stage. The bare chat service
stops being the thing that answers.

Keep the real-time pipeline exactly as it is — Pipecat owns audio, turn-taking,
the half-duplex gate, self-echo rejection and the orb taps. What changes is what
sits where `SeamLLMService` sits today: a stage that runs a graph turn and
streams the response back as text for TTS.

Non-negotiable: **the text seam survives.** D49 chose cascaded streaming over
speech-to-speech precisely because an agent needs a text bottleneck — every tool
call, policy decision, memory write and audit line is text. Do not collapse it.

`InMemorySaver` → **`SqliteSaver`** here (standing debt). A voice session that
cannot resume across processes is not a session, and approvals that block on an
`interrupt()` need durable state.

## Deliverable 2 — latency, or this step undoes step 4

The voice path's §1 budget is **< 1500 ms p50 to first word**. A planner turn is
seconds. Routing every utterance through the planner would regress the single
number step 4, 4b, 5b and 6b all defended.

Three tiers, and the routing decision must itself be cheap:

1. **Deterministic** — `stop`, `wake`, `sleep`, `move_orb`. Local, model-free,
   no graph. 617/700 ms measured. **Unchanged and unregressed.**
2. **Conversational** — no tool needed. The fast model answers directly, as
   today. This is the common case and it must not get slower.
3. **Agentic** — a tool is needed. **Acknowledge, then deliver:** speak a short
   honest ack within the fast budget (*"Let me check your calendar."*) and
   stream the real answer when the graph returns. 5b measured the ack at ~633 ms
   while the plan completes at ~4 s; that pattern is what makes tier 3 bearable.

For routing between 2 and 3, use the planner's own tool-calling (5c measures
it; reported ~97.5% at the 4B scale). **Do not build a classifier here** — that
is step 8, and it comes after deliberately so this step proves the product works
before optimising the routing.

The ack must never claim an action it has not taken. *"Let me check"* is honest;
*"I've sent it"* before the tool returns is the exact failure mode invariant #6
exists to prevent.

## Deliverable 3 — approval, spoken

`interrupt()` is the approval gate (D53). Today it blocks and waits for a click
or a typed answer. By voice it must:

- **Say what it is about to do**, specifically — recipient, time, file, amount.
- Open the orb's approval HUD at the same time (step 6 wired this view; the
  relay already blocks the graph on a `threading.Event`).
- Accept a **spoken** yes/no, and treat anything ambiguous as *no*.
- Keep `Esc` and the click path working. The deterministic stop still wins.
- **Exercise deny end to end into the audit log.** Step 6 only ever ran approve;
  step 6c was asked to try deny. Whatever it found, prove it here.

A spoken approval is a safety surface. Ambiguity resolves to refusal, and a
refusal is spoken aloud, not silent.

## Deliverable 4 — read-back before commit (invariant #15)

The graph already verifies before committing. By voice, the read-back must be
**heard**: the resolved values spoken back before the irreversible step —
especially dates and times, because 5b caught the planner rendering "Monday" as
a Sunday and placing a reminder in July.

That finding is why this is a deliverable and not a nicety. If 5c's planner
still botches relative dates, the read-back is the only thing between a wrong
date and a real calendar entry.

## Deliverable 5 — the orb tells the truth about the agent

Step 6 built the taps and the state machine; the agent's events already have a
sink (`agent_event_sink`). Now there is real traffic to show:

- `thinking` while the graph runs, `acting` while a tool executes,
  `awaiting_approval` on an interrupt, `refusing` on a policy deny.
- **The HUD from the runtime** — `plan`, `verify` and provenance views into
  `sess.show_hud(...)`. Only `approval` is wired today; this is step 6's owed
  item #3 and this step is where the data finally exists.
- The honesty test must stay green. States come from measured graph events, not
  from a timer that guesses how long a tool takes.

## Deliverable 6 — prove it as a product, not as a pipeline

A8-granted, real accounts, spoken end to end. A3–A6 and A9 have never run live
against a real Calendar/Mail account by voice.

Pick five real requests the owner would actually make and run them aloud —
something read-only, something that writes, something needing approval,
something that must be refused, and something multi-step. Record what happened,
including the failures.

Then re-measure §1 with the orb co-running: the deterministic row, the
conversational row, and a new **agentic row** (ack latency and total
time-to-delivered). Device-timestamped if 6c established that harness; say which
method you used either way.

## Out of scope

- **No decision classifier** — step 8.
- **No memory substrate** — step 7. Working memory stays the session object;
  do not start building retrieval.
- **No new TTS** — step 10.
- Do not re-tune the voice pipeline's audio layer. 4c owns it.

## Acceptance

- [ ] 5c's results read; `SeamLLMService` removed if the collapse test said so,
      with the reason recorded.
- [ ] One runtime: the graph answers voice turns; the text seam intact;
      `SqliteSaver` in place.
- [ ] Three-tier routing live. **Deterministic row unregressed**, measured.
- [ ] Conversational row within the < 1500 ms p50 budget, measured.
- [ ] Agentic row measured: ack latency and total delivery, with the ack proven
      never to claim an uncompleted action.
- [ ] Spoken approval works; ambiguous input resolves to refusal; **deny
      exercised end to end into the audit log**; `Esc` and click paths intact.
- [ ] Read-back spoken before every irreversible commit, dates included.
- [ ] Orb drives from real graph events; `plan`/`verify`/provenance HUD views
      wired; honesty test green.
- [ ] Five real spoken requests run against real accounts and written up.
- [ ] `step9-results.md`; PR open.

## The standing rules

Numbers or nothing, and one more: this step is where WELLSY either becomes a
thing you talk to that does things, or stays two demos. If a tier misses its
budget, report the miss with the number — do not hide a 4-second planner behind
a cheerful ack and call the row green.
