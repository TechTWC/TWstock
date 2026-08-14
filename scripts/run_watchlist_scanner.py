from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.watchlist_scanner import (
    load_watchlist,
    scan_watchlist,
    write_watchlist_outputs,
)
from twstock_data.dataset import fetch_official_research_dataset
from twstock_data.http import HttpTransport


def run(
    argv: list[str] | None = None, *, transport: HttpTransport | None = None
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan multiple TWSE-listed symbols with incremental official raw "
            "daily prices and a standalone visual report. "
            "Shadow Observation only; corporate actions remain UNVERIFIED."
        )
    )
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--raw-cache-dir",
        required=True,
        help=(
            "Persistent TWSE cache. Completed historical months resume from "
            "validated cache; the actual current month is always refreshed."
        ),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Bounded HTTP retries per TWSE month (default: 2).",
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.retries < 0:
        parser.error("--retries must be nonnegative")

    symbols = load_watchlist(Path(args.watchlist))
    raw_root = Path(args.raw_cache_dir)

    def loader(symbol: str, start: str, end: str):
        return fetch_official_research_dataset(
            symbol,
            start,
            end,
            transport=transport,
            timeout=args.timeout,
            retries=args.retries,
            raw_cache_dir=raw_root / symbol,
            incremental_cache=True,
        )

    scan = scan_watchlist(
        symbols,
        args.start,
        args.end,
        dataset_loader=loader,
    )
    write_watchlist_outputs(scan, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
