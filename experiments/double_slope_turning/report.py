from __future__ import annotations

import csv
from dataclasses import asdict
from html import escape
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from experiments.moving_average_state import MAStateResult
from twstock_data.models import MarketBar
from twstock_data.normalization import stable_json_bytes

from .comparison import ComparisonResult, EventOutcome
from .models import DoubleSlopeResult, SlopeState


_STATE_LABELS = {
    SlopeState.INSUFFICIENT_HISTORY: "資料不足",
    SlopeState.FLAT: "近期斜率近乎水平",
    SlopeState.RISING: "近期斜率向上",
    SlopeState.FALLING: "近期斜率向下",
    SlopeState.TURNING_UP: "雙斜率確認轉多",
    SlopeState.TURNING_DOWN: "雙斜率確認轉空",
}
_STATE_COLORS = {
    SlopeState.INSUFFICIENT_HISTORY: "#94a3b8",
    SlopeState.FLAT: "#fbbf24",
    SlopeState.RISING: "#22c55e",
    SlopeState.FALLING: "#fb7185",
    SlopeState.TURNING_UP: "#38bdf8",
    SlopeState.TURNING_DOWN: "#f97316",
}
_EVIDENCE_LABELS = {
    "SLOPE_DIFFERENCE_NOT_INTERPRETABLE_YET": "歷史資料不足，尚不能比較兩段斜率",
    "PRIOR_SLOPE_FLAT_OR_DOWN": "前20日斜率為水平或下降",
    "RECENT_SLOPE_POSITIVE": "最近20日斜率向上",
    "POSITIVE_SLOPE_CHANGE_EXCEEDS_Z_THRESHOLD": "斜率改善幅度超過標準化門檻",
    "CONSECUTIVE_CONFIRMATION_MET": "已連續兩日符合候選條件",
    "PRIOR_SLOPE_FLAT_OR_UP": "前20日斜率為水平或上升",
    "RECENT_SLOPE_NEGATIVE": "最近20日斜率向下",
    "NEGATIVE_SLOPE_CHANGE_EXCEEDS_Z_THRESHOLD": "斜率惡化幅度超過標準化門檻",
    "RECENT_SLOPE_APPROXIMATELY_FLAT": "最近20日斜率接近水平",
    "TURN_CANDIDATE_AWAITING_CONFIRMATION": "轉折候選尚未完成連續兩日確認",
    "NO_SIGNIFICANT_CONSECUTIVE_SLOPE_REVERSAL": "目前方向明確，但未出現顯著反向轉折",
    "NORMAL_APPROXIMATION_NOT_CALIBRATED_FOR_TAIWAN_EQUITIES": "常態近似尚未以台股校準，不能解讀成真實成功機率",
}


def write_comparison_outputs(
    double_slope_results: Sequence[DoubleSlopeResult],
    ma_results: Sequence[MAStateResult],
    comparison: ComparisonResult,
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    output_dir: Path,
    *,
    source_manifests: Mapping[str, Mapping[str, object]],
    research_source_url: str,
) -> None:
    ds_ordered = tuple(sorted(double_slope_results, key=lambda item: item.symbol))
    ma_ordered = tuple(sorted(ma_results, key=lambda item: item.symbol))
    _validate_inputs(ds_ordered, ma_ordered, bars_by_symbol, source_manifests)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_latest(output_dir / "double_slope_latest.csv", ds_ordered)
    _write_events(output_dir / "double_slope_events.csv", ds_ordered)
    _write_outcomes(output_dir / "method_event_outcomes.csv", comparison.outcomes)
    _write_pairs(output_dir / "matched_detections.csv", comparison)
    manifest = _manifest(ds_ordered, ma_ordered, comparison, source_manifests, research_source_url)
    (output_dir / "double_slope_comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "double_slope_comparison_report.html").write_text(
        render_comparison_html(
            ds_ordered,
            ma_ordered,
            comparison,
            bars_by_symbol,
            manifest,
            research_source_url,
        ),
        encoding="utf-8",
    )


