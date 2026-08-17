from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import math
from numbers import Real


class SlopeState(str, Enum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    FLAT = "FLAT"
    RISING = "RISING"
    FALLING = "FALLING"
    TURNING_UP = "TURNING_UP"
    TURNING_DOWN = "TURNING_DOWN"


@dataclass(frozen=True)
class DoubleSlopeConfig:
    parameter_version: str = "DOUBLE-SLOPE-PARAM-001"
    prior_window: int = 20
    recent_window: int = 20
    slope_flat_tolerance_pct: float = 0.0005
    z_threshold: float = 1.96
    confirmation_bars: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_version, str) or not self.parameter_version.strip():
            raise ValueError("parameter_version must be a nonempty string")
        for name in ("prior_window", "recent_window", "confirmation_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if self.prior_window < 3 or self.recent_window < 3:
            raise ValueError("slope windows must be at least 3")
        if self.confirmation_bars < 1:
            raise ValueError("confirmation_bars must be positive")
        for name in ("slope_flat_tolerance_pct", "z_threshold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.slope_flat_tolerance_pct < 0 or self.slope_flat_tolerance_pct >= 1:
            raise ValueError("slope_flat_tolerance_pct must be in [0, 1)")
        if self.z_threshold <= 0:
            raise ValueError("z_threshold must be positive")

    @property
    def minimum_history_bars(self) -> int:
        return self.prior_window + self.recent_window

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
class DoubleSlopeObservation:
    symbol: str
    trade_date: date
    close: float
    state: SlopeState
    prior_slope_pct: float | None
    recent_slope_pct: float | None
    slope_difference_pct: float | None
    difference_standard_error: float | None
    z_score: float | None
    approximate_two_sided_p: float | None
    raw_turn_direction: str | None
    consecutive_confirmation_count: int
    support_evidence: tuple[str, ...]
    contrary_evidence: tuple[str, ...]


@dataclass(frozen=True)
class DoubleSlopeEvent:
    event_id: str
    symbol: str
    trade_date: date
    direction: str
    close: float
    prior_slope_pct: float
    recent_slope_pct: float
    z_score: float


@dataclass(frozen=True)
class DoubleSlopeResult:
    symbol: str
    parameter_version: str
    parameter_hash: str
    observations: tuple[DoubleSlopeObservation, ...]
    events: tuple[DoubleSlopeEvent, ...]
    corporate_action_status: str = "UNVERIFIED"
    investment_use: str = "PROHIBITED"
