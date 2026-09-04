from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.fundamental_quality_valuation.backtest import build_backtest_events, summarize_baselines
from experiments.fundamental_quality_valuation.data import load_universe, normalize_quarterly
from experiments.fundamental_quality_valuation.engine import _cagr, classify_security
from experiments.fundamental_quality_valuation.models import (
    ClassificationResult,
    SectorLogic,
    SecurityData,
)
from experiments.fundamental_quality_valuation.validation import (
    ALL_STATES,
    confusion_matrix,
    realized_fundamental_state,
    state_accuracy_metrics,
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
                "availability_method": "AVAILABLE_DATE_PROXY",
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
    older = TemporalRecord(date(2025, 3, 31), None, date(2025, 5, 30), "vendor", 1, "AVAILABLE_DATE_PROXY")
    future = TemporalRecord(date(2025, 6, 30), None, date(2025, 8, 29), "vendor", 2, "AVAILABLE_DATE_PROXY")
    assert available_as_of((older, future), date(2025, 6, 1)) == (older,)


def test_temporal_ordering_fails_closed() -> None:
    record = TemporalRecord(date(2025, 3, 31), date(2025, 3, 1), date(2025, 5, 1), "vendor", 1, "VERIFIED")
    with pytest.raises(ValueError, match="precedes period_end"):
        validate_temporal_record(record)


def test_turning_up_requires_multi_family_corroboration() -> None:
    security = _security()
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.fundamental_state == "IMPROVING"
    assert result.state_detail == "TURNING_UP"
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
    assert result.quality == "UNKNOWN"
    assert result.fundamental_state == "UNKNOWN"
    assert result.data_quality == "INSUFFICIENT"
    assert "FINANCIAL_STATE_UNSUPPORTED" in result.reason_codes


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
            "signal_date": ["2025-05-30"] * 4,
            "symbol": ["1", "2", "3", "4"],
            "quality": ["GOOD", "GOOD", "WEAK", "ACCEPTABLE"],
            "fundamental_state": ["IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN"],
            "valuation": ["LOW", "NORMAL", "LOW", "HIGH"],
            "pe_percentile": [0.1, 0.5, 0.2, 0.9],
            "pb_percentile": [0.2, 0.5, 0.1, 0.9],
            "roe_cross_sectional_percentile": [1.0, 0.75, 0.5, 0.25],
            "revenue_yoy_cross_sectional_percentile": [1.0, 0.75, 0.5, 0.25],
            **{
                f"{metric}_{horizon}d": [0.1, 0.05, -0.1, 0.0]
                for horizon in CONFIG["backtest"]["forward_horizons"]
                for metric in (
                    "return",
                    "benchmark_return",
                    "excess_return",
                    "max_close_to_close_favorable_return",
                    "max_close_to_close_adverse_return",
                    "max_drawdown",
                )
            },
        }
    )
    summary = summarize_baselines(events, CONFIG)
    assert set(summary["baseline"]) == {
        "A_0050_BUY_AND_HOLD",
        "B_CURRENT_CONSTITUENT_UNCONDITIONAL",
        "C_STATE_ONLY",
        "D_QUALITY_ONLY",
        "E_VALUATION_ONLY",
        "F_QUALITY_PLUS_VALUATION",
        "G_STATE_PLUS_VALUATION",
        "H_FULL_MODEL",
    }


def test_financial_missing_eps_is_unknown() -> None:
    security = _security(SectorLogic.FINANCIAL)
    security.quarterly.loc[:, "ttm_eps"] = np.nan
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.quality == "UNKNOWN"
    assert result.fundamental_state == "UNKNOWN"
    assert result.data_quality == "INSUFFICIENT"
    assert "FINANCIAL_CORE_MISSING_EPS" in result.reason_codes


