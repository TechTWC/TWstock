from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .stage_a import canonical_hash, sha256_path


STAGE_B_STARTING_HEAD = "9a5f2ed69c960b1993b144caee1308c7f8a8046d"
EXPECTED_UNIVERSE_SHA256 = "aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46"
EXPECTED_SIGNAL_SHA256 = "9c13f87abe8ca25efeb869482724eb49f89c1c234df240d72472641e6bd81241"
EXPECTED_FROZEN_RULES_HASH = "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f"
EXPECTED_STAGE_A_MANIFEST_IDENTITY = "fbc45f41048d9af30a2e9c04ae53d91715cee42087c89c08f818b23bbed1fcf9"
EXPECTED_SIGNAL_ROWS = 1563
EXPECTED_NON_FINANCIAL_ISSUERS = 38
EXPECTED_FINANCIAL_ISSUERS = 12
PRIMARY_HORIZONS = (60, 120, 252, 504)
MIN_SUPPORT_OBSERVATIONS = 30
MIN_SUPPORT_ISSUERS = 5
BOOTSTRAP_REPLICATIONS = 399

CANONICAL_STATES = ("IMPROVING", "STABLE", "DETERIORATING")
STATE_DETAILS = (
    "BOTTOMING",
    "TURNING_UP",
    "CONFIRMED_GROWTH",
    "MATURE_GROWTH",
    "DECELERATING",
    "DETERIORATING",
    "UNKNOWN",
)
QUALITY_BUCKETS = ("GOOD", "ACCEPTABLE", "WEAK", "UNKNOWN")
VALUATION_BUCKETS = ("LOW", "NORMAL", "HIGH", "NOT_MEANINGFUL")
TIMING_LABELS = ("CORRECT", "TOO_EARLY", "TOO_LATE", "FALSE_RECOVERY")

EVIDENCE_RUBRIC = {
    "registered_before_results": True,
    "support_gate": {
        "minimum_observations": MIN_SUPPORT_OBSERVATIONS,
        "minimum_unique_issuers": MIN_SUPPORT_ISSUERS,
    },
    "axis_directional_rule": (
        "At least three of four primary horizons must show both positive median-excess "
        "lift and positive outperform-rate lift for the pre-specified leading bucket "
        "versus all eligible observations."
    ),
    "axis_cluster_rule": (
        "At least one primary horizon must have a positive issuer- or time-clustered "
        "95% lower confidence bound for mean excess return."
    ),
    "economic_ordering_rule": (
        "A main axis must exhibit its pre-specified strict ordering in at least three "
        "primary horizons to count toward MODERATE or STRONG: IMPROVING > STABLE > "
        "DETERIORATING; GOOD > ACCEPTABLE > WEAK; LOW > NORMAL > HIGH."
    ),
    "concentration_gate": {
        "issuer_hhi_max": 0.15,
        "largest_issuer_observation_share_max": 0.10,
        "sector_hhi_max": 0.15,
        "largest_sector_observation_share_max": 0.25,
    },
    "grades": {
        "NONE": "No axis or supported intersection meets the minimum repeated-horizon association rule.",
        "WEAK": (
            "At least one axis or supported intersection improves median excess return and "
            "outperformance in at least two horizons, but consistency, clustered uncertainty, "
            "regime robustness, or concentration robustness is incomplete."
        ),
        "MODERATE": (
            "At least one pre-specified axis meets the three-of-four directional rule and the "
            "cluster rule, remains positive ex-TSMC and after top-five removal, and is not "
            "confined to only one fixed regime."
        ),
        "STRONG": (
            "At least two pre-specified axes including Fundamental State meet MODERATE; the "
            "state ordering holds in at least three horizons; issuer and time clustered lower "
            "bounds are positive in at least three horizons; and both fixed regimes plus "
            "outlier/concentration diagnostics remain supportive."
        ),
    },
    "claim_boundary": "Association only; no causal, investable-alpha, or historical-0050 claim.",
}


@dataclass(frozen=True)
class FrozenIdentity:
    universe_sha256: str
    signal_sha256: str
    frozen_rules_hash: str
    stage_a_manifest_identity: str


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _rules_hash(config: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "quality_rules": config["quality_rules"],
            "valuation_rules": config["valuation_rules"],
        }
    )


