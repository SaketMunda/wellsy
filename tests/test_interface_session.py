"""OrbSession co-run + the worker-thread <-> UI approval relay, on the headless
backend (no display, no Qt)."""

from __future__ import annotations

import threading
import time

from engine.interface.session import ApprovalRelay, OrbSession, approval_view


def test_approval_view_shape():
    v = approval_view({"tool": "pim.mail_send_draft", "args": {"id": 1}, "risk": 2,
                       "reason": "risk 2 needs approval"})
    assert v["kind"] == "approval"
    assert v["tool"] == "pim.mail_send_draft"
    assert v["reversible"] is True          # risk 2 < 3
    assert approval_view({"risk": 3})["reversible"] is False


def test_relay_roundtrip():
    r = ApprovalRelay()
    r.reset()
    out: dict = {}

    def worker():
        out["ans"] = r.wait(timeout=2.0)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.1)
    r.set(True)                              # "main thread" click
    t.join(2.0)
    assert out["ans"] == {"approved": True, "source": "user:orb"}


def test_relay_timeout_denies():
    r = ApprovalRelay()
    r.reset()
    ans = r.wait(timeout=0.2)
    assert ans["approved"] is False
    assert "timeout" in ans["source"]


def test_session_runs_async_main_and_services_an_approval():
    sess = OrbSession(backend=_Recorder(), hz=120)

    def make_coro(stop):
        async def _main():
            # simulate the graph asking for approval mid-run
            ans = await _to_thread(lambda: sess.ui_approver(
                {"tool": "fs.fs_delete_file", "args": {"path": "/x"}, "risk": 3,
                 "reason": "delete is risk 3"}))
            return ans
        return _main()

    # answer the approval shortly after it opens
    def answerer():
        for _ in range(200):
            if sess._backend.huds and sess._backend.huds[-1] == "approval":  # type: ignore[attr-defined]
                sess.relay.set(False)
                return
            time.sleep(0.01)

    threading.Thread(target=answerer, daemon=True).start()
    result = sess.run(make_coro)
    assert result == {"approved": False, "source": "user:orb"}
    assert sess._backend.huds == ["approval", None]          # shown then hidden
    assert sess._backend.stopped


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
