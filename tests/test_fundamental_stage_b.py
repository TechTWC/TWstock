from __future__ import annotations

from datetime import date, timedelta
import json
import math
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from experiments.fundamental_quality_valuation.stage_b import (
    CANONICAL_STATES,
    EXPECTED_FROZEN_RULES_HASH,
    EXPECTED_SIGNAL_SHA256,
    EXPECTED_STAGE_A_MANIFEST_IDENTITY,
    EXPECTED_UNIVERSE_SHA256,
    MIN_SUPPORT_ISSUERS,
    MIN_SUPPORT_OBSERVATIONS,
    PRIMARY_HORIZONS,
    build_predictive_events,
    overlap_diagnostics,
    summary_row,
    summarize_combinations,
    summarize_dimension,
    summarize_outliers,
    validate_frozen_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/0050_fundamental_v0_1"
UNIVERSE = ROOT / "data/research/0050_fundamental_v0_1/universe_2026-09-03.csv"
SIGNALS = ARTIFACTS / "0050_pit_signal_timeline_v0.1.csv"
CONFIG = ROOT / "config/fundamental_quality_valuation_v0_1.json"
MANIFEST = ARTIFACTS / "artifact_manifest.json"


def _market(days: int = 900, start: date = date(2019, 1, 2), slope: float = 0.001) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=days).date
    values = 100.0 * (1.0 + slope) ** np.arange(days)
    return pd.DataFrame({"date": dates, "adj_close": values, "close": values})


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "1111", "company": "A", "sector_logic": "GENERAL", "peer_group": "A", "financial_subtype": ""},
            {"symbol": "2880", "company": "F", "sector_logic": "FINANCIAL", "peer_group": "BANK", "financial_subtype": "BANK"},
        ]
    )


def _signal(entry: str = "2019-01-02", symbol: str = "1111", state: str = "IMPROVING") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "period_end": "2018-09-30",
                "announcement_timestamp": "2019-01-01T12:00:00+08:00",
                "signal_date": "2019-01-01",
                "first_trade_date": entry,
                "quality": "GOOD",
                "fundamental_state": state,
                "state_detail": "TURNING_UP",
                "valuation": "N/M",
                "data_quality": "FULL",
                "reason_codes": "TEST",
                "availability_method": "MOPS_EXACT",
                "source_hash": "a" * 64,
                "predictive_eligible": True,
            }
        ]
    )


def test_frozen_identities_match_exact_stage_a_inputs() -> None:
    universe, signals, _, _, identity = validate_frozen_inputs(UNIVERSE, SIGNALS, CONFIG, MANIFEST)
    assert len(universe) == 50
    assert len(signals) == 1563
    assert identity.universe_sha256 == EXPECTED_UNIVERSE_SHA256
    assert identity.signal_sha256 == EXPECTED_SIGNAL_SHA256
    assert identity.frozen_rules_hash == EXPECTED_FROZEN_RULES_HASH
    assert identity.stage_a_manifest_identity == EXPECTED_STAGE_A_MANIFEST_IDENTITY


@pytest.mark.parametrize("target", ["universe", "signal", "config", "manifest"])
def test_each_frozen_identity_mismatch_fails_closed(tmp_path: Path, target: str) -> None:
    paths = {
        "universe": tmp_path / "universe.csv",
        "signal": tmp_path / "signals.csv",
        "config": tmp_path / "config.json",
        "manifest": tmp_path / "manifest.json",
    }
    shutil.copy2(UNIVERSE, paths["universe"])
    shutil.copy2(SIGNALS, paths["signal"])
    shutil.copy2(CONFIG, paths["config"])
    shutil.copy2(MANIFEST, paths["manifest"])
    if target in {"universe", "signal"}:
        paths[target].write_bytes(paths[target].read_bytes() + b"\n")
    elif target == "config":
        payload = json.loads(paths[target].read_text())
        payload["quality_rules"]["general"]["median_roe_5y_min"] = 999
        paths[target].write_text(json.dumps(payload))
    else:
        payload = json.loads(paths[target].read_text())
        payload["stage_a_hardening"]["mops_exact"] = 0
        paths[target].write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="mismatch"):
        validate_frozen_inputs(paths["universe"], paths["signal"], paths["config"], paths["manifest"])


