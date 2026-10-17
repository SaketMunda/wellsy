# Step 9 results — the agent is the brain of the voice loop

**Session date:** 2026-10-17 · **Branch:** `rebuild/step9-assistant-convergence`
(off `master` @ `cdfac69`) · **Machine:** M4 Pro, macOS 15.5, two 1920×1080
displays · **Server:** Ollama **0.40.5** · pipecat 1.8.1 · LangGraph 1.2.11 ·
langgraph-checkpoint-sqlite 3.1.2.

**One-line verdict:** WELLSY now does what you ask by voice. A spoken request
that needs a calendar, reminders, mail, notes or files goes through the
LangGraph agent: honest ack, plan, read-back spoken before any gated commit,
spoken yes/no, verified result spoken back. Seven requests (read, silent write,
approval, refusal, no-capability refusal, multi-step draft-and-send, follow-up)
all behave correctly on the final code. **Not done:** the live run with a
microphone against the owner's real Calendar/Mail. Everything here was driven
with typed transcripts through the real stages, against the portable PIM store.

---

## 0. What changed, in one table

| Deliverable | Shipped | Where |
|---|---|---|
| 5c collapse | `qwen3.5:4b-q4_K_M` everywhere (voice text + vision + routing, agent `fast` + `planner`, `openai_http`, `metrics.py`); `reasoning_effort:"none"` on **every** request; `SeamLLMService`'s model flip removed (a vision turn is now the same model with its own short prompt, no history, no tools) | `agent/models.py`, `voice/adapters.py`, `inference/backends/openai_http.py`, `voice/metrics.py` |
| 1. One runtime | The voice LLM carries one tool, `use_tools`; the model's own tool call routes the turn into a persistent `AgentRuntime` (MCP, policy gate, audit, read-back). Text seam intact (D49). `InMemorySaver` → **`AsyncSqliteSaver`** | `voice/agent_bridge.py`, `agent/runner.py` |
| 2. Three tiers | deterministic (IntentGate) → conversational (model text, unchanged path) → agentic (deterministic ack, then the graph). No classifier | `agent_bridge.py`, `intent_gate.py` |
| 3. Spoken approval | `interrupt()` is asked aloud with the read-back and the HUD opens at the same time; answered by speech (fixed grammar), click or Esc, first wins; anything unclear is a no, spoken; one no ends that run's asking; 45 s timeout = no | `honesty/approval.py`, `ApprovalBroker`, `session.ApprovalRelay.listener` |
| 4. Read-back before commit | Deterministic spoken preview of the resolved values, weekday **and** date; date-vs-words check (today/tomorrow, weekday, month-day, time, already past); a mismatch is spoken first and **forces an approval** on a step the policy would run silently | `agent/readback.py`, `graph.policy_check_node` |
| 5. Orb from the graph | Graph emits plan_ready / step_start / step_done / step_denied / reporting; orb THINKING / ACTING / AWAITING_APPROVAL / REFUSING follow them; HUD `plan`, `verify`, `provenance` (new QML kind), approval view shows the read-back and warnings | `graph.py`, `interface/taps.py`, `Hud.qml` |
| Honesty | ClaimGuard now also refuses **completed-action claims** with no evidence: every claimed verb ("sent", "scheduled") and object ("reminder", "email") needs a read-back-verified tool of that kind in the most recent agent run | `voice/claim_guard.py` |

Tests: **284 passed** (224 → 284; `tests/test_step9_convergence.py` 55 new, +5
intent cases), exit 0. The known `recursive_mutex` abort at teardown still prints.

---

## 1. 5c read first — the collapse, and what 0.40.5 still does

Re-verified on 0.40.5 before building (`runs/step9/probe_*.py`):

| Check | Result |
|---|---|
| `/v1` + `reasoning_effort:"none"` | 0 reasoning chars, answer at 97 ms warm |
| `/v1` + the old `think:false` + `chat_template_kwargs` | **197–221 reasoning chars, no content**: still ignored |
| `/v1` + `num_ctx` (top level or `options`) | ignored; a 5,200-token prompt is **silently truncated to 2,050** counted tokens |
| tool calls on `/v1`, streamed | arrive as **one delta when complete** (the ack waits for the whole call) |
| `developer` role | **dropped by the Qwen3.5 template**: a tool result sent as `developer` was ignored 3/3 ("I'll let you know when results are in"); as `system` it was read 3/3. This also silently dropped 6c's "you were asleep" note and the greeting instruction. Fixed in `build_chat_completion_params`, on the outgoing request only |
| cache, append-only session with the tool attached | warm turns 96–151 ms first word; a history-free request in between does not evict the conversation (0.69 vs 0.71 s delivery with/without a planner request between) |

