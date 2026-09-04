from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, TypeVar


@dataclass(frozen=True)
class TemporalRecord:
    period_end: date
    announcement_date: date | None
    available_date: date
    source: str
    value: object
    availability_method: str


T = TypeVar("T", bound=TemporalRecord)


def derive_financial_available_date(
    period_end: date,
    *,
    q1_lag_days: int = 60,
    q2_lag_days: int = 60,
    q3_lag_days: int = 60,
    q4_lag_days: int = 90,
) -> date:
    """Return a conservative date-only proxy when filing timestamps are absent.

    This proxy is deliberately not described as a verified announcement date.  Any
    experiment using it must carry ``AVAILABLE_DATE_PROXY`` and remain provisional.
    """

    lag_by_month = {
        3: q1_lag_days,
        6: q2_lag_days,
        9: q3_lag_days,
        12: q4_lag_days,
    }
    try:
        lag = lag_by_month[period_end.month]
    except KeyError as exc:
        raise ValueError(f"Not a calendar quarter end: {period_end.isoformat()}") from exc
    return period_end + timedelta(days=lag)


def validate_temporal_record(record: TemporalRecord) -> None:
    if not record.source.strip():
        raise ValueError("PIT record source must not be blank")
    if record.announcement_date is not None:
        if record.announcement_date < record.period_end:
            raise ValueError("announcement_date precedes period_end")
        if record.available_date < record.announcement_date:
            raise ValueError("available_date precedes announcement_date")
    elif record.availability_method != "AVAILABLE_DATE_PROXY":
        raise ValueError("missing announcement_date requires an explicit proxy method")
    if record.available_date < record.period_end:
        raise ValueError("available_date precedes period_end")


def available_as_of(records: Iterable[T], as_of: date) -> tuple[T, ...]:
    selected: list[T] = []
    for record in records:
        validate_temporal_record(record)
        if record.available_date <= as_of:
            selected.append(record)
    return tuple(sorted(selected, key=lambda item: (item.period_end, item.available_date)))


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])
