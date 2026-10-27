# WELLSY status

The master session maintains this file. See `.claude/MASTER.md` §7.

## Now
- **Phase 1 (voice + brain + model picker): BUILT; LIVE RUN DONE 2026-10-26; one "Done when" line fails.** Branch `rebuild/phase1-voice-brain`.
  Owner's live run, own voice, laptop speakers, browser transport (16:15-16:20): 16 user turns, 17 replies, 0 replies cut off,
  1 of 16 user turns was echo (the pyaudio mic on speakers: every reply cut, 3 of 10 turns echo). 4 research tasks, 1 cancelled by voice.
  - Spoken replies < 1 s: **FAIL.** Live p50 1.47 s over 10 turns (scripted: p50 1.22-1.26 s). Gemini 3.8 Live alone is 1.0-1.1 s. Needs a decision.
    Turns right after a `delegate` call took 9.8-16.2 s: fixed 2026-10-27 (decision log), now 0.5-1.1 s to "on it".
  - Research answered out loud + shown in the HUD: **PASS (live).** e.g. "AI news research", 14 sources, $0.117, 56 s (DeepSeek).
  - Brain swap DeepSeek / GLM / Claude is one setting: **PASS.** `brain = "glm"` in settings.toml, all three answered.
- **Owner to-do:** open the Phase 1 PR; decide the latency bar (see Blockers); add OpenAI credit to test Premium voice; revoke the old Gmail app password.

## Blockers
- **Latency bar vs Gemini Live** (owner decides). Gemini 3.1 Flash Live Preview: p50 0.85 s raw, about 1.05 s with VAD. gpt-realtime-2.1 unmeasured (no credit).
- **Premium voice untested** (owner): the OpenAI account returns insufficient_quota.

## Pinned components (pinned 2026-10-24; cutoff 2026-10-10)
`[tool.uv] exclude-newer = 2026-10-10` holds the whole tree, transitive deps included, to releases at least two weeks old.

| Component | Pin | Released | Key dependencies (resolved) |
|---|---|---|---|
| deepagents | 0.7.23 | 2026-10-07 | langchain 1.4.4, langchain-core 1.6.9, langgraph 1.2.14. Latest is 0.7.32: 9 releases in 10 days |
| pipecat-ai[google,local,webrtc,runner] | 1.12.0 | 2026-09-26 | google-genai 2.29.0, openai 3.28.0, aiortc 1.15.0, fastapi 0.143.0, pipecat-ai-prebuilt 1.3.0. Was 1.8.1; the 19 HUD tests pass on 1.12.0 |
| langchain-openrouter | 0.2.9 | 2026-09-22 | openrouter 0.10.8 (needs <1.0, latest is 1.3.x) |
| composio + composio-langchain | 0.25.0 | 2026-09-29 | **composio-client 2.0.0rc8** (pre-release, 2026-09-21; allowed only for this package) |
| langchain-mcp-adapters | 0.3.2 | 2026-08-06 | mcp 1.30.0 |
| @playwright/mcp (npm) | 0.0.83 | 2026-09-28 | playwright 1.64.0-alpha-1790635538000 (alpha); Node ≥18 |
| langchain-tavily | 0.2.18 | 2026-04-16 | web search for the brain. `langchain-parallel` 0.5.0 needs openai<2 (Pipecat has 3.28) |
| truststore | 0.10.4 | (resolved) | TLS via the OS store: python.org's macOS Python has no root certs, Tavily failed every call |
| Local extra: pipecat-ai[kokoro,mlx-whisper,whisper], langchain-ollama | 1.12.0, 1.1.0 | | kokoro-onnx 0.6.1, mlx-whisper 0.4.3, faster-whisper 1.2.1 |
| Dev: pipecat-ai[evals] | 1.12.0 | | the spoken test harness (Kokoro voice) |

