from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/fundamental_external_universe_e0_v0_1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/fundamental_external_universe_e0_v0_1"

REQUIRED_COLUMNS = {
    "historical_membership": {
        "observation_date",
        "symbol",
        "company",
        "index_name",
        "sector_logic",
        "cohort_eligible",
        "is_0050_member",
        "source_url",
        "source_published_at",
        "source_sha256",
    },
    "security_master": {
        "symbol",
        "listing_date",
        "delisting_date",
        "security_type",
        "status",
        "source_scope",
        "source_url",
        "source_as_of",
        "source_sha256",
    },
    "mops_coverage": {
        "symbol",
        "period_end",
        "announcement_timestamp",
        "availability_method",
        "source_identifier",
        "source_url",
        "source_sha256",
    },
    "expected_support": {
        "horizon",
        "dimension",
        "bucket",
        "expected_observations",
        "expected_unique_issuers",
        "support_status",
    },
}

PROHIBITED_OUTCOME_COLUMNS = {
    "exit_date",
    "stock_return",
    "benchmark_return",
    "excess_return",
    "outperform_0050",
    "outperform_0050_rate",
    "forward_return",
    "median_return",
    "mean_return",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        return headers, [dict(row) for row in reader]


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _validate_date(value: str) -> bool:
    try:
        date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return False
    return True


def _valid_sha256(value: str) -> bool:
    cleaned = value.strip().lower()
    return len(cleaned) == 64 and all(character in "0123456789abcdef" for character in cleaned)


def _positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def inspect_external_input(kind: str, path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "input": kind,
        "path": path.as_posix(),
        "status": "MISSING",
        "rows": 0,
        "sha256": "",
        "detail": "required pre-outcome input is not present",
    }
    if not path.is_file():
        return result

    headers, rows = read_csv(path)
    header_set = set(headers)
    prohibited = sorted(header_set & PROHIBITED_OUTCOME_COLUMNS)
    missing = sorted(REQUIRED_COLUMNS[kind] - header_set)
    result.update(rows=len(rows), sha256=sha256_path(path))
    if prohibited:
        result.update(
            status="REJECTED_OUTCOME_DATA",
            detail=f"outcome columns are forbidden in E0: {', '.join(prohibited)}",
        )
        return result
    if missing:
        result.update(
            status="INVALID_SCHEMA",
            detail=f"missing required columns: {', '.join(missing)}",
        )
        return result
    if not rows:
        result.update(status="EMPTY", detail="input has headers but no observations")
        return result

    if kind == "historical_membership":
        invalid_dates = sum(not _validate_date(row["observation_date"]) for row in rows)
        invalid_hashes = sum(not _valid_sha256(row["source_sha256"]) for row in rows)
        external_rows = [
            row
            for row in rows
            if row["is_0050_member"].strip().lower() in {"false", "0", "no"}
            and row["cohort_eligible"].strip().lower() in {"true", "1", "yes"}
            and row["sector_logic"].strip().upper() != "FINANCIAL"
        ]
        symbols = {row["symbol"].strip() for row in external_rows if row["symbol"].strip()}
        wrong_index_rows = sum(
            row["index_name"].strip().upper() != "TAIWAN_MID_CAP_100"
            for row in external_rows
        )
        if invalid_dates or invalid_hashes or wrong_index_rows or not external_rows or not symbols:
            result.update(
                status="INVALID_CONTENT",
                detail=(
                    f"invalid_dates={invalid_dates}; invalid_hashes={invalid_hashes}; "
                    f"wrong_index_rows={wrong_index_rows}; eligible_external_rows={len(external_rows)}; "
                    f"eligible_external_symbols={len(symbols)}"
                ),
            )
            return result
        result["eligible_external_rows"] = len(external_rows)
        result["eligible_external_symbols"] = len(symbols)

    if kind == "security_master":
        invalid_hashes = sum(not _valid_sha256(row["source_sha256"]) for row in rows)
        invalid_listing_dates = sum(not _validate_date(row["listing_date"]) for row in rows)
        non_historical_rows = sum(
            row["source_scope"].strip().upper() != "HISTORICAL_ALL_LISTINGS"
            for row in rows
        )
        if invalid_hashes or invalid_listing_dates or non_historical_rows:
            result.update(
                status="INVALID_CONTENT",
                detail=(
                    f"invalid_hashes={invalid_hashes}; invalid_listing_dates={invalid_listing_dates}; "
                    f"non_historical_source_rows={non_historical_rows}"
                ),
            )
            return result

    if kind == "mops_coverage":
        invalid_hashes = sum(not _valid_sha256(row["source_sha256"]) for row in rows)
        missing_timestamps = sum(not row["announcement_timestamp"].strip() for row in rows)
        if invalid_hashes or missing_timestamps:
            result.update(
                status="INVALID_CONTENT",
                detail=f"invalid_hashes={invalid_hashes}; missing_announcement_timestamps={missing_timestamps}",
            )
            return result

    if kind == "expected_support":
        invalid_counts = sum(
            _positive_int(row["expected_observations"]) is None
            or _positive_int(row["expected_unique_issuers"]) is None
            for row in rows
        )
        invalid_horizons = sum(_positive_int(row["horizon"]) is None for row in rows)
        if invalid_counts or invalid_horizons:
            result.update(
                status="INVALID_CONTENT",
                detail=(
                    f"invalid_nonnegative_counts={invalid_counts}; "
                    f"invalid_horizons={invalid_horizons}"
                ),
            )
            return result

    result.update(status="PASS", detail="schema and fail-closed E0 checks passed")
    return result


def run_audit(root: Path, config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))

    model_path = root / config["frozen_model_config_path"]
    universe_path = root / config["frozen_0050_universe_path"]
    financial_path = root / config["frozen_0050_financial_path"]
    checkpoint_path = root / config["frozen_0050_mops_checkpoint_path"]

    model = json.loads(model_path.read_text(encoding="utf-8"))
    actual_model_hash = canonical_hash(
        {"quality_rules": model["quality_rules"], "valuation_rules": model["valuation_rules"]}
    )
    actual_universe_hash = sha256_path(universe_path)
    if actual_model_hash != config["frozen_model_hash"]:
        raise ValueError("frozen model hash mismatch")
    if actual_universe_hash != config["frozen_0050_universe_hash"]:
        raise ValueError("frozen 0050 universe hash mismatch")

    _, universe = read_csv(universe_path)
    _, financials = read_csv(financial_path)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    universe_symbols = {row["symbol"].strip() for row in universe}
    financial_symbols = {row["symbol"].strip() for row in financials}
    financial_count = sum(row["sector_logic"].strip() == "FINANCIAL" for row in universe)
    external_financial_symbols = sorted(financial_symbols - universe_symbols)

    external_root = root / config["external_input_root"]
    inventory = []
    for kind, filename in config["required_external_inputs"].items():
        path = external_root / filename
        result = inspect_external_input(kind, path)
        result["path"] = path.relative_to(root).as_posix()
        inventory.append(result)

    input_by_kind = {row["input"]: row for row in inventory}
    membership_symbols: set[str] = set()
    security_symbols: set[str] = set()
    mops_symbols: set[str] = set()
    if input_by_kind["historical_membership"]["status"] == "PASS":
        _, rows = read_csv(external_root / config["required_external_inputs"]["historical_membership"])
        membership_symbols = {
            row["symbol"].strip()
            for row in rows
            if row["cohort_eligible"].strip().lower() in {"true", "1", "yes"}
            and row["is_0050_member"].strip().lower() in {"false", "0", "no"}
            and row["sector_logic"].strip().upper() != "FINANCIAL"
        }
    if input_by_kind["security_master"]["status"] == "PASS":
        _, rows = read_csv(external_root / config["required_external_inputs"]["security_master"])
        security_symbols = {row["symbol"].strip() for row in rows if row["symbol"].strip()}
    if input_by_kind["mops_coverage"]["status"] == "PASS":
        _, rows = read_csv(external_root / config["required_external_inputs"]["mops_coverage"])
        mops_symbols = {row["symbol"].strip() for row in rows if row["symbol"].strip()}

    cross_input_status = "BLOCKED"
    cross_input_evidence = "required inputs have not all passed schema/content validation"
    if membership_symbols and security_symbols and mops_symbols:
        missing_security = membership_symbols - security_symbols
        missing_mops = membership_symbols - mops_symbols
        if not missing_security and not missing_mops:
            cross_input_status = "PASS"
            cross_input_evidence = "all eligible external symbols appear in security-master and MOPS coverage inputs"
        else:
            cross_input_evidence = (
                f"eligible symbols missing from security master={len(missing_security)}; "
                f"missing from MOPS coverage={len(missing_mops)}"
            )

    support_status = "BLOCKED"
    support_evidence = input_by_kind["expected_support"]["detail"]
    if input_by_kind["expected_support"]["status"] == "PASS":
        _, support_rows = read_csv(external_root / config["required_external_inputs"]["expected_support"])
        actual_grid = {
            (row["dimension"].strip().upper(), row["bucket"].strip().upper(), int(row["horizon"]))
            for row in support_rows
            if _positive_int(row["horizon"]) is not None
        }
        required_grid = {
            (dimension, bucket, int(horizon))
            for dimension, buckets in config["primary_bucket_grid"].items()
            for bucket in buckets
            for horizon in config["primary_horizons"]
        }
        underpowered = [
            row
            for row in support_rows
            if (row["dimension"].strip().upper(), row["bucket"].strip().upper(), int(row["horizon"])) in required_grid
            and (
                int(row["expected_observations"]) < config["minimum_observations_per_bucket_horizon"]
                or int(row["expected_unique_issuers"]) < config["minimum_unique_issuers_per_bucket_horizon"]
            )
        ]
        overclaimed_issuer_cells = sum(
            int(row["expected_unique_issuers"]) > len(membership_symbols)
            for row in support_rows
        )
        missing_grid = required_grid - actual_grid
        if not missing_grid and not underpowered and not overclaimed_issuer_cells:
            support_status = "PASS"
            support_evidence = "all primary bucket/horizon cells meet the frozen minimum support gate"
        else:
            support_evidence = (
                f"missing_primary_cells={len(missing_grid)}; "
                f"underpowered_primary_cells={len(underpowered)}; "
                f"overclaimed_issuer_cells={overclaimed_issuer_cells}"
            )
    stop_conditions = [
        {
            "condition": "PIT_EXTERNAL_UNIVERSE",
            "status": "PASS" if input_by_kind["historical_membership"]["status"] == "PASS" else "BLOCKED",
            "evidence": input_by_kind["historical_membership"]["detail"],
        },
        {
            "condition": "SURVIVORSHIP_AND_DELISTING",
            "status": "PASS" if input_by_kind["security_master"]["status"] == "PASS" else "BLOCKED",
            "evidence": input_by_kind["security_master"]["detail"],
        },
        {
            "condition": "EXTERNAL_MOPS_PIT_COVERAGE",
            "status": "PASS" if input_by_kind["mops_coverage"]["status"] == "PASS" else "BLOCKED",
            "evidence": input_by_kind["mops_coverage"]["detail"],
        },
        {
            "condition": "EXPECTED_SUPPORT_BY_HORIZON",
            "status": support_status,
            "evidence": support_evidence,
        },
        {
            "condition": "CROSS_INPUT_SYMBOL_CLOSURE",
            "status": cross_input_status,
            "evidence": cross_input_evidence,
        },
    ]
    ready = all(row["status"] == "PASS" for row in stop_conditions)
    status = "READY_FOR_INDEPENDENT_E0_REVIEW" if ready else "DATA_NOT_READY"

    manifest: dict[str, Any] = {
        "contract_id": config["contract_id"],
        "stage": config["stage"],
        "issue": config["issue"],
        "audit_as_of_date": config["audit_as_of_date"],
        "status": status,
        "e1_return_analysis_gate": "PENDING_INDEPENDENT_E0_REVIEW" if ready else "BLOCKED",
        "frozen_identity": {
            "freeze_head": config["freeze_head"],
            "model_sha256": actual_model_hash,
            "original_0050_universe_sha256": actual_universe_hash,
            "original_0050_financial_sha256": sha256_path(financial_path),
            "original_0050_mops_checkpoint_sha256": sha256_path(checkpoint_path),
            "e0_config_sha256": sha256_path(config_path),
            "e0_audit_code_sha256": sha256_path(Path(__file__)),
        },
        "frozen_repository_coverage": {
            "current_0050_universe_rows": len(universe),
            "current_0050_unique_symbols": len(universe_symbols),
            "current_0050_non_financial_symbols": len(universe) - financial_count,
            "current_0050_financial_symbols": financial_count,
            "normalized_financial_rows": len(financials),
            "normalized_financial_unique_symbols": len(financial_symbols),
            "normalized_external_symbols": len(external_financial_symbols),
            "mops_checkpoint_successful_company_archives": checkpoint["completion"]["successful_company_archives"],
            "historical_membership_available": input_by_kind["historical_membership"]["status"] == "PASS",
            "survivorship_or_delisting_coverage_available": input_by_kind["security_master"]["status"] == "PASS",
        },
        "external_inputs": inventory,
        "stop_conditions": stop_conditions,
        "governance": {
            "network_requests_performed": 0,
            "future_returns_computed": False,
            "outcome_files_read": [],
            "frozen_model_modified": False,
            "thresholds_modified": False,
            "composite_score_created": False,
            "external_cohort_frozen": ready,
        },
        "next_allowed_action": (
            "independent E0 review; do not open outcomes before the pre-result checkpoint"
            if ready
            else "acquire and freeze the four required PIT inputs, then rerun E0; E1 remains forbidden"
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "e0_readiness_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "e0_input_inventory.csv",
        ["input", "path", "status", "rows", "sha256", "detail"],
        inventory,
    )
    write_csv(
        output_dir / "e0_stop_conditions.csv",
        ["condition", "status", "evidence"],
        stop_conditions,
    )
    support_rows = []
    for horizon in config["primary_horizons"]:
        support_rows.append(
            {
                "horizon": horizon,
                "expected_observations": "",
                "expected_unique_issuers": "",
                "support_status": "NOT_ESTIMABLE" if not ready else "SEE_FROZEN_EXTERNAL_INPUT",
            }
        )
    write_csv(
        output_dir / "e0_expected_support.csv",
        ["horizon", "expected_observations", "expected_unique_issuers", "support_status"],
        support_rows,
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed Stage E0 external-universe readiness audit; never reads outcomes."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = run_audit(ROOT, args.config, args.output_dir)
    print(json.dumps({"status": manifest["status"], "gate": manifest["e1_return_analysis_gate"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
