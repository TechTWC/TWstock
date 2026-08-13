from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Sequence

from experiments.breakout_tracker_v5 import (
    BreakoutSnapshot,
    BreakoutState,
    BreakoutTracker,
    TrackerConfig,
)
from experiments.continuous_high_monitor import (
    ContinuousHighMonitor,
    HighSnapshot,
    HighStage,
    MonitorConfig,
    MonitorResult,
)
from twstock_data.dataset import ResearchMarketDataset
from twstock_data.errors import DataValidationError, MarketDataError
from twstock_data.normalization import stable_json_bytes, validate_date_range

from .models import CandidateObservation, TimelineEvent, WatchlistScan


DatasetLoader = Callable[[str, str, str], ResearchMarketDataset]
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_TIER_PRIORITY = {
    "DUAL_TRIGGER": 0,
    "BREAKOUT_TRIGGER": 1,
    "EARLY_HIGH": 2,
    "STRENGTHENING": 3,
    "NEW_HIGH": 4,
    "RETEST": 5,
    "LEADER": 6,
    "SETUP": 7,
    "CONFIRMED": 8,
    "WATCH": 9,
    "EXTENDED": 10,
    "COOLING": 11,
    "WEAKENING": 12,
    "INACTIVE": 13,
    "UNAVAILABLE": 99,
}


