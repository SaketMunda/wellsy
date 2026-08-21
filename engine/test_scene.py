"""Python port of src/narration/describeScene.test.ts's cases — same
behavior, not a shared fixture (only parseIntent's cases are shared per
decisions.md D37)."""

from __future__ import annotations

from scene import describe_scene, query_object


def track(label: str, **over) -> dict:
    base = {
        "id": 0,
        "label": label,
        "score": 0.9,
        "bbox": [0, 0, 10, 10],
        "ageMs": 0,
        "missedFrames": 0,
        "labelConfidence": 1,
        "runnerUpLabel": None,
        "labelVotes": {label: 0.9},
    }
    base.update(over)
    return base


def test_empty_scene() -> None:
    assert describe_scene([]) == "nothing in view right now."


def test_single_object() -> None:
    assert describe_scene([track("laptop")]) == "one thing: a laptop."


def test_three_distinct_objects_oxford_comma() -> None:
    scene = [track("person"), track("laptop"), track("bottle")]
    assert describe_scene(scene) == "three things: a person, a laptop, and a bottle."


def test_two_objects_no_comma() -> None:
    scene = [track("person"), track("laptop")]
    assert describe_scene(scene) == "two things: a person and a laptop."


def test_pluralizes_repeated_label() -> None:
    scene = [track("person"), track("person")]
    assert describe_scene(scene) == "two things: two people."


def test_uncertain_track_reported_unidentified() -> None:
    scene = [
        track("person"),
        track("laptop"),
        track("bed", labelConfidence=0.5, runnerUpLabel="dining table"),
    ]
    assert describe_scene(scene) == "three things: a person, a laptop, and something unidentified."


def test_groups_multiple_unidentified() -> None:
    scene = [
        track("bed", id=1, labelConfidence=0.5, runnerUpLabel="dining table"),
        track("couch", id=2, labelConfidence=0.5, runnerUpLabel="bed"),
    ]
    assert describe_scene(scene) == "two things: two unidentified things."


def test_query_yes_with_count() -> None:
    assert query_object([track("laptop")], "laptop") == "yes. one laptop in view."
    assert query_object([track("person"), track("person")], "person") == "yes. two people in view."


def test_query_no() -> None:
    assert query_object([track("laptop")], "bottle") == "no. no bottle in view."


def test_query_hedges_when_only_candidate_uncertain() -> None:
    scene = [track("bed", labelConfidence=0.5, runnerUpLabel="dining table")]
    assert query_object(scene, "dining table") == "maybe. something that could be a dining table, unconfirmed."
    assert query_object(scene, "bed") == "maybe. something that could be a bed, unconfirmed."
