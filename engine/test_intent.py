"""Reads spec/intent-cases.json — the same fixture parseIntent.test.ts reads.
One spec, two implementations; see decisions.md D37."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intent import parse_intent

SPEC_PATH = Path(__file__).parent.parent / "spec" / "intent-cases.json"
CASES = json.loads(SPEC_PATH.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_intent_case(case: dict) -> None:
    result = parse_intent(case["transcript"]).to_dict()
    assert result == case["intent"]
