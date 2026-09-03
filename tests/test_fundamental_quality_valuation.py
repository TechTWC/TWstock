from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.fundamental_quality_valuation.backtest import summarize_baselines
from experiments.fundamental_quality_valuation.data import load_universe, normalize_quarterly
from experiments.fundamental_quality_valuation.engine import classify_security
from experiments.fundamental_quality_valuation.models import (
    ClassificationResult,
    SectorLogic,
    SecurityData,
)
from experiments.fundamental_quality_valuation.pit import (
    TemporalRecord,
    available_as_of,
    derive_financial_available_date,
    validate_temporal_record,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/fundamental_quality_valuation_v0_1.json").read_text(encoding="utf-8"))


def _security(sector: SectorLogic = SectorLogic.GENERAL) -> SecurityData:
    period_ends = pd.date_range("2019-03-31", periods=28, freq="QE").date
    rows = []
    for index, period_end in enumerate(period_ends):
        revenue_yoy = 0.08
        eps_yoy = 0.10
        if index == 25:
            revenue_yoy, eps_yoy = -0.18, -0.25
        elif index == 26:
            revenue_yoy, eps_yoy = -0.08, -0.10
        elif index == 27:
            revenue_yoy, eps_yoy = 0.04, 0.06
        rows.append(
            {
                "period_end": period_end,
                "announcement_date": None,
                "available_date": period_end + timedelta(days=60 if period_end.month != 12 else 90),
                "availability_method": "CONSERVATIVE_FILING_LAG_PROXY",
                "timestamp_confidence": "conservative",
                "revenue": 100 + index * 4,
                "gross_profit": 45 + index * 2,
                "operating_income": 20 + index,
                "net_income": 16 + index,
                "eps": 2.0 + index * 0.1,
                "cfo": 22 + index,
                "capex": 5,
                "fcf": 17 + index,
                "ttm_revenue": 400 * (1.08 ** (index / 4)),
                "ttm_gross_profit": 180 * (1.08 ** (index / 4)),
                "ttm_operating_income": 80 * (1.08 ** (index / 4)),
                "ttm_net_income": 64 * (1.10 ** (index / 4)),
                "ttm_eps": 8 * (1.10 ** (index / 4)),
                "ttm_cfo": 88 * (1.09 ** (index / 4)),
                "ttm_capex": 20,
                "ttm_fcf": 68 * (1.09 ** (index / 4)),
                "equity": 320 * (1.07 ** (index / 4)),
                "assets": 500 * (1.07 ** (index / 4)),
                "liabilities": 180,
                "cash": 70,
                "debt": 40,
                "net_debt": -30,
                "net_debt_equity": -0.10,
                "debt_equity": 0.13,
                "current_ratio": 1.8,
                "gross_margin": 0.45,
                "operating_margin": 0.20,
                "net_margin": 0.16,
                "roe": 0.18,
                "roa": 0.08,
                "roic": 0.15,
                "cfo_net_income": 1.25,
                "revenue_yoy": revenue_yoy,
                "eps_yoy": eps_yoy,
                "fcf_yoy": 0.05 + max(eps_yoy, -0.05),
                "operating_margin_change": 0.01,
                "equity_yoy": 0.07,
            }
        )
    quarterly = pd.DataFrame(rows)
    market_dates = pd.bdate_range("2019-01-01", "2026-09-03").date
    market = pd.DataFrame(
        {
            "date": market_dates,
            "close": np.linspace(60, 160, len(market_dates)),
            "max": np.linspace(61, 161, len(market_dates)),
            "min": np.linspace(59, 159, len(market_dates)),
            "PER": np.linspace(10, 24, len(market_dates)),
            "PBR": np.linspace(1.5, 4.0, len(market_dates)),
            "dividend_yield": np.linspace(4.0, 1.5, len(market_dates)),
        }
    )
    return SecurityData(
        symbol="9999",
        company="Synthetic",
        industry="Test Industry",
        sector_logic=sector,
        quarterly=quarterly,
        market=market,
        data_flags=["AVAILABLE_DATE_PROXY", "UNADJUSTED_PRICE_RETURN"],
    )


def test_universe_has_exactly_fifty_unique_constituents() -> None:
    rows = load_universe(ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv")
    assert len(rows) == 50
    assert len({row["symbol"] for row in rows}) == 50


def test_conservative_availability_proxy_and_pit_filter() -> None:
    assert derive_financial_available_date(date(2025, 3, 31)) == date(2025, 5, 30)
    assert derive_financial_available_date(date(2025, 12, 31)) == date(2026, 3, 31)
    older = TemporalRecord(date(2025, 3, 31), None, date(2025, 5, 30), "vendor", 1, "CONSERVATIVE_FILING_LAG_PROXY")
    future = TemporalRecord(date(2025, 6, 30), None, date(2025, 8, 29), "vendor", 2, "CONSERVATIVE_FILING_LAG_PROXY")
    assert available_as_of((older, future), date(2025, 6, 1)) == (older,)


def test_temporal_ordering_fails_closed() -> None:
    record = TemporalRecord(date(2025, 3, 31), date(2025, 3, 1), date(2025, 5, 1), "vendor", 1, "VERIFIED")
    with pytest.raises(ValueError, match="precedes period_end"):
        validate_temporal_record(record)


def test_turning_up_requires_multi_family_corroboration() -> None:
    security = _security()
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.fundamental_state == "TURNING_UP"
    assert "RECOVERY_CORROBORATED" in result.reason_codes
    assert result.quality == "GOOD"
    assert result.data_quality == "PARTIAL"


def test_future_financial_row_is_not_visible_before_available_date() -> None:
    security = _security()
    as_of = date(2026, 9, 3)
    before = classify_security(security, as_of, CONFIG)
    future = security.quarterly.iloc[-1].copy()
    future["period_end"] = date(2026, 9, 30)
    future["available_date"] = date(2026, 11, 29)
    future["ttm_eps"] = 999999
    security.quarterly = pd.concat([security.quarterly, pd.DataFrame([future])], ignore_index=True)
    after = classify_security(security, as_of, CONFIG)
    assert after.period_end == before.period_end
    assert after.metrics["ttm_eps"] == before.metrics["ttm_eps"]


def test_financial_sector_does_not_apply_general_fcf_gate() -> None:
    security = _security(SectorLogic.FINANCIAL)
    security.quarterly.loc[:, "ttm_fcf"] = -999
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert "SECTOR_LOGIC_FINANCIAL" in result.reason_codes
    assert "GENERAL_FCF_LOGIC_NOT_APPLIED" in result.data_quality_flags
    assert result.quality == "GOOD"


def test_valuation_uses_latest_finite_exchange_observation() -> None:
    security = _security()
    security.market.loc[security.market.index[-1], ["PER", "PBR", "dividend_yield"]] = np.nan
    expected_pe = float(security.market["PER"].dropna().iloc[-1])
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.metrics["pe"] == expected_pe
    assert result.valuation != "N/M"


def test_short_financial_history_is_unknown_and_insufficient() -> None:
    security = _security()
    security.quarterly = security.quarterly.tail(5).reset_index(drop=True)
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.quality == "UNKNOWN"
    assert result.fundamental_state == "UNKNOWN"
    assert result.data_quality == "INSUFFICIENT"
    assert "QUALITY_HISTORY_INSUFFICIENT" in result.reason_codes


def test_cash_flow_ytd_is_deaccumulated() -> None:
    dates = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    financial = []
    balance = []
    cashflow = []
    for index, item in enumerate(dates, start=1):
        for kind, value in (("Revenue", 100), ("GrossProfit", 40), ("OperatingIncome", 20), ("IncomeAfterTaxes", 16), ("PreTaxIncome", 20), ("EPS", 2)):
            financial.append({"date": item, "type": kind, "value": value})
        for kind, value in (("Equity", 100), ("TotalAssets", 200), ("Liabilities", 100), ("CashAndCashEquivalents", 20), ("LongtermBorrowings", 10), ("CurrentAssets", 80), ("CurrentLiabilities", 40)):
            balance.append({"date": item, "type": kind, "value": value})
        cashflow.extend(
            [
                {"date": item, "type": "CashFlowsFromOperatingActivities", "value": index * 30},
                {"date": item, "type": "PropertyAndPlantAndEquipment", "value": index * -5},
            ]
        )
    result = normalize_quarterly(financial, balance, cashflow, CONFIG["financial_availability_lag_days"])
    assert result["cfo"].tolist() == [30, 30, 30, 30]
    assert result["capex"].tolist() == [5, 5, 5, 5]
    assert result["ttm_fcf"].iloc[-1] == 100


def test_outputs_have_no_score_field() -> None:
    assert not any("score" in field.name.lower() for field in fields(ClassificationResult))
    result = classify_security(_security(), date(2026, 9, 3), CONFIG).to_dict()
    assert not any("score" in key.lower() for key in result)


def test_all_required_baselines_are_emitted() -> None:
    events = pd.DataFrame(
        {
            "period_end": ["2025-03-31"] * 4,
            "quality": ["GOOD", "GOOD", "WEAK", "ACCEPTABLE"],
            "fundamental_state": ["TURNING_UP", "CONFIRMED_GROWTH", "DETERIORATING", "UNKNOWN"],
            "valuation": ["LOW", "NORMAL", "LOW", "HIGH"],
            "pe_percentile": [0.1, 0.5, 0.2, 0.9],
            "pb_percentile": [0.2, 0.5, 0.1, 0.9],
            "roe_cross_sectional_percentile": [1.0, 0.75, 0.5, 0.25],
            "revenue_yoy_cross_sectional_percentile": [1.0, 0.75, 0.5, 0.25],
            **{
                f"{metric}_{horizon}d": [0.1, 0.05, -0.1, 0.0]
                for horizon in CONFIG["backtest"]["forward_horizons"]
                for metric in ("return", "excess_return", "mfe", "mae", "max_drawdown")
            },
        }
    )
    summary = summarize_baselines(events, CONFIG)
    assert set(summary["baseline"]) == {
        "A_ALL_CURRENT_0050",
        "B_LOW_PE",
        "C_LOW_PB",
        "D_HIGH_ROE",
        "E_HIGH_REVENUE_GROWTH",
        "F_QUALITY_ONLY",
        "G_VALUATION_ONLY",
        "H_FULL_MODEL",
    }
