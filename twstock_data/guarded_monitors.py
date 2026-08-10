from __future__ import annotations

from typing import Sequence

from experiments.breakout_tracker_v5 import (
    BreakoutSnapshot,
    BreakoutTracker,
    TrackerConfig,
)
from experiments.continuous_high_monitor import (
    ContinuousHighMonitor,
    MonitorConfig,
    MonitorResult,
)

from .corporate_actions import (
    AnalysisGuardDecision,
    AnalysisGuardState,
    CorporateActionEvent,
    build_analysis_guard_decisions,
    clean_bar_segments,
)
from .models import MarketBar


CONTINUOUS_HIGH_ANALYZER = "CONTINUOUS_HIGH"
BREAKOUT_TRACKER_ANALYZER = "BREAKOUT_TRACKER"


def continuous_high_required_clean_bars(config: MonitorConfig) -> int:
    # Reopen the first valid short-window observation. Longer windows remain
    # unavailable inside the engine until their own history is complete.
    return min(config.high_windows) + 1


def breakout_required_clean_bars(config: TrackerConfig) -> int:
    return max(
        config.pivot_lookback + config.pivot_confirmation_bars,
        config.volume_lookback + 1,
    )


def run_guarded_continuous_high(
    bars: Sequence[MarketBar],
    events: Sequence[CorporateActionEvent],
    config: MonitorConfig,
) -> tuple[MonitorResult, tuple[AnalysisGuardDecision, ...]]:
    decisions = build_analysis_guard_decisions(
        bars,
        events,
        analyzer=CONTINUOUS_HIGH_ANALYZER,
        required_clean_bars=continuous_high_required_clean_bars(config),
    )
    monitor = ContinuousHighMonitor(config)
    if not events:
        return monitor.run(bars), decisions

    allowed_dates = {
        item.trade_date
        for item in decisions
        if item.state is AnalysisGuardState.ALLOWED
    }
    feature_rows = []
    snapshots = []
    emitted_events = []
    for segment in clean_bar_segments(bars, events):
        result = monitor.run(segment)
        feature_rows.extend(
            item for item in result.feature_rows if item.trade_date in allowed_dates
        )
        snapshots.extend(
            item for item in result.snapshots if item.trade_date in allowed_dates
        )
        emitted_events.extend(
            item for item in result.events if item.trade_date in allowed_dates
        )

    first = snapshots[0] if snapshots else None
    return (
        MonitorResult(
            symbol=bars[0].symbol if bars else "",
            parameter_version=config.parameter_version,
            parameter_hash=config.parameter_hash,
            first_discovery_date=first.trade_date if first else None,
            first_discovery_close=first.close if first else None,
            feature_rows=tuple(feature_rows),
            snapshots=tuple(snapshots),
            events=tuple(emitted_events),
        ),
        decisions,
    )


def run_guarded_breakout_tracker(
    bars: Sequence[MarketBar],
    events: Sequence[CorporateActionEvent],
    config: TrackerConfig,
) -> tuple[tuple[BreakoutSnapshot, ...], tuple[AnalysisGuardDecision, ...]]:
    decisions = build_analysis_guard_decisions(
        bars,
        events,
        analyzer=BREAKOUT_TRACKER_ANALYZER,
        required_clean_bars=breakout_required_clean_bars(config),
    )
    tracker = BreakoutTracker(config)
    if not events:
        return tracker.run(bars), decisions

    allowed_dates = {
        item.trade_date
        for item in decisions
        if item.state is AnalysisGuardState.ALLOWED
    }
    snapshots: list[BreakoutSnapshot] = []
    for segment in clean_bar_segments(bars, events):
        snapshots.extend(
            item
            for item in tracker.run(segment)
            if item.trade_date in allowed_dates
        )
    return tuple(snapshots), decisions
