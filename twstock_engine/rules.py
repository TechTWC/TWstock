from __future__ import annotations

import math

from .models import (
    EarningsDirectionResult,
    EligibilityResult,
    FundamentalResult,
    Settings,
    StockSnapshot,
    ValuationResult,
)


def evaluate_eligibility(
    snapshot: StockSnapshot, settings: Settings
) -> EligibilityResult:
    """Evaluate the Phase A1 TW common-stock liquidity gate."""

    if snapshot.market != settings.supported_market:
        return EligibilityResult("NOT_SUPPORTED", ("UNSUPPORTED_MARKET",))
    if snapshot.security_type != settings.supported_security_type:
        return EligibilityResult("NOT_SUPPORTED", ("UNSUPPORTED_SECURITY_TYPE",))
    if snapshot.average_turnover_20d >= settings.tw_min_average_turnover_20d:
        return EligibilityResult("ELIGIBLE", ("TW_LIQUIDITY_THRESHOLD_MET",))
    return EligibilityResult("ILLIQUID", ("TW_LIQUIDITY_THRESHOLD_NOT_MET",))


def evaluate_fundamental_status(
    snapshot: StockSnapshot, settings: Settings
) -> FundamentalResult:
    """Apply the v1.10 Phase A1 financial-survival rules."""

    risk_flags: list[str] = []
    warnings: list[str] = []
    informational_tags: list[str] = []

    if snapshot.latest_equity <= settings.equity_failure_threshold:
        risk_flags.append("NONPOSITIVE_EQUITY")
    if (
        snapshot.ttm_operating_income
        <= settings.ttm_operating_income_failure_threshold
    ):
        risk_flags.append("NONPOSITIVE_TTM_OPERATING_INCOME")
    if (
        snapshot.latest_q_operating_income < settings.negative_quarter_threshold
        and snapshot.previous_q_operating_income
        < settings.negative_quarter_threshold
    ):
        risk_flags.append("TWO_CONSECUTIVE_NEGATIVE_OPERATING_QUARTERS")

    if snapshot.ttm_operating_cash_flow <= settings.nonpositive_ocf_threshold:
        warnings.append("NONPOSITIVE_TTM_OPERATING_CASH_FLOW")

    debt_ratio = snapshot.latest_total_liabilities / snapshot.latest_total_assets
    if debt_ratio > settings.debt_ratio_warning_threshold:
        warnings.append("HIGH_DEBT_RATIO")

    if snapshot.latest_current_liabilities == 0:
        current_ratio = math.inf
    else:
        current_ratio = (
            snapshot.latest_current_assets / snapshot.latest_current_liabilities
        )

    if current_ratio < settings.current_ratio_threshold:
        if snapshot.ttm_operating_cash_flow <= settings.nonpositive_ocf_threshold:
            warnings.append("LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF")
        else:
            informational_tags.append("LOW_CURRENT_RATIO_CONTEXT")

    if risk_flags:
        status = "FUNDAMENTAL_FAIL"
    elif len(warnings) >= settings.warning_watch_min_count:
        status = "FUNDAMENTAL_WATCH"
    else:
        status = "FUNDAMENTAL_PASS"

    return FundamentalResult(
        status=status,
        warning_reasons=tuple(warnings),
        risk_flags=tuple(risk_flags),
        informational_tags=tuple(informational_tags),
        warning_count=len(warnings),
        debt_ratio=debt_ratio,
        current_ratio=current_ratio,
    )


def calculate_absolute_pe_status(
    snapshot: StockSnapshot, settings: Settings
) -> ValuationResult:
    """Calculate absolute PE and classify it at the configured boundaries."""

    if snapshot.ttm_net_income <= settings.net_income_positive_threshold:
        return ValuationResult(
            status="VALUATION_UNKNOWN",
            pe_ttm=None,
            reasons=("NONPOSITIVE_TTM_NET_INCOME",),
        )
    if snapshot.market_cap <= settings.market_cap_positive_threshold:
        return ValuationResult(
            status="VALUATION_UNKNOWN",
            pe_ttm=None,
            reasons=("NONPOSITIVE_MARKET_CAP",),
        )

    pe_ttm = snapshot.market_cap / snapshot.ttm_net_income
    if pe_ttm <= settings.very_low_pe_max:
        status = "VERY_LOW_VALUATION"
    elif pe_ttm <= settings.absolute_cheap_pe_max:
        status = "ABSOLUTE_CHEAP"
    elif pe_ttm <= settings.fair_pe_max:
        status = "FAIR_VALUATION"
    else:
        status = "VALUATION_NOT_CHEAP"

    return ValuationResult(status=status, pe_ttm=pe_ttm, reasons=())


def evaluate_earnings_direction(
    snapshot: StockSnapshot, settings: Settings
) -> EarningsDirectionResult:
    """Classify operating-income direction without inventing turnaround growth."""

    latest = snapshot.latest_q_operating_income
    prior_year = snapshot.prior_year_q_operating_income
    positive = settings.earnings_positive_threshold

    if prior_year > positive and latest > positive:
        yoy = latest / prior_year - 1.0
        status = (
            "EARNINGS_OK"
            if yoy >= settings.earnings_yoy_ok_threshold
            else "EARNINGS_WEAK"
        )
        return EarningsDirectionResult(status, yoy)

    if prior_year <= positive and latest > positive:
        return EarningsDirectionResult("TURNAROUND_POSITIVE", None)
    if prior_year > positive and latest <= positive:
        return EarningsDirectionResult("TURNAROUND_NEGATIVE", None)
    return EarningsDirectionResult("BOTH_NON_POSITIVE", None)
