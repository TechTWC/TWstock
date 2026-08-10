from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, quote, urlsplit


EXPECTED_OUTPUTS = {
    "market_bars": "market_bars.csv",
    "dataset_manifest": "dataset_manifest.json",
    "corporate_actions": "corporate_actions.csv",
    "corporate_action_manifest": "corporate_action_manifest.json",
    "analysis_guard": "analysis_guard.csv",
    "continuous_high_timeline": "continuous_high_timeline.csv",
    "continuous_high_features": "continuous_high_features.csv",
    "continuous_high_html": "continuous_high.html",
    "breakout_snapshots": "breakout_snapshots.csv",
}
EXPECTED_CORPORATE_ACTION_DATASETS = {
    "TaiwanStockDividendResult",
    "TaiwanStockCapitalReductionReferencePrice",
    "TaiwanStockSplitPrice",
    "TaiwanStockParValueChange",
}
FINMIND_DATA_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_TW_SYMBOL_RE = re.compile(r"^([0-9]{4,6})\.TW$")
TOKEN_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
FORBIDDEN_RETAINED_PATTERNS = (
    re.compile(rb"authorization\s*[:=]\s*bearer", re.IGNORECASE),
    re.compile(rb"(?:[?&]|%26|\\u0026)token(?:=|%3d)", re.IGNORECASE),
)
MAX_SCAN_FILE_BYTES = 25 * 1024 * 1024
MAX_SCAN_TOTAL_BYTES = 250 * 1024 * 1024


class LiveSmokeValidationError(RuntimeError):
    """A fail-closed live-smoke contract violation with a secret-safe message."""


def _fail(message: str) -> None:
    raise LiveSmokeValidationError(message)


def _require_exact(mapping: dict[str, object], key: str, expected: object, label: str) -> None:
    if key not in mapping or type(mapping[key]) is not type(expected) or mapping[key] != expected:
        _fail(f"{label}.{key} does not match the required contract")


def _require_int(mapping: dict[str, object], key: str, label: str, *, minimum: int = 0) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{label}.{key} must be an integer >= {minimum}")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _require_string_list(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(f"{label} must be a list of strings")
    if nonempty and not value:
        _fail(f"{label} must not be empty")
    return value


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail(f"{label} is missing, unreadable, or invalid JSON")
    if not isinstance(payload, dict):
        _fail(f"{label} must contain a JSON object")
    return payload


def _safe_required_file(root: Path, filename: str) -> Path:
    if Path(filename).name != filename or filename in {"", ".", ".."}:
        _fail("run_manifest.outputs contains an unsafe path")
    path = root / filename
    if path.is_symlink() or not path.is_file():
        _fail(f"required output file is missing or unsafe: {filename}")
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(f"required output escapes output directory: {filename}")
    return path


def _read_csv_rows(path: Path, required_fields: set[str], label: str) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            if not required_fields.issubset(fields):
                _fail(f"{label} is missing required columns")
            return list(reader)
    except (OSError, UnicodeError, csv.Error):
        _fail(f"{label} is unreadable or invalid CSV")


def _validate_requested_identity(
    manifest: dict[str, object],
    label: str,
    *,
    expected_requested_symbol: str,
    expected_canonical_symbol: str,
    expected_start: str,
    expected_end: str,
) -> None:
    if "requested_symbol" in manifest:
        _require_exact(manifest, "requested_symbol", expected_requested_symbol, label)
    _require_exact(manifest, "canonical_symbol", expected_canonical_symbol, label)
    _require_exact(manifest, "requested_start", expected_start, label)
    _require_exact(manifest, "requested_end", expected_end, label)


