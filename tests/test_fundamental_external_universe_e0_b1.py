from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.reconstruct_fundamental_external_universe_e0_b1_v0_1 import (
    apply_interim_replacement,
    canonical_model_hash,
    financial_eligible,
    quarter_intervals,
    reject_outcome_fields,
    require_seed,
    retain_lifecycle_rows,
    run_reconstruction,
    sha256_path,
    validate_membership_rows,
    validate_official_url,
    validate_raw_source,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/fundamental_external_universe_e0_b1_v0_1.json"
ARTIFACTS = ROOT / "artifacts/fundamental_external_universe_e0_v0_1"
DATA = ROOT / "data/research/fundamental_external_universe_e0_b1_v0_1"
ALLOWED_HOSTS = {"taiwanindex.com.tw", "backend.taiwanindex.com.tw", "twse.com.tw"}


def membership_row(**overrides: str) -> dict[str, str]:
    row = {
        "index_name": "TAIWAN_50",
        "symbol": "1101",
        "company_name": "A",
        "membership_start": "2020-01-01",
        "membership_end": "2020-03-31",
        "effective_from": "2020-01-01",
        "effective_to": "2020-03-31",
        "event_type": "SEED",
        "event_source_date": "2019-12-01",
        "source_url": "https://taiwanindex.com.tw/news/1",
        "source_authority": "TAIWAN_INDEX_PLUS",
        "source_sha256": "a" * 64,
        "pit_verified": "true",
        "verification_note": "",
    }
    row.update(overrides)
    return row


def test_seed_required() -> None:
    require_seed([membership_row()])


def test_no_seed_fails_closed() -> None:
    with pytest.raises(ValueError, match="seed"):
        require_seed([membership_row(event_type="REGULAR_ADDITION")])


def test_duplicate_membership_rejected() -> None:
    row = membership_row()
    with pytest.raises(ValueError, match="duplicate"):
        validate_membership_rows(
            [row, dict(row)], expected_counts={"TAIWAN_50": 2}, allowed_hosts=ALLOWED_HOSTS
        )


def test_overlapping_intervals_rejected() -> None:
    rows = [
        membership_row(effective_from="2020-01-01", effective_to="2020-03-31"),
        membership_row(effective_from="2020-03-31", effective_to="2020-06-30"),
    ]
    with pytest.raises(ValueError, match="overlapping"):
        validate_membership_rows(rows, expected_counts={"TAIWAN_50": 2}, allowed_hosts=ALLOWED_HOSTS)


def test_unexplained_entry_and_exit_rejected() -> None:
    with pytest.raises(ValueError, match="unexplained"):
        validate_membership_rows(
            [membership_row(event_type="UNKNOWN")],
            expected_counts={"TAIWAN_50": 1},
            allowed_hosts=ALLOWED_HOSTS,
        )


def test_expected_count_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="count mismatch"):
        validate_membership_rows(
            [membership_row()], expected_counts={"TAIWAN_50": 50}, allowed_hosts=ALLOWED_HOSTS
        )


def test_taiwan50_midcap_overlap_requires_explanation() -> None:
    rows = [membership_row(), membership_row(index_name="TAIWAN_MID_CAP_100")]
    with pytest.raises(ValueError, match="overlap"):
        validate_membership_rows(
            rows,
            expected_counts={"TAIWAN_50": 1, "TAIWAN_MID_CAP_100": 1},
            allowed_hosts=ALLOWED_HOSTS,
        )


def test_effective_date_boundary_is_inclusive_and_ordered() -> None:
    validate_membership_rows(
        [membership_row(effective_from="2020-01-01", effective_to="2020-01-01")],
        expected_counts={"TAIWAN_50": 1},
        allowed_hosts=ALLOWED_HOSTS,
    )
    with pytest.raises(ValueError, match="boundary"):
        validate_membership_rows(
            [membership_row(effective_from="2020-01-02", effective_to="2020-01-01")],
            expected_counts={"TAIWAN_50": 1},
            allowed_hosts=ALLOWED_HOSTS,
        )


def test_interim_replacement_handled() -> None:
    assert apply_interim_replacement({"1101", "1102"}, "1101", "1103") == {"1102", "1103"}
    with pytest.raises(ValueError, match="reconcile"):
        apply_interim_replacement({"1101"}, "9999", "1103")


