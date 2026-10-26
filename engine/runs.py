"""Append-only JSONL logs under `runs/` (git-ignored): one line per task, per turn."""

from __future__ import annotations

import json
import math
import statistics
import time

from engine.settings import REPO

RUNS = REPO / "runs"


def log(stream: str, record: dict) -> None:
    """`runs/<stream>.jsonl`, e.g. "tasks" (cost per task) or "latency" (per turn)."""
    RUNS.mkdir(exist_ok=True)
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}
    with (RUNS / f"{stream}.jsonl").open("a") as f:
        f.write(json.dumps(line, default=str) + "\n")


def read(stream: str) -> list[dict]:
    p = RUNS / f"{stream}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def percentile(xs: list[float], q: float) -> float:
    """Nearest-rank percentile, q in 0..100."""
    s = sorted(xs)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


def summary(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "p50": round(statistics.median(xs), 3),
            "p95": round(percentile(xs, 95), 3), "max": round(max(xs), 3)}
