from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class QualityState(str, Enum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class FundamentalState(str, Enum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DETERIORATING = "DETERIORATING"
    UNKNOWN = "UNKNOWN"


class StateDetail(str, Enum):
    DETERIORATING = "DETERIORATING"
    BOTTOMING = "BOTTOMING"
    TURNING_UP = "TURNING_UP"
    CONFIRMED_GROWTH = "CONFIRMED_GROWTH"
    MATURE_GROWTH = "MATURE_GROWTH"
    DECELERATING = "DECELERATING"
    UNKNOWN = "UNKNOWN"


class ValuationState(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    NOT_MEANINGFUL = "N/M"


class DataQuality(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class SectorLogic(str, Enum):
    GENERAL = "GENERAL"
    FINANCIAL = "FINANCIAL"
    CYCLICAL = "CYCLICAL"


@dataclass(frozen=True)
class PITMetadata:
    period_end: str
    announcement_date: str | None
    available_date: str
    as_of_date: str
    source: str
    retrieval_date: str | None
    source_version: str | None
    source_hash: str | None
    availability_method: str
    timestamp_confidence: str


@dataclass
class SecurityData:
    symbol: str
    company: str
    industry: str
    sector_logic: SectorLogic
    quarterly: Any
    market: Any
    peer_group: str = "UNCLASSIFIED"
    financial_subtype: str | None = None
    source: str = "FinMind v4 (TWSE/MOPS-derived vendor dataset)"
    source_metadata: dict[str, Any] = field(default_factory=dict)
    data_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClassificationResult:
    symbol: str
    company: str
    industry: str
    sector_logic: str
    peer_group: str
    financial_subtype: str | None
    as_of_date: str
    period_end: str | None
    quality: str
    fundamental_state: str
    state_detail: str
    valuation: str
    research_classification: str
    data_quality: str
    quality_reasons: tuple[str, ...]
    fundamental_reasons: tuple[str, ...]
    valuation_reasons: tuple[str, ...]
    reason_codes: tuple[str, ...]
    data_quality_flags: tuple[str, ...]
    metrics: dict[str, float | str | None]
    intrinsic_value: dict[str, float | None]
    pit_metadata: PITMetadata | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["quality_reasons"] = list(self.quality_reasons)
        result["fundamental_reasons"] = list(self.fundamental_reasons)
        result["valuation_reasons"] = list(self.valuation_reasons)
        result["reason_codes"] = list(self.reason_codes)
        result["data_quality_flags"] = list(self.data_quality_flags)
        return result
