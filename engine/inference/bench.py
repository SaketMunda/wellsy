"""`wellsy bench` — the cross-platform inference benchmark harness.

`.claude/rebuild/step2-backend-abstraction.md` Deliverable 4. One command, no
arguments required, runs anywhere. For every modality and every *available*
backend it reports, honestly and by measurement (INVARIANTS "measured, not
estimated"):

    cold-start load ms, warm p50 / p95 over >= N trials (default 20),
    resident-memory delta, RTF where it applies, platform, accelerator,
    and the backend's pinned version + verification date.

Unavailable backends still get a row (status ``unavailable`` + reason) so the
table is always complete — that is the point of the harness: every later step
runs ``wellsy bench`` to prove it did not regress, and a silently missing row
hides a regression.

Machine-readable output goes to
``spec/results/bench-<date>-<platform>-<commit>.jsonl`` (first line is a
``kind:"run"`` meta record, then one ``kind:"result"`` record per row). A
human-readable table is printed to stdout.

    wellsy bench                     # everything
    wellsy bench --modality vad      # one modality
    wellsy bench --backend energy    # one backend
    wellsy bench --trials 50
"""

from __future__ import annotations

import os as _os

# Keep huggingface_hub's cache-check progress bars out of the middle of the
# table (mlx_lm.load prints them even for a fully-cached model).
_os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import argparse
import json
import platform as _platform
import statistics
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from engine.inference import base, registry

RESULTS_DIR = Path(__file__).resolve().parents[2] / "spec" / "results"
AUDIO_SR = 16000
AUDIO_SECONDS = 5.0


# --------------------------------------------------------------------------- #
# small helpers                                                                #
# --------------------------------------------------------------------------- #


def pct(vals: list[float], p: float) -> float:
    """Nearest-rank percentile — same convention as bench/detector_bench.py."""

    if not vals:
        return float("nan")
    s = sorted(vals)
    idx = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return s[idx]


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        return out.stdout.strip() or "nogit"
    except Exception:
        return "nogit"


def _rss_mb() -> float:
    import psutil  # in the default deps

    return psutil.Process().memory_info().rss / (1024 * 1024)


# --------------------------------------------------------------------------- #
# synthetic workloads                                                          #
# --------------------------------------------------------------------------- #


