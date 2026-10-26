"""`wellsy doctor`: check every key, account and component. Read-only.

Each check goes through the component's own client: the OpenRouter SDK, the
Google GenAI SDK, the Composio SDK, and Playwright MCP over the MCP client.
Every red line ends with the exact thing the owner has to do.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from urllib.parse import urlsplit

from engine import settings as cfg

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


@dataclass
class Line:
    ok: bool
    what: str
    detail: str = ""
    fix: str = ""


class Report:
    def __init__(self, color: bool):
        self.lines: list[Line] = []
        self.color = color

    def section(self, title: str) -> None:
        print(f"\n{title}")

    def add(self, ok: bool, what: str, detail: str = "", fix: str = "") -> bool:
        line = Line(ok, what, cfg.scrub(detail), fix)
        self.lines.append(line)
        mark = "✓" if ok else "✗"
        if self.color:
            mark = f"{GREEN if ok else RED}{mark}{RESET}"
        tail = f"  {DIM}{line.detail}{RESET}" if self.color and line.detail else (f"  {line.detail}" if line.detail else "")
        print(f"  {mark} {what}{tail}")
        if not ok and fix:
            print(f"      → {fix}")
        return ok

    @property
    def red(self) -> int:
        return sum(not l.ok for l in self.lines)


def _leaf(e: BaseException) -> BaseException:
    """The real error inside an anyio/asyncio ExceptionGroup."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def _err(e: BaseException) -> str:
    e = _leaf(e)
    return f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"


def _preset_models(settings: dict, provider: str) -> list[tuple[str, str]]:
    """Every [models] entry from `provider`, labelled with the presets that use it."""
    used: dict[str, list[str]] = {}
    for preset, roles in settings["presets"].items():
        for role, name in roles.items():
            used.setdefault(name, []).append(f"{preset}.{role}")
    return [(f"{name} ({', '.join(used.get(name, ['brain swap']))})", spec["model"])
            for name, spec in settings["models"].items() if spec.get("provider") == provider]


def check_keys(rep: Report) -> dict[str, bool]:
    rep.section("Keys (.env)")
    have = {}
    for k in cfg.KEYS:
        v = os.environ.get(k, "").strip()
        have[k] = bool(v)
        rep.add(bool(v), k, "set" if v else "missing",
                f"add {k}=<your key> to {cfg.REPO / '.env'}")
    return have


def check_openrouter(rep: Report, settings: dict) -> None:
    rep.section("OpenRouter")
    from openrouter import OpenRouter, operations

    key = os.environ["OPENROUTER_API_KEY"]
    fix_key = "create a key at https://openrouter.ai/settings/keys and put it in .env as OPENROUTER_API_KEY"
    try:
        with OpenRouter(api_key=key, timeout_ms=20000) as client:
            meta = client.api_keys.get_current_key_metadata().data
            limit = f" of ${meta.limit:.2f} limit" if meta.limit is not None else ""
            left_ok = meta.limit_remaining is None or meta.limit_remaining > 0.5
            rep.add(True, "key works", f"${meta.usage:.2f} used{limit}")
            if not left_ok:
                rep.add(False, "credit left", f"${meta.limit_remaining:.2f} remaining",
                        "raise the key's limit or add credit at https://openrouter.ai/settings/credits")
            ids = {m.id for m in client.models.list_for_user(
                security=operations.ListModelsUserSecurity(bearer=key)).data}
    except Exception as e:  # noqa: BLE001 - every failure becomes a red line
        rep.add(False, "key works", _err(e), fix_key)
        return
    for role, model in _preset_models(settings, "openrouter"):
        rep.add(model in ids, f"{role}  {model}", "resolves" if model in ids else "not available to this key",
                f"pick a current ID from https://openrouter.ai/models and set it in engine/settings.toml "
                f"[models], or allow its providers in https://openrouter.ai/settings/preferences")


