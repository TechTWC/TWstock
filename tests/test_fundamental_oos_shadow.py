from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pandas as pd
import pytest

from experiments.fundamental_oos_shadow.ledger import (
    GENESIS,
    ContractError,
    LedgerError,
    append_outcome_record,
    append_signal_record,
    load_contract,
    record_hash,
    validate_fixture,
    validate_outcome_ledger,
    validate_signal_ledger,
    verify_freeze,
)
from scripts.run_0050_fundamental_oos_v0_1 import main as cli_main


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/fundamental_oos_shadow_v0_1.json"
FIXTURE_PATH = ROOT / "tests/fixtures/fundamental_oos_shadow/oos_a_valid_fixture.json"
SIGNAL_LEDGER = ROOT / "data/research/0050_fundamental_oos_v0_1/oos_signal_ledger.jsonl"
OUTCOME_LEDGER = ROOT / "data/research/0050_fundamental_oos_v0_1/oos_outcome_ledger.jsonl"


@pytest.fixture
def contract() -> dict[str, object]:
    return load_contract(CONTRACT_PATH)


@pytest.fixture
def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _sessions(payload: dict[str, object]) -> dict[str, list[str]]:
    return payload["session_snapshot"]  # type: ignore[return-value]


def _candidate(payload: dict[str, object]) -> dict[str, object]:
    return deepcopy(payload["signal"])  # type: ignore[return-value]


