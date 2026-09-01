# Step 5 results — agent runtime: LangGraph, MCP tools, policy gate, audit log

**Session date:** 2026-09-01 · **Branch:** `rebuild/step5-agent-runtime` ·
Depends on step 2 (satisfied). Driven entirely by **typed text** (Deliverable 5).

---

## 1. What shipped

New package `engine/agent/` (nothing here existed before this step):

| File | Delivers |
|---|---|
| `backends/base.py` | platform-neutral `PimBackend` protocol + plain data types |
| `backends/portable.py` | JSON store under `runs/agent/pim_store.json` — **the default**, deterministic, seeded relative to `today` |
| `backends/macos.py` | `osascript` (JXA) backend — darwin-only, `WELLSY_PIM_BACKEND=macos`, acceptance-relevant subset only |
| `servers/pim.py` | FastMCP stdio server: Calendar, Reminders, Mail, Notes, Contacts (19 tools + 1 deliberately unannotated) |
| `servers/fs.py` | FastMCP stdio server: filesystem scoped to explicit allowed roots (5 tools) |
| `servers/_break.py` | `WELLSY_AGENT_BREAK_TOOLS` — the only sanctioned deliberate-failure injection (A11) |
| `policy.yaml` | the sidecar, keyed by `<server>.<tool_name>`; 23 annotated tools |
| `policy.py` | `PolicyGate.check(tool, args, ctx) -> Decision(allow\|confirm\|deny)` — 150 lines, no engine, no OPA |
| `autonomy.py` | `AutonomyLedger` — the autonomy *level*, read off the audit log, never a flag |
| `audit.py` | JSONL audit log; pending line written **before** the action returns (#12); extends `honesty/provenance.py` |
| `models.py` | two model roles (`fast` / `planner`) + deterministic `acknowledgement()` |
| `mcp_client.py` | `AgentTools` — `langchain_mcp_adapters.MultiServerMCPClient`, one persistent session per server, `list_tools()` with full schemas |
| `graph.py` | the LangGraph state machine: `plan → dispatch → policy_check → act → verify → … → report` |
| `runner.py` | `run_agent(outcome, approver=…)` — drives the graph, services every `interrupt()` |
| `cli.py` | `wellsy agent` / `wellsy tools` / `wellsy audit` / `wellsy autonomy` |

**Tests:** 21 new (`test_agent_policy.py` 9, `test_agent_audit.py` 4,
`test_agent_runtime.py` 8). **Full suite 142 green** (was 121), tree clean.

`list_tools()` returns **24 tools** with full JSON schemas (acceptance item 1: ≥ 15). ✔

---

## 2. Dependencies — verified 2026-09-01 (INVARIANTS #8)

| Package | Pinned | Released | Why this pin |
|---|---|---|---|
| `langgraph` | 1.2.11 | 2026-08-11 | `interrupt()` is the approval gate (D53); checkpoint-per-node makes A11 possible |
| `langchain-mcp-adapters` | 0.3.2 | 2026-08-06 | MCP tools → LangChain tools |
| `mcp` | 1.29.1 | — | protocol revision **2025-06-18**. **Not** the 2026-07-28 rewrite: `langchain-mcp-adapters` 0.3.2 core-pins `mcp<2.0.0`, so SDK v2 would break the D53 integration |
| `langchain-openai` | 1.6.0 | — | `ChatOpenAI` against the same local OpenAI-compatible endpoint the voice path uses |
| `pyyaml` | 6.0.3 | — | the policy sidecar |

Side-effect of the resolve: `websockets` 17.1 → **16.1.1** (pipecat still
imports; 142 tests green).

---

## 3. Ratified deviations

1. **We authored the MCP servers** (`servers/pim.py`, `servers/fs.py`) instead
   of adopting a community macOS Apple-app MCP server. Verified 2026-09-01: the
   candidates (`apple-mcp`, `macos-mcp`, `Apple-MCPs`) are 2-commit repos, no
   tagged release, a Node/bun runtime dependency, **no Mail tools**, and **no
   read-only / safety-mode flag**. None clears INVARIANTS #8. Authoring FastMCP
   servers *is* using the standard (MCP) — it is not the bespoke tool registry
   the step forbids.
2. **MCP held at 1.x**, not the 2026-07-28 stateless rewrite — forced by the
   adapter pin above. Revisit when `langchain-mcp-adapters` supports SDK v2.
3. **The portable JSON PIM backend is the default.** The macOS `osascript`
   backend is opt-in and covers only the acceptance-relevant operations. Live
   verification against a real calendar / mail account (A3–A6 end to end) is
   **owed** and needs the owner at the machine, like step 4b.
4. **LangGraph checkpointer is `InMemorySaver`.** Enough for A11 within one run
   (partial progress survives the broken step). A `SqliteSaver` swap for
   cross-process durability is a one-liner, not done.

---

## 4. Acceptance — item by item (all typed-text, scripted planner)

| # / scenario | Test | Result |
|---|---|---|
| 1 · `list_tools()` ≥ 15 w/ schemas | `test_list_tools_returns_15_plus_with_schemas` | **24 tools**, every one with a JSON schema ✔ |
| 2 · A5+A6 · draft ≠ send; send gated; deny → honest, no retry, audit line | `test_draft_then_send_denied_does_not_send` | draft (risk 1) runs silent; send (risk 2) blocks; **deny → not sent, `attempts==0`, `status=denied`, denial audit line, sent folder unchanged**; approve → sends, read-back verified ✔ |
| 3 · ask twice, no approval, risk-3 never runs | `test_asking_twice_without_approval_never_runs_risk3` | `fs.fs_delete_file` denied twice; file still on disk ✔ |
| 4 · A4 · reversible mutation gated + **independent** read-back | `test_reversible_mutation_is_gated_and_verified_by_readback` | move gated → approved → moved; read-back is a **separate `calendar_get_event`**, not the move's return; audit line has `readBack.verified=true` ✔ |
| 5 · A11 · broken tool at step 2 of 4 | `test_midplan_tool_failure_preserves_progress` | s1 ok, **s2 error `attempts==3` (1 + retry limit 2)**, s3 ok, s4 ok; `status=partial`; report says "partly done / failed / succeeded"; broken step has no `result` (no fabricated success); 3 `error` audit lines ✔ |
| 6 · A12 · audit read-back from the log | `test_audit_readback_matches_the_log` | `audit.summarize(plan_id)` tool list & order == `step_results`; every `outcome` matches ✔ |
| 7 · unannotated tool = risk 3, fail closed | `test_unannotated_tool_treated_as_risk3` + `test_unannotated_tool_is_risk3_fail_closed` | `pim.debug_echo` (no `policy.yaml` entry) → risk 3, `confirm`, never `allow`; denied when approval declined ✔ |
| A10 · ambiguity → exactly one question | `test_ambiguity_asks_exactly_one_question` | `{"clarify": …}` → `status=clarify`, one question, zero steps ✔ |
| A3 · calendar read | real end-to-end run (`wellsy agent "What is on my calendar tomorrow?" --yes`) | **passes**: planner (`qwen3:4b`) emits a 1-step `calendar_list_events` plan with the correct tomorrow window; fast reporter (`qwen2.5:3b`) returns **one paragraph** naming the three real seeded events, no invented entries, correct local times, read-back verified. Live-account read is deviation 3. |

Not in step-5 scope: A9 end-to-end with the model reporter (the paragraph path
is wired and unit-tested via `deterministic_report`; a live model reporter run
is light), A13 (proactive), autonomy promotion inside a live multi-run session.

---

## 5. The autonomy rule — as implemented

`PolicyGate.check`:

* risk 0 → **allow** (silent).
* risk 1 (`create draft`, `create reminder`, `write to scratch`) → **allow**
  unless the sidecar flags `requires_approval`.
* risk 2 (`send mail`, `create/move event`) → **confirm**, until
  `AutonomyLedger.clean_runs(capability) >= WELLSY_AUTONOMY_CLEAN_RUNS`
  (default 3), then **allow** with `approvalSource="autonomy:promoted"`.
  A "clean run" = a finalised audit entry for that capability with
  `outcome="ok"`, a `readBack` that verified, and `approvalSource` starting
  `user:`. **One error or denial for the capability resets the streak.**
* risk 3 (`delete`, shell, write outside roots) → **confirm**, always. Never
  promoted, regardless of history (`test_risk3_never_promotes`).
* An `fs.*` write/delete whose `path` argument escapes every allowed root is
  forced to risk 3 even though the sidecar keys the tool, not the args.
* Unannotated → risk 3, `confirm`, `annotated=False`.

There is **no persisted autonomy state** to tamper with — the verdict is
recomputed from `runs/agent/audit.jsonl` every check.

---

## 6. Two model roles (Deliverable 2b) — wired, and measured

`models.get_model("fast" | "planner")` → `ChatOpenAI` on the local endpoint.
Defaults: `fast=qwen2.5:3b` (reasoning off), `planner=qwen3:4b` (reasoning on).
`runner.run_agent` emits `models.acknowledgement(outcome)` (deterministic, no
model) the instant a request routes to the planner — the acknowledge-then-
deliver rule.

**Measured, single streamed turn, planner prompt + 24-tool catalog, via httpx
against `/v1/chat/completions`, models warm, ctx 4096** (a ≥ 20-trial campaign
is **owed** — see §8):

| Role | Model | TTFT | tok/s after first | full turn |
|---|---|---|---|---|
| fast | `qwen2.5:3b` | **0.19 s** | 88.7 | 0.89 s (complete plan-shaped JSON) |
| planner | `qwen3:4b` | **33.2 s** | 64.7 | 34.2 s (62 content deltas after ~2100 reasoning tokens) |

The planner number is the **step-4b reasoning tax, now measured on the planner
path itself.** 33 s TTFT is unshippable even against the "3–4 s acceptable"
planner budget. Acknowledge-then-deliver hides the *first word* but not a 33 s
wait for the actual answer. **`qwen3:4b` on Ollama 0.33.2 is not the planner**
— it needs bounded thinking, a working think-off, or a different model. This is
the same open question as the VLM reasoning pass and is now recorded debt.

`qwen2.5:3b` in the fast slot is **interim**, carried from step 4b — a 2024-era
model kept only because it clears the number. The Deliverable-2b bench-off of
current non-reasoning instruct models (and recording the losers) was
**explicitly deferred this session** by the owner; it remains owed before this
default is blessed (INVARIANTS #8).

---

## 7. Report back — the numbers that unblock the hardware purchase

Machine of record: Apple M4 Pro, **25.8 GB** unified, macOS 15.5 (darwin/arm64).

### Final model sizes & residency

| Role | Model | Resident size (`ollama ps`, ctx 4096) | Resident or on demand |
|---|---|---|---|
| fast | `qwen2.5:3b` | **2.2 GB** | resident (`keep_alive:-1`) |
| planner | `qwen3:4b` | **3.2 GB** | resident (`keep_alive:-1`) |
| VLM | `qwen3-vl:4b` | **3.6 GB** | resident (`keep_alive:-1`) |
| **all three co-resident** | | **9.0 GB** | |

Plus the step-4 stack: faster-whisper `base.en` **626 MB**, Kokoro TTS
**697 MB**, Silero VAD ~20 MB.

### Runtime resident memory (python side, models excluded — they live in the
ollama server process)

`psutil` proc-tree, full tool layer warm, single sample:

| Process | RSS |
|---|---|
| runner (LangGraph + MCP client + langchain-core) | 84.8 MB |
| `pim` MCP server subprocess | 60.5 MB |
| `fs` MCP server subprocess | 59.5 MB |
| **total agent-runtime tree** | **204.7 MB** |

So the **agent runtime itself is cheap** (~0.2 GB). The budget is the models.

**Peak vs steady:** peak == steady here — the servers are stdio-persistent, the
graph holds no large buffers, `InMemorySaver` checkpoints are small dicts. No
measurable growth across a 4-step plan.

### Steady-state full-stack estimate (warm, all roles resident)

9.0 GB (LLM/VLM) + 1.3 GB (ASR+TTS) + ~0.2 GB (agent runtime) + perception
(YOLOE detector, measured elsewhere) ≈ **~11 GB before the OS and the GPU
framebuffer**. Fits the 25.8 GB dev box with room; see Jetson below.

### Tokens/sec needed to hold the §1 latency budget under tool-calling load

* **Fast path** (§1: < 1500 ms p50 to first word): needs TTFT < ~1 s and
  ≳ 30 tok/s to keep the TTS buffer fed. `qwen2.5:3b` (0.19 s / 88.7 tok/s)
  clears it with a wide margin **and leaves headroom for the ASR+TTS+VAD
  contention measured in step 4**.
* **Planner**: off the hot path by construction, so its throughput sets
  *time-to-delivered-answer*, not first word. Target: a ≤ 6-step plan in
  **≤ 4 s** → needs ≳ 50 tok/s **and no unbounded reasoning prefix**. Neither
  holds for `qwen3:4b` today (34 s).

### Does the Jetson Orin NX class target (~16 GB, 100 TOPS) constrain the desktop build?

**Yes — decisively.**

* 9.0 GB of LLM/VLM + 1.3 GB ASR/TTS + runtime + perception + **ROS 2 later**,
  on 16 GB shared with the OS *and* the GPU framebuffer, means **three
  LLM/VLM roles cannot be co-resident with headroom on Orin NX.**
* Design consequence for the desktop build: **size for "fast (≤ 2.5 GB)
  resident + exactly one of {planner, VLM} resident, the other loaded on
  demand"**, not all three. The M4 Pro's slack is slack — do not spend it on a
  topology the robot cannot run (stack-teardown §12.2).
* Levers, cheapest first: (a) one 3–4B model serving fast+planner with a *real*
  thinking on/off (not available on the qwen3/Ollama combo tested); (b) a
  smaller non-reasoning VLM — `qwen2.5vl:3b` is pulled (3.2 GB) and is the
  likely route, same as the step-4b VLM debt; (c) accept a ~3–10 s model-swap
  when switching between planner and vision.
* **Recommended box:** the desktop dev target can stay 24 GB, but the model
  *selection* must be validated at a 16 GB working set before any Jetson
  purchase. A single 24 GB Orin (G1 Comp class) removes the constraint; Orin NX
  16 GB (G1 EDU) does not, and that is production target #1.

---

## 8. Debt carried forward

1. **Planner model** — `qwen3:4b` measured at 33 s TTFT on the planner path.
   Unshippable. Needs bounded thinking / working think-off / a different
   reasoning-capable planner. Same family of problem as:
2. **VLM reasoning pass** — `qwen3-vl:4b` still reasons uncontrollably
   (step 4b). `qwen2.5vl:3b` pulled; route vision through it or a bounded-think
   VLM. A ≥ 20-trial VLM TTFT campaign is owed (A7/A8 gate).
3. **Fast-slot bench-off** — current non-reasoning instruct models vs
   `qwen2.5:3b`, with the losing numbers recorded. Deferred this session by
   decision; owed before the default is blessed (INVARIANTS #8).
4. **Planner/fast throughput ≥ 20-trial campaign** — §6 has one measured turn
   per role. `wellsy bench --modality llm` extension owed.
5. **macOS `osascript` backend live verification** — A3/A4/A5/A6 against a real
   Calendar / Mail account. Owner at the machine (like step 4b). The backend
   covers the acceptance surface; the rest raises `ToolError(not_implemented)`.
6. **Durable checkpointer** — swap `InMemorySaver` → `SqliteSaver` for
   cross-process resume.
7. **A9 with the model reporter** end-to-end; **A13** (proactive) — later
   phases, not step 5.
8. **`WELLSY_LLM_TIMEOUT` default raised 60 → 120 s** to accommodate the cold
   planner; a symptom of debt #1, not a fix.
9. **Intermittent `libc++abi: recursive_mutex lock failed` at pytest teardown**
   when the full suite mixes the pipecat (anyio) tests and the agent (stdio MCP)
   tests — a child-process shutdown race, non-deterministic (1 in ~4 full
   runs), **exit code stays 0, no test fails**. Isolated agent-test runs never
   show it. Worth pinning down before CI gates on the full suite.
