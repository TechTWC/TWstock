from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile

from twstock_data.sources.twse_corporate_actions import (
    CAPITAL_REDUCTION_CASH_RETURN, CAPITAL_REDUCTION_LOSS,
    FACE_VALUE_CHANGE_REVERSE_SPLIT, FACE_VALUE_CHANGE_SPLIT, STOCK_DIVIDEND,
    CorporateActionEvent,
)
from .corporate_actions import NORMALIZED, NormalizedRiverObservation
from .pe_river import RiverObservation


def _event_marker_label(event: CorporateActionEvent) -> str:
    label = {
        STOCK_DIVIDEND: "Stock Dividend",
        CAPITAL_REDUCTION_CASH_RETURN: "Cash Capital Reduction",
        CAPITAL_REDUCTION_LOSS: "Loss Capital Reduction",
        FACE_VALUE_CHANGE_SPLIT: "Face Value Split",
        FACE_VALUE_CHANGE_REVERSE_SPLIT: "Face Value Reverse Split",
    }.get(event.action_type, event.action_type.replace("_", " ").title())
    if event.action_type in (
            FACE_VALUE_CHANGE_SPLIT, FACE_VALUE_CHANGE_REVERSE_SPLIT):
        label += f"\n{event.share_factor:g}x"
    return label


def _summary_lines(metadata: dict, event_count: int, *, adjusted: bool) -> list[str]:
    """Build the PDF summary without conflating raw and normalized metrics."""
    def number(value, suffix=""):
        return f"{value:,.2f}{suffix}" if value is not None else "Unavailable"

    raw_stats = metadata.get("raw_pe_distribution", metadata["percentiles"])
    normalized_stats = metadata.get("normalized_pe_distribution")
    normalization_status = metadata.get("normalization_status")
    normalized_complete = (
        adjusted
        and normalization_status == NORMALIZED
        and normalized_stats is not None
    )
    normalized_pe = metadata.get("latest_normalized_pe") if normalized_complete else None
    normalized_percentile = (
        number(normalized_stats["current_percentile"], "%")
        if normalized_complete else "Incomplete")

    lines = ["LATEST & DISTRIBUTION", "",
        f"Market date     {metadata['latest_market_date']}",
        f"Latest close    {number(metadata.get('latest_adjusted_close', metadata['latest_close']))} TWD",
        f"Valid PE date   {metadata['latest_valid_pe_date'] or 'Unavailable'}",
        f"PE-date close   {number(metadata['latest_valid_pe_close'])} TWD",
        f"Official PE     {number(metadata['latest_pe'], 'x')}"]
    if adjusted:
        lines.extend([
            f"Normalized PE   {number(normalized_pe, 'x')}",
            f"Raw PE percentile {number(raw_stats['current_percentile'], '%')}",
            f"Norm percentile {normalized_percentile}", "",
            f"Norm P10        {number(normalized_stats['p10'], 'x') if normalized_complete else 'Unavailable'}",
            f"Norm P25        {number(normalized_stats['p25'], 'x') if normalized_complete else 'Unavailable'}",
            f"Norm median     {number(normalized_stats['p50'], 'x') if normalized_complete else 'Unavailable'}",
            f"Norm P75        {number(normalized_stats['p75'], 'x') if normalized_complete else 'Unavailable'}",
            f"Norm P90        {number(normalized_stats['p90'], 'x') if normalized_complete else 'Unavailable'}",
        ])
    else:
        lines.extend([
            f"Raw PE percentile {number(raw_stats['current_percentile'], '%')}", "",
            f"P10             {number(raw_stats['p10'], 'x')}",
            f"P25             {number(raw_stats['p25'], 'x')}",
            f"Median          {number(raw_stats['p50'], 'x')}",
            f"P75             {number(raw_stats['p75'], 'x')}",
            f"P90             {number(raw_stats['p90'], 'x')}",
        ])
    lines.extend(["", "ACTUAL COVERAGE", "",
        f"Start           {metadata['actual_start_date']}",
        f"End             {metadata['actual_end_date']}",
        f"Observations    {metadata['observation_count']:,}",
        f"Valid PE        {metadata['valid_pe_observation_count']:,}",
        f"Missing PE      {metadata['missing_pe_count']:,}",
        f"Actions         {event_count if adjusted else 0:,}", "",
        "Coverage:",
        f"  {metadata['coverage_status']}"])
    if adjusted:
        lines.extend([
            "Normalization coverage:",
            f"  {metadata.get('normalization_coverage_start', 'Unavailable')} onward",
            "Normalization:",
            f"  {normalization_status or 'Unavailable'}",
        ])
    return lines


