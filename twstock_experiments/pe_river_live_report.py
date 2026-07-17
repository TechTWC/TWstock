from __future__ import annotations

import csv
import html
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence

from .pe_river_live_metrics import HistoricalPEPoint


def json_value(value: object) -> object:
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, dict): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_value(v) for v in value]
    return value


def fmt(value: object, digits: int = 2, suffix: str = "") -> str:
    if value is None: return "—"
    parsed = Decimal(str(value)); quantum = Decimal("1").scaleb(-digits)
    return f"{parsed.quantize(quantum, rounding=ROUND_HALF_UP):.{digits}f}{suffix}"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(json_value(payload), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_historical_pe_csv(path: Path, points: Sequence[HistoricalPEPoint]) -> None:
    multiples = list(points[0].bands) if points else []
    fields = ["trade_date", "close_twd", "ttm_eps_twd", "pe_ttm"] + [f"price_at_{m}x" for m in multiples]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for point in points:
            row = {"trade_date": point.trade_date.isoformat(), "close_twd": fmt(point.close_twd), "ttm_eps_twd": fmt(point.ttm_eps_twd), "pe_ttm": fmt(point.pe_ttm, 4)}
            row.update({f"price_at_{m}x": fmt(v) for m, v in point.bands.items()}); writer.writerow(row)


def write_diagnostic_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    fields = ("signal_date", "exit_date", "bucket", "pe_ttm", "expanding_pe_percentile", "close_twd", "ma200_twd", "stock_forward_return_pct", "benchmark_forward_return_pct", "excess_return_pct")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in rows: writer.writerow({field: json_value(row.get(field)) for field in fields})


def _month_ends(points: Sequence[HistoricalPEPoint]) -> list[HistoricalPEPoint]:
    out: list[HistoricalPEPoint] = []
    for point in points:
        if not out or point.trade_date.strftime("%Y-%m") != out[-1].trade_date.strftime("%Y-%m"): out.append(point)
        else: out[-1] = point
    return out


def historical_river_svg(points: Sequence[HistoricalPEPoint], multiples: Sequence[Decimal]) -> str:
    sampled = _month_ends(points)
    if len(sampled) < 2: return "<p>歷史資料不足，無法繪圖。</p>"
    width, height, left, right, top, bottom = 1060, 470, 72, 100, 30, 60
    values = [p.close_twd for p in sampled] + [p.bands[str(m)] for p in sampled for m in multiples]
    low, high = min(values) * Decimal("0.92"), max(values) * Decimal("1.06"); span = high - low
    x = lambda i: left + i / (len(sampled)-1) * (width-left-right)
    y = lambda value: top + float((high-value)/span) * (height-top-bottom)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img"><rect width="100%" height="100%" rx="14" fill="#fbfcfe"/>']
    for step in range(6):
        value = low + span * Decimal(step)/5; yy = y(value)
        parts += [f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#e5e7eb"/>', f'<text x="{left-8}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{fmt(value,0)}</text>']
    colors = ["#93c5fd", "#60a5fa", "#3b82f6", "#1d4ed8"]
    for idx, multiple in enumerate(multiples):
        curve = " ".join(("M" if i == 0 else "L") + f" {x(i):.1f} {y(p.bands[str(multiple)]):.1f}" for i,p in enumerate(sampled))
        parts += [f'<path d="{curve}" fill="none" stroke="{colors[min(idx,3)]}" stroke-width="2"/>', f'<text x="{width-right+8}" y="{y(sampled[-1].bands[str(multiple)])+4:.1f}" font-size="11" fill="{colors[min(idx,3)]}">{fmt(multiple,0)}x</text>']
    price_curve = " ".join(("M" if i == 0 else "L") + f" {x(i):.1f} {y(p.close_twd):.1f}" for i,p in enumerate(sampled))
    parts.append(f'<path d="{price_curve}" fill="none" stroke="#dc2626" stroke-width="3"/>')
    for i in range(0, len(sampled), max(1, len(sampled)//6)):
        parts.append(f'<text x="{x(i):.1f}" y="{height-24}" text-anchor="middle" font-size="11" fill="#64748b">{sampled[i].trade_date:%Y-%m}</text>')
    return "".join(parts) + "</svg>"


def pill(text: str, kind: str = "neutral") -> str:
    return f'<span class="pill {kind}">{html.escape(text)}</span>'


def write_live_html(path: Path, analysis: dict[str, object], points: Sequence[HistoricalPEPoint], multiples: Sequence[Decimal]) -> None:
    quote, valuation = analysis["quote"], analysis["current_valuation"]
    technical, fundamental = analysis["technical_context"], analysis["fundamental_context"]
    diagnostic, forward = analysis["diagnostic_backtest"], analysis["forward_scenarios"]
    assert isinstance(quote, dict) and isinstance(valuation, dict) and isinstance(technical, dict) and isinstance(fundamental, dict) and isinstance(diagnostic, dict) and isinstance(forward, list)
    band_rows = "".join(f"<tr><td>{m}x</td><td>{fmt(valuation['river_band_prices_twd'][m],0)}</td><td>{fmt(valuation['price_gap_to_band_pct'][m],2,'%')}</td></tr>" for m in valuation["river_band_prices_twd"])
    forward_rows = "".join(f"<tr><td><strong>{html.escape(str(i['scenario']))}</strong></td><td>{fmt(i['ntm_eps_twd'])}</td><td>{fmt(i['exit_pe'])}x</td><td>{fmt(i['scenario_price_twd'],0)}</td><td>{fmt(i['expected_price_return_pct'],2,'%')}</td><td>{pill(str(i['assumption_status']),'warning')}</td></tr>" for i in forward)
    revenue_rows = "".join(f"<tr><td>{i['month']}</td><td>{fmt(i['revenue_million_twd'],0)}</td><td>{fmt(i['yoy_pct'],2,'%')}</td></tr>" for i in fundamental["monthly_revenue_yoy"][-6:])
    diag_rows = "".join(f"<tr><td>{i['bucket']}</td><td>{i['observation_count']}</td><td>{fmt(i['average_excess_return_pct'],2,'%')}</td><td>{fmt(i['median_excess_return_pct'],2,'%')}</td><td>{fmt(i['positive_excess_rate_pct'],2,'%')}</td></tr>" for i in diagnostic["summary"])
    latest_q = fundamental["latest_quarter"]
    fallback = analysis.get("quote_fallback_reason")
    fallback_html = f'<p class="warn"><strong>延遲報價抓取失敗：</strong>{html.escape(str(fallback))}<br>已改用最新官方完成交易日收盤。</p>' if fallback else ""
    notes = "".join(f"<li>{html.escape(str(note))}</li>" for note in analysis["method_notes"])
    document = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>2330 Live PE River</title><style>
:root{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#111827}}main{{max-width:1220px;margin:auto;padding:26px 20px 60px}}header,section{{background:#fff;border:1px solid #dce3ec;border-radius:16px;padding:22px;margin-bottom:17px}}h1{{margin:6px 0}}h2{{margin:0 0 14px;font-size:1.2rem}}h3{{font-size:.86rem;color:#64748b;margin:0 0 7px}}p,li{{color:#475569;line-height:1.65}}.eye{{font-size:.74rem;font-weight:800;letter-spacing:.08em;color:#1d4ed8}}.status{{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}}.pill{{display:inline-block;padding:4px 9px;border-radius:999px;background:#eef2f7;color:#475569;font-size:.7rem;font-weight:800}}.pill.good{{background:#dcfce7;color:#166534}}.pill.warning{{background:#fef3c7;color:#92400e}}.pill.danger{{background:#fee2e2;color:#991b1b}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}}.card{{border:1px solid #e2e8f0;border-radius:13px;padding:15px;background:#fbfdff}}.metric{{font-weight:850;font-size:1.65rem}}.muted{{font-size:.8rem;color:#64748b;line-height:1.5}}.callout{{border-left:4px solid #2563eb;background:#eff6ff;padding:13px 15px;border-radius:8px;color:#1e3a8a}}.warn{{border-left:4px solid #d97706;background:#fffbeb;padding:13px 15px;border-radius:8px;color:#92400e}}.chart,.table{{overflow:auto}}.chart svg{{min-width:820px;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:.86rem}}th,td{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;white-space:nowrap}}th{{background:#f8fafc;color:#475569}}@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><header><div class="eye">TWSTOCK EXPERIMENT · TW-EXP-2330-PE-RIVER-0002</div><h1>2330.TW 最新估值河流與投資脈絡</h1><p>延遲行情、PIT TTM EPS、歷史Trailing P/E、技術位置、營收與利潤率分開呈現。</p><div class="status">{pill('EXPLORATORY_NOT_VALIDATED','danger')}{pill(str(quote['data_status']),'warning')}{pill('TWSE OFFICIAL HISTORY','good')}{pill('NO ALPHA CLAIM','danger')}</div></header>{fallback_html}
<section><h2>最新狀況</h2><div class="grid"><div class="card"><h3>最新可用價格</h3><div class="metric">NT$ {fmt(quote['price_twd'],0)}</div><div class="muted">{quote['observed_at']}<br>{quote['source']} · {quote['market_state']}</div></div><div class="card"><h3>PIT TTM EPS</h3><div class="metric">{fmt(valuation['ttm_eps_twd'])}</div><div class="muted">{' → '.join(valuation['included_periods'])}</div></div><div class="card"><h3>Trailing P/E</h3><div class="metric">{fmt(valuation['pe_ttm'])}x</div><div class="muted">歷史百分位 {fmt(valuation['historical_trailing_pe_percentile'],1,'%')} · n={valuation['historical_observation_count']}</div></div><div class="card"><h3>長期趨勢</h3><div class="metric">MA200 {fmt(technical['ma200_twd'],0)}</div><div class="muted">價格相對MA200 {fmt(technical['price_vs_ma200_pct'],2,'%')}<br>距60日高點 {fmt(technical['drawdown_from_60d_high_pct'],2,'%')}</div></div></div><p class="callout">目前價格應同時對照估值百分位、盈餘與營收趨勢，以及價格是否仍高於長期趨勢。單看河流顏色不構成訊號。</p></section>
<section><h2>歷史Point-in-Time河流</h2><div class="chart">{historical_river_svg(points,multiples)}</div><p class="muted">官方TWSE完成交易日收盤；本版覆蓋 {analysis['historical_coverage']['start']} 至 {analysis['historical_coverage']['end']}，尚不是完整十年。</p></section>
<section><h2>最新估值階梯</h2><div class="table"><table><thead><tr><th>P/E</th><th>河流價</th><th>價格相對河流</th></tr></thead><tbody>{band_rows}</tbody></table></div></section>
<section><h2>基本面驗證</h2><div class="grid"><div class="card"><h3>最新季度</h3><div class="metric">{latest_q['period']}</div><div class="muted">EPS {fmt(latest_q['diluted_eps_twd'])}</div></div><div class="card"><h3>毛利率</h3><div class="metric">{fmt(latest_q['gross_margin_pct'],1,'%')}</div><div class="muted">QoQ {fmt(fundamental['gross_margin_qoq_ppt'],1,'ppt')} · YoY {fmt(fundamental['gross_margin_yoy_ppt'],1,'ppt')}</div></div><div class="card"><h3>營業利益率</h3><div class="metric">{fmt(latest_q['operating_margin_pct'],1,'%')}</div><div class="muted">QoQ {fmt(fundamental['operating_margin_qoq_ppt'],1,'ppt')} · YoY {fmt(fundamental['operating_margin_yoy_ppt'],1,'ppt')}</div></div><div class="card"><h3>近3月營收YoY</h3><div class="metric">{fmt(fundamental['latest_3m_average_revenue_yoy_pct'],1,'%')}</div><div class="muted">目前僅供最新脈絡</div></div></div><div class="table"><table><thead><tr><th>月份</th><th>營收百萬元</th><th>YoY</th></tr></thead><tbody>{revenue_rows}</tbody></table></div></section>
<section><h2>技術與相對動能</h2><div class="table"><table><tbody><tr><th>官方最後交易日</th><td>{technical['official_last_trade_date']}</td><th>官方收盤</th><td>{fmt(technical['official_last_close_twd'],0)}</td></tr><tr><th>MA50</th><td>{fmt(technical['ma50_twd'],0)}</td><th>相對MA50</th><td>{fmt(technical['price_vs_ma50_pct'],2,'%')}</td></tr><tr><th>MA200</th><td>{fmt(technical['ma200_twd'],0)}</td><th>相對MA200</th><td>{fmt(technical['price_vs_ma200_pct'],2,'%')}</td></tr><tr><th>2330 12-1動能</th><td>{fmt(technical['stock_momentum_12_1_pct'],2,'%')}</td><th>相對0050</th><td>{fmt(technical['relative_momentum_12_1_pct'],2,'%')}</td></tr></tbody></table></div></section>
<section><h2>Forward情境（人工假設）</h2><div class="table"><table><thead><tr><th>情境</th><th>NTM EPS</th><th>出場P/E</th><th>情境價</th><th>相對最新價格</th><th>性質</th></tr></thead><tbody>{forward_rows}</tbody></table></div><p class="muted">尚未取得可合法重建的歷史法人共識版本，因此不把人工情境冒充成Forward P/E歷史。</p></section>
<section><h2>63交易日診斷性回看</h2><div class="table"><table><thead><tr><th>狀態桶</th><th>樣本</th><th>平均超額</th><th>中位超額</th><th>正超額比例</th></tr></thead><tbody>{diag_rows}</tbody></table></div><p class="warn">單一股票、短歷史結果不能證明超額報酬。正式驗證須擴展股票池、交易成本、樣本外與多重測試控制。</p></section><section><h2>資料與限制</h2><ul>{notes}</ul></section></main></body></html>'''
    path.write_text(document, encoding="utf-8")
