from __future__ import annotations

import hashlib

from experiments.moving_average_state import MAStateObservation, MAStateResult, TrendState

from .models import (
    RadarState,
    RadarStateConfig,
    RadarStateEvent,
    RadarStateObservation,
    RadarStateResult,
)


_UP_STATES = {
    RadarState.TURNING_UP,
    RadarState.TREND_CONFIRMED,
    RadarState.PERSISTING,
    RadarState.EXTENDED,
}


class SevenStateRadarEngine:
    """Translate the transparent MA baseline into seven research states."""

    def __init__(self, config: RadarStateConfig | None = None) -> None:
        self.config = config or RadarStateConfig()

    def run(self, ma_result: MAStateResult) -> RadarStateResult:
        if not ma_result.observations:
            raise ValueError("ma_result must contain observations")
        observations: list[RadarStateObservation] = []
        events: list[RadarStateEvent] = []
        previous_state: RadarState | None = None
        days_in_state = 0
        consecutive_confirmed_bars = 0
        confirmation_active = False
        for ma_observation in ma_result.observations:
            if ma_observation.state is TrendState.UPTREND:
                consecutive_confirmed_bars = (
                    consecutive_confirmed_bars + 1 if confirmation_active else 1
                )
                confirmation_active = True
            elif confirmation_active and ma_observation.state is TrendState.TURNING_UP:
                consecutive_confirmed_bars += 1
            else:
                consecutive_confirmed_bars = 0
                confirmation_active = False
            state, evidence, limitations = self._classify(
                ma_observation,
                previous_state,
                consecutive_confirmed_bars,
            )
            days_in_state = days_in_state + 1 if state is previous_state else 1
            observation = RadarStateObservation(
                symbol=ma_observation.symbol,
                trade_date=ma_observation.trade_date,
                close=ma_observation.close,
                state=state,
                days_in_state=days_in_state,
                ma_state=ma_observation.state,
                consecutive_confirmed_bars=consecutive_confirmed_bars,
                distance_to_ma20_pct=ma_observation.distance_to_medium_ma_pct,
                evidence=evidence,
                limitations=limitations,
            )
            observations.append(observation)
            if state is not previous_state:
                events.append(self._event(observation, previous_state))
                previous_state = state
        return RadarStateResult(
            symbol=ma_result.symbol,
            parameter_version=self.config.parameter_version,
            parameter_hash=self.config.parameter_hash,
            ma_parameter_hash=ma_result.parameter_hash,
            observations=tuple(observations),
            events=tuple(events),
        )

    def _classify(
        self,
        observation: MAStateObservation,
        previous_state: RadarState | None,
        consecutive_confirmed_bars: int,
    ) -> tuple[RadarState, tuple[str, ...], tuple[str, ...]]:
        ma_state = observation.state
        distance = observation.distance_to_medium_ma_pct
        limitations = (
            "MA_BASELINE_ONLY",
            "THRESHOLDS_NOT_YET_CALIBRATED_ON_TAIWAN_EQUITIES",
            "CORPORATE_ACTION_UNVERIFIED",
        )
        if ma_state in (TrendState.TURNING_DOWN, TrendState.DOWNTREND):
            return (
                RadarState.WEAKENING,
                (f"MA_STATE:{ma_state.value}", "SHORT_OR_MEDIUM_TREND_DAMAGED"),
                limitations,
            )
        if ma_state is TrendState.UPTREND:
            if distance is not None and distance >= self.config.extended_distance_to_ma20_pct:
                return (
                    RadarState.EXTENDED,
                    (
                        "FULL_BULLISH_ALIGNMENT",
                        f"DISTANCE_TO_MA20_GE:{self.config.extended_distance_to_ma20_pct:.4f}",
                    ),
                    limitations,
                )
            if consecutive_confirmed_bars >= self.config.persistence_bars:
                return (
                    RadarState.PERSISTING,
                    (
                        "FULL_BULLISH_ALIGNMENT",
                        f"CONFIRMED_ALIGNMENT_BARS_GE:{self.config.persistence_bars}",
                    ),
                    limitations,
                )
            return (
                RadarState.TREND_CONFIRMED,
                (
                    "FULL_BULLISH_ALIGNMENT",
                    f"CONFIRMED_ALIGNMENT_BARS:{consecutive_confirmed_bars}",
                ),
                limitations,
            )
        if ma_state is TrendState.TURNING_UP:
            if distance is not None and distance >= self.config.extended_distance_to_ma20_pct:
                return (
                    RadarState.EXTENDED,
                    (
                        "EARLY_UP_CONFIGURATION",
                        f"DISTANCE_TO_MA20_GE:{self.config.extended_distance_to_ma20_pct:.4f}",
                    ),
                    limitations,
                )
            if consecutive_confirmed_bars >= self.config.persistence_bars:
                return (
                    RadarState.PERSISTING,
                    (
                        "PREVIOUSLY_CONFIRMED_UPTREND_REMAINS_BULLISH",
                        f"CONFIRMED_TREND_AGE_BARS_GE:{self.config.persistence_bars}",
                    ),
                    limitations,
                )
            return (
                RadarState.TURNING_UP,
                ("CLOSE_ABOVE_MA20", "MA5_ABOVE_MA10", "MA20_SLOPE_POSITIVE"),
                limitations,
            )
        if ma_state is TrendState.BASE:
            return (
                RadarState.BASE,
                ("MA20_AND_MA60_APPROXIMATELY_FLAT", "MOVING_AVERAGES_COMPRESSED"),
                limitations,
            )
        if previous_state in _UP_STATES:
            return (
                RadarState.WEAKENING,
                ("PREVIOUSLY_BULLISH_STATE", "CURRENT_MA_SIGNALS_NO_LONGER_BULLISH"),
                limitations,
            )
        return (
            RadarState.NOISE,
            (f"MA_STATE:{ma_state.value}", "NO_DOMINANT_DIRECTIONAL_STRUCTURE"),
            limitations,
        )

    def _event(
        self,
        observation: RadarStateObservation,
        previous_state: RadarState | None,
    ) -> RadarStateEvent:
        previous = previous_state.value if previous_state else "NONE"
        detail = f"{previous}->{observation.state.value}"
        identity = "|".join(
            (
                "SEVEN_STATE_RADAR",
                self.config.parameter_hash,
                observation.symbol,
                observation.trade_date.isoformat(),
                detail,
            )
        )
        return RadarStateEvent(
            event_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            symbol=observation.symbol,
            trade_date=observation.trade_date,
            previous_state=previous_state,
            current_state=observation.state,
            close=observation.close,
            detail=detail,
        )
