from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPERIMENT_DIR = ROOT / "data/experiments/2330_pe_river"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/experiments/2330_pe_river"


class ExperimentInputError(ValueError):
    """Raised when an experiment input is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class EPSObservation:
    period: str
    period_end: date
    publication_date: date
    research_available_date: date
    diluted_eps_twd: Decimal
    data_status: str
    source_note: str
    source_url: str


@dataclass(frozen=True)
class PriceObservation:
    symbol: str
    name: str
    price_date: date
    close_twd: Decimal
    data_status: str
    source_note: str
    source_url: str


@dataclass(frozen=True)
class ForwardScenario:
    scenario: str
    ntm_eps_twd: Decimal
    exit_pe: Decimal
    assumption_status: str
    description: str


@dataclass(frozen=True)
class RiverSnapshot:
    label: str
    as_of_date: date
    reference_price_twd: Decimal
    included_periods: tuple[str, ...]
    ttm_eps_twd: Decimal
    pe_ttm: Decimal
    band_prices: dict[str, Decimal]
    price_gap_to_band_pct: dict[str, Decimal]


def _parse_date(raw: str, *, field: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ExperimentInputError(f"{field} must be ISO YYYY-MM-DD: {raw!r}") from exc


def _decimal(raw: str, *, field: str, positive: bool = True) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ExperimentInputError(f"{field} must be a decimal number: {raw!r}") from exc
    if not value.is_finite():
        raise ExperimentInputError(f"{field} must be finite")
    if positive and value <= 0:
        raise ExperimentInputError(f"{field} must be positive")
    return value


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ExperimentInputError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ExperimentInputError(f"CSV has no header: {path}")
        rows = list(reader)
    if not rows:
        raise ExperimentInputError(f"CSV has no data rows: {path}")
    return rows


def load_eps_history(path: Path) -> list[EPSObservation]:
    observations: list[EPSObservation] = []
    seen_periods: set[str] = set()
    for row_number, row in enumerate(_read_rows(path), start=2):
        period = row.get("period", "").strip()
        if not period:
            raise ExperimentInputError(f"Row {row_number}: period is required")
        if period in seen_periods:
            raise ExperimentInputError(f"Row {row_number}: duplicate period {period}")
        seen_periods.add(period)
        period_end = _parse_date(row.get("period_end", ""), field="period_end")
        publication_date = _parse_date(
            row.get("publication_date", ""), field="publication_date"
        )
        available = _parse_date(
            row.get("research_available_date", ""), field="research_available_date"
        )
        if publication_date < period_end:
            raise ExperimentInputError(
                f"Row {row_number}: publication_date cannot precede period_end"
            )
        if available < publication_date:
            raise ExperimentInputError(
                f"Row {row_number}: research_available_date cannot precede publication_date"
            )
        observations.append(
            EPSObservation(
                period=period,
                period_end=period_end,
                publication_date=publication_date,
                research_available_date=available,
                diluted_eps_twd=_decimal(
                    row.get("diluted_eps_twd", ""), field="diluted_eps_twd"
                ),
                data_status=row.get("data_status", "").strip() or "UNKNOWN",
                source_note=row.get("source_note", "").strip(),
                source_url=row.get("source_url", "").strip(),
            )
        )
    return sorted(observations, key=lambda item: item.period_end)


def load_price(path: Path) -> PriceObservation:
    rows = _read_rows(path)
    if len(rows) != 1:
        raise ExperimentInputError("reference_price.csv must contain exactly one row")
    row = rows[0]
    symbol = row.get("symbol", "").strip()
    if not symbol:
        raise ExperimentInputError("symbol is required")
    return PriceObservation(
        symbol=symbol,
        name=row.get("name", "").strip() or symbol,
        price_date=_parse_date(row.get("price_date", ""), field="price_date"),
        close_twd=_decimal(row.get("close_twd", ""), field="close_twd"),
        data_status=row.get("data_status", "").strip() or "UNKNOWN",
        source_note=row.get("source_note", "").strip(),
        source_url=row.get("source_url", "").strip(),
    )


def load_multiples(path: Path) -> tuple[Decimal, ...]:
    values = tuple(
        _decimal(row.get("pe_multiple", ""), field="pe_multiple")
        for row in _read_rows(path)
    )
    if len(values) < 2:
        raise ExperimentInputError("At least two PE multiples are required")
    if tuple(sorted(set(values))) != values:
        raise ExperimentInputError("PE multiples must be unique and strictly ascending")
    return values


def load_scenarios(path: Path) -> list[ForwardScenario]:
    scenarios: list[ForwardScenario] = []
    seen: set[str] = set()
    for row_number, row in enumerate(_read_rows(path), start=2):
        name = row.get("scenario", "").strip().upper()
        if not name:
            raise ExperimentInputError(f"Row {row_number}: scenario is required")
        if name in seen:
            raise ExperimentInputError(f"Row {row_number}: duplicate scenario {name}")
        seen.add(name)
        scenarios.append(
            ForwardScenario(
                scenario=name,
                ntm_eps_twd=_decimal(row.get("ntm_eps_twd", ""), field="ntm_eps_twd"),
                exit_pe=_decimal(row.get("exit_pe", ""), field="exit_pe"),
                assumption_status=row.get("assumption_status", "").strip()
                or "UNCLASSIFIED_ASSUMPTION",
                description=row.get("description", "").strip(),
            )
        )
    return scenarios


def ttm_eps_as_of(
    observations: Iterable[EPSObservation], as_of_date: date
) -> tuple[Decimal, tuple[str, ...]]:
    eligible = [
        item for item in observations if item.research_available_date <= as_of_date
    ]
    eligible.sort(key=lambda item: item.period_end)
    if len(eligible) < 4:
        raise ExperimentInputError(
            f"Need four PIT-available EPS observations as of {as_of_date}; got {len(eligible)}"
        )
    selected = eligible[-4:]
    return (
        sum((item.diluted_eps_twd for item in selected), Decimal("0")),
        tuple(item.period for item in selected),
    )


def build_snapshot(
    *,
    label: str,
    as_of_date: date,
    reference_price: Decimal,
    observations: Iterable[EPSObservation],
    multiples: Iterable[Decimal],
) -> RiverSnapshot:
    ttm_eps, periods = ttm_eps_as_of(observations, as_of_date)
    band_prices = {str(value): ttm_eps * value for value in multiples}
    gaps = {
        multiple: (reference_price / band_price - Decimal("1")) * Decimal("100")
        for multiple, band_price in band_prices.items()
    }
    return RiverSnapshot(
        label=label,
        as_of_date=as_of_date,
        reference_price_twd=reference_price,
        included_periods=periods,
        ttm_eps_twd=ttm_eps,
        pe_ttm=reference_price / ttm_eps,
        band_prices=band_prices,
        price_gap_to_band_pct=gaps,
    )


def build_analysis(
    *,
    price: PriceObservation,
    observations: list[EPSObservation],
    multiples: tuple[Decimal, ...],
    scenarios: list[ForwardScenario],
    pre_as_of: date,
    post_as_of: date,
) -> dict[str, object]:
    if pre_as_of > post_as_of:
        raise ExperimentInputError("pre_as_of cannot be after post_as_of")
    pre = build_snapshot(
        label="PRE_RELEASE",
        as_of_date=pre_as_of,
        reference_price=price.close_twd,
        observations=observations,
        multiples=multiples,
    )
    post = build_snapshot(
        label="POST_RELEASE",
        as_of_date=post_as_of,
        reference_price=price.close_twd,
        observations=observations,
        multiples=multiples,
    )

    forward = []
    for item in scenarios:
        target = item.ntm_eps_twd * item.exit_pe
        forward.append(
            {
                **asdict(item),
                "target_price_twd": target,
                "expected_price_return_pct":
                    (target / price.close_twd - Decimal("1")) * Decimal("100"),
            }
        )

    implied = [
        {
            "pe_multiple": multiple,
            "implied_eps_twd": price.close_twd / multiple,
            "growth_vs_post_ttm_pct":
                ((price.close_twd / multiple) / post.ttm_eps_twd - Decimal("1"))
                * Decimal("100"),
        }
        for multiple in multiples
    ]

    return {
        "experiment_id": "TW-EXP-2330-PE-RIVER-0001",
        "experiment_status": "EXPLORATORY_NOT_VALIDATED",
        "symbol": price.symbol,
        "name": price.name,
        "reference_price": asdict(price),
        "pre_release": asdict(pre),
        "post_release": asdict(post),
        "ttm_eps_change_pct":
            (post.ttm_eps_twd / pre.ttm_eps_twd - Decimal("1")) * Decimal("100"),
        "pe_change": post.pe_ttm - pre.pe_ttm,
        "forward_scenarios": forward,
        "implied_eps": implied,
        "method_notes": [
            "Every EPS observation is gated by research_available_date before entering TTM EPS.",
            "The same reference close is used before and after the earnings release to isolate the EPS update effect; the post-release snapshot is not a tradable historical price observation.",
            "Forward scenarios are editable manual assumptions, not analyst consensus and not forecasts produced by this program.",
            "No buy, sell, target-price recommendation, or validated alpha claim is produced.",
        ],
    }


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def write_json_report(analysis: dict[str, object], path: Path) -> None:
    path.write_text(
        json.dumps(_json_value(analysis), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _fmt_decimal(value: object, digits: int = 2) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantum = Decimal("1").scaleb(-digits)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), f".{digits}f")


def write_valuation_ladder(analysis: dict[str, object], path: Path) -> None:
    pre = analysis["pre_release"]
    post = analysis["post_release"]
    assert isinstance(pre, dict) and isinstance(post, dict)
    pre_bands = pre["band_prices"]
    post_bands = post["band_prices"]
    pre_gaps = pre["price_gap_to_band_pct"]
    post_gaps = post["price_gap_to_band_pct"]
    assert isinstance(pre_bands, dict) and isinstance(post_bands, dict)
    assert isinstance(pre_gaps, dict) and isinstance(post_gaps, dict)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "pe_multiple",
                "pre_release_band_price_twd",
                "post_release_band_price_twd",
                "pre_release_price_gap_pct",
                "post_release_price_gap_pct",
            ),
        )
        writer.writeheader()
        for multiple in pre_bands:
            writer.writerow(
                {
                    "pe_multiple": multiple,
                    "pre_release_band_price_twd": _fmt_decimal(pre_bands[multiple]),
                    "post_release_band_price_twd": _fmt_decimal(post_bands[multiple]),
                    "pre_release_price_gap_pct": _fmt_decimal(pre_gaps[multiple]),
                    "post_release_price_gap_pct": _fmt_decimal(post_gaps[multiple]),
                }
            )


def _pill(text: str, css_class: str = "neutral") -> str:
    return f'<span class="pill {css_class}">{html.escape(text)}</span>'


def _river_svg(
    pre: dict[str, object], post: dict[str, object], price: Decimal
) -> str:
    pre_bands = pre["band_prices"]
    post_bands = post["band_prices"]
    assert isinstance(pre_bands, dict) and isinstance(post_bands, dict)
    multiples = list(pre_bands.keys())
    values = [Decimal(str(value)) for value in pre_bands.values()] + [
        Decimal(str(value)) for value in post_bands.values()
    ] + [price]
    min_value = min(values) * Decimal("0.92")
    max_value = max(values) * Decimal("1.06")
    width, height = 860, 430
    left, right, top, bottom = 80, 50, 35, 65
    x_pre, x_post = 260, 620

    def y(value: Decimal) -> float:
        usable = height - top - bottom
        return float(top + (max_value - value) / (max_value - min_value) * Decimal(usable))

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="PIT PE river bridge">',
        '<rect width="100%" height="100%" rx="16" fill="#fbfcfe"/>',
    ]
    for step in range(6):
        value = min_value + (max_value - min_value) * Decimal(step) / Decimal(5)
        yy = y(value)
        parts.append(
            f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="#e8ecf2"/>'
        )
        parts.append(
            f'<text x="{left-10}" y="{yy+4:.2f}" text-anchor="end" font-size="12" fill="#6b7280">{_fmt_decimal(value, 0)}</text>'
        )

    band_colors = ["#dbeafe", "#bfdbfe", "#93c5fd"]
    for index in range(len(multiples) - 1):
        low, high = multiples[index], multiples[index + 1]
        points = [
            f"{x_pre},{y(Decimal(str(pre_bands[low]))):.2f}",
            f"{x_pre},{y(Decimal(str(pre_bands[high]))):.2f}",
            f"{x_post},{y(Decimal(str(post_bands[high]))):.2f}",
            f"{x_post},{y(Decimal(str(post_bands[low]))):.2f}",
        ]
        color = band_colors[min(index, len(band_colors) - 1)]
        parts.append(
            f'<polygon points="{" ".join(points)}" fill="{color}" opacity="0.68"/>'
        )

    for multiple in multiples:
        y1 = y(Decimal(str(pre_bands[multiple])))
        y2 = y(Decimal(str(post_bands[multiple])))
        parts.append(
            f'<line x1="{x_pre}" y1="{y1:.2f}" x2="{x_post}" y2="{y2:.2f}" stroke="#2563eb" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x_post+12}" y="{y2+4:.2f}" font-size="12" fill="#1d4ed8">{html.escape(multiple)}x · {_fmt_decimal(post_bands[multiple], 0)}</text>'
        )

    price_y = y(price)
    parts.append(
        f'<line x1="{left}" y1="{price_y:.2f}" x2="{width-right}" y2="{price_y:.2f}" stroke="#dc2626" stroke-width="3" stroke-dasharray="9 6"/>'
    )
    parts.append(
        f'<text x="{left}" y="{price_y-10:.2f}" font-size="13" font-weight="700" fill="#b91c1c">Reference close {_fmt_decimal(price, 0)}</text>'
    )
    parts.extend(
        [
            f'<text x="{x_pre}" y="{height-30}" text-anchor="middle" font-size="14" font-weight="700" fill="#111827">Before 2026Q2 usable</text>',
            f'<text x="{x_post}" y="{height-30}" text-anchor="middle" font-size="14" font-weight="700" fill="#111827">After 2026Q2 usable</text>',
            '<text x="18" y="215" transform="rotate(-90 18 215)" text-anchor="middle" font-size="12" fill="#6b7280">TWD price implied by TTM EPS × PE</text>',
            '</svg>',
        ]
    )
    return "".join(parts)


def write_html_report(analysis: dict[str, object], path: Path) -> None:
    price = analysis["reference_price"]
    pre = analysis["pre_release"]
    post = analysis["post_release"]
    forward = analysis["forward_scenarios"]
    implied = analysis["implied_eps"]
    assert isinstance(price, dict) and isinstance(pre, dict) and isinstance(post, dict)
    assert isinstance(forward, list) and isinstance(implied, list)
    close = Decimal(str(price["close_twd"]))
    pre_ttm = Decimal(str(pre["ttm_eps_twd"]))
    post_ttm = Decimal(str(post["ttm_eps_twd"]))
    pre_pe = Decimal(str(pre["pe_ttm"]))
    post_pe = Decimal(str(post["pe_ttm"]))
    ttm_change = Decimal(str(analysis["ttm_eps_change_pct"]))

    forward_rows = []
    for item in forward:
        assert isinstance(item, dict)
        expected_return = Decimal(str(item["expected_price_return_pct"]))
        return_class = "positive" if expected_return >= 0 else "negative"
        forward_rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(item['scenario']))}</strong></td>"
            f"<td>{_fmt_decimal(item['ntm_eps_twd'])}</td>"
            f"<td>{_fmt_decimal(item['exit_pe'])}x</td>"
            f"<td>{_fmt_decimal(item['target_price_twd'], 0)}</td>"
            f'<td class="{return_class}">{_fmt_decimal(expected_return)}%</td>'
            f"<td>{_pill(str(item['assumption_status']), 'warning')}</td>"
            f"<td>{html.escape(str(item['description']))}</td>"
            "</tr>"
        )

    implied_rows = []
    for item in implied:
        assert isinstance(item, dict)
        implied_rows.append(
            "<tr>"
            f"<td>{_fmt_decimal(item['pe_multiple'])}x</td>"
            f"<td>{_fmt_decimal(item['implied_eps_twd'])}</td>"
            f"<td>{_fmt_decimal(item['growth_vs_post_ttm_pct'])}%</td>"
            "</tr>"
        )

    source_rows = []
    for item in analysis.get("eps_observations", []):
        assert isinstance(item, dict)
        source_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item['period']))}</td>"
            f"<td>{_fmt_decimal(item['diluted_eps_twd'])}</td>"
            f"<td>{html.escape(str(item['publication_date']))}</td>"
            f"<td>{html.escape(str(item['research_available_date']))}</td>"
            f"<td>{_pill(str(item['data_status']), 'good')}</td>"
            f"<td>{html.escape(str(item['source_note']))}</td>"
            "</tr>"
        )

    pre_periods = " → ".join(str(item) for item in pre["included_periods"])
    post_periods = " → ".join(str(item) for item in post["included_periods"])
    notes = "".join(
        f"<li>{html.escape(str(note))}</li>" for note in analysis["method_notes"]
    )

    document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2330 PE River Experiment</title>
<style>
:root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f3f6fa; color: #111827; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 30px 22px 56px; }}
header, section {{ background: #fff; border: 1px solid #dce3ec; border-radius: 16px; padding: 24px; margin-bottom: 18px; box-shadow: 0 6px 20px rgba(15,23,42,.04); }}
h1 {{ margin: 8px 0; font-size: 2rem; }} h2 {{ margin: 0 0 16px; font-size: 1.25rem; }} h3 {{ margin: 0 0 8px; font-size: .95rem; color: #475569; }}
p {{ color: #475569; line-height: 1.65; }}
.eyebrow {{ color: #1d4ed8; font-weight: 800; letter-spacing: .08em; font-size: .75rem; }}
.pill {{ display: inline-block; border-radius: 999px; padding: 4px 9px; font-size: .72rem; font-weight: 800; background: #eef2f7; color: #475569; }}
.pill.good {{ background: #dcfce7; color: #166534; }} .pill.warning {{ background: #fef3c7; color: #92400e; }} .pill.danger {{ background: #fee2e2; color: #991b1b; }}
.status-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 14px; }}
.card {{ border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; background: #fbfdff; }}
.metric {{ font-size: 1.7rem; font-weight: 800; margin: 5px 0; }} .muted {{ color: #64748b; font-size: .84rem; line-height: 1.5; }}
.callout {{ border-left: 4px solid #2563eb; background: #eff6ff; padding: 14px 16px; border-radius: 8px; color: #1e3a8a; line-height: 1.65; }}
.chart {{ overflow-x: auto; }} .chart svg {{ min-width: 760px; width: 100%; height: auto; }} .table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }} th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; white-space: nowrap; }} th {{ color: #475569; background: #f8fafc; }} td:last-child {{ white-space: normal; min-width: 220px; }}
.positive {{ color: #047857; font-weight: 800; }} .negative {{ color: #b91c1c; font-weight: 800; }} ul {{ color: #475569; line-height: 1.7; }}
@media (max-width: 820px) {{ .grid {{ grid-template-columns: repeat(2,minmax(0,1fr)); }} }} @media (max-width: 520px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 18px 12px 36px; }} }}
</style>
</head>
<body><main>
<header>
<div class="eyebrow">TWSTOCK EXPERIMENT · TW-EXP-2330-PE-RIVER-0001</div>
<h1>2330.TW 本益比河流｜Point-in-Time 原型</h1>
<p>把傳統河流圖改造成可檢查的研究畫面：實際已公告 EPS、資訊可用日、TTM 河流更新、Forward 情境及市場隱含 EPS 分開呈現。</p>
<div class="status-row">{_pill('EXPLORATORY_NOT_VALIDATED','danger')}{_pill('OFFICIAL EPS ACTUALS','good')}{_pill('MANUAL FORWARD ASSUMPTIONS','warning')}{_pill(str(price['data_status']))}</div>
</header>
<section>
<h2>本次實驗最重要的具體結果</h2>
<div class="grid">
<div class="card"><h3>參考收盤價</h3><div class="metric">NT$ {_fmt_decimal(close,0)}</div><div class="muted">{html.escape(str(price['price_date']))}<br>{html.escape(str(price['source_note']))}</div></div>
<div class="card"><h3>法說前可用 TTM EPS</h3><div class="metric">{_fmt_decimal(pre_ttm)}</div><div class="muted">P/E {_fmt_decimal(pre_pe)}x<br>{html.escape(pre_periods)}</div></div>
<div class="card"><h3>Q2 可用後 TTM EPS</h3><div class="metric">{_fmt_decimal(post_ttm)}</div><div class="muted">P/E {_fmt_decimal(post_pe)}x<br>{html.escape(post_periods)}</div></div>
<div class="card"><h3>單次 EPS 更新效果</h3><div class="metric">+{_fmt_decimal(ttm_change)}%</div><div class="muted">固定同一參考價格下，P/E 由 {_fmt_decimal(pre_pe)}x 降至 {_fmt_decimal(post_pe)}x</div></div>
</div>
<p class="callout"><strong>解讀：</strong>股價不變，只把 2026Q2 EPS 納入可用資訊後，28x 河流價由 NT$ {_fmt_decimal(pre['band_prices']['28'],0)} 上移至 NT$ {_fmt_decimal(post['band_prices']['28'],0)}；股價高於 28x 河流的幅度由 {_fmt_decimal(pre['price_gap_to_band_pct']['28'])}% 降至 {_fmt_decimal(post['price_gap_to_band_pct']['28'])}%。這就是「盈餘追趕股價」的可視化。</p>
</section>
<section><h2>TTM 河流更新橋接圖</h2><div class="chart">{_river_svg(pre, post, close)}</div><p class="muted">刻意使用同一個 2026-07-16 收盤價隔離財報資訊更新影響；右側不是 2026-07-17 的實際成交結果。</p></section>
<section><h2>Forward 情境：把河流轉成預期報酬</h2><div class="table-wrap"><table><thead><tr><th>情境</th><th>NTM EPS</th><th>出場 P/E</th><th>情境價</th><th>價格報酬</th><th>資料性質</th><th>說明</th></tr></thead><tbody>{''.join(forward_rows)}</tbody></table></div><p class="muted">數值是可編輯測試假設，不是法人共識、不是本系統預測，也不是目標價。</p></section>
<section><h2>反推市場要求：目前價格需要多少 EPS？</h2><div class="table-wrap"><table><thead><tr><th>假設合理 P/E</th><th>股價隱含 EPS</th><th>相對最新 TTM EPS 必要成長</th></tr></thead><tbody>{''.join(implied_rows)}</tbody></table></div></section>
<section><h2>資料與 Point-in-Time 邊界</h2><div class="table-wrap"><table><thead><tr><th>季度</th><th>稀釋 EPS</th><th>公告日</th><th>研究可用日</th><th>狀態</th><th>來源</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div><ul>{notes}</ul></section>
<section><h2>下一步應調整什麼</h2><p>先用這個畫面確認最重視的決策問題，再依序加入：① 歷史 Forward P/E 百分位；② 盈餘上修／下修；③ 月營收與毛利率驗證；④ 技術與相對動能；⑤ Point-in-Time 回測。每增加一層，都必須保留資料來源與可用日。</p></section>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def run(
    *,
    eps_path: Path,
    price_path: Path,
    multiples_path: Path,
    scenarios_path: Path,
    output_dir: Path,
    pre_as_of: date,
    post_as_of: date,
) -> dict[str, object]:
    observations = load_eps_history(eps_path)
    price = load_price(price_path)
    multiples = load_multiples(multiples_path)
    scenarios = load_scenarios(scenarios_path)
    analysis = build_analysis(
        price=price,
        observations=observations,
        multiples=multiples,
        scenarios=scenarios,
        pre_as_of=pre_as_of,
        post_as_of=post_as_of,
    )
    analysis["eps_observations"] = [asdict(item) for item in observations]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_report(analysis, output_dir / "analysis.json")
    write_valuation_ladder(analysis, output_dir / "valuation_ladder.csv")
    write_html_report(analysis, output_dir / "report.html")
    return analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the exploratory Point-in-Time PE river report."
    )
    parser.add_argument("--eps", type=Path, default=DEFAULT_EXPERIMENT_DIR / "eps_history.csv")
    parser.add_argument("--price", type=Path, default=DEFAULT_EXPERIMENT_DIR / "reference_price.csv")
    parser.add_argument("--multiples", type=Path, default=DEFAULT_EXPERIMENT_DIR / "river_multiples.csv")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_EXPERIMENT_DIR / "forward_scenarios.csv")
    parser.add_argument("--pre-as-of", type=lambda raw: _parse_date(raw, field="pre_as_of"), default=date(2026, 7, 16))
    parser.add_argument("--post-as-of", type=lambda raw: _parse_date(raw, field="post_as_of"), default=date(2026, 7, 17))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        analysis = run(
            eps_path=args.eps,
            price_path=args.price,
            multiples_path=args.multiples,
            scenarios_path=args.scenarios,
            output_dir=args.output_dir,
            pre_as_of=args.pre_as_of,
            post_as_of=args.post_as_of,
        )
    except ExperimentInputError as exc:
        parser.error(str(exc))
    print(f"Experiment: {analysis['experiment_id']}")
    print(f"Status: {analysis['experiment_status']}")
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
