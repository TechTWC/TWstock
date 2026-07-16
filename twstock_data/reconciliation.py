from __future__ import annotations
from .models import MarketDataRecord, ReconciliationIssue, ReconciliationResult, SourceState

def reconcile_market_data(primary: tuple[MarketDataRecord,...], secondary: tuple[MarketDataRecord,...] = (), primary_error: str | None = None) -> ReconciliationResult:
    if not primary:
        if secondary: return ReconciliationResult(SourceState.SECONDARY_ONLY, secondary)
        return ReconciliationResult(SourceState.SOURCE_UNAVAILABLE, (), cross_check_unavailable=True)
    if not secondary:
        return ReconciliationResult(SourceState.PRIMARY_VERIFIED, primary, cross_check_unavailable=True)
    by_secondary = {r.trade_date: r for r in secondary}; issues=[]
    for p in primary:
        s = by_secondary.get(p.trade_date)
        if s is None:
            issues.append(ReconciliationIssue(p.trade_date, "trade_date", p.trade_date, None)); continue
        for field in ("traded_share_volume","official_traded_value_twd","close_price"):
            pv, sv = getattr(p, field), getattr(s, field)
            if pv != sv: issues.append(ReconciliationIssue(p.trade_date, field, pv, sv))
    state = SourceState.SOURCE_MISMATCH if issues else SourceState.PRIMARY_VERIFIED
    return ReconciliationResult(state, primary, tuple(issues))
