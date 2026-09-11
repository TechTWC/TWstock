from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Iterable, Mapping

import pandas as pd

from experiments.fundamental_quality_valuation.stage_a import canonical_hash


GENESIS = "GENESIS"
HASH_LENGTH = 64
SIGNAL_STATUSES = {"ACTIVE_SIGNAL", "SUPERSEDING_EVENT"}
OUTCOME_STATUSES = {"PENDING", "MATURED", "UNAVAILABLE"}
QUALITY_VALUES = {"GOOD", "ACCEPTABLE", "WEAK", "UNKNOWN"}
STATE_VALUES = {"IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN"}
STATE_DETAIL_VALUES = {
    "DETERIORATING",
    "BOTTOMING",
    "TURNING_UP",
    "CONFIRMED_GROWTH",
    "MATURE_GROWTH",
    "DECELERATING",
    "UNKNOWN",
}
VALUATION_VALUES = {"LOW", "NORMAL", "HIGH", "N/M"}
DATA_QUALITY_VALUES = {"OK", "PARTIAL", "INSUFFICIENT"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]

SIGNAL_REQUIRED = {
    "event_id",
    "sequence_number",
    "symbol",
    "company",
    "sector_logic",
    "predictive_eligible",
    "period_end",
    "mops_announcement_timestamp",
    "mops_retrieved_at",
    "financial_source_retrieved_at",
    "valuation_source_retrieved_at",
    "information_cutoff_timestamp",
    "signal_generated_at",
    "signal_date",
    "first_trade_date",
    "quality",
    "fundamental_state",
    "state_detail",
    "valuation",
    "data_quality",
    "reason_codes",
    "financial_source_hash",
    "mops_source_hash",
    "valuation_source_hash",
    "model_hash",
    "universe_hash",
    "record_hash",
    "previous_record_hash",
    "status",
}

OUTCOME_REQUIRED = {
    "outcome_event_id",
    "sequence_number",
    "event_id",
    "horizon_trading_days",
    "status",
    "entry_date",
    "exit_date",
    "stock_return",
    "0050_return",
    "excess_return",
    "stock_source_hash",
    "benchmark_source_hash",
    "session_source_hash",
    "calculated_at",
    "record_hash",
    "previous_record_hash",
}


class ContractError(RuntimeError):
    """A frozen OOS contract or availability guard failed closed."""


