from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import json
import math
from pathlib import Path
import textwrap
from typing import Any, Iterable

import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .models import ClassificationResult, SecurityData


DISCLAIMER = "Research / Shadow Model. Not investment advice. Provisional PIT, secondary-source adjusted-return, and survivorship limitations apply."


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _flat_result(result: ClassificationResult) -> dict[str, Any]:
    record: dict[str, Any] = {
        "symbol": result.symbol,
        "company": result.company,
        "industry": result.industry,
        "sector_logic": result.sector_logic,
        "as_of_date": result.as_of_date,
        "period_end": result.period_end,
        "quality": result.quality,
        "fundamental_state": result.fundamental_state,
        "valuation": result.valuation,
        "research_classification": result.research_classification,
        "data_quality": result.data_quality,
        "quality_reasons": " | ".join(result.quality_reasons),
        "fundamental_reasons": " | ".join(result.fundamental_reasons),
        "valuation_reasons": " | ".join(result.valuation_reasons),
        "reason_codes": " | ".join(result.reason_codes),
        "data_quality_flags": " | ".join(result.data_quality_flags),
    }
    record.update(result.metrics)
    record.update({f"intrinsic_{key}": value for key, value in result.intrinsic_value.items()})
    if result.pit_metadata:
        record.update({f"pit_{key}": value for key, value in result.pit_metadata.__dict__.items()})
    return record


def write_current_csv(results: Iterable[ClassificationResult], path: Path) -> None:
    records = [_flat_result(result) for result in results]
    fields = list(dict.fromkeys(key for record in records for key in record))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_json_bundle(
    results: list[ClassificationResult],
    securities: list[SecurityData],
    events: pd.DataFrame,
    baselines: pd.DataFrame,
    state_validation: pd.DataFrame,
    quality_persistence: pd.DataFrame,
    config: dict[str, Any],
    path: Path,
) -> None:
    payload = {
        "model": {
            "model_id": config["model_id"],
            "version": config["model_version"],
            "status": config["status"],
            "as_of_date": config["as_of_date"],
            "claim_boundary": {
                "analysis_quality": "evaluated separately through state recognition and persistence",
                "investment_prediction": "not established; return evidence is provisional",
            },
        },
        "limitations": [
            "SURVIVORSHIP_BIAS_PRESENT: historical runs use the current 0050 universe",
            "AVAILABLE_DATE_PROXY: FinMind rows do not include verified filing timestamps",
            "Return calculations prefer Yahoo adjusted close; raw prices are retained and source quality is flagged per security",
            "Peer valuation and financial-sector NIM/NPL/capital adequacy are not available in v0.1 data",
            "Frozen Technical v0.6 output was not present in the repository and was not recreated or changed",
        ],
        "current_results": [result.to_dict() for result in results],
        "quarterly_financials": [
            {
                "symbol": security.symbol,
                "company": security.company,
                "sector_logic": security.sector_logic.value,
                "records": security.quarterly.to_dict(orient="records"),
            }
            for security in securities
        ],
        "backtest_events": events.to_dict(orient="records"),
        "baseline_summary": baselines.to_dict(orient="records"),
        "state_validation_summary": state_validation.to_dict(orient="records"),
        "quality_persistence_summary": quality_persistence.to_dict(orient="records"),
        "config": config,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_quarterly_csv(securities: Iterable[SecurityData], path: Path) -> None:
    frames: list[pd.DataFrame] = []
    for security in securities:
        frame = security.quarterly.copy()
        frame.insert(0, "sector_logic", security.sector_logic.value)
        frame.insert(0, "company", security.company)
        frame.insert(0, "symbol", security.symbol)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False, encoding="utf-8-sig")


def _configure_font(font_path: Path | None) -> None:
    if font_path and font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        family = font_manager.FontProperties(fname=str(font_path)).get_name()
        plt.rcParams["font.family"] = family
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False


