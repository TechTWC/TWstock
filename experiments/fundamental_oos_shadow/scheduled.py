from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Mapping

from .ledger import ContractError


RUNTIME_MANIFEST_VERSION = "OOS-C-RUNTIME-1"
RUNTIME_MANIFEST_PATH = "config/collector_runtime_manifest_v0_1.json"
RUNTIME_ENTRYPOINTS = ("scripts/run_0050_fundamental_oos_v0_1.py",)
RUNTIME_REQUIRED_NON_PYTHON_PATHS = (
    "config/fundamental_oos_shadow_v0_1.json",
    "config/fundamental_quality_valuation_v0_1.json",
    "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv",
    "requirements-dev.txt",
)

SCHEDULED_WRITE_ALLOWLIST = (
    "data/research/0050_fundamental_oos_v0_1/oos_signal_ledger.jsonl",
    "data/research/0050_fundamental_oos_v0_1/oos_outcome_ledger.jsonl",
    "data/research/0050_fundamental_oos_v0_1/oos_pending_candidates.json",
    "artifacts/0050_fundamental_oos_v0_1/source_blobs/",
    "artifacts/0050_fundamental_oos_v0_1/runs/",
)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _validated_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("Runtime manifest contains an invalid path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ContractError(f"Runtime manifest path is not canonical: {value}")
    return value


def _sha256_path(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"Runtime dependency is missing: {path}")
    return sha256(path.read_bytes()).hexdigest()


def build_runtime_manifest(root: Path, runtime_paths: Iterable[str]) -> dict[str, object]:
    """Build the deterministic manifest whose canonical JSON is the runtime identity."""

    paths = [_validated_relative_path(value) for value in runtime_paths]
    if not paths or len(paths) != len(set(paths)):
        raise ContractError("Runtime manifest path set is empty or contains duplicates")
    ordered = sorted(paths)
    return {
        "manifest_version": RUNTIME_MANIFEST_VERSION,
        "hash_algorithm": "SHA256",
        "canonical_path_ordering": "UTF8_BYTEWISE_ASCENDING",
        "runtime_paths": [
            {"runtime_path": relative, "blob_sha256": _sha256_path(root / relative)}
            for relative in ordered
        ],
    }


def runtime_manifest_sha(manifest: Mapping[str, object]) -> str:
    return sha256(_canonical_json_bytes(manifest)).hexdigest()


def load_runtime_manifest(
    root: Path, manifest_path: str = RUNTIME_MANIFEST_PATH
) -> dict[str, object]:
    try:
        manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("Collector runtime manifest is missing or invalid") from exc
    if not isinstance(manifest, dict):
        raise ContractError("Collector runtime manifest must be a JSON object")
    return manifest


def _module_path(root: Path, module: str) -> str | None:
    if not module:
        return None
    relative = module.replace(".", "/")
    module_file = f"{relative}.py"
    package_file = f"{relative}/__init__.py"
    if (root / module_file).is_file():
        return module_file
    if (root / package_file).is_file():
        return package_file
    return None


def _package_initializers(root: Path, relative: str) -> set[str]:
    path = PurePosixPath(relative)
    directories = path.parts[:-1]
    return {
        "/".join((*directories[:index], "__init__.py"))
        for index in range(1, len(directories) + 1)
        if (root / "/".join((*directories[:index], "__init__.py"))).is_file()
    }


def _imported_modules(tree: ast.AST, current_package: str) -> set[str]:
    modules: set[str] = set()
    package_parts = current_package.split(".") if current_package else []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                remove = node.level - 1
                if remove > len(package_parts):
                    raise ContractError("Runtime module uses an invalid relative import")
                base_parts = package_parts[: len(package_parts) - remove]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(base_parts)
            else:
                base = node.module or ""
            if base:
                modules.add(base)
                modules.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            attribute = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name == "__import__" or attribute == "import_module":
                raise ContractError("Dynamic repository imports are prohibited in scheduled runtime")
    return modules


def discover_runtime_python_dependencies(
    root: Path, entrypoints: Iterable[str] = RUNTIME_ENTRYPOINTS
) -> list[str]:
    """Bounded AST audit of repository-local imports reachable from scheduled entrypoints."""

    pending = [_validated_relative_path(value) for value in entrypoints]
    discovered: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in discovered:
            continue
        path = root / relative
        if not path.is_file() or path.suffix != ".py":
            raise ContractError(f"Runtime Python dependency is missing: {relative}")
        discovered.add(relative)
        for initializer in _package_initializers(root, relative):
            if initializer not in discovered:
                pending.append(initializer)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError) as exc:
            raise ContractError(f"Runtime Python dependency cannot be audited: {relative}") from exc
        parts = PurePosixPath(relative).parts
        current_package = ".".join(parts[:-1])
        for module in _imported_modules(tree, current_package):
            imported = _module_path(root, module)
            if imported and imported not in discovered:
                pending.append(imported)
    return sorted(discovered)


