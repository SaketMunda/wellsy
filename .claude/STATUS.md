# WELLSY status

The master session maintains this file. See `.claude/MASTER.md` §7.

## Now
- **Phase:** 0 (setup). Not started.
- **Blocked on the owner:**
  - an OpenRouter key;
  - a Google AI (Gemini) key;
  - a Composio key, with Gmail and Google Calendar connected;
  - a WELLSY Chrome profile logged into Amazon, Flipkart, Myntra, and Netflix.
- **Owner to-dos:**
  - revoke the old Gmail app password;
  - delete `~/.config/wellsy/accounts.json`. Both come from the deleted IMAP code.

## Pinned components
None yet. Phase 0 verifies and pins these:
- deepagents
- Pipecat (1.8.1 is in the repo today)
- Playwright MCP
- Composio (it depends on a pre-release client, so pin a release at least two weeks old)
- OpenRouter model IDs

## Latest acceptance results
None yet. The 20-task test (PLAN.md §5) first runs at the end of Phase 3.

## Decision log
- 2026-10-23: master-session prompt (`.claude/MASTER.md`) and this file added.
- 2026-10-22: reset merged (PR #22). Only `engine/interface/` is kept. PLAN.md is the only plan.
- 2026-10-22: default models are the cheapest competitive ones: DeepSeek V4 Flash (brain),
  with GLM-5.3 and Kimi K3 for escalation, and Gemini Live (voice). Claude and GPT are Premium only.
- 2026-10-22: no lock-in to any provider. deepagents replaces the Claude Agent SDK.
- 2026-10-22: JARVIS scope (any task, not email only). Results are shown on screen as well as spoken.
- 2026-10-22: the owner retired the "no cloud" and "lightweight" rules. Best value on the market comes first.
- 2026-10-22: the live run of the old local stack failed. It sent an email to the wrong address. Reset decided.
