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


def _write_mismatched_output(tmp_path: Path) -> Path:
    output = tmp_path / "live_smoke"
    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True)

    raw_body = b'{"stat":"OK","title":"2330 test response"}'
    digest = hashlib.sha256(raw_body).hexdigest()
    raw_name = "twse_2330_20260701.raw"
    (raw_dir / raw_name).write_bytes(raw_body)
    (raw_dir / "twse_2330_20260701.metadata.json").write_text(
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
                "finmind_state": "SECONDARY_ONLY",
                "finmind_secondary_available": True,
                "reconciliation_state": "SOURCE_MISMATCH",
                "cross_check_unavailable": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "reconciliation.json").write_text(
        json.dumps(
            {
                "state": "SOURCE_MISMATCH",
                "records": [],
                "issues": [
                    {
                        "trade_date": "2026-07-15",
                        "field": "official_traded_value_twd",
                        "primary_value": 30000000,
                        "secondary_value": 29999999,
                    }
                ],
                "cross_check_unavailable": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with (output / "twse_normalized.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
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
                "trade_date": "2026-07-15",
                "traded_share_volume": "20000",
                "official_traded_value_twd": "30000000",
                "raw_content_hash": digest,
            }
        )

    return output


def test_finmind_source_mismatch_fails_live_smoke_validation(tmp_path: Path) -> None:
    output = _write_mismatched_output(tmp_path)

    with pytest.raises(
        SmokeValidationError,
        match="cross-source reconciliation did not verify.*SOURCE_MISMATCH",
    ):
        validate_smoke_output(
            output,
            symbol="2330.TW",
            start="2026-06-01",
            end="2026-07-15",
        )
