from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


class ValidationError(AssertionError):
    pass


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise ValidationError(f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValidationError(f"missing required file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_no_secret(root: Path, secret: str | None) -> None:
    if not secret:
        return
    for path in root.rglob("*"):
        if path.is_file() and path.suffix != ".raw":
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if secret in text:
                raise ValidationError(f"secret token value appears in text artifact: {path}")


def validate(output_dir: Path, symbol: str, start: str, end: str, secret: str | None = None) -> None:
    manifest = _load_json(output_dir / "source_manifest.json")
    _load_json(output_dir / "reconciliation.json")
    rows = _read_csv(output_dir / "twse_normalized.csv")

    if not rows:
        if manifest.get("twse_state") == "SOURCE_UNAVAILABLE":
            raise ValidationError("SOURCE_UNAVAILABLE: TWSE returned no primary records")
        raise ValidationError("TWSE records are empty")

    if manifest.get("canonical_symbol") != symbol:
        raise ValidationError(f"manifest canonical_symbol {manifest.get('canonical_symbol')!r} != {symbol!r}")
    if manifest.get("twse_state") != "PRIMARY_VERIFIED":
        raise ValidationError(f"twse_state must be PRIMARY_VERIFIED, got {manifest.get('twse_state')!r}")

    dates = [row["trade_date"] for row in rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValidationError("TWSE trade dates must be unique and ascending")

    raw_hashes: set[str] = set()
    for row in rows:
        trade_date = row["trade_date"]
        if not (start <= trade_date <= end):
            raise ValidationError(f"TWSE trade date outside requested range: {trade_date}")
        if row.get("canonical_symbol") != symbol:
            raise ValidationError(f"row canonical_symbol mismatch on {trade_date}")
        if row.get("source") != "TWSE":
            raise ValidationError(f"row source must be TWSE on {trade_date}")
        if row.get("source_tier") != "PRIMARY":
            raise ValidationError(f"row source_tier must be PRIMARY on {trade_date}")
        if int(row["traded_share_volume"]) <= 0:
            raise ValidationError(f"nonpositive traded_share_volume on {trade_date}")
        if int(row["official_traded_value_twd"]) <= 0:
            raise ValidationError(f"nonpositive official_traded_value_twd on {trade_date}")
        raw_hashes.add(row["raw_content_hash"])

    metadata_paths = sorted((output_dir / "raw").glob("*.metadata.json"))
    if not metadata_paths:
        raise ValidationError("raw metadata files are missing")

    preserved_hashes: set[str] = set()
    for metadata_path in metadata_paths:
        metadata = _load_json(metadata_path)
        raw_file = metadata.get("raw_file")
        if not raw_file:
            raise ValidationError(f"metadata missing raw_file: {metadata_path}")
        raw_path = metadata_path.parent / raw_file
        if not raw_path.exists():
            raise ValidationError(f"raw file referenced by metadata is missing: {raw_path}")
        digest = _sha256(raw_path)
        if metadata.get("sha256") != digest:
            raise ValidationError(f"metadata SHA-256 mismatch: {metadata_path}")
        preserved_hashes.add(digest)

    missing_hashes = raw_hashes - preserved_hashes
    if missing_hashes:
        raise ValidationError(f"normalized raw_content_hash values lack preserved raw files: {sorted(missing_hashes)}")

    _assert_no_secret(output_dir, secret)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate manual live market-data smoke-test outputs.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--secret", default=None)
    args = parser.parse_args(argv)
    try:
        validate(args.output_dir, args.symbol, args.start, args.end, args.secret)
    except ValidationError as exc:
        print(exc)
        return 1
    print("market data smoke validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