def test_first_trade_date_is_entry_and_returns_use_exact_common_dates() -> None:
    stock = _market(slope=0.002)
    benchmark = _market(slope=0.001)
    events = build_predictive_events(
        _signal(), _universe(), {"1111": stock}, benchmark, as_of=date(2023, 1, 1)
    )
    row = events.iloc[0]
    assert row["entry_date"] == "2019-01-02"
    assert row["entry_contract"] == "FROZEN_STAGE_A_FIRST_TRADE_DATE"
    assert row["valuation_frozen"] == "N/M"
    assert row["valuation_bucket"] == "NOT_MEANINGFUL"
    expected_stock = (1.002**60) - 1
    expected_benchmark = (1.001**60) - 1
    assert row["return_60d"] == pytest.approx(expected_stock)
    assert row["benchmark_return_60d"] == pytest.approx(expected_benchmark)
    assert row["excess_return_60d"] == pytest.approx(expected_stock - expected_benchmark)


def test_future_price_changes_never_change_frozen_signal() -> None:
    base = _market(slope=0.001)
    changed = base.copy()
    changed.loc[changed.index >= 20, "adj_close"] *= 4
    first = build_predictive_events(_signal(), _universe(), {"1111": base}, base, as_of=date(2023, 1, 1))
    second = build_predictive_events(_signal(), _universe(), {"1111": changed}, base, as_of=date(2023, 1, 1))
    for column in ("quality", "fundamental_state", "state_detail", "valuation_frozen", "entry_date"):
        assert first.loc[0, column] == second.loc[0, column]
    assert first.loc[0, "return_60d"] != second.loc[0, "return_60d"]


def test_missing_entry_and_incomplete_horizon_fail_closed() -> None:
    market = _market(days=100)
    missing = build_predictive_events(
        _signal(entry="2019-01-03"),
        _universe(),
        {"1111": market[market["date"] != date(2019, 1, 3)]},
        market,
        as_of=date(2019, 12, 31),
    )
    assert missing.loc[0, "exclusion_reason"] == "ENTRY_ADJUSTED_CLOSE_MISSING"
    assert pd.isna(missing.loc[0, "return_60d"])
    short = build_predictive_events(
        _signal(), _universe(), {"1111": market}, market, as_of=date(2019, 12, 31)
    )
    assert math.isfinite(short.loc[0, "return_60d"])
    assert pd.isna(short.loc[0, "return_120d"])
    assert pd.isna(short.loc[0, "return_252d"])
    assert pd.isna(short.loc[0, "return_504d"])


def test_financial_signal_is_never_accepted() -> None:
    market = _market()
    with pytest.raises(RuntimeError, match="financial"):
        build_predictive_events(
            _signal(symbol="2880"), _universe(), {"2880": market}, market, as_of=date(2023, 1, 1)
        )


def _summary_events(n: int = 40) -> pd.DataFrame:
    rows = []
    for index in range(n):
        row = {
            "symbol": str(1000 + index % 8),
            "entry_date": (date(2019, 1, 2) + timedelta(days=index * 20)).isoformat(),
            "fundamental_state": CANONICAL_STATES[index % 3],
            "state_detail": "TURNING_UP",
            "quality": "GOOD",
            "valuation_bucket": "LOW",
            "peer_group": "A" if index % 2 else "B",
        }
        for horizon in PRIMARY_HORIZONS:
            row[f"return_{horizon}d"] = 0.01 * (index % 7)
            row[f"excess_return_{horizon}d"] = 0.005 * ((index % 5) - 1)
            row[f"exit_date_{horizon}d"] = (date.fromisoformat(row["entry_date"]) + timedelta(days=horizon)).isoformat()
        rows.append(row)
    return pd.DataFrame(rows)


def test_unknown_is_not_in_directional_main_comparison_and_support_is_fixed() -> None:
    events = _summary_events()
    events.loc[0, "fundamental_state"] = "UNKNOWN"
    summary = summarize_dimension(events, "fundamental_state", CANONICAL_STATES, "FUNDAMENTAL_STATE")
    assert set(summary["bucket"]) == set(CANONICAL_STATES)
    assert "UNKNOWN" not in set(summary["bucket"])
    assert set(summary["support_min_observations"]) == {MIN_SUPPORT_OBSERVATIONS}
    assert set(summary["support_min_issuers"]) == {MIN_SUPPORT_ISSUERS}


