"""Reads spec/intent-cases.json — the case list for the deterministic intent
path (invariant #3). Ported unchanged from engine/test_intent.py; only the
import path and the fixture location moved with the rebuild."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.honesty.intent import parse_intent

SPEC_PATH = Path(__file__).resolve().parents[1] / "spec" / "intent-cases.json"
CASES = json.loads(SPEC_PATH.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_intent_case(case: dict) -> None:
    result = parse_intent(case["transcript"]).to_dict()
    assert result == case["intent"]
