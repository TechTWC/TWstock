from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.fundamental_quality_valuation.mops import parse_mops_filing_html  # noqa: E402


DEFAULT_CACHE = ROOT / "outputs/raw_fundamental_predictive_v0_1/mops"
DEFAULT_BUNDLE = ROOT / "outputs/raw_fundamental_predictive_v0_1/immutable_starting_head_bundle.json"
DEFAULT_OUTPUT = ROOT / "artifacts/0050_fundamental_v0_1/checkpoints/mops_20260904"
STARTING_HEAD = "5abbf53dfc26a55e78d6628ce9087fe17f2cd9f2"
AS_OF_DATE = "2026-09-03"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_mops_response(path: Path) -> tuple[bool, str]:
    text = path.read_bytes().decode("big5", errors="replace")
    if "查詢過量" in text:
        return False, "MOPS_RATE_LIMIT_RESPONSE"
    if "電子資料查詢作業" not in text:
        return False, "UNEXPECTED_MOPS_RESPONSE"
    return True, "VALID_MOPS_ARCHIVE_RESPONSE"


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _requested_observations(bundle_path: Path) -> dict[tuple[str, int], list[str]]:
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    requested: dict[tuple[str, int], list[str]] = {}
    for security in payload["quarterly_financials"]:
        symbol = str(security["symbol"])
        for record in security["records"]:
            period_end = str(record["period_end"])[:10]
            if period_end > AS_OF_DATE:
                continue
            requested.setdefault((symbol, int(period_end[:4])), []).append(period_end)
    return {key: sorted(set(values)) for key, values in requested.items()}


