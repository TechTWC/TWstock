from __future__ import annotations

from datetime import date
import hashlib
import math
from numbers import Real
from typing import Sequence

from twstock_data.models import MarketBar

from .models import (
    DoubleSlopeConfig,
    DoubleSlopeEvent,
    DoubleSlopeObservation,
    DoubleSlopeResult,
    SlopeState,
)


class DoubleSlopeTurningEngine:
    """Compare adjacent log-price OLS slopes using information through date t."""

    def __init__(self, config: DoubleSlopeConfig | None = None) -> None:
        self.config = config or DoubleSlopeConfig()

    def run(self, bars: Sequence[MarketBar]) -> DoubleSlopeResult:
        source = tuple(bars)
        _validate_bars(source)
        log_closes = tuple(math.log(bar.close) for bar in source)
        observations: list[DoubleSlopeObservation] = []
        events: list[DoubleSlopeEvent] = []
        pending_direction: str | None = None
        confirmation_count = 0
        for index, bar in enumerate(source):
            statistics = self._statistics(log_closes, index)
            raw_direction = self._raw_turn_direction(statistics)
            if raw_direction is None:
                pending_direction = None
                confirmation_count = 0
            elif raw_direction == pending_direction:
                confirmation_count += 1
            else:
                pending_direction = raw_direction
                confirmation_count = 1
            state = self._state(statistics, raw_direction, confirmation_count)
            support, contrary = self._evidence(
                statistics, raw_direction, confirmation_count, state
            )
            observation = DoubleSlopeObservation(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                close=bar.close,
                state=state,
                prior_slope_pct=statistics.prior_slope_pct,
                recent_slope_pct=statistics.recent_slope_pct,
                slope_difference_pct=statistics.slope_difference_pct,
                difference_standard_error=statistics.difference_standard_error,
                z_score=statistics.z_score,
                approximate_two_sided_p=statistics.approximate_two_sided_p,
                raw_turn_direction=raw_direction,
                consecutive_confirmation_count=confirmation_count,
                support_evidence=support,
                contrary_evidence=contrary,
            )
            observations.append(observation)
            if state in (SlopeState.TURNING_UP, SlopeState.TURNING_DOWN):
                assert statistics.prior_slope_pct is not None
                assert statistics.recent_slope_pct is not None
                assert statistics.z_score is not None
                events.append(
                    self._event(
                        bar.trade_date,
                        bar.symbol,
                        bar.close,
                        state,
                        statistics.prior_slope_pct,
                        statistics.recent_slope_pct,
                        statistics.z_score,
                    )
                )
        return DoubleSlopeResult(
            symbol=source[0].symbol,
            parameter_version=self.config.parameter_version,
            parameter_hash=self.config.parameter_hash,
            observations=tuple(observations),
            events=tuple(events),
        )

    def _statistics(
        self, log_closes: Sequence[float], index: int
    ) -> "_SlopeStatistics":
        config = self.config
        start = index + 1 - config.minimum_history_bars
        if start < 0:
            return _SlopeStatistics()
        split = start + config.prior_window
        end = split + config.recent_window
        prior = _ols_slope(log_closes[start:split])
        recent = _ols_slope(log_closes[split:end])
        difference = recent.slope - prior.slope
        standard_error = math.sqrt(prior.standard_error**2 + recent.standard_error**2)
        if standard_error == 0:
            if difference > 0:
                z_score = math.inf
            elif difference < 0:
                z_score = -math.inf
            else:
                z_score = 0.0
        else:
            z_score = difference / standard_error
        approximate_p = math.erfc(abs(z_score) / math.sqrt(2.0))
        return _SlopeStatistics(
            prior_slope_pct=math.expm1(prior.slope),
            recent_slope_pct=math.expm1(recent.slope),
            slope_difference_pct=math.expm1(recent.slope) - math.expm1(prior.slope),
            difference_standard_error=standard_error,
            z_score=z_score,
            approximate_two_sided_p=approximate_p,
        )

    def _raw_turn_direction(self, statistics: "_SlopeStatistics") -> str | None:
        if statistics.z_score is None:
            return None
        assert statistics.prior_slope_pct is not None
        assert statistics.recent_slope_pct is not None
        tolerance = self.config.slope_flat_tolerance_pct
        if (
            statistics.prior_slope_pct <= tolerance
            and statistics.recent_slope_pct > tolerance
            and statistics.z_score >= self.config.z_threshold
        ):
            return "UP"
        if (
            statistics.prior_slope_pct >= -tolerance
            and statistics.recent_slope_pct < -tolerance
            and statistics.z_score <= -self.config.z_threshold
        ):
            return "DOWN"
        return None

    def _state(
        self,
        statistics: "_SlopeStatistics",
        raw_direction: str | None,
        confirmation_count: int,
    ) -> SlopeState:
        if statistics.recent_slope_pct is None:
            return SlopeState.INSUFFICIENT_HISTORY
        if raw_direction == "UP" and confirmation_count == self.config.confirmation_bars:
            return SlopeState.TURNING_UP
        if raw_direction == "DOWN" and confirmation_count == self.config.confirmation_bars:
            return SlopeState.TURNING_DOWN
        tolerance = self.config.slope_flat_tolerance_pct
        if statistics.recent_slope_pct > tolerance:
            return SlopeState.RISING
        if statistics.recent_slope_pct < -tolerance:
            return SlopeState.FALLING
        return SlopeState.FLAT

    def _evidence(
        self,
        statistics: "_SlopeStatistics",
        raw_direction: str | None,
        confirmation_count: int,
        state: SlopeState,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if statistics.recent_slope_pct is None:
            return (
                (f"INSUFFICIENT_HISTORY:NEED_{self.config.minimum_history_bars}_BARS",),
                ("SLOPE_DIFFERENCE_NOT_INTERPRETABLE_YET",),
            )
        support: list[str] = []
        contrary: list[str] = []
        if state is SlopeState.TURNING_UP:
            support.extend((
                "PRIOR_SLOPE_FLAT_OR_DOWN",
                "RECENT_SLOPE_POSITIVE",
                "POSITIVE_SLOPE_CHANGE_EXCEEDS_Z_THRESHOLD",
                "CONSECUTIVE_CONFIRMATION_MET",
            ))
        elif state is SlopeState.TURNING_DOWN:
            support.extend((
                "PRIOR_SLOPE_FLAT_OR_UP",
                "RECENT_SLOPE_NEGATIVE",
                "NEGATIVE_SLOPE_CHANGE_EXCEEDS_Z_THRESHOLD",
                "CONSECUTIVE_CONFIRMATION_MET",
            ))
        elif state is SlopeState.RISING:
            support.append("RECENT_SLOPE_POSITIVE")
        elif state is SlopeState.FALLING:
            support.append("RECENT_SLOPE_NEGATIVE")
        else:
            support.append("RECENT_SLOPE_APPROXIMATELY_FLAT")
        if raw_direction and confirmation_count < self.config.confirmation_bars:
            contrary.append("TURN_CANDIDATE_AWAITING_CONFIRMATION")
        if raw_direction is None and state in (SlopeState.RISING, SlopeState.FALLING):
            contrary.append("NO_SIGNIFICANT_CONSECUTIVE_SLOPE_REVERSAL")
        contrary.append("NORMAL_APPROXIMATION_NOT_CALIBRATED_FOR_TAIWAN_EQUITIES")
        return tuple(support), tuple(contrary)

    def _event(
        self,
        trade_date: date,
        symbol: str,
        close: float,
        state: SlopeState,
        prior_slope_pct: float,
        recent_slope_pct: float,
        z_score: float,
    ) -> DoubleSlopeEvent:
        direction = "UP" if state is SlopeState.TURNING_UP else "DOWN"
        identity = "|".join((
            self.config.parameter_hash,
            symbol,
            trade_date.isoformat(),
            direction,
        ))
        return DoubleSlopeEvent(
            event_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            symbol=symbol,
            trade_date=trade_date,
            direction=direction,
            close=close,
            prior_slope_pct=prior_slope_pct,
            recent_slope_pct=recent_slope_pct,
            z_score=z_score,
        )


class _Regression:
    def __init__(self, slope: float, standard_error: float) -> None:
        self.slope = slope
        self.standard_error = standard_error


class _SlopeStatistics:
    def __init__(
        self,
        *,
        prior_slope_pct: float | None = None,
        recent_slope_pct: float | None = None,
        slope_difference_pct: float | None = None,
        difference_standard_error: float | None = None,
        z_score: float | None = None,
        approximate_two_sided_p: float | None = None,
    ) -> None:
        self.prior_slope_pct = prior_slope_pct
        self.recent_slope_pct = recent_slope_pct
        self.slope_difference_pct = slope_difference_pct
        self.difference_standard_error = difference_standard_error
        self.z_score = z_score
        self.approximate_two_sided_p = approximate_two_sided_p


def _ols_slope(values: Sequence[float]) -> _Regression:
    count = len(values)
    x_mean = (count - 1) / 2.0
    y_mean = sum(values) / count
    sxx = sum((index - x_mean) ** 2 for index in range(count))
    slope = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    ) / sxx
    intercept = y_mean - slope * x_mean
    residual_sum_squares = sum(
        (value - (intercept + slope * index)) ** 2
        for index, value in enumerate(values)
    )
    residual_variance = residual_sum_squares / (count - 2)
    standard_error = math.sqrt(max(0.0, residual_variance / sxx))
    return _Regression(slope, standard_error)


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
