from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/fundamental_external_universe_e0_b1_v0_1.json"

MEMBERSHIP_COLUMNS = [
    "index_name", "symbol", "company_name", "membership_start", "membership_end",
    "effective_from", "effective_to", "event_type", "event_source_date", "source_url",
    "source_authority", "source_sha256", "pit_verified", "verification_note",
]
SECURITY_MASTER_COLUMNS = [
    "symbol", "company_name", "listing_date", "delisting_date", "market",
    "security_type", "name_change", "symbol_change", "merger_or_conversion",
    "current_status", "source_url", "source_sha256", "pit_verified",
]
INTERVAL_COLUMNS = [
    "interval_start", "interval_end", "taiwan50_count", "midcap100_count",
    "overlap_count", "unexplained_entries", "unexplained_exits", "verified", "reason",
]
PROVENANCE_COLUMNS = [
    "source_id", "source_type", "publication_date", "effective_date", "index_scope",
    "event_kind", "title", "source_url", "source_authority", "raw_relative_path",
    "raw_sha256", "retrieved_at", "acquisition_status", "verification_note",
]
PROHIBITED_OUTCOME_FIELDS = {
    "stock_future_return", "future_return", "stock_return", "benchmark_return",
    "excess_return", "outperform", "outperform_0050", "forward_price",
    "return_60d", "return_120d", "return_252d", "return_504d",
}
ALLOWED_AUTHORITIES = {"TAIWAN_INDEX_PLUS", "TWSE", "FTSE_RUSSELL"}
ENTRY_EVENTS = {"SEED", "REGULAR_ADDITION", "INTERIM_ADDITION", "RESERVE_REPLACEMENT_IN"}
EXIT_EVENTS = {"REGULAR_DELETION", "INTERIM_DELETION", "RESERVE_REPLACEMENT_OUT"}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_model_hash(model: dict[str, Any]) -> str:
    payload = {"quality_rules": model["quality_rules"], "valuation_rules": model["valuation_rules"]}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def reject_outcome_fields(columns: Iterable[str]) -> None:
    found = sorted({column.strip().lower() for column in columns} & PROHIBITED_OUTCOME_FIELDS)
    if found:
        raise ValueError(f"outcome fields are forbidden in E0-B1: {', '.join(found)}")


def validate_official_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        raise ValueError(f"non-official or unsafe primary source URL: {url}")


def validate_raw_source(raw_root: Path, relative_path: str, expected_sha256: str) -> Path:
    candidate = (raw_root / relative_path).resolve()
    root = raw_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("raw source path escapes immutable source root")
    if not candidate.is_file():
        raise ValueError(f"raw source missing: {relative_path}")
    actual = sha256_path(candidate)
    if actual != expected_sha256:
        raise ValueError(f"raw source hash mismatch: {relative_path}")
    return candidate


