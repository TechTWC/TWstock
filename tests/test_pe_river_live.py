import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from twstock_data.models import MarketDataRecord, SourceTier
from twstock_experiments.pe_river import load_eps_history, load_multiples, ttm_eps_as_of
from twstock_experiments.pe_river_live_metrics import (
    DEFAULT_HORIZONS,
    HistoricalPEPoint,
    build_forward_pe_context,
    build_historical_forward_pe_points,
    build_historical_pe_points,
    build_multi_horizon_diagnostic,
    calculate_fundamental_context,
    calculate_technical_context,
    empirical_percentile,
    summarize_multi_horizon,
)
from twstock_experiments.pe_river_live_sources import (
    LiveExperimentError,
    load_forward_eps_vintages,
    load_monthly_revenue,
    load_quarterly_fundamentals,
    parse_yahoo_quote_payload,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/experiments/2330_pe_river"
FIXTURES = ROOT / "tests/fixtures"


def _record(symbol: str, day: date, close: int | Decimal) -> MarketDataRecord:
    price = float(close)
    return MarketDataRecord(
        source="TWSE",
        source_tier=SourceTier.PRIMARY,
        source_symbol=symbol.split(".")[0],
        canonical_symbol=symbol,
        market="TW",
        trade_date=day.isoformat(),
        traded_share_volume=1,
        official_traded_value_twd=1,
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        transaction_count=1,
        retrieved_at="2026-07-17T00:00:00Z",
        source_reference="fixture",
        raw_content_hash="fixture",
    )


def test_parses_delayed_yahoo_quote_with_explicit_secondary_status() -> None:
    payload = json.loads((FIXTURES / "yahoo_2330_delayed.json").read_text())
    quote = parse_yahoo_quote_payload(
        payload, expected_symbol="2330.TW", source_url="https://example.test"
    )
    assert quote.price_twd == Decimal("2390.0")
    assert quote.previous_close_twd == Decimal("2470.0")
    assert quote.data_status == "SECONDARY_DELAYED_QUOTE"
    assert quote.source_tier == "SECONDARY"
    assert quote.observed_at.endswith("+08:00")


def test_rejects_quote_symbol_mismatch() -> None:
    payload = json.loads((FIXTURES / "yahoo_2330_delayed.json").read_text())
    with pytest.raises(LiveExperimentError, match="symbol mismatch"):
        parse_yahoo_quote_payload(payload, expected_symbol="0050.TW")


def test_empirical_percentile_is_deterministic() -> None:
    assert empirical_percentile(
        [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")],
        Decimal("25"),
    ) == Decimal("50")
    assert empirical_percentile([], Decimal("25")) is None


def test_eps_history_supports_complete_five_year_pit_river() -> None:
    history = load_eps_history(DATA / "eps_history.csv")
    assert history[0].period == "2020Q1"
    assert history[-1].period == "2026Q2"
    assert len(history) == 26

    ttm, periods = ttm_eps_as_of(history, date(2021, 7, 16))
    assert ttm == Decimal("21.38")
    assert periods == ("2020Q3", "2020Q4", "2021Q1", "2021Q2")


def test_historical_pe_uses_only_pit_available_eps() -> None:
    eps = load_eps_history(DATA / "eps_history.csv")
    multiples = load_multiples(DATA / "river_multiples.csv")
    records = (
        _record("2330.TW", date(2026, 7, 16), 2470),
        _record("2330.TW", date(2026, 7, 17), 2390),
    )
    points = build_historical_pe_points(records, eps, multiples)
    assert points[0].ttm_eps_twd == Decimal("74.38")
    assert points[1].ttm_eps_twd == Decimal("86.27")
    assert points[1].bands["28"] == Decimal("2415.56")


def test_historical_pe_respects_requested_analysis_window() -> None:
    eps = load_eps_history(DATA / "eps_history.csv")
    multiples = load_multiples(DATA / "river_multiples.csv")
    records = (
        _record("2330.TW", date(2021, 1, 15), 600),
        _record("2330.TW", date(2021, 7, 19), 580),
        _record("2330.TW", date(2026, 7, 17), 2390),
    )
    points = build_historical_pe_points(
        records,
        eps,
        multiples,
        start_date=date(2021, 7, 17),
        end_date=date(2026, 7, 17),
    )
    assert [point.trade_date for point in points] == [
        date(2021, 7, 19),
        date(2026, 7, 17),
    ]


def test_forward_pe_fails_closed_without_verified_vintages() -> None:
    vintages = load_forward_eps_vintages(DATA / "forward_eps_vintages.csv")
    assert vintages == []
    context = build_forward_pe_context(
        quote_date=date(2026, 7, 17),
        quote_price=Decimal("2390"),
        vintages=vintages,
        historical_points=[],
    )
    assert context["status"] == "HISTORICAL_FORWARD_PE_UNAVAILABLE_NO_VERIFIED_VINTAGES"
    assert context["historical_forward_pe_percentile"] is None


def test_forward_pe_vintages_are_applied_without_lookahead(tmp_path: Path) -> None:
    path = tmp_path / "forward.csv"
    path.write_text(
        "as_of_date,ntm_eps_twd,source_name,data_status,source_url,source_note\n"
        "2025-01-01,60,TestConsensus,VERIFIED_ANALYST_CONSENSUS_VINTAGE,https://example.test/a,first\n"
        "2025-07-01,70,TestConsensus,VERIFIED_ANALYST_CONSENSUS_VINTAGE,https://example.test/b,second\n",
        encoding="utf-8",
    )
    vintages = load_forward_eps_vintages(path)
    records = (
        _record("2330.TW", date(2024, 12, 31), 100),
        _record("2330.TW", date(2025, 1, 2), 120),
        _record("2330.TW", date(2025, 6, 30), 130),
        _record("2330.TW", date(2025, 7, 2), 140),
    )
    points = build_historical_forward_pe_points(records, vintages)
    assert [point.trade_date for point in points] == [
        date(2025, 1, 2),
        date(2025, 6, 30),
        date(2025, 7, 2),
    ]
    assert [point.ntm_eps_twd for point in points] == [
        Decimal("60"),
        Decimal("60"),
        Decimal("70"),
    ]
    context = build_forward_pe_context(
        quote_date=date(2025, 7, 2),
        quote_price=Decimal("140"),
        vintages=vintages,
        historical_points=points,
    )
    assert context["current_forward_pe"] == Decimal("2")
    assert context["status"] == "INSUFFICIENT_VERIFIED_FORWARD_PE_HISTORY"


def test_forward_pe_rejects_manual_scenarios_as_history(tmp_path: Path) -> None:
    path = tmp_path / "forward.csv"
    path.write_text(
        "as_of_date,ntm_eps_twd,source_name,data_status,source_url,source_note\n"
        "2025-01-01,60,Manual,ILLUSTRATIVE_MANUAL_ASSUMPTION,https://example.test,not consensus\n",
        encoding="utf-8",
    )
    with pytest.raises(
        Exception, match="VERIFIED_ANALYST_CONSENSUS_VINTAGE"
    ):
        load_forward_eps_vintages(path)


def test_technical_context_calculates_ma_and_relative_momentum() -> None:
    start = date(2025, 1, 1)
    stock = tuple(
        _record("2330.TW", start + timedelta(days=index), 100 + index)
        for index in range(300)
    )
    benchmark = tuple(
        _record("0050.TW", start + timedelta(days=index), 100 + index // 2)
        for index in range(300)
    )
    context = calculate_technical_context(stock, benchmark, Decimal("410"))
    assert context["ma50_twd"] == Decimal("374.5")
    assert context["ma200_twd"] == Decimal("299.5")
    assert context["relative_momentum_12_1_pct"] is not None


def test_fundamental_context_exposes_latest_margins_and_revenue_yoy() -> None:
    quarterly = load_quarterly_fundamentals(DATA / "quarterly_fundamentals.csv")
    monthly = load_monthly_revenue(DATA / "monthly_revenue.csv")
    context = calculate_fundamental_context(
        quarterly, monthly, as_of_date=date(2026, 7, 17)
    )
    assert context["latest_quarter"]["period"] == "2026Q2"
    assert context["gross_margin_qoq_ppt"] == Decimal("1.5")
    assert context["operating_margin_yoy_ppt"] == Decimal("10.7")
    assert context["latest_monthly_revenue_yoy"]["month"] == "2026-06"
    assert context["latest_3m_average_revenue_yoy_pct"] > Decimal("30")


def test_multi_horizon_diagnostic_extends_to_one_year() -> None:
    start = date(2022, 1, 1)
    stock = tuple(
        _record(
            "2330.TW",
            start + timedelta(days=index),
            Decimal("100") + Decimal(index) / Decimal("10"),
        )
        for index in range(1500)
    )
    benchmark = tuple(
        _record(
            "0050.TW",
            start + timedelta(days=index),
            Decimal("100") + Decimal(index) / Decimal("20"),
        )
        for index in range(1500)
    )
    pe_points = []
    for index, record in enumerate(stock):
        close = Decimal(str(record.close_price))
        pe = Decimal("12") + Decimal(index % 400) / Decimal("25")
        pe_points.append(
            HistoricalPEPoint(
                trade_date=date.fromisoformat(record.trade_date),
                close_twd=close,
                ttm_eps_twd=close / pe,
                pe_ttm=pe,
                bands={"20": close / pe * Decimal("20")},
            )
        )

    rows = build_multi_horizon_diagnostic(
        stock, benchmark, pe_points, horizons=DEFAULT_HORIZONS
    )
    assert {row["horizon_sessions"] for row in rows} == set(DEFAULT_HORIZONS)
    summaries = summarize_multi_horizon(rows, horizons=DEFAULT_HORIZONS)
    assert any(
        item["horizon_label"] == "12M" and item["bucket"] == "ALL"
        for item in summaries
    )
    assert any(
        item["horizon_label"] == "3M"
        and item["average_excess_return_pct"] is not None
        for item in summaries
    )
