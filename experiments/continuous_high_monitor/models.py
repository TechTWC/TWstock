from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date
from enum import Enum
import hashlib
import json
import math
from numbers import Real
from typing import Mapping


class HighStage(str, Enum):
    WATCH = "WATCH"
    EMERGING = "EMERGING"
    STRENGTHENING = "STRENGTHENING"
    LEADER = "LEADER"
    COOLING = "COOLING"
    WEAKENING = "WEAKENING"


class RiskFlag(str, Enum):
    VOLUME_SURGE = "VOLUME_SURGE"
    ACCELERATING = "ACCELERATING"
    EXTENDED = "EXTENDED"
    PULLBACK = "PULLBACK"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"


class MonitorEventType(str, Enum):
    DISCOVERED = "DISCOVERED"
    STAGE_CHANGED = "STAGE_CHANGED"
    NEW_HIGH = "NEW_HIGH"
    RISK_ADDED = "RISK_ADDED"
    RISK_CLEARED = "RISK_CLEARED"


@dataclass(frozen=True)
class MonitorConfig:
    parameter_version: str = "CH-PARAM-001"
    high_windows: tuple[int, ...] = (20, 60, 120, 250)
    near_high_window: int = 60
    near_high_pct: float = 0.05
    base_high_window: int = 20
    strengthening_high_window: int = 60
    leader_high_window: int = 120
    high_count_window: int = 20
    strengthening_high_count: int = 3
    volume_average_window: int = 20
    volume_surge_ratio: float = 1.5
    extension_ma_window: int = 20
    extension_pct: float = 0.15
    pullback_pct: float = 0.05
    weakening_high_window: int = 60
    weakening_drawdown_pct: float = 0.12
    acceleration_window: int = 5
    acceleration_high_count: int = 3
    minimum_trading_value: float = 20_000_000.0

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_version, str) or not self.parameter_version.strip():
            raise ValueError("parameter_version must be a nonempty string")
        if not isinstance(self.high_windows, tuple):
            raise ValueError("high_windows must be a tuple")
        if len(self.high_windows) < 2:
            raise ValueError("high_windows must contain at least two windows")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in self.high_windows):
            raise ValueError("high_windows must contain integers")
        if any(value < 2 for value in self.high_windows):
            raise ValueError("high_windows values must be at least 2")
        if tuple(sorted(set(self.high_windows))) != self.high_windows:
            raise ValueError("high_windows must be unique and strictly ascending")

        integer_fields = (
            "near_high_window",
            "base_high_window",
            "strengthening_high_window",
            "leader_high_window",
            "high_count_window",
            "strengthening_high_count",
            "volume_average_window",
            "extension_ma_window",
            "weakening_high_window",
            "acceleration_window",
            "acceleration_high_count",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

        required_high_windows = {
            self.near_high_window,
            self.base_high_window,
            self.strengthening_high_window,
            self.leader_high_window,
            self.weakening_high_window,
        }
        missing = sorted(required_high_windows.difference(self.high_windows))
        if missing:
            raise ValueError(f"referenced high windows missing from high_windows: {missing}")
        if not (
            self.base_high_window
            <= self.strengthening_high_window
            <= self.leader_high_window
        ):
            raise ValueError(
                "stage high windows must satisfy base <= strengthening <= leader"
            )
        if self.strengthening_high_count > self.high_count_window:
            raise ValueError("strengthening_high_count cannot exceed high_count_window")
        if self.acceleration_high_count > self.acceleration_window:
            raise ValueError("acceleration_high_count cannot exceed acceleration_window")

        fractions = (
            "near_high_pct",
            "extension_pct",
            "pullback_pct",
            "weakening_drawdown_pct",
        )
        for name in fractions:
            value = getattr(self, name)
            self._validate_real(name, value)
            if value < 0 or value >= 1:
                raise ValueError(f"{name} must be in [0, 1)")
        if self.pullback_pct > self.weakening_drawdown_pct:
            raise ValueError("pullback_pct cannot exceed weakening_drawdown_pct")

        self._validate_real("volume_surge_ratio", self.volume_surge_ratio)
        if self.volume_surge_ratio <= 0:
            raise ValueError("volume_surge_ratio must be positive")
        self._validate_real("minimum_trading_value", self.minimum_trading_value)
        if self.minimum_trading_value < 0:
            raise ValueError("minimum_trading_value must be nonnegative")

    @staticmethod
    def _validate_real(name: str, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "MonitorConfig":
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(values).difference(allowed))
        if unknown:
            raise ValueError(f"unknown monitor config keys: {unknown}")
        normalized = dict(values)
        if "high_windows" in normalized:
            raw = normalized["high_windows"]
            if not isinstance(raw, (list, tuple)):
                raise ValueError("high_windows must be an array")
            normalized["high_windows"] = tuple(raw)
        return cls(**normalized)  # type: ignore[arg-type]

    def canonical_json(self) -> str:
        payload = asdict(self)
        payload["high_windows"] = list(self.high_windows)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @property
    def parameter_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HighFeatures:
    prior_highs: tuple[tuple[int, float], ...]
    new_high_windows: tuple[int, ...]
    distance_to_near_high_pct: float | None
    recent_high_count: int
    acceleration_high_count: int
    volume_ratio: float | None
    moving_average: float | None
    ma_extension_pct: float | None
    drawdown_from_recent_high_pct: float | None
    trading_value: float

    def prior_high(self, window: int) -> float | None:
        return dict(self.prior_highs).get(window)


@dataclass(frozen=True)
class FeatureObservation:
    symbol: str
    trade_date: date
    close: float
    features: HighFeatures


@dataclass(frozen=True)
class HighSnapshot:
    symbol: str
    trade_date: date
    close: float
    stage: HighStage
    features: HighFeatures
    risk_flags: tuple[RiskFlag, ...]


@dataclass(frozen=True)
class MonitorEvent:
    event_id: str
    symbol: str
    trade_date: date
    event_type: MonitorEventType
    detail: str
    stage: HighStage
    close: float


@dataclass(frozen=True)
class MonitorResult:
    symbol: str
    parameter_version: str
    parameter_hash: str
    first_discovery_date: date | None
    first_discovery_close: float | None
    feature_rows: tuple[FeatureObservation, ...]
    snapshots: tuple[HighSnapshot, ...]
    events: tuple[MonitorEvent, ...]
