from __future__ import annotations
import argparse, csv, json
from dataclasses import asdict
from pathlib import Path
from .errors import SourceUnavailableError
from .normalization import canonical_symbol, redact_tokens_in_text, sanitize_url, source_symbol_from_input, validate_date_range
from .sources.twse import fetch_twse_daily, TWSE_STOCK_DAY_ENDPOINT
from .sources.finmind import fetch_finmind_daily, FINMIND_DAILY_ENDPOINT
from .reconciliation import reconcile_market_data
from .models import SourceResult, SourceState

def _record_dict(record):
    row = asdict(record)
    row["source_tier"] = record.source_tier.value
    return row

def _write_csv(path: Path, records):
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_record_dict(record) for record in records]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def _json_safe(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return value

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch-market")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--raw-cache-dir")
    args = parser.parse_args(argv)
    validate_date_range(args.start, args.end)
    source_symbol = source_symbol_from_input(args.symbol)
    canonical = canonical_symbol(source_symbol, "TW")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_cache_dir = Path(args.raw_cache_dir) if args.raw_cache_dir else None
    twse_records = ()
    twse_state = SourceState.PRIMARY_VERIFIED
    twse_error = None
    try:
        twse_records = fetch_twse_daily(source_symbol, args.start, args.end, raw_cache_dir=raw_cache_dir)
        if not twse_records:
            twse_state = SourceState.SOURCE_UNAVAILABLE
            twse_error = "TWSE returned no records for requested range"
    except SourceUnavailableError as e:
        twse_state = SourceState.SOURCE_UNAVAILABLE
        twse_error = redact_tokens_in_text(sanitize_url(str(e)))
    finmind_result = fetch_finmind_daily(source_symbol, canonical, args.start, args.end, raw_cache_dir=raw_cache_dir)
    reconciliation = reconcile_market_data(twse_records, finmind_result.records, twse_error)
    _write_csv(out / "twse_normalized.csv", twse_records)
    _write_csv(out / "finmind_normalized.csv", finmind_result.records)
    (out / "reconciliation.json").write_text(json.dumps(_json_safe(reconciliation), ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "requested_symbol": args.symbol,
        "source_symbol": source_symbol,
        "canonical_symbol": canonical,
        "requested_start": args.start,
        "requested_end": args.end,
        "twse_endpoint": TWSE_STOCK_DAY_ENDPOINT,
        "twse_state": twse_state.value,
        "twse_error": twse_error,
        "finmind_endpoint": FINMIND_DAILY_ENDPOINT,
        "finmind_state": finmind_result.state.value,
        "finmind_error": finmind_result.error,
        "finmind_secondary_available": bool(finmind_result.records),
        "reconciliation_state": reconciliation.state.value,
        "cross_check_unavailable": reconciliation.cross_check_unavailable,
        "record_count": len(twse_records),
    }
    (out / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
