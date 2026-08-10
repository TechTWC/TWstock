from __future__ import annotations

from dataclasses import replace
from datetime import date
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from experiments.continuous_high_monitor import ContinuousHighMonitor, MonitorConfig
from experiments.continuous_high_monitor.report import render_html_report
from scripts.run_real_market_monitor import run as run_real_market_monitor
from twstock_data.dataset import (
    build_research_dataset,
    fetch_research_dataset,
    read_research_bars_csv,
    write_research_dataset,
)
from twstock_data.errors import DataValidationError, SourceUnavailableError
from twstock_data.models import (
    MarketDataRecord,
    ReconciliationIssue,
    ReconciliationResult,
    SourceState,
    SourceTier,
)
from twstock_data.http import HttpResponse


FIXTURES = Path(__file__).parent / "fixtures"
TWSE_PAYLOAD = (FIXTURES / "twse_stock_day_2330_202607.json").read_bytes()
FINMIND_PAYLOAD = (FIXTURES / "finmind_2330_202607.json").read_bytes()


class RoutingTransport:
    def __init__(self, *, mismatch: bool = False, fail_primary: bool = False) -> None:
        self.mismatch = mismatch
        self.fail_primary = fail_primary
        self.urls: list[str] = []

    def get(self, url: str, timeout: float) -> HttpResponse:
        self.urls.append(url)
        if "twse.com.tw" in url:
            if self.fail_primary:
                raise OSError("primary blocked")
            return HttpResponse(url, 200, TWSE_PAYLOAD)
        dataset_name = parse_qs(urlsplit(url).query).get("dataset", [""])[0]
        if dataset_name != "TaiwanStockPrice":
            return HttpResponse(url, 200, json.dumps({"data": []}).encode())
        payload = json.loads(FINMIND_PAYLOAD)
        if self.mismatch:
            payload["data"][0]["Trading_Volume"] = 1
        return HttpResponse(url, 200, json.dumps(payload).encode())


class HeaderAwareRoutingTransport(RoutingTransport):
    def __init__(self) -> None:
        super().__init__()
        self.header_calls: list[tuple[str, dict[str, str]]] = []

    def get_with_headers(
        self, url: str, timeout: float, headers: dict[str, str]
    ) -> HttpResponse:
        self.header_calls.append((url, dict(headers)))
        return self.get(url, timeout)


def record(
    *,
    source: str = "TWSE",
    tier: SourceTier = SourceTier.PRIMARY,
    trade_date: str = "2026-07-15",
    close: float = 100.0,
    volume: int = 20_000,
    traded_value: int = 2_345_678,
    retrieved_at: str = "2026-07-16T00:00:00+00:00",
    raw_hash: str = "a" * 64,
) -> MarketDataRecord:
    return MarketDataRecord(
        source=source,
        source_tier=tier,
        source_symbol="2330",
        canonical_symbol="2330.TW",
        market="TW",
        trade_date=trade_date,
        traded_share_volume=volume,
        official_traded_value_twd=traded_value,
        open_price=98.0,
        high_price=102.0,
        low_price=97.0,
        close_price=close,
        transaction_count=777,
        retrieved_at=retrieved_at,
        source_reference="https://example.invalid/source",
        raw_content_hash=raw_hash,
    )


