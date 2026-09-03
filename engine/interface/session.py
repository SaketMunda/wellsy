"""Run the Presence UI alongside an asyncio runtime (voice worker / agent loop).

Qt must own the process main thread, so the asyncio work runs on a worker
thread and the UI is driven from a main-thread `QTimer`. All UI mutations from
the worker thread go through a thread-safe queue that the tick drains on the
main thread — no cross-thread QObject calls.

The headless backend has no such constraint; it takes the same path with a
plain loop instead of a Qt timer.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Any, Callable

from engine.interface.backends import select_backend
from engine.interface.signals import SignalBus
from engine.interface.state import derive_state


class ApprovalRelay:
    """Bridges a worker-thread approver call to a main-thread QML click."""

    def __init__(self) -> None:
        self._ev = threading.Event()
        self._answer: dict | None = None

    def reset(self) -> None:
        self._ev.clear()
        self._answer = None

    def set(self, approved: bool) -> None:          # main thread (QML -> backend)
        self._answer = {"approved": bool(approved), "source": "user:orb"}
        self._ev.set()

    def wait(self, timeout: float | None = None) -> dict:   # worker thread
        self._ev.wait(timeout)
        return self._answer or {"approved": False, "source": "user:orb:timeout"}


def approval_view(request: dict) -> dict:
    return {
        "kind": "approval",
        "title": "Approve this action?",
        "tool": request.get("tool", ""),
        "args": request.get("args", {}),
        "risk": request.get("risk"),
        "reversible": (request.get("risk", 3) or 3) < 3,
        "reason": request.get("reason") or request.get("why") or "",
    }


class OrbSession:
    """Owns the backend, the UI command queue, and the co-run of an async main.

        sess = OrbSession(bus)
        sess.run(lambda stop: my_async_main(stop))
    """

    def __init__(self, bus: SignalBus | None = None, *, backend=None, hz: int = 60,
                 on_escape: Callable[[], None] | None = None):
        self.bus = bus or SignalBus()
        self.relay = ApprovalRelay()
        self._hz = hz
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._on_escape = on_escape
        self._backend = backend or select_backend(
            on_approval=self.relay.set, on_escape=self._escape,
        )

    # -- worker-thread facing helpers (safe to call from the async main) ---- #

    def show_hud(self, view: dict) -> None:
        self._q.put(("hud_show", view))

    def hide_hud(self) -> None:
        self._q.put(("hud_hide",))

    def ui_approver(self, request: dict) -> dict:
        """Pass as `run_agent(approver=...)`. Blocks the worker thread until the
        user answers in the orb HUD."""
        self.relay.reset()
        self.show_hud(approval_view(request))
        ans = self.relay.wait()
        self.hide_hud()
        return ans

    # -- internals -------------------------------------------------------- #

    def _escape(self) -> None:
        if self._on_escape:
            self._on_escape()

    def _drain(self) -> None:
        try:
            while True:
                cmd = self._q.get_nowait()
                if cmd[0] == "hud_show":
                    self._backend.show_hud(cmd[1])
                elif cmd[0] == "hud_hide":
                    self._backend.hide_hud()
                elif cmd[0] == "quit":
                    self._backend.stop()
        except queue.Empty:
            pass

    def _tick(self) -> None:
        self._backend.render(derive_state(self.bus))
        self._drain()

    def run(self, make_coro: Callable[[threading.Event], Any]) -> Any:
        """`make_coro(stop)` returns the coroutine to run on the worker thread.
        Blocks until it finishes (or the UI is closed), then returns its
        result (or re-raises its exception)."""
        self._backend.start()
        stop = threading.Event()
        box: dict[str, Any] = {}

        def worker() -> None:
            try:
                box["result"] = asyncio.run(make_coro(stop))
            except BaseException as e:  # noqa: BLE001 - surfaced on the main thread
                box["error"] = e
            finally:
                stop.set()
                self._q.put(("quit",))

        th = threading.Thread(target=worker, name="orb-async", daemon=True)
        th.start()

        if hasattr(self._backend, "exec_"):
            from PySide6.QtCore import QTimer

            timer = QTimer()
            timer.setInterval(max(1, int(1000 / self._hz)))
            timer.timeout.connect(self._tick)
            timer.start()
            self._backend.exec_()          # returns when ("quit",) is drained
        else:
            period = 1.0 / self._hz
            try:
                while not stop.is_set():
                    self._tick()
                    time.sleep(period)
            except KeyboardInterrupt:
                stop.set()
            self._drain()          # apply any final hud_hide / quit
            self._backend.stop()

        th.join(timeout=3.0)
        if "error" in box:
            raise box["error"]
        return box.get("result")
