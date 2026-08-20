"""Day 9: pushes engine frames to the HUD over a local WebSocket.

One producer (`main.py`'s frame loop), any number of connected browser
clients, one socket, no protocol version, no schema library — see
day9-prompt.md's "what not to build". `main.py`'s stdout JSONL (`emit()`)
is untouched by this module; the WebSocket payload is built separately in
`main.py` so the two wire formats can't drift into needing to match.

**localhost only** (decisions.md D10/D35) — `HOST` is `127.0.0.1`, never
`0.0.0.0`. The private server (Day 14) is different hardware; this module
does not anticipate it.

Runs the `websockets` sync server in its own background thread so it can
sit next to `main.py`'s existing synchronous frame loop without pulling the
whole engine onto asyncio. `broadcast()` is called once per emitted frame
(~8Hz) from the main thread; sends are best-effort per client — a slow or
gone client is dropped, never buffered into, matching D29's "drop frames,
never buffer" rule one layer up, at the socket instead of the queue.
"""

from __future__ import annotations

import json
import sys
import threading
from typing import Any

from websockets.sync.server import ServerConnection, serve

HOST = "127.0.0.1"


class Bridge:
    def __init__(self, port: int) -> None:
        self._port = port
        self._lock = threading.Lock()
        self._clients: set[ServerConnection] = set()
        self._server = serve(self._handle, HOST, port)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()
        print(f"[bridge] ws://{HOST}:{self._port} (localhost only)", file=sys.stderr, flush=True)

    def _handle(self, ws: ServerConnection) -> None:
        with self._lock:
            self._clients.add(ws)
        try:
            # No messages expected from the client — this loop just blocks
            # until the connection closes, so we notice a disconnect and
            # stop trying to send to a dead socket.
            for _ in ws:
                pass
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients.discard(ws)

    def broadcast(self, payload: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        if not clients:
            return
        message = json.dumps(payload)
        for ws in clients:
            try:
                ws.send(message)
            except Exception:
                # A send failure means this client is gone or wedged —
                # drop it rather than retry/buffer. The next frame will
                # try again for anyone still connected.
                with self._lock:
                    self._clients.discard(ws)

    def close(self) -> None:
        self._server.shutdown()
