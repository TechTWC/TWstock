from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Mapping, Sequence

from experiments.breakout_tracker_v5 import (
    BreakoutSnapshot,
    BreakoutState,
    BreakoutTracker,
    TrackerConfig,
)
from experiments.continuous_high_monitor import (
    ContinuousHighMonitor,
    HighSnapshot,
    MonitorConfig,
    MonitorResult,
)
from experiments.double_slope_turning import (
    DoubleSlopeConfig,
    DoubleSlopeResult,
    DoubleSlopeTurningEngine,
    SlopeState,
)
from experiments.moving_average_state import (
    MAStateConfig,
    MAStateResult,
    MovingAverageStateEngine,
)
from experiments.seven_state_radar import (
    RadarState,
    RadarStateConfig,
    RadarStateResult,
    SevenStateRadarEngine,
)
from twstock_data.dataset import ResearchMarketDataset
from twstock_data.errors import DataValidationError, MarketDataError
from twstock_data.normalization import stable_json_bytes, validate_date_range
from twstock_data.sources.tpex_cb import CbMarketSnapshot

from .models import (
    CandidateObservation,
    SymbolVisualization,
    TimelineEvent,
    WatchlistScan,
)


DatasetLoader = Callable[[str, str, str], ResearchMarketDataset]
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_STATE_PRIORITY = {
    RadarState.TURNING_UP.value: 0,
    RadarState.TREND_CONFIRMED.value: 1,
    RadarState.PERSISTING.value: 2,
    RadarState.BASE.value: 3,
    RadarState.EXTENDED.value: 4,
    RadarState.WEAKENING.value: 5,
    RadarState.NOISE.value: 6,
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
    ma_config: MAStateConfig | None = None,
    double_slope_config: DoubleSlopeConfig | None = None,
    radar_config: RadarStateConfig | None = None,
    cb_snapshot: CbMarketSnapshot | None = None,
    symbol_names: Mapping[str, str] | None = None,
) -> WatchlistScan:
    """Scan symbols with a seven-state MA radar and independent slope method."""

    validate_date_range(requested_start, requested_end)
    validated_symbols = _validate_symbols(symbols)
    names = _validate_symbol_names(symbol_names or {}, validated_symbols)
    monitor_config = monitor_config or MonitorConfig()
    tracker_config = tracker_config or TrackerConfig()
    ma_config = ma_config or MAStateConfig()
    double_slope_config = double_slope_config or DoubleSlopeConfig()
    radar_config = radar_config or RadarStateConfig()
    minimum_history = max(
        max(monitor_config.high_windows) + 1,
        ma_config.minimum_context_history_bars,
        double_slope_config.minimum_history_bars,
    )
    ma_engine = MovingAverageStateEngine(ma_config)
    double_slope_engine = DoubleSlopeTurningEngine(double_slope_config)
    radar_engine = SevenStateRadarEngine(radar_config)
    breakout_hash = hashlib.sha256(
        stable_json_bytes(asdict(tracker_config))
    ).hexdigest()

    candidates: list[CandidateObservation] = []
    timeline: list[TimelineEvent] = []
    datasets: list[ResearchMarketDataset] = []
    visualizations: list[SymbolVisualization] = []

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
                _with_company_name(
                    _with_cb_classification(
                        _error_candidate(
                            source_symbol,
                            minimum_history,
                            type(error).__name__,
                        ),
                        cb_snapshot,
                    ),
                    names,
                )
            )
            continue

        datasets.append(dataset)
        breakout = BreakoutTracker(tracker_config).run(dataset.bars)
        monitor = ContinuousHighMonitor(monitor_config).run(dataset.bars)
        ma_result = ma_engine.run(dataset.bars)
        double_slope_result = double_slope_engine.run(dataset.bars)
        radar_result = radar_engine.run(ma_result)
        visualizations.append(
            SymbolVisualization(
                source_symbol=source_symbol,
                breakout_snapshots=tuple(breakout),
                continuous_high_result=monitor,
                ma_state_result=ma_result,
                double_slope_result=double_slope_result,
                radar_state_result=radar_result,
                monitor_config=monitor_config,
            )
        )
        timeline.extend(_radar_events(radar_result))
        timeline.extend(_double_slope_events(double_slope_result))
        timeline.extend(_breakout_events(breakout, breakout_hash))
        timeline.extend(_continuous_high_events(monitor))
        candidate = _candidate_from_results(
            dataset,
            breakout,
            monitor,
            ma_result,
            double_slope_result,
            radar_result,
            minimum_history,
        )
        candidates.append(
            _with_company_name(
                _with_cb_classification(candidate, cb_snapshot), names
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
        ma_parameter_version=ma_config.parameter_version,
        ma_parameter_hash=ma_config.parameter_hash,
        double_slope_parameter_version=double_slope_config.parameter_version,
        double_slope_parameter_hash=double_slope_config.parameter_hash,
        radar_parameter_version=radar_config.parameter_version,
        radar_parameter_hash=radar_config.parameter_hash,
        candidates=ranked,
        timeline=ordered_timeline,
        cb_data_as_of=cb_snapshot.data_as_of if cb_snapshot else None,
        cb_source_status=(
            cb_snapshot.source_status if cb_snapshot else "UNVERIFIED"
        ),
        datasets=tuple(datasets),
        visualizations=tuple(visualizations),
    )


def _validate_symbols(symbols: Sequence[object]) -> tuple[str, ...]:
    if isinstance(symbols, (str, bytes)):
        raise DataValidationError("watchlist symbols must be a sequence")
    normalized = tuple(symbols)
    if not normalized:
        raise DataValidationError("watchlist must contain at least one symbol")
    if len(normalized) > 2000:
        raise DataValidationError("watchlist cannot exceed 2000 symbols")
    if any(not isinstance(item, str) or not _SYMBOL_RE.fullmatch(item) for item in normalized):
        raise DataValidationError("watchlist symbols must be 4-6 ASCII digits")
    if len(set(normalized)) != len(normalized):
        raise DataValidationError("watchlist contains duplicate symbols")
    return tuple(sorted(normalized))


def _validate_symbol_names(
    symbol_names: Mapping[str, str], symbols: Sequence[str]
) -> dict[str, str]:
    if not isinstance(symbol_names, Mapping):
        raise DataValidationError("symbol_names must be a mapping")
    allowed = frozenset(symbols)
    names: dict[str, str] = {}
    for symbol, name in symbol_names.items():
        if symbol not in allowed:
            raise DataValidationError("symbol_names contains an unknown symbol")
        if not isinstance(name, str) or not name.strip():
            raise DataValidationError("symbol_names values must be nonempty strings")
        names[symbol] = name.strip()
    return names


def _with_company_name(
    candidate: CandidateObservation, symbol_names: Mapping[str, str]
) -> CandidateObservation:
    return replace(
        candidate,
        company_name=symbol_names.get(candidate.source_symbol, ""),
    )


def _with_cb_classification(
    candidate: CandidateObservation,
    snapshot: CbMarketSnapshot | None,
) -> CandidateObservation:
    if snapshot is None:
        return candidate
    classification = snapshot.classify(candidate.source_symbol)
    return replace(
        candidate,
        cb_issuer_status=classification.status,
        cb_current_issue_count=classification.current_issue_count,
        cb_recent_delisted_count=classification.recent_delisted_count,
        cb_issue_names=classification.issue_names,
        cb_data_as_of=classification.data_as_of,
        cb_source_status=classification.source_status,
    )


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
    ma_result: MAStateResult,
    double_slope_result: DoubleSlopeResult,
    radar_result: RadarStateResult,
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
    latest_ma = ma_result.observations[-1]
    latest_double_slope = double_slope_result.observations[-1]
    latest_radar = radar_result.observations[-1]
    latest_radar_event = radar_result.events[-1]
    transition = (
        latest_radar_event.detail
        if latest_radar_event.trade_date == latest_date
        else ""
    )
    relationship = _method_relationship(
        latest_radar.state,
        latest_double_slope.state,
    )
    tier = f"RADAR_{latest_radar.state.value}"
    reasons = [
        f"RADAR_STATE:{latest_radar.state.value}",
        f"MA_STATE:{latest_ma.state.value}",
        f"DOUBLE_SLOPE:{latest_double_slope.state.value}",
        f"METHOD_RELATIONSHIP:{relationship}",
    ]
    if transition:
        reasons.append(f"TODAY_TRANSITION:{transition}")
    reasons.extend(f"RADAR_EVIDENCE:{item}" for item in latest_radar.evidence)
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
        company_name="",
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
        market_state=latest_radar.state.value,
        market_state_days=latest_radar.days_in_state,
        market_state_transition=transition,
        ma_state=latest_ma.state.value,
        ma_long_term_context=latest_ma.long_term_context.value,
        ma20_slope_pct=latest_ma.medium_slope_pct,
        ma60_slope_pct=latest_ma.long_slope_pct,
        distance_to_ma20_pct=latest_ma.distance_to_medium_ma_pct,
        double_slope_state=latest_double_slope.state.value,
        double_slope_prior_pct=latest_double_slope.prior_slope_pct,
        double_slope_recent_pct=latest_double_slope.recent_slope_pct,
        double_slope_z_score=latest_double_slope.z_score,
        method_relationship=relationship,
    )


