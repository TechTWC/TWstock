from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .models import FundamentalState, SectorLogic


EVALUATED_STATES = (
    FundamentalState.IMPROVING.value,
    FundamentalState.STABLE.value,
    FundamentalState.DETERIORATING.value,
)
ALL_STATES = EVALUATED_STATES + (FundamentalState.UNKNOWN.value,)


def _finite(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalized_direction(current: object, future: object, threshold: float) -> int | None:
    left = _finite(current)
    right = _finite(future)
    if left is None or right is None:
        return None
    scale = max(abs(left), abs(right), 1e-12)
    delta = (right - left) / scale
    if delta > threshold:
        return 1
    if delta < -threshold:
        return -1
    return 0


def _absolute_direction(current: object, future: object, threshold: float) -> int | None:
    left = _finite(current)
    right = _finite(future)
    if left is None or right is None:
        return None
    delta = right - left
    if delta > threshold:
        return 1
    if delta < -threshold:
        return -1
    return 0


def _family_vote(values: Iterable[int | None]) -> int | None:
    selected = [value for value in values if value is not None]
    if not selected:
        return None
    total = sum(selected)
    if total > 0:
        return 1
    if total < 0:
        return -1
    return 0


def _directions(current: pd.Series, future: pd.Series, rules: dict[str, Any]) -> dict[str, int | None]:
    level = float(rules.get("level_change_threshold", 0.02))
    ratio = float(rules.get("ratio_change_threshold", 0.01))
    balance = float(rules.get("balance_sheet_change_threshold", 0.05))
    return {
        "revenue": _normalized_direction(current.get("ttm_revenue"), future.get("ttm_revenue"), level),
        "earnings": _family_vote(
            (
                _normalized_direction(current.get("ttm_eps"), future.get("ttm_eps"), level),
                _normalized_direction(current.get("ttm_net_income"), future.get("ttm_net_income"), level),
            )
        ),
        "operating_margin": _absolute_direction(
            current.get("operating_margin"), future.get("operating_margin"), ratio
        ),
        "capital_efficiency": _family_vote(
            (
                _absolute_direction(current.get("roe"), future.get("roe"), ratio),
                _absolute_direction(current.get("roic"), future.get("roic"), ratio),
            )
        ),
        "cash_flow": _family_vote(
            (
                _normalized_direction(current.get("ttm_cfo"), future.get("ttm_cfo"), level),
                _normalized_direction(current.get("ttm_fcf"), future.get("ttm_fcf"), level),
            )
        ),
        "balance_sheet": _family_vote(
            (
                # Less net debt and more liquidity are improvements.
                None
                if _absolute_direction(
                    current.get("net_debt_equity"), future.get("net_debt_equity"), balance
                )
                is None
                else -_absolute_direction(
                    current.get("net_debt_equity"), future.get("net_debt_equity"), balance
                ),
                _absolute_direction(current.get("current_ratio"), future.get("current_ratio"), balance),
                _normalized_direction(current.get("equity"), future.get("equity"), level),
            )
        ),
    }


def _label(directions: dict[str, int | None], rules: dict[str, Any]) -> str:
    selected = [value for value in directions.values() if value is not None]
    minimum = int(rules.get("minimum_families", 4))
    directional_minimum = int(rules.get("directional_family_minimum", 3))
    margin = int(rules.get("directional_vote_margin", 2))
    if len(selected) < minimum:
        return FundamentalState.UNKNOWN.value
    improving = sum(value > 0 for value in selected)
    deteriorating = sum(value < 0 for value in selected)
    if improving >= directional_minimum and improving - deteriorating >= margin:
        return FundamentalState.IMPROVING.value
    if deteriorating >= directional_minimum and deteriorating - improving >= margin:
        return FundamentalState.DETERIORATING.value
    return FundamentalState.STABLE.value


def realized_fundamental_state(
    quarterly: pd.DataFrame,
    row_index: int,
    sector_logic: SectorLogic,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Ex-post evaluation label; this function is never called by signal generation."""

    if sector_logic == SectorLogic.FINANCIAL:
        return {
            "realized_state": FundamentalState.UNKNOWN.value,
            "realized_reason": "FINANCIAL_STATE_UNSUPPORTED",
            "realized_family_count": 0,
            "realized_improving_families": 0,
            "realized_deteriorating_families": 0,
            "lead_lag_quarters": None,
            "transition_confirmed": None,
        }
    horizons = int(rules.get("evaluation_quarters", 4))
    future = quarterly.iloc[row_index + 1 : row_index + horizons + 1]
    if len(future) < horizons:
        return {
            "realized_state": FundamentalState.UNKNOWN.value,
            "realized_reason": "REALIZED_FUTURE_WINDOW_INCOMPLETE",
            "realized_family_count": 0,
            "realized_improving_families": 0,
            "realized_deteriorating_families": 0,
            "lead_lag_quarters": None,
            "transition_confirmed": None,
        }
    current = quarterly.iloc[row_index]
    endpoint = future.iloc[-1]
    directions = _directions(current, endpoint, rules)
    realized = _label(directions, rules)
    selected = [value for value in directions.values() if value is not None]

    lead_lag: int | None = None
    target_sign = {
        FundamentalState.IMPROVING.value: 1,
        FundamentalState.DETERIORATING.value: -1,
    }.get(realized)
    half_labels: list[str] = []
    for quarter, (_, observation) in enumerate(future.iterrows(), start=1):
        point_label = _label(_directions(current, observation, rules), rules)
        half_labels.append(point_label)
        if target_sign is not None and lead_lag is None:
            expected = (
                FundamentalState.IMPROVING.value
                if target_sign > 0
                else FundamentalState.DETERIORATING.value
            )
            if point_label == expected:
                lead_lag = quarter
    transition_confirmed: bool | None
    if realized in (FundamentalState.IMPROVING.value, FundamentalState.DETERIORATING.value):
        transition_confirmed = sum(label == realized for label in half_labels[-2:]) == 2
    elif realized == FundamentalState.STABLE.value:
        transition_confirmed = sum(label == realized for label in half_labels[-2:]) >= 1
        lead_lag = 0
    else:
        transition_confirmed = None
    return {
        "realized_state": realized,
        "realized_reason": "EX_POST_FOUR_QUARTER_MULTI_FAMILY_LABEL",
        "realized_family_count": len(selected),
        "realized_improving_families": sum(value > 0 for value in selected),
        "realized_deteriorating_families": sum(value < 0 for value in selected),
        "lead_lag_quarters": lead_lag,
        "transition_confirmed": transition_confirmed,
        **{f"realized_{name}_direction": value for name, value in directions.items()},
    }


def confusion_matrix(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for predicted in ALL_STATES:
        for realized in ALL_STATES:
            count = int(
                (
                    (events.get("fundamental_state") == predicted)
                    & (events.get("realized_fundamental_state") == realized)
                ).sum()
            )
            rows.append({"predicted_state": predicted, "realized_state": realized, "count": count})
    return pd.DataFrame(rows)


def state_accuracy_metrics(events: pd.DataFrame) -> pd.DataFrame:
    # UNKNOWN predictions remain false negatives for an observed canonical
    # state; only UNKNOWN realized labels are outside the evaluation set.
    evaluable = events[
        events["realized_fundamental_state"].isin(EVALUATED_STATES)
    ].copy()
    rows: list[dict[str, Any]] = []
    for state in EVALUATED_STATES:
        predicted = evaluable["fundamental_state"] == state
        actual = evaluable["realized_fundamental_state"] == state
        tp = int((predicted & actual).sum())
        fp = int((predicted & ~actual).sum())
        fn = int((~predicted & actual).sum())
        tn = int((~predicted & ~actual).sum())
        matches = evaluable[predicted & actual]
        lead_lag = pd.to_numeric(matches.get("lead_lag_quarters"), errors="coerce").dropna()
        transition = matches.get("transition_confirmed", pd.Series(dtype=bool)).dropna()
        persistence = matches.get("realized_persistent", pd.Series(dtype=bool)).dropna()
        rows.append(
            {
                "state": state,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "false_positive_rate": fp / (fp + tn) if fp + tn else None,
                "false_negative_rate": fn / (tp + fn) if tp + fn else None,
                "support": int(actual.sum()),
                "predicted_count": int(predicted.sum()),
                "median_lead_lag_quarters": float(lead_lag.median()) if not lead_lag.empty else None,
                "mean_lead_lag_quarters": float(lead_lag.mean()) if not lead_lag.empty else None,
                "transition_confirmation_rate": float(transition.astype(bool).mean()) if not transition.empty else None,
                "persistence_rate": float(persistence.astype(bool).mean()) if not persistence.empty else None,
            }
        )
    return pd.DataFrame(rows)


def attach_realized_persistence(events: pd.DataFrame) -> pd.DataFrame:
    """Confirm that the next event's ex-post label agrees for the same issuer."""

    output = events.sort_values(["symbol", "signal_date"]).copy()
    output["next_realized_fundamental_state"] = output.groupby("symbol")[
        "realized_fundamental_state"
    ].shift(-1)
    output["realized_persistent"] = np.where(
        output["realized_fundamental_state"].isin(EVALUATED_STATES)
        & output["next_realized_fundamental_state"].isin(EVALUATED_STATES),
        output["realized_fundamental_state"] == output["next_realized_fundamental_state"],
        None,
    )
    return output.sort_index()