def test_abnormal_financial_roe_mapping_fails_closed() -> None:
    security = _security(SectorLogic.FINANCIAL)
    security.quarterly.loc[:, "bvps"] = 20.0
    security.quarterly.loc[security.quarterly.index[-1], "roe"] = 0.71
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.quality == "UNKNOWN"
    assert result.data_quality == "INSUFFICIENT"
    assert "FINANCIAL_ROE_MAPPING_ANOMALY" in result.reason_codes


def test_unstable_source_history_provenance_fails_closed() -> None:
    security = _security(SectorLogic.CYCLICAL)
    security.data_flags.append("SOURCE_HISTORY_PROVENANCE_UNSTABLE")
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.quality == "UNKNOWN"
    assert result.fundamental_state == "UNKNOWN"
    assert result.state_detail == "UNKNOWN"
    assert result.data_quality == "INSUFFICIENT"
    assert "STATE_SOURCE_HISTORY_UNSUPPORTED" in result.reason_codes


def test_missing_pb_does_not_automatically_pass_low_valuation() -> None:
    security = _security()
    security.market.loc[:, "PER"] = 20.0
    security.market.loc[security.market.index[-1], "PER"] = 5.0
    security.market.loc[:, "PBR"] = np.nan
    security.quarterly.loc[:, "ttm_fcf"] = -10.0
    result = classify_security(security, date(2026, 9, 3), CONFIG)
    assert result.metrics["pe_percentile"] <= 0.25
    assert result.metrics["pb"] is None
    assert result.valuation != "LOW"


def test_roic_requires_debt_and_cash_without_zero_imputation() -> None:
    dates = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    financial: list[dict[str, object]] = []
    balance: list[dict[str, object]] = []
    for item in dates:
        for kind, value in (
            ("Revenue", 100),
            ("OperatingIncome", 20),
            ("IncomeAfterTaxes", 15),
            ("PreTaxIncome", 20),
            ("EPS", 2),
        ):
            financial.append({"date": item, "type": kind, "value": value})
        balance.extend(
            [
                {"date": item, "type": "Equity", "value": 100},
                {"date": item, "type": "TotalAssets", "value": 200},
            ]
        )
    normalized = normalize_quarterly(financial, balance, [], CONFIG["financial_availability_lag_days"])
    assert normalized["debt"].isna().all()
    assert normalized["cash"].isna().all()
    assert normalized["roic"].isna().all()


def test_missing_quarter_prevents_cagr() -> None:
    quarterly = _security().quarterly.copy()
    quarterly = quarterly.drop(index=quarterly.index[-6]).reset_index(drop=True)
    assert _cagr(quarterly, "ttm_eps", 3) is None


def test_realized_labels_cannot_change_contemporaneous_signal() -> None:
    security = _security()
    row_index = 22
    as_of = security.quarterly.iloc[row_index]["available_date"]
    before = classify_security(security, as_of, CONFIG)
    first_realized = realized_fundamental_state(
        security.quarterly,
        row_index,
        security.sector_logic,
        CONFIG["realized_state_rules"],
    )
    future_rows = security.quarterly.index > row_index
    for column in ("ttm_revenue", "ttm_eps", "ttm_net_income", "ttm_cfo", "ttm_fcf", "equity"):
        security.quarterly.loc[future_rows, column] *= 0.05
    security.quarterly.loc[future_rows, ["operating_margin", "roe", "roic", "current_ratio"]] = -1.0
    second_realized = realized_fundamental_state(
        security.quarterly,
        row_index,
        security.sector_logic,
        CONFIG["realized_state_rules"],
    )
    after = classify_security(security, as_of, CONFIG)
    assert first_realized["realized_state"] != second_realized["realized_state"]
    assert before.fundamental_state == after.fundamental_state
    assert before.state_detail == after.state_detail


