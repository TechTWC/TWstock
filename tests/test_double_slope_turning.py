from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import math
from pathlib import Path
import tempfile
import unittest

from experiments.double_slope_turning import (
    DoubleSlopeConfig,
    DoubleSlopeTurningEngine,
    SlopeState,
    compare_with_ma_baseline,
    render_comparison_html,
)
from experiments.moving_average_state import MAStateConfig, MovingAverageStateEngine
from scripts.run_double_slope_comparison import RESEARCH_SOURCE_URL, run
from twstock_data.models import MarketBar


def _bars(closes: list[float], symbol: str = "2330.TW") -> tuple[MarketBar, ...]:
    first = date(2024, 1, 1)
    return tuple(
        MarketBar(
            symbol=symbol,
            trade_date=first + timedelta(days=index),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=1_000_000,
            official_traded_value_twd=close * 1_000_000,
        )
        for index, close in enumerate(closes)
    )


def _manifest(symbol: str = "2330.TW") -> dict[str, object]:
    return {
        "canonical_symbol": symbol,
        "selected_source": "TWSE",
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_actions_applied": False,
        "dataset_hash": symbol.replace(".", "") * 4,
    }


def _flat_then_rise() -> list[float]:
    return [100.0] * 60 + [100.0 * math.exp(0.008 * index) for index in range(1, 81)]


class DoubleSlopeTurningTests(unittest.TestCase):
    def test_flat_to_rise_emits_one_confirmed_up_event_per_candidate_run(self) -> None:
        result = DoubleSlopeTurningEngine().run(_bars(_flat_then_rise()))
        up_events = [event for event in result.events if event.direction == "UP"]

        self.assertTrue(up_events)
        first = up_events[0]
        observation = next(
            item for item in result.observations if item.trade_date == first.trade_date
        )
        self.assertEqual(observation.state, SlopeState.TURNING_UP)
        self.assertEqual(observation.consecutive_confirmation_count, 2)
        self.assertLessEqual(first.prior_slope_pct, 0.0005)
        self.assertGreater(first.recent_slope_pct, 0.0005)
        self.assertGreaterEqual(first.z_score, 1.96)

    def test_scale_invariance_and_prefix_replay(self) -> None:
        closes = _flat_then_rise()
        engine = DoubleSlopeTurningEngine()
        original = engine.run(_bars(closes))
        scaled = engine.run(_bars([value * 10 for value in closes]))

        self.assertEqual(
            [item.state for item in original.observations],
            [item.state for item in scaled.observations],
        )
        for first, second in zip(original.observations, scaled.observations, strict=True):
            if first.recent_slope_pct is not None:
                self.assertAlmostEqual(first.recent_slope_pct, second.recent_slope_pct)
        for cutoff in (45, 70, 100, 130):
            prefix = engine.run(_bars(closes)[:cutoff])
            self.assertEqual(prefix.observations, original.observations[:cutoff])
            self.assertEqual(
                prefix.events,
                tuple(
                    event
                    for event in original.events
                    if event.trade_date <= prefix.observations[-1].trade_date
                ),
            )

    def test_insufficient_history_and_invalid_config_fail_cleanly(self) -> None:
        result = DoubleSlopeTurningEngine().run(_bars([100.0] * 39))
        self.assertTrue(
            all(
                item.state is SlopeState.INSUFFICIENT_HISTORY
                for item in result.observations
            )
        )
        with self.assertRaisesRegex(ValueError, "at least 3"):
            DoubleSlopeConfig(prior_window=2)
        with self.assertRaisesRegex(ValueError, "positive"):
            DoubleSlopeConfig(z_threshold=0)
        with self.assertRaisesRegex(ValueError, "finite"):
            DoubleSlopeConfig(slope_flat_tolerance_pct=float("nan"))

    def test_comparison_keeps_future_outcomes_separate_from_detection(self) -> None:
        bars = _bars(_flat_then_rise() + [190.0] * 40)
        double_slope = DoubleSlopeTurningEngine().run(bars)
        ma_result = MovingAverageStateEngine().run(bars)
        comparison = compare_with_ma_baseline(
            [double_slope], [ma_result], {"2330.TW": bars}
        )

        self.assertTrue(comparison.events)
        self.assertTrue(comparison.outcomes)
        self.assertTrue(
            any(item.evaluation_status == "EVALUATED" for item in comparison.outcomes)
        )
        self.assertEqual(
            [item.trade_date for item in double_slope.events],
            [
                item.trade_date
                for item in DoubleSlopeTurningEngine().run(bars).events
            ],
        )

    def test_report_is_standalone_and_explains_non_replication(self) -> None:
        bars = _bars(_flat_then_rise() + [190.0] * 40)
        double_slope = DoubleSlopeTurningEngine().run(bars)
        ma_result = MovingAverageStateEngine().run(bars)
        comparison = compare_with_ma_baseline(
            [double_slope], [ma_result], {"2330.TW": bars}
        )
        manifest = {
            "report_id": "TEST",
        }
        html = render_comparison_html(
            [double_slope],
            [ma_result],
            comparison,
            {"2330.TW": bars},
            manifest,
            RESEARCH_SOURCE_URL,
        )

        self.assertIn("這不是論文的精確重製", html)
        self.assertIn('id="double-slope-comparison-chart-2330.TW"', html)
        self.assertIn('data-method="DOUBLE_SLOPE"', html)
        self.assertIn('data-method="MA_BASELINE"', html)
        self.assertIn("NO_FOLLOW_THROUGH_20D", html)
        self.assertIn("UNVERIFIED", html)
        self.assertIn("PROHIBITED", html)
        self.assertIn("沒有分數", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("候選排名", html)

    def test_writer_and_offline_cli_produce_complete_contract(self) -> None:
        bars = _bars(_flat_then_rise() + [190.0] * 160)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            symbol_dir = root / "input" / "symbols" / "2330"
            symbol_dir.mkdir(parents=True)
            with (symbol_dir / "market_bars.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                fields = (
                    "symbol", "trade_date", "open", "high", "low", "close",
                    "volume", "official_traded_value_twd",
                )
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for bar in bars:
                    writer.writerow({
                        "symbol": bar.symbol,
                        "trade_date": bar.trade_date.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "official_traded_value_twd": bar.official_traded_value_twd,
                    })
            (symbol_dir / "dataset_manifest.json").write_text(
                json.dumps(_manifest()), encoding="utf-8"
            )
            result = run([
                "--input-root", str(root / "input"),
                "--output-dir", str(root / "output"),
            ])
            names = {path.name for path in (root / "output").iterdir()}
            manifest = json.loads(
                (root / "output" / "double_slope_comparison_manifest.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            names,
            {
                "double_slope_latest.csv",
                "double_slope_events.csv",
                "method_event_outcomes.csv",
                "matched_detections.csv",
                "double_slope_comparison_manifest.json",
                "double_slope_comparison_report.html",
            },
        )
        self.assertFalse(manifest["exact_paper_replication"])
        self.assertEqual(manifest["ranking"], "NONE")
        self.assertEqual(manifest["score"], "NONE")


if __name__ == "__main__":
    unittest.main()
