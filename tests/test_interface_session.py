"""OrbSession co-run + panel clicks routed to the runtime, on the headless
backend (no display, no Qt)."""

from __future__ import annotations

import asyncio

from engine.interface.session import OrbSession


def test_session_runs_async_main_and_routes_panel_clicks():
    sess = OrbSession(backend=_Recorder(), hz=120)
    clicks = []
    sess.on_action = clicks.append

    def make_coro(stop):
        async def _main():
            sess.show_hud({"kind": "board", "items": [{"id": "t1", "approval": {"id": "a1"}}]})
            for _ in range(200):
                if sess._backend.huds == ["board"]:  # type: ignore[attr-defined]
                    break
                await asyncio.sleep(0.01)
            sess._action({"type": "approve", "id": "a1"})   # what the Qt bridge calls
            return "ok"
        return _main()

    assert sess.run(make_coro) == "ok"
    assert clicks == [{"type": "approve", "id": "a1"}]
    assert sess._backend.huds == ["board"] and sess._backend.stopped


async def _to_thread(fn):
    import asyncio
    return await asyncio.get_running_loop().run_in_executor(None, fn)


class _Recorder:
    """Minimal PresenceBackend stand-in; records HUD show/hide + stop."""
    name = "recorder"

    def __init__(self):
        self.huds: list = []
        self.stopped = False
        self.renders = 0

    def start(self): ...
    def render(self, snap): self.renders += 1
    def show_hud(self, view): self.huds.append(view.get("kind"))
    def hide_hud(self): self.huds.append(None)
    def stop(self): self.stopped = True
