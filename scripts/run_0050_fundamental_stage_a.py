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
from experiments.fundamental_quality_valuation.session_contract import (  # noqa: E402
    EXPECTED_FROZEN_SESSION_SHA256,
    first_trade_date_is_valid,
    load_frozen_sessions,
)
from experiments.fundamental_quality_valuation.test_reporting import (  # noqa: E402
    targeted_test_reporting,
)
from scripts.checkpoint_0050_mops_cache_v0_1 import (  # noqa: E402
    restore_checkpoint,
    verify_checkpoint,
)


STARTING_HEAD = "e369d88f6c5ddb116ec3990e99ea876c4d3039b6"
HARDENING_STARTING_HEAD = "f2060e6243ec59bb859e61c2f96e48f84b01dd95"
EXPECTED_FIXED_COHORT_COUNT = 50
EXPECTED_FIXED_COHORT_SHA256 = "aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46"
EXPECTED_FROZEN_RULES_HASH = "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f"
EXPECTED_MOPS_CHECKPOINT_HASH = "c904a167202e2cf7d067f9eae392085e771c209235ded41742b46c428c895fa3"
EXPECTED_SELECTED_FILING_HASH = "549cac3184edcc6472cd2133454914a211567d2500dcd3800d89d444e9accf3a"
REVIEWED_HEAD = "dc94919a7bffba7912e3a4768582e162720450c2"
EXPECTED_STAGE_A_BASELINE = {
    "financial_observations": 2067,
    "mops_exact": 2053,
    "proxy": 14,
    "unmatched": 14,
    "conflict_observations": 0,
    "fixed_cohort": 50,
    "eligible_non_financial": 38,
    "excluded_financial": 12,
    "pit_signal_observations": 1563,
}
DEFAULT_CHECKPOINT = ROOT / "artifacts/0050_fundamental_v0_1/checkpoints/mops_20260904"
DEFAULT_CACHE = ROOT / "outputs/raw_fundamental_predictive_v0_1/mops"
DEFAULT_MARKET_CACHE = ROOT / "outputs/fundamental_stage_a_market"
DEFAULT_OUTPUT = ROOT / "artifacts/0050_fundamental_v0_1"
DEFAULT_NORMALIZED = DEFAULT_OUTPUT / "0050_normalized_financials_pit_v0.1.csv"
DEFAULT_UNIVERSE = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
DEFAULT_CONFIG = ROOT / "config/fundamental_quality_valuation_v0_1.json"
DEFAULT_SESSION_CALENDAR = (
    ROOT / "data/research/0050_fundamental_v0_1/frozen_twse_sessions_v0.1.csv"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Stage A MOPS-aware PIT artifacts without MOPS network I/O")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--mops-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--market-cache", type=Path, default=DEFAULT_MARKET_CACHE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normalized", type=Path, default=DEFAULT_NORMALIZED)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--session-calendar", type=Path, default=DEFAULT_SESSION_CALENDAR)
    parser.add_argument("--refresh-market", action="store_true")
    parser.add_argument(
        "--hardening-only",
        action="store_true",
        help="Refresh only Stage A diagnostics, summary, and manifest from frozen local inputs",
    )
    parser.add_argument("--workers", type=int, default=4)
    return parser


