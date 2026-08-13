from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import hashlib
import json
from pathlib import Path

from twstock_data.dataset import write_research_dataset
from twstock_data.normalization import stable_json_bytes

from .models import CandidateObservation, TimelineEvent, WatchlistScan


_CANDIDATE_FIELDS = (
    "rank",
    "source_symbol",
    "symbol",
    "scan_status",
    "candidate_tier",
    "observed_date",
    "close",
    "breakout_state",
    "breakout_reason",
    "distance_to_pivot_pct",
    "volume_ratio",
    "high_stage",
    "new_high_windows",
    "risk_flags",
    "reason_codes",
    "bar_count",
    "minimum_history_bars",
    "dataset_hash",
    "data_source_status",
    "corporate_action_status",
    "investment_use",
    "error_code",
)
_TIMELINE_FIELDS = (
    "event_id",
    "symbol",
    "trade_date",
    "source_engine",
    "event_type",
    "detail",
    "state",
    "close",
)
_HTML_TIMELINE_LIMIT = 1000


def write_watchlist_outputs(scan: WatchlistScan, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_candidates(output_dir / "watchlist_candidates.csv", scan.candidates)
    _write_timeline(output_dir / "watchlist_timeline.csv", scan.timeline)
    manifest = _manifest(scan)
    (output_dir / "watchlist_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "watchlist.html").write_text(
        render_watchlist_html(scan, manifest), encoding="utf-8"
    )
    for dataset in scan.datasets:
        write_research_dataset(
            dataset, output_dir / "symbols" / dataset.source_symbol
        )


def render_watchlist_html(
    scan: WatchlistScan, manifest: dict[str, object] | None = None
) -> str:
    manifest = manifest or _manifest(scan)
    candidate_rows = "\n".join(_candidate_row(item) for item in scan.candidates)
    timeline_rows = "\n".join(
        _timeline_row(item)
        for item in reversed(scan.timeline[-_HTML_TIMELINE_LIMIT:])
    )
    as_of = scan.as_of_trade_date.isoformat() if scan.as_of_trade_date else "—"
    ranked_count = sum(item.rank is not None for item in scan.candidates)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TWstock Watchlist Scanner v0.1</title>
<style>
:root {{ color-scheme: dark; --bg:#0b1020; --panel:#131a2c; --line:#2a3550; --text:#e8edf7; --muted:#9ba8bf; --accent:#6ee7b7; --warn:#fbbf24; --danger:#fb7185; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:28px; background:var(--bg); color:var(--text); font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1500px; margin:auto; }}
h1,h2 {{ margin:0 0 12px; }} h1 {{ font-size:26px; }} h2 {{ margin-top:28px; font-size:18px; }}
.warning {{ border:1px solid var(--danger); background:#351523; padding:16px; border-radius:10px; color:#ffd8df; font-weight:700; }}
.summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:18px 0; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.card b {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; }} .card span {{ font-size:20px; }}
.table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:10px; }}
table {{ width:100%; border-collapse:collapse; background:var(--panel); white-space:nowrap; }}
th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ position:sticky; top:0; background:#1a2338; color:var(--muted); font-size:12px; }}
td.reasons {{ white-space:normal; min-width:340px; }} .rank {{ color:var(--accent); font-weight:800; }}
.bad {{ color:var(--danger); font-weight:700; }} .warn {{ color:var(--warn); }} .muted {{ color:var(--muted); }}
code {{ color:#c4b5fd; }} footer {{ color:var(--muted); margin-top:24px; }}
</style>
</head>
<body><main>
<h1>Watchlist Scanner v0.1</h1>
<div class="warning">SHADOW OBSERVATION ONLY · 不作投資使用 · Investment use: PROHIBITED<br>
公司行動狀態：UNVERIFIED。價格為 TWSE 官方原始未還權日價；除權息、分割等跳空尚未驗證。</div>
<div class="summary">
  <div class="card"><b>掃描檔數</b><span>{len(scan.requested_symbols)}</span></div>
  <div class="card"><b>可排名候選</b><span>{ranked_count}</span></div>
  <div class="card"><b>共同觀察日</b><span>{escape(as_of)}</span></div>
  <div class="card"><b>資料政策</b><span>TWSE only</span></div>
</div>
<p class="muted">排序是可重現的觀察優先序，不是預測分數或買賣建議。先依事件層級，再依成交量比、距離 Pivot、股票代碼決定。</p>
<h2>候選排名與原因</h2>
<div class="table-wrap"><table>
<thead><tr><th>Rank</th><th>股票</th><th>狀態</th><th>候選層級</th><th>觀察日</th><th>收盤</th><th>Breakout</th><th>Continuous High</th><th>新高視窗</th><th>量比</th><th>風險</th><th>原因</th><th>公司行動</th></tr></thead>
<tbody>{candidate_rows}</tbody></table></div>
<h2>事件時間線（新到舊；最多顯示最新 {_HTML_TIMELINE_LIMIT} 筆，完整資料見 CSV）</h2>
<div class="table-wrap"><table>
<thead><tr><th>日期</th><th>股票</th><th>引擎</th><th>事件</th><th>狀態</th><th>細節</th><th>收盤</th><th>Event ID</th></tr></thead>
<tbody>{timeline_rows}</tbody></table></div>
<footer>Manifest ID: <code>{escape(str(manifest["scan_id"]))}</code> · Schema: TWSTOCK-WATCHLIST-SCAN-001</footer>
</main></body></html>"""


def _write_candidates(
    path: Path, candidates: tuple[CandidateObservation, ...]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CANDIDATE_FIELDS)
        writer.writeheader()
        for item in candidates:
            writer.writerow(_candidate_mapping(item))


def _write_timeline(path: Path, events: tuple[TimelineEvent, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TIMELINE_FIELDS)
        writer.writeheader()
        for item in events:
            row = asdict(item)
            row["trade_date"] = item.trade_date.isoformat()
            row["close"] = _number(item.close)
            writer.writerow(row)


def _candidate_mapping(item: CandidateObservation) -> dict[str, object]:
    row = asdict(item)
    row["rank"] = "" if item.rank is None else item.rank
    row["observed_date"] = (
        item.observed_date.isoformat() if item.observed_date else ""
    )
    row["close"] = _number(item.close)
    row["distance_to_pivot_pct"] = _number(item.distance_to_pivot_pct)
    row["volume_ratio"] = _number(item.volume_ratio)
    row["new_high_windows"] = "|".join(str(value) for value in item.new_high_windows)
    row["risk_flags"] = "|".join(item.risk_flags)
    row["reason_codes"] = "|".join(item.reason_codes)
    return row


def _manifest(scan: WatchlistScan) -> dict[str, object]:
    identity = {
        "schema_version": "TWSTOCK-WATCHLIST-SCAN-001",
        "requested_start": scan.requested_start,
        "requested_end": scan.requested_end,
        "requested_symbols": list(scan.requested_symbols),
        "dataset_hashes": sorted(
            dataset.dataset_hash for dataset in scan.datasets
        ),
        "monitor_parameter_hash": scan.monitor_parameter_hash,
        "breakout_config_hash": scan.breakout_config_hash,
    }
    scan_id = hashlib.sha256(stable_json_bytes(identity)).hexdigest()
    statuses = {
        status: sum(item.scan_status == status for item in scan.candidates)
        for status in (
            "OK",
            "INSUFFICIENT_HISTORY",
            "STALE_DATA",
            "DATA_UNAVAILABLE",
        )
    }
    return {
        **identity,
        "scan_id": scan_id,
        "run_type": "SHADOW_OBSERVATION",
        "source_policy": "OFFICIAL_TWSE_ONLY_NO_FINMIND",
        "source_cross_check_status": "UNAVAILABLE_BY_POLICY",
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_action_status": "UNVERIFIED",
        "investment_use": "PROHIBITED",
        "as_of_trade_date": (
            scan.as_of_trade_date.isoformat() if scan.as_of_trade_date else None
        ),
        "minimum_history_bars": scan.minimum_history_bars,
        "monitor_parameter_version": scan.monitor_parameter_version,
        "counts": {
            "requested": len(scan.requested_symbols),
            "datasets_loaded": len(scan.datasets),
            "ranked": sum(item.rank is not None for item in scan.candidates),
            "events": len(scan.timeline),
            **statuses,
        },
        "ranking_policy": {
            "method": "DETERMINISTIC_LEXICOGRAPHIC_NO_SCORE",
            "tier_order": [
                "DUAL_TRIGGER",
                "BREAKOUT_TRIGGER",
                "EARLY_HIGH",
                "STRENGTHENING",
                "NEW_HIGH",
                "RETEST",
                "LEADER",
                "SETUP",
                "CONFIRMED",
                "WATCH",
                "EXTENDED",
                "COOLING",
                "WEAKENING",
                "INACTIVE",
            ],
            "within_tier": [
                "volume_ratio_desc",
                "absolute_distance_to_pivot_asc",
                "source_symbol_asc",
            ],
            "excluded_statuses": [
                "INSUFFICIENT_HISTORY",
                "STALE_DATA",
                "DATA_UNAVAILABLE",
            ],
        },
        "outputs": {
            "candidates": "watchlist_candidates.csv",
            "timeline": "watchlist_timeline.csv",
            "manifest": "watchlist_manifest.json",
            "html": "watchlist.html",
            "symbol_evidence": "symbols/<symbol>/",
        },
        "warnings": [
            "Shadow Observation only; not for investment use.",
            "Corporate-action data is absent and marked UNVERIFIED.",
            "TWSE prices are raw and unadjusted; ex-right, ex-dividend, and split discontinuities may create false events.",
            "Candidate rank is an observation priority, not an expected-return or risk score.",
        ],
    }


def _candidate_row(item: CandidateObservation) -> str:
    rank = str(item.rank) if item.rank is not None else "—"
    observed = item.observed_date.isoformat() if item.observed_date else "—"
    status_class = "" if item.scan_status == "OK" else "bad"
    risks = ", ".join(item.risk_flags) or "—"
    highs = ", ".join(f"{value}D" for value in item.new_high_windows) or "—"
    reasons = " · ".join(item.reason_codes)
    return f"""<tr>
<td class="rank">{escape(rank)}</td><td>{escape(item.symbol)}</td>
<td class="{status_class}">{escape(item.scan_status)}</td><td>{escape(item.candidate_tier)}</td>
<td>{escape(observed)}</td><td>{escape(_number(item.close))}</td>
<td>{escape(item.breakout_state)}</td><td>{escape(item.high_stage)}</td>
<td>{escape(highs)}</td><td>{escape(_number(item.volume_ratio))}</td>
<td class="warn">{escape(risks)}</td><td class="reasons">{escape(reasons)}</td>
<td class="bad">{escape(item.corporate_action_status)}</td></tr>"""


def _timeline_row(item: TimelineEvent) -> str:
    return f"""<tr><td>{item.trade_date.isoformat()}</td><td>{escape(item.symbol)}</td>
<td>{escape(item.source_engine)}</td><td>{escape(item.event_type)}</td>
<td>{escape(item.state)}</td><td>{escape(item.detail)}</td>
<td>{escape(_number(item.close))}</td><td><code>{escape(item.event_id)}</code></td></tr>"""


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.10g}"
