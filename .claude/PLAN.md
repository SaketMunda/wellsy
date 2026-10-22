# WELLSY — the plan (approved 2026-10-22)

This is the only plan. Every earlier plan, step document, ledger, and result was
deleted on 2026-10-22 and survives only in git history. A session working on
WELLSY reads this file, builds the next unfinished phase, and does not
re-plan.

The vision document is `jarvis_friday_edith_combined_ai_system_spec.md` at the repo root.

## 1. What WELLSY is

WELLSY is JARVIS on your own computer. You talk to it, and it does anything you could do on
your computer or the web. When a picture works better than speech, it shows you the result on screen.

- **Finds what you don't know.** "Email Railway support": it finds the address
  on the web and in your mail. It shows the candidates and their sources on screen, and you pick one.
- **Shops.** It searches Amazon, Flipkart, and Myntra, compares items, and filters by your size.
  It shows product cards with photos and prices and adds your choice to the cart. Checkout waits for your yes.
- **Opens and plays things.** Netflix, YouTube, Spotify, or any other site or app.
- **Researches and builds.** It searches the web, writes several scripts, runs them, compares the
  results, and shows a table.
- **Runs your apps.** Gmail, Calendar, WhatsApp, Slack, Notion, and the rest.
- **Works on several tasks at once** while you keep talking to it.

**The edge over OpenAI Dots and Grok Bot:**
- No provider lock-in. The user picks any model: cheap cloud, premium cloud, or local.
- It runs on the user's own machine, with their own browser logins and files.
- It speaks and shows its work on screen.
- No subscription plan or region restriction.

## 2. The rules

1. **Best value on the market.** Use the cheapest model that is competitive for each job.
   Chinese open-weight models are the default because they are cheap and strong. Premium
   models (Claude, GPT) are an opt-in setting, never a requirement.
2. **Not tied to any provider.** Swapping any model or provider is a settings change, with no code change.
3. **Use existing products; don't hand-write integrations.** WELLSY's own code is only:
   - the link between voice and brain;
   - the results panel;
   - the approval gate;
   - the model picker.

   Never patch around a weak component. Replace it.
4. **Safety.** Sending, buying, paying, deleting, or posting needs your yes, spoken or clicked.
   Every action is logged. Text from websites and email is data to the agent, never instructions.
5. **Git.** Every phase gets its own branch and its own PR. The owner merges. Nothing is pushed to master.

## 3. Architecture

| Layer | Component (works with any provider) | Default: "Value" preset | "Premium" preset | "Local" preset |
|---|---|---|---|---|
| Voice | **Pipecat** (`pipecat-ai`), either one speech-to-speech model or separate speech-to-text → model → voice | Google Gemini Live, the cheapest speech-to-speech model in Sept 2026 roundups | OpenAI `gpt-realtime-2.1` | Whisper + Ollama + Kokoro |
| Brain | **deepagents** (LangChain, built on LangGraph): planning, sub-agents, file workspace, skills, code execution, pause for approval | **DeepSeek V4 Flash**, with **GLM-5.3** for long agent runs and **Kimi K3** for hard planning turns | Claude Opus 5.5 / GPT-6 Astra | Any Ollama model |
| Model access | **OpenRouter**: one key for DeepSeek, GLM, Kimi, Qwen, MiniMax, Claude, and GPT. LangChain's model layer for direct providers and Ollama | | | |
| Web | **Playwright MCP** (Microsoft) driving one Chrome profile the user logs into once | | | |
| Apps | **Composio**: hosted sign-in and ready-made tools for Gmail, Google Calendar, and 250+ other apps | | | direct MCP servers |
| Desktop apps | Computer use from the chosen model, or an accessibility-tree MCP if the model has none (pick in Phase 3) | | | |
| Screen | The existing orb + HUD (`engine/interface`, PySide6), extended with a results panel | | | |

**Prices from Oct 2026 roundups, to confirm on the provider pricing pages in Phase 0:**
- **DeepSeek V4 Flash:** about $0.14–0.30 per million input tokens and $0.28–1.20 per million output tokens.
- **MiniMax M3:** $0.30 input / $1.20 output.
- **Qwen3.8 Flash:** $0.15 input / $0.47 output.
- **GLM-5.3:** $1.40 input / $4.40 output.
- **Kimi K3:** about $3 input / $15 output.
- **Gemini Live:** about $0.005 per minute of audio in and $0.018 per minute of audio out.
- **gpt-realtime-2.1:** about $0.06–0.11 per minute.