def _fmt(value: object, percent: bool = False) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(parsed):
        return "—"
    return f"{parsed:.1%}" if percent else f"{parsed:,.2f}"


def _footer(fig: plt.Figure, page_label: str) -> None:
    fig.text(0.01, 0.008, DISCLAIMER, fontsize=7, color="#666666")
    fig.text(0.99, 0.008, page_label, fontsize=7, color="#666666", ha="right")


def _distribution_page(pdf: PdfPages, results: list[ClassificationResult], config: dict[str, Any]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10.5))
    fig.suptitle("0050 Fundamental Quality & Valuation Model v0.1 — Executive Summary", fontsize=18, weight="bold")
    dimensions = [
        ("Quality", [result.quality for result in results]),
        ("Fundamental State", [result.fundamental_state for result in results]),
        ("Valuation", [result.valuation for result in results]),
        ("Research Classification", [result.research_classification for result in results]),
    ]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"]
    for axis, (title, values), color in zip(axes.flat, dimensions, colors):
        counts = Counter(values)
        labels = list(counts)
        axis.barh(labels, [counts[label] for label in labels], color=color, alpha=0.85)
        axis.set_title(title)
        axis.set_xlabel("Companies")
        for index, label in enumerate(labels):
            axis.text(counts[label] + 0.2, index, str(counts[label]), va="center", fontsize=9)
    fig.text(
        0.5,
        0.045,
        "Current constituents only. Historical tests carry survivorship bias, conservative filing-date proxies, and secondary-source adjusted returns.\n"
        "No Fundamental Score, Quality Score, Technical Score, Total Score, or weighted ranking is produced.",
        ha="center",
        fontsize=10,
        color="#8b0000",
    )
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.94))
    _footer(fig, f"As of {config['as_of_date']}")
    pdf.savefig(fig)
    plt.close(fig)


