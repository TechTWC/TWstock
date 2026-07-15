from __future__ import annotations

import csv
import json
import math
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from twstock_engine.actions import resolve_primary_action
from twstock_engine.models import InputValidationError, Settings, StockSnapshot
from twstock_engine.rules import (
    calculate_absolute_pe_status,
    evaluate_earnings_direction,
    evaluate_eligibility,
    evaluate_fundamental_status,
)
from twstock_engine.runner import load_snapshots, run, screen_snapshot


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Settings.load(ROOT / "config/settings.yaml")

def csv_row(**overrides: str) -> dict[str, str]:
    row = {
        "symbol": "2330.TW",
        "name": "Canonical Test",
        "market": "TW",
        "security_type": "COMMON",
        "price_date": "2026-07-10",
        "required_data_valid": "true",
        "financial_data_usable": "true",
        "average_turnover_20d": "30000000",
        "market_cap": "1000",
        "ttm_net_income": "100",
        "ttm_operating_income": "200",
        "ttm_operating_cash_flow": "100",
        "latest_equity": "500",
        "latest_total_assets": "1000",
        "latest_total_liabilities": "400",
        "latest_current_assets": "150",
        "latest_current_liabilities": "100",
        "latest_q_operating_income": "120",
        "previous_q_operating_income": "100",
        "prior_year_q_operating_income": "100",
        "is_synthetic": "true",
        "source_note": "SYNTHETIC TEST DATA ONLY",
    }
    row.update(overrides)
    return row

def snapshot(**overrides: object) -> StockSnapshot:
    values: dict[str, object] = {
        "symbol": "TEST.TW",
        "name": "Synthetic Unit Test",
        "market": "TW",
        "security_type": "COMMON",
        "price_date": date(2026, 7, 10),
        "required_data_valid": True,
        "financial_data_usable": True,
        "average_turnover_20d": 30_000_000.0,
        "market_cap": 1_000.0,
        "ttm_net_income": 100.0,
        "ttm_operating_income": 200.0,
        "ttm_operating_cash_flow": 100.0,
        "latest_equity": 500.0,
        "latest_total_assets": 1_000.0,
        "latest_total_liabilities": 400.0,
        "latest_current_assets": 150.0,
        "latest_current_liabilities": 100.0,
        "latest_q_operating_income": 120.0,
        "previous_q_operating_income": 100.0,
        "prior_year_q_operating_income": 100.0,
        "is_synthetic": True,
        "source_note": "SYNTHETIC TEST DATA ONLY",
    }
    values.update(overrides)
    return StockSnapshot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("pe", "expected"),
    [
        (10.0, "VERY_LOW_VALUATION"),
        (15.0, "ABSOLUTE_CHEAP"),
        (30.0, "FAIR_VALUATION"),
    ],
)
def test_pe_boundary_cases(pe: float, expected: str) -> None:
    result = calculate_absolute_pe_status(
        snapshot(market_cap=pe * 100.0, ttm_net_income=100.0), SETTINGS
    )
    assert result.status == expected
    assert result.pe_ttm == pe


@pytest.mark.parametrize("ttm_net_income", [0.0, -1.0])
def test_nonpositive_ttm_net_income_is_unknown(ttm_net_income: float) -> None:
    result = calculate_absolute_pe_status(
        snapshot(ttm_net_income=ttm_net_income), SETTINGS
    )
    assert result.status == "VALUATION_UNKNOWN"
    assert result.pe_ttm is None


@pytest.mark.parametrize(
    ("overrides", "risk_flag"),
    [
        ({"latest_equity": 0.0}, "NONPOSITIVE_EQUITY"),
        (
            {"ttm_operating_income": 0.0},
            "NONPOSITIVE_TTM_OPERATING_INCOME",
        ),
        (
            {
                "latest_q_operating_income": -1.0,
                "previous_q_operating_income": -2.0,
            },
            "TWO_CONSECUTIVE_NEGATIVE_OPERATING_QUARTERS",
        ),
    ],
)
def test_severe_fundamental_failures(
    overrides: dict[str, float], risk_flag: str
) -> None:
    result = evaluate_fundamental_status(snapshot(**overrides), SETTINGS)
    assert result.status == "FUNDAMENTAL_FAIL"
    assert risk_flag in result.risk_flags


def test_one_warning_remains_fundamental_pass() -> None:
    result = evaluate_fundamental_status(
        snapshot(latest_total_liabilities=800.0), SETTINGS
    )
    assert result.status == "FUNDAMENTAL_PASS"
    assert result.warning_reasons == ("HIGH_DEBT_RATIO",)


