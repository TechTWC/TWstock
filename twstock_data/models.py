from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class SourceTier(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"

class SourceState(str, Enum):
    PRIMARY_VERIFIED = "PRIMARY_VERIFIED"
    SECONDARY_ONLY = "SECONDARY_ONLY"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

@dataclass(frozen=True)
class MarketDataRecord:
    source: str
    source_tier: SourceTier
    source_symbol: str
    canonical_symbol: str
    market: str
    trade_date: str
    traded_share_volume: int
    official_traded_value_twd: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    transaction_count: int
    retrieved_at: str
    source_reference: str
    raw_content_hash: str

@dataclass(frozen=True)
class SourceResult:
    state: SourceState
    records: tuple[MarketDataRecord, ...] = ()
    error: str | None = None

@dataclass(frozen=True)
class ReconciliationIssue:
    trade_date: str
    field: str
    primary_value: object
    secondary_value: object

@dataclass(frozen=True)
class ReconciliationResult:
    state: SourceState
    records: tuple[MarketDataRecord, ...]
    issues: tuple[ReconciliationIssue, ...] = ()
    cross_check_unavailable: bool = False
