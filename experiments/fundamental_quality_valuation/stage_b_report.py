from __future__ import annotations

import math
from pathlib import Path
import textwrap
from typing import Any

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DISCLAIMER = (
    "Research / Shadow Model. No buy/sell recommendation, target price, or return promise. "
    "CURRENT_CONSTITUENTS_ONLY; exploratory association."
)


def _configure_font(font_path: Path | None) -> None:
    if font_path and font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42


def _footer(fig: plt.Figure, label: str) -> None:
    fig.text(0.01, 0.01, DISCLAIMER, fontsize=6.5, color="#666666")
    fig.text(0.99, 0.01, label, fontsize=6.5, color="#666666", ha="right")


def _pct(value: object) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{parsed:.1%}" if math.isfinite(parsed) else "—"


def _text_page(pdf: PdfPages, title: str, sections: list[tuple[str, str]], label: str) -> None:
    fig, axis = plt.subplots(figsize=(16, 10.5))
    axis.axis("off")
    axis.set_title(title, fontsize=19, weight="bold", pad=20)
    y = 0.92
    for heading, body in sections:
        axis.text(0.04, y, heading, fontsize=12, weight="bold", va="top", transform=axis.transAxes)
        y -= 0.045
        wrapped = "\n".join(textwrap.wrap(body, width=145))
        axis.text(0.05, y, wrapped, fontsize=9.5, va="top", linespacing=1.4, transform=axis.transAxes)
        y -= 0.055 + 0.028 * max(1, len(wrapped.splitlines()))
    _footer(fig, label)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _axis_chart_page(
    pdf: PdfPages,
    title: str,
    summary: pd.DataFrame,
    buckets: list[str],
    label: str,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10.5))
    fig.suptitle(title, fontsize=17, weight="bold")
    metrics = (
        ("median_return", "Median stock return"),
        ("median_excess_return", "Median excess return vs 0050"),
        ("outperform_0050_rate", "Outperform-0050 rate"),
        ("observations", "Evaluable observations"),
    )
    horizon_order = ["60d", "120d", "252d", "504d"]
    for axis, (metric, metric_title) in zip(axes.flat, metrics):
        selected = summary[summary["bucket"].isin(buckets)]
        pivot = selected.pivot(index="horizon", columns="bucket", values=metric).reindex(horizon_order)
        pivot = pivot.reindex(columns=buckets)
        pivot.plot(kind="bar", ax=axis)
        axis.set_title(metric_title)
        axis.set_xlabel("3M / 6M / 12M / 24M trading-day horizons")
        axis.tick_params(axis="x", rotation=0)
        axis.grid(axis="y", alpha=0.2)
        if metric != "observations":
            axis.axhline(0, color="#444444", lw=0.7)
    fig.text(
        0.5,
        0.045,
        "Means, medians, dispersion, issuer-clustered and entry-quarter-clustered uncertainty are retained in the CSV artifacts.",
        ha="center",
        fontsize=8,
        color="#8b0000",
    )
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.94))
    _footer(fig, label)
    pdf.savefig(fig)
    plt.close(fig)


