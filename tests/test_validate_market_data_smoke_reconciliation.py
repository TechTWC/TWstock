from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_market_data_smoke import SmokeValidationError, validate_smoke_output
from tests.test_validate_market_data_smoke import _valid_output


def test_manifest_reconciliation_state_must_match_reconciliation_file(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["reconciliation_state"] = "PRIMARY_VERIFIED"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    reconciliation_path = output / "reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["state"] = "SOURCE_MISMATCH"
    reconciliation_path.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")

    with pytest.raises(SmokeValidationError, match="reconciliation state mismatch"):
        validate_smoke_output(output, symbol="2330.TW", start="2026-06-01", end="2026-07-15")


def test_finmind_source_mismatch_fails_live_smoke_validation(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "finmind_state": "SECONDARY_ONLY",
            "finmind_secondary_available": True,
            "reconciliation_state": "SOURCE_MISMATCH",
            "cross_check_unavailable": False,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    reconciliation_path = output / "reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation.update(
        {
            "state": "SOURCE_MISMATCH",
            "issues": [
                {
                    "trade_date": "2026-07-15",
                    "field": "official_traded_value_twd",
                    "primary_value": 30000000,
                    "secondary_value": 29999999,
                }
            ],
            "cross_check_unavailable": False,
        }
    )
    reconciliation_path.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")

    with pytest.raises(
        SmokeValidationError,
        match="cross-source reconciliation did not verify.*SOURCE_MISMATCH",
    ):
        validate_smoke_output(output, symbol="2330.TW", start="2026-06-01", end="2026-07-15")


def test_primary_verified_with_finmind_unavailable_and_cross_check_unavailable_passes(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)

    result = validate_smoke_output(output, symbol="2330.TW", start="2026-06-01", end="2026-07-15")

    assert result["status"] == "PRIMARY_VERIFIED"
    assert result["reconciliation_state"] == "PRIMARY_VERIFIED"


def test_contradictory_cross_check_unavailable_values_fail(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    reconciliation_path = output / "reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["cross_check_unavailable"] = False
    reconciliation_path.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")

    with pytest.raises(SmokeValidationError, match="cross_check_unavailable mismatch"):
        validate_smoke_output(output, symbol="2330.TW", start="2026-06-01", end="2026-07-15")


def test_finmind_available_with_cross_check_unavailable_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["finmind_state"] = "SECONDARY_ONLY"
    manifest["finmind_secondary_available"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(SmokeValidationError, match="FinMind secondary data is available"):
        validate_smoke_output(output, symbol="2330.TW", start="2026-06-01", end="2026-07-15")
