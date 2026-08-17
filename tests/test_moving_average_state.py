from __future__ import annotations

import csv
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from experiments.moving_average_state import (
    LongTermContext,
    MAStateConfig,
    MovingAverageStateEngine,
    TrendState,
    render_html_report,
    write_outputs,
)
from scripts.run_ma_state_baseline import run as run_ma_state_baseline
from twstock_data.models import MarketBar


def _bars(closes: list[float], symbol: str = "2330.TW") -> tuple[MarketBar, ...]:
    first = date(2025, 1, 1)
    return tuple(
        MarketBar(
            symbol=symbol,
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


def _manifest(symbol: str = "2330.TW") -> dict[str, object]:
    return {
        "canonical_symbol": symbol,
        "selected_source": "TWSE",
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_actions_applied": False,
        "dataset_hash": symbol.replace(".", "") * 4,
    }


class MovingAverageStateTests(unittest.TestCase):
    def test_flat_rising_and_falling_series_reach_expected_states(self) -> None:
        engine = MovingAverageStateEngine()
        flat = engine.run(_bars([100.0] * 90))
        rising = engine.run(_bars([80.0 + index for index in range(100)]))
        falling = engine.run(_bars([200.0 - index for index in range(100)]))

        self.assertEqual(flat.observations[-1].state, TrendState.BASE)
        self.assertEqual(rising.observations[-1].state, TrendState.UPTREND)
        self.assertEqual(falling.observations[-1].state, TrendState.DOWNTREND)
        self.assertIn(
            "FULL_BULLISH_ALIGNMENT",
            rising.observations[-1].structural_labels,
        )
        self.assertIn(
            "FULL_BEARISH_ALIGNMENT",
            falling.observations[-1].structural_labels,
        )
        self.assertEqual(
            rising.observations[-1].long_term_context,
            LongTermContext.INSUFFICIENT_HISTORY,
        )

    def test_long_term_context_does_not_delay_core_state(self) -> None:
        result = MovingAverageStateEngine().run(
            _bars([80.0 + index for index in range(100)])
        )

        self.assertEqual(result.observations[-1].state, TrendState.UPTREND)
        self.assertEqual(
            result.observations[-1].long_term_context,
            LongTermContext.INSUFFICIENT_HISTORY,
        )

    def test_long_term_bull_and_bear_are_classified_after_full_history(self) -> None:
        engine = MovingAverageStateEngine()
        rising = engine.run(_bars([100.0 + index for index in range(300)]))
        falling = engine.run(_bars([500.0 - index for index in range(300)]))

        self.assertEqual(
            rising.observations[-1].long_term_context,
            LongTermContext.LONG_TERM_BULL,
        )
        self.assertEqual(
            falling.observations[-1].long_term_context,
            LongTermContext.LONG_TERM_BEAR,
        )
        self.assertIsNotNone(rising.observations[-1].ma_global_long)
        self.assertIn(
            "PRICE_ABOVE_MA120_ABOVE_MA240",
            rising.observations[-1].long_term_support_evidence,
        )

    def test_base_to_uptrend_keeps_early_turning_up_observations(self) -> None:
        closes = [100.0] * 75 + [101.0 + index * 0.8 for index in range(25)]
        result = MovingAverageStateEngine().run(_bars(closes))
        states = [item.state for item in result.observations]

        self.assertIn(TrendState.BASE, states)
        self.assertIn(TrendState.TURNING_UP, states)
        self.assertEqual(states[-1], TrendState.UPTREND)
        transitions = [event.current_state for event in result.events]
        self.assertIn(TrendState.TURNING_UP, transitions)
        self.assertIn(TrendState.UPTREND, transitions)

    def test_price_jump_is_not_hidden_by_still_compressed_averages(self) -> None:
        closes = [100.0] * 75 + [104.0]
        result = MovingAverageStateEngine().run(_bars(closes))

        self.assertNotEqual(result.observations[-1].state, TrendState.BASE)

    def test_turning_down_is_distinct_from_confirmed_downtrend(self) -> None:
        closes = [80.0 + index for index in range(90)]
        closes.extend([closes[-1] - (index + 1) * 2 for index in range(18)])
        result = MovingAverageStateEngine().run(_bars(closes))
        tail_states = [item.state for item in result.observations[-20:]]

        self.assertIn(TrendState.TURNING_DOWN, tail_states)
        self.assertEqual(tail_states[-1], TrendState.TURNING_DOWN)

    def test_prefix_replay_is_point_in_time_stable(self) -> None:
        bars = _bars([100.0] * 70 + [100.0 + index * 0.7 for index in range(40)])
        engine = MovingAverageStateEngine()
        full = engine.run(bars)
        for cutoff in (65, 75, 90, 105):
            prefix = engine.run(bars[:cutoff])
            self.assertEqual(prefix.observations, full.observations[:cutoff])
            self.assertEqual(prefix.events, tuple(event for event in full.events if event.trade_date <= bars[cutoff - 1].trade_date))

    def test_config_is_bound_and_invalid_windows_fail(self) -> None:
        first = MAStateConfig()
        second = MAStateConfig(base_ma_spread_tolerance_pct=0.04)
        self.assertNotEqual(first.parameter_hash, second.parameter_hash)
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            MAStateConfig(fast_window=10, short_window=5)
        with self.assertRaisesRegex(ValueError, "finite"):
            MAStateConfig(base_flat_slope_tolerance_pct=float("nan"))

    def test_report_has_no_rank_or_score_and_keeps_warnings_and_charts(self) -> None:
        bars = _bars([100.0] * 250 + [100.0 + index for index in range(50)])
        result = MovingAverageStateEngine().run(bars)
        html = render_html_report([result], {result.symbol: bars})

        self.assertIn("均線趨勢狀態基準 v0.2", html)
        self.assertIn('id="ma-state-chart-2330.TW"', html)
        self.assertIn('id="ma-long-chart-2330.TW"', html)
        self.assertIn('data-series="ma_fast"', html)
        self.assertIn('data-series="ma_half_year"', html)
        self.assertIn("MA200（比較）", html)
        self.assertIn("長期背景", html)
        self.assertIn("支持證據", html)
        self.assertIn("反對證據", html)
        self.assertIn("UNVERIFIED", html)
        self.assertIn("PROHIBITED", html)
        self.assertIn("沒有分數", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("候選排名", html)

    def test_writer_outputs_machine_readable_state_and_timeline(self) -> None:
        bars = _bars([100.0] * 70 + [100.0 + index for index in range(30)])
        result = MovingAverageStateEngine().run(bars)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_outputs(
                [result],
                {result.symbol: bars},
                output,
                source_manifests={result.symbol: _manifest()},
            )
            names = {path.name for path in output.iterdir()}
            manifest = json.loads((output / "ma_state_manifest.json").read_text(encoding="utf-8"))
            with (output / "ma_state_latest.csv").open(encoding="utf-8") as handle:
                latest = list(csv.DictReader(handle))

        self.assertEqual(
            names,
            {
                "ma_state_latest.csv",
                "ma_state_timeline.csv",
                "ma_state_manifest.json",
                "ma_state_report.html",
            },
        )
        self.assertEqual(manifest["ranking"], "NONE")
        self.assertEqual(manifest["score"], "NONE")
        self.assertEqual(manifest["corporate_action_status"], "UNVERIFIED")
        self.assertEqual(latest[0]["state"], TrendState.UPTREND.value)
        self.assertEqual(
            latest[0]["long_term_context"],
            LongTermContext.INSUFFICIENT_HISTORY.value,
        )
        self.assertEqual(latest[0]["investment_use"], "PROHIBITED")

    def test_offline_cli_reads_preserved_watchlist_evidence(self) -> None:
        bars = _bars([100.0] * 70 + [100.0 + index for index in range(30)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            symbol_dir = root / "input" / "symbols" / "2330"
            symbol_dir.mkdir(parents=True)
            with (symbol_dir / "market_bars.csv").open("w", encoding="utf-8", newline="") as handle:
                fields = ("symbol", "trade_date", "open", "high", "low", "close", "volume", "official_traded_value_twd")
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
            result = run_ma_state_baseline(
                ["--input-root", str(root / "input"), "--output-dir", str(root / "output")]
            )
            html = (root / "output" / "ma_state_report.html").read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertIn("2330.TW", html)


if __name__ == "__main__":
    unittest.main()
