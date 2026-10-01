from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from twstock_data.errors import DataValidationError
from twstock_data.sources.twse_corporate_actions import (
    CAPITAL_REDUCTION_CASH_RETURN, CORPORATE_ACTION_REVIEW_REQUIRED,
    NORMALIZATION_READY, STOCK_DIVIDEND, CorporateActionEvent,
    build_ex_right_url, build_reduction_url, mark_conflicting_duplicates,
    parse_ex_right_events, parse_reduction_events,
)
from twstock_data.sources.twse_valuation import ValuationObservation
from twstock_valuation.corporate_actions import (
    NORMALIZED_PERCENTILE_COMPLETE, NORMALIZED_PERCENTILE_INCOMPLETE,
    PE_UNAVAILABLE, normalize_for_corporate_actions, normalized_distributions,
)

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


def test_no_event_is_identical_to_old_calculation():
    row = normalize_for_corporate_actions([
        observation("2026-09-01", 600, 20, date(2026, 6, 30), "2330")
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
