"""`wellsy connect <toolkit>...`: connect an app to WELLSY's Composio user.

Composio hosts the sign-in. This prints its Connect Link, opens it in your
browser, and waits until you finish signing in.
"""

from __future__ import annotations

import argparse
import webbrowser

from engine import settings as cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wellsy connect", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("toolkits", nargs="+", help="Composio toolkit slugs, e.g. gmail googlecalendar")
    ap.add_argument("--timeout", type=float, default=300, help="seconds to wait for each sign-in")
    args = ap.parse_args(argv)

    cfg.load_env()
    from composio import Composio

    user_id = cfg.load()["composio"]["user_id"]
    session = Composio().create(user_id=user_id)
    connected = {t.slug for t in session.toolkits(toolkits=args.toolkits, is_connected=True).items}
    for toolkit in args.toolkits:
        if toolkit in connected:
            print(f"{toolkit}: already connected for '{user_id}'")
            continue
        request = session.authorize(toolkit)
        print(f"{toolkit}: sign in here → {request.redirect_url}")
        webbrowser.open(request.redirect_url)
        account = request.wait_for_connection(timeout=args.timeout)
        print(f"{toolkit}: {account.status}")
    return 0
