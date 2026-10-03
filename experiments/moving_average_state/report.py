from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from twstock_data.models import MarketBar
from twstock_data.normalization import stable_json_bytes

from .models import (
    LongTermContext,
    MAStateEvent,
    MAStateObservation,
    MAStateResult,
    TrendState,
)


_STATE_LABELS = {
    TrendState.UNCLEAR: "方向不明",
    TrendState.BASE: "整理／築底",
    TrendState.TURNING_UP: "剛轉多",
    TrendState.UPTREND: "上升趨勢",
    TrendState.TURNING_DOWN: "剛轉弱",
    TrendState.DOWNTREND: "下降趨勢",
}
_STATE_COLORS = {
    TrendState.UNCLEAR: "#94a3b8",
    TrendState.BASE: "#fbbf24",
    TrendState.TURNING_UP: "#2dd4bf",
    TrendState.UPTREND: "#22c55e",
    TrendState.TURNING_DOWN: "#fb923c",
    TrendState.DOWNTREND: "#fb7185",
}
_STATE_EXPLANATIONS = {
    TrendState.UNCLEAR: "目前訊號互相矛盾，不能歸入其他狀態。",
    TrendState.BASE: "MA20、MA60接近水平，四條均線彼此靠近；尚不知道最後向上或向下。",
    TrendState.TURNING_UP: "股價站上MA20、MA5高於MA10且MA20向上，但長期趨勢尚未完整確認。",
    TrendState.UPTREND: "股價與四條均線完整多頭排列，MA20及MA60均明顯向上。",
    TrendState.TURNING_DOWN: "股價跌到MA20下方、MA5低於MA10且MA20向下，但空頭尚未完整確認。",
    TrendState.DOWNTREND: "股價與四條均線完整空頭排列，MA20及MA60均明顯向下。",
}
_CONTEXT_LABELS = {
    LongTermContext.INSUFFICIENT_HISTORY: "長期資料不足",
    LongTermContext.LONG_TERM_BULL: "長期多頭",
    LongTermContext.LONG_TERM_REPAIR: "長期修復",
    LongTermContext.LONG_TERM_BOTTOMING: "長期底部翻轉",
    LongTermContext.LONG_TERM_BEAR_RALLY: "長期空頭中的反彈",
    LongTermContext.LONG_TERM_BEAR: "長期空頭",
    LongTermContext.LONG_TERM_MIXED: "長期訊號混合",
}
_CONTEXT_COLORS = {
    LongTermContext.INSUFFICIENT_HISTORY: "#94a3b8",
    LongTermContext.LONG_TERM_BULL: "#22c55e",
    LongTermContext.LONG_TERM_REPAIR: "#2dd4bf",
    LongTermContext.LONG_TERM_BOTTOMING: "#60a5fa",
    LongTermContext.LONG_TERM_BEAR_RALLY: "#fb923c",
    LongTermContext.LONG_TERM_BEAR: "#fb7185",
    LongTermContext.LONG_TERM_MIXED: "#c084fc",
}
_CONTEXT_EXPLANATIONS = {
    LongTermContext.INSUFFICIENT_HISTORY: "尚未累積MA240與斜率所需的完整歷史，不能判斷長期背景。",
    LongTermContext.LONG_TERM_BULL: "價格高於MA120與MA240，MA120高於MA240，且兩者方向向上。",
    LongTermContext.LONG_TERM_REPAIR: "價格已站上MA120，但尚未形成完整長期多頭排列。",
    LongTermContext.LONG_TERM_BOTTOMING: "MA120已明顯向上，而MA240接近平坦；可能處於大型底部修復階段。",
    LongTermContext.LONG_TERM_BEAR_RALLY: "短中期正在轉強，但仍低於下降中的MA120，且MA240也向下。",
    LongTermContext.LONG_TERM_BEAR: "價格低於MA120與MA240，MA120低於MA240，且兩者方向向下。",
    LongTermContext.LONG_TERM_MIXED: "長期價格位置、均線排列與斜率彼此不一致。",
}
_EVIDENCE_LABELS = {
    "PRICE_AND_MAS_FULL_BULLISH_ORDER": "股價、MA5、MA10、MA20、MA60完整由高到低排列",
    "PRICE_AND_MAS_FULL_BEARISH_ORDER": "股價、MA5、MA10、MA20、MA60完整由低到高排列",
    "MA20_SLOPE_POSITIVE": "MA20正在上升",
    "MA60_SLOPE_POSITIVE": "MA60正在上升",
    "MA20_SLOPE_NEGATIVE": "MA20正在下降",
    "MA60_SLOPE_NEGATIVE": "MA60正在下降",
    "MA20_AND_MA60_APPROXIMATELY_FLAT": "MA20與MA60接近水平",
    "MOVING_AVERAGES_COMPRESSED": "四條均線彼此靠近",
    "PRICE_NEAR_MA20": "收盤價仍位於MA20附近",
    "BASE_DOES_NOT_DETERMINE_BREAK_DIRECTION": "整理本身不能判定下一步一定向上",
    "CLOSE_ABOVE_MA20": "收盤價位於MA20之上",
    "MA5_ABOVE_MA10": "MA5高於MA10",
    "FULL_BULLISH_ALIGNMENT_NOT_CONFIRMED": "尚未形成完整多頭排列",
    "MA60_SLOPE_NOT_POSITIVE": "MA60尚未轉為向上",
    "CLOSE_BELOW_MA20": "收盤價位於MA20之下",
    "MA5_BELOW_MA10": "MA5低於MA10",
    "FULL_BEARISH_ALIGNMENT_NOT_CONFIRMED": "尚未形成完整空頭排列",
    "MA60_SLOPE_STILL_POSITIVE": "MA60仍然向上，長期趨勢尚未轉空",
    "NO_SINGLE_BASELINE_RULE_DOMINATES": "目前沒有一套均線條件足以主導判斷",
    "NOT_FULL_BULLISH_ALIGNMENT": "不是完整多頭排列",
    "NOT_FULL_BEARISH_ALIGNMENT": "不是完整空頭排列",
    "NOT_BASE_COMPRESSION": "不符合整理區的均線收斂條件",
    "STATE_NOT_INTERPRETABLE_YET": "歷史資料不足，暫時不能解讀",
    "LONG_TERM_CONTEXT_NOT_INTERPRETABLE_YET": "長期歷史資料不足，暫時不能解讀",
    "PRICE_ABOVE_MA120_ABOVE_MA240": "收盤價高於MA120，且MA120高於MA240",
    "PRICE_BELOW_MA120_BELOW_MA240": "收盤價低於MA120，且MA120低於MA240",
    "PRICE_ABOVE_MA120": "收盤價已站上MA120",
    "MA120_SLOPE_POSITIVE": "MA120正在上升",
    "MA120_SLOPE_NEGATIVE": "MA120正在下降",
    "MA240_SLOPE_POSITIVE": "MA240正在上升",
    "MA240_SLOPE_NEGATIVE": "MA240正在下降",
    "MA240_APPROXIMATELY_FLAT": "MA240接近平坦",
    "LONG_TERM_BULLISH_ALIGNMENT_NOT_CONFIRMED": "尚未形成完整長期多頭排列",
    "EARLY_UP_STATE_BELOW_MA120": "短中期轉強，但收盤價仍低於MA120",
    "RALLY_MAY_NOT_BE_LONG_TERM_REVERSAL": "這次反彈尚未證明是長期反轉",
    "LONG_TERM_SIGNALS_MIXED": "長期價格位置、排列與斜率互相矛盾",
    "NO_DOMINANT_LONG_TERM_CONTEXT": "目前沒有明確的長期背景",
    "MA200_AND_MA240_PRICE_TEST_DISAGREE": "MA200與MA240對價格位置的判斷不同",
    "MA200_AND_MA240_SLOPE_DIRECTION_DISAGREE": "MA200與MA240的斜率方向不同",
}