## Models and prices (checked 2026-10-24, USD per 1M tokens)
| Role | Model | ID in settings | In | Out | Source |
|---|---|---|---|---|---|
| Brain (Value) | DeepSeek V4.1 Flash | `deepseek/deepseek-v4.1-flash-1017` (DeepSeek API: `deepseek-flash`) | 0.30 (0.15 off-peak) | 1.20 (0.60 off-peak) | api-docs.deepseek.com/quick_start/pricing |
| Long runs | GLM-5.3 | `z-ai/glm-5.3` | 1.40 | 4.40 | docs.z.ai/guides/overview/pricing |
| Hard planning | Kimi K3 | `moonshotai/kimi-k3` | 3.00 | 15.00 | Moonshot endpoint, openrouter.ai/api/v1/models/moonshotai/kimi-k3/endpoints (Kimi's page did not render prices) |
| Premium brain | Claude Opus 5.5 | `anthropic/claude-opus-5.5` (API: `claude-opus-5-5`) | 4.00 | 20.00 | platform.claude.com/docs/en/about-claude/pricing |
| Premium brain | GPT-6 Astra | `openai/gpt-6-astra` | 10.00 | 50.00 | openrouter.ai/api/v1/models |
| Web search | Tavily basic search | `[search]` | $0.008/search, 1,000 free/month | | tavily.com/pricing |
| Voice (Value) | Gemini 3.8 Live (stable) | `gemini-3.8-live` | audio 3.00 ($0.005/min) | audio 12.00 ($0.018/min) | ai.google.dev/gemini-api/docs/pricing |

- **DeepSeek V4 Flash is superseded by V4.1 Flash.** DeepSeek's pricing page says `deepseek-v4-flash` is retired and its requests
  are served by DeepSeek-V4.1-Flash-1017.
- **Kimi K3.1 Pro** (`moonshotai/kimi-k3.1-pro`) came out 2026-10-23 at $2/$10. It succeeds K3 and is cheaper. Too new to adopt; re-check after 2026-11-06.
- Pipecat 1.12's Gemini Live service defaults to the old `gemini-2.5-flash-native-audio-preview-12-2025`. Phase 1 must
  pass the settings model.
- OpenRouter's headline price is its cheapest endpoint. Those are often small resellers, so the table uses each maker's first-party price.

## Latest acceptance results
- 2026-10-24, Phase 1, scripted (Pipecat eval harness, Kokoro voice, real Gemini/OpenRouter/Tavily):
  latency 20/20 turns answered, p50 1.22 s / p95 1.66 s (fail); tasks.yaml 2/2 (delegate, talk while it runs,
  two tasks, cancel by label); Local preset 2/2. Cost per research task (LLM, OpenRouter usage.cost; search adds
  $0.008 x calls at list price): DeepSeek V4.1 Flash $0.0096 (7 searches), GLM-5.3 $0.041 (6), Claude Opus 5.5 $0.207 (3).
- The 20-task test (PLAN.md §5) first runs at the end of Phase 3.

## Decision log
- 2026-10-27: on Gemini 3.8 Live the voice says "on it" before calling `delegate` (it ended the call's turn with no audio, 9.5 s of silence), and WELLSY sends no progress notes mid-task: any text sent while a NON_BLOCKING call is pending (client content or realtime text) stalls 3.8 Live, so the result was never spoken unless the user talked (raw SDK, 3 of 3; without it, spoken 0.7 s after it lands). Now: "on it" 0.5-1.1 s after the request (5 of 5), result spoken unprompted (3 of 3, browser). No spoken progress on Gemini; the Local preset keeps it.
- 2026-10-24: `wellsy talk` audio goes through the browser (Pipecat SmallWebRTC + its prebuilt page, 127.0.0.1) for WebRTC echo cancellation. On the pyaudio mic, laptop speakers cut every reply: 22 interruptions in 36 s, 3 of 10 "user" turns were Wellsy's own words. `--local` keeps the direct mic for headphones. Checked in headless Chrome: greeting, a spoken question answered, latency 1.27 s (unchanged); the speaker echo itself is the owner's run.
- 2026-10-24: voice = Gemini Sulafat, expressive delivery via the prompt (3.8 Live rejects affective dialog). Name "Wellsy" said right ~3 of 4 times, never "Wesley" (36 samples, Whisper-checked); Gemini Live has no pronunciation control.
- 2026-10-24: Phase 1 cancel is `cancel_task(label)`. Pipecat's `cancel_delegate` picks a task by an id Gemini Live never receives.
- 2026-10-24: brain answers through a `return_direct` tool. LangChain `response_format` truncated on GLM-5.3 and was rejected by Claude Opus 5.5.
- 2026-10-24: web search = Tavily via `langchain-tavily`. OpenRouter's `openrouter:web_search` ($0.001-0.005) is cheaper but langchain-openrouter 0.2.9 cannot bind it or return its citations.
- 2026-10-24: Gemini Live keeps server-side turn-taking (HIGH end sensitivity, 300 ms). Thinking level is rejected by 3.8 Live; budget 0, 150 ms and local turns were all slower.
- 2026-10-24: Phase 0 done (PR #24): doctor 30/30 green live. Old `local_store.json` deleted by the owner.
- 2026-10-24: Phase 0 built. `wellsy doctor`/`profile`/`connect`; presets in `engine/settings.toml`. Value brain is DeepSeek V4.1 Flash, because V4 Flash is retired.
- 2026-10-24: owners log into sites inside Chrome launched by Playwright MCP. Playwright's mock keychain on macOS means
  cookies from a normal Chrome window would not decrypt. Site checks run headed: Myntra blocks headless Chrome.
- 2026-10-24: Composio agent skill installed project-scoped (`.agents/skills/composio`, symlinked into `.claude/skills`).
- 2026-10-23: master-session prompt (`.claude/MASTER.md`) and this file added.
- 2026-10-22: reset merged (PR #22). Only `engine/interface/` is kept. PLAN.md is the only plan.
- 2026-10-22: default models are the cheapest competitive ones: DeepSeek V4 Flash (brain),
  with GLM-5.3 and Kimi K3 for escalation, and Gemini Live (voice). Claude and GPT are Premium only.
- 2026-10-22: no lock-in to any provider. deepagents replaces the Claude Agent SDK.
- 2026-10-22: JARVIS scope (any task, not email only). Results are shown on screen as well as spoken.
- 2026-10-22: the owner retired the "no cloud" and "lightweight" rules. Best value on the market comes first.
- 2026-10-22: the live run of the old local stack failed. It sent an email to the wrong address. Reset decided.
