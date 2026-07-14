from __future__ import annotations

from .models import (
    ActionResolution,
    EarningsDirectionResult,
    EligibilityResult,
    FundamentalResult,
    StockSnapshot,
    ValuationResult,
)


PRIMARY_ACTION_ORDER = (
    "DATA_REVIEW",
    "NOT_ELIGIBLE",
    "EXCLUDE",
    "FUNDAMENTAL_REVIEW",
    "VALUATION_WAIT",
    "VALUE_TRAP_REVIEW",
    "VALUE_CANDIDATE",
    "VALUATION_WATCH",
)

_NEGATIVE_EARNINGS_STATUSES = {
    "EARNINGS_WEAK",
    "TURNAROUND_NEGATIVE",
    "BOTH_NON_POSITIVE",
}


def _data_quality_flags(snapshot: StockSnapshot) -> tuple[str, ...]:
    flags: list[str] = []
    if not snapshot.required_data_valid:
        flags.append("REQUIRED_DATA_INVALID")
    if not snapshot.financial_data_usable:
        flags.append("FINANCIAL_DATA_UNUSABLE")
    return tuple(flags)


def resolve_primary_action(
    snapshot: StockSnapshot,
    eligibility: EligibilityResult,
    fundamental: FundamentalResult,
    valuation: ValuationResult,
    earnings: EarningsDirectionResult,
) -> ActionResolution:
    """Resolve exactly one primary action using v1.10 precedence."""

    data_flags = _data_quality_flags(snapshot)
    if data_flags:
        return ActionResolution("DATA_REVIEW", data_flags, data_flags)

    if eligibility.status != "ELIGIBLE":
        return ActionResolution("NOT_ELIGIBLE", eligibility.reasons, data_flags)

    if fundamental.status == "FUNDAMENTAL_FAIL":
        return ActionResolution(
            "EXCLUDE", ("FUNDAMENTAL_FAIL",), data_flags
        )

    if fundamental.status == "FUNDAMENTAL_WATCH":
        return ActionResolution(
            "FUNDAMENTAL_REVIEW", ("FUNDAMENTAL_WATCH",), data_flags
        )

    if valuation.status == "VALUATION_UNKNOWN":
        return ActionResolution(
            "DATA_REVIEW", valuation.reasons or ("VALUATION_UNKNOWN",), data_flags
        )

    if valuation.status == "VALUATION_NOT_CHEAP":
        return ActionResolution(
            "VALUATION_WAIT", ("VALUATION_NOT_CHEAP",), data_flags
        )

    if earnings.status in _NEGATIVE_EARNINGS_STATUSES:
        return ActionResolution(
            "VALUE_TRAP_REVIEW",
            (valuation.status, earnings.status),
            data_flags,
        )

    if valuation.status in {"VERY_LOW_VALUATION", "ABSOLUTE_CHEAP"}:
        return ActionResolution(
            "VALUE_CANDIDATE",
            ("FUNDAMENTAL_PASS", valuation.status, earnings.status),
            data_flags,
        )

    return ActionResolution(
        "VALUATION_WATCH",
        (valuation.status, earnings.status),
        data_flags,
    )
