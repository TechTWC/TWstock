from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_market_data_smoke import ValidationError, validate


def _write_valid_fixture(root: Path, token: str | None = None) -> None:
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True)
    raw_one = b'{"stat":"OK","month":"202606"}'
    raw_two = b'{"stat":"OK","month":"202607"}'
    for index, raw in enumerate((raw_one, raw_two), start=1):
        digest = hashlib.sha256(raw).hexdigest()
        raw_name = f"twse_{index}.raw"
        (raw_dir / raw_name).write_bytes(raw)
        (raw_dir / f"twse_{index}.metadata.json").write_text(
            json.dumps({"raw_file": raw_name, "sha256": digest}, indent=2),
            encoding="utf-8",
        )

    (root / "source_manifest.json").write_text(
        json.dumps(
            {
                "canonical_symbol": "2330.TW",
                "twse_state": "PRIMARY_VERIFIED",
                "finmind_error": "token=<redacted>",
                "note": "safe" if token is None else "token not included",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "reconciliation.json").write_text(json.dumps({"state": "PRIMARY_VERIFIED"}), encoding="utf-8")
    with (root / "twse_normalized.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "source_tier",
                "canonical_symbol",
                "trade_date",
                "traded_share_volume",
                "official_traded_value_twd",
                "raw_content_hash",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source": "TWSE",
                "source_tier": "PRIMARY",
                "canonical_symbol": "2330.TW",
                "trade_date": "2026-06-02",
                "traded_share_volume": "1000",
                "official_traded_value_twd": "500000",
                "raw_content_hash": hashlib.sha256(raw_one).hexdigest(),
            }
        )
        writer.writerow(
            {
                "source": "TWSE",
                "source_tier": "PRIMARY",
                "canonical_symbol": "2330.TW",
                "trade_date": "2026-07-01",
                "traded_share_volume": "2000",
                "official_traded_value_twd": "1000000",
                "raw_content_hash": hashlib.sha256(raw_two).hexdigest(),
            }
        )


def test_validate_accepts_complete_primary_verified_fixture(tmp_path: Path) -> None:
    _write_valid_fixture(tmp_path)

    validate(tmp_path, "2330.TW", "2026-06-01", "2026-07-15")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda root: (root / "source_manifest.json").unlink(), "source_manifest.json"),
        (lambda root: (root / "twse_normalized.csv").write_text("source\n", encoding="utf-8"), "TWSE records"),
        (
            lambda root: (root / "source_manifest.json").write_text(
                json.dumps({"canonical_symbol": "2330.TW", "twse_state": "SOURCE_UNAVAILABLE"}),
                encoding="utf-8",
            ),
            "twse_state",
        ),
        (
            lambda root: (root / "raw" / "twse_1.raw").write_bytes(b"changed"),
            "SHA-256 mismatch",
        ),
    ],
)
def test_validate_rejects_invalid_fixtures(tmp_path: Path, mutate, message: str) -> None:
    _write_valid_fixture(tmp_path)
    mutate(tmp_path)

    with pytest.raises(ValidationError, match=message):
        validate(tmp_path, "2330.TW", "2026-06-01", "2026-07-15")


def test_validate_rejects_secret_token_in_text_artifact(tmp_path: Path) -> None:
    _write_valid_fixture(tmp_path)
    (tmp_path / "leak.txt").write_text("abc secret-token-value xyz", encoding="utf-8")

    with pytest.raises(ValidationError, match="secret token"):
        validate(tmp_path, "2330.TW", "2026-06-01", "2026-07-15", "secret-token-value")


def test_validate_rejects_secondary_only_live_result(tmp_path: Path) -> None:
    _write_valid_fixture(tmp_path)
    (tmp_path / "source_manifest.json").write_text(
        json.dumps({"canonical_symbol": "2330.TW", "twse_state": "SOURCE_UNAVAILABLE"}),
        encoding="utf-8",
    )
    (tmp_path / "twse_normalized.csv").write_text("source\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="SOURCE_UNAVAILABLE"):
        validate(tmp_path, "2330.TW", "2026-06-01", "2026-07-15")
