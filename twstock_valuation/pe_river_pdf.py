from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile

from .pe_river import RiverObservation


def write_report(rows: tuple[RiverObservation, ...], metadata: dict, output: Path):
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
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "date", "official_close", "official_pe", "pe_status",
                         "reference_eps_twd"] + [f"river_{m:g}x" for m in multiples]
                        + ["close_source_url", "pe_source_url"])
        for row in rows:
            obs = row.observation
            writer.writerow([obs.symbol, obs.trade_date.isoformat(), obs.official_close,
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
        y = [r.band_prices[i] if r.band_prices[i] is not None else float("nan") for r in rows]
        ax.plot(dates, y, label=f"{multiple:g}x PE", color=colors[i % len(colors)], lw=1, alpha=.85)
    ax.plot(dates, [r.observation.official_close for r in rows], label="Official Close",
            color="#15283c", lw=1.4, zorder=10)
    ax.set_ylabel("Price (TWD)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.grid(alpha=.16)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 1.105), ncol=min(6, len(multiples) + 1),
              frameon=False, fontsize=9)
    ax.margins(x=.01)
    fig.text(.065, .95, f"{symbol} | TWSE Historical PE River", fontsize=21,
             color="#15283c", weight="bold")
    fig.text(.065, .91, f"{metadata['requested_coverage']} coverage | As of {metadata['latest_market_date']}",
             fontsize=11, color="#617080")
    panel = fig.add_axes((.75, .21, .23, .65))
    panel.axis("off")
    def number(value, suffix=""):
        return f"{value:,.2f}{suffix}" if value is not None else "Unavailable"
    stats = metadata["percentiles"]
    lines = ["LATEST & DISTRIBUTION", "",
        f"Market date     {metadata['latest_market_date']}",
        f"Latest close    {number(metadata['latest_close'])} TWD",
        f"Valid PE date   {metadata['latest_valid_pe_date'] or 'Unavailable'}",
        f"PE-date close   {number(metadata['latest_valid_pe_close'])} TWD",
        f"Latest PE       {number(metadata['latest_pe'], 'x')}",
        f"PE percentile   {number(stats['current_percentile'], '%')}", "",
        f"P10             {number(stats['p10'], 'x')}",
        f"P25             {number(stats['p25'], 'x')}",
        f"Median          {number(stats['p50'], 'x')}",
        f"P75             {number(stats['p75'], 'x')}",
        f"P90             {number(stats['p90'], 'x')}", "", "ACTUAL COVERAGE", "",
        f"Start           {metadata['actual_start_date']}",
        f"End             {metadata['actual_end_date']}",
        f"Observations    {metadata['observation_count']:,}",
        f"Valid PE        {metadata['valid_pe_observation_count']:,}",
        f"Missing PE      {metadata['missing_pe_count']:,}", "",
        f"Status: {metadata['coverage_status']}"]
    panel.text(0, 1, "\n".join(lines), va="top", fontfamily="monospace", fontsize=9.3,
               linespacing=1.3, color="#243b50")
    notes = [
        "Source: TWSE BWIBBU official monthly P/E + STOCK_DAY_AVG official daily close; same symbol/name and date.",
        "River price = TWSE-implied reference EPS x multiple; implied EPS = official close / official PE (published PE is rounded).",
        "Reference EPS is not reconstructed accounting EPS. Historical PE is used as published, without corporate-action adjustments.",
        "Missing PE leaves gaps. Distribution uses positive official PE only; rank = count(PE <= latest valid PE) / valid count.",
        "Coverage reflects available source observations; this report does not certify trading-calendar completeness.",
    ]
    fig.text(.065, .13, "\n".join(notes), fontsize=8.5, linespacing=1.5, color="#617080", va="top")
    try:
        fig.savefig(pdf, format="pdf", metadata={"Title": f"{symbol} TWSE Historical PE River", "Author": "TWstock"})
    finally:
        plt.close(fig)
    metadata = {**metadata, "outputs": {"pdf": str(pdf.resolve()), "csv": str(csv_path.resolve()),
                                       "metadata": str(json_path.resolve())}}
    json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return metadata
