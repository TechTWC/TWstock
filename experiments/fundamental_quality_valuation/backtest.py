from __future__ import annotations

from datetime import date
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .engine import classify_security
from .models import SecurityData, StateDetail
from .validation import attach_realized_persistence, realized_fundamental_state


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
                "peer_group": security.peer_group,
                "financial_subtype": security.financial_subtype,
                "period_end": observation["period_end"].isoformat(),
                "announcement_date": (
                    observation["announcement_date"].isoformat()
                    if pd.notna(observation.get("announcement_date"))
                    else None
                ),
                "available_date": signal_date.isoformat(),
                "signal_date": signal_date.isoformat(),
                "execution_date": entry["date"].isoformat(),
                "trade_date": entry["date"].isoformat(),
                "price_date": entry["date"].isoformat(),
                "source": security.source,
                "retrieval_date": security.source_metadata.get("retrieval_date"),
                "source_version": security.source_metadata.get("source_version"),
                "source_hash": security.source_metadata.get("source_hash"),
                "quality": result.quality,
                "fundamental_state": result.fundamental_state,
                "state_detail": result.state_detail,
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
                "state_validation": _state_validation(q, row_index) if result.state_detail == StateDetail.TURNING_UP.value else None,
                "survivorship_bias": "CURRENT_CONSTITUENTS_ONLY",
                "availability_quality": str(observation.get("availability_method", "AVAILABLE_DATE_PROXY")),
                "price_return_quality": "ADJUSTED_RETURN_SECONDARY_SOURCE" if price_column == "adj_close" else "UNADJUSTED_PRICE_RETURN",
            }
            realized = realized_fundamental_state(
                q,
                row_index,
                security.sector_logic,
                config.get("realized_state_rules", {}),
            )
            record.update(
                {
                    "realized_fundamental_state": realized.pop("realized_state"),
                    **realized,
                }
            )
            for years, quarters in ((1, 4), (3, 12), (5, 20)):
                future_quality = _future_quality(q, row_index, quarters)
                for metric, value in future_quality.items():
                    record[f"future_{years}y_{metric}"] = value
            for horizon in horizons:
                exit_position = entry_position + horizon
                prefix = f"{horizon}d"
                if exit_position >= len(market):
                    for name in (
                        "return",
                        "benchmark_return",
                        "excess_return",
                        "max_close_to_close_favorable_return",
                        "max_close_to_close_adverse_return",
                        "max_drawdown",
                    ):
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
                record[f"benchmark_return_{prefix}"] = benchmark_return
                record[f"excess_return_{prefix}"] = stock_return - benchmark_return if stock_return is not None and benchmark_return is not None else None
                record[f"max_close_to_close_favorable_return_{prefix}"] = highest / entry_price - 1.0 if highest is not None else None
                record[f"max_close_to_close_adverse_return_{prefix}"] = lowest / entry_price - 1.0 if lowest is not None else None
                record[f"max_drawdown_{prefix}"] = _max_drawdown(window[price_column])
            records.append(record)
    events = pd.DataFrame(records)
    if events.empty:
        return events
    for column in ("roe", "revenue_yoy"):
        values = pd.to_numeric(events[column], errors="coerce")
        events[f"{column}_cross_sectional_percentile"] = values.groupby(events["period_end"]).rank(pct=True)
    return attach_realized_persistence(events)


def _cluster_standard_error(frame: pd.DataFrame, values: pd.Series, cluster: pd.Series) -> float | None:
    selected = pd.DataFrame({"value": values, "cluster": cluster}).dropna()
    if len(selected) < 2 or selected["cluster"].nunique() < 2:
        return None
    mean = float(selected["value"].mean())
    contributions = selected.assign(centered=selected["value"] - mean).groupby("cluster")["centered"].sum()
    groups = len(contributions)
    variance = groups / (groups - 1) * float((contributions**2).sum()) / len(selected) ** 2
    return math.sqrt(max(variance, 0.0))


