"""Step 4c — open-air audio: the echo-regression fixes.

Deliverable 1 (half-duplex gate) and Deliverable 2 (self-transcript rejection).
The strings under test are the *actual* transcripts from the live session
2026-09-02 recorded in `.claude/rebuild/step4c-echo-and-duplex.md` — the loop
where the bot heard itself, VAD read it as barge-in, and STT transcribed the
bot's own words as the user.
"""

from __future__ import annotations

import asyncio

import pytest

from engine.voice.duplex import (
    SelfEchoWindow,
    build_echo_text_tap,
    build_half_duplex_gate,
    build_self_echo_filter,
    echo_match_score,
    is_self_echo,
)

# --------------------------------------------------------------------------- #
# Deliverable 2 — reject its own words (acceptance #3)                          #
# --------------------------------------------------------------------------- #

# what the bot actually spoke -> the fragments STT produced from the playback
_LOG_2026_09_02 = [
    ("What can I do for you?", ["What can I do for?", "what can I do for"]),
    (
        "I can't share deeds as I don't have physical access to your files.",
        ["I can't share deep.", "I can't share her.", "I can't share."],
    ),
]


@pytest.mark.parametrize("spoken,fragments", _LOG_2026_09_02)
def test_self_echo_catches_the_real_fragments(spoken, fragments):
    for frag in fragments:
        echo, score, matched = is_self_echo(frag, [spoken], threshold=0.8)
        assert echo, f"{frag!r} not flagged against {spoken!r} (score {score:.2f})"
        assert matched == spoken


def test_self_echo_distinguishes_deeds_from_deep():
    # the discriminating case the prompt names explicitly:
    # "I can't share deep." (echo) vs a genuine "I can't share deeds…" reply
    spoken = "I can't share deeds as I don't have physical access to your files."
    assert is_self_echo("I can't share deep.", [spoken], threshold=0.8)[0]
    # a real user asking about deeds is close to the bot's own words but should
    # still be admitted when it is not a near-verbatim prefix
    echo, score, _ = is_self_echo(
        "can you share the deeds from last year", [spoken], threshold=0.8
    )
    assert not echo, f"real question suppressed (score {score:.2f})"


def test_self_echo_ignores_unrelated_user_speech():
    spoken = ["What can I do for you?", "I can't share deeds as I don't have physical access."]
    for user in ["what time is it", "play some music", "remind me to call mom at six"]:
        echo, score, _ = is_self_echo(user, spoken, threshold=0.8)
        assert not echo, f"{user!r} wrongly flagged (score {score:.2f})"


def test_self_echo_short_transcript_needs_exact_match():
    spoken = ["Going to sleep now."]
    # a lone fuzzy word is not enough
    assert not is_self_echo("sweep", spoken, threshold=0.8, min_words=2)[0]
    # an exact word that the bot said is
    assert is_self_echo("sleep", spoken, threshold=0.8, min_words=2)[0]


def test_echo_match_score_is_high_for_prefix_fragment():
    s = "I can't share deeds as I don't have physical access to your files."
    assert echo_match_score(s, "I can't share") == 1.0
    assert echo_match_score(s, "I can't share deep.") > 0.85
    assert echo_match_score(s, "the weather is nice today") < 0.5


# --------------------------------------------------------------------------- #
# SelfEchoWindow                                                               #
# --------------------------------------------------------------------------- #


def test_window_ttl_expires_old_utterances():
    w = SelfEchoWindow(ttl_s=10.0)
    w.add("hello there", now=100.0)
    w.add("something newer", now=108.0)
    assert w.recent(now=109.0) == ["hello there", "something newer"]
    assert w.recent(now=111.0) == ["something newer"]   # first one aged out
    assert w.recent(now=200.0) == []


# --------------------------------------------------------------------------- #
# processors under run_test                                                    #
# --------------------------------------------------------------------------- #


def test_self_echo_filter_drops_echo_keeps_user():
    asyncio.run(_self_echo_filter_drops_echo_keeps_user())


async def _self_echo_filter_drops_echo_keeps_user():
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.tests.utils import run_test

    window = SelfEchoWindow(ttl_s=60.0)
    window.add("I can't share deeds as I don't have physical access to your files.")

    suppressed = []
    flt = build_self_echo_filter(
        window, threshold=0.8, on_suppress=lambda t, s, m: suppressed.append((t, s))
    )

    frames_in = [
        TranscriptionFrame("I can't share deep.", "", "t0", finalized=True),   # echo
        TranscriptionFrame("what's the weather like", "", "t1", finalized=True),  # user
    ]
    down, _up = await run_test(flt, frames_to_send=frames_in)
    kept = [f.text for f in down if isinstance(f, TranscriptionFrame)]
    assert kept == ["what's the weather like"]
    assert suppressed and suppressed[0][0] == "I can't share deep."


