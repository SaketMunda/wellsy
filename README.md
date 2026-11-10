# WELLSY

WELLSY is a voice-first JARVIS that runs on your own computer. You talk to it, and it
does anything you could do on your computer or on the web:
- finds things you don't know, such as the right support email address;
- shops and compares products;
- opens and plays Netflix or YouTube;
- researches a topic, writes scripts, and compares the results;
- runs your apps;
- works on several tasks at once.

When a picture is clearer than speech, it shows the result on screen.

It is not locked to any provider. By default it uses the cheapest competitive models
(MiniMax, GLM, Kimi, and Gemini Live, through OpenRouter or Google). You can switch
to premium models such as Claude or GPT, or to local models through Ollama, by
changing one setting.

## Status

The project was reset on 2026-10-22. The plan is in [.claude/PLAN.md](.claude/PLAN.md)
and the vision is in [jarvis_friday_edith_combined_ai_system_spec.md](jarvis_friday_edith_combined_ai_system_spec.md).

Only the on-screen orb and HUD (`engine/interface/`) carry over from the earlier build.
Everything else is being built phase by phase from the plan.

## Run what exists today

```bash
uv sync --extra interface            # add --extra local for the Local preset (Whisper + Ollama + Kokoro)
uv run pytest
uv run wellsy --help
```

## Set up (Phase 0)

Put `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `COMPOSIO_API_KEY` and `TAVILY_API_KEY` in `.env` (it is git-ignored). Then:

```bash
uv run wellsy profile                        # Chrome opens on the WELLSY profile; log into your sites by hand
uv run wellsy connect gmail googlecalendar   # Composio's hosted sign-in
uv run wellsy doctor                         # read-only check of every key, account and component
```

Models and providers are set in [engine/settings.toml](engine/settings.toml).

## Talk to it (Phase 1)

```bash
uv run wellsy talk                    # opens the talk page in your browser (press Connect), orb + HUD.
                                      # The browser cancels echo, so laptop speakers work.
                                      # Small talk is answered by the voice; real tasks go to the brain
                                      # and their answers appear in the HUD.
uv run wellsy talk --local            # mic + speakers directly, no echo cancellation: headphones only
uv run wellsy talk --local --out "MacBook Pro Speakers"   # with --local: pick a speaker (or --in for a mic) by name
uv run wellsy ask "question"          # the brain alone, typed
uv run wellsy report                  # latency p50/p95, cost per task per brain, approvals, echo; from runs/
```

The model picker is the top of [engine/settings.toml](engine/settings.toml): `preset = "value" | "premium" | "local"`,
and `brain = "glm"` (or `"claude-opus"`, `"deepseek-flash"`, any name in `[models]`) swaps only the brain.
`WELLSY_PRESET` / `WELLSY_BRAIN` do the same for one run.

## Results panel and approvals (Phase 2)

Every task appears on the panel beside the orb. It shows running tasks with a Cancel
button, and each answer with its cards, comparison table, candidates and sources.

The brain can use your apps through Composio (`[composio] brain_toolkits`, Gmail and
Calendar for now). An app action that sends, creates, changes or deletes something
stops before it runs:
- WELLSY reads the action back and asks "Shall I go ahead?";
- the panel shows the action with Approve / Deny.

A spoken yes counts only if you actually said yes after the read-back. The voice
model's own say-so never approves. A no, or silence for `[approval] timeout_secs`,
blocks the action. Every request and decision goes to `runs/actions.jsonl`, and
`wellsy report` sums them up. `wellsy ask` asks for the same approval as a typed y/N.

Scripted spoken checks use Pipecat's eval harness against `wellsy talk --eval 8765`:

```bash
uv run python -m pipecat.evals run evals/latency.yaml --bot-url ws://localhost:8765 --timeout 20
uv run python -m pipecat.evals run evals/tasks.yaml   --bot-url ws://localhost:8765 --timeout 30
uv run pipecat eval run evals/approval.yaml --bot-url ws://localhost:8765   # a spoken no, and silence; nothing is sent
uv run pipecat eval run evals/approval_send.yaml --bot-url ws://localhost:8765   # a spoken yes: SENDS one real email to your own address
```
