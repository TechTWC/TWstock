from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Iterable, Sequence

from twstock_data.models import MarketDataRecord

from .pe_river import ExperimentInputError, ttm_eps_as_of
from .pe_river_live_sources import FundamentalObservation, LiveExperimentError, MonthlyRevenueObservation, positive_decimal


@dataclass(frozen=True)
class HistoricalPEPoint:
    trade_date: date
    close_twd: Decimal
    ttm_eps_twd: Decimal
    pe_ttm: Decimal
    bands: dict[str, Decimal]


def build_historical_pe_points(records: Iterable[MarketDataRecord], eps_observations: Iterable[object], multiples: Iterable[Decimal]) -> list[HistoricalPEPoint]:
    points: list[HistoricalPEPoint] = []
    for record in sorted(records, key=lambda item: item.trade_date):
        trade_date = date.fromisoformat(record.trade_date)
        try:
            ttm_eps, _ = ttm_eps_as_of(eps_observations, trade_date)
        except ExperimentInputError:
            continue
        close = positive_decimal(record.close_price, field="close_price")
        points.append(HistoricalPEPoint(trade_date, close, ttm_eps, close / ttm_eps, {str(value): ttm_eps * value for value in multiples}))
    return points


def empirical_percentile(values: Iterable[Decimal], current: Decimal) -> Decimal | None:
    ordered = sorted(values)
    return Decimal(bisect_right(ordered, current)) / Decimal(len(ordered)) * Decimal("100") if ordered else None


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _momentum_12_1(records: Sequence[MarketDataRecord]) -> Decimal | None:
    if len(records) < 252:
        return None
    recent = positive_decimal(records[-21].close_price, field="12-1 recent")
    start = positive_decimal(records[-252].close_price, field="12-1 start")
    return (recent / start - Decimal("1")) * Decimal("100")


def calculate_technical_context(stock_records: Sequence[MarketDataRecord], benchmark_records: Sequence[MarketDataRecord], current_price: Decimal) -> dict[str, object]:
    if not stock_records:
        raise LiveExperimentError("Stock history is empty")
    closes = [positive_decimal(item.close_price, field="close_price") for item in stock_records]
    ma50 = _mean(closes[-50:]) if len(closes) >= 50 else None
    ma200 = _mean(closes[-200:]) if len(closes) >= 200 else None
    high60, low60 = max(closes[-60:]), min(closes[-60:])
    stock_momentum, benchmark_momentum = _momentum_12_1(stock_records), _momentum_12_1(benchmark_records)
    return {
        "official_last_trade_date": stock_records[-1].trade_date,
        "official_last_close_twd": closes[-1],
        "ma50_twd": ma50, "ma200_twd": ma200,
        "price_vs_ma50_pct": (current_price / ma50 - 1) * 100 if ma50 else None,
        "price_vs_ma200_pct": (current_price / ma200 - 1) * 100 if ma200 else None,
        "high_60d_twd": high60, "low_60d_twd": low60,
        "drawdown_from_60d_high_pct": (current_price / high60 - 1) * 100,
        "stock_momentum_12_1_pct": stock_momentum,
        "benchmark_momentum_12_1_pct": benchmark_momentum,
        "relative_momentum_12_1_pct": stock_momentum - benchmark_momentum if stock_momentum is not None and benchmark_momentum is not None else None,
        "benchmark_symbol": benchmark_records[-1].canonical_symbol if benchmark_records else None,
    }


def calculate_fundamental_context(quarterly: Sequence[FundamentalObservation], monthly: Sequence[MonthlyRevenueObservation], *, as_of_date: date) -> dict[str, object]:
    usable = [item for item in quarterly if item.research_available_date <= as_of_date]
    if not usable:
        raise LiveExperimentError("No PIT-available quarterly fundamentals")
    latest, previous = usable[-1], usable[-2] if len(usable) >= 2 else None
    prior_year = usable[-5] if len(usable) >= 5 else None
    revenue_by_month = {item.month: item for item in monthly}
    yoy_rows: list[dict[str, object]] = []
    for item in monthly:
        year, month = map(int, item.month.split("-"))
        prior = revenue_by_month.get(f"{year - 1:04d}-{month:02d}")
        if prior:
            yoy_rows.append({
                "month": item.month, "revenue_million_twd": item.revenue_million_twd,
                "prior_year_revenue_million_twd": prior.revenue_million_twd,
                "yoy_pct": (item.revenue_million_twd / prior.revenue_million_twd - 1) * 100,
                "data_status": item.data_status,
            })
    recent_three = [Decimal(str(item["yoy_pct"])) for item in yoy_rows[-3:]]
    return {
        "latest_quarter": asdict(latest),
        "gross_margin_qoq_ppt": latest.gross_margin_pct - previous.gross_margin_pct if previous else None,
        "operating_margin_qoq_ppt": latest.operating_margin_pct - previous.operating_margin_pct if previous else None,
        "gross_margin_yoy_ppt": latest.gross_margin_pct - prior_year.gross_margin_pct if prior_year else None,
        "operating_margin_yoy_ppt": latest.operating_margin_pct - prior_year.operating_margin_pct if prior_year else None,
        "monthly_revenue_yoy": yoy_rows,
        "latest_monthly_revenue_yoy": yoy_rows[-1] if yoy_rows else None,
        "latest_3m_average_revenue_yoy_pct": _mean(recent_three),
        "monthly_revenue_pit_status": "CURRENT_CONTEXT_ONLY_NOT_PIT_BACKTEST_READY",
    }


