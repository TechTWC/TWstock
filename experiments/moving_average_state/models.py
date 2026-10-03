from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import math
from numbers import Real


class TrendState(str, Enum):
    UNCLEAR = "UNCLEAR"
    BASE = "BASE"
    TURNING_UP = "TURNING_UP"
    UPTREND = "UPTREND"
    TURNING_DOWN = "TURNING_DOWN"
    DOWNTREND = "DOWNTREND"


class LongTermContext(str, Enum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    LONG_TERM_BULL = "LONG_TERM_BULL"
    LONG_TERM_REPAIR = "LONG_TERM_REPAIR"
    LONG_TERM_BOTTOMING = "LONG_TERM_BOTTOMING"
    LONG_TERM_BEAR_RALLY = "LONG_TERM_BEAR_RALLY"
    LONG_TERM_BEAR = "LONG_TERM_BEAR"
    LONG_TERM_MIXED = "LONG_TERM_MIXED"


@dataclass(frozen=True)
class MAStateConfig:
    parameter_version: str = "MA-STATE-PARAM-002"
    fast_window: int = 5
    short_window: int = 10
    medium_window: int = 20
    long_window: int = 60
    half_year_window: int = 120
    global_long_window: int = 200
    annual_window: int = 240
    slope_lookback: int = 5
    base_flat_slope_tolerance_pct: float = 0.005
    base_ma_spread_tolerance_pct: float = 0.03
    long_term_flat_slope_tolerance_pct: float = 0.002

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_version, str) or not self.parameter_version.strip():
            raise ValueError("parameter_version must be a nonempty string")
        windows = (
            self.fast_window,
            self.short_window,
            self.medium_window,
            self.long_window,
            self.half_year_window,
            self.global_long_window,
            self.annual_window,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in windows):
            raise ValueError("moving-average windows must be integers")
        if not (
            2
            <= self.fast_window
            < self.short_window
            < self.medium_window
            < self.long_window
            < self.half_year_window
            < self.global_long_window
            < self.annual_window
        ):
            raise ValueError("moving-average windows must be strictly increasing and at least 2")
        if isinstance(self.slope_lookback, bool) or not isinstance(self.slope_lookback, int):
            raise ValueError("slope_lookback must be an integer")
        if self.slope_lookback < 1:
            raise ValueError("slope_lookback must be positive")
        for name in (
            "base_flat_slope_tolerance_pct",
            "base_ma_spread_tolerance_pct",
            "long_term_flat_slope_tolerance_pct",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0 or value >= 1:
                raise ValueError(f"{name} must be in [0, 1)")

    @property
    def minimum_history_bars(self) -> int:
        return self.long_window + self.slope_lookback

    @property
    def minimum_context_history_bars(self) -> int:
        return self.annual_window + self.slope_lookback

    def canonical_json(self) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @property
    def parameter_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MAStateObservation:
    symbol: str
    trade_date: date
    close: float
    state: TrendState
    ma_fast: float | None
    ma_short: float | None
    ma_medium: float | None
    ma_long: float | None
    ma_half_year: float | None
    ma_global_long: float | None
    ma_annual: float | None
    medium_slope_pct: float | None
    long_slope_pct: float | None
    half_year_slope_pct: float | None
    global_long_slope_pct: float | None
    annual_slope_pct: float | None
    ma_spread_pct: float | None
    distance_to_medium_ma_pct: float | None
    distance_to_half_year_ma_pct: float | None
    distance_to_global_long_ma_pct: float | None
    distance_to_annual_ma_pct: float | None
    long_term_context: LongTermContext
    long_term_support_evidence: tuple[str, ...]
    long_term_contrary_evidence: tuple[str, ...]
    structural_labels: tuple[str, ...]
    support_evidence: tuple[str, ...]
    contrary_evidence: tuple[str, ...]


@dataclass(frozen=True)
class MAStateEvent:
    event_id: str
    symbol: str
    trade_date: date
    previous_state: TrendState | None
    current_state: TrendState
    close: float


@dataclass(frozen=True)
class MAStateResult:
    symbol: str
    parameter_version: str
    parameter_hash: str
    observations: tuple[MAStateObservation, ...]
    events: tuple[MAStateEvent, ...]
    corporate_action_status: str = "UNVERIFIED"
    investment_use: str = "PROHIBITED"
