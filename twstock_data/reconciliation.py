from __future__ import annotations
from .models import MarketDataRecord, ReconciliationIssue, ReconciliationResult, SourceState

def reconcile_market_data(primary: tuple[MarketDataRecord, ...], secondary: tuple[MarketDataRecord, ...] = (), primary_error: str | None = None) -> ReconciliationResult:
    if not primary:
        if secondary:
            return ReconciliationResult(SourceState.SECONDARY_ONLY, secondary)
        return ReconciliationResult(SourceState.SOURCE_UNAVAILABLE, (), cross_check_unavailable=True)
    if not secondary:
        return ReconciliationResult(SourceState.PRIMARY_VERIFIED, primary, cross_check_unavailable=True)
    by_primary = {record.trade_date: record for record in primary}
    by_secondary = {record.trade_date: record for record in secondary}
    issues: list[ReconciliationIssue] = []
    for trade_date in sorted(set(by_primary) - set(by_secondary)):
        issues.append(ReconciliationIssue(trade_date, "trade_date_only_in_twse", trade_date, None))
    for trade_date in sorted(set(by_secondary) - set(by_primary)):
        issues.append(ReconciliationIssue(trade_date, "trade_date_only_in_finmind", None, trade_date))
    for trade_date in sorted(set(by_primary) & set(by_secondary)):
        p = by_primary[trade_date]
        s = by_secondary[trade_date]
        for field in ("traded_share_volume", "official_traded_value_twd", "close_price"):
            pv, sv = getattr(p, field), getattr(s, field)
            if pv != sv:
                issues.append(ReconciliationIssue(trade_date, field, pv, sv))
    state = SourceState.SOURCE_MISMATCH if issues else SourceState.PRIMARY_VERIFIED
    return ReconciliationResult(state, primary, tuple(issues))
