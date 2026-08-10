from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import math
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from experiments.breakout_tracker_v5 import PriceBar
from experiments.continuous_high_monitor import (
    ContinuousHighMonitor,
    HighStage,
    MonitorConfig,
    MonitorEventType,
    RiskFlag,
    load_config,
    render_html_report,
    write_feature_csv,
    write_timeline_csv,
)


START = date(2026, 1, 1)


def config(**changes: object) -> MonitorConfig:
    defaults: dict[str, object] = {
        "parameter_version": "TEST-001",
        "high_windows": (3, 5, 8, 12),
        "near_high_window": 5,
        "near_high_pct": 0.05,
        "base_high_window": 3,
        "strengthening_high_window": 5,
        "leader_high_window": 8,
        "high_count_window": 5,
        "strengthening_high_count": 2,
        "volume_average_window": 3,
        "volume_surge_ratio": 1.5,
        "extension_ma_window": 3,
        "extension_pct": 0.10,
        "pullback_pct": 0.05,
        "weakening_high_window": 5,
        "weakening_drawdown_pct": 0.10,
        "acceleration_window": 3,
        "acceleration_high_count": 2,
        "minimum_trading_value": 0.0,
    }
    defaults.update(changes)
    return MonitorConfig(**defaults)  # type: ignore[arg-type]


def bars(
    closes: list[float] | None = None,
    *,
    symbol: str = "SYNTHETIC.TW",
) -> list[PriceBar]:
    values = closes or [10.0, 9.8, 9.5, 9.2, 9.1, 9.4, 9.8, 10.2, 10.6, 11.0, 11.5, 12.0, 13.0, 11.0, 9.5]
    output: list[PriceBar] = []
    for index, close in enumerate(values):
        previous = values[index - 1] if index else close
        open_price = (previous + close) / 2
        volume = 100.0
        if index == 8:
            volume = 200.0
        output.append(
            PriceBar(
                symbol=symbol,
                trade_date=START + timedelta(days=index),
                open=open_price,
                high=max(open_price, close) + 0.1,
                low=min(open_price, close) - 0.1,
                close=close,
                volume=volume,
            )
        )
    return output


