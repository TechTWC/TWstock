from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest

from twstock_data.errors import DataValidationError
from twstock_data.http import HttpResponse
from twstock_data.sources.twse_corporate_actions import (
    CAPITAL_REDUCTION_CASH_RETURN, CAPITAL_REDUCTION_LOSS,
    CORPORATE_ACTION_REVIEW_REQUIRED, NORMALIZATION_READY, STOCK_DIVIDEND,
    UNSUPPORTED_ACTION, CorporateActionEvent,
    build_ex_right_url, build_reduction_url, fetch_corporate_action_history,
    mark_conflicting_duplicates, parse_ex_right_events, parse_reduction_events,
)
from twstock_data.sources.twse_valuation import ValuationObservation
from twstock_valuation.corporate_actions import (
    NORMALIZED, NORMALIZATION_COVERAGE_START,
    NORMALIZED_PERCENTILE_COMPLETE, NORMALIZED_PERCENTILE_INCOMPLETE,
    PE_UNAVAILABLE, SOURCE_COVERAGE_INCOMPLETE,
    build_corporate_action_metadata, normalize_for_corporate_actions,
    normalized_distributions,
)
from twstock_valuation.pe_river import build_metadata, calculate_rivers

FIXTURES = Path(__file__).parent / "fixtures"
OFFICIAL = "https://www.twse.com.tw/rwd/zh/"


def event(day="2026-09-02", factor=3.0, action=STOCK_DIVIDEND,
          status=NORMALIZATION_READY, symbol="6669", cash=None):
    return CorporateActionEvent(
        symbol=symbol, effective_date=date.fromisoformat(day), action_type=action,
        share_factor=factor, cash_return_per_share=cash, pre_event_close=7800,
        official_reference_price=2600, source_url=OFFICIAL + "summary",
        detail_source_url=OFFICIAL + "detail", retrieved_at="2026-10-01T00:00:00Z",
        raw_hash="0" * 64, status=status,
    )


def observation(day, close, pe, period_end, symbol="6669"):
    raw = None if period_end is None else f"{period_end.year - 1911}/{(period_end.month - 1) // 3 + 1}"
    return ValuationObservation(symbol, date.fromisoformat(day), close, pe,
                                financial_report_period_raw=raw,
                                reference_period_end=period_end)


def test_official_6669_ex_right_contract():
    summary = (FIXTURES / "twse_ex_right_6669_20260902.json").read_bytes()
    detail = (FIXTURES / "twse_ex_right_detail_6669_20260902.json").read_bytes()
    source = build_ex_right_url(date(2026, 9, 2), date(2026, 9, 2))
    events = parse_ex_right_events(
        summary, {("6669", date(2026, 9, 2)): detail}, "6669", source,
        "2026-10-01T00:00:00Z")
    assert len(events) == 1
    result = events[0]
    assert result.action_type == STOCK_DIVIDEND
    assert result.effective_date == date(2026, 9, 2)
    assert result.bonus_share_rate == pytest.approx(1.9828)
    assert result.cash_rights_rate == 0
    assert result.share_factor == pytest.approx(2.9828)
    assert result.pre_event_close == 7800
    assert result.official_reference_price == 2614.99
    assert result.status == NORMALIZATION_READY
    assert result.derived is False


def test_official_2603_reduction_contract():
    summary = (FIXTURES / "twse_reduction_2603_2022.json").read_bytes()
    detail = (FIXTURES / "twse_reduction_detail_2603_20220906.json").read_bytes()
    source = build_reduction_url(date(2022, 1, 1), date(2022, 12, 31))
    events = parse_reduction_events(
        summary, {("2603", "20220906"): detail}, "2603", source,
        "2026-10-01T00:00:00Z")
    assert len(events) == 1
    result = events[0]
    assert result.action_type == CAPITAL_REDUCTION_CASH_RETURN
    assert result.reduction_type == "退還股款"
    assert result.effective_date == result.resume_date == date(2022, 9, 19)
    assert result.share_factor == pytest.approx(.4)
    assert result.cash_return_per_share == 6
    assert result.pre_event_close == 80.8
    assert result.official_reference_price == 187
    assert result.status == NORMALIZATION_READY
    assert result.derived is False


def test_capital_reduction_loss_parser_is_normalization_ready():
    summary = json.loads((FIXTURES / "twse_reduction_2603_2022.json").read_text())
    summary["data"][0][summary["fields"].index("減資原因")] = "彌補虧損"
    detail = (FIXTURES / "twse_reduction_detail_2603_20220906.json").read_bytes()
    source = build_reduction_url(date(2022, 1, 1), date(2022, 12, 31))
    result = parse_reduction_events(
        json.dumps(summary, ensure_ascii=False).encode(),
        {("2603", "20220906"): detail}, "2603", source,
        "2026-10-01T00:00:00Z")[0]
    assert result.action_type == CAPITAL_REDUCTION_LOSS
    assert result.share_factor == pytest.approx(.4)
    assert result.status == NORMALIZATION_READY


