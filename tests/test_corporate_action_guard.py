from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from experiments.breakout_tracker_v5 import BreakoutTracker, TrackerConfig
from experiments.continuous_high_monitor import ContinuousHighMonitor, MonitorConfig
from twstock_data.corporate_actions import (
    AnalysisGuardState,
    CorporateActionEvidence,
    CorporateActionType,
    FinMindBearerTransport,
    REQUIRED_FINMIND_DATASETS,
    build_analysis_guard_decisions,
    build_corporate_action_dataset,
    fetch_finmind_corporate_actions,
    parse_finmind_corporate_action_payload,
    write_corporate_action_dataset,
)
from twstock_data.errors import DataValidationError, SourceUnavailableError
from twstock_data.guarded_monitors import (
    run_guarded_breakout_tracker,
    run_guarded_continuous_high,
)
from twstock_data.http import HttpResponse
from twstock_data.models import MarketBar, SourceTier


def evidence(dataset_name: str, suffix: str) -> CorporateActionEvidence:
    return CorporateActionEvidence(
        source="FinMind",
        source_tier=SourceTier.SECONDARY,
        source_dataset=dataset_name,
        source_symbol="2330",
        canonical_symbol="2330.TW",
        requested_start="2026-01-01",
        requested_end="2026-12-31",
        retrieved_at="2026-08-10T00:00:00+00:00",
        source_reference=f"https://example.invalid/{dataset_name}",
        raw_content_hash=suffix * 64,
    )


def all_evidence() -> tuple[CorporateActionEvidence, ...]:
    return tuple(
        evidence(name, chr(ord("a") + index))
        for index, name in enumerate(REQUIRED_FINMIND_DATASETS)
    )


def parsed_event(
    *,
    effective_date: str = "2026-06-15",
    before_price: float = 100.0,
    after_price: float = 95.0,
):
    dataset_name = "TaiwanStockDividendResult"
    matching = next(item for item in all_evidence() if item.source_dataset == dataset_name)
    return parse_finmind_corporate_action_payload(
        dataset_name,
        {
            "data": [
                {
                    "date": effective_date,
                    "stock_id": "2330",
                    "before_price": before_price,
                    "after_price": after_price,
                    "stock_or_cache_dividend": "息",
                }
            ]
        },
        source_symbol="2330",
        canonical="2330.TW",
        start="2026-01-01",
        end="2026-12-31",
        raw_content_hash=matching.raw_content_hash,
    )[0]


def bars(count: int = 40, *, start: date = date(2026, 5, 1)) -> tuple[MarketBar, ...]:
    output = []
    for index in range(count):
        close = 100.0 + index * 0.25
        output.append(
            MarketBar(
                symbol="2330.TW",
                trade_date=start + timedelta(days=index),
                open=close - 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=10_000 + index,
                official_traded_value_twd=1_000_000 + index,
            )
        )
    return tuple(output)