class ContinuousHighMonitorTests(unittest.TestCase):
    def test_first_discovery_is_immutable_when_future_bars_are_appended(self) -> None:
        source = bars()
        monitor = ContinuousHighMonitor(config())

        prefix = monitor.run(source[:10])
        full = monitor.run(source)

        self.assertEqual(prefix.first_discovery_date, START + timedelta(days=6))
        self.assertEqual(prefix.first_discovery_close, 9.8)
        self.assertEqual(full.first_discovery_date, prefix.first_discovery_date)
        self.assertEqual(full.first_discovery_close, prefix.first_discovery_close)

    def test_current_close_is_excluded_from_its_new_high_window(self) -> None:
        source = bars([10.0, 9.0, 8.0, 7.0, 6.0, 10.0, 10.01])
        result = ContinuousHighMonitor(config()).run(source)
        snapshots = {item.trade_date: item for item in result.snapshots}

        equal_prior_high = snapshots[START + timedelta(days=5)]
        above_prior_high = snapshots[START + timedelta(days=6)]

        self.assertNotIn(5, equal_prior_high.features.new_high_windows)
        self.assertIn(5, above_prior_high.features.new_high_windows)
        self.assertEqual(above_prior_high.features.prior_high(5), 10.0)

    def test_stage_progression_keeps_simultaneous_high_windows(self) -> None:
        result = ContinuousHighMonitor(config()).run(bars())
        by_date = {item.trade_date: item for item in result.snapshots}

        self.assertEqual(by_date[START + timedelta(days=6)].stage, HighStage.EMERGING)
        self.assertEqual(
            by_date[START + timedelta(days=7)].stage, HighStage.STRENGTHENING
        )
        leader = by_date[START + timedelta(days=8)]
        self.assertEqual(leader.stage, HighStage.LEADER)
        self.assertEqual(leader.features.new_high_windows, (3, 5, 8))
        self.assertIn(RiskFlag.VOLUME_SURGE, leader.risk_flags)
        self.assertIn(RiskFlag.ACCELERATING, leader.risk_flags)
        self.assertEqual(by_date[START + timedelta(days=14)].stage, HighStage.WEAKENING)

    def test_high_stage_persists_inside_near_high_band(self) -> None:
        source = bars([10.0, 9.8, 9.5, 9.2, 9.1, 9.4, 9.8, 10.2, 10.6, 10.55])
        result = ContinuousHighMonitor(config()).run(source)
        by_date = {item.trade_date: item for item in result.snapshots}

        self.assertEqual(by_date[START + timedelta(days=8)].stage, HighStage.LEADER)
        self.assertEqual(by_date[START + timedelta(days=9)].stage, HighStage.LEADER)

    def test_monotonic_rise_is_detected_without_a_pivot_dependency(self) -> None:
        source = bars([10.0 + index * 0.2 for index in range(15)])
        result = ContinuousHighMonitor(config()).run(source)

        self.assertIsNotNone(result.first_discovery_date)
        self.assertTrue(
            any(item.stage is HighStage.LEADER for item in result.snapshots)
        )
        self.assertTrue(
            any(
                event.event_type is MonitorEventType.NEW_HIGH
                and event.detail == "12D_CLOSE_HIGH"
                for event in result.events
            )
        )

    def test_declining_stock_is_not_first_discovered_as_weakening(self) -> None:
        source = bars([20.0 - index * 0.5 for index in range(15)])
        result = ContinuousHighMonitor(config()).run(source)

        self.assertIsNone(result.first_discovery_date)
        self.assertEqual(result.snapshots, ())
        self.assertEqual(result.events, ())
        self.assertEqual(len(result.feature_rows), len(source))

    def test_prefix_replay_matches_full_replay(self) -> None:
        source = bars()
        monitor = ContinuousHighMonitor(config())
        full = monitor.run(source)

        for length in range(1, len(source) + 1):
            prefix = monitor.run(source[:length])
            cutoff = source[length - 1].trade_date
            expected_snapshots = tuple(
                item for item in full.snapshots if item.trade_date <= cutoff
            )
            expected_events = tuple(item for item in full.events if item.trade_date <= cutoff)
            self.assertEqual(prefix.snapshots, expected_snapshots)
            self.assertEqual(prefix.events, expected_events)
            self.assertEqual(prefix.feature_rows, full.feature_rows[:length])

    def test_event_ids_are_stable_and_unique(self) -> None:
        monitor = ContinuousHighMonitor(config())
        first = monitor.run(bars())
        second = monitor.run(bars())

        self.assertEqual(first.events, second.events)
        event_ids = [item.event_id for item in first.events]
        self.assertEqual(len(event_ids), len(set(event_ids)))

    def test_event_ids_and_timeline_are_scoped_to_parameter_identity(self) -> None:
        source = bars()
        first_config = config(parameter_version="TEST-001", strengthening_high_count=2)
        second_config = config(parameter_version="TEST-002", strengthening_high_count=3)
        first = ContinuousHighMonitor(first_config).run(source)
        second = ContinuousHighMonitor(second_config).run(source)

        first_ids = {item.event_id for item in first.events}
        second_ids = {item.event_id for item in second.events}
        self.assertTrue(first_ids)
        self.assertTrue(second_ids)
        self.assertTrue(first_ids.isdisjoint(second_ids))

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "timeline.csv"
            write_timeline_csv(first, target)
            rows = target.read_text(encoding="utf-8").splitlines()
        header = rows[0].split(",")
        first_row = rows[1].split(",")
        self.assertEqual(header[:3], ["parameter_version", "parameter_hash", "event_id"])
        self.assertEqual(first_row[header.index("parameter_version")], first.parameter_version)
        self.assertEqual(first_row[header.index("parameter_hash")], first.parameter_hash)

    def test_invalid_config_and_unknown_json_keys_fail_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly ascending"):
            config(high_windows=(5, 3, 8, 12))
        with self.assertRaisesRegex(ValueError, "missing"):
            config(high_windows=(3, 5, 8, 10), leader_high_window=12)
        with self.assertRaisesRegex(ValueError, "base <= strengthening <= leader"):
            config(strengthening_high_window=8, leader_high_window=5)
        with self.assertRaisesRegex(ValueError, "finite"):
            config(extension_pct=math.nan)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            config(acceleration_high_count=4)
        with self.assertRaisesRegex(ValueError, "unknown"):
            MonitorConfig.from_mapping({"surprise_parameter": 1})

    def test_config_file_round_trip_preserves_hash(self) -> None:
        selected = config()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(selected.canonical_json(), encoding="utf-8")
            loaded = load_config(path)
        self.assertEqual(loaded, selected)
        self.assertEqual(loaded.parameter_hash, selected.parameter_hash)
        self.assertEqual(len(loaded.parameter_hash), 64)

    def test_bad_bar_order_and_mixed_symbols_fail_loudly(self) -> None:
        source = bars()
        with self.assertRaisesRegex(ValueError, "strictly ascending"):
            ContinuousHighMonitor(config()).run([source[1], source[0]])
        mixed = source[:2] + [replace(source[2], symbol="OTHER.TW")]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            ContinuousHighMonitor(config()).run(mixed)

    def test_boolean_and_string_ohlcv_values_fail_with_value_error(self) -> None:
        source = bars()
        boolean_bar = replace(
            source[0], open=True, high=True, low=True, close=True, volume=True
        )
        with self.assertRaisesRegex(ValueError, "invalid OHLC"):
            ContinuousHighMonitor(config()).run([boolean_bar])

        string_price = replace(source[0], close="10.0")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "invalid OHLC"):
            ContinuousHighMonitor(config()).run([string_price])

        string_volume = replace(source[0], volume="100")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "invalid volume"):
            ContinuousHighMonitor(config()).run([string_volume])

    def test_html_svg_and_timeline_csv_are_standalone_and_escaped(self) -> None:
        source = bars(symbol="<SYNTHETIC&>")
        selected = config()
        result = ContinuousHighMonitor(selected).run(source)
        report = render_html_report(bars=source, result=result, config=selected)

        self.assertIn("<svg", report)
        self.assertIn("系統首次發現", report)
        self.assertIn("關鍵事件時間線", report)
        self.assertIn("完整的每日新高事件", report)
        self.assertIn(selected.parameter_hash, report)
        self.assertIn("&lt;SYNTHETIC&amp;&gt;", report)
        self.assertNotIn("<SYNTHETIC&>", report)
        self.assertNotIn("nan", report.lower())
        svg_start = report.index("<svg")
        svg_end = report.index("</svg>", svg_start) + len("</svg>")
        ElementTree.fromstring(report[svg_start:svg_end])

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "timeline.csv"
            write_timeline_csv(result, target)
            content = target.read_text(encoding="utf-8")
        self.assertIn("event_id,symbol,trade_date,event_type", content)
        self.assertIn("DISCOVERED", content)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "features.csv"
            write_feature_csv(result, selected, target)
            features = target.read_text(encoding="utf-8")
        self.assertIn("parameter_version,parameter_hash,symbol,trade_date", features)
        self.assertIn("prior_high_3d,new_high_3d", features)
        self.assertEqual(len(features.splitlines()), len(source) + 1)
        first_data_row = features.splitlines()[1].split(",")
        header = features.splitlines()[0].split(",")
        self.assertEqual(first_data_row[header.index("new_high_3d")], "")

        with self.assertRaisesRegex(ValueError, "parameter hash"):
            render_html_report(
                bars=source,
                result=result,
                config=replace(selected, near_high_pct=0.04),
            )
        with self.assertRaisesRegex(ValueError, "feature rows"):
            render_html_report(
                bars=source[:-1],
                result=result,
                config=selected,
            )
        inconsistent_volume = list(source)
        inconsistent_volume[8] = replace(
            inconsistent_volume[8], volume=inconsistent_volume[8].volume + 1.0
        )
        with self.assertRaisesRegex(ValueError, "volume"):
            render_html_report(
                bars=inconsistent_volume,
                result=result,
                config=selected,
            )


if __name__ == "__main__":
    unittest.main()
