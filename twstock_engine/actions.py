from __future__ import annotations

from .models import StockSnapshot

CHEAP_STATUSES = {"VERY_LOW_VALUATION", "ABSOLUTE_CHEAP"}
POSITIVE_EARNINGS = {"EARNINGS_OK", "TURNAROUND_POSITIVE"}


def resolve_primary_action(
    snapshot: StockSnapshot,
    eligibility_status: str,
    fundamental_status: str,
    valuation_status: str,
    earnings_direction: str,
    settings: dict,
) -> tuple[str, list[str], list[str]]:
    trigger_reasons: list[str] = []
    data_quality_flags: list[str] = []

    if not snapshot.required_data_valid:
        data_quality_flags.append("REQUIRED_DATA_INVALID")
    if not snapshot.financial_data_usable:
        data_quality_flags.append("FINANCIAL_DATA_UNUSABLE")
    if data_quality_flags:
        return "DATA_REVIEW", trigger_reasons, data_quality_flags

    if eligibility_status != "ELIGIBLE":
        return "NOT_ELIGIBLE", [eligibility_status], data_quality_flags
    if fundamental_status == "FUNDAMENTAL_FAIL":
        return "EXCLUDE", [fundamental_status], data_quality_flags
    if fundamental_status == "FUNDAMENTAL_WATCH":
        return "FUNDAMENTAL_REVIEW", [fundamental_status], data_quality_flags
    if valuation_status == "VALUATION_UNKNOWN":
        return "FUNDAMENTAL_REVIEW", [valuation_status], data_quality_flags
    if valuation_status == "VALUATION_NOT_CHEAP":
        return "VALUATION_WAIT", [valuation_status], data_quality_flags
    if valuation_status == "FAIR_VALUATION":
        return "VALUATION_WATCH", [valuation_status], data_quality_flags
    if valuation_status in CHEAP_STATUSES and earnings_direction in POSITIVE_EARNINGS:
        return "VALUE_CANDIDATE", [valuation_status, earnings_direction], data_quality_flags
    if valuation_status in CHEAP_STATUSES:
        return "VALUE_TRAP_REVIEW", [valuation_status, earnings_direction], data_quality_flags
    return "VALUATION_WATCH", [valuation_status, earnings_direction], data_quality_flags