class LedgerError(RuntimeError):
    """An append-only ledger invariant failed closed."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractError(f"Expected a JSON object: {path}")
    return payload


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include an explicit timezone offset")
    return parsed


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO date") from exc


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == HASH_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_hash(record: Mapping[str, Any]) -> str:
    """Hash canonical record content, excluding the self-referential hash field."""

    payload = dict(record)
    payload.pop("record_hash", None)
    return canonical_hash(payload)


def load_contract(path: Path) -> dict[str, Any]:
    contract = _read_json(path)
    required = {
        "freeze_head",
        "frozen_model_config_path",
        "frozen_model_hash",
        "frozen_universe_path",
        "frozen_universe_hash",
        "oos_start_timestamp",
        "primary_horizons",
        "eligible_sector_policy",
        "frozen_cohort_count",
        "expected_non_financial",
        "financial_excluded",
        "historical_primary_evidence",
        "historical_evidence_label",
        "return_benchmark",
        "no_threshold_change",
        "no_retroactive_backfill",
        "no_composite_score",
        "live_collection_enabled",
        "live_collection_mode",
        "scheduled_collection_enabled",
        "scheduled_collection_prepared",
        "scheduled_collection_active",
        "historical_backfill_enabled",
        "outcome_calculation_enabled",
        "pending_candidate_registry_path",
        "source_blob_root",
        "run_manifest_root",
        "collector_runtime_manifest_path",
    }
    missing = sorted(required - contract.keys())
    if missing:
        raise ContractError(f"OOS contract missing fields: {', '.join(missing)}")
    fixed = {
        "stage": "OOS-C",
        "freeze_head": "188aa8120a6c35b3b6377490f1ed9456566824bd",
        "frozen_model_hash": "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f",
        "frozen_universe_hash": "aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46",
        "oos_start_timestamp": "2026-09-11T00:00:00+08:00",
        "primary_horizons": [60, 120, 252, 504],
        "eligible_sector_policy": "NON_FINANCIAL_ONLY",
        "frozen_cohort_count": 50,
        "expected_non_financial": 38,
        "financial_excluded": 12,
        "historical_primary_evidence": "MODERATE",
        "historical_evidence_label": "EXPLORATORY_PREDICTIVE_ASSOCIATION",
        "return_benchmark": "0050",
        "no_threshold_change": True,
        "no_retroactive_backfill": True,
        "no_composite_score": True,
        "live_collection_enabled": True,
        "live_collection_mode": "MANUAL_AND_SCHEDULED_ENGINE",
        "scheduled_collection_enabled": False,
        "scheduled_collection_prepared": True,
        "scheduled_collection_active": False,
        "historical_backfill_enabled": False,
        "outcome_calculation_enabled": False,
        "source_blob_root": "artifacts/0050_fundamental_oos_v0_1/source_blobs",
        "run_manifest_root": "artifacts/0050_fundamental_oos_v0_1/runs",
        "collector_runtime_manifest_path": "config/collector_runtime_manifest_v0_1.json",
    }
    for key, expected in fixed.items():
        if contract.get(key) != expected:
            raise ContractError(f"Frozen OOS contract mismatch for {key}")
    _parse_timestamp(contract["oos_start_timestamp"], "oos_start_timestamp")
    return contract


def verify_freeze(root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    model_config = _read_json(root / str(contract["frozen_model_config_path"]))
    actual_model_hash = canonical_hash(
        {
            "quality_rules": model_config["quality_rules"],
            "valuation_rules": model_config["valuation_rules"],
        }
    )
    actual_universe_hash = _sha256_path(root / str(contract["frozen_universe_path"]))
    universe = pd.read_csv(root / str(contract["frozen_universe_path"]), dtype=str).fillna("")
    financial = int((universe["sector_logic"] == "FINANCIAL").sum())
    non_financial = int((universe["sector_logic"] != "FINANCIAL").sum())
    checks = {
        "model_hash": actual_model_hash == contract["frozen_model_hash"],
        "universe_hash": actual_universe_hash == contract["frozen_universe_hash"],
        "cohort_count": len(universe) == int(contract["frozen_cohort_count"]),
        "eligible_non_financial": non_financial == int(contract["expected_non_financial"]),
        "excluded_financial": financial == int(contract["financial_excluded"]),
    }
    try:
        commit = subprocess.run(
            ["git", "cat-file", "-e", f"{contract['freeze_head']}^{{commit}}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", str(contract["freeze_head"]), "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        checks["freeze_head_exists"] = commit.returncode == 0
        checks["freeze_head_is_ancestor"] = ancestor.returncode == 0
    except FileNotFoundError:
        checks["freeze_head_exists"] = False
        checks["freeze_head_is_ancestor"] = False
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise ContractError(f"Frozen identity verification failed: {', '.join(failed)}")
    return {
        "checks": checks,
        "actual_model_hash": actual_model_hash,
        "actual_universe_hash": actual_universe_hash,
        "frozen_cohort": len(universe),
        "eligible_non_financial": non_financial,
        "excluded_financial": financial,
    }


def _require_fields(record: Mapping[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - record.keys())
    if missing:
        raise LedgerError(f"{label} missing fields: {', '.join(missing)}")


def _information_cutoff(record: Mapping[str, Any]) -> datetime:
    fields = (
        "mops_announcement_timestamp",
        "mops_retrieved_at",
        "financial_source_retrieved_at",
        "valuation_source_retrieved_at",
        "signal_generated_at",
    )
    timestamps = [_parse_timestamp(record[field], field) for field in fields]
    return max(timestamps)


def _first_common_session_after(
    cutoff: datetime,
    twse_sessions: Iterable[str],
    stock_sessions: Iterable[str],
    benchmark_sessions: Iterable[str],
) -> date:
    twse = {_parse_date(item, "twse_session") for item in twse_sessions}
    stock = {_parse_date(item, "stock_session") for item in stock_sessions}
    benchmark = {_parse_date(item, "benchmark_session") for item in benchmark_sessions}
    common = sorted(twse & stock & benchmark)
    if not common or any(item.weekday() >= 5 for item in common):
        raise ContractError("Session snapshot is empty or contains a weekend")
    result = next((item for item in common if item > cutoff.date()), None)
    if result is None:
        raise ContractError("No common frozen session exists after information cutoff")
    return result


def validate_signal_record(
    record: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    twse_sessions: Iterable[str],
    stock_sessions: Iterable[str],
    benchmark_sessions: Iterable[str],
) -> None:
    _require_fields(record, SIGNAL_REQUIRED, "Signal record")
    if not isinstance(record["event_id"], str) or not record["event_id"]:
        raise LedgerError("event_id must be non-empty")
    if not isinstance(record["sequence_number"], int) or record["sequence_number"] < 1:
        raise LedgerError("sequence_number must be a positive integer")
    start = _parse_timestamp(contract["oos_start_timestamp"], "oos_start_timestamp")
    timestamp_fields = (
        "mops_announcement_timestamp",
        "mops_retrieved_at",
        "financial_source_retrieved_at",
        "valuation_source_retrieved_at",
        "signal_generated_at",
    )
    if any(_parse_timestamp(record[field], field) < start for field in timestamp_fields):
        raise ContractError("PRE_OOS_EXCLUDED")
    cutoff = _information_cutoff(record)
    supplied_cutoff = _parse_timestamp(
        record["information_cutoff_timestamp"], "information_cutoff_timestamp"
    )
    if supplied_cutoff != cutoff:
        raise ContractError("information_cutoff_timestamp is not the conservative maximum")
    if _parse_timestamp(record["signal_generated_at"], "signal_generated_at") != cutoff:
        raise ContractError("Signal was generated before all required data was available")
    if _parse_date(record["signal_date"], "signal_date") != cutoff.date():
        raise ContractError("signal_date must equal the information cutoff local date")
    expected_first_trade = _first_common_session_after(
        cutoff, twse_sessions, stock_sessions, benchmark_sessions
    )
    if _parse_date(record["first_trade_date"], "first_trade_date") != expected_first_trade:
        raise ContractError("first_trade_date is not the first accepted common frozen session")
    if record["model_hash"] != contract["frozen_model_hash"]:
        raise ContractError("Frozen model hash mismatch")
    if record["universe_hash"] != contract["frozen_universe_hash"]:
        raise ContractError("Frozen universe hash mismatch")
    if record["quality"] not in QUALITY_VALUES:
        raise LedgerError("Unknown quality value")
    if record["fundamental_state"] not in STATE_VALUES:
        raise LedgerError("Unknown fundamental_state value")
    if record["state_detail"] not in STATE_DETAIL_VALUES:
        raise LedgerError("Unknown state_detail value")
    if record["valuation"] not in VALUATION_VALUES:
        raise LedgerError("Unknown valuation value")
    if record["data_quality"] not in DATA_QUALITY_VALUES:
        raise LedgerError("Unknown data_quality value")
    if record["sector_logic"] == "FINANCIAL" or record["predictive_eligible"] is not True:
        raise ContractError("FINANCIAL_ISSUER_NOT_PREDICTIVE_ELIGIBLE")
    if record["sector_logic"] not in {"GENERAL", "CYCLICAL"}:
        raise ContractError("Only frozen non-financial sector logic is eligible")
    universe_path = PROJECT_ROOT / str(contract["frozen_universe_path"])
    universe = pd.read_csv(universe_path, dtype=str).fillna("")
    matches = universe[universe["symbol"] == str(record["symbol"])]
    if len(matches) != 1:
        raise ContractError("SYMBOL_NOT_IN_FROZEN_UNIVERSE")
    frozen_sector = str(matches.iloc[0]["sector_logic"])
    if frozen_sector == "FINANCIAL":
        raise ContractError("FINANCIAL_ISSUER_NOT_PREDICTIVE_ELIGIBLE")
    if record["sector_logic"] != frozen_sector:
        raise ContractError("Signal sector_logic differs from frozen universe")
    if not isinstance(record["reason_codes"], list) or not all(
        isinstance(item, str) and item for item in record["reason_codes"]
    ):
        raise LedgerError("reason_codes must be a non-empty string array")
    for field in ("financial_source_hash", "mops_source_hash", "valuation_source_hash"):
        if not _is_hash(record[field]):
            raise LedgerError(f"{field} must be a lowercase SHA-256")
    if record["status"] not in SIGNAL_STATUSES:
        raise LedgerError("Signal status is not appendable")
    supersedes = record.get("supersedes_event_id")
    if record["status"] == "SUPERSEDING_EVENT" and not supersedes:
        raise LedgerError("SUPERSEDING_EVENT requires supersedes_event_id")
    if record["status"] == "ACTIVE_SIGNAL" and supersedes is not None:
        raise LedgerError("ACTIVE_SIGNAL cannot supersede another event")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise LedgerError(f"Ledger does not exist: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"Invalid JSONL at line {line_number}: {path}") from exc
        if not isinstance(value, dict):
            raise LedgerError(f"JSONL line {line_number} is not an object: {path}")
        records.append(value)
    return records


def _validate_chain(
    records: Iterable[Mapping[str, Any]],
    *,
    identity_field: str,
) -> list[dict[str, Any]]:
    checked = [dict(record) for record in records]
    seen: set[str] = set()
    previous = GENESIS
    for expected_sequence, record in enumerate(checked, start=1):
        _require_fields(record, {identity_field, "sequence_number", "previous_record_hash", "record_hash"}, "Ledger record")
        identity = record[identity_field]
        if identity in seen:
            raise LedgerError(f"Duplicate {identity_field}: {identity}")
        if record["sequence_number"] != expected_sequence:
            raise LedgerError("Ledger sequence is not continuous")
        if record["previous_record_hash"] != previous:
            raise LedgerError("previous_record_hash mismatch")
        actual = record_hash(record)
        if record["record_hash"] != actual:
            raise LedgerError("record_hash mismatch")
        seen.add(identity)
        previous = actual
    return checked


def validate_signal_ledger(path: Path) -> list[dict[str, Any]]:
    records = _validate_chain(_read_jsonl(path), identity_field="event_id")
    event_ids = {record["event_id"] for record in records}
    for record in records:
        _require_fields(record, SIGNAL_REQUIRED, "Signal ledger record")
        if record["status"] == "SUPERSEDING_EVENT":
            target = record.get("supersedes_event_id")
            if target not in event_ids or target == record["event_id"]:
                raise LedgerError("SUPERSEDING_EVENT target does not exist")
            if next(index for index, item in enumerate(records) if item["event_id"] == target) >= records.index(record):
                raise LedgerError("SUPERSEDING_EVENT must follow its original record")
    return records


def validate_outcome_ledger(path: Path) -> list[dict[str, Any]]:
    records = _validate_chain(_read_jsonl(path), identity_field="outcome_event_id")
    for record in records:
        _require_fields(record, OUTCOME_REQUIRED, "Outcome ledger record")
    return records


def _atomic_append_line(path: Path, record: Mapping[str, Any]) -> None:
    """Replace the ledger with its old bytes plus one complete, fsynced line.

    Validation happens before this function.  A write/fsync/replace failure therefore
    leaves either the prior ledger or the complete new ledger, never a partial line.
    """

    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    before = path.read_bytes()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(before)
            handle.write((encoded + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def append_signal_record(
    path: Path,
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    twse_sessions: Iterable[str],
    stock_sessions: Iterable[str],
    benchmark_sessions: Iterable[str],
) -> dict[str, Any]:
    verify_freeze(PROJECT_ROOT, contract)
    existing = validate_signal_ledger(path)
    record = deepcopy(dict(candidate))
    record["sequence_number"] = len(existing) + 1
    record["previous_record_hash"] = existing[-1]["record_hash"] if existing else GENESIS
    record.pop("record_hash", None)
    record["record_hash"] = record_hash(record)
    validate_signal_record(
        record,
        contract,
        twse_sessions=twse_sessions,
        stock_sessions=stock_sessions,
        benchmark_sessions=benchmark_sessions,
    )
    if record["event_id"] in {item["event_id"] for item in existing}:
        raise LedgerError(f"Duplicate event_id: {record['event_id']}")
    if record["status"] == "SUPERSEDING_EVENT":
        target = record.get("supersedes_event_id")
        if target not in {item["event_id"] for item in existing}:
            raise LedgerError("SUPERSEDING_EVENT target does not exist")
    _validate_chain([*existing, record], identity_field="event_id")
    _atomic_append_line(path, record)
    validate_signal_ledger(path)
    return record


def validate_outcome_record(
    record: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    signal: Mapping[str, Any],
    common_sessions: Iterable[str],
    as_of: str,
) -> None:
    _require_fields(record, OUTCOME_REQUIRED, "Outcome record")
    if record["event_id"] != signal["event_id"]:
        raise LedgerError("Outcome event_id does not match signal")
    horizon = record["horizon_trading_days"]
    if horizon not in contract["primary_horizons"]:
        raise ContractError("Outcome horizon is not frozen")
    if record["status"] not in OUTCOME_STATUSES:
        raise LedgerError("Unknown outcome status")
    sessions = sorted({_parse_date(item, "common_session") for item in common_sessions})
    entry = _parse_date(record["entry_date"], "entry_date")
    if entry != _parse_date(signal["first_trade_date"], "signal.first_trade_date"):
        raise ContractError("Outcome entry_date differs from immutable signal")
    if entry not in sessions:
        raise ContractError("Outcome entry_date is not an accepted common session")
    entry_index = sessions.index(entry)
    target_index = entry_index + int(horizon)
    calculation_date = _parse_timestamp(record["calculated_at"], "calculated_at").date()
    as_of_date = _parse_date(as_of, "as_of")
    matured = target_index < len(sessions) and sessions[target_index] <= as_of_date
    returns = (record["stock_return"], record["0050_return"], record["excess_return"])
    if record["status"] == "PENDING":
        if matured:
            raise ContractError("A matured outcome cannot remain PENDING")
        if record["exit_date"] is not None or any(value is not None for value in returns):
            raise ContractError("Pending outcome must not contain future returns")
    elif record["status"] == "MATURED":
        if not matured:
            raise ContractError("OUTCOME_NOT_MATURED")
        expected_exit = sessions[target_index]
        if _parse_date(record["exit_date"], "exit_date") != expected_exit:
            raise ContractError("Outcome exit_date is not the frozen horizon session")
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in returns
        ):
            raise ContractError("Matured outcome requires all return values")
        if abs(float(record["stock_return"]) - float(record["0050_return"]) - float(record["excess_return"])) > 1e-12:
            raise ContractError("excess_return arithmetic mismatch")
    else:
        if not matured:
            raise ContractError("UNAVAILABLE cannot be asserted before maturity")
        if any(value is not None for value in returns):
            raise ContractError("Unavailable outcome must not contain returns")
    if calculation_date > as_of_date:
        raise ContractError("calculated_at cannot be after as_of")
    for field in ("stock_source_hash", "benchmark_source_hash", "session_source_hash"):
        value = record[field]
        if record["status"] == "PENDING" and value is None:
            continue
        if not _is_hash(value):
            raise LedgerError(f"{field} must be null for pending or a lowercase SHA-256")


def append_outcome_record(
    path: Path,
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    signal: Mapping[str, Any],
    common_sessions: Iterable[str],
    as_of: str,
) -> dict[str, Any]:
    existing = validate_outcome_ledger(path)
    record = deepcopy(dict(candidate))
    record["sequence_number"] = len(existing) + 1
    record["previous_record_hash"] = existing[-1]["record_hash"] if existing else GENESIS
    record.pop("record_hash", None)
    record["record_hash"] = record_hash(record)
    validate_outcome_record(record, contract, signal=signal, common_sessions=common_sessions, as_of=as_of)
    if record["outcome_event_id"] in {item["outcome_event_id"] for item in existing}:
        raise LedgerError(f"Duplicate outcome_event_id: {record['outcome_event_id']}")
    same_maturity = [
        item
        for item in existing
        if item["event_id"] == record["event_id"]
        and item["horizon_trading_days"] == record["horizon_trading_days"]
    ]
    if same_maturity:
        if same_maturity[-1]["status"] != "PENDING":
            raise LedgerError("Final maturity outcome cannot be superseded")
        if record["status"] == "PENDING":
            raise LedgerError("Duplicate PENDING maturity state")
    _validate_chain([*existing, record], identity_field="outcome_event_id")
    _atomic_append_line(path, record)
    validate_outcome_ledger(path)
    return record


def validate_source_snapshot(snapshot: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    required = {
        "snapshot_id",
        "event_id",
        "snapshot_type",
        "retrieved_at",
        "source_url_or_identifier",
        "sha256",
        "artifact_path",
        "processing_status",
    }
    _require_fields(snapshot, required, "Source snapshot")
    if snapshot["snapshot_type"] not in {"MOPS", "FINANCIAL", "VALUATION", "MARKET_SESSION"}:
        raise ContractError("Unknown source snapshot type")
    if snapshot["processing_status"] not in {
        "READY",
        "PENDING_DATA",
        "PRE_OOS_EXCLUDED",
        "FAILED_CLOSED",
    }:
        raise ContractError("Unknown source snapshot processing status")
    retrieved = _parse_timestamp(snapshot["retrieved_at"], "snapshot.retrieved_at")
    start = _parse_timestamp(contract["oos_start_timestamp"], "oos_start_timestamp")
    if retrieved < start and snapshot["processing_status"] != "PRE_OOS_EXCLUDED":
        raise ContractError("PRE_OOS_EXCLUDED")
    if snapshot["processing_status"] == "READY" and not _is_hash(snapshot["sha256"]):
        raise ContractError("Ready source snapshot requires SHA-256")


def validate_fixture(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    required = {"signal", "source_snapshots", "session_snapshot"}
    missing = required - payload.keys()
    if missing:
        raise ContractError(f"Fixture missing fields: {', '.join(sorted(missing))}")
    snapshots = payload["source_snapshots"]
    if not isinstance(snapshots, list) or len(snapshots) != 4:
        raise ContractError("Fixture must contain four source snapshots")
    for snapshot in snapshots:
        validate_source_snapshot(snapshot, contract)
    ready_by_type = {
        snapshot["snapshot_type"]: snapshot
        for snapshot in snapshots
        if snapshot["processing_status"] == "READY"
    }
    if set(ready_by_type) != {"MOPS", "FINANCIAL", "VALUATION", "MARKET_SESSION"}:
        raise ContractError("PENDING_DATA: all required snapshots must be ready")
    signal = deepcopy(dict(payload["signal"]))
    signal["sequence_number"] = 1
    signal["previous_record_hash"] = GENESIS
    signal.pop("record_hash", None)
    signal["record_hash"] = record_hash(signal)
    session = payload["session_snapshot"]
    validate_signal_record(
        signal,
        contract,
        twse_sessions=session["twse_sessions"],
        stock_sessions=session["stock_sessions"],
        benchmark_sessions=session["benchmark_sessions"],
    )
    expected_hashes = {
        "mops_source_hash": ready_by_type["MOPS"]["sha256"],
        "financial_source_hash": ready_by_type["FINANCIAL"]["sha256"],
        "valuation_source_hash": ready_by_type["VALUATION"]["sha256"],
    }
    for field, expected in expected_hashes.items():
        if signal[field] != expected:
            raise ContractError(f"Signal {field} does not match source snapshot")
    return signal
