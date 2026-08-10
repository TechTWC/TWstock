from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Sequence

from experiments.breakout_tracker_v5 import BreakoutSnapshot, BreakoutState, PriceBar

from .models import (
    HighSnapshot,
    HighStage,
    MonitorConfig,
    MonitorEventType,
    MonitorResult,
)


STAGE_COLORS = {
    HighStage.WATCH: "#38bdf8",
    HighStage.EMERGING: "#2563eb",
    HighStage.STRENGTHENING: "#1d4ed8",
    HighStage.LEADER: "#16a34a",
    HighStage.COOLING: "#f59e0b",
    HighStage.WEAKENING: "#dc2626",
}


def write_timeline_csv(result: MonitorResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "parameter_version",
                "parameter_hash",
                "event_id",
                "symbol",
                "trade_date",
                "event_type",
                "detail",
                "stage",
                "close",
            )
        )
        for event in result.events:
            writer.writerow(
                (
                    result.parameter_version,
                    result.parameter_hash,
                    event.event_id,
                    event.symbol,
                    event.trade_date.isoformat(),
                    event.event_type.value,
                    event.detail,
                    event.stage.value,
                    f"{event.close:.6f}",
                )
            )


def write_feature_csv(
    result: MonitorResult, config: MonitorConfig, path: Path
) -> None:
    if result.parameter_version != config.parameter_version:
        raise ValueError("result parameter version does not match feature config")
    if result.parameter_hash != config.parameter_hash:
        raise ValueError("result parameter hash does not match feature config")
    path.parent.mkdir(parents=True, exist_ok=True)
    stage_by_date = {item.trade_date: item for item in result.snapshots}
    fixed_fields = [
        "parameter_version",
        "parameter_hash",
        "symbol",
        "trade_date",
        "close",
        "stage",
        "risk_flags",
        "distance_to_near_high_pct",
        "recent_high_count",
        "acceleration_high_count",
        "volume_ratio",
        "moving_average",
        "ma_extension_pct",
        "drawdown_from_recent_high_pct",
        "trading_value",
    ]
    high_fields = [
        field
        for window in config.high_windows
        for field in (f"prior_high_{window}d", f"new_high_{window}d")
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fixed_fields + high_fields)
        writer.writeheader()
        for observation in result.feature_rows:
            features = observation.features
            snapshot = stage_by_date.get(observation.trade_date)
            row: dict[str, object] = {
                "parameter_version": result.parameter_version,
                "parameter_hash": result.parameter_hash,
                "symbol": observation.symbol,
                "trade_date": observation.trade_date.isoformat(),
                "close": _csv_float(observation.close),
                "stage": snapshot.stage.value if snapshot else "",
                "risk_flags": (
                    "|".join(item.value for item in snapshot.risk_flags)
                    if snapshot
                    else ""
                ),
                "distance_to_near_high_pct": _csv_float(
                    features.distance_to_near_high_pct
                ),
                "recent_high_count": features.recent_high_count,
                "acceleration_high_count": features.acceleration_high_count,
                "volume_ratio": _csv_float(features.volume_ratio),
                "moving_average": _csv_float(features.moving_average),
                "ma_extension_pct": _csv_float(features.ma_extension_pct),
                "drawdown_from_recent_high_pct": _csv_float(
                    features.drawdown_from_recent_high_pct
                ),
                "trading_value": _csv_float(features.trading_value),
            }
            for window in config.high_windows:
                prior_high = features.prior_high(window)
                row[f"prior_high_{window}d"] = _csv_float(prior_high)
                row[f"new_high_{window}d"] = (
                    "" if prior_high is None else int(window in features.new_high_windows)
                )
            writer.writerow(row)


def _csv_float(value: float | None) -> str:
    return "" if value is None else f"{value:.10g}"


def write_html_report(
    *,
    path: Path,
    bars: Sequence[PriceBar],
    result: MonitorResult,
    config: MonitorConfig,
    breakout_snapshots: Sequence[BreakoutSnapshot] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_html_report(
            bars=bars,
            result=result,
            config=config,
            breakout_snapshots=breakout_snapshots,
        ),
        encoding="utf-8",
    )