def _active_archives(cache_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    archives: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    symbols = sorted(
        {
            path.name.split("_", 1)[0]
            for path in cache_dir.glob("*_ALL_AVAILABLE_YEARS_MOPS_t57sb01.*")
        }
    )
    for symbol in symbols:
        html_path = cache_dir / f"{symbol}_ALL_AVAILABLE_YEARS_MOPS_t57sb01.html"
        metadata_path = html_path.with_suffix(".metadata.json")
        reason_codes: list[str] = []
        if not html_path.exists():
            reason_codes.append("ACTIVE_HTML_MISSING")
        if not metadata_path.exists():
            reason_codes.append("ACTIVE_METADATA_MISSING")
        metadata: dict[str, Any] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                reason_codes.append("ACTIVE_METADATA_INVALID_JSON")
        valid = False
        response_reason = "ACTIVE_HTML_MISSING"
        if html_path.exists():
            valid, response_reason = _valid_mops_response(html_path)
            if not valid:
                reason_codes.append(response_reason)
        if not metadata.get("source_url"):
            reason_codes.append("ACTIVE_METADATA_SOURCE_URL_MISSING")
        if not metadata.get("retrieval_timestamp"):
            reason_codes.append("ACTIVE_METADATA_RETRIEVAL_TIMESTAMP_MISSING")
        if reason_codes:
            failures.append(
                {
                    "symbol": symbol,
                    "scope": "ALL_AVAILABLE_YEARS",
                    "reason_code": " | ".join(reason_codes),
                    "html_path": html_path.name,
                    "metadata_path": metadata_path.name,
                    "resume_required": True,
                }
            )
            continue
        raw = html_path.read_bytes()
        response_hash = sha256(raw).hexdigest()
        records = parse_mops_filing_html(
            raw.decode("big5", errors="replace"),
            source_url=str(metadata["source_url"]),
            retrieval_timestamp=str(metadata["retrieval_timestamp"]),
            response_sha256=response_hash,
        )
        archives[symbol] = {
            "html_path": html_path,
            "metadata_path": metadata_path,
            "source_url": str(metadata["source_url"]),
            "retrieval_timestamp": str(metadata["retrieval_timestamp"]),
            "response_sha256": response_hash,
            "metadata_sha256": _sha256(metadata_path),
            "record_periods": {record.period_end for record in records},
        }
    return archives, failures


def _cache_inventory(cache_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    legacy_failures: list[dict[str, Any]] = []
    for path in sorted(item for item in cache_dir.iterdir() if item.is_file()):
        active = "_ALL_AVAILABLE_YEARS_" in path.name
        is_html = path.suffix == ".html"
        status = "VALID_JSON_METADATA"
        reason_code = "CACHE_METADATA_PRESENT"
        if is_html:
            valid, reason_code = _valid_mops_response(path)
            status = "VALID_MOPS_RESPONSE" if valid else "INVALID_MOPS_RESPONSE"
            if not active and not valid:
                parts = path.name.split("_")
                legacy_failures.append(
                    {
                        "symbol": parts[0],
                        "fiscal_year": parts[1],
                        "reason_code": reason_code,
                        "cache_file": path.name,
                        "superseded_by_valid_all_year_archive": True,
                        "resume_required": False,
                    }
                )
        else:
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                status = "INVALID_JSON_METADATA"
                reason_code = "CACHE_METADATA_INVALID_JSON"
        inventory.append(
            {
                "path": path.name,
                "scope": "ACTIVE_ALL_YEAR" if active else "LEGACY_PER_YEAR",
                "kind": "HTML" if is_html else "METADATA",
                "status": status,
                "reason_code": reason_code,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return inventory, legacy_failures


def _archive_cache(cache_dir: Path, archive_path: Path) -> None:
    temporary = archive_path.with_suffix(".tar.gz.part")
    with tarfile.open(temporary, "w:gz", compresslevel=9) as archive:
        for path in sorted(item for item in cache_dir.iterdir() if item.is_file()):
            archive.add(path, arcname=path.name, recursive=False)
    temporary.replace(archive_path)


def create_checkpoint(cache_dir: Path, bundle_path: Path, output_dir: Path) -> dict[str, Any]:
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"MOPS cache is missing: {cache_dir}")
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Immutable starting bundle is missing: {bundle_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    requested = _requested_observations(bundle_path)
    active, active_failures = _active_archives(cache_dir)
    inventory, legacy_failures = _cache_inventory(cache_dir)
    completed: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    proxy_observations = 0
    exact_observations = 0
    for (symbol, fiscal_year), periods in sorted(requested.items()):
        archive = active.get(symbol)
        if archive is None:
            remaining.append(
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "reason_code": "VALID_ALL_YEAR_ARCHIVE_NOT_AVAILABLE",
                    "next_action": "FETCH_SYMBOL_ALL_AVAILABLE_YEARS_ONLY",
                }
            )
            continue
        matched = sum(period in archive["record_periods"] for period in periods)
        proxy = len(periods) - matched
        exact_observations += matched
        proxy_observations += proxy
        completed.append(
            {
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "status": "COMPLETED_FROM_VALID_ALL_YEAR_CACHE",
                "requested_observations": len(periods),
                "mops_exact_observations": matched,
                "proxy_observations": proxy,
                "html_cache_file": archive["html_path"].name,
                "metadata_file": archive["metadata_path"].name,
                "response_sha256": archive["response_sha256"],
                "metadata_sha256": archive["metadata_sha256"],
                "retrieval_timestamp": archive["retrieval_timestamp"],
                "source_url": archive["source_url"],
            }
        )

    completed_path = output_dir / "completed_company_years.csv"
    remaining_path = output_dir / "remaining_company_years.csv"
    failures_path = output_dir / "failures.csv"
    legacy_failures_path = output_dir / "legacy_cache_failures.csv"
    inventory_path = output_dir / "mops_cache_inventory.csv"
    archive_path = output_dir / "mops_cache_and_metadata.tar.gz"
    _write_csv(
        completed_path,
        [
            "symbol",
            "fiscal_year",
            "status",
            "requested_observations",
            "mops_exact_observations",
            "proxy_observations",
            "html_cache_file",
            "metadata_file",
            "response_sha256",
            "metadata_sha256",
            "retrieval_timestamp",
            "source_url",
        ],
        completed,
    )
    _write_csv(
        remaining_path,
        ["symbol", "fiscal_year", "reason_code", "next_action"],
        remaining,
    )
    _write_csv(
        failures_path,
        ["symbol", "scope", "reason_code", "html_path", "metadata_path", "resume_required"],
        active_failures,
    )
    _write_csv(
        legacy_failures_path,
        [
            "symbol",
            "fiscal_year",
            "reason_code",
            "cache_file",
            "superseded_by_valid_all_year_archive",
            "resume_required",
        ],
        legacy_failures,
    )
    _write_csv(
        inventory_path,
        ["path", "scope", "kind", "status", "reason_code", "bytes", "sha256"],
        inventory,
    )
    _archive_cache(cache_dir, archive_path)

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tracked_files = [
        completed_path,
        remaining_path,
        failures_path,
        legacy_failures_path,
        inventory_path,
        archive_path,
    ]
    checkpoint = {
        "checkpoint_version": "MOPS-CACHE-CHECKPOINT-v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "network_requests_performed": False,
        "source_starting_head": STARTING_HEAD,
        "workspace_head_at_checkpoint": head,
        "as_of_date": AS_OF_DATE,
        "cache": {
            "workspace_location": str(cache_dir.relative_to(ROOT)),
            "portable_archive": str(archive_path.relative_to(ROOT)),
            "portable_archive_sha256": _sha256(archive_path),
            "files": len(inventory),
            "bytes": sum(int(row["bytes"]) for row in inventory),
            "active_all_year_html": sum(
                row["scope"] == "ACTIVE_ALL_YEAR" and row["kind"] == "HTML"
                for row in inventory
            ),
            "active_all_year_metadata": sum(
                row["scope"] == "ACTIVE_ALL_YEAR" and row["kind"] == "METADATA"
                for row in inventory
            ),
            "legacy_per_year_html": sum(
                row["scope"] == "LEGACY_PER_YEAR" and row["kind"] == "HTML"
                for row in inventory
            ),
            "legacy_per_year_metadata": sum(
                row["scope"] == "LEGACY_PER_YEAR" and row["kind"] == "METADATA"
                for row in inventory
            ),
        },
        "completion": {
            "requested_company_years": len(requested),
            "completed_company_years": len(completed),
            "remaining_company_years": len(remaining),
            "successful_company_archives": len(active),
            "failed_active_company_archives": len(active_failures),
            "requested_financial_observations": sum(len(value) for value in requested.values()),
            "mops_exact_observations": exact_observations,
            "proxy_observations": proxy_observations,
            "legacy_rate_limit_failures_superseded": len(legacy_failures),
        },
        "resume": {
            "can_resume": not active_failures,
            "remaining_list": str(remaining_path.relative_to(ROOT)),
            "failure_list": str(failures_path.relative_to(ROOT)),
            "legacy_failure_list": str(legacy_failures_path.relative_to(ROOT)),
            "restore_command": (
                "python scripts/checkpoint_0050_mops_cache_v0_1.py --restore-to "
                "outputs/raw_fundamental_predictive_v0_1/mops"
            ),
            "request_contract": "Only company-year rows in remaining_company_years.csv may be requested next.",
            "next_network_requests_required": len({row["symbol"] for row in remaining}),
        },
        "checkpoint_files": {
            str(path.relative_to(output_dir)): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in tracked_files
        },
    }
    checkpoint_path = output_dir / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return checkpoint


def verify_checkpoint(output_dir: Path) -> dict[str, Any]:
    checkpoint_path = output_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for relative, expected in checkpoint["checkpoint_files"].items():
        path = output_dir / relative
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint file is missing: {path}")
        actual = _sha256(path)
        if actual != expected["sha256"]:
            raise ValueError(f"Checkpoint hash mismatch for {path.name}: {actual}")
    archive = ROOT / checkpoint["cache"]["portable_archive"]
    if _sha256(archive) != checkpoint["cache"]["portable_archive_sha256"]:
        raise ValueError("Portable MOPS cache archive hash mismatch")
    return checkpoint


def restore_checkpoint(output_dir: Path, target: Path) -> dict[str, Any]:
    checkpoint = verify_checkpoint(output_dir)
    archive_path = ROOT / checkpoint["cache"]["portable_archive"]
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or Path(member.name).name != member.name:
                raise ValueError(f"Unsafe or unexpected archive member: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            destination = target / member.name
            content = source.read()
            if destination.exists():
                if sha256(destination.read_bytes()).hexdigest() != sha256(content).hexdigest():
                    raise FileExistsError(f"Refusing to overwrite different cache file: {destination}")
                continue
            temporary = destination.with_suffix(destination.suffix + ".part")
            temporary.write_bytes(content)
            temporary.replace(destination)
    return checkpoint


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, or restore an offline MOPS cache checkpoint; never performs network I/O."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--create", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--restore-to", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.create:
        checkpoint = create_checkpoint(args.cache_dir, args.bundle, args.output_dir)
    elif args.verify:
        checkpoint = verify_checkpoint(args.output_dir)
    else:
        checkpoint = restore_checkpoint(args.output_dir, args.restore_to)
    print(json.dumps(checkpoint["completion"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
