from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.breakout_tracker_v5 import BreakoutTracker, TrackerConfig
from experiments.continuous_high_monitor import ContinuousHighMonitor, MonitorConfig
from experiments.continuous_high_monitor.report import (
    write_feature_csv,
    write_html_report,
    write_timeline_csv,
)
from twstock_data.dataset import fetch_research_dataset, write_research_dataset
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
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.retries < 0:
        parser.error("--retries must be nonnegative")

    output = Path(args.output_dir)
    dataset = fetch_research_dataset(
        args.symbol,
        args.start,
        args.end,
        transport=transport,
        timeout=args.timeout,
        retries=args.retries,
        raw_cache_dir=Path(args.raw_cache_dir),
        allow_secondary_only=args.allow_secondary_only,
    )
    write_research_dataset(dataset, output)

    monitor_config = MonitorConfig()
    tracker_config = TrackerConfig()
    monitor_result = ContinuousHighMonitor(monitor_config).run(dataset.bars)
    breakout_snapshots = BreakoutTracker(tracker_config).run(dataset.bars)

    write_timeline_csv(monitor_result, output / "continuous_high_timeline.csv")
    write_feature_csv(
        monitor_result,
        monitor_config,
        output / "continuous_high_features.csv",
    )
    write_html_report(
        path=output / "continuous_high.html",
        bars=dataset.bars,
        result=monitor_result,
        config=monitor_config,
        breakout_snapshots=breakout_snapshots,
    )
    _write_breakout_csv(output / "breakout_snapshots.csv", breakout_snapshots)

    tracker_payload = asdict(tracker_config)
    tracker_hash = hashlib.sha256(stable_json_bytes(tracker_payload)).hexdigest()
    minimum_history_bars = max(monitor_config.high_windows) + 1
    history_sufficient = len(dataset.bars) >= minimum_history_bars
    run_manifest = {
        "schema_version": "TWSTOCK-REAL-MARKET-RUN-001",
        "run_type": "BOUNDED_EXPLORATORY_REAL_DATA",
        "canonical_symbol": dataset.canonical_symbol,
        "requested_start": dataset.requested_start,
        "requested_end": dataset.requested_end,
        "dataset_hash": dataset.dataset_hash,
        "dataset_source_state": dataset.source_state.value,
        "dataset_cross_check_unavailable": dataset.cross_check_unavailable,
        "price_basis": dataset.price_basis,
        "adjustment_policy": dataset.adjustment_policy,
        "corporate_actions_applied": dataset.corporate_actions_applied,
        "continuous_high_parameter_version": monitor_config.parameter_version,
        "continuous_high_parameter_hash": monitor_config.parameter_hash,
        "breakout_config": tracker_payload,
        "breakout_config_hash": tracker_hash,
        "bar_count": len(dataset.bars),
        "minimum_history_bars": minimum_history_bars,
        "history_sufficient_for_longest_high_window": history_sufficient,
        "continuous_high_event_count": len(monitor_result.events),
        "breakout_snapshot_count": len(breakout_snapshots),
        "outputs": {
            "market_bars": "market_bars.csv",
            "dataset_manifest": "dataset_manifest.json",
            "continuous_high_timeline": "continuous_high_timeline.csv",
            "continuous_high_features": "continuous_high_features.csv",
            "continuous_high_html": "continuous_high.html",
            "breakout_snapshots": "breakout_snapshots.csv",
        },
        "status": "EXPLORATORY_NOT_VALIDATED",
        "warnings": [
            (
                "Raw unadjusted market data; no corporate-action processing, "
                "performance validation, or investment-use approval."
            ),
            *(
                []
                if history_sufficient
                else [
                    "Requested history is shorter than the longest monitor window; "
                    "long-window fields remain unavailable rather than false."
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


if __name__ == "__main__":
    raise SystemExit(run())
