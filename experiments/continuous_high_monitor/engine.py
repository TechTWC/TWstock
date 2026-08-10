from __future__ import annotations

from datetime import date
import hashlib
import math
from numbers import Real
from typing import Sequence

from experiments.breakout_tracker_v5 import PriceBar

from .models import (
    FeatureObservation,
    HighFeatures,
    HighSnapshot,
    HighStage,
    MonitorConfig,
    MonitorEvent,
    MonitorEventType,
    MonitorResult,
    RiskFlag,
)


class ContinuousHighMonitor:
    """Replay one symbol using only observations available on each date."""

    def __init__(self, config: MonitorConfig | None = None) -> None:
        self.config = config or MonitorConfig()

    def run(self, bars: Sequence[PriceBar]) -> MonitorResult:
        self._validate_bars(bars)
        if not bars:
            return MonitorResult(
                symbol="",
                parameter_version=self.config.parameter_version,
                parameter_hash=self.config.parameter_hash,
                first_discovery_date=None,
                first_discovery_close=None,
                feature_rows=(),
                snapshots=(),
                events=(),
            )

        feature_rows: list[FeatureObservation] = []
        snapshots: list[HighSnapshot] = []
        events: list[MonitorEvent] = []
        base_high_occurrences: list[bool] = []
        previous_stage: HighStage | None = None
        previous_risks: tuple[RiskFlag, ...] = ()
        discovered = False

        for index, bar in enumerate(bars):
            prior_highs = self._prior_highs(index, bars)
            new_high_windows = tuple(
                window
                for window, prior_high in prior_highs
                if bar.close > prior_high
            )
            base_high_occurrences.append(
                self.config.base_high_window in new_high_windows
            )
            features = self._features(
                index=index,
                bars=bars,
                prior_highs=prior_highs,
                new_high_windows=new_high_windows,
                base_high_occurrences=base_high_occurrences,
            )
            feature_rows.append(
                FeatureObservation(
                    symbol=bar.symbol,
                    trade_date=bar.trade_date,
                    close=bar.close,
                    features=features,
                )
            )
            stage = self._stage(features, discovered, previous_stage)
            if stage is None:
                continue

            risks = self._risks(features)
            snapshot = HighSnapshot(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                close=bar.close,
                stage=stage,
                features=features,
                risk_flags=risks,
            )
            snapshots.append(snapshot)

            if not discovered:
                discovered = True
                events.append(self._event(snapshot, MonitorEventType.DISCOVERED, stage.value))
            elif stage is not previous_stage:
                assert previous_stage is not None
                events.append(
                    self._event(
                        snapshot,
                        MonitorEventType.STAGE_CHANGED,
                        f"{previous_stage.value}->{stage.value}",
                    )
                )

            for window in new_high_windows:
                events.append(
                    self._event(snapshot, MonitorEventType.NEW_HIGH, f"{window}D_CLOSE_HIGH")
                )

            added = set(risks).difference(previous_risks)
            cleared = set(previous_risks).difference(risks)
            for risk in sorted(added, key=lambda item: item.value):
                events.append(self._event(snapshot, MonitorEventType.RISK_ADDED, risk.value))
            for risk in sorted(cleared, key=lambda item: item.value):
                events.append(self._event(snapshot, MonitorEventType.RISK_CLEARED, risk.value))

            previous_stage = stage
            previous_risks = risks

        first = snapshots[0] if snapshots else None
        return MonitorResult(
            symbol=bars[0].symbol,
            parameter_version=self.config.parameter_version,
            parameter_hash=self.config.parameter_hash,
            first_discovery_date=first.trade_date if first else None,
            first_discovery_close=first.close if first else None,
            feature_rows=tuple(feature_rows),
            snapshots=tuple(snapshots),
            events=tuple(events),
        )

    def _prior_highs(
        self, index: int, bars: Sequence[PriceBar]
    ) -> tuple[tuple[int, float], ...]:
        output: list[tuple[int, float]] = []
        for window in self.config.high_windows:
            if index >= window:
                output.append(
                    (window, max(item.close for item in bars[index - window : index]))
                )
        return tuple(output)

    def _features(
        self,
        *,
        index: int,
        bars: Sequence[PriceBar],
        prior_highs: tuple[tuple[int, float], ...],
        new_high_windows: tuple[int, ...],
        base_high_occurrences: Sequence[bool],
    ) -> HighFeatures:
        bar = bars[index]
        high_map = dict(prior_highs)
        near_high = high_map.get(self.config.near_high_window)
        distance = None if near_high is None else (bar.close / near_high) - 1

        recent_start = max(0, len(base_high_occurrences) - self.config.high_count_window)
        acceleration_start = max(
            0, len(base_high_occurrences) - self.config.acceleration_window
        )
        recent_count = sum(base_high_occurrences[recent_start:])
        acceleration_count = sum(base_high_occurrences[acceleration_start:])

        volume_ratio = self._prior_average_ratio(
            index, bars, self.config.volume_average_window, attribute="volume"
        )
        moving_average = None
        if index + 1 >= self.config.extension_ma_window:
            selected = bars[index - self.config.extension_ma_window + 1 : index + 1]
            moving_average = sum(item.close for item in selected) / len(selected)
        extension = None if moving_average is None else (bar.close / moving_average) - 1

        recent_high = high_map.get(self.config.weakening_high_window)
        drawdown = None if recent_high is None else (bar.close / recent_high) - 1

        return HighFeatures(
            prior_highs=prior_highs,
            new_high_windows=new_high_windows,
            distance_to_near_high_pct=distance,
            recent_high_count=recent_count,
            acceleration_high_count=acceleration_count,
            volume_ratio=volume_ratio,
            moving_average=moving_average,
            ma_extension_pct=extension,
            drawdown_from_recent_high_pct=drawdown,
            trading_value=(
                bar.official_traded_value_twd
                if bar.official_traded_value_twd is not None
                else bar.close * bar.volume
            ),
        )

    def _stage(
        self,
        features: HighFeatures,
        discovered: bool,
        previous_stage: HighStage | None,
    ) -> HighStage | None:
        drawdown = features.drawdown_from_recent_high_pct
        if (
            discovered
            and drawdown is not None
            and drawdown <= -self.config.weakening_drawdown_pct
        ):
            return HighStage.WEAKENING
        if self.config.leader_high_window in features.new_high_windows:
            return HighStage.LEADER
        if (
            self.config.strengthening_high_window in features.new_high_windows
            or features.recent_high_count >= self.config.strengthening_high_count
        ):
            candidate = HighStage.STRENGTHENING
        elif self.config.base_high_window in features.new_high_windows:
            candidate = HighStage.EMERGING
        else:
            distance = features.distance_to_near_high_pct
            if distance is not None and distance >= -self.config.near_high_pct:
                candidate = HighStage.WATCH
            elif discovered:
                return HighStage.COOLING
            else:
                return None

        persistence = {
            HighStage.LEADER: {
                HighStage.STRENGTHENING,
                HighStage.EMERGING,
                HighStage.WATCH,
            },
            HighStage.STRENGTHENING: {HighStage.EMERGING, HighStage.WATCH},
            HighStage.EMERGING: {HighStage.WATCH},
        }
        if previous_stage in persistence and candidate in persistence[previous_stage]:
            return previous_stage
        return candidate

    def _risks(self, features: HighFeatures) -> tuple[RiskFlag, ...]:
        output: list[RiskFlag] = []
        if features.volume_ratio is not None and features.volume_ratio >= self.config.volume_surge_ratio:
            output.append(RiskFlag.VOLUME_SURGE)
        if features.acceleration_high_count >= self.config.acceleration_high_count:
            output.append(RiskFlag.ACCELERATING)
        if features.ma_extension_pct is not None and features.ma_extension_pct >= self.config.extension_pct:
            output.append(RiskFlag.EXTENDED)
        if (
            features.drawdown_from_recent_high_pct is not None
            and features.drawdown_from_recent_high_pct <= -self.config.pullback_pct
        ):
            output.append(RiskFlag.PULLBACK)
        if features.trading_value < self.config.minimum_trading_value:
            output.append(RiskFlag.LOW_LIQUIDITY)
        return tuple(output)

    @staticmethod
    def _prior_average_ratio(
        index: int,
        bars: Sequence[PriceBar],
        window: int,
        *,
        attribute: str,
    ) -> float | None:
        if index < window:
            return None
        prior = [getattr(item, attribute) for item in bars[index - window : index]]
        average = sum(prior) / len(prior)
        if average <= 0:
            return None
        return getattr(bars[index], attribute) / average

    def _event(
        self,
        snapshot: HighSnapshot,
        event_type: MonitorEventType,
        detail: str,
    ) -> MonitorEvent:
        identity = "|".join(
            (
                self.config.parameter_version,
                self.config.parameter_hash,
                snapshot.symbol,
                snapshot.trade_date.isoformat(),
                event_type.value,
                detail,
            )
        )
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        return MonitorEvent(
            event_id=event_id,
            symbol=snapshot.symbol,
            trade_date=snapshot.trade_date,
            event_type=event_type,
            detail=detail,
            stage=snapshot.stage,
            close=snapshot.close,
        )

    @staticmethod
    def _validate_bars(bars: Sequence[PriceBar]) -> None:
        if not bars:
            return
        symbol = bars[0].symbol
        previous_date: date | None = None
        for index, bar in enumerate(bars):
            if not bar.symbol or bar.symbol != symbol:
                raise ValueError("bars must contain exactly one nonempty symbol")
            if not isinstance(bar.trade_date, date):
                raise ValueError(f"bar {index} contains invalid trade_date")
            if previous_date is not None and bar.trade_date <= previous_date:
                raise ValueError("bars must be strictly ascending by trade_date")
            prices = (bar.open, bar.high, bar.low, bar.close)
            if not all(
                not isinstance(value, bool)
                and isinstance(value, Real)
                and math.isfinite(value)
                and value > 0
                for value in prices
            ):
                raise ValueError(f"bar {index} contains invalid OHLC values")
            if bar.low > bar.high:
                raise ValueError(f"bar {index} has low above high")
            if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
                raise ValueError(f"bar {index} violates OHLC bounds")
            if (
                isinstance(bar.volume, bool)
                or not isinstance(bar.volume, Real)
                or not math.isfinite(bar.volume)
                or bar.volume < 0
            ):
                raise ValueError(f"bar {index} contains invalid volume")
            if bar.official_traded_value_twd is not None and (
                isinstance(bar.official_traded_value_twd, bool)
                or not isinstance(bar.official_traded_value_twd, Real)
                or not math.isfinite(bar.official_traded_value_twd)
                or bar.official_traded_value_twd <= 0
            ):
                raise ValueError(
                    f"bar {index} contains invalid official traded value"
                )
            previous_date = bar.trade_date
