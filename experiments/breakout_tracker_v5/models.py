from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from numbers import Real


class BreakoutState(str, Enum):
    SETUP = "SETUP"
    NEW_TRIGGER = "NEW_TRIGGER"
    CONFIRMED = "CONFIRMED"
    RETEST = "RETEST"
    EXTENDED = "EXTENDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PriceBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class TrackerConfig:
    pivot_lookback: int = 20
    pivot_confirmation_bars: int = 3
    max_setup_bars: int = 60
    breakout_buffer_pct: float = 0.0
    volume_lookback: int = 20
    min_breakout_volume_ratio: float | None = None
    retest_band_pct: float = 0.02
    failure_pct: float = 0.03
    extension_pct: float = 0.15
    max_tracking_bars: int = 40

    def __post_init__(self) -> None:
        integer_fields = {
            "pivot_lookback": self.pivot_lookback,
            "pivot_confirmation_bars": self.pivot_confirmation_bars,
            "max_setup_bars": self.max_setup_bars,
            "volume_lookback": self.volume_lookback,
            "max_tracking_bars": self.max_tracking_bars,
        }
        for name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

        if self.pivot_lookback < 2:
            raise ValueError("pivot_lookback must be at least 2")

        percentage_fields = {
            "breakout_buffer_pct": self.breakout_buffer_pct,
            "retest_band_pct": self.retest_band_pct,
            "failure_pct": self.failure_pct,
            "extension_pct": self.extension_pct,
        }
        for name, value in percentage_fields.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")

        if self.failure_pct >= 1:
            raise ValueError("failure_pct must be less than 1")

        if self.min_breakout_volume_ratio is not None:
            if (
                isinstance(self.min_breakout_volume_ratio, bool)
                or not isinstance(self.min_breakout_volume_ratio, Real)
                or not math.isfinite(self.min_breakout_volume_ratio)
            ):
                raise ValueError("min_breakout_volume_ratio must be finite")
            if self.min_breakout_volume_ratio <= 0:
                raise ValueError("min_breakout_volume_ratio must be positive")


@dataclass(frozen=True)
class BreakoutSnapshot:
    symbol: str
    trade_date: date
    state: BreakoutState
    pivot_date: date
    pivot_price: float
    breakout_date: date | None
    days_since_breakout: int | None
    close: float
    distance_to_pivot_pct: float
    volume_ratio: float | None
    reason: str