def test_two_warnings_become_fundamental_watch() -> None:
    result = evaluate_fundamental_status(
        snapshot(
            ttm_operating_cash_flow=0.0,
            latest_current_assets=80.0,
            latest_current_liabilities=100.0,
        ),
        SETTINGS,
    )
    assert result.status == "FUNDAMENTAL_WATCH"
    assert set(result.warning_reasons) == {
        "NONPOSITIVE_TTM_OPERATING_CASH_FLOW",
        "LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF",
    }


def test_low_current_ratio_with_positive_ocf_is_context_only() -> None:
    result = evaluate_fundamental_status(
        snapshot(
            ttm_operating_cash_flow=1.0,
            latest_current_assets=80.0,
            latest_current_liabilities=100.0,
        ),
        SETTINGS,
    )
    assert result.status == "FUNDAMENTAL_PASS"
    assert result.warning_count == 0
    assert result.informational_tags == ("LOW_CURRENT_RATIO_CONTEXT",)


def test_low_current_ratio_with_zero_ocf_adds_warning() -> None:
    result = evaluate_fundamental_status(
        snapshot(
            ttm_operating_cash_flow=0.0,
            latest_current_assets=80.0,
            latest_current_liabilities=100.0,
        ),
        SETTINGS,
    )
    assert "LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF" in result.warning_reasons
    assert "LOW_CURRENT_RATIO_CONTEXT" not in result.informational_tags


def test_zero_current_liabilities_is_positive_infinity() -> None:
    result = evaluate_fundamental_status(
        snapshot(latest_current_liabilities=0.0), SETTINGS
    )
    assert math.isinf(result.current_ratio)
    assert "LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF" not in result.warning_reasons
    assert "LOW_CURRENT_RATIO_CONTEXT" not in result.informational_tags


def test_current_ratio_exactly_one_has_no_warning_or_context() -> None:
    result = evaluate_fundamental_status(
        snapshot(latest_current_assets=100.0, latest_current_liabilities=100.0),
        SETTINGS,
    )
    assert result.warning_reasons == ()
    assert result.informational_tags == ()


def test_turnaround_positive_has_no_fabricated_yoy() -> None:
    result = evaluate_earnings_direction(
        snapshot(latest_q_operating_income=10.0, prior_year_q_operating_income=0.0),
        SETTINGS,
    )
    assert result.status == "TURNAROUND_POSITIVE"
    assert result.operating_income_yoy is None


def test_earnings_weak_has_negative_yoy() -> None:
    result = evaluate_earnings_direction(
        snapshot(latest_q_operating_income=80.0, prior_year_q_operating_income=100.0),
        SETTINGS,
    )
    assert result.status == "EARNINGS_WEAK"
    assert result.operating_income_yoy == pytest.approx(-0.2)


def test_illiquid_stock_is_not_eligible() -> None:
    result = evaluate_eligibility(snapshot(average_turnover_20d=19_999_999.0), SETTINGS)
    assert result.status == "ILLIQUID"


def test_liquidity_threshold_is_inclusive() -> None:
    result = evaluate_eligibility(snapshot(average_turnover_20d=20_000_000.0), SETTINGS)
    assert result.status == "ELIGIBLE"


def test_financial_data_unusable_forces_data_review() -> None:
    result = screen_snapshot(snapshot(financial_data_usable=False), SETTINGS)
    assert result.action.primary_action == "DATA_REVIEW"
    assert result.action.data_quality_flags == ("FINANCIAL_DATA_UNUSABLE",)


def test_threshold_change_requires_no_rule_code_change() -> None:
    stricter = replace(SETTINGS, tw_min_average_turnover_20d=40_000_000.0)
    result = evaluate_eligibility(snapshot(average_turnover_20d=30_000_000.0), stricter)
    assert result.status == "ILLIQUID"


def test_missing_required_data_flag_forces_data_review() -> None:
    result = screen_snapshot(snapshot(required_data_valid=False), SETTINGS)
    assert result.action.primary_action == "DATA_REVIEW"
    assert result.action.data_quality_flags == ("REQUIRED_DATA_INVALID",)

@pytest.mark.parametrize("symbol", ["2330.TW", "SYN001.TW"])
def test_tw_canonical_symbols_are_accepted(symbol: str) -> None:
    item = StockSnapshot.from_csv_row(csv_row(symbol=symbol))
    assert item.symbol == symbol


@pytest.mark.parametrize("symbol", ["2330", "2330.TWO", "2330.tw", ".TW"])
def test_invalid_tw_canonical_symbols_are_rejected(symbol: str) -> None:
    with pytest.raises(InputValidationError, match="Invalid canonical symbol"):
        StockSnapshot.from_csv_row(csv_row(symbol=symbol))


