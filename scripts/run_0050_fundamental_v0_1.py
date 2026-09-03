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
    summarize_baselines,
    summarize_quality_persistence,
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
from experiments.fundamental_quality_valuation.report import (  # noqa: E402
    write_current_csv,
    write_json_bundle,
    write_pdf_report,
    write_quarterly_csv,
)


FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"


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
    path = cache_dir / "NotoSansCJKtc-Regular.otf"
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
            pd.to_numeric(frame[column], errors="coerce").groupby(frame["industry"]).rank(pct=True)
        )
    frame["peer_context_note"] = "Descriptive peer context only; low P/E is not treated as cheap without quality and growth context"
    return frame


def _data_quality(results: list[Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": result.symbol,
                "company": result.company,
                "data_quality": result.data_quality,
                "flags": " | ".join(result.data_quality_flags),
                "period_end": result.period_end,
                "as_of_date": result.as_of_date,
                "announcement_date": result.pit_metadata.announcement_date if result.pit_metadata else None,
                "available_date": result.pit_metadata.available_date if result.pit_metadata else None,
                "availability_method": result.pit_metadata.availability_method if result.pit_metadata else None,
                "source": result.pit_metadata.source if result.pit_metadata else None,
                "sector_specific_logic": result.sector_logic,
            }
            for result in results
        ]
    )


def _write_manifest(output_dir: Path, config: dict[str, Any], securities: list[SecurityData]) -> None:
    files = [path for path in sorted(output_dir.iterdir()) if path.is_file() and path.name != "artifact_manifest.json"]
    payload = {
        "experiment_id": "EXP-0050-FQV-20260903-V01",
        "experiment_type": "fundamental_quality_valuation_shadow_research",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "data_reference": "FinMind v4 cached raw responses; current 0050 universe snapshot",
        "config": config,
        "period": {"start": config["history_start"], "end": config["as_of_date"]},
        "universe": {"name": config["universe"], "count": len(securities), "bias": config["universe_bias_flag"]},
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
    quality_persistence = summarize_quality_persistence(events)
    print(f"[validation] {len(events)} PIT-proxy events", flush=True)

    write_current_csv(results, args.output_dir / "0050_current_state_matrix_v0.1.csv")
    write_quarterly_csv(securities, args.output_dir / "0050_normalized_financials_pit_v0.1.csv")
    events.to_csv(args.output_dir / "0050_backtest_events_v0.1.csv", index=False, encoding="utf-8-sig")
    baselines.to_csv(args.output_dir / "0050_baseline_comparison_v0.1.csv", index=False, encoding="utf-8-sig")
    state_validation.to_csv(args.output_dir / "0050_state_validation_v0.1.csv", index=False, encoding="utf-8-sig")
    quality_persistence.to_csv(args.output_dir / "0050_quality_persistence_v0.1.csv", index=False, encoding="utf-8-sig")
    _peer_context(results).to_csv(args.output_dir / "0050_peer_context_v0.1.csv", index=False, encoding="utf-8-sig")
    _data_quality(results).to_csv(args.output_dir / "0050_data_quality_report_v0.1.csv", index=False, encoding="utf-8-sig")
    write_json_bundle(
        results,
        securities,
        events,
        baselines,
        state_validation,
        quality_persistence,
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
            quality_persistence,
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
