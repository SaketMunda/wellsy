"""ASR on the words the agent needs exactly: names and email addresses (step 9
live-run follow-up). Utterances are synthesised with the shipped Kokoro voice,
so this compares models and hotwords on clean speech — not the owner's accent
or room, which only a recorded take can measure.

    .venv/bin/python bench/asr_names.py --models base.en small.en large-v3-turbo
"""
from __future__ import annotations

import argparse, json, os, re, statistics, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CASES = [
    ("Send an email to saket dot munda at the rate gmail dot com.", ["saket", "munda", "gmail"]),
    ("Email Saket Munda that I am running late.", ["saket", "munda"]),
    ("The correct address is saket dot munda at gmail dot com.", ["saket", "munda", "gmail"]),
    ("Remind me to call Priya tomorrow at six pm.", ["priya"]),
    ("Draft a reply to Dana saying Thursday works.", ["dana", "thursday"]),
    ("What is on my calendar tomorrow?", ["calendar", "tomorrow"]),
]


def main() -> int:
    import numpy as np
    import soxr
    from faster_whisper import WhisperModel

    from engine.inference import registry
    from engine.inference.backends.whisper_faster import _DOWNLOAD_ROOT

    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["base.en", "small.en", "large-v3-turbo"])
    ap.add_argument("--hotwords", default="Saket Munda, Priya, Dana, gmail")
    a = ap.parse_args()

    tts = registry.get_backend("tts", None)
    clips = []
    for text, _ in CASES:
        pcm = np.concatenate([np.asarray(c.pcm, dtype=np.float32).reshape(-1) for c in tts.stream(iter([text]))])
        clips.append(soxr.resample(pcm, getattr(tts, "SAMPLE_RATE", 24000), 16000).astype(np.float32))

    rows, summary = [], {}
    for model in a.models:
        m = WhisperModel(model, device="cpu", compute_type="int8", download_root=str(_DOWNLOAD_ROOT))
        lang = "en" if model.endswith(".en") or True else None
        for hw in (None, a.hotwords):
            hits, total, ms = 0, 0, []
            for (text, keys), clip in zip(CASES, clips):
                t0 = time.perf_counter()
                segs, _ = m.transcribe(clip, language="en", beam_size=1, vad_filter=False,
                                       condition_on_previous_text=False, hotwords=hw)
                out = " ".join(s.text.strip() for s in segs)
                ms.append((time.perf_counter() - t0) * 1000)
                got = sum(k in out.lower() for k in keys)
                hits += got; total += len(keys)
                rows.append({"model": model, "hotwords": bool(hw), "said": text, "heard": out, "keywords": f"{got}/{len(keys)}"})
                print(model, "hw" if hw else "--", f"{ms[-1]:.0f} ms", "|", out, flush=True)
            summary[f"{model}{' +hotwords' if hw else ''}"] = {"keywords": f"{hits}/{total}",
                                                            "ms_p50": round(statistics.median(ms))}
    out = REPO / "spec" / "results" / f"asr-names-{time.strftime('%Y-%m-%d-%H%M')}.jsonl"
    with open(out, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
        f.write(json.dumps({"summary": summary, "method": "Kokoro-synthesised clips, faster-whisper int8 CPU, beam 1"}) + "\n")
    print(json.dumps(summary, indent=1)); print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
