from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
import shutil

import pandas as pd
import numpy as np
import pytest

from experiments.fundamental_quality_valuation.mops import (
    MopsFilingRecord,
    select_mops_filings,
)
from experiments.fundamental_quality_valuation.stage_a import (
    AVAILABLE_DATE_PROXY,
    MOPS_EXACT,
    build_financial_timeline,
    build_signal_timeline,
    canonical_hash,
    load_offline_mops_archive,
)
from scripts.checkpoint_0050_mops_cache_v0_1 import restore_checkpoint, verify_checkpoint
from scripts.run_0050_fundamental_stage_a import (
    EXPECTED_FIXED_COHORT_SHA256,
    EXPECTED_SELECTED_FILING_HASH,
    _load_universe,
    _selected_filing_hash,
    _validate_normalized_symbol_set,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "artifacts/0050_fundamental_v0_1/checkpoints/mops_20260904"
EXPECTED_FROZEN_RULES_HASH = "8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f"


def _filing(
    *,
    symbol: str = "2330",
    quarter: int = 1,
    timestamp: str = "2025-05-08T15:30:00+08:00",
    kind: str = "CONSOLIDATED",
    identifier: str = "202501_2330_AI1.pdf",
    correction: str = "無",
) -> MopsFilingRecord:
    month = quarter * 3
    day = 31 if month in {3, 12} else 30
    period_end = date(2025, month, day).isoformat()
    return MopsFilingRecord(
        symbol=symbol,
        fiscal_year=2025,
        fiscal_quarter=quarter,
        period_end=period_end,
        announcement_date=timestamp[:10],
        announcement_timestamp=timestamp,
        source="MOPS official electronic document archive",
        source_url="https://example.invalid/frozen-provenance-only",
        source_identifier=identifier,
        source_provenance="TWSE_MOPS_T57SB01_OFFICIAL_DOCUMENT_UPLOAD",
        retrieval_timestamp="2026-09-04T00:00:00+00:00",
        response_sha256="a" * 64,
        source_hash=canonical_hash({"identifier": identifier, "timestamp": timestamp}),
        document_kind=kind,
        document_detail="IFRSs合併財報",
        file_size_bytes=123,
        correction_status=correction,
    )


def _normalized(period_end: str = "2025-03-31") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "2330",
                "company": "台積電",
                "sector_logic": "GENERAL",
                "peer_group": "SEMICONDUCTOR_FOUNDRY",
                "financial_subtype": "",
                "period_end": period_end,
                "source_hash": "f" * 64,
            }
        ]
    )


def _sessions() -> tuple[date, ...]:
    return tuple(pd.bdate_range("2025-01-01", "2026-12-31").date)


def _lags() -> dict[str, int]:
    return {"q1": 60, "q2": 60, "q3": 60, "q4": 90}


def test_checkpoint_restore_and_offline_archive_load_never_calls_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("experiments.fundamental_quality_valuation.mops.urlopen", forbidden)
    cache = tmp_path / "mops"
    checkpoint = restore_checkpoint(CHECKPOINT, cache)
    filings, decisions = load_offline_mops_archive(cache, ["2330"])
    assert checkpoint["resume"]["next_network_requests_required"] == 0
    assert filings
    assert decisions


def test_mops_exact_timestamp_has_priority_over_proxy() -> None:
    filing = _filing()
    selected, audit = select_mops_filings([filing])
    timeline, _ = build_financial_timeline(
        _normalized(),
        {("2330", 2025, 1): selected[0]},
        {("2330", 2025, 1): audit[0]},
        _sessions(),
        _lags(),
    )
    assert timeline.loc[0, "availability_method"] == MOPS_EXACT
    assert timeline.loc[0, "signal_date"] == date(2025, 5, 8)


def test_future_filing_does_not_change_earlier_pit_mapping() -> None:
    first = _filing()
    first_selected, first_audit = select_mops_filings([first])
    base, _ = build_financial_timeline(
        _normalized(),
        {("2330", 2025, 1): first_selected[0]},
        {("2330", 2025, 1): first_audit[0]},
        _sessions(),
        _lags(),
    )
    future = _filing(
        quarter=2,
        timestamp="2025-08-08T16:00:00+08:00",
        identifier="202502_2330_AI1.pdf",
    )
    all_selected, all_audit = select_mops_filings([first, future])
    expanded_input = pd.concat([_normalized(), _normalized("2025-06-30")], ignore_index=True)
    expanded, _ = build_financial_timeline(
        expanded_input,
        {(item.symbol, item.fiscal_year, item.fiscal_quarter): item for item in all_selected},
        {(item.symbol, item.fiscal_year, item.fiscal_quarter): item for item in all_audit},
        _sessions(),
        _lags(),
    )
    assert expanded.iloc[0]["source_hash"] == base.iloc[0]["source_hash"]
    assert expanded.iloc[0]["signal_date"] == base.iloc[0]["signal_date"]


