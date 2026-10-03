from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from experiments.breakout_tracker_v5 import BreakoutSnapshot
from experiments.continuous_high_monitor import MonitorConfig, MonitorResult
from experiments.double_slope_turning import DoubleSlopeResult
from experiments.moving_average_state import MAStateResult
from experiments.seven_state_radar import RadarStateResult
from twstock_data.dataset import ResearchMarketDataset


@dataclass(frozen=True)
class CandidateObservation:
    rank: int | None
    source_symbol: str
    symbol: str
    company_name: str
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
    market_state: str = "NOISE"
    market_state_days: int = 0
    market_state_transition: str = ""
    ma_state: str = "UNCLEAR"
    ma_long_term_context: str = "INSUFFICIENT_HISTORY"
    ma20_slope_pct: float | None = None
    ma60_slope_pct: float | None = None
    distance_to_ma20_pct: float | None = None
    double_slope_state: str = "INSUFFICIENT_HISTORY"
    double_slope_prior_pct: float | None = None
    double_slope_recent_pct: float | None = None
    double_slope_z_score: float | None = None
    method_relationship: str = "NOT_COMPARABLE"
    cb_issuer_status: str = "UNVERIFIED"
    cb_current_issue_count: int = 0
    cb_recent_delisted_count: int = 0
    cb_issue_names: tuple[str, ...] = ()
    cb_data_as_of: date | None = None
    cb_source_status: str = "UNVERIFIED"
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
class SymbolVisualization:
    """Exact engine results retained for the standalone visual report."""

    source_symbol: str
    breakout_snapshots: tuple[BreakoutSnapshot, ...]
    continuous_high_result: MonitorResult
    ma_state_result: MAStateResult
    double_slope_result: DoubleSlopeResult
    radar_state_result: RadarStateResult
    monitor_config: MonitorConfig = field(compare=False, repr=False)


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
    ma_parameter_version: str
    ma_parameter_hash: str
    double_slope_parameter_version: str
    double_slope_parameter_hash: str
    radar_parameter_version: str
    radar_parameter_hash: str
    candidates: tuple[CandidateObservation, ...]
    timeline: tuple[TimelineEvent, ...]
    cb_data_as_of: date | None = None
    cb_source_status: str = "UNVERIFIED"
    datasets: tuple[ResearchMarketDataset, ...] = field(
        default=(), compare=False, repr=False
    )
    visualizations: tuple[SymbolVisualization, ...] = field(
        default=(), compare=False, repr=False
    )
