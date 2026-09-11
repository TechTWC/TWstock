from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/0050-fundamental-oos-shadow.yml"
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")
COLLECTOR_BASELINE = "c44f5f723b25e22b7d65adcbe9b8db23dabf58fc"
RUNTIME_FREEZE_SHA = "131ef2d6964d7169a647baede2d2c2c80205488db55acec7d79411b12ad78239"


def _step(name: str, next_name: str | None = None) -> str:
    start = WORKFLOW.index(f"- name: {name}")
    end = WORKFLOW.index(f"- name: {next_name}", start) if next_name else len(WORKFLOW)
    return WORKFLOW[start:end]


def test_scheduler_hard_codes_independent_runtime_identities() -> None:
    assert f"COLLECTOR_CODE_BASELINE_HEAD: {COLLECTOR_BASELINE}" in WORKFLOW
    assert f"EXPECTED_COLLECTOR_RUNTIME_FREEZE_SHA: {RUNTIME_FREEZE_SHA}" in WORKFLOW
    assert WORKFLOW.count(COLLECTOR_BASELINE) == 1
    assert WORKFLOW.count(RUNTIME_FREEZE_SHA) == 1


def test_expected_runtime_identity_is_not_self_sourced_from_oos_contract() -> None:
    guard = _step(
        "Verify independent runtime freeze and protected-path diff", "Set up Python"
    )
    assert 'os.environ["EXPECTED_COLLECTOR_RUNTIME_FREEZE_SHA"]' in guard
    assert "fundamental_oos_shadow_v0_1.json" not in guard
    assert "collector_runtime_freeze_sha\"]" not in guard


def test_runtime_and_baseline_guards_precede_dependency_install_and_collector() -> None:
    ancestor = WORKFLOW.index("Verify reviewed collector baseline is an ancestor")
    runtime = WORKFLOW.index("Verify independent runtime freeze and protected-path diff")
    install = WORKFLOW.index("Install fixed dependencies")
    frozen = WORKFLOW.index("Verify frozen identities ledgers and snapshots")
    collector = WORKFLOW.index("Run scheduled-safe collector")
    assert ancestor < runtime < install < frozen < collector


def test_runtime_hash_mismatch_fails_closed_before_collector() -> None:
    guard = _step(
        "Verify independent runtime freeze and protected-path diff", "Set up Python"
    )
    assert "COLLECTOR_RUNTIME_FREEZE_MISMATCH" in guard
    assert "raise SystemExit" in guard


def test_protected_path_diff_fails_closed_before_collector() -> None:
    guard = _step(
        "Verify independent runtime freeze and protected-path diff", "Set up Python"
    )
    assert 'git diff --quiet "$COLLECTOR_CODE_BASELINE_HEAD..HEAD"' in guard
    assert "COLLECTOR_CODE_DRIFT" in guard


def test_checkout_does_not_persist_credentials() -> None:
    checkout = _step(
        "Check out OOS collector branch without persisted credentials",
        "Verify reviewed collector baseline is an ancestor",
    )
    assert "persist-credentials: false" in checkout
    assert "persist-credentials: true" not in WORKFLOW


def test_write_credential_is_exposed_only_in_final_push_step() -> None:
    final_name = "Commit and fast-forward push OOS data only"
    final_index = WORKFLOW.index(f"- name: {final_name}")
    final = _step(final_name)
    assert "GITHUB_TOKEN" not in WORKFLOW[:final_index]
    assert "GITHUB_TOKEN: ${{ github.token }}" in final
    assert "AUTHORIZATION: bearer ${GITHUB_TOKEN}" in final


def test_collector_process_has_no_write_token() -> None:
    collector = _step(
        "Run scheduled-safe collector",
        "Validate collector result and decide whether data state changed",
    )
    assert "GITHUB_TOKEN" not in collector
    assert "github.token" not in collector


def test_push_is_non_force_and_targets_only_oos_branch() -> None:
    final = _step("Commit and fast-forward push OOS data only")
    assert 'push --no-force origin "HEAD:refs/heads/$OOS_BRANCH"' in final
    assert not re.search(r"\bpush\s+--force\b", final)
    assert "+HEAD" not in final
    assert "research/0050-fundamental-oos-shadow-v0-1" in WORKFLOW


def test_main_never_receives_oos_data_commit() -> None:
    assert "HEAD:main" not in WORKFLOW
    assert "refs/heads/main" not in WORKFLOW
    assert "git push origin main" not in WORKFLOW


def test_fetch_before_push_race_guard_is_preserved() -> None:
    final = _step("Commit and fast-forward push OOS data only")
    assert 'fetch --no-tags origin "$OOS_BRANCH"' in final
    assert 'test "$(git rev-parse FETCH_HEAD)" = "$starting_head"' in final
    assert "CONCURRENT_WRITE_OR_PUSH_RACE" in final


def test_schedule_and_concurrency_are_unchanged() -> None:
    assert 'cron: "30 22 * * *"' in WORKFLOW
    assert 'timezone: "Asia/Taipei"' in WORKFLOW
    assert "group: 0050-fundamental-oos-shadow-v0-1" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_permissions_remain_minimum_required_for_final_push() -> None:
    assert re.search(r"(?m)^permissions:\n  contents: write$", WORKFLOW)
    assert "pull-requests: write" not in WORKFLOW
    assert "issues: write" not in WORKFLOW
    assert "deployments: write" not in WORKFLOW


def test_outcome_calculation_remains_disabled() -> None:
    assert "OUTCOME_CALCULATION_MUST_REMAIN_DISABLED" in WORKFLOW
    assert "oos_outcome_ledger.jsonl" in WORKFLOW
    assert "--calculate-outcomes" not in WORKFLOW


def test_no_pat_or_deployment_behavior_is_introduced() -> None:
    assert not re.search(r"\bPAT\b", WORKFLOW, flags=re.IGNORECASE)
    assert "deploy" not in WORKFLOW.lower()
    assert "force-push" not in WORKFLOW.lower()