def render_comparison_html(
    double_slope_results: Sequence[DoubleSlopeResult],
    ma_results: Sequence[MAStateResult],
    comparison: ComparisonResult,
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    manifest: Mapping[str, object],
    research_source_url: str,
) -> str:
    ds_ordered = tuple(sorted(double_slope_results, key=lambda item: item.symbol))
    ma_by_symbol = {item.symbol: item for item in ma_results}
    latest_rows = "\n".join(_latest_row(item) for item in ds_ordered)
    summary_rows = "\n".join(_summary_row(item) for item in comparison.summaries)
    symbol_summary_rows = _symbol_summary_rows(comparison)
    pair_rows = "\n".join(_pair_row(item) for item in comparison.pairs) or _empty_row(6)
    outcome_rows = "\n".join(
        _outcome_row(item)
        for item in sorted(
            comparison.outcomes,
            key=lambda value: (value.trade_date, value.symbol, value.method),
            reverse=True,
        )
    ) or _empty_row(10)
    charts = "\n".join(
        _comparison_chart(item, ma_by_symbol[item.symbol], bars_by_symbol[item.symbol])
        for item in ds_ordered
    )
    lead = (
        f"{comparison.median_double_slope_lead_bars:.1f}個交易日"
        if comparison.median_double_slope_lead_bars is not None
        else "沒有可配對事件"
    )
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>雙斜率轉折 vs 均線基準 v0.1</title>
<style>
:root{{color-scheme:dark;--bg:#0b1020;--panel:#131a2c;--line:#2a3550;--text:#e8edf7;--muted:#9ba8bf;--danger:#fb7185}}
*{{box-sizing:border-box}}body{{margin:0;padding:28px;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1500px;margin:auto}}h1,h2,h3{{margin:0 0 12px}}h2{{margin-top:28px;font-size:19px}}h3{{margin-top:20px}}.warning{{border:1px solid var(--danger);background:#351523;padding:16px;border-radius:10px;color:#ffd8df;font-weight:700}}.note{{border:1px solid #2563eb;background:#10234d;padding:14px;border-radius:10px;margin-top:12px}}.table-wrap,.chart-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}.chart-wrap{{padding:12px}}.chart-wrap svg{{display:block;min-width:960px;width:100%;height:auto}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#1a2338;color:var(--muted);font-size:12px}}td.wrap{{white-space:normal;min-width:300px}}.pill{{display:inline-block;padding:3px 8px;border-radius:999px;background:color-mix(in srgb,var(--state) 25%,#111827);color:var(--state);font-weight:800}}.muted{{color:var(--muted)}}.bad{{color:var(--danger);font-weight:800}}code{{color:#c4b5fd}}a{{color:#7dd3fc}}footer{{margin-top:28px;color:var(--muted)}}
</style></head><body><main>
<h1>雙斜率轉折 vs 均線基準 v0.1</h1>
<div class="warning">SHADOW OBSERVATION ONLY · 不作投資使用 · Investment use: PROHIBITED<br>公司行動：UNVERIFIED；TWSE官方原始未還權價格。沒有分數、排名、勝率宣稱或買賣建議。</div>
<div class="note"><b>這不是論文的精確重製。</b>公開資料只能確認其核心為「連續兩段滾動迴歸斜率差的假設檢定」。本實驗明確採用兩段各20日的對數收盤OLS斜率、標準誤獨立近似、|z|≥1.96及連續兩日確認。研究來源：<a href="{escape(research_source_url)}">Bramante、Facchinetti、Zappa（2019）</a>。</div>
<p class="muted">雙斜率偵測只使用當日及以前資料。均線對照使用已凍結的MA5／10／20／60核心狀態；MA120／200／240不參與轉多日期。</p>
<h2>比較定義</h2>
<div class="table-wrap"><table><tbody>
<tr><th>偵測時間</th><td class="wrap">兩方法同一股票的轉多事件，於±{comparison.pair_window_bars}個交易日內做最近且一對一配對。正數代表雙斜率較早，負數代表均線較早。配對後中位數：<b>{lead}</b>。</td></tr>
<tr><th>主要誤報代理</th><td class="wrap"><code>NO_FOLLOW_THROUGH_20D</code>：訊號後完整{comparison.forward_window_bars}日內，最大收盤漲幅未達{comparison.follow_through_threshold_pct * 100:.0f}%。這是暫定研究定義，不是自然定律。</td></tr>
<tr><th>補充失敗觀察</th><td class="wrap"><code>NEGATIVE_AT_20D</code>：第20日報酬≤0；<code>DOWNSIDE_FIRST</code>：收盤先跌5%，才可能先漲5%。三種定義分開呈現，不混成分數。</td></tr>
<tr><th>尚未成熟</th><td class="wrap">距資料截止日不足20個交易日的訊號標示<code>PENDING</code>，不計入誤報率。</td></tr>
</tbody></table></div>
<h2>方法比較摘要</h2>
<div class="table-wrap"><table><thead><tr><th>方法</th><th>轉多事件</th><th>已評估</th><th>待觀察</th><th>20日未達+5%</th><th>第20日≤0</th><th>先跌5%</th><th>未延續率</th></tr></thead><tbody>{summary_rows}</tbody></table></div>
<p class="muted">目前只有三檔股票，且同一股票的事件可能在時間上重疊，因此事件不是獨立樣本；以下差異只能用來篩選值得擴大測試的方法，不能視為統計顯著或可交易績效。</p>
<h2>逐股票拆解</h2>
<div class="table-wrap"><table><thead><tr><th>股票</th><th>方法</th><th>轉多事件</th><th>已評估</th><th>20日未達+5%</th><th>未延續率</th><th>第20日≤0</th><th>先跌5%</th></tr></thead><tbody>{symbol_summary_rows}</tbody></table></div>
<h2>雙斜率目前狀態</h2>
<div class="table-wrap"><table><thead><tr><th>股票</th><th>日期</th><th>狀態</th><th>收盤</th><th>前20日斜率</th><th>近20日斜率</th><th>斜率差</th><th>z值</th><th>近似p值</th><th>支持證據</th><th>限制／反證</th></tr></thead><tbody>{latest_rows}</tbody></table></div>
<h2>配對後的發現時間</h2>
<p class="muted">「雙斜率領先」為均線日期減雙斜率日期；+3表示雙斜率早3個交易日，−3表示雙斜率晚3日。</p>
<div class="table-wrap"><table><thead><tr><th>股票</th><th>雙斜率日期</th><th>均線日期</th><th>雙斜率領先</th><th>雙斜率Event ID</th><th>均線Event ID</th></tr></thead><tbody>{pair_rows}</tbody></table></div>
<h2>逐事件結果</h2>
<div class="table-wrap"><table><thead><tr><th>日期</th><th>股票</th><th>方法</th><th>訊號價</th><th>狀態</th><th>20日報酬</th><th>20日最大漲幅</th><th>20日最大回撤</th><th>未延續</th><th>±5%先後</th></tr></thead><tbody>{outcome_rows}</tbody></table></div>
<h2>每檔事件位置圖</h2>
<p class="muted">白線是收盤；藍色菱形是雙斜率轉多；橘色圓點是均線轉多。圖形只顯示事件位置，不表示買點。</p>
{charts}
<footer>Manifest ID: <code>{escape(str(manifest["report_id"]))}</code> · Schema: TWSTOCK-DOUBLE-SLOPE-COMPARISON-001</footer>
</main></body></html>'''


def _latest_row(result: DoubleSlopeResult) -> str:
    item = result.observations[-1]
    return (
        f"<tr><td><code>{escape(item.symbol)}</code></td><td>{item.trade_date.isoformat()}</td>"
        f'<td><span class="pill" style="--state:{_STATE_COLORS[item.state]}">{item.state.value} · {escape(_STATE_LABELS[item.state])}</span></td>'
        f"<td>{_number(item.close)}</td><td>{_pct(item.prior_slope_pct)}</td>"
        f"<td>{_pct(item.recent_slope_pct)}</td><td>{_pct(item.slope_difference_pct)}</td>"
        f"<td>{_number(item.z_score)}</td><td>{_number(item.approximate_two_sided_p, 4)}</td>"
        f'<td class="wrap">{_codes(item.support_evidence)}</td>'
        f'<td class="wrap">{_codes(item.contrary_evidence)}</td></tr>'
    )


def _summary_row(summary: object) -> str:
    return (
        f"<tr><td><code>{escape(summary.method)}</code></td>"
        f"<td>{summary.total_up_events}</td><td>{summary.evaluable_events}</td>"
        f"<td>{summary.pending_events}</td><td>{summary.no_follow_through_events}</td>"
        f"<td>{summary.negative_at_20d_events}</td><td>{summary.downside_first_events}</td>"
        f"<td>{_pct(summary.no_follow_through_rate)}</td></tr>"
    )


def _symbol_summary_rows(comparison: ComparisonResult) -> str:
    rows: list[str] = []
    symbols = sorted({item.symbol for item in comparison.outcomes})
    for symbol in symbols:
        for method in ("DOUBLE_SLOPE", "MA_BASELINE"):
            selected = tuple(
                item
                for item in comparison.outcomes
                if item.symbol == symbol and item.method == method
            )
            evaluated = tuple(
                item for item in selected if item.evaluation_status == "EVALUATED"
            )
            no_follow = sum(
                item.no_follow_through is True for item in evaluated
            )
            rate = no_follow / len(evaluated) if evaluated else None
            rows.append(
                f"<tr><td><code>{escape(symbol)}</code></td>"
                f"<td><code>{escape(method)}</code></td><td>{len(selected)}</td>"
                f"<td>{len(evaluated)}</td><td>{no_follow}</td><td>{_pct(rate)}</td>"
                f"<td>{sum(item.negative_at_horizon is True for item in evaluated)}</td>"
                f"<td>{sum(item.five_pct_path_result == 'DOWNSIDE_FIRST' for item in evaluated)}</td></tr>"
            )
    return "\n".join(rows) or _empty_row(8)


def _pair_row(pair: object) -> str:
    return (
        f"<tr><td><code>{escape(pair.symbol)}</code></td>"
        f"<td>{pair.double_slope_date.isoformat()}</td><td>{pair.ma_date.isoformat()}</td>"
        f"<td>{pair.double_slope_lead_bars:+d}</td>"
        f"<td><code>{escape(pair.double_slope_event_id)}</code></td>"
        f"<td><code>{escape(pair.ma_event_id)}</code></td></tr>"
    )


def _outcome_row(item: EventOutcome) -> str:
    no_follow = (
        "PENDING" if item.no_follow_through is None else "YES" if item.no_follow_through else "NO"
    )
    return (
        f"<tr><td>{item.trade_date.isoformat()}</td><td><code>{escape(item.symbol)}</code></td>"
        f"<td><code>{escape(item.method)}</code></td><td>{_number(item.close)}</td>"
        f"<td>{escape(item.evaluation_status)}</td><td>{_pct(item.forward_return)}</td>"
        f"<td>{_pct(item.maximum_gain)}</td><td>{_pct(item.maximum_drawdown)}</td>"
        f"<td>{no_follow}</td><td>{escape(item.five_pct_path_result)}</td></tr>"
    )


def _comparison_chart(
    double_slope: DoubleSlopeResult,
    ma_result: MAStateResult,
    bars: Sequence[MarketBar],
) -> str:
    visible_start = max(0, len(bars) - 320)
    visible = tuple(bars[visible_start:])
    width, height = 1180, 500
    left, right, top, bottom = 76, 28, 48, 430
    plot_width, plot_height = width - left - right, bottom - top
    prices = [bar.close for bar in visible]
    low, high = min(prices), max(prices)
    padding = (high - low) * 0.08 if high != low else max(abs(high) * 0.02, 1.0)
    price_min, price_max = low - padding, high + padding
    span = price_max - price_min

    def x(index: int) -> float:
        return left + index / max(1, len(visible) - 1) * plot_width

    def y(value: float) -> float:
        return top + (price_max - value) / span * plot_height

    parts = [
        f'<section><h3>{escape(double_slope.symbol)}</h3><div class="chart-wrap">',
        f'<svg id="double-slope-comparison-chart-{escape(double_slope.symbol)}" viewBox="0 0 {width} {height}" role="img">',
        f'<title>{escape(double_slope.symbol)} 雙斜率與均線轉多事件比較</title>',
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
        index = round((len(visible) - 1) * step / 5)
        xx = x(index)
        parts.extend((
            f'<line x1="{xx:.1f}" y1="{top}" x2="{xx:.1f}" y2="{bottom}" stroke="#1e293b"/>',
            f'<text x="{xx:.1f}" y="{bottom+25}" text-anchor="middle" font-size="11" fill="#9ba8bf">{visible[index].trade_date.isoformat()}</text>',
        ))
    points = " ".join(f"{x(index):.1f},{y(bar.close):.1f}" for index, bar in enumerate(visible))
    parts.append(f'<polyline data-series="close" points="{points}" fill="none" stroke="#f8fafc" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    visible_dates = {bar.trade_date: index for index, bar in enumerate(visible)}
    for event in double_slope.events:
        if event.direction != "UP" or event.trade_date not in visible_dates:
            continue
        index = visible_dates[event.trade_date]
        xx, yy = x(index), y(event.close)
        title = escape(f"雙斜率轉多 · {event.trade_date.isoformat()} · {event.close:.2f}")
        points = f"{xx:.1f},{yy-7:.1f} {xx+7:.1f},{yy:.1f} {xx:.1f},{yy+7:.1f} {xx-7:.1f},{yy:.1f}"
        parts.append(f'<polygon data-method="DOUBLE_SLOPE" points="{points}" fill="#38bdf8" stroke="#082f49" stroke-width="1.5"><title>{title}</title></polygon>')
    for event in ma_result.events:
        if event.current_state.value != "TURNING_UP" or event.trade_date not in visible_dates:
            continue
        index = visible_dates[event.trade_date]
        xx, yy = x(index), y(event.close)
        title = escape(f"均線轉多 · {event.trade_date.isoformat()} · {event.close:.2f}")
        parts.append(f'<circle data-method="MA_BASELINE" cx="{xx:.1f}" cy="{yy:.1f}" r="5.5" fill="#fb923c" stroke="#431407" stroke-width="1.5"><title>{title}</title></circle>')
    parts.extend((
        f'<line x1="{left}" y1="22" x2="{left+24}" y2="22" stroke="#f8fafc" stroke-width="3"/><text x="{left+30}" y="26" font-size="11" fill="#cbd5e1">收盤</text>',
        f'<polygon points="{left+130},15 {left+137},22 {left+130},29 {left+123},22" fill="#38bdf8"/><text x="{left+145}" y="26" font-size="11" fill="#cbd5e1">雙斜率轉多</text>',
        f'<circle cx="{left+275}" cy="22" r="5.5" fill="#fb923c"/><text x="{left+288}" y="26" font-size="11" fill="#cbd5e1">均線轉多</text>',
        "</svg></div></section>",
    ))
    return "".join(parts)


def _write_latest(path: Path, results: Sequence[DoubleSlopeResult]) -> None:
    fields = (
        "symbol", "trade_date", "state", "close", "prior_slope_pct",
        "recent_slope_pct", "slope_difference_pct", "difference_standard_error",
        "z_score", "approximate_two_sided_p", "raw_turn_direction",
        "consecutive_confirmation_count", "support_evidence", "contrary_evidence",
        "corporate_action_status", "investment_use",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            item = result.observations[-1]
            row = asdict(item)
            row["trade_date"] = item.trade_date.isoformat()
            row["state"] = item.state.value
            row["support_evidence"] = "|".join(item.support_evidence)
            row["contrary_evidence"] = "|".join(item.contrary_evidence)
            row["corporate_action_status"] = result.corporate_action_status
            row["investment_use"] = result.investment_use
            writer.writerow(row)


def _write_events(path: Path, results: Sequence[DoubleSlopeResult]) -> None:
    fields = (
        "event_id", "symbol", "trade_date", "direction", "close",
        "prior_slope_pct", "recent_slope_pct", "z_score",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for event in result.events:
                row = asdict(event)
                row["trade_date"] = event.trade_date.isoformat()
                writer.writerow(row)


def _write_outcomes(path: Path, outcomes: Sequence[EventOutcome]) -> None:
    fields = tuple(asdict(outcomes[0]).keys()) if outcomes else (
        "method", "event_id", "symbol", "trade_date", "close", "evaluation_status",
        "forward_return", "maximum_gain", "maximum_drawdown",
        "no_follow_through", "negative_at_horizon", "five_pct_path_result",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in outcomes:
            row = asdict(item)
            row["trade_date"] = item.trade_date.isoformat()
            writer.writerow(row)


def _write_pairs(path: Path, comparison: ComparisonResult) -> None:
    fields = (
        "symbol", "double_slope_event_id", "double_slope_date", "ma_event_id",
        "ma_date", "double_slope_lead_bars",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in comparison.pairs:
            row = asdict(item)
            row["double_slope_date"] = item.double_slope_date.isoformat()
            row["ma_date"] = item.ma_date.isoformat()
            writer.writerow(row)


def _manifest(
    double_slope_results: Sequence[DoubleSlopeResult],
    ma_results: Sequence[MAStateResult],
    comparison: ComparisonResult,
    source_manifests: Mapping[str, Mapping[str, object]],
    research_source_url: str,
) -> dict[str, object]:
    ds_versions = {item.parameter_version for item in double_slope_results}
    ds_hashes = {item.parameter_hash for item in double_slope_results}
    ma_versions = {item.parameter_version for item in ma_results}
    ma_hashes = {item.parameter_hash for item in ma_results}
    if any(len(values) != 1 for values in (ds_versions, ds_hashes, ma_versions, ma_hashes)):
        raise ValueError("each method must use one parameter identity")
    payload = {
        "schema_version": "TWSTOCK-DOUBLE-SLOPE-COMPARISON-001",
        "method": "PAPER_INSPIRED_CONSECUTIVE_LOG_PRICE_OLS_SLOPES",
        "exact_paper_replication": False,
        "research_source_url": research_source_url,
        "double_slope_parameter_version": next(iter(ds_versions)),
        "double_slope_parameter_hash": next(iter(ds_hashes)),
        "ma_parameter_version": next(iter(ma_versions)),
        "ma_parameter_hash": next(iter(ma_hashes)),
        "symbols": [item.symbol for item in double_slope_results],
        "dataset_hashes": {
            symbol: source_manifests[symbol]["dataset_hash"]
            for symbol in sorted(source_manifests)
        },
        "forward_window_bars": comparison.forward_window_bars,
        "follow_through_threshold_pct": comparison.follow_through_threshold_pct,
        "pair_window_bars": comparison.pair_window_bars,
        "ranking": "NONE",
        "score": "NONE",
        "corporate_action_status": "UNVERIFIED",
        "investment_use": "PROHIBITED",
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "outputs": [
            "double_slope_latest.csv",
            "double_slope_events.csv",
            "method_event_outcomes.csv",
            "matched_detections.csv",
            "double_slope_comparison_manifest.json",
            "double_slope_comparison_report.html",
        ],
    }
    return {**payload, "report_id": hashlib.sha256(stable_json_bytes(payload)).hexdigest()}


def _validate_inputs(
    double_slope_results: Sequence[DoubleSlopeResult],
    ma_results: Sequence[MAStateResult],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    source_manifests: Mapping[str, Mapping[str, object]],
) -> None:
    symbols = {item.symbol for item in double_slope_results}
    if not symbols or len(symbols) != len(double_slope_results):
        raise ValueError("double-slope results must contain unique symbols")
    if symbols != {item.symbol for item in ma_results} or symbols != set(bars_by_symbol) or symbols != set(source_manifests):
        raise ValueError("all comparison inputs must contain identical symbols")
    for symbol in symbols:
        manifest = source_manifests[symbol]
        if manifest.get("selected_source") != "TWSE":
            raise ValueError("comparison requires TWSE source")
        if manifest.get("price_basis") != "RAW_OFFICIAL_DAILY":
            raise ValueError("comparison requires official raw daily prices")
        if manifest.get("adjustment_policy") != "RAW_UNADJUSTED":
            raise ValueError("comparison requires raw unadjusted prices")
        if manifest.get("corporate_actions_applied") is not False:
            raise ValueError("corporate actions must remain explicitly unapplied")
        if not isinstance(manifest.get("dataset_hash"), str) or not manifest["dataset_hash"]:
            raise ValueError("source manifest must contain dataset_hash")


def _codes(values: Sequence[str]) -> str:
    rendered = []
    for value in values:
        if value.startswith("INSUFFICIENT_HISTORY:NEED_"):
            count = value.removeprefix("INSUFFICIENT_HISTORY:NEED_").removesuffix("_BARS")
            label = f"歷史資料不足，需要至少{count}個交易日"
        else:
            label = _EVIDENCE_LABELS.get(value, value)
        rendered.append(f"{escape(label)}<br><code>{escape(value)}</code>")
    return "<br>".join(rendered) or "—"


def _number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if math.isinf(value):
        return "+∞" if value > 0 else "−∞"
    return f"{value:.{digits}f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def _empty_row(columns: int) -> str:
    return f'<tr><td colspan="{columns}" class="muted">沒有資料</td></tr>'
