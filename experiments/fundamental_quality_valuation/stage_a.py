from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .engine import classify_security
from .models import SectorLogic, SecurityData
from .mops import (
    MopsFilingRecord,
    MopsSelectionDecision,
    parse_mops_filing_candidates,
    select_mops_filings,
)
from .pit import derive_financial_available_date, parse_date


MOPS_EXACT = "MOPS_EXACT"
AVAILABLE_DATE_PROXY = "AVAILABLE_DATE_PROXY"
MOPS_CONFLICT = "MOPS_CONFLICT_FAIL_CLOSED"


def sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def verify_restored_cache(cache_dir: Path, inventory_path: Path) -> int:
    inventory = pd.read_csv(inventory_path, dtype=str, encoding="utf-8-sig").fillna("")
    for row in inventory.to_dict(orient="records"):
        path = cache_dir / row["path"]
        if not path.is_file():
            raise FileNotFoundError(f"Restored MOPS cache member is missing: {path.name}")
        actual = sha256_path(path)
        if actual != row["sha256"]:
            raise ValueError(f"Restored MOPS cache hash mismatch: {path.name}")
    return len(inventory)


def load_offline_mops_archive(
    cache_dir: Path,
    symbols: Iterable[str],
) -> tuple[
    dict[tuple[str, int, int], MopsFilingRecord],
    dict[tuple[str, int, int], MopsSelectionDecision],
]:
    """Read only restored all-year archives. This function has no network fallback."""

    filings: dict[tuple[str, int, int], MopsFilingRecord] = {}
    decisions: dict[tuple[str, int, int], MopsSelectionDecision] = {}
    for symbol in sorted(set(str(value) for value in symbols)):
        html_path = cache_dir / f"{symbol}_ALL_AVAILABLE_YEARS_MOPS_t57sb01.html"
        metadata_path = html_path.with_suffix(".metadata.json")
        if not html_path.is_file() or not metadata_path.is_file():
            raise FileNotFoundError(f"Frozen MOPS archive is incomplete for {symbol}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not metadata.get("source_url") or not metadata.get("retrieval_timestamp"):
            raise ValueError(f"Frozen MOPS metadata is incomplete for {symbol}")
        raw = html_path.read_bytes()
        candidates = parse_mops_filing_candidates(
            raw.decode("big5", errors="replace"),
            source_url=str(metadata["source_url"]),
            retrieval_timestamp=str(metadata["retrieval_timestamp"]),
            response_sha256=sha256(raw).hexdigest(),
        )
        selected, audit = select_mops_filings(candidates)
        for record in selected:
            key = (record.symbol, record.fiscal_year, record.fiscal_quarter)
            if key in filings:
                raise ValueError(f"Duplicate selected MOPS key: {key}")
            filings[key] = record
        for decision in audit:
            key = (decision.symbol, decision.fiscal_year, decision.fiscal_quarter)
            if key in decisions:
                raise ValueError(f"Duplicate MOPS selection decision: {key}")
            decisions[key] = decision
    return filings, decisions


def first_session_after(signal_date: date, sessions: Iterable[date]) -> date:
    result = next((session for session in sessions if session > signal_date), None)
    if result is None:
        raise ValueError(f"No TWSE session after {signal_date.isoformat()}")
    return result


def market_information_date(
    signal_date: date,
    announcement_timestamp: str | None,
    sessions: Iterable[date],
) -> date | None:
    ordered = tuple(sessions)
    if announcement_timestamp:
        announced = datetime.fromisoformat(announcement_timestamp)
        if signal_date in ordered and announced.timetz().replace(tzinfo=None) > time(13, 30):
            return signal_date
    return next((session for session in reversed(ordered) if session < signal_date), None)


def _quarter(period_end: date) -> int:
    if period_end.month not in {3, 6, 9, 12}:
        raise ValueError(f"Not a calendar quarter end: {period_end.isoformat()}")
    return period_end.month // 3


def build_financial_timeline(
    normalized: pd.DataFrame,
    filings: dict[tuple[str, int, int], MopsFilingRecord],
    decisions: dict[tuple[str, int, int], MopsSelectionDecision],
    sessions: Iterable[date],
    availability_lags: dict[str, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sessions = tuple(sorted(set(sessions)))
    frame = normalized.copy()
    frame["symbol"] = frame["symbol"].astype(str)
    frame["period_end"] = pd.to_datetime(frame["period_end"], errors="raise").dt.date
    if frame.duplicated(["symbol", "period_end"]).any():
        raise ValueError("Normalized financial input contains duplicate symbol/period_end rows")

    rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for original in frame.sort_values(["symbol", "period_end"]).to_dict(orient="records"):
        item = dict(original)
        period_end = parse_date(item["period_end"])
        fiscal_year = period_end.year
        fiscal_quarter = _quarter(period_end)
        key = (str(item["symbol"]), fiscal_year, fiscal_quarter)
        filing = filings.get(key)
        decision = decisions.get(key)
        conflict = decision is not None and decision.status == "CONFLICT_FAIL_CLOSED"
        if conflict:
            announcement_date = None
            announcement_timestamp = None
            signal_date = None
            first_trade = None
            method = MOPS_CONFLICT
            confidence = "fail_closed"
            mapping_status = "CONFLICT"
            reason = decision.reason_code
        elif filing is not None:
            announcement_date = date.fromisoformat(filing.announcement_date)
            announcement_timestamp = filing.announcement_timestamp
            signal_date = announcement_date
            first_trade = first_session_after(signal_date, sessions)
            method = MOPS_EXACT
            confidence = "official_timestamp_second_precision"
            mapping_status = "EXACT_MATCH"
            reason = decision.reason_code if decision else "MOPS_EXACT_MATCH"
        else:
            announcement_date = None
            announcement_timestamp = None
            signal_date = derive_financial_available_date(
                period_end,
                q1_lag_days=int(availability_lags["q1"]),
                q2_lag_days=int(availability_lags["q2"]),
                q3_lag_days=int(availability_lags["q3"]),
                q4_lag_days=int(availability_lags["q4"]),
            )
            first_trade = first_session_after(signal_date, sessions)
            method = AVAILABLE_DATE_PROXY
            confidence = "conservative_proxy"
            mapping_status = "UNMATCHED_PROXY"
            reason = "MOPS_GENUINELY_UNMATCHED"

        financial_source_hash = str(item.get("source_hash") or "")
        combined_source_hash = canonical_hash(
            {
                "financial_source_hash": financial_source_hash,
                "mops_source_hash": filing.source_hash if filing else None,
                "availability_method": method,
                "signal_date": signal_date,
            }
        )
        item.update(
            {
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "announcement_date": announcement_date,
                "announcement_timestamp": announcement_timestamp,
                "available_date": signal_date,
                "signal_date": signal_date,
                "first_trade_date": first_trade,
                "availability_method": method,
                "timestamp_confidence": confidence,
                "mops_document_kind": filing.document_kind if filing else None,
                "mops_source_identifier": filing.source_identifier if filing else None,
                "mops_source_provenance": filing.source_provenance if filing else None,
                "mops_response_hash": filing.response_sha256 if filing else None,
                "mops_source_hash": filing.source_hash if filing else None,
                "mops_correction_status": filing.correction_status if filing else None,
                "mapping_status": mapping_status,
                "mapping_reason_code": reason,
                "financial_source_hash": financial_source_hash,
                "source_hash": combined_source_hash,
            }
        )
        rows.append(item)
        diagnostic_rows.append(
            {
                "symbol": item["symbol"],
                "period_end": period_end,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "mapping_status": mapping_status,
                "selection_status": decision.status if decision else "NO_MOPS_CANDIDATE",
                "selection_reason_code": reason,
                "candidate_count": decision.candidate_count if decision else 0,
                "exact_duplicate_count": decision.exact_duplicate_count if decision else 0,
                "multiple_vintage_count": decision.multiple_vintage_count if decision else 0,
                "multiple_document_kind_count": (
                    decision.multiple_document_kind_count if decision else 0
                ),
                "correction_candidate_count": (
                    decision.correction_candidate_count if decision else 0
                ),
                "duplicate_candidate_count": decision.duplicate_candidate_count if decision else 0,
                "duplicate_candidate_count_semantic": (
                    "DEPRECATED_LEGACY_CANDIDATES_BEYOND_FIRST"
                ),
                "conflict_candidate_count": decision.conflict_candidate_count if decision else 0,
                "corrected_filing_case": decision.corrected_filing_case if decision else False,
                "selected_document_kind": filing.document_kind if filing else None,
                "selected_source_identifier": filing.source_identifier if filing else None,
                "selected_announcement_timestamp": filing.announcement_timestamp if filing else None,
            }
        )
    timeline = pd.DataFrame(rows)
    diagnostics = pd.DataFrame(diagnostic_rows)
    return timeline, diagnostics


def build_signal_timeline(
    financial_timeline: pd.DataFrame,
    universe: pd.DataFrame,
    market_by_symbol: dict[str, pd.DataFrame],
    sessions: Iterable[date],
    config: dict[str, Any],
) -> pd.DataFrame:
    sessions = tuple(sorted(set(sessions)))
    universe = universe.copy()
    universe["symbol"] = universe["symbol"].astype(str)
    meta = universe.set_index("symbol").to_dict(orient="index")
    records: list[dict[str, Any]] = []
    for symbol, raw_quarterly in financial_timeline.groupby("symbol", sort=True):
        info = meta[str(symbol)]
        if info["sector_logic"] == SectorLogic.FINANCIAL.value:
            continue
        quarterly = raw_quarterly.copy().sort_values("period_end").reset_index(drop=True)
        for column in ("period_end", "announcement_date", "available_date", "signal_date", "first_trade_date"):
            quarterly[column] = pd.to_datetime(quarterly[column], errors="coerce").dt.date
        market = market_by_symbol.get(str(symbol), pd.DataFrame()).copy()
        if not market.empty:
            market["date"] = pd.to_datetime(market["date"], errors="raise").dt.date
        security = SecurityData(
            symbol=str(symbol),
            company=str(info["company"]),
            industry="UNKNOWN",
            sector_logic=SectorLogic(str(info["sector_logic"])),
            quarterly=quarterly,
            market=market,
            peer_group=str(info["peer_group"]),
            financial_subtype=str(info.get("financial_subtype") or "") or None,
            source="FinMind normalized financials + frozen MOPS checkpoint",
            source_metadata={},
            data_flags=[],
        )
        for row in quarterly.to_dict(orient="records"):
            if row["mapping_status"] == "CONFLICT" or pd.isna(row["signal_date"]):
                continue
            signal_date = parse_date(row["signal_date"])
            if signal_date > date.fromisoformat(config["as_of_date"]):
                continue
            market_date = market_information_date(
                signal_date,
                row.get("announcement_timestamp"),
                sessions,
            )
            result = classify_security(
                security,
                signal_date,
                config,
                market_as_of=market_date or signal_date,
            )
            reason_codes = list(result.reason_codes)
            reason_codes.append(str(row["mapping_reason_code"]))
            if row["availability_method"] == AVAILABLE_DATE_PROXY:
                reason_codes.append("AVAILABLE_DATE_PROXY")
            records.append(
                {
                    "symbol": str(symbol),
                    "period_end": parse_date(row["period_end"]),
                    "announcement_timestamp": row.get("announcement_timestamp"),
                    "signal_date": signal_date,
                    "first_trade_date": parse_date(row["first_trade_date"]),
                    "quality": result.quality,
                    "fundamental_state": result.fundamental_state,
                    "state_detail": result.state_detail,
                    "valuation": result.valuation,
                    "data_quality": result.data_quality,
                    "reason_codes": " | ".join(dict.fromkeys(reason_codes)),
                    "availability_method": row["availability_method"],
                    "source_hash": row["source_hash"],
                    "predictive_eligible": True,
                }
            )
    columns = [
        "symbol",
        "period_end",
        "announcement_timestamp",
        "signal_date",
        "first_trade_date",
        "quality",
        "fundamental_state",
        "state_detail",
        "valuation",
        "data_quality",
        "reason_codes",
        "availability_method",
        "source_hash",
        "predictive_eligible",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records, columns=columns).sort_values(
        ["symbol", "signal_date", "period_end"]
    ).reset_index(drop=True)


def coverage_frame(timeline: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (sector, method), group in timeline.groupby(["sector_logic", "availability_method"], dropna=False):
        rows.append(
            {
                "scope": "SECTOR",
                "sector_logic": sector,
                "availability_method": method,
                "observations": len(group),
                "symbols": group["symbol"].nunique(),
            }
        )
    for method, group in timeline.groupby("availability_method", dropna=False):
        rows.append(
            {
                "scope": "TOTAL",
                "sector_logic": "ALL",
                "availability_method": method,
                "observations": len(group),
                "symbols": group["symbol"].nunique(),
            }
        )
    return pd.DataFrame(rows).sort_values(["scope", "sector_logic", "availability_method"])


def validate_stage_a_frames(financial: pd.DataFrame, signals: pd.DataFrame) -> None:
    numeric = pd.concat(
        [financial.select_dtypes(include=[np.number]), signals.select_dtypes(include=[np.number])],
        axis=0,
        ignore_index=True,
    )
    if not numeric.empty and np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Stage A artifact contains an infinite numeric value")
    exact = financial[financial["availability_method"] == MOPS_EXACT]
    if exact["announcement_timestamp"].isna().any():
        raise ValueError("MOPS_EXACT row is missing announcement_timestamp")
    valid = financial[financial["availability_method"].isin({MOPS_EXACT, AVAILABLE_DATE_PROXY})]
    if not (
        pd.to_datetime(valid["first_trade_date"]).dt.date
        > pd.to_datetime(valid["signal_date"]).dt.date
    ).all():
        raise ValueError("first_trade_date does not obey the strict next-session rule")
    if not signals.empty and not (signals["predictive_eligible"] == True).all():  # noqa: E712
        raise ValueError("Signal timeline contains an ineligible issuer")


def selection_decision_dict(decision: MopsSelectionDecision) -> dict[str, Any]:
    result = asdict(decision)
    if decision.selected is not None:
        result["selected"] = decision.selected.to_dict()
    return result
