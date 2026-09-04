"""`wellsy bench --modality llm` per-slot bench-off — unit coverage.

Step 5b Deliverable 1. No live server: `stream_turn` is stubbed so the
aggregation, the thinking-token metric, the candidate filter and the JSONL
emission are all tested deterministically. A live campaign is the results doc's
job, not the suite's.
"""

from __future__ import annotations

import json

import pytest

from engine.inference import llm_bench
from engine.inference.llm_bench import Candidate, TurnResult, bench_candidate


def _turn(ttft=0.05, wall=0.9, content_chars=400, think_chars=0,
          eval_count=120, eval_s=1.0, load_s=None, prompt_tokens=350, content_text=""):
    return TurnResult(ttft, wall, content_chars, think_chars, eval_count, eval_s,
                      load_s, prompt_tokens, ok=True, content_text=content_text)


_GOOD_PLAN = (
    '{"steps": [{"tool": "calendar_move_event", "args": {}}, '
    '{"tool": "mail_create_draft", "args": {}}, '
    '{"tool": "reminders_create", "args": {}}]}'
)


def test_plan_is_valid_accepts_good_plan_and_rejects_junk():
    assert llm_bench.plan_is_valid(_GOOD_PLAN)
    assert llm_bench.plan_is_valid("```json\n" + _GOOD_PLAN + "\n```")
    assert not llm_bench.plan_is_valid("here is your plan: do three things")
    assert not llm_bench.plan_is_valid('{"steps": [{"tool": "not_a_tool", "args": {}}]}')
    assert not llm_bench.plan_is_valid('{"steps": [{"tool": "mail_send_draft"}]}')  # <3


def test_think_tokens_est_is_char_proportional_split_of_eval_count():
    # half the characters are thinking -> half the real tokens attributed to it
    t = _turn(content_chars=200, think_chars=200, eval_count=100)
    assert t.think_tokens_est == 50.0
    # no thinking at all -> zero, never None when eval_count is known
    assert _turn(think_chars=0, eval_count=100).think_tokens_est == 0.0
    # server gave no token count -> None, not a fabricated number (INVARIANTS #6)
    assert _turn(eval_count=None).think_tokens_est is None


def test_tok_per_s_needs_both_count_and_duration():
    assert _turn(eval_count=120, eval_s=2.0).tok_per_s == 60.0
    assert _turn(eval_count=120, eval_s=None).tok_per_s is None


def test_bench_candidate_aggregates_p50_p95_and_records_method(monkeypatch):
    calls = {"n": 0}

    def fake_stream_turn(client, base_url, model, messages, *, think, images, **kw):
        calls["n"] += 1
        # cold turn (first call) carries a load time; warm turns don't
        return _turn(ttft=0.10 if calls["n"] == 1 else 0.04,
                     load_s=1.8 if calls["n"] == 1 else None,
                     think_chars=0, eval_count=100, eval_s=1.25)

    monkeypatch.setattr(llm_bench, "stream_turn", fake_stream_turn)
    monkeypatch.setattr(llm_bench, "_is_ollama", lambda _u: True)
    monkeypatch.setattr(llm_bench, "_unload", lambda *a, **k: None)
    monkeypatch.setattr(llm_bench, "_resident_mb", lambda *a, **k: 2100.0)

    cand = Candidate("fast", "dummy:3b", "test", think=None)
    row = bench_candidate(cand, base_url="http://x/v1", trials=20, warmup=2)

    assert row["status"] == "ok"
    assert row["trials"] == 20
    assert row["coldLoadS"] == 1.8            # from the separated cold turn
    assert row["ttftP50Ms"] == pytest.approx(40.0, abs=1)
    assert row["tokPerSP50"] == pytest.approx(80.0, abs=1)
    assert row["thinkTokensP50"] == 0.0
    assert row["residentMb"] == 2100.0
    assert "n>=20 warm, cold turn separate" in row["method"]
    # cold + warmup(2) + trials(20)
    assert calls["n"] == 23