def _speechy_audio(seconds: float = AUDIO_SECONDS, sr: int = AUDIO_SR) -> np.ndarray:
    """A deterministic waveform that alternates 400 ms voiced-ish bursts with
    200 ms near-silence. Not speech, but it exercises a VAD/ASR front-end with
    changing energy and a plausible spectrum."""

    n = int(seconds * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(0)
    voiced = (
        0.3 * np.sin(2 * np.pi * 140 * t)
        + 0.15 * np.sin(2 * np.pi * 240 * t)
        + 0.05 * rng.standard_normal(n)
    ).astype(np.float32)
    env = np.zeros(n, dtype=np.float32)
    step = int(0.6 * sr)
    on = int(0.4 * sr)
    for start in range(0, n, step):
        env[start:start + on] = 1.0
    return voiced * env


def _frames(audio: np.ndarray, size: int) -> list[np.ndarray]:
    return [audio[i:i + size] for i in range(0, len(audio) - size + 1, size)]


# `/no_think` measures the runtime, not Qwen3's 15-20 s of reasoning tokens
# (ignored as plain text by non-Qwen servers). TTFT here is prompt-processing +
# first-token, which is the number a voice path cares about.
LLM_MESSAGES = [
    {"role": "user", "content": "/no_think Count from one to twenty in words, comma separated."}
]
TTS_TEXT_CHUNKS = [
    "Hello. ",
    "This is a streaming synthesis check ",
    "for the WELLSY inference seam.",
]


# --------------------------------------------------------------------------- #
# per-backend benchmark                                                        #
# --------------------------------------------------------------------------- #


def _empty_row(modality: str, backend: str) -> dict[str, Any]:
    return {
        "kind": "result",
        "modality": modality,
        "backend": backend,
        "status": "unavailable",
        "reason": None,
        "platform": base.platform_tag(),
        "accelerator": None,
        "version": None,
        "verified": None,
        "streams": None,
        "coldLoadMs": None,
        "coldFirstOpMs": None,
        "p50Ms": None,
        "p95Ms": None,
        "meanMs": None,
        "trials": 0,
        "residentMb": None,
        "rtfP50": None,
        "rtfP95": None,
        "extra": {},
    }


def _drain(it: Iterable[Any]) -> list[Any]:
    return list(it)


def bench_one(modality: str, backend: str, *, trials: int, warmup: int) -> dict[str, Any]:
    row = _empty_row(modality, backend)
    cls = registry.backends_for(modality)[backend]

    try:
        if not cls.is_available():
            row["reason"] = "is_available() == False"
            return row
    except Exception as e:  # pragma: no cover
        row["status"] = "error"
        row["reason"] = f"is_available() raised: {e}"
        return row

    # ---- cold load ----
    rss0 = _rss_mb()
    t0 = time.monotonic()
    try:
        inst = registry.get_backend(modality, backend)
    except base.BackendUnavailable as e:
        row["reason"] = str(e)
        return row
    except Exception as e:  # pragma: no cover
        row["status"] = "error"
        row["reason"] = f"construction raised: {e}"
        return row
    row["coldLoadMs"] = round((time.monotonic() - t0) * 1000, 2)

    caps = getattr(inst, "capabilities", None)
    if caps is not None:
        row["accelerator"] = caps.accelerator
        row["version"] = caps.version
        row["verified"] = caps.verified
        row["streams"] = caps.streams

    # workload closure -> (wall_seconds, audio_or_output_seconds_or_None, extra)
    run = _make_runner(modality, inst)

    # ---- cold first op ----
    try:
        t0 = time.monotonic()
        first = run()
        row["coldFirstOpMs"] = round((time.monotonic() - t0) * 1000, 2)
    except (base.BackendUnavailable, NotImplementedError) as e:
        row["reason"] = f"{type(e).__name__}: {e}"
        _close(inst)
        return row
    except Exception as e:  # pragma: no cover
        row["status"] = "error"
        row["reason"] = f"first op raised: {e}"
        _close(inst)
        return row
    row["residentMb"] = round(max(0.0, _rss_mb() - rss0), 1)

    # ---- warm ----
    for _ in range(max(0, warmup)):
        run()

    wall_ms: list[float] = []
    rtf: list[float] = []
    ttft_ms: list[float] = []
    for _ in range(trials):
        r = run()
        wall_ms.append(r["wall_s"] * 1000)
        if r.get("media_s"):
            rtf.append(r["wall_s"] / r["media_s"])
        if r.get("ttft_s") is not None:
            ttft_ms.append(r["ttft_s"] * 1000)

    row["status"] = "ok"
    row["trials"] = trials
    row["p50Ms"] = round(pct(wall_ms, 50), 2)
    row["p95Ms"] = round(pct(wall_ms, 95), 2)
    row["meanMs"] = round(statistics.mean(wall_ms), 2)
    if rtf:
        row["rtfP50"] = round(pct(rtf, 50), 4)
        row["rtfP95"] = round(pct(rtf, 95), 4)
    if ttft_ms:
        row["extra"]["ttftP50Ms"] = round(pct(ttft_ms, 50), 2)
        row["extra"]["ttftP95Ms"] = round(pct(ttft_ms, 95), 2)
    if isinstance(first, dict) and first.get("note"):
        row["extra"]["note"] = first["note"]
    _close(inst)
    return row


def _close(inst: Any) -> None:
    for name in ("close", "reset"):
        fn = getattr(inst, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


def _make_runner(modality: str, inst: Any):
    """Return a zero-arg callable that performs one unit of work and returns a
    dict with wall_s, optional media_s (for RTF), optional ttft_s."""

    if modality == "llm":
        def run_llm() -> dict[str, Any]:
            t0 = time.monotonic()
            ttft = None
            n_deltas = 0
            for d in inst.stream(LLM_MESSAGES):
                if ttft is None and getattr(d, "text", ""):
                    ttft = time.monotonic() - t0
                n_deltas += 1
            return {"wall_s": time.monotonic() - t0, "ttft_s": ttft, "n_deltas": n_deltas}
        return run_llm

    if modality == "vad":
        audio = _speechy_audio()
        frame = getattr(inst, "FRAME", 512)
        frames = _frames(audio, frame)
        media_s = len(frames) * frame / AUDIO_SR
        reset = getattr(inst, "reset", None)
        def run_vad() -> dict[str, Any]:
            if callable(reset):
                reset()  # each trial starts from a clean recurrent state
            t0 = time.monotonic()
            out = _drain(inst.stream(iter(frames)))
            return {"wall_s": time.monotonic() - t0, "media_s": media_s, "n": len(out)}
        return run_vad

    if modality == "asr":
        audio = _speechy_audio()
        chunks = _frames(audio, int(0.5 * AUDIO_SR))
        media_s = len(chunks) * int(0.5 * AUDIO_SR) / AUDIO_SR
        def run_asr() -> dict[str, Any]:
            t0 = time.monotonic()
            out = _drain(inst.stream(iter(chunks)))
            return {"wall_s": time.monotonic() - t0, "media_s": media_s, "n": len(out)}
        return run_asr

    if modality == "tts":
        def run_tts() -> dict[str, Any]:
            t0 = time.monotonic()
            total = 0
            sr = getattr(inst, "SAMPLE_RATE", 24000)
            for ch in inst.stream(iter(TTS_TEXT_CHUNKS)):
                total += int(np.asarray(ch.pcm).size)
                sr = ch.sample_rate or sr
            return {"wall_s": time.monotonic() - t0, "media_s": total / sr if total else None}
        return run_tts

    raise KeyError(modality)


# --------------------------------------------------------------------------- #
# table + file                                                                 #
# --------------------------------------------------------------------------- #

_COLS = [
    ("modality", 8), ("backend", 12), ("status", 11), ("accel", 9),
    ("cold_ms", 9), ("p50_ms", 9), ("p95_ms", 9), ("rtf_p50", 8),
    ("resid_mb", 9), ("version", 26), ("verified", 10),
]


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) >= 1 or v == 0 else f"{v:.4f}"
    return str(v)


def print_table(rows: list[dict[str, Any]]) -> None:
    header = "  ".join(name.ljust(w) for name, w in _COLS)
    print(header)
    print("-" * len(header))
    for r in rows:
        cells = {
            "modality": r["modality"], "backend": r["backend"], "status": r["status"],
            "accel": r["accelerator"], "cold_ms": r["coldLoadMs"], "p50_ms": r["p50Ms"],
            "p95_ms": r["p95Ms"], "rtf_p50": r["rtfP50"], "resid_mb": r["residentMb"],
            "version": r["version"], "verified": r["verified"],
        }
        print("  ".join(_fmt(cells[name]).ljust(w)[:w] for name, w in _COLS))
        if r["status"] != "ok" and r["reason"]:
            print(f"    └─ {r['reason']}")
        if r["extra"].get("ttftP50Ms") is not None:
            print(f"    └─ TTFT p50 {r['extra']['ttftP50Ms']} ms / p95 {r['extra']['ttftP95Ms']} ms")


def write_jsonl(rows: list[dict[str, Any]], path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "run", **meta}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# entry point                                                                  #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="wellsy bench",
        description="Cross-platform inference benchmark. No arguments required.",
    )
    ap.add_argument("--modality", choices=[*registry.MODALITIES, "all"], default="all")
    ap.add_argument("--backend", default=None, help="only this backend id (across the chosen modality/-ies)")
    ap.add_argument("--trials", type=int, default=20, help="timed warm trials (>= 20 for acceptance)")
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--out", default=None, help="override the .jsonl output path")
    ap.add_argument("--slot", choices=["planner", "fast", "vlm", "all"], default="all",
                    help="llm only: which model role to bench (step 5b)")
    ap.add_argument("--candidate", default=None, help="llm only: a single model id")
    args = ap.parse_args(argv)

    # `--modality llm` is the per-slot model bench-off (step 5b Deliverable 1),
    # not the old single composite row. `--backend` still forces the legacy
    # backend-regression path for the llm modality.
    if args.modality == "llm" and not args.backend:
        from engine.inference import llm_bench

        llm_argv = ["--slot", args.slot, "--trials", str(args.trials),
                    "--warmup", str(args.warmup)]
        if args.candidate:
            llm_argv += ["--candidate", args.candidate]
        if args.out:
            llm_argv += ["--out", args.out]
        return llm_bench.run(llm_argv)

    modalities = list(registry.MODALITIES) if args.modality == "all" else [args.modality]
    snapshot = registry.describe()

    print(f"[bench] platform={snapshot['platform']}  accelerator={snapshot['accelerator']}  "
          f"jetson={snapshot['isJetson']}  trials={args.trials}")
    print(f"[bench] auto-selected: {snapshot['selected']}")
    print()

    rows: list[dict[str, Any]] = []
    for m in modalities:
        for backend in sorted(registry.backends_for(m)):
            if args.backend and backend != args.backend:
                continue
            rows.append(bench_one(m, backend, trials=args.trials, warmup=args.warmup))

    print_table(rows)

    commit = _commit()
    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"bench-{date.today().isoformat()}-{base.platform_tag().replace('/', '-')}-{commit}.jsonl"
    )
    meta = {
        "date": date.today().isoformat(),
        "platform": base.platform_tag(),
        "python": _platform.python_version(),
        "commit": commit,
        "accelerator": snapshot["accelerator"],
        "selected": snapshot["selected"],
        "available": snapshot["available"],
        "trials": args.trials,
    }
    write_jsonl(rows, out, meta)
    print(f"\n[bench] wrote {out}")

    # Exit non-zero only on an unexpected error, not on an expected
    # 'unavailable' (no server, scaffolded model). CI decides what to gate on.
    return 1 if any(r["status"] == "error" for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
