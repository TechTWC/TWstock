from __future__ import annotations
import argparse, csv, json
from dataclasses import asdict
from pathlib import Path
from .normalization import canonical_symbol
from .sources.twse import fetch_twse_daily, TWSE_STOCK_DAY_ENDPOINT
from .sources.finmind import fetch_finmind_daily, FINMIND_DAILY_ENDPOINT
from .reconciliation import reconcile_market_data

def _write_csv(path: Path, records):
    if not records: return
    path.parent.mkdir(parents=True, exist_ok=True)
    rows=[asdict(r) for r in records]
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="cmd", required=True)
    p=sub.add_parser("fetch-market"); p.add_argument("--symbol", required=True); p.add_argument("--start", required=True); p.add_argument("--end", required=True); p.add_argument("--output-dir", required=True)
    args=parser.parse_args(argv)
    source_symbol=args.symbol.removesuffix(".TW"); canonical=canonical_symbol(source_symbol,"TW"); out=Path(args.output_dir)
    twse=fetch_twse_daily(source_symbol,args.start,args.end); fin=fetch_finmind_daily(source_symbol,canonical,args.start,args.end)
    rec=reconcile_market_data(twse, fin.records)
    _write_csv(out/"twse_normalized.csv", twse); _write_csv(out/"finmind_normalized.csv", fin.records)
    (out/"reconciliation.json").write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8")
    manifest={"twse_endpoint":TWSE_STOCK_DAY_ENDPOINT,"finmind_endpoint":FINMIND_DAILY_ENDPOINT,"finmind_state":fin.state.value,"record_count":len(twse)}
    (out/"source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
