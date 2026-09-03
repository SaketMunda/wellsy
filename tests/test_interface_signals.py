"""SignalBus semantics — depth-1 latest-wins, staleness, decay to default."""

from __future__ import annotations

from engine.interface.signals import Channel, SignalBus


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_channel_latest_wins():
    clk = FakeClock()
    ch: Channel[float] = Channel("x", stale_after=1.0, clock=clk)
    ch.push(0.1)
    ch.push(0.2)
    ch.push(0.3)
    assert ch.latest().value == 0.3  # no backlog, only the newest


def test_channel_goes_stale_and_decays_to_default():
    clk = FakeClock()
    ch: Channel[float] = Channel("amp", stale_after=0.12, clock=clk)
    ch.push(0.9)
    assert ch.fresh() and ch.value_or(0.0) == 0.9
    clk.t += 0.2  # older than stale_after
    assert not ch.fresh()
    assert ch.value_or(0.0) == 0.0


def test_level_latch_never_stale():
    clk = FakeClock()
    ch: Channel[bool] = Channel("wake", stale_after=None, clock=clk)
    ch.push(True)
    clk.t += 10_000
    assert ch.fresh()
    assert ch.value_or(False) is True


def test_clear_removes_the_sample():
    ch: Channel[float] = Channel("amp", stale_after=1.0, clock=FakeClock())
    ch.push(0.5)
    ch.clear()
    assert ch.latest() is None
    assert ch.value_or(0.0) == 0.0


def test_bus_push_helpers_route_to_the_right_channel():
    clk = FakeClock()
    bus = SignalBus(clock=clk)
    bus.push_vad_amplitude(0.4)
    bus.push_tts_amplitude(0.6)
    bus.set_agent_phase("acting")
    bus.set_approval_pending(True)
    bus.set_wake(True)
    assert bus.channel("vad_amplitude").value_or(0.0) == 0.4
    assert bus.channel("tts_amplitude").value_or(0.0) == 0.6
    assert bus.channel("agent_phase").value_or("idle") == "acting"
    assert bus.channel("approval").value_or(None) == "pending"
    assert bus.channel("wake").value_or(False) is True
    bus.set_approval_pending(False)
    assert bus.channel("approval").latest() is None


def test_unknown_channel_is_a_keyerror_not_a_silent_noop():
    bus = SignalBus()
    try:
        bus.channel("typo_here")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for an undeclared channel")