def check_gemini(rep: Report, settings: dict) -> None:
    rep.section("Gemini")
    from google import genai

    fix_key = "create a key at https://aistudio.google.com/apikey and put it in .env as GEMINI_API_KEY"
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        names = {m.name.removeprefix("models/") for m in client.models.list()}
        rep.add(True, "key works", f"{len(names)} models visible")
    except Exception as e:  # noqa: BLE001
        rep.add(False, "key works", _err(e), fix_key)
        return
    for role, model in _preset_models(settings, "gemini"):
        if model not in names:
            rep.add(False, f"{role}  {model}", "model not found for this key",
                    "pick a Live model from https://ai.google.dev/gemini-api/docs/models and set it in engine/settings.toml")
            continue

        async def _open() -> None:
            # Opens a Live session and closes it at once. No audio is sent.
            async with client.aio.live.connect(model=model, config={"response_modalities": ["AUDIO"]}):
                pass

        try:
            asyncio.run(asyncio.wait_for(_open(), 20))
            rep.add(True, f"{role}  {model}", "Live session opened")
        except Exception as e:  # noqa: BLE001
            rep.add(False, f"{role}  {model}", f"Live session failed: {_err(e)}",
                    "enable billing for the key's project at https://aistudio.google.com/ (the Live API needs the paid tier), then re-run")


def check_composio(rep: Report, settings: dict) -> None:
    rep.section("Composio")
    from composio import Composio

    user_id = settings["composio"]["user_id"]
    try:
        composio = Composio()
        composio.connected_accounts.list(limit=1)
        rep.add(True, "key works")
    except Exception as e:  # noqa: BLE001
        rep.add(False, "key works", _err(e),
                "copy the project API key from https://dashboard.composio.dev (Platform → your project → Settings) "
                "into .env as COMPOSIO_API_KEY")
        return

    for toolkit, slug in settings["composio"]["read_checks"].items():
        try:
            accounts = composio.connected_accounts.list(
                toolkit_slugs=[toolkit], user_ids=[user_id], statuses=["ACTIVE"]).items
        except Exception as e:  # noqa: BLE001
            rep.add(False, f"{toolkit} connected", _err(e), "re-run; if it persists, check https://status.composio.dev")
            continue
        if not accounts:
            others = composio.connected_accounts.list(toolkit_slugs=[toolkit], statuses=["ACTIVE"]).items
            fix = f"run `uv run wellsy connect {toolkit}` and sign in on the page it opens"
            if others:
                fix += (f" (an active {toolkit} account exists under another Composio user; "
                        f"or set composio.user_id in engine/settings.toml to that user)")
            rep.add(False, f"{toolkit} connected", f"no active account for user '{user_id}'", fix)
            continue
        rep.add(True, f"{toolkit} connected", f"{len(accounts)} active account(s) for user '{user_id}'")
        try:
            read_only = {t.slug for t in composio.client.tools.list(
                toolkit_slug=toolkit, tags=["readOnlyHint"], limit=200).items}
            if slug not in read_only:
                rep.add(False, f"{toolkit} read-only call", f"{slug} is not tagged read-only by Composio",
                        f"set composio.read_checks.{toolkit} in engine/settings.toml to a tool from "
                        f"https://docs.composio.dev/toolkits/{toolkit}.md marked read-only")
                continue
            version = composio.tools.get_raw_composio_tool_by_slug(slug).version
            res = composio.tools.execute(slug, arguments={}, user_id=user_id,
                                         connected_account_id=accounts[0].id, version=version)
            rep.add(bool(res.get("successful")), f"{toolkit} read-only call  {slug}",
                    "succeeded" if res.get("successful") else f"failed: {str(res.get('error'))[:200]}",
                    f"reconnect with `uv run wellsy connect {toolkit}`; if it still fails, send the error above "
                    "to Composio support with the log ID from https://dashboard.composio.dev → Logs")
        except Exception as e:  # noqa: BLE001
            rep.add(False, f"{toolkit} read-only call  {slug}", _err(e),
                    f"reconnect with `uv run wellsy connect {toolkit}`, then re-run")


async def _check_sites(rep: Report, settings: dict) -> None:
    from engine.setup.browser import call, playwright_mcp, result_value

    try:
        # Headed: Myntra refuses headless Chrome, and Netflix breaks under it.
        async with playwright_mcp(settings, headless=False) as session:
            for site in settings["web"]["sites"]:
                name = site["name"]
                try:
                    await call(session, "browser_navigate", url=site["check_url"])
                    final = result_value(await call(session, "browser_evaluate", function="() => location.href"))
                except Exception as e:  # noqa: BLE001
                    _browser_error(rep, f"{name} logged in", e)
                    if "chrome" in str(e).lower() and ("not found" in str(e).lower() or "not installed" in str(e).lower()):
                        return
                    continue
                ok = re.search(site["logged_in"], final) is not None
                landed = urlsplit(final)
                rep.add(ok, f"{name} logged in",
                        "account page loaded" if ok else f"landed on {landed.netloc}{landed.path}",
                        f"run `uv run wellsy profile` and log into {name} by hand in the window it opens")
            await call(session, "browser_close")
    except Exception as e:  # noqa: BLE001
        _browser_error(rep, "Playwright MCP started", e)