def validate_membership_rows(
    rows: list[dict[str, str]],
    *,
    expected_counts: dict[str, int],
    allowed_hosts: set[str],
) -> dict[str, Any]:
    reject_outcome_fields(rows[0].keys() if rows else [])
    duplicate_keys: set[tuple[str, str, str]] = set()
    seen: set[tuple[str, str, str]] = set()
    unexplained_entries = 0
    unexplained_exits = 0
    intervals_by_security: dict[tuple[str, str], list[tuple[date, date]]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        authority = row["source_authority"].strip().upper()
        if authority not in ALLOWED_AUTHORITIES:
            raise ValueError("non-official source cannot establish primary membership")
        validate_official_url(row["source_url"], allowed_hosts)
        start = date.fromisoformat(row["effective_from"])
        end = date.fromisoformat(row["effective_to"])
        if end < start:
            raise ValueError("effective-date boundary is reversed")
        key = (row["index_name"], row["symbol"], row["effective_from"])
        if key in seen:
            duplicate_keys.add(key)
        seen.add(key)
        intervals_by_security.setdefault((row["index_name"], row["symbol"]), []).append((start, end))
        counts[row["index_name"]] = counts.get(row["index_name"], 0) + 1
        event = row["event_type"].strip().upper()
        if event not in ENTRY_EVENTS | EXIT_EVENTS | {"UNCHANGED"}:
            unexplained_entries += 1
            unexplained_exits += 1
    if duplicate_keys:
        raise ValueError("duplicate membership rows rejected")
    for intervals in intervals_by_security.values():
        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            if current[0] <= previous[1]:
                raise ValueError("overlapping membership intervals rejected")
    if unexplained_entries:
        raise ValueError("unexplained membership entry rejected")
    if unexplained_exits:
        raise ValueError("unexplained membership exit rejected")
    mismatches = {
        index: {"expected": expected, "actual": counts.get(index, 0)}
        for index, expected in expected_counts.items()
        if counts.get(index, 0) != expected
    }
    if mismatches:
        raise ValueError(f"expected constituent count mismatch: {mismatches}")
    taiwan50 = {row["symbol"] for row in rows if row["index_name"] == "TAIWAN_50"}
    midcap100 = {row["symbol"] for row in rows if row["index_name"] == "TAIWAN_MID_CAP_100"}
    overlap = sorted(taiwan50 & midcap100)
    if overlap:
        raise ValueError(f"Taiwan50/MidCap100 overlap requires explanation: {overlap}")
    return {"counts": counts, "overlap": overlap}


def require_seed(rows: list[dict[str, str]]) -> None:
    seeds = [row for row in rows if row.get("event_type", "").strip().upper() == "SEED"]
    if not seeds:
        raise ValueError("credible full-membership seed is required")
    if not all(row.get("pit_verified", "").strip().lower() in {"true", "1", "yes"} for row in seeds):
        raise ValueError("seed must be PIT verified")


def apply_interim_replacement(members: set[str], removed: str, added: str) -> set[str]:
    if removed not in members or added in members:
        raise ValueError("interim replacement does not reconcile")
    return (members - {removed}) | {added}


def retain_lifecycle_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [dict(row) for row in rows]


def financial_eligible(sector_logic: str) -> bool:
    return sector_logic.strip().upper() != "FINANCIAL"


def quarter_intervals(start: date, end: date) -> list[tuple[date, date]]:
    intervals: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = cursor.month + 3
        next_year = cursor.year
        if next_month > 12:
            next_month -= 12
            next_year += 1
        boundary = date(next_year, next_month, 1)
        interval_end = min(end, boundary - timedelta(days=1))
        intervals.append((cursor, interval_end))
        cursor = boundary
    return intervals


def build_source_provenance(config: dict[str, Any], root: Path) -> tuple[list[dict[str, Any]], int, int]:
    discovery_path = root / config["source_discovery_path"]
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    reject_outcome_fields(discovery.keys())
    allowed_hosts = set(config["official_host_allowlist"])
    validate_official_url(discovery["source_url"], allowed_hosts)

    raw_root = root / config["raw_source_root"]
    capture_path = root / config["source_index_capture_path"]
    actual_capture_hash = sha256_path(capture_path)
    if actual_capture_hash != config["source_index_capture_sha256"]:
        raise ValueError("source index capture hash mismatch")

    rows: list[dict[str, Any]] = [{
        "source_id": "taiwanindex_technical_notice_index",
        "source_type": "OFFICIAL_RENDERED_INDEX_CAPTURE",
        "publication_date": "",
        "effective_date": "",
        "index_scope": "FTSE_TWSE_TAIWAN_INDEX_SERIES",
        "event_kind": "SOURCE_INDEX",
        "title": "Taiwan Index Plus technical-notice archive",
        "source_url": discovery["source_url"],
        "source_authority": "TAIWAN_INDEX_PLUS",
        "raw_relative_path": capture_path.relative_to(raw_root).as_posix(),
        "raw_sha256": actual_capture_hash,
        "retrieved_at": discovery["retrieved_at"],
        "acquisition_status": "RAW_CAPTURED",
        "verification_note": "Rendered official archive index captured with all rows visible; linked documents remain pending retrieval.",
    }]
    regular = 0
    interim = 0
    for item in discovery["rows"]:
        published = item["row"][:10].replace("/", "-")
        if published > config["observation_end"]:
            raise ValueError("source published after research as-of boundary")
        validate_official_url(item["href"], allowed_hosts)
        is_regular = item["row"].endswith("定審結果")
        regular += int(is_regular)
        interim += int(not is_regular)
        rows.append({
            "source_id": f"technical_notice_{item['href'].split('/')[-2]}",
            "source_type": "OFFICIAL_TECHNICAL_NOTICE",
            "publication_date": published,
            "effective_date": "",
            "index_scope": "FTSE_TWSE_TAIWAN_INDEX_SERIES",
            "event_kind": "REGULAR_REVIEW" if is_regular else "INTERIM_OR_EXTRAORDINARY_CANDIDATE",
            "title": item["row"][11:].rsplit(" ", 1)[0],
            "source_url": item["href"],
            "source_authority": "TAIWAN_INDEX_PLUS",
            "raw_relative_path": "",
            "raw_sha256": "",
            "retrieved_at": discovery["retrieved_at"],
            "acquisition_status": "DISCOVERED_NOT_RETRIEVED",
            "verification_note": "Document content/effective date not normalized; cannot establish membership.",
        })
    return rows, regular, interim


def run_reconstruction(root: Path, config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not (config["no_future_returns"] and config["no_outcome_files"] and config["no_model_change"]):
        raise ValueError("E0-B1 anti-leakage contract is not fail closed")

    model_path = root / config["frozen_model_config_path"]
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model_hash = canonical_model_hash(model)
    if model_hash != config["frozen_model_hash"]:
        raise ValueError("frozen model hash mismatch")
    if sha256_path(root / config["frozen_0050_universe_path"]) != config["frozen_0050_universe_hash"]:
        raise ValueError("frozen 0050 universe hash mismatch")

    provenance, regular_count, interim_count = build_source_provenance(config, root)
    data_root = root / config["data_output_root"]
    artifact_root = root / config["artifact_output_root"]

    membership_rows: list[dict[str, Any]] = []
    security_rows: list[dict[str, Any]] = []
    write_csv(data_root / "historical_external_membership.csv", MEMBERSHIP_COLUMNS, membership_rows)
    write_csv(data_root / "external_security_master.csv", SECURITY_MASTER_COLUMNS, security_rows)
    write_csv(artifact_root / "source_provenance_manifest.csv", PROVENANCE_COLUMNS, provenance)

    intervals = quarter_intervals(
        date.fromisoformat(config["observation_start"]),
        date.fromisoformat(config["observation_end"]),
    )
    interval_rows = [{
        "interval_start": start.isoformat(),
        "interval_end": end.isoformat(),
        "taiwan50_count": "",
        "midcap100_count": "",
        "overlap_count": "",
        "unexplained_entries": "",
        "unexplained_exits": "",
        "verified": "false",
        "reason": "MEMBERSHIP_INTERVAL_NOT_VERIFIED:MISSING_OFFICIAL_FULL_CONSTITUENT_SEED;NOTICE_DOCUMENTS_NOT_NORMALIZED",
    } for start, end in intervals]
    write_csv(artifact_root / "membership_interval_audit.csv", INTERVAL_COLUMNS, interval_rows)

    coverage = [
        {"metric": "study_calendar_quarter_intervals", "value": len(intervals), "status": "OBSERVED"},
        {"metric": "verified_intervals", "value": 0, "status": "FAIL"},
        {"metric": "unverified_intervals", "value": len(intervals), "status": "FAIL"},
        {"metric": "regular_review_source_candidates", "value": regular_count, "status": "DISCOVERED"},
        {"metric": "interim_extraordinary_source_candidates", "value": interim_count, "status": "DISCOVERED"},
        {"metric": "unique_midcap100_symbols_observed", "value": 0, "status": "NOT_ESTIMABLE"},
        {"metric": "unique_ex_0050_symbols", "value": 0, "status": "NOT_ESTIMABLE"},
        {"metric": "non_financial_candidates", "value": 0, "status": "NOT_ESTIMABLE"},
        {"metric": "financial_excluded", "value": 0, "status": "NOT_ESTIMABLE"},
        {"metric": "delisted_merged_removed_observed", "value": 0, "status": "NOT_ESTIMABLE"},
        {"metric": "pit_verified_ratio", "value": "0/31", "status": "FAIL"},
        {"metric": "complete_primary_cohort_timeline", "value": "false", "status": "FAIL"},
    ]
    write_csv(artifact_root / "historical_membership_coverage.csv", ["metric", "value", "status"], coverage)

    manifest: dict[str, Any] = {
        "contract_id": config["contract_id"],
        "stage": config["stage"],
        "status": "DATA_NOT_READY",
        "e0_b2_gate": "BLOCKED",
        "observation_window": [config["observation_start"], config["observation_end"]],
        "official_source_authorities_used": ["TAIWAN_INDEX_PLUS"],
        "source_discovery": {
            "regular_review_candidates": regular_count,
            "interim_or_extraordinary_candidates": interim_count,
            "raw_index_capture_sha256": config["source_index_capture_sha256"],
            "notice_documents_retrieved": 0,
        },
        "seed_snapshot": {"source": "", "date": "", "status": "FAIL", "reason": "MISSING_OFFICIAL_FULL_CONSTITUENT_SEED"},
        "verified_membership_intervals": 0,
        "unverified_membership_intervals": len(intervals),
        "taiwan50_pit_reconstruction": "FAIL",
        "midcap100_pit_reconstruction": "FAIL",
        "interval_count_reconciliation": "FAIL",
        "unique_midcap100_historical_symbols": 0,
        "unique_ex_0050_symbols": 0,
        "non_financial_candidate_symbols": 0,
        "financial_excluded": 0,
        "removed_delisted_merged_symbols_retained": 0,
        "security_master_lifecycle": "FAIL",
        "governance": {
            "outcome_files_read": [],
            "future_returns_computed": False,
            "frozen_model_modified": False,
            "frozen_model_hash": model_hash,
            "network_acquisition_contract_enabled": True,
            "reconstruction_script_network_requests": 0,
        },
        "unresolved": [
            "official full-membership seed snapshot",
            "raw linked technical-notice documents and effective dates",
            "complete regular/interim event reconciliation",
            "historical TWSE/MOPS security lifecycle for reconstructed symbols",
        ],
        "next_allowed_action": "continue E0-B1 official evidence acquisition; E0-B2 and E1 remain forbidden",
    }
    manifest_path = artifact_root / "e0_b1_stage_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed E0-B1 membership/security-master reconstruction")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = run_reconstruction(ROOT, args.config)
    print(json.dumps({"status": manifest["status"], "e0_b2_gate": manifest["e0_b2_gate"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