def render_html_report(
    *,
    bars: Sequence[PriceBar],
    result: MonitorResult,
    config: MonitorConfig,
    breakout_snapshots: Sequence[BreakoutSnapshot] = (),
) -> str:
    if bars and result.symbol != bars[0].symbol:
        raise ValueError("result symbol does not match chart bars")
    expected_rows = tuple(
        (
            item.symbol,
            item.trade_date,
            item.close,
            (
                item.official_traded_value_twd
                if item.official_traded_value_twd is not None
                else item.close * item.volume
            ),
        )
        for item in bars
    )
    actual_rows = tuple(
        (
            item.symbol,
            item.trade_date,
            item.close,
            item.features.trading_value,
        )
        for item in result.feature_rows
    )
    if actual_rows != expected_rows:
        raise ValueError("result feature rows or volume do not match chart bars")
    if result.parameter_version != config.parameter_version:
        raise ValueError("result parameter version does not match chart config")
    if result.parameter_hash != config.parameter_hash:
        raise ValueError("result parameter hash does not match chart config")
    if any(item.symbol != result.symbol for item in breakout_snapshots):
        raise ValueError("breakout snapshot symbol does not match monitor result")
    snapshot_by_date = {item.trade_date: item for item in result.snapshots}
    svg = _monitor_svg(bars, result, config, breakout_snapshots)
    current = result.snapshots[-1] if result.snapshots else None
    discovery = (
        f"{result.first_discovery_date.isoformat()} · {result.first_discovery_close:.2f}"
        if result.first_discovery_date is not None and result.first_discovery_close is not None
        else "尚未發現"
    )
    current_stage = current.stage.value if current else "UNDETECTED"
    current_risks = ", ".join(item.value for item in current.risk_flags) if current else "—"
    key_events = []
    seen_high_levels: set[str] = set()
    for event in result.events:
        if event.event_type is MonitorEventType.NEW_HIGH:
            if event.detail in seen_high_levels:
                continue
            seen_high_levels.add(event.detail)
        key_events.append(event)
    event_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(event.event_id)}</code></td>"
        f"<td>{event.trade_date.isoformat()}</td>"
        f"<td>{html.escape(event.event_type.value)}</td>"
        f"<td>{html.escape(event.detail)}</td>"
        f"<td><span class='stage' style='--stage:{STAGE_COLORS[event.stage]}'>{event.stage.value}</span></td>"
        f"<td>{event.close:.2f}</td>"
        "</tr>"
        for event in key_events
    ) or "<tr><td colspan='6'>尚無事件</td></tr>"

    latest_features = current.features if current else None
    high_label = (
        ", ".join(f"{value}D" for value in latest_features.new_high_windows)
        if latest_features and latest_features.new_high_windows
        else "—"
    )
    latest_extension = (
        f"{latest_features.ma_extension_pct * 100:.2f}%"
        if latest_features and latest_features.ma_extension_pct is not None
        else "—"
    )
    latest_volume = (
        f"{latest_features.volume_ratio:.2f}x"
        if latest_features and latest_features.volume_ratio is not None
        else "—"
    )
    symbol = html.escape(result.symbol or "NO SYMBOL")
    parameter_hash = html.escape(result.parameter_hash)

    return f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{symbol} Continuous High Monitor</title>
