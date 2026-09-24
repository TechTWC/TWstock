from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.fundamental_quality_valuation.session_contract import (
    EXPECTED_FROZEN_SESSION_SHA256,
    first_trade_date_is_valid,
    load_frozen_sessions,
)
from experiments.fundamental_quality_valuation.stage_a import canonical_hash
from experiments.fundamental_quality_valuation.stage_b import build_predictive_events
from experiments.fundamental_quality_valuation.test_reporting import targeted_test_reporting


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/0050_fundamental_v0_1"
SESSION_PATH = ROOT / "data/research/0050_fundamental_v0_1/frozen_twse_sessions_v0.1.csv"
SIGNAL_PATH = ARTIFACTS / "0050_pit_signal_timeline_v0.1.csv"
EVIDENCE_PATH = ARTIFACTS / "0050_predictive_evidence_v0.1.json"
MANIFEST_PATH = ARTIFACTS / "artifact_manifest.json"
MODEL_HASH = "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f"
UNIVERSE_HASH = "aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46"
AFFECTED = {"2345", "2368", "2454", "3653", "3661"}


def _evidence() -> dict[str, object]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _market() -> pd.DataFrame:
    dates = pd.bdate_range("2018-03-30", periods=100).date
    values = 100.0 * (1.001 ** np.arange(len(dates)))
    return pd.DataFrame({"date": dates, "adj_close": values, "close": values})


def _signal(entry: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": "1111", "period_end": "2017-12-31", "signal_date": "2018-03-30",
        "first_trade_date": entry, "quality": "GOOD", "fundamental_state": "STABLE",
        "state_detail": "CONFIRMED_GROWTH", "valuation": "NORMAL", "data_quality": "OK",
        "reason_codes": "TEST", "availability_method": "MOPS_EXACT", "source_hash": "a" * 64,
        "predictive_eligible": True,
    }])


def _universe() -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": "1111", "company": "A", "sector_logic": "GENERAL",
        "peer_group": "A", "financial_subtype": "",
    }])


def test_first_trade_dates_exist_in_frozen_session_calendar() -> None:
    sessions = set(load_frozen_sessions(SESSION_PATH))
    signals = pd.read_csv(SIGNAL_PATH)
    assert set(pd.to_datetime(signals["first_trade_date"]).dt.date) <= sessions


def test_weekend_cannot_pass_frozen_session_contract() -> None:
    sessions = load_frozen_sessions(SESSION_PATH)
    assert date(2018, 3, 31) not in sessions
    assert not first_trade_date_is_valid(date(2018, 3, 30), date(2018, 3, 31), sessions)


def test_weekday_non_session_cannot_pass_frozen_session_contract() -> None:
    sessions = load_frozen_sessions(SESSION_PATH)
    assert date(2018, 2, 15).weekday() < 5 and date(2018, 2, 15) not in sessions
    assert not first_trade_date_is_valid(date(2018, 2, 14), date(2018, 2, 15), sessions)


def test_invalid_session_fails_closed_in_stage_b() -> None:
    market = _market()
    events = build_predictive_events(
        _signal("2018-03-31"), _universe(), {"1111": market}, market,
        as_of=date(2018, 12, 31), frozen_sessions=tuple(market["date"]),
    )
    assert events.loc[0, "exclusion_reason"] == "ENTRY_NOT_FROZEN_SESSION"
    assert pd.isna(events.loc[0, "return_60d"])


def test_five_known_cases_no_longer_use_2018_03_31() -> None:
    signals = pd.read_csv(SIGNAL_PATH, dtype={"symbol": str})
    selected = signals[(signals["symbol"].isin(AFFECTED)) & (signals["period_end"] == "2017-12-31")]
    assert set(selected["symbol"]) == AFFECTED
    assert set(selected["first_trade_date"]) == {"2018-04-02"}


def test_stage_a_and_stage_b_use_same_session_contract_identity() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["stage_a"]["session_calendar_sha256"] == EXPECTED_FROZEN_SESSION_SHA256
    assert manifest["stage_b"]["frozen_identity"]["session_calendar_sha256"] == EXPECTED_FROZEN_SESSION_SHA256


def test_future_price_cannot_change_frozen_signal_fields() -> None:
    source = (ROOT / "experiments/fundamental_quality_valuation/stage_b.py").read_text(encoding="utf-8")
    assert "record = dict(row)" in source
    assert "record[\"valuation_frozen\"] = record[\"valuation\"]" in source


def test_frozen_model_hash_is_unchanged() -> None:
    config = json.loads((ROOT / "config/fundamental_quality_valuation_v0_1.json").read_text())
    actual = canonical_hash({"quality_rules": config["quality_rules"], "valuation_rules": config["valuation_rules"]})
    assert actual == MODEL_HASH


def test_frozen_universe_hash_is_unchanged() -> None:
    path = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == UNIVERSE_HASH


def test_mops_network_requests_are_zero() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["stage_a"]["mops_network_requests"] == 0
    assert manifest["stage_b"]["mops_network_requests"] == 0
    assert _evidence()["mops_network_requests"] == 0


def test_mechanical_and_primary_assessments_are_separate() -> None:
    evidence = _evidence()
    assert evidence["mechanical_rubric_grade"] == "STRONG"
    assert evidence["independent_reviewer_evidence_assessment"] == "MODERATE"


def test_primary_research_evidence_assessment_is_moderate() -> None:
    assert _evidence()["primary_research_evidence_assessment"] == "MODERATE"


def test_pre_registration_status_is_not_verifiable() -> None:
    evidence = _evidence()
    assert evidence["pre_registration_status"] == "NOT_VERIFIABLE"
    assert "immutable pre-result Git checkpoint" in evidence["pre_registration_explanation"]


def test_good_stable_is_disclosed_as_exploratory_among_23_cells() -> None:
    disclosure = _evidence()["good_x_stable_disclosure"]
    assert disclosure["supported_two_axis_cells_at_252d"] == 23
    assert disclosure["selection_status"] == "EX_POST_STRONGEST_SUPPORTED_CELL"
    assert disclosure["evidence_use"] == "EXPLORATORY_DESCRIPTIVE_ONLY"
    assert disclosure["winners_curse_risk"] is True


def test_targeted_test_count_reproduces_actual_collection() -> None:
    counts = targeted_test_reporting(ROOT)
    assert counts == {
        "original_stage_a": 22,
        "original_stage_b": 16,
        "original_targeted_tests": 38,
        "correction_regression_tests": 15,
        "current_total_targeted_tests": 53,
    }
