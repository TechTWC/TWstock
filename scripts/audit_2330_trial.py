from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINANCIAL_EXTRACT = ROOT / "data/trial/sources/2330_financial_extract.csv"
SNAPSHOT = ROOT / "data/trial/phase_a1_real_snapshot.csv"
MILLION = Decimal("1000000")
EXPECTED_PE = Decimal("32.80537939074004")
EXPECTED_MARKET_CAP = Decimal("63274982963480")
EXPECTED_TTM_NET_INCOME_RAW = Decimal("1928799000000")

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


def _decimal(value: str) -> Decimal:
    return Decimal(value.strip())


def audit_financial_extract() -> None:
    with FINANCIAL_EXTRACT.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for field in FINANCIAL_FIELDS:
                million = _decimal(row[f"{field}_million_twd"])
                raw = _decimal(row[f"{field}_raw_twd"])
                expected = million * MILLION
                if raw != expected:
                    raise AssertionError(
                        f"{row['period']} {field}: {raw} != {million} * 1,000,000"
                    )


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


def audit_pe_cross_check() -> None:
    pe = EXPECTED_MARKET_CAP / EXPECTED_TTM_NET_INCOME_RAW
    if abs(pe - EXPECTED_PE) > Decimal("0.00000000000001"):
        raise AssertionError(f"PE cross-check changed: {pe} != {EXPECTED_PE}")


def main() -> int:
    audit_financial_extract()
    audit_snapshot_if_present()
    audit_pe_cross_check()
    print("2330 trial unit audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