def _validate_market_manifest(
    manifest: dict[str, object],
    *,
    expected_requested_symbol: str,
    expected_symbol: str,
    expected_start: str,
    expected_end: str,
) -> tuple[str, int]:
    label = "dataset_manifest"
    _require_exact(manifest, "schema_version", "TWSTOCK-RESEARCH-DATASET-001", label)
    _validate_requested_identity(
        manifest,
        label,
        expected_requested_symbol=expected_requested_symbol,
        expected_canonical_symbol=expected_symbol,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    _require_exact(manifest, "source_state", "PRIMARY_VERIFIED", label)
    _require_exact(manifest, "selected_source", "TWSE", label)
    _require_exact(manifest, "cross_check_unavailable", False, label)
    _require_exact(manifest, "reconciliation_issue_count", 0, label)
    _require_exact(manifest, "price_basis", "RAW_OFFICIAL_DAILY", label)
    _require_exact(manifest, "adjustment_policy", "RAW_UNADJUSTED", label)
    _require_exact(manifest, "corporate_actions_applied", False, label)
    record_count = _require_int(manifest, "record_count", label, minimum=1)
    dataset_hash = _require_sha256(manifest.get("dataset_hash"), f"{label}.dataset_hash")
    raw_hashes = _require_string_list(
        manifest.get("raw_content_hashes"), f"{label}.raw_content_hashes", nonempty=True
    )
    verification_hashes = _require_string_list(
        manifest.get("verification_raw_content_hashes"),
        f"{label}.verification_raw_content_hashes",
        nonempty=True,
    )
    if any(not SHA256_RE.fullmatch(item) for item in (*raw_hashes, *verification_hashes)):
        _fail(f"{label} contains an invalid source content hash")
    if _require_string_list(
        manifest.get("verification_sources"), f"{label}.verification_sources", nonempty=True
    ) != ["FinMind"]:
        _fail(f"{label}.verification_sources must contain only FinMind")
    try:
        first_trade_date = date.fromisoformat(str(manifest["first_trade_date"]))
        last_trade_date = date.fromisoformat(str(manifest["last_trade_date"]))
        start = date.fromisoformat(expected_start)
        end = date.fromisoformat(expected_end)
    except (KeyError, TypeError, ValueError):
        _fail(f"{label} contains invalid trade-date bounds")
    if not start <= first_trade_date <= last_trade_date <= end:
        _fail(f"{label} trade-date bounds escape the requested period")
    return dataset_hash, record_count


def _validate_corporate_action_manifest(
    manifest: dict[str, object],
    *,
    expected_requested_symbol: str,
    expected_symbol: str,
    expected_start: str,
    expected_end: str,
) -> tuple[str, int]:
    label = "corporate_action_manifest"
    _require_exact(manifest, "schema_version", "TWSTOCK-CORPORATE-ACTIONS-001", label)
    _validate_requested_identity(
        manifest,
        label,
        expected_requested_symbol=expected_requested_symbol,
        expected_canonical_symbol=expected_symbol,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    _require_exact(manifest, "coverage_state", "SECONDARY_COMPLETE", label)
    _require_exact(manifest, "source", "FinMind", label)
    _require_exact(manifest, "source_tier", "SECONDARY", label)
    _require_exact(manifest, "policy_version", "CA-GUARD-001", label)
    _require_exact(manifest, "knowledge_policy", "EFFECTIVE_DATE_CONSERVATIVE", label)
    datasets = _require_string_list(
        manifest.get("source_datasets"), f"{label}.source_datasets", nonempty=True
    )
    if len(datasets) != 4 or set(datasets) != EXPECTED_CORPORATE_ACTION_DATASETS:
        _fail(f"{label} does not contain the four required FinMind datasets")
    event_count = _require_int(manifest, "event_count", label)
    dataset_hash = _require_sha256(manifest.get("dataset_hash"), f"{label}.dataset_hash")
    evidence = manifest.get("source_evidence")
    if not isinstance(evidence, list) or len(evidence) != 4:
        _fail(f"{label}.source_evidence must contain four entries")
    evidence_datasets: list[str] = []
    evidence_hashes: list[str] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            _fail(f"{label}.source_evidence[{index}] must be an object")
        _require_exact(item, "source", "FinMind", f"{label}.source_evidence[{index}]")
        _require_exact(item, "source_tier", "SECONDARY", f"{label}.source_evidence[{index}]")
        source_dataset = item.get("source_dataset")
        if not isinstance(source_dataset, str):
            _fail(f"{label}.source_evidence[{index}].source_dataset is invalid")
        _validate_finmind_source_reference(
            item.get("source_reference"),
            expected_dataset=source_dataset,
            expected_source_symbol=expected_requested_symbol,
            expected_start=expected_start,
            expected_end=expected_end,
            label=f"{label}.source_evidence[{index}].source_reference",
        )
        evidence_datasets.append(source_dataset)
        evidence_hashes.append(
            _require_sha256(
                item.get("raw_content_hash"),
                f"{label}.source_evidence[{index}].raw_content_hash",
            )
        )
        if not isinstance(item.get("retrieved_at"), str) or not item["retrieved_at"]:
            _fail(f"{label}.source_evidence[{index}].retrieved_at is invalid")
    if len(set(evidence_datasets)) != 4 or set(evidence_datasets) != EXPECTED_CORPORATE_ACTION_DATASETS:
        _fail(f"{label}.source_evidence does not cover each required dataset exactly once")
    manifest_hashes = _require_string_list(
        manifest.get("raw_content_hashes"), f"{label}.raw_content_hashes", nonempty=True
    )
    if sorted(manifest_hashes) != sorted(evidence_hashes):
        _fail(f"{label}.raw_content_hashes do not match source evidence")
    return dataset_hash, event_count


def _validate_finmind_source_reference(
    value: object,
    *,
    expected_dataset: str,
    expected_source_symbol: str,
    expected_start: str,
    expected_end: str,
    label: str,
) -> None:
    if not isinstance(value, str):
        _fail(f"{label} must be a sanitized FinMind URL")
    try:
        parts = urlsplit(value)
        query_items = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        port = parts.port
    except ValueError:
        _fail(f"{label} must be a valid sanitized FinMind URL")
    if (
        parts.scheme != "https"
        or (parts.hostname or "").lower() != "api.finmindtrade.com"
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
        or parts.path != "/api/v4/data"
        or parts.fragment
    ):
        _fail(f"{label} does not use the exact FinMind HTTPS data endpoint")
    expected_query = sorted(
        [
            ("dataset", expected_dataset),
            ("data_id", expected_source_symbol),
            ("start_date", expected_start),
            ("end_date", expected_end),
        ]
    )
    if sorted(query_items) != expected_query or len(query_items) != len(expected_query):
        _fail(f"{label} contains unexpected, duplicate, missing, or credential query fields")


def _scan_retained_files(roots: tuple[Path, ...], token: str) -> tuple[int, int]:
    token_bytes = token.encode("utf-8")
    encoded_token = quote(token, safe="").encode("ascii")
    needles = {token_bytes, encoded_token}
    file_count = 0
    total_bytes = 0
    seen: set[Path] = set()
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            _fail("retained output or raw-cache directory is missing or unsafe")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                _fail("retained output contains a symlink or unsupported file")
            if path.is_dir():
                continue
            if not path.is_file():
                _fail("retained output contains a symlink or unsupported file")
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            size = path.stat().st_size
            if size > MAX_SCAN_FILE_BYTES:
                _fail("retained output contains a file that exceeds the scan limit")
            total_bytes += size
            if total_bytes > MAX_SCAN_TOTAL_BYTES:
                _fail("retained output exceeds the total scan limit")
            try:
                content = path.read_bytes()
            except OSError:
                _fail("retained output contains an unreadable file")
            if any(needle and needle in content for needle in needles):
                _fail("retained output contains the configured FinMind token")
            if any(pattern.search(content) for pattern in FORBIDDEN_RETAINED_PATTERNS):
                _fail("retained output contains forbidden authentication material")
            file_count += 1
    if file_count == 0:
        _fail("no retained files were available for credential scanning")
    return file_count, total_bytes


def validate_live_smoke(
    *,
    output_dir: Path,
    raw_cache_dir: Path,
    expected_symbol: str,
    expected_start: str,
    expected_end: str,
    token_env_name: str = "FINMIND_TOKEN",
) -> dict[str, object]:
    match = CANONICAL_TW_SYMBOL_RE.fullmatch(expected_symbol)
    if match is None:
        _fail("expected_symbol must be a canonical Taiwan symbol")
    try:
        start = date.fromisoformat(expected_start)
        end = date.fromisoformat(expected_end)
    except ValueError:
        _fail("expected date range must use valid ISO dates")
    if start > end:
        _fail("expected date range is reversed")
    if not TOKEN_ENV_RE.fullmatch(token_env_name):
        _fail("token environment variable name is invalid")
    token = os.environ.get(token_env_name, "")
    if len(token) < 8 or token.strip() != token:
        _fail("configured FinMind token is missing or invalid")

    output_dir = Path(output_dir)
    raw_cache_dir = Path(raw_cache_dir)
    run_path = _safe_required_file(output_dir, "run_manifest.json")
    run_manifest = _read_json(run_path, "run_manifest")
    outputs = run_manifest.get("outputs")
    if not isinstance(outputs, dict) or outputs != EXPECTED_OUTPUTS:
        _fail("run_manifest.outputs does not match the guarded output contract")
    output_paths = {
        key: _safe_required_file(output_dir, filename)
        for key, filename in EXPECTED_OUTPUTS.items()
    }
    scanned_files, scanned_bytes = _scan_retained_files((output_dir, raw_cache_dir), token)

    expected_requested_symbol = match.group(1)
    _require_exact(run_manifest, "schema_version", "TWSTOCK-REAL-MARKET-RUN-002", "run_manifest")
    _require_exact(run_manifest, "run_type", "BOUNDED_EXPLORATORY_REAL_DATA", "run_manifest")
    _validate_requested_identity(
        run_manifest,
        "run_manifest",
        expected_requested_symbol=expected_requested_symbol,
        expected_canonical_symbol=expected_symbol,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    _require_exact(run_manifest, "dataset_source_state", "PRIMARY_VERIFIED", "run_manifest")
    _require_exact(run_manifest, "dataset_cross_check_unavailable", False, "run_manifest")
    _require_exact(run_manifest, "price_basis", "RAW_OFFICIAL_DAILY", "run_manifest")
    _require_exact(run_manifest, "adjustment_policy", "RAW_UNADJUSTED", "run_manifest")
    _require_exact(run_manifest, "corporate_actions_applied", False, "run_manifest")
    _require_exact(run_manifest, "corporate_action_guard_applied", True, "run_manifest")
    _require_exact(
        run_manifest, "corporate_action_coverage_state", "SECONDARY_COMPLETE", "run_manifest"
    )
    _require_exact(run_manifest, "corporate_action_source_tier", "SECONDARY", "run_manifest")
    _require_exact(run_manifest, "corporate_action_policy_version", "CA-GUARD-001", "run_manifest")
    _require_exact(run_manifest, "status", "EXPLORATORY_NOT_VALIDATED", "run_manifest")
    bar_count = _require_int(run_manifest, "bar_count", "run_manifest", minimum=1)
    run_event_count = _require_int(run_manifest, "corporate_action_event_count", "run_manifest")
    blocked_count = _require_int(run_manifest, "analysis_blocked_row_count", "run_manifest")
    run_dataset_hash = _require_sha256(
        run_manifest.get("dataset_hash"), "run_manifest.dataset_hash"
    )
    run_corporate_hash = _require_sha256(
        run_manifest.get("corporate_action_dataset_hash"),
        "run_manifest.corporate_action_dataset_hash",
    )
    continuous_hash = _require_sha256(
        run_manifest.get("continuous_high_parameter_hash"),
        "run_manifest.continuous_high_parameter_hash",
    )
    breakout_hash = _require_sha256(
        run_manifest.get("breakout_config_hash"), "run_manifest.breakout_config_hash"
    )
    research_input_hash = _require_sha256(
        run_manifest.get("research_input_hash"), "run_manifest.research_input_hash"
    )
    expected_research_input_hash = hashlib.sha256(
        json.dumps(
            {
                "schema_version": "TWSTOCK-GUARDED-RESEARCH-INPUT-001",
                "market_dataset_hash": run_dataset_hash,
                "corporate_action_dataset_hash": run_corporate_hash,
                "corporate_action_policy_version": "CA-GUARD-001",
                "continuous_high_parameter_hash": continuous_hash,
                "breakout_config_hash": breakout_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if research_input_hash != expected_research_input_hash:
        _fail("run_manifest.research_input_hash is detached from its declared inputs")

    dataset_manifest = _read_json(output_paths["dataset_manifest"], "dataset_manifest")
    dataset_hash, dataset_record_count = _validate_market_manifest(
        dataset_manifest,
        expected_requested_symbol=expected_requested_symbol,
        expected_symbol=expected_symbol,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    corporate_manifest = _read_json(
        output_paths["corporate_action_manifest"], "corporate_action_manifest"
    )
    corporate_hash, corporate_event_count = _validate_corporate_action_manifest(
        corporate_manifest,
        expected_requested_symbol=expected_requested_symbol,
        expected_symbol=expected_symbol,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    if run_dataset_hash != dataset_hash or bar_count != dataset_record_count:
        _fail("run and market dataset manifests disagree")
    if run_corporate_hash != corporate_hash or run_event_count != corporate_event_count:
        _fail("run and corporate-action manifests disagree")

    market_rows = _read_csv_rows(
        output_paths["market_bars"], {"symbol", "trade_date"}, "market_bars.csv"
    )
    corporate_rows = _read_csv_rows(
        output_paths["corporate_actions"],
        {
            "event_id",
            "source_dataset",
            "canonical_symbol",
            "event_type",
            "effective_date",
        },
        "corporate_actions.csv",
    )
    guard_rows = _read_csv_rows(
        output_paths["analysis_guard"],
        {"symbol", "trade_date", "analyzer", "state"},
        "analysis_guard.csv",
    )
    if len(market_rows) != bar_count:
        _fail("market_bars.csv row count does not match manifests")
    if len(corporate_rows) != run_event_count:
        _fail("corporate_actions.csv row count does not match manifests")
    if len(guard_rows) != bar_count * 2:
        _fail("analysis_guard.csv must contain two analyzer rows per market bar")
    if any(row.get("symbol") != expected_symbol for row in market_rows):
        _fail("market_bars.csv contains an unexpected symbol")
    if any(row.get("canonical_symbol") != expected_symbol for row in corporate_rows):
        _fail("corporate_actions.csv contains an unexpected symbol")
    if any(row.get("symbol") != expected_symbol for row in guard_rows):
        _fail("analysis_guard.csv contains an unexpected symbol")
    market_dates = [row.get("trade_date") for row in market_rows]
    if any(not isinstance(item, str) or not item for item in market_dates):
        _fail("market_bars.csv contains an invalid trade date")
    if len(set(market_dates)) != bar_count:
        _fail("market_bars.csv contains duplicate trade dates")
    try:
        parsed_market_dates = [date.fromisoformat(item) for item in market_dates]
    except ValueError:
        _fail("market_bars.csv contains a non-ISO trade date")
    if parsed_market_dates != sorted(parsed_market_dates):
        _fail("market_bars.csv trade dates are not strictly ascending")
    if (
        market_dates[0] != dataset_manifest.get("first_trade_date")
        or market_dates[-1] != dataset_manifest.get("last_trade_date")
        or not all(start <= item <= end for item in parsed_market_dates)
    ):
        _fail("market_bars.csv date bounds do not match the dataset manifest")
    event_ids = [row.get("event_id") for row in corporate_rows]
    if any(not isinstance(item, str) or not item for item in event_ids):
        _fail("corporate_actions.csv contains an invalid event ID")
    if len(set(event_ids)) != len(event_ids):
        _fail("corporate_actions.csv contains duplicate event IDs")
    try:
        event_dates = [date.fromisoformat(str(row.get("effective_date"))) for row in corporate_rows]
    except ValueError:
        _fail("corporate_actions.csv contains a non-ISO effective date")
    if any(not start <= item <= end for item in event_dates):
        _fail("corporate_actions.csv contains an event outside the requested period")
    if any(
        row.get("source_dataset") not in EXPECTED_CORPORATE_ACTION_DATASETS
        for row in corporate_rows
    ):
        _fail("corporate_actions.csv contains an unexpected source dataset")
    required_analyzers = {"CONTINUOUS_HIGH", "BREAKOUT_TRACKER"}
    expected_guard_keys = {
        (analyzer, trade_date)
        for analyzer in required_analyzers
        for trade_date in market_dates
    }
    observed_guard_keys = {
        (row.get("analyzer"), row.get("trade_date")) for row in guard_rows
    }
    if len(observed_guard_keys) != len(guard_rows) or observed_guard_keys != expected_guard_keys:
        _fail("analysis_guard.csv does not contain exactly two analyzer rows per market date")
    if sum(row.get("state") == "ANALYSIS_BLOCKED" for row in guard_rows) != blocked_count:
        _fail("analysis_guard.csv blocked count does not match run manifest")
    if any(row.get("state") not in {"ALLOWED", "ANALYSIS_BLOCKED"} for row in guard_rows):
        _fail("analysis_guard.csv contains an unsupported state")

    return {
        "status": "LIVE_SMOKE_VALIDATED",
        "canonical_symbol": expected_symbol,
        "requested_start": expected_start,
        "requested_end": expected_end,
        "bar_count": bar_count,
        "corporate_action_event_count": run_event_count,
        "analysis_blocked_row_count": blocked_count,
        "scanned_file_count": scanned_files,
        "scanned_byte_count": scanned_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed validation for the guarded real-market live smoke output."
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--raw-cache-dir", required=True, type=Path)
    parser.add_argument("--expected-symbol", required=True)
    parser.add_argument("--expected-start", required=True)
    parser.add_argument("--expected-end", required=True)
    parser.add_argument("--token-env-name", default="FINMIND_TOKEN")
    args = parser.parse_args(argv)
    try:
        summary = validate_live_smoke(
            output_dir=args.output_dir,
            raw_cache_dir=args.raw_cache_dir,
            expected_symbol=args.expected_symbol,
            expected_start=args.expected_start,
            expected_end=args.expected_end,
            token_env_name=args.token_env_name,
        )
    except LiveSmokeValidationError as exc:
        print(f"live-smoke validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
