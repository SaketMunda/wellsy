"""T1: open-vocabulary detection — YOLOE via Ultralytics (PyTorch/MPS).

See decisions.md D30 for why this is YOLOE-on-PyTorch-MPS and not the
brief's literal "YOLOE via MLX": no PyPI package implements an
open-vocabulary detector on MLX (checked directly, not assumed) — building
YOLOE's text-prompt head from scratch in raw MLX ops is a multi-day job,
not a Day 8 job. This keeps the thing that actually matters (open
vocabulary, so "microphone" and "bed" are namable at all) and drops only
the specific runtime named in the plan.

Model weights (the .pt detector and the MobileCLIP text encoder it downloads
on first use — `mobileclip2_b.ts`, ~254 MB, for YOLOE-26) are cached under WEIGHTS_DIR, *outside* the repo —
see the boundary in day8-prompt.md: nothing large or generated belongs in
git. `configure_weights_cache()` points Ultralytics' own settings at that
directory and chdirs into it before any download-triggering call, because
Ultralytics' asset downloader falls back to the *current working directory*
for anything not already found at an absolute path or in its settings dir
(read from its source directly — this isn't documented behavior).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

WEIGHTS_DIR = Path.home() / ".cache" / "wellsy" / "weights"
# Step 5c: YOLOE-26 (YOLO26 arch, NMS-free head; ultralytics >= 8.4.0), same
# `s` scale and set_classes() API as the yoloe-11s it replaced. Measured on one
# recorded clip, gate held open: equal-or-better on live T1 (p50 30.0-30.8 vs
# 30.3-32.5 ms), cold first call, phone recall and false positives
# (`.claude/rebuild/step5c-results.md` §4). LVIS 30.8 vs 27.5 per the docs.
MODEL_NAME = "yoloe-26s-seg.pt"
PROMPTS_PATH = Path(__file__).resolve().parent.parent / "config" / "prompts.txt"

# UNIDENTIFIED discipline (decisions.md D22) survives the detector swap: an
# open-vocab model can still be confidently wrong, so anything below this
# floor is relabeled rather than trusted outright.
UNCERTAIN_CONFIDENCE = 0.35


def configure_weights_cache() -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    from ultralytics import settings as ul_settings

    ul_settings.update(weights_dir=str(WEIGHTS_DIR))
    os.chdir(WEIGHTS_DIR)


def load_prompts(path: Path = PROMPTS_PATH) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def load_model(device: str = "mps", name: str | None = None):
    """`name` overrides MODEL_NAME — verification harnesses only (step 5c's
    `wellsy --detector`); the shipped default is MODEL_NAME."""
    configure_weights_cache()
    from ultralytics import YOLOE

    model = YOLOE(name or MODEL_NAME)
    return model


def set_prompts(model, names: list[str]) -> None:
    """(Re)binds the model's text-prompt classes. Called once at startup and
    again on prompts.txt hot-reload.

    The YOLOE-11 text encoder (`mobileclip_blt.ts`) carries float64 tensors
    MPS can't hold — a real MPS gap, not a config mistake. Step 5c measured
    YOLOE-26's `mobileclip2_b.ts` embedding on MPS directly (float32, no
    error), so this CPU detour is no longer required for the default model;
    it is kept because it is harmless, works for both encoders, and removing
    it is a step-9 code change, not a model-string change. So text-prompt embedding runs on CPU (cheap,
    one-off per prompt-list change), and only the per-frame image forward
    pass — the thing running at 8Hz — moves to MPS.
    """
    model.model.to("cpu")
    text_pe = model.get_text_pe(names)
    model.set_classes(names, text_pe)


def predict(model, frame_bgr: np.ndarray, device: str = "mps") -> list[dict]:
    """Runs one detection pass. Returns a list of dicts matching
    src/vision/types.ts's `Detection` shape: label, score, bbox as
    [x, y, width, height] in pixel space — so Day 9's bridge is plumbing,
    not translation.
    """
    results = model.predict(frame_bgr, device=device, verbose=False)[0]
    names = results.names
    detections = []
    boxes = results.boxes
    if boxes is None:
        return detections
    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        score = float(box.conf[0])
        cls_id = int(box.cls[0])
        label = names[cls_id]
        if score < UNCERTAIN_CONFIDENCE:
            label = "UNIDENTIFIED"
        detections.append({
            "label": label,
            "score": round(score, 4),
            "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
        })
    return detections