def _empty_ledger(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text("", encoding="utf-8")
    return path


def _append_valid_signal(
    path: Path,
    contract: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    sessions = _sessions(payload)
    return append_signal_record(
        path,
        _candidate(payload),
        contract,
        twse_sessions=sessions["twse_sessions"],
        stock_sessions=sessions["stock_sessions"],
        benchmark_sessions=sessions["benchmark_sessions"],
    )


def _business_sessions(count: int = 70) -> list[str]:
    return [item.date().isoformat() for item in pd.bdate_range("2026-11-16", periods=count)]


def _pending_outcome() -> dict[str, object]:
    return {
        "outcome_event_id": "0050-FQV-OOS-2330-2026Q3-001:60:PENDING",
        "event_id": "0050-FQV-OOS-2330-2026Q3-001",
        "horizon_trading_days": 60,
        "status": "PENDING",
        "entry_date": "2026-11-16",
        "exit_date": None,
        "stock_return": None,
        "0050_return": None,
        "excess_return": None,
        "stock_source_hash": None,
        "benchmark_source_hash": None,
        "session_source_hash": None,
        "calculated_at": "2026-11-17T18:00:00+08:00",
    }


def _matured_outcome(sessions: list[str]) -> dict[str, object]:
    return {
        "outcome_event_id": "0050-FQV-OOS-2330-2026Q3-001:60:MATURED",
        "event_id": "0050-FQV-OOS-2330-2026Q3-001",
        "horizon_trading_days": 60,
        "status": "MATURED",
        "entry_date": "2026-11-16",
        "exit_date": sessions[60],
        "stock_return": 0.20,
        "0050_return": 0.10,
        "excess_return": 0.10,
        "stock_source_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "benchmark_source_hash": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "session_source_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "calculated_at": f"{sessions[60]}T18:00:00+08:00",
    }


def test_freeze_head_and_contract_are_exact(contract: dict[str, object]) -> None:
    assert contract["freeze_head"] == "188aa8120a6c35b3b6377490f1ed9456566824bd"
    assert contract["oos_start_timestamp"] == "2026-09-11T00:00:00+08:00"
    assert contract["primary_horizons"] == [60, 120, 252, 504]


def test_frozen_model_universe_and_cohort_identity(contract: dict[str, object]) -> None:
    result = verify_freeze(ROOT, contract)
    assert result["actual_model_hash"] == contract["frozen_model_hash"]
    assert result["actual_universe_hash"] == contract["frozen_universe_hash"]
    assert result["frozen_cohort"] == 50
    assert result["eligible_non_financial"] == 38
    assert result["excluded_financial"] == 12


def test_initial_ledgers_are_separate_and_empty() -> None:
    assert SIGNAL_LEDGER != OUTCOME_LEDGER
    assert validate_signal_ledger(SIGNAL_LEDGER) == []
    assert validate_outcome_ledger(OUTCOME_LEDGER) == []


def test_valid_fixture_is_deterministic(
    contract: dict[str, object], fixture_payload: dict[str, object]
) -> None:
    first = validate_fixture(fixture_payload, contract)
    second = validate_fixture(fixture_payload, contract)
    assert first == second
    assert first["previous_record_hash"] == GENESIS
    assert first["record_hash"] == record_hash(first)


def test_pre_oos_event_and_historical_backfill_fail_closed(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate["period_end"] = "2026-06-30"
    candidate["mops_announcement_timestamp"] = "2026-08-14T15:00:00+08:00"
    ledger = _empty_ledger(tmp_path, "signals.jsonl")
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="PRE_OOS_EXCLUDED"):
        append_signal_record(
            ledger,
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )
    assert ledger.read_text(encoding="utf-8") == ""


def test_pending_numeric_source_never_creates_signal(
    contract: dict[str, object], fixture_payload: dict[str, object]
) -> None:
    payload = deepcopy(fixture_payload)
    payload["source_snapshots"][1]["processing_status"] = "PENDING_DATA"  # type: ignore[index]
    payload["source_snapshots"][1]["sha256"] = None  # type: ignore[index]
    with pytest.raises(ContractError, match="PENDING_DATA"):
        validate_fixture(payload, contract)


def test_information_cutoff_is_conservative_maximum(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate["information_cutoff_timestamp"] = "2026-11-13T15:05:00+08:00"
    with pytest.raises(ContractError, match="conservative maximum"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            candidate,
            contract,
            **{
                "twse_sessions": _sessions(fixture_payload)["twse_sessions"],
                "stock_sessions": _sessions(fixture_payload)["stock_sessions"],
                "benchmark_sessions": _sessions(fixture_payload)["benchmark_sessions"],
            },
        )


def test_signal_cannot_precede_latest_source_availability(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate["valuation_source_retrieved_at"] = "2026-11-14T15:00:00+08:00"
    candidate["information_cutoff_timestamp"] = "2026-11-14T15:00:00+08:00"
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="generated before"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )


def test_financial_issuer_is_never_predictive_eligible(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate.update({"symbol": "2881", "company": "富邦金", "sector_logic": "FINANCIAL"})
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="FINANCIAL_ISSUER"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )


def test_financial_issuer_cannot_masquerade_as_general(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate.update({"symbol": "2881", "company": "富邦金", "sector_logic": "GENERAL"})
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="FINANCIAL_ISSUER"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )


@pytest.mark.parametrize("field", ["model_hash", "universe_hash"])
def test_frozen_hash_mismatch_fails_closed(
    field: str,
    contract: dict[str, object],
    fixture_payload: dict[str, object],
    tmp_path: Path,
) -> None:
    candidate = _candidate(fixture_payload)
    candidate[field] = "0" * 64
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="hash mismatch"):
        append_signal_record(
            _empty_ledger(tmp_path, f"{field}.jsonl"),
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )


def test_signal_ledger_append_only_and_duplicate_event_fails(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    ledger = _empty_ledger(tmp_path, "signals.jsonl")
    first = _append_valid_signal(ledger, contract, fixture_payload)
    original = ledger.read_bytes()
    with pytest.raises(LedgerError, match="Duplicate event_id"):
        _append_valid_signal(ledger, contract, fixture_payload)
    assert ledger.read_bytes() == original
    assert validate_signal_ledger(ledger) == [first]


def test_sequence_gap_and_previous_hash_mismatch_fail_closed(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    ledger = _empty_ledger(tmp_path, "signals.jsonl")
    first = _append_valid_signal(ledger, contract, fixture_payload)
    second = deepcopy(first)
    second["event_id"] = "second"
    second["sequence_number"] = 3
    second["previous_record_hash"] = first["record_hash"]
    second["record_hash"] = record_hash(second)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(second) + "\n")
    with pytest.raises(LedgerError, match="sequence"):
        validate_signal_ledger(ledger)

    second["sequence_number"] = 2
    second["previous_record_hash"] = "0" * 64
    second["record_hash"] = record_hash(second)
    ledger.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="previous_record_hash"):
        validate_signal_ledger(ledger)


def test_modifying_old_record_is_detected(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    ledger = _empty_ledger(tmp_path, "signals.jsonl")
    _append_valid_signal(ledger, contract, fixture_payload)
    tampered = json.loads(ledger.read_text(encoding="utf-8"))
    tampered["quality"] = "WEAK"
    ledger.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="record_hash mismatch"):
        validate_signal_ledger(ledger)


def test_superseding_event_preserves_original(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    ledger = _empty_ledger(tmp_path, "signals.jsonl")
    original = _append_valid_signal(ledger, contract, fixture_payload)
    correction = _candidate(fixture_payload)
    correction.update(
        {
            "event_id": "0050-FQV-OOS-2330-2026Q3-001-C1",
            "status": "SUPERSEDING_EVENT",
            "supersedes_event_id": original["event_id"],
            "reason_codes": ["SOURCE_CORRECTION"],
        }
    )
    sessions = _sessions(fixture_payload)
    append_signal_record(
        ledger,
        correction,
        contract,
        twse_sessions=sessions["twse_sessions"],
        stock_sessions=sessions["stock_sessions"],
        benchmark_sessions=sessions["benchmark_sessions"],
    )
    records = validate_signal_ledger(ledger)
    assert len(records) == 2
    assert records[0] == original
    assert records[1]["supersedes_event_id"] == original["event_id"]


def test_first_trade_date_must_be_first_common_legal_session(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    candidate = _candidate(fixture_payload)
    candidate["first_trade_date"] = "2026-11-17"
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="first accepted common"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            candidate,
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=sessions["benchmark_sessions"],
        )


def test_missing_benchmark_session_fails_closed(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    sessions = _sessions(fixture_payload)
    with pytest.raises(ContractError, match="first accepted common"):
        append_signal_record(
            _empty_ledger(tmp_path, "signals.jsonl"),
            _candidate(fixture_payload),
            contract,
            twse_sessions=sessions["twse_sessions"],
            stock_sessions=sessions["stock_sessions"],
            benchmark_sessions=["2026-11-13", "2026-11-17"],
        )


def test_outcome_cannot_mature_before_horizon(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    signal = validate_fixture(fixture_payload, contract)
    sessions = _business_sessions()
    outcome = _matured_outcome(sessions)
    with pytest.raises(ContractError, match="OUTCOME_NOT_MATURED"):
        append_outcome_record(
            _empty_ledger(tmp_path, "outcomes.jsonl"),
            outcome,
            contract,
            signal=signal,
            common_sessions=sessions,
            as_of=sessions[20],
        )


def test_pending_outcome_has_no_returns_and_matures_append_only(
    contract: dict[str, object], fixture_payload: dict[str, object], tmp_path: Path
) -> None:
    signal = validate_fixture(fixture_payload, contract)
    sessions = _business_sessions()
    ledger = _empty_ledger(tmp_path, "outcomes.jsonl")
    pending = append_outcome_record(
        ledger,
        _pending_outcome(),
        contract,
        signal=signal,
        common_sessions=sessions,
        as_of="2026-11-17",
    )
    prefix = ledger.read_bytes()
    matured = append_outcome_record(
        ledger,
        _matured_outcome(sessions),
        contract,
        signal=signal,
        common_sessions=sessions,
        as_of=sessions[60],
    )
    assert ledger.read_bytes().startswith(prefix)
    assert pending["stock_return"] is None
    assert matured["exit_date"] == sessions[60]
    assert len(validate_outcome_ledger(ledger)) == 2


def test_live_mode_fails_closed() -> None:
    with pytest.raises(SystemExit, match="LIVE_COLLECTION_NOT_ENABLED_IN_OOS_A"):
        cli_main(["--live"])


def test_dry_run_makes_zero_network_connections(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def blocked_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("network connection attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    assert cli_main(["--dry-run", "--fixture", "--validate-ledger"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["network_requests"] == 0
    assert report["signal_ledger_records"] == 0
    assert report["outcome_ledger_records"] == 0
    assert report["fixture"]["persisted"] is False


def test_frozen_fundamental_and_technical_paths_are_untouched(contract: dict[str, object]) -> None:
    paths = [
        "config/fundamental_quality_valuation_v0_1.json",
        "experiments/fundamental_quality_valuation",
        "twstock_engine",
    ]
    result = subprocess.run(
        ["git", "diff", "--name-only", str(contract["freeze_head"]), "--", *paths],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ""


def test_no_composite_score_and_future_snooping_guards(contract: dict[str, object]) -> None:
    signal_schema = json.loads(
        (ROOT / "data/research/0050_fundamental_oos_v0_1/schemas/oos_signal_record.schema.json").read_text()
    )
    assert contract["no_threshold_change"] is True
    assert contract["no_retroactive_backfill"] is True
    assert contract["no_composite_score"] is True
    assert contract["live_collection_enabled"] is False
    assert "composite_score" not in signal_schema["properties"]


def test_all_machine_readable_json_and_schemas_parse() -> None:
    paths = [CONTRACT_PATH, FIXTURE_PATH]
    paths.extend((ROOT / "data/research/0050_fundamental_oos_v0_1/schemas").glob("*.json"))
    for path in paths:
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