def test_later_correction_is_not_retroactive() -> None:
    original = _filing(timestamp="2025-05-08T15:30:00+08:00", identifier="original.pdf")
    correction = _filing(
        timestamp="2025-05-20T18:00:00+08:00",
        identifier="correction.pdf",
        correction="更正",
    )
    selected, audit = select_mops_filings([original, correction])
    timeline, _ = build_financial_timeline(
        _normalized(),
        {("2330", 2025, 1): selected[0]},
        {("2330", 2025, 1): audit[0]},
        _sessions(),
        _lags(),
    )
    assert selected[0].source_identifier == "correction.pdf"
    assert timeline.loc[0, "signal_date"] == date(2025, 5, 20)
    assert timeline.loc[0, "signal_date"] > date.fromisoformat(original.announcement_date)


def test_first_trade_date_is_strictly_next_twse_session() -> None:
    filing = _filing(timestamp="2025-05-09T08:00:00+08:00")
    selected, audit = select_mops_filings([filing])
    timeline, _ = build_financial_timeline(
        _normalized(),
        {("2330", 2025, 1): selected[0]},
        {("2330", 2025, 1): audit[0]},
        _sessions(),
        _lags(),
    )
    assert timeline.loc[0, "first_trade_date"] == date(2025, 5, 12)
    assert timeline.loc[0, "first_trade_date"] > date(2025, 5, 9)


def test_financial_stock_is_not_in_predictive_eligible_signal_universe() -> None:
    row = _normalized()
    row.loc[:, "symbol"] = "2880"
    row.loc[:, "sector_logic"] = "FINANCIAL"
    timeline, _ = build_financial_timeline(row, {}, {}, _sessions(), _lags())
    universe = pd.DataFrame(
        [{"symbol": "2880", "company": "華南金", "sector_logic": "FINANCIAL", "peer_group": "BANK", "financial_subtype": "BANK_HOLDING"}]
    )
    signals = build_signal_timeline(timeline, universe, {}, _sessions(), {"as_of_date": "2026-09-03"})
    assert signals.empty


def test_fixed_cohort_loading_is_exactly_50_and_hash_frozen() -> None:
    path = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
    first = _load_universe(path)
    second = _load_universe(path)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == first["symbol"].nunique() == 50
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_FIXED_COHORT_SHA256


@pytest.mark.parametrize("delta", [-1, 1])
def test_fixed_cohort_wrong_count_fails_closed(tmp_path: Path, delta: int) -> None:
    source = pd.read_csv(
        ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv",
        dtype=str,
        encoding="utf-8-sig",
    )
    changed = source.iloc[:-1].copy() if delta < 0 else pd.concat(
        [source, source.iloc[[0]].assign(symbol="9999")], ignore_index=True
    )
    path = tmp_path / "universe.csv"
    changed.to_csv(path, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="exactly 50 rows"):
        _load_universe(path)


def test_fixed_cohort_duplicate_symbol_fails_closed(tmp_path: Path) -> None:
    source = pd.read_csv(
        ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv",
        dtype=str,
        encoding="utf-8-sig",
    )
    source.loc[source.index[-1], "symbol"] = source.loc[source.index[0], "symbol"]
    path = tmp_path / "universe.csv"
    source.to_csv(path, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="duplicate symbols"):
        _load_universe(path)


def test_fixed_cohort_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    source = pd.read_csv(
        ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv",
        dtype=str,
        encoding="utf-8-sig",
    )
    source.loc[source.index[0], "company"] = "tampered"
    path = tmp_path / "universe.csv"
    source.to_csv(path, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="Frozen universe hash mismatch"):
        _load_universe(path)


def test_normalized_financial_symbol_set_mismatch_fails_closed() -> None:
    universe = _load_universe(
        ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
    )
    normalized = pd.DataFrame({"symbol": universe["symbol"].iloc[:-1]})
    with pytest.raises(RuntimeError, match="Normalized financial symbol set mismatch"):
        _validate_normalized_symbol_set(normalized, universe)


