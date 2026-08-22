"""Day 11: the brain swap (decisions.md D41, day11-prompt.md). This module
used to be a blind text-only chat call — YOLOE's labels, flattened into a
`describe_scene()` string, handed to `qwen2.5:7b`, which never saw a pixel.
Every grounding bug D40's amendments recorded ("you're standing next to the
chair", "you're holding glasses") was that chain inventing detail a word
list gave it no way to actually know. This module now sends the real frame.

**Runtime: Ollama, unchanged from D40's second amendment** — same local
server, same `/api/chat` endpoint, same reason (native Metal via llama.cpp
on this machine, already running, already the house choice). What changed
is the model and the payload shape: `qwen2.5:7b` (text-only) -> a
vision-language model that takes an `images` field alongside the text.

**Model: `qwen3-vl:4b` (Qwen3-VL-4B-Instruct, Apache 2.0) -- the brief's own
fallback, taken for real reasons, not by default.** `qwen3-vl:8b` was
pulled and measured first (`.claude/day11-results.md` row 1/2): real
first-token latency on this M4 Pro (24GB), 12 streamed queries against a
real camera frame, was p50 2753ms / p95 3048ms -- well outside the brief's
"~1.5s is comfortably answerable directly" bar. `qwen3-vl:4b`, measured the
same way against the same frame, came in at p50 1692ms / p95 2282ms --
still not *comfortably* under 1.5s, but roughly half 8B's latency for
identical correctness on every one of the day's five reading tests and
both verbatim grounding retests (see the results doc). Both models stay
pullable locally (`ollama list`) if 8B's extra headroom is ever worth the
cost on a beefier machine; only `MODEL_NAME` needs to change.

**The few-shot grounding hack from the qwen2.5:7b era is gone, deliberately
-- not an oversight.** It existed because a blind model had no way to
verify a claim and had to be walked through "don't invent furniture" by
demonstration. A model that is actually looking at the frame doesn't need
that crutch for the same reason a person describing a photo in front of
them doesn't need a worked example of "don't make things up" -- it can
just look. The system prompt still asks for honesty about *ambiguous* or
*unreadable* content (bad focus, cut-off text), which is a real limitation
a seeing model can still hit, unlike the old model's problem of not seeing
at all.

**Tracks are corroboration, not the source, structurally, not just by
prompt wording** (day11-prompt.md Part 1.3): they're handed to the model as
a labelled "what the tracker currently reports" block, separate from the
image, so the model can cross-check or note a mismatch rather than being
asked to synthesize an answer purely from them the way the old chain was.
`query_loop.py` does the actual structural enforcement -- logging
`possibleDisagreement` via `provenance.py` independent of what this class
returns, so a confident-sounding wrong answer still leaves a paper trail.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

import cv2
import numpy as np

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_VERSION_URL = "http://localhost:11434/api/version"
MODEL_NAME = "qwen3-vl:4b"

# Same reasoning as D40's second amendment: low temperature for a terse,
# repeatable spoken answer rather than the model's default creative range.
# Not yet re-tested against the VLM specifically -- carried forward as the
# same starting value, flagged for retuning if real answers ring flowery.
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are YAP, a terse voice assistant that can see through a camera "
    "(or, when told, the user's screen) and answer questions about what's "
    "actually in the image. You do not control any commands yourself -- "
    "those are handled elsewhere. Answer in at most two short sentences, "
    "spoken style, no markdown, no emoji. Only describe what is actually "
    "visible in the image -- if something is blurry, cut off, or you "
    "genuinely cannot tell, say so briefly rather than guessing. If a "
    "tracker's object list is included below the image, treat it as a "
    "second opinion, not ground truth -- prefer what you actually see. You "
    "have no memory of earlier turns -- if the question depends on "
    "something said before, say you didn't catch it rather than guessing."
)

# JPEG, not PNG: smaller payload over localhost for a 720p-ish webcam/screen
# frame, and Ollama's vision models accept base64 JPEG/PNG interchangeably.
# Quality 85 is the same "good enough for a VLM to read text, small enough
# to not add meaningfully to the request" tradeoff most VLM integrations
# use -- not benchmarked against a lower value this session.
JPEG_QUALITY = 85


def _encode_jpeg_b64(frame_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise RuntimeError("cv2.imencode failed to produce a JPEG from the given frame")
    return base64.b64encode(buf.tobytes()).decode("ascii")


class Llm:
    """Talks to a local Ollama server running a vision-capable model. Same
    zero-new-dependency shape as the D40 text-only version: stdlib
    `urllib`, localhost, no SDK."""

    def __init__(self, model_name: str = MODEL_NAME, base_url: str = OLLAMA_URL) -> None:
        self._model_name = model_name
        self._base_url = base_url
        try:
            urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=2)
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama server not reachable at {OLLAMA_VERSION_URL} -- "
                "is `ollama serve` running? (`ollama list` from a shell "
                "should show your pulled models if it is.)"
            ) from e

    def respond(
        self,
        transcript: str,
        frame_bgr: np.ndarray | None,
        scene: str | None = None,
    ) -> str:
        """`frame_bgr`: the actual camera or screen frame the answer should
        be grounded in -- required in practice (query_loop.py always has
        one by the time it calls this), but left optional at the type level
        so a caller with no frame gets an honest text-only answer instead
        of a crash. `scene`: `describe_scene()`'s tracker-derived string,
        passed as corroboration per day11-prompt.md Part 1.3, not as the
        source of the answer."""
        parts = [transcript]
        if scene:
            parts.insert(0, f"[tracker's object list, for cross-reference only: {scene}]")
        user_content = "\n".join(parts)

        message: dict = {"role": "user", "content": user_content}
        if frame_bgr is not None:
            message["images"] = [_encode_jpeg_b64(frame_bgr)]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            message,
        ]
        payload = json.dumps({
            "model": self._model_name,
            "messages": messages,
            "options": {"temperature": TEMPERATURE},
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._base_url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
        return body["message"]["content"].strip()
