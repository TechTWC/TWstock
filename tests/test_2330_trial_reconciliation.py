from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from scripts.audit_2330_trial import (
    EXPECTED_MARKET_CAP,
    EXPECTED_PE,
    EXPECTED_TTM_NET_INCOME_RAW,
    audit_financial_extract,
    audit_pe_cross_check,
    audit_snapshot_if_present,
)

ROOT = Path(__file__).resolve().parents[1]
FINANCIAL_EXTRACT = ROOT / "data/trial/sources/2330_financial_extract.csv"
SNAPSHOT = ROOT / "data/trial/phase_a1_real_snapshot.csv"
TWSE_20D = ROOT / "data/trial/sources/2330_twse_20d.csv"


def test_financial_extract_raw_twd_conversions() -> None:
    audit_financial_extract()


def test_snapshot_raw_twd_conversions_if_snapshot_is_present() -> None:
    audit_snapshot_if_present()


def test_pe_cross_check_uses_corrected_million_twd_conversion() -> None:
    audit_pe_cross_check()
    pe = EXPECTED_MARKET_CAP / EXPECTED_TTM_NET_INCOME_RAW
    assert abs(pe - EXPECTED_PE) < Decimal("0.00000000000001")


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
