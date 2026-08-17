from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from statistics import median
from typing import Mapping, Sequence

from experiments.moving_average_state import MAStateResult, TrendState
from twstock_data.models import MarketBar

from .models import DoubleSlopeResult


@dataclass(frozen=True)
class ComparableUpEvent:
    method: str
    event_id: str
    symbol: str
    trade_date: date
    close: float


@dataclass(frozen=True)
class EventOutcome:
    method: str
    event_id: str
    symbol: str
    trade_date: date
    close: float
    evaluation_status: str
    forward_return: float | None
    maximum_gain: float | None
    maximum_drawdown: float | None
    no_follow_through: bool | None
    negative_at_horizon: bool | None
    five_pct_path_result: str


@dataclass(frozen=True)
class DetectionPair:
    symbol: str
    double_slope_event_id: str
    double_slope_date: date
    ma_event_id: str
    ma_date: date
    double_slope_lead_bars: int


@dataclass(frozen=True)
class MethodSummary:
    method: str
    total_up_events: int
    evaluable_events: int
    pending_events: int
    no_follow_through_events: int
    negative_at_20d_events: int
    downside_first_events: int
    no_follow_through_rate: float | None


@dataclass(frozen=True)
class ComparisonResult:
    events: tuple[ComparableUpEvent, ...]
    outcomes: tuple[EventOutcome, ...]
    pairs: tuple[DetectionPair, ...]
    summaries: tuple[MethodSummary, ...]
    median_double_slope_lead_bars: float | None
    forward_window_bars: int = 20
    follow_through_threshold_pct: float = 0.05
    pair_window_bars: int = 20


def compare_with_ma_baseline(
    double_slope_results: Sequence[DoubleSlopeResult],
    ma_results: Sequence[MAStateResult],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    *,
    forward_window_bars: int = 20,
    follow_through_threshold_pct: float = 0.05,
    pair_window_bars: int = 20,
) -> ComparisonResult:
    if forward_window_bars < 1 or pair_window_bars < 0:
        raise ValueError("comparison windows must be valid")
    if not 0 < follow_through_threshold_pct < 1:
        raise ValueError("follow_through_threshold_pct must be in (0, 1)")
    ds_by_symbol = _unique_by_symbol(double_slope_results)
    ma_by_symbol = _unique_by_symbol(ma_results)
    if set(ds_by_symbol) != set(ma_by_symbol) or set(ds_by_symbol) != set(bars_by_symbol):
        raise ValueError("double-slope, MA, and bar symbols must match exactly")
    events: list[ComparableUpEvent] = []
    pairs: list[DetectionPair] = []
    for symbol in sorted(ds_by_symbol):
        bars = tuple(bars_by_symbol[symbol])
        _validate_result_alignment(ds_by_symbol[symbol], ma_by_symbol[symbol], bars)
        ds_events = tuple(
            ComparableUpEvent(
                method="DOUBLE_SLOPE",
                event_id=event.event_id,
                symbol=symbol,
                trade_date=event.trade_date,
                close=event.close,
            )
            for event in ds_by_symbol[symbol].events
            if event.direction == "UP"
        )
        ma_events = tuple(
            ComparableUpEvent(
                method="MA_BASELINE",
                event_id=event.event_id,
                symbol=symbol,
                trade_date=event.trade_date,
                close=event.close,
            )
            for event in ma_by_symbol[symbol].events
            if event.current_state is TrendState.TURNING_UP
        )
        events.extend(ds_events)
        events.extend(ma_events)
        pairs.extend(_pair_events(ds_events, ma_events, bars, pair_window_bars))
    ordered_events = tuple(
        sorted(events, key=lambda item: (item.trade_date, item.symbol, item.method, item.event_id))
    )
    outcomes = tuple(
        _evaluate_event(
            event,
            tuple(bars_by_symbol[event.symbol]),
            forward_window_bars,
            follow_through_threshold_pct,
        )
        for event in ordered_events
    )
    summaries = tuple(_summarize(method, outcomes) for method in ("DOUBLE_SLOPE", "MA_BASELINE"))
    lead_values = [pair.double_slope_lead_bars for pair in pairs]
    return ComparisonResult(
        events=ordered_events,
        outcomes=outcomes,
        pairs=tuple(sorted(pairs, key=lambda item: (item.symbol, item.double_slope_date, item.ma_date))),
        summaries=summaries,
        median_double_slope_lead_bars=median(lead_values) if lead_values else None,
        forward_window_bars=forward_window_bars,
        follow_through_threshold_pct=follow_through_threshold_pct,
        pair_window_bars=pair_window_bars,
    )