def _load_universe(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    required = {"symbol", "company", "sector_logic", "peer_group", "financial_subtype"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Invalid fixed cohort columns: missing={sorted(missing)}")
    if len(frame) != EXPECTED_FIXED_COHORT_COUNT:
        raise ValueError(
            f"Fixed cohort must contain exactly {EXPECTED_FIXED_COHORT_COUNT} rows; got {len(frame)}"
        )
    if frame["symbol"].duplicated().any() or frame["symbol"].nunique() != EXPECTED_FIXED_COHORT_COUNT:
        raise ValueError("Fixed cohort contains duplicate symbols")
    actual_hash = sha256_path(path)
    if actual_hash != EXPECTED_FIXED_COHORT_SHA256:
        raise ValueError(
            "Frozen universe hash mismatch: "
            f"expected {EXPECTED_FIXED_COHORT_SHA256}, got {actual_hash}"
        )
    return frame.sort_values("symbol").reset_index(drop=True)


def _validate_normalized_symbol_set(normalized: pd.DataFrame, universe: pd.DataFrame) -> None:
    if "symbol" not in normalized:
        raise ValueError("Normalized financial input is missing symbol")
    normalized_symbols = set(normalized["symbol"].astype(str).str.strip())
    universe_symbols = set(universe["symbol"].astype(str).str.strip())
    if normalized_symbols != universe_symbols:
        missing = sorted(universe_symbols - normalized_symbols)
        extra = sorted(normalized_symbols - universe_symbols)
        raise RuntimeError(
            f"Normalized financial symbol set mismatch: missing={missing}, extra={extra}"
        )


def _selected_filing_hash(filings: dict[tuple[str, int, int], Any]) -> str:
    payload = [
        {
            "key": list(key),
            "source_hash": filing.source_hash,
            "source_identifier": filing.source_identifier,
            "announcement_timestamp": filing.announcement_timestamp,
            "document_kind": filing.document_kind,
        }
        for key, filing in sorted(filings.items())
    ]
    return canonical_hash(payload)


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


def _invalid_first_trade_count(frame: pd.DataFrame, sessions: tuple[object, ...]) -> int:
    invalid = 0
    for row in frame.to_dict(orient="records"):
        signal = pd.to_datetime(row.get("signal_date"), errors="coerce")
        entry = pd.to_datetime(row.get("first_trade_date"), errors="coerce")
        if pd.isna(signal) or pd.isna(entry):
            invalid += 1
            continue
        if not first_trade_date_is_valid(signal.date(), entry.date(), sessions):
            invalid += 1
    return invalid


def _update_manifest(
    output_dir: Path,
    stage_summary: dict[str, Any],
    *,
    section: str = "stage_a",
) -> None:
    manifest_path = output_dir / "artifact_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if section == "stage_a" and "stage_a" in payload:
        history = payload.setdefault("audit_history", {})
        history.setdefault(
            "before_final_review_correction",
            {
                "reviewed_head": REVIEWED_HEAD,
                "stage_a": payload.get("stage_a"),
                "stage_a_hardening": payload.get("stage_a_hardening"),
                "stage_b": payload.get("stage_b"),
            },
        )
    payload[section] = stage_summary
    payload["artifacts"] = [
        {"path": path.name, "sha256": sha256_path(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != manifest_path.name
    ]
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _assert_frozen_stage_a_baseline(actual: dict[str, int]) -> None:
    changed = {
        name: {"expected": expected, "actual": actual.get(name)}
        for name, expected in EXPECTED_STAGE_A_BASELINE.items()
        if actual.get(name) != expected
    }
    if changed:
        raise RuntimeError(f"Frozen Stage A baseline changed: {changed}")


def _hardening_diagnostics(
    existing: pd.DataFrame,
    filings: dict[tuple[str, int, int], Any],
    decisions: dict[tuple[str, int, int], Any],
) -> pd.DataFrame:
    frame = existing.copy()
    frame["symbol"] = frame["symbol"].astype(str)
    audit_columns = [
        "selection_status",
        "selection_reason_code",
        "candidate_count",
        "conflict_candidate_count",
        "corrected_filing_case",
        "selected_document_kind",
        "selected_source_identifier",
        "selected_announcement_timestamp",
    ]
    before = frame[audit_columns].fillna("").astype(str)
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        key = (str(row["symbol"]), int(row["fiscal_year"]), int(row["fiscal_quarter"]))
        decision = decisions.get(key)
        filing = filings.get(key)
        expected = {
            "selection_status": decision.status if decision else "NO_MOPS_CANDIDATE",
            "selection_reason_code": (
                decision.reason_code if decision else "MOPS_GENUINELY_UNMATCHED"
            ),
            "candidate_count": decision.candidate_count if decision else 0,
            "conflict_candidate_count": decision.conflict_candidate_count if decision else 0,
            "corrected_filing_case": decision.corrected_filing_case if decision else False,
            "selected_document_kind": filing.document_kind if filing else None,
            "selected_source_identifier": filing.source_identifier if filing else None,
            "selected_announcement_timestamp": filing.announcement_timestamp if filing else None,
        }
        updated = dict(row)
        updated.update(expected)
        updated.update(
            {
                "exact_duplicate_count": decision.exact_duplicate_count if decision else 0,
                "multiple_vintage_count": decision.multiple_vintage_count if decision else 0,
                "multiple_document_kind_count": (
                    decision.multiple_document_kind_count if decision else 0
                ),
                "correction_candidate_count": (
                    decision.correction_candidate_count if decision else 0
                ),
                "duplicate_candidate_count": (
                    decision.duplicate_candidate_count if decision else 0
                ),
                "duplicate_candidate_count_semantic": (
                    "DEPRECATED_LEGACY_CANDIDATES_BEYOND_FIRST"
                ),
            }
        )
        rows.append(updated)
    result = pd.DataFrame(rows)
    after = result[audit_columns].fillna("").astype(str)
    if not before.equals(after):
        raise RuntimeError("Diagnostic refactor would change the selected filing contract")
    prefix = list(existing.columns)
    for name in (
        "exact_duplicate_count",
        "multiple_vintage_count",
        "multiple_document_kind_count",
        "correction_candidate_count",
        "duplicate_candidate_count_semantic",
    ):
        if name not in prefix:
            prefix.append(name)
    return result[prefix]


def _run_hardening_only(
    *,
    args: argparse.Namespace,
    current_head: str,
    checkpoint: dict[str, Any],
    restored_files: int,
    config: dict[str, Any],
    universe: pd.DataFrame,
    filings: dict[tuple[str, int, int], Any],
    decisions: dict[tuple[str, int, int], Any],
    selected_filing_hash: str,
) -> int:
    financial_path = args.output_dir / "0050_pit_financial_timeline_v0.1.csv.gz"
    mapping_path = args.output_dir / "0050_mops_pit_mapping_v0.1.csv"
    signal_path = args.output_dir / "0050_pit_signal_timeline_v0.1.csv"
    diagnostics_path = args.output_dir / "0050_mops_mapping_diagnostics_v0.1.csv"
    coverage_path = args.output_dir / "0050_mops_pit_coverage_v0.1.csv"
    summary_path = args.output_dir / "0050_stage_a_data_quality_summary_v0.1.json"
    financial = pd.read_csv(financial_path, dtype={"symbol": str}, low_memory=False)
    signals = pd.read_csv(signal_path, dtype={"symbol": str}, low_memory=False)
    existing_diagnostics = pd.read_csv(
        diagnostics_path,
        dtype={"symbol": str},
        encoding="utf-8-sig",
        low_memory=False,
    )
    diagnostics = _hardening_diagnostics(existing_diagnostics, filings, decisions)

    eligible_non_financial = int((universe["sector_logic"] != "FINANCIAL").sum())
    excluded_financial = int((universe["sector_logic"] == "FINANCIAL").sum())
    baseline = {
        "financial_observations": len(financial),
        "mops_exact": int((financial["availability_method"] == MOPS_EXACT).sum()),
        "proxy": int((financial["availability_method"] == AVAILABLE_DATE_PROXY).sum()),
        "unmatched": int((diagnostics["mapping_status"] == "UNMATCHED_PROXY").sum()),
        "conflict_observations": int(
            (financial["availability_method"] == MOPS_CONFLICT).sum()
        ),
        "fixed_cohort": len(universe),
        "eligible_non_financial": eligible_non_financial,
        "excluded_financial": excluded_financial,
        "pit_signal_observations": len(signals),
    }
    _assert_frozen_stage_a_baseline(baseline)
    exact_duplicate_rows = int(diagnostics["exact_duplicate_count"].sum())
    multiple_vintage_cases = int((diagnostics["multiple_vintage_count"] > 0).sum())
    multiple_document_kind_cases = int(
        (diagnostics["multiple_document_kind_count"] > 0).sum()
    )
    correction_candidate_cases = int(
        (diagnostics["correction_candidate_count"] > 0).sum()
    )
    conflict_cases = int((diagnostics["conflict_candidate_count"] > 0).sum())
    diagnostic_baseline = {
        "exact_duplicate_rows": 0,
        "multiple_vintage_cases": 341,
        "multiple_document_kind_cases": 341,
        "correction_candidate_cases": 0,
        "conflict_cases": 0,
    }
    actual_diagnostics = {
        "exact_duplicate_rows": exact_duplicate_rows,
        "multiple_vintage_cases": multiple_vintage_cases,
        "multiple_document_kind_cases": multiple_document_kind_cases,
        "correction_candidate_cases": correction_candidate_cases,
        "conflict_cases": conflict_cases,
    }
    if actual_diagnostics != diagnostic_baseline:
        raise RuntimeError(
            f"Stage A diagnostic baseline changed: expected {diagnostic_baseline}, "
            f"got {actual_diagnostics}"
        )
    frozen_rules_hash = canonical_hash(
        {"quality_rules": config["quality_rules"], "valuation_rules": config["valuation_rules"]}
    )
    if frozen_rules_hash != EXPECTED_FROZEN_RULES_HASH:
        raise RuntimeError("Frozen model rules hash changed")

    _write_csv(diagnostics, diagnostics_path)
    summary: dict[str, Any] = {
        "stage": "Fundamental Model v0.1 — Stage A Hardening Pass",
        "status": "PASS",
        "stage_a_starting_head": STARTING_HEAD,
        "stage_a_head": HARDENING_STARTING_HEAD,
        "starting_head": HARDENING_STARTING_HEAD,
        "generation_head": current_head,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mops_network_requests": 0,
        "checkpoint_verification": "PASS",
        "checkpoint_archive_sha256": checkpoint["cache"]["portable_archive_sha256"],
        "restored_cache_files": restored_files,
        **baseline,
        **actual_diagnostics,
        "duplicate_candidate_count": int(diagnostics["duplicate_candidate_count"].sum()),
        "duplicate_candidate_count_semantic": (
            "DEPRECATED_LEGACY_CANDIDATES_BEYOND_FIRST_NOT_BAD_DATA"
        ),
        "predictive_returns_computed": False,
        "frozen_rules_modified": False,
        "frozen_rules_hash": frozen_rules_hash,
        "config_sha256": sha256_path(args.config),
        "normalized_input_sha256": sha256_path(args.normalized),
        "universe_sha256": sha256_path(args.universe),
        "fixed_cohort_hash_verified": True,
        "selected_filing_hash": selected_filing_hash,
        "filing_selection_results_unchanged": True,
        "artifact_change_reason": (
            "Mapping diagnostic fields were split by semantic category; filing selection, "
            "financial timeline, signal timeline, coverage, and model rules are unchanged."
        ),
        "artifact_hashes": {
            path.name: sha256_path(path)
            for path in (financial_path, mapping_path, signal_path, diagnostics_path, coverage_path)
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _update_manifest(args.output_dir, summary, section="stage_a_hardening")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("--workers must be between 1 and 8")
    current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not subprocess.call(
        ["git", "merge-base", "--is-ancestor", STARTING_HEAD, current_head], cwd=ROOT
    ) == 0:
        raise RuntimeError(f"Current head is not descended from frozen starting head {STARTING_HEAD}")
    if not subprocess.call(
        ["git", "merge-base", "--is-ancestor", HARDENING_STARTING_HEAD, current_head], cwd=ROOT
    ) == 0:
        raise RuntimeError(
            f"Current head is not descended from hardening starting head {HARDENING_STARTING_HEAD}"
        )

    checkpoint = verify_checkpoint(args.checkpoint_dir)
    restore_checkpoint(args.checkpoint_dir, args.mops_cache)
    restored_files = verify_restored_cache(
        args.mops_cache,
        args.checkpoint_dir / "mops_cache_inventory.csv",
    )
    checkpoint_hash = checkpoint["cache"]["portable_archive_sha256"]
    if checkpoint_hash != EXPECTED_MOPS_CHECKPOINT_HASH:
        raise RuntimeError(
            f"Frozen MOPS checkpoint hash mismatch: expected {EXPECTED_MOPS_CHECKPOINT_HASH}, "
            f"got {checkpoint_hash}"
        )
    if checkpoint["resume"]["next_network_requests_required"] != 0:
        raise RuntimeError("Frozen checkpoint requires additional MOPS network requests")
    print(f"[checkpoint] verified and restored {restored_files} files; MOPS network requests=0", flush=True)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    universe = _load_universe(args.universe)
    normalized = pd.read_csv(args.normalized, dtype={"symbol": str}, encoding="utf-8-sig", low_memory=False)
    _validate_normalized_symbol_set(normalized, universe)
    filings, decisions = load_offline_mops_archive(args.mops_cache, universe["symbol"])
    selected_filing_hash = _selected_filing_hash(filings)
    if selected_filing_hash != EXPECTED_SELECTED_FILING_HASH:
        raise RuntimeError(
            f"MOPS filing selection changed: expected {EXPECTED_SELECTED_FILING_HASH}, "
            f"got {selected_filing_hash}"
        )

    if args.hardening_only:
        return _run_hardening_only(
            args=args,
            current_head=current_head,
            checkpoint=checkpoint,
            restored_files=restored_files,
            config=config,
            universe=universe,
            filings=filings,
            decisions=decisions,
            selected_filing_hash=selected_filing_hash,
        )

    eligible_symbols = universe.loc[universe["sector_logic"] != "FINANCIAL", "symbol"].tolist()
    market_symbols = sorted(set(eligible_symbols + ["0050"]))
    market = _load_markets(market_symbols, config, args.market_cache, args.refresh_market, args.workers)
    sessions = load_frozen_sessions(args.session_calendar)
    previous_signals = pd.read_csv(
        args.output_dir / "0050_pit_signal_timeline_v0.1.csv",
        dtype={"symbol": str},
        encoding="utf-8-sig",
    )
    invalid_first_trade_before = _invalid_first_trade_count(previous_signals, sessions)
    financial, diagnostics = build_financial_timeline(
        normalized,
        filings,
        decisions,
        sessions,
        config["financial_availability_lag_days"],
    )
    signals = build_signal_timeline(financial, universe, market, sessions, config)
    validate_stage_a_frames(financial, signals, sessions)
    invalid_first_trade_after = _invalid_first_trade_count(signals, sessions)
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
    exact_duplicate_rows = int(diagnostics["exact_duplicate_count"].sum())
    multiple_vintage_cases = int((diagnostics["multiple_vintage_count"] > 0).sum())
    multiple_document_kind_cases = int(
        (diagnostics["multiple_document_kind_count"] > 0).sum()
    )
    correction_candidate_cases = int(
        (diagnostics["correction_candidate_count"] > 0).sum()
    )
    legacy_duplicate_candidates = int(diagnostics["duplicate_candidate_count"].sum())
    config_payload = json.loads(args.config.read_text(encoding="utf-8"))
    frozen_rules_hash = canonical_hash(
        {"quality_rules": config_payload["quality_rules"], "valuation_rules": config_payload["valuation_rules"]}
    )
    if frozen_rules_hash != EXPECTED_FROZEN_RULES_HASH:
        raise RuntimeError(
            f"Frozen model rules hash changed: expected {EXPECTED_FROZEN_RULES_HASH}, "
            f"got {frozen_rules_hash}"
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
        "reviewed_head": REVIEWED_HEAD,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mops_network_requests": 0,
        "session_contract": "FROZEN_0050_BENCHMARK_TRADING_SESSIONS",
        "session_calendar_sha256": sha256_path(args.session_calendar),
        "session_calendar_expected_sha256": EXPECTED_FROZEN_SESSION_SHA256,
        "session_calendar_rows": len(sessions),
        "invalid_first_trade_date_before": invalid_first_trade_before,
        "invalid_first_trade_date_after": invalid_first_trade_after,
        "checkpoint_verification": "PASS",
        "checkpoint_archive_sha256": checkpoint["cache"]["portable_archive_sha256"],
        "restored_cache_files": restored_files,
        "financial_observations": len(financial),
        "mops_exact": exact,
        "proxy": proxy,
        "unmatched": int((diagnostics["mapping_status"] == "UNMATCHED_PROXY").sum()),
        "exact_duplicate_rows": exact_duplicate_rows,
        "multiple_vintage_cases": multiple_vintage_cases,
        "multiple_document_kind_cases": multiple_document_kind_cases,
        "correction_candidate_cases": correction_candidate_cases,
        "duplicate_candidate_count": legacy_duplicate_candidates,
        "duplicate_candidate_count_semantic": "DEPRECATED_LEGACY_CANDIDATES_BEYOND_FIRST_NOT_BAD_DATA",
        "conflict_observations": conflicts,
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
        "fixed_cohort_hash_verified": True,
        "selected_filing_hash": selected_filing_hash,
        "filing_selection_results_unchanged": True,
        "market_snapshot_hash": canonical_hash(market_hashes),
        "targeted_tests": targeted_test_reporting(ROOT),
        "artifact_change_reason": (
            "Final Review Correction Pass: first_trade_date is derived from the frozen "
            "Stage B benchmark session calendar; model classifications and thresholds are unchanged."
        ),
        "artifact_hashes": {},
    }
    _assert_frozen_stage_a_baseline(
        {
            name: int(summary[name])
            for name in EXPECTED_STAGE_A_BASELINE
        }
    )
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