def _preferred_volume_ratio(
    breakout: BreakoutSnapshot | None, high: HighSnapshot | None
) -> float | None:
    if high is not None and high.features.volume_ratio is not None:
        return high.features.volume_ratio
    return breakout.volume_ratio if breakout is not None else None


def _ranking_key(item: CandidateObservation) -> tuple[float | int | str, ...]:
    return (
        _STATE_PRIORITY[item.market_state],
        _transition_priority(item.market_state_transition),
        item.market_state_days,
        item.source_symbol,
    )


def _transition_priority(transition: str) -> int:
    research_priority = {
        "BASE->TURNING_UP",
        "TURNING_UP->TREND_CONFIRMED",
        "TREND_CONFIRMED->EXTENDED",
        "PERSISTING->EXTENDED",
        "TURNING_UP->EXTENDED",
        "TURNING_UP->WEAKENING",
        "TREND_CONFIRMED->WEAKENING",
        "PERSISTING->WEAKENING",
        "EXTENDED->WEAKENING",
    }
    if transition in research_priority:
        return 0
    if transition:
        return 1
    return 2


def _method_relationship(
    radar_state: RadarState,
    double_slope_state: SlopeState,
) -> str:
    radar_up = radar_state in {
        RadarState.TURNING_UP,
        RadarState.TREND_CONFIRMED,
        RadarState.PERSISTING,
        RadarState.EXTENDED,
    }
    slope_up = double_slope_state in {SlopeState.TURNING_UP, SlopeState.RISING}
    slope_down = double_slope_state in {SlopeState.TURNING_DOWN, SlopeState.FALLING}
    if radar_up and slope_up:
        return "ALIGNED_UP"
    if radar_state is RadarState.WEAKENING and slope_down:
        return "ALIGNED_WEAKENING"
    if radar_up and slope_down:
        return "DISAGREE_SLOPE_WEAKER"
    if radar_state is RadarState.WEAKENING and slope_up:
        return "DISAGREE_SLOPE_STRONGER"
    if double_slope_state is SlopeState.INSUFFICIENT_HISTORY:
        return "NOT_COMPARABLE"
    return "MIXED_OR_NEUTRAL"