def small_monitor_config() -> MonitorConfig:
    return MonitorConfig(
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


class CorporateActionGuardTests(unittest.TestCase):
    def test_bearer_transport_authenticates_only_exact_finmind_endpoint(self) -> None:
        class Transport:
            def __init__(self) -> None:
                self.plain_urls: list[str] = []
                self.authenticated_calls: list[tuple[str, dict[str, str]]] = []

            def get(self, url: str, timeout: float) -> HttpResponse:
                self.plain_urls.append(url)
                return HttpResponse(url, 200, b"{}")

            def get_with_headers(
                self, url: str, timeout: float, headers: dict[str, str]
            ) -> HttpResponse:
                self.authenticated_calls.append((url, dict(headers)))
                return HttpResponse(url, 200, b"{}")

        transport = Transport()
        authenticated = FinMindBearerTransport(transport, "SECRET")
        urls = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?token=SECRET",
            "http://api.finmindtrade.com/api/v4/data?token=SECRET",
            "https://api.finmindtrade.com.evil.invalid/api/v4/data?token=SECRET",
            "https://api.finmindtrade.com:444/api/v4/data?token=SECRET",
            "https://api.finmindtrade.com/not-data?token=SECRET",
            "https://api.finmindtrade.com/api/v4/data?token=SECRET",
        )
        for url in urls:
            authenticated.get(url, 1.0)

        self.assertEqual(len(transport.authenticated_calls), 1)
        authenticated_url, headers = transport.authenticated_calls[0]
        self.assertEqual(
            authenticated_url,
            "https://api.finmindtrade.com/api/v4/data",
        )
        self.assertEqual(headers["Authorization"], "Bearer SECRET")
        self.assertEqual(len(transport.plain_urls), 5)
        self.assertTrue(
            all(
                "SECRET" not in url and "token=" not in url
                for url in transport.plain_urls
            )
        )

    def test_all_four_finmind_schemas_normalize_to_explicit_events(self) -> None:
        cases = {
            "TaiwanStockDividendResult": (
                {
                    "date": "2026-06-15",
                    "stock_id": "2330",
                    "before_price": 100,
                    "after_price": 95,
                    "stock_or_cache_dividend": "息",
                },
                CorporateActionType.EX_DIVIDEND,
            ),
            "TaiwanStockCapitalReductionReferencePrice": (
                {
                    "date": "2026-06-16",
                    "stock_id": "2330",
                    "ClosingPriceonTheLastTradingDay": 100,
                    "PostReductionReferencePrice": 125,
                    "ReasonforCapitalReduction": "Cash refund",
                },
                CorporateActionType.CAPITAL_REDUCTION,
            ),
            "TaiwanStockSplitPrice": (
                {
                    "date": "2026-06-17",
                    "stock_id": "2330",
                    "type": "分割",
                    "before_price": 100,
                    "after_price": 20,
                },
                CorporateActionType.SPLIT,
            ),
            "TaiwanStockParValueChange": (
                {
                    "date": "2026-06-18",
                    "stock_id": "2330",
                    "stock_name": "台積電",
                    "before_close": 100,
                    "after_ref_close": 50,
                },
                CorporateActionType.PAR_VALUE_CHANGE,
            ),
        }
        for index, (dataset_name, (row, expected_type)) in enumerate(cases.items()):
            with self.subTest(dataset=dataset_name):
                result = parse_finmind_corporate_action_payload(
                    dataset_name,
                    {"data": [row]},
                    source_symbol="2330",
                    canonical="2330.TW",
                    start="2026-01-01",
                    end="2026-12-31",
                    raw_content_hash=chr(ord("a") + index) * 64,
                )
                self.assertEqual(result[0].event_type, expected_type)
                self.assertEqual(result[0].knowledge_date, result[0].effective_date)
                self.assertEqual(
                    result[0].knowledge_basis, "EFFECTIVE_DATE_CONSERVATIVE"
                )

    def test_dataset_requires_complete_exact_query_coverage(self) -> None:
        with self.assertRaisesRegex(DataValidationError, "all four"):
            build_corporate_action_dataset(
                requested_symbol="2330",
                requested_start="2026-01-01",
                requested_end="2026-12-31",
                events=(),
                evidence=all_evidence()[:-1],
            )

    def test_dataset_identity_tracks_events_and_source_payloads(self) -> None:
        event = parsed_event()
        first = build_corporate_action_dataset(
            requested_symbol="2330",
            requested_start="2026-01-01",
            requested_end="2026-12-31",
            events=(event,),
            evidence=all_evidence(),
        )
        dividend_evidence = next(
            item
            for item in all_evidence()
            if item.source_dataset == "TaiwanStockDividendResult"
        )
        changed_event = parse_finmind_corporate_action_payload(
            "TaiwanStockDividendResult",
            {
                "data": [
                    {
                        "date": "2026-06-15",
                        "stock_id": "2330",
                        "before_price": 100.0,
                        "after_price": 94.0,
                        "stock_or_cache_dividend": "息",
                    }
                ]
            },
            source_symbol="2330",
            canonical="2330.TW",
            start="2026-01-01",
            end="2026-12-31",
            raw_content_hash=dividend_evidence.raw_content_hash,
        )[0]
        changed_content = build_corporate_action_dataset(
            requested_symbol="2330",
            requested_start="2026-01-01",
            requested_end="2026-12-31",
            events=(changed_event,),
            evidence=all_evidence(),
        )
        changed_evidence = list(all_evidence())
        changed_evidence[0] = replace(changed_evidence[0], raw_content_hash="f" * 64)
        changed_source = build_corporate_action_dataset(
            requested_symbol="2330",
            requested_start="2026-01-01",
            requested_end="2026-12-31",
            events=(event,),
            evidence=changed_evidence,
        )
        changed_timestamp_evidence = list(all_evidence())
        changed_timestamp_evidence[0] = replace(
            changed_timestamp_evidence[0],
            retrieved_at="2026-08-10T00:00:01+00:00",
        )
        changed_timestamp = build_corporate_action_dataset(
            requested_symbol="2330",
            requested_start="2026-01-01",
            requested_end="2026-12-31",
            events=(event,),
            evidence=changed_timestamp_evidence,
        )
        self.assertNotEqual(first.dataset_hash, changed_content.dataset_hash)
        self.assertNotEqual(first.dataset_hash, changed_source.dataset_hash)
        self.assertNotEqual(first.dataset_hash, changed_timestamp.dataset_hash)

        unsafe_reference = list(all_evidence())
        unsafe_reference[0] = replace(
            unsafe_reference[0],
            source_reference="https://example.invalid/data?token=SECRET",
        )
        with self.assertRaisesRegex(DataValidationError, "contains credentials"):
            build_corporate_action_dataset(
                requested_symbol="2330",
                requested_start="2026-01-01",
                requested_end="2026-12-31",
                events=(event,),
                evidence=unsafe_reference,
            )

    def test_event_id_and_type_cannot_detach_from_source_content(self) -> None:
        event = parsed_event()
        for detached, message in (
            (replace(event, after_reference_price=94.0), "id/content"),
            (replace(event, event_type=CorporateActionType.SPLIT), "type/dataset"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(DataValidationError, message):
                    build_corporate_action_dataset(
                        requested_symbol="2330",
                        requested_start="2026-01-01",
                        requested_end="2026-12-31",
                        events=(detached,),
                        evidence=all_evidence(),
                    )

    def test_http_success_with_api_error_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(SourceUnavailableError, "status"):
            parse_finmind_corporate_action_payload(
                "TaiwanStockDividendResult",
                {"status": 402, "msg": "rate limit", "data": []},
                source_symbol="2330",
                canonical="2330.TW",
                start="2026-01-01",
                end="2026-12-31",
                raw_content_hash="a" * 64,
            )

    def test_documented_full_market_sources_filter_requested_symbol(self) -> None:
        result = parse_finmind_corporate_action_payload(
            "TaiwanStockSplitPrice",
            {
                "data": [
                    {
                        "date": "2026-06-17",
                        "stock_id": "0050",
                        "type": "分割",
                        "before_price": 200,
                        "after_price": 50,
                    },
                    {
                        "date": "2026-06-18",
                        "stock_id": "2330",
                        "type": "反分割",
                        "before_price": 100,
                        "after_price": 500,
                    },
                ]
            },
            source_symbol="2330",
            canonical="2330.TW",
            start="2026-01-01",
            end="2026-12-31",
            raw_content_hash="a" * 64,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_symbol, "2330")

    def test_manifest_and_writer_reject_detached_metadata(self) -> None:
        dataset = build_corporate_action_dataset(
            requested_symbol="2330",
            requested_start="2026-01-01",
            requested_end="2026-12-31",
            events=(parsed_event(),),
            evidence=all_evidence(),
        )
        detached = replace(dataset, dataset_hash="0" * 64)
        with self.assertRaisesRegex(DataValidationError, "metadata"):
            detached.manifest()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DataValidationError, "metadata"):
                write_corporate_action_dataset(detached, Path(directory))
            write_corporate_action_dataset(dataset, Path(directory))
            self.assertTrue((Path(directory) / "corporate_actions.csv").exists())
            self.assertTrue(
                (Path(directory) / "corporate_action_manifest.json").exists()
            )

    def test_future_event_never_rewrites_earlier_guard_state(self) -> None:
        source = bars(20)
        event = parsed_event(effective_date=source[15].trade_date.isoformat())
        with_event = build_analysis_guard_decisions(
            source,
            (event,),
            analyzer="TEST",
            required_clean_bars=4,
        )
        without_event = build_analysis_guard_decisions(
            source[:15],
            (),
            analyzer="TEST",
            required_clean_bars=4,
        )
        self.assertEqual(with_event[:15], without_event)
        self.assertEqual(
            with_event[15].state,
            AnalysisGuardState.ANALYSIS_BLOCKED,
        )
        self.assertEqual(with_event[18].state, AnalysisGuardState.ALLOWED)

    def test_no_action_results_are_bit_for_bit_engine_compatible(self) -> None:
        source = bars(40)
        monitor_config = small_monitor_config()
        tracker_config = TrackerConfig(
            pivot_lookback=3,
            pivot_confirmation_bars=1,
            volume_lookback=2,
        )
        raw_monitor = ContinuousHighMonitor(monitor_config).run(source)
        raw_tracker = BreakoutTracker(tracker_config).run(source)
        guarded_monitor, monitor_decisions = run_guarded_continuous_high(
            source, (), monitor_config
        )
        guarded_tracker, tracker_decisions = run_guarded_breakout_tracker(
            source, (), tracker_config
        )
        self.assertEqual(guarded_monitor, raw_monitor)
        self.assertEqual(guarded_tracker, raw_tracker)
        self.assertTrue(
            all(item.state is AnalysisGuardState.ALLOWED for item in monitor_decisions)
        )
        self.assertTrue(
            all(item.state is AnalysisGuardState.ALLOWED for item in tracker_decisions)
        )

    def test_event_resets_both_engines_and_blocks_warmup_outputs(self) -> None:
        source = bars(20)
        event = parsed_event(effective_date=source[10].trade_date.isoformat())
        monitor_config = small_monitor_config()
        tracker_config = TrackerConfig(
            pivot_lookback=3,
            pivot_confirmation_bars=1,
            volume_lookback=2,
        )
        monitor, monitor_decisions = run_guarded_continuous_high(
            source, (event,), monitor_config
        )
        breakout, breakout_decisions = run_guarded_breakout_tracker(
            source, (event,), tracker_config
        )
        monitor_allowed = {
            item.trade_date
            for item in monitor_decisions
            if item.state is AnalysisGuardState.ALLOWED
        }
        breakout_allowed = {
            item.trade_date
            for item in breakout_decisions
            if item.state is AnalysisGuardState.ALLOWED
        }
        self.assertTrue(all(item.trade_date in monitor_allowed for item in monitor.feature_rows))
        self.assertTrue(all(item.trade_date in monitor_allowed for item in monitor.snapshots))
        self.assertTrue(all(item.trade_date in breakout_allowed for item in breakout))
        self.assertEqual(
            monitor_decisions[10].state,
            AnalysisGuardState.ANALYSIS_BLOCKED,
        )
        self.assertEqual(monitor_decisions[12].state, AnalysisGuardState.ALLOWED)
        reopened = next(
            item for item in monitor.feature_rows if item.trade_date == source[12].trade_date
        )
        self.assertIsNotNone(reopened.features.prior_high(2))
        self.assertIsNone(reopened.features.prior_high(3))
        self.assertEqual(
            breakout_decisions[10].state,
            AnalysisGuardState.ANALYSIS_BLOCKED,
        )

    def test_reverse_split_fake_high_and_breakout_are_suppressed(self) -> None:
        start = date(2026, 6, 1)
        prices = (
            (9.0, 10.0),
            (10.0, 11.0),
            (11.0, 12.0),
            (11.0, 11.5),
            (50.0, 51.0),
            (50.5, 51.5),
            (51.0, 52.0),
            (51.5, 52.5),
        )
        source = tuple(
            MarketBar(
                symbol="2330.TW",
                trade_date=start + timedelta(days=index),
                open=close,
                high=high,
                low=close - 0.5,
                close=close,
                volume=10_000,
                official_traded_value_twd=1_000_000,
            )
            for index, (close, high) in enumerate(prices)
        )
        split_evidence = next(
            item
            for item in all_evidence()
            if item.source_dataset == "TaiwanStockSplitPrice"
        )
        event = parse_finmind_corporate_action_payload(
            "TaiwanStockSplitPrice",
            {
                "data": [
                    {
                        "date": source[4].trade_date.isoformat(),
                        "stock_id": "2330",
                        "type": "反分割",
                        "before_price": 11.0,
                        "after_price": 50.0,
                    }
                ]
            },
            source_symbol="2330",
            canonical="2330.TW",
            start="2026-01-01",
            end="2026-12-31",
            raw_content_hash=split_evidence.raw_content_hash,
        )[0]
        tracker_config = TrackerConfig(
            pivot_lookback=3,
            pivot_confirmation_bars=1,
            volume_lookback=2,
        )
        monitor_config = small_monitor_config()
        raw_breakout = BreakoutTracker(tracker_config).run(source)
        raw_monitor = ContinuousHighMonitor(monitor_config).run(source)
        guarded_breakout, _ = run_guarded_breakout_tracker(
            source, (event,), tracker_config
        )
        guarded_monitor, _ = run_guarded_continuous_high(
            source, (event,), monitor_config
        )
        event_date = source[4].trade_date
        self.assertTrue(
            any(
                item.trade_date == event_date and item.state.value == "NEW_TRIGGER"
                for item in raw_breakout
            )
        )
        self.assertTrue(
            any(
                item.trade_date == event_date and item.event_type.value == "NEW_HIGH"
                for item in raw_monitor.events
            )
        )
        self.assertFalse(any(item.trade_date == event_date for item in guarded_breakout))
        self.assertFalse(
            any(item.trade_date == event_date for item in guarded_monitor.feature_rows)
        )

    def test_fetch_requires_token_and_all_queries_succeed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SourceUnavailableError, "required"):
                fetch_finmind_corporate_actions(
                    "2330", "2026-01-01", "2026-12-31"
                )

        class Transport:
            def __init__(self) -> None:
                self.datasets: list[str] = []
                self.urls: list[str] = []
                self.headers: list[dict[str, str]] = []

            def get_with_headers(
                self, url: str, timeout: float, headers: dict[str, str]
            ) -> HttpResponse:
                dataset_name = parse_qs(urlsplit(url).query)["dataset"][0]
                self.datasets.append(dataset_name)
                self.urls.append(url)
                self.headers.append(headers)
                return HttpResponse(url, 200, json.dumps({"data": []}).encode())

            def get(self, url: str, timeout: float) -> HttpResponse:
                raise AssertionError("authenticated transport path was not used")

        transport = Transport()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"FINMIND_TOKEN": "SECRET"}, clear=False):
                dataset = fetch_finmind_corporate_actions(
                    "2330",
                    "2026-01-01",
                    "2026-12-31",
                    transport=transport,
                    retries=0,
                    raw_cache_dir=directory,
                )
            metadata = sorted(Path(directory).glob("*.metadata.json"))
        self.assertEqual(tuple(sorted(transport.datasets)), REQUIRED_FINMIND_DATASETS)
        self.assertTrue(all("SECRET" not in url for url in transport.urls))
        self.assertTrue(all("token=" not in url for url in transport.urls))
        self.assertTrue(
            all(item["Authorization"] == "Bearer SECRET" for item in transport.headers)
        )
        self.assertEqual(len(dataset.evidence), 4)
        self.assertEqual(len(metadata), 4)
        manifest_text = json.dumps(dataset.manifest())
        self.assertNotIn("SECRET", manifest_text)
        self.assertEqual(len(dataset.manifest()["source_evidence"]), 4)
        self.assertTrue(
            all(
                item["source_reference"]
                for item in dataset.manifest()["source_evidence"]
            )
        )

    def test_one_failed_query_prevents_complete_coverage(self) -> None:
        class Transport:
            def get(self, url: str, timeout: float) -> HttpResponse:
                dataset_name = parse_qs(urlsplit(url).query)["dataset"][0]
                if dataset_name == "TaiwanStockSplitPrice":
                    payload = {"status": 402, "msg": "rate limit", "data": []}
                else:
                    payload = {"status": 200, "msg": "success", "data": []}
                return HttpResponse(url, 200, json.dumps(payload).encode())

        with patch.dict(os.environ, {"FINMIND_TOKEN": "SECRET"}, clear=False):
            with self.assertRaisesRegex(SourceUnavailableError, "SplitPrice"):
                fetch_finmind_corporate_actions(
                    "2330",
                    "2026-01-01",
                    "2026-12-31",
                    transport=Transport(),
                    retries=0,
                )


if __name__ == "__main__":
    unittest.main()
