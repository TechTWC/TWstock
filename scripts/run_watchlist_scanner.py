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
from twstock_data.errors import SourceUnavailableError
from twstock_data.sources.tpex_cb import PostTransport, fetch_tpex_cb_market_snapshot
from twstock_data.sources.twse_market_bulk import (
    fetch_twse_bulk_research_datasets,
)
from twstock_data.sources.twse_universe import (
    fetch_twse_listed_common_stock_universe,
)


def run(
    argv: list[str] | None = None,
    *,
    transport: HttpTransport | None = None,
    cb_transport: PostTransport | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the seven-state Daily Taiwan Market Radar with independent MA "
            "and double-slope outputs on official raw daily prices. Shadow "
            "Observation only; corporate actions remain UNVERIFIED."
        )
    )
    universe = parser.add_mutually_exclusive_group(required=True)
    universe.add_argument("--watchlist")
    universe.add_argument(
        "--all-listed",
        action="store_true",
        help="Use the official TWSE listed-company universe (ordinary shares; TDR excluded).",
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--raw-cache-dir",
        required=True,
        help=(
            "Persistent TWSE cache. Watchlists reuse validated monthly files; "
            "--all-listed reuses validated all-market daily files."
        ),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Bounded HTTP retries per official request (default: 2).",
    )
    parser.add_argument(
        "--include-cb",
        action="store_true",
        help=(
            "Classify issuers with official TPEx current/recent CB data. "
            "A not-found result is not a never-issued claim."
        ),
    )
    parser.add_argument(
        "--max-new-market-days",
        type=int,
        default=10,
        help=(
            "Safety limit for new weekday downloads in --all-listed mode. "
            "Use a larger explicit value only for the first historical bootstrap."
        ),
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.retries < 0:
        parser.error("--retries must be nonnegative")
    if args.max_new_market_days < 0:
        parser.error("--max-new-market-days must be nonnegative")

    if args.all_listed:
        companies = fetch_twse_listed_common_stock_universe(
            transport=transport,
            timeout=args.timeout,
            retries=args.retries,
        )
        symbols = tuple(company.symbol for company in companies)
        symbol_names = {company.symbol: company.name for company in companies}
    else:
        symbols = load_watchlist(Path(args.watchlist))
        symbol_names = {}
    raw_root = Path(args.raw_cache_dir)
    cb_snapshot = (
        fetch_tpex_cb_market_snapshot(
            transport=cb_transport,
            timeout=args.timeout,
            retries=args.retries,
        )
        if args.include_cb
        else None
    )

    if args.all_listed:
        bulk_datasets = fetch_twse_bulk_research_datasets(
            symbols,
            args.start,
            args.end,
            cache_dir=raw_root,
            transport=transport,
            timeout=args.timeout,
            retries=args.retries,
            max_new_market_days=args.max_new_market_days,
        )

        def loader(symbol: str, start: str, end: str):
            del start, end
            try:
                return bulk_datasets[symbol]
            except KeyError as error:
                raise SourceUnavailableError(
                    f"bulk TWSE history unavailable for {symbol}"
                ) from error

    else:
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
        cb_snapshot=cb_snapshot,
        symbol_names=symbol_names,
    )
    write_watchlist_outputs(scan, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