def test_unknown_reduction_reason_is_review_required_and_never_enters_factors():
    summary = json.loads((FIXTURES / "twse_reduction_2603_2022.json").read_text())
    summary["data"][0][summary["fields"].index("減資原因")] = "合併換股"
    detail = (FIXTURES / "twse_reduction_detail_2603_20220906.json").read_bytes()
    source = build_reduction_url(date(2022, 1, 1), date(2022, 12, 31))
    result = parse_reduction_events(
        json.dumps(summary, ensure_ascii=False).encode(),
        {("2603", "20220906"): detail}, "2603", source,
        "2026-10-01T00:00:00Z")[0]
    assert result.action_type == UNSUPPORTED_ACTION
    assert result.status == CORPORATE_ACTION_REVIEW_REQUIRED

    before, after = normalize_for_corporate_actions([
        observation("2022-09-06", 80.8, 1.17, date(2022, 6, 30), "2603"),
        observation("2022-09-19", 169, 2.45, date(2022, 6, 30), "2603"),
    ], [result], analysis_end_date=date(2022, 9, 19))
    assert before.future_share_factor is None
    assert before.adjusted_close is None
    assert after.pending_share_factor is None
    assert after.normalized_pe is None


def test_unknown_action_cannot_be_constructed_as_normalization_ready():
    with pytest.raises(DataValidationError, match="unsupported corporate-action type"):
        event(action="MERGER_SHARE_EXCHANGE", factor=.5)


def test_three_for_one_pending_until_reference_quarter_catches_up():
    action = event()
    q2 = date(2026, 6, 30)
    q3 = date(2026, 9, 30)
    rows = normalize_for_corporate_actions([
        observation("2026-09-03", 147, 7, q2),
        observation("2026-10-01", 150, 7.5, q3),
    ], [action])
    assert rows[0].pending_share_factor == 3
    assert rows[0].normalized_pe == 21
    assert rows[0].normalized_reference_eps_local == 7
    assert rows[1].pending_share_factor == 1
    assert rows[1].normalized_pe == 7.5


def test_sixty_percent_reduction_normalizes_stale_pe():
    reduction = event("2022-09-19", .4, CAPITAL_REDUCTION_CASH_RETURN,
                      symbol="2603", cash=6)
    row = normalize_for_corporate_actions([
        observation("2022-09-20", 187, 20, date(2022, 6, 30), "2603")
    ], [reduction])[0]
    assert row.pending_share_factor == .4
    assert row.normalized_pe == 8
    assert row.normalized_reference_eps_local == pytest.approx(23.375)


def test_latest_share_basis_adjusts_pre_event_price_and_river():
    rows = normalize_for_corporate_actions([
        observation("2026-09-01", 7800, 21, date(2026, 6, 30)),
        observation("2026-09-03", 2610, 7, date(2026, 6, 30)),
    ], [event()])
    assert rows[0].future_share_factor == 3
    assert rows[0].adjusted_close == 2600
    assert rows[0].adjusted_reference_eps == pytest.approx((7800 / 21) / 3)
    assert rows[1].future_share_factor == 1
    assert rows[1].normalized_pe == 21


def test_multiple_action_factors_multiply_deterministically():
    events = [event("2026-07-01", 2), event("2026-09-02", 3)]
    row = normalize_for_corporate_actions([
        observation("2026-09-03", 100, 5, date(2026, 3, 31))
    ], events)[0]
    assert row.pending_share_factor == 6
    assert row.normalized_pe == 30


@pytest.mark.parametrize("symbol", ["2330", "2454", "2317"])
def test_no_event_is_identical_to_old_calculation(symbol):
    row = normalize_for_corporate_actions([
        observation("2026-09-01", 600, 20, date(2026, 6, 30), symbol)
    ], [])[0]
    assert row.pending_share_factor == 1
    assert row.future_share_factor == 1
    assert row.normalized_pe == 20
    assert row.raw_implied_reference_eps == row.normalized_reference_eps_local == 30
    assert row.adjusted_close == 600
    assert row.adjusted_band_prices == (450, 600, 750, 900, 1050)


def test_missing_pe_stays_unavailable():
    row = normalize_for_corporate_actions([
        observation("2026-09-03", 150, None, date(2026, 6, 30))
    ], [event()])[0]
    assert row.normalization_status == PE_UNAVAILABLE
    assert row.raw_implied_reference_eps is None
    assert row.normalized_pe is None
    assert row.normalized_reference_eps_local is None
    assert row.adjusted_reference_eps is None
    assert row.adjusted_band_prices == (None,) * 5