def load_watchlist(path: Path) -> tuple[str, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DataValidationError(f"watchlist not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DataValidationError("watchlist is not valid JSON") from error
    if not isinstance(payload, dict):
        raise DataValidationError("watchlist root must be an object")
    if set(payload) != {"schema_version", "symbols"}:
        raise DataValidationError(
            "watchlist fields must be exactly schema_version and symbols"
        )
    if payload["schema_version"] != "TWSTOCK-WATCHLIST-001":
        raise DataValidationError("unsupported watchlist schema_version")
    symbols = payload["symbols"]
    if not isinstance(symbols, list):
        raise DataValidationError("watchlist symbols must be an array")
    return _validate_symbols(symbols)


def scan_watchlist(
    symbols: Sequence[str],
    requested_start: str,
    requested_end: str,
    *,
    dataset_loader: DatasetLoader,
    monitor_config: MonitorConfig | None = None,
    tracker_config: TrackerConfig | None = None,
) -> WatchlistScan:
    """Scan independent symbols and produce deterministic, non-advisory ranks."""

    validate_date_range(requested_start, requested_end)
    validated_symbols = _validate_symbols(symbols)
    monitor_config = monitor_config or MonitorConfig()
    tracker_config = tracker_config or TrackerConfig()
    minimum_history = max(monitor_config.high_windows) + 1
    breakout_hash = hashlib.sha256(
        stable_json_bytes(asdict(tracker_config))
    ).hexdigest()

    candidates: list[CandidateObservation] = []
    timeline: list[TimelineEvent] = []
    datasets: list[ResearchMarketDataset] = []

    for source_symbol in validated_symbols:
        try:
            dataset = dataset_loader(
                source_symbol, requested_start, requested_end
            )
            _validate_dataset_identity(
                dataset,
                source_symbol,
                requested_start,
                requested_end,
            )
        except MarketDataError as error:
            candidates.append(
                _error_candidate(
                    source_symbol,
                    minimum_history,
                    type(error).__name__,
                )
            )
            continue

        datasets.append(dataset)
        breakout = BreakoutTracker(tracker_config).run(dataset.bars)
        monitor = ContinuousHighMonitor(monitor_config).run(dataset.bars)
        timeline.extend(_breakout_events(breakout, breakout_hash))
        timeline.extend(_continuous_high_events(monitor))
        candidates.append(
            _candidate_from_results(
                dataset,
                breakout,
                monitor,
                minimum_history,
            )
        )

    as_of = max(
        (
            item.observed_date
            for item in candidates
            if item.observed_date is not None
        ),
        default=None,
    )
    comparable: list[CandidateObservation] = []
    for item in candidates:
        if (
            item.scan_status == "OK"
            and as_of is not None
            and item.observed_date != as_of
        ):
            comparable.append(
                replace(
                    item,
                    scan_status="STALE_DATA",
                    reason_codes=(
                        *item.reason_codes,
                        f"STALE_VS_SCAN_AS_OF:{as_of.isoformat()}",
                    ),
                )
            )
        else:
            comparable.append(item)

    rankable = sorted(
        (item for item in comparable if item.scan_status == "OK"),
        key=_ranking_key,
    )
    rank_by_symbol = {
        item.source_symbol: rank for rank, item in enumerate(rankable, 1)
    }
    ranked = tuple(
        sorted(
            (
                replace(item, rank=rank_by_symbol.get(item.source_symbol))
                for item in comparable
            ),
            key=lambda item: (
                item.rank is None,
                item.rank if item.rank is not None else 10**9,
                item.source_symbol,
            ),
        )
    )
    ordered_timeline = tuple(
        sorted(
            timeline,
            key=lambda event: (
                event.trade_date,
                event.symbol,
                event.source_engine,
                event.event_type,
                event.event_id,
            ),
        )
    )
    return WatchlistScan(
        requested_start=requested_start,
        requested_end=requested_end,
        requested_symbols=validated_symbols,
        as_of_trade_date=as_of,
        minimum_history_bars=minimum_history,
        monitor_parameter_version=monitor_config.parameter_version,
        monitor_parameter_hash=monitor_config.parameter_hash,
        breakout_config_hash=breakout_hash,
        candidates=ranked,
        timeline=ordered_timeline,
        datasets=tuple(datasets),
    )


def _validate_symbols(symbols: Sequence[object]) -> tuple[str, ...]:
    if isinstance(symbols, (str, bytes)):
        raise DataValidationError("watchlist symbols must be a sequence")
    normalized = tuple(symbols)
    if not normalized:
        raise DataValidationError("watchlist must contain at least one symbol")
    if len(normalized) > 100:
        raise DataValidationError("watchlist cannot exceed 100 symbols")
    if any(not isinstance(item, str) or not _SYMBOL_RE.fullmatch(item) for item in normalized):
        raise DataValidationError("watchlist symbols must be 4-6 ASCII digits")
    if len(set(normalized)) != len(normalized):
        raise DataValidationError("watchlist contains duplicate symbols")
    return tuple(sorted(normalized))


def _validate_dataset_identity(
    dataset: ResearchMarketDataset,
    source_symbol: str,
    requested_start: str,
    requested_end: str,
) -> None:
    dataset.manifest()
    if dataset.source_symbol != source_symbol:
        raise DataValidationError("dataset source symbol does not match watchlist")
    if (
        dataset.requested_start != requested_start
        or dataset.requested_end != requested_end
    ):
        raise DataValidationError("dataset date range does not match scan request")
    if dataset.selected_source != "TWSE":
        raise DataValidationError("watchlist scanner accepts TWSE datasets only")
    if dataset.price_basis != "RAW_OFFICIAL_DAILY":
        raise DataValidationError("watchlist scanner requires official raw daily prices")
    if not dataset.cross_check_unavailable:
        raise DataValidationError(
            "official-only scan must remain explicitly uncross-checked"
        )


def _candidate_from_results(
    dataset: ResearchMarketDataset,
    breakout: Sequence[BreakoutSnapshot],
    monitor: MonitorResult,
    minimum_history: int,
) -> CandidateObservation:
    latest_date = dataset.bars[-1].trade_date
    latest_breakout = breakout[-1] if breakout and breakout[-1].trade_date == latest_date else None
    latest_feature = monitor.feature_rows[-1]
    latest_high = (
        monitor.snapshots[-1]
        if monitor.snapshots and monitor.snapshots[-1].trade_date == latest_date
        else None
    )
    tier = _candidate_tier(latest_breakout, latest_high, latest_feature.features.new_high_windows)
    reasons = [f"TIER:{tier}"]
    if latest_breakout is not None:
        reasons.append(f"BREAKOUT:{latest_breakout.state.value}")
        reasons.append(f"BREAKOUT_REASON:{latest_breakout.reason}")
    if latest_high is not None:
        reasons.append(f"HIGH_STAGE:{latest_high.stage.value}")
    if latest_feature.features.new_high_windows:
        windows = ",".join(str(item) for item in latest_feature.features.new_high_windows)
        reasons.append(f"NEW_HIGH_WINDOWS:{windows}")
    for risk in latest_high.risk_flags if latest_high is not None else ():
        reasons.append(f"RISK:{risk.value}")
    reasons.append("CORPORATE_ACTION:UNVERIFIED")

    sufficient = len(dataset.bars) >= minimum_history
    if not sufficient:
        reasons.append(
            f"INSUFFICIENT_HISTORY:{len(dataset.bars)}<{minimum_history}"
        )
    return CandidateObservation(
        rank=None,
        source_symbol=dataset.source_symbol,
        symbol=dataset.canonical_symbol,
        scan_status="OK" if sufficient else "INSUFFICIENT_HISTORY",
        candidate_tier=tier,
        observed_date=latest_date,
        close=dataset.bars[-1].close,
        breakout_state=(
            latest_breakout.state.value if latest_breakout is not None else "NONE"
        ),
        breakout_reason=(latest_breakout.reason if latest_breakout is not None else ""),
        distance_to_pivot_pct=(
            latest_breakout.distance_to_pivot_pct
            if latest_breakout is not None
            else None
        ),
        volume_ratio=_preferred_volume_ratio(latest_breakout, latest_high),
        high_stage=(latest_high.stage.value if latest_high is not None else "NONE"),
        new_high_windows=latest_feature.features.new_high_windows,
        risk_flags=tuple(
            risk.value for risk in latest_high.risk_flags
        ) if latest_high is not None else (),
        reason_codes=tuple(reasons),
        bar_count=len(dataset.bars),
        minimum_history_bars=minimum_history,
        dataset_hash=dataset.dataset_hash,
    )


def _candidate_tier(
    breakout: BreakoutSnapshot | None,
    high: HighSnapshot | None,
    new_high_windows: Sequence[int],
) -> str:
    breakout_state = breakout.state if breakout is not None else None
    stage = high.stage if high is not None else None
    has_new_high = bool(new_high_windows)
    if breakout_state is BreakoutState.NEW_TRIGGER and has_new_high:
        return "DUAL_TRIGGER"
    if breakout_state is BreakoutState.NEW_TRIGGER:
        return "BREAKOUT_TRIGGER"
    if stage is HighStage.EMERGING and has_new_high:
        return "EARLY_HIGH"
    if stage is HighStage.STRENGTHENING:
        return "STRENGTHENING"
    if has_new_high:
        return "NEW_HIGH"
    if breakout_state is BreakoutState.RETEST:
        return "RETEST"
    if stage is HighStage.LEADER:
        return "LEADER"
    if breakout_state is BreakoutState.SETUP:
        return "SETUP"
    if breakout_state is BreakoutState.CONFIRMED:
        return "CONFIRMED"
    if stage is HighStage.WATCH:
        return "WATCH"
    if breakout_state is BreakoutState.EXTENDED:
        return "EXTENDED"
    if stage is HighStage.COOLING:
        return "COOLING"
    if stage is HighStage.WEAKENING:
        return "WEAKENING"
    return "INACTIVE"


def _preferred_volume_ratio(
    breakout: BreakoutSnapshot | None, high: HighSnapshot | None
) -> float | None:
    if high is not None and high.features.volume_ratio is not None:
        return high.features.volume_ratio
    return breakout.volume_ratio if breakout is not None else None


def _ranking_key(item: CandidateObservation) -> tuple[float | int | str, ...]:
    volume = item.volume_ratio if item.volume_ratio is not None else -1.0
    distance = (
        abs(item.distance_to_pivot_pct)
        if item.distance_to_pivot_pct is not None
        else float("inf")
    )
    return (
        _TIER_PRIORITY[item.candidate_tier],
        -volume,
        distance,
        item.source_symbol,
    )


def _error_candidate(
    source_symbol: str, minimum_history: int, error_code: str
) -> CandidateObservation:
    return CandidateObservation(
        rank=None,
        source_symbol=source_symbol,
        symbol=f"{source_symbol}.TW",
        scan_status="DATA_UNAVAILABLE",
        candidate_tier="UNAVAILABLE",
        observed_date=None,
        close=None,
        breakout_state="NONE",
        breakout_reason="",
        distance_to_pivot_pct=None,
        volume_ratio=None,
        high_stage="NONE",
        new_high_windows=(),
        risk_flags=(),
        reason_codes=(f"DATA_ERROR:{error_code}", "CORPORATE_ACTION:UNVERIFIED"),
        bar_count=0,
        minimum_history_bars=minimum_history,
        dataset_hash="",
        error_code=error_code,
    )


def _breakout_events(
    snapshots: Sequence[BreakoutSnapshot], config_hash: str
) -> tuple[TimelineEvent, ...]:
    events: list[TimelineEvent] = []
    previous_state: BreakoutState | None = None
    for snapshot in snapshots:
        if snapshot.state is previous_state:
            continue
        detail = (
            snapshot.state.value
            if previous_state is None
            else f"{previous_state.value}->{snapshot.state.value}"
        )
        identity = "|".join(
            (
                "BREAKOUT_TRACKER_V5",
                config_hash,
                snapshot.symbol,
                snapshot.trade_date.isoformat(),
                "STATE_CHANGED",
                detail,
                snapshot.reason,
            )
        )
        events.append(
            TimelineEvent(
                event_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
                symbol=snapshot.symbol,
                trade_date=snapshot.trade_date,
                source_engine="BREAKOUT_TRACKER_V5",
                event_type="STATE_CHANGED",
                detail=f"{detail};{snapshot.reason}",
                state=snapshot.state.value,
                close=snapshot.close,
            )
        )
        previous_state = snapshot.state
    return tuple(events)


def _continuous_high_events(result: MonitorResult) -> tuple[TimelineEvent, ...]:
    return tuple(
        TimelineEvent(
            event_id=event.event_id,
            symbol=event.symbol,
            trade_date=event.trade_date,
            source_engine="CONTINUOUS_HIGH",
            event_type=event.event_type.value,
            detail=event.detail,
            state=event.stage.value,
            close=event.close,
        )
        for event in result.events
    )
