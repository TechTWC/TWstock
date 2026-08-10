from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Sequence

from .models import BreakoutSnapshot, BreakoutState, PriceBar, TrackerConfig


@dataclass
class _Cycle:
    pivot_index: int
    pivot_date: date
    pivot_price: float
    breakout_index: int | None = None
    breakout_date: date | None = None


class BreakoutTracker:
    """Replay one symbol's bars without reading future observations."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()

    def run(self, bars: Sequence[PriceBar]) -> tuple[BreakoutSnapshot, ...]:
        self._validate_bars(bars)
        snapshots: list[BreakoutSnapshot] = []
        cycle: _Cycle | None = None

        for index, bar in enumerate(bars):
            if cycle is None:
                cycle = self._confirmed_cycle_at(index, bars)

            if cycle is None:
                continue

            volume_ratio = self._volume_ratio(index, bars)

            if cycle.breakout_index is None:
                setup_age = index - cycle.pivot_index
                if setup_age > self.config.max_setup_bars:
                    cycle = None
                    continue

                if self._is_first_breakout(bar, cycle, volume_ratio):
                    cycle.breakout_index = index
                    cycle.breakout_date = bar.trade_date
                    snapshots.append(
                        self._snapshot(
                            bar=bar,
                            cycle=cycle,
                            state=BreakoutState.NEW_TRIGGER,
                            days_since_breakout=0,
                            volume_ratio=volume_ratio,
                            reason="FIRST_CLOSE_ABOVE_FROZEN_PIVOT",
                        )
                    )
                else:
                    snapshots.append(
                        self._snapshot(
                            bar=bar,
                            cycle=cycle,
                            state=BreakoutState.SETUP,
                            days_since_breakout=None,
                            volume_ratio=volume_ratio,
                            reason="CONFIRMED_PIVOT_AWAITING_FIRST_BREAKOUT",
                        )
                    )
                continue

            days_since_breakout = index - cycle.breakout_index
            state, reason = self._post_breakout_state(
                bar=bar,
                cycle=cycle,
                days_since_breakout=days_since_breakout,
            )
            snapshots.append(
                self._snapshot(
                    bar=bar,
                    cycle=cycle,
                    state=state,
                    days_since_breakout=days_since_breakout,
                    volume_ratio=volume_ratio,
                    reason=reason,
                )
            )

            if state is BreakoutState.FAILED:
                cycle = None

        return tuple(snapshots)

    def _confirmed_cycle_at(
        self, index: int, bars: Sequence[PriceBar]
    ) -> _Cycle | None:
        candidate_index = index - self.config.pivot_confirmation_bars
        earliest_candidate = self.config.pivot_lookback - 1
        if candidate_index < earliest_candidate:
            return None

        candidate = bars[candidate_index]
        prior_start = candidate_index - self.config.pivot_lookback + 1
        prior_bars = bars[prior_start:candidate_index]
        if not prior_bars:
            return None
        if candidate.high <= max(bar.high for bar in prior_bars):
            return None

        confirmation_bars = bars[candidate_index + 1 : index + 1]
        if len(confirmation_bars) != self.config.pivot_confirmation_bars:
            return None
        if any(bar.high > candidate.high for bar in confirmation_bars):
            return None

        return _Cycle(
            pivot_index=candidate_index,
            pivot_date=candidate.trade_date,
            pivot_price=candidate.high,
        )

    def _is_first_breakout(
        self,
        bar: PriceBar,
        cycle: _Cycle,
        volume_ratio: float | None,
    ) -> bool:
        breakout_level = cycle.pivot_price * (1 + self.config.breakout_buffer_pct)
        if bar.close <= breakout_level:
            return False

        minimum_ratio = self.config.min_breakout_volume_ratio
        if minimum_ratio is None:
            return True
        return volume_ratio is not None and volume_ratio >= minimum_ratio

    def _post_breakout_state(
        self,
        bar: PriceBar,
        cycle: _Cycle,
        days_since_breakout: int,
    ) -> tuple[BreakoutState, str]:
        failure_level = cycle.pivot_price * (1 - self.config.failure_pct)
        if bar.close < failure_level:
            return BreakoutState.FAILED, "CLOSE_BELOW_FAILURE_LEVEL"

        retest_ceiling = cycle.pivot_price * (1 + self.config.retest_band_pct)
        if bar.low <= retest_ceiling:
            return BreakoutState.RETEST, "LOW_REVISITED_PIVOT_BAND"

        extension_level = cycle.pivot_price * (1 + self.config.extension_pct)
        if bar.close >= extension_level:
            return BreakoutState.EXTENDED, "CLOSE_REACHED_EXTENSION_LEVEL"

        if days_since_breakout > self.config.max_tracking_bars:
            return BreakoutState.EXTENDED, "BREAKOUT_CYCLE_AGED_OUT"

        return BreakoutState.CONFIRMED, "ABOVE_FAILURE_LEVEL_AFTER_TRIGGER"

    def _volume_ratio(
        self, index: int, bars: Sequence[PriceBar]
    ) -> float | None:
        start = index - self.config.volume_lookback
        if start < 0:
            return None
        prior = bars[start:index]
        average = sum(bar.volume for bar in prior) / len(prior)
        if average <= 0:
            return None
        return bars[index].volume / average

    @staticmethod
    def _snapshot(
        *,
        bar: PriceBar,
        cycle: _Cycle,
        state: BreakoutState,
        days_since_breakout: int | None,
        volume_ratio: float | None,
        reason: str,
    ) -> BreakoutSnapshot:
        return BreakoutSnapshot(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            state=state,
            pivot_date=cycle.pivot_date,
            pivot_price=cycle.pivot_price,
            breakout_date=cycle.breakout_date,
            days_since_breakout=days_since_breakout,
            close=bar.close,
            distance_to_pivot_pct=(bar.close / cycle.pivot_price) - 1,
            volume_ratio=volume_ratio,
            reason=reason,
        )

    @staticmethod
    def _validate_bars(bars: Sequence[PriceBar]) -> None:
        if not bars:
            return

        symbol = bars[0].symbol
        previous_date: date | None = None
        for index, bar in enumerate(bars):
            if not bar.symbol or bar.symbol != symbol:
                raise ValueError("bars must contain exactly one nonempty symbol")
            if not isinstance(bar.trade_date, date):
                raise ValueError(f"bar {index} contains invalid trade_date")
            if previous_date is not None and bar.trade_date <= previous_date:
                raise ValueError("bars must be strictly ascending by trade_date")

            prices = (bar.open, bar.high, bar.low, bar.close)
            if not all(math.isfinite(value) and value > 0 for value in prices):
                raise ValueError(f"bar {index} contains invalid OHLC values")
            if bar.low > bar.high:
                raise ValueError(f"bar {index} has low above high")
            if bar.low > min(bar.open, bar.close) or bar.high < max(
                bar.open, bar.close
            ):
                raise ValueError(f"bar {index} violates OHLC bounds")
            if not math.isfinite(bar.volume) or bar.volume < 0:
                raise ValueError(f"bar {index} contains invalid volume")

            previous_date = bar.trade_date