def validate_frozen_inputs(
    universe_path: Path,
    signal_path: Path,
    config_path: Path,
    manifest_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any], FrozenIdentity]:
    universe_hash = sha256_path(universe_path)
    signal_hash = sha256_path(signal_path)
    if universe_hash != EXPECTED_UNIVERSE_SHA256:
        raise RuntimeError(
            f"Frozen universe hash mismatch: expected {EXPECTED_UNIVERSE_SHA256}, got {universe_hash}"
        )
    if signal_hash != EXPECTED_SIGNAL_SHA256:
        raise RuntimeError(
            f"Frozen Stage A signal hash mismatch: expected {EXPECTED_SIGNAL_SHA256}, got {signal_hash}"
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rules_hash = _rules_hash(config)
    if rules_hash != EXPECTED_FROZEN_RULES_HASH:
        raise RuntimeError(
            f"Frozen Model rules hash mismatch: expected {EXPECTED_FROZEN_RULES_HASH}, got {rules_hash}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage_a = manifest.get("stage_a_hardening")
    if not isinstance(stage_a, dict):
        raise RuntimeError("Stage A manifest identity missing: stage_a_hardening")
    stage_a_identity = canonical_hash(stage_a)
    if stage_a_identity != EXPECTED_STAGE_A_MANIFEST_IDENTITY:
        raise RuntimeError(
            "Stage A manifest identity mismatch: "
            f"expected {EXPECTED_STAGE_A_MANIFEST_IDENTITY}, got {stage_a_identity}"
        )
    recorded = stage_a.get("artifact_hashes", {}).get(signal_path.name)
    if recorded != signal_hash:
        raise RuntimeError(
            f"Stage A manifest signal identity mismatch: manifest={recorded}, actual={signal_hash}"
        )
    if stage_a.get("universe_sha256") != universe_hash:
        raise RuntimeError("Stage A manifest universe identity mismatch")
    if stage_a.get("frozen_rules_hash") != rules_hash:
        raise RuntimeError("Stage A manifest Frozen Model rules identity mismatch")

    universe = pd.read_csv(universe_path, dtype=str, encoding="utf-8-sig").fillna("")
    signals = pd.read_csv(signal_path, dtype={"symbol": str}, encoding="utf-8-sig")
    if len(universe) != 50 or universe["symbol"].nunique() != 50:
        raise RuntimeError("Frozen universe must contain exactly 50 unique issuers")
    financial = universe[universe["sector_logic"] == "FINANCIAL"]
    eligible_universe = universe[universe["sector_logic"] != "FINANCIAL"]
    if len(financial) != EXPECTED_FINANCIAL_ISSUERS or len(eligible_universe) != EXPECTED_NON_FINANCIAL_ISSUERS:
        raise RuntimeError("Frozen financial/non-financial cohort counts changed")
    if len(signals) != EXPECTED_SIGNAL_ROWS:
        raise RuntimeError(f"Frozen Stage A signal row count changed: {len(signals)}")
    eligible_symbols = set(eligible_universe["symbol"])
    signal_symbols = set(signals["symbol"].astype(str))
    if not signal_symbols.issubset(eligible_symbols):
        raise RuntimeError(
            f"Financial or out-of-cohort issuer entered Stage B signals: {sorted(signal_symbols - eligible_symbols)}"
        )
    if not signals["predictive_eligible"].fillna(False).astype(bool).all():
        raise RuntimeError("Frozen Stage A signal file contains non-eligible observations")
    required = {
        "symbol",
        "period_end",
        "signal_date",
        "first_trade_date",
        "quality",
        "fundamental_state",
        "state_detail",
        "valuation",
        "availability_method",
        "source_hash",
    }
    missing = required.difference(signals.columns)
    if missing:
        raise RuntimeError(f"Frozen Stage A signals missing columns: {sorted(missing)}")
    identity = FrozenIdentity(universe_hash, signal_hash, rules_hash, stage_a_identity)
    return universe, signals, config, manifest, identity


def _prepare_market(frame: pd.DataFrame, as_of: date) -> pd.DataFrame:
    required = {"date", "adj_close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Adjusted-close market input missing columns: {sorted(missing)}")
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.date
    result["adj_close"] = pd.to_numeric(result["adj_close"], errors="coerce")
    result = result[
        result["date"].notna()
        & result["adj_close"].notna()
        & (result["adj_close"] > 0)
        & (result["date"] <= as_of)
    ].copy()
    if result["date"].duplicated().any():
        raise RuntimeError("Market input contains duplicate trading dates")
    return result.sort_values("date").reset_index(drop=True)


def _max_drawdown(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None
    return float((clean / clean.cummax() - 1.0).min())


def _legacy_label_map(legacy_events: pd.DataFrame | None) -> dict[tuple[str, str], str]:
    if legacy_events is None or legacy_events.empty or "state_validation" not in legacy_events:
        return {}
    selected = legacy_events.dropna(subset=["state_validation"]).copy()
    selected["symbol"] = selected["symbol"].astype(str)
    selected["period_end"] = selected["period_end"].astype(str)
    selected = selected[selected["state_validation"].isin(TIMING_LABELS)]
    duplicated = selected.duplicated(["symbol", "period_end"], keep=False)
    if duplicated.any():
        conflicts = selected.loc[duplicated].groupby(["symbol", "period_end"])["state_validation"].nunique()
        if (conflicts > 1).any():
            raise RuntimeError("Conflicting existing state-validation labels")
    return {
        (str(row.symbol), str(row.period_end)): str(row.state_validation)
        for row in selected.drop_duplicates(["symbol", "period_end"]).itertuples()
    }


def build_predictive_events(
    signals: pd.DataFrame,
    universe: pd.DataFrame,
    markets: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    *,
    as_of: date,
    horizons: Iterable[int] = PRIMARY_HORIZONS,
    legacy_events: pd.DataFrame | None = None,
) -> pd.DataFrame:
    horizons = tuple(int(value) for value in horizons)
    if tuple(horizons) != PRIMARY_HORIZONS:
        raise ValueError(f"Primary horizons are frozen at {PRIMARY_HORIZONS}")
    eligible_universe = universe[universe["sector_logic"] != "FINANCIAL"].copy()
    eligible_symbols = set(eligible_universe["symbol"].astype(str))
    if set(signals["symbol"].astype(str)) - eligible_symbols:
        raise RuntimeError("Stage B received a financial or out-of-cohort signal")

    benchmark_frame = _prepare_market(benchmark, as_of)
    benchmark_index = {value: index for index, value in enumerate(benchmark_frame["date"])}
    benchmark_prices = dict(zip(benchmark_frame["date"], benchmark_frame["adj_close"]))
    universe_columns = ["symbol", "company", "sector_logic", "peer_group", "financial_subtype"]
    merged = signals.copy()
    merged["symbol"] = merged["symbol"].astype(str)
    merged = merged.merge(eligible_universe[universe_columns], on="symbol", how="left", validate="many_to_one")
    if merged["company"].isna().any():
        raise RuntimeError("Stage B signal cannot be resolved to Frozen cohort metadata")
    label_map = _legacy_label_map(legacy_events)
    prepared_markets = {
        symbol: _prepare_market(frame, as_of)
        for symbol, frame in markets.items()
        if symbol in eligible_symbols
    }
    records: list[dict[str, Any]] = []
    for row in merged.to_dict(orient="records"):
        symbol = str(row["symbol"])
        period_end = str(row["period_end"])
        entry_date = pd.to_datetime(row.get("first_trade_date"), errors="coerce")
        record = dict(row)
        record["valuation_frozen"] = record["valuation"]
        record["valuation_bucket"] = (
            "NOT_MEANINGFUL" if str(record["valuation"]) in {"N/M", "NOT_MEANINGFUL"} else str(record["valuation"])
        )
        record["entry_date"] = entry_date.date().isoformat() if pd.notna(entry_date) else None
        record["entry_contract"] = "FROZEN_STAGE_A_FIRST_TRADE_DATE"
        record["return_policy"] = "YAHOO_ADJUSTED_CLOSE_EXACT_COMMON_TWSE_DATES"
        record["survivorship_bias"] = "CURRENT_CONSTITUENTS_ONLY"
        record["state_validation"] = label_map.get((symbol, period_end))
        record["exclusion_reason"] = None
        for horizon in horizons:
            for name in (
                "exit_date",
                "return",
                "benchmark_return",
                "excess_return",
                "max_close_to_close_favorable_return",
                "max_close_to_close_adverse_return",
                "max_drawdown",
            ):
                record[f"{name}_{horizon}d"] = None

        if pd.isna(entry_date):
            record["exclusion_reason"] = "MISSING_FIRST_TRADE_DATE"
            records.append(record)
            continue
        entry = entry_date.date()
        market = prepared_markets.get(symbol)
        if market is None or market.empty:
            record["exclusion_reason"] = "MISSING_ADJUSTED_CLOSE_SERIES"
            records.append(record)
            continue
        stock_prices = dict(zip(market["date"], market["adj_close"]))
        if entry not in benchmark_index:
            record["exclusion_reason"] = "ENTRY_NOT_BENCHMARK_SESSION"
            records.append(record)
            continue
        if entry not in stock_prices:
            record["exclusion_reason"] = "ENTRY_ADJUSTED_CLOSE_MISSING"
            records.append(record)
            continue
        entry_stock = float(stock_prices[entry])
        entry_benchmark = float(benchmark_prices[entry])
        for horizon in horizons:
            exit_position = benchmark_index[entry] + horizon
            if exit_position >= len(benchmark_frame):
                continue
            exit_date = benchmark_frame.iloc[exit_position]["date"]
            record[f"exit_date_{horizon}d"] = exit_date.isoformat()
            if exit_date not in stock_prices:
                continue
            exit_stock = float(stock_prices[exit_date])
            exit_benchmark = float(benchmark_prices[exit_date])
            stock_return = exit_stock / entry_stock - 1.0
            benchmark_return = exit_benchmark / entry_benchmark - 1.0
            window = market[(market["date"] >= entry) & (market["date"] <= exit_date)]["adj_close"]
            record[f"return_{horizon}d"] = stock_return
            record[f"benchmark_return_{horizon}d"] = benchmark_return
            record[f"excess_return_{horizon}d"] = stock_return - benchmark_return
            record[f"max_close_to_close_favorable_return_{horizon}d"] = float(window.max() / entry_stock - 1.0)
            record[f"max_close_to_close_adverse_return_{horizon}d"] = float(window.min() / entry_stock - 1.0)
            record[f"max_drawdown_{horizon}d"] = _max_drawdown(window)
        records.append(record)
    result = pd.DataFrame(records)
    if len(result) != len(signals):
        raise RuntimeError("Stage B changed the Frozen Stage A observation count")
    return result.replace([np.inf, -np.inf], np.nan)


def _cluster_standard_error(values: pd.Series, clusters: pd.Series) -> float | None:
    selected = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "cluster": clusters}).dropna()
    if len(selected) < 2 or selected["cluster"].nunique() < 2:
        return None
    mean = float(selected["value"].mean())
    sums = selected.assign(centered=selected["value"] - mean).groupby("cluster")["centered"].sum()
    groups = len(sums)
    variance = groups / (groups - 1) * float((sums**2).sum()) / len(selected) ** 2
    return math.sqrt(max(variance, 0.0))


def _cluster_median_ci(
    values: pd.Series,
    clusters: pd.Series,
    *,
    seed: int,
    replications: int = BOOTSTRAP_REPLICATIONS,
) -> tuple[float | None, float | None]:
    selected = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "cluster": clusters}).dropna()
    names = selected["cluster"].drop_duplicates().tolist()
    if len(selected) < 2 or len(names) < 2:
        return None, None
    grouped = {name: group["value"].to_numpy() for name, group in selected.groupby("cluster", sort=False)}
    rng = np.random.default_rng(seed)
    estimates = np.empty(replications, dtype=float)
    for index in range(replications):
        sampled = rng.choice(names, size=len(names), replace=True)
        estimates[index] = float(np.median(np.concatenate([grouped[name] for name in sampled])))
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def _stable_seed(label: str) -> int:
    return int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16)