def test_missing_pe_and_period_do_not_block_prior_normalized_distribution():
    rows = normalize_for_corporate_actions([
        observation("2026-09-30", 2090, 6.7, date(2026, 6, 30)),
        observation("2026-10-01", 2110, None, None),
    ], [event(factor=2.9828)], analysis_end_date=date(2026, 10, 1))
    assert rows[-1].normalization_status == PE_UNAVAILABLE
    assert rows[-1].normalized_pe is None
    assert rows[-1].adjusted_reference_eps is None
    assert rows[-1].adjusted_band_prices == (None,) * 5
    result = normalized_distributions(rows)
    assert result["normalization_status"] == NORMALIZED_PERCENTILE_COMPLETE
    assert result["normalized_pe_distribution"]["current_percentile"] == 100


def test_review_required_event_blocks_normalized_percentile():
    unresolved = event(status=CORPORATE_ACTION_REVIEW_REQUIRED)
    rows = normalize_for_corporate_actions([
        observation("2026-09-03", 150, 7, date(2026, 6, 30))
    ], [unresolved])
    assert rows[0].normalization_status == CORPORATE_ACTION_REVIEW_REQUIRED
    assert rows[0].normalized_pe is None
    result = normalized_distributions(rows)
    assert result["normalization_status"] == NORMALIZED_PERCENTILE_INCOMPLETE
    assert result["normalized_pe_distribution"] is None
    assert result["raw_pe_distribution"]["p50"] == 7


def test_complete_normalized_percentile_uses_normalized_pe():
    rows = normalize_for_corporate_actions([
        observation("2026-09-03", 150, 7, date(2026, 6, 30)),
        observation("2026-09-04", 156, 8, date(2026, 6, 30)),
    ], [event()])
    result = normalized_distributions(rows)
    assert result["normalization_status"] == NORMALIZED_PERCENTILE_COMPLETE
    assert result["raw_pe_distribution"]["p50"] == 7.5
    assert result["normalized_pe_distribution"]["p50"] == 22.5


def test_pre_2011_rows_fail_closed_but_keep_raw_evidence():
    row = normalize_for_corporate_actions([
        observation("2010-12-31", 100, 10, date(2010, 9, 30))
    ], [])[0]
    assert NORMALIZATION_COVERAGE_START == date(2011, 1, 1)
    assert row.normalization_status == SOURCE_COVERAGE_INCOMPLETE
    assert row.raw_implied_reference_eps == 10
    assert row.pending_share_factor is None
    assert row.future_share_factor is None
    assert row.normalized_pe is None
    assert row.normalized_reference_eps_local is None
    assert row.adjusted_close is None
    assert row.adjusted_reference_eps is None
    assert row.adjusted_band_prices == (None,) * 5


def test_max_spanning_pre_2011_has_no_normalized_distribution():
    rows = normalize_for_corporate_actions([
        observation("2010-12-31", 100, 10, date(2010, 9, 30)),
        observation("2011-01-03", 110, 11, date(2010, 12, 31)),
    ], [])
    result = normalized_distributions(rows)
    assert result["normalization_status"] == NORMALIZED_PERCENTILE_INCOMPLETE
    assert result["normalized_pe_distribution"] is None
    assert result["raw_pe_distribution"]["p50"] == 10.5


def test_post_2019_6669_coverage_remains_fully_normalized():
    observations = [
        observation("2026-09-01", 7800, 20, date(2026, 6, 30)),
        observation("2026-09-03", 2090, 6.7, date(2026, 6, 30)),
    ]
    action = event(factor=2.9828)
    rows = normalize_for_corporate_actions(observations, [action])
    raw = calculate_rivers(observations)
    base = build_metadata(
        raw, requested_coverage="MAX", requested_start=date(2019, 3, 27))
    metadata = build_corporate_action_metadata(rows, [action], base)
    assert rows[-1].normalized_pe == pytest.approx(19.98476)
    assert metadata["normalization_status"] == NORMALIZED
    assert metadata["normalized_pe_distribution"] is not None


def test_metadata_canonical_contract_and_compatibility_aliases():
    observations = [observation("2026-09-03", 2090, 6.7, date(2026, 6, 30))]
    action = event(factor=2.9828)
    rows = normalize_for_corporate_actions(observations, [action])
    base = build_metadata(
        calculate_rivers(observations), requested_coverage="MAX",
        requested_start=date(2019, 3, 27))
    metadata = build_corporate_action_metadata(rows, [action], base)
    assert metadata["corporate_action_mode"] == "LATEST_SHARE_COUNT"
    assert metadata["corporate_actions"] == metadata["corporate_action_events"]
    assert metadata["supported_action_count"] == 1
    assert metadata["unsupported_action_count"] == 0
    assert metadata["latest_official_pe"] == metadata["latest_pe"] == 6.7
    assert metadata["latest_normalized_pe"] == pytest.approx(19.98476)
    assert metadata["raw_pe_percentile"] == 100
    assert metadata["normalized_pe_percentile"] == 100
    assert metadata["normalization_coverage_start"] == "2011-01-01"
    assert metadata["normalization_status"] == NORMALIZED


