from __future__ import annotations

from datetime import date
import hashlib
import math
from numbers import Real
from typing import Sequence

from twstock_data.models import MarketBar

from .models import (
    LongTermContext,
    MAStateConfig,
    MAStateEvent,
    MAStateObservation,
    MAStateResult,
    TrendState,
)


class MovingAverageStateEngine:
    """Classify each point-in-time prefix with a transparent MA baseline."""

    def __init__(self, config: MAStateConfig | None = None) -> None:
        self.config = config or MAStateConfig()

    def run(self, bars: Sequence[MarketBar]) -> MAStateResult:
        source = tuple(bars)
        _validate_bars(source)
        closes = tuple(bar.close for bar in source)
        moving_averages = {
            window: _rolling_mean(closes, window)
            for window in (
                self.config.fast_window,
                self.config.short_window,
                self.config.medium_window,
                self.config.long_window,
                self.config.half_year_window,
                self.config.global_long_window,
                self.config.annual_window,
            )
        }
        observations: list[MAStateObservation] = []
        events: list[MAStateEvent] = []
        previous_state: TrendState | None = None
        for index, bar in enumerate(source):
            observation = self._observation(index, bar, moving_averages)
            observations.append(observation)
            if observation.state is not previous_state:
                events.append(
                    self._event(
                        bar.trade_date,
                        bar.symbol,
                        bar.close,
                        previous_state,
                        observation.state,
                    )
                )
                previous_state = observation.state
        return MAStateResult(
            symbol=source[0].symbol,
            parameter_version=self.config.parameter_version,
            parameter_hash=self.config.parameter_hash,
            observations=tuple(observations),
            events=tuple(events),
        )

    def _observation(
        self,
        index: int,
        bar: MarketBar,
        moving_averages: dict[int, tuple[float | None, ...]],
    ) -> MAStateObservation:
        config = self.config
        ma_fast = moving_averages[config.fast_window][index]
        ma_short = moving_averages[config.short_window][index]
        ma_medium = moving_averages[config.medium_window][index]
        ma_long = moving_averages[config.long_window][index]
        ma_half_year = moving_averages[config.half_year_window][index]
        ma_global_long = moving_averages[config.global_long_window][index]
        ma_annual = moving_averages[config.annual_window][index]
        prior_index = index - config.slope_lookback
        prior_medium = (
            moving_averages[config.medium_window][prior_index]
            if prior_index >= 0
            else None
        )
        prior_long = (
            moving_averages[config.long_window][prior_index]
            if prior_index >= 0
            else None
        )
        medium_slope = _normalized_change(ma_medium, prior_medium)
        long_slope = _normalized_change(ma_long, prior_long)
        half_year_slope = _prior_normalized_change(
            moving_averages[config.half_year_window], index, config.slope_lookback
        )
        global_long_slope = _prior_normalized_change(
            moving_averages[config.global_long_window], index, config.slope_lookback
        )
        annual_slope = _prior_normalized_change(
            moving_averages[config.annual_window], index, config.slope_lookback
        )
        available = (ma_fast, ma_short, ma_medium, ma_long)
        ma_spread = None
        distance_to_medium = None
        if all(value is not None for value in available):
            values = tuple(float(value) for value in available if value is not None)
            ma_spread = max(values) / min(values) - 1
            distance_to_medium = bar.close / float(ma_medium) - 1
        distance_to_half_year = _distance(bar.close, ma_half_year)
        distance_to_global_long = _distance(bar.close, ma_global_long)
        distance_to_annual = _distance(bar.close, ma_annual)

        previous_fast = moving_averages[config.fast_window][index - 1] if index else None
        previous_short = moving_averages[config.short_window][index - 1] if index else None
        labels = _structural_labels(
            bar.close,
            ma_fast,
            ma_short,
            ma_medium,
            ma_long,
            previous_fast,
            previous_short,
            medium_slope,
            long_slope,
        )
        state = _classify_state(
            bar.close,
            ma_fast,
            ma_short,
            ma_medium,
            ma_long,
            medium_slope,
            long_slope,
            ma_spread,
            config,
        )
        long_term_context = _classify_long_term_context(
            state,
            bar.close,
            ma_medium,
            ma_half_year,
            ma_annual,
            half_year_slope,
            annual_slope,
            config,
        )
        long_term_support, long_term_contrary = _long_term_evidence(
            long_term_context,
            bar.close,
            ma_half_year,
            ma_global_long,
            ma_annual,
            half_year_slope,
            global_long_slope,
            annual_slope,
            config,
        )
        support, contrary = _evidence(
            state,
            bar.close,
            ma_fast,
            ma_short,
            ma_medium,
            ma_long,
            medium_slope,
            long_slope,
            ma_spread,
            config,
        )
        return MAStateObservation(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            close=bar.close,
            state=state,
            ma_fast=ma_fast,
            ma_short=ma_short,
            ma_medium=ma_medium,
            ma_long=ma_long,
            ma_half_year=ma_half_year,
            ma_global_long=ma_global_long,
            ma_annual=ma_annual,
            medium_slope_pct=medium_slope,
            long_slope_pct=long_slope,
            half_year_slope_pct=half_year_slope,
            global_long_slope_pct=global_long_slope,
            annual_slope_pct=annual_slope,
            ma_spread_pct=ma_spread,
            distance_to_medium_ma_pct=distance_to_medium,
            distance_to_half_year_ma_pct=distance_to_half_year,
            distance_to_global_long_ma_pct=distance_to_global_long,
            distance_to_annual_ma_pct=distance_to_annual,
            long_term_context=long_term_context,
            long_term_support_evidence=long_term_support,
            long_term_contrary_evidence=long_term_contrary,
            structural_labels=labels,
            support_evidence=support,
            contrary_evidence=contrary,
        )

    def _event(
        self,
        trade_date: date,
        symbol: str,
        close: float,
        previous_state: TrendState | None,
        current_state: TrendState,
    ) -> MAStateEvent:
        identity = "|".join(
            (
                self.config.parameter_hash,
                symbol,
                trade_date.isoformat(),
                previous_state.value if previous_state else "NONE",
                current_state.value,
            )
        )
        return MAStateEvent(
            event_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            symbol=symbol,
            trade_date=trade_date,
            previous_state=previous_state,
            current_state=current_state,
            close=close,
        )


