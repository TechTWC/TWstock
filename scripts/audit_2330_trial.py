from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINANCIAL_EXTRACT = ROOT / "data/trial/sources/2330_financial_extract.csv"
SNAPSHOT = ROOT / "data/trial/phase_a1_real_snapshot.csv"
MILLION = Decimal("1000000")
EXPECTED_PE = Decimal("32.80537939074004")
# Arithmetic reference only: this market-cap basis remains unverified until
# outstanding shares and treasury-share treatment are reconciled.
UNVERIFIED_MARKET_CAP_REFERENCE_RAW = Decimal("63274982963480")
EXPECTED_TTM_NET_INCOME_RAW = Decimal("1928799000000")
EXPECTED_TTM_OPERATING_INCOME_RAW = Decimal("2187977000000")
EXPECTED_TTM_OPERATING_CASH_FLOW_RAW = Decimal("2348378000000")
EXPECTED_PERIODS = frozenset({"2025 Q2", "2025 Q3", "2025 Q4", "2026 Q1"})

FINANCIAL_FIELDS = (
    "operating_income",
    "parent_net_income",
    "operating_cash_flow",
)

CANONICAL_MILLION_VALUES = {
    "ttm_net_income": Decimal("1928799"),
    "ttm_operating_income": Decimal("2187977"),
    "ttm_operating_cash_flow": Decimal("2348378"),
    "latest_equity": Decimal("5932389"),
    "latest_total_assets": Decimal("8660950"),
    "latest_total_liabilities": Decimal("2728561"),
    "latest_current_assets": Decimal("4265512"),
    "latest_current_liabilities": Decimal("1714254"),
    "latest_q_operating_income": Decimal("658966"),
    "previous_q_operating_income": Decimal("564903"),
    "prior_year_q_operating_income": Decimal("407081"),
}


@dataclass(frozen=True)
class FinancialExtractTotals:
    ttm_net_income_raw: Decimal
    ttm_operating_income_raw: Decimal
    ttm_operating_cash_flow_raw: Decimal


def _decimal(value: str) -> Decimal:
    return Decimal(value.strip())


def audit_financial_extract(
    path: Path = FINANCIAL_EXTRACT,
) -> FinancialExtractTotals:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 4:
        raise AssertionError(f"Expected exactly four financial extract rows, got {len(rows)}")

    periods = [row["period"].strip() for row in rows]
    duplicate_periods = sorted({period for period in periods if periods.count(period) > 1})
    if duplicate_periods:
        raise AssertionError("Duplicate financial extract periods: " + ", ".join(duplicate_periods))

    period_set = set(periods)
    missing_periods = sorted(EXPECTED_PERIODS - period_set)
    unexpected_periods = sorted(period_set - EXPECTED_PERIODS)
    if missing_periods or unexpected_periods:
        details = []
        if missing_periods:
            details.append("missing: " + ", ".join(missing_periods))
        if unexpected_periods:
            details.append("unexpected: " + ", ".join(unexpected_periods))
        raise AssertionError("Invalid financial extract periods (" + "; ".join(details) + ")")

    totals = {field: Decimal("0") for field in FINANCIAL_FIELDS}
    for row in rows:
        for field in FINANCIAL_FIELDS:
            million = _decimal(row[f"{field}_million_twd"])
            raw = _decimal(row[f"{field}_raw_twd"])
            expected = million * MILLION
            if raw != expected:
                raise AssertionError(
                    f"{row['period']} {field}: {raw} != {million} * 1,000,000"
                )
            totals[field] += raw

    derived = FinancialExtractTotals(
        ttm_net_income_raw=totals["parent_net_income"],
        ttm_operating_income_raw=totals["operating_income"],
        ttm_operating_cash_flow_raw=totals["operating_cash_flow"],
    )
    if derived.ttm_net_income_raw != EXPECTED_TTM_NET_INCOME_RAW:
        raise AssertionError(
            f"TTM parent net income mismatch: {derived.ttm_net_income_raw} "
            f"!= {EXPECTED_TTM_NET_INCOME_RAW}"
        )
    if derived.ttm_operating_income_raw != EXPECTED_TTM_OPERATING_INCOME_RAW:
        raise AssertionError(
            f"TTM operating income mismatch: {derived.ttm_operating_income_raw} "
            f"!= {EXPECTED_TTM_OPERATING_INCOME_RAW}"
        )
    if derived.ttm_operating_cash_flow_raw != EXPECTED_TTM_OPERATING_CASH_FLOW_RAW:
        raise AssertionError(
            f"TTM operating cash flow mismatch: {derived.ttm_operating_cash_flow_raw} "
            f"!= {EXPECTED_TTM_OPERATING_CASH_FLOW_RAW}"
        )
    return derived


def audit_snapshot_if_present() -> None:
    if not SNAPSHOT.exists():
        return
    with SNAPSHOT.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise AssertionError("phase_a1_real_snapshot.csv must contain exactly one row")
    row = rows[0]
    for field, million in CANONICAL_MILLION_VALUES.items():
        raw = _decimal(row[field])
        expected = million * MILLION
        if raw != expected:
            raise AssertionError(f"{field}: {raw} != {million} * 1,000,000")


def audit_pe_cross_check(totals: FinancialExtractTotals) -> None:
    pe = UNVERIFIED_MARKET_CAP_REFERENCE_RAW / totals.ttm_net_income_raw
    if abs(pe - EXPECTED_PE) > Decimal("0.00000000000001"):
        raise AssertionError(f"PE cross-check changed: {pe} != {EXPECTED_PE}")


def main() -> int:
    totals = audit_financial_extract()
    audit_snapshot_if_present()
    audit_pe_cross_check(totals)
    print("2330 trial unit audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
