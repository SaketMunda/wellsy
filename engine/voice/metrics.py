"""`wellsy voice --measure` and `--profile-cpu` — the numbers step 4 owes.

Measurement rule (INVARIANTS): p50 / p95 over >= 20 trials, cold vs warm
reported separately, method recorded next to the number.

**Method — component timing against a real utterance.** A fixed sentence is
synthesised once by our own Kokoro backend (so every trial is byte-identical),
written to 16 kHz PCM, and pushed through each stage of the *real* pipeline
seam:

  * ASR   — `FasterWhisperAsr.stream([wav])` → wall time to the `Final`
  * LLM   — the OpenAI-compatible stream (same client Pipecat uses) → wall time
            to the first content token (TTFT) and to completion
  * TTS   — `KokoroTts.stream([sentence])` → wall time to the first `PcmChunk`
            (time-to-first-audio, TTFA)

The §1 rows are then composed from the measured stages, exactly as the streaming
pipeline overlaps them:

  deterministic  = ASR + TTS_TTFA                 (IntentGate answers, no model)
  llm            = ASR + LLM_TTFT + TTS_TTFA      (TTS starts on the 1st sentence)

and the **streaming-overlap proof** is a direct check: first TTS PCM wall-time <
LLM full-completion wall-time on the same turn.

What this does NOT cover, and needs a live mic session with the owner:
the true mic-diaphragm→speaker-cone number, barge-in (A14), and the VLM row
(camera/screen in the loop). `wellsy voice` runs that pipeline for real.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import date
from pathlib import Path

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parents[2] / "spec" / "results"
SR = 16000
DET_UTTERANCE = "what can you do"
LLM_UTTERANCE = "what is the capital of France"
FIXED_ANSWER_SENTENCE = "The capital of France is Paris."
# A deliberately multi-sentence answer, so "first PCM before LLM done" is a real
# gap and not a rounding artefact of a one-sentence reply.
OVERLAP_QUESTION = "Name the eight planets of the solar system, one short sentence each."


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def _stats(vals: list[float]) -> dict:
    v = [x for x in vals if x == x]
    if not v:
        return {"p50_ms": None, "p95_ms": None, "mean_ms": None, "n": 0}
    return {
        "p50_ms": round(_pct(v, 50), 1),
        "p95_ms": round(_pct(v, 95), 1),
        "mean_ms": round(statistics.mean(v), 1),
        "n": len(v),
    }


def _synth_pcm(text: str) -> np.ndarray:
    """16 kHz float32 mono of `text` via the real Kokoro backend."""
    from engine.inference import registry

    tts = registry.get_backend("tts")
    parts = []
    try:
        for chunk in tts.stream(iter([text])):
            p = np.asarray(chunk.pcm, dtype=np.float32).reshape(-1)
            if chunk.sample_rate != SR and p.size:
                import soxr

                p = soxr.resample(p, chunk.sample_rate, SR)
            parts.append(p)
    finally:
        if hasattr(tts, "close"):
            tts.close()
    return np.concatenate(parts) if parts else np.zeros(SR, np.float32)


# --------------------------------------------------------------------------- #
# stage timers                                                                 #
# --------------------------------------------------------------------------- #


def _time_asr(asr, pcm: np.ndarray) -> float:
    t0 = time.monotonic()
    text = ""
    for out in asr.stream(iter([pcm])):
        text = out.text or text
    return (time.monotonic() - t0) * 1000


def _time_tts_ttfa(tts, sentence: str) -> float:
    t0 = time.monotonic()
    for _chunk in tts.stream(iter([sentence])):
        return (time.monotonic() - t0) * 1000
    return float("nan")


def _time_llm(client, model: str, question: str) -> tuple[float, float, float]:
    """(ttft_ms, first_sentence_ms, full_ms) for one streamed completion."""
    t0 = time.monotonic()
    ttft = first_sentence = None
    buf = ""
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are WELLSY. Answer in one short spoken sentence."},
            {"role": "user", "content": question},
        ],
        stream=True,
        extra_body={"keep_alive": -1, "think": False, "chat_template_kwargs": {"enable_thinking": False}},
    )
    for ev in stream:
        piece = (ev.choices[0].delta.content or "") if ev.choices else ""
        if not piece:
            continue
        if ttft is None:
            ttft = (time.monotonic() - t0) * 1000
        buf += piece
        if first_sentence is None and any(buf.rstrip().endswith(p) for p in ".!?"):
            first_sentence = (time.monotonic() - t0) * 1000
    full = (time.monotonic() - t0) * 1000
    return (
        ttft if ttft is not None else float("nan"),
        first_sentence if first_sentence is not None else full,
        full,
    )


# --------------------------------------------------------------------------- #
# --measure                                                                    #
# --------------------------------------------------------------------------- #


def _measure(trials: int) -> dict:
    import os

    from openai import OpenAI

    from engine.inference import registry

    base_url = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("WELLSY_LLM_MODEL", "qwen3:4b")
    client = OpenAI(api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"), base_url=base_url)

    det_pcm = _synth_pcm(DET_UTTERANCE)
    llm_pcm = _synth_pcm(LLM_UTTERANCE)

    asr = registry.get_backend("asr")
    tts = registry.get_backend("tts")

    series: dict[str, list[float]] = {k: [] for k in
                                     ("asr_det", "asr_llm", "tts_ttfa", "llm_ttft", "llm_first_sent", "llm_full")}
    overlap = []  # (first_pcm_wall_ms, llm_done_wall_ms) on a long answer, measured concurrently
    cold: dict[str, float] = {}

    n = trials + 1  # trial 0 == cold
    for i in range(n):
        a_det = _time_asr(asr, det_pcm)
        a_llm = _time_asr(asr, llm_pcm)
        t_ttfa = _time_tts_ttfa(tts, FIXED_ANSWER_SENTENCE)
        ttft, first_sent, full = _time_llm(client, model, LLM_UTTERANCE)
        if i == 0:
            cold = {"asr_det": a_det, "asr_llm": a_llm, "tts_ttfa": t_ttfa,
                    "llm_ttft": ttft, "llm_full": full}
        else:
            series["asr_det"].append(a_det)
            series["asr_llm"].append(a_llm)
            series["tts_ttfa"].append(t_ttfa)
            series["llm_ttft"].append(ttft)
            series["llm_first_sent"].append(first_sent)
            series["llm_full"].append(full)

    # Streaming-overlap proof — measured concurrently, not composed. Stream a
    # multi-sentence answer; the instant the first sentence lands, synthesise it
    # and stamp the first PCM sample; keep draining the LLM to completion and
    # stamp that. First PCM must precede LLM-done.
    for _ in range(3):
        t0 = time.monotonic()
        first_pcm_t = llm_done_t = None
        buf, said = "", False
        stream = client.chat.completions.create(
            model=model, stream=True,
            messages=[{"role": "system", "content": "You are WELLSY. One short sentence per item."},
                      {"role": "user", "content": OVERLAP_QUESTION}],
            extra_body={"keep_alive": -1, "think": False,
                        "chat_template_kwargs": {"enable_thinking": False}},
        )
        for ev in stream:
            piece = (ev.choices[0].delta.content or "") if ev.choices else ""
            buf += piece
            if not said and any(buf.rstrip().endswith(p) for p in ".!?") and len(buf.strip()) > 8:
                said = True
                for _c in tts.stream(iter([buf.strip()])):
                    first_pcm_t = (time.monotonic() - t0) * 1000
                    break
        llm_done_t = (time.monotonic() - t0) * 1000
        if first_pcm_t is not None:
            overlap.append((round(first_pcm_t, 1), round(llm_done_t, 1)))

    if hasattr(tts, "close"):
        tts.close()

    st = {k: _stats(v) for k, v in series.items()}

    deterministic = _stats([x + y for x, y in zip(series["asr_det"], series["tts_ttfa"])])
    llm_e2e = _stats([a + t + f for a, t, f in
                      zip(series["asr_llm"], series["llm_ttft"], series["tts_ttfa"])])
    overlap_ok = sum(1 for fp, ld in overlap if fp < ld)

    return {
        "trials": trials,
        "stages_warm": st,
        "cold_ms": {k: round(v, 1) for k, v in cold.items()},
        "composed": {
            "deterministic  (asr + tts_ttfa)": deterministic,
            "llm  (asr + llm_ttft + tts_ttfa)": llm_e2e,
        },
        "streaming_overlap": {
            "first_pcm_before_llm_done": [overlap_ok, len(overlap)],
            "samples_ms": [{"first_pcm": fp, "llm_done": ld} for fp, ld in overlap],
        },
        "llm_model": model,
        "notes": [
            "component timing; the mic->speaker e2e and A14 need a live session (see module docstring)",
            "deterministic path has no LLM; IntentGate reply is effectively 0 ms",
            "llm row will miss <1500 ms while Ollama 0.33.2 + this qwen3 build runs the reasoning pass regardless of think/enable_thinking",
        ],
    }


# --------------------------------------------------------------------------- #
# --profile-cpu                                                                #
# --------------------------------------------------------------------------- #


async def _profile_cpu(seconds: float) -> dict:
    import psutil

    from engine.voice import pipeline as vp

    worker, runner, _ws, _ctx = vp.build(start_awake=True)
    await runner.add_workers(worker)
    run_task = asyncio.create_task(runner.run())
    proc = psutil.Process()
    proc.cpu_percent(None)
    await asyncio.sleep(2.0)

    samples: list[float] = []
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        await asyncio.sleep(0.5)
        cpu = proc.cpu_percent(None)
        for c in proc.children(recursive=True):
            try:
                cpu += c.cpu_percent(None)
            except psutil.Error:
                pass
        samples.append(cpu)

    await runner.cancel()
    try:
        await asyncio.wait_for(run_task, timeout=10)
    except Exception:
        pass

    ncpu = psutil.cpu_count() or 1
    return {
        "seconds": seconds,
        "samples": len(samples),
        "mean_pct_of_one_core": round(statistics.mean(samples), 1) if samples else None,
        "p95_pct_of_one_core": round(_pct(samples, 95), 1) if samples else None,
        "max_pct_of_one_core": round(max(samples), 1) if samples else None,
        "mean_pct_of_machine": round(statistics.mean(samples) / ncpu, 1) if samples else None,
        "ncpu": ncpu,
        "note": "process + children cpu_percent, 0.5 s cadence, idle (awake, no speech); "
                "Chatterbox regression was ~18% avg / 44% spikes of the machine",
    }


def main(args: argparse.Namespace) -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    if getattr(args, "profile_cpu", None) is not None:
        res = asyncio.run(_profile_cpu(args.profile_cpu))
        print(json.dumps(res, indent=2))
        p = RESULTS_DIR / f"voice-cpu-{stamp}.json"
        p.write_text(json.dumps(res, indent=2) + "\n")
        print(f"wrote {p}")
        return 0

    trials = getattr(args, "trials", 20) or 20
    res = _measure(trials)
    print(json.dumps(res, indent=2))
    tag = res.get("llm_model", "llm").replace(":", "-").replace("/", "-")
    p = RESULTS_DIR / f"voice-latency-{stamp}-{tag}.json"
    p.write_text(json.dumps({"date": stamp, **res}, indent=2) + "\n")
    print(f"wrote {p}")
    return 0
