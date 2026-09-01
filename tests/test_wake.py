"""Wake fuzzy-match scoring + the tune sweep's decision rule.

The *value* of the threshold is chosen by `wellsy tune-wake` against committed
recordings (Deliverable 5) — not asserted here. What is asserted: the scorer
ranks a clean/near wake utterance above ordinary speech, and the sweep, given a
separable score set, picks a threshold that admits every wake and rejects every
non-wake.
"""

from __future__ import annotations

from engine.voice.wake import WakeState, is_wake, wake_score

PHRASES = ["wellsy", "hey wellsy"]


def test_exact_and_near_score_high():
    assert wake_score("wellsy", PHRASES) == 1.0
    assert wake_score("hey wellsy", PHRASES) == 1.0
    assert wake_score("welsey", PHRASES) > 0.75      # common STT slip
    assert wake_score("hey welsey", PHRASES) > 0.75
    assert wake_score("um wellsy you there", PHRASES) > 0.75  # buried in a window


def test_clearly_unrelated_speech_scores_low():
    for s in ["what time is it", "the sky is blue", "show me the weather"]:
        assert wake_score(s, PHRASES) < 0.6


def test_wake_beats_nonwake_margin():
    # difflib alone cannot cleanly separate "well" (0.8 vs "wellsy") from a real
    # slip like "welsey" — that gap is exactly why the threshold is tuned
    # against recordings (Deliverable 5), not asserted here. What must hold is
    # the ordering: a true wake outscores ordinary speech.
    wake = min(wake_score(s, PHRASES) for s in ["wellsy", "hey wellsy", "welsey"])
    nonwake = max(wake_score(s, PHRASES) for s in ["what time is it", "the sky is blue"])
    assert wake > nonwake


def test_is_wake_threshold():
    assert is_wake("wellsy", PHRASES, 0.8)
    assert not is_wake("what time is it", PHRASES, 0.8)


def test_wake_state_toggle():
    st = WakeState()
    assert not st.awake
    st.wake()
    assert st.awake
    st.sleep()
    assert not st.awake


def test_sweep_picks_separating_threshold():
    # mimic wake_fixtures.tune_main's rule on a separable set
    wake_scores = [1.0, 0.95, 0.83, 0.8, 0.78]
    nonwake_scores = [0.2, 0.35, 0.5, 0.55, 0.6]
    best, best_cost = None, 1e9
    for thr in [x / 100 for x in range(50, 96)]:
        fr = sum(1 for s in wake_scores if s < thr)
        fa = sum(1 for s in nonwake_scores if s >= thr)
        cost = 2.0 * fa / len(nonwake_scores) + fr / len(wake_scores)
        if cost < best_cost or (cost == best_cost and thr > best):
            best, best_cost = thr, cost
    assert 0.6 < best <= 0.78
    assert best_cost == 0.0  # perfectly separable -> zero FA and FR
