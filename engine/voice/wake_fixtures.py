"""`wellsy record-wake` and `wellsy tune-wake` — Deliverable 5.

The wake threshold is picked from a measured false-accept / false-reject curve
over real recordings, never intuition. `record-wake` captures the fixtures (the
owner at the mic); `tune-wake` replays them through the real ASR path, sweeps
the `difflib` threshold, and writes the chosen value to `engine/config/voice.json`
plus the full curve to `spec/results/`.

Fixtures live in `spec/fixtures/wake/{wake,nonwake}/*.wav` and are committed, so
the choice is reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from datetime import date
from pathlib import Path

import numpy as np

from engine.voice.config import load_voice_config, save_wake_threshold
from engine.voice.wake import wake_score

_REPO = Path(__file__).resolve().parents[2]
FIX_DIR = _REPO / "spec" / "fixtures" / "wake"
RESULTS_DIR = _REPO / "spec" / "results"
SR = 16000

# What to ask the owner to say. (label, prompt, count, bucket)
_PLAN = [
    ("wellsy", 'Say just: "wellsy"', 20, "wake"),
    ("hey_wellsy", 'Say: "hey wellsy"', 12, "wake"),
    ("nearmiss", 'Say a near-miss (e.g. "well see", "wall street", "elsie", "wells")', 15, "nonwake"),
    ("chatter", 'Say a normal sentence with NO wake word', 18, "nonwake"),
]


def _record_clip(seconds: float) -> np.ndarray:
    import pyaudio

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SR, input=True, frames_per_buffer=1024)
    frames = []
    for _ in range(int(SR / 1024 * seconds)):
        frames.append(stream.read(1024, exception_on_overflow=False))
    stream.stop_stream()
    stream.close()
    pa.terminate()
    return np.frombuffer(b"".join(frames), dtype=np.int16)


def _write_wav(path: Path, pcm: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.astype(np.int16).tobytes())


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getframerate() != SR and pcm.size:
            import soxr

            pcm = soxr.resample(pcm, w.getframerate(), SR)
    return pcm


def record_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy record-wake")
    ap.add_argument("--seconds", type=float, default=2.0, help="clip length")
    ap.add_argument("--only", choices=[p[0] for p in _PLAN], help="record just one set")
    args = ap.parse_args(argv)

    if not sys.stdin.isatty():
        print("record-wake needs an interactive terminal (owner at the mic).", file=sys.stderr)
        return 2

    total_new = 0
    for label, prompt, count, bucket in _PLAN:
        if args.only and label != args.only:
            continue
        out_dir = FIX_DIR / bucket
        existing = len(list(out_dir.glob(f"{label}_*.wav"))) if out_dir.exists() else 0
        print(f"\n=== {label}: {prompt} ===  ({existing} already recorded, want {count})")
        for i in range(existing, count):
            input(f"  [{i + 1}/{count}] press Enter, then speak…")
            pcm = _record_clip(args.seconds)
            peak = float(np.abs(pcm).max()) / 32768.0
            _write_wav(out_dir / f"{label}_{i:03d}.wav", pcm)
            total_new += 1
            print(f"      saved (peak {peak:.2f}{'  ⚠ very quiet' if peak < 0.05 else ''})")

    print(f"\nrecorded {total_new} new clips under {FIX_DIR}")
    print("next: wellsy tune-wake")
    return 0


def _load_fixtures() -> tuple[list[np.ndarray], list[np.ndarray]]:
    wake = [_read_wav(p) for p in sorted((FIX_DIR / "wake").glob("*.wav"))]
    nonwake = [_read_wav(p) for p in sorted((FIX_DIR / "nonwake").glob("*.wav"))]
    return wake, nonwake


def tune_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy tune-wake")
    ap.add_argument("--asr-backend", default=None, help="registry ASR backend (default: auto)")
    ap.add_argument("--fa-weight", type=float, default=2.0,
                    help="cost multiplier on false-accepts vs false-rejects when picking")
    ap.add_argument("--write", action="store_true", help="persist the chosen threshold to voice.json")
    args = ap.parse_args(argv)

    wake_clips, nonwake_clips = _load_fixtures()
    if len(wake_clips) < 10 or len(nonwake_clips) < 10:
        print(f"need >=10 clips each; have wake={len(wake_clips)} nonwake={len(nonwake_clips)}. "
              f"Run `wellsy record-wake` first.", file=sys.stderr)
        return 2

    from engine.inference import registry

    asr = registry.get_backend("asr", args.asr_backend)
    cfg = load_voice_config()
    phrases = cfg.wake_phrases

    def scores(clips: list[np.ndarray]) -> list[tuple[str, float]]:
        out = []
        for pcm in clips:
            text = asr.transcribe(pcm) if hasattr(asr, "transcribe") else _stream_text(asr, pcm)
            out.append((text, wake_score(text, phrases)))
        return out

    wake_s = scores(wake_clips)
    nonwake_s = scores(nonwake_clips)

    curve = []
    for thr in [round(x / 100, 2) for x in range(50, 96, 1)]:
        fr = sum(1 for _, s in wake_s if s < thr)
        fa = sum(1 for _, s in nonwake_s if s >= thr)
        cost = args.fa_weight * fa / len(nonwake_s) + fr / len(wake_s)
        curve.append({"threshold": thr,
                      "false_accept": fa, "false_accept_rate": round(fa / len(nonwake_s), 4),
                      "false_reject": fr, "false_reject_rate": round(fr / len(wake_s), 4),
                      "cost": round(cost, 4)})

    best = min(curve, key=lambda r: (r["cost"], -r["threshold"]))

    print(f"\nwake clips: {len(wake_clips)}   non-wake clips: {len(nonwake_clips)}   "
          f"ASR: {asr.capabilities.version}")
    print(f"{'thr':>5} {'FA':>4} {'FA%':>7} {'FR':>4} {'FR%':>7} {'cost':>7}")
    for r in curve:
        mark = "  <-- chosen" if r["threshold"] == best["threshold"] else ""
        if r["threshold"] % 0.05 < 1e-9 or mark:
            print(f"{r['threshold']:>5.2f} {r['false_accept']:>4} {r['false_accept_rate']:>7.1%} "
                  f"{r['false_reject']:>4} {r['false_reject_rate']:>7.1%} {r['cost']:>7.3f}{mark}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"wake-tune-{date.today().isoformat()}.json"
    payload = {
        "date": date.today().isoformat(),
        "asr": asr.capabilities.as_row() if hasattr(asr.capabilities, "as_row") else str(asr.capabilities),
        "phrases": phrases,
        "n_wake": len(wake_clips),
        "n_nonwake": len(nonwake_clips),
        "fa_weight": args.fa_weight,
        "chosen_threshold": best["threshold"],
        "chosen": best,
        "curve": curve,
        "wake_transcripts": [{"text": t, "score": round(s, 4)} for t, s in wake_s],
        "nonwake_transcripts": [{"text": t, "score": round(s, 4)} for t, s in nonwake_s],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {out_path}")

    if args.write:
        save_wake_threshold(best["threshold"], provenance={
            "source": out_path.name, "n_wake": len(wake_clips), "n_nonwake": len(nonwake_clips),
            "false_accept_rate": best["false_accept_rate"], "false_reject_rate": best["false_reject_rate"],
        })
        print(f"set wake_threshold = {best['threshold']} in engine/config/voice.json")
    else:
        print("re-run with --write to persist the threshold")
    return 0


def _stream_text(asr, pcm: np.ndarray) -> str:
    last = ""
    for out in asr.stream(iter([pcm])):
        last = out.text or last
    return last
