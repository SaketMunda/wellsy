"""`wellsy profile`: open Chrome on the WELLSY profile so the owner can log in by hand.

Chrome is opened through Playwright MCP, the same way WELLSY drives it later.
That matters on macOS: Playwright launches Chrome with a mock keychain, so
cookies saved by a normal Chrome window on this profile would not decrypt.
WELLSY never types the owner's passwords.
"""

from __future__ import annotations

import argparse
import asyncio

from engine import settings as cfg


async def _run(settings: dict) -> None:
    from engine.setup.browser import call, playwright_mcp

    sites = settings["web"]["sites"]
    async with playwright_mcp(settings, headless=False) as session:
        await call(session, "browser_navigate", url=sites[0]["login_url"])
        for site in sites[1:]:
            await call(session, "browser_tabs", action="new", url=site["login_url"])
        print("Chrome is open on the WELLSY profile with one tab per site:")
        for site in sites:
            print(f"  - {site['name']}: {site['login_url']}")
        print("Log into each one yourself. Tick 'keep me signed in' where offered.")
        await asyncio.to_thread(input, "Press Enter here when you are done (this closes the window)... ")
        await call(session, "browser_close")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="wellsy profile", description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    settings = cfg.load()
    profile = cfg.profile_dir(settings)
    profile.mkdir(parents=True, exist_ok=True)
    print(f"Profile: {profile}")
    try:
        asyncio.run(_run(settings))
    except Exception as e:  # noqa: BLE001
        print(f"Could not open Chrome: {str(e).splitlines()[0][:300]}")
        print("If Chrome is missing, install Google Chrome (`brew install --cask google-chrome`) and re-run.")
        return 1
    print("Done. Run `uv run wellsy doctor` to check the logins.")
    return 0