def write_report(rows: tuple[RiverObservation, ...], metadata: dict, output: Path, *,
                 normalized_rows: tuple[NormalizedRiverObservation, ...] | None = None,
                 events: tuple[CorporateActionEvent, ...] = ()):
    # Headless PDF backend; respect user-supplied Matplotlib config location.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "twstock-matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    symbol = metadata["symbol"]
    pdf = output / f"{symbol}_pe_river.pdf"
    csv_path = output / "historical_pe_river.csv"
    json_path = output / "report_metadata.json"
    multiples = metadata["multiples"]
    adjusted = normalized_rows is not None
    if adjusted:
        if len(rows) != len(normalized_rows) or any(
                raw.observation != normalized.observation
                for raw, normalized in zip(rows, normalized_rows)):
            raise ValueError("raw and normalized report rows do not align")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if adjusted:
            writer.writerow([
                "symbol", "canonical_symbol", "market", "company", "date",
                "official_close", "adjusted_close", "official_pe",
                "normalized_pe", "pe_status", "normalization_status",
                "financial_report_period", "reference_period_end",
                "raw_implied_reference_eps", "reference_eps_twd",
                "pending_share_factor",
                "normalized_reference_eps_local", "future_share_factor",
                "adjusted_reference_eps",
            ] + [f"raw_river_{m:g}x" for m in multiples]
              + [f"adjusted_river_{m:g}x" for m in multiples]
              + ["applied_pending_events", "applied_future_events",
                 "close_source_url", "pe_source_url"])
            for raw, normalized in zip(rows, normalized_rows):
                obs = raw.observation
                valid = raw.reference_eps_twd is not None
                writer.writerow([
                    obs.symbol, metadata.get("canonical_symbol"), metadata.get("market"),
                    metadata.get("company"), obs.trade_date.isoformat(), obs.official_close,
                    normalized.adjusted_close if normalized.adjusted_close is not None else "",
                    obs.official_pe if valid else "",
                    normalized.normalized_pe if normalized.normalized_pe is not None else "",
                    "VALID_PE" if valid else "PE_UNAVAILABLE",
                    normalized.normalization_status,
                    obs.financial_report_period_raw or "",
                    obs.reference_period_end.isoformat() if obs.reference_period_end else "",
                    normalized.raw_implied_reference_eps
                    if normalized.raw_implied_reference_eps is not None else "",
                    normalized.raw_implied_reference_eps
                    if normalized.raw_implied_reference_eps is not None else "",
                    normalized.pending_share_factor
                    if normalized.pending_share_factor is not None else "",
                    normalized.normalized_reference_eps_local
                    if normalized.normalized_reference_eps_local is not None else "",
                    normalized.future_share_factor
                    if normalized.future_share_factor is not None else "",
                    normalized.adjusted_reference_eps
                    if normalized.adjusted_reference_eps is not None else "",
                ] + [value if value is not None else "" for value in raw.band_prices]
                  + [value if value is not None else ""
                     for value in normalized.adjusted_band_prices]
                  + [";".join(day.isoformat() for day in normalized.applied_pending_events),
                     ";".join(day.isoformat() for day in normalized.applied_future_events),
                     obs.close_source_url, obs.pe_source_url])
        else:
            writer.writerow(["symbol", "canonical_symbol", "market", "company", "date",
                             "official_close", "official_pe", "pe_status",
                             "reference_eps_twd"] + [f"river_{m:g}x" for m in multiples]
                            + ["close_source_url", "pe_source_url"])
            for row in rows:
                obs = row.observation
                writer.writerow([obs.symbol, metadata.get("canonical_symbol"),
                    metadata.get("market"), metadata.get("company"),
                    obs.trade_date.isoformat(), obs.official_close,
                    obs.official_pe if row.reference_eps_twd is not None else "",
                    "VALID_PE" if row.reference_eps_twd is not None else "PE_UNAVAILABLE",
                    row.reference_eps_twd if row.reference_eps_twd is not None else ""]
                    + [p if p is not None else "" for p in row.band_prices]
                    + [obs.close_source_url, obs.pe_source_url])

    fig = plt.figure(figsize=(16.5, 9.3), facecolor="white")
    ax = fig.add_axes((.065, .21, .65, .64))
    dates = [r.observation.trade_date for r in rows]
    colors = ("#4777ad", "#479c9c", "#89a952", "#d6a14b", "#c86c69")
    for i, multiple in enumerate(multiples):
        values = (normalized_rows if adjusted else rows)
        y = [(r.adjusted_band_prices[i] if adjusted else r.band_prices[i])
             if (r.adjusted_band_prices[i] if adjusted else r.band_prices[i]) is not None
             else float("nan") for r in values]
        label = f"Adjusted {multiple:g}x" if adjusted else f"{multiple:g}x PE"
        ax.plot(dates, y, label=label, color=colors[i % len(colors)], lw=1, alpha=.85)
    close_values = ([r.adjusted_close if r.adjusted_close is not None else float("nan")
                     for r in normalized_rows] if adjusted else
                    [r.observation.official_close for r in rows])
    ax.plot(dates, close_values, label="Adjusted Close" if adjusted else "Official Close",
            color="#15283c", lw=1.4, zorder=10)
    marker_count = 0
    for event in events if adjusted else ():
        if dates[0] <= event.effective_date <= dates[-1]:
            marker_count += 1
            label = _event_marker_label(event)
            ax.axvline(event.effective_date, color="#8c5b42", lw=1, ls="--", alpha=.8)
            ax.annotate(label, (event.effective_date, 1), xycoords=("data", "axes fraction"),
                        xytext=(3, -4), textcoords="offset points", rotation=90,
                        va="top", ha="left", fontsize=7.5, color="#8c5b42")
    ax.set_ylabel("Price (TWD)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.grid(alpha=.16)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.105), ncol=min(6, len(multiples) + 1),
              frameon=False, fontsize=9)
    ax.margins(x=.01)
    title = metadata.get(
        "report_title",
        f"{metadata.get('canonical_symbol', symbol)} | {metadata.get('market', 'TWSE')} Historical PE River")
    fig.text(.065, .95, title, fontsize=21,
             color="#15283c", weight="bold")
    fig.text(.065, .91, f"{metadata['requested_coverage']} coverage | As of {metadata['latest_market_date']}",
             fontsize=11, color="#617080")
    panel = fig.add_axes((.75, .21, .23, .65))
    panel.axis("off")
    lines = _summary_lines(metadata, len(events), adjusted=adjusted)
    panel.text(0, 1, "\n".join(lines), va="top", fontfamily="monospace", fontsize=9.3,
               linespacing=1.3, color="#243b50")
    market = metadata.get("market", "TWSE")
    exchange_source = (
        "TPEx peQryStock + tradingStock; TPEx exDailyQ, revivt and pvChgRslt."
        if market == "TPEX" else
        "TWSE BWIBBU + STOCK_DAY_AVG; TWSE TWT49U/TWT49UDetail and TWTAUU/TWTAVUDetail.")
    notes = ([
        f"Source: {exchange_source}",
        "Face-value-change coverage: MOPS Company Act category 11, proven per symbol and date interval.",
        "Primary chart is on the latest share-count basis; official close, official PE, raw EPS and raw rivers remain in CSV for audit.",
        "Missing PE leaves raw implied EPS, normalized EPS and both river series blank; no fill or interpolation.",
        "Cash distributions are not total-return adjusted.",
        "Coverage reflects available source observations; this report does not certify trading-calendar completeness.",
    ] if adjusted else [
        f"Source: {metadata.get('source_contract')}",
        f"River price = {market}-implied reference EPS x multiple; implied EPS = official close / official PE (published PE is rounded).",
        "Reference EPS is not reconstructed accounting EPS. Historical PE is used as published, without corporate-action adjustments.",
        "Missing PE leaves gaps. Distribution uses positive official PE only; rank = count(PE <= latest valid PE) / valid count.",
        "Coverage reflects available source observations; this report does not certify trading-calendar completeness.",
    ])
    fig.text(.065, .13, "\n".join(notes), fontsize=8.5, linespacing=1.5, color="#617080", va="top")
    try:
        fig.savefig(pdf, format="pdf", metadata={"Title": title, "Author": "TWstock"})
    finally:
        plt.close(fig)
    metadata = {**metadata, "pdf_event_marker_count": marker_count,
                "outputs": {"pdf": str(pdf.resolve()), "csv": str(csv_path.resolve()),
                            "metadata": str(json_path.resolve())}}
    json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return metadata
