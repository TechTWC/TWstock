from __future__ import annotations

import csv
from dataclasses import replace
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.watchlist_scanner import (
    load_watchlist,
    scan_watchlist,
    write_watchlist_outputs,
)
from scripts.run_watchlist_scanner import run as run_watchlist_scanner
from twstock_data.dataset import (
    build_research_dataset,
    fetch_official_research_dataset,
)
from twstock_data.errors import DataValidationError, SourceUnavailableError
from twstock_data.models import (
    MarketDataRecord,
    ReconciliationResult,
    SourceState,
    SourceTier,
)


START = "2024-01-01"
END = "2026-12-31"


def _dataset(
    symbol: str,
    *,
    count: int = 260,
    start_offset: int = 0,
    last_volume_multiplier: float = 1.0,
):
    records: list[MarketDataRecord] = []
    first = date(2025, 1, 1) + timedelta(days=start_offset)
    for index in range(count):
        trade_date = first + timedelta(days=index)
        if index < 19:
            close = 100.0
            high = 101.0
            low = 99.0
            open_price = 100.0
        elif index == 19:
            close = 108.0
            high = 110.0
            low = 99.0
            open_price = 100.0
        elif index < 23:
            close = 107.0
            high = 109.0
            low = 106.0
            open_price = 107.0
        else:
            close = 111.0 + (index - 23) * 0.2
            high = close + 1.0
            low = close - 1.0
            open_price = close - 0.2
        volume = 1_000_000
        if index == count - 1:
            volume = int(volume * last_volume_multiplier)
        records.append(
            MarketDataRecord(
                source="TWSE",
                source_tier=SourceTier.PRIMARY,
                source_symbol=symbol,
                canonical_symbol=f"{symbol}.TW",
                market="TW",
                trade_date=trade_date.isoformat(),
                traded_share_volume=volume,
                official_traded_value_twd=int(close * volume),
                open_price=open_price,
                high_price=high,
                low_price=low,
                close_price=close,
                transaction_count=1000,
                retrieved_at="2026-08-13T00:00:00+00:00",
                source_reference="https://www.twse.com.tw/",
                raw_content_hash=(symbol[-1] * 64),
            )
        )
    return build_research_dataset(
        ReconciliationResult(
            SourceState.PRIMARY_VERIFIED,
            tuple(records),
            cross_check_unavailable=True,
        ),
        requested_symbol=symbol,
        requested_start=START,
        requested_end=END,
    )


