"""Load `engine/settings.toml` and the API keys in the repo's `.env`."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = Path(__file__).with_name("settings.toml")

KEYS = ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "COMPOSIO_API_KEY")


def load() -> dict:
    with SETTINGS.open("rb") as f:
        return tomllib.load(f)


def load_env() -> None:
    """Put `.env` keys into the environment. Values already set win."""
    from dotenv import load_dotenv

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