def _evaluate_event(
    event: ComparableUpEvent,
    bars: tuple[MarketBar, ...],
    forward_window: int,
    threshold: float,
) -> EventOutcome:
    index_by_date = {bar.trade_date: index for index, bar in enumerate(bars)}
    try:
        event_index = index_by_date[event.trade_date]
    except KeyError as error:
        raise ValueError("event date is absent from source bars") from error
    if event_index + forward_window >= len(bars):
        return EventOutcome(
            method=event.method,
            event_id=event.event_id,
            symbol=event.symbol,
            trade_date=event.trade_date,
            close=event.close,
            evaluation_status="PENDING",
            forward_return=None,
            maximum_gain=None,
            maximum_drawdown=None,
            no_follow_through=None,
            negative_at_horizon=None,
            five_pct_path_result="PENDING",
        )
    future = bars[event_index + 1 : event_index + forward_window + 1]
    returns = tuple(bar.close / event.close - 1 for bar in future)
    upside_index = next((index for index, value in enumerate(returns) if value >= threshold), None)
    downside_index = next((index for index, value in enumerate(returns) if value <= -threshold), None)
    if upside_index is None and downside_index is None:
        path_result = "NEITHER"
    elif downside_index is None or (
        upside_index is not None and upside_index < downside_index
    ):
        path_result = "UPSIDE_FIRST"
    else:
        path_result = "DOWNSIDE_FIRST"
    maximum_gain = max(returns)
    forward_return = returns[-1]
    return EventOutcome(
        method=event.method,
        event_id=event.event_id,
        symbol=event.symbol,
        trade_date=event.trade_date,
        close=event.close,
        evaluation_status="EVALUATED",
        forward_return=forward_return,
        maximum_gain=maximum_gain,
        maximum_drawdown=min(returns),
        no_follow_through=maximum_gain < threshold,
        negative_at_horizon=forward_return <= 0,
        five_pct_path_result=path_result,
    )


def _pair_events(
    double_slope_events: Sequence[ComparableUpEvent],
    ma_events: Sequence[ComparableUpEvent],
    bars: Sequence[MarketBar],
    pair_window: int,
) -> tuple[DetectionPair, ...]:
    index_by_date = {bar.trade_date: index for index, bar in enumerate(bars)}
    candidates = []
    for ds_index, ds_event in enumerate(double_slope_events):
        for ma_index, ma_event in enumerate(ma_events):
            distance = index_by_date[ma_event.trade_date] - index_by_date[ds_event.trade_date]
            if abs(distance) <= pair_window:
                candidates.append((abs(distance), ds_event.trade_date, ma_event.trade_date, ds_index, ma_index, distance))
    used_ds: set[int] = set()
    used_ma: set[int] = set()
    pairs: list[DetectionPair] = []
    for _, _, _, ds_index, ma_index, distance in sorted(candidates):
        if ds_index in used_ds or ma_index in used_ma:
            continue
        ds_event = double_slope_events[ds_index]
        ma_event = ma_events[ma_index]
        pairs.append(DetectionPair(
            symbol=ds_event.symbol,
            double_slope_event_id=ds_event.event_id,
            double_slope_date=ds_event.trade_date,
            ma_event_id=ma_event.event_id,
            ma_date=ma_event.trade_date,
            double_slope_lead_bars=distance,
        ))
        used_ds.add(ds_index)
        used_ma.add(ma_index)
    return tuple(pairs)


def _summarize(method: str, outcomes: Sequence[EventOutcome]) -> MethodSummary:
    selected = tuple(item for item in outcomes if item.method == method)
    evaluated = tuple(item for item in selected if item.evaluation_status == "EVALUATED")
    no_follow = sum(item.no_follow_through is True for item in evaluated)
    return MethodSummary(
        method=method,
        total_up_events=len(selected),
        evaluable_events=len(evaluated),
        pending_events=len(selected) - len(evaluated),
        no_follow_through_events=no_follow,
        negative_at_20d_events=sum(item.negative_at_horizon is True for item in evaluated),
        downside_first_events=sum(item.five_pct_path_result == "DOWNSIDE_FIRST" for item in evaluated),
        no_follow_through_rate=no_follow / len(evaluated) if evaluated else None,
    )


def _unique_by_symbol(results: Sequence[object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for result in results:
        symbol = getattr(result, "symbol", None)
        if not isinstance(symbol, str) or not symbol or symbol in output:
            raise ValueError("results must contain unique nonempty symbols")
        output[symbol] = result
    if not output:
        raise ValueError("results must not be empty")
    return output


def _validate_result_alignment(
    double_slope: DoubleSlopeResult,
    ma_result: MAStateResult,
    bars: tuple[MarketBar, ...],
) -> None:
    if not bars or len(double_slope.observations) != len(bars) or len(ma_result.observations) != len(bars):
        raise ValueError("comparison observations must align with source bars")
    for bar, ds_observation, ma_observation in zip(
        bars, double_slope.observations, ma_result.observations, strict=True
    ):
        if (
            bar.symbol != ds_observation.symbol
            or bar.symbol != ma_observation.symbol
            or bar.trade_date != ds_observation.trade_date
            or bar.trade_date != ma_observation.trade_date
            or not math.isclose(bar.close, ds_observation.close, rel_tol=0.0, abs_tol=1e-9)
            or not math.isclose(bar.close, ma_observation.close, rel_tol=0.0, abs_tol=1e-9)
        ):
            raise ValueError("comparison identity does not align with source bars")
