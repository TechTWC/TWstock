from datetime import date
import pytest

from twstock_data.sources.twse_valuation import ValuationObservation
from twstock_valuation.pe_river import (
    build_metadata, calculate_rivers, distribution, select_coverage, years_before,
)


def observation(day="2026-09-29", close=600, pe=20):
    return ValuationObservation("2330", date.fromisoformat(day), close, pe)


def test_river_arithmetic():
    row = calculate_rivers([observation()])[0]
    assert row.reference_eps_twd == 30
    assert row.band_prices == (450, 600, 750, 900, 1050)
    assert calculate_rivers([observation()], [10, 40])[0].band_prices == (300, 1200)


@pytest.mark.parametrize("pe", [None, 0, -1, float("nan"), float("inf")])
def test_unavailable_no_implied_eps(pe):
    row = calculate_rivers([observation(pe=pe)])[0]
    assert row.reference_eps_twd is None
    assert row.band_prices == (None,) * 5


def test_quantiles_and_empirical_rank():
    values = [10, 20, 30, 40, 50, None, 0, -1, float("nan")]
    result = distribution(values, 30)
    assert [result[k] for k in ("p10", "p25", "p50", "p75", "p90")] == [14, 20, 30, 40, 46]
    assert result["current_percentile"] == 60
    assert distribution([20, 20, 30], 20)["current_percentile"] == pytest.approx(200 / 3)
    assert distribution([], None)["p50"] is None


def test_max_and_20_year_window():
    rows = [observation("2005-09-02"), observation("2006-09-28"),
            observation("2006-09-29"), observation()]
    selected, start = select_coverage(rows, 20)
    assert start == date(2006, 9, 29)
    assert len(selected) == 2
    selected, start = select_coverage(rows)
    assert start == date(2005, 9, 1)
    assert len(selected) == 4


def test_short_history_not_failure():
    selected, start = select_coverage([observation("2024-01-02"), observation()], 20)
    metadata = build_metadata(calculate_rivers(selected), requested_coverage="20Y", requested_start=start)
    assert metadata["coverage_status"] == "SHORTER_AVAILABLE_HISTORY"
    assert metadata["actual_start_date"] == "2024-01-02"


def test_latest_market_and_latest_valid_are_separate():
    rows = calculate_rivers([observation("2026-09-28", close=600, pe=20), observation(close=610, pe=None)])
    result = build_metadata(rows, requested_coverage="MAX", requested_start=date(2005, 9, 1))
    assert result["latest_market_date"] == "2026-09-29"
    assert result["latest_valid_pe_date"] == "2026-09-28"
    assert result["latest_close"] == 610
    assert result["latest_valid_pe_close"] == 600
    assert result["latest_pe"] == 20
    assert result["missing_pe_count"] == 1
    assert result["valid_pe_observation_count"] == 1
    assert result["percentiles"]["p50"] == 20


@pytest.mark.parametrize("multiples", [[], [20, 15], [20, 20], [0], [-1], [float("inf")]])
def test_invalid_multiples(multiples):
    with pytest.raises(ValueError):
        calculate_rivers([observation()], multiples)


def test_duplicate_order_and_symbol_guards():
    with pytest.raises(ValueError):
        calculate_rivers([observation(), observation()])
    with pytest.raises(ValueError):
        calculate_rivers([observation(), observation("2026-09-28")])
    with pytest.raises(ValueError):
        calculate_rivers([observation("2026-09-28"), ValuationObservation("2303", date(2026, 9, 29), 60, 20)])


def test_leap_year_window():
    assert years_before(date(2024, 2, 29), 5) == date(2019, 2, 28)


def test_internal_empty_source_month_is_a_gap():
    rows = calculate_rivers([observation("2026-07-01"), observation()])
    result = build_metadata(rows, requested_coverage="MAX", requested_start=date(2005, 9, 1),
                            month_results=[{"month": "2026-08", "close_count": 0, "pe_count": 0}])
    assert result["coverage_status"] == "SOURCE_GAPS"
    assert result["incomplete_months"] == ["2026-08"]


def test_nontrading_start_date_does_not_imply_short_history():
    rows = calculate_rivers([observation("2005-09-02"), observation()])
    result = build_metadata(rows, requested_coverage="MAX", requested_start=date(2005, 9, 1))
    assert result["coverage_status"] == "AVAILABLE_HISTORY"
