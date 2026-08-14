from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from twstock_experiments.pe_river import (
    ExperimentInputError,
    build_analysis,
    load_eps_history,
    load_multiples,
    load_price,
    load_scenarios,
    run,
    ttm_eps_as_of,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/experiments/2330_pe_river"


def test_point_in_time_ttm_changes_only_after_q2_becomes_available() -> None:
    history = load_eps_history(DATA / "eps_history.csv")
    pre, pre_periods = ttm_eps_as_of(history, date(2026, 7, 16))
    post, post_periods = ttm_eps_as_of(history, date(2026, 7, 17))

    assert pre == Decimal("74.38")
    assert pre_periods == ("2025Q2", "2025Q3", "2025Q4", "2026Q1")
    assert post == Decimal("86.27")
    assert post_periods == ("2025Q3", "2025Q4", "2026Q1", "2026Q2")


def test_analysis_reproduces_bridge_math() -> None:
    analysis = build_analysis(
        price=load_price(DATA / "reference_price.csv"),
        observations=load_eps_history(DATA / "eps_history.csv"),
        multiples=load_multiples(DATA / "river_multiples.csv"),
        scenarios=load_scenarios(DATA / "forward_scenarios.csv"),
        pre_as_of=date(2026, 7, 16),
        post_as_of=date(2026, 7, 17),
    )
    pre = analysis["pre_release"]
    post = analysis["post_release"]
    assert pre["pe_ttm"].quantize(Decimal("0.01")) == Decimal("33.21")
    assert post["pe_ttm"].quantize(Decimal("0.01")) == Decimal("28.63")
    assert pre["band_prices"]["28"] == Decimal("2082.64")
    assert post["band_prices"]["28"] == Decimal("2415.56")


def test_forward_scenarios_are_explicitly_manual() -> None:
    scenarios = load_scenarios(DATA / "forward_scenarios.csv")
    assert all("MANUAL_ASSUMPTION" in item.assumption_status for item in scenarios)


def test_runner_writes_human_and_machine_readable_outputs(tmp_path: Path) -> None:
    run(
        eps_path=DATA / "eps_history.csv",
        price_path=DATA / "reference_price.csv",
        multiples_path=DATA / "river_multiples.csv",
        scenarios_path=DATA / "forward_scenarios.csv",
        output_dir=tmp_path,
        pre_as_of=date(2026, 7, 16),
        post_as_of=date(2026, 7, 17),
    )
    assert (tmp_path / "analysis.json").is_file()
    assert (tmp_path / "valuation_ladder.csv").is_file()
    report = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "EXPLORATORY_NOT_VALIDATED" in report
    assert "Forward 情境" in report
    assert "Point-in-Time" in report


def test_rejects_unsorted_or_duplicate_multiples(tmp_path: Path) -> None:
    bad = tmp_path / "multiples.csv"
    bad.write_text("pe_multiple\n28\n24\n", encoding="utf-8")
    with pytest.raises(ExperimentInputError, match="strictly ascending"):
        load_multiples(bad)
