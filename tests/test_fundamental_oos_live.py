from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket

import pytest

from experiments.fundamental_oos_shadow.ledger import (
    ContractError,
    LedgerError,
    append_signal_record,
    load_contract,
    validate_signal_ledger,
)
from experiments.fundamental_oos_shadow.live import (
    CANDIDATE_STATUSES,
    CandidateRegistry,
    ContentAddressedSourceStore,
    SnapshotStore,
    _candidate_from_filing,
    _financial_complete,
    _next_common_session,
    _valuation_complete,
    conservative_cutoff,
    filing_identity_hash,
    run_collection,
    run_live_collection,
    run_scheduled_collection,
    stable_event_id,
    validate_snapshot_tree,
)
from experiments.fundamental_oos_shadow.scheduled import (
    SCHEDULED_WRITE_ALLOWLIST,
    assert_scheduled_write_allowlist,
    verify_collector_runtime_freeze,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/fundamental_oos_shadow_v0_1.json"
FIXTURE_PATH = ROOT / "tests/fixtures/fundamental_oos_shadow/oos_a_valid_fixture.json"


@pytest.fixture
def contract() -> dict[str, object]:
    return load_contract(CONTRACT_PATH)


@pytest.fixture
def filing() -> dict[str, object]:
    return {
        "symbol": "2330",
        "period_end": "2026-09-30",
        "fiscal_year": 2026,
        "fiscal_quarter": 3,
        "announcement_timestamp": "2026-11-12T15:01:02+08:00",
        "retrieval_timestamp": "2026-11-12T16:00:00+08:00",
        "source_identifier": "202603_2330_AI1.pdf",
        "document_kind": "CONSOLIDATED",
        "file_size_bytes": 12345,
        "correction_status": "無",
        "response_sha256": "a" * 64,
    }


def _registry_candidate(contract: dict[str, object], filing: dict[str, object]) -> dict[str, object]:
    event_id = stable_event_id(filing, contract)
    return {
        "candidate_id": event_id,
        "event_id": event_id,
        "symbol": "2330",
        "company": "台積電",
        "period_end": "2026-09-30",
        "fiscal_year": 2026,
        "fiscal_quarter": 3,
        "mops_announcement_timestamp": filing["announcement_timestamp"],
        "mops_retrieved_at": filing["retrieval_timestamp"],
        "mops_source_hash": filing["response_sha256"],
        "mops_filing_identity_hash": filing_identity_hash(filing),
        "status": "MOPS_DISCOVERED",
    }


def test_contract_is_exact_oos_c_prepared_not_active(contract: dict[str, object]) -> None:
    assert contract["stage"] == "OOS-C"
    assert contract["live_collection_enabled"] is True
    assert contract["live_collection_mode"] == "MANUAL_AND_SCHEDULED_ENGINE"
    assert contract["scheduled_collection_enabled"] is False
    assert contract["scheduled_collection_prepared"] is True
    assert contract["scheduled_collection_active"] is False
    assert contract["historical_backfill_enabled"] is False
    assert contract["outcome_calculation_enabled"] is False


def test_stable_event_id_is_deterministic(contract: dict[str, object], filing: dict[str, object]) -> None:
    assert stable_event_id(filing, contract) == stable_event_id(deepcopy(filing), contract)


def test_event_id_ignores_retrieval_and_archive_response(
    contract: dict[str, object], filing: dict[str, object]
) -> None:
    changed = deepcopy(filing)
    changed["retrieval_timestamp"] = "2026-11-13T16:00:00+08:00"
    changed["response_sha256"] = "b" * 64
    assert stable_event_id(filing, contract) == stable_event_id(changed, contract)


def test_genuine_filing_correction_changes_identity(
    contract: dict[str, object], filing: dict[str, object]
) -> None:
    changed = deepcopy(filing)
    changed["announcement_timestamp"] = "2026-11-13T15:01:02+08:00"
    changed["source_identifier"] = "202603_2330_AI1_C1.pdf"
    changed["correction_status"] = "更正"
    assert stable_event_id(filing, contract) != stable_event_id(changed, contract)


def test_financial_filing_is_audit_only(
    contract: dict[str, object], filing: dict[str, object]
) -> None:
    financial = deepcopy(filing)
    financial["symbol"] = "2881"
    candidate = _candidate_from_filing(
        financial,
        {"company": "富邦金", "sector_logic": "FINANCIAL", "peer_group": "FINANCIAL"},
        contract,
    )
    assert candidate["status"] == "FINANCIAL_EXCLUDED"


def test_conservative_cutoff_is_maximum() -> None:
    assert conservative_cutoff(
        "2026-11-12T15:00:00+08:00",
        "2026-11-12T08:00:00+00:00",
        "2026-11-13T01:00:00+00:00",
    ) == "2026-11-13T01:00:00+00:00"


def test_conservative_cutoff_rejects_naive_timestamp() -> None:
    with pytest.raises(ContractError, match="explicit timezones"):
        conservative_cutoff("2026-11-12T15:00:00")


def test_candidate_registry_round_trip_first_seen_lock(
    tmp_path: Path, contract: dict[str, object], filing: dict[str, object]
) -> None:
    registry = CandidateRegistry(tmp_path / "pending.json")
    candidates: dict[str, dict[str, object]] = {}
    candidate = _registry_candidate(contract, filing)
    current = registry.upsert_first_seen(candidates, candidate)
    current["status"] = "PENDING_FINANCIAL_DATA"
    current["first_complete_data_locked_at"] = "2026-11-14T08:00:00+08:00"
    later = deepcopy(candidate)
    later["mops_retrieved_at"] = "2026-11-15T08:00:00+08:00"
    assert registry.upsert_first_seen(candidates, later) is current
    registry.save(candidates)
    loaded = registry.load()
    assert loaded[str(candidate["candidate_id"])]["first_complete_data_locked_at"] == current["first_complete_data_locked_at"]


def test_candidate_registry_keeps_first_archive_hash_and_rejects_identity_conflict(
    tmp_path: Path, contract: dict[str, object], filing: dict[str, object]
) -> None:
    registry = CandidateRegistry(tmp_path / "pending.json")
    candidate = _registry_candidate(contract, filing)
    candidates = {str(candidate["candidate_id"]): candidate}
    conflict = deepcopy(candidate)
    conflict["mops_source_hash"] = "b" * 64
    assert registry.upsert_first_seen(candidates, conflict)["mops_source_hash"] == "a" * 64
    conflict["period_end"] = "2026-12-31"
    with pytest.raises(ContractError, match="identity conflict"):
        registry.upsert_first_seen(candidates, conflict)


def test_all_candidate_statuses_are_bounded() -> None:
    assert CANDIDATE_STATUSES == {
        "MOPS_DISCOVERED", "PENDING_FINANCIAL_DATA", "PENDING_VALUATION_DATA",
        "PENDING_SESSION", "READY_FOR_SIGNAL", "SIGNAL_EMITTED",
        "FINANCIAL_EXCLUDED", "SOURCE_CONFLICT", "FAILED_CLOSED",
    }


def test_finmind_missing_target_quarter_stays_pending() -> None:
    assert not _financial_complete([{"period_end": "2026-06-30", "ttm_revenue": 1}], "2026-09-30")


def test_finmind_incomplete_inputs_stay_pending() -> None:
    row = {"period_end": "2026-09-30", "ttm_revenue": 1, "ttm_eps": 2, "equity": 3, "ttm_cfo": None}
    assert not _financial_complete([row], "2026-09-30")


def test_valuation_requires_price_and_context() -> None:
    assert not _valuation_complete([])
    assert not _valuation_complete([{"close": 100, "PER": None, "PBR": None, "dividend_yield": None}])
    assert _valuation_complete([{"close": 100, "PER": 20, "PBR": None, "dividend_yield": None}])


def test_session_guard_selects_strictly_later_common_weekday() -> None:
    sessions = {
        "twse_sessions": ["2026-11-13", "2026-11-16"],
        "stock_sessions": ["2026-11-13", "2026-11-16"],
        "benchmark_sessions": ["2026-11-13", "2026-11-16"],
    }
    assert _next_common_session("2026-11-13T08:00:00+08:00", sessions) == "2026-11-16"


def test_session_guard_fails_closed_on_weekend() -> None:
    sessions = {
        "twse_sessions": ["2026-11-14"],
        "stock_sessions": ["2026-11-14"],
        "benchmark_sessions": ["2026-11-14"],
    }
    with pytest.raises(ContractError, match="weekend"):
        _next_common_session("2026-11-13T08:00:00+08:00", sessions)


def test_session_guard_returns_pending_when_next_session_unconfirmed() -> None:
    sessions = {
        "twse_sessions": ["2026-11-13"],
        "stock_sessions": ["2026-11-13"],
        "benchmark_sessions": ["2026-11-13"],
    }
    assert _next_common_session("2026-11-13T08:00:00+08:00", sessions) is None


def test_snapshot_is_immutable_and_hash_reproducible(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "raw")
    first = store.write(
        identity="candidate-1", snapshot_type="MOPS",
        retrieved_at="2026-11-12T08:00:00+00:00", source_identifier="mops://2330",
        raw=b"official-response", normalized={"rows": 1},
    )
    second = store.write(
        identity="candidate-1", snapshot_type="MOPS",
        retrieved_at="2026-11-12T08:00:00+00:00", source_identifier="mops://2330",
        raw=b"official-response", normalized={"rows": 1},
    )
    assert first == second
    assert validate_snapshot_tree(tmp_path / "raw") == 1


def test_snapshot_tampering_is_detected(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "raw")
    manifest = store.write(
        identity="candidate-1", snapshot_type="FINANCIAL",
        retrieved_at="2026-11-12T08:00:00+00:00", source_identifier="finmind://2330",
        raw=b"numbers",
    )
    manifest_path = next((tmp_path / "raw").glob("*/*/manifest.json"))
    (manifest_path.parent / "raw.bin").write_bytes(b"changed")
    with pytest.raises(ContractError, match="hash mismatch"):
        SnapshotStore.validate_manifest(manifest_path)
    assert manifest["source_sha256"] != "0" * 64


def test_content_addressed_store_deduplicates_identical_body(tmp_path: Path) -> None:
    store = ContentAddressedSourceStore(tmp_path / "source_blobs", tmp_path / "raw")
    first = store.put(b"same-official-body")
    second = store.put(b"same-official-body")
    assert first["changed"] is True
    assert second["status"] == "UNCHANGED_SOURCE"
    assert second["previous_snapshot_reference"]
    assert store.validate_all() == 1


def test_content_addressed_store_writes_changed_body_once(tmp_path: Path) -> None:
    store = ContentAddressedSourceStore(tmp_path / "source_blobs", tmp_path / "raw")
    assert store.put(b"version-1")["new_blob"] is True
    assert store.put(b"version-2")["new_blob"] is True
    assert store.validate_all() == 2


def test_content_addressed_store_reuses_legacy_oos_b_snapshot(tmp_path: Path) -> None:
    legacy = SnapshotStore(tmp_path / "raw")
    legacy.write(
        identity="scan-1",
        snapshot_type="MOPS",
        retrieved_at="2026-09-11T00:00:00+00:00",
        source_identifier="mops://2330",
        raw=b"legacy-body",
    )
    store = ContentAddressedSourceStore(tmp_path / "source_blobs", tmp_path / "raw")
    result = store.put(b"legacy-body")
    assert result["status"] == "UNCHANGED_SOURCE"
    assert result["new_blob"] is False
    assert store.validate_all() == 0


def test_collector_runtime_freeze_matches_manifest(contract: dict[str, object]) -> None:
    result = verify_collector_runtime_freeze(
        ROOT, manifest_path=str(contract["collector_runtime_manifest_path"])
    )
    assert result["status"] == "PASS"
    assert result["runtime_path_count"] >= 18


def test_scheduled_write_allowlist_fails_closed() -> None:
    assert "artifacts/0050_fundamental_oos_v0_1/runs/" in SCHEDULED_WRITE_ALLOWLIST
    allowed = assert_scheduled_write_allowlist(
        ROOT,
        [
            "data/research/0050_fundamental_oos_v0_1/oos_pending_candidates.json",
            "artifacts/0050_fundamental_oos_v0_1/source_blobs/a.bin",
        ],
    )
    assert len(allowed) == 2
    with pytest.raises(ContractError, match="NON_ALLOWLISTED"):
        assert_scheduled_write_allowlist(ROOT, ["experiments/fundamental_oos_shadow/live.py"])


class _NoOpSource:
    def __init__(self) -> None:
        self.network_requests = {"MOPS": 0, "FinMind": 0, "TWSE": 0, "Other": 0}

    def scan_mops(self, symbol: str) -> tuple[dict[str, object], bytes]:
        self.network_requests["MOPS"] += 1
        raw = f"official-{symbol}".encode()
        return {
            "symbol": symbol,
            "source_url": f"mops://{symbol}",
            "retrieval_timestamp": "2026-09-11T16:00:00+08:00",
            "response_sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "records": [],
            "source_conflicts": [],
        }, raw

    def financial(self, symbol: str, start: str, end: str) -> tuple[dict[str, object], bytes]:
        raise AssertionError("no candidate must not fetch financial data")

    def valuation(self, symbol: str, start: str, end: str) -> tuple[dict[str, object], bytes]:
        raise AssertionError("no candidate must not fetch valuation data")

    def sessions(self, symbol: str, start: str, end: str) -> tuple[dict[str, object], bytes]:
        raise AssertionError("no candidate must not fetch sessions")


def _minimal_collection_root(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    (tmp_path / "data").mkdir()
    (tmp_path / "data/universe.csv").write_text(
        "symbol,company,sector_logic,peer_group,financial_subtype\n2330,TSMC,GENERAL,TECH,\n",
        encoding="utf-8",
    )
    (tmp_path / "data/signals.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "data/outcomes.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "data/pending.json").write_text(
        '{"candidates":[],"registry_version":"OOS-C-1"}\n', encoding="utf-8"
    )
    (tmp_path / "model.json").write_text('{"history_start":"2016-01-01"}\n', encoding="utf-8")
    contract: dict[str, object] = {
        "stage": "OOS-C",
        "live_collection_enabled": True,
        "live_collection_mode": "MANUAL_AND_SCHEDULED_ENGINE",
        "scheduled_collection_prepared": True,
        "scheduled_collection_active": False,
        "historical_backfill_enabled": False,
        "outcome_calculation_enabled": False,
        "signal_ledger_path": "data/signals.jsonl",
        "outcome_ledger_path": "data/outcomes.jsonl",
        "pending_candidate_registry_path": "data/pending.json",
        "raw_snapshot_root": "artifacts/raw",
        "source_blob_root": "artifacts/source_blobs",
        "run_manifest_root": "artifacts/runs",
        "frozen_universe_path": "data/universe.csv",
        "frozen_model_config_path": "model.json",
        "frozen_model_hash": "a" * 64,
        "frozen_universe_hash": "b" * 64,
        "oos_start_timestamp": "2026-09-11T00:00:00+08:00",
        "frozen_cohort_count": 1,
        "expected_non_financial": 1,
        "collector_runtime_manifest_path": "config/runtime.json",
    }
    return tmp_path, contract


def test_noop_scheduled_run_is_bounded_and_deduplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, minimal = _minimal_collection_root(tmp_path)
    monkeypatch.setattr(
        "experiments.fundamental_oos_shadow.live.verify_freeze", lambda *args: {"status": "PASS"}
    )
    monkeypatch.setattr(
        "experiments.fundamental_oos_shadow.live.verify_collector_runtime_freeze",
        lambda *args, **kwargs: {
            "status": "PASS",
            "collector_runtime_freeze_sha": "c" * 64,
        },
    )
    first = run_collection(
        root,
        minimal,
        _NoOpSource(),
        mode="SCHEDULED",
        now=lambda: datetime(2026, 9, 11, 14, 30, tzinfo=timezone.utc),
        enforce_repository_guards=False,
    )
    second = run_collection(
        root,
        minimal,
        _NoOpSource(),
        mode="SCHEDULED",
        now=lambda: datetime(2026, 9, 12, 14, 30, tzinfo=timezone.utc),
        enforce_repository_guards=False,
    )
    assert first["new_blobs"] == 1
    assert second["new_blobs"] == 0
    assert second["unchanged_source_bodies"] == 1
    assert second["duplicate_blobs_avoided"] == 1
    assert second["commit_worthy_state_change"] is False
    assert len(list((root / "artifacts/runs").glob("*.json"))) == 2
    assert sum(path.stat().st_size for path in (root / "artifacts/runs").glob("*.json")) < 20_000


def test_manual_and_scheduled_wrappers_share_collection_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modes: list[str] = []

    def fake_engine(*args: object, mode: str, **kwargs: object) -> dict[str, object]:
        modes.append(mode)
        return {"mode": mode}

    monkeypatch.setattr("experiments.fundamental_oos_shadow.live.run_collection", fake_engine)
    run_live_collection(tmp_path, {}, _NoOpSource())
    run_scheduled_collection(tmp_path, {}, _NoOpSource(), enforce_repository_guards=False)
    assert modes == ["MANUAL", "SCHEDULED"]


def test_atomic_append_failure_leaves_ledger_unchanged(
    tmp_path: Path, contract: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    ledger = tmp_path / "signals.jsonl"
    ledger.write_text("", encoding="utf-8")
    sessions = payload["session_snapshot"]

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        append_signal_record(
            ledger, payload["signal"], contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )
    assert ledger.read_bytes() == b""


def test_duplicate_signal_append_fails_closed(
    tmp_path: Path, contract: dict[str, object]
) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    ledger = tmp_path / "signals.jsonl"
    ledger.write_text("", encoding="utf-8")
    sessions = payload["session_snapshot"]
    append_signal_record(
        ledger, payload["signal"], contract,
        twse_sessions=sessions["twse_sessions"], stock_sessions=sessions["stock_sessions"],
        benchmark_sessions=sessions["benchmark_sessions"],
    )
    before = ledger.read_bytes()
    with pytest.raises(LedgerError, match="Duplicate event_id"):
        append_signal_record(
            ledger, payload["signal"], contract,
            twse_sessions=sessions["twse_sessions"], stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )
    assert ledger.read_bytes() == before
    assert len(validate_signal_ledger(ledger)) == 1


def test_offline_import_and_validation_do_not_connect(
    monkeypatch: pytest.MonkeyPatch, contract: dict[str, object]
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    assert contract["stage"] == "OOS-C"
    assert validate_signal_ledger(ROOT / str(contract["signal_ledger_path"])) == []


def test_scheduler_prepared_but_inactive_and_no_composite_score(contract: dict[str, object]) -> None:
    schema = json.loads(
        (ROOT / "data/research/0050_fundamental_oos_v0_1/schemas/oos_signal_record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["scheduled_collection_enabled"] is False
    assert contract["scheduled_collection_prepared"] is True
    assert contract["scheduled_collection_active"] is False
    assert contract["no_composite_score"] is True
    assert "composite_score" not in schema["properties"]
