from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from experiments.fundamental_oos_shadow.ledger import ContractError, load_contract, verify_freeze
from experiments.fundamental_oos_shadow.scheduled import (
    RUNTIME_MANIFEST_PATH,
    audit_runtime_manifest_dependencies,
    build_runtime_manifest,
    load_runtime_manifest,
    runtime_manifest_sha,
    verify_collector_code_baseline,
    verify_collector_runtime_freeze,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config/fundamental_oos_shadow_v0_1.json"
KNOWN_RUNTIME_DEPENDENCIES = {
    "scripts/run_0050_fundamental_oos_v0_1.py",
    "experiments/fundamental_oos_shadow/__init__.py",
    "experiments/fundamental_oos_shadow/ledger.py",
    "experiments/fundamental_oos_shadow/live.py",
    "experiments/fundamental_oos_shadow/scheduled.py",
    "experiments/fundamental_quality_valuation/data.py",
    "experiments/fundamental_quality_valuation/engine.py",
    "experiments/fundamental_quality_valuation/models.py",
    "experiments/fundamental_quality_valuation/mops.py",
    "experiments/fundamental_quality_valuation/stage_a.py",
    "experiments/fundamental_quality_valuation/pit.py",
    "experiments/fundamental_quality_valuation/session_contract.py",
    "requirements-dev.txt",
}


def _runtime_paths(root: Path = ROOT) -> list[str]:
    return [
        str(entry["runtime_path"])
        for entry in load_runtime_manifest(root)["runtime_paths"]
    ]


def _copy_runtime_fixture(tmp_path: Path) -> Path:
    for relative in _runtime_paths():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    manifest = tmp_path / RUNTIME_MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / RUNTIME_MANIFEST_PATH, manifest)
    return tmp_path


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repository(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Runtime Guard Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "runtime baseline")
    return _git(root, "rev-parse", "HEAD")


def test_runtime_manifest_is_deterministic_and_canonically_ordered(tmp_path: Path) -> None:
    (tmp_path / "b").write_text("two\n", encoding="utf-8")
    (tmp_path / "a").write_text("one\n", encoding="utf-8")
    first = build_runtime_manifest(tmp_path, ["b", "a"])
    second = build_runtime_manifest(tmp_path, ["a", "b"])
    assert first == second
    assert [entry["runtime_path"] for entry in first["runtime_paths"]] == ["a", "b"]
    assert runtime_manifest_sha(first) == runtime_manifest_sha(second)


def test_all_known_runtime_dependencies_are_included() -> None:
    report = verify_collector_runtime_freeze(ROOT)
    assert report["status"] == "PASS"
    assert KNOWN_RUNTIME_DEPENDENCIES <= set(report["runtime_paths"])
    assert report["runtime_path_count"] == 18
    assert report["static_import_audit"]["status"] == "PASS"


def test_omitted_imported_runtime_dependency_fails_closed() -> None:
    declared = set(_runtime_paths()) - {
        "experiments/fundamental_quality_valuation/engine.py"
    }
    with pytest.raises(ContractError, match="RUNTIME_DEPENDENCY_OMITTED.*engine.py"):
        audit_runtime_manifest_dependencies(ROOT, declared)


@pytest.mark.parametrize(
    "relative",
    [
        "experiments/fundamental_quality_valuation/engine.py",
        "experiments/fundamental_quality_valuation/data.py",
        "experiments/fundamental_quality_valuation/models.py",
        "experiments/fundamental_quality_valuation/mops.py",
        "experiments/fundamental_quality_valuation/stage_a.py",
        "requirements-dev.txt",
        "experiments/fundamental_oos_shadow/live.py",
    ],
)
def test_runtime_dependency_drift_is_detected(tmp_path: Path, relative: str) -> None:
    root = _copy_runtime_fixture(tmp_path)
    with (root / relative).open("a", encoding="utf-8") as handle:
        handle.write("\n# simulated drift\n")
    with pytest.raises(ContractError, match="COLLECTOR_RUNTIME_DRIFT"):
        verify_collector_runtime_freeze(root)


def test_mutable_oos_data_does_not_change_runtime_hash(tmp_path: Path) -> None:
    root = _copy_runtime_fixture(tmp_path)
    before = verify_collector_runtime_freeze(root)["collector_runtime_freeze_sha"]
    mutable = [
        "data/research/0050_fundamental_oos_v0_1/oos_signal_ledger.jsonl",
        "artifacts/0050_fundamental_oos_v0_1/source_blobs/body.bin",
        "artifacts/0050_fundamental_oos_v0_1/runs/run.json",
    ]
    for relative in mutable:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("changed\n", encoding="utf-8")
    after = verify_collector_runtime_freeze(root)["collector_runtime_freeze_sha"]
    assert before == after


def test_adversarial_self_attestation_is_rejected(tmp_path: Path) -> None:
    root = _copy_runtime_fixture(tmp_path)
    baseline_expected = verify_collector_runtime_freeze(root)[
        "collector_runtime_freeze_sha"
    ]
    baseline = _init_repository(root)
    engine = root / "experiments/fundamental_quality_valuation/engine.py"
    engine.write_text(engine.read_text(encoding="utf-8") + "\n# attacker drift\n", encoding="utf-8")
    replacement = build_runtime_manifest(root, _runtime_paths(root))
    (root / RUNTIME_MANIFEST_PATH).write_text(
        json.dumps(replacement, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "simulate branch-local self-attestation")
    with pytest.raises(ContractError, match="COLLECTOR_RUNTIME_FREEZE_MISMATCH"):
        verify_collector_runtime_freeze(root, expected_sha=str(baseline_expected))
    with pytest.raises(ContractError, match="COLLECTOR_CODE_DRIFT"):
        verify_collector_code_baseline(root, baseline)


def test_data_only_branch_advancement_is_accepted(tmp_path: Path) -> None:
    root = _copy_runtime_fixture(tmp_path)
    baseline = _init_repository(root)
    ledger = root / "data/research/0050_fundamental_oos_v0_1/oos_signal_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"record":"data-only"}\n', encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "data-only advancement")
    report = verify_collector_code_baseline(root, baseline)
    assert report["status"] == "PASS"
    assert report["protected_path_count"] == 19


def test_frozen_identities_and_oos_governance_remain_unchanged() -> None:
    contract = load_contract(CONTRACT_PATH)
    result = verify_freeze(ROOT, contract)
    assert all(result["checks"].values())
    assert contract["frozen_model_hash"] == (
        "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f"
    )
    assert contract["frozen_universe_hash"] == (
        "aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46"
    )
    assert contract["oos_start_timestamp"] == "2026-09-11T00:00:00+08:00"
    assert contract["outcome_calculation_enabled"] is False
