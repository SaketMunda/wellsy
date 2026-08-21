"""Grounded voice answers — Python port of src/narration/describeScene.ts.

Day 10 (decisions.md D37): T3 lives in the engine, so this reads
`Track` dicts straight from tracker.py instead of round-tripping to the
browser. Same honesty rule as the TS original and as drawHud.ts/events.ts:
never invents an object, never resolves an uncertain label to one winner —
an uncertain track (see tracker.py's labelConfidence/runnerUpLabel) is
reported as "unidentified," grouped, never guessed.
"""

from __future__ import annotations

# Mirrors tracker.py's UNCERTAIN_CONFIDENCE-shaped threshold used by drawHud.ts/
# events.ts/describeScene.ts in the browser build — duplicated on purpose,
# same reasoning as generateLine.ts's PLURALS (small, independent consumers).
UNCERTAIN_CONFIDENCE = 0.6

PLURALS: dict[str, str] = {
    "person": "people",
    "mouse": "mice",
    "knife": "knives",
    "sandwich": "sandwiches",
    "couch": "couches",
    "bench": "benches",
    "scissors": "scissors",
    "skis": "skis",
    "broccoli": "broccoli",
}

NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]

UNIDENTIFIED = " unidentified"


def _plural(label: str, n: int) -> str:
    if n == 1:
        return label
    return PLURALS.get(label, f"{label}s")


def _article(label: str) -> str:
    return "an" if label[:1].lower() in "aeiou" else "a"


def _number_word(n: int) -> str:
    if 0 <= n < len(NUMBER_WORDS):
        return NUMBER_WORDS[n]
    return str(n)


def _join_english(parts: list[str]) -> str:
    if not parts:
        return "nothing"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _is_uncertain(track: dict) -> bool:
    return track.get("labelConfidence", 1.0) < UNCERTAIN_CONFIDENCE and track.get("runnerUpLabel") is not None


def describe_scene(tracks: list[dict]) -> str:
    if not tracks:
        return "nothing in view right now."

    counts: dict[str, int] = {}
    order: list[str] = []
    for t in tracks:
        key = UNIDENTIFIED if _is_uncertain(t) else t["label"]
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1

    parts = []
    for key in order:
        count = counts[key]
        if key == UNIDENTIFIED:
            parts.append("something unidentified" if count == 1 else f"{_number_word(count)} unidentified things")
        else:
            parts.append(f"{_article(key)} {key}" if count == 1 else f"{_number_word(count)} {_plural(key, count)}")

    total = len(tracks)
    noun = "thing" if total == 1 else "things"
    return f"{_number_word(total)} {noun}: {_join_english(parts)}."


def query_object(tracks: list[dict], obj: str) -> str:
    target = obj.strip().lower()
    matches = [t for t in tracks if t["label"].lower() == target and not _is_uncertain(t)]
    if matches:
        n = len(matches)
        if n == 1:
            return f"yes. one {target} in view."
        return f"yes. {_number_word(n)} {_plural(target, n)} in view."

    maybe = any(
        _is_uncertain(t) and (t["label"].lower() == target or (t.get("runnerUpLabel") or "").lower() == target)
        for t in tracks
    )
    if maybe:
        return f"maybe. something that could be a {target}, unconfirmed."
    return f"no. no {target} in view."
