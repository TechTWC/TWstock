from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.audit_2330_trial import (
    EXPECTED_PE,
    EXPECTED_TTM_NET_INCOME_RAW,
    EXPECTED_TTM_OPERATING_CASH_FLOW_RAW,
    EXPECTED_TTM_OPERATING_INCOME_RAW,
    FINANCIAL_EXTRACT,
    FinancialExtractTotals,
    UNVERIFIED_MARKET_CAP_REFERENCE_RAW,
    audit_financial_extract,
    audit_pe_cross_check,
    audit_snapshot_if_present,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/trial/phase_a1_real_snapshot.csv"
TWSE_20D = ROOT / "data/trial/sources/2330_twse_20d.csv"


def _read_financial_rows() -> list[dict[str, str]]:
    with FINANCIAL_EXTRACT.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_financial_rows(path: Path, rows: list[dict[str, str]]) -> Path:
    assert rows
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _raw_from_million(value: str) -> str:
    return str(Decimal(value) * Decimal("1000000"))


def test_financial_extract_raw_twd_conversions_and_ttm_totals() -> None:
    totals = audit_financial_extract()
    assert totals == FinancialExtractTotals(
        ttm_net_income_raw=EXPECTED_TTM_NET_INCOME_RAW,
        ttm_operating_income_raw=EXPECTED_TTM_OPERATING_INCOME_RAW,
        ttm_operating_cash_flow_raw=EXPECTED_TTM_OPERATING_CASH_FLOW_RAW,
    )


def test_snapshot_raw_twd_conversions_if_snapshot_is_present() -> None:
    audit_snapshot_if_present()


def test_pe_cross_check_uses_derived_ttm_net_income() -> None:
    totals = audit_financial_extract()
    audit_pe_cross_check(totals)
    pe = UNVERIFIED_MARKET_CAP_REFERENCE_RAW / totals.ttm_net_income_raw
    assert abs(pe - EXPECTED_PE) < Decimal("0.00000000000001")


def test_pe_cross_check_rejects_wrong_derived_ttm_net_income() -> None:
    bad_totals = FinancialExtractTotals(
        ttm_net_income_raw=Decimal("1"),
        ttm_operating_income_raw=EXPECTED_TTM_OPERATING_INCOME_RAW,
        ttm_operating_cash_flow_raw=EXPECTED_TTM_OPERATING_CASH_FLOW_RAW,
    )
    with pytest.raises(AssertionError, match="PE cross-check changed"):
        audit_pe_cross_check(bad_totals)


def test_blocked_trial_does_not_publish_canonical_snapshot() -> None:
    assert not SNAPSHOT.exists()


def test_financial_extract_includes_raw_twd_columns() -> None:
    with FINANCIAL_EXTRACT.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
    assert "operating_income_raw_twd" in reader.fieldnames
    assert "parent_net_income_raw_twd" in reader.fieldnames
    assert "operating_cash_flow_raw_twd" in reader.fieldnames


def test_twse_extract_remains_source_gap_only_without_claimed_turnover() -> None:
    assert not TWSE_20D.exists()


def test_financial_extract_rejects_removed_quarter(tmp_path: Path) -> None:
    rows = _read_financial_rows()[:-1]
    path = _write_financial_rows(tmp_path / "missing.csv", rows)
    with pytest.raises(AssertionError, match="Expected exactly four financial extract rows"):
        audit_financial_extract(path)


def test_financial_extract_rejects_duplicate_period(tmp_path: Path) -> None:
    rows = _read_financial_rows()
    rows[1] = {**rows[1], "period": rows[0]["period"]}
    path = _write_financial_rows(tmp_path / "duplicate.csv", rows)
    with pytest.raises(AssertionError, match="Duplicate financial extract periods"):
        audit_financial_extract(path)


def test_financial_extract_rejects_internally_consistent_zero_rows(tmp_path: Path) -> None:
    rows = _read_financial_rows()
    for row in rows:
        for field in ("operating_income", "parent_net_income", "operating_cash_flow"):
            row[f"{field}_million_twd"] = "0"
            row[f"{field}_raw_twd"] = "0"
    path = _write_financial_rows(tmp_path / "zero.csv", rows)
    with pytest.raises(AssertionError, match="TTM parent net income mismatch"):
        audit_financial_extract(path)


def test_financial_extract_rejects_correct_rows_with_wrong_ttm_total(tmp_path: Path) -> None:
    rows = _read_financial_rows()
    rows[0]["parent_net_income_million_twd"] = "1"
    rows[0]["parent_net_income_raw_twd"] = _raw_from_million("1")
    path = _write_financial_rows(tmp_path / "wrong-total.csv", rows)
    with pytest.raises(AssertionError, match="TTM parent net income mismatch"):
        audit_financial_extract(path)


def test_financial_extract_rejects_unexpected_fifth_period(tmp_path: Path) -> None:
    rows = _read_financial_rows()
    extra = {**rows[0], "period": "2026 Q2"}
    rows.append(extra)
    path = _write_financial_rows(tmp_path / "unexpected-fifth.csv", rows)
    with pytest.raises(AssertionError, match="Expected exactly four financial extract rows"):
        audit_financial_extract(path)
