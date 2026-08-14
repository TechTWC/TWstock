from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_market_data_smoke import (
    SmokeValidationError,
    validate_smoke_output,
)


CSV_FIELDS = [
    "source",
    "source_tier",
    "source_symbol",
    "canonical_symbol",
    "market",
    "trade_date",
    "traded_share_volume",
    "official_traded_value_twd",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "transaction_count",
    "retrieved_at",
    "source_reference",
    "raw_content_hash",
]


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _valid_output(tmp_path: Path) -> Path:
    output = tmp_path / "live_smoke"
    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True)

    raw_body = b'{"stat":"OK","title":"2330 test response"}'
    digest = hashlib.sha256(raw_body).hexdigest()
    raw_name = "twse_2330_20260601.raw"
    (raw_dir / raw_name).write_bytes(raw_body)
    (raw_dir / "twse_2330_20260601.metadata.json").write_text(
        json.dumps(
            {
                "source": "TWSE",
                "source_tier": "PRIMARY",
                "source_symbol": "2330",
                "canonical_symbol": "2330.TW",
                "requested_start": "2026-06-01",
                "requested_end": "2026-07-15",
                "retrieval_timestamp": "2026-07-16T00:00:00+00:00",
                "sanitized_source_url": "https://www.twse.com.tw/example?stockNo=2330",
                "http_status": 200,
                "sha256": digest,
                "raw_file": raw_name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (output / "source_manifest.json").write_text(
        json.dumps(
            {
                "requested_symbol": "2330.TW",
                "source_symbol": "2330",
                "canonical_symbol": "2330.TW",
                "requested_start": "2026-06-01",
                "requested_end": "2026-07-15",
                "twse_state": "PRIMARY_VERIFIED",
                "finmind_state": "SOURCE_UNAVAILABLE",
                "reconciliation_state": "PRIMARY_VERIFIED",
                "cross_check_unavailable": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "reconciliation.json").write_text(
        json.dumps(
            {
                "state": "PRIMARY_VERIFIED",
                "records": [],
                "issues": [],
                "cross_check_unavailable": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    base = {
        "source": "TWSE",
        "source_tier": "PRIMARY",
        "source_symbol": "2330",
        "canonical_symbol": "2330.TW",
        "market": "TW",
        "traded_share_volume": "20000",
        "official_traded_value_twd": "30000000",
        "open_price": "100.0",
        "high_price": "101.0",
        "low_price": "99.0",
        "close_price": "100.0",
        "transaction_count": "1234",
        "retrieved_at": "2026-07-16T00:00:00+00:00",
        "source_reference": "https://www.twse.com.tw/example",
        "raw_content_hash": digest,
    }
    rows = [
        {**base, "trade_date": "2026-06-30"},
        {**base, "trade_date": "2026-07-15"},
    ]
    _write_rows(output / "twse_normalized.csv", rows)
    return output


def _validate(output: Path, secret_value: str | None = None) -> dict:
    return validate_smoke_output(
        output,
        symbol="2330.TW",
        start="2026-06-01",
        end="2026-07-15",
        secret_value=secret_value,
    )


def test_valid_primary_verified_smoke_output_passes(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    result = _validate(output)
    assert result["status"] == "PRIMARY_VERIFIED"
    assert result["record_count"] == 2
    assert result["first_trade_date"] == "2026-06-30"
    assert result["last_trade_date"] == "2026-07-15"


def test_missing_required_output_file_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    (output / "reconciliation.json").unlink()
    with pytest.raises(SmokeValidationError, match="required file is missing"):
        _validate(output)


def test_empty_twse_normalized_output_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    _write_rows(output / "twse_normalized.csv", [])
    with pytest.raises(SmokeValidationError, match="no normalized records"):
        _validate(output)


def test_unsorted_twse_dates_fail(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    rows = list(reversed(_read_rows(output / "twse_normalized.csv")))
    _write_rows(output / "twse_normalized.csv", rows)
    with pytest.raises(SmokeValidationError, match="not sorted"):
        _validate(output)


def test_raw_sha_mismatch_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    raw_path = next((output / "raw").glob("*.raw"))
    raw_path.write_bytes(b"changed after metadata was written")
    with pytest.raises(SmokeValidationError, match="SHA-256 mismatch"):
        _validate(output)


def test_secret_value_in_text_artifact_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    secret = "DO_NOT_LEAK_THIS_TOKEN"
    (output / "leaked.txt").write_text(f"token={secret}", encoding="utf-8")
    with pytest.raises(SmokeValidationError, match="secret value leaked"):
        _validate(output, secret_value=secret)


def test_secondary_only_or_unavailable_twse_fails(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    manifest_path = output / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["twse_state"] = "SOURCE_UNAVAILABLE"
    manifest["finmind_state"] = "SECONDARY_ONLY"
    manifest["reconciliation_state"] = "SECONDARY_ONLY"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(SmokeValidationError, match="SOURCE_UNAVAILABLE"):
        _validate(output)