def test_conflicting_duplicate_events_are_fail_closed():
    events = mark_conflicting_duplicates([event(factor=2), event(factor=3)])
    assert len(events) == 2
    assert all(item.status == CORPORATE_ACTION_REVIEW_REQUIRED for item in events)


@pytest.mark.parametrize("factor", [0, -1, float("nan"), float("inf")])
def test_invalid_share_factor_rejected(factor):
    with pytest.raises(DataValidationError):
        event(factor=factor)


def test_cash_return_gap_is_not_forced_to_total_return_continuity():
    reduction = event("2022-09-19", .4, CAPITAL_REDUCTION_CASH_RETURN,
                      symbol="2603", cash=6)
    rows = normalize_for_corporate_actions([
        observation("2022-09-06", 80.8, 8, date(2022, 6, 30), "2603"),
        observation("2022-09-19", 187, 20, date(2022, 6, 30), "2603"),
    ], [reduction])
    assert rows[0].adjusted_close == pytest.approx(202)
    assert rows[1].adjusted_close == 187
    assert rows[0].adjusted_close - rows[1].adjusted_close == pytest.approx(15)


def test_2603_2022_acceptance_regression():
    reduction = event("2022-09-19", .4, CAPITAL_REDUCTION_CASH_RETURN,
                      symbol="2603", cash=6)
    before, event_day, rollover = normalize_for_corporate_actions([
        observation("2022-09-06", 80.8, 1.17, date(2022, 6, 30), "2603"),
        observation("2022-09-19", 169, 2.45, date(2022, 6, 30), "2603"),
        observation("2022-11-07", 143.5, .79, date(2022, 9, 30), "2603"),
    ], [reduction])
    assert before.future_share_factor == pytest.approx(.4)
    assert before.adjusted_close == pytest.approx(202)
    assert event_day.pending_share_factor == pytest.approx(.4)
    assert event_day.normalized_pe == pytest.approx(.98)
    assert rollover.pending_share_factor == 1
    assert rollover.normalized_pe == pytest.approx(.79)


def test_explicit_cash_rights_is_review_required():
    summary = (FIXTURES / "twse_ex_right_6669_20260902.json").read_bytes()
    detail_path = FIXTURES / "twse_ex_right_detail_6669_20260902.json"
    detail = detail_path.read_text().replace('"0.00000000 股"', '"100.00000000 股"').encode()
    source = build_ex_right_url(date(2026, 9, 2), date(2026, 9, 2))
    result = parse_ex_right_events(
        summary, {("6669", date(2026, 9, 2)): detail}, "6669", source,
        "2026-10-01T00:00:00Z")[0]
    assert result.cash_rights_rate == .1
    assert result.status == CORPORATE_ACTION_REVIEW_REQUIRED


def test_official_history_cache_reuses_integrity_checked_responses(tmp_path):
    summary = (FIXTURES / "twse_ex_right_6669_20260902.json").read_bytes()
    detail = (FIXTURES / "twse_ex_right_detail_6669_20260902.json").read_bytes()
    empty_reduction = json.dumps({
        "stat": "OK",
        "fields": ["恢復買賣日期", "股票代號", "停止買賣前收盤價格",
                   "恢復買賣參考價", "減資原因", "詳細資料"],
        "data": [],
    }).encode()

    class FixtureTransport:
        def __init__(self):
            self.urls = []

        def get(self, url, timeout):
            self.urls.append(url)
            if "/TWT49U?" in url:
                body = summary
            elif "/TWT49UDetail?" in url:
                body = detail
            elif "/TWTAUU?" in url:
                body = empty_reduction
            else:
                raise AssertionError(url)
            return HttpResponse(url, 200, body)

    transport = FixtureTransport()
    result = fetch_corporate_action_history(
        "6669", date(2026, 9, 1), date(2026, 9, 30), tmp_path,
        transport=transport, request_interval=0, refresh_date=date(2027, 1, 1))
    assert len(transport.urls) == 3
    assert len(result.events) == 1
    assert result.events[0].share_factor == pytest.approx(2.9828)
    assert result.events[0].derived is False

    class NoNetwork:
        def get(self, url, timeout):
            raise AssertionError(f"unexpected refetch: {url}")

    cached = fetch_corporate_action_history(
        "6669", date(2026, 9, 1), date(2026, 9, 30), tmp_path,
        transport=NoNetwork(), request_interval=0, refresh_date=date(2027, 1, 1))
    assert cached.events[0].share_factor == pytest.approx(2.9828)
    assert {row["status"] for row in cached.request_results} == {"CACHE_HIT"}
