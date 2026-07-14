# Fundamental–Valuation–Technical Monitor v1.10

This repository snapshot preserves the Phase A1 rules implemented by the **Phase A1 Logic Sandbox v0.1**. The sandbox implements only deterministic screening decisions from a canonical, already-normalized CSV snapshot.

## Implemented Phase A1 flow

Canonical snapshot CSV → input validation → Gate 1 liquidity → Gate 2 financial survival → Gate 3A absolute PE valuation → Gate 3C operating-income direction → primary action resolution → CSV and static HTML output.

## Gate 1: liquidity

For `market == TW`, a stock is `ELIGIBLE` when `average_turnover_20d` is greater than or equal to the configured TWD threshold. Otherwise it is `ILLIQUID`.

## Gate 2: financial survival

Severe failures produce `FUNDAMENTAL_FAIL` when equity is nonpositive, TTM operating income is nonpositive, or the latest and previous quarter operating income are both negative.

Warnings are tracked separately from severe failures. Nonpositive TTM operating cash flow, high debt ratio, and low current ratio with nonpositive OCF contribute warnings. A low current ratio with positive OCF contributes only `LOW_CURRENT_RATIO_CONTEXT` as an informational tag. Zero current liabilities make the current ratio positive infinity.

Zero or one warning produces `FUNDAMENTAL_PASS`; two or more warnings produce `FUNDAMENTAL_WATCH`.

## Gate 3A: absolute PE valuation

PE is `market_cap / ttm_net_income`. Nonpositive net income produces `VALUATION_UNKNOWN`. Configured PE thresholds classify `VERY_LOW_VALUATION`, `ABSOLUTE_CHEAP`, `FAIR_VALUATION`, and `VALUATION_NOT_CHEAP`.

## Gate 3C: operating-income direction

The sandbox compares latest quarter operating income with the prior-year quarter. It emits `EARNINGS_OK`, `EARNINGS_WEAK`, `TURNAROUND_POSITIVE`, `TURNAROUND_NEGATIVE`, or `BOTH_NON_POSITIVE`. It does not fabricate growth percentages for turnaround cases.

## Primary actions

Supported primary actions are `DATA_REVIEW`, `NOT_ELIGIBLE`, `EXCLUDE`, `FUNDAMENTAL_REVIEW`, `VALUATION_WAIT`, `VALUE_TRAP_REVIEW`, `VALUE_CANDIDATE`, and `VALUATION_WATCH`. Historical PE actions are excluded.