def _error_candidate(
    source_symbol: str, minimum_history: int, error_code: str
) -> CandidateObservation:
    return CandidateObservation(
        rank=None,
        source_symbol=source_symbol,
        symbol=f"{source_symbol}.TW",
        company_name="",
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


def _radar_events(result: RadarStateResult) -> tuple[TimelineEvent, ...]:
    return tuple(
        TimelineEvent(
            event_id=event.event_id,
            symbol=event.symbol,
            trade_date=event.trade_date,
            source_engine="SEVEN_STATE_RADAR",
            event_type="STATE_CHANGED",
            detail=event.detail,
            state=event.current_state.value,
            close=event.close,
        )
        for event in result.events
    )

def _double_slope_events(result: DoubleSlopeResult) -> tuple[TimelineEvent, ...]:
    return tuple(
        TimelineEvent(
            event_id=event.event_id,
            symbol=event.symbol,
            trade_date=event.trade_date,
            source_engine="DOUBLE_SLOPE",
            event_type=f"TURNING_{event.direction}",
            detail=(
                f"prior={event.prior_slope_pct:.8f};"
                f"recent={event.recent_slope_pct:.8f};z={event.z_score:.4f}"
            ),
            state=f"TURNING_{event.direction}",
            close=event.close,
        )
        for event in result.events
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
