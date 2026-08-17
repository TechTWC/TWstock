from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.moving_average_state import (
    MAStateConfig,
    MovingAverageStateEngine,
    write_outputs,
)
from twstock_data.dataset import read_research_bars_csv
from twstock_data.errors import DataValidationError


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an offline, no-score classic moving-average state and long-term context report "
            "from previously preserved official-TWSE watchlist evidence."
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
    results = []
    config = MAStateConfig()
    engine = MovingAverageStateEngine(config)
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
        results.append(engine.run(bars))
    if not results:
        parser.error("--input-root contains no complete symbol evidence")
    write_outputs(
        results,
        bars_by_symbol,
        Path(args.output_dir),
        source_manifests=source_manifests,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
