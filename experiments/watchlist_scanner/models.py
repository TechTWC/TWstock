from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from twstock_data.dataset import ResearchMarketDataset


@dataclass(frozen=True)
class CandidateObservation:
    rank: int | None
    source_symbol: str
    symbol: str
    scan_status: str
    candidate_tier: str
    observed_date: date | None
    close: float | None
    breakout_state: str
    breakout_reason: str
    distance_to_pivot_pct: float | None
    volume_ratio: float | None
    high_stage: str
    new_high_windows: tuple[int, ...]
    risk_flags: tuple[str, ...]
    reason_codes: tuple[str, ...]
    bar_count: int
    minimum_history_bars: int
    dataset_hash: str
    data_source_status: str = "OFFICIAL_TWSE_PRIMARY_ONLY_UNCROSSCHECKED"
    corporate_action_status: str = "UNVERIFIED"
    investment_use: str = "PROHIBITED"
    error_code: str = ""


@dataclass(frozen=True)
class TimelineEvent:
    event_id: str
    symbol: str
    trade_date: date
    source_engine: str
    event_type: str
    detail: str
    state: str
    close: float


@dataclass(frozen=True)
class WatchlistScan:
    requested_start: str
    requested_end: str
    requested_symbols: tuple[str, ...]
    as_of_trade_date: date | None
    minimum_history_bars: int
    monitor_parameter_version: str
    monitor_parameter_hash: str
    breakout_config_hash: str
    candidates: tuple[CandidateObservation, ...]
    timeline: tuple[TimelineEvent, ...]
    datasets: tuple[ResearchMarketDataset, ...] = field(
        default=(), compare=False, repr=False
    )