class WatchlistScannerTests(unittest.TestCase):
    def test_official_loader_never_invokes_finmind_even_with_token(self) -> None:
        source = _dataset("2330", count=1).records
        with patch.dict(os.environ, {"FINMIND_TOKEN": "MUST_NOT_BE_USED"}), patch(
            "twstock_data.dataset.fetch_twse_daily", return_value=source
        ) as twse, patch(
            "twstock_data.dataset.fetch_finmind_daily",
            side_effect=AssertionError("FinMind must not be called"),
        ) as finmind:
            dataset = fetch_official_research_dataset(
                "2330", START, END
            )

        twse.assert_called_once()
        finmind.assert_not_called()
        self.assertEqual(dataset.selected_source, "TWSE")
        self.assertTrue(dataset.cross_check_unavailable)

    def test_detached_or_wrong_period_dataset_is_isolated_before_analysis(self) -> None:
        valid = _dataset("2330")
        detached = replace(valid, requested_start="2023-01-01")
        wrong_period_source = _dataset("2317")
        wrong_period = build_research_dataset(
            ReconciliationResult(
                SourceState.PRIMARY_VERIFIED,
                wrong_period_source.records,
                cross_check_unavailable=True,
            ),
            requested_symbol="2317",
            requested_start="2023-01-01",
            requested_end=END,
        )
        datasets = {"2330": detached, "2317": wrong_period}

        scan = scan_watchlist(
            ["2330", "2317"],
            START,
            END,
            dataset_loader=lambda symbol, _start, _end: datasets[symbol],
        )
        rows = {item.source_symbol: item for item in scan.candidates}

        self.assertEqual(rows["2330"].scan_status, "DATA_UNAVAILABLE")
        self.assertEqual(rows["2317"].scan_status, "DATA_UNAVAILABLE")
        self.assertEqual(scan.timeline, ())

    def test_ranking_is_deterministic_and_input_order_independent(self) -> None:
        datasets = {
            "2330": _dataset("2330", last_volume_multiplier=3.0),
            "2317": _dataset("2317", last_volume_multiplier=1.5),
        }
        loader = lambda symbol, _start, _end: datasets[symbol]

        first = scan_watchlist(
            ["2330", "2317"], START, END, dataset_loader=loader
        )
        second = scan_watchlist(
            ["2317", "2330"], START, END, dataset_loader=loader
        )

        self.assertEqual(first.candidates, second.candidates)
        self.assertEqual(first.timeline, second.timeline)
        self.assertEqual(first.candidates[0].source_symbol, "2330")
        self.assertEqual([item.rank for item in first.candidates], [1, 2])

    def test_failure_short_history_and_stale_data_are_unranked(self) -> None:
        datasets = {
            "2330": _dataset("2330"),
            "2317": _dataset("2317", start_offset=-1),
            "2454": _dataset("2454", count=100),
        }

        def loader(symbol: str, _start: str, _end: str):
            if symbol == "1101":
                raise SourceUnavailableError("blocked")
            return datasets[symbol]

        scan = scan_watchlist(
            ["2330", "2317", "2454", "1101"],
            START,
            END,
            dataset_loader=loader,
        )
        rows = {item.source_symbol: item for item in scan.candidates}

        self.assertEqual(rows["2330"].rank, 1)
        self.assertEqual(rows["2317"].scan_status, "STALE_DATA")
        self.assertEqual(rows["2454"].scan_status, "INSUFFICIENT_HISTORY")
        self.assertIn(
            "INSUFFICIENT_HISTORY:100<251", rows["2454"].reason_codes
        )
        self.assertEqual(rows["1101"].scan_status, "DATA_UNAVAILABLE")
        self.assertTrue(all(rows[symbol].rank is None for symbol in ("2317", "2454", "1101")))

    def test_short_history_latest_date_still_defines_scan_as_of(self) -> None:
        datasets = {
            "2330": _dataset("2330", count=260),
            "2454": _dataset("2454", count=100, start_offset=200),
        }

        scan = scan_watchlist(
            ["2330", "2454"],
            START,
            END,
            dataset_loader=lambda symbol, _start, _end: datasets[symbol],
        )
        rows = {item.source_symbol: item for item in scan.candidates}

        self.assertEqual(scan.as_of_trade_date, datasets["2454"].bars[-1].trade_date)
        self.assertEqual(rows["2330"].scan_status, "STALE_DATA")
        self.assertEqual(rows["2454"].scan_status, "INSUFFICIENT_HISTORY")
        self.assertTrue(all(item.rank is None for item in scan.candidates))

    def test_timeline_contains_both_engines_and_stable_ids(self) -> None:
        dataset = _dataset("2330")
        loader = lambda _symbol, _start, _end: dataset
        first = scan_watchlist(["2330"], START, END, dataset_loader=loader)
        second = scan_watchlist(["2330"], START, END, dataset_loader=loader)

        self.assertEqual(
            {item.source_engine for item in first.timeline},
            {"BREAKOUT_TRACKER_V5", "CONTINUOUS_HIGH"},
        )
        self.assertEqual(
            [item.event_id for item in first.timeline],
            [item.event_id for item in second.timeline],
        )

    def test_outputs_repeat_unverified_and_prohibited_contract(self) -> None:
        dataset = _dataset("2330")
        scan = scan_watchlist(
            ["2330"], START, END, dataset_loader=lambda *_: dataset
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_watchlist_outputs(scan, output)
            manifest_text = (output / "watchlist_manifest.json").read_text(
                encoding="utf-8"
            )
            html = (output / "watchlist.html").read_text(encoding="utf-8")
            with (output / "watchlist_candidates.csv").open(
                encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            names = {path.name for path in output.iterdir()}

            self.assertEqual(
                names,
                {
                    "watchlist_candidates.csv",
                    "watchlist_timeline.csv",
                    "watchlist_manifest.json",
                    "watchlist.html",
                    "symbols",
                },
            )
            self.assertEqual(rows[0]["corporate_action_status"], "UNVERIFIED")
            self.assertEqual(rows[0]["investment_use"], "PROHIBITED")
            self.assertIn("UNVERIFIED", manifest_text)
            self.assertIn("PROHIBITED", manifest_text)
            self.assertIn("UNVERIFIED", html)
            self.assertIn("不作投資使用", html)
            self.assertTrue((output / "symbols" / "2330" / "market_bars.csv").is_file())

    def test_visual_report_embeds_rank_price_volume_and_event_charts(self) -> None:
        datasets = {
            "2330": _dataset("2330", last_volume_multiplier=3.0),
            "2317": _dataset("2317", last_volume_multiplier=1.5),
        }
        scan = scan_watchlist(
            ["2330", "2317"],
            START,
            END,
            dataset_loader=lambda symbol, _start, _end: datasets[symbol],
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_watchlist_outputs(scan, output)
            html = (output / "watchlist.html").read_text(encoding="utf-8")
            manifest = json.loads(
                (output / "watchlist_manifest.json").read_text(encoding="utf-8")
            )

        self.assertIn("Watchlist Scanner v0.3", html)
        self.assertIn('id="candidate-ranking-chart"', html)
        self.assertIn('id="event-timeline-chart"', html)
        self.assertIn('id="symbol-2330"', html)
        self.assertIn('id="symbol-2317"', html)
        self.assertEqual(
            html.count('aria-label="Continuous High Monitor daily timeline"'),
            2,
        )
        self.assertIn("成交量 / 前20日均量", html)
        self.assertIn("rolling high", html)
        self.assertIn("Pivot breakout", html)
        self.assertIn("序位圖，不使用長條長度", html)
        self.assertNotIn("<script", html)
        self.assertEqual(
            manifest["visualization_policy"]["rank_encoding"],
            "ORDINAL_ONLY_NO_SCORE_MAGNITUDE",
        )
        self.assertEqual(
            manifest["visualization_policy"]["corporate_action_status"],
            "UNVERIFIED",
        )

    def test_visualizations_retain_exact_engine_results_for_each_dataset(self) -> None:
        datasets = {symbol: _dataset(symbol) for symbol in ("2330", "2317")}
        scan = scan_watchlist(
            ["2330", "2317"],
            START,
            END,
            dataset_loader=lambda symbol, _start, _end: datasets[symbol],
        )

        self.assertEqual(
            [item.source_symbol for item in scan.visualizations],
            ["2317", "2330"],
        )
        for visualization in scan.visualizations:
            dataset = datasets[visualization.source_symbol]
            self.assertEqual(
                visualization.continuous_high_result.symbol,
                dataset.canonical_symbol,
            )
            self.assertEqual(
                visualization.continuous_high_result.parameter_hash,
                scan.monitor_parameter_hash,
            )
            self.assertTrue(visualization.breakout_snapshots)

    def test_watchlist_schema_rejects_duplicates_and_invalid_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "TWSTOCK-WATCHLIST-001",
                        "symbols": ["2330", "2330"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataValidationError, "duplicate"):
                load_watchlist(path)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "TWSTOCK-WATCHLIST-001",
                        "symbols": ["2330.TW"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DataValidationError, "digits"):
                load_watchlist(path)

    def test_cli_help_exposes_bounded_official_scanner(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            run_watchlist_scanner(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_cli_enables_incremental_cache_for_each_symbol(self) -> None:
        dataset = _dataset("2330")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watchlist = root / "watchlist.json"
            watchlist.write_text(
                json.dumps(
                    {
                        "schema_version": "TWSTOCK-WATCHLIST-001",
                        "symbols": ["2330"],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "scripts.run_watchlist_scanner.fetch_official_research_dataset",
                return_value=dataset,
            ) as fetch:
                result = run_watchlist_scanner(
                    [
                        "--watchlist",
                        str(watchlist),
                        "--start",
                        START,
                        "--end",
                        END,
                        "--output-dir",
                        str(root / "output"),
                        "--raw-cache-dir",
                        str(root / "cache"),
                    ]
                )

        self.assertEqual(result, 0)
        self.assertTrue(fetch.call_args.kwargs["incremental_cache"])
        self.assertEqual(
            fetch.call_args.kwargs["raw_cache_dir"], root / "cache" / "2330"
        )


if __name__ == "__main__":
    unittest.main()