`SeamLLMService` removal reason, recorded: 5c §3 measured one model as viable for
all three slots (−2.1 GB RSS, 43 % fewer image tokens, 8/10 vs 7/10 grounded),
so the text↔VL switch was dead weight. The vision turn keeps its shape (own
prompt, images only, 90 tokens). Collapsed vision, replayed: "What's on my
screen?" → a grounded description of the actual window in **4.05 s** first
speakable text (capture + two displays; n=1; 6c/5c two-display shipped figure
was ~4.45 s composed).

---

## 2. The five requests (+2) — what happened, failures included

Method: `bench/voice_agent_replay.py`. The **real** IntentGate → LLM (+`use_tools`)
→ `VoiceAgentBridge` → `AgentRuntime` (stdio MCP, policy gate, audit, read-back,
SQLite) → ProvenanceLogger → ClaimGuard chain, built by the production factories,
on the live model. Two stand-ins: **TurnCommit** for the user aggregator's turn
detection, **Recorder** for TTS. Approvals are injected as transcripts 0.8 s
after the question. Store: the seeded **portable** PIM backend
(`WELLSY_PIM_BACKEND=portable`), not a real account. Today = Saturday 17 Oct.

**Final run** (`spec/results/step9-replay-five-2026-10-17-1226.jsonl`, audit at
`runs/step9/five-final-audit.jsonl`):

| # | Said | Tier | Heard (TTSSpeak frames, then the model) | Result |
|---|---|---|---|---|
| 1 read | "What's on my calendar tomorrow?" | agentic | "Let me check your calendar." → "You have three events tomorrow: a team standup at 9:30 AM, a design review in Zoom at 3 PM, and a one-on-one with Priya at 4:30 PM." | correct |
| 2 write | "Remind me to call mom tomorrow at 6 pm." | agentic, silent (risk 1) | ack → "I've added a reminder for you to call Mom tomorrow at 6 PM." | created, verified, right date |
| 3 approval | "Book a dentist appointment on Monday at 3 pm." → "Yes, go ahead." | agentic | ack → **"I'm about to add “Dentist Appointment” to your calendar, Monday, October 19 from 3 PM to 4 PM. Shall I go ahead?"** → "I've booked a dentist appointment for Monday at 3 PM." | created, verified; audit `approvalSource: voice:yes` |
| 4 refuse | "Delete the file plan.txt in my scratch folder." → "No, don't." | agentic, risk 3 | ack → "I'm about to delete the file plan.txt. Shall I go ahead?" → **"Okay, I won't do that."** (model not re-run) | not deleted; audit denial `voice:no` |
| 4b no capability | "Order me a pizza." | conversational | "I can't order or buy anything yet." | honest refusal |
| 5 multi-step | "Draft a reply to Dana saying Thursday works for us, and send it." → "Yes, send it." | agentic, 3 steps | ack → "I'm about to send the email “Thursday works for us” to dana.kim@partner.example. Shall I go ahead?" → "I've sent the email to Dana saying Thursday works for us." | contacts_search → draft → send (`$2.id`), all verified |
| 6 follow-up | "What did I just ask you to send?" | conversational | "You asked me to send a reply to Dana confirming that Thursday works for us." | answered from context, no tool |

**It took eight runs to get there. Every failure found on the way, and its fix**
(each run is its own `step9-replay-five-*.jsonl`):

