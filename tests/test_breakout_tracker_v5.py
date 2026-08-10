from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import unittest

from experiments.breakout_tracker_v5 import (
    BreakoutState,
    BreakoutTracker,
    PriceBar,
    TrackerConfig,
)


START = date(2026, 1, 1)


def bar(
    offset: int,
    *,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
    symbol: str = "SYNTHETIC.TW",
) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        trade_date=START + timedelta(days=offset),
        open=(low + close) / 2,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def lifecycle_bars() -> list[PriceBar]:
    return [
        bar(0, high=9.0, low=8.5, close=8.8),
        bar(1, high=10.0, low=9.0, close=9.7),
        bar(2, high=12.0, low=10.0, close=11.5),  # future Pivot
        bar(3, high=11.8, low=11.0, close=11.4),
        bar(4, high=11.9, low=11.1, close=11.6),  # Pivot known here
        bar(5, high=12.4, low=12.2, close=12.3, volume=120),
        bar(6, high=12.7, low=12.3, close=12.5, volume=110),
        bar(7, high=12.3, low=12.05, close=12.2, volume=105),
        bar(8, high=14.2, low=13.9, close=14.0, volume=130),
        bar(9, high=11.8, low=11.4, close=11.5, volume=140),
    ]


class BreakoutTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TrackerConfig(
            pivot_lookback=3,
            pivot_confirmation_bars=2,
            volume_lookback=3,
            retest_band_pct=0.01,
            failure_pct=0.03,
            extension_pct=0.15,
            max_tracking_bars=20,
        )

    def test_pivot_is_not_emitted_before_confirmation(self) -> None:
        bars = lifecycle_bars()
        tracker = BreakoutTracker(self.config)

        self.assertEqual(tracker.run(bars[:4]), ())
        first = tracker.run(bars[:5])

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].state, BreakoutState.SETUP)
        self.assertEqual(first[0].trade_date, bars[4].trade_date)
        self.assertEqual(first[0].pivot_date, bars[2].trade_date)
        self.assertEqual(first[0].pivot_price, 12.0)

    def test_full_lifecycle_and_frozen_pivot(self) -> None:
        snapshots = BreakoutTracker(self.config).run(lifecycle_bars())

        self.assertEqual(
            [snapshot.state for snapshot in snapshots],
            [
                BreakoutState.SETUP,
                BreakoutState.NEW_TRIGGER,
                BreakoutState.CONFIRMED,
                BreakoutState.RETEST,
                BreakoutState.EXTENDED,
                BreakoutState.FAILED,
            ],
        )
        self.assertEqual(
            sum(s.state is BreakoutState.NEW_TRIGGER for s in snapshots), 1
        )
        self.assertEqual({s.pivot_price for s in snapshots}, {12.0})
        self.assertEqual({s.pivot_date for s in snapshots}, {START + timedelta(days=2)})
        self.assertEqual(
            {s.breakout_date for s in snapshots[1:]},
            {START + timedelta(days=5)},
        )

    def test_prefix_replay_matches_full_replay(self) -> None:
        bars = lifecycle_bars()
        tracker = BreakoutTracker(self.config)
        full = tracker.run(bars)

        for length in range(1, len(bars) + 1):
            prefix = tracker.run(bars[:length])
            expected = tuple(
                snapshot
                for snapshot in full
                if snapshot.trade_date <= bars[length - 1].trade_date
            )
            self.assertEqual(prefix, expected)

    def test_optional_volume_gate_uses_prior_volume_only(self) -> None:
        config = replace(self.config, min_breakout_volume_ratio=1.5)
        bars = lifecycle_bars()
        bars[5] = bar(5, high=12.4, low=12.2, close=12.3, volume=100)
        bars[6] = bar(6, high=12.7, low=12.3, close=12.5, volume=200)

        snapshots = BreakoutTracker(config).run(bars[:7])

        self.assertEqual(
            [snapshot.state for snapshot in snapshots],
            [BreakoutState.SETUP, BreakoutState.SETUP, BreakoutState.NEW_TRIGGER],
        )
        self.assertAlmostEqual(snapshots[-1].volume_ratio or 0.0, 2.0)
        self.assertEqual(snapshots[-1].breakout_date, bars[6].trade_date)

    def test_invalid_order_and_mixed_symbol_fail_loudly(self) -> None:
        bars = lifecycle_bars()
        bad_order = [bars[1], bars[0]]
        with self.assertRaisesRegex(ValueError, "strictly ascending"):
            BreakoutTracker(self.config).run(bad_order)

        mixed = [bars[0], replace(bars[1], symbol="OTHER.TW")]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            BreakoutTracker(self.config).run(mixed)

    def test_invalid_ohlc_fails_loudly(self) -> None:
        invalid = replace(lifecycle_bars()[0], high=8.0)
        with self.assertRaisesRegex(ValueError, "low above high"):
            BreakoutTracker(self.config).run([invalid])

    def test_invalid_config_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "pivot_lookback"):
            TrackerConfig(pivot_lookback=1)
        with self.assertRaisesRegex(ValueError, "failure_pct"):
            TrackerConfig(failure_pct=1.0)
        with self.assertRaisesRegex(ValueError, "max_setup_bars"):
            TrackerConfig(pivot_confirmation_bars=5, max_setup_bars=4)


if __name__ == "__main__":
    unittest.main()
