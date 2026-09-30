from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
import math
from typing import Sequence

from twstock_data.sources.twse_valuation import HISTORY_START, ValuationObservation

DEFAULT_MULTIPLES = (15.0, 20.0, 25.0, 30.0, 35.0)


@dataclass(frozen=True)
class RiverObservation:
    observation: ValuationObservation
    reference_eps_twd: float | None
    band_prices: tuple[float | None, ...]


def years_before(day: date, years: int) -> date:
    if years not in (5, 10, 20):
        raise ValueError("years must be 5, 10, or 20")
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def select_coverage(observations: Sequence[ValuationObservation], years: int | None = None):
    if not observations:
        raise ValueError("no historical observations")
    latest = observations[-1].trade_date
    start = max(HISTORY_START, years_before(latest, years)) if years else HISTORY_START
    return tuple(row for row in observations if row.trade_date >= start), start


def calculate_rivers(observations: Sequence[ValuationObservation], multiples=DEFAULT_MULTIPLES):
    multiples = tuple(float(m) for m in multiples)
    if (not multiples or any(not math.isfinite(m) or m <= 0 for m in multiples)
            or tuple(sorted(set(multiples))) != multiples):
        raise ValueError("multiples must be distinct, increasing, positive finite numbers")
    output = []
    previous = None
    symbol = None
    for row in observations:
        if previous is not None and row.trade_date <= previous:
            raise ValueError("observations must have unique chronological dates")
        if symbol is not None and row.symbol != symbol:
            raise ValueError("mixed symbols")
        if not math.isfinite(row.official_close) or row.official_close <= 0:
            raise ValueError("invalid official close")
        pe = row.official_pe
        # Defense in depth: unavailable/nonpositive PE cannot produce EPS.
        eps = row.official_close / pe if pe is not None and math.isfinite(pe) and pe > 0 else None
        bands = tuple(eps * m if eps is not None else None for m in multiples)
        if eps is not None and (not math.isfinite(eps) or any(not math.isfinite(b) for b in bands)):
            raise ValueError("nonfinite river calculation")
        output.append(RiverObservation(row, eps, bands))
        previous, symbol = row.trade_date, row.symbol
    return tuple(output)


def distribution(pe_values: Sequence[float], current: float | None) -> dict:
    values = sorted(v for v in pe_values if v is not None and math.isfinite(v) and v > 0)
    def quantile(p):
        if not values:
            return None
        position = (len(values) - 1) * p
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (position - low)
    return {"p10": quantile(.10), "p25": quantile(.25), "p50": quantile(.50),
            "p75": quantile(.75), "p90": quantile(.90),
            "current_percentile": (100 * bisect_right(values, current) / len(values)
                if values and current is not None and math.isfinite(current) and current > 0 else None),
            "quantile_method": "linear interpolation at (n-1)*p",
            "rank_method": "empirical CDF: 100 * count(PE <= latest valid PE) / valid count"}


def build_metadata(rows: Sequence[RiverObservation], *, requested_coverage: str,
                   requested_start: date, multiples=DEFAULT_MULTIPLES,
                   cutoff: date | None = None, month_results=()):
    if not rows:
        raise ValueError("empty report")
    valid = [r for r in rows if r.reference_eps_twd is not None]
    latest = valid[-1].observation if valid else None
    first, last = rows[0].observation, rows[-1].observation
    pe_stats = distribution([r.observation.official_pe for r in valid], latest.official_pe if latest else None)
    relevant_missing = [result for result in month_results
        if (any(first.trade_date.isoformat() <= d <= last.trade_date.isoformat()
                for d in result.get("missing_pe_dates", []))
            or (first.trade_date.strftime("%Y-%m") <= result["month"] <= last.trade_date.strftime("%Y-%m")
                and result.get("close_count") == 0))]
    status = "SOURCE_GAPS" if relevant_missing else (
        "SHORTER_AVAILABLE_HISTORY" if first.trade_date > requested_start + timedelta(days=7) else "AVAILABLE_HISTORY")
    return {
        "schema_version": "TWSTOCK-PE-RIVER-PDF-001", "symbol": first.symbol,
        "requested_coverage": requested_coverage, "requested_start": requested_start.isoformat(),
        "requested_end_cutoff": cutoff.isoformat() if cutoff else last.trade_date.isoformat(),
        "actual_start_date": first.trade_date.isoformat(), "actual_end_date": last.trade_date.isoformat(),
        "years_covered": (last.trade_date - first.trade_date).days / 365.2425,
        "observation_count": len(rows), "valid_pe_observation_count": len(valid),
        "missing_pe_count": len(rows) - len(valid), "coverage_status": status,
        "coverage_note": "Actual official observations; no trading-calendar completeness claim. Later listing, holidays, or unavailable source history may limit the start.",
        "latest_market_date": last.trade_date.isoformat(), "latest_close": last.official_close,
        "latest_valid_pe_date": latest.trade_date.isoformat() if latest else None,
        "latest_valid_pe_close": latest.official_close if latest else None,
        "latest_pe": latest.official_pe if latest else None,
        "percentiles": pe_stats, "multiples": list(multiples),
        "eps_semantics": "TWSE-implied reference EPS = same-day official unadjusted close / official PE; not reported or diluted accounting EPS. Subject to published PE rounding.",
        "source_contract": "TWSE BWIBBU monthly PE and STOCK_DAY_AVG daily close, exact symbol/name and trading-date join. BWIBBU has no close column or code in its title. STOCK_DAY_AVG title verifies code; names must match.",
        "source_semantics_url": "https://www.twse.com.tw/zh/trading/historical/bwibbu.html",
        "source_semantics": "Contemporaneous most-recent-four-quarter reference earnings; no historical back-calculation or corporate-action adjustment applied here. TWSE can substitute a reference price on days without a closing price; unmatched dates fail closed.",
        "unavailable_policy": "Blank, -, --, zero or negative PE -> PE_UNAVAILABLE; malformed numeric -> fail closed; no fill/interpolation.",
        "incomplete_months": [r["month"] for r in relevant_missing],
        "month_results": list(month_results),
    }
