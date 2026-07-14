from __future__ import annotations

from .models import StockSnapshot


def evaluate_eligibility(snapshot: StockSnapshot, settings: dict) -> tuple[str, list[str]]:
    market_rules = settings["phase_a1"]["liquidity"].get(snapshot.market, {})
    minimum = float(market_rules.get("min_average_turnover_20d", float("inf")))
    if snapshot.average_turnover_20d >= minimum:
        return "ELIGIBLE", []
    return "ILLIQUID", ["AVERAGE_TURNOVER_20D_BELOW_MINIMUM"]


def evaluate_fundamental_status(snapshot: StockSnapshot, settings: dict) -> tuple[str, list[str], list[str], list[str]]:
    trigger_reasons: list[str] = []
    warning_reasons: list[str] = []
    informational_tags: list[str] = []
    risk_flags: list[str] = []

    if snapshot.latest_equity <= 0:
        trigger_reasons.append("NONPOSITIVE_EQUITY")
    if snapshot.ttm_operating_income <= 0:
        trigger_reasons.append("NONPOSITIVE_TTM_OPERATING_INCOME")
    if snapshot.latest_q_operating_income < 0 and snapshot.previous_q_operating_income < 0:
        trigger_reasons.append("TWO_CONSECUTIVE_NEGATIVE_OPERATING_QUARTERS")
    if trigger_reasons:
        risk_flags.extend(trigger_reasons)
        return "FUNDAMENTAL_FAIL", trigger_reasons, warning_reasons, informational_tags

    fundamentals = settings["phase_a1"]["fundamentals"]
    if snapshot.ttm_operating_cash_flow <= 0:
        warning_reasons.append("NONPOSITIVE_TTM_OPERATING_CASH_FLOW")
    debt_ratio = snapshot.latest_total_liabilities / snapshot.latest_total_assets if snapshot.latest_total_assets else float("inf")
    if debt_ratio > float(fundamentals["high_debt_ratio"]):
        warning_reasons.append("HIGH_DEBT_RATIO")
    current_ratio = float("inf") if snapshot.latest_current_liabilities == 0 else snapshot.latest_current_assets / snapshot.latest_current_liabilities
    if current_ratio < float(fundamentals["low_current_ratio"]):
        if snapshot.ttm_operating_cash_flow <= 0:
            warning_reasons.append("LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF")
        else:
            informational_tags.append("LOW_CURRENT_RATIO_CONTEXT")

    status = "FUNDAMENTAL_PASS" if len(warning_reasons) <= 1 else "FUNDAMENTAL_WATCH"
    return status, trigger_reasons, warning_reasons, informational_tags


def calculate_absolute_pe_status(snapshot: StockSnapshot, settings: dict) -> tuple[str, float | None]:
    pe = snapshot.pe
    if pe is None or pe <= 0:
        return "VALUATION_UNKNOWN", None
    valuation = settings["phase_a1"]["valuation"]
    if pe <= float(valuation["very_low_pe_max"]):
        return "VERY_LOW_VALUATION", pe
    if pe <= float(valuation["absolute_cheap_pe_max"]):
        return "ABSOLUTE_CHEAP", pe
    if pe <= float(valuation["fair_pe_max"]):
        return "FAIR_VALUATION", pe
    return "VALUATION_NOT_CHEAP", pe


def evaluate_earnings_direction(snapshot: StockSnapshot, settings: dict | None = None) -> str:
    latest = snapshot.latest_q_operating_income
    prior = snapshot.prior_year_q_operating_income
    if latest > 0 and prior > 0:
        return "EARNINGS_OK" if latest >= prior else "EARNINGS_WEAK"
    if prior <= 0 and latest > 0:
        return "TURNAROUND_POSITIVE"
    if prior > 0 and latest <= 0:
        return "TURNAROUND_NEGATIVE"
    return "BOTH_NON_POSITIVE"
