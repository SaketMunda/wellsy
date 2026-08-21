"""Local LLM fallback for T3's query loop — the actual answer to "why is
everything not matched by parseIntent hardcoded, don't we have an LLM?"
(decisions.md D40): we did, but only in the browser (Qwen2.5-0.5B via
WebLLM/WebGPU, D13), which the engine cannot reach — T3 lives in Python
(D37), a separate process with no WebGPU.

This is the fallback path only. `parse_intent()` still handles everything
safety- or reliability-critical (`stop`, `wake`, `sleep`, `describe_scene`,
`query_object`, `help`) with zero-model determinism — an LLM must never be
in the loop for whether "stop" actually stops (D6/D25's reasoning, unchanged).
This module only answers what parse_intent calls `unknown`: open-ended
chatter a fixed regex list was never going to cover completely.

**Runtime: Ollama, not MLX (decisions.md D40's second amendment).** First
build used `mlx-lm` + Qwen2.5-0.5B-Instruct-4bit, native on this M4 Pro.
Real retests found the 0.5B model hit a genuine reasoning ceiling no
prompt trick fixed — e.g. "what am I holding?" against a scene with only
[person, chair] answered "I'm holding a person," confidently wrong, not a
grounding-data problem. The user already runs Ollama for other projects
(models pre-pulled, confirmed fast on this exact machine) — Ollama on
macOS is a native binary using Metal via llama.cpp, not a Docker
container, so switching to it loses nothing this project needs (no
GPU/camera/mic passthrough problem Docker would have caused). Measured,
this session: qwen2.5:7b (already pulled, no download) at temperature 0.2
with the same few-shot grounding technique below answered the same
"what am I holding?" test correctly 5/5 ("I cannot see what you are
holding") vs the 0.5B/MLX path's confident wrong answers. `mlx-lm` was
removed as a dependency — Ollama replaces it, not sits alongside it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_VERSION_URL = "http://localhost:11434/api/version"
MODEL_NAME = "qwen2.5:7b"

# Low temperature, deliberately: decisions.md D40's second amendment found
# the default (higher) temperature gave inconsistent answers to the exact
# same question ("You are holding a person" one time in three, "You are
# holding a camera" -- fully invented -- at default temp with no few-shot).
# 0.2 was the value actually tested, not a guessed default.
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are YAP, a terse voice assistant describing a live camera feed to "
    "someone wearing it. You do not control any commands yourself -- those "
    "are handled elsewhere. Answer in at most one short sentence, spoken "
    "style, no markdown, no emoji. If you don't know, say so briefly. "
    "You have no memory of earlier turns in this conversation -- if the "
    "question depends on something said before, say you didn't catch it "
    "rather than guessing."
)

# A worked example, not just a prose rule. decisions.md D40 amendment:
# telling the model "don't invent details" as a plain instruction did not
# work on either the 0.5B (MLX) or 7B (Ollama) model -- both kept
# inventing furniture, décor, or held objects not in the given facts.
# Small and mid-size instruct models both follow a demonstrated pattern
# far more reliably than a negative prohibition; this one example is what
# actually suppressed the embellishment in testing, on both models.
FEW_SHOT: list[dict[str, str]] = [
    {
        "role": "user",
        "content": "[what the camera currently sees: two things: a person and a chair.]\ndescribe the room",
    },
    {
        "role": "assistant",
        "content": "I see a person and a chair -- that's all I can make out.",
    },
]


class Llm:
    """Talks to a local Ollama server (`ollama serve`, already running as
    this user's existing setup -- not started or managed by this project).
    No model download, no new dependency: `qwen2.5:7b` was already pulled,
    and the request goes over stdlib `urllib` to localhost."""

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

    def respond(self, transcript: str, scene: str | None = None) -> str:
        """`scene`: the current `describe_scene()` output, if available --
        grounds the answer in what the detector actually sees right now.
        Found necessary from a real retest (decisions.md D40 amendment):
        without it, any scene-shaped question ("describe the room") gets
        answered with plausible-sounding, entirely invented decor instead
        of the real detected objects -- confidently wrong is worse than
        saying "I don't understand."
        """
        user_content = transcript
        if scene:
            user_content = (
                f"[what the camera currently sees: {scene}]\n{transcript}"
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *FEW_SHOT,
            {"role": "user", "content": user_content},
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        return body["message"]["content"].strip()
