from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Sequence

from .actions import resolve_primary_action
from .models import InputValidationError, ScreeningResult, Settings, StockSnapshot
from .report import write_csv, write_html, write_json
from .rules import (
    calculate_absolute_pe_status,
    evaluate_earnings_direction,
    evaluate_eligibility,
    evaluate_fundamental_status,
)


def screen_snapshot(snapshot: StockSnapshot, settings: Settings) -> ScreeningResult:
    eligibility = evaluate_eligibility(snapshot, settings)
    fundamental = evaluate_fundamental_status(snapshot, settings)
    valuation = calculate_absolute_pe_status(snapshot, settings)
    earnings = evaluate_earnings_direction(snapshot, settings)
    action = resolve_primary_action(
        snapshot, eligibility, fundamental, valuation, earnings
    )

    risk_flags = list(fundamental.risk_flags)
    if earnings.status in {
        "EARNINGS_WEAK",
        "TURNAROUND_NEGATIVE",
        "BOTH_NON_POSITIVE",
    }:
        risk_flags.append(earnings.status)

    informational_tags = list(fundamental.informational_tags)
    if snapshot.is_synthetic:
        informational_tags.append("SYNTHETIC_TEST_DATA")

    return ScreeningResult(
        snapshot=snapshot,
        eligibility=eligibility,
        fundamental=fundamental,
        valuation=valuation,
        earnings=earnings,
        action=action,
        risk_flags=tuple(dict.fromkeys(risk_flags)),
        informational_tags=tuple(dict.fromkeys(informational_tags)),
    )


def load_snapshots(path: Path) -> list[StockSnapshot]:
    if not path.exists():
        raise InputValidationError(f"Input CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputValidationError("Input CSV has no header")
        snapshots: list[StockSnapshot] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                snapshots.append(StockSnapshot.from_csv_row(row))
            except InputValidationError as exc:
                raise InputValidationError(f"Row {row_number}: {exc}") from exc
    if not snapshots:
        raise InputValidationError("Input CSV contains no stock rows")
    return snapshots


def run(input_path: Path, output_dir: Path, settings_path: Path) -> list[ScreeningResult]:
    settings = Settings.load(settings_path)
    snapshots = load_snapshots(input_path)
    results = [screen_snapshot(snapshot, settings) for snapshot in snapshots]

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, output_dir / "screening_results.csv")
    write_json(
        results,
        output_dir / "screening_results.json",
        release_name=settings.release_name,
        strategy_name=settings.strategy_name,
        strategy_version=settings.strategy_version,
    )
    write_html(
        results,
        output_dir / "report.html",
        release_name=settings.release_name,
        strategy_name=settings.strategy_name,
        strategy_version=settings.strategy_version,
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Phase A1 deterministic logic sandbox."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--settings", type=Path, default=Path("config/settings.yaml")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        results = run(args.input, args.output_dir, args.settings)
    except InputValidationError as exc:
        parser.error(str(exc))

    counts = Counter(result.action.primary_action for result in results)
    print(f"Processed {len(results)} stocks")
    for action, count in sorted(counts.items()):
        print(f"{action}: {count}")
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
