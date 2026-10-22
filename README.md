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
(DeepSeek, GLM, Kimi, and Gemini Live, through OpenRouter or Google). You can switch
to premium models such as Claude or GPT, or to local models through Ollama, by
changing one setting.

## Status

The project was reset on 2026-10-22. The plan is in [.claude/PLAN.md](.claude/PLAN.md)
and the vision is in [jarvis_friday_edith_combined_ai_system_spec.md](jarvis_friday_edith_combined_ai_system_spec.md).

Only the on-screen orb and HUD (`engine/interface/`) carry over from the earlier build.
Everything else is being built phase by phase from the plan.

## Run what exists today

```bash
uv sync --extra interface
uv run pytest
uv run wellsy --help
```