<style>
:root{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0f172a}}
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa}}main{{max-width:1280px;margin:auto;padding:26px 20px 60px}}
header,section{{background:#fff;border:1px solid #dce3ec;border-radius:16px;padding:22px;margin-bottom:17px}}
h1{{margin:6px 0}}h2{{margin:0 0 14px;font-size:1.15rem}}p{{color:#475569;line-height:1.65}}
.eye{{font-size:.74rem;font-weight:800;letter-spacing:.08em;color:#1d4ed8}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}}
.card{{border:1px solid #e2e8f0;border-radius:13px;padding:15px;background:#fbfdff}}.card h3{{font-size:.78rem;color:#64748b;margin:0 0 7px}}.metric{{font-weight:850;font-size:1.35rem}}
.chart,.table{{overflow:auto}}.chart svg{{min-width:960px;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:.82rem}}th,td{{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;white-space:nowrap}}th{{background:#f8fafc;color:#475569}}
.stage{{display:inline-block;border-left:5px solid var(--stage);padding-left:7px;font-weight:800}}code{{font-size:.72rem;background:#eef2f7;padding:2px 5px;border-radius:4px}}
.warn{{border-left:4px solid #d97706;background:#fffbeb;padding:13px 15px;border-radius:8px;color:#92400e}}.meta{{font-size:.78rem;word-break:break-all;color:#64748b}}
@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main>
<header>
<div class="eye">TWSTOCK EXPERIMENT · CONTINUOUS HIGH MONITOR v0.1</div>
<h1>{symbol} 強勢發展時間線</h1>
<p>提早觀察持續創高、階段變化與追價風險；可選擇疊加 Breakout Tracker v5 的 Pivot 突破事件。</p>
</header>
<section>
<div class="grid">
<div class="card"><h3>系統首次發現</h3><div class="metric">{discovery}</div></div>
<div class="card"><h3>目前階段</h3><div class="metric">{html.escape(current_stage)}</div></div>
<div class="card"><h3>今日新高層級</h3><div class="metric">{html.escape(high_label)}</div></div>
<div class="card"><h3>量比／均線延伸</h3><div class="metric">{latest_volume} / {latest_extension}</div></div>
</div>
<p class="warn"><strong>探索性研究：</strong>階段描述價格行為，不是買賣指令。現在風險標籤：{html.escape(current_risks)}</p>
</section>
<section><h2>每日價格、成交量與均線延伸</h2><div class="chart">{svg}</div></section>
<section>
<h2>關鍵事件時間線</h2>
<div class="table"><table><thead><tr><th>事件 ID</th><th>日期</th><th>類型</th><th>內容</th><th>階段</th><th>收盤</th></tr></thead><tbody>{event_rows}</tbody></table></div>
<p class="meta">畫面保留每個新高層級的首次達成，以及所有階段與風險轉換；完整的每日新高事件保存在 timeline.csv。</p>
</section>
<section>
<h2>參數與重現資訊</h2>
<p class="meta">參數版本：<strong>{html.escape(config.parameter_version)}</strong><br>參數 SHA-256：<code>{parameter_hash}</code><br>資料列：{len(bars)}；發現後快照：{len(snapshot_by_date)}；事件：{len(result.events)}</p>
<p class="meta">{html.escape(config.canonical_json())}</p>
</section>
</main></body></html>'''


def _monitor_svg(
    bars: Sequence[PriceBar],
    result: MonitorResult,
    config: MonitorConfig,
    breakout_snapshots: Sequence[BreakoutSnapshot],
) -> str:
    if len(bars) < 2:
        return "<p>資料不足，無法繪圖。</p>"
    width, height = 1180, 790
    left, right = 72, 28
    price_top, price_bottom = 35, 430
    volume_top, volume_bottom = 475, 610
    extension_top, extension_bottom = 660, 750
    plot_width = width - left - right
    index_by_date = {bar.trade_date: index for index, bar in enumerate(bars)}
    snapshots = {item.trade_date: item for item in result.snapshots}

    moving_averages = [
        item.features.moving_average
        for item in result.feature_rows
        if item.features.moving_average is not None
    ]
    prices = [item.close for item in bars] + moving_averages
    price_low = min(prices) * 0.96
    price_high = max(prices) * 1.04
    price_span = price_high - price_low or 1.0

    max_volume = max(item.volume for item in bars) or 1.0
    extension_values = [
        item.features.ma_extension_pct
        for item in result.feature_rows
        if item.features.ma_extension_pct is not None
    ] + [0.0, config.extension_pct]
    extension_low = min(extension_values) - 0.02
    extension_high = max(extension_values) + 0.02
    extension_span = extension_high - extension_low or 1.0

    def x(index: int) -> float:
        return left + index / (len(bars) - 1) * plot_width

    def price_y(value: float) -> float:
        return price_top + (price_high - value) / price_span * (price_bottom - price_top)

    def volume_y(value: float) -> float:
        return volume_bottom - value / max_volume * (volume_bottom - volume_top)

    def extension_y(value: float) -> float:
        return extension_top + (extension_high - value) / extension_span * (extension_bottom - extension_top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Continuous High Monitor daily timeline">',
        '<rect width="100%" height="100%" rx="14" fill="#fbfcfe"/>',
    ]
    for step in range(6):
        value = price_low + price_span * step / 5
        yy = price_y(value)
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left-8}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{value:.1f}</text>')

    price_path = " ".join(
        ("M" if index == 0 else "L") + f" {x(index):.1f} {price_y(bar.close):.1f}"
        for index, bar in enumerate(bars)
    )
    parts.append(f'<path d="{price_path}" fill="none" stroke="#0f172a" stroke-width="2.5"/>')

    ma_points = [
        (index_by_date[item.trade_date], item.features.moving_average)
        for item in result.feature_rows
        if item.features.moving_average is not None
    ]
    if ma_points:
        ma_path = " ".join(
            ("M" if point_index == 0 else "L") + f" {x(index):.1f} {price_y(value):.1f}"
            for point_index, (index, value) in enumerate(ma_points)
        )
        parts.append(f'<path d="{ma_path}" fill="none" stroke="#f59e0b" stroke-width="1.7" stroke-dasharray="6 4"/>')

    important_events = [
        event
        for event in result.events
        if event.event_type in (MonitorEventType.DISCOVERED, MonitorEventType.STAGE_CHANGED)
    ]
    for event in important_events:
        index = index_by_date[event.trade_date]
        color = STAGE_COLORS[event.stage]
        parts.append(
            f'<circle cx="{x(index):.1f}" cy="{price_y(event.close):.1f}" r="5" fill="{color}" stroke="#fff" stroke-width="2"><title>{html.escape(event.trade_date.isoformat())} · {html.escape(event.detail)} · {event.close:.2f}</title></circle>'
        )
    first_high_events = {}
    for event in result.events:
        if event.event_type is MonitorEventType.NEW_HIGH:
            first_high_events.setdefault(event.detail, event)
    new_high_dates = {event.trade_date for event in first_high_events.values()}
    for trade_date in sorted(new_high_dates):
        snapshot = snapshots[trade_date]
        index = index_by_date[trade_date]
        label = "/".join(f"{window}D" for window in snapshot.features.new_high_windows)
        px, py = x(index), price_y(snapshot.close)
        parts.append(
            f'<path d="M {px:.1f} {py-9:.1f} l -4 -7 l 8 0 z" fill="#2563eb"><title>{trade_date.isoformat()} · {html.escape(label)} closing high</title></path>'
        )
    for snapshot in breakout_snapshots:
        if snapshot.state is not BreakoutState.NEW_TRIGGER or snapshot.trade_date not in index_by_date:
            continue
        index = index_by_date[snapshot.trade_date]
        parts.append(
            f'<rect x="{x(index)-5:.1f}" y="{price_y(snapshot.close)-5:.1f}" width="10" height="10" fill="#7c3aed" transform="rotate(45 {x(index):.1f} {price_y(snapshot.close):.1f})"><title>{snapshot.trade_date.isoformat()} · PIVOT BREAKOUT</title></rect>'
        )

    for index, bar in enumerate(bars):
        color = "#60a5fa" if index == 0 or bar.close >= bars[index - 1].close else "#f87171"
        parts.append(
            f'<rect x="{x(index)-1.5:.1f}" y="{volume_y(bar.volume):.1f}" width="3" height="{volume_bottom-volume_y(bar.volume):.1f}" fill="{color}" opacity=".7"/>'
        )
    volume_average_points = []
    for item in result.feature_rows:
        ratio = item.features.volume_ratio
        if ratio is None or ratio <= 0:
            continue
        index = index_by_date[item.trade_date]
        volume_average_points.append((index, bars[index].volume / ratio))
    if volume_average_points:
        volume_path = " ".join(
            ("M" if point_index == 0 else "L") + f" {x(index):.1f} {volume_y(value):.1f}"
            for point_index, (index, value) in enumerate(volume_average_points)
        )
        parts.append(f'<path d="{volume_path}" fill="none" stroke="#1d4ed8" stroke-width="1.5"/>')

    zero_y = extension_y(0.0)
    threshold_y = extension_y(config.extension_pct)
    parts.append(f'<line x1="{left}" y1="{zero_y:.1f}" x2="{width-right}" y2="{zero_y:.1f}" stroke="#94a3b8"/>')
    parts.append(f'<line x1="{left}" y1="{threshold_y:.1f}" x2="{width-right}" y2="{threshold_y:.1f}" stroke="#f97316" stroke-dasharray="5 4"/>')
    extension_points = [
        (index_by_date[item.trade_date], item.features.ma_extension_pct)
        for item in result.feature_rows
        if item.features.ma_extension_pct is not None
    ]
    if extension_points:
        extension_path = " ".join(
            ("M" if point_index == 0 else "L") + f" {x(index):.1f} {extension_y(value):.1f}"
            for point_index, (index, value) in enumerate(extension_points)
        )
        parts.append(f'<path d="{extension_path}" fill="none" stroke="#ea580c" stroke-width="1.8"/>')

    label_step = max(1, len(bars) // 8)
    label_indices = list(range(0, len(bars), label_step))
    if label_indices[-1] != len(bars) - 1:
        label_indices.append(len(bars) - 1)
    for index in label_indices:
        parts.append(f'<text x="{x(index):.1f}" y="{height-12}" text-anchor="middle" font-size="11" fill="#64748b">{bars[index].trade_date:%Y-%m-%d}</text>')
    parts.extend(
        (
            f'<text x="{left}" y="20" font-size="12" font-weight="700" fill="#334155">收盤價 / MA{config.extension_ma_window}</text>',
            f'<text x="{left}" y="463" font-size="12" font-weight="700" fill="#334155">成交量 / 前{config.volume_average_window}日均量</text>',
            f'<text x="{left}" y="648" font-size="12" font-weight="700" fill="#334155">距 MA{config.extension_ma_window}（橘線門檻 {config.extension_pct:.0%}）</text>',
            '<text x="865" y="20" font-size="11" fill="#2563eb">▲ rolling high</text>',
            '<text x="970" y="20" font-size="11" fill="#7c3aed">◆ Pivot breakout</text>',
            '</svg>',
        )
    )
    return "".join(parts)
