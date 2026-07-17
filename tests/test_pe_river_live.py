import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from twstock_data.models import MarketDataRecord, SourceTier
from twstock_experiments.pe_river import load_eps_history, load_multiples
from twstock_experiments.pe_river_live import (
    LiveExperimentError,
    build_historical_pe_points,
    calculate_fundamental_context,
    calculate_technical_context,
    empirical_percentile,
    load_monthly_revenue,
    load_quarterly_fundamentals,
    parse_yahoo_quote_payload,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/experiments/2330_pe_river"
FIXTURES = ROOT / "tests/fixtures"


def _record(symbol: str, day: date, close: int) -> MarketDataRecord:
    return MarketDataRecord(
        source="TWSE",
        source_tier=SourceTier.PRIMARY,
        source_symbol=symbol.split(".")[0],
        canonical_symbol=symbol,
        market="TW",
        trade_date=day.isoformat(),
        traded_share_volume=1,
        official_traded_value_twd=1,
        open_price=float(close),
        high_price=float(close),
        low_price=float(close),
        close_price=float(close),
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


def test_technical_context_calculates_ma_and_relative_momentum() -> None:
    start = date(2025, 1, 1)
    stock = tuple(_record("2330.TW", start + timedelta(days=i), 100 + i) for i in range(300))
    benchmark = tuple(_record("0050.TW", start + timedelta(days=i), 100 + i // 2) for i in range(300))
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
