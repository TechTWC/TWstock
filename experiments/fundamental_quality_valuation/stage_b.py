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
  