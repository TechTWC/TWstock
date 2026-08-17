from __future__ import annotations

from datetime import date, timedelta
import unittest

from experiments.moving_average_state import MovingAverageStateEngine
from experiments.seven_state_radar import (
    RadarState,
    RadarStateConfig,
    SevenStateRadarEngine,
)
from twstock_data.models import MarketBar


def _bars(closes: list[float]) -> tuple[MarketBar, ...]:
    first = date(2025, 1, 1)
    return tuple(
        MarketBar(
            symbol="2330.TW",
            trade_date=first + timedelta(days=index),
            open=close,
            high=close + 1,
            low=max(0.01, close - 1),
            close=close,
            volume=1_000_000,
            official_traded_value_twd=close * 1_000_000,
        )
        for index, close in enumerate(closes)
    )


class SevenStateRadarTests(unittest.TestCase):
    def test_rules_reach_all_seven_mutually_exclusive_states(self) -> None:
        normal = [100.0] * 75 + [101.0 + index * 0.8 for index in range(40)]
        normal.extend([132.0 - index * 3.0 for index in range(15)])
        fast = [100.0] * 75 + [104.0 + index * 2.0 for index in range(25)]
        engine = SevenStateRadarEngine()
        normal_result = engine.run(MovingAverageStateEngine().run(_bars(normal)))
        fast_result = engine.run(MovingAverageStateEngine().run(_bars(fast)))
        observed = {item.state for item in normal_result.observations}
        observed.update(item.state for item in fast_result.observations)

        self.assertEqual(observed, set(RadarState))
        self.assertTrue(
            any(
                event.detail == "BASE->TURNING_UP"
                for event in normal_result.events
            )
        )
        self.assertTrue(
            any(item.state is RadarState.EXTENDED for item in fast_result.observations)
        )

    def test_persistence_and_extension_are_transparent_rules(self) -> None:
        closes = [100.0] * 75 + [101.0 + index * 0.8 for index in range(40)]
        result = SevenStateRadarEngine(
            RadarStateConfig(persistence_bars=10, extended_distance_to_ma20_pct=0.12)
        ).run(MovingAverageStateEngine().run(_bars(closes)))
        persistent = next(
            item for item in result.observations if item.state is RadarState.PERSISTING
        )

        self.assertGreaterEqual(persistent.consecutive_confirmed_bars, 10)
        self.assertLess(persistent.distance_to_ma20_pct, 0.12)
        self.assertIn("MA_BASELINE_ONLY", persistent.limitations)
        self.assertIn(
            "THRESHOLDS_NOT_YET_CALIBRATED_ON_TAIWAN_EQUITIES",
            persistent.limitations,
        )

    def test_confirmed_trend_does_not_reset_on_temporary_slope_slowdown(self) -> None:
        closes = [100.0] * 75 + [101.0 + index * 0.8 for index in range(40)]
        closes.extend([132.0 - index * 3.0 for index in range(15)])
        result = SevenStateRadarEngine().run(
            MovingAverageStateEngine().run(_bars(closes))
        )

        self.assertFalse(
            any(
                event.detail == "PERSISTING->TURNING_UP"
                for event in result.events
            )
        )
        self.assertTrue(
            any(
                item.state is RadarState.PERSISTING
                and item.ma_state.value == "TURNING_UP"
                for item in result.observations
            )
        )

    def test_prefix_replay_is_point_in_time_stable(self) -> None:
        bars = _bars([100.0] * 75 + [101.0 + index * 0.8 for index in range(40)])
        ma_engine = MovingAverageStateEngine()
        radar_engine = SevenStateRadarEngine()
        full = radar_engine.run(ma_engine.run(bars))
        for cutoff in (65, 80, 95, 110):
            prefix = radar_engine.run(ma_engine.run(bars[:cutoff]))
            self.assertEqual(prefix.observations, full.observations[:cutoff])
            self.assertEqual(
                prefix.events,
                tuple(
                    event
                    for event in full.events
                    if event.trade_date <= bars[cutoff - 1].trade_date
                ),
            )

    def test_invalid_config_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 2"):
            RadarStateConfig(persistence_bars=1)
        with self.assertRaisesRegex(ValueError, r"in \(0, 1\)"):
            RadarStateConfig(extended_distance_to_ma20_pct=1.0)


if __name__ == "__main__":
    unittest.main()