| Run | Failure (as heard) | Cause | Fix |
|---|---|---|---|
| 1145 | Answer ignored the tool result: "Checking your calendar… I'll let you know when results are in" | `developer` role dropped (§1) | `developer`→`system` on the request |
| 1145 | "I've drafted the email… and sent it" on a run where **both steps errored** | ClaimGuard's 120 s window let an earlier verified reminder vouch for it | evidence per verb and per object, from the latest run only |
| 1145 | `calendar_create_event` / `mail_create_draft` errored ("add an untitled item") | planner saw descriptions, not argument names | tool signatures in the planner catalog |
| 1145 | `draft_id: "<from_create>"` | a static plan cannot know an id a step creates | step references `"$2.id"`, resolved at dispatch; a reference to a failed step blocks the dependent step |
| 1145 | a declined delete asked twice more and waited out **two 45 s timeouts** (94 s turn) | each gated step asked independently | one no ends the run's asking |
| 1145 | "I can order a pizza for you, but I need your location…" | capability fabrication | prompt states what it can't do |
| 1150 | **"Careful: you said tomorrow, but I have Monday, October 19."** | planner put tomorrow (Sunday) on Monday | caught by the read-back → no answer → refused, nothing written. Then: a deterministic day table in the planner prompt ("tomorrow: Sunday 2026-10-18"); date check reads only the user's words |
| 1150 | dentist event created but reported **unverified** | read-back sliced `start[:19]` of `…T15:00+05:30` into the offset | parse the datetimes |
| 1153 | "I can't book appointments for you yet." | my capability list read "book" as buying | prompt: booking = adding to the calendar |
| 1155 | dentist planned as **`notes_create`**, then "I've scheduled your dentist appointment" passed ClaimGuard | 4B planner brittle to the paraphrase appended to the outcome; "scheduled" accepted any create | restatement only when the words need a reference resolved; "scheduled/booked" need a calendar tool |
| 1155 | "What did I just ask you to send?" **re-ran the request and created a second draft** | the router re-issued the previous request | tool description: questions about earlier turns are answered from the conversation |
| 1200 | "I also set a reminder for your call with mom" — never set; passed ClaimGuard on a verified *calendar* event | evidence matched the verb, not the object | the object named (reminder / email / event / note / file) needs its own verified tool |
| 1208 | startup greeting called `use_tools` on its own and read a calendar nobody asked for | the model acted with no user request | the bridge refuses a tool call with no user message behind it |
| (vision replay) | "Thanks. And what's on my calendar today?" → "Anytime." — request dropped | canned `thanks`/`help`/`presence` matched anywhere in the sentence | canned filler only when it is the whole utterance (`spec/intent-cases.json` +5) |

The read-back also caught the planner once more in run 1145: **"Careful: you
said Monday, but I have Tuesday, October 20."** That is the 5b failure (a wrong
weekday reaching a real calendar), stopped out loud before commit, twice.

**Still wrong in the final runs, logged not fixed:** one reply subject was
"Re: [Original Subject]" (a planner placeholder, run 1209; the read-back spoke it
before the send, so the user hears it and can refuse); plans sometimes add
unneeded reads (notes_list, list_messages); "Say that again, please" re-ran a
read-only calendar lookup (routing bench, below).

---

## 3. Routing and planner quality — measured, because validity was not enough

**Routing** (`bench/routing_accuracy.py`; production system prompt + pipecat's
async-tool instructions + `use_tools`; 6-message history incl. one agentic turn;
30 labelled utterances × 3 trials):

| Sampling | Prompt | Correct | needed a tool, answered without | tool on a question |
|---|---|---|---|---|
| Ollama default 1.0 / 0.95 (the **thinking**-mode row) | before fixes | 85/90 | 5 | 0 |
| card non-thinking 0.7 / 0.8 | before fixes | 87/90 | 3 | 0 |
| **card 0.7 / 0.8 (shipped)** | final | **89/90** | **0** | 1 ("Say that again, please" → re-ran a calendar read) |

