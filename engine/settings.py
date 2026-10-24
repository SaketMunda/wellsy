"""Load `engine/settings.toml` and the API keys in the repo's `.env`."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = Path(__file__).with_name("settings.toml")

KEYS = ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "COMPOSIO_API_KEY", "TAVILY_API_KEY")
# Keys a provider needs, checked when a model from it is picked.
PROVIDER_KEYS = {"openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


def load() -> dict:
    """The settings file. `WELLSY_PRESET` / `WELLSY_BRAIN` in the environment
    stand in for the `preset` / `brain` lines, so a benchmark can switch either
    without editing the file."""
    with SETTINGS.open("rb") as f:
        s = tomllib.load(f)
    s["preset"] = os.environ.get("WELLSY_PRESET") or s["preset"]
    s["brain"] = os.environ.get("WELLSY_BRAIN", s.get("brain", ""))
    return s


def model(settings: dict, role: str) -> dict:
    """The model spec for a role in the active preset, plus its `name`.
    The top-level `brain` setting, when set, replaces the preset's brain."""
    name = settings["presets"][settings["preset"]][role]
    if role == "brain" and settings.get("brain"):
        name = settings["brain"]
    if name not in settings["models"]:
        raise KeyError(f"engine/settings.toml: {role} = {name!r} is not in [models]")
    return {"name": name, **settings["models"][name]}


def load_env() -> None:
    """Put `.env` keys into the environment. Values already set win.

    Also make Python's TLS trust the operating system's certificate store
    (truststore, as pip does). python.org's macOS builds ship with no root
    certificates, so aiohttp-based clients such as the Tavily tool failed
    every HTTPS call (2026-10-24)."""
    import truststore
    from dotenv import load_dotenv

    truststore.inject_into_ssl()
    load_dotenv(REPO / ".env", override=False)


def profile_dir(settings: dict) -> Path:
    return Path(os.path.expanduser(settings["web"]["profile_dir"]))


def scrub(text: str) -> str:
    """Remove any key value from text before it is printed."""
    for k in KEYS:
        v = os.environ.get(k)
        if v and len(v) > 8:
            text = text.replace(v, f"<{k}>")
    return text
