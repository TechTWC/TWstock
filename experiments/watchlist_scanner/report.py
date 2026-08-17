from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
from html import escape
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

from experiments.continuous_high_monitor import render_monitor_svg
from experiments.moving_average_state import (
    render_core_ma_svg,
    render_long_term_ma_svg,
)
from experiments.seven_state_radar import RadarState
from twstock_data.dataset import write_research_dataset
from twstock_data.models import MarketBar
from twstock_data.normalization import stable_json_bytes

from .models import CandidateObservation, TimelineEvent, WatchlistScan


_CANDIDATE_FIELDS = (
    "rank",
    "source_symbol",
    "symbol",
    "company_name",
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
    "market_state",
    "market_state_days",
    "market_state_transition",
    "ma_state",
    "ma_long_term_context",
    "ma20_slope_pct",
    "ma60_slope_pct",
    "distance_to_ma20_pct",
    "double_slope_state",
    "double_slope_prior_pct",
    "double_slope_recent_pct",
    "double_slope_z_score",
    "method_relationship",
    "cb_issuer_status",
    "cb_current_issue_count",
    "cb_recent_delisted_count",
    "cb_issue_names",
    "cb_data_as_of",
    "cb_source_status",
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
_FULL_MARKET_RANKING_CHART_LIMIT = 200
_FULL_MARKET_SYMBOL_CHART_LIMIT = 30
_FULL_MARKET_TIMELINE_SYMBOL_LIMIT = 100
_STATE_LABELS = {
    RadarState.NOISE.value: "0 雜訊／方向不明",
    RadarState.BASE.value: "1 整理／築底",
    RadarState.TURNING_UP.value: "2 剛轉多",
    RadarState.TREND_CONFIRMED.value: "3 趨勢確認",
    RadarState.PERSISTING.value: "4 持續上升",
    RadarState.EXTENDED.value: "5 過度延伸",
    RadarState.WEAKENING.value: "6 衰退／轉空",
}
_STATE_COLORS = {
    RadarState.NOISE.value: "#94a3b8",
    RadarState.BASE.value: "#fbbf24",
    RadarState.TURNING_UP.value: "#2dd4bf",
    RadarState.TREND_CONFIRMED.value: "#22c55e",
    RadarState.PERSISTING.value: "#16a34a",
    RadarState.EXTENDED.value: "#c084fc",
    RadarState.WEAKENING.value: "#fb7185",
}
_STATE_RULES = {
    RadarState.NOISE.value: "資料不足，或均線訊號互相矛盾，沒有可主導的方向結構。",
    RadarState.BASE.value: "MA20、MA60接近水平，MA5／10／20／60收斂，價格靠近MA20。",
    RadarState.TURNING_UP.value: "價格站上MA20、MA5高於MA10、MA20轉升，但完整多頭排列尚未確認。",
    RadarState.TREND_CONFIRMED.value: "價格與MA5／10／20／60完整多頭排列，MA20與MA60向上，尚未持續滿10日。",
    RadarState.PERSISTING.value: "曾完成趨勢確認後，核心多頭結構持續至少10個交易日，且距MA20尚未達過熱門檻。",
    RadarState.EXTENDED.value: "轉多或多頭狀態下，價格距MA20至少12%；保留趨勢資訊但避免誤認為早期。",
    RadarState.WEAKENING.value: "均線已轉弱／轉空，或先前多頭結構不再成立。",
}


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
    observed_count = sum(item.rank is not None for item in scan.candidates)
    current_cb_count = sum(
        item.cb_issuer_status == "CURRENT_CB" for item in scan.candidates
    )
    ranking_svg = _ranking_svg(scan.candidates)
    timeline_svg = _timeline_svg(scan)
    symbol_charts = _symbol_charts(scan)
    state_cards = _state_summary_cards(scan.candidates)
    transition_rows = _today_transition_rows(scan)
    glossary_rows = _state_glossary_rows()
    ranking_scope = (
        f"全市場模式僅繪製前 {_FULL_MARKET_RANKING_CHART_LIMIT} 列；完整資料保留在下表與 CSV。"
        if len(scan.candidates) > _FULL_MARKET_RANKING_CHART_LIMIT
        else "圖中包含本次全部候選列。"
    )
    symbol_scope = (
        f"全市場模式只繪製前 {_FULL_MARKET_SYMBOL_CHART_LIMIT} 個可排名候選，避免單一 HTML 過大；完整狀態保留在 CSV。"
        if len(scan.candidates) > 100
        else "圖中包含全部成功載入的股票。"
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Radar v0.4</title>
<style>
:root {{ color-scheme: dark; --bg:#0b1020; --panel:#131a2c; --line:#2a3550; --text:#e8edf7; --muted:#9ba8bf; --accent:#6ee7b7; --warn:#fbbf24; --danger:#fb7185; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:28px; background:var(--bg); color:var(--text); font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1500px; margin:auto; }}
h1,h2 {{ margin:0 0 12px; }} h1 {{ font-size:26px; }} h2 {{ margin-top:28px; font-size:18px; }}
h3 {{ margin:0 0 5px; font-size:16px; }} h4 {{ margin:16px 0 6px; font-size:14px; }}
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
.pill {{ display:inline-block; padding:3px 8px; border-radius:999px; background:color-mix(in srgb,var(--state) 24%,#111827); color:var(--state); font-weight:800; }}
code {{ color:#c4b5fd; }} footer {{ color:var(--muted); margin-top:24px; }}
</style>
</head>
<body><main>
<h1>Watchlist Radar v0.4</h1>
<div class="warning">SHADOW OBSERVATION ONLY · 不作投資使用 · Investment use: PROHIBITED<br>
公司行動狀態：UNVERIFIED。價格為 TWSE 官方原始未還權日價；除權息、分割等跳空尚未驗證。</div>
<div class="summary">
  <div class="card"><b>掃描檔數</b><span>{len(scan.requested_symbols)}</span></div>
  <div class="card"><b>可判讀股票</b><span>{observed_count}</span></div>
  <div class="card"><b>共同觀察日</b><span>{escape(as_of)}</span></div>
  <div class="card"><b>資料政策</b><span>TWSE only</span></div>
  <div class="card"><b>目前有 CB</b><span>{current_cb_count}</span></div>
</div>
<p class="muted">主分類只由透明均線基準轉譯成七狀態；雙斜率獨立顯示，不合成分數。Breakout／Continuous High只列為輔助證據，不參與觀察順序。順序依七狀態、目標轉換類型、其他今日轉換、狀態持續日數、股票代碼決定；整理→剛轉多會排在剛轉多群組最前面。</p>
<h2>全市場七狀態分布</h2>
<div class="summary">{state_cards}</div>
<h2>今天值得先看的狀態轉換</h2>
<p class="muted">只列今天發生的狀態轉換；沒有出現時代表本次資料中沒有該類事件，不代表市場風險為零。</p>
<div class="table-wrap"><table><thead><tr><th>類型</th><th>檔數</th><th>股票</th><th>白話意義</th></tr></thead><tbody>{transition_rows}</tbody></table></div>
<h2>七狀態規則</h2>
<div class="table-wrap"><table><thead><tr><th>狀態</th><th>本版可檢驗規則</th></tr></thead><tbody>{glossary_rows}</tbody></table></div>
<h2>市場觀察順序圖</h2>
<p class="muted">這不是分數圖，也不表示報酬或勝率；目的是把剛轉多與剛確認放在最前面供人工研究。{escape(ranking_scope)}</p>
<div class="chart-wrap">{ranking_svg}</div>
<h2>全市場方法並排表</h2>
<div class="table-wrap"><table>
<thead><tr><th>順序</th><th>股票</th><th>資料</th><th>七狀態</th><th>持續日</th><th>今日轉換</th><th>均線原始判定</th><th>雙斜率判定</th><th>兩方法關係</th><th>長期背景</th><th>MA20／60斜率</th><th>距MA20</th><th>CB 狀態</th><th>CB 檔數</th><th>CB 名稱</th><th>輔助 Breakout／High</th><th>原因</th><th>公司行動</th></tr></thead>
<tbody>{candidate_rows}</tbody></table></div>
<h2>圖形化事件時間線</h2>
<div class="legend"><span><b style="color:#2dd4bf">●</b> 七狀態轉換</span><span><b style="color:#f59e0b">▲</b> 雙斜率轉折</span><span><b style="color:#a78bfa">◆</b> Breakout（輔助）</span><span><b style="color:#38bdf8">■</b> Continuous High（輔助）</span></div>
<div class="chart-wrap">{timeline_svg}</div>
<h2>事件時間線（新到舊；最多顯示最新 {_HTML_TIMELINE_LIMIT} 筆，完整資料見 CSV）</h2>
<div class="table-wrap"><table>
<thead><tr><th>日期</th><th>股票</th><th>引擎</th><th>事件</th><th>狀態</th><th>細節</th><th>收盤</th><th>Event ID</th></tr></thead>
<tbody>{timeline_rows}</tbody></table></div>
<h2>每檔股價、價量與事件圖</h2>
<p class="muted">主圖把七狀態轉換與雙斜率轉折直接標在事件日收盤價上；舊 Breakout／Continuous High保留為淡化的輔助標記。圖中價格均為 TWSE 原始未還權價格。{escape(symbol_scope)}</p>
{symbol_charts}
<footer>Manifest ID: <code>{escape(str(manifest["scan_id"]))}</code> · Schema: TWSTOCK-WATCHLIST-RADAR-004</footer>
</main></body></html>"""


def _ranking_svg(candidates: tuple[CandidateObservation, ...]) -> str:
    if not candidates:
        return "<p>沒有候選資料。</p>"
    displayed = candidates[:_FULL_MARKET_RANKING_CHART_LIMIT]
    width = 1180
    row_height = 48
    height = 48 + len(displayed) * row_height
    parts = [
        f'<svg id="candidate-ranking-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="ranking-title ranking-desc">',
        '<title id="ranking-title">七狀態市場觀察順序</title>',
        '<desc id="ranking-desc">依七狀態與轉換新鮮度排列；圖形不表示預期報酬或投資分數。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for index, item in enumerate(displayed):
        y = 30 + index * row_height
        rank = str(item.rank) if item.rank is not None else "—"
        status = _STATE_LABELS.get(item.market_state, item.market_state) if item.rank is not None else item.scan_status
        engine_state = f"均線 {item.ma_state} · 雙斜率 {item.double_slope_state}"
        relationship = item.method_relationship
        row_fill = "#17223a" if index % 2 == 0 else "#131c31"
        rank_fill = "#0f766e" if item.rank is not None else "#475569"
        parts.extend(
            (
                f'<rect x="12" y="{y-20}" width="1156" height="40" rx="8" fill="{row_fill}"/>',
                f'<circle cx="40" cy="{y}" r="15" fill="{rank_fill}"/>',
                f'<text x="40" y="{y+4}" text-anchor="middle" font-size="12" font-weight="700" fill="#f8fafc">{escape(rank)}</text>',
                f'<text x="70" y="{y+5}" font-size="14" font-weight="700" fill="#e8edf7">{escape(item.symbol)} {escape(item.company_name)}</text>',
                f'<text x="215" y="{y+5}" font-size="13" fill="#6ee7b7">{escape(status)}</text>',
                f'<text x="510" y="{y+5}" font-size="12" fill="#cbd5e1">{escape(engine_state)}</text>',
                f'<text x="990" y="{y+5}" font-size="12" fill="#9ba8bf">{escape(relationship)}</text>',
            )
        )
    parts.append("</svg>")
    return "".join(parts)


def _state_summary_cards(candidates: tuple[CandidateObservation, ...]) -> str:
    return "".join(
        f'<div class="card"><b>{escape(_STATE_LABELS[state.value])}</b><span style="color:{_STATE_COLORS[state.value]}">{sum(item.scan_status == "OK" and item.market_state == state.value for item in candidates)}</span></div>'
        for state in RadarState
    )


def _state_glossary_rows() -> str:
    return "".join(
        f'<tr><td><span class="pill" style="--state:{_STATE_COLORS[state.value]}">{escape(_STATE_LABELS[state.value])}</span></td><td class="reasons">{escape(_STATE_RULES[state.value])}</td></tr>'
        for state in RadarState
    )


def _today_transition_rows(scan: WatchlistScan) -> str:
    categories = (
        (
            "整理→剛轉多",
            {"BASE->TURNING_UP"},
            "最接近原始目標：整理後開始轉為上升。",
        ),
        (
            "剛轉多→趨勢確認",
            {"TURNING_UP->TREND_CONFIRMED"},
            "早期轉強已形成完整均線多頭結構。",
        ),
        (
            "持續／確認→過度延伸",
            {"TREND_CONFIRMED->EXTENDED", "PERSISTING->EXTENDED", "TURNING_UP->EXTENDED"},
            "趨勢仍可能向上，但位置已不再屬於早期。",
        ),
        (
            "趨勢→轉弱",
            {
                "TURNING_UP->WEAKENING",
                "TREND_CONFIRMED->WEAKENING",
                "PERSISTING->WEAKENING",
                "EXTENDED->WEAKENING",
            },
            "原先向上結構已受損，需優先檢查是假突破或趨勢結束。",
        ),
    )
    rows: list[str] = []
    for label, transitions, meaning in categories:
        selected = tuple(
            item.symbol
            for item in scan.candidates
            if item.scan_status == "OK"
            and item.observed_date == scan.as_of_trade_date
            and item.market_state_transition in transitions
        )
        symbols = "、".join(selected) if selected else "—"
        rows.append(
            f"<tr><td>{escape(label)}</td><td>{len(selected)}</td><td>{escape(symbols)}</td><td class=\"reasons\">{escape(meaning)}</td></tr>"
        )
    return "".join(rows)


def _timeline_svg(scan: WatchlistScan) -> str:
    allowed_symbols: tuple[str, ...] | None = None
    if len(scan.candidates) > 100:
        allowed_symbols = tuple(
            candidate.symbol
            for candidate in scan.candidates
            if candidate.rank is not None
        )[:_FULL_MARKET_TIMELINE_SYMBOL_LIMIT]
    eligible_events = tuple(
        event
        for event in scan.timeline
        if allowed_symbols is None or event.symbol in allowed_symbols
    )
    primary = tuple(
        event
        for event in eligible_events
        if event.source_engine in {"SEVEN_STATE_RADAR", "DOUBLE_SLOPE"}
    )
    auxiliary = tuple(
        event
        for event in eligible_events
        if event.source_engine not in {"SEVEN_STATE_RADAR", "DOUBLE_SLOPE"}
    )
    if len(primary) >= _HTML_TIMELINE_LIMIT:
        events = primary[-_HTML_TIMELINE_LIMIT:]
    else:
        auxiliary_room = _HTML_TIMELINE_LIMIT - len(primary)
        events = tuple(
            sorted(
                (*primary, *auxiliary[-auxiliary_room:]),
                key=lambda event: (
                    event.trade_date,
                    event.symbol,
                    event.source_engine,
                    event.event_id,
                ),
            )
        )
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
        '<title id="timeline-title">七狀態、雙斜率與輔助引擎事件時間線</title>',
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
        if source_engine == "SEVEN_STATE_RADAR":
            marker_y = yy - 9
            parts.append(
                f'<circle data-engine="SEVEN_STATE_RADAR" cx="{xx:.1f}" cy="{marker_y:.1f}" r="5" fill="#2dd4bf" stroke="#10182a"><title>{title}</title></circle>'
            )
        elif source_engine == "DOUBLE_SLOPE":
            marker_y = yy + 9
            parts.append(
                f'<path data-engine="DOUBLE_SLOPE" d="M {xx:.1f} {marker_y-5:.1f} L {xx-5:.1f} {marker_y+4:.1f} L {xx+5:.1f} {marker_y+4:.1f} Z" fill="#f59e0b"><title>{title}</title></path>'
            )
        elif source_engine == "BREAKOUT_TRACKER_V5":
            marker_y = yy - 4
            parts.append(
                f'<rect x="{xx-4:.1f}" y="{marker_y-4:.1f}" width="8" height="8" fill="#a78bfa" transform="rotate(45 {xx:.1f} {marker_y:.1f})"><title>{title}</title></rect>'
            )
        else:
            marker_y = yy + 4
            parts.append(
                f'<rect x="{xx-3.5:.1f}" y="{marker_y-3.5:.1f}" width="7" height="7" fill="#38bdf8"><title>{title}</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def _symbol_charts(scan: WatchlistScan) -> str:
    datasets = {item.source_symbol: item for item in scan.datasets}
    visualizations = {item.source_symbol: item for item in scan.visualizations}
    events_by_symbol: dict[str, list[TimelineEvent]] = {}
    for event in scan.timeline:
        events_by_symbol.setdefault(event.symbol, []).append(event)
    sections: list[str] = []
    candidates = scan.candidates
    if len(candidates) > 100:
        candidates = tuple(
            candidate for candidate in candidates if candidate.rank is not None
        )[:_FULL_MARKET_SYMBOL_CHART_LIMIT]
    for candidate in candidates:
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
        event_price_svg = _event_price_svg(
            dataset.bars, events_by_symbol.get(candidate.symbol, ())
        )
        core_ma_svg = render_core_ma_svg(
            visualization.ma_state_result, dataset.bars
        )
        long_term_ma_svg = render_long_term_ma_svg(
            visualization.ma_state_result, dataset.bars
        )
        rank_label = f"觀察順序 #{candidate.rank}" if candidate.rank is not None else "未判讀"
        sections.append(
            f'''<section class="symbol-chart" id="symbol-{escape(candidate.source_symbol)}">
<h3>{escape(rank_label)} · {escape(candidate.symbol)} {escape(candidate.company_name)} · {escape(_STATE_LABELS.get(candidate.market_state, candidate.market_state))}</h3>
<p class="symbol-meta">觀察日 {escape(candidate.observed_date.isoformat() if candidate.observed_date else "—")} · 收盤 {escape(_number(candidate.close))} · 均線 {escape(candidate.ma_state)} · 雙斜率 {escape(candidate.double_slope_state)} · 方法關係 {escape(candidate.method_relationship)} · CB {escape(candidate.cb_issuer_status)} · 公司行動 <span class="bad">UNVERIFIED</span></p>
<h4>七狀態與雙斜率事件疊加股價圖</h4>
<div class="legend"><span><b style="color:#f8fafc">━</b> 收盤價</span><span><b style="color:#2dd4bf">●</b> 七狀態轉換</span><span><b style="color:#f59e0b">▲</b> 雙斜率轉折</span><span><b style="color:#a78bfa">◆</b> Breakout（輔助）</span><span><b style="color:#38bdf8">■</b> Continuous High（輔助）</span><span>標記均定位在事件日收盤價，游標停留可看內容</span></div>
<div class="chart-wrap">{event_price_svg}</div>
<h4>核心均線圖：收盤與 MA5／10／20／60</h4>
<div class="chart-wrap">{core_ma_svg}</div>
<h4>長期均線圖：收盤與 MA60／120／200／240</h4>
<p class="symbol-meta">MA120／240用於長期背景；MA200只作國際慣例比較，不會否決早期候選。</p>
<div class="chart-wrap">{long_term_ma_svg}</div>
<h4>舊版價量、rolling high 與 Pivot 輔助圖</h4>
<div class="chart-wrap">{svg}</div>
</section>'''
        )
    return "\n".join(sections) or "<p>沒有可用的個股資料圖。</p>"


def _event_price_svg(
    bars: Sequence[MarketBar], events: Sequence[TimelineEvent]
) -> str:
    """Render every engine event at its exact event-day closing-price anchor."""

    if not bars:
        return "<p>沒有可用的價格資料。</p>"
    symbol = bars[0].symbol
    safe_symbol = escape(symbol)
    bar_by_date = {bar.trade_date: bar for bar in bars}
    grouped: dict[tuple[date, str], list[TimelineEvent]] = {}
    for event in events:
        if event.symbol != symbol:
            raise ValueError(
                f"event {event.event_id} symbol does not match price series"
            )
        if event.source_engine not in {
            "SEVEN_STATE_RADAR",
            "DOUBLE_SLOPE",
            "BREAKOUT_TRACKER_V5",
            "CONTINUOUS_HIGH",
        }:
            raise ValueError(
                f"event {event.event_id} uses an unsupported source engine"
            )
        bar = bar_by_date.get(event.trade_date)
        if bar is None:
            raise ValueError(f"event {event.event_id} has no matching price bar")
        if not math.isclose(event.close, bar.close, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"event {event.event_id} close does not match price bar"
            )
        grouped.setdefault((event.trade_date, event.source_engine), []).append(
            event
        )

    width, height = 1180, 470
    left, right, top, bottom = 76, 28, 48, 405
    plot_width = width - left - right
    plot_height = bottom - top
    closes = [bar.close for bar in bars]
    low, high = min(closes), max(closes)
    price_span = high - low
    padding = price_span * 0.08 if price_span else max(abs(high) * 0.02, 1.0)
    price_min = low - padding
    price_max = high + padding
    scale_span = price_max - price_min
    x_by_date = {
        bar.trade_date: left + index / max(1, len(bars) - 1) * plot_width
        for index, bar in enumerate(bars)
    }

    def y(price: float) -> float:
        return top + (price_max - price) / scale_span * plot_height

    title_id = f"event-price-title-{safe_symbol}"
    desc_id = f"event-price-desc-{safe_symbol}"
    parts = [
        f'<svg id="event-price-chart-{safe_symbol}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{safe_symbol} 全部事件疊加收盤價圖</title>',
        f'<desc id="{desc_id}">白線為每日收盤價；綠色圓點與橘色三角形是七狀態及雙斜率事件，紫色菱形與藍色方形是輔助引擎事件。每個標記以細線連回事件日收盤價。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for step in range(6):
        price = price_max - scale_span * step / 5
        yy = top + plot_height * step / 5
        parts.extend(
            (
                f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#26324a"/>',
                f'<text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#9ba8bf">{escape(_number(price))}</text>',
            )
        )
    tick_indexes = sorted(
        {round((len(bars) - 1) * step / 5) for step in range(6)}
    )
    for index in tick_indexes:
        bar = bars[index]
        xx = x_by_date[bar.trade_date]
        parts.extend(
            (
                f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" stroke="#1e293b"/>',
                f'<text x="{xx:.1f}" y="{bottom+25}" text-anchor="middle" font-size="11" fill="#9ba8bf">{bar.trade_date.isoformat()}</text>',
            )
        )
    path = " ".join(
        f'{"M" if index == 0 else "L"}{x_by_date[bar.trade_date]:.1f},{y(bar.close):.1f}'
        for index, bar in enumerate(bars)
    )
    parts.append(
        f'<path d="{path}" fill="none" stroke="#f8fafc" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>'
    )
    for (trade_date, source_engine), grouped_events in sorted(grouped.items()):
        bar = bar_by_date[trade_date]
        xx = x_by_date[trade_date]
        anchor_y = y(bar.close)
        marker_specs = {
            "SEVEN_STATE_RADAR": (-18, "#2dd4bf"),
            "DOUBLE_SLOPE": (18, "#f59e0b"),
            "BREAKOUT_TRACKER_V5": (-8, "#a78bfa"),
            "CONTINUOUS_HIGH": (8, "#38bdf8"),
        }
        offset, color = marker_specs[source_engine]
        marker_y = anchor_y + offset
        details = " | ".join(
            f"{event.event_id} · {event.event_type} · {event.state} · {event.detail}"
            for event in grouped_events
        )
        title = escape(
            f"{trade_date.isoformat()} · 收盤 {_number(bar.close)} · "
            f"{source_engine} · {details}"
        )
        parts.append(
            f'<line x1="{xx:.1f}" y1="{anchor_y:.1f}" x2="{xx:.1f}" y2="{marker_y:.1f}" stroke="{color}" stroke-width="1"/>'
        )
        if source_engine == "SEVEN_STATE_RADAR":
            parts.append(
                f'<circle data-engine="SEVEN_STATE_RADAR" data-date="{trade_date.isoformat()}" data-event-count="{len(grouped_events)}" cx="{xx:.1f}" cy="{marker_y:.1f}" r="5" fill="#2dd4bf" stroke="#10182a"><title>{title}</title></circle>'
            )
        elif source_engine == "DOUBLE_SLOPE":
            parts.append(
                f'<path data-engine="DOUBLE_SLOPE" data-date="{trade_date.isoformat()}" data-event-count="{len(grouped_events)}" d="M {xx:.1f} {marker_y-5:.1f} L {xx-5:.1f} {marker_y+4:.1f} L {xx+5:.1f} {marker_y+4:.1f} Z" fill="#f59e0b"><title>{title}</title></path>'
            )
        elif source_engine == "BREAKOUT_TRACKER_V5":
            parts.append(
                f'<rect data-engine="BREAKOUT_TRACKER_V5" data-date="{trade_date.isoformat()}" data-event-count="{len(grouped_events)}" x="{xx-4.5:.1f}" y="{marker_y-4.5:.1f}" width="9" height="9" fill="#a78bfa" stroke="#10182a" stroke-width="1" transform="rotate(45 {xx:.1f} {marker_y:.1f})"><title>{title}</title></rect>'
            )
        else:
            parts.append(
                f'<rect data-engine="CONTINUOUS_HIGH" data-date="{trade_date.isoformat()}" data-event-count="{len(grouped_events)}" x="{xx-4:.1f}" y="{marker_y-4:.1f}" width="8" height="8" fill="#38bdf8" stroke="#10182a"><title>{title}</title></rect>'
            )
    parts.extend(
        (
            f'<text x="{left}" y="{height-12}" font-size="11" fill="#9ba8bf">{len(events)} 個事件 · {len(grouped)} 個日期／引擎標記 · TWSE 原始未還權收盤價 · 公司行動 UNVERIFIED</text>',
            "</svg>",
        )
    )
    return "".join(parts)


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
    row["ma20_slope_pct"] = _number(item.ma20_slope_pct)
    row["ma60_slope_pct"] = _number(item.ma60_slope_pct)
    row["distance_to_ma20_pct"] = _number(item.distance_to_ma20_pct)
    row["double_slope_prior_pct"] = _number(item.double_slope_prior_pct)
    row["double_slope_recent_pct"] = _number(item.double_slope_recent_pct)
    row["double_slope_z_score"] = _number(item.double_slope_z_score)
    row["new_high_windows"] = "|".join(str(value) for value in item.new_high_windows)
    row["risk_flags"] = "|".join(item.risk_flags)
    row["reason_codes"] = "|".join(item.reason_codes)
    row["cb_issue_names"] = "|".join(item.cb_issue_names)
    row["cb_data_as_of"] = (
        item.cb_data_as_of.isoformat() if item.cb_data_as_of else ""
    )
    return row


def _manifest(scan: WatchlistScan) -> dict[str, object]:
    cb_classification_hash = hashlib.sha256(
        stable_json_bytes(
            [
                {
                    "source_symbol": item.source_symbol,
                    "status": item.cb_issuer_status,
                    "current_issue_count": item.cb_current_issue_count,
                    "recent_delisted_count": item.cb_recent_delisted_count,
                    "issue_names": list(item.cb_issue_names),
                }
                for item in sorted(
                    scan.candidates, key=lambda candidate: candidate.source_symbol
                )
            ]
        )
    ).hexdigest()
    universe_identity_hash = hashlib.sha256(
        stable_json_bytes(
            [
                {
                    "source_symbol": item.source_symbol,
                    "company_name": item.company_name,
                }
                for item in sorted(
                    scan.candidates,
                    key=lambda candidate: candidate.source_symbol,
                )
            ]
        )
    ).hexdigest()
    identity = {
        "schema_version": "TWSTOCK-WATCHLIST-RADAR-004",
        "requested_start": scan.requested_start,
        "requested_end": scan.requested_end,
        "requested_symbols": list(scan.requested_symbols),
        "dataset_hashes": sorted(
            dataset.dataset_hash for dataset in scan.datasets
        ),
        "monitor_parameter_hash": scan.monitor_parameter_hash,
        "breakout_config_hash": scan.breakout_config_hash,
        "ma_parameter_hash": scan.ma_parameter_hash,
        "double_slope_parameter_hash": scan.double_slope_parameter_hash,
        "radar_parameter_hash": scan.radar_parameter_hash,
        "cb_source_status": scan.cb_source_status,
        "cb_data_as_of": (
            scan.cb_data_as_of.isoformat() if scan.cb_data_as_of else None
        ),
        "cb_classification_hash": cb_classification_hash,
        "universe_identity_hash": universe_identity_hash,
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
        "source_policy": "OFFICIAL_TWSE_PRICES_OPTIONAL_OFFICIAL_TPEX_CB_NO_FINMIND",
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
        "ma_parameter_version": scan.ma_parameter_version,
        "double_slope_parameter_version": scan.double_slope_parameter_version,
        "radar_parameter_version": scan.radar_parameter_version,
        "state_counts": {
            state.value: sum(
                item.scan_status == "OK" and item.market_state == state.value
                for item in scan.candidates
            )
            for state in RadarState
        },
        "counts": {
            "requested": len(scan.requested_symbols),
            "datasets_loaded": len(scan.datasets),
            "ranked": sum(item.rank is not None for item in scan.candidates),
            "events": len(scan.timeline),
            "current_cb_issuers": sum(
                item.cb_issuer_status == "CURRENT_CB" for item in scan.candidates
            ),
            "recently_delisted_cb_issuers": sum(
                item.cb_issuer_status == "RECENTLY_DELISTED_CB_OR_EB"
                for item in scan.candidates
            ),
            "upcoming_cb_issuers": sum(
                item.cb_issuer_status == "UPCOMING_CB"
                for item in scan.candidates
            ),
            **statuses,
        },
        "ranking_policy": {
            "method": "SEVEN_STATE_OBSERVATION_ORDER_NO_SCORE",
            "tier_order": [
                "TURNING_UP",
                "TREND_CONFIRMED",
                "PERSISTING",
                "BASE",
                "EXTENDED",
                "WEAKENING",
                "NOISE",
            ],
            "within_tier": [
                "target_transition_types_first",
                "other_today_transitions_second",
                "days_in_state_asc",
                "source_symbol_asc",
            ],
            "score": "NONE",
            "breakout_and_continuous_high_influence": "NONE_AUXILIARY_ONLY",
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
            "ranking_chart": "SEVEN_STATE_OBSERVATION_ORDER_NO_SCORE",
            "symbol_charts": "PRICE_EVENTS_CORE_MA_LONG_TERM_MA_AND_AUXILIARY_PRICE_VOLUME",
            "event_price_charts": "RADAR_AND_DOUBLE_SLOPE_PRIMARY_WITH_AUXILIARY_EVENTS_ON_CLOSE_LINE",
            "event_timeline_limit_in_html": _HTML_TIMELINE_LIMIT,
            "full_market_ranking_chart_limit": _FULL_MARKET_RANKING_CHART_LIMIT,
            "full_market_symbol_chart_limit": _FULL_MARKET_SYMBOL_CHART_LIMIT,
            "full_market_timeline_symbol_limit": _FULL_MARKET_TIMELINE_SYMBOL_LIMIT,
            "complete_event_timeline": "watchlist_timeline.csv",
            "price_basis": "RAW_OFFICIAL_DAILY_UNADJUSTED",
            "corporate_action_status": "UNVERIFIED",
            "investment_use": "PROHIBITED",
        },
        "warnings": [
            "Shadow Observation only; not for investment use.",
            "Corporate-action data is absent and marked UNVERIFIED.",
            "CB NOT_FOUND_CURRENT_OR_RECENT does not prove that the issuer has never issued a CB.",
            "TWSE prices are raw and unadjusted; ex-right, ex-dividend, and split discontinuities may create false events.",
            "Observation order is state-based research priority, not an expected-return or risk score.",
            "Double-slope and MA outputs are displayed independently and are not combined into a score.",
            "The seven-state thresholds are transparent research defaults and are not yet calibrated on Taiwan equities.",
        ],
    }


def _candidate_row(item: CandidateObservation) -> str:
    rank = str(item.rank) if item.rank is not None else "—"
    observed = item.observed_date.isoformat() if item.observed_date else "—"
    status_class = "" if item.scan_status == "OK" else "bad"
    reasons = " · ".join(item.reason_codes)
    cb_count = (
        item.cb_current_issue_count
        or item.cb_recent_delisted_count
        or len(item.cb_issue_names)
    )
    cb_names = ", ".join(item.cb_issue_names) or "—"
    state_color = _STATE_COLORS.get(item.market_state, "#94a3b8")
    state_label = _STATE_LABELS.get(item.market_state, item.market_state)
    transition = item.market_state_transition or "—"
    auxiliary = f"{item.breakout_state} / {item.high_stage}"
    slopes = f"{_pct(item.ma20_slope_pct)} / {_pct(item.ma60_slope_pct)}"
    return f"""<tr>
<td class="rank">{escape(rank)}</td><td>{escape(item.symbol)}<br><span class="muted">{escape(item.company_name or "—")}</span></td>
<td class="{status_class}">{escape(item.scan_status)}<br><span class="muted">{escape(observed)}</span></td>
<td><span class="pill" style="--state:{state_color}">{escape(state_label)}</span></td>
<td>{item.market_state_days}</td><td>{escape(transition)}</td>
<td>{escape(item.ma_state)}</td><td>{escape(item.double_slope_state)}</td>
<td>{escape(item.method_relationship)}</td><td>{escape(item.ma_long_term_context)}</td>
<td>{escape(slopes)}</td><td>{escape(_pct(item.distance_to_ma20_pct))}</td>
<td>{escape(item.cb_issuer_status)}</td><td>{cb_count}</td><td>{escape(cb_names)}</td>
<td>{escape(auxiliary)}</td><td class="reasons">{escape(reasons)}</td>
<td class="bad">{escape(item.corporate_action_status)}</td></tr>"""


def _timeline_row(item: TimelineEvent) -> str:
    return f"""<tr><td>{item.trade_date.isoformat()}</td><td>{escape(item.symbol)}</td>
<td>{escape(item.source_engine)}</td><td>{escape(item.event_type)}</td>
<td>{escape(item.state)}</td><td>{escape(item.detail)}</td>
<td>{escape(_number(item.close))}</td><td><code>{escape(item.event_id)}</code></td></tr>"""


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.10g}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"