def _summary_row(
    frame: pd.DataFrame,
    label: str,
    horizon: int,
    *,
    return_column: str | None = None,
    excess_column: str | None = None,
) -> dict[str, Any]:
    prefix = f"{horizon}d"
    return_name = return_column or f"return_{prefix}"
    excess_name = excess_column or f"excess_return_{prefix}"
    valid = pd.to_numeric(frame[return_name], errors="coerce").notna()
    selected = frame.loc[valid].copy()
    returns = pd.to_numeric(selected[return_name], errors="coerce")
    excess_source = selected[excess_name] if excess_name in selected else pd.Series(np.nan, index=selected.index)
    excess = pd.to_numeric(excess_source, errors="coerce").dropna()
    favorable_source = (
        selected[f"max_close_to_close_favorable_return_{prefix}"]
        if f"max_close_to_close_favorable_return_{prefix}" in selected
        else pd.Series(np.nan, index=selected.index)
    )
    favorable = pd.to_numeric(
        favorable_source, errors="coerce"
    ).dropna()
    adverse_source = (
        selected[f"max_close_to_close_adverse_return_{prefix}"]
        if f"max_close_to_close_adverse_return_{prefix}" in selected
        else pd.Series(np.nan, index=selected.index)
    )
    adverse = pd.to_numeric(
        adverse_source, errors="coerce"
    ).dropna()
    drawdown_source = (
        selected[f"max_drawdown_{prefix}"]
        if f"max_drawdown_{prefix}" in selected
        else pd.Series(np.nan, index=selected.index)
    )
    drawdowns = pd.to_numeric(drawdown_source, errors="coerce").dropna()
    if returns.empty:
        return {"baseline": label, "horizon": prefix, "n": 0}
    standard_error = returns.std(ddof=1) / math.sqrt(len(returns)) if len(returns) > 1 else math.nan
    issuer_se = _cluster_standard_error(selected, returns, selected.get("symbol", pd.Series(index=selected.index)))
    signal_dates = selected["signal_date"] if "signal_date" in selected else pd.Series(pd.NaT, index=selected.index)
    time_cluster = pd.to_datetime(signal_dates, errors="coerce").dt.to_period("Q").astype(str)
    time_se = _cluster_standard_error(selected, returns, time_cluster)
    return {
        "baseline": label,
        "horizon": prefix,
        "n": int(len(returns)),
        "unique_issuer_count": int(selected["symbol"].nunique()) if "symbol" in selected else 1,
        "mean_return": float(returns.mean()),
        "median_return": float(returns.median()),
        "positive_rate": float((returns > 0).mean()),
        "mean_excess_return": float(excess.mean()) if not excess.empty else None,
        "median_excess_return": float(excess.median()) if not excess.empty else None,
        "mean_max_close_to_close_favorable_return": float(favorable.mean()) if not favorable.empty else None,
        "mean_max_close_to_close_adverse_return": float(adverse.mean()) if not adverse.empty else None,
        "worst_max_drawdown": float(drawdowns.min()) if not drawdowns.empty else None,
        "iid_standard_error": float(standard_error) if math.isfinite(standard_error) else None,
        "iid_ci95_low": float(returns.mean() - 1.96 * standard_error) if math.isfinite(standard_error) else None,
        "iid_ci95_high": float(returns.mean() + 1.96 * standard_error) if math.isfinite(standard_error) else None,
        "issuer_cluster_standard_error": issuer_se,
        "issuer_cluster_ci95_low": float(returns.mean() - 1.96 * issuer_se) if issuer_se is not None else None,
        "issuer_cluster_ci95_high": float(returns.mean() + 1.96 * issuer_se) if issuer_se is not None else None,
        "time_cluster_standard_error": time_se,
        "time_cluster_ci95_low": float(returns.mean() - 1.96 * time_se) if time_se is not None else None,
        "time_cluster_ci95_high": float(returns.mean() + 1.96 * time_se) if time_se is not None else None,
        "independence_assumption": "NON_IID_REPEATED_ISSUER_OVERLAPPING_WINDOWS",
    }


