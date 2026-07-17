from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from twstock_data.http import HttpTransport

from .pe_river import DEFAULT_EXPERIMENT_DIR, ExperimentInputError, ForwardScenario, load_eps_history, load_multiples, load_scenarios, ttm_eps_as_of
from .pe_river_live_metrics import HistoricalPEPoint, build_diagnostic_backtest, build_historical_pe_points, calculate_fundamental_context, calculate_technical_context, empirical_percentile, summarize_diagnostic
from .pe_river_live_report import write_diagnostic_csv, write_historical_pe_csv, write_json, write_live_html
from .pe_river_live_sources import DelayedQuote, FundamentalObservation, LiveExperimentError, MonthlyRevenueObservation, TAIPEI, fetch_history, load_monthly_revenue, load_quarterly_fundamentals, parse_yahoo_quote_payload, resolve_quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "outputs/experiments/2330_pe_river_live"


def build_live_analysis(*, symbol: str, quote: DelayedQuote, quote_fallback_reason: str | None, stock_records, benchmark_records, eps_observations: Sequence[object], multiples: Sequence[Decimal], scenarios: Sequence[ForwardScenario], quarterly: Sequence[FundamentalObservation], monthly: Sequence[MonthlyRevenueObservation]) -> tuple[dict[str, object], list[HistoricalPEPoint], list[dict[str, object]]]:
    quote_date = datetime.fromisoformat(quote.observed_at).astimezone(TAIPEI).date()
    ttm_eps, periods = ttm_eps_as_of(eps_observations, quote_date)
    current_pe = quote.price_twd / ttm_eps
    points = build_historical_pe_points(stock_records, eps_observations, multiples)
    percentile = empirical_percentile((point.pe_ttm for point in points), current_pe)
    bands = {str(m): ttm_eps * m for m in multiples}
    gaps = {key: (quote.price_twd / value - 1) * 100 for key, value in bands.items()}
    forward = []
    for scenario in scenarios:
        scenario_price = scenario.ntm_eps_twd * scenario.exit_pe
        forward.append({**asdict(scenario), "scenario_price_twd": scenario_price, "expected_price_return_pct": (scenario_price / quote.price_twd - 1) * 100})
    technical = calculate_technical_context(stock_records, benchmark_records, quote.price_twd)
    fundamental = calculate_fundamental_context(quarterly, monthly, as_of_date=quote_date)
    diagnostic_rows = build_diagnostic_backtest(stock_records, benchmark_records, points)
    analysis = {
        "experiment_id": "TW-EXP-2330-PE-RIVER-0002", "experiment_status": "EXPLORATORY_NOT_VALIDATED",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbol": symbol,
        "quote": asdict(quote), "quote_fallback_reason": quote_fallback_reason,
        "current_valuation": {"ttm_eps_twd": ttm_eps, "included_periods": periods, "pe_ttm": current_pe, "historical_trailing_pe_percentile": percentile, "historical_observation_count": len(points), "river_band_prices_twd": bands, "price_gap_to_band_pct": gaps},
        "technical_context": technical, "fundamental_context": fundamental, "forward_scenarios": forward,
        "historical_coverage": {"start": points[0].trade_date if points else None, "end": points[-1].trade_date if points else None, "status": "AVAILABLE_PIT_TRAILING_PE_HISTORY_NOT_TEN_YEAR_FORWARD_PE"},
        "diagnostic_backtest": {"horizon_sessions": 63, "rows": diagnostic_rows, "summary": summarize_diagnostic(diagnostic_rows), "status": "SINGLE_STOCK_SHORT_HISTORY_DIAGNOSTIC_NOT_ALPHA_VALIDATION"},
        "method_notes": [
            "Current quote is secondary and delayed when Yahoo is available; otherwise the latest completed official TWSE close is used and tagged as fallback.",
            "Historical P/E is Point-in-Time trailing P/E, not reconstructed historical Forward P/E.",
            "MA50, MA200 and 12-1 momentum use completed official TWSE sessions.",
            "Monthly revenue is official current context but does not yet carry research_available_at for historical backtesting.",
            "The 63-session diagnostic uses one stock and short history; it cannot establish alpha.",
            "No buy, sell, target-price recommendation or live-capital authorization is produced.",
        ],
    }
    return analysis, points, diagnostic_rows


def run_live(*, symbol: str, benchmark_symbol: str, history_start: date, output_dir: Path, eps_path: Path, multiples_path: Path, scenarios_path: Path, fundamentals_path: Path, monthly_revenue_path: Path, stock_history_csv: Path | None = None, benchmark_history_csv: Path | None = None, quote_transport: HttpTransport | None = None) -> dict[str, object]:
    today = datetime.now(TAIPEI).date()
    stock_records = fetch_history(symbol, history_start, today, csv_path=stock_history_csv)
    benchmark_records = fetch_history(benchmark_symbol, history_start, today, csv_path=benchmark_history_csv)
    quote, fallback_reason = resolve_quote(symbol, stock_records, transport=quote_transport)
    eps, multiples, scenarios = load_eps_history(eps_path), load_multiples(multiples_path), load_scenarios(scenarios_path)
    quarterly, monthly = load_quarterly_fundamentals(fundamentals_path), load_monthly_revenue(monthly_revenue_path)
    analysis, points, diagnostic_rows = build_live_analysis(symbol=symbol, quote=quote, quote_fallback_reason=fallback_reason, stock_records=stock_records, benchmark_records=benchmark_records, eps_observations=eps, multiples=multiples, scenarios=scenarios, quarterly=quarterly, monthly=monthly)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "live_analysis.json", analysis); write_historical_pe_csv(output_dir / "historical_pe.csv", points)
    write_diagnostic_csv(output_dir / "diagnostic_backtest.csv", diagnostic_rows); write_live_html(output_dir / "live_report.html", analysis, points, multiples)
    return analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a delayed live 2330 PE-river research report.")
    parser.add_argument("--symbol", default="2330.TW"); parser.add_argument("--benchmark-symbol", default="0050.TW")
    parser.add_argument("--history-start", type=date.fromisoformat, default=date(2024, 1, 1)); parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--eps", type=Path, default=DEFAULT_EXPERIMENT_DIR / "eps_history.csv"); parser.add_argument("--multiples", type=Path, default=DEFAULT_EXPERIMENT_DIR / "river_multiples.csv")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_EXPERIMENT_DIR / "forward_scenarios.csv"); parser.add_argument("--fundamentals", type=Path, default=DEFAULT_EXPERIMENT_DIR / "quarterly_fundamentals.csv")
    parser.add_argument("--monthly-revenue", type=Path, default=DEFAULT_EXPERIMENT_DIR / "monthly_revenue.csv"); parser.add_argument("--stock-history-csv", type=Path); parser.add_argument("--benchmark-history-csv", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(argv)
    try:
        analysis = run_live(symbol=args.symbol, benchmark_symbol=args.benchmark_symbol, history_start=args.history_start, output_dir=args.output_dir, eps_path=args.eps, multiples_path=args.multiples, scenarios_path=args.scenarios, fundamentals_path=args.fundamentals, monthly_revenue_path=args.monthly_revenue, stock_history_csv=args.stock_history_csv, benchmark_history_csv=args.benchmark_history_csv)
    except (LiveExperimentError, ExperimentInputError) as exc:
        parser.error(str(exc))
    print(f"Symbol: {analysis['symbol']}"); print(f"Price: {analysis['quote']['price_twd']} ({analysis['quote']['data_status']})")
    print(f"TTM P/E: {analysis['current_valuation']['pe_ttm']}"); print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