def _benchmark_close(benchmark_records: Sequence[MarketDataRecord], target: date) -> Decimal | None:
    eligible = [record for record in benchmark_records if date.fromisoformat(record.trade_date) <= target]
    return positive_decimal(eligible[-1].close_price, field="benchmark close") if eligible else None


def build_diagnostic_backtest(stock_records: Sequence[MarketDataRecord], benchmark_records: Sequence[MarketDataRecord], pe_points: Sequence[HistoricalPEPoint], *, horizon_sessions: int = 63) -> list[dict[str, object]]:
    if not pe_points:
        return []
    pe_by_date = {point.trade_date: point for point in pe_points}
    record_index = {date.fromisoformat(item.trade_date): index for index, item in enumerate(stock_records)}
    month_ends: list[date] = []
    for point in pe_points:
        if not month_ends or point.trade_date.strftime("%Y-%m") != month_ends[-1].strftime("%Y-%m"):
            month_ends.append(point.trade_date)
        else:
            month_ends[-1] = point.trade_date
    rows, expanding, ordered, cursor = [], [], sorted(pe_points, key=lambda item: item.trade_date), 0
    for signal_date in month_ends:
        while cursor < len(ordered) and ordered[cursor].trade_date <= signal_date:
            expanding.append(ordered[cursor].pe_ttm); cursor += 1
        index = record_index.get(signal_date)
        if index is None or index < 199 or index + horizon_sessions >= len(stock_records) or len(expanding) < 60:
            continue
        point = pe_by_date[signal_date]
        percentile = empirical_percentile(expanding, point.pe_ttm)
        ma200 = _mean([positive_decimal(item.close_price, field="backtest close") for item in stock_records[index-199:index+1]])
        if percentile is None or ma200 is None:
            continue
        bucket = "LOW_PE_WITH_TREND" if percentile <= 30 and point.close_twd >= ma200 else "HIGH_PE" if percentile >= 80 else "NEUTRAL"
        exit_record = stock_records[index + horizon_sessions]
        exit_date, stock_exit = date.fromisoformat(exit_record.trade_date), positive_decimal(exit_record.close_price, field="backtest exit")
        stock_return = (stock_exit / point.close_twd - 1) * 100
        bench_start, bench_exit = _benchmark_close(benchmark_records, signal_date), _benchmark_close(benchmark_records, exit_date)
        bench_return = (bench_exit / bench_start - 1) * 100 if bench_start and bench_exit else None
        rows.append({
            "signal_date": signal_date, "exit_date": exit_date, "bucket": bucket,
            "pe_ttm": point.pe_ttm, "expanding_pe_percentile": percentile,
            "close_twd": point.close_twd, "ma200_twd": ma200,
            "stock_forward_return_pct": stock_return, "benchmark_forward_return_pct": bench_return,
            "excess_return_pct": stock_return - bench_return if bench_return is not None else None,
        })
    return rows


def summarize_diagnostic(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    summaries = []
    for bucket in ("LOW_PE_WITH_TREND", "NEUTRAL", "HIGH_PE"):
        selected = [row for row in rows if row["bucket"] == bucket]
        excess = [Decimal(str(row["excess_return_pct"])) for row in selected if row["excess_return_pct"] is not None]
        summaries.append({
            "bucket": bucket, "observation_count": len(selected),
            "average_excess_return_pct": _mean(excess),
            "median_excess_return_pct": Decimal(str(median(excess))) if excess else None,
            "positive_excess_rate_pct": Decimal(sum(value > 0 for value in excess)) / Decimal(len(excess)) * 100 if excess else None,
        })
    return summaries
