from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from twstock_data.http import HttpTransport

from .pe_river import (
    DEFAULT_EXPERIMENT_DIR,
    ExperimentInputError,
    ForwardScenario,
    load_eps_history,
    load_multiples,
    load_scenarios,
    ttm_eps_as_of,
)
from .pe_river_live_metrics import (
    DEFAULT_HORIZONS,
    HistoricalForwardPEPoint,
    HistoricalPEPoint,
    build_forward_pe_context,
    build_historical_forward_pe_points,
    build_historical_pe_points,
    build_multi_horizon_diagnostic,
    calculate_fundamental_context,
    calculate_technical_context,
    empirical_percentile,
    summarize_multi_horizon,
)
from .pe_river_live_report import (
    write_historical_forward_pe_csv,
    write_historical_pe_csv,
    write_json,
    write_live_html,
    write_multi_horizon_csv,
)
from .pe_river_live_sources import (
    DelayedQuote,
    ForwardEPSVintage,
    FundamentalObservation,
    LiveExperimentError,
    MonthlyRevenueObservation,
    TAIPEI,
    fetch_history,
    load_forward_eps_vintages,
    load_monthly_revenue,
    load_quarterly_fundamentals,
    resolve_quote,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "outputs/experiments/2330_pe_river_live"
DEFAULT_ANALYSIS_YEARS = 5
HISTORY_BUFFER_DAYS = 450


def _years_ago(value: date, years: int) -> date:
    if years <= 0:
        raise LiveExperimentError("analysis_years must be positive")
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def build_live_analysis(
    *,
    symbol: str,
    quote: DelayedQuote,
    quote_fallback_reason: str | None,
    stock_records,
    benchmark_records,
    eps_observations: Sequence[object],
    multiples: Sequence[Decimal],
    scenarios: Sequence[ForwardScenario],
    quarterly: Sequence[FundamentalObservation],
    monthly: Sequence[MonthlyRevenueObservation],
    forward_vintages: Sequence[ForwardEPSVintage],
    analysis_start: date,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> tuple[
    dict[str, object],
    list[HistoricalPEPoint],
    list[HistoricalForwardPEPoint],
    list[dict[str, object]],
]:
    quote_date = datetime.fromisoformat(quote.observed_at).astimezone(TAIPEI).date()
    if analysis_start > quote_date:
        raise LiveExperimentError("analysis_start cannot be after quote date")

    ttm_eps, periods = ttm_eps_as_of(eps_observations, quote_date)
    current_pe = quote.price_twd / ttm_eps
    trailing_points = build_historical_pe_points(
        stock_records,
        eps_observations,
        multiples,
        start_date=analysis_start,
        end_date=quote_date,
    )
    trailing_percentile = empirical_percentile(
        (point.pe_ttm for point in trailing_points), current_pe
    )
    bands = {str(multiple): ttm_eps * multiple for multiple in multiples}
    gaps = {
        key: (quote.price_twd / value - 1) * 100 for key, value in bands.items()
    }

    forward_points = build_historical_forward_pe_points(
        stock_records,
        forward_vintages,
        start_date=analysis_start,
        end_date=quote_date,
    )
    forward_pe = build_forward_pe_context(
        quote_date=quote_date,
        quote_price=quote.price_twd,
        vintages=forward_vintages,
        historical_points=forward_points,
    )

    forward_scenarios = []
    for scenario in scenarios:
        scenario_price = scenario.ntm_eps_twd * scenario.exit_pe
        forward_scenarios.append(
            {
                **asdict(scenario),
                "scenario_price_twd": scenario_price,
                "expected_price_return_pct": (
                    scenario_price / quote.price_twd - 1
                )
                * 100,
            }
        )

    technical = calculate_technical_context(
        stock_records, benchmark_records, quote.price_twd
    )
    fundamental = calculate_fundamental_context(
        quarterly, monthly, as_of_date=quote_date
    )
    diagnostic_rows = build_multi_horizon_diagnostic(
        stock_records,
        benchmark_records,
        trailing_points,
        horizons=horizons,
    )
    diagnostic_summary = summarize_multi_horizon(
        diagnostic_rows, horizons=horizons
    )

    analysis = {
        "experiment_id": "TW-EXP-2330-PE-RIVER-0003",
        "experiment_status": "EXPLORATORY_NOT_VALIDATED",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol,
        "quote": asdict(quote),
        "quote_fallback_reason": quote_fallback_reason,
        "current_valuation": {
            "ttm_eps_twd": ttm_eps,
            "included_periods": periods,
            "pe_ttm": current_pe,
            "historical_trailing_pe_percentile": trailing_percentile,
            "historical_observation_count": len(trailing_points),
            "river_band_prices_twd": bands,
            "price_gap_to_band_pct": gaps,
        },
        "historical_forward_pe": forward_pe,
        "technical_context": technical,
        "fundamental_context": fundamental,
        "forward_scenarios": forward_scenarios,
        "historical_coverage": {
            "requested_start": analysis_start,
            "actual_trailing_pe_start": (
                trailing_points[0].trade_date if trailing_points else None
            ),
            "actual_trailing_pe_end": (
                trailing_points[-1].trade_date if trailing_points else None
            ),
            "trailing_observation_count": len(trailing_points),
            "forward_observation_count": len(forward_points),
            "status": "FIVE_YEAR_PIT_TRAILING_PE_COMPLETE_SUBJECT_TO_SOURCE_AVAILABILITY",
        },
        "diagnostic_backtest": {
            "horizon_sessions": list(horizons),
            "horizon_labels": {
                "21": "1M",
                "63": "3M",
                "126": "6M",
                "189": "9M",
                "252": "12M",
            },
            "rows": diagnostic_rows,
            "summary": diagnostic_summary,
            "status": "SINGLE_STOCK_FIVE_YEAR_OVERLAPPING_HORIZON_DIAGNOSTIC_NOT_ALPHA_VALIDATION",
        },
        "method_notes": [
            "Current quote is secondary and delayed when Yahoo is available; otherwise the latest completed official TWSE close is used and tagged as fallback.",
            "The five-year river uses official TWSE completed-session closes and only quarterly EPS that had passed research_available_date on each historical date.",
            "Historical Forward P/E is produced only from verified point-in-time analyst-consensus vintages. Manual scenarios and ex-post actual EPS are rejected from that dataset.",
            "If verified Forward EPS vintages are absent, the historical Forward P/E percentile remains explicitly unavailable rather than being fabricated.",
            "MA50, MA200 and 12-1 momentum use completed official TWSE sessions, including a pre-window history buffer where available.",
            "The diagnostic reports 21, 63, 126, 189 and 252-session forward excess returns versus 0050.",
            "Monthly signal observations and long forward horizons overlap, so observations are not statistically independent.",
            "Monthly revenue is official current context but does not yet carry research_available_at for historical backtesting.",
            "The diagnostic uses one stock and five years of history; it cannot establish alpha or guarantee future returns.",
            "No buy, sell, target-price recommendation or live-capital authorization is produced.",
        ],
    }
    return analysis, trailing_points, forward_points, diagnostic_rows


def run_live(
    *,
    symbol: str,
    benchmark_symbol: str,
    output_dir: Path,
    eps_path: Path,
    multiples_path: Path,
    scenarios_path: Path,
    fundamentals_path: Path,
    monthly_revenue_path: Path,
    forward_vintages_path: Path,
    analysis_years: int = DEFAULT_ANALYSIS_YEARS,
    analysis_start: date | None = None,
    history_start: date | None = None,
    stock_history_csv: Path | None = None,
    benchmark_history_csv: Path | None = None,
    quote_transport: HttpTransport | None = None,
) -> dict[str, object]:
    today = datetime.now(TAIPEI).date()
    preliminary_analysis_start = analysis_start or _years_ago(today, analysis_years)
    fetch_start = history_start or (
        preliminary_analysis_start - timedelta(days=HISTORY_BUFFER_DAYS)
    )

    stock_records = fetch_history(
        symbol, fetch_start, today, csv_path=stock_history_csv
    )
    benchmark_records = fetch_history(
        benchmark_symbol, fetch_start, today, csv_path=benchmark_history_csv
    )
    quote, fallback_reason = resolve_quote(
        symbol, stock_records, transport=quote_transport
    )
    quote_date = datetime.fromisoformat(quote.observed_at).astimezone(TAIPEI).date()
    final_analysis_start = analysis_start or _years_ago(quote_date, analysis_years)

    eps = load_eps_history(eps_path)
    multiples = load_multiples(multiples_path)
    scenarios = load_scenarios(scenarios_path)
    quarterly = load_quarterly_fundamentals(fundamentals_path)
    monthly = load_monthly_revenue(monthly_revenue_path)
    forward_vintages = load_forward_eps_vintages(forward_vintages_path)

    analysis, trailing_points, forward_points, diagnostic_rows = build_live_analysis(
        symbol=symbol,
        quote=quote,
        quote_fallback_reason=fallback_reason,
        stock_records=stock_records,
        benchmark_records=benchmark_records,
        eps_observations=eps,
        multiples=multiples,
        scenarios=scenarios,
        quarterly=quarterly,
        monthly=monthly,
        forward_vintages=forward_vintages,
        analysis_start=final_analysis_start,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "live_analysis.json", analysis)
    write_historical_pe_csv(output_dir / "historical_pe.csv", trailing_points)
    write_historical_forward_pe_csv(
        output_dir / "historical_forward_pe.csv", forward_points
    )
    write_multi_horizon_csv(
        output_dir / "multi_horizon_backtest.csv", diagnostic_rows
    )
    write_live_html(output_dir / "live_report.html", analysis, trailing_points, multiples)
    return analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a delayed live five-year 2330 PE-river research report."
    )
    parser.add_argument("--symbol", default="2330.TW")
    parser.add_argument("--benchmark-symbol", default="0050.TW")
    parser.add_argument("--analysis-years", type=int, default=DEFAULT_ANALYSIS_YEARS)
    parser.add_argument("--analysis-start", type=date.fromisoformat)
    parser.add_argument("--history-start", type=date.fromisoformat)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--eps", type=Path, default=DEFAULT_EXPERIMENT_DIR / "eps_history.csv"
    )
    parser.add_argument(
        "--multiples",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR / "river_multiples.csv",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR / "forward_scenarios.csv",
    )
    parser.add_argument(
        "--fundamentals",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR / "quarterly_fundamentals.csv",
    )
    parser.add_argument(
        "--monthly-revenue",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR / "monthly_revenue.csv",
    )
    parser.add_argument(
        "--forward-vintages",
        type=Path,
        default=DEFAULT_EXPERIMENT_DIR / "forward_eps_vintages.csv",
    )
    parser.add_argument("--stock-history-csv", type=Path)
    parser.add_argument("--benchmark-history-csv", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        analysis = run_live(
            symbol=args.symbol,
            benchmark_symbol=args.benchmark_symbol,
            output_dir=args.output_dir,
            eps_path=args.eps,
            multiples_path=args.multiples,
            scenarios_path=args.scenarios,
            fundamentals_path=args.fundamentals,
            monthly_revenue_path=args.monthly_revenue,
            forward_vintages_path=args.forward_vintages,
            analysis_years=args.analysis_years,
            analysis_start=args.analysis_start,
            history_start=args.history_start,
            stock_history_csv=args.stock_history_csv,
            benchmark_history_csv=args.benchmark_history_csv,
        )
    except (LiveExperimentError, ExperimentInputError) as exc:
        parser.error(str(exc))
    print(f"Symbol: {analysis['symbol']}")
    print(
        f"Price: {analysis['quote']['price_twd']} "
        f"({analysis['quote']['data_status']})"
    )
    print(f"TTM P/E: {analysis['current_valuation']['pe_ttm']}")
    print(
        "Historical Forward P/E: "
        f"{analysis['historical_forward_pe']['status']}"
    )
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
