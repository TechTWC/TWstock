from __future__ import annotations

from datetime import date
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .engine import classify_security
from .models import FundamentalState, SecurityData


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _max_drawdown(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None
    running_high = clean.cummax()
    drawdown = clean / running_high - 1.0
    return float(drawdown.min())


def _benchmark_return(benchmark: pd.DataFrame, entry_date: date, exit_date: date) -> float | None:
    if benchmark.empty:
        return None
    entry = benchmark[benchmark["date"] >= entry_date]
    exit_rows = benchmark[benchmark["date"] <= exit_date]
    if entry.empty or exit_rows.empty:
        return None
    entry_row = entry.iloc[0]
    exit_row = exit_rows.iloc[-1]
    price_column = "adj_close" if "adj_close" in benchmark and benchmark["adj_close"].notna().any() else "close"
    entry_price = _finite(entry_row[price_column])
    exit_price = _finite(exit_row[price_column])
    if entry_price is None or exit_price is None or entry_price <= 0:
        return None
    return exit_price / entry_price - 1.0


def _state_validation(q: pd.DataFrame, row_index: int) -> str | None:
    future = q.iloc[row_index + 1 : row_index + 5]
    if len(future) < 2:
        return None
    current = q.iloc[row_index]
    current_rev = _finite(current.get("revenue_yoy"))
    current_eps = _finite(current.get("eps_yoy"))
    if current_rev is None or current_eps is None:
        return None
    future_rev = [_finite(value) for value in future["revenue_yoy"]]
    future_eps = [_finite(value) for value in future["eps_yoy"]]
    if any(value is None for value in future_rev[:2] + future_eps[:2]):
        return None
    previous = q.iloc[max(0, row_index - 2) : row_index]
    already_improved = (
        len(previous) == 2
        and all((_finite(value) or -math.inf) > 0 for value in previous["revenue_yoy"])
        and all((_finite(value) or -math.inf) > 0 for value in previous["eps_yoy"])
    )
    if already_improved:
        return "TOO_LATE"
    first_improves = future_rev[0] >= current_rev and future_eps[0] >= current_eps
    second_confirms = future_rev[1] >= current_rev and future_eps[1] >= current_eps
    if first_improves and second_confirms:
        if len(future_rev) >= 4 and future_rev[3] is not None and future_eps[3] is not None:
            if future_rev[3] < current_rev and future_eps[3] < current_eps:
                return "FALSE_RECOVERY"
        return "CORRECT"
    later = [
        index
        for index, (revenue, eps) in enumerate(zip(future_rev[1:], future_eps[1:]), start=1)
        if revenue is not None and eps is not None and revenue >= current_rev and eps >= current_eps
    ]
    if later:
        return "TOO_EARLY"
    return "FALSE_RECOVERY"


def _future_quality(q: pd.DataFrame, row_index: int, quarters: int) -> dict[str, float | None]:
    target = row_index + quarters
    if target >= len(q):
        return {"roe": None, "roic": None, "eps_growth": None, "fcf_positive": None, "margin_change": None}
    current = q.iloc[row_index]
    future = q.iloc[target]
    current_eps = _finite(current.get("ttm_eps"))
    future_eps = _finite(future.get("ttm_eps"))
    eps_growth = None
    if current_eps is not None and future_eps is not None and current_eps > 0:
        eps_growth = future_eps / current_eps - 1.0
    current_margin = _finite(current.get("operating_margin"))
    future_margin = _finite(future.get("operating_margin"))
    return {
        "roe": _finite(future.get("roe")),
        "roic": _finite(future.get("roic")),
        "eps_growth": eps_growth,
        "fcf_positive": 1.0 if (_finite(future.get("ttm_fcf")) or 0) > 0 else 0.0,
        "margin_change": future_margin - current_margin if future_margin is not None and current_margin is not None else None,
    }


def build_backtest_events(
    securities: Iterable[SecurityData],
    benchmark: pd.DataFrame,
    config: dict[str, Any],
    as_of: date,
) -> pd.DataFrame:
    start = date.fromisoformat(config["backtest"]["start_date"])
    horizons = [int(value) for value in config["backtest"]["forward_horizons"]]
    records: list[dict[str, Any]] = []
    for security in securities:
        q = security.quarterly.sort_values("available_date").reset_index(drop=True)
        market = security.market.sort_values("date").reset_index(drop=True)
        price_column = "adj_close" if "adj_close" in market and market["adj_close"].notna().any() else "close"
        for row_index, observation in q.iterrows():
            signal_date = observation["available_date"]
            if signal_date < start or signal_date > as_of or row_index < 10:
                continue
            result = classify_security(security, signal_date, config)
            future_market = market[market["date"] > signal_date]
            if future_market.empty:
                continue
            entry_position = future_market.index[0]
            entry = market.loc[entry_position]
            entry_price = _finite(entry[price_column])
            if entry_price is None or entry_price <= 0:
                continue
            record: dict[str, Any] = {
                "symbol": security.symbol,
                "company": security.company,
                "industry": security.industry,
                "sector_logic": security.sector_logic.value,
                "period_end": observation["period_end"].isoformat(),
                "signal_date": signal_date.isoformat(),
                "execution_date": entry["date"].isoformat(),
                "quality": result.quality,
                "fundamental_state": result.fundamental_state,
                "valuation": result.valuation,
                "research_classification": result.research_classification,
                "data_quality": result.data_quality,
                "pe": result.metrics.get("pe"),
                "pb": result.metrics.get("pb"),
                "pe_percentile": result.metrics.get("pe_percentile"),
                "pb_percentile": result.metrics.get("pb_percentile"),
                "roe": result.metrics.get("roe"),
                "roic": result.metrics.get("roic"),
                "revenue_yoy": result.metrics.get("revenue_yoy"),
                "eps_yoy": result.metrics.get("eps_yoy"),
                "state_validation": _state_validation(q, row_index) if result.fundamental_state == FundamentalState.TURNING_UP.value else None,
                "survivorship_bias": "SURVIVORSHIP_BIAS_PRESENT",
                "availability_quality": "AVAILABLE_DATE_PROXY",
                "price_return_quality": "ADJUSTED_RETURN_SECONDARY_SOURCE" if price_column == "adj_close" else "UNADJUSTED_PRICE_RETURN",
            }
            for years, quarters in ((1, 4), (3, 12), (5, 20)):
                future_quality = _future_quality(q, row_index, quarters)
                for metric, value in future_quality.items():
                    record[f"future_{years}y_{metric}"] = value
            for horizon in horizons:
                exit_position = entry_position + horizon
                prefix = f"{horizon}d"
                if exit_position >= len(market):
                    for name in ("return", "excess_return", "mfe", "mae", "max_drawdown"):
                        record[f"{name}_{prefix}"] = None
                    continue
                exit_row = market.loc[exit_position]
                window = market.loc[entry_position:exit_position]
                exit_price = _finite(exit_row[price_column])
                stock_return = exit_price / entry_price - 1.0 if exit_price is not None else None
                benchmark_return = _benchmark_return(benchmark, entry["date"], exit_row["date"])
                high_column = price_column
                low_column = price_column
                highest = _finite(pd.to_numeric(window[high_column], errors="coerce").max())
                lowest = _finite(pd.to_numeric(window[low_column], errors="coerce").min())
                record[f"return_{prefix}"] = stock_return
                record[f"excess_return_{prefix}"] = stock_return - benchmark_return if stock_return is not None and benchmark_return is not None else None
                record[f"mfe_{prefix}"] = highest / entry_price - 1.0 if highest is not None else None
                record[f"mae_{prefix}"] = lowest / entry_price - 1.0 if lowest is not None else None
                record[f"max_drawdown_{prefix}"] = _max_drawdown(window[price_column])
            records.append(record)
    events = pd.DataFrame(records)
    if events.empty:
        return events
    for column in ("roe", "revenue_yoy"):
        values = pd.to_numeric(events[column], errors="coerce")
        events[f"{column}_cross_sectional_percentile"] = values.groupby(events["period_end"]).rank(pct=True)
    return events


def _summary_row(frame: pd.DataFrame, label: str, horizon: int) -> dict[str, Any]:
    prefix = f"{horizon}d"
    returns = pd.to_numeric(frame[f"return_{prefix}"], errors="coerce").dropna()
    excess = pd.to_numeric(frame[f"excess_return_{prefix}"], errors="coerce").dropna()
    mfe = pd.to_numeric(frame[f"mfe_{prefix}"], errors="coerce").dropna()
    mae = pd.to_numeric(frame[f"mae_{prefix}"], errors="coerce").dropna()
    drawdowns = pd.to_numeric(frame[f"max_drawdown_{prefix}"], errors="coerce").dropna()
    if returns.empty:
        return {"baseline": label, "horizon": prefix, "n": 0}
    standard_error = returns.std(ddof=1) / math.sqrt(len(returns)) if len(returns) > 1 else math.nan
    return {
        "baseline": label,
        "horizon": prefix,
        "n": int(len(returns)),
        "mean_return": float(returns.mean()),
        "median_return": float(returns.median()),
        "hit_rate": float((returns > 0).mean()),
        "mean_excess_return": float(excess.mean()) if not excess.empty else None,
        "mean_mfe": float(mfe.mean()) if not mfe.empty else None,
        "mean_mae": float(mae.mean()) if not mae.empty else None,
        "worst_max_drawdown": float(drawdowns.min()) if not drawdowns.empty else None,
        "ci95_low": float(returns.mean() - 1.96 * standard_error) if math.isfinite(standard_error) else None,
        "ci95_high": float(returns.mean() + 1.96 * standard_error) if math.isfinite(standard_error) else None,
    }


def summarize_baselines(events: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    conditions = {
        "A_ALL_CURRENT_0050": pd.Series(True, index=events.index),
        "B_LOW_PE": pd.to_numeric(events["pe_percentile"], errors="coerce") <= 0.25,
        "C_LOW_PB": pd.to_numeric(events["pb_percentile"], errors="coerce") <= 0.25,
        "D_HIGH_ROE": pd.to_numeric(events["roe_cross_sectional_percentile"], errors="coerce") >= 0.75,
        "E_HIGH_REVENUE_GROWTH": pd.to_numeric(events["revenue_yoy_cross_sectional_percentile"], errors="coerce") >= 0.75,
        "F_QUALITY_ONLY": events["quality"] == "GOOD",
        "G_VALUATION_ONLY": events["valuation"] == "LOW",
        "H_FULL_MODEL": (
            (events["quality"] == "GOOD")
            & (events["fundamental_state"] == "TURNING_UP")
            & events["valuation"].isin(["LOW", "NORMAL"])
        ),
    }
    rows = []
    for label, condition in conditions.items():
        selected = events[condition.fillna(False)]
        for horizon in config["backtest"]["forward_horizons"]:
            rows.append(_summary_row(selected, label, int(horizon)))
    return pd.DataFrame(rows)


def summarize_state_validation(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "state_validation" not in events:
        return pd.DataFrame(columns=["label", "count", "share"])
    values = events["state_validation"].dropna()
    counts = values.value_counts()
    total = int(counts.sum())
    return pd.DataFrame(
        [
            {"label": label, "count": int(count), "share": float(count / total) if total else None}
            for label, count in counts.items()
        ]
    )


def summarize_quality_persistence(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if events.empty:
        return pd.DataFrame()
    for quality, group in events.groupby("quality"):
        for years in (1, 3, 5):
            row: dict[str, Any] = {"quality": quality, "horizon": f"{years}Y", "n_events": int(len(group))}
            for metric in ("roe", "roic", "eps_growth", "fcf_positive", "margin_change"):
                values = pd.to_numeric(group[f"future_{years}y_{metric}"], errors="coerce").dropna()
                row[f"median_{metric}"] = float(values.median()) if not values.empty else None
                row[f"n_{metric}"] = int(len(values))
            rows.append(row)
    return pd.DataFrame(rows)
