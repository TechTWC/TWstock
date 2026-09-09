from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.fundamental_quality_valuation.data import fetch_yahoo_market  # noqa: E402
from experiments.fundamental_quality_valuation.stage_a import sha256_path  # noqa: E402
from experiments.fundamental_quality_valuation.stage_b import (  # noqa: E402
    CANONICAL_STATES,
    EXPECTED_SIGNAL_SHA256,
    PRIMARY_HORIZONS,
    QUALITY_BUCKETS,
    STATE_DETAILS,
    STAGE_B_STARTING_HEAD,
    TIMING_LABELS,
    VALUATION_BUCKETS,
    assert_finite_artifact,
    build_evidence,
    build_predictive_events,
    overlap_diagnostics,
    summarize_combinations,
    summarize_dimension,
    summarize_outliers,
    summarize_regimes,
    summarize_timing_labels,
    validate_frozen_inputs,
)
from experiments.fundamental_quality_valuation.stage_b_report import write_stage_b_pdf  # noqa: E402


DEFAULT_OUTPUT = ROOT / "artifacts/0050_fundamental_v0_1"
DEFAULT_UNIVERSE = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
DEFAULT_CONFIG = ROOT / "config/fundamental_quality_valuation_v0_1.json"
DEFAULT_SIGNAL = DEFAULT_OUTPUT / "0050_pit_signal_timeline_v0.1.csv"
DEFAULT_MANIFEST = DEFAULT_OUTPUT / "artifact_manifest.json"
DEFAULT_LEGACY_EVENTS = DEFAULT_OUTPUT / "0050_backtest_events_v0.1.csv"
DEFAULT_MARKET_CACHE = ROOT / "outputs/fundamental_stage_b_market"

STAGE_B_FILES = (
    "0050_predictive_events_v0.1.csv",
    "0050_state_predictive_summary_v0.1.csv",
    "0050_state_detail_predictive_summary_v0.1.csv",
    "0050_quality_predictive_summary_v0.1.csv",
    "0050_valuation_predictive_summary_v0.1.csv",
    "0050_predictive_combinations_v0.1.csv",
    "0050_too_late_return_diagnostic_v0.1.csv",
    "0050_regime_robustness_v0.1.csv",
    "0050_outlier_sensitivity_v0.1.csv",
    "0050_overlap_diagnostics_v0.1.csv",
    "0050_predictive_price_sources_v0.1.csv",
    "0050_predictive_evidence_v0.1.json",
    "0050_fundamental_quality_valuation_predictive_validation_v0.1.pdf",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Fundamental Model v0.1 Stage B from Frozen Stage A PIT signals"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNAL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--legacy-events", type=Path, default=DEFAULT_LEGACY_EVENTS)
    parser.add_argument("--market-cache", type=Path, default=DEFAULT_MARKET_CACHE)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    return parser


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.replace([np.inf, -np.inf], np.nan).to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
    )


def _load_market(symbol: str, start: str, end: str, cache: Path, offline: bool) -> pd.DataFrame:
    raw = cache / f"{symbol}_YahooChart.json"
    if offline and not raw.exists():
        raise RuntimeError(f"Offline adjusted-close cache missing: {raw}")
    return fetch_yahoo_market(symbol, start, end, cache)


