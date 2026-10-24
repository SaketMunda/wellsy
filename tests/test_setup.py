"""Offline tests for the Phase 0 setup commands. Live checks run in `wellsy doctor`."""

import re

from engine import cli, settings
from engine.setup.browser import result_value


def test_result_value_reads_the_result_block():
    reply = '### Result\n"https://www.amazon.in/ap/signin"\n### Ran Playwright code\n```js\n```'
    assert result_value(reply) == "https://www.amazon.in/ap/signin"


def test_scrub_removes_key_values(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-secretsecret")
    assert settings.scrub("401 for sk-or-v1-secretsecret") == "401 for <OPENROUTER_API_KEY>"


def test_every_preset_role_names_a_provider_and_model():
    s = settings.load()
    assert s["preset"] in s["presets"]
    for preset, roles in s["presets"].items():
        for role in roles:
            spec = settings.model({**s, "preset": preset, "brain": ""}, role)
            assert spec["provider"] and spec["model"]


def test_brain_swap_is_one_setting():
    s = settings.load()
    for name in ("deepseek-flash", "glm", "claude-opus"):
        assert settings.model({**s, "preset": "value", "brain": name}, "brain")["name"] == name
    # the voice stays the preset's
    assert settings.model({**s, "preset": "value", "brain": "claude-opus"}, "voice")["name"] == "gemini-live"


def test_site_checks_reject_sign_in_pages():
    # Where each site sends a logged-out profile (seen live on 2026-10-24).
    landed = {
        "Amazon": "https://www.amazon.in/ap/signin?openid.return_to=x",
        "Flipkart": "https://www.flipkart.com/login?ret=/account/orders",
        "Myntra": "https://www.myntra.com/login?referer=/my/orders",
        "Netflix": "https://www.netflix.com/in/login",
    }
    for site in settings.load()["web"]["sites"]:
        assert not re.search(site["logged_in"], landed[site["name"]]), site["name"]
        assert re.search(site["logged_in"], site["check_url"]), site["name"]


def test_cli_routes_subcommands(monkeypatch):
    seen = {}
    import engine.setup.doctor as doctor
    import engine.interface.cli as orb

    monkeypatch.setattr(doctor, "main", lambda a: seen.setdefault("doctor", a) and 0)
    import engine.talk as talk

    monkeypatch.setattr(orb, "main", lambda a: seen.setdefault("orb", a) and 0)
    monkeypatch.setattr(talk, "main", lambda a: seen.setdefault(a[0], a) and 0)
    cli.main(["doctor", "--no-color"])
    cli.main(["--demo"])
    cli.main(["talk", "--no-orb"])
    cli.main(["ask", "hello"])
    assert seen == {"doctor": ["--no-color"], "orb": ["--demo"],
                    "talk": ["talk", "--no-orb"], "ask": ["ask", "hello"]}
