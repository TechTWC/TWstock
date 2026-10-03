from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from twstock_data.normalization import canonical_symbol, source_symbol_from_input


class SmokeValidationError(RuntimeError):
    """Raised when live market-data smoke outputs are incomplete or inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SmokeValidationError(f"required file is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeValidationError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise SmokeValidationError(f"JSON root must be an object: {path}")
    return value


def _read_twse_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SmokeValidationError(f"required file is missing: {path}")
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise SmokeValidationError(f"CSV header is missing: {path}")
            rows = list(reader)
    except OSError as exc:
        raise SmokeValidationError(f"unable to read CSV file: {path}") from exc
    if not rows:
        raise SmokeValidationError("TWSE live smoke returned no normalized records")
    return rows


def _positive_integer(value: str, field: str, row_number: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SmokeValidationError(
            f"row {row_number} has invalid integer {field}: {value!r}"
        ) from exc
    if number <= 0:
        raise SmokeValidationError(
            f"row {row_number} has nonpositive {field}: {number}"
        )
    return number


def _scan_for_secret(output_dir: Path, secret_value: str | None) -> None:
    if not secret_value:
        return
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        if secret_value in text:
            raise SmokeValidationError(f"secret value leaked into artifact: {path}")


def _validate_reconciliation(
    manifest: dict[str, Any],
    reconciliation: dict[str, Any],
) -> None:
    manifest_state = manifest.get("reconciliation_state")
    reconciliation_state = reconciliation.get("state")

    if manifest_state != reconciliation_state:
        raise SmokeValidationError(
            "reconciliation state mismatch between source_manifest.json and "
            f"reconciliation.json: {manifest_state!r} != {reconciliation_state!r}"
        )
    if reconciliation_state != "PRIMARY_VERIFIED":
        raise SmokeValidationError(
            "live cross-source reconciliation did not verify the primary data: "
            f"{reconciliation_state or 'UNKNOWN'}"
        )

    manifest_cross_check = manifest.get("cross_check_unavailable")
    reconciliation_cross_check = reconciliation.get("cross_check_unavailable")
    if manifest_cross_check != reconciliation_cross_check:
        raise SmokeValidationError(
            "cross_check_unavailable mismatch between source_manifest.json and "
            "reconciliation.json"
        )

    finmind_available = bool(manifest.get("finmind_secondary_available")) or (
        manifest.get("finmind_state") == "SECONDARY_ONLY"
    )
    if finmind_available and manifest_cross_check is True:
        raise SmokeValidationError(
            "FinMind secondary data is available but reconciliation reports the "
            "cross-check as unavailable"
        )


def _validate_raw_evidence(
    raw_dir: Path,
    normalized_hashes: set[str],
) -> tuple[int, set[str]]:
    if not raw_dir.is_dir():
        raise SmokeValidationError(f"raw cache directory is missing: {raw_dir}")

    metadata_paths = sorted(raw_dir.rglob("*.metadata.json"))
    if not metadata_paths:
        raise SmokeValidationError("no raw response metadata files were preserved")

    preserved_hashes: set[str] = set()
    for metadata_path in metadata_paths:
        metadata = _load_json(metadata_path)
        raw_name = metadata.get("raw_file")
        expected_hash = metadata.get("sha256")
        if not isinstance(raw_name, str) or not raw_name:
            raise SmokeValidationError(
                f"raw metadata is missing raw_file: {metadata_path}"
            )
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise SmokeValidationError(
                f"raw metadata has invalid sha256: {metadata_path}"
            )
        raw_path = metadata_path.parent / raw_name
        if not raw_path.is_file():
            raise SmokeValidationError(f"preserved raw file is missing: {raw_path}")
        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise SmokeValidationError(
                f"raw SHA-256 mismatch for {raw_path}: {actual_hash} != {expected_hash}"
            )
        preserved_hashes.add(actual_hash)

    missing_hashes = sorted(normalized_hashes - preserved_hashes)
    if missing_hashes:
        raise SmokeValidationError(
            "normalized TWSE rows reference raw hashes without preserved evidence: "
            + ", ".join(missing_hashes)
        )
    return len(metadata_paths), preserved_hashes


def validate_smoke_output(
    output_dir: Path,
    *,
    symbol: str,
    start: str,
    end: str,
    secret_value: str | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    manifest = _load_json(output_dir / "source_manifest.json")
    reconciliation = _load_json(output_dir / "reconciliation.json")
    source_symbol = source_symbol_from_input(symbol)
    expected_canonical = canonical_symbol(source_symbol, "TW")

    if manifest.get("canonical_symbol") != expected_canonical:
        raise SmokeValidationError(
            "source manifest canonical symbol mismatch: "
            f"{manifest.get('canonical_symbol')!r} != {expected_canonical!r}"
        )
    if manifest.get("requested_start") != start or manifest.get("requested_end") != end:
        raise SmokeValidationError(
            "source manifest requested range does not match workflow inputs"
        )

    twse_state = manifest.get("twse_state")
    if twse_state != "PRIMARY_VERIFIED":
        raise SmokeValidationError(
            f"TWSE live smoke did not verify the primary source: "
            f"{twse_state or 'UNKNOWN'}"
        )

    _validate_reconciliation(manifest, reconciliation)
    rows = _read_twse_rows(output_dir / "twse_normalized.csv")

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except ValueError as exc:
        raise SmokeValidationError("workflow date inputs must use ISO YYYY-MM-DD") from exc
    if start_date > end_date:
        raise SmokeValidationError("workflow start date is after end date")

    dates: list[date] = []
    normalized_hashes: set[str] = set()
    required_fields = {
        "source",
        "source_tier",
        "canonical_symbol",
        "trade_date",
        "traded_share_volume",
        "official_traded_value_twd",
        "raw_content_hash",
    }
    for row_number, row in enumerate(rows, start=2):
        missing = sorted(field for field in required_fields if not row.get(field))
        if missing:
            raise SmokeValidationError(
                f"row {row_number} is missing required values: {', '.join(missing)}"
            )
        if row["source"] != "TWSE":
            raise SmokeValidationError(
                f"row {row_number} has non-TWSE source: {row['source']!r}"
            )
        if row["source_tier"] != "PRIMARY":
            raise SmokeValidationError(
                f"row {row_number} has non-primary source tier: {row['source_tier']!r}"
            )
        if row["canonical_symbol"] != expected_canonical:
            raise SmokeValidationError(
                f"row {row_number} canonical symbol mismatch: {row['canonical_symbol']!r}"
            )
        try:
            trade_date = date.fromisoformat(row["trade_date"])
        except ValueError as exc:
            raise SmokeValidationError(
                f"row {row_number} has invalid trade_date: {row['trade_date']!r}"
            ) from exc
        if not (start_date <= trade_date <= end_date):
            raise SmokeValidationError(
                f"row {row_number} trade_date is outside the requested range: {trade_date}"
            )
        dates.append(trade_date)
        _positive_integer(row["traded_share_volume"], "traded_share_volume", row_number)
        _positive_integer(
            row["official_traded_value_twd"],
            "official_traded_value_twd",
            row_number,
        )
        raw_content_hash = row["raw_content_hash"]
        if len(raw_content_hash) != 64:
            raise SmokeValidationError(
                f"row {row_number} has invalid raw_content_hash: {raw_content_hash!r}"
            )
        normalized_hashes.add(raw_content_hash)

    if len(dates) != len(set(dates)):
        raise SmokeValidationError("TWSE normalized records contain duplicate trade dates")
    if dates != sorted(dates):
        raise SmokeValidationError("TWSE normalized records are not sorted by trade_date")

    metadata_count, preserved_hashes = _validate_raw_evidence(
        output_dir / "raw",
        normalized_hashes,
    )
    _scan_for_secret(output_dir, secret_value)

    return {
        "status": "PRIMARY_VERIFIED",
        "reconciliation_state": "PRIMARY_VERIFIED",
        "canonical_symbol": expected_canonical,
        "record_count": len(rows),
        "first_trade_date": dates[0].isoformat(),
        "last_trade_date": dates[-1].isoformat(),
        "raw_metadata_count": metadata_count,
        "preserved_raw_hash_count": len(preserved_hashes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args(argv)

    try:
        result = validate_smoke_output(
            Path(args.output_dir),
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            secret_value=os.environ.get("FINMIND_TOKEN"),
        )
    except SmokeValidationError as exc:
        print(f"LIVE MARKET-DATA SMOKE FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