def summary_row(
    frame: pd.DataFrame,
    *,
    dimension: str,
    bucket: str,
    horizon: int,
) -> dict[str, Any]:
    return_name = f"return_{horizon}d"
    excess_name = f"excess_return_{horizon}d"
    valid = pd.to_numeric(frame.get(return_name), errors="coerce").notna() & pd.to_numeric(
        frame.get(excess_name), errors="coerce"
    ).notna()
    selected = frame.loc[valid].copy()
    returns = pd.to_numeric(selected.get(return_name), errors="coerce")
    excess = pd.to_numeric(selected.get(excess_name), errors="coerce")
    issuers = selected.get("symbol", pd.Series(index=selected.index, dtype=object)).astype(str)
    quarters = pd.to_datetime(selected.get("entry_date"), errors="coerce").dt.to_period("Q").astype(str)
    support = (
        len(selected) >= MIN_SUPPORT_OBSERVATIONS
        and issuers.nunique() >= MIN_SUPPORT_ISSUERS
    )
    base: dict[str, Any] = {
        "dimension": dimension,
        "bucket": bucket,
        "horizon": f"{horizon}d",
        "observations": int(len(selected)),
        "unique_issuers": int(issuers.nunique()),
        "support_status": "SUPPORTED" if support else "INSUFFICIENT_SUPPORT",
        "support_min_observations": MIN_SUPPORT_OBSERVATIONS,
        "support_min_issuers": MIN_SUPPORT_ISSUERS,
        "uncertainty_contract": "ISSUER_AND_ENTRY_QUARTER_CLUSTERED",
    }
    if selected.empty:
        return base
    issuer_return_se = _cluster_standard_error(returns, issuers)
    time_return_se = _cluster_standard_error(returns, quarters)
    issuer_excess_se = _cluster_standard_error(excess, issuers)
    time_excess_se = _cluster_standard_error(excess, quarters)
    seed = _stable_seed(f"{dimension}|{bucket}|{horizon}")
    issuer_median_return = _cluster_median_ci(returns, issuers, seed=seed)
    time_median_return = _cluster_median_ci(returns, quarters, seed=seed + 1)
    issuer_median_excess = _cluster_median_ci(excess, issuers, seed=seed + 2)
    time_median_excess = _cluster_median_ci(excess, quarters, seed=seed + 3)
    mean_return = float(returns.mean())
    mean_excess = float(excess.mean())
    base.update(
        {
            "mean_return": mean_return,
            "median_return": float(returns.median()),
            "positive_return_rate": float((returns > 0).mean()),
            "mean_excess_return": mean_excess,
            "median_excess_return": float(excess.median()),
            "outperform_0050_rate": float((excess > 0).mean()),
            "standard_deviation": float(returns.std(ddof=1)) if len(returns) > 1 else None,
            "p25_return": float(returns.quantile(0.25)),
            "p75_return": float(returns.quantile(0.75)),
            "issuer_cluster_mean_return_se": issuer_return_se,
            "issuer_cluster_mean_return_ci95_low": mean_return - 1.96 * issuer_return_se if issuer_return_se is not None else None,
            "issuer_cluster_mean_return_ci95_high": mean_return + 1.96 * issuer_return_se if issuer_return_se is not None else None,
            "time_cluster_mean_return_se": time_return_se,
            "time_cluster_mean_return_ci95_low": mean_return - 1.96 * time_return_se if time_return_se is not None else None,
            "time_cluster_mean_return_ci95_high": mean_return + 1.96 * time_return_se if time_return_se is not None else None,
            "issuer_cluster_mean_excess_se": issuer_excess_se,
            "issuer_cluster_mean_excess_ci95_low": mean_excess - 1.96 * issuer_excess_se if issuer_excess_se is not None else None,
            "issuer_cluster_mean_excess_ci95_high": mean_excess + 1.96 * issuer_excess_se if issuer_excess_se is not None else None,
            "time_cluster_mean_excess_se": time_excess_se,
            "time_cluster_mean_excess_ci95_low": mean_excess - 1.96 * time_excess_se if time_excess_se is not None else None,
            "time_cluster_mean_excess_ci95_high": mean_excess + 1.96 * time_excess_se if time_excess_se is not None else None,
            "issuer_cluster_median_return_ci95_low": issuer_median_return[0],
            "issuer_cluster_median_return_ci95_high": issuer_median_return[1],
            "time_cluster_median_return_ci95_low": time_median_return[0],
            "time_cluster_median_return_ci95_high": time_median_return[1],
            "issuer_cluster_median_excess_ci95_low": issuer_median_excess[0],
            "issuer_cluster_median_excess_ci95_high": issuer_median_excess[1],
            "time_cluster_median_excess_ci95_low": time_median_excess[0],
            "time_cluster_median_excess_ci95_high": time_median_excess[1],
        }
    )
    return base


