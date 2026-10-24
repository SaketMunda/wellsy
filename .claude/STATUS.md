# WELLSY status

The master session maintains this file. See `.claude/MASTER.md` §7.

## Now
- **Phase 0 (setup): DONE.** Merged as PR #24. Live `wellsy doctor` on the owner's Mac, 2026-10-24: **30 green, 0 red**.
  Keys, every OpenRouter preset ID, Gemini Live, Gmail + Calendar (one read-only call each), Chrome and
  Amazon/Flipkart/Myntra/Netflix logins via Playwright MCP, and every pin all green.
- **Next:** Phase 1 (voice + brain + model picker). The master session writes the brief.
- **Owner to-do:** revoke the old Gmail app password (from the deleted IMAP code).
- **OpenRouter key:** $2.15 used of a $5.00 limit. Raise it before Phase 1 live runs.

## Pinned components (pinned 2026-10-24; cutoff 2026-10-10)
`[tool.uv] exclude-newer = 2026-10-10` holds the whole tree, transitive deps included, to releases at least two weeks old.

| Component | Pin | Released | Key dependencies (resolved) |
|---|---|---|---|
| deepagents | 0.7.23 | 2026-10-07 | langchain 1.4.4, langchain-core 1.6.9, langgraph 1.2.14. Latest is 0.7.32: 9 releases in 10 days |
| pipecat-ai[google] | 1.12.0 | 2026-09-26 | google-genai 2.29.0, openai 3.28.0. Was 1.8.1; the 19 HUD tests pass on 1.12.0 |
| langchain-openrouter | 0.2.9 | 2026-09-22 | openrouter 0.10.8 (needs <1.0, latest is 1.3.x) |
| composio + composio-langchain | 0.25.0 | 2026-09-29 | **composio-client 2.0.0rc8** (pre-release, 2026-09-21; allowed only for this package) |
| langchain-mcp-adapters | 0.3.2 | 2026-08-06 | mcp 1.30.0 |
| @playwright/mcp (npm) | 0.0.83 | 2026-09-28 | playwright 1.64.0-alpha-1790635538000 (alpha); Node ≥18 |

## Models and prices (checked 2026-10-24, USD per 1M tokens)
| Role | Model | ID in settings | In | Out | Source |
|---|---|---|---|---|---|
| Brain (Value) | DeepSeek V4.1 Flash | `deepseek/deepseek-v4.1-flash-1017` (DeepSeek API: `deepseek-flash`) | 0.30 (0.15 off-peak) | 1.20 (0.60 off-peak) | api-docs.deepseek.com/quick_start/pricing |
| Long runs | GLM-5.3 | `z-ai/glm-5.3` | 1.40 | 4.40 | docs.z.ai/guides/overview/pricing |
| Hard planning | Kimi K3 | `moonshotai/kimi-k3` | 3.00 | 15.00 | Moonshot endpoint, openrouter.ai/api/v1/models/moonshotai/kimi-k3/endpoints (Kimi's page did not render prices) |
| Premium brain | Claude Opus 5.5 | `anthropic/claude-opus-5.5` (API: `claude-opus-5-5`) | 4.00 | 20.00 | platform.claude.com/docs/en/about-claude/pricing |
| Premium brain | GPT-6 Astra | `openai/gpt-6-astra` | 10.00 | 50.00 | openrouter.ai/api/v1/models |
| Voice (Value) | Gemini 3.8 Live (stable) | `gemini-3.8-live` | audio 3.00 ($0.005/min) | audio 12.00 ($0.018/min) | ai.google.dev/gemini-api/docs/pricing |

- **DeepSeek V4 Flash is superseded by V4.1 Flash.** DeepSeek's pricing page says `deepseek-v4-flash` is retired and its requests
  are served by DeepSeek-V4.1-Flash-1017.
- **Kimi K3.1 Pro** (`moonshotai/kimi-k3.1-pro`) came out 2026-10-23 at $2/$10. It succeeds K3 and is cheaper. Too new to adopt; re-check after 2026-11-06.
- Pipecat 1.12's Gemini Live service defaults to the old `gemini-2.5-flash-native-audio-preview-12-2025`. Phase 1 must
  pass the settings model.
- OpenRouter's headline price is its cheapest endpoint. Those are often small resellers, so the table uses each maker's first-party price.

## Latest acceptance results
None yet. The 20-task test (PLAN.md §5) first runs at the end of Phase 3.

## Decision log
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
