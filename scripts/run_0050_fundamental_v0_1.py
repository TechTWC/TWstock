from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.fundamental_quality_valuation.backtest import (  # noqa: E402
    build_backtest_events,
    diagnose_too_late,
    summarize_baselines,
    summarize_quality_persistence,
    summarize_return_diagnostics,
    summarize_robustness,
    summarize_state_validation,
)
from experiments.fundamental_quality_valuation.data import (  # noqa: E402
    ResearchDataError,
    fetch_finmind_dataset,
    fetch_stock_info,
    fetch_yahoo_market,
    load_security_data,
    load_yahoo_fallback_security_data,
    load_universe,
    normalize_market,
)
from experiments.fundamental_quality_valuation.engine import classify_security  # noqa: E402
from experiments.fundamental_quality_valuation.models import SectorLogic, SecurityData  # noqa: E402
from experiments.fundamental_quality_valuation.validation import (  # noqa: E402
    confusion_matrix,
    state_accuracy_metrics,
)
from experiments.fundamental_quality_valuation.report import (  # noqa: E402
    write_current_csv,
    write_json_bundle,
    write_pdf_report,
    write_quarterly_csv,
)


FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run independent 0050 Fundamental Quality & Valuation v0.1 research")
    parser.add_argument("--config", type=Path, default=ROOT / "config/fundamental_quality_valuation_v0_1.json")
    parser.add_argument("--universe", type=Path, default=ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "outputs/raw_fundamental_v0_1")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/0050_fundamental_v0_1")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--skip-font-download", action="store_true")
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font(cache_dir: Path, skip_download: bool) -> Path | None:
    path = cache_dir / "NotoSansTC-wght.ttf"
    if path.exists():
        return path
    if skip_download:
        return None
    print("[font] downloading Noto Sans CJK TC for PDF rendering", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(FONT_URL, headers={"User-Agent": "TWstock-research/0.1"})
    with urlopen(request, timeout=180) as response:
        data = response.read()
    if len(data) < 1_000_000:
        raise RuntimeError("Downloaded font payload is unexpectedly small")
    path.write_bytes(data)
    return path


def _load_one(
    row: dict[str, str],
    stock_info: dict[str, dict[str, str]],
    config: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
) -> SecurityData:
    symbol = row["symbol"]
    info = stock_info.get(symbol, {})
    common = {
        "symbol": symbol,
        "company": info.get("company") or row["company"],
        "industry": info.get("industry") or "UNKNOWN",
        "sector_logic": SectorLogic(row["sector_logic"]),
        "peer_group": row["peer_group"],
        "financial_subtype": row["financial_subtype"] or None,
        "start_date": config["history_start"],
        "end_date": config["as_of_date"],
        "cache_dir": cache_dir,
        "availability_lags": config["financial_availability_lag_days"],
    }
    if not refresh and (cache_dir / f"{symbol}_YahooFundamentals.json").exists():
        security = load_yahoo_fallback_security_data(**common)
    else:
        try:
            security = load_security_data(**common, refresh=refresh)
        except ResearchDataError as exc:
            if "402" not in str(exc) and "upper limit" not in str(exc).lower():
                raise
            security = load_yahoo_fallback_security_data(**common)
    try:
        adjusted = fetch_yahoo_market(symbol, config["history_start"], config["as_of_date"], cache_dir)
        if "adj_close" in adjusted and adjusted["adj_close"].notna().any():
            security.market = security.market.merge(
                adjusted[["date", "adj_close"]], on="date", how="left", suffixes=("", "_yahoo")
            )
            if "adj_close_yahoo" in security.market:
                security.market["adj_close"] = security.market["adj_close"].fillna(security.market["adj_close_yahoo"])
                security.market = security.market.drop(columns=["adj_close_yahoo"])
            security.data_flags = [flag for flag in security.data_flags if flag != "UNADJUSTED_PRICE_RETURN"]
            security.data_flags.extend(["ADJUSTED_RETURN_SECONDARY_SOURCE", "RAW_PRICE_RETAINED"])
    except Exception:
        security.data_flags.append("UNADJUSTED_PRICE_RETURN")
    if "vendor source history is insufficient" in row.get("source_note", "").lower():
        security.data_flags.extend(
            [
                "REVIEWED_HEAD_SOURCE_HISTORY_INSUFFICIENT",
                "SOURCE_HISTORY_PROVENANCE_UNSTABLE",
            ]
        )
    security.data_flags.append("UNIVERSE_SOURCE_RECONSTRUCTED")
    return security


def _load_benchmark(config: dict[str, Any], cache_dir: Path, refresh: bool) -> pd.DataFrame:
    adjusted = fetch_yahoo_market("0050", config["history_start"], config["as_of_date"], cache_dir)
    try:
        prices = fetch_finmind_dataset(
            "TaiwanStockPrice", "0050", config["history_start"], config["as_of_date"], cache_dir, refresh=refresh
        )["data"]
        valuation = fetch_finmind_dataset(
            "TaiwanStockPER", "0050", config["history_start"], config["as_of_date"], cache_dir, refresh=refresh
        )["data"]
        benchmark = normalize_market(prices, valuation)
        return benchmark.merge(adjusted[["date", "adj_close"]], on="date", how="left")
    except ResearchDataError:
        return adjusted


def _peer_context(results: list[Any]) -> pd.DataFrame:
    rows = []
    for result in results:
        rows.append(
            {
                "symbol": result.symbol,
                "company": result.company,
                "industry": result.industry,
                "peer_group": result.peer_group,
                "sector_logic": result.sector_logic,
                "quality": result.quality,
                "fundamental_state": result.fundamental_state,
                "valuation": result.valuation,
                "pe": result.metrics.get("pe"),
                "pb": result.metrics.get("pb"),
                "roe": result.metrics.get("roe"),
                "roic": result.metrics.get("roic"),
                "revenue_yoy": result.metrics.get("revenue_yoy"),
            }
        )
    frame = pd.DataFrame(rows)
    for column in ("pe", "pb", "roe", "roic", "revenue_yoy"):
        frame[f"peer_{column}_percentile"] = (
            pd.to_numeric(frame[column], errors="coerce").groupby(frame["peer_group"]).rank(pct=True)
        )
    frame["peer_context_note"] = "Business-model peer taxonomy; descriptive only and never a composite score"
    return frame


def _data_quality(
    results: list[Any], securities: list[SecurityData], config: dict[str, Any]
) -> pd.DataFrame:
    result_by_symbol = {result.symbol: result for result in results}
    expected_periods = pd.date_range(
        pd.Timestamp(config["history_start"]),
        pd.Timestamp(config["as_of_date"]),
        freq="QE-DEC",
    ).date
    rows: list[dict[str, Any]] = []
    for security in securities:
        result = result_by_symbol[security.symbol]
        q = security.quarterly.copy()
        core_columns = [column for column in ("revenue", "net_income", "eps", "equity") if column in q]
        observed = q[core_columns].notna().any(axis=1) if core_columns else pd.Series(False, index=q.index)
        observed_periods = set(q.loc[observed, "period_end"])
        missing_periods = [period.isoformat() for period in expected_periods if period not in observed_periods]

        def coverage(column: str) -> float:
            if column not in q or len(expected_periods) == 0:
                return 0.0
            return float(pd.to_numeric(q[column], errors="coerce").notna().sum() / len(expected_periods))

        actual = int(q.get("announcement_date", pd.Series(dtype=object)).notna().sum())
        proxy = int((q.get("availability_method", pd.Series(dtype=object)) == "AVAILABLE_DATE_PROXY").sum())
        pit_denominator = actual + proxy
        market = security.market
        valuation_available = (
            market[[column for column in ("PER", "PBR") if column in market]].notna().any(axis=1)
            if not market.empty
            else pd.Series(dtype=bool)
        )
        financial_core = [result.metrics.get(name) for name in ("ttm_eps", "ttm_net_income", "equity", "bvps", "roe")]
        reason_codes = list(result.reason_codes)
        if security.symbol == "8046":
            reason_codes.append("REVIEWED_HEAD_SOURCE_HISTORY_INSUFFICIENT")
        if security.symbol == "7769":
            reason_codes.append("ISSUER_LISTING_HISTORY_SHORT")
        missing_metrics = [
            column
            for column in ("ttm_revenue", "ttm_eps", "roe", "roic", "ttm_fcf", "equity")
            if coverage(column) == 0
        ]
        rows.append(
            {
                "symbol": security.symbol,
                "company": security.company,
                "sector": security.sector_logic.value,
                "peer_group": security.peer_group,
                "financial_subtype": security.financial_subtype,
                "history_quarters": int(observed.sum()),
                "expected_quarters": len(expected_periods),
                "missing_quarters": len(missing_periods),
                "missing_quarter_periods": " | ".join(missing_periods),
                "missing_metrics": " | ".join(missing_metrics),
                "eps_coverage": coverage("ttm_eps"),
                "roe_coverage": coverage("roe"),
                "fcf_coverage": coverage("ttm_fcf"),
                "valuation_coverage": float(valuation_available.mean()) if not valuation_available.empty else 0.0,
                "price_coverage": float(pd.to_numeric(market.get("close"), errors="coerce").notna().mean()) if not market.empty else 0.0,
                "pit_actual_date_coverage": actual / pit_denominator if pit_denominator else 0.0,
                "pit_proxy_coverage": proxy / pit_denominator if pit_denominator else 0.0,
                "financial_completeness": sum(value is not None for value in financial_core) / len(financial_core),
                "current_state_usability": result.fundamental_state != "UNKNOWN" and result.data_quality != "INSUFFICIENT",
                "current_state": result.fundamental_state,
                "state_detail": result.state_detail,
                "data_quality": result.data_quality,
                "reason_codes": " | ".join(dict.fromkeys(reason_codes)),
                "source_history_note": (
                    "Reviewed-head fallback had insufficient source history; correction refresh recovered 42 quarters; this was not short company history"
                    if security.symbol == "8046"
                    else None
                ),
                "flags": " | ".join(result.data_quality_flags),
                "period_end": result.period_end,
                "as_of_date": result.as_of_date,
                "announcement_date": result.pit_metadata.announcement_date if result.pit_metadata else None,
                "available_date": result.pit_metadata.available_date if result.pit_metadata else None,
                "retrieval_date": result.pit_metadata.retrieval_date if result.pit_metadata else None,
                "availability_method": result.pit_metadata.availability_method if result.pit_metadata else None,
                "source": result.pit_metadata.source if result.pit_metadata else None,
                "source_version": result.pit_metadata.source_version if result.pit_metadata else None,
                "source_hash": result.pit_metadata.source_hash if result.pit_metadata else None,
            }
        )
    return pd.DataFrame(rows)


def _financial_mapping_audit(results: list[Any]) -> pd.DataFrame:
    rows = []
    for result in results:
        if result.sector_logic != "FINANCIAL":
            continue
        metrics = result.metrics
        core = {
            "EPS": metrics.get("ttm_eps"),
            "NET_INCOME": metrics.get("ttm_net_income"),
            "EQUITY": metrics.get("equity"),
            "BVPS": metrics.get("bvps"),
            "ROE": metrics.get("roe"),
        }
        rows.append(
            {
                "symbol": result.symbol,
                "company": result.company,
                "financial_subtype": result.financial_subtype,
                "eps_statement": "income statement / vendor EPS field",
                "net_income_statement": "income statement / vendor IncomeAfterTaxes fallback",
                "equity_statement": "balance sheet / owners-of-parent equity fallback",
                "bvps_statement": "balance sheet / vendor per-share field when supplied",
                "period_basis": "UNVERIFIED_STANDALONE_VS_CUMULATIVE",
                "unit_basis": "VENDOR_NATIVE_UNVERIFIED_FOR_CROSS_FIELD_CONSISTENCY",
                "ttm_eps": core["EPS"],
                "ttm_net_income": core["NET_INCOME"],
                "equity": core["EQUITY"],
                "bvps": core["BVPS"],
                "roe": core["ROE"],
                "missing_core_fields": " | ".join(name for name, value in core.items() if value is None),
                "roe_mapping_anomaly": metrics.get("roe") is not None and abs(float(metrics["roe"])) > 0.50,
                "usable": False,
                "result": "UNKNOWN / INSUFFICIENT",
                "reason_code": "FINANCIAL_STATE_UNSUPPORTED",
            }
        )
    return pd.DataFrame(rows)


def _write_manifest(output_dir: Path, config: dict[str, Any], securities: list[SecurityData]) -> None:
    files = [path for path in sorted(output_dir.iterdir()) if path.is_file() and path.name != "artifact_manifest.json"]
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    config_hash = hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    source_hashes = sorted(
        str(security.source_metadata.get("source_hash"))
        for security in securities
        if security.source_metadata.get("source_hash")
    )
    snapshot_identity = hashlib.sha256("\n".join(source_hashes).encode("utf-8")).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "experiment_id": "EXP-0050-FQV-20260903-V01",
        "experiment_type": "fundamental_quality_valuation_shadow_research",
        "generation_timestamp": generated_at,
        "commit_sha": commit_sha,
        "generation_commit_sha": commit_sha,
        "code_version": "FQV-v0.1-correction-pass-1",
        "config_hash": config_hash,
        "data_snapshot_identity": snapshot_identity,
        "source_hash_count": len(source_hashes),
        "data_reference": "Immutable source metadata and hashes; normalized permissible research outputs; vendor raw payloads excluded",
        "config": config,
        "period": {"start": config["history_start"], "end": config["as_of_date"]},
        "universe": {"name": config["universe"], "count": len(securities), "bias": "CURRENT_CONSTITUENTS_ONLY"},
        "status": "PROVISIONAL_SHADOW",
        "claim_boundary": "analysis quality and investment prediction are separate; prediction is not established",
        "artifacts": [{"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size} for path in files],
    }
    (output_dir / "artifact_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    if args.workers < 1 or args.workers > 8:
        raise SystemExit("--workers must be between 1 and 8")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    universe = load_universe(args.universe)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "data_fetch_failures.json").unlink(missing_ok=True)
    print(f"[start] {len(universe)} current 0050 constituents; as-of {config['as_of_date']}", flush=True)
    stock_info = fetch_stock_info(args.cache_dir, refresh=args.refresh)

    securities: list[SecurityData] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_load_one, row, stock_info, config, args.cache_dir, args.refresh): row
            for row in universe
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            row = futures[future]
            try:
                security = future.result()
                securities.append(security)
                print(
                    f"[data {completed:02d}/50] {security.symbol} {security.company}: "
                    f"{len(security.quarterly)} quarters, {len(security.market)} market rows",
                    flush=True,
                )
            except Exception as exc:
                failures.append({"symbol": row["symbol"], "error": str(exc)})
                print(f"[data {completed:02d}/50] {row['symbol']} FAILED: {exc}", flush=True)
    if failures:
        (args.output_dir / "data_fetch_failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"Data acquisition failed closed for {len(failures)} securities")
    securities.sort(key=lambda item: item.symbol)
    benchmark = _load_benchmark(config, args.cache_dir, args.refresh)
    as_of = date.fromisoformat(config["as_of_date"])
    results = [classify_security(security, as_of, config) for security in securities]
    print("[model] current classifications complete", flush=True)

    events = build_backtest_events(securities, benchmark, config, as_of)
    baselines = summarize_baselines(events, config)
    state_validation = summarize_state_validation(events)
    state_confusion = confusion_matrix(events)
    state_accuracy = state_accuracy_metrics(events)
    too_late_diagnosis = diagnose_too_late(events)
    quality_persistence = summarize_quality_persistence(events)
    return_diagnostics = summarize_return_diagnostics(events, config)
    robustness = summarize_robustness(events, config)
    data_quality = _data_quality(results, securities, config)
    financial_audit = _financial_mapping_audit(results)
    print(f"[validation] {len(events)} PIT-proxy events", flush=True)

    write_current_csv(results, args.output_dir / "0050_current_state_matrix_v0.1.csv")
    write_quarterly_csv(securities, args.output_dir / "0050_normalized_financials_pit_v0.1.csv")
    events.to_csv(args.output_dir / "0050_backtest_events_v0.1.csv", index=False, encoding="utf-8-sig")
    baselines.to_csv(args.output_dir / "0050_baseline_comparison_v0.1.csv", index=False, encoding="utf-8-sig")
    state_validation.to_csv(args.output_dir / "0050_state_validation_v0.1.csv", index=False, encoding="utf-8-sig")
    state_confusion.to_csv(args.output_dir / "0050_state_confusion_matrix_v0.1.csv", index=False, encoding="utf-8-sig")
    state_accuracy.to_csv(args.output_dir / "0050_state_accuracy_metrics_v0.1.csv", index=False, encoding="utf-8-sig")
    too_late_diagnosis.to_csv(args.output_dir / "0050_too_late_diagnosis_v0.1.csv", index=False, encoding="utf-8-sig")
    quality_persistence.to_csv(args.output_dir / "0050_quality_persistence_v0.1.csv", index=False, encoding="utf-8-sig")
    return_diagnostics.to_csv(args.output_dir / "0050_return_diagnostics_v0.1.csv", index=False, encoding="utf-8-sig")
    robustness.to_csv(args.output_dir / "0050_robustness_diagnostics_v0.1.csv", index=False, encoding="utf-8-sig")
    financial_audit.to_csv(args.output_dir / "0050_financial_mapping_audit_v0.1.csv", index=False, encoding="utf-8-sig")
    _peer_context(results).to_csv(args.output_dir / "0050_peer_context_v0.1.csv", index=False, encoding="utf-8-sig")
    data_quality.to_csv(args.output_dir / "0050_data_quality_report_v0.1.csv", index=False, encoding="utf-8-sig")
    write_json_bundle(
        results,
        securities,
        events,
        baselines,
        state_validation,
        state_confusion,
        state_accuracy,
        quality_persistence,
        return_diagnostics,
        robustness,
        data_quality,
        financial_audit,
        too_late_diagnosis,
        config,
        args.output_dir / "0050_fundamental_quality_valuation_backtest_v0.1.json",
    )
    if not args.skip_pdf:
        font_path = _font(args.cache_dir, args.skip_font_download)
        write_pdf_report(
            results,
            securities,
            events,
            baselines,
            state_validation,
            state_confusion,
            state_accuracy,
            quality_persistence,
            return_diagnostics,
            data_quality,
            config,
            args.output_dir / "0050_fundamental_quality_valuation_backtest_v0.1.pdf",
            font_path=font_path,
        )
        print("[report] PDF complete", flush=True)
    _write_manifest(args.output_dir, config, securities)
    print(f"[done] artifacts: {args.output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
