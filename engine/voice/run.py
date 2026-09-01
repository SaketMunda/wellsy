"""CLI entrypoints for the voice path — dispatched from `engine/cli.py`.

    wellsy voice                 live streaming conversation (wake phrase to start)
    wellsy voice --awake         skip the wake phrase
    wellsy voice --measure       the spec/phase1-acceptance.md §1 latency harness
    wellsy voice --profile-cpu N sample idle CPU for N seconds
    wellsy record-wake           guided capture of wake / non-wake fixtures
    wellsy tune-wake             sweep the fuzzy threshold against the fixtures
"""

from __future__ import annotations


def voice(argv: list[str]) -> int:
    from engine.voice import pipeline

    return pipeline.main(argv)


def record_wake(argv: list[str]) -> int:
    from engine.voice import wake_fixtures

    return wake_fixtures.record_main(argv)


def tune_wake(argv: list[str]) -> int:
    from engine.voice import wake_fixtures

    return wake_fixtures.tune_main(argv)
