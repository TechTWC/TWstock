from __future__ import annotations

from datetime import date
import math
from statistics import median
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .models import (
    ClassificationResult,
    DataQuality,
    FundamentalState,
    PITMetadata,
    QualityState,
    SectorLogic,
    SecurityData,
    StateDetail,
    ValuationState,
)
from .pit import parse_date


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _last_finite(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame:
        return None
    series = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return _finite(series.iloc[-1]) if not series.empty else None


def _last_finite_with_date(frame: pd.DataFrame, column: str) -> tuple[float | None, date | None]:
    if column not in frame or "date" not in frame:
        return None, None
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    selected = frame.loc[values.notna(), ["date"]].copy()
    if selected.empty:
        return None, None
    index = selected.index[-1]
    return _finite(values.loc[index]), parse_date(frame.loc[index, "date"])


def _median_finite(values: Iterable[object]) -> float | None:
    selected = [_finite(value) for value in values]
    selected = [value for value in selected if value is not None]
    return median(selected) if selected else None


def _quarter_ordinal(value: object) -> int | None:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    return int(timestamp.year * 4 + ((timestamp.month - 1) // 3))


def _cagr(frame: pd.DataFrame, column: str, years: int) -> float | None:
    """Calendar-quarter CAGR; gaps never masquerade as elapsed observations."""

    if column not in frame or "period_end" not in frame or frame.empty:
        return None
    ordered = frame.sort_values("period_end").reset_index(drop=True)
    ordinals = ordered["period_end"].map(_quarter_ordinal)
    current_ordinal = ordinals.iloc[-1]
    if current_ordinal is None:
        return None
    target_ordinal = current_ordinal - years * 4
    matches = ordered[ordinals == target_ordinal]
    interval = ordered[(ordinals >= target_ordinal) & (ordinals <= current_ordinal)]
    expected = years * 4 + 1
    if len(matches) != 1 or len(interval) != expected or interval["period_end"].map(_quarter_ordinal).nunique() != expected:
        return None
    current = _finite(ordered[column].iloc[-1])
    previous = _finite(matches[column].iloc[0])
    if current is None or previous is None or current <= 0 or previous <= 0:
        return None
    return (current / previous) ** (1.0 / years) - 1.0


def _coverage(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna().mean())


def _percentile(history: pd.Series, current: float | None, *, positive: bool = False) -> float | None:
    if current is None:
        return None
    values = pd.to_numeric(history, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if positive:
        values = values[values > 0]
    if values.empty:
        return None
    return float((values <= current).mean())


def _quantile(history: pd.Series, quantile: float, *, positive: bool = False) -> float | None:
    values = pd.to_numeric(history, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if positive:
        values = values[values > 0]
    return _finite(values.quantile(quantile)) if not values.empty else None


def _general_quality(
    q: pd.DataFrame, metrics: dict[str, float | str | None], rules: dict[str, Any]
) -> tuple[QualityState, list[str], list[str]]:
    reasons: list[str] = []
    codes: list[str] = []
    equity = metrics["equity"]
    ttm_op = metrics["ttm_operating_income"]
    median_roe = metrics["median_roe_5y"]
    median_roic = metrics["median_roic_5y"]
    fcf_ratio = metrics["fcf_positive_ratio_5y"]
    cfo_ni = metrics["median_cfo_net_income_5y"]
    net_debt_equity = metrics["net_debt_equity"]
    current_ratio = metrics["current_ratio"]
    revenue_cagr = metrics["revenue_cagr_3y"]
    eps_cagr = metrics["eps_cagr_3y"]
    fcf_cagr = metrics["fcf_cagr_3y"]
    interest_coverage = metrics["interest_coverage"]

    coverage_rules = rules.get("minimum_metric_coverage", {})
    insufficient = [
        column
        for column, minimum in coverage_rules.items()
        if float(metrics.get(f"coverage_{column}") or 0.0) < float(minimum)
    ]
    if insufficient:
        return (
            QualityState.UNKNOWN,
            ["Minimum historical metric coverage is not met"],
            [f"METRIC_COVERAGE_INSUFFICIENT_{column.upper()}" for column in insufficient],
        )

    if equity is not None and equity <= 0:
        return QualityState.WEAK, ["Equity is non-positive"], ["NONPOSITIVE_EQUITY"]
    if ttm_op is not None and ttm_op <= 0:
        return QualityState.WEAK, ["TTM operating income is non-positive"], ["NONPOSITIVE_TTM_OPERATING_INCOME"]
    if median_roe is not None and median_roe < 0:
        return QualityState.WEAK, ["Five-year median ROE is negative"], ["NEGATIVE_MEDIAN_ROE"]
    if fcf_ratio is not None and fcf_ratio < 0.50:
        return QualityState.WEAK, ["Free cash flow was positive in fewer than half of observed TTM periods"], ["FCF_PERSISTENCE_WEAK"]

    profitability_durable = (
        median_roe is not None
        and median_roic is not None
        and median_roe >= float(rules["median_roe_5y_min"])
        and median_roic >= float(rules["median_roic_5y_min"])
        and (metrics["operating_margin"] or 0) > 0
    )
    growth_durable = (
        revenue_cagr is not None
        and eps_cagr is not None
        and revenue_cagr > 0
        and eps_cagr > 0
        and (fcf_cagr is None or fcf_cagr > 0)
    )
    cash_conversion_supported = (
        cfo_ni is not None
        and fcf_ratio is not None
        and cfo_ni >= float(rules["median_cfo_net_income_min"])
        and fcf_ratio >= float(rules["fcf_positive_ratio_min"])
    )
    balance_sheet_resilient_base = (
        (net_debt_equity is not None and net_debt_equity <= float(rules["net_debt_equity_max"]))
        or (current_ratio is not None and current_ratio >= 1.0 and (metrics["ttm_fcf"] or 0) > 0)
    )
    debt = _finite(metrics.get("debt"))
    net_debt = _finite(metrics.get("net_debt"))
    interest_supported = (
        (net_debt is not None and net_debt <= 0)
        or (debt is not None and debt <= 0)
        or interest_coverage is not None
        and interest_coverage >= float(rules["interest_coverage_min"])
    )
    balance_sheet_resilient = balance_sheet_resilient_base and interest_supported

    gate_map = {
        "PROFITABILITY_DURABLE": profitability_durable,
        "GROWTH_DURABLE": growth_durable,
        "CASH_CONVERSION_SUPPORTED": cash_conversion_supported,
        "BALANCE_SHEET_RESILIENT": balance_sheet_resilient,
    }
    for code, passed in gate_map.items():
        codes.append(code if passed else f"{code}_NOT_ESTABLISHED")
    codes.append("INTEREST_COVERAGE_SUPPORTED" if interest_supported else "INTEREST_COVERAGE_NOT_ESTABLISHED")
    if profitability_durable:
        reasons.append("ROE, ROIC and operating margin meet the durable-profitability gate")
    if growth_durable:
        reasons.append("Revenue and EPS grew over three years without contradictory FCF evidence")
    if cash_conversion_supported:
        reasons.append("Operating cash flow supports earnings and free cash flow is persistent")
    if balance_sheet_resilient:
        reasons.append("Balance-sheet resilience gate is met")

    required = (median_roe, median_roic, revenue_cagr, eps_cagr, cfo_ni, fcf_ratio)
    if sum(value is not None for value in required) < 4:
        return QualityState.UNKNOWN, reasons or ["Insufficient history for general-company quality gates"], codes
    if profitability_durable and growth_durable and cash_conversion_supported and balance_sheet_resilient:
        return QualityState.GOOD, reasons, codes
    if profitability_durable and balance_sheet_resilient and (growth_durable or cash_conversion_supported):
        return QualityState.ACCEPTABLE, reasons or ["Core profitability and safety pass; another quality gate remains unproven"], codes
    return QualityState.WEAK, reasons or ["Durable profitability and resilience are not established"], codes


def _financial_quality(
    metrics: dict[str, float | str | None], rules: dict[str, Any]
) -> tuple[QualityState, list[str], list[str]]:
    """Fail closed until the v0.1 source can support financial-sector semantics.

    The generic vendor statements do not establish standalone-quarter versus
    cumulative bases consistently and do not provide NIM/NPL/capital or
    insurance operating fields.  A partial generic tuple must never become
    ACCEPTABLE merely because three values happen to exist.
    """

    codes = ["SECTOR_LOGIC_FINANCIAL", "FINANCIAL_STATE_UNSUPPORTED"]
    core = {
        "EPS": metrics.get("ttm_eps"),
        "NET_INCOME": metrics.get("ttm_net_income"),
        "EQUITY": metrics.get("equity"),
        "BVPS": metrics.get("bvps"),
        "ROE": metrics.get("roe"),
    }
    missing = [name for name, value in core.items() if _finite(value) is None]
    if missing:
        codes.extend(f"FINANCIAL_CORE_MISSING_{name}" for name in missing)
    roe = _finite(metrics.get("roe"))
    if roe is not None and abs(roe) > float(rules.get("roe_mapping_plausibility_max", 0.50)):
        codes.append("FINANCIAL_ROE_MAPPING_ANOMALY")
    return (
        QualityState.UNKNOWN,
        ["Reliable PIT bank/insurance-specific core fields are unavailable in the v0.1 source contract"],
        codes + ["FINANCIAL_CORE_DATA_INSUFFICIENT"],
    )


def _state_detail(q: pd.DataFrame) -> tuple[StateDetail, list[str], list[str]]:
    if len(q) < 11:
        return StateDetail.UNKNOWN, ["Fewer than eleven PIT-available quarters"], ["STATE_HISTORY_INSUFFICIENT"]
    recent = q.tail(8).reset_index(drop=True)
    for column in ("revenue_yoy", "eps_yoy", "operating_margin_change", "fcf_yoy"):
        if column not in recent:
            return StateDetail.UNKNOWN, [f"Missing {column}"], ["STATE_INPUT_MISSING"]
    rev = [_finite(value) for value in recent["revenue_yoy"]]
    eps = [_finite(value) for value in recent["eps_yoy"]]
    margin = [_finite(value) for value in recent["operating_margin_change"]]
    fcf = [_finite(value) for value in recent["fcf_yoy"]]
    if rev[-1] is None or rev[-2] is None or eps[-1] is None or eps[-2] is None:
        return StateDetail.UNKNOWN, ["Latest revenue/EPS direction is unavailable"], ["STATE_INPUT_MISSING"]

    revenue_improving = rev[-1] > rev[-2] and (rev[-3] is None or rev[-2] >= rev[-3])
    earnings_support = eps[-1] > eps[-2]
    margin_support = margin[-1] is not None and margin[-1] >= 0
    cash_support = fcf[-1] is not None and fcf[-2] is not None and fcf[-1] > fcf[-2]
    corroborated_recovery = revenue_improving and (earnings_support or (margin_support and cash_support))

    if rev[-1] < 0 and corroborated_recovery:
        return StateDetail.BOTTOMING, ["Revenue contraction is narrowing with EPS or margin-and-cash-flow support"], ["REVENUE_CONTRACTION_NARROWING", "RECOVERY_CORROBORATED"]
    crossed_positive = rev[-2] <= 0 < rev[-1]
    if corroborated_recovery and (crossed_positive or (rev[-3] is not None and rev[-3] < rev[-2] < rev[-1])):
        return StateDetail.TURNING_UP, ["Revenue growth is in an early recovery and at least one independent fundamental family corroborates it"], ["EARLY_REVENUE_RECOVERY", "RECOVERY_CORROBORATED"]

    last_three_rev = rev[-3:]
    last_three_eps = eps[-3:]
    if all(value is not None and value > 0 for value in last_three_rev + last_three_eps):
        declining = last_three_rev[0] > last_three_rev[1] > last_three_rev[2] and last_three_eps[0] > last_three_eps[1] > last_three_eps[2]
        if declining and (margin[-1] is None or margin[-1] <= 0):
            return StateDetail.DECELERATING, ["Revenue and EPS remain positive but have decelerated for three observations"], ["POSITIVE_GROWTH_DECELERATING"]
        if all(value is not None and value > 0 for value in rev[-8:] + eps[-8:]):
            return StateDetail.MATURE_GROWTH, ["Revenue and EPS growth have remained positive across eight observations"], ["SUSTAINED_GROWTH_EIGHT_PERIODS"]
        return StateDetail.CONFIRMED_GROWTH, ["Revenue and EPS growth are positive across three observations"], ["GROWTH_CONFIRMED_THREE_PERIODS"]

    revenue_deteriorating = rev[-1] < rev[-2] and (rev[-3] is None or rev[-2] <= rev[-3])
    earnings_deteriorating = eps[-1] < eps[-2]
    margin_deteriorating = margin[-1] is not None and margin[-1] < 0
    cash_deteriorating = fcf[-1] is not None and fcf[-2] is not None and fcf[-1] < fcf[-2]
    if revenue_deteriorating and (earnings_deteriorating or (margin_deteriorating and cash_deteriorating)):
        return StateDetail.DETERIORATING, ["Revenue direction is weakening with EPS or margin-and-cash-flow deterioration"], ["DETERIORATION_CORROBORATED"]
    return StateDetail.UNKNOWN, ["Mixed fundamental directions do not satisfy a named state gate"], ["MIXED_FUNDAMENTAL_DIRECTION"]


def canonical_state(detail: StateDetail) -> FundamentalState:
    """Pre-registered mapping; correction changes taxonomy, not thresholds."""

    mapping = {
        StateDetail.BOTTOMING: FundamentalState.IMPROVING,
        StateDetail.TURNING_UP: FundamentalState.IMPROVING,
        StateDetail.CONFIRMED_GROWTH: FundamentalState.STABLE,
        StateDetail.MATURE_GROWTH: FundamentalState.STABLE,
        StateDetail.DECELERATING: FundamentalState.STABLE,
        StateDetail.DETERIORATING: FundamentalState.DETERIORATING,
        StateDetail.UNKNOWN: FundamentalState.UNKNOWN,
    }
    return mapping[detail]


def _dcf_value(fcf_per_share: float, growth: float, discount: float, terminal: float, years: int) -> float | None:
    if fcf_per_share <= 0 or discount <= terminal:
        return None
    value = 0.0
    cash = fcf_per_share
    for year in range(1, years + 1):
        cash *= 1.0 + growth
        value += cash / (1.0 + discount) ** year
    terminal_value = cash * (1.0 + terminal) / (discount - terminal)
    return value + terminal_value / (1.0 + discount) ** years


def _reverse_dcf_growth(price: float, fcf_per_share: float, discount: float, terminal: float, years: int) -> float | None:
    if price <= 0 or fcf_per_share <= 0:
        return None
    low, high = -0.10, 0.30
    low_value = _dcf_value(fcf_per_share, low, discount, terminal, years)
    high_value = _dcf_value(fcf_per_share, high, discount, terminal, years)
    if low_value is None or high_value is None or not (low_value <= price <= high_value):
        return None
    for _ in range(80):
        mid = (low + high) / 2.0
        value = _dcf_value(fcf_per_share, mid, discount, terminal, years)
        if value is None:
            return None
        if value < price:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _normalized_pe_history(q: pd.DataFrame, market: pd.DataFrame, window: int = 20) -> pd.Series:
    """Quarterly normalized P/E observations using one definition through time."""

    values: list[float] = []
    ordered_q = q.sort_values("available_date").reset_index(drop=True)
    ordered_market = market.sort_values("date")
    for index, row in ordered_q.iterrows():
        eps = _median_finite(ordered_q.iloc[max(0, index - window + 1) : index + 1]["ttm_eps"])
        if eps is None or eps <= 0:
            continue
        known_market = ordered_market[ordered_market["date"] <= row["available_date"]]
        price = _last_finite(known_market, "close")
        if price is not None and price > 0:
            values.append(price / eps)
    return pd.Series(values, dtype=float)


def _valuation(
    security: SecurityData,
    q: pd.DataFrame,
    market: pd.DataFrame,
    metrics: dict[str, float | str | None],
    state: FundamentalState,
    rules: dict[str, Any],
) -> tuple[ValuationState, list[str], list[str], dict[str, float | None]]:
    reasons: list[str] = []
    codes: list[str] = []
    empty_intrinsic = {"bear": None, "base": None, "bull": None, "margin_of_safety_base": None, "reverse_dcf_growth": None}
    if market.empty:
        return ValuationState.NOT_MEANINGFUL, ["No market valuation history"], ["VALUATION_HISTORY_MISSING"], empty_intrinsic
    # Price and exchange valuation observations do not necessarily share a
    # trading date.  Use the latest finite value available for each field at
    # the requested as-of date instead of requiring a same-row match.
    current_price, price_date = _last_finite_with_date(market, "close")
    current_pe, pe_date = _last_finite_with_date(market, "PER")
    current_pb, pb_date = _last_finite_with_date(market, "PBR")
    current_yield, yield_date = _last_finite_with_date(market, "dividend_yield")
    freshness_reference = price_date or parse_date(market["date"].iloc[-1])
    maximum_staleness = int(rules.get("maximum_valuation_staleness_days", 10))
    age = {
        "pe": (freshness_reference - pe_date).days if pe_date else None,
        "pb": (freshness_reference - pb_date).days if pb_date else None,
        "dividend_yield": (freshness_reference - yield_date).days if yield_date else None,
    }
    if age["pe"] is None or age["pe"] > maximum_staleness:
        current_pe = None
        codes.append("PE_STALE_OR_MISSING")
    if age["pb"] is None or age["pb"] > maximum_staleness:
        current_pb = None
        codes.append("PB_STALE_OR_MISSING")
    if age["dividend_yield"] is None or age["dividend_yield"] > maximum_staleness:
        current_yield = None
        codes.append("DIVIDEND_YIELD_STALE_OR_MISSING")
    minimum = int(rules["minimum_history_observations"])
    pe_history = pd.to_numeric(market.get("PER"), errors="coerce")
    pb_history = pd.to_numeric(market.get("PBR"), errors="coerce")
    yield_history = pd.to_numeric(market.get("dividend_yield"), errors="coerce")
    pe_percentile = _percentile(pe_history, current_pe, positive=True) if pe_history.notna().sum() >= minimum else None
    pb_percentile = _percentile(pb_history, current_pb, positive=True) if pb_history.notna().sum() >= minimum else None
    yield_percentile = _percentile(yield_history, current_yield, positive=True) if yield_history.notna().sum() >= minimum else None
    metrics.update(
        {
            "price": current_price,
            "pe": current_pe,
            "pb": current_pb,
            "dividend_yield": current_yield,
            "price_date": price_date.isoformat() if price_date else None,
            "pe_date": pe_date.isoformat() if pe_date else None,
            "pb_date": pb_date.isoformat() if pb_date else None,
            "dividend_yield_date": yield_date.isoformat() if yield_date else None,
            "pe_staleness_days": age["pe"],
            "pb_staleness_days": age["pb"],
            "dividend_yield_staleness_days": age["dividend_yield"],
            "pe_percentile": pe_percentile,
            "pb_percentile": pb_percentile,
            "dividend_yield_percentile": yield_percentile,
            "pe_p25": _quantile(pe_history, 0.25, positive=True),
            "pe_median": _quantile(pe_history, 0.50, positive=True),
            "pe_p75": _quantile(pe_history, 0.75, positive=True),
            "pb_p25": _quantile(pb_history, 0.25, positive=True),
            "pb_median": _quantile(pb_history, 0.50, positive=True),
            "pb_p75": _quantile(pb_history, 0.75, positive=True),
        }
    )

    ttm_eps_history = pd.to_numeric(q["ttm_eps"], errors="coerce").dropna().tail(20)
    normalized_eps = _median_finite(ttm_eps_history)
    normalized_pe = current_price / normalized_eps if current_price and normalized_eps and normalized_eps > 0 else None
    normalized_history = _normalized_pe_history(q, market)
    metrics["normalized_eps_5y"] = normalized_eps
    metrics["normalized_pe"] = normalized_pe
    metrics["normalized_pe_history_n"] = int(len(normalized_history))
    metrics["normalized_pe_p25"] = _quantile(normalized_history, 0.25, positive=True)
    metrics["normalized_pe_p75"] = _quantile(normalized_history, 0.75, positive=True)

    ttm_net_income = _finite(metrics["ttm_net_income"])
    ttm_eps = _finite(metrics["ttm_eps"])
    ttm_fcf = _finite(metrics["ttm_fcf"])
    estimated_shares = ttm_net_income / ttm_eps if ttm_net_income and ttm_eps and ttm_eps > 0 else None
    fcf_per_share = ttm_fcf / estimated_shares if ttm_fcf and estimated_shares and estimated_shares > 0 else None
    fcf_yield = fcf_per_share / current_price if fcf_per_share and current_price and current_price > 0 else None
    metrics["fcf_per_share"] = fcf_per_share
    metrics["fcf_yield"] = fcf_yield

    if security.sector_logic == SectorLogic.FINANCIAL:
        codes.append("VALUATION_SECTOR_FINANCIAL_PB_PRIMARY")
        if current_pb is None or pb_percentile is None:
            valuation = ValuationState.NOT_MEANINGFUL
            reasons.append("P/B history is unavailable for financial-sector valuation")
        elif pb_percentile <= float(rules["low_percentile_max"]) and state != FundamentalState.DETERIORATING:
            valuation = ValuationState.LOW
            reasons.append("P/B is in the lowest historical quartile without a deteriorating state")
        elif pb_percentile >= float(rules["high_percentile_min"]):
            valuation = ValuationState.HIGH
            reasons.append("P/B is in the highest historical quartile")
        else:
            valuation = ValuationState.NORMAL
            reasons.append("P/B is within the middle historical range")
        return valuation, reasons, codes, empty_intrinsic

    if security.sector_logic == SectorLogic.CYCLICAL:
        codes.append("VALUATION_SECTOR_CYCLICAL_NORMALIZED_EPS")
        p25 = _quantile(normalized_history, 0.25, positive=True)
        p75 = _quantile(normalized_history, 0.75, positive=True)
        normalized_minimum = int(rules.get("normalized_pe_minimum_observations", 12))
        if normalized_pe is None or p25 is None or p75 is None or len(normalized_history) < normalized_minimum:
            valuation = ValuationState.NOT_MEANINGFUL
            reasons.append("Comparable normalized P/E history is unavailable")
        elif normalized_pe <= p25:
            valuation = ValuationState.LOW
            reasons.append("Normalized P/E is below the historical lower quartile")
        elif normalized_pe >= p75:
            valuation = ValuationState.HIGH
            reasons.append("Normalized P/E is above the historical upper quartile")
        else:
            valuation = ValuationState.NORMAL
            reasons.append("Normalized P/E is within the historical interquartile range")
        if current_pe and normalized_pe and current_pe < normalized_pe * 0.67:
            codes.append("CYCLICAL_LOW_PE_TRAP_RISK")
            reasons.append("Current P/E is materially below normalized P/E; peak-earnings distortion is possible")
    else:
        if current_pe is None or current_pe <= 0:
            valuation = ValuationState.NOT_MEANINGFUL
            reasons.append("Current P/E is not meaningful")
            codes.append("NONPOSITIVE_OR_MISSING_PE")
        elif pe_percentile is None:
            valuation = ValuationState.NOT_MEANINGFUL
            reasons.append("Historical P/E observations are insufficient")
            codes.append("VALUATION_HISTORY_INSUFFICIENT")
        elif pe_percentile <= float(rules["low_percentile_max"]) and (
            (pb_percentile is not None and pb_percentile <= 0.50)
            or (fcf_yield is not None and fcf_yield > 0)
        ):
            valuation = ValuationState.LOW
            reasons.append("P/E is in the lowest historical quartile with P/B or positive-FCF corroboration")
            codes.append("HISTORICAL_VALUATION_LOW")
        elif pe_percentile >= float(rules["high_percentile_min"]) and (
            pb_percentile is None or pb_percentile >= float(rules["high_percentile_min"])
        ):
            valuation = ValuationState.HIGH
            reasons.append("P/E and available P/B context are in the highest historical quartile")
            codes.append("HISTORICAL_VALUATION_HIGH")
        else:
            valuation = ValuationState.NORMAL
            reasons.append("Valuation is within the model's middle historical context")
            codes.append("HISTORICAL_VALUATION_NORMAL")

    intrinsic = dict(empty_intrinsic)
    if fcf_per_share is not None and fcf_per_share > 0 and current_price is not None:
        discount = float(rules["dcf_discount_rate"])
        terminal = float(rules["dcf_terminal_growth"])
        years = int(rules["dcf_projection_years"])
        observed_growth = _finite(metrics["fcf_cagr_3y"])
        base_growth = min(0.15, max(0.0, observed_growth if observed_growth is not None else 0.03))
        floor = float(rules["dcf_growth_floor"])
        cap = float(rules["dcf_growth_cap"])
        bear_growth = max(floor, base_growth - 0.05)
        bull_growth = min(cap, base_growth + 0.05)
        intrinsic = {
            "bear": _dcf_value(fcf_per_share, bear_growth, discount, terminal, years),
            "base": _dcf_value(fcf_per_share, base_growth, discount, terminal, years),
            "bull": _dcf_value(fcf_per_share, bull_growth, discount, terminal, years),
            "margin_of_safety_base": None,
            "reverse_dcf_growth": _reverse_dcf_growth(current_price, fcf_per_share, discount, terminal, years),
        }
        if intrinsic["base"] is not None:
            intrinsic["margin_of_safety_base"] = intrinsic["base"] / current_price - 1.0
        codes.append("SIMPLIFIED_DCF_AVAILABLE")
    else:
        codes.append("SIMPLIFIED_DCF_NOT_APPLICABLE")
    return valuation, reasons, codes, intrinsic


def _research_classification(
    quality: QualityState,
    state: FundamentalState,
    detail: StateDetail,
    valuation: ValuationState,
) -> str:
    if quality == QualityState.GOOD and detail == StateDetail.TURNING_UP and valuation in {ValuationState.LOW, ValuationState.NORMAL}:
        return "VALUE_RECOVERY"
    if quality == QualityState.GOOD and detail == StateDetail.CONFIRMED_GROWTH and valuation == ValuationState.NORMAL:
        return "QUALITY_AT_FAIR_PRICE"
    if (quality == QualityState.WEAK or state == FundamentalState.DETERIORATING) and valuation == ValuationState.LOW:
        return "POSSIBLE_VALUE_TRAP"
    if quality == QualityState.GOOD and detail in {StateDetail.MATURE_GROWTH, StateDetail.DECELERATING} and valuation == ValuationState.HIGH:
        return "HIGH_EXPECTATION_RISK"
    return "UNCLASSIFIED_RESEARCH_CASE"


def classify_security(
    security: SecurityData,
    as_of: str | date,
    config: dict[str, Any],
) -> ClassificationResult:
    selected_date = parse_date(as_of)
    q = security.quarterly[security.quarterly["available_date"] <= selected_date].copy()
    market = security.market[security.market["date"] <= selected_date].copy()
    flags = list(dict.fromkeys(security.data_flags))
    if q.empty:
        return ClassificationResult(
            symbol=security.symbol,
            company=security.company,
            industry=security.industry,
            sector_logic=security.sector_logic.value,
            peer_group=security.peer_group,
            financial_subtype=security.financial_subtype,
            as_of_date=selected_date.isoformat(),
            period_end=None,
            quality=QualityState.UNKNOWN.value,
            fundamental_state=FundamentalState.UNKNOWN.value,
            valuation=ValuationState.NOT_MEANINGFUL.value,
            research_classification="UNCLASSIFIED_RESEARCH_CASE",
            data_quality=DataQuality.INSUFFICIENT.value,
            quality_reasons=("No PIT-available financial observations",),
            fundamental_reasons=("No PIT-available financial observations",),
            state_detail=StateDetail.UNKNOWN.value,
            valuation_reasons=("No market context joined to a financial observation",),
            reason_codes=("PIT_FINANCIAL_DATA_EMPTY",),
            data_quality_flags=tuple(flags + ["INSUFFICIENT_FINANCIAL_HISTORY"]),
            metrics={},
            intrinsic_value={"bear": None, "base": None, "bull": None, "margin_of_safety_base": None, "reverse_dcf_growth": None},
            pit_metadata=None,
        )

    recent_5y = q.tail(20)
    latest = q.iloc[-1]
    fcf_series = pd.to_numeric(recent_5y["ttm_fcf"], errors="coerce").dropna()
    metrics: dict[str, float | str | None] = {
        "revenue": _finite(latest.get("revenue")),
        "ttm_revenue": _finite(latest.get("ttm_revenue")),
        "ttm_eps": _finite(latest.get("ttm_eps")),
        "ttm_net_income": _finite(latest.get("ttm_net_income")),
        "ttm_operating_income": _finite(latest.get("ttm_operating_income")),
        "ttm_cfo": _finite(latest.get("ttm_cfo")),
        "ttm_fcf": _finite(latest.get("ttm_fcf")),
        "equity": _finite(latest.get("equity")),
        "assets": _finite(latest.get("assets")),
        "cash": _finite(latest.get("cash")),
        "debt": _finite(latest.get("debt")),
        "net_debt": _finite(latest.get("net_debt")),
        "net_debt_equity": _finite(latest.get("net_debt_equity")),
        "debt_equity": _finite(latest.get("debt_equity")),
        "bvps": _finite(latest.get("bvps")),
        "ttm_interest_expense": _finite(latest.get("ttm_interest_expense")),
        "interest_coverage": None,
        "current_ratio": _finite(latest.get("current_ratio")),
        "gross_margin": _finite(latest.get("gross_margin")),
        "operating_margin": _finite(latest.get("operating_margin")),
        "net_margin": _finite(latest.get("net_margin")),
        "roe": _finite(latest.get("roe")),
        "roa": _finite(latest.get("roa")),
        "roic": _finite(latest.get("roic")),
        "revenue_yoy": _finite(latest.get("revenue_yoy")),
        "eps_yoy": _finite(latest.get("eps_yoy")),
        "fcf_yoy": _finite(latest.get("fcf_yoy")),
        "operating_margin_change": _finite(latest.get("operating_margin_change")),
        "median_roe_5y": _median_finite(recent_5y["roe"]),
        "median_roa_5y": _median_finite(recent_5y["roa"]),
        "median_roic_5y": _median_finite(recent_5y["roic"]),
        "median_cfo_net_income_5y": _median_finite(recent_5y["cfo_net_income"]),
        "fcf_positive_ratio_5y": float((fcf_series > 0).mean()) if not fcf_series.empty else None,
        "revenue_cagr_3y": _cagr(q, "ttm_revenue", 3),
        "revenue_cagr_5y": _cagr(q, "ttm_revenue", 5),
        "eps_cagr_3y": _cagr(q, "ttm_eps", 3),
        "eps_cagr_5y": _cagr(q, "ttm_eps", 5),
        "fcf_cagr_3y": _cagr(q, "ttm_fcf", 3),
        "fcf_cagr_5y": _cagr(q, "ttm_fcf", 5),
        "equity_cagr_3y": _cagr(q, "equity", 3),
    }
    interest_expense = _finite(metrics["ttm_interest_expense"])
    if interest_expense is not None and abs(interest_expense) > 1e-12:
        metrics["interest_coverage"] = (
            _finite(metrics["ttm_operating_income"]) / abs(interest_expense)
            if _finite(metrics["ttm_operating_income"]) is not None
            else None
        )
    for column in (
        "ttm_revenue",
        "ttm_eps",
        "roe",
        "roic",
        "ttm_cfo",
        "ttm_fcf",
        "equity",
    ):
        metrics[f"coverage_{column}"] = _coverage(recent_5y, column)

    if security.sector_logic == SectorLogic.FINANCIAL:
        quality, quality_reasons, quality_codes = _financial_quality(
            metrics, config["quality_rules"]["financial"]
        )
        detail = StateDetail.UNKNOWN
        state = FundamentalState.UNKNOWN
        state_reasons = ["Financial realized/signal state is unsupported under the v0.1 PIT source contract"]
        state_codes = ["FINANCIAL_STATE_UNSUPPORTED"]
        flags.extend(
            [
                "FINANCIAL_NIM_NPL_CAPITAL_ADEQUACY_UNAVAILABLE",
                "GENERAL_FCF_LOGIC_NOT_APPLIED",
                "FINANCIAL_STATE_UNSUPPORTED",
            ]
        )
    elif "SOURCE_HISTORY_PROVENANCE_UNSTABLE" in flags:
        quality = QualityState.UNKNOWN
        quality_reasons = ["Source-history continuity changed since the reviewed head and is not cross-vintage verified"]
        quality_codes = ["SOURCE_HISTORY_PROVENANCE_UNSTABLE"]
        detail = StateDetail.UNKNOWN
        state = FundamentalState.UNKNOWN
        state_reasons = ["Fundamental state fails closed while source-history provenance is unstable"]
        state_codes = ["STATE_SOURCE_HISTORY_UNSUPPORTED"]
    elif len(q) < 12:
        quality = QualityState.UNKNOWN
        quality_reasons = ["Fewer than 12 PIT-available quarterly observations"]
        quality_codes = ["QUALITY_HISTORY_INSUFFICIENT"]
        detail, state_reasons, state_codes = _state_detail(q)
        state = canonical_state(detail)
    else:
        quality, quality_reasons, quality_codes = _general_quality(
            q, metrics, config["quality_rules"]["general"]
        )
        if security.sector_logic == SectorLogic.CYCLICAL:
            quality_codes.append("SECTOR_LOGIC_CYCLICAL")
            flags.append("NORMALIZED_EARNINGS_REQUIRED")
        detail, state_reasons, state_codes = _state_detail(q)
        state = canonical_state(detail)
    valuation, valuation_reasons, valuation_codes, intrinsic = _valuation(
        security,
        q,
        market,
        metrics,
        state,
        config["valuation_rules"],
    )
    if (
        (metrics["revenue_yoy"] or 0) > 0
        and (metrics["operating_margin_change"] or 0) < 0
        and (metrics["fcf_yoy"] or 0) < 0
    ):
        flags.append("LOW_QUALITY_GROWTH")
    if (
        len(q) >= 5
        and (metrics["eps_yoy"] or 0) > 0
        and (_finite(q["cfo_net_income"].iloc[-1]) or 0) < 0.8
    ):
        flags.append("EARNINGS_QUALITY_REVIEW")
    if len(q) < 12:
        flags.append("SHORT_FINANCIAL_HISTORY")
    if len(market) < int(config["valuation_rules"]["minimum_history_observations"]):
        flags.append("SHORT_VALUATION_HISTORY")

    essential = (
        metrics["ttm_revenue"], metrics["ttm_eps"], metrics["equity"], metrics["roe"], metrics.get("price")
    )
    coverage_failed = any(code.startswith("METRIC_COVERAGE_INSUFFICIENT_") for code in quality_codes)
    if security.sector_logic == SectorLogic.FINANCIAL:
        data_quality = DataQuality.INSUFFICIENT
    elif (
        coverage_failed
        or "SOURCE_HISTORY_PROVENANCE_UNSTABLE" in flags
        or len(q) < 12
        or sum(value is not None for value in essential) < 3
    ):
        data_quality = DataQuality.INSUFFICIENT
    elif flags:
        data_quality = DataQuality.PARTIAL
    else:
        data_quality = DataQuality.OK
    research_classification = _research_classification(quality, state, detail, valuation)
    announcement = latest.get("announcement_date")
    announcement_date = None if pd.isna(announcement) else parse_date(announcement).isoformat()
    metadata = security.source_metadata
    pit = PITMetadata(
        period_end=latest["period_end"].isoformat(),
        announcement_date=announcement_date,
        available_date=latest["available_date"].isoformat(),
        as_of_date=selected_date.isoformat(),
        source=security.source,
        retrieval_date=metadata.get("retrieval_date"),
        source_version=metadata.get("source_version"),
        source_hash=metadata.get("source_hash"),
        availability_method=str(latest["availability_method"]),
        timestamp_confidence=str(latest["timestamp_confidence"]),
    )
    return ClassificationResult(
        symbol=security.symbol,
        company=security.company,
        industry=security.industry,
        sector_logic=security.sector_logic.value,
        peer_group=security.peer_group,
        financial_subtype=security.financial_subtype,
        as_of_date=selected_date.isoformat(),
        period_end=latest["period_end"].isoformat(),
        quality=quality.value,
        fundamental_state=state.value,
        state_detail=detail.value,
        valuation=valuation.value,
        research_classification=research_classification,
        data_quality=data_quality.value,
        quality_reasons=tuple(quality_reasons),
        fundamental_reasons=tuple(state_reasons),
        valuation_reasons=tuple(valuation_reasons),
        reason_codes=tuple(quality_codes + state_codes + valuation_codes),
        data_quality_flags=tuple(dict.fromkeys(flags)),
        metrics=metrics,
        intrinsic_value=intrinsic,
        pit_metadata=pit,
    )