Card values verified at source (`huggingface.co/Qwen/Qwen3.5-4B`, Best Practices:
"Instruct (or non-thinking) mode for general tasks: temperature=0.7, top_p=0.8,
top_k=20, min_p=0.0, presence_penalty=1.5"). Ollama already defaults top_k and
presence to those; only temperature/top_p are sent.

**Planner correctness** (`bench/planner_correctness.py`; production planner
prompt + live 24-tool catalog; temperature 0; 8 intents × 2 phrasings; a plan is
correct only with the right tool, the right resolved date/time, references
threaded, and **no mutation the user did not ask for**):

| Planner | Correct | Misses |
|---|---|---|
| `qwen3:4b-instruct-2507` (5b incumbent) | 10/16 | cannot plan a timed reminder (0/2), never plans the delete (0/2), questions (0/2, by the first check) |
| `qwen3.5:4b` before the planner fixes | 13/16 | draft-and-send 1/2, questions 0/2 |
| **`qwen3.5:4b` final** | **15/16** | "Draft a reply to Dana … and send it" drafts without sending; **`complete_plan()` now appends the send** when the user's words say send (still spoken-approved) |

5c's "20/20 plans" were schema-valid plans; this is the first correctness number.
Plan time p50 1.95 s, max 3.5 s.

---

## 4. §1, re-measured — deterministic, conversational, agentic

**Method, all rows:** n=20 warm, nearest-rank. "Composed" = ASR p50/p95 (267 /
276 ms) + the measured model-side figure + Kokoro TTFA p50/p95 (345 / 406 ms),
the same composition as 5c §5.1. Not device-timestamped: 6c did not establish
that harness and this step had no live audio session. The orb was not co-running
(no Qt in the replay); the orb's CPU rows are unchanged code (6b: ≤ 2.88 % p95).

| Row | Target p50 / p95 | Measured | Composed p50 / p95 | Verdict |
|---|---|---|---|---|
| **Deterministic** (`wellsy voice --measure`, n=20) | < 800 / < 1200 | ASR + TTS, gate 0.9–2.8 ms in replay | **574 / 589** (was 617 / 700) | **PASS, unregressed** |
| Conversational, bare one-turn prompt (`--measure`) | < 1500 / < 2500 | llm TTFT on qwen3.5 | **640 / 647** (6b: 615 / 622) | PASS (+25 ms, 5c projected ~662) |
| **Conversational, in session** (replay `rows`, system prompt + tool + history, ctx 4096) | < 1500 / < 2500 | first speakable 361 / 2356 ms | **973 / 3038** | **PASS p50 · MISS p95** (a history trim, §5) |
| ↳ same, server ctx 16384 (temporary second server, §5) | | 388 / 709 ms | **1000 / 1391** | PASS both |
| **Agentic: ack** (transcript → "Let me check…") | within the fast budget | 705 / 824 ms (tool call 702 / 821) | **1317 / 1506** | PASS (one 2.98 s outlier in the final five-run: delete) |
| ↳ same, ctx 16384 | | 653 / 710 ms | 1265 / 1392 | PASS |
| **Agentic: delivered** (read-only, first word of the real answer) | 3–4 s (planner row) | 4477 / 7834 ms | **5089 / 8516** | **MISS** |
| ↳ same, ctx 16384 | | 4297 / 6352 ms | 4909 / 7034 | **MISS** |
| ↳ breakdown at 4096: tool call · graph · delivery LLM | | 702 · **1585 / 3284** · **1313 / 3762** | | |
| Approval turns: answer → first word of result | — | 1.19 s and 2.70 s (final five-run, n=2) | | reported, n too small for p95 |

Result files: `voice-latency-2026-10-17-qwen3.5-4b-q4_K_M.json`,
`step9-replay-rows-2026-10-17-1215.jsonl` (4096, final code),
`step9-replay-rows-2026-10-17-1219.jsonl` (16384), `-1210` (before the budget fix).

**Honest reading.** The conversational path did get slower in a real session:
~1.0 s composed p50 against the 615 ms bare number. The cost is the longer
prompt (identity + tool rules + one tool schema) and Qwen3.5's 71 ms TTFT vs
24 ms. It is inside budget at p50, and the p95 miss is the trim (§5), not the
model. The delivered row misses the planner's 3–4 s: graph ~1.6 s plus a
second model pass of ~1.3 s to say the result, behind a ~0.7 s tool call.
Nothing is hidden behind the ack: the ack is honest and lands at ~1.3 s, and
the real answer lands at ~5 s.

---

## 5. The context window is the remaining lever (owner decision)

Ollama runs 4096 tokens unless `OLLAMA_CONTEXT_LENGTH` is set, `/v1` ignores
per-request `num_ctx`, and above the window it **truncates silently** (§1). So
`SeamLLMService` fits every request to a budget. On Qwen3.5 every front-trim is
a history edit → re-prefill:

| Budget | Trims in a 41-turn session | Delivery after a trim / without | Conversational p95 |
|---|---|---|---|
| 3000 (as shipped by 6c) | every ~2 agentic turns | **2.0–2.8 s / 0.9–1.5 s** (`runs/step9/rows-requests.jsonl`) | 1525 ms composed |
| 3500 (shipped now; estimate measured 5–10 % above the server's real `prompt_tokens`) | every ~3 | up to 3.8 s (bigger drops) | 3038 ms composed |
| 16384 server window (temporary `ollama serve` on :11435, owner's server untouched, then stopped) | **none** — append-only to 132 messages | 1.2 / 2.1 s p50 / p95 | **1391 ms** composed |

The window is now configurable on the WELLSY side (`WELLSY_LLM_NUM_CTX`, default
4096 → budget 3500). **Recommendation:** set Ollama's context length to 16384
(app Settings, or `OLLAMA_CONTEXT_LENGTH=16384`) and run with
`WELLSY_LLM_NUM_CTX=16384`. The cost is RSS, ~4.4 GB at 16K vs 3.7–4.0 GB at 4K
(5c §5.2, §5.4). That clears the conversational and ack p95s. Not done here, because
it is the owner's server config. One effect to know about: with no trimming the
model answered 4 repeated questions from **earlier tool results still in
context** (correct, but potentially stale) instead of calling the tool again.

---

## 6. Approval, deny, Esc, click — what is proven and how

| Claim | Proof |
|---|---|
| deny end to end into the audit log | `test_spoken_deny_end_to_end_into_audit_log`: spoken "no, don't" → audit `policyDecision: deny`, `approvalSource: voice:no` → nothing written to the store → "Okay, I won't do that." spoken → model not re-run. Live replay: the delete, `runs/step9/five-final-audit.jsonl` |
| ambiguous → refusal, spoken | grammar tests (18 phrasings); `test_unclear_answer_is_a_spoken_refusal` ("what time is it" → "I didn't hear a clear yes…", `voice:unclear`); timeout → `voice:timeout` |
| the answer never reaches the model | `test_gate_answers_pending_approval_and_forwards_nothing` (yes / unclear / stop through the real IntentGate under pipecat's `run_test`) |
| stop wins | `stop` while pending → deny + `InterruptionFrame`, and every later gated step in that run is refused silently (`test_stop_denies_pending_and_the_rest_of_the_run`) |
| click path | `ApprovalRelay.listener` → `broker.answer_threadsafe` from the Qt thread (`test_click_answers_from_another_thread`, `approvalSource: user:orb`). **Not clicked live.** |
| Esc | wired (tty ESC and the orb's Esc both call `broker.stop()` before the interrupt). **Not pressed live.** |
| durable approvals | `test_interrupted_plan_resumes_from_a_second_runtime`: runtime 1 stops at `interrupt()` and closes; runtime 2 (new MCP sessions, new SQLite connection) resumes it with `Command(resume=…)` |
| echo filter does not eat "yes, go ahead" | `build_self_echo_filter(exempt=…)` off while an approval is pending; a real echo would parse unclear → refusal |

The ack is proven never to claim: `test_ack_never_claims_an_action` runs every
ack string through ClaimGuard; the ack is deterministic (`models.acknowledgement`)
and pushed before the graph starts.

## 7. Orb and HUD

States come from graph events only (`test_orb_states_follow_graph_events`:
plan_ready → THINKING, step_start → ACTING, interrupt → AWAITING_APPROVAL, deny →
REFUSING). The honesty suite (`test_interface_state.py`) is unchanged and green.
HUD: `plan` (steps with their real policy decision), `verify` (read-back method,
confirmed or not), `provenance` (tool · status · read-back · audit id · `wellsy
audit --plan`), and the approval view now leads with the spoken read-back and
any "Careful:" warning. **Not eyeballed on the Qt panel**: driven headless and
by tests only.

---

## 8. Acceptance

- [x] 5c read; `SeamLLMService`'s flip removed, reason recorded (§1).
- [x] One runtime: the graph answers voice turns through `use_tools`; text seam intact; `AsyncSqliteSaver`.
- [x] Three tiers live; **deterministic row unregressed** (574 / 589 composed).
- [~] Conversational row: **p50 inside budget** (973 ms in session, 640 ms bare); **p95 misses at the shipped 4096 window** (3038 ms, trim); passes at 16K (§5).
- [x] Agentic row measured: ack 1317 / 1506 composed, never a claim; **delivered 5.1 / 8.5 s composed: MISS** vs the 3–4 s planner row.
- [x] Spoken approval; ambiguous → spoken refusal; deny end to end into the audit log; click and Esc wired and unit-proven (not live).
- [x] Read-back spoken before every gated commit, dates as weekday + date; a date mismatch forces approval (caught the planner twice in replay).
- [x] Orb from real graph events; `plan`/`verify`/`provenance` HUD wired; honesty test green.
- [ ] **Five real spoken requests against real accounts: NOT done.** Seven requests ran through the real stages with typed transcripts against the portable store. Owed: a live `wellsy run` with `WELLSY_PIM_BACKEND=macos`, mic and speakers.
- [x] `step9-results.md`; PR: see the session report.

## 9. Debt carried forward

- The live spoken run against real Calendar/Mail (above), with Esc and a HUD click exercised live, and the Qt HUD views looked at.
- Agentic delivered row misses (graph ~1.6 s + a second model pass ~1.3 s). Levers: 16K window (§5); streaming the result straight to TTS for simple reads; step 8's cheaper decide path.
- Planner: placeholder subjects, unneeded reads; `complete_plan` patches one known omission only.
- Routing: "say that again" re-runs a read; answers from stale tool results when nothing is trimmed.
- Read-back lookups (`calendar_get_event`, `mail_get_draft`) call MCP directly, not through the policy gate: both are risk-0 reads; noted, not changed.
- Step references cannot filter ("the design review" among several events) — `$1.id` takes the first match.
- Unchanged from before: device-timestamped §1, spoken barge-in/AEC (4c), Linux/CUDA unexecuted, the pytest-teardown `recursive_mutex` abort.