def _add_lift(rows: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    baselines = {
        f"{horizon}d": summary_row(events, dimension="all", bucket="ALL", horizon=horizon)
        for horizon in PRIMARY_HORIZONS
    }
    result = rows.copy()
    for metric, output in (
        ("median_return", "median_return_lift_vs_all"),
        ("median_excess_return", "median_excess_return_lift_vs_all"),
        ("outperform_0050_rate", "outperform_rate_lift_vs_all"),
    ):
        result[output] = result.apply(
            lambda row: (
                _finite(row.get(metric)) - _finite(baselines[str(row["horizon"])].get(metric))
                if _finite(row.get(metric)) is not None
                and _finite(baselines[str(row["horizon"])].get(metric)) is not None
                else None
            ),
            axis=1,
        )
    return result


def summarize_dimension(
    events: pd.DataFrame,
    column: str,
    buckets: Iterable[str],
    dimension: str,
) -> pd.DataFrame:
    rows = []
    for bucket in buckets:
        selected = events[events[column].astype(str) == bucket]
        for horizon in PRIMARY_HORIZONS:
            rows.append(summary_row(selected, dimension=dimension, bucket=bucket, horizon=horizon))
    return _add_lift(pd.DataFrame(rows), events)


def summarize_combinations(events: pd.DataFrame) -> pd.DataFrame:
    specifications = (
        ("QUALITY_X_STATE", ("quality", "fundamental_state"), (QUALITY_BUCKETS[:3], CANONICAL_STATES)),
        ("STATE_X_VALUATION", ("fundamental_state", "valuation_bucket"), (CANONICAL_STATES, VALUATION_BUCKETS[:3])),
        ("QUALITY_X_VALUATION", ("quality", "valuation_bucket"), (QUALITY_BUCKETS[:3], VALUATION_BUCKETS[:3])),
        (
            "QUALITY_X_STATE_X_VALUATION",
            ("quality", "fundamental_state", "valuation_bucket"),
            (QUALITY_BUCKETS[:3], CANONICAL_STATES, VALUATION_BUCKETS[:3]),
        ),
    )
    rows: list[dict[str, Any]] = []
    from itertools import product

    for dimension, columns, levels in specifications:
        for values in product(*levels):
            mask = pd.Series(True, index=events.index)
            for column, value in zip(columns, values):
                mask &= events[column].astype(str) == value
            bucket = " × ".join(values)
            for horizon in PRIMARY_HORIZONS:
                row = summary_row(events[mask], dimension=dimension, bucket=bucket, horizon=horizon)
                for column, value in zip(columns, values):
                    row[column] = value
                rows.append(row)
    return _add_lift(pd.DataFrame(rows), events)


def summarize_timing_labels(events: pd.DataFrame) -> pd.DataFrame:
    return summarize_dimension(events, "state_validation", TIMING_LABELS, "STATE_VALIDATION_LABEL")


def summarize_regimes(events: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(events["entry_date"], errors="coerce")
    regimes = {
        "PRE_2023": dates.dt.year < 2023,
        "2023_ONWARD": dates.dt.year >= 2023,
    }
    rows: list[pd.DataFrame] = []
    for regime, mask in regimes.items():
        selected = events[mask.fillna(False)]
        state = summarize_dimension(selected, "fundamental_state", CANONICAL_STATES, "FUNDAMENTAL_STATE")
        state.insert(0, "regime", regime)
        all_rows = pd.DataFrame(
            [summary_row(selected, dimension="ALL", bucket="ALL", horizon=h) for h in PRIMARY_HORIZONS]
        )
        all_rows = _add_lift(all_rows, selected)
        all_rows.insert(0, "regime", regime)
        rows.extend([all_rows, state])
    return pd.concat(rows, ignore_index=True)


def summarize_outliers(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in PRIMARY_HORIZONS:
        return_column = f"return_{horizon}d"
        valid = events[pd.to_numeric(events[return_column], errors="coerce").notna()].copy()
        ranked = valid.sort_values(return_column, ascending=False)
        variants = {
            "FULL_SAMPLE": valid,
            "EX_TSMC": valid[valid["symbol"].astype(str) != "2330"],
            "TOP_1_RETURN_REMOVED": ranked.iloc[1:],
            "TOP_5_RETURNS_REMOVED": ranked.iloc[5:],
        }
        top_five = ranked.head(5)
        positive_sum = pd.to_numeric(valid.loc[valid[return_column] > 0, return_column], errors="coerce").sum()
        contribution = (
            float(pd.to_numeric(top_five[return_column], errors="coerce").sum() / positive_sum)
            if positive_sum > 0
            else None
        )
        for scope, selected in variants.items():
            for bucket in ("ALL", *CANONICAL_STATES):
                group = selected if bucket == "ALL" else selected[selected["fundamental_state"] == bucket]
                row = summary_row(group, dimension="FUNDAMENTAL_STATE", bucket=bucket, horizon=horizon)
                row.update(
                    {
                        "analysis_type": "RETURN_SENSITIVITY",
                        "scope": scope,
                        "top_five_positive_return_contribution": contribution,
                    }
                )
                rows.append(row)

    valid_252 = events[pd.to_numeric(events["return_252d"], errors="coerce").notna()].copy()
    for concentration_type, column in (("ISSUER_CONCENTRATION", "symbol"), ("SECTOR_CONCENTRATION", "peer_group")):
        shares = valid_252[column].astype(str).value_counts(normalize=True)
        rows.append(
            {
                "analysis_type": concentration_type,
                "scope": "FULL_SAMPLE_252D",
                "dimension": column,
                "bucket": "ALL",
                "horizon": "252d",
                "observations": int(len(valid_252)),
                "unique_issuers": int(valid_252["symbol"].nunique()),
                "concentration_group_count": int(len(shares)),
                "largest_group": str(shares.index[0]) if len(shares) else None,
                "largest_group_observation_share": float(shares.iloc[0]) if len(shares) else None,
                "herfindahl_index": float((shares**2).sum()) if len(shares) else None,
                "support_status": "DIAGNOSTIC",
            }
        )
    result = pd.DataFrame(rows)
    sensitivity = result["analysis_type"] == "RETURN_SENSITIVITY"
    sensitivity_rows = _add_lift(result.loc[sensitivity].copy(), events)
    return pd.concat([sensitivity_rows, result.loc[~sensitivity]], ignore_index=True, sort=False)


def overlap_diagnostics(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in PRIMARY_HORIZONS:
        selected = events[["symbol", "entry_date", f"exit_date_{horizon}d", f"return_{horizon}d"]].copy()
        selected["entry"] = pd.to_datetime(selected["entry_date"], errors="coerce")
        selected["exit"] = pd.to_datetime(selected[f"exit_date_{horizon}d"], errors="coerce")
        selected = selected[
            selected["entry"].notna()
            & selected["exit"].notna()
            & pd.to_numeric(selected[f"return_{horizon}d"], errors="coerce").notna()
        ].sort_values("entry").reset_index(drop=True)
        involved: set[int] = set()
        overlap_pairs = 0
        same_issuer_pairs = 0
        cross_issuer_pairs = 0
        for left in range(len(selected)):
            left_exit = selected.at[left, "exit"]
            for right in range(left + 1, len(selected)):
                if selected.at[right, "entry"] > left_exit:
                    break
                overlap_pairs += 1
                involved.update((left, right))
                if str(selected.at[left, "symbol"]) == str(selected.at[right, "symbol"]):
                    same_issuer_pairs += 1
                else:
                    cross_issuer_pairs += 1
        rows.append(
            {
                "horizon": f"{horizon}d",
                "eligible_observations": int(len(selected)),
                "overlapping_observations_count": int(len(involved)),
                "overlapping_observations_ratio": float(len(involved) / len(selected)) if len(selected) else None,
                "overlap_pair_count": overlap_pairs,
                "same_issuer_overlap_pair_count": same_issuer_pairs,
                "same_calendar_period_cross_issuer_overlap_pair_count": cross_issuer_pairs,
                "definition": "Closed entry-to-exit intervals; pair overlaps when the later entry is on/before the earlier exit.",
            }
        )
    return pd.DataFrame(rows)


def _bucket_horizon_signal(summary: pd.DataFrame, bucket: str) -> dict[str, Any]:
    selected = summary[(summary["bucket"] == bucket) & (summary["support_status"] == "SUPPORTED")]
    directional = selected[
        (pd.to_numeric(selected["median_excess_return_lift_vs_all"], errors="coerce") > 0)
        & (pd.to_numeric(selected["outperform_rate_lift_vs_all"], errors="coerce") > 0)
    ]
    clustered = selected[
        (pd.to_numeric(selected["issuer_cluster_mean_excess_ci95_low"], errors="coerce") > 0)
        | (pd.to_numeric(selected["time_cluster_mean_excess_ci95_low"], errors="coerce") > 0)
    ]
    return {
        "supported_horizons": int(len(selected)),
        "positive_median_excess_and_outperform_lift_horizons": int(len(directional)),
        "positive_clustered_lower_bound_horizons": int(len(clustered)),
        "meets_axis_directional_rule": len(directional) >= 3,
        "meets_axis_cluster_rule": len(clustered) >= 1,
    }


def _economic_ordering(summary: pd.DataFrame, buckets: tuple[str, ...]) -> dict[str, Any]:
    ordering = {}
    for horizon in PRIMARY_HORIZONS:
        selected = summary[summary["horizon"] == f"{horizon}d"].set_index("bucket")
        values = [_finite(selected.at[bucket, "median_excess_return"]) if bucket in selected.index else None for bucket in buckets]
        supported = [
            bool(bucket in selected.index and selected.at[bucket, "support_status"] == "SUPPORTED")
            for bucket in buckets
        ]
        ordering[f"{horizon}d"] = bool(
            all(value is not None for value in values)
            and all(supported)
            and all(left > right for left, right in zip(values, values[1:]))  # type: ignore[operator]
        )
    return {"by_horizon": ordering, "horizons_with_ordering": int(sum(ordering.values()))}


def _supported_extremes(summary: pd.DataFrame, horizon: str = "252d") -> dict[str, Any]:
    selected = summary[
        (summary["horizon"] == horizon) & (summary["support_status"] == "SUPPORTED")
    ].copy()
    selected["rank_value"] = pd.to_numeric(selected["median_excess_return"], errors="coerce")
    selected = selected.dropna(subset=["rank_value"]).sort_values("rank_value", ascending=False)
    if selected.empty:
        return {"horizon": horizon, "strongest": None, "weakest": None}

    def row_payload(row: pd.Series) -> dict[str, Any]:
        return {
            "bucket": str(row["bucket"]),
            "observations": int(row["observations"]),
            "unique_issuers": int(row["unique_issuers"]),
            "median_return": _finite(row.get("median_return")),
            "median_excess_return": _finite(row.get("median_excess_return")),
            "outperform_0050_rate": _finite(row.get("outperform_0050_rate")),
        }

    return {
        "selection_basis": f"highest/lowest supported median excess return at fixed {horizon}",
        "horizon": horizon,
        "strongest": row_payload(selected.iloc[0]),
        "weakest": row_payload(selected.iloc[-1]),
    }


def _best_state_horizon(state: pd.DataFrame) -> dict[str, Any] | None:
    rows = []
    for horizon in PRIMARY_HORIZONS:
        selected = state[state["horizon"] == f"{horizon}d"].set_index("bucket")
        if not set(CANONICAL_STATES).issubset(selected.index):
            continue
        median_spread = _finite(selected.at["IMPROVING", "median_excess_return"])
        median_low = _finite(selected.at["DETERIORATING", "median_excess_return"])
        rate_high = _finite(selected.at["IMPROVING", "outperform_0050_rate"])
        rate_low = _finite(selected.at["DETERIORATING", "outperform_0050_rate"])
        if None in (median_spread, median_low, rate_high, rate_low):
            continue
        excess_spread = median_spread - median_low  # type: ignore[operator]
        outperform_spread = rate_high - rate_low  # type: ignore[operator]
        rows.append(
            {
                "horizon": f"{horizon}d",
                "selection_basis": "largest sum of IMPROVING-minus-DETERIORATING median-excess and outperform-rate spreads",
                "median_excess_spread": excess_spread,
                "outperform_rate_spread": outperform_spread,
                "fixed_comparison_index": excess_spread + outperform_spread,
            }
        )
    return max(rows, key=lambda row: row["fixed_comparison_index"]) if rows else None


def _strongest_supported(combinations: pd.DataFrame, dimension_kind: str) -> dict[str, Any] | None:
    selected = combinations[
        (combinations["dimension"] == dimension_kind)
        & (combinations["horizon"] == "252d")
        & (combinations["support_status"] == "SUPPORTED")
    ].copy()
    selected["rank_value"] = pd.to_numeric(selected["median_excess_return_lift_vs_all"], errors="coerce")
    selected = selected.dropna(subset=["rank_value"]).sort_values(
        ["rank_value", "unique_issuers", "observations"], ascending=[False, False, False]
    )
    if selected.empty:
        return None
    row = selected.iloc[0]
    return {
        "selection_basis": "pre-specified 252d median excess-return lift among supported cells",
        "bucket": str(row["bucket"]),
        "observations": int(row["observations"]),
        "unique_issuers": int(row["unique_issuers"]),
        "median_return": _finite(row.get("median_return")),
        "median_excess_return": _finite(row.get("median_excess_return")),
        "outperform_0050_rate": _finite(row.get("outperform_0050_rate")),
        "median_excess_return_lift_vs_all": _finite(row.get("median_excess_return_lift_vs_all")),
    }


def build_evidence(
    events: pd.DataFrame,
    state: pd.DataFrame,
    state_detail: pd.DataFrame,
    quality: pd.DataFrame,
    valuation: pd.DataFrame,
    combinations: pd.DataFrame,
    timing: pd.DataFrame,
    regimes: pd.DataFrame,
    outliers: pd.DataFrame,
    overlap: pd.DataFrame,
    identity: FrozenIdentity,
) -> dict[str, Any]:
    axis_checks = {
        "fundamental_state_improving": _bucket_horizon_signal(state, "IMPROVING"),
        "state_detail_turning_up": _bucket_horizon_signal(state_detail, "TURNING_UP"),
        "quality_good": _bucket_horizon_signal(quality, "GOOD"),
        "valuation_low": _bucket_horizon_signal(valuation, "LOW"),
    }
    ordering = _economic_ordering(state, CANONICAL_STATES)
    quality_ordering = _economic_ordering(quality, ("GOOD", "ACCEPTABLE", "WEAK"))
    valuation_ordering = _economic_ordering(valuation, ("LOW", "NORMAL", "HIGH"))
    lifecycle_ordering = _economic_ordering(
        state_detail,
        ("TURNING_UP", "CONFIRMED_GROWTH", "MATURE_GROWTH", "DECELERATING", "DETERIORATING"),
    )
    two_axis_candidates = combinations[combinations["dimension"] != "QUALITY_X_STATE_X_VALUATION"]
    strongest_two = None
    for dimension in ("QUALITY_X_STATE", "STATE_X_VALUATION", "QUALITY_X_VALUATION"):
        candidate = _strongest_supported(two_axis_candidates, dimension)
        if candidate and (
            strongest_two is None
            or (candidate.get("median_excess_return_lift_vs_all") or -math.inf)
            > (strongest_two.get("median_excess_return_lift_vs_all") or -math.inf)
        ):
            strongest_two = {"dimension": dimension, **candidate}
    strongest_three = _strongest_supported(combinations, "QUALITY_X_STATE_X_VALUATION")

    weak_axis = any(
        item["positive_median_excess_and_outperform_lift_horizons"] >= 2
        for item in axis_checks.values()
    )
    ordering_by_axis = {
        "fundamental_state_improving": ordering,
        "quality_good": quality_ordering,
        "valuation_low": valuation_ordering,
    }
    moderate_axes = [
        name
        for name, item in axis_checks.items()
        if name in ordering_by_axis
        and item["meets_axis_directional_rule"]
        and item["meets_axis_cluster_rule"]
        and ordering_by_axis[name]["horizons_with_ordering"] >= 3
    ]

    def sensitivity_positive(scope: str, bucket: str = "IMPROVING") -> bool:
        selected = outliers[
            (outliers.get("analysis_type") == "RETURN_SENSITIVITY")
            & (outliers.get("scope") == scope)
            & (outliers.get("bucket") == bucket)
            & (outliers.get("support_status") == "SUPPORTED")
        ]
        positive = (
            (pd.to_numeric(selected.get("median_excess_return_lift_vs_all"), errors="coerce") > 0)
            & (pd.to_numeric(selected.get("outperform_rate_lift_vs_all"), errors="coerce") > 0)
        )
        return int(positive.sum()) >= 3

    regime_state = regimes[
        (regimes["dimension"] == "FUNDAMENTAL_STATE")
        & (regimes["bucket"] == "IMPROVING")
        & (regimes["support_status"] == "SUPPORTED")
    ]
    regime_support = {}
    for regime in ("PRE_2023", "2023_ONWARD"):
        selected = regime_state[regime_state["regime"] == regime]
        regime_support[regime] = int(
            (
                (pd.to_numeric(selected["median_excess_return_lift_vs_all"], errors="coerce") > 0)
                & (pd.to_numeric(selected["outperform_rate_lift_vs_all"], errors="coerce") > 0)
            ).sum()
        )
    concentration_rows = outliers[
        outliers.get("analysis_type").isin(["ISSUER_CONCENTRATION", "SECTOR_CONCENTRATION"])
    ]
    issuer_concentration = concentration_rows[
        concentration_rows["analysis_type"] == "ISSUER_CONCENTRATION"
    ]
    sector_concentration = concentration_rows[
        concentration_rows["analysis_type"] == "SECTOR_CONCENTRATION"
    ]
    concentration_gate = EVIDENCE_RUBRIC["concentration_gate"]

    def concentration_pass(frame: pd.DataFrame, hhi_key: str, share_key: str) -> bool:
        if frame.empty:
            return False
        row = frame.iloc[0]
        hhi = _finite(row.get("herfindahl_index"))
        share = _finite(row.get("largest_group_observation_share"))
        return bool(
            hhi is not None
            and share is not None
            and hhi <= float(concentration_gate[hhi_key])
            and share <= float(concentration_gate[share_key])
        )

    issuer_concentration_pass = concentration_pass(
        issuer_concentration, "issuer_hhi_max", "largest_issuer_observation_share_max"
    )
    sector_concentration_pass = concentration_pass(
        sector_concentration, "sector_hhi_max", "largest_sector_observation_share_max"
    )
    robust_state = (
        sensitivity_positive("EX_TSMC")
        and sensitivity_positive("TOP_5_RETURNS_REMOVED")
        and all(value >= 2 for value in regime_support.values())
        and issuer_concentration_pass
        and sector_concentration_pass
    )
    strong = (
        "fundamental_state_improving" in moderate_axes
        and len(moderate_axes) >= 2
        and ordering["horizons_with_ordering"] >= 3
        and axis_checks["fundamental_state_improving"]["positive_clustered_lower_bound_horizons"] >= 3
        and robust_state
    )
    moderate = bool(moderate_axes) and robust_state
    combination_weak = bool(
        strongest_two
        and (strongest_two.get("median_excess_return_lift_vs_all") or 0) > 0
    )
    grade = "STRONG" if strong else "MODERATE" if moderate else "WEAK" if (weak_axis or combination_weak) else "NONE"
    label = "EXPLORATORY_PREDICTIVE_ASSOCIATION" if grade != "NONE" else "NO_RELIABLE_PREDICTIVE_ASSOCIATION"

    def horizon_counts() -> dict[str, int]:
        return {
            f"{horizon}d": int(pd.to_numeric(events[f"return_{horizon}d"], errors="coerce").notna().sum())
            for horizon in PRIMARY_HORIZONS
        }

    too_late_12m = timing[(timing["bucket"] == "TOO_LATE") & (timing["horizon"] == "252d")]
    too_late_answer = None if too_late_12m.empty else {
        "observations": int(too_late_12m.iloc[0]["observations"]),
        "median_return": _finite(too_late_12m.iloc[0].get("median_return")),
        "median_excess_return": _finite(too_late_12m.iloc[0].get("median_excess_return")),
        "outperform_0050_rate": _finite(too_late_12m.iloc[0].get("outperform_0050_rate")),
        "interpretation": "Timing label is not automatically a failure; remaining return is measured after the Frozen entry date.",
    }

    return {
        "stage": "Fundamental Model v0.1 — Stage B: Predictive Validation",
        "stage_b_status": "PASS",
        "starting_head": STAGE_B_STARTING_HEAD,
        "frozen_identity": identity.__dict__,
        "mops_network_requests": 0,
        "survivorship_bias": "CURRENT_CONSTITUENTS_ONLY",
        "evidence_label": label,
        "predictive_evidence_grade": grade,
        "rubric": EVIDENCE_RUBRIC,
        "eligible_observations_by_horizon": horizon_counts(),
        "axis_checks": axis_checks,
        "state_economic_ordering": ordering,
        "quality_economic_ordering": quality_ordering,
        "valuation_economic_ordering": valuation_ordering,
        "state_detail_lifecycle_ordering": lifecycle_ordering,
        "state_detail_strongest_and_weakest_supported": _supported_extremes(state_detail),
        "strongest_supported_two_axis_combination": strongest_two,
        "strongest_supported_three_axis_combination": (
            {"dimension": "QUALITY_X_STATE_X_VALUATION", **strongest_three}
            if strongest_three
            else None
        ),
        "too_late_remaining_return_12m": too_late_answer,
        "regime_improving_positive_horizons": regime_support,
        "robustness": {
            "ex_tsmc_supportive": sensitivity_positive("EX_TSMC"),
            "top_five_removed_supportive": sensitivity_positive("TOP_5_RETURNS_REMOVED"),
            "issuer_concentration_gate_pass": issuer_concentration_pass,
            "sector_concentration_gate_pass": sector_concentration_pass,
            "state_robustness_gate": robust_state,
        },
        "overlap_diagnostics": overlap.to_dict(orient="records"),
        "research_questions": {
            "Q1_state_predictive_information": axis_checks["fundamental_state_improving"],
            "Q2_improving_vs_stable_deteriorating": ordering,
            "Q3_state_detail_vs_canonical": {
                "canonical_state_ordering": ordering,
                "state_detail_lifecycle_ordering": lifecycle_ordering,
                "conclusion": (
                    "state_detail does not establish a complete ordered lifecycle when any required "
                    "bucket is unsupported or the strict lifecycle order fails; it can still identify "
                    "descriptively stronger and weaker supported buckets."
                ),
            },
            "Q4_turning_up_remaining_return": axis_checks["state_detail_turning_up"],
            "Q5_quality_independent_information": {
                "marginal_axis_result": axis_checks["quality_good"],
                "economic_ordering": quality_ordering,
                "independence_boundary": "Marginal categorical association is measured; causal or multivariable independence is not established.",
            },
            "Q6_valuation_independent_information": {
                "marginal_axis_result": axis_checks["valuation_low"],
                "economic_ordering": valuation_ordering,
                "independence_boundary": "Marginal categorical association is measured; causal or multivariable independence is not established.",
            },
            "Q7_quality_x_state": _strongest_supported(combinations, "QUALITY_X_STATE"),
            "Q8_state_x_valuation": _strongest_supported(combinations, "STATE_X_VALUATION"),
            "Q9_three_axis_intersection": strongest_three,
            "Q10_best_horizon": _best_state_horizon(state),
            "Q11_too_late_remaining_return": too_late_answer,
            "Q12_regime_and_concentration": {
                "regime": regime_support,
                "ex_tsmc": sensitivity_positive("EX_TSMC"),
                "top_five_removed": sensitivity_positive("TOP_5_RETURNS_REMOVED"),
                "issuer_concentration_gate_pass": issuer_concentration_pass,
                "sector_concentration_gate_pass": sector_concentration_pass,
            },
            "Q13_overall_evidence": grade,
        },
        "limitations": [
            "CURRENT_CONSTITUENTS_ONLY; results are not survivorship-bias-free historical 0050 performance.",
            "Repeated issuer observations and overlapping windows are not IID.",
            "Issuer- and entry-quarter-clustered uncertainty does not eliminate all common-regime dependence.",
            "Adjusted-close paths are close-to-close; excursions are not intraday MFE/MAE.",
            "Categorical intersections are exploratory and are not scores or tuned trading rules.",
            "Financial issuers are excluded from all predictive evidence.",
        ],
    }


def assert_finite_artifact(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON value")
    if isinstance(value, dict):
        for item in value.values():
            assert_finite_artifact(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_finite_artifact(item)