def _table_page(
    pdf: PdfPages,
    title: str,
    frame: pd.DataFrame,
    columns: list[str],
    labels: list[str],
    page_label: str,
    *,
    percent_columns: set[str] | None = None,
    max_rows: int = 24,
) -> None:
    selected = frame.head(max_rows).copy()
    percent_columns = percent_columns or set()
    cells: list[list[str]] = []
    for _, row in selected.iterrows():
        values = []
        for column in columns:
            value = row.get(column)
            if column in percent_columns:
                values.append(_pct(value))
            elif pd.isna(value):
                values.append("—")
            else:
                values.append(str(value))
        cells.append(values)
    fig, axis = plt.subplots(figsize=(16, 10.5))
    axis.axis("off")
    axis.set_title(title, fontsize=17, weight="bold", pad=18)
    table = axis.table(cellText=cells, colLabels=labels, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(7.2)
    table.scale(1, 1.55)
    for (row, _), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#d9eaf7")
            cell.set_text_props(weight="bold")
    _footer(fig, page_label)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def write_stage_b_pdf(
    path: Path,
    *,
    evidence: dict[str, Any],
    state: pd.DataFrame,
    state_detail: pd.DataFrame,
    quality: pd.DataFrame,
    valuation: pd.DataFrame,
    combinations: pd.DataFrame,
    timing: pd.DataFrame,
    regimes: pd.DataFrame,
    outliers: pd.DataFrame,
    overlap: pd.DataFrame,
    state_accuracy: pd.DataFrame,
    state_confusion: pd.DataFrame,
    mops_coverage: pd.DataFrame,
    font_path: Path | None = None,
) -> None:
    _configure_font(font_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
        metadata = pdf.infodict()
        metadata["Title"] = "0050 Fundamental Model v0.1 — Stage B Predictive Validation"
        metadata["Subject"] = DISCLAIMER
        metadata["Author"] = "TWstock research"

        counts = evidence["eligible_observations_by_horizon"]
        _text_page(
            pdf,
            "0050 Fundamental Model v0.1 — Stage B Predictive Validation",
            [
                ("Research question", "Do the already-Frozen Quality, Fundamental State, state_detail and Valuation categories contain information about later adjusted-close returns?"),
                ("Frozen data contract", f"Stage A signal SHA-256: {evidence['frozen_identity']['signal_sha256']}. Entry is exactly Stage A first_trade_date. Horizons are 60, 120, 252 and 504 common TWSE trading sessions."),
                ("Cohort boundary", "Only the 38 non-financial issuers in the fixed September 2026 cohort enter the analysis. Twelve financial issuers are excluded. The claim is current fixed cohort predictive association only."),
                ("Eligible returns", ", ".join(f"{key}: {value}" for key, value in counts.items())),
                ("Conclusion", f"Evidence grade: {evidence['predictive_evidence_grade']}. Label: {evidence['evidence_label']}. A correct Stage B can PASS even when evidence is weak or none."),
            ],
            "Research question and frozen contract",
        )

        fig, axes = plt.subplots(1, 2, figsize=(16, 10.5))
        fig.suptitle("A. Fundamental Identification Accuracy", fontsize=18, weight="bold")
        states = ["IMPROVING", "STABLE", "DETERIORATING"]
        if not state_confusion.empty:
            matrix = state_confusion[
                state_confusion["predicted_state"].isin(states)
                & state_confusion["realized_state"].isin(states)
            ].pivot(index="predicted_state", columns="realized_state", values="count").reindex(
                index=states, columns=states, fill_value=0
            ).fillna(0)
            axes[0].imshow(matrix.to_numpy(), cmap="Blues")
            axes[0].set_xticks(range(3), states, rotation=20)
            axes[0].set_yticks(range(3), states)
            axes[0].set_title("Frozen identification confusion matrix")
            for row in range(3):
                for column in range(3):
                    axes[0].text(column, row, int(matrix.iloc[row, column]), ha="center", va="center")
        if not state_accuracy.empty:
            acc = state_accuracy.set_index("state").reindex(states)
            x = np.arange(3)
            axes[1].bar(x - 0.18, acc["precision"], 0.36, label="Precision")
            axes[1].bar(x + 0.18, acc["recall"], 0.36, label="Recall")
            axes[1].set_xticks(x, states)
            axes[1].set_ylim(0, 1)
            axes[1].set_title("Frozen canonical-state accuracy")
            axes[1].legend()
        fig.text(0.5, 0.05, "Identification accuracy and future-return predictive power are separate research layers.", ha="center", color="#8b0000")
        fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.94))
        _footer(fig, "Layer A — identification")
        pdf.savefig(fig)
        plt.close(fig)

        _axis_chart_page(pdf, "B1. Future Return Predictive Power — Canonical State", state, states, "Canonical state")
        _axis_chart_page(
            pdf,
            "B2. Future Return Predictive Power — state_detail",
            state_detail,
            ["TURNING_UP", "CONFIRMED_GROWTH", "MATURE_GROWTH", "DECELERATING", "DETERIORATING"],
            "state_detail lifecycle",
        )
        _axis_chart_page(pdf, "B3. Quality Predictive Test", quality, ["GOOD", "ACCEPTABLE", "WEAK"], "Quality")
        _axis_chart_page(pdf, "B4. Valuation Predictive Test", valuation, ["LOW", "NORMAL", "HIGH"], "Valuation")

        supported = combinations[
            (combinations["horizon"] == "252d") & (combinations["support_status"] == "SUPPORTED")
        ].sort_values("median_excess_return_lift_vs_all", ascending=False)
        _table_page(
            pdf,
            "B5. Supported Categorical Intersections — 12M",
            supported,
            ["dimension", "bucket", "observations", "unique_issuers", "median_return", "median_excess_return", "outperform_0050_rate", "median_excess_return_lift_vs_all"],
            ["Dimension", "Cell", "N", "Issuers", "Median", "Median excess", "Outperform", "Excess lift"],
            "No score; fixed support gate",
            percent_columns={"median_return", "median_excess_return", "outperform_0050_rate", "median_excess_return_lift_vs_all"},
        )
        _axis_chart_page(pdf, "B6. TOO_LATE Investment Relevance", timing, list(("CORRECT", "TOO_EARLY", "TOO_LATE", "FALSE_RECOVERY")), "Existing timing labels")

        regime_state = regimes[
            (regimes["dimension"] == "FUNDAMENTAL_STATE")
            & (regimes["bucket"].isin(states))
        ].copy()
        _table_page(
            pdf,
            "B7. Regime Robustness — pre-2023 vs 2023 onward",
            regime_state,
            ["regime", "bucket", "horizon", "observations", "unique_issuers", "median_excess_return", "outperform_0050_rate", "support_status"],
            ["Regime", "State", "Horizon", "N", "Issuers", "Median excess", "Outperform", "Support"],
            "Fixed calendar split",
            percent_columns={"median_excess_return", "outperform_0050_rate"},
        )

        sensitivity = outliers[
            (outliers["analysis_type"] == "RETURN_SENSITIVITY")
            & (outliers["bucket"] == "IMPROVING")
        ]
        _table_page(
            pdf,
            "B8. Outlier and Concentration Robustness",
            sensitivity,
            ["scope", "horizon", "observations", "unique_issuers", "median_return", "median_excess_return", "outperform_0050_rate", "top_five_positive_return_contribution"],
            ["Scope", "Horizon", "N", "Issuers", "Median", "Median excess", "Outperform", "Top-5 contribution"],
            "Full / ex-TSMC / top-return removal",
            percent_columns={"median_return", "median_excess_return", "outperform_0050_rate", "top_five_positive_return_contribution"},
        )

        _table_page(
            pdf,
            "B9. Overlapping-Window Audit",
            overlap,
            ["horizon", "eligible_observations", "overlapping_observations_count", "overlapping_observations_ratio", "overlap_pair_count", "same_issuer_overlap_pair_count", "same_calendar_period_cross_issuer_overlap_pair_count"],
            ["Horizon", "Eligible", "Overlapping obs", "Ratio", "Pairs", "Same issuer", "Cross issuer/calendar"],
            "Observations are not IID",
            percent_columns={"overlapping_observations_ratio"},
        )

        if not mops_coverage.empty:
            total = mops_coverage[mops_coverage["scope"] == "TOTAL"]
            exact = int(
                total.loc[total["availability_method"] == "MOPS_EXACT", "observations"].sum()
            )
            proxy = int(
                total.loc[
                    total["availability_method"] == "AVAILABLE_DATE_PROXY", "observations"
                ].sum()
            )
            coverage_text = (
                f"Frozen Stage A financial timeline: {exact + proxy:,} observations; "
                f"{exact:,} MOPS exact ({exact / (exact + proxy):.1%}) and {proxy:,} explicit "
                "available-date proxies. Stage B performs zero MOPS network requests and does "
                "not remap any filing date."
            )
        else:
            coverage_text = "Coverage artifact unavailable"
        _text_page(
            pdf,
            "B10. Evidence Grade and Limitations",
            [
                ("MOPS PIT coverage", coverage_text),
                ("Evidence grade", f"{evidence['predictive_evidence_grade']} — {evidence['evidence_label']}. The deterministic rubric was registered in code and documentation before this run."),
                ("Uncertainty", "Every summary retains issuer-clustered and entry-quarter-clustered mean uncertainty plus deterministic cluster-bootstrap median intervals. Ordinary IID confidence is not used as the evidentiary basis."),
                ("Overlap", "The overlap artifact counts observations and pairs whose forward windows intersect. The 1,563 signal records are not treated as 1,563 independent trials."),
                ("Limitations", " ".join(evidence["limitations"])),
                ("Prohibited claims", "No buy/sell recommendation, target price, expected-return promise, historical-0050 strategy performance, causal claim, composite score, or parameter optimization."),
            ],
            "Evidence and limitations",
        )