def test_echo_text_tap_populates_window():
    asyncio.run(_echo_text_tap_populates_window())


async def _echo_text_tap_populates_window():
    from pipecat.frames.frames import TTSSpeakFrame, TTSTextFrame
    from pipecat.tests.utils import run_test

    window = SelfEchoWindow(ttl_s=60.0)
    tap = build_echo_text_tap(window)
    frames_in = [
        TTSTextFrame("Paris is the capital", aggregated_by="sentence"),
        TTSSpeakFrame("Going to sleep."),
    ]
    down, _up = await run_test(tap, frames_to_send=frames_in)
    # frames pass through untouched
    assert sum(isinstance(f, (TTSTextFrame, TTSSpeakFrame)) for f in down) == 2
    assert window.recent() == ["Paris is the capital", "Going to sleep."]


# --------------------------------------------------------------------------- #
# Deliverable 1 — half-duplex gate (acceptance #2)                             #
# --------------------------------------------------------------------------- #


def _audio_frame(n_samples: int = 320, sr: int = 16000):
    from pipecat.frames.frames import InputAudioRawFrame

    return InputAudioRawFrame(audio=b"\x00\x01" * n_samples, sample_rate=sr, num_channels=1)


def test_gate_mutes_mic_while_bot_speaks_and_unmutes_after_tail():
    asyncio.run(_gate_mutes_mic_while_bot_speaks_and_unmutes_after_tail())


async def _gate_mutes_mic_while_bot_speaks_and_unmutes_after_tail():
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        InputAudioRawFrame,
    )
    from pipecat.tests.utils import run_test
    from pipecat.tests.utils import SleepFrame

    transitions = []
    gate = build_half_duplex_gate(
        tail_ms=120, mode="mute", on_transition=transitions.append
    )

    frames_in = [
        _audio_frame(),                       # before: passes
        BotStartedSpeakingFrame(),
        _audio_frame(), _audio_frame(),       # muted: dropped
        BotStoppedSpeakingFrame(),
        _audio_frame(),                       # still in the decay tail: dropped
        SleepFrame(sleep=0.3),
        _audio_frame(),                       # tail elapsed: passes
    ]
    down, _up = await run_test(gate, frames_to_send=frames_in)

    audio_out = sum(isinstance(f, InputAudioRawFrame) for f in down)
    assert audio_out == 2, f"expected 2 mic frames through, got {audio_out}"
    # logged once per edge, not per frame
    assert transitions == [True, False]
    # the bot-speaking frames themselves are never swallowed
    assert any(isinstance(f, BotStartedSpeakingFrame) for f in down)
    assert any(isinstance(f, BotStoppedSpeakingFrame) for f in down)


def test_gate_never_swallows_the_stop_path_while_muted():
    asyncio.run(_gate_never_swallows_the_stop_path())


async def _gate_never_swallows_the_stop_path():
    from pipecat.frames.frames import BotStartedSpeakingFrame, InterruptionFrame
    from pipecat.tests.utils import run_test

    gate = build_half_duplex_gate(tail_ms=50, mode="mute")
    frames_in = [
        BotStartedSpeakingFrame(),
        InterruptionFrame(),      # ESC / deterministic stop — must pass even while muted
    ]
    down, _up = await run_test(gate, frames_to_send=frames_in)
    assert any(isinstance(f, InterruptionFrame) for f in down)


def test_gate_full_mode_never_mutes():
    asyncio.run(_gate_full_mode_never_mutes())


async def _gate_full_mode_never_mutes():
    from pipecat.frames.frames import BotStartedSpeakingFrame, InputAudioRawFrame
    from pipecat.tests.utils import run_test

    transitions = []
    gate = build_half_duplex_gate(tail_ms=100, mode="full", on_transition=transitions.append)
    frames_in = [BotStartedSpeakingFrame(), _audio_frame(), _audio_frame()]
    down, _up = await run_test(gate, frames_to_send=frames_in)
    assert sum(isinstance(f, InputAudioRawFrame) for f in down) == 2
    assert transitions == []