def _matrix_pages(pdf: PdfPages, results: list[ClassificationResult]) -> None:
    ordered = sorted(results, key=lambda item: (item.quality, item.fundamental_state, item.valuation, item.symbol))
    page_size = 17
    total_pages = math.ceil(len(ordered) / page_size)
    for page, start in enumerate(range(0, len(ordered), page_size), start=1):
        selected = ordered[start : start + page_size]
        fig, axis = plt.subplots(figsize=(16, 10.5))
        axis.axis("off")
        axis.set_title("0050 Current State Matrix (no composite score)", fontsize=17, weight="bold", pad=18)
        columns = ["Ticker", "Company", "Logic", "Quality", "State", "Valuation", "Research class", "Rev YoY", "EPS YoY", "FCF bn", "P/E", "P/B", "ROE", "ROIC", "Data"]
        cells = []
        for result in selected:
            m = result.metrics
            cells.append(
                [
                    result.symbol,
                    result.company,
                    result.sector_logic,
                    result.quality,
                    result.fundamental_state.replace("_", "\n"),
                    result.valuation,
                    result.research_classification.replace("_", "\n"),
                    _fmt(m.get("revenue_yoy"), True),
                    _fmt(m.get("eps_yoy"), True),
                    _fmt((m.get("ttm_fcf") / 1e9) if m.get("ttm_fcf") is not None else None),
                    _fmt(m.get("pe")),
                    _fmt(m.get("pb")),
                    _fmt(m.get("roe"), True),
                    _fmt(m.get("roic"), True),
                    result.data_quality,
                ]
            )
        table = axis.table(
            cellText=cells,
            colLabels=columns,
            loc="center",
            cellLoc="left",
            colWidths=[0.045, 0.075, 0.058, 0.06, 0.085, 0.06, 0.105, 0.055, 0.055, 0.055, 0.045, 0.045, 0.05, 0.05, 0.06],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(6.2)
        table.scale(1, 2.05)
        for (row, _), cell in table.get_celld().items():
            if row == 0:
                cell.set_facecolor("#d9eaf7")
                cell.set_text_props(weight="bold")
        _footer(fig, f"Matrix {page}/{total_pages}")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


STATE_COLORS = {
    "DETERIORATING": "#d62728",
    "BOTTOMING": "#ff7f0e",
    "TURNING_UP": "#2ca02c",
    "CONFIRMED_GROWTH": "#1f77b4",
    "MATURE_GROWTH": "#9467bd",
    "DECELERATING": "#8c564b",
    "UNKNOWN": "#7f7f7f",
}


def _plot_series_or_message(
    axis: Any,
    dates: pd.Series,
    series: list[tuple[pd.Series, str, str]],
    title: str,
    message: str = "Not applicable or unavailable",
) -> bool:
    available = False
    for values, label, color in series:
        numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
        if numeric.notna().any():
            axis.plot(dates, numeric, label=label, color=color)
            available = True
    axis.set_title(title)
    if available:
        axis.legend(fontsize=6)
    else:
        axis.axis("off")
        axis.text(0.5, 0.5, message, ha="center", va="center", color="#6b7280", transform=axis.transAxes)
        axis.set_title(title)
    return available


def _plot_security_page(
    pdf: PdfPages,
    security: SecurityData,
    result: ClassificationResult,
    events: pd.DataFrame,
) -> None:
    q = security.quarterly.copy()
    market = security.market.copy()
    cutoff = date.fromisoformat(result.as_of_date)
    q = q[q["period_end"] >= date(cutoff.year - 10, cutoff.month, min(cutoff.day, 28))]
    market = market[market["date"] >= date(cutoff.year - 10, cutoff.month, min(cutoff.day, 28))]
    fig, axes = plt.subplots(4, 2, figsize=(16, 10.5))
    fig.suptitle(
        f"{result.symbol} {result.company} | {result.quality} × {result.fundamental_state} × {result.valuation}",
        fontsize=15,
        weight="bold",
    )
    axes = axes.flat
    dates = pd.to_datetime(market["date"])
    _plot_series_or_message(axes[0], dates, [(market["close"], "Close", "#1f2937")], "1. Price + fundamental-state transitions")
    stock_events = events[events["symbol"] == security.symbol] if not events.empty else pd.DataFrame()
    for _, event in stock_events.iterrows():
        if event["fundamental_state"] in ("UNKNOWN",) or event["signal_date"] < str(q["available_date"].min()):
            continue
        axes[0].axvline(pd.Timestamp(event["signal_date"]), color=STATE_COLORS.get(event["fundamental_state"], "gray"), alpha=0.18, lw=0.8)

    qdates = pd.to_datetime(q["period_end"])
    if len(q) < 12:
        for axis in axes[1:]:
            axis.axis("off")
        axes[3].text(
            0.5,
            0.55,
            f"INSUFFICIENT FINANCIAL HISTORY\n{len(q)} PIT-available quarterly observations; at least 12 are required for quality classification.",
            ha="center",
            va="center",
            fontsize=14,
            color="#8b0000",
            weight="bold",
            transform=axes[3].transAxes,
        )
        axes[5].text(
            0.5,
            0.55,
            "Known observations remain in the CSV/JSON bundle.\nSparse series are intentionally not connected into potentially misleading charts.",
            ha="center",
            va="center",
            fontsize=11,
            color="#4b5563",
            transform=axes[5].transAxes,
        )
    else:
        revenue_available = _plot_series_or_message(
            axes[1], qdates, [(q["ttm_revenue"] / 1e9, "TTM Revenue (NT$bn)", "#1f77b4")], "2. Revenue / revenue growth"
        )
        if revenue_available and pd.to_numeric(q["revenue_yoy"], errors="coerce").notna().any():
            twin = axes[1].twinx()
            twin.plot(qdates, q["revenue_yoy"] * 100, color="#ff7f0e", label="YoY %", alpha=0.75)
            twin.legend(loc="upper right", fontsize=6)

        _plot_series_or_message(
            axes[2], qdates, [(q["eps"], "Quarter EPS", "#9ca3af"), (q["ttm_eps"], "TTM EPS", "#2ca02c")], "3. EPS / TTM EPS"
        )

        _plot_series_or_message(
            axes[3], qdates, [(q["gross_margin"] * 100, "Gross margin", "#1f77b4"), (q["operating_margin"] * 100, "Operating margin", "#ff7f0e")], "4. Margins (%)",
            "Not applicable for the available financial-sector schema",
        )

        _plot_series_or_message(
            axes[4], qdates, [(q["roe"] * 100, "ROE", "#1f77b4"), (q["roic"] * 100, "ROIC", "#2ca02c")], "5. ROE / ROIC (%)"
        )

        _plot_series_or_message(
            axes[5], qdates, [(q["ttm_cfo"] / 1e9, "TTM CFO", "#1f77b4"), (q["ttm_fcf"] / 1e9, "TTM FCF", "#ff7f0e")], "6. Operating cash flow / FCF (NT$bn)",
            "Not applicable for the available financial-sector schema",
        )

        _plot_series_or_message(axes[6], dates, [(market["PER"], "P/E", "#7c3aed")], "7. Historical P/E range")
        if axes[6].axison:
            for value, label in ((result.metrics.get("pe_p25"), "P25"), (result.metrics.get("pe_median"), "Median"), (result.metrics.get("pe_p75"), "P75")):
                if value is not None:
                    axes[6].axhline(value, ls="--", lw=0.7, label=label)
            axes[6].legend(fontsize=6, ncol=4)

        pb_available = _plot_series_or_message(axes[7], dates, [(market["PBR"], "P/B", "#1f77b4")], "8. P/B / dividend yield")
        if pb_available and pd.to_numeric(market["dividend_yield"], errors="coerce").notna().any():
            twin2 = axes[7].twinx()
            twin2.plot(dates, market["dividend_yield"], color="#2ca02c", alpha=0.7, label="Dividend yield %")
            twin2.legend(loc="upper right", fontsize=6)

    for axis in axes:
        axis.grid(alpha=0.2)
        axis.tick_params(labelsize=6)
        axis.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    reason = "\n".join(
        textwrap.wrap(
            "Quality: " + "; ".join(result.quality_reasons)
            + " | State: " + "; ".join(result.fundamental_reasons)
            + " | Valuation: " + "; ".join(result.valuation_reasons),
            width=180,
        )
    )
    fig.text(0.02, 0.035, reason, fontsize=6.5)
    fig.tight_layout(rect=(0.01, 0.075, 0.99, 0.94), h_pad=1.4)
    _footer(fig, f"{result.symbol} | period end {result.period_end} | data {result.data_quality}")
    pdf.savefig(fig)
    plt.close(fig)


def _case_page(pdf: PdfPages, results: list[ClassificationResult], events: pd.DataFrame) -> None:
    targets = [
        ("GOOD + TURNING_UP + LOW", lambda r: r.quality == "GOOD" and r.fundamental_state == "TURNING_UP" and r.valuation == "LOW"),
        ("GOOD + TURNING_UP + HIGH", lambda r: r.quality == "GOOD" and r.fundamental_state == "TURNING_UP" and r.valuation == "HIGH"),
        ("GOOD + CONFIRMED_GROWTH", lambda r: r.quality == "GOOD" and r.fundamental_state == "CONFIRMED_GROWTH"),
        ("Possible Value Trap", lambda r: r.research_classification == "POSSIBLE_VALUE_TRAP"),
        ("Cyclical Low-P/E Trap", lambda r: "CYCLICAL_LOW_PE_TRAP_RISK" in r.reason_codes),
        ("Financial-sector special case", lambda r: r.sector_logic == "FINANCIAL"),
    ]
    rows: list[list[str]] = []
    for label, predicate in targets:
        match = next((result for result in results if predicate(result)), None)
        rows.append([label, f"{match.symbol} {match.company}" if match else "No current case", "; ".join(match.valuation_reasons if match else ("No observation satisfies the pre-registered case",))])
    for validation_label, title in (("CORRECT", "TURNING_UP correct historical case"), ("FALSE_RECOVERY", "TURNING_UP incorrect historical case")):
        match = events[events["state_validation"] == validation_label].head(1) if not events.empty else pd.DataFrame()
        if match.empty:
            rows.append([title, "No historical case", "No evaluable event in the current-universe provisional run"])
        else:
            row = match.iloc[0]
            rows.append([title, f"{row['symbol']} {row['company']} ({row['signal_date']})", validation_label])
    fig, axis = plt.subplots(figsize=(16, 10.5))
    axis.axis("off")
    axis.set_title("Representative Cases — selection is descriptive, not a ranking", fontsize=17, weight="bold")
    wrapped = [[a, b, "\n".join(textwrap.wrap(c, 90))] for a, b, c in rows]
    table = axis.table(cellText=wrapped, colLabels=["Required case", "Selected observation", "Why / availability"], loc="center", cellLoc="left", colWidths=[0.24, 0.22, 0.54])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 2.5)
    _footer(fig, "Representative cases")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _backtest_pages(
    pdf: PdfPages,
    baselines: pd.DataFrame,
    state_validation: pd.DataFrame,
    quality_persistence: pd.DataFrame,
) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(16, 10.5))
    fig.suptitle("Historical Validation — provisional evidence", fontsize=17, weight="bold")
    if not state_validation.empty:
        axes[0].bar(state_validation["label"], state_validation["count"], color="#2ca02c")
        axes[0].set_title("A. Fundamental TURNING_UP recognition labels")
    else:
        axes[0].text(0.5, 0.5, "No evaluable TURNING_UP validation events", ha="center")
    if not quality_persistence.empty:
        pivot = quality_persistence.pivot(index="quality", columns="horizon", values="median_eps_growth")
        pivot.plot(kind="bar", ax=axes[1])
        axes[1].set_title("B. Quality persistence: median future EPS growth")
        axes[1].set_ylabel("Growth")
    else:
        axes[1].text(0.5, 0.5, "No quality persistence observations", ha="center")
    fig.text(0.5, 0.045, "These are analysis-quality diagnostics. They do not establish investment prediction.", ha="center", color="#8b0000")
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.94))
    _footer(fig, "Recognition and persistence")
    pdf.savefig(fig)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(16, 10.5))
    fig.suptitle("Valuation Outcomes and Required Baselines", fontsize=17, weight="bold")
    if not baselines.empty:
        one_year = baselines[baselines["horizon"] == "252d"].copy()
        axes[0].bar(one_year["baseline"], one_year["median_return"], color="#1f77b4")
        axes[0].tick_params(axis="x", rotation=25, labelsize=7)
        axes[0].set_title("Median 1Y adjusted price return")
        axes[1].bar(one_year["baseline"], one_year["mean_excess_return"], color="#ff7f0e")
        axes[1].tick_params(axis="x", rotation=25, labelsize=7)
        axes[1].set_title("Mean 1Y excess return vs adjusted 0050 close")
    else:
        axes[0].text(0.5, 0.5, "No baseline output", ha="center")
        axes[1].text(0.5, 0.5, "No baseline output", ha="center")
    fig.text(0.5, 0.04, "Secondary-source adjusted returns and current-universe survivorship bias prohibit a predictive claim.", ha="center", color="#8b0000")
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.94))
    _footer(fig, "Baseline comparison")
    pdf.savefig(fig)
    plt.close(fig)


