from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.fundamental_quality_valuation.data import (  # noqa: E402
    fetch_finmind_dataset,
    normalize_market,
)
from experiments.fundamental_quality_valuation.stage_a import (  # noqa: E402
    AVAILABLE_DATE_PROXY,
    MOPS_CONFLICT,
    MOPS_EXACT,
    build_financial_timeline,
    build_signal_timeline,
    canonical_hash,
    coverage_frame,
    load_offline_mops_archive,
    sha256_path,
    validate_stage_a_frames,
    verify_restored_cache,
)
from scripts.checkpoint_0050_mops_cache_v0_1 import (  # noqa: E402
    restore_checkpoint,
    verify_checkpoint,
)


STARTING_HEAD = "e369d88f6c5ddb116ec3990e99ea876c4d3039b6"
DEFAULT_CHECKPOINT = ROOT / "artifacts/0050_fundamental_v0_1/checkpoints/mops_20260904"
DEFAULT_CACHE = ROOT / "outputs/raw_fundamental_predictive_v0_1/mops"
DEFAULT_MARKET_CACHE = ROOT / "outputs/fundamental_stage_a_market"
DEFAULT_OUTPUT = ROOT / "artifacts/0050_fundamental_v0_1"
DEFAULT_NORMALIZED = DEFAULT_OUTPUT / "0050_normalized_financials_pit_v0.1.csv"
DEFAULT_UNIVERSE = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
DEFAULT_CONFIG = ROOT / "config/fundamental_quality_valuation_v0_1.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Stage A MOPS-aware PIT artifacts without MOPS network I/O")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--mops-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--market-cache", type=Path, default=DEFAULT_MARKET_CACHE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normalized", type=Path, default=DEFAULT_NORMALIZED)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--refresh-market", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    return parser


def _load_universe(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    required = {"symbol", "company", "sector_logic", "peer_group", "financial_subtype"}
    missing = required.difference(frame.columns)
    if missing or frame.empty or frame["symbol"].duplicated().any():
        raise ValueError(f"Invalid fixed cohort: missing={sorted(missing)}")
    return frame.sort_values("symbol").reset_index(drop=True)


def _market(symbol: str, config: dict[str, Any], cache: Path, refresh: bool) -> pd.DataFrame:
    price = fetch_finmind_dataset(
        "TaiwanStockPrice",
        symbol,
        config["history_start"],
        config["as_of_date"],
        cache,
        refresh=refresh,
    )
    per = fetch_finmind_dataset(
        "TaiwanStockPER",
        symbol,
        config["history_start"],
        config["as_of_date"],
        cache,
        refresh=refresh,
    )
    return normalize_market(price["data"], per["data"])


def _load_markets(
    symbols: list[str], config: dict[str, Any], cache: Path, refresh: bool, workers: int
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_market, symbol, config, cache, refresh): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            result[symbol] = future.result()
            print(f"[market] {symbol}: {len(result[symbol])} sessions", flush=True)
    return result


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    compression = {"method": "gzip", "compresslevel": 9, "mtime": 0} if path.suffix == ".gz" else None
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
        compression=compression,
    )