class ResearchMarketDatasetTests(unittest.TestCase):
    def test_documented_direct_script_entrypoint_starts(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/run_real_market_monitor.py", "--help"],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--raw-cache-dir", completed.stdout)

    def test_runner_rejects_nonfinite_or_nonpositive_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for value in ("nan", "inf", "-inf", "0"):
                with self.subTest(timeout=value):
                    with self.assertRaises(SystemExit) as raised:
                        run_real_market_monitor(
                            [
                                "--symbol",
                                "2330",
                                "--start",
                                "2026-07-01",
                                "--end",
                                "2026-07-31",
                                "--output-dir",
                                str(Path(directory) / "output"),
                                "--raw-cache-dir",
                                str(Path(directory) / "raw"),
                                f"--timeout={value}",
                            ],
                            transport=RoutingTransport(),
                        )
                    self.assertEqual(raised.exception.code, 2)

    def test_fetch_pipeline_primary_with_optional_secondary_cross_check(self) -> None:
        with patch.dict(os.environ, {"FINMIND_TOKEN": "FAKE"}, clear=False):
            dataset = fetch_research_dataset(
                "2330",
                "2026-07-01",
                "2026-07-31",
                transport=RoutingTransport(),
                retries=0,
            )
        self.assertEqual(dataset.source_state, SourceState.PRIMARY_VERIFIED)
        self.assertFalse(dataset.cross_check_unavailable)
        self.assertEqual(dataset.selected_source, "TWSE")
        self.assertEqual(dataset.verification_sources, ("FinMind",))
        self.assertEqual(len(dataset.verification_raw_content_hashes), 1)

    def test_fetch_pipeline_accepts_official_primary_without_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            dataset = fetch_research_dataset(
                "2330",
                "2026-07-01",
                "2026-07-31",
                transport=RoutingTransport(),
                retries=0,
            )
        self.assertEqual(dataset.source_state, SourceState.PRIMARY_VERIFIED)
        self.assertTrue(dataset.cross_check_unavailable)

    def test_fetch_pipeline_rejects_cross_source_mismatch(self) -> None:
        with patch.dict(os.environ, {"FINMIND_TOKEN": "FAKE"}, clear=False):
            with self.assertRaisesRegex(DataValidationError, "SOURCE_MISMATCH"):
                fetch_research_dataset(
                    "2330",
                    "2026-07-01",
                    "2026-07-31",
                    transport=RoutingTransport(mismatch=True),
                    retries=0,
                )

    def test_fetch_pipeline_preserves_primary_and_secondary_raw_responses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"FINMIND_TOKEN": "FAKE"}, clear=False):
                fetch_research_dataset(
                    "2330",
                    "2026-07-01",
                    "2026-07-31",
                    transport=RoutingTransport(),
                    retries=0,
                    raw_cache_dir=directory,
                )
            metadata = sorted(Path(directory).glob("*.metadata.json"))
            raw = sorted(Path(directory).glob("*.raw"))
        self.assertEqual(len(metadata), 2)
        self.assertEqual(len(raw), 2)

    def test_real_market_runner_writes_reproducible_bounded_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            raw = root / "raw"
            transport = RoutingTransport()
            with patch.dict(os.environ, {"FINMIND_TOKEN": "FAKE"}, clear=False):
                code = run_real_market_monitor(
                    [
                        "--symbol",
                        "2330",
                        "--start",
                        "2026-07-01",
                        "--end",
                        "2026-07-31",
                        "--output-dir",
                        str(output),
                        "--raw-cache-dir",
                        str(raw),
                        "--retries",
                        "0",
                    ],
                    transport=transport,
                )
            manifest = json.loads(
                (output / "run_manifest.json").read_text(encoding="utf-8")
            )
            names = {item.name for item in output.iterdir()}
            requested_urls = list(transport.urls)

        self.assertEqual(code, 0)
        self.assertEqual(manifest["dataset_source_state"], "PRIMARY_VERIFIED")
        self.assertEqual(manifest["status"], "EXPLORATORY_NOT_VALIDATED")
        self.assertFalse(manifest["history_sufficient_for_longest_high_window"])
        self.assertFalse(manifest["clean_history_sufficient_for_longest_high_window"])
        self.assertEqual(manifest["minimum_history_bars"], 251)
        self.assertTrue(manifest["corporate_action_guard_applied"])
        self.assertEqual(
            manifest["corporate_action_coverage_state"], "SECONDARY_COMPLETE"
        )
        self.assertEqual(manifest["corporate_action_event_count"], 0)
        self.assertEqual(manifest["continuous_high_html_bar_count"], 1)
        self.assertTrue(all("FAKE" not in url for url in requested_urls))
        self.assertTrue(all("token=" not in url for url in requested_urls))
        self.assertEqual(
            names,
            {
                "analysis_guard.csv",
                "breakout_snapshots.csv",
                "corporate_action_manifest.json",
                "corporate_actions.csv",
                "continuous_high.html",
                "continuous_high_features.csv",
                "continuous_high_timeline.csv",
                "dataset_manifest.json",
                "market_bars.csv",
                "run_manifest.json",
            },
        )

    def test_real_market_runner_never_sends_finmind_bearer_to_twse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = HeaderAwareRoutingTransport()
            with patch.dict(os.environ, {"FINMIND_TOKEN": "SECRET"}, clear=False):
                code = run_real_market_monitor(
                    [
                        "--symbol",
                        "2330",
                        "--start",
                        "2026-07-01",
                        "--end",
                        "2026-07-31",
                        "--output-dir",
                        str(root / "output"),
                        "--raw-cache-dir",
                        str(root / "raw"),
                        "--retries",
                        "0",
                    ],
                    transport=transport,
                )

        self.assertEqual(code, 0)
        self.assertTrue(any("twse.com.tw" in url for url in transport.urls))
        self.assertTrue(transport.header_calls)
        self.assertTrue(
            all(
                urlsplit(url).scheme == "https"
                and urlsplit(url).hostname == "api.finmindtrade.com"
                for url, _ in transport.header_calls
            )
        )
        self.assertEqual(
            {
                parse_qs(urlsplit(url).query)["dataset"][0]
                for url, _ in transport.header_calls
            },
            {
                "TaiwanStockPrice",
                "TaiwanStockDividendResult",
                "TaiwanStockCapitalReductionReferencePrice",
                "TaiwanStockSplitPrice",
                "TaiwanStockParValueChange",
            },
        )
        self.assertTrue(
            all(
                headers["Authorization"] == "Bearer SECRET"
                for _, headers in transport.header_calls
            )
        )

    def test_real_market_runner_fails_closed_without_action_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(SourceUnavailableError, "corporate-action"):
                    run_real_market_monitor(
                        [
                            "--symbol",
                            "2330",
                            "--start",
                            "2026-07-01",
                            "--end",
                            "2026-07-31",
                            "--output-dir",
                            str(output),
                            "--raw-cache-dir",
                            str(root / "raw"),
                            "--retries",
                            "0",
                        ],
                        transport=RoutingTransport(),
                    )
            self.assertFalse(output.exists())

    def test_real_market_runner_blocks_outputs_after_effective_event(self) -> None:
        class EventTransport(RoutingTransport):
            def get(self, url: str, timeout: float) -> HttpResponse:
                dataset_name = parse_qs(urlsplit(url).query).get("dataset", [""])[0]
                if dataset_name == "TaiwanStockDividendResult":
                    payload = {
                        "status": 200,
                        "msg": "success",
                        "data": [
                            {
                                "date": "2026-07-15",
                                "stock_id": "2330",
                                "before_price": 102.0,
                                "after_price": 100.0,
                                "stock_or_cache_dividend": "息",
                            }
                        ],
                    }
                    self.urls.append(url)
                    return HttpResponse(url, 200, json.dumps(payload).encode())
                return super().get(url, timeout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            with patch.dict(os.environ, {"FINMIND_TOKEN": "FAKE"}, clear=False):
                code = run_real_market_monitor(
                    [
                        "--symbol",
                        "2330",
                        "--start",
                        "2026-07-01",
                        "--end",
                        "2026-07-31",
                        "--output-dir",
                        str(output),
                        "--raw-cache-dir",
                        str(root / "raw"),
                        "--retries",
                        "0",
                    ],
                    transport=EventTransport(),
                )
            manifest = json.loads(
                (output / "run_manifest.json").read_text(encoding="utf-8")
            )
            with (output / "corporate_actions.csv").open(encoding="utf-8") as handle:
                action_rows = list(csv.DictReader(handle))
            with (output / "analysis_guard.csv").open(encoding="utf-8") as handle:
                guard_rows = list(csv.DictReader(handle))

        self.assertEqual(code, 0)
        self.assertEqual(len(action_rows), 1)
        self.assertEqual({row["state"] for row in guard_rows}, {"ANALYSIS_BLOCKED"})
        self.assertEqual(manifest["corporate_action_event_count"], 1)
        self.assertEqual(manifest["analysis_blocked_row_count"], 2)
        self.assertFalse(manifest["continuous_high_guard_ready_on_last_bar"])
        self.assertFalse(manifest["breakout_guard_ready_on_last_bar"])
        self.assertEqual(manifest["continuous_high_html_bar_count"], 0)

    def test_primary_dataset_preserves_official_value_and_provenance(self) -> None:
        source = record()
        reconciliation = ReconciliationResult(
            state=SourceState.PRIMARY_VERIFIED,
            records=(source,),
            cross_check_unavailable=True,
        )

        dataset = build_research_dataset(
            reconciliation,
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
        )

        self.assertEqual(dataset.canonical_symbol, "2330.TW")
        self.assertEqual(dataset.selected_source, "TWSE")
        self.assertTrue(dataset.cross_check_unavailable)
        self.assertEqual(dataset.bars[0].official_traded_value_twd, 2_345_678)
        self.assertEqual(dataset.raw_content_hashes, ("a" * 64,))
        self.assertEqual(dataset.adjustment_policy, "RAW_UNADJUSTED")

    def test_dataset_hash_ignores_retrieval_time_but_tracks_market_content(self) -> None:
        first = record(retrieved_at="2026-07-16T00:00:00+00:00")
        later_retrieval = replace(first, retrieved_at="2026-07-17T00:00:00+00:00")
        changed_close = replace(first, close_price=101.0)

        def build(item: MarketDataRecord):
            return build_research_dataset(
                ReconciliationResult(
                    SourceState.PRIMARY_VERIFIED,
                    (item,),
                    cross_check_unavailable=True,
                ),
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
            )

        self.assertEqual(build(first).dataset_hash, build(later_retrieval).dataset_hash)
        self.assertNotEqual(build(first).dataset_hash, build(changed_close).dataset_hash)

    def test_source_mismatch_is_fail_closed(self) -> None:
        mismatch = ReconciliationResult(
            SourceState.SOURCE_MISMATCH,
            (record(),),
            issues=(
                ReconciliationIssue(
                    "2026-07-15", "close_price", 100.0, 100.5
                ),
            ),
        )
        with self.assertRaisesRegex(DataValidationError, "SOURCE_MISMATCH"):
            build_research_dataset(
                mismatch,
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
            )

    def test_secondary_only_requires_explicit_opt_in(self) -> None:
        secondary = record(source="FinMind", tier=SourceTier.SECONDARY)
        reconciliation = ReconciliationResult(
            SourceState.SECONDARY_ONLY, (secondary,)
        )
        with self.assertRaisesRegex(DataValidationError, "SECONDARY_ONLY"):
            build_research_dataset(
                reconciliation,
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
            )

        dataset = build_research_dataset(
            reconciliation,
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
            allow_secondary_only=True,
        )
        self.assertEqual(dataset.selected_source, "FinMind")
        self.assertEqual(dataset.source_state, SourceState.SECONDARY_ONLY)
        self.assertEqual(dataset.price_basis, "RAW_SECONDARY_DAILY")

    def test_source_state_requires_the_contractually_named_provider(self) -> None:
        cases = (
            (
                ReconciliationResult(
                    SourceState.PRIMARY_VERIFIED,
                    (record(source="Yahoo"),),
                    cross_check_unavailable=True,
                ),
                (),
                False,
            ),
            (
                ReconciliationResult(
                    SourceState.SECONDARY_ONLY,
                    (record(source="Yahoo", tier=SourceTier.SECONDARY),),
                ),
                (),
                True,
            ),
            (
                ReconciliationResult(SourceState.PRIMARY_VERIFIED, (record(),)),
                (
                    record(
                        source="Yahoo",
                        tier=SourceTier.SECONDARY,
                        raw_hash="b" * 64,
                    ),
                ),
                False,
            ),
        )
        for reconciliation, verification, allow_secondary in cases:
            with self.subTest(state=reconciliation.state.value):
                with self.assertRaisesRegex(DataValidationError, "source provider"):
                    build_research_dataset(
                        reconciliation,
                        requested_symbol="2330",
                        requested_start="2026-07-01",
                        requested_end="2026-07-31",
                        allow_secondary_only=allow_secondary,
                        verification_records=verification,
                    )

    def test_invalid_record_date_and_hash_fail_with_controlled_error(self) -> None:
        for bad, message in (
            (replace(record(), trade_date="2026/07/15"), "trade date"),
            (replace(record(), trade_date=None), "trade date"),
            (replace(record(), raw_content_hash="z" * 64), "raw content hash"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(DataValidationError, message):
                    build_research_dataset(
                        ReconciliationResult(
                            SourceState.PRIMARY_VERIFIED,
                            (bad,),
                            cross_check_unavailable=True,
                        ),
                        requested_symbol="2330",
                        requested_start="2026-07-01",
                        requested_end="2026-07-31",
                    )

        with self.assertRaisesRegex(DataValidationError, "trade date"):
            build_research_dataset(
                ReconciliationResult(
                    SourceState.PRIMARY_VERIFIED,
                    (
                        record(trade_date="2026-07-14"),
                        replace(record(), trade_date=None),
                    ),
                    cross_check_unavailable=True,
                ),
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
            )

    def test_csv_round_trip_preserves_engine_bars_and_manifest(self) -> None:
        records = (
            record(trade_date="2026-07-14", close=99.0, raw_hash="a" * 64),
            record(trade_date="2026-07-15", close=100.0, raw_hash="b" * 64),
        )
        dataset = build_research_dataset(
            ReconciliationResult(
                SourceState.PRIMARY_VERIFIED,
                records,
                cross_check_unavailable=True,
            ),
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_research_dataset(dataset, output)
            loaded = read_research_bars_csv(output / "market_bars.csv")
            manifest = json.loads(
                (output / "dataset_manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(loaded, dataset.bars)
        self.assertEqual(manifest["dataset_hash"], dataset.dataset_hash)
        self.assertEqual(manifest["record_count"], 2)
        self.assertEqual(manifest["price_basis"], "RAW_OFFICIAL_DAILY")

    def test_writer_rejects_bars_or_hash_detached_from_dataset_content(self) -> None:
        dataset = build_research_dataset(
            ReconciliationResult(
                SourceState.PRIMARY_VERIFIED,
                (record(),),
                cross_check_unavailable=True,
            ),
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
        )
        detached_bar = replace(dataset.bars[0], close=101.0)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DataValidationError, "bars do not match"):
                write_research_dataset(
                    replace(dataset, bars=(detached_bar,)),
                    Path(directory),
                )
            with self.assertRaisesRegex(DataValidationError, "hash does not match"):
                write_research_dataset(
                    replace(dataset, dataset_hash="0" * 64),
                    Path(directory),
                )

            for field, detached in (
                (
                    "adjustment policy",
                    replace(dataset, adjustment_policy="TOTAL_RETURN"),
                ),
                (
                    "corporate actions",
                    replace(dataset, corporate_actions_applied=True),
                ),
                (
                    "raw hashes",
                    replace(dataset, raw_content_hashes=("f" * 64,)),
                ),
                (
                    "retrieval timestamps",
                    replace(
                        dataset,
                        retrieval_timestamps=("2099-01-01T00:00:00+00:00",),
                    ),
                ),
                (
                    "requested symbol",
                    replace(dataset, requested_symbol="9999"),
                ),
            ):
                with self.subTest(field=field):
                    with self.assertRaisesRegex(
                        DataValidationError, "dataset metadata does not match"
                    ):
                        detached.manifest()
                    with self.assertRaisesRegex(
                        DataValidationError, "dataset metadata does not match"
                    ):
                        write_research_dataset(detached, Path(directory))

    def test_writer_rejects_detached_secondary_verification_provenance(self) -> None:
        primary = record()
        secondary = record(
            source="FinMind",
            tier=SourceTier.SECONDARY,
            raw_hash="b" * 64,
        )
        dataset = build_research_dataset(
            ReconciliationResult(SourceState.PRIMARY_VERIFIED, (primary,)),
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
            verification_records=(secondary,),
        )
        with tempfile.TemporaryDirectory() as directory:
            write_research_dataset(dataset, Path(directory))
            detached = replace(
                dataset,
                verification_retrieval_timestamps=(
                    "2099-01-01T00:00:00+00:00",
                ),
            )
            with self.assertRaisesRegex(
                DataValidationError, "dataset metadata does not match"
            ):
                write_research_dataset(detached, Path(directory))

    def test_continuous_high_uses_official_value_when_available(self) -> None:
        bars = build_research_dataset(
            ReconciliationResult(
                SourceState.PRIMARY_VERIFIED,
                (record(),),
                cross_check_unavailable=True,
            ),
            requested_symbol="2330",
            requested_start="2026-07-01",
            requested_end="2026-07-31",
        ).bars
        config = MonitorConfig(
            high_windows=(2, 3),
            near_high_window=2,
            base_high_window=2,
            strengthening_high_window=2,
            leader_high_window=3,
            high_count_window=2,
            strengthening_high_count=2,
            volume_average_window=2,
            extension_ma_window=2,
            weakening_high_window=2,
            acceleration_window=2,
            acceleration_high_count=2,
            minimum_trading_value=0,
        )
        result = ContinuousHighMonitor(config).run(bars)

        self.assertEqual(result.feature_rows[0].features.trading_value, 2_345_678)
        rendered = render_html_report(bars=bars, result=result, config=config)
        self.assertIn("2330.TW", rendered)

    def test_claimed_cross_check_requires_secondary_provenance(self) -> None:
        with self.assertRaisesRegex(DataValidationError, "verification provenance"):
            build_research_dataset(
                ReconciliationResult(SourceState.PRIMARY_VERIFIED, (record(),)),
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
            )

    def test_secondary_provenance_must_match_primary_records(self) -> None:
        primary = record()
        secondary = record(
            source="FinMind",
            tier=SourceTier.SECONDARY,
            volume=1,
            raw_hash="b" * 64,
        )
        with self.assertRaisesRegex(DataValidationError, "does not match"):
            build_research_dataset(
                ReconciliationResult(SourceState.PRIMARY_VERIFIED, (primary,)),
                requested_symbol="2330",
                requested_start="2026-07-01",
                requested_end="2026-07-31",
                verification_records=(secondary,),
            )


if __name__ == "__main__":
    unittest.main()
