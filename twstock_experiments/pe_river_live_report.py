from __future__ import annotations

import csv
import html
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence

from .pe_river_live_metrics import HistoricalForwardPEPoint, HistoricalPEPoint


def json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def fmt(value: object, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    parsed = Decimal(str(value))
    quantum = Decimal("1").scaleb(-digits)
    return f"{parsed.quantize(quantum, rounding=ROUND_HALF_UP):.{digits}f}{suffix}"


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(json_value(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_historical_pe_csv(
    path: Path, points: Sequence[HistoricalPEPoint]
) -> None:
    multiples = list(points[0].bands) if points else []
    fields = ["trade_date", "close_twd", "ttm_eps_twd", "pe_ttm"] + [
        f"price_at_{multiple}x" for multiple in multiples
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for point in points:
            row = {
                "trade_date": point.trade_date.isoformat(),
                "close_twd": fmt(point.close_twd),
                "ttm_eps_twd": fmt(point.ttm_eps_twd),
                "pe_ttm": fmt(point.pe_ttm, 4),
            }
            row.update(
                {
                    f"price_at_{multiple}x": fmt(value)
                    for multiple, value in point.bands.items()
                }
            )
            writer.writerow(row)


def write_historical_forward_pe_csv(
    path: Path, points: Sequence[HistoricalForwardPEPoint]
) -> None:
    fields = (
        "trade_date",
        "close_twd",
        "ntm_eps_twd",
        "pe_forward",
        "vintage_as_of_date",
        "source_name",
        "data_status",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "trade_date": point.trade_date.isoformat(),
                    "close_twd": fmt(point.close_twd),
                    "ntm_eps_twd": fmt(point.ntm_eps_twd),
                    "pe_forward": fmt(point.pe_forward, 4),
                    "vintage_as_of_date": point.vintage_as_of_date.isoformat(),
                    "source_name": point.source_name,
                    "data_status": point.data_status,
                }
            )


def write_multi_horizon_csv(
    path: Path, rows: Sequence[dict[str, object]]
) -> None:
    fields = (
        "signal_date",
        "exit_date",
        "horizon_sessions",
        "horizon_label",
        "bucket",
        "pe_ttm",
        "expanding_pe_percentile",
        "close_twd",
        "ma200_twd",
        "stock_forward_return_pct",
        "benchmark_forward_return_pct",
        "excess_return_pct",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: json_value(row.get(field)) for field in fields}
            )


# Compatibility alias for callers that still use the v0.2 name.
def write_diagnostic_csv(
    path: Path, rows: Sequence[dict[str, object]]
) -> None:
    write_multi_horizon_csv(path, rows)


def _month_ends(points: Sequence[HistoricalPEPoint]) -> list[HistoricalPEPoint]:
    output: list[HistoricalPEPoint] = []
    for point in points:
        if (
            not output
            or point.trade_date.strftime("%Y-%m")
            != output[-1].trade_date.strftime("%Y-%m")
        ):
            output.append(point)
        else:
            output[-1] = point
    return output


def historical_river_svg(
    points: Sequence[HistoricalPEPoint], multiples: Sequence[Decimal]
) -> str:
    sampled = _month_ends(points)
    if len(sampled) < 2:
        return "<p>歷史資料不足，無法繪圖。</p>"
    width, height, left, right, top, bottom = 1120, 500, 72, 105, 30, 68
    values = [point.close_twd for point in sampled] + [
        point.bands[str(multiple)]
        for point in sampled
        for multiple in multiples
    ]
    low = min(values) * Decimal("0.92")
    high = max(values) * Decimal("1.06")
    span = high - low

    def x(index: int) -> float:
        return left + index / (len(sampled) - 1) * (width - left - right)

    def y(value: Decimal) -> float:
        return top + float((high - value) / span) * (height - top - bottom)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Five-year Point-in-Time PE river">',
        '<rect width="100%" height="100%" rx="14" fill="#fbfcfe"/>',
    ]
    for step in range(6):
        value = low + span * Decimal(step) / Decimal(5)
        yy = y(value)
        parts.extend(
            [
                f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#e5e7eb"/>',
                f'<text x="{left-8}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{fmt(value,0)}</text>',
            ]
        )

    colors = ["#bfdbfe", "#93c5fd", "#60a5fa", "#2563eb", "#1d4ed8"]
    for index, multiple in enumerate(multiples):
        curve = " ".join(
            ("M" if point_index == 0 else "L")
            + f" {x(point_index):.1f} {y(point.bands[str(multiple)]):.1f}"
            for point_index, point in enumerate(sampled)
        )
        color = colors[min(index, len(colors) - 1)]
        parts.extend(
            [
                f'<path d="{curve}" fill="none" stroke="{color}" stroke-width="2"/>',
                f'<text x="{width-right+8}" y="{y(sampled[-1].bands[str(multiple)])+4:.1f}" font-size="11" fill="{color}">{fmt(multiple,0)}x</text>',
            ]
        )

    price_curve = " ".join(
        ("M" if index == 0 else "L")
        + f" {x(index):.1f} {y(point.close_twd):.1f}"
        for index, point in enumerate(sampled)
    )
    parts.append(
        f'<path d="{price_curve}" fill="none" stroke="#dc2626" stroke-width="3"/>'
    )
    label_step = max(1, len(sampled) // 8)
    for index in range(0, len(sampled), label_step):
        parts.append(
            f'<text x="{x(index):.1f}" y="{height-25}" text-anchor="middle" font-size="11" fill="#64748b">{sampled[index].trade_date:%Y-%m}</text>'
        )
    parts.append(
        f'<text x="{x(len(sampled)-1):.1f}" y="{height-25}" text-anchor="middle" font-size="11" fill="#64748b">{sampled[-1].trade_date:%Y-%m}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def pill(text: str, kind: str = "neutral") -> str:
    return (
        f'<span class="pill {kind}">{html.escape(text)}</span>'
    )


def _forward_pe_section(forward_pe: dict[str, object]) -> str:
    status = str(forward_pe["status"])
    if status != "AVAILABLE_VERIFIED_HISTORICAL_FORWARD_PE":
        return f"""
<section>
<h2>歷史 Forward P/E 百分位</h2>
<p class="warn"><strong>目前未產生數值：</strong>{html.escape(status)}。系統只接受具日期版本的法人共識 NTM EPS，且每一筆都必須標示 <code>VERIFIED_ANALYST_CONSENSUS_VINTAGE</code>。目前輸入檔沒有符合條件的歷史版本，因此不以人工 Bear/Base/Bull 假設或事後實際 EPS 冒充歷史 Forward P/E。</p>
<div class="grid">
<div class="card"><h3>可用歷史觀察</h3><div class="metric">{forward_pe['historical_observation_count']}</div></div>
<div class="card"><h3>可用預估版本</h3><div class="metric">{forward_pe['vintage_count']}</div></div>
<div class="card"><h3>目前 Forward P/E</h3><div class="metric">—</div></div>
<div class="card"><h3>歷史百分位</h3><div class="metric">—</div></div>
</div>
</section>"""
    return f"""
<section>
<h2>歷史 Forward P/E 百分位</h2>
<div class="grid">
<div class="card"><h3>最新 NTM EPS</h3><div class="metric">{fmt(forward_pe['current_ntm_eps_twd'])}</div></div>
<div class="card"><h3>最新 Forward P/E</h3><div class="metric">{fmt(forward_pe['current_forward_pe'])}x</div></div>
<div class="card"><h3>五年百分位</h3><div class="metric">{fmt(forward_pe['historical_forward_pe_percentile'],1,'%')}</div></div>
<div class="card"><h3>觀察／版本數</h3><div class="metric">{forward_pe['historical_observation_count']} / {forward_pe['vintage_count']}</div></div>
</div>
<p class="muted">只使用當時已存在的法人共識版本，不使用事後修正資料。</p>
</section>"""


def write_live_html(
    path: Path,
    analysis: dict[str, object],
    points: Sequence[HistoricalPEPoint],
    multiples: Sequence[Decimal],
) -> None:
    quote = analysis["quote"]
    valuation = analysis["current_valuation"]
    forward_pe = analysis["historical_forward_pe"]
    technical = analysis["technical_context"]
    fundamental = analysis["fundamental_context"]
    diagnostic = analysis["diagnostic_backtest"]
    forward = analysis["forward_scenarios"]
    coverage = analysis["historical_coverage"]
    assert isinstance(quote, dict)
    assert isinstance(valuation, dict)
    assert isinstance(forward_pe, dict)
    assert isinstance(technical, dict)
    assert isinstance(fundamental, dict)
    assert isinstance(diagnostic, dict)
    assert isinstance(forward, list)
    assert isinstance(coverage, dict)

    band_rows = "".join(
        f"<tr><td>{multiple}x</td><td>{fmt(valuation['river_band_prices_twd'][multiple],0)}</td><td>{fmt(valuation['price_gap_to_band_pct'][multiple],2,'%')}</td></tr>"
        for multiple in valuation["river_band_prices_twd"]
    )
    forward_rows = "".join(
        f"<tr><td><strong>{html.escape(str(item['scenario']))}</strong></td><td>{fmt(item['ntm_eps_twd'])}</td><td>{fmt(item['exit_pe'])}x</td><td>{fmt(item['scenario_price_twd'],0)}</td><td>{fmt(item['expected_price_return_pct'],2,'%')}</td><td>{pill(str(item['assumption_status']),'warning')}</td></tr>"
        for item in forward
    )
    revenue_rows = "".join(
        f"<tr><td>{item['month']}</td><td>{fmt(item['revenue_million_twd'],0)}</td><td>{fmt(item['yoy_pct'],2,'%')}</td></tr>"
        for item in fundamental["monthly_revenue_yoy"][-6:]
    )
    diagnostic_rows = "".join(
        f"<tr><td>{item['horizon_label']}</td><td>{item['horizon_sessions']}</td><td>{item['bucket']}</td><td>{item['observation_count']}</td><td>{fmt(item['average_stock_return_pct'],2,'%')}</td><td>{fmt(item['average_benchmark_return_pct'],2,'%')}</td><td>{fmt(item['average_excess_return_pct'],2,'%')}</td><td>{fmt(item['median_excess_return_pct'],2,'%')}</td><td>{fmt(item['positive_excess_rate_pct'],2,'%')}</td></tr>"
        for item in diagnostic["summary"]
    )
    latest_q = fundamental["latest_quarter"]
    fallback = analysis.get("quote_fallback_reason")
    fallback_html = (
        f'<p class="warn"><strong>延遲報價抓取失敗：</strong>{html.escape(str(fallback))}<br>已改用最新官方完成交易日收盤。</p>'
        if fallback
        else ""
    )
    notes = "".join(
        f"<li>{html.escape(str(note))}</li>" for note in analysis["method_notes"]
    )
    forward_pe_html = _forward_pe_section(forward_pe)

    document = f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>2330 Five-Year PIT PE River</title>
<style>
:root{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#111827}}main{{max-width:1280px;margin:auto;padding:26px 20px 60px}}header,section{{background:#fff;border:1px solid #dce3ec;border-radius:16px;padding:22px;margin-bottom:17px}}h1{{margin:6px 0}}h2{{margin:0 0 14px;font-size:1.2rem}}h3{{font-size:.86rem;color:#64748b;margin:0 0 7px}}p,li{{color:#475569;line-height:1.65}}code{{background:#eef2f7;padding:2px 5px;border-radius:4px}}.eye{{font-size:.74rem;font-weight:800;letter-spacing:.08em;color:#1d4ed8}}.status{{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}}.pill{{display:inline-block;padding:4px 9px;border-radius:999px;background:#eef2f7;color:#475569;font-size:.7rem;font-weight:800}}.pill.good{{background:#dcfce7;color:#166534}}.pill.warning{{background:#fef3c7;color:#92400e}}.pill.danger{{background:#fee2e2;color:#991b1b}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}}.card{{border:1px solid #e2e8f0;border-radius:13px;padding:15px;background:#fbfdff}}.metric{{font-weight:850;font-size:1.65rem}}.muted{{font-size:.8rem;color:#64748b;line-height:1.5}}.callout{{border-left:4px solid #2563eb;background:#eff6ff;padding:13px 15px;border-radius:8px;color:#1e3a8a}}.warn{{border-left:4px solid #d97706;background:#fffbeb;padding:13px 15px;border-radius:8px;color:#92400e}}.chart,.table{{overflow:auto}}.chart svg{{min-width:900px;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:.84rem}}th,td{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;white-space:nowrap}}th{{background:#f8fafc;color:#475569}}@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main>
<header>
<div class="eye">TWSTOCK EXPERIMENT · TW-EXP-2330-PE-RIVER-0003</div>
<h1>2330.TW 五年 Point-in-Time 估值河流</h1>
<p>延遲行情、五年PIT Trailing P/E、嚴格的歷史Forward P/E資料契約，以及最長一年多期超額報酬診斷。</p>
<div class="status">{pill('EXPLORATORY_NOT_VALIDATED','danger')}{pill(str(quote['data_status']),'warning')}{pill('TWSE OFFICIAL HISTORY','good')}{pill('5-YEAR PIT RIVER','good')}{pill('NO ALPHA CLAIM','danger')}</div>
</header>
{fallback_html}
<section>
<h2>最新狀況</h2>
<div class="grid">
<div class="card"><h3>最新可用價格</h3><div class="metric">NT$ {fmt(quote['price_twd'],0)}</div><div class="muted">{quote['observed_at']}<br>{quote['source']} · {quote['market_state']}</div></div>
<div class="card"><h3>PIT TTM EPS</h3><div class="metric">{fmt(valuation['ttm_eps_twd'])}</div><div class="muted">{' → '.join(valuation['included_periods'])}</div></div>
<div class="card"><h3>Trailing P/E</h3><div class="metric">{fmt(valuation['pe_ttm'])}x</div><div class="muted">五年百分位 {fmt(valuation['historical_trailing_pe_percentile'],1,'%')} · n={valuation['historical_observation_count']}</div></div>
<div class="card"><h3>長期趨勢</h3><div class="metric">MA200 {fmt(technical['ma200_twd'],0)}</div><div class="muted">價格相對MA200 {fmt(technical['price_vs_ma200_pct'],2,'%')}<br>距60日高點 {fmt(technical['drawdown_from_60d_high_pct'],2,'%')}</div></div>
</div>
<p class="callout">目前價格需同時對照五年估值位置、盈餘與營收趨勢及長期價格趨勢；單看河流顏色不構成買賣訊號。</p>
</section>
<section>
<h2>完整五年 Point-in-Time 河流</h2>
<div class="chart">{historical_river_svg(points,multiples)}</div>
<p class="muted">要求區間 {coverage['requested_start']} 至 {coverage['actual_trailing_pe_end']}；實際可計算區間 {coverage['actual_trailing_pe_start']} 至 {coverage['actual_trailing_pe_end']}，共 {coverage['trailing_observation_count']} 個官方TWSE交易日觀察。每一天只使用當時已達 research_available_date 的季度EPS。</p>
</section>
{forward_pe_html}
<section>
<h2>最新估值階梯</h2>
<div class="table"><table><thead><tr><th>P/E</th><th>河流價</th><th>價格相對河流</th></tr></thead><tbody>{band_rows}</tbody></table></div>
</section>
<section>
<h2>多期超額報酬診斷：最長一年</h2>
<div class="table"><table><thead><tr><th>期間</th><th>交易日</th><th>估值狀態</th><th>樣本</th><th>2330平均報酬</th><th>0050平均報酬</th><th>平均超額</th><th>超額中位數</th><th>正超額比例</th></tr></thead><tbody>{diagnostic_rows}</tbody></table></div>
<p class="warn"><strong>限制：</strong>1、3、6、9、12個月以21、63、126、189、252交易日近似。月末訊號與長期持有期間互相重疊，觀察值不是獨立樣本；單一股票五年結果只能作診斷，不能證明Alpha。</p>
</section>
<section>
<h2>基本面驗證</h2>
<div class="grid">
<div class="card"><h3>最新季度</h3><div class="metric">{latest_q['period']}</div><div class="muted">EPS {fmt(latest_q['diluted_eps_twd'])}</div></div>
<div class="card"><h3>毛利率</h3><div class="metric">{fmt(latest_q['gross_margin_pct'],1,'%')}</div><div class="muted">QoQ {fmt(fundamental['gross_margin_qoq_ppt'],1,'ppt')} · YoY {fmt(fundamental['gross_margin_yoy_ppt'],1,'ppt')}</div></div>
<div class="card"><h3>營業利益率</h3><div class="metric">{fmt(latest_q['operating_margin_pct'],1,'%')}</div><div class="muted">QoQ {fmt(fundamental['operating_margin_qoq_ppt'],1,'ppt')} · YoY {fmt(fundamental['operating_margin_yoy_ppt'],1,'ppt')}</div></div>
<div class="card"><h3>近3月營收YoY</h3><div class="metric">{fmt(fundamental['latest_3m_average_revenue_yoy_pct'],1,'%')}</div><div class="muted">目前僅供最新脈絡</div></div>
</div>
<div class="table"><table><thead><tr><th>月份</th><th>營收百萬元</th><th>YoY</th></tr></thead><tbody>{revenue_rows}</tbody></table></div>
</section>
<section>
<h2>技術與相對動能</h2>
<div class="table"><table><tbody><tr><th>官方最後交易日</th><td>{technical['official_last_trade_date']}</td><th>官方收盤</th><td>{fmt(technical['official_last_close_twd'],0)}</td></tr><tr><th>MA50</th><td>{fmt(technical['ma50_twd'],0)}</td><th>相對MA50</th><td>{fmt(technical['price_vs_ma50_pct'],2,'%')}</td></tr><tr><th>MA200</th><td>{fmt(technical['ma200_twd'],0)}</td><th>相對MA200</th><td>{fmt(technical['price_vs_ma200_pct'],2,'%')}</td></tr><tr><th>2330 12-1動能</th><td>{fmt(technical['stock_momentum_12_1_pct'],2,'%')}</td><th>相對0050</th><td>{fmt(technical['relative_momentum_12_1_pct'],2,'%')}</td></tr></tbody></table></div>
</section>
<section>
<h2>Forward情境（人工壓力測試）</h2>
<div class="table"><table><thead><tr><th>情境</th><th>NTM EPS</th><th>出場P/E</th><th>情境價</th><th>相對最新價格</th><th>性質</th></tr></thead><tbody>{forward_rows}</tbody></table></div>
<p class="muted">這些人工情境只做壓力測試，與上方嚴格的歷史Forward P/E資料集完全分離。</p>
</section>
<section><h2>資料與限制</h2><ul>{notes}</ul></section>
</main></body></html>'''
    path.write_text(document, encoding="utf-8")