def _load_markets(
    symbols: list[str],
    *,
    start: str,
    end: str,
    cache: Path,
    workers: int,
    offline: bool,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    cache.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_load_market, symbol, start, end, cache, offline): symbol
            for symbol in symbols
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            try:
                result[symbol] = future.result()
                print(f"[adjusted close {completed:02d}/{len(symbols)}] {symbol}: {len(result[symbol])} rows", flush=True)
            except Exception as exc:
                failures.append(f"{symbol}: {exc}")
    if failures:
        raise RuntimeError("Adjusted-close acquisition failed closed: " + " | ".join(sorted(failures)))
    audit_rows = []
    for symbol in symbols:
        raw = cache / f"{symbol}_YahooChart.json"
        frame = result[symbol].copy()
        dates = pd.to_datetime(frame["date"], errors="coerce")
        audit_rows.append(
            {
                "symbol": symbol,
                "source": "Yahoo Finance chart API via existing return-source adapter",
                "price_policy": "ADJUSTED_CLOSE",
                "raw_policy": "Raw close retained in local ignored cache; not used for Stage B returns",
                "trading_date_policy": "EXACT_COMMON_TWSE_DATE",
                "rows_received": int(len(frame)),
                "first_date": dates.min().date().isoformat() if dates.notna().any() else None,
                "last_date_before_as_of_clip": dates.max().date().isoformat() if dates.notna().any() else None,
                "cache_sha256": sha256_path(raw),
                "mops_network_request": False,
            }
        )
    return result, pd.DataFrame(audit_rows)


def _validate_csvs(paths: list[Path]) -> None:
    for path in paths:
        frame = pd.read_csv(path, low_memory=False)
        numeric = frame.select_dtypes(include=[np.number])
        if not numeric.empty and np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
            raise RuntimeError(f"CSV contains an infinite numeric value: {path.name}")