def _technical_page(pdf: PdfPages) -> None:
    fig, axis = plt.subplots(figsize=(16, 10.5))
    axis.axis("off")
    axis.set_title("Frozen Technical v0.6 Cross-display", fontsize=18, weight="bold")
    axis.text(
        0.5,
        0.60,
        "NOT AVAILABLE IN THE INSPECTED REPOSITORY",
        ha="center",
        fontsize=20,
        color="#8b0000",
        weight="bold",
    )
    axis.text(
        0.5,
        0.43,
        "The research branch does not recreate, tune, or alter Technical v0.6.\n"
        "When an authenticated frozen output artifact is supplied, it may be joined by ticker and as-of date for display only.\n"
        "No combined score or buy/sell signal will be produced.",
        ha="center",
        fontsize=12,
        linespacing=1.8,
    )
    _footer(fig, "Technical cross-display boundary")
    pdf.savefig(fig)
    plt.close(fig)


def _questions_page(pdf: PdfPages, state_validation: pd.DataFrame, baselines: pd.DataFrame) -> None:
    correct_share = None
    if not state_validation.empty:
        match = state_validation[state_validation["label"] == "CORRECT"]
        correct_share = _finite_value(match["share"].iloc[0]) if not match.empty else 0.0
    full_n = 0
    if not baselines.empty:
        selected = baselines[(baselines["baseline"] == "H_FULL_MODEL") & (baselines["horizon"] == "252d")]
        if not selected.empty:
            full_n = int(selected["n"].iloc[0])
    lines = [
        "Q1 Quality separation: descriptive output produced; formal discrimination requires cleaner PIT and sector data.",
        f"Q2 TURNING_UP recognition: provisional correct share = {_fmt(correct_share, True)}; inspect sample counts and label definitions.",
        "Q3 GOOD persistence: compare the Quality Persistence table; missing future 3Y/5Y observations remain explicit.",
        "Q4 Valuation outcomes: computed for LOW/NORMAL/HIGH, but secondary-source adjusted returns and survivorship bias prevent inference.",
        f"Q5 Full model vs baselines: 1Y evaluable full-model observations = {full_n}; confidence intervals are reported.",
        "Q6 Technical + fundamental: not evaluated because the frozen Technical v0.6 artifact was absent.",
        "",
        "Conclusion boundary:",
        "'The model can analyse a company' is assessed by state recognition, persistence, reasons, and data quality.",
        "'The model predicts investment returns' needs adjusted returns, historical constituents, verified filing timestamps, OOS evidence, and uncertainty tests.",
        "This v0.1 run does not establish the second claim.",
    ]
    fig, axis = plt.subplots(figsize=(16, 10.5))
    axis.axis("off")
    axis.set_title("Research Questions and Claim Boundary", fontsize=18, weight="bold")
    axis.text(0.05, 0.88, "\n\n".join(lines), va="top", fontsize=11, linespacing=1.4)
    _footer(fig, "Final research questions")
    pdf.savefig(fig)
    plt.close(fig)


def _finite_value(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def write_pdf_report(
    results: list[ClassificationResult],
    securities: list[SecurityData],
    events: pd.DataFrame,
    baselines: pd.DataFrame,
    state_validation: pd.DataFrame,
    quality_persistence: pd.DataFrame,
    config: dict[str, Any],
    path: Path,
    *,
    font_path: Path | None = None,
) -> None:
    _configure_font(font_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    security_by_symbol = {security.symbol: security for security in securities}
    with PdfPages(path) as pdf:
        metadata = pdf.infodict()
        metadata["Title"] = "0050 Fundamental Quality & Valuation Backtest v0.1"
        metadata["Subject"] = DISCLAIMER
        metadata["Author"] = "TWstock research"
        _distribution_page(pdf, results, config)
        _matrix_pages(pdf, results)
        for result in sorted(results, key=lambda item: item.symbol):
            _plot_security_page(pdf, security_by_symbol[result.symbol], result, events)
        _case_page(pdf, results, events)
        _backtest_pages(pdf, baselines, state_validation, quality_persistence)
        _technical_page(pdf)
        _questions_page(pdf, state_validation, baselines)
