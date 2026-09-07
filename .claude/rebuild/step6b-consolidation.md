# Step 6b — Consolidation: land step 6 on top of 5b, green, on master

**Read first:** `.claude/rebuild/INVARIANTS.md` (**#8**, **#6**, **#14**),
`.claude/rebuild/step6-results.md` (all six increments — it is the log of what
this branch already did), `.claude/rebuild/step5b-results.md` §2/§3/§4/§5
(the model decisions that must survive this merge), `step4c-results.md`.
**Depends on steps 4c, 5b, 6. Blocks step 7.**

## Why this step exists

Three streams of work are finished but not reconciled, and the tree currently
cannot tell you which one is true.

1. **Step 6 is on a branch cut before 5b merged.** `rebuild/step6-native-interface`
   forked from `3a8f7e1`; 5b landed after, as `7a0a12d` (PR #11). So the branch
   you can actually run the orb from is still wired to `qwen2.5:3b` — the 2024
   interim model 5b measured and *beat*. Every step-6 CPU and latency number was
   taken against the wrong model set.
2. **Increment 6 is uncommitted.** Six modified files carrying the two `wellsy run`
   crash fixes and the orb-contrast work sit in the working tree, unversioned.
3. **A test is red on this branch and nobody owns it.**
   `tests/test_duplex.py::test_self_echo_filter_drops_echo_keeps_user` fails
   *with the step-6 changes stashed* — it is step-4c debt surfaced here.

This step does no new design. It is the merge, the collision resolution, the
re-measure, and the PR.

## Scope guard — what this step is NOT

**Do not start the step-7 convergence** (the agent as the brain of the voice
loop). `step6-results.md` increment 5 names it as the real architectural ask;
it stays the next step. `move_orb` and the identity prompt remain the stopgaps.
Do not chase the orb art pass, the GPU point-sprite path, or the global hotkey —
they stay on step 6's "Still owed" list untouched.

---

## Deliverable 1 — commit increment 6 before touching anything else

The working tree holds unversioned work. Commit it on
`rebuild/step6-native-interface` **as its own commit, before the merge**, so the
merge diff is readable and increment 6 is recoverable if the merge goes wrong.

Modified: `.claude/rebuild/step6-results.md`, `engine/interface/backends/qt/Presence.qml`,
`engine/interface/backends/qt/pointcloud.py`, `engine/voice/adapters.py`,
`engine/voice/intent_gate.py`, `engine/voice/pipeline.py`.

Untracked, each needs a decision recorded in the commit message — do not sweep
them in silently:

- `original-c74c21520a6153e0940bd240c4a3633e.mp4` — 7.8 MB, the owner's orb
  reference clip. It is an input to art direction, not source. Either give it a
  real name under a reference directory or `.gitignore` it. **A 7.8 MB binary
  does not go into the tree under a hash name.**
- `spec/results/streaming-2026-09-03.txt`, `streaming-2026-09-04.txt` — measured
  evidence. These belong in the tree; `spec/results/` already tracks its siblings.

## Deliverable 2 — merge master, and resolve the model collision correctly

`git merge master` into the branch (**merge, not rebase** — five WIP commits
rebased over a rewritten `adapters.py` is a worse conflict, three times over).

Two files conflict, and the conflict is entirely about model defaults:

| File | 5b's change | Step 6's change | Resolution |
|---|---|---|---|
| `engine/voice/adapters.py` | `build_llm()` default `qwen2.5:3b` → `qwen3:4b-instruct-2507-q4_K_M`, with the measured rationale in the docstring | `build_llm()` replaced wholesale by `SeamLLMService` (one stage, two models) + `_resolve_ollama_model()` | **Both win.** Keep step 6's `SeamLLMService` architecture; take 5b's *models* and 5b's measured rationale into its docstring. |
| `engine/voice/pipeline.py` | header comment + `SYSTEM_PROMPT` preamble renamed to the 5b model | header comment + `SYSTEM_PROMPT` rewritten for the identity fix (increment 5) | **Both win.** Step 6's identity prompt body, 5b's model names in the surrounding comments. |

The two defaults that must be true when the merge is done:

- text/fast/planner: **`qwen3:4b-instruct-2507-q4_K_M`**
- VLM: **`qwen3-vl:2b-instruct-q4_K_M`**

Note a discrepancy already in the branch: the increment-6 *code* uses
`qwen3-vl:2b-instruct` while the increment-6 *prose* in `step6-results.md` says
`WELLSY_VLM_MODEL` defaults to `qwen2.5vl:3b`. The code is right, the doc is
stale — fix the doc, do not "fix" the code back.

`_resolve_ollama_model()`'s quant-suffix tolerance is what makes the bare
`qwen3-vl:2b-instruct` resolve against the pulled `-q4_K_M` tag. Verify that
against `/api/tags` on the running server rather than assuming it.

Also check, do not assume: `engine/agent/models.py`, `spec/model-inventory.md`,
and `engine/inference/backends/openai_http.py` came from master's side and should
need no hand-editing. Confirm no step-6 commit reintroduced a `qwen2.5` default
anywhere. `grep -rn "qwen2.5" engine/ spec/` should return only historical prose
that explicitly labels itself as the beaten incumbent.

## Deliverable 3 — the red test

`tests/test_duplex.py::test_self_echo_filter_drops_echo_keeps_user` fails with a
`TimeoutError`. Two candidate causes, and you must establish which before fixing:

- the fuzzy self-echo matcher itself hangs or is pathologically slow on the
  test's inputs (a real step-4c defect — the open-air gate depends on this
  filter, so it would be shipping broken), or
- `pipecat.tests.utils.run_test`'s harness contract changed under a dependency
  bump, and the *test* is stale while the filter is fine.

They have opposite fixes and only one of them is a product bug. Determine it by
calling the matcher directly, outside the pipecat harness, with the same strings.
Report which it was. If it is the first, it invalidates a step-4c "tested" claim
and that correction goes in `step4c-results.md` — do not quietly fix it.

## Deliverable 4 — re-measure what the merge invalidated

The heavier model changes the machine's steady state, so step 6's numbers no
longer describe the shipped configuration.

1. **CPU profile** — re-run `wellsy orb --profile-cpu` for asleep / idle /
   acting / HUD with the 5b model set resident (5.2 GB, both roles pinned
   `keep_alive:-1`). Budgets unchanged: 1 % / 1 % / 3 % / 6 %. Increment 6's
   numbers (asleep p95 0.75 %, acting p95 2.83 %) are the baseline to compare
   against. If a row now misses, say so and name the lever — do not trim points
   until it passes and then report the pass without the trade.
2. **The §1 fast row** — `wellsy voice` end to end, wake → first word, against
   `qwen3:4b-instruct-2507`. 5b projects ~633 ms p50 from component numbers;
   this is the first chance to measure it through the real pipeline with the orb
   co-running. n ≥ 20, p50 and p95, timestamp at the first PCM sample written to
   the output device.
3. **One live `wellsy run`** — orb up, speak to it, ask it something about the
   screen (the increment-6 crash path), tell it to move to a corner, Ctrl-C out.
   This is the acceptance that matters and no automated test replaces it. Record
   what actually happened, including anything that felt wrong.

Full suite green, including `tests/test_portability.py` and the honesty test in
`tests/test_interface_state.py`. Report the test count; step 6 documented 186 and
that number should now be higher, not equal.

## Deliverable 5 — results doc and PR

Append a final increment to `.claude/rebuild/step6-results.md`: the merge and how
each collision resolved, the red-test verdict, the re-measured table with the old
numbers beside the new ones, and the live-run account. Then correct increment 6's
stale `qwen2.5vl:3b` line.

Open the PR to `master`. Step 6's "Still owed" list carries forward as-is minus
anything this step actually closed — and be strict about what "closed" means.

## Acceptance

- [ ] Increment 6 committed; the mp4 and the two `streaming-*.txt` each have a
      recorded disposition.
- [ ] `master` merged in; both model defaults are the 5b winners; `SeamLLMService`
      and the identity prompt both survive.
- [ ] The red duplex test is diagnosed (product bug vs stale test), fixed, and the
      verdict written down — in `step4c-results.md` if it was a product bug.
- [ ] Full suite green, count reported.
- [ ] CPU profile re-run against the 5b model set; every row pass/miss stated
      honestly with the trade named.
- [ ] §1 fast row measured end to end at n ≥ 20, p50/p95, method recorded.
- [ ] One live `wellsy run` performed and written up — including the screen
      question and the move command.
- [ ] `step6-results.md` updated; PR open to `master`.

## The standing rules

Numbers or nothing (#6): no row lands without its method next to it. Nothing is
"tested" because it was written carefully — it is tested because a test failed
first. If something is broken or unverified when you finish, the deliverable is
the honest sentence saying so, not a green checkbox. Every file this work touches
lives inside this repo.
