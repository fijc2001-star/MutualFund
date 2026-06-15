from __future__ import annotations

from mutualfund.realtime.demo import DemoFeed


def test_snapshot_shape_and_monotonic_time() -> None:
    feed = DemoFeed("AAPL", seed=42)
    bars = feed.snapshot(60)
    assert len(bars) == 60
    times = [b.time for b in bars]
    assert times == sorted(times)
    assert len(set(times)) == 60  # strictly increasing
    assert all(b.high >= b.open and b.high >= b.close for b in bars)
    assert all(b.low <= b.open and b.low <= b.close for b in bars)


def test_bars_carry_positive_volume() -> None:
    feed = DemoFeed("AAPL", seed=42)
    bars = feed.snapshot(30)
    assert all(b.volume > 0 for b in bars)


def test_signals_are_throttled_and_valid() -> None:
    feed = DemoFeed("TSLA", seed=7)
    sides: set[str] = set()
    last_signal_index = -10
    for i in range(300):
        bar = feed.next_bar()
        sig = feed.maybe_signal(bar)
        if sig is not None:
            assert sig.side in {"buy", "sell"}
            assert sig.price == bar.close
            assert i - last_signal_index >= 4  # throttled
            last_signal_index = i
            sides.add(sig.side)
    assert sides  # produced at least one signal over 300 bars