def test_bench_candidate_flags_a_reasoning_prefix(monkeypatch):
    def fake_stream_turn(client, base_url, model, messages, *, think, images, **kw):
        # 90% of characters are chain-of-thought
        return _turn(content_chars=100, think_chars=900, eval_count=1000, eval_s=5.0)

    monkeypatch.setattr(llm_bench, "stream_turn", fake_stream_turn)
    monkeypatch.setattr(llm_bench, "_is_ollama", lambda _u: True)
    monkeypatch.setattr(llm_bench, "_unload", lambda *a, **k: None)
    monkeypatch.setattr(llm_bench, "_resident_mb", lambda *a, **k: None)

    row = bench_candidate(Candidate("planner", "reasoner:4b", "test", think=None),
                          base_url="http://x/v1", trials=20, warmup=0)
    assert row["thinkTokensP50"] == pytest.approx(900.0, abs=1)
    assert row["contentTokensP50"] == pytest.approx(100.0, abs=1)


def test_bench_candidate_scores_plan_validity_for_planner_slot(monkeypatch):
    seq = [True, True, False, True]  # 3/4 valid
    i = {"k": 0}

    def fake_stream_turn(client, base_url, model, messages, *, think, images, **kw):
        good = seq[i["k"] % len(seq)]
        i["k"] += 1
        return _turn(content_text=_GOOD_PLAN if good else "nope, prose only",
                     eval_count=100, eval_s=1.0)

    monkeypatch.setattr(llm_bench, "stream_turn", fake_stream_turn)
    monkeypatch.setattr(llm_bench, "_is_ollama", lambda _u: True)
    monkeypatch.setattr(llm_bench, "_unload", lambda *a, **k: None)
    monkeypatch.setattr(llm_bench, "_resident_mb", lambda *a, **k: None)

    row = bench_candidate(Candidate("planner", "p:4b", "t"), base_url="http://x/v1",
                          trials=4, warmup=0)
    assert row["planValidRate"] == 0.75


def test_unavailable_server_is_a_row_not_a_crash(monkeypatch):
    monkeypatch.setattr(llm_bench, "_is_ollama", lambda _u: False)

    class _Resp:
        status_code = 503

    monkeypatch.setattr(llm_bench.httpx, "get", lambda *a, **k: _Resp())
    row = bench_candidate(Candidate("fast", "x:3b", "t"), base_url="http://nope/v1",
                          trials=20, warmup=0)
    assert row["status"] == "unavailable"
    assert "no server" in row["reason"]


def test_run_filters_by_slot_and_candidate_and_writes_jsonl(monkeypatch, tmp_path):
    seen = []

    def fake_bench_candidate(cand, **kw):
        seen.append((cand.slot, cand.model))
        return {"kind": "result", "slot": cand.slot, "model": cand.model,
                "status": "ok", "reason": None, "trials": kw["trials"],
                "method": "x"}

    monkeypatch.setattr(llm_bench, "bench_candidate", fake_bench_candidate)
    out = tmp_path / "r.jsonl"
    rc = llm_bench.run(["--slot", "planner", "--trials", "20", "--out", str(out)])

    assert rc == 0
    assert seen and all(s == "planner" for s, _ in seen)
    lines = out.read_text().strip().splitlines()
    assert json.loads(lines[0])["kind"] == "run"
    assert all(json.loads(x)["slot"] == "planner" for x in lines[1:])


def test_run_reports_error_rows_as_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_bench, "bench_candidate",
                        lambda cand, **kw: {"kind": "result", "slot": cand.slot,
                                            "model": cand.model, "status": "error",
                                            "reason": "boom", "trials": 0, "method": "x"})
    rc = llm_bench.run(["--slot", "fast", "--out", str(tmp_path / "r.jsonl")])
    assert rc == 1
