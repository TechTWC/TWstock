from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from twstock_data.errors import MarketDataError
from twstock_data.sources.mops_face_value_change import fetch_face_value_change_history
from twstock_data.sources.security_identity import (
    AUTO, TPEX, TWSE, resolve_security_identity,
)
from twstock_data.sources.twse_corporate_actions import (
    FACE_VALUE_CHANGE_REVERSE_SPLIT, FACE_VALUE_CHANGE_SPLIT,
    fetch_corporate_action_history as fetch_twse_corporate_actions,
)
from twstock_data.sources.tpex_corporate_actions import (
    fetch_corporate_action_history as fetch_tpex_corporate_actions,
)
from twstock_data.sources.twse_valuation import (
    HISTORY_START as TWSE_HISTORY_START, completed_session_cutoff,
    fetch_history as fetch_twse_history,
)
from twstock_data.sources.tpex_valuation import (
    HISTORY_START as TPEX_HISTORY_START, fetch_history as fetch_tpex_history,
)
from twstock_valuation.pe_river import DEFAULT_MULTIPLES, build_metadata, calculate_rivers, select_coverage, years_before
from twstock_valuation.corporate_actions import (
    build_corporate_action_metadata, normalize_for_corporate_actions,
)
from twstock_valuation.pe_river_pdf import write_report


def run(argv=None, *, transport=None, now=None) -> int:
    parser = argparse.ArgumentParser(
        description="Official TWSE/TPEx historical PE river PDF (ordinary common shares only)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--market", choices=(AUTO, TWSE, TPEX), default=AUTO)
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--max", action="store_true", help="All available official history (default)")
    window.add_argument("--years", type=int, choices=(5, 10, 20))
    parser.add_argument("--multiples", type=float, nargs="+", default=DEFAULT_MULTIPLES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--request-interval", type=float, default=1,
                        help="Minimum seconds between official requests (default: 1)")
    args = parser.parse_args(argv)
    if (not math.isfinite(args.timeout) or args.timeout <= 0 or args.retries < 0
            or not math.isfinite(args.request_interval) or args.request_interval < 0):
        parser.error("timeout must be positive; retries and request interval must be nonnegative")
    try:
        calculate_rivers((), args.multiples)
        identity = resolve_security_identity(
            args.symbol, args.market, transport=transport,
            timeout=args.timeout, retries=args.retries)
        cutoff = completed_session_cutoff(now)
        history_start = (TPEX_HISTORY_START if identity.market == TPEX
                         else TWSE_HISTORY_START)
        start = (max(history_start, years_before(cutoff, args.years).replace(day=1))
                 if args.years else history_start)
        output = args.output_dir or ROOT / "outputs" / "pe_river" / args.symbol
        cache = (args.cache_dir or ROOT / "data" / "runtime" / "raw" / "pe_river" /
                 identity.market / identity.canonical_symbol)
        fetch_history = fetch_tpex_history if identity.market == TPEX else fetch_twse_history
        history_kwargs = ({"company_name": identity.company_short_name}
                          if identity.market == TPEX else {})
        history = fetch_history(
            args.symbol, start, cutoff, cache, transport=transport,
            timeout=args.timeout, retries=args.retries,
            request_interval=args.request_interval,
            refresh_date=now.date() if now else None,
            progress=lambda result: print(
                f"{result['month']}: close={result['close_status']} PE={result['pe_status']}",
                flush=True), **history_kwargs)
        observations, requested_start = select_coverage(
            history.observations, args.years, history_start=history_start)
        rows = calculate_rivers(observations, args.multiples)
        fetch_actions = (fetch_tpex_corporate_actions if identity.market == TPEX
                         else fetch_twse_corporate_actions)
        action_kwargs = ({"company_name": identity.company_short_name}
                         if identity.market == TPEX else {})
        actions = fetch_actions(
            args.symbol, observations[0].trade_date, cutoff, cache,
            transport=transport, timeout=args.timeout, retries=args.retries,
            request_interval=args.request_interval,
            refresh_date=now.date() if now else None,
            progress=lambda result: print(
                f"action {result['source']} {result['year']}: "
                f"{result['status']} events={result['event_count']}", flush=True),
            **action_kwargs,
        )
        face_value = fetch_face_value_change_history(
            args.symbol, observations[0].trade_date, cutoff, cache,
            market=identity.market,
            transport=transport, timeout=args.timeout, retries=args.retries,
            request_interval=args.request_interval,
            refresh_date=now.date() if now else None,
        )
        # MOPS category-11 details contain exact old/new par values and take
        # precedence over a same-date TPEx price-reference face-value row.
        mops_face_keys = {(event.effective_date, event.action_type)
                          for event in face_value.events}
        exchange_events = tuple(event for event in actions.events if not (
            event.action_type in {FACE_VALUE_CHANGE_SPLIT,
                                  FACE_VALUE_CHANGE_REVERSE_SPLIT}
            and (event.effective_date, event.action_type) in mops_face_keys))
        all_events = exchange_events + face_value.events
        print(
            "action MOPS face value: "
            f"{face_value.proof.status} rows={face_value.proof.result_count} "
            f"details={face_value.proof.detail_count} events={len(face_value.events)}",
            flush=True,
        )
        normalized = normalize_for_corporate_actions(
            observations, all_events, args.multiples,
            analysis_end_date=cutoff,
        )
        metadata = build_metadata(rows, requested_coverage=f"{args.years}Y" if args.years else "MAX",
            requested_start=requested_start, multiples=args.multiples, cutoff=cutoff,
            month_results=history.month_results, source_start=history.source_start,
            identity=identity)
        metadata = build_corporate_action_metadata(
            normalized, all_events, metadata,
            actions.request_results + face_value.request_results,
            face_value_proof=face_value.proof)
        saved = write_report(
            rows, metadata, output, normalized_rows=normalized, events=all_events)
        print(f"PDF: {saved['outputs']['pdf']}")
        print(f"Identity: {identity.canonical_symbol} {identity.market} {identity.company_name}")
        print(f"Coverage: {saved['actual_start_date']} -> {saved['actual_end_date']}; "
              f"{saved['valid_pe_observation_count']} valid PE / {saved['observation_count']} observations")
        print(f"Latest PE: raw={saved['latest_pe']} normalized={saved['latest_normalized_pe']}; "
              f"corporate actions={len(saved['corporate_action_events'])}")
        return 0
    except (MarketDataError, ValueError, OSError) as exc:
        print(f"PE river report failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
