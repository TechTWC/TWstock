from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil

import pytest

from scripts.audit_fundamental_external_universe_e0_v0_1 import (
    PROHIBITED_OUTCOME_COLUMNS,
    inspect_external_input,
    run_audit,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/fundamental_external_universe_e0_v0_1.json"
ARTIFACTS = ROOT / "artifacts/fundamental_external_universe_e0_v0_1"


def _write_csv(path: Path, columns: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def _copy_frozen_inputs(root: Path) -> None:
    for relative in (
        "config/fundamental_quality_valuation_v0_1.json",
        "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv",
        "artifacts/0050_fundamental_v0_1/0050_normalized_financials_pit_v0.1.csv",
        "artifacts/0050_fundamental_v0_1/checkpoints/mops_20260904/checkpoint.json",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def test_tracked_e0_manifest_fails_closed_before_external_inputs_exist() -> None:
    manifest = json.loads((ARTIFACTS / "e0_readiness_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "DATA_NOT_READY"
    assert manifest["e1_return_analysis_gate"] == "BLOCKED"
    assert manifest["governance"]["future_returns_computed"] is False
    assert manifest["governance"]["outcome_files_read"] == []
    assert all(not row["path"].startswith("/") for row in manifest["external_inputs"])
    assert manifest["frozen_repository_coverage"] == {
        "current_0050_universe_rows": 50,
        "current_0050_unique_symbols": 50,
        "current_0050_non_financial_symbols": 38,
        "current_0050_financial_symbols": 12,
        "normalized_financial_rows": 2067,
        "normalized_financial_unique_symbols": 50,
        "normalized_external_symbols": 0,
        "mops_checkpoint_successful_company_archives": 50,
        "historical_membership_available": False,
        "survivorship_or_delisting_coverage_available": False,
    }


def test_repository_audit_reproduces_tracked_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "artifacts"
    actual = run_audit(ROOT, CONFIG, output)
    expected = json.loads((ARTIFACTS / "e0_readiness_manifest.json").read_text(encoding="utf-8"))
    assert actual == expected
    for name in (
        "e0_readiness_manifest.json",
        "e0_input_inventory.csv",
        "e0_stop_conditions.csv",
        "e0_expected_support.csv",
    ):
        assert (output / name).read_bytes() == (ARTIFACTS / name).read_bytes()


def test_outcome_column_is_rejected_in_e0(tmp_path: Path) -> None:
    path = tmp_path / "historical_external_membership.csv"
    columns = [
        "observation_date", "symbol", "company", "sector_logic", "cohort_eligible",
        "is_0050_member", "source_url", "source_published_at", "source_sha256",
        "excess_return",
    ]
    _write_csv(
        path,
        columns,
        [["2020-01-02", "1234", "A", "GENERAL", "true", "false", "https://example.invalid", "2019-12-31", "a" * 64, "0.10"]],
    )
    result = inspect_external_input("historical_membership", path)
    assert result["status"] == "REJECTED_OUTCOME_DATA"
    assert "excess_return" in result["detail"]


def test_all_named_outcome_columns_are_forbidden() -> None:
    assert {"exit_date", "forward_return", "excess_return", "outperform_0050"} <= PROHIBITED_OUTCOME_COLUMNS


def test_primary_cohort_is_frozen_before_outcomes() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["primary_cohort_policy"] == "HISTORICAL_PIT_TAIWAN_MID_CAP_100_NON_FINANCIAL_EX_0050"
    assert config["no_future_returns"] is True
    source = (ROOT / "scripts/audit_fundamental_external_universe_e0_v0_1.py").read_text(encoding="utf-8")
    assert "0050_predictive_events" not in source
    assert "0050_backtest_events" not in source
    assert "0050_return_diagnostics" not in source


def test_complete_pre_outcome_inputs_only_advance_to_independent_review(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _copy_frozen_inputs(root)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config_path = root / "config/fundamental_external_universe_e0_v0_1.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    external = root / config["external_input_root"]
    symbols = [f"1{index:03d}" for index in range(1, 6)]

    _write_csv(
        external / config["required_external_inputs"]["historical_membership"],
        [
            "observation_date", "symbol", "company", "index_name", "sector_logic",
            "cohort_eligible", "is_0050_member", "source_url", "source_published_at",
            "source_sha256",
        ],
        [
            ["2020-01-02", symbol, f"Company {symbol}", "TAIWAN_MID_CAP_100", "GENERAL", "true", "false", "https://example.invalid", "2019-12-31", "a" * 64]
            for symbol in symbols
        ],
    )
    _write_csv(
        external / config["required_external_inputs"]["security_master"],
        [
            "symbol", "listing_date", "delisting_date", "security_type", "status",
            "source_scope", "source_url", "source_as_of", "source_sha256",
        ],
        [
            [symbol, "2010-01-01", "", "COMMON_STOCK", "ACTIVE", "HISTORICAL_ALL_LISTINGS", "https://example.invalid", "2026-09-11", "b" * 64]
            for symbol in symbols
        ],
    )
    _write_csv(
        external / config["required_external_inputs"]["mops_coverage"],
        [
            "symbol", "period_end", "announcement_timestamp", "availability_method",
            "source_identifier", "source_url", "source_sha256",
        ],
        [
            [symbol, "2019-12-31", "2020-03-31T15:00:00+08:00", "MOPS_EXACT", f"filing-{symbol}", "https://example.invalid", "c" * 64]
            for symbol in symbols
        ],
    )
    support_rows = []
    for dimension, buckets in config["primary_bucket_grid"].items():
        for bucket in buckets:
            for horizon in config["primary_horizons"]:
                support_rows.append([str(horizon), dimension, bucket, "30", "5", "PASS"])
    _write_csv(
        external / config["required_external_inputs"]["expected_support"],
        ["horizon", "dimension", "bucket", "expected_observations", "expected_unique_issuers", "support_status"],
        support_rows,
    )

    manifest = run_audit(root, config_path, root / "output")
    assert manifest["status"] == "READY_FOR_INDEPENDENT_E0_REVIEW"
    assert manifest["e1_return_analysis_gate"] == "PENDING_INDEPENDENT_E0_REVIEW"
    assert manifest["governance"]["future_returns_computed"] is False
    assert manifest["governance"]["external_cohort_frozen"] is True


def test_frozen_identity_mismatch_stops_audit(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _copy_frozen_inputs(root)
    changed_config = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed_config["frozen_model_hash"] = "0" * 64
    config_path = root / "e0.json"
    config_path.write_text(json.dumps(changed_config), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen model hash mismatch"):
        run_audit(root, config_path, root / "output")