def summarize_baselines(events: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    conditions = {
        "B_CURRENT_CONSTITUENT_UNCONDITIONAL": pd.Series(True, index=events.index),
        "C_STATE_ONLY": events["fundamental_state"] == "IMPROVING",
        "D_QUALITY_ONLY": events["quality"] == "GOOD",
        "E_VALUATION_ONLY": events["valuation"] == "LOW",
        "F_QUALITY_PLUS_VALUATION": (events["quality"] == "GOOD") & events["valuation"].isin(["LOW", "NORMAL"]),
        "G_STATE_PLUS_VALUATION": (events["fundamental_state"] == "IMPROVING") & events["valuation"].isin(["LOW", "NORMAL"]),
        "H_FULL_MODEL": (
            (events["quality"] == "GOOD")
            & (events["fundamental_state"] == "IMPROVING")
            & events["valuation"].isin(["LOW", "NORMAL"])
        ),
    }
    rows = []
    benchmark_dates = events.sort_values("signal_date").drop_duplicates("signal_date").copy()
    benchmark_dates["symbol"] = "0050"
    for horizon in config["backtest"]["forward_horizons"]:
        prefix = f"{int(horizon)}d"
        benchmark_dates[f"benchmark_excess_return_{prefix}"] = np.where(
            pd.to_numeric(benchmark_dates[f"benchmark_return_{prefix}"], errors="coerce").notna(),
            0.0,
            np.nan,
        )
        rows.append(
            _summary_row(
                benchmark_dates,
                "A_0050_BUY_AND_HOLD",
                int(horizon),
                return_column=f"benchmark_return_{prefix}",
                excess_column=f"benchmark_excess_return_{prefix}",
            )
        )
    for label, condition in conditions.items():
        selected = events[condition.fillna(False)]
        for horizon in config["backtest"]["forward_horizons"]:
            rows.append(_summary_row(selected, label, int(horizon)))
    return pd.DataFrame(rows)


def summarize_return_diagnostics(events: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    horizons = [horizon for horizon in config["backtest"]["forward_horizons"] if int(horizon) in (60, 120, 252, 504)]
    for state in ("IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN", "ALL"):
        selected = events if state == "ALL" else events[events["fundamental_state"] == state]
        for horizon in horizons:
            row = _summary_row(selected, f"STATE_{state}", int(horizon))
            row["diagnostic_only"] = True
            rows.append(row)
    return pd.DataFrame(rows)


def summarize_robustness(events: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    semiconductor = events["peer_group"].str.contains(
        "SEMICONDUCTOR|IC_DESIGN|MEMORY", case=False, na=False
    )
    signal_dates = pd.to_datetime(events["signal_date"], errors="coerce")
    groups = {
        "FULL_SAMPLE": pd.Series(True, index=events.index),
        "EX_TSMC": events["symbol"].astype(str) != "2330",
        "EX_SEMICONDUCTOR": ~semiconductor,
        "FINANCIAL_ONLY": events["sector_logic"] == "FINANCIAL",
        "NON_FINANCIAL_ONLY": events["sector_logic"] != "FINANCIAL",
        "PRE_2023": signal_dates.dt.year < 2023,
        "2023_AND_LATER": signal_dates.dt.year >= 2023,
    }
    full_model = (
        (events["quality"] == "GOOD")
        & (events["fundamental_state"] == "IMPROVING")
        & events["valuation"].isin(["LOW", "NORMAL"])
    )
    rows: list[dict[str, Any]] = []
    for name, condition in groups.items():
        selected = events[condition.fillna(False) & full_model]
        for horizon in (60, 120, 252, 504):
            if horizon in [int(value) for value in config["backtest"]["forward_horizons"]]:
                row = _summary_row(selected, f"ROBUSTNESS_{name}", horizon)
                row["scope"] = name
                row["model_filter"] = "GOOD + IMPROVING + LOW/NORMAL"
                rows.append(row)
    return pd.DataFrame(rows)


def summarize_state_validation(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "state_validation" not in events:
        return pd.DataFrame(columns=["label", "count", "share", "definition"])
    values = events["state_validation"].dropna()
    counts = values.value_counts()
    total = int(counts.sum())
    before = {
        "CORRECT": (74, 0.23125),
        "TOO_EARLY": (18, 0.05625),
        "TOO_LATE": (153, 0.478125),
        "FALSE_RECOVERY": (75, 0.234375),
    }
    definitions = {
        "CORRECT": "next two reported quarters improve/confirm revenue and EPS without a fourth-quarter reversal",
        "TOO_EARLY": "confirmation appears only after the first future quarter",
        "TOO_LATE": "revenue and EPS were already positive in both prior observations when TURNING_UP fired",
        "FALSE_RECOVERY": "future revenue/EPS do not confirm, or reverse by the fourth future quarter",
    }
    return pd.DataFrame(
        [
            {
                "label": label,
                "count": int(counts.get(label, 0)),
                "share": float(counts.get(label, 0) / total) if total else None,
                "before_reviewed_head_count": before[label][0],
                "before_reviewed_head_share": before[label][1],
                "definition": definitions[label],
            }
            for label in ("CORRECT", "TOO_EARLY", "TOO_LATE", "FALSE_RECOVERY")
        ]
    )


def diagnose_too_late(events: pd.DataFrame) -> pd.DataFrame:
    selected = events[events.get("state_validation") == "TOO_LATE"].copy()
    factors = {
        "STATE_RULE_REQUIRES_MULTI_PERIOD_CONFIRMATION": len(selected),
        "TTM_ROLLING_WINDOW_LAG": len(selected),
        "QUARTERLY_REPORTING_FREQUENCY": len(selected),
        "AVAILABLE_DATE_PROXY_TIMING_UNCERTAINTY": int(
            (selected.get("availability_quality") == "AVAILABLE_DATE_PROXY").sum()
        ),
    }
    return pd.DataFrame(
        [
            {
                "factor": factor,
                "count": int(count),
                "share_of_too_late": float(count / len(selected)) if len(selected) else None,
                "interpretation": "diagnostic contributor; not causal attribution and not used to tune thresholds",
            }
            for factor, count in factors.items()
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
