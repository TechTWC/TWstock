from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Iterable, Mapping

from .ledger import ContractError


SCHEDULED_WRITE_ALLOWLIST = (
    "data/research/0050_fundamental_oos_v0_1/oos_signal_ledger.jsonl",
    "data/research/0050_fundamental_oos_v0_1/oos_outcome_ledger.jsonl",
    "data/research/0050_fundamental_oos_v0_1/oos_pending_candidates.json",
    "artifacts/0050_fundamental_oos_v0_1/source_blobs/",
    "artifacts/0050_fundamental_oos_v0_1/runs/",
)


def collector_code_hash(root: Path, relative_paths: Iterable[str]) -> str:
    """Return a stable identity for the scheduled collector implementation."""

    digest = sha256()
    paths = sorted(str(path) for path in relative_paths)
    if not paths:
        raise ContractError("Collector freeze path set is empty")
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise ContractError(f"Collector freeze path is missing: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_collector_code_freeze(
    root: Path, contract: Mapping[str, object]
) -> dict[str, object]:
    expected = str(contract.get("collector_code_freeze_sha", ""))
    paths = contract.get("collector_code_paths")
    if len(expected) != 64 or not isinstance(paths, list):
        raise ContractError("Collector code freeze contract is incomplete")
    actual = collector_code_hash(root, [str(path) for path in paths])
    if actual != expected:
        raise ContractError("COLLECTOR_CODE_DRIFT")
    return {
        "collector_code_freeze_sha": expected,
        "actual_collector_code_sha": actual,
        "collector_code_paths": list(paths),
        "status": "PASS",
    }


def _git_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    entries = [entry for entry in result.stdout.split(b"\0") if entry]
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index].decode("utf-8", errors="strict")
        if len(entry) < 4:
            raise ContractError("Unparseable git status entry")
        status = entry[:2]
        paths.append(entry[3:])
        if "R" in status or "C" in status:
            index += 1
            if index >= len(entries):
                raise ContractError("Unparseable git rename status")
            paths.append(entries[index].decode("utf-8", errors="strict"))
        index += 1
    return sorted(set(paths))


def assert_clean_scheduler_start(root: Path) -> None:
    changed = _git_paths(root)
    if changed:
        raise ContractError(
            "SCHEDULED_RUN_REQUIRES_CLEAN_CHECKOUT: " + ", ".join(changed)
        )


def _is_allowlisted(path: str) -> bool:
    return any(
        path == allowed or (allowed.endswith("/") and path.startswith(allowed))
        for allowed in SCHEDULED_WRITE_ALLOWLIST
    )


def assert_scheduled_write_allowlist(
    root: Path, changed_paths: Iterable[str] | None = None
) -> list[str]:
    changed = sorted(set(changed_paths if changed_paths is not None else _git_paths(root)))
    rejected = [path for path in changed if not _is_allowlisted(path)]
    if rejected:
        raise ContractError("NON_ALLOWLISTED_SCHEDULED_DIFF: " + ", ".join(rejected))
    return changed