def audit_runtime_manifest_dependencies(
    root: Path, runtime_paths: Iterable[str]
) -> dict[str, object]:
    declared = {_validated_relative_path(value) for value in runtime_paths}
    discovered = set(discover_runtime_python_dependencies(root))
    missing_python = sorted(discovered - declared)
    missing_required = sorted(set(RUNTIME_REQUIRED_NON_PYTHON_PATHS) - declared)
    if missing_python or missing_required:
        missing = missing_python + missing_required
        raise ContractError("RUNTIME_DEPENDENCY_OMITTED: " + ", ".join(missing))
    return {
        "status": "PASS",
        "discovered_python_paths": sorted(discovered),
        "required_non_python_paths": list(RUNTIME_REQUIRED_NON_PYTHON_PATHS),
    }


def verify_collector_runtime_freeze(
    root: Path,
    *,
    expected_sha: str | None = None,
    manifest_path: str = RUNTIME_MANIFEST_PATH,
) -> dict[str, object]:
    manifest = load_runtime_manifest(root, manifest_path)
    if set(manifest) != {
        "manifest_version",
        "hash_algorithm",
        "canonical_path_ordering",
        "runtime_paths",
    }:
        raise ContractError("Collector runtime manifest schema is invalid")
    if (
        manifest["manifest_version"] != RUNTIME_MANIFEST_VERSION
        or manifest["hash_algorithm"] != "SHA256"
        or manifest["canonical_path_ordering"] != "UTF8_BYTEWISE_ASCENDING"
        or not isinstance(manifest["runtime_paths"], list)
    ):
        raise ContractError("Collector runtime manifest contract is invalid")
    entries = manifest["runtime_paths"]
    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"runtime_path", "blob_sha256"}:
            raise ContractError("Collector runtime manifest entry is invalid")
        relative = _validated_relative_path(entry["runtime_path"])
        expected_blob = entry["blob_sha256"]
        if not isinstance(expected_blob, str) or len(expected_blob) != 64:
            raise ContractError(f"Runtime blob identity is invalid: {relative}")
        actual_blob = _sha256_path(root / relative)
        if actual_blob != expected_blob:
            raise ContractError(f"COLLECTOR_RUNTIME_DRIFT: {relative}")
        paths.append(relative)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ContractError("Runtime manifest paths are not canonically ordered")
    audit = audit_runtime_manifest_dependencies(root, paths)
    actual_sha = runtime_manifest_sha(manifest)
    if expected_sha is not None:
        if len(expected_sha) != 64 or actual_sha != expected_sha:
            raise ContractError("COLLECTOR_RUNTIME_FREEZE_MISMATCH")
    return {
        "status": "PASS",
        "collector_runtime_freeze_sha": actual_sha,
        "runtime_manifest_path": manifest_path,
        "runtime_paths": paths,
        "runtime_path_count": len(paths),
        "static_import_audit": audit,
    }


def runtime_protected_paths(
    root: Path, manifest_path: str = RUNTIME_MANIFEST_PATH
) -> list[str]:
    report = verify_collector_runtime_freeze(root, manifest_path=manifest_path)
    return sorted({manifest_path, *report["runtime_paths"]})


def verify_collector_code_baseline(
    root: Path,
    baseline_head: str,
    *,
    manifest_path: str = RUNTIME_MANIFEST_PATH,
) -> dict[str, object]:
    if len(baseline_head) != 40:
        raise ContractError("Collector code baseline head is invalid")
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{baseline_head}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_head, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if exists.returncode or ancestor.returncode:
        raise ContractError("COLLECTOR_CODE_BASELINE_NOT_ANCESTOR")
    protected = runtime_protected_paths(root, manifest_path)
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{baseline_head}..HEAD", "--", *protected],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if changed:
        raise ContractError("COLLECTOR_CODE_DRIFT: " + ", ".join(changed))
    return {
        "status": "PASS",
        "collector_code_baseline_head": baseline_head,
        "protected_paths": protected,
        "protected_path_count": len(protected),
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
