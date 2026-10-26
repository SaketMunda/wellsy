"""`wellsy` entry point.

    wellsy                  # the orb + HUD (see engine/interface/cli.py)
    wellsy talk             # talk to WELLSY: voice + brain + HUD (see engine/talk.py)
    wellsy ask "question"   # the brain alone, typed
    wellsy report           # latency p50/p95, cost per task, echo, from runs/
    wellsy doctor           # check every key, account and component (read-only)
    wellsy profile          # open Chrome on the WELLSY profile to log into sites by hand
    wellsy connect gmail    # connect an app through Composio's hosted sign-in
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "doctor":
        from engine.setup.doctor import main as run
    elif cmd == "profile":
        from engine.setup.profile import main as run
    elif cmd == "connect":
        from engine.setup.connect import main as run
    elif cmd in ("talk", "ask", "report"):
        from engine.talk import main as run
        rest = argv
    else:
        from engine.interface.cli import main as run
        rest = rest if cmd == "orb" else argv
    return run(rest)


if __name__ == "__main__":
    sys.exit(main())
