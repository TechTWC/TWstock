from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from twstock_experiments.decision_checklist import (
    DecisionInputs,
    MarketSnapshot,
    evaluate_decision,
    market_snapshot_from_analysis,
    valuation_multiplier,
    write_decision_page,
    write_site_index,
)


def _market(*, percentile: str = "75", forward: bool = False) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="2330.TW",
        price_twd=Decimal("2330"),
        pe_ttm=Decimal("27.01"),
        trailing_pe_percentile=Decimal(percentile),
        price_vs_ma200_pct=Decimal("27"),
        latest_three_month_revenue_yoy_pct=Decimal("38"),
        latest_operating_margin_pct=Decimal("60"),
        forward_pe_status="AVAILABLE" if forward else "HISTORICAL_FORWARD_PE_UNAVAILABLE_NO_VERIFIED_VINTAGES",
        forward_pe_available=forward,
    )


def _inputs(**overrides: object) -> DecisionInputs:
    values = {
        "investment_horizon_years": 5,
        "has_emergency_fund": True,
        "uses_borrowed_money": False,
        "needs_cash_within_three_years": False,
        "drawdown_tolerance_pct": 30,
        "current_position_weight_pct": Decimal("0"),
        "target_position_weight_pct": Decimal("10"),
    }
    values.update(overrides)
    return DecisionInputs(**values)


def test_valuation_multiplier_uses_predeclared_bands() -> None:
    assert valuation_multiplier(Decimal("10")) == Decimal("1.50")
    assert valuation_multiplier(Decimal("40")) == Decimal("1.00")
    assert valuation_multiplier(Decimal("75")) == Decimal("0.75")
    assert valuation_multiplier(Decimal("85")) == Decimal("0.50")
    assert valuation_multiplier(Decimal("95")) == Decimal("0.25")


def test_current_like_market_continues_dca_but_only_small_tactical_add() -> None:
    result = evaluate_decision(_market(), _inputs())
    assert result.dca_action == "CONTINUE"
    assert result.dca_multiplier == Decimal("0.75")
    assert result.tactical_add_action == "SMALL"
    assert result.decision_confidence == "MEDIUM_LOW"
    assert any("Forward P/E" in warning for warning in result.warnings)


def test_hard_personal_finance_gate_pauses_all_new_money() -> None:
    result = evaluate_decision(
        _market(percentile="20", forward=True),
        _inputs(uses_borrowed_money=True),
    )
    assert result.dca_action == "PAUSE"
    assert result.dca_multiplier == Decimal("0")
    assert result.tactical_add_action == "NONE"
    assert result.decision_confidence == "LOW"


def test_strong_tactical_add_requires_low_valuation_and_forward_evidence() -> None:
    result = evaluate_decision(
        _market(percentile="20", forward=True),
        _inputs(current_position_weight_pct=Decimal("2"), target_position_weight_pct=Decimal("10")),
    )
    assert result.dca_action == "INCREASE"
    assert result.dca_multiplier == Decimal("1.50")
    assert result.tactical_add_action == "STRONG"
    assert result.decision_confidence == "MEDIUM_HIGH"


def test_target_weight_gate_prevents_concentration() -> None:
    result = evaluate_decision(
        _market(percentile="20", forward=True),
        _inputs(current_position_weight_pct=Decimal("12"), target_position_weight_pct=Decimal("10")),
    )
    assert result.dca_action == "PAUSE"
    assert result.tactical_add_action == "NONE"
    assert result.allocation_headroom_pct == Decimal("-2")


def test_page_generation_embeds_market_data_and_navigation(tmp_path: Path) -> None:
    analysis = {
        "symbol": "2330.TW",
        "quote": {"price_twd": 2330},
        "current_valuation": {
            "pe_ttm": 27.01,
            "historical_trailing_pe_percentile": 75.35,
        },
        "technical_context": {"price_vs_ma200_pct": 27.01},
        "fundamental_context": {
            "latest_3m_average_revenue_yoy_pct": 38.5,
            "latest_quarter": {"operating_margin_pct": 60.3},
        },
        "historical_forward_pe": {
            "status": "HISTORICAL_FORWARD_PE_UNAVAILABLE_NO_VERIFIED_VINTAGES"
        },
    }
    market = market_snapshot_from_analysis(analysis)
    assert market.symbol == "2330.TW"
    page = tmp_path / "decision_checklist.html"
    index = tmp_path / "index.html"
    write_decision_page(analysis, page)
    write_site_index(analysis, index)
    page_text = page.read_text(encoding="utf-8")
    index_text = index.read_text(encoding="utf-8")
    assert "定期定額與加碼進場檢核" in page_text
    assert "live_report.html" in page_text
    assert "decision_checklist.html" in index_text
    assert "TW-DECISION-CHECKLIST-0.1" in page_text
    assert json.loads(json.dumps({"ok": True})) == {"ok": True}