def _update_manifest(
    manifest: dict[str, Any],
    output_dir: Path,
    evidence: dict[str, Any],
) -> None:
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    stage_b_hashes = {
        name: sha256_path(output_dir / name)
        for name in STAGE_B_FILES
        if (output_dir / name).exists()
    }
    manifest["stage_b"] = {
        "stage": "Fundamental Model v0.1 — Stage B: Predictive Validation",
        "status": "PASS",
        "starting_head": STAGE_B_STARTING_HEAD,
        "generation_head": commit_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mops_network_requests": 0,
        "frozen_universe_verified": True,
        "frozen_stage_a_signal_verified": True,
        "frozen_model_rules_verified": True,
        "stage_a_manifest_identity_verified": True,
        "frozen_identity": evidence["frozen_identity"],
        "eligible_observations_by_horizon": evidence["eligible_observations_by_horizon"],
        "predictive_evidence_grade": evidence["predictive_evidence_grade"],
        "evidence_label": evidence["evidence_label"],
        "support_gate": evidence["rubric"]["support_gate"],
        "survivorship_bias": "CURRENT_CONSTITUENTS_ONLY",
        "financial_issuers_excluded": 12,
        "frozen_rules_modified": False,
        "artifact_hashes": stage_b_hashes,
    }
    manifest["artifacts"] = [
        {"path": path.name, "sha256": sha256_path(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "artifact_manifest.json"
    ]
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _validate_manifest(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["artifacts"]:
        path = output_dir / item["path"]
        if not path.exists() or sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"Manifest hash mismatch: {item['path']}")
    for name, expected in manifest["stage_b"]["artifact_hashes"].items():
        if sha256_path(output_dir / name) != expected:
            raise RuntimeError(f"Stage B manifest hash mismatch: {name}")


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("--workers must be between 1 and 8")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    universe, signals, config, manifest, identity = validate_frozen_inputs(
        args.universe, args.signals, args.config, args.manifest
    )
    if identity.signal_sha256 != EXPECTED_SIGNAL_SHA256:
        raise RuntimeError("Frozen signal identity changed after validation")
    print("[frozen] universe, Stage A signal, rules, and manifest identity PASS", flush=True)
    eligible_symbols = sorted(
        universe.loc[universe["sector_logic"] != "FINANCIAL", "symbol"].astype(str).tolist()
    )
    all_market, price_sources = _load_markets(
        ["0050", *eligible_symbols],
        start=config["history_start"],
        end=config["as_of_date"],
        cache=args.market_cache,
        workers=args.workers,
        offline=args.offline,
    )
    benchmark = all_market.pop("0050")
    legacy_events = (
        pd.read_csv(args.legacy_events, dtype={"symbol": str}, low_memory=False)
        if args.legacy_events.exists()
        else pd.DataFrame()
    )
    events = build_predictive_events(
        signals,
        universe,
        all_market,
        benchmark,
        as_of=date.fromisoformat(config["as_of_date"]),
        legacy_events=legacy_events,
    )
    print(f"[events] {len(events)} Frozen Stage A observations; financial issuers excluded", flush=True)
    state = summarize_dimension(events, "fundamental_state", CANONICAL_STATES, "FUNDAMENTAL_STATE")
    state_detail = summarize_dimension(events, "state_detail", STATE_DETAILS, "STATE_DETAIL")
    quality = summarize_dimension(events, "quality", QUALITY_BUCKETS, "QUALITY")
    valuation_all = summarize_dimension(events, "valuation_bucket", VALUATION_BUCKETS, "VALUATION")
    valuation_all.insert(0, "sector_scope", "ALL_NON_FINANCIAL")
    valuation_parts = [valuation_all]
    for sector in ("GENERAL", "CYCLICAL"):
        selected = events[events["sector_logic"] == sector]
        part = summarize_dimension(selected, "valuation_bucket", VALUATION_BUCKETS, "VALUATION")
        part.insert(0, "sector_scope", sector)
        valuation_parts.append(part)
    valuation = pd.concat(valuation_parts, ignore_index=True)
    combinations = summarize_combinations(events)
    timing = summarize_timing_labels(events)
    regimes = summarize_regimes(events)
    outliers = summarize_outliers(events)
    overlap = overlap_diagnostics(events)
    evidence = build_evidence(
        events,
        state,
        state_detail,
        quality,
        valuation_all,
        combinations,
        timing,
        regimes,
        outliers,
        overlap,
        identity,
    )
    assert_finite_artifact(evidence)

    outputs = {
        "0050_predictive_events_v0.1.csv": events,
        "0050_state_predictive_summary_v0.1.csv": state,
        "0050_state_detail_predictive_summary_v0.1.csv": state_detail,
        "0050_quality_predictive_summary_v0.1.csv": quality,
        "0050_valuation_predictive_summary_v0.1.csv": valuation,
        "0050_predictive_combinations_v0.1.csv": combinations,
        "0050_too_late_return_diagnostic_v0.1.csv": timing,
        "0050_regime_robustness_v0.1.csv": regimes,
        "0050_outlier_sensitivity_v0.1.csv": outliers,
        "0050_overlap_diagnostics_v0.1.csv": overlap,
        "0050_predictive_price_sources_v0.1.csv": price_sources,
    }
    for name, frame in outputs.items():
        _write_csv(frame, args.output_dir / name)
    evidence_path = args.output_dir / "0050_predictive_evidence_v0.1.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if not args.skip_pdf:
        write_stage_b_pdf(
            args.output_dir / "0050_fundamental_quality_valuation_predictive_validation_v0.1.pdf",
            evidence=evidence,
            state=state,
            state_detail=state_detail,
            quality=quality,
            valuation=valuation_all,
            combinations=combinations,
            timing=timing,
            regimes=regimes,
            outliers=outliers,
            overlap=overlap,
            state_accuracy=pd.read_csv(args.output_dir / "0050_state_accuracy_metrics_v0.1.csv"),
            state_confusion=pd.read_csv(args.output_dir / "0050_state_confusion_matrix_v0.1.csv"),
            mops_coverage=pd.read_csv(args.output_dir / "0050_mops_pit_coverage_v0.1.csv"),
        )
        pdf = args.output_dir / "0050_fundamental_quality_valuation_predictive_validation_v0.1.pdf"
        if not pdf.read_bytes().startswith(b"%PDF"):
            raise RuntimeError("PDF generation failed")
        print("[pdf] Stage B complete", flush=True)
    _validate_csvs([args.output_dir / name for name in outputs])
    _update_manifest(manifest, args.output_dir, evidence)
    _validate_manifest(args.output_dir)
    print(
        "[done] "
        + json.dumps(
            {
                "eligible": evidence["eligible_observations_by_horizon"],
                "grade": evidence["predictive_evidence_grade"],
                "label": evidence["evidence_label"],
                "mops_network_requests": 0,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
