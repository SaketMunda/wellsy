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
    assert src.index("motion_gate(prev_gray, gray)") < src.index("t1_should_run(")


def test_flag_is_on_the_cli():
    assert "--gate-open" in inspect.getsource(cli.main)