def _update_manifest(output_dir: Path, stage_summary: dict[str, Any]) -> None:
    manifest_path = output_dir / "artifact_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    payload["stage_a"] = stage_summary
    payload["artifacts"] = [
        {"path": path.name, "sha256": sha256_path(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != manifest_path.name
    ]
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("--workers must be between 1 and 8")
    current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not subprocess.call(
        ["git", "merge-base", "--is-ancestor", STARTING_HEAD, current_head], cwd=ROOT
    ) == 0:
        raise RuntimeError(f"Current head is not descended from frozen starting head {STARTING_HEAD}")

    checkpoint = verify_checkpoint(args.checkpoint_dir)
    restore_checkpoint(args.checkpoint_dir, args.mops_cache)
    restored_files = verify_restored_cache(
        args.mops_cache,
        args.checkpoint_dir / "mops_cache_inventory.csv",
    )
    if checkpoint["resume"]["next_network_requests_required"] != 0:
        raise RuntimeError("Frozen checkpoint requires additional MOPS network requests")
    print(f"[checkpoint] verified and restored {restored_files} files; MOPS network requests=0", flush=True)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    universe = _load_universe(args.universe)
    normalized = pd.read_csv(args.normalized, dtype={"symbol": str}, encoding="utf-8-sig", low_memory=False)
    if set(normalized["symbol"].astype(str)) != set(universe["symbol"]):
        raise RuntimeError("Normalized financial input does not match the fixed cohort")
    filings, decisions = load_offline_mops_archive(args.mops_cache, universe["symbol"])

    eligible_symbols = universe.loc[universe["sector_logic"] != "FINANCIAL", "symbol"].tolist()
    market_symbols = sorted(set(eligible_symbols + ["0050"]))
    market = _load_markets(market_symbols, config, args.market_cache, args.refresh_market, args.workers)
    sessions = tuple(market["0050"]["date"])
    financial, diagnostics = build_financial_timeline(
        normalized,
        filings,
        decisions,
        sessions,
        config["financial_availability_lag_days"],
    )
    signals = build_signal_timeline(financial, universe, market, sessions, config)
    validate_stage_a_frames(financial, signals)
    coverage = coverage_frame(financial)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    financial_path = args.output_dir / "0050_pit_financial_timeline_v0.1.csv.gz"
    mapping_path = args.output_dir / "0050_mops_pit_mapping_v0.1.csv"
    signal_path = args.output_dir / "0050_pit_signal_timeline_v0.1.csv"
    diagnostics_path = args.output_dir / "0050_mops_mapping_diagnostics_v0.1.csv"
    coverage_path = args.output_dir / "0050_mops_pit_coverage_v0.1.csv"
    summary_path = args.output_dir / "0050_stage_a_data_quality_summary_v0.1.json"
    _write_csv(financial, financial_path)
    mapping_columns = [
        "symbol", "period_end", "fiscal_year", "fiscal_quarter", "announcement_date",
        "announcement_timestamp", "available_date", "signal_date", "first_trade_date",
        "availability_method", "timestamp_confidence", "mops_document_kind",
        "mops_source_identifier", "mops_source_provenance", "mops_response_hash",
        "mops_source_hash", "mapping_status", "mapping_reason_code", "source_hash",
    ]
    _write_csv(financial[mapping_columns], mapping_path)
    _write_csv(signals, signal_path)
    _write_csv(diagnostics, diagnostics_path)
    _write_csv(coverage, coverage_path)

    exact = int((financial["availability_method"] == MOPS_EXACT).sum())
    proxy = int((financial["availability_method"] == AVAILABLE_DATE_PROXY).sum())
    conflicts = int((financial["availability_method"] == MOPS_CONFLICT).sum())
    duplicate_observations = int((diagnostics["duplicate_candidate_count"] > 0).sum())
    duplicate_candidates = int(diagnostics["duplicate_candidate_count"].sum())
    corrected = int(diagnostics["corrected_filing_case"].sum())
    config_payload = json.loads(args.config.read_text(encoding="utf-8"))
    frozen_rules_hash = canonical_hash(
        {"quality_rules": config_payload["quality_rules"], "valuation_rules": config_payload["valuation_rules"]}
    )
    market_hashes = {
        path.name: sha256_path(path)
        for path in sorted(args.market_cache.glob("*.json"))
    }
    summary = {
        "stage": "Fundamental Model v0.1 — Stage A: MOPS PIT Integration",
        "status": "PASS" if conflicts == 0 else "FAIL",
        "starting_head": STARTING_HEAD,
        "generation_head": current_head,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mops_network_requests": 0,
        "checkpoint_verification": "PASS",
        "checkpoint_archive_sha256": checkpoint["cache"]["portable_archive_sha256"],
        "restored_cache_files": restored_files,
        "financial_observations": len(financial),
        "mops_exact": exact,
        "proxy": proxy,
        "unmatched": int((diagnostics["mapping_status"] == "UNMATCHED_PROXY").sum()),
        "duplicate_observations": duplicate_observations,
        "duplicate_candidates": duplicate_candidates,
        "conflict_observations": conflicts,
        "corrected_filing_cases": corrected,
        "fixed_cohort": len(universe),
        "eligible_non_financial": len(eligible_symbols),
        "excluded_financial": int((universe["sector_logic"] == "FINANCIAL").sum()),
        "pit_signal_observations": len(signals),
        "predictive_returns_computed": False,
        "frozen_rules_modified": False,
        "frozen_rules_hash": frozen_rules_hash,
        "config_sha256": sha256_path(args.config),
        "normalized_input_sha256": sha256_path(args.normalized),
        "universe_sha256": sha256_path(args.universe),
        "market_snapshot_hash": canonical_hash(market_hashes),
        "artifact_hashes": {},
    }
    summary["artifact_hashes"] = {
        path.name: sha256_path(path)
        for path in (financial_path, mapping_path, signal_path, diagnostics_path, coverage_path)
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _update_manifest(args.output_dir, summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
