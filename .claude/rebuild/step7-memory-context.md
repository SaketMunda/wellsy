# Step 6 — Memory substrate, provenance-aware writes, context engine

**Read first:** `.claude/rebuild/INVARIANTS.md` (#6, #10, #11),
`spec/phase1-acceptance.md` **A1, A2**. **Depends on step 5.**

## Where this stands today

Zero of six memory types exist. The only state is a 10-second conversation
window. This is the Phase 1 success criterion: after this step, a cold start
followed by *"what was I working on yesterday, and what's the first thing I
should do about it?"* must produce a correct, grounded, memory-derived answer.

## Deliverable 1 — substrate

**Use sqlite-vec plus hand-editable markdown core blocks. Not Letta.**

The reasoning, so it is not relitigated: Letta makes every memory operation an
LLM call and adds a server process. On a machine already near its ceiling with a
VLM and a detector resident — and heading for a Jetson Orin NX with *less*
headroom — that cost lands in exactly the wrong place. sqlite-vec is portable
(invariant #14), tiny, and trivially inspectable, which invariant #10 requires
anyway.

Map the six types:

| Type | Implementation |
|---|---|
| Working | A real session object replacing the 10 s window |
| Episodic | Every exchange and every audit event, embedded and searchable |
| Semantic | Stable facts and preferences — **human-readable markdown, hand-editable.** Non-negotiable. |
| Procedural | "How the owner likes X done" — same store, tagged |
| Relationship | People entities from Contacts plus mail/calendar co-occurrence |
| Project | Long-running work threads, keyed by name |

## Deliverable 2 — provenance-aware writes

Every memory row carries `source`, `timestamp`, `confidence`, and
`type ∈ {observed, inferred, stated}`.

This is the direct extension of the honesty layer that is already this project's
differentiator. Apply it to memory or the differentiator dies at the moment it
matters most — a confidently-recalled fabrication is worse than a confidently-
described wallpaper.

**Invariant #11, hard rule: an inference is never auto-promoted to a fact.**
Promotion requires a second independent observation or explicit user
confirmation. No background process promotes anything.

## Deliverable 3 — context engine

One always-warm object, **updated incrementally, never rebuilt per request**:

```
Context = { identity, session, recent_episodes[k], relevant_semantic[k],
            perception_state, calendar_window(±24h), active_projects,
            available_tools, permissions, time, system_state }
```

- **Budget the assembly.** Hard token ceiling, log utilisation every request. A
  context engine that silently grows is how a 2 s answer becomes 12 s in week 3.
- **Retrieval is hybrid** — semantic + recency + explicit-mention boost. Do not
  use pure vector similarity; it fails on temporal queries, which are most of
  what a personal assistant is actually asked.

## Deliverable 4 — inspection CLI

`wellsy memory inspect` prints all semantic memory as readable markdown.
Hand-editing that file must change subsequent behaviour with no code change.
This is invariant #10 and it is also the only practical way to debug a memory
system.

## Acceptance

1. **A1** passes from a full cold start, twice: recall names a real topic from a
   prior day, every claim traceable to a stored episode. **Confabulation is a
   hard fail, not a partial pass.**
2. **A2** passes across a process restart, and hand-editing the markdown changes
   behaviour.
3. Context assembly stays within its token budget; utilisation is logged; report
   p50/p95 assembly time.
4. A temporal query ("what did I do last Tuesday?") returns correctly — prove
   hybrid retrieval beats pure vector similarity here with a measurement, not an
   assertion.
5. **No latency regression** against the step 4 table. Report it. Memory
   retrieval sitting in the hot path is the most likely source of a slow creep
   back toward the old behaviour.
6. A negative test: an inferred fact is demonstrably not promoted without a
   second observation or confirmation.

## Do not

- Do not adopt Letta or any memory service requiring an LLM call per operation.
- Do not store semantic memory in an opaque binary blob.
- Do not let the context engine grow unbudgeted.
- Do not auto-promote inferences under any heuristic, however confident.

## Report back

A1/A2 results, context assembly budget and measured utilisation, the temporal-
retrieval comparison, and the full latency table re-run to prove no regression.
