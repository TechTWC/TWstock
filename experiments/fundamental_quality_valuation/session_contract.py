from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Iterable

import pandas as pd

EXPECTED_FROZEN_SESSION_SHA256 = (
    "151a7905b6983c422b3c7780d3f0e4ef559cd80ec5d0c91486f4ed457a0d7a34"
)


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_sessions(values: Iterable[date]) -> tuple[date, ...]:
    sessions = tuple(sorted(set(values)))
    if not sessions:
        raise ValueError("Frozen session calendar is empty")
    if any(value.weekday() >= 5 for value in sessions):
        raise ValueError("Frozen session calendar contains a weekend")
    return sessions


def load_frozen_sessions(
    path: Path,
    *,
    expected_sha256: str = EXPECTED_FROZEN_SESSION_SHA256,
) -> tuple[date, ...]:
    actual_sha256 = _sha256_path(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "Frozen session calendar hash mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    frame = pd.read_csv(path, dtype=str, encoding="utf-8")
    if list(frame.columns) != ["session_date"]:
        raise ValueError("Frozen session calendar must contain only session_date")
    parsed = pd.to_datetime(frame["session_date"], errors="raise").dt.date
    sessions = normalize_sessions(parsed)
    if len(sessions) != len(frame) or list(parsed) != list(sessions):
        raise ValueError("Frozen session calendar must be strictly sorted and unique")
    return sessions


def first_frozen_session_after(signal_date: date, sessions: Iterable[date]) -> date:
    ordered = normalize_sessions(sessions)
    result = next((session for session in ordered if session > signal_date), None)
    if result is None:
        raise ValueError(f"No frozen session after {signal_date.isoformat()}")
    return result


def first_trade_date_is_valid(
    signal_date: date,
    first_trade_date: date,
    sessions: Iterable[date],
) -> bool:
    ordered = normalize_sessions(sessions)
    return (
        first_trade_date > signal_date
        and first_trade_date in set(ordered)
        and first_trade_date == first_frozen_session_after(signal_date, ordered)
    )
