"""`wellsy orb` — run the Presence interface.

    wellsy orb                       # auto backend; ASLEEP until a real seam feeds the bus
    wellsy orb --backend headless    # force the no-GPU backend (state as JSONL on stderr)
    wellsy orb --demo                # walk the non-reactive states (cannot fake listening/speaking)
    wellsy orb --capability          # print the honest Presence capability probe and exit
    wellsy orb --profile-cpu N --hold STATE   # CPU sample, p50/p95, exit
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
    ap.add_argument("--profile-cpu", metavar="SECONDS", type=float, default=None,
                    help="hold a state for N s, sample this process's CPU, print p50/p95, exit")
    ap.add_argument("--hold", choices=["asleep", "idle", "acting", "hud"], default="asleep",
                    help="state to hold while profiling (--profile-cpu)")
    args = ap.parse_args(argv)

    if args.capability:
        from engine.interface.capability import probe
        print(probe().summary())
        return 0

    if args.profile_cpu is not None:
        return _profile_cpu(args.profile_cpu, args.hold, args.backend)

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


def _profile_cpu(seconds: float, hold: str, backend_kind: str) -> int:
    """Sample this process's CPU while the orb holds one state. Method (recorded
    per the measurement rule): psutil.Process().cpu_percent over 250 ms windows,
    normalised to *one core* then divided by os.cpu_count() to read as
    '% of the machine'; p50/p95 over the run; first sample discarded (priming)."""
    import os
    import statistics
    import time

    import psutil

    from engine.interface.app import run_presence
    from engine.interface.backends import select_backend
    from engine.interface.signals import SignalBus

    bus = SignalBus()
    if hold in ("idle", "acting", "hud"):
        bus.set_wake(True)
    if hold in ("acting", "hud"):
        bus.set_agent_phase("acting")

    be = select_backend(None if backend_kind == "auto" else backend_kind)
    proc = psutil.Process()
    ncpu = os.cpu_count() or 1
    samples: list[float] = []

    if hasattr(be, "exec_"):
        from PySide6.QtCore import QTimer

        be.start()
        if hold == "hud":
            be.show_hud({"kind": "plan", "title": "profiling", "steps": [
                {"tool": "pim.calendar_list_events", "decision": "allow"},
                {"tool": "pim.mail_create_draft", "decision": "confirm"},
            ]})
        from engine.interface.state import derive_state

        rt = QTimer(); rt.setInterval(16)
        rt.timeout.connect(lambda: be.render(derive_state(bus)))
        rt.start()

        proc.cpu_percent(None)  # prime
        st = QTimer(); st.setInterval(250)
        st.timeout.connect(lambda: samples.append(proc.cpu_percent(None) / ncpu))
        st.start()
        QTimer.singleShot(int(seconds * 1000), be.stop)
        be.exec_()
    else:
        be.start()
        from engine.interface.state import derive_state

        proc.cpu_percent(None)
        end = time.monotonic() + seconds
        last = 0.0
        while time.monotonic() < end:
            be.render(derive_state(bus))
            now = time.monotonic()
            if now - last >= 0.25:
                samples.append(proc.cpu_percent(None) / ncpu)
                last = now
            time.sleep(0.016)
        be.stop()

    samples = samples[1:] or samples
    if not samples:
        print("no samples", flush=True)
        return 1
    p50 = statistics.median(samples)
    p95 = sorted(samples)[min(len(samples) - 1, int(round(0.95 * (len(samples) - 1))))]
    budget = {"asleep": 1.0, "idle": 1.0, "acting": 3.0, "hud": 6.0}[hold]
    verdict = "OK" if p95 <= budget else "OVER BUDGET"
    print(f"\norb --profile-cpu  hold={hold}  backend={be.name}  n={len(samples)}")
    print(f"  p50 = {p50:.2f}% of the machine")
    print(f"  p95 = {p95:.2f}% of the machine   (budget {budget:.0f}%)  -> {verdict}")
    print("  method: psutil cpu_percent / 250 ms windows / ncpu; first sample dropped")
    return 0 if p95 <= budget else 1