def test_clustered_uncertainty_is_reported() -> None:
    row = summary_row(_summary_events(), dimension="TEST", bucket="ALL", horizon=60)
    assert row["issuer_cluster_mean_return_se"] is not None
    assert row["time_cluster_mean_return_se"] is not None
    assert row["issuer_cluster_median_return_ci95_low"] is not None
    assert row["time_cluster_median_return_ci95_high"] is not None


def test_combination_support_gate_is_deterministic_and_no_score_exists() -> None:
    events = _summary_events()
    first = summarize_combinations(events)
    second = summarize_combinations(events)
    pd.testing.assert_frame_equal(first, second)
    assert not any("score" in column.lower() for column in first.columns)
    assert set(first["support_status"]) <= {"SUPPORTED", "INSUFFICIENT_SUPPORT"}


def test_overlap_diagnostic_counts_same_issuer_and_calendar_overlap() -> None:
    result = overlap_diagnostics(_summary_events(12))
    assert set(result["horizon"]) == {"60d", "120d", "252d", "504d"}
    assert (result["overlapping_observations_count"] > 0).all()
    assert (result["same_issuer_overlap_pair_count"] > 0).any()
    assert (result["same_calendar_period_cross_issuer_overlap_pair_count"] > 0).all()


def test_ex_tsmc_and_top_return_removal_are_explicit() -> None:
    events = _summary_events()
    events.loc[0, "symbol"] = "2330"
    result = summarize_outliers(events)
    scopes = set(result.loc[result["analysis_type"] == "RETURN_SENSITIVITY", "scope"])
    assert scopes == {"FULL_SAMPLE", "EX_TSMC", "TOP_1_RETURN_REMOVED", "TOP_5_RETURNS_REMOVED"}
    all_rows = result[
        (result["analysis_type"] == "RETURN_SENSITIVITY") & (result["bucket"] == "ALL")
    ]
    assert (all_rows["median_return_lift_vs_all"].abs() < 1e-12).all()
    assert (all_rows["median_excess_return_lift_vs_all"].abs() < 1e-12).all()
    assert (all_rows["outperform_rate_lift_vs_all"].abs() < 1e-12).all()
    assert {"ISSUER_CONCENTRATION", "SECTOR_CONCENTRATION"}.issubset(set(result["analysis_type"]))


def test_stage_b_source_has_no_mops_network_or_tuning_or_composite_score() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "experiments/fundamental_quality_valuation/stage_b.py",
            "scripts/run_0050_fundamental_stage_b.py",
        )
    ).lower()
    assert "mops.twse" not in sources
    assert "gridsearch" not in sources
    assert "threshold optimization" not in sources
    assert "composite_score" not in sources
    assert "weighted_score" not in sources


def test_generated_stage_b_artifacts_are_finite_and_manifest_hashed() -> None:
    required = {
        "0050_predictive_events_v0.1.csv",
        "0050_state_predictive_summary_v0.1.csv",
        "0050_state_detail_predictive_summary_v0.1.csv",
        "0050_quality_predictive_summary_v0.1.csv",
        "0050_valuation_predictive_summary_v0.1.csv",
        "0050_predictive_combinations_v0.1.csv",
        "0050_too_late_return_diagnostic_v0.1.csv",
        "0050_regime_robustness_v0.1.csv",
        "0050_outlier_sensitivity_v0.1.csv",
        "0050_overlap_diagnostics_v0.1.csv",
        "0050_predictive_evidence_v0.1.json",
        "0050_fundamental_quality_valuation_predictive_validation_v0.1.pdf",
    }
    assert required.issubset({path.name for path in ARTIFACTS.iterdir()})
    payload = json.loads((ARTIFACTS / "0050_predictive_evidence_v0.1.json").read_text())
    assert payload["mops_network_requests"] == 0
    assert payload["stage_b_status"] == "PASS"
    assert payload["predictive_evidence_grade"] in {"NONE", "WEAK", "MODERATE", "STRONG"}
    for csv_path in (ARTIFACTS / name for name in required if name.endswith(".csv")):
        frame = pd.read_csv(csv_path, low_memory=False)
        numeric = frame.select_dtypes(include=[np.number])
        assert not np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any(), csv_path.name
    manifest = json.loads(MANIFEST.read_text())
    indexed = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    for name in required:
        assert name in indexed
        assert __import__("hashlib").sha256((ARTIFACTS / name).read_bytes()).hexdigest() == indexed[name]