def test_blank_tw_symbol_is_rejected_as_blank_required_value() -> None:
    with pytest.raises(
        InputValidationError, match="Blank required CSV values: symbol"
    ):
        StockSnapshot.from_csv_row(csv_row(symbol="   "))


def test_load_snapshots_reports_row_number_for_invalid_symbol(tmp_path: Path) -> None:
    input_path = tmp_path / "snapshot.csv"
    row = csv_row(symbol="2330")
    columns = list(row)
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(InputValidationError, match="Row 2: Invalid canonical symbol"):
        load_snapshots(input_path)


def test_csv_missing_required_column_is_rejected() -> None:
    row = {"symbol": "TEST.TW"}
    with pytest.raises(InputValidationError, match="Missing required CSV fields"):
        StockSnapshot.from_csv_row(row)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            {
                "required_data_valid": False,
                "average_turnover_20d": 1.0,
                "latest_equity": 0.0,
            },
            "DATA_REVIEW",
        ),
        (
            {"average_turnover_20d": 1.0, "latest_equity": 0.0},
            "NOT_ELIGIBLE",
        ),
        ({"latest_equity": 0.0}, "EXCLUDE"),
        (
            {
                "ttm_operating_cash_flow": 0.0,
                "latest_current_assets": 80.0,
            },
            "FUNDAMENTAL_REVIEW",
        ),
        (
            {
                "market_cap": 4_000.0,
                "latest_q_operating_income": 80.0,
                "prior_year_q_operating_income": 100.0,
            },
            "VALUATION_WAIT",
        ),
        (
            {
                "market_cap": 1_200.0,
                "latest_q_operating_income": 80.0,
                "prior_year_q_operating_income": 100.0,
            },
            "VALUE_TRAP_REVIEW",
        ),
        ({"market_cap": 1_500.0}, "VALUE_CANDIDATE"),
        ({"market_cap": 3_000.0}, "VALUATION_WATCH"),
    ],
)
def test_primary_action_precedence(case: dict[str, object], expected: str) -> None:
    result = screen_snapshot(snapshot(**case), SETTINGS)
    assert result.action.primary_action == expected


def test_resolve_primary_action_is_pure_and_repeatable() -> None:
    item = snapshot(market_cap=1_000.0)
    eligibility = evaluate_eligibility(item, SETTINGS)
    fundamental = evaluate_fundamental_status(item, SETTINGS)
    valuation = calculate_absolute_pe_status(item, SETTINGS)
    earnings = evaluate_earnings_direction(item, SETTINGS)
    first = resolve_primary_action(
        item, eligibility, fundamental, valuation, earnings
    )
    second = resolve_primary_action(
        item, eligibility, fundamental, valuation, earnings
    )
    assert first == second


def test_sample_run_generates_csv_json_and_html(tmp_path: Path) -> None:
    results = run(
        ROOT / "data/sample/phase_a1_snapshot.csv",
        tmp_path,
        ROOT / "config/settings.yaml",
    )
    assert len(results) == 10
    assert (tmp_path / "screening_results.csv").exists()
    assert (tmp_path / "screening_results.json").exists()
    assert (tmp_path / "report.html").exists()

    payload = json.loads((tmp_path / "screening_results.json").read_text("utf-8"))
    assert payload["release_name"] == "Phase A1 Logic Sandbox v0.1"
    assert len(payload["results"]) == 10

    with (tmp_path / "screening_results.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["warning_reasons"] != rows[0]["informational_tags"]
    assert "LOW_CURRENT_RATIO_CONTEXT" in rows[0]["informational_tags"]
    assert "LOW_CURRENT_RATIO_CONTEXT" not in rows[0]["warning_reasons"]


def test_json_output_serializes_positive_infinity_safely(tmp_path: Path) -> None:
    input_path = tmp_path / "snapshot.csv"
    input_path.write_text(
        "symbol,name,market,security_type,price_date,required_data_valid,"
        "financial_data_usable,average_turnover_20d,market_cap,ttm_net_income,"
        "ttm_operating_income,ttm_operating_cash_flow,latest_equity,"
        "latest_total_assets,latest_total_liabilities,latest_current_assets,"
        "latest_current_liabilities,latest_q_operating_income,"
        "previous_q_operating_income,prior_year_q_operating_income\n"
        "INF.TW,Synthetic Infinity,TW,COMMON,2026-07-10,true,true,30000000,"
        "1000,100,200,100,500,1000,400,100,0,120,100,100\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "outputs"
    run(input_path, output_dir, ROOT / "config/settings.yaml")
    payload = json.loads((output_dir / "screening_results.json").read_text("utf-8"))
    assert payload["results"][0]["current_ratio"] == "Infinity"