def _rolling_mean(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        output.append(running / window if index + 1 >= window else None)
    return tuple(output)


def _normalized_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    return current / prior - 1


def _prior_normalized_change(
    values: Sequence[float | None], index: int, lookback: int
) -> float | None:
    prior_index = index - lookback
    prior = values[prior_index] if prior_index >= 0 else None
    return _normalized_change(values[index], prior)


def _distance(close: float, moving_average: float | None) -> float | None:
    return close / moving_average - 1 if moving_average is not None else None


def _classify_long_term_context(
    state: TrendState,
    close: float,
    ma_medium: float | None,
    ma_half_year: float | None,
    ma_annual: float | None,
    half_year_slope: float | None,
    annual_slope: float | None,
    config: MAStateConfig,
) -> LongTermContext:
    required = (
        ma_medium,
        ma_half_year,
        ma_annual,
        half_year_slope,
        annual_slope,
    )
    if any(value is None for value in required):
        return LongTermContext.INSUFFICIENT_HISTORY
    assert ma_medium is not None
    assert ma_half_year is not None and ma_annual is not None
    assert half_year_slope is not None and annual_slope is not None
    tolerance = config.long_term_flat_slope_tolerance_pct
    if (
        close > ma_half_year > ma_annual
        and half_year_slope > tolerance
        and annual_slope > 0
    ):
        return LongTermContext.LONG_TERM_BULL
    if (
        close < ma_half_year < ma_annual
        and half_year_slope < -tolerance
        and annual_slope < 0
    ):
        return LongTermContext.LONG_TERM_BEAR
    if half_year_slope > tolerance and abs(annual_slope) <= tolerance:
        return LongTermContext.LONG_TERM_BOTTOMING
    if close > ma_half_year:
        return LongTermContext.LONG_TERM_REPAIR
    if (
        state in (TrendState.TURNING_UP, TrendState.UPTREND)
        and close > ma_medium
        and close < ma_half_year
        and half_year_slope < 0
        and annual_slope < 0
    ):
        return LongTermContext.LONG_TERM_BEAR_RALLY
    return LongTermContext.LONG_TERM_MIXED


def _long_term_evidence(
    context: LongTermContext,
    close: float,
    ma_half_year: float | None,
    ma_global_long: float | None,
    ma_annual: float | None,
    half_year_slope: float | None,
    global_long_slope: float | None,
    annual_slope: float | None,
    config: MAStateConfig,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = (
        ma_half_year,
        ma_global_long,
        ma_annual,
        half_year_slope,
        global_long_slope,
        annual_slope,
    )
    if any(value is None for value in required):
        return (
            (f"INSUFFICIENT_LONG_HISTORY:NEED_{config.minimum_context_history_bars}_BARS",),
            ("LONG_TERM_CONTEXT_NOT_INTERPRETABLE_YET",),
        )
    assert ma_half_year is not None and ma_global_long is not None and ma_annual is not None
    assert half_year_slope is not None and global_long_slope is not None
    assert annual_slope is not None
    support: list[str] = []
    contrary: list[str] = []
    if context is LongTermContext.LONG_TERM_BULL:
        support.extend(("PRICE_ABOVE_MA120_ABOVE_MA240", "MA120_SLOPE_POSITIVE", "MA240_SLOPE_POSITIVE"))
    elif context is LongTermContext.LONG_TERM_BEAR:
        support.extend(("PRICE_BELOW_MA120_BELOW_MA240", "MA120_SLOPE_NEGATIVE", "MA240_SLOPE_NEGATIVE"))
    elif context is LongTermContext.LONG_TERM_BOTTOMING:
        support.extend(("MA120_SLOPE_POSITIVE", "MA240_APPROXIMATELY_FLAT"))
        contrary.append("LONG_TERM_BULLISH_ALIGNMENT_NOT_CONFIRMED")
    elif context is LongTermContext.LONG_TERM_REPAIR:
        support.append("PRICE_ABOVE_MA120")
        contrary.append("LONG_TERM_BULLISH_ALIGNMENT_NOT_CONFIRMED")
    elif context is LongTermContext.LONG_TERM_BEAR_RALLY:
        support.extend(("EARLY_UP_STATE_BELOW_MA120", "MA120_SLOPE_NEGATIVE", "MA240_SLOPE_NEGATIVE"))
        contrary.append("RALLY_MAY_NOT_BE_LONG_TERM_REVERSAL")
    else:
        support.append("LONG_TERM_SIGNALS_MIXED")
        contrary.append("NO_DOMINANT_LONG_TERM_CONTEXT")
    if (close > ma_global_long) != (close > ma_annual):
        contrary.append("MA200_AND_MA240_PRICE_TEST_DISAGREE")
    if (global_long_slope > 0) != (annual_slope > 0):
        contrary.append("MA200_AND_MA240_SLOPE_DIRECTION_DISAGREE")
    return tuple(support), tuple(contrary)


def _classify_state(
    close: float,
    ma_fast: float | None,
    ma_short: float | None,
    ma_medium: float | None,
    ma_long: float | None,
    medium_slope: float | None,
    long_slope: float | None,
    ma_spread: float | None,
    config: MAStateConfig,
) -> TrendState:
    values = (ma_fast, ma_short, ma_medium, ma_long, medium_slope, long_slope, ma_spread)
    if any(value is None for value in values):
        return TrendState.UNCLEAR
    assert ma_fast is not None and ma_short is not None
    assert ma_medium is not None and ma_long is not None
    assert medium_slope is not None and long_slope is not None and ma_spread is not None

    bullish = close > ma_fast > ma_short > ma_medium > ma_long
    bearish = close < ma_fast < ma_short < ma_medium < ma_long
    if (
        bullish
        and medium_slope > config.base_flat_slope_tolerance_pct
        and long_slope > config.base_flat_slope_tolerance_pct
    ):
        return TrendState.UPTREND
    if (
        bearish
        and medium_slope < -config.base_flat_slope_tolerance_pct
        and long_slope < -config.base_flat_slope_tolerance_pct
    ):
        return TrendState.DOWNTREND
    if (
        abs(medium_slope) <= config.base_flat_slope_tolerance_pct
        and abs(long_slope) <= config.base_flat_slope_tolerance_pct
        and ma_spread <= config.base_ma_spread_tolerance_pct
        and abs(close / ma_medium - 1) <= config.base_ma_spread_tolerance_pct
    ):
        return TrendState.BASE
    if close > ma_medium and ma_fast > ma_short and medium_slope > 0:
        return TrendState.TURNING_UP
    if close < ma_medium and ma_fast < ma_short and medium_slope < 0:
        return TrendState.TURNING_DOWN
    return TrendState.UNCLEAR


def _structural_labels(
    close: float,
    ma_fast: float | None,
    ma_short: float | None,
    ma_medium: float | None,
    ma_long: float | None,
    previous_fast: float | None,
    previous_short: float | None,
    medium_slope: float | None,
    long_slope: float | None,
) -> tuple[str, ...]:
    labels: list[str] = []
    if ma_medium is not None:
        labels.append("ABOVE_MA20" if close > ma_medium else "BELOW_OR_AT_MA20")
    if all(value is not None for value in (ma_fast, ma_short, ma_medium, ma_long)):
        assert ma_fast is not None and ma_short is not None
        assert ma_medium is not None and ma_long is not None
        if close > ma_fast > ma_short > ma_medium > ma_long:
            labels.append("FULL_BULLISH_ALIGNMENT")
        if close < ma_fast < ma_short < ma_medium < ma_long:
            labels.append("FULL_BEARISH_ALIGNMENT")
    if (
        previous_fast is not None
        and previous_short is not None
        and ma_fast is not None
        and ma_short is not None
    ):
        if previous_fast <= previous_short and ma_fast > ma_short:
            labels.append("FAST_CROSS_UP_TODAY")
        if previous_fast >= previous_short and ma_fast < ma_short:
            labels.append("FAST_CROSS_DOWN_TODAY")
    if medium_slope is not None:
        labels.append("MA20_SLOPE_POSITIVE" if medium_slope > 0 else "MA20_SLOPE_NONPOSITIVE")
    if long_slope is not None:
        labels.append("MA60_SLOPE_POSITIVE" if long_slope > 0 else "MA60_SLOPE_NONPOSITIVE")
    return tuple(labels)


def _evidence(
    state: TrendState,
    close: float,
    ma_fast: float | None,
    ma_short: float | None,
    ma_medium: float | None,
    ma_long: float | None,
    medium_slope: float | None,
    long_slope: float | None,
    ma_spread: float | None,
    config: MAStateConfig,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if any(value is None for value in (ma_fast, ma_short, ma_medium, ma_long, medium_slope, long_slope, ma_spread)):
        return (
            (f"INSUFFICIENT_HISTORY:NEED_{config.minimum_history_bars}_BARS",),
            ("STATE_NOT_INTERPRETABLE_YET",),
        )
    assert ma_fast is not None and ma_short is not None
    assert ma_medium is not None and ma_long is not None
    assert medium_slope is not None and long_slope is not None and ma_spread is not None
    facts = {
        "close_above_medium": close > ma_medium,
        "fast_above_short": ma_fast > ma_short,
        "medium_positive": medium_slope > 0,
        "long_positive": long_slope > 0,
        "bullish": close > ma_fast > ma_short > ma_medium > ma_long,
        "bearish": close < ma_fast < ma_short < ma_medium < ma_long,
        "base_slopes": abs(medium_slope) <= config.base_flat_slope_tolerance_pct
        and abs(long_slope) <= config.base_flat_slope_tolerance_pct,
        "compressed": ma_spread <= config.base_ma_spread_tolerance_pct,
        "price_near_medium": abs(close / ma_medium - 1)
        <= config.base_ma_spread_tolerance_pct,
    }
    support: list[str] = []
    contrary: list[str] = []
    if state is TrendState.UPTREND:
        support.extend(("PRICE_AND_MAS_FULL_BULLISH_ORDER", "MA20_SLOPE_POSITIVE", "MA60_SLOPE_POSITIVE"))
    elif state is TrendState.DOWNTREND:
        support.extend(("PRICE_AND_MAS_FULL_BEARISH_ORDER", "MA20_SLOPE_NEGATIVE", "MA60_SLOPE_NEGATIVE"))
    elif state is TrendState.BASE:
        support.extend(("MA20_AND_MA60_APPROXIMATELY_FLAT", "MOVING_AVERAGES_COMPRESSED", "PRICE_NEAR_MA20"))
        contrary.append("BASE_DOES_NOT_DETERMINE_BREAK_DIRECTION")
    elif state is TrendState.TURNING_UP:
        support.extend(("CLOSE_ABOVE_MA20", "MA5_ABOVE_MA10", "MA20_SLOPE_POSITIVE"))
        if not facts["bullish"]:
            contrary.append("FULL_BULLISH_ALIGNMENT_NOT_CONFIRMED")
        if not facts["long_positive"]:
            contrary.append("MA60_SLOPE_NOT_POSITIVE")
    elif state is TrendState.TURNING_DOWN:
        support.extend(("CLOSE_BELOW_MA20", "MA5_BELOW_MA10", "MA20_SLOPE_NEGATIVE"))
        if not facts["bearish"]:
            contrary.append("FULL_BEARISH_ALIGNMENT_NOT_CONFIRMED")
        if facts["long_positive"]:
            contrary.append("MA60_SLOPE_STILL_POSITIVE")
    else:
        support.append("NO_SINGLE_BASELINE_RULE_DOMINATES")
        contrary.extend(
            item
            for item, condition in (
                ("NOT_FULL_BULLISH_ALIGNMENT", not facts["bullish"]),
                ("NOT_FULL_BEARISH_ALIGNMENT", not facts["bearish"]),
                (
                    "NOT_BASE_COMPRESSION",
                    not (
                        facts["base_slopes"]
                        and facts["compressed"]
                        and facts["price_near_medium"]
                    ),
                ),
            )
            if condition
        )
    return tuple(support), tuple(contrary)


def _validate_bars(bars: Sequence[MarketBar]) -> None:
    if not bars:
        raise ValueError("bars must not be empty")
    symbol = bars[0].symbol
    previous: date | None = None
    for index, bar in enumerate(bars):
        if not isinstance(bar, MarketBar):
            raise ValueError(f"bar {index} must be MarketBar")
        if not bar.symbol or bar.symbol != symbol:
            raise ValueError("bars must contain one nonempty symbol")
        if previous is not None and bar.trade_date <= previous:
            raise ValueError("bars must have unique ascending dates")
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            or value <= 0
            for value in values
        ):
            raise ValueError(f"bar {index} contains invalid OHLCV")
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise ValueError(f"bar {index} violates OHLC bounds")
        previous = bar.trade_date
