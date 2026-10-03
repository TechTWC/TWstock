from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.double_slope_turning import (
    DoubleSlopeConfig,
    DoubleSlopeTurningEngine,
    compare_with_ma_baseline,
    write_comparison_outputs,
)
from experiments.moving_average_state import MAStateConfig, MovingAverageStateEngine
from twstock_data.dataset import read_research_bars_csv
from twstock_data.errors import DataValidationError


RESEARCH_SOURCE_URL = "https://onlinelibrary.wiley.com/doi/10.1002/sam.11411"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an offline Shadow Observation comparison of a paper-inspired "
            "consecutive-slope detector and the frozen classic-MA baseline."
        )
    )
    parser.add_argument(
        "--input-root",
        required=True,
        help="Existing watchlist output containing symbols/*/market_bars.csv.",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    input_root = Path(args.input_root)
    symbols_root = input_root / "symbols"
    if not symbols_root.is_dir():
        parser.error("--input-root must contain a symbols directory")
    bars_by_symbol = {}
    source_manifests = {}
    double_slope_results = []
    ma_results = []
    double_slope_engine = DoubleSlopeTurningEngine(DoubleSlopeConfig())
    ma_engine = MovingAverageStateEngine(MAStateConfig())
    for symbol_dir in sorted(path for path in symbols_root.iterdir() if path.is_dir()):
        bars_path = symbol_dir / "market_bars.csv"
        manifest_path = symbol_dir / "dataset_manifest.json"
        if not bars_path.is_file() or not manifest_path.is_file():
            raise DataValidationError(f"incomplete symbol evidence directory: {symbol_dir.name}")
        bars = read_research_bars_csv(bars_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise DataValidationError(f"invalid dataset manifest: {symbol_dir.name}") from error
        if not isinstance(manifest, dict):
            raise DataValidationError(f"dataset manifest root must be object: {symbol_dir.name}")
        symbol = bars[0].symbol
        if manifest.get("canonical_symbol") != symbol:
            raise DataValidationError(f"dataset manifest symbol mismatch: {symbol_dir.name}")
        bars_by_symbol[symbol] = bars
        source_manifests[symbol] = manifest
        double_slope_results.append(double_slope_engine.run(bars))
        ma_results.append(ma_engine.run(bars))
    if not double_slope_results:
        parser.error("--input-root contains no complete symbol evidence")
    comparison = compare_with_ma_baseline(
        double_slope_results,
        ma_results,
        bars_by_symbol,
    )
    write_comparison_outputs(
        double_slope_results,
        ma_results,
        comparison,
        bars_by_symbol,
        Path(args.output_dir),
        source_manifests=source_manifests,
        research_source_url=RESEARCH_SOURCE_URL,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