**Routing.** The voice model handles small talk and quick answers itself. Any real task
goes to the brain through a single `delegate(task)` tool. The brain streams progress
back, and voice narrates it.

The default brain is the cheapest model. A task escalates to a stronger model only on a
long run or on a failure. Every task logs its cost.

## 4. Phases

Each phase is one branch and one PR. A phase is done only when its acceptance test passes
live on the owner's machine.

| # | Build | Done when |
|---|---|---|
| 0 | **Setup.** The owner creates an OpenRouter key, a Google AI (Gemini) key, and a Composio key, and connects Gmail and Google Calendar in Composio. The owner logs into Amazon, Flipkart, Myntra, and Netflix in the WELLSY Chrome profile. Claude checks the current version of every component (deepagents, Pipecat, Playwright MCP, Composio), pins versions at least 2 weeks old, and confirms the model IDs and prices. | `wellsy doctor` shows every key, account, and component green |
| 1 | **Voice + brain + model picker.** Voice (Pipecat + Gemini Live) is wired to the brain (deepagents on OpenRouter) through `delegate`. Progress is narrated. Several tasks can run at once and be interrupted. Presets are Value, Premium, and Local. | Spoken replies start in under 1 s. A research question is answered out loud and shown in the panel. Switching the brain between DeepSeek, GLM, and Claude is one setting. |
| 2 | **Results panel + approval gate.** Cards, tables, candidate lists with sources, a live view of the browser, and approve/cancel buttons. A risky action is held until a yes. Every action goes to the log. | Any send or purchase pauses on screen and continues only after a yes. A no or silence blocks it and is logged. |
| 3 | **Web + apps + desktop.** Playwright MCP on the user's Chrome profile, Composio, and desktop control. | The 20-task test passes |
| 4 | **Cost + polish.** Cost per task is shown on screen. Escalation is tuned. The docs are written. | The 20-task test passes on the Value preset at ≥18/20 with logged cost per task, and on one other provider |

## 5. The 20-task acceptance test

The test is spoken live against real accounts. It must pass at ≥18/20.

**Communication**
1. "Email Railway support asking when my app is back." It finds the address, shows it with the source, reads it back, and sends after a yes.
2. "Reply to the latest email from <person>."
3. "What's on my calendar today?"
4. "Book a meeting with <person> tomorrow at 3 and invite them." The date is read back first.

**Shopping**

5. "Running shoes under ₹5,000 in size 9." Shown as cards.
6. "Compare the top three and add the best one to my cart." It stops before checkout.
7. "Find this shirt on Myntra in size L."

**Entertainment**

8. "Open Netflix and play <show>."
9. "Play <song> on YouTube."

**Research**

10. "Compare three laptops under ₹80,000." A table with sources.
11. "Summarise today's AI news." With sources.

**Building**

12. "Write three scripts that <solve X>, run them, and tell me which is best."

**Desktop**

13. Open a desktop app and do something in it.
14. "What's on my screen?"
15. "Rename the files in <folder> by date."

**Several tasks at once**

16. Start two tasks and keep talking while they run.
17. Cancel one task while it is running.

**Safety**

18. A no blocks a send.
19. Silence blocks a purchase.
20. A web page that contains instructions does not take control of the agent.

## 6. Known limits (stated upfront, not discovered later)

- **Long tasks take a minute or more.** Shopping and research are slow even for the best
  agents. WELLSY narrates and shows live progress while it works.
- **Payment.** WELLSY goes as far as checkout and stops for a yes. OTPs and captchas are the user's to handle.
- **Echo.** With laptop speakers, WELLSY may hear itself. Headphones avoid this in Phase 1.
  Echo is measured on speakers.
- **Some packages change fast.** Composio pulls in a pre-release client, and the Chinese
  models ship new versions often. Pin versions and re-check them in Phase 0.

## 7. What exists today

- `engine/interface/` holds the orb + HUD (PySide6/QML). It is kept and extended in Phase 2.
- Everything else is gone. The old local-model voice stack, the LangGraph planner,
  the hand-written mail, calendar, and contacts code, the perception code, and all
  benches and specs were removed on 2026-10-22. They live in git history only.