def test_announcement_date_and_proxy_provenance() -> None:
    financial = [
        {"date": "2025-03-31", "announcement_date": "2025-05-12", "type": "Revenue", "value": 100},
        {"date": "2025-06-30", "type": "Revenue", "value": 110},
    ]
    normalized = normalize_quarterly(financial, [], [], CONFIG["financial_availability_lag_days"])
    assert normalized.loc[0, "announcement_date"] == date(2025, 5, 12)
    assert normalized.loc[0, "available_date"] == date(2025, 5, 12)
    assert normalized.loc[0, "availability_method"] == "ACTUAL_ANNOUNCEMENT_DATE"
    assert pd.isna(normalized.loc[1, "announcement_date"])
    assert normalized.loc[1, "availability_method"] == "AVAILABLE_DATE_PROXY"


def test_504_trading_day_horizon_is_emitted() -> None:
    assert 504 in CONFIG["backtest"]["forward_horizons"]
    security = _security()
    events = build_backtest_events(
        [security], security.market[["date", "close"]].copy(), CONFIG, date(2026, 9, 3)
    )
    assert "return_504d" in events
    assert events["return_504d"].notna().any()


def test_manifest_records_generation_head(tmp_path: Path) -> None:
    from scripts.run_0050_fundamental_v0_1 import _write_manifest
    import subprocess

    security = _security()
    security.source_metadata = {"source_hash": "a" * 64}
    (tmp_path / "sample.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _write_manifest(tmp_path, CONFIG, [security])
    manifest = json.loads((tmp_path / "artifact_manifest.json").read_text(encoding="utf-8"))
    expected = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert manifest["commit_sha"] == expected
    assert manifest["generation_commit_sha"] == expected
    assert len(manifest["config_hash"]) == 64
    assert len(manifest["data_snapshot_identity"]) == 64


def test_canonical_confusion_matrix_is_complete() -> None:
    events = pd.DataFrame(
        {
            "fundamental_state": ["IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN"],
            "realized_fundamental_state": ["IMPROVING", "STABLE", "STABLE", "DETERIORATING"],
            "lead_lag_quarters": [1, 0, 0, 2],
            "transition_confirmed": [True, True, True, True],
            "realized_persistent": [True, True, False, False],
        }
    )
    matrix = confusion_matrix(events)
    assert len(matrix) == len(ALL_STATES) ** 2
    assert set(matrix["predicted_state"]) == set(ALL_STATES)
    assert set(matrix["realized_state"]) == set(ALL_STATES)
    metrics = state_accuracy_metrics(events)
    assert set(metrics["state"]) == {"IMPROVING", "STABLE", "DETERIORATING"}
    assert metrics["support"].sum() == 4


def test_generated_artifacts_are_parseable_finite_and_hashed() -> None:
    artifact_dir = ROOT / "artifacts/0050_fundamental_v0_1"
    required = {
        "0050_current_state_matrix_v0.1.csv",
        "0050_normalized_financials_pit_v0.1.csv",
        "0050_backtest_events_v0.1.csv",
        "0050_state_confusion_matrix_v0.1.csv",
        "0050_state_accuracy_metrics_v0.1.csv",
        "0050_return_diagnostics_v0.1.csv",
        "0050_fundamental_quality_valuation_backtest_v0.1.json",
        "0050_fundamental_quality_valuation_backtest_v0.1.pdf",
        "artifact_manifest.json",
    }
    assert required.issubset({path.name for path in artifact_dir.iterdir()})
    payload = json.loads(
        (artifact_dir / "0050_fundamental_quality_valuation_backtest_v0.1.json").read_text(
            encoding="utf-8"
        )
    )

    def assert_finite(value: object) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for item in value.values():
                assert_finite(item)
        elif isinstance(value, list):
            for item in value:
                assert_finite(item)

    assert_finite(payload)
    for csv_path in artifact_dir.glob("*.csv"):
        frame = pd.read_csv(csv_path, low_memory=False)
        numeric = frame.select_dtypes(include=[np.number])
        assert not np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any(), csv_path.name
    manifest = json.loads((artifact_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["artifacts"]:
        path = artifact_dir / item["path"]
        assert path.exists()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
