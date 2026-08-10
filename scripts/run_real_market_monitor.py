from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.breakout_tracker_v5 import TrackerConfig
from experiments.continuous_high_monitor import MonitorConfig, MonitorResult
from experiments.continuous_high_monitor.report import (
    write_feature_csv,
    write_html_report,
    write_timeline_csv,
)
from twstock_data.dataset import fetch_research_dataset, write_research_dataset
from twstock_data.corporate_actions import (
    AnalysisGuardState,
    CORPORATE_ACTION_POLICY_VERSION,
    FinMindBearerTransport,
    fetch_finmind_corporate_actions,
    write_analysis_guard_csv,
    write_corporate_action_dataset,
)
from twstock_data.guarded_monitors import (
    run_guarded_breakout_tracker,
    run_guarded_continuous_high,
)
from twstock_data.http import HttpTransport
from twstock_data.normalization import stable_json_bytes


def run(argv: list[str] | None = None, *, transport: HttpTransport | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch reconciled Taiwan daily bars and run bounded research monitors."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--raw-cache-dir", required=True)
    parser.add_argument("--allow-secondary-only", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    if args.retries < 0:
        parser.error("--retries must be nonnegative")

    output = Path(args.output_dir)
    token = os.environ.get("FINMIND_TOKEN")
    authenticated_transport = (
        FinMindBearerTransport(transport, token) if token else transport
    )
    dataset = fetch_research_dataset(
        args.symbol,
        args.start,
        args.end,
        transport=authenticated_transport,
        timeout=args.timeout,
        retries=args.retries,
        raw_cache_dir=Path(args.raw_cache_dir),
        allow_secondary_only=args.allow_secondary_only,
    )
    corporate_actions = fetch_finmind_corporate_actions(
        args.symbol,
        args.start,
        args.end,
        transport=authenticated_transport,
        timeout=args.timeout,
        retries=args.retries,
        raw_cache_dir=Path(args.raw_cache_dir),
    )
    write_research_dataset(dataset, output)
    write_corporate_action_dataset(corporate_actions, output)

    monitor_config = MonitorConfig()
    tracker_config = TrackerConfig()
    monitor_result, monitor_guard = run_guarded_continuous_high(
        dataset.bars,
        corporate_actions.events,
        monitor_config,
    )
    breakout_snapshots, breakout_guard = run_guarded_breakout_tracker(
        dataset.bars,
        corporate_actions.events,
        tracker_config,
    )
    write_analysis_guard_csv(
        output / "analysis_guard.csv",
        (*monitor_guard, *breakout_guard),
    )

    write_timeline_csv(monitor_result, output / "continuous_high_timeline.csv")
    write_feature_csv(
        monitor_result,
        monitor_config,
        output / "continuous_high_features.csv",
    )
    report_bars, report_result, report_breakout = _latest_safe_report_view(
        dataset.bars,
        monitor_result,
        breakout_snapshots,
        monitor_guard,
    )
    write_html_report(
        path=output / "continuous_high.html",
        bars=report_bars,
        result=report_result,
        config=monitor_config,
        breakout_snapshots=report_breakout,
    )
    _write_breakout_csv(output / "breakout_snapshots.csv", breakout_snapshots)

    tracker_payload = asdict(tracker_config)
    tracker_hash = hashlib.sha256(stable_json_bytes(tracker_payload)).hexdigest()
    research_input_hash = hashlib.sha256(
        stable_json_bytes(
            {
                "schema_version": "TWSTOCK-GUARDED-RESEARCH-INPUT-001",
                "market_dataset_hash": dataset.dataset_hash,
                "corporate_action_dataset_hash": corporate_actions.dataset_hash,
                "corporate_action_policy_version": CORPORATE_ACTION_POLICY_VERSION,
                "continuous_high_parameter_hash": monitor_config.parameter_hash,
                "breakout_config_hash": tracker_hash,
            }
        )
    ).hexdigest()
    minimum_history_bars = max(monitor_config.high_windows) + 1
    history_sufficient = len(dataset.bars) >= minimum_history_bars
    clean_history_sufficient = bool(monitor_guard) and (
        monitor_guard[-1].clean_segment_bars >= minimum_history_bars
    )
    continuous_guard_ready = bool(monitor_guard) and (
        monitor_guard[-1].state is AnalysisGuardState.ALLOWED
    )
    breakout_guard_ready = bool(breakout_guard) and (
        breakout_guard[-1].state is AnalysisGuardState.ALLOWED
    )
    run_manifest = {
        "schema_version": "TWSTOCK-REAL-MARKET-RUN-002",
        "run_type": "BOUNDED_EXPLORATORY_REAL_DATA",
        "canonical_symbol": dataset.canonical_symbol,
        "requested_start": dataset.requested_start,
        "requested_end": dataset.requested_end,
        "dataset_hash": dataset.dataset_hash,
        "corporate_action_dataset_hash": corporate_actions.dataset_hash,
        "research_input_hash": research_input_hash,
        "dataset_source_state": dataset.source_state.value,
        "dataset_cross_check_unavailable": dataset.cross_check_unavailable,
        "price_basis": dataset.price_basis,
        "adjustment_policy": dataset.adjustment_policy,
        "corporate_actions_applied": dataset.corporate_actions_applied,
        "corporate_action_guard_applied": True,
        "corporate_action_coverage_state": corporate_actions.coverage_state.value,
        "corporate_action_source_tier": "SECONDARY",
        "corporate_action_policy_version": corporate_actions.policy_version,
        "corporate_action_event_count": len(corporate_actions.events),
        "continuous_high_parameter_version": monitor_config.parameter_version,
        "continuous_high_parameter_hash": monitor_config.parameter_hash,
        "breakout_config": tracker_payload,
        "breakout_config_hash": tracker_hash,
        "bar_count": len(dataset.bars),
        "minimum_history_bars": minimum_history_bars,
        "history_sufficient_for_longest_high_window": history_sufficient,
        "clean_history_sufficient_for_longest_high_window": clean_history_sufficient,
        "continuous_high_guard_ready_on_last_bar": continuous_guard_ready,
        "breakout_guard_ready_on_last_bar": breakout_guard_ready,
        "analysis_blocked_row_count": sum(
            item.state is AnalysisGuardState.ANALYSIS_BLOCKED
            for item in (*monitor_guard, *breakout_guard)
        ),
        "continuous_high_event_count": len(monitor_result.events),
        "breakout_snapshot_count": len(breakout_snapshots),
        "continuous_high_html_scope": "LATEST_SAFE_SEGMENT",
        "continuous_high_html_bar_count": len(report_bars),
        "outputs": {
            "market_bars": "market_bars.csv",
            "dataset_manifest": "dataset_manifest.json",
            "corporate_actions": "corporate_actions.csv",
            "corporate_action_manifest": "corporate_action_manifest.json",
            "analysis_guard": "analysis_guard.csv",
            "continuous_high_timeline": "continuous_high_timeline.csv",
            "continuous_high_features": "continuous_high_features.csv",
            "continuous_high_html": "continuous_high.html",
            "breakout_snapshots": "breakout_snapshots.csv",
        },
        "status": "EXPLORATORY_NOT_VALIDATED",
        "warnings": [
            (
                "Raw unadjusted market data; corporate actions only block contaminated "
                "analysis windows and do not adjust prices, returns, or holdings."
            ),
            (
                "Corporate-action coverage is complete across four FinMind query datasets "
                "but remains secondary-source only and is not TWSE-cross-verified."
            ),
            *(
                []
                if history_sufficient
                else [
                    "Requested history is shorter than the longest monitor window; "
                    "long-window fields remain unavailable rather than false."
                ]
            ),
            *(
                []
                if not history_sufficient or clean_history_sufficient
                else [
                    "Total history is long enough, but the latest post-action clean "
                    "segment is shorter than the longest monitor window."
                ]
            ),
        ],
    }
    (output / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


def _write_breakout_csv(path: Path, snapshots) -> None:
    fields = (
        "symbol",
        "trade_date",
        "state",
        "pivot_date",
        "pivot_price",
        "breakout_date",
        "days_since_breakout",
        "close",
        "distance_to_pivot_pct",
        "volume_ratio",
        "reason",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in snapshots:
            writer.writerow(
                {
                    "symbol": item.symbol,
                    "trade_date": item.trade_date.isoformat(),
                    "state": item.state.value,
                    "pivot_date": item.pivot_date.isoformat(),
                    "pivot_price": f"{item.pivot_price:.10g}",
                    "breakout_date": (
                        item.breakout_date.isoformat() if item.breakout_date else ""
                    ),
                    "days_since_breakout": (
                        "" if item.days_since_breakout is None else item.days_since_breakout
                    ),
                    "close": f"{item.close:.10g}",
                    "distance_to_pivot_pct": f"{item.distance_to_pivot_pct:.10g}",
                    "volume_ratio": (
                        "" if item.volume_ratio is None else f"{item.volume_ratio:.10g}"
                    ),
                    "reason": item.reason,
                }
            )


def _latest_safe_report_view(
    bars,
    result: MonitorResult,
    breakout_snapshots,
    guard_decisions,
):
    observed_action_dates = [
        item.latest_effective_date
        for item in guard_decisions
        if item.latest_effective_date is not None
    ]
    if not observed_action_dates:
        return tuple(bars), result, tuple(breakout_snapshots)

    latest_action = max(observed_action_dates)
    report_dates = {
        item.trade_date
        for item in guard_decisions
        if item.latest_effective_date == latest_action
        and item.state is AnalysisGuardState.ALLOWED
    }
    report_bars = tuple(item for item in bars if item.trade_date in report_dates)
    report_features = tuple(
        item for item in result.feature_rows if item.trade_date in report_dates
    )
    report_snapshots = tuple(
        item for item in result.snapshots if item.trade_date in report_dates
    )
    report_events = tuple(
        item for item in result.events if item.trade_date in report_dates
    )
    first = report_snapshots[0] if report_snapshots else None
    report_result = MonitorResult(
        symbol=result.symbol,
        parameter_version=result.parameter_version,
        parameter_hash=result.parameter_hash,
        first_discovery_date=first.trade_date if first else None,
        first_discovery_close=first.close if first else None,
        feature_rows=report_features,
        snapshots=report_snapshots,
        events=report_events,
    )
    report_breakout = tuple(
        item for item in breakout_snapshots if item.trade_date in report_dates
    )
    return report_bars, report_result, report_breakout


if __name__ == "__main__":
    raise SystemExit(run())