async def _check_chrome(rep: Report, settings: dict) -> bool:
    """Launch the configured browser on a throwaway in-memory profile."""
    from mcp import StdioServerParameters

    from engine.setup.browser import call, server_params, session_for

    base = server_params(settings, headless=True)
    i = base.args.index("--user-data-dir")
    params = StdioServerParameters(command=base.command, args=base.args[:i] + base.args[i + 2:] + ["--isolated"])
    try:
        async with session_for(params) as session:
            await call(session, "browser_navigate", url="about:blank")
            await call(session, "browser_close")
    except Exception as e:  # noqa: BLE001
        _browser_error(rep, f"browser '{settings['web']['browser']}' launches", e)
        return False
    return rep.add(True, f"browser '{settings['web']['browser']}' launches")


def _browser_error(rep: Report, what: str, e: BaseException) -> None:
    msg = str(_leaf(e))
    low = msg.lower()
    if "chrome" in low and ("not found" in low or "not installed" in low):
        fix = ("install Google Chrome (https://www.google.com/chrome/ or `brew install --cask google-chrome`). "
               "Playwright's own Chromium cannot play Netflix")
    elif "user data directory is already in use" in low or "processsingleton" in low or "singletonlock" in low:
        fix = "close the WELLSY Chrome window (the one `wellsy profile` opened), then re-run"
    else:
        fix = "re-run; if it repeats, run `uv run wellsy profile` and check the window opens"
    rep.add(False, what, _err(e), fix)


def check_browser(rep: Report, settings: dict) -> None:
    rep.section("Browser (Playwright MCP, WELLSY Chrome profile)")
    pin = settings["web"]["playwright_mcp"]
    try:
        out = subprocess.run(["npx", "-y", f"@playwright/mcp@{pin}", "--version"],
                             capture_output=True, text=True, timeout=120).stdout.strip()
        ok = out.endswith(pin)
        rep.add(ok, f"@playwright/mcp {pin}", out or "no output",
                f"check Node and npm work: `npx -y @playwright/mcp@{pin} --version` should print {pin}")
        if not ok:
            return
    except FileNotFoundError:
        rep.add(False, "Node.js / npx", "npx not found", "install Node.js 18 or newer from https://nodejs.org")
        return
    except Exception as e:  # noqa: BLE001
        rep.add(False, f"@playwright/mcp {pin}", _err(e), "check your network, then re-run")
        return

    if not asyncio.run(_check_chrome(rep, settings)):
        return

    profile = cfg.profile_dir(settings)
    if not rep.add(profile.is_dir(), "WELLSY Chrome profile", str(profile) if profile.is_dir() else f"missing: {profile}",
                   "run `uv run wellsy profile`: it creates the profile, opens Chrome on it, and you log into "
                   "Amazon, Flipkart, Myntra and Netflix by hand"):
        return
    print("  (a Chrome window opens for a few seconds to check the logins)")
    asyncio.run(_check_sites(rep, settings))


def check_pins(rep: Report) -> None:
    rep.section("Installed versions vs pins (pyproject.toml)")
    from packaging.requirements import Requirement
    from packaging.version import Version

    with (cfg.REPO / "pyproject.toml").open("rb") as f:
        deps = tomllib.load(f)["project"]["dependencies"]
    for dep in deps:
        req = Requirement(dep)
        pinned = [s.version for s in req.specifier if s.operator == "=="]
        if not pinned:
            continue
        try:
            have = metadata.version(req.name)
        except metadata.PackageNotFoundError:
            have = None
        rep.add(have is not None and Version(have) == Version(pinned[0]), f"{req.name} {pinned[0]}", f"installed {have}" if have else "not installed",
                "run `uv sync --extra interface`")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wellsy doctor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    cfg.load_env()
    settings = cfg.load()
    rep = Report(color=sys.stdout.isatty() and not args.no_color)
    print("WELLSY doctor (read-only)")

    have = check_keys(rep)
    if have["OPENROUTER_API_KEY"]:
        check_openrouter(rep, settings)
    if have["GEMINI_API_KEY"]:
        check_gemini(rep, settings)
    if have["COMPOSIO_API_KEY"]:
        check_composio(rep, settings)
    check_browser(rep, settings)
    check_pins(rep)

    green = len(rep.lines) - rep.red
    print(f"\n{green} green, {rep.red} red" + ("" if rep.red else ". All green."))
    return 0 if rep.red == 0 else 1