def write_outputs(
    results: Sequence[MAStateResult],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    output_dir: Path,
    *,
    source_manifests: Mapping[str, Mapping[str, object]],
) -> None:
    ordered = tuple(sorted(results, key=lambda item: item.symbol))
    _validate_inputs(ordered, bars_by_symbol, source_manifests)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_latest_csv(output_dir / "ma_state_latest.csv", ordered)
    _write_timeline_csv(output_dir / "ma_state_timeline.csv", ordered)
    manifest = _manifest(ordered, source_manifests)
    (output_dir / "ma_state_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "ma_state_report.html").write_text(
        render_html_report(ordered, bars_by_symbol, manifest=manifest),
        encoding="utf-8",
    )


def render_core_ma_svg(
    result: MAStateResult, bars: Sequence[MarketBar]
) -> str:
    """Render close with MA5/10/20/60 and exact MA state events."""

    _validate_chart_identity(result, bars)
    return _price_ma_svg(result, bars)


def render_long_term_ma_svg(
    result: MAStateResult, bars: Sequence[MarketBar]
) -> str:
    """Render close with MA60/120/200/240 as long-term context."""

    _validate_chart_identity(result, bars)
    return _long_term_ma_svg(result, bars)


def _validate_chart_identity(
    result: MAStateResult, bars: Sequence[MarketBar]
) -> None:
    if not bars:
        raise ValueError("bars must not be empty")
    if any(bar.symbol != result.symbol for bar in bars):
        raise ValueError("moving-average chart bars use a different symbol")
    if len(result.observations) != len(bars):
        raise ValueError("moving-average chart observation count mismatch")
    for observation, bar in zip(result.observations, bars):
        if observation.trade_date != bar.trade_date:
            raise ValueError("moving-average chart trade date mismatch")
        if not math.isclose(
            observation.close, bar.close, rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError("moving-average chart close mismatch")


def render_html_report(
    results: Sequence[MAStateResult],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    ordered = tuple(sorted(results, key=lambda item: item.symbol))
    if not ordered:
        raise ValueError("results must not be empty")
    source_manifests = {
        item.symbol: {
            "selected_source": "TWSE",
            "price_basis": "RAW_OFFICIAL_DAILY",
            "adjustment_policy": "RAW_UNADJUSTED",
            "corporate_actions_applied": False,
            "dataset_hash": "TEST_ONLY",
        }
        for item in ordered
    }
    _validate_inputs(ordered, bars_by_symbol, source_manifests)
    manifest = manifest or _manifest(ordered, source_manifests)
    latest_rows = "\n".join(_latest_row(item) for item in ordered)
    all_events = tuple(
        sorted(
            (event for item in ordered for event in item.events),
            key=lambda event: (event.trade_date, event.symbol, event.event_id),
            reverse=True,
        )
    )
    timeline_rows = "\n".join(_event_row(event) for event in all_events)
    charts = "\n".join(
        _symbol_section(item, bars_by_symbol[item.symbol]) for item in ordered
    )
    state_counts = {
        state: sum(item.observations[-1].state is state for item in ordered)
        for state in TrendState
    }
    count_cards = "".join(
        f'<div class="card"><b>{escape(_STATE_LABELS[state])}</b><span>{count}</span></div>'
        for state, count in state_counts.items()
    )
    glossary_rows = "".join(
        f'<tr><td><span class="pill" style="--state:{_STATE_COLORS[state]}">{state.value} · {escape(_STATE_LABELS[state])}</span></td><td class="wrap">{escape(_STATE_EXPLANATIONS[state])}</td></tr>'
        for state in TrendState
    )
    context_glossary_rows = "".join(
        f'<tr><td><span class="pill" style="--state:{_CONTEXT_COLORS[context]}">{context.value} · {escape(_CONTEXT_LABELS[context])}</span></td><td class="wrap">{escape(_CONTEXT_EXPLANATIONS[context])}</td></tr>'
        for context in LongTermContext
    )
    long_term_rows = "\n".join(_long_term_row(item) for item in ordered)
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>均線趨勢狀態基準 v0.2</title>
<style>
:root{{color-scheme:dark;--bg:#0b1020;--panel:#131a2c;--line:#2a3550;--text:#e8edf7;--muted:#9ba8bf;--danger:#fb7185}}
*{{box-sizing:border-box}}body{{margin:0;padding:28px;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1500px;margin:auto}}h1,h2,h3{{margin:0 0 12px}}h2{{margin-top:28px;font-size:19px}}h3{{margin-top:20px}}.warning{{border:1px solid var(--danger);background:#351523;padding:16px;border-radius:10px;color:#ffd8df;font-weight:700}}.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}}.card b{{display:block;color:var(--muted);font-size:12px}}.card span{{font-size:22px}}.table-wrap,.chart-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}.chart-wrap{{padding:12px}}.chart-wrap svg{{display:block;min-width:960px;width:100%;height:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#1a2338;color:var(--muted);font-size:12px}}td.wrap{{white-space:normal;min-width:300px}}.pill{{display:inline-block;padding:3px 8px;border-radius:999px;background:color-mix(in srgb,var(--state) 25%,#111827);color:var(--state);font-weight:800}}.muted{{color:var(--muted)}}.bad{{color:var(--danger);font-weight:800}}code{{color:#c4b5fd}}footer{{margin-top:28px;color:var(--muted)}}
</style></head><body><main>
<h1>均線趨勢狀態基準 v0.2</h1>
<div class="warning">SHADOW OBSERVATION ONLY · 不作投資使用 · Investment use: PROHIBITED<br>公司行動：UNVERIFIED；TWSE 官方原始未還權價格。此報表只有狀態描述，沒有分數、勝率或買賣建議。</div>
<div class="summary">{count_cards}</div>
<p class="muted">方法隔離：核心六狀態只使用收盤價與 MA5／MA10／MA20／MA60；MA120／MA240只描述長期背景，MA200只作國際慣例比較，不會否決早期候選。不使用 Breakout、Continuous High、成交量、相對強度、BOCPD 或 HMM。</p>
<p class="muted">暫定基準參數：以最近5個交易日衡量均線方向；整理狀態要求MA20／MA60斜率變動不超過0.5%，且四條核心均線最大距離不超過3%；長期平坦容許值為0.2%。這些只是公開、未最佳化的比較基準，不是已驗證門檻。</p>
<h2>六個互斥狀態怎麼看</h2>
<div class="table-wrap"><table><thead><tr><th>狀態</th><th>白話意義</th></tr></thead><tbody>{glossary_rows}</tbody></table></div>
<h2>長期背景怎麼看</h2>
<p class="muted">長期背景與核心狀態是兩個不同問題。例如一檔股票可以同時是「剛轉多」及「長期空頭中的反彈」。</p>
<div class="table-wrap"><table><thead><tr><th>長期背景</th><th>白話意義</th></tr></thead><tbody>{context_glossary_rows}</tbody></table></div>
<h2>目前狀態（只按股票代碼排列）</h2>
<div class="table-wrap"><table><thead><tr><th>股票</th><th>觀察日</th><th>目前狀態開始日</th><th>狀態</th><th>收盤</th><th>MA5／10／20／60</th><th>MA20斜率</th><th>MA60斜率</th><th>距MA20</th><th>支持證據</th><th>反對證據</th><th>資料</th></tr></thead><tbody>{latest_rows}</tbody></table></div>
<h2>目前長期背景（不參與核心狀態判定）</h2>
<div class="table-wrap"><table><thead><tr><th>股票</th><th>長期背景</th><th>MA120／200／240</th><th>MA120／200／240斜率</th><th>距MA120／200／240</th><th>支持證據</th><th>風險與分歧</th></tr></thead><tbody>{long_term_rows}</tbody></table></div>
<h2>狀態轉換時間線（新到舊）</h2>
<div class="table-wrap"><table><thead><tr><th>日期</th><th>股票</th><th>前狀態</th><th>新狀態</th><th>收盤</th><th>Event ID</th></tr></thead><tbody>{timeline_rows}</tbody></table></div>
<h2>每檔股價、核心狀態與長期背景圖</h2>
<p class="muted">第一張圖顯示收盤與MA5／10／20／60，圓點是核心狀態改變；第二張圖顯示收盤與MA60／120／200／240，用來比較台股年線MA240和國際常用MA200。所有距離只顯示原始診斷值，尚未定義過度延伸門檻。</p>
{charts}
<footer>Manifest ID: <code>{escape(str(manifest["report_id"]))}</code> · Schema: TWSTOCK-MA-STATE-REPORT-002</footer>
</main></body></html>'''


def _latest_row(result: MAStateResult) -> str:
    item = result.observations[-1]
    color = _STATE_COLORS[item.state]
    averages = " / ".join(
        _number(value) for value in (item.ma_fast, item.ma_short, item.ma_medium, item.ma_long)
    )
    return (
        f"<tr><td><code>{escape(item.symbol)}</code></td>"
        f"<td>{item.trade_date.isoformat()}</td>"
        f"<td>{_state_start_date(result)}</td>"
        f'<td><span class="pill" style="--state:{color}">{escape(item.state.value)} · {escape(_STATE_LABELS[item.state])}</span></td>'
        f"<td>{_number(item.close)}</td><td>{escape(averages)}</td>"
        f"<td>{_pct(item.medium_slope_pct)}</td><td>{_pct(item.long_slope_pct)}</td>"
        f"<td>{_pct(item.distance_to_medium_ma_pct)}</td>"
        f'<td class="wrap">{_codes(item.support_evidence)}</td>'
        f'<td class="wrap">{_codes(item.contrary_evidence)}</td>'
        '<td><span class="bad">UNVERIFIED</span></td></tr>'
    )


def _long_term_row(result: MAStateResult) -> str:
    item = result.observations[-1]
    context = item.long_term_context
    averages = " / ".join(
        _number(value)
        for value in (item.ma_half_year, item.ma_global_long, item.ma_annual)
    )
    slopes = " / ".join(
        _pct(value)
        for value in (
            item.half_year_slope_pct,
            item.global_long_slope_pct,
            item.annual_slope_pct,
        )
    )
    distances = " / ".join(
        _pct(value)
        for value in (
            item.distance_to_half_year_ma_pct,
            item.distance_to_global_long_ma_pct,
            item.distance_to_annual_ma_pct,
        )
    )
    return (
        f"<tr><td><code>{escape(item.symbol)}</code></td>"
        f'<td><span class="pill" style="--state:{_CONTEXT_COLORS[context]}">'
        f"{escape(context.value)} · {escape(_CONTEXT_LABELS[context])}</span></td>"
        f"<td>{escape(averages)}</td><td>{escape(slopes)}</td>"
        f"<td>{escape(distances)}</td>"
        f'<td class="wrap">{_codes(item.long_term_support_evidence)}</td>'
        f'<td class="wrap">{_codes(item.long_term_contrary_evidence)}</td></tr>'
    )


def _event_row(event: MAStateEvent) -> str:
    previous = event.previous_state.value if event.previous_state else "NONE"
    color = _STATE_COLORS[event.current_state]
    return (
        f"<tr><td>{event.trade_date.isoformat()}</td><td><code>{escape(event.symbol)}</code></td>"
        f"<td>{escape(previous)}</td>"
        f'<td><span class="pill" style="--state:{color}">{escape(event.current_state.value)}</span></td>'
        f"<td>{_number(event.close)}</td><td><code>{escape(event.event_id)}</code></td></tr>"
    )


def _symbol_section(result: MAStateResult, bars: Sequence[MarketBar]) -> str:
    latest = result.observations[-1]
    return (
        f'<section id="symbol-{escape(result.symbol)}"><h3>{escape(result.symbol)} · '
        f'{escape(latest.state.value)} · {escape(_STATE_LABELS[latest.state])}</h3>'
        f'<p class="muted">觀察日 {latest.trade_date.isoformat()} · 目前狀態開始日 {_state_start_date(result)} · 收盤 {_number(latest.close)} · '
        f'距MA20 {_pct(latest.distance_to_medium_ma_pct)} · 長期背景 '
        f'<span class="pill" style="--state:{_CONTEXT_COLORS[latest.long_term_context]}">'
        f'{escape(_CONTEXT_LABELS[latest.long_term_context])}</span> · 公司行動 <span class="bad">UNVERIFIED</span></p>'
        f'<div class="chart-wrap">{_price_ma_svg(result, bars)}</div>'
        f'<div class="chart-wrap" style="margin-top:12px">{_long_term_ma_svg(result, bars)}</div></section>'
    )


def _price_ma_svg(result: MAStateResult, bars: Sequence[MarketBar]) -> str:
    observations = result.observations
    if len(observations) != len(bars):
        raise ValueError("result observations do not match chart bars")
    for observation, bar in zip(observations, bars, strict=True):
        if observation.symbol != bar.symbol or observation.trade_date != bar.trade_date:
            raise ValueError("result identity does not match chart bars")
        if not math.isclose(observation.close, bar.close, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("result close does not match chart bars")
    start = max(0, len(bars) - 260)
    visible_bars = bars[start:]
    visible = observations[start:]
    width, height = 1180, 500
    left, right, top, bottom = 76, 28, 48, 430
    plot_width, plot_height = width - left - right, bottom - top
    series_values = [bar.close for bar in visible_bars]
    for item in visible:
        series_values.extend(
            value for value in (item.ma_fast, item.ma_short, item.ma_medium, item.ma_long) if value is not None
        )
    low, high = min(series_values), max(series_values)
    padding = (high - low) * 0.08 if high != low else max(abs(high) * 0.02, 1.0)
    price_min, price_max = low - padding, high + padding
    span = price_max - price_min

    def x(index: int) -> float:
        return left + index / max(1, len(visible_bars) - 1) * plot_width

    def y(value: float) -> float:
        return top + (price_max - value) / span * plot_height

    title_id = f"ma-state-title-{escape(result.symbol)}"
    desc_id = f"ma-state-desc-{escape(result.symbol)}"
    parts = [
        f'<svg id="ma-state-chart-{escape(result.symbol)}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{escape(result.symbol)} 股價與均線狀態圖</title>',
        f'<desc id="{desc_id}">收盤價、MA5、MA10、MA20、MA60及全部狀態切換事件。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for step in range(6):
        value = price_max - span * step / 5
        yy = top + plot_height * step / 5
        parts.extend((
            f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#26324a"/>',
            f'<text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#9ba8bf">{escape(_number(value))}</text>',
        ))
    for step in range(6):
        index = round((len(visible_bars) - 1) * step / 5)
        xx = x(index)
        parts.extend((
            f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" stroke="#1e293b"/>',
            f'<text x="{xx:.1f}" y="{bottom+25}" text-anchor="middle" font-size="11" fill="#9ba8bf">{visible_bars[index].trade_date.isoformat()}</text>',
        ))
    series = (
        ("close", "#f8fafc", 2.0),
        ("ma_fast", "#38bdf8", 1.3),
        ("ma_short", "#a78bfa", 1.3),
        ("ma_medium", "#fbbf24", 1.6),
        ("ma_long", "#f472b6", 1.6),
    )
    for name, color, stroke_width in series:
        points: list[str] = []
        for index, item in enumerate(visible):
            value = item.close if name == "close" else getattr(item, name)
            if value is None:
                continue
            points.append(f"{x(index):.1f},{y(value):.1f}")
        if points:
            parts.append(
                f'<polyline data-series="{name}" points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
    visible_dates = {bar.trade_date: index for index, bar in enumerate(visible_bars)}
    for event in result.events:
        index = visible_dates.get(event.trade_date)
        if index is None:
            continue
        xx, yy = x(index), y(event.close)
        color = _STATE_COLORS[event.current_state]
        previous = event.previous_state.value if event.previous_state else "NONE"
        title = escape(
            f"{event.trade_date.isoformat()} · {previous} → {event.current_state.value} · 收盤 {_number(event.close)}"
        )
        parts.append(
            f'<circle data-state="{event.current_state.value}" data-date="{event.trade_date.isoformat()}" cx="{xx:.1f}" cy="{yy:.1f}" r="5" fill="{color}" stroke="#10182a" stroke-width="1.5"><title>{title}</title></circle>'
        )
    legend = (("收盤", "#f8fafc"), ("MA5", "#38bdf8"), ("MA10", "#a78bfa"), ("MA20", "#fbbf24"), ("MA60", "#f472b6"))
    for index, (label, color) in enumerate(legend):
        xx = left + index * 115
        parts.extend((
            f'<line x1="{xx}" y1="22" x2="{xx+24}" y2="22" stroke="{color}" stroke-width="3"/>',
            f'<text x="{xx+30}" y="26" font-size="11" fill="#cbd5e1">{label}</text>',
        ))
    parts.append("</svg>")
    return "".join(parts)


def _long_term_ma_svg(result: MAStateResult, bars: Sequence[MarketBar]) -> str:
    observations = result.observations
    if len(observations) != len(bars):
        raise ValueError("result observations do not match long-term chart bars")
    start = max(0, len(bars) - 320)
    visible_bars = bars[start:]
    visible = observations[start:]
    width, height = 1180, 500
    left, right, top, bottom = 76, 28, 48, 430
    plot_width, plot_height = width - left - right, bottom - top
    series_values = [bar.close for bar in visible_bars]
    for item in visible:
        series_values.extend(
            value
            for value in (
                item.ma_long,
                item.ma_half_year,
                item.ma_global_long,
                item.ma_annual,
            )
            if value is not None
        )
    low, high = min(series_values), max(series_values)
    padding = (high - low) * 0.08 if high != low else max(abs(high) * 0.02, 1.0)
    price_min, price_max = low - padding, high + padding
    span = price_max - price_min

    def x(index: int) -> float:
        return left + index / max(1, len(visible_bars) - 1) * plot_width

    def y(value: float) -> float:
        return top + (price_max - value) / span * plot_height

    title_id = f"ma-long-title-{escape(result.symbol)}"
    desc_id = f"ma-long-desc-{escape(result.symbol)}"
    parts = [
        f'<svg id="ma-long-chart-{escape(result.symbol)}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{escape(result.symbol)} 長期均線背景圖</title>',
        f'<desc id="{desc_id}">收盤價、MA60、MA120、MA200與MA240；MA200只作比較，MA120與MA240用於長期背景。</desc>',
        f'<rect width="{width}" height="{height}" rx="12" fill="#10182a"/>',
    ]
    for step in range(6):
        value = price_max - span * step / 5
        yy = top + plot_height * step / 5
        parts.extend((
            f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#26324a"/>',
            f'<text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#9ba8bf">{escape(_number(value))}</text>',
        ))
    for step in range(6):
        index = round((len(visible_bars) - 1) * step / 5)
        xx = x(index)
        parts.extend((
            f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" stroke="#1e293b"/>',
            f'<text x="{xx:.1f}" y="{bottom+25}" text-anchor="middle" font-size="11" fill="#9ba8bf">{visible_bars[index].trade_date.isoformat()}</text>',
        ))
    series = (
        ("close", "#f8fafc", 2.0),
        ("ma_long", "#f472b6", 1.4),
        ("ma_half_year", "#2dd4bf", 1.7),
        ("ma_global_long", "#fb923c", 1.7),
        ("ma_annual", "#ef4444", 1.9),
    )
    for name, color, stroke_width in series:
        points: list[str] = []
        for index, item in enumerate(visible):
            value = item.close if name == "close" else getattr(item, name)
            if value is not None:
                points.append(f"{x(index):.1f},{y(value):.1f}")
        if points:
            parts.append(
                f'<polyline data-series="{name}" points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
    legend = (
        ("收盤", "#f8fafc"),
        ("MA60", "#f472b6"),
        ("MA120", "#2dd4bf"),
        ("MA200（比較）", "#fb923c"),
        ("MA240（台股年線）", "#ef4444"),
    )
    legend_offsets = (0, 105, 210, 330, 485)
    for offset, (label, color) in zip(legend_offsets, legend, strict=True):
        xx = left + offset
        parts.extend((
            f'<line x1="{xx}" y1="22" x2="{xx+24}" y2="22" stroke="{color}" stroke-width="3"/>',
            f'<text x="{xx+30}" y="26" font-size="11" fill="#cbd5e1">{label}</text>',
        ))
    parts.append("</svg>")
    return "".join(parts)


def _write_latest_csv(path: Path, results: Sequence[MAStateResult]) -> None:
    fields = (
        "symbol", "trade_date", "state_start_date", "state", "close", "ma_fast", "ma_short",
        "ma_medium", "ma_long", "ma_half_year", "ma_global_long", "ma_annual",
        "medium_slope_pct", "long_slope_pct", "half_year_slope_pct",
        "global_long_slope_pct", "annual_slope_pct", "ma_spread_pct",
        "distance_to_medium_ma_pct", "distance_to_half_year_ma_pct",
        "distance_to_global_long_ma_pct", "distance_to_annual_ma_pct",
        "long_term_context", "long_term_support_evidence",
        "long_term_contrary_evidence", "structural_labels",
        "support_evidence", "contrary_evidence", "corporate_action_status",
        "investment_use",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            item = result.observations[-1]
            row = asdict(item)
            row["trade_date"] = item.trade_date.isoformat()
            row["state_start_date"] = _state_start_date(result)
            row["state"] = item.state.value
            row["long_term_context"] = item.long_term_context.value
            for name in (
                "long_term_support_evidence",
                "long_term_contrary_evidence",
                "structural_labels",
                "support_evidence",
                "contrary_evidence",
            ):
                row[name] = "|".join(row[name])
            row["corporate_action_status"] = result.corporate_action_status
            row["investment_use"] = result.investment_use
            writer.writerow(row)


def _write_timeline_csv(path: Path, results: Sequence[MAStateResult]) -> None:
    fields = ("event_id", "symbol", "trade_date", "previous_state", "current_state", "close")
    events = sorted(
        (event for result in results for event in result.events),
        key=lambda event: (event.trade_date, event.symbol, event.event_id),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in events:
            writer.writerow({
                "event_id": event.event_id,
                "symbol": event.symbol,
                "trade_date": event.trade_date.isoformat(),
                "previous_state": event.previous_state.value if event.previous_state else "",
                "current_state": event.current_state.value,
                "close": event.close,
            })


def _manifest(
    results: Sequence[MAStateResult],
    source_manifests: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    parameter_versions = {item.parameter_version for item in results}
    parameter_hashes = {item.parameter_hash for item in results}
    if len(parameter_versions) != 1 or len(parameter_hashes) != 1:
        raise ValueError("all results must use one parameter identity")
    payload = {
        "schema_version": "TWSTOCK-MA-STATE-REPORT-002",
        "method": "CLASSIC_MOVING_AVERAGE_STATE_WITH_LONG_TERM_CONTEXT",
        "parameter_version": next(iter(parameter_versions)),
        "parameter_hash": next(iter(parameter_hashes)),
        "symbols": [item.symbol for item in results],
        "dataset_hashes": {
            symbol: manifest["dataset_hash"] for symbol, manifest in sorted(source_manifests.items())
        },
        "outputs": ["ma_state_latest.csv", "ma_state_timeline.csv", "ma_state_manifest.json", "ma_state_report.html"],
        "ranking": "NONE",
        "score": "NONE",
        "core_state_windows": [5, 10, 20, 60],
        "long_term_context_windows": [120, 240],
        "comparison_only_windows": [200],
        "long_term_context_is_hard_filter": False,
        "corporate_action_status": "UNVERIFIED",
        "investment_use": "PROHIBITED",
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
    }
    report_id = hashlib.sha256(stable_json_bytes(payload)).hexdigest()
    return {**payload, "report_id": report_id}


def _validate_inputs(
    results: Sequence[MAStateResult],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    source_manifests: Mapping[str, Mapping[str, object]],
) -> None:
    if not results:
        raise ValueError("results must not be empty")
    symbols = [item.symbol for item in results]
    if len(symbols) != len(set(symbols)):
        raise ValueError("results contain duplicate symbols")
    if set(symbols) != set(bars_by_symbol) or set(symbols) != set(source_manifests):
        raise ValueError("result, bar, and manifest symbols must match exactly")
    for result in results:
        bars = tuple(bars_by_symbol[result.symbol])
        if not bars or len(bars) != len(result.observations):
            raise ValueError("result observations do not match source bars")
        manifest = source_manifests[result.symbol]
        if manifest.get("selected_source") != "TWSE":
            raise ValueError("moving-average baseline requires TWSE source")
        if manifest.get("price_basis") != "RAW_OFFICIAL_DAILY":
            raise ValueError("moving-average baseline requires official raw daily prices")
        if manifest.get("adjustment_policy") != "RAW_UNADJUSTED":
            raise ValueError("moving-average baseline requires raw unadjusted prices")
        if manifest.get("corporate_actions_applied") is not False:
            raise ValueError("corporate-action application must remain explicitly false")
        if not isinstance(manifest.get("dataset_hash"), str) or not manifest["dataset_hash"]:
            raise ValueError("source manifest must contain dataset_hash")


def _codes(values: Sequence[str]) -> str:
    rendered = []
    for value in values:
        label = value
        if value.startswith("INSUFFICIENT_HISTORY:NEED_"):
            count = value.removeprefix("INSUFFICIENT_HISTORY:NEED_").removesuffix("_BARS")
            label = f"歷史資料不足，需要至少{count}個交易日"
        elif value.startswith("INSUFFICIENT_LONG_HISTORY:NEED_"):
            count = value.removeprefix("INSUFFICIENT_LONG_HISTORY:NEED_").removesuffix("_BARS")
            label = f"長期背景資料不足，需要至少{count}個交易日"
        else:
            label = _EVIDENCE_LABELS.get(value, value)
        rendered.append(f"{escape(label)}<br><code>{escape(value)}</code>")
    return "<br>".join(rendered) or "—"


def _state_start_date(result: MAStateResult) -> str:
    latest_state = result.observations[-1].state
    for event in reversed(result.events):
        if event.current_state is latest_state:
            return event.trade_date.isoformat()
    raise ValueError("result has no event for latest state")


def _number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"
