"""`wellsy talk` through the browser: Pipecat's SmallWebRTC transport and its prebuilt page.

No `from __future__ import annotations` here: FastAPI reads the route signatures'
types at runtime, and postponed annotations hide `Request` from it (HTTP 422).
"""

import asyncio
import uuid
import webbrowser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from engine import voice


async def serve(settings: dict, *, session=None, stop=None, open_browser: bool = True) -> None:
    """Talk through the browser: Pipecat's SmallWebRTC transport and its prebuilt page,
    on 127.0.0.1 only. The browser captures the mic with WebRTC echo cancellation, so
    WELLSY's own voice on laptop speakers is removed before Gemini hears it (the pyaudio
    mic interrupted every reply on speakers, 2026-10-24). Pipecat's dev runner does the
    same with `bot()` discovery and every transport; this is its WebRTC routes only,
    one call at a time. Ends when `stop` is set, or on Ctrl-C."""
    from pipecat_ai_prebuilt.frontend import PipecatPrebuiltUI   # prints its dist path on import

    handler = SmallWebRTCRequestHandler()
    sessions: set[str] = set()
    calls: dict[asyncio.Task, asyncio.Event] = {}

    async def on_connection(connection) -> None:
        for ended in calls.values():        # a reload or a second tab replaces the call
            ended.set()
        transport = SmallWebRTCTransport(connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True))
        ended = asyncio.Event()

        @transport.event_handler("on_client_disconnected")
        async def _gone(_t, _c) -> None:
            ended.set()

        call = asyncio.create_task(voice.run(settings, transport, session=session, stop=ended))
        calls[call] = ended
        call.add_done_callback(lambda t: calls.pop(t, None))

    @asynccontextmanager
    async def lifespan(_app):
        yield
        for ended in calls.values():
            ended.set()
        await asyncio.gather(*calls, return_exceptions=True)
        await handler.close()

    app = FastAPI(lifespan=lifespan)
    app.mount("/client", PipecatPrebuiltUI)

    @app.get("/", include_in_schema=False)
    async def _root():
        return RedirectResponse(url="/client/")

    @app.get("/status")
    async def _status():
        return {"status": "ready", "transports": ["webrtc"]}

    @app.post("/start")
    async def _start():
        sid = str(uuid.uuid4())
        sessions.add(sid)
        return {"sessionId": sid}

    @app.api_route("/sessions/{sid}/api/offer", methods=["POST", "PATCH"])
    async def _offer(sid: str, request: Request):
        if sid not in sessions:
            raise HTTPException(404, "unknown session")
        data = await request.json()
        if request.method == "PATCH":
            await handler.handle_patch_request(SmallWebRTCPatchRequest(
                pc_id=data["pc_id"], candidates=[IceCandidate(**c) for c in data.get("candidates", [])]))
            return {"status": "success"}
        return await handler.handle_web_request(
            request=SmallWebRTCRequest(sdp=data["sdp"], type=data["type"], pc_id=data.get("pc_id"),
                                       restart_pc=data.get("restart_pc")),
            webrtc_connection_callback=on_connection)

    port = int(settings["voice"].get("webrtc_port", 7860))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started and not serving.done():
        await asyncio.sleep(0.05)
    if serving.done():
        await serving                       # e.g. the port is taken
        raise RuntimeError(f"could not serve on 127.0.0.1:{port}")
    url = f"http://127.0.0.1:{port}/client/"
    print(f"WELLSY: open {url} and press Connect (Ctrl-C to stop).", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        while not serving.done():
            if stop is not None and stop.is_set():
                server.should_exit = True
            await asyncio.sleep(0.1)
    finally:
        server.should_exit = True
        await serving
