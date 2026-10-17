"""`wellsy --gate-open` — the step 5c verification-harness flag.

Step 6c measured T1 running on 1.8 % of frames because the T0 gate stayed
closed. The flag lets a detector comparison bypass that decision without
retuning or skipping T0 (INVARIANTS #5).
"""

from __future__ import annotations

import inspect

from engine import cli


def test_default_behaviour_is_unchanged():
    # still frame, past the hold window, already bootstrapped -> T1 idle
    assert cli.t1_should_run(gated=True, held_open=False, bootstrapped=True) is False
    assert cli.t1_should_run(gated=False, held_open=False, bootstrapped=True) is True
    assert cli.t1_should_run(gated=True, held_open=True, bootstrapped=True) is True
    assert cli.t1_should_run(gated=True, held_open=False, bootstrapped=False) is True


def test_gate_open_runs_t1_on_a_still_frame():
    assert cli.t1_should_run(gated=True, held_open=False, bootstrapped=True,
                             gate_open=True) is True


def test_t0_still_runs_before_the_decision_with_gate_open():
    """INVARIANTS #5: the motion gate is computed and timed every frame; the
    flag only changes whether its verdict is consulted."""
    src = inspect.getsource(cli.run_camera)
    assert src.index("motion_gate(prev_gray, gray)") < src.index("t1_reason(")


def test_flag_is_on_the_cli():
    assert "--gate-open" in inspect.getsource(cli.main)


# --- T1 heartbeat (5c follow-up) --------------------------------------------- #


def test_heartbeat_runs_t1_on_a_still_frame_when_due():
    """A still person putting on glasses never opens T0 (peak 4.1/255 vs 5.0);
    the heartbeat is what makes the change visible at all."""
    assert cli.t1_reason(gated=True, held_open=False, bootstrapped=True,
                         heartbeat_due=True) == "heartbeat"
    assert cli.t1_reason(gated=True, held_open=False, bootstrapped=True,
                         heartbeat_due=False) is None


def test_reason_precedence_is_reported_honestly():
    assert cli.t1_reason(gated=True, held_open=False, bootstrapped=False) == "bootstrap"
    assert cli.t1_reason(gated=False, held_open=True, bootstrapped=True,
                         heartbeat_due=True) == "motion"
    assert cli.t1_reason(gated=True, held_open=True, bootstrapped=True,
                         heartbeat_due=True) == "hold"
    assert cli.t1_reason(gated=True, held_open=False, bootstrapped=True,
                         gate_open=True) == "gate-open"


def test_heartbeat_default_and_off_switch():
    assert cli.T1_HEARTBEAT_S == 1.0
    src = inspect.getsource(cli.run_camera)
    # 0 disables it: the pre-5c motion-only behaviour stays reachable
    assert "heartbeat_s > 0 and" in src
    # the 8 Hz cap still applies to heartbeat runs too
    assert "reason is not None and due" in src