def test_checkpoint_archive_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "checkpoint"
    shutil.copytree(CHECKPOINT, copied)
    archive = copied / "mops_cache_and_metadata.tar.gz"
    archive.write_bytes(archive.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_checkpoint(copied)


def test_exact_duplicate_row_is_separate_from_other_candidate_semantics() -> None:
    filing = _filing()
    selected, audit = select_mops_filings([filing, filing])
    assert selected == (filing,)
    assert audit[0].candidate_count == 2
    assert audit[0].exact_duplicate_count == 1
    assert audit[0].multiple_vintage_count == 0
    assert audit[0].multiple_document_kind_count == 0
    assert audit[0].correction_candidate_count == 0


def test_consolidated_and_individual_are_not_exact_duplicates() -> None:
    consolidated = _filing(identifier="consolidated.pdf")
    individual = _filing(kind="INDIVIDUAL", identifier="individual.pdf")
    selected, audit = select_mops_filings([individual, consolidated])
    assert selected == (consolidated,)
    assert audit[0].exact_duplicate_count == 0
    assert audit[0].multiple_vintage_count == 0
    assert audit[0].multiple_document_kind_count == 1
    assert audit[0].duplicate_candidate_count == 1


def test_correction_vintage_is_not_an_exact_duplicate_and_selection_is_unchanged() -> None:
    original = _filing(timestamp="2025-05-08T15:30:00+08:00", identifier="original.pdf")
    correction = _filing(
        timestamp="2025-05-20T18:00:00+08:00",
        identifier="correction.pdf",
        correction="更正",
    )
    selected, audit = select_mops_filings([original, correction])
    assert selected == (correction,)
    assert audit[0].exact_duplicate_count == 0
    assert audit[0].multiple_vintage_count == 1
    assert audit[0].multiple_document_kind_count == 0
    assert audit[0].correction_candidate_count == 1


def test_conflicting_filings_are_audited_and_ambiguous_tie_fails_closed() -> None:
    conflict_a = _filing(identifier="a.pdf")
    conflict_b = _filing(identifier="b.pdf")
    selected, audit = select_mops_filings([conflict_a, conflict_b])
    assert selected == ()
    assert audit[0].status == "CONFLICT_FAIL_CLOSED"
    assert audit[0].conflict_candidate_count == 2


def test_frozen_archive_selection_fingerprint_is_unchanged(tmp_path: Path) -> None:
    cache = tmp_path / "mops"
    restore_checkpoint(CHECKPOINT, cache)
    universe = _load_universe(
        ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
    )
    filings, _ = load_offline_mops_archive(cache, universe["symbol"])
    assert _selected_filing_hash(filings) == EXPECTED_SELECTED_FILING_HASH


def test_unmatched_observation_keeps_explicit_proxy() -> None:
    timeline, diagnostics = build_financial_timeline(_normalized(), {}, {}, _sessions(), _lags())
    assert timeline.loc[0, "availability_method"] == AVAILABLE_DATE_PROXY
    assert diagnostics.loc[0, "mapping_status"] == "UNMATCHED_PROXY"


def test_frozen_quality_and_valuation_thresholds_are_unchanged() -> None:
    config = json.loads(
        (ROOT / "config/fundamental_quality_valuation_v0_1.json").read_text(encoding="utf-8")
    )
    actual = canonical_hash(
        {"quality_rules": config["quality_rules"], "valuation_rules": config["valuation_rules"]}
    )
    assert actual == EXPECTED_FROZEN_RULES_HASH


def test_generated_compressed_financial_timeline_is_parseable_and_finite() -> None:
    path = ROOT / "artifacts/0050_fundamental_v0_1/0050_pit_financial_timeline_v0.1.csv.gz"
    frame = pd.read_csv(path, low_memory=False)
    assert len(frame) == 2067
    numeric = frame.select_dtypes(include=[np.number])
    assert not np.isinf(numeric.to_numpy(dtype=float, na_value=math.nan)).any()


def test_generated_stage_a_hardening_artifacts_preserve_frozen_baseline() -> None:
    artifact_dir = ROOT / "artifacts/0050_fundamental_v0_1"
    summary = json.loads(
        (artifact_dir / "0050_stage_a_data_quality_summary_v0.1.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["financial_observations"] == 2067
    assert summary["mops_exact"] == 2053
    assert summary["proxy"] == 14
    assert summary["unmatched"] == 14
    assert summary["conflict_observations"] == 0
    assert summary["fixed_cohort"] == 50
    assert summary["eligible_non_financial"] == 38
    assert summary["excluded_financial"] == 12
    assert summary["pit_signal_observations"] == 1563
    assert summary["predictive_returns_computed"] is False
    assert summary["mops_network_requests"] == 0
    assert summary["frozen_rules_hash"] == EXPECTED_FROZEN_RULES_HASH
    assert summary["selected_filing_hash"] == EXPECTED_SELECTED_FILING_HASH
    assert summary["filing_selection_results_unchanged"] is True
    assert summary["exact_duplicate_rows"] == 0
    assert summary["multiple_vintage_cases"] == 341
    assert summary["multiple_document_kind_cases"] == 341
    assert summary["correction_candidate_cases"] == 0
    diagnostics = pd.read_csv(
        artifact_dir / "0050_mops_mapping_diagnostics_v0.1.csv",
        dtype={"symbol": str},
        encoding="utf-8-sig",
    )
    assert int(diagnostics["exact_duplicate_count"].sum()) == 0
    assert int((diagnostics["multiple_vintage_count"] > 0).sum()) == 341
    assert int((diagnostics["multiple_document_kind_count"] > 0).sum()) == 341
    assert int((diagnostics["correction_candidate_count"] > 0).sum()) == 0
    assert set(diagnostics["duplicate_candidate_count_semantic"]) == {
        "DEPRECATED_LEGACY_CANDIDATES_BEYOND_FIRST"
    }
