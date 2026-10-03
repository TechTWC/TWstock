from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import math
from numbers import Real

from experiments.moving_average_state import TrendState


class RadarState(str, Enum):
    NOISE = "NOISE"
    BASE = "BASE"
    TURNING_UP = "TURNING_UP"
    TREND_CONFIRMED = "TREND_CONFIRMED"
    PERSISTING = "PERSISTING"
    EXTENDED = "EXTENDED"
    WEAKENING = "WEAKENING"


@dataclass(frozen=True)
class RadarStateConfig:
    parameter_version: str = "SEVEN-STATE-PARAM-001"
    persistence_bars: int = 10
    extended_distance_to_ma20_pct: float = 0.12

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_version, str) or not self.parameter_version.strip():
            raise ValueError("parameter_version must be a nonempty string")
        if isinstance(self.persistence_bars, bool) or not isinstance(self.persistence_bars, int):
            raise ValueError("persistence_bars must be an integer")
        if self.persistence_bars < 2:
            raise ValueError("persistence_bars must be at least 2")
        value = self.extended_distance_to_ma20_pct
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError("extended_distance_to_ma20_pct must be finite")
        if value <= 0 or value >= 1:
            raise ValueError("extended_distance_to_ma20_pct must be in (0, 1)")

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
class RadarStateObservation:
    symbol: str
    trade_date: date
    close: float
    state: RadarState
    days_in_state: int
    ma_state: TrendState
    consecutive_confirmed_bars: int
    distance_to_ma20_pct: float | None
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RadarStateEvent:
    event_id: str
    symbol: str
    trade_date: date
    previous_state: RadarState | None
    current_state: RadarState
    close: float
    detail: str


@dataclass(frozen=True)
class RadarStateResult:
    symbol: str
    parameter_version: str
    parameter_hash: str
    ma_parameter_hash: str
    observations: tuple[RadarStateObservation, ...]
    events: tuple[RadarStateEvent, ...]
    corporate_action_status: str = "UNVERIFIED"
    investment_use: str = "PROHIBITED"