def test_delisted_and_renamed_issuers_retained() -> None:
    rows = [
        {"symbol": "2823", "current_status": "DELISTED", "name_change": ""},
        {"symbol": "2883", "current_status": "ACTIVE", "name_change": "開發金->凱基金"},
    ]
    assert retain_lifecycle_rows(rows) == rows


def test_financial_exclusion_is_deterministic() -> None:
    assert financial_eligible("FINANCIAL") is False
    assert financial_eligible(" financial ") is False
    assert financial_eligible("TECHNOLOGY") is True


def test_outcome_fields_rejected() -> None:
    for field in ("future_return", "benchmark_return", "excess_return", "outperform", "forward_price"):
        with pytest.raises(ValueError, match="forbidden"):
            reject_outcome_fields([field])


def test_non_official_source_rejected_as_primary() -> None:
    with pytest.raises(ValueError, match="non-official"):
        validate_official_url("https://example.com/members.csv", ALLOWED_HOSTS)


def test_source_hash_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "source.bin"
    path.write_bytes(b"official-source")
    expected = hashlib.sha256(b"official-source").hexdigest()
    assert sha256_path(path) == expected == sha256_path(path)


def test_raw_source_is_immutable_by_hash(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "source.html"
    source.write_bytes(b"v1")
    expected = sha256_path(source)
    assert validate_raw_source(raw, "source.html", expected) == source
    source.write_bytes(b"v2")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_raw_source(raw, "source.html", expected)


def test_missing_provenance_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        validate_raw_source(tmp_path, "missing.pdf", "0" * 64)


def test_quarter_interval_coverage_is_complete() -> None:
    intervals = quarter_intervals(date(2019, 1, 1), date(2026, 9, 3))
    assert len(intervals) == 31
    assert intervals[0] == (date(2019, 1, 1), date(2019, 3, 31))
    assert intervals[-1] == (date(2026, 7, 1), date(2026, 9, 3))


def test_tracked_e0_b1_manifest_fails_closed_without_seed() -> None:
    manifest = json.loads((ARTIFACTS / "e0_b1_stage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "DATA_NOT_READY"
    assert manifest["e0_b2_gate"] == "BLOCKED"
    assert manifest["seed_snapshot"]["status"] == "FAIL"
    assert manifest["verified_membership_intervals"] == 0
    assert manifest["unverified_membership_intervals"] == 31
    assert manifest["governance"]["outcome_files_read"] == []
    assert manifest["governance"]["future_returns_computed"] is False


def test_frozen_model_hash_unchanged() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    model = json.loads((ROOT / config["frozen_model_config_path"]).read_text(encoding="utf-8"))
    assert canonical_model_hash(model) == config["frozen_model_hash"]


def test_repository_reconstruction_is_reproducible() -> None:
    before = {
        path.name: path.read_bytes()
        for path in (
            ARTIFACTS / "e0_b1_stage_manifest.json",
            ARTIFACTS / "membership_interval_audit.csv",
            ARTIFACTS / "historical_membership_coverage.csv",
            ARTIFACTS / "source_provenance_manifest.csv",
            DATA / "historical_external_membership.csv",
            DATA / "external_security_master.csv",
        )
    }
    manifest = run_reconstruction(ROOT, CONFIG)
    assert manifest["status"] == "DATA_NOT_READY"
    after = {path.name: path.read_bytes() for path in (
        ARTIFACTS / "e0_b1_stage_manifest.json",
        ARTIFACTS / "membership_interval_audit.csv",
        ARTIFACTS / "historical_membership_coverage.csv",
        ARTIFACTS / "source_provenance_manifest.csv",
        DATA / "historical_external_membership.csv",
        DATA / "external_security_master.csv",
    )}
    assert after == before


def test_pr32_pr33_scheduler_and_main_paths_untouched() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed = subprocess.run(
        ["git", "diff", "--name-only", config["starting_head"]],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    allowed_prefixes = (
        "artifacts/fundamental_external_universe_e0_v0_1/",
        "config/fundamental_external_universe_e0_b1_v0_1.json",
        "data/research/fundamental_external_universe_e0_b1_v0_1/",
        "docs/research/fundamental_external_universe_e0_b1_v0.1.md",
        "scripts/reconstruct_fundamental_external_universe_e0_b1_v0_1.py",
        "tests/test_fundamental_external_universe_e0_b1.py",
    )
    assert all(path.startswith(allowed_prefixes) for path in changed)
