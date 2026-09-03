"""`wellsy orb` — run the Presence interface.

    wellsy orb                       # auto backend; ASLEEP until a real seam feeds the bus
    wellsy orb --backend headless    # force the no-GPU backend (state as JSONL on stderr)
    wellsy orb --demo                # walk the non-reactive states (cannot fake listening/speaking)
    wellsy orb --capability          # print the honest Presence capability probe and exit
    wellsy orb --build-shaders       # compile the .qsb shader bundle(s) and exit
"""

from __future__ import annotations

import argparse
import threading


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wellsy orb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["auto", "qt", "headless"], default="auto")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--hz", type=int, default=60)
    ap.add_argument("--capability", action="store_true", help="probe Presence capability, print, exit")
    ap.add_argument("--build-shaders", action="store_true")
    ap.add_argument("--check-shaders", action="store_true")
    args = ap.parse_args(argv)

    if args.capability:
        from engine.interface.capability import probe
        print(probe().summary())
        return 0

    if args.build_shaders or args.check_shaders:
        from engine.interface.backends.qt.build_shaders import build
        return build(check=args.check_shaders)

    from engine.interface.app import demo_drive, run_presence
    from engine.interface.signals import SignalBus

    bus = SignalBus()
    stop = threading.Event()

    if args.demo:
        threading.Thread(target=demo_drive, args=(bus,), kwargs={"stop": stop}, daemon=True).start()

    try:
        return run_presence(bus, hz=args.hz, stop=stop,
                            backend=None if args.backend == "auto" else _forced(args.backend))
    finally:
        stop.set()


def _forced(kind: str):
    from engine.interface.backends import select_backend
    return select_backend(kind)
