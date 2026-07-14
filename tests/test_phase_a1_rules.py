from twstock_engine.actions import resolve_primary_action
from twstock_engine.models import StockSnapshot
from twstock_engine.runner import load_settings
from twstock_engine.rules import calculate_absolute_pe_status, evaluate_earnings_direction, evaluate_eligibility, evaluate_fundamental_status

SETTINGS = load_settings("config/settings.yaml")

def snap(**kw):
    base = dict(symbol="T", name="Synthetic Test", market="TW", security_type="COMMON", price_date="2026-06-30", required_data_valid=True, financial_data_usable=True, average_turnover_20d=20_000_000, market_cap=1_000, ttm_net_income=100, ttm_operating_income=100, ttm_operating_cash_flow=100, latest_equity=100, latest_total_assets=100, latest_total_liabilities=50, latest_current_assets=100, latest_current_liabilities=100, latest_q_operating_income=20, previous_q_operating_income=10, prior_year_q_operating_income=10)
    base.update(kw)
    return StockSnapshot(**base)

def test_pe_boundaries_and_unknown():
    assert calculate_absolute_pe_status(snap(market_cap=1000), SETTINGS)[0] == "VERY_LOW_VALUATION"
    assert calculate_absolute_pe_status(snap(market_cap=1500), SETTINGS)[0] == "ABSOLUTE_CHEAP"
    assert calculate_absolute_pe_status(snap(market_cap=3000), SETTINGS)[0] == "FAIR_VALUATION"
    assert calculate_absolute_pe_status(snap(ttm_net_income=0), SETTINGS)[0] == "VALUATION_UNKNOWN"

def test_fundamental_severe_failures():
    assert evaluate_fundamental_status(snap(latest_equity=0), SETTINGS)[0] == "FUNDAMENTAL_FAIL"
    assert evaluate_fundamental_status(snap(ttm_operating_income=0), SETTINGS)[0] == "FUNDAMENTAL_FAIL"
    assert evaluate_fundamental_status(snap(latest_q_operating_income=-1, previous_q_operating_income=-1), SETTINGS)[0] == "FUNDAMENTAL_FAIL"

def test_warning_counts_and_current_ratio_contexts():
    status, _, warnings, info = evaluate_fundamental_status(snap(ttm_operating_cash_flow=0), SETTINGS)
    assert status == "FUNDAMENTAL_PASS" and warnings == ["NONPOSITIVE_TTM_OPERATING_CASH_FLOW"]
    status, _, warnings, _ = evaluate_fundamental_status(snap(ttm_operating_cash_flow=0, latest_total_liabilities=80), SETTINGS)
    assert status == "FUNDAMENTAL_WATCH" and len(warnings) == 2
    status, _, warnings, info = evaluate_fundamental_status(snap(latest_current_assets=50, latest_current_liabilities=100, ttm_operating_cash_flow=1), SETTINGS)
    assert status == "FUNDAMENTAL_PASS" and not warnings and info == ["LOW_CURRENT_RATIO_CONTEXT"]
    status, _, warnings, _ = evaluate_fundamental_status(snap(latest_current_assets=50, latest_current_liabilities=100, ttm_operating_cash_flow=0), SETTINGS)
    assert status == "FUNDAMENTAL_WATCH" and "LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF" in warnings
    assert evaluate_fundamental_status(snap(latest_current_liabilities=0), SETTINGS)[0] == "FUNDAMENTAL_PASS"

def test_earnings_direction():
    assert evaluate_earnings_direction(snap(prior_year_q_operating_income=-1, latest_q_operating_income=1), SETTINGS) == "TURNAROUND_POSITIVE"
    assert evaluate_earnings_direction(snap(prior_year_q_operating_income=2, latest_q_operating_income=1), SETTINGS) == "EARNINGS_WEAK"

def test_eligibility_data_and_precedence():
    assert evaluate_eligibility(snap(average_turnover_20d=19_999_999), SETTINGS)[0] == "ILLIQUID"
    s = snap(required_data_valid=False, average_turnover_20d=1, latest_equity=0)
    assert resolve_primary_action(s, "ILLIQUID", "FUNDAMENTAL_FAIL", "VERY_LOW_VALUATION", "EARNINGS_OK", SETTINGS)[0] == "DATA_REVIEW"
    s = snap(average_turnover_20d=1)
    assert resolve_primary_action(s, "ILLIQUID", "FUNDAMENTAL_PASS", "VERY_LOW_VALUATION", "EARNINGS_OK", SETTINGS)[0] == "NOT_ELIGIBLE"
    s = snap()
    assert resolve_primary_action(s, "ELIGIBLE", "FUNDAMENTAL_PASS", "ABSOLUTE_CHEAP", "EARNINGS_OK", SETTINGS)[0] == "VALUE_CANDIDATE"
