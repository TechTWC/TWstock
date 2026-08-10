from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_live_smoke import (
    EXPECTED_CORPORATE_ACTION_DATASETS,
    EXPECTED_OUTPUTS,
    LiveSmokeValidationError,
    main,
    validate_live_smoke,
)


TOKEN = "TEST_FINMIND_SECRET_12345"
START = "2025-07-10"
END = "2026-08-10"
SYMBOL = "2330.TW"
DATASET_HASH = "a" * 64
CORPORATE_HASH = "b" * 64
CONTINUOUS_HASH = "4" * 64
BREAKOUT_HASH = "5" * 64
RESEARCH_HASH = hashlib.sha256(
    json.dumps(
        {
            "schema_version": "TWSTOCK-GUARDED-RESEARCH-INPUT-001",
            "market_dataset_hash": DATASET_HASH,
            "corporate_action_dataset_hash": CORPORATE_HASH,
            "corporate_action_policy_version": "CA-GUARD-001",
            "continuous_high_parameter_hash": CONTINUOUS_HASH,
            "breakout_config_hash": BREAKOUT_HASH,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()
RAW_HASHES = ["d" * 64, "e" * 64, "f" * 64, "1" * 64]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _build_valid_tree(root: Path) -> tuple[Path, Path]:
    output = root / "output"
    raw = root / "raw"
    output.mkdir()
    raw.mkdir()
    datasets = sorted(EXPECTED_CORPORATE_ACTION_DATASETS)
    run_manifest = {
        "schema_version": "TWSTOCK-REAL-MARKET-RUN-002",
        "run_type": "BOUNDED_EXPLORATORY_REAL_DATA",
        "canonical_symbol": SYMBOL,
        "requested_start": START,
        "requested_end": END,
        "dataset_hash": DATASET_HASH,
        "corporate_action_dataset_hash": CORPORATE_HASH,
        "research_input_hash": RESEARCH_HASH,
        "dataset_source_state": "PRIMARY_VERIFIED",
        "dataset_cross_check_unavailable": False,
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_actions_applied": False,
        "corporate_action_guard_applied": True,
        "corporate_action_coverage_state": "SECONDARY_COMPLETE",
        "corporate_action_source_tier": "SECONDARY",
        "corporate_action_policy_version": "CA-GUARD-001",
        "corporate_action_event_count": 0,
        "continuous_high_parameter_hash": CONTINUOUS_HASH,
        "breakout_config_hash": BREAKOUT_HASH,
        "bar_count": 2,
        "analysis_blocked_row_count": 0,
        "outputs": EXPECTED_OUTPUTS,
        "status": "EXPLORATORY_NOT_VALIDATED",
    }
    dataset_manifest = {
        "schema_version": "TWSTOCK-RESEARCH-DATASET-001",
        "requested_symbol": "2330",
        "source_symbol": "2330",
        "canonical_symbol": SYMBOL,
        "requested_start": START,
        "requested_end": END,
        "source_state": "PRIMARY_VERIFIED",
        "selected_source": "TWSE",
        "cross_check_unavailable": False,
        "record_count": 2,
        "first_trade_date": "2025-07-10",
        "last_trade_date": "2026-08-10",
        "dataset_hash": DATASET_HASH,
        "raw_content_hashes": ["2" * 64],
        "verification_sources": ["FinMind"],
        "verification_raw_content_hashes": ["3" * 64],
        "reconciliation_issue_count": 0,
        "price_basis": "RAW_OFFICIAL_DAILY",
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_actions_applied": False,
    }
    evidence = [
        {
            "source": "FinMind",
            "source_tier": "SECONDARY",
            "source_dataset": dataset,
            "retrieved_at": "2026-08-10T00:00:00+00:00",
            "source_reference": (
                "https://api.finmindtrade.com/api/v4/data"
                f"?dataset={dataset}&data_id=2330&start_date={START}&end_date={END}"
            ),
            "raw_content_hash": RAW_HASHES[index],
        }
        for index, dataset in enumerate(datasets)
    ]
    corporate_manifest = {
        "schema_version": "TWSTOCK-CORPORATE-ACTIONS-001",
        "requested_symbol": "2330",
        "source_symbol": "2330",
        "canonical_symbol": SYMBOL,
        "requested_start": START,
        "requested_end": END,
        "coverage_state": "SECONDARY_COMPLETE",
        "source": "FinMind",
        "source_tier": "SECONDARY",
        "policy_version": "CA-GUARD-001",
        "knowledge_policy": "EFFECTIVE_DATE_CONSERVATIVE",
        "source_datasets": datasets,
        "source_evidence": evidence,
        "event_count": 0,
        "dataset_hash": CORPORATE_HASH,
        "raw_content_hashes": RAW_HASHES,
    }
    (output / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    (output / "dataset_manifest.json").write_text(
        json.dumps(dataset_manifest), encoding="utf-8"
    )
    (output / "corporate_action_manifest.json").write_text(
        json.dumps(corporate_manifest), encoding="utf-8"
    )
    _write_csv(
        output / "market_bars.csv",
        ["symbol", "trade_date"],
        [
            {"symbol": SYMBOL, "trade_date": "2025-07-10"},
            {"symbol": SYMBOL, "trade_date": "2026-08-10"},
        ],
    )
    _write_csv(
        output / "corporate_actions.csv",
        [
            "event_id",
            "source_dataset",
            "canonical_symbol",
            "event_type",
            "effective_date",
        ],
        [],
    )
    guard_rows = [
        {
            "symbol": SYMBOL,
            "trade_date": trade_date,
            "analyzer": analyzer,
            "state": "ALLOWED",
        }
        for analyzer in ("CONTINUOUS_HIGH", "BREAKOUT_TRACKER")
        for trade_date in ("2025-07-10", "2026-08-10")
    ]
    _write_csv(
        output / "analysis_guard.csv",
        ["symbol", "trade_date", "analyzer", "state"],
        guard_rows,
    )
    for filename in (
        "continuous_high_timeline.csv",
        "continuous_high_features.csv",
        "breakout_snapshots.csv",
    ):
        (output / filename).write_text("header\n", encoding="utf-8")
    (output / "continuous_high.html").write_text("<html></html>", encoding="utf-8")
    (raw / "source.metadata.json").write_text(
        json.dumps({"sanitized_source_url": "https://example.invalid/data"}),
        encoding="utf-8",
    )
    return output, raw


class ValidateLiveSmokeTests(unittest.TestCase):
    def _validate(self, output: Path, raw: Path):
        with patch.dict(os.environ, {"FINMIND_TOKEN": TOKEN}, clear=False):
            return validate_live_smoke(
                output_dir=output,
                raw_cache_dir=raw,
                expected_symbol=SYMBOL,
                expected_start=START,
                expected_end=END,
            )

    def test_valid_contract_passes_without_returning_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            summary = self._validate(output, raw)
        self.assertEqual(summary["status"], "LIVE_SMOKE_VALIDATED")
        self.assertEqual(summary["bar_count"], 2)
        self.assertNotIn(TOKEN, json.dumps(summary))

    def test_primary_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "run_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["dataset_source_state"] = "SOURCE_MISMATCH"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "dataset_source_state"):
                self._validate(output, raw)

    def test_cross_check_unavailable_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "dataset_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["cross_check_unavailable"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "cross_check_unavailable"):
                self._validate(output, raw)

    def test_incomplete_corporate_action_coverage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "corporate_action_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["source_datasets"] = payload["source_datasets"][:-1]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "four required"):
                self._validate(output, raw)

    def test_corporate_action_source_reference_is_exact_and_credential_free(self) -> None:
        unsafe_references = (
            (
                "https://api.finmindtrade.com.evil.invalid/api/v4/data"
                f"?dataset=TaiwanStockDividendResult&data_id=2330&start_date={START}&end_date={END}"
            ),
            (
                "https://api.finmindtrade.com/api/v4/data"
                f"?dataset=TaiwanStockDividendResult&data_id=2330&start_date={START}&end_date={END}"
                "&token=redacted"
            ),
            (
                "https://api.finmindtrade.com/api/v4/data"
                f"?dataset=TaiwanStockDividendResult&data_id=2330&data_id=2317"
                f"&start_date={START}&end_date={END}"
            ),
        )
        for source_reference in unsafe_references:
            with self.subTest(source_reference=source_reference[:60]):
                with tempfile.TemporaryDirectory() as directory:
                    output, raw = _build_valid_tree(Path(directory))
                    path = output / "corporate_action_manifest.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    dividend = next(
                        item
                        for item in payload["source_evidence"]
                        if item["source_dataset"] == "TaiwanStockDividendResult"
                    )
                    dividend["source_reference"] = source_reference
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(LiveSmokeValidationError):
                        self._validate(output, raw)

    def test_manifest_hash_disagreement_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "dataset_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["dataset_hash"] = "9" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "manifests disagree"):
                self._validate(output, raw)

    def test_research_input_hash_must_bind_declared_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "run_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["research_input_hash"] = "9" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "detached"):
                self._validate(output, raw)

    def test_missing_required_output_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            (output / "analysis_guard.csv").unlink()
            with self.assertRaisesRegex(LiveSmokeValidationError, "missing or unsafe"):
                self._validate(output, raw)

    def test_unexpected_output_mapping_fails_before_path_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "run_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["outputs"]["market_bars"] = "../market_bars.csv"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(LiveSmokeValidationError, "output contract"):
                self._validate(output, raw)

    def test_exact_token_in_manifest_fails_without_echoing_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "dataset_manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["unsafe"] = TOKEN
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(LiveSmokeValidationError) as caught:
                self._validate(output, raw)
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_generic_bearer_header_and_token_query_fail(self) -> None:
        for unsafe in (b"Authorization: Bearer REDACTED", b"https://x.invalid/?token=redacted"):
            with self.subTest(unsafe=unsafe[:12]):
                with tempfile.TemporaryDirectory() as directory:
                    output, raw = _build_valid_tree(Path(directory))
                    (raw / "unsafe.raw").write_bytes(unsafe)
                    with self.assertRaisesRegex(
                        LiveSmokeValidationError, "authentication material"
                    ):
                        self._validate(output, raw)

    def test_missing_token_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(LiveSmokeValidationError, "missing or invalid"):
                    validate_live_smoke(
                        output_dir=output,
                        raw_cache_dir=raw,
                        expected_symbol=SYMBOL,
                        expected_start=START,
                        expected_end=END,
                    )

    def test_guard_row_count_and_blocked_count_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            with (output / "analysis_guard.csv").open("a", encoding="utf-8") as handle:
                handle.write("2330.TW,2026-08-10,EXTRA,ALLOWED\n")
            with self.assertRaisesRegex(LiveSmokeValidationError, "two analyzer rows"):
                self._validate(output, raw)

    def test_duplicate_guard_pair_cannot_hide_missing_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            path = output / "analysis_guard.csv"
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[-1] = dict(rows[0])
            _write_csv(path, ["symbol", "trade_date", "analyzer", "state"], rows)
            with self.assertRaisesRegex(LiveSmokeValidationError, "per market date"):
                self._validate(output, raw)

    def test_symlinked_required_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            target = output / "real.html"
            target.write_text("<html></html>", encoding="utf-8")
            (output / "continuous_high.html").unlink()
            try:
                (output / "continuous_high.html").symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(LiveSmokeValidationError, "missing or unsafe"):
                self._validate(output, raw)

    def test_symlinked_raw_cache_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            target = Path(directory) / "outside"
            target.mkdir()
            try:
                (raw / "linked-directory").symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(LiveSmokeValidationError, "symlink"):
                self._validate(output, raw)

    def test_cli_failure_is_secret_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, raw = _build_valid_tree(Path(directory))
            (raw / "unsafe.raw").write_text(TOKEN, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(os.environ, {"FINMIND_TOKEN": TOKEN}, clear=False):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(
                        [
                            "--output-dir",
                            str(output),
                            "--raw-cache-dir",
                            str(raw),
                            "--expected-symbol",
                            SYMBOL,
                            "--expected-start",
                            START,
                            "--expected-end",
                            END,
                        ]
                    )
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
