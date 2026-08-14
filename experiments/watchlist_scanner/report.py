from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
from html import escape
import hashlib
import json
from pathlib import Path

from experiments.continuous_high_monitor import render_monitor_svg
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
    ranking_svg = _ranking_svg(scan.candidates)
    timeline_svg = _timeline_svg(scan)
    symbol_charts = _symbol_charts(scan)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TWstock Watchlist Scanner v0.3</title>
<style>
:root {{ color-scheme: dark; --bg:#0b1020; --panel:#131a2c; --line:#2a3550; --text:#e8edf7; --muted:#9ba8bf; --accent:#6ee7b7; --warn:#fbbf24; --danger:#fb7185; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:28px; background:var(--bg); color:var(--text); font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1500px; margin:auto; }}
h1,h2 {{ margin:0 0 12px; }} h1 {{ font-size:26px; }} h2 {{ margin-top:28px; font-size:18px; }}
h3 {{ margin:0 0 5px; font-size:16px; }}
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
.chart-wrap {{ overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }}
.chart-wrap svg {{ display:block; min-width:960px; width:100%; height:auto; }}
.symbol-chart {{ margin:14px 0 24px; }}
.symbol-meta {{ color:var(--muted); margin:0 0 9px; }}
.legend {{ display:flex; flex-wrap:wrap; gap:16px; color:var(--muted); margin:6px 0 10px; }}
.legend b {{ color:var(--text); }}
code {{ color:#c4b5fd; }} footer {{ color:var(--muted); margin-top:24px; }}
</style>
</head>
<body><main>
<h1>Watchlist Scanner v0.3</h1>
<div class="warning">SHADOW OBSERVATION ONLY · 不作投資使用 · Investment use: PROHIBITED<br>
公司行動狀態：UNVERIFIED。價格為 TWSE 官方原始未還權日價；除權息、分割等跳空尚未驗證。</div>
<div class="summary">
  <div class="card"><b>掃描檔數</b><span>{len(scan.requested_symbols)}</span></div>
  <div class="card"><b>可排名候選</b><span>{ranked_count}</span></div>
  <div class="card"><b>共同觀察日</b><span>{escape(as_of)}</span></div>
  <div class="card"><b>資料政策</b><span>TWSE only</span></div>
</div>
<p class="muted">排序是可重現的觀察優先序，不是預測分數或買賣建議。先依事件層級，再依成交量比、距離 Pivot、股票代碼決定。</p>
<h2>候選排名圖</h2>
<p class="muted">這是序位圖，不使用長條長度暗示報酬、勝率或強弱分數；每列只呈現排名、候選層級與目前引擎狀態。</p>
<div class="chart-wrap">{ranking_svg}</div>
<h2>候選排名與原因</h2>
<div class="table-wrap"><table>
<thead><tr><th>Rank</th><th>股票</th><th>狀態</th><th>候選層級</th><th>觀察日</th><th>收盤</th><th>Breakout</th><th>Continuous High</th><th>新高視窗</th><th>量比</th><th>風險</th><th>原因</th><th>公司行動</th></tr></thead>
<tbody>{candidate_rows}</tbody></table></div>
<h2>圖形化事件時間線</h2>
<div class="legend"><span><b>◆</b> Breakout Tracker v5</span><span><b>●</b> Continuous High</span></div>
<div class="chart-wrap">{timeline_svg}</div>
<h2>事件時間線（新到舊；最多顯示最新 {_HTML_TIMELINE_LIMIT} 筆，完整資料見 CSV）</h2>
<div class="table-wrap"><table>
<thead><tr><th>日期</th><th>股票</th><th>引擎</th><th>事件</th><th>狀態</th><th>細節</th><th>收盤</th><th>Event ID</th></tr></thead>
<tbody>{timeline_rows}</tbody></table></div>
<h2>每檔價量與事件圖</h2>
<p class="muted">黑線為收盤價、藍紅柱為成交量；藍色三角形標示 Continuous High，紫色菱形標示 Pivot breakout。圖中價格均為 TWSE 原始未還權價格。</p>
{symbol_charts}
<footer>Manifest ID: <code>{escape(str(manifest["scan_id"]))}</code> · Schema: TWSTOCK-WATCHLIST-SCAN-001</footer>
</main></body></html>"""


def _ranking_svg(candidates: tuple[CandidateObservation, ...]) -> str:
    if not candidates:
        return "<p>沒有候選資料。</p>"
    width = 1180
    row_height = 48
    height = 48 + len(candidates) * row_height
    parts = [
        f'<svg id="candidate-ranking-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="ranking-title ranking-desc">',
        '<title id="ranking-title">候選觀察序位</title>',
        '<desc id="ranking-desc">依確定性規則排列的候選序位；圖形不表示預期報酬或投資分數。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for index, item in enumerate(candidates):
        y = 30 + index * row_height
        rank = str(item.rank) if item.rank is not None else "—"
        status = item.candidate_tier if item.rank is not None else item.scan_status
        engine_state = f"Breakout {item.breakout_state} · High {item.high_stage}"
        ratio = f"量比 {item.volume_ratio:.2f}x" if item.volume_ratio is not None else "量比 —"
        row_fill = "#17223a" if index % 2 == 0 else "#131c31"
        rank_fill = "#0f766e" if item.rank is not None else "#475569"
        parts.extend(
            (
                f'<rect x="12" y="{y-20}" width="1156" height="40" rx="8" fill="{row_fill}"/>',
                f'<circle cx="40" cy="{y}" r="15" fill="{rank_fill}"/>',
                f'<text x="40" y="{y+4}" text-anchor="middle" font-size="12" font-weight="700" fill="#f8fafc">{escape(rank)}</text>',
                f'<text x="70" y="{y+5}" font-size="14" font-weight="700" fill="#e8edf7">{escape(item.symbol)}</text>',
                f'<text x="215" y="{y+5}" font-size="13" fill="#6ee7b7">{escape(status)}</text>',
                f'<text x="510" y="{y+5}" font-size="12" fill="#cbd5e1">{escape(engine_state)}</text>',
                f'<text x="1025" y="{y+5}" font-size="12" fill="#9ba8bf">{escape(ratio)}</text>',
            )
        )
    parts.append("</svg>")
    return "".join(parts)


def _timeline_svg(scan: WatchlistScan) -> str:
    events = scan.timeline[-_HTML_TIMELINE_LIMIT:]
    if not events:
        return "<p>尚無事件可繪製；完整狀態仍保留於候選表。</p>"
    symbols = tuple(
        item.symbol
        for item in scan.candidates
        if any(event.symbol == item.symbol for event in events)
    )
    width = 1180
    left, right = 145, 28
    top, row_height = 55, 36
    height = top + len(symbols) * row_height + 42
    first_ordinal = min(event.trade_date.toordinal() for event in events)
    last_ordinal = max(event.trade_date.toordinal() for event in events)
    same_day = first_ordinal == last_ordinal
    span = max(1, last_ordinal - first_ordinal)
    plot_width = width - left - right

    def x(trade_date: date) -> float:
        if same_day:
            return left + plot_width / 2
        return left + (trade_date.toordinal() - first_ordinal) / span * plot_width

    y_by_symbol = {
        symbol: top + index * row_height for index, symbol in enumerate(symbols)
    }
    parts = [
        f'<svg id="event-timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="timeline-title timeline-desc">',
        '<title id="timeline-title">Breakout 與 Continuous High 圖形化事件時間線</title>',
        f'<desc id="timeline-desc">最多顯示最新 {_HTML_TIMELINE_LIMIT} 筆事件，完整事件保留於 CSV。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for symbol, yy in y_by_symbol.items():
        parts.append(
            f'<text x="{left-12}" y="{yy+4}" text-anchor="end" font-size="12" font-weight="700" fill="#e8edf7">{escape(symbol)}</text>'
        )
        parts.append(
            f'<line x1="{left}" y1="{yy}" x2="{width-right}" y2="{yy}" stroke="#2a3550"/>'
        )
    tick_steps = (2,) if same_day else range(5)
    for step in tick_steps:
        ordinal = first_ordinal if same_day else first_ordinal + round(span * step / 4)
        tick_date = date.fromordinal(ordinal)
        xx = left + plot_width * step / 4
        parts.append(
            f'<line x1="{xx:.1f}" y1="30" x2="{xx:.1f}" y2="{height-28}" stroke="#26324a"/>'
        )
        parts.append(
            f'<text x="{xx:.1f}" y="20" text-anchor="middle" font-size="11" fill="#9ba8bf">{tick_date.isoformat()}</text>'
        )
    event_groups: dict[tuple[str, date, str], list[TimelineEvent]] = {}
    for event in events:
        event_groups.setdefault(
            (event.symbol, event.trade_date, event.source_engine), []
        ).append(event)
    for (symbol, trade_date, source_engine), grouped_events in event_groups.items():
        yy = y_by_symbol.get(symbol)
        if yy is None:
            continue
        xx = x(trade_date)
        details = " | ".join(
            f"{event.event_type} · {event.state} · {event.detail}"
            for event in grouped_events
        )
        title = escape(
            f"{trade_date.isoformat()} · {source_engine} · {details}"
        )
        if source_engine == "BREAKOUT_TRACKER_V5":
            marker_y = yy - 4
            parts.append(
                f'<rect x="{xx-4:.1f}" y="{marker_y-4:.1f}" width="8" height="8" fill="#a78bfa" transform="rotate(45 {xx:.1f} {marker_y:.1f})"><title>{title}</title></rect>'
            )
        else:
            marker_y = yy + 4
            parts.append(
                f'<circle cx="{xx:.1f}" cy="{marker_y:.1f}" r="4" fill="#38bdf8" stroke="#10182a" stroke-width="1"><title>{title}</title></circle>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _symbol_charts(scan: WatchlistScan) -> str:
    datasets = {item.source_symbol: item for item in scan.datasets}
    visualizations = {item.source_symbol: item for item in scan.visualizations}
    sections: list[str] = []
    for candidate in scan.candidates:
        dataset = datasets.get(candidate.source_symbol)
        visualization = visualizations.get(candidate.source_symbol)
        if dataset is None or visualization is None:
            continue
        svg = render_monitor_svg(
            dataset.bars,
            visualization.continuous_high_result,
            visualization.monitor_config,
            visualization.breakout_snapshots,
        )
        rank_label = f"#{candidate.rank}" if candidate.rank is not None else "未排名"
        sections.append(
            f'''<section class="symbol-chart" id="symbol-{escape(candidate.source_symbol)}">
<h3>{escape(rank_label)} · {escape(candidate.symbol)} · {escape(candidate.candidate_tier)}</h3>
<p class="symbol-meta">觀察日 {escape(candidate.observed_date.isoformat() if candidate.observed_date else "—")} · 收盤 {escape(_number(candidate.close))} · Breakout {escape(candidate.breakout_state)} · Continuous High {escape(candidate.high_stage)} · 公司行動 <span class="bad">UNVERIFIED</span></p>
<div class="chart-wrap">{svg}</div>
</section>'''
        )
    return "\n".join(sections) or "<p>沒有可用的個股資料圖。</p>"


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
        "visualization_policy": {
            "format": "STANDALONE_INLINE_SVG_NO_EXTERNAL_DEPENDENCIES",
            "rank_encoding": "ORDINAL_ONLY_NO_SCORE_MAGNITUDE",
            "ranking_chart": "ALL_CANDIDATES_IN_DETERMINISTIC_ORDER",
            "symbol_charts": "ALL_SUCCESSFULLY_LOADED_DATASETS",
            "event_timeline_limit_in_html": _HTML_TIMELINE_LIMIT,
            "complete_event_timeline": "watchlist_timeline.csv",
            "price_basis": "RAW_OFFICIAL_DAILY_UNADJUSTED",
            "corporate_action_status": "UNVERIFIED",
            "investment_use": "PROHIBITED",
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
