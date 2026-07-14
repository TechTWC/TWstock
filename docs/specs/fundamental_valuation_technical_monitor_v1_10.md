# Fundamental–Valuation–Technical Monitor v1.10

## Phase A1 executable specification profile

- Document version: `v1.10`
- Strategy: `Fundamental_Valuation_Trend_Breakout_v1`
- Release: `Phase A1 Logic Sandbox v0.1`
- Status: experimental implementation baseline
- Market: Taiwan-listed common stocks (`TW`) only
- Purpose: rapidly test deterministic Phase A1 screening rules against a canonical, already-normalized CSV snapshot

This repository file records the v1.10 rules that are executable in the logic sandbox. The broader v1.10 data pipeline, historical PE, technical monitor, holding monitor, execution validation, and live adapters remain outside this release.

## 1. Deterministic flow

```text
Canonical snapshot CSV
→ input validation
→ Gate 1 liquidity
→ Gate 2 financial survival
→ Gate 3A absolute PE valuation
→ Gate 3C operating-income direction
→ primary action resolution
→ CSV, JSON, and static HTML output
```

All thresholds are read from `config/settings.yaml`. Rule functions must not embed threshold values.

## 2. Canonical input

One row represents one stock and contains at least:

```text
symbol
name
market
security_type
price_date
required_data_valid
financial_data_usable
average_turnover_20d
market_cap
ttm_net_income
ttm_operating_income
ttm_operating_cash_flow
latest_equity
latest_total_assets
latest_total_liabilities
latest_current_assets
latest_current_liabilities
latest_q_operating_income
previous_q_operating_income
prior_year_q_operating_income
```

The input is treated as normalized and prevalidated. This release does not fetch or normalize TWSE/MOPS data.

## 3. Gate 1 — liquidity and eligibility

For supported `TW` common stocks:

```text
average_turnover_20d >= TWD 20,000,000
→ ELIGIBLE

otherwise
→ ILLIQUID
```

Unsupported markets or security types are `NOT_SUPPORTED`. Any non-eligible result resolves to `NOT_ELIGIBLE` after data-quality precedence.

## 4. Gate 2 — financial survival

### 4.1 Severe failure

Any condition produces `FUNDAMENTAL_FAIL`:

```text
latest_equity <= 0

ttm_operating_income <= 0

latest_q_operating_income < 0
AND previous_q_operating_income < 0
```

Specific conditions are retained in `risk_flags`.

### 4.2 Warnings

Add `NONPOSITIVE_TTM_OPERATING_CASH_FLOW` when:

```text
ttm_operating_cash_flow <= 0
```

Add `HIGH_DEBT_RATIO` when:

```text
latest_total_liabilities / latest_total_assets > 0.75
```

Add `LOW_CURRENT_RATIO_WITH_NONPOSITIVE_OCF` only when:

```text
current_ratio < 1
AND ttm_operating_cash_flow <= 0
```

When:

```text
current_ratio < 1
AND ttm_operating_cash_flow > 0
```

do not increment the warning count. Add `LOW_CURRENT_RATIO_CONTEXT` only to `informational_tags`.

If current liabilities are zero, current ratio is positive infinity.

```text
warning count 0 or 1 → FUNDAMENTAL_PASS
warning count 2 or more → FUNDAMENTAL_WATCH
```

Warnings and informational tags must never be merged.

## 5. Gate 3A — absolute PE

```text
PE_TTM = market_cap / ttm_net_income
```

Only positive, usable TTM net income and positive market cap produce PE.

```text
0 < PE <= 10       → VERY_LOW_VALUATION
10 < PE <= 15      → ABSOLUTE_CHEAP
15 < PE <= 30      → FAIR_VALUATION
PE > 30            → VALUATION_NOT_CHEAP
invalid/nonpositive basis → VALUATION_UNKNOWN
```

Boundary values 10, 15, and 30 are inclusive in the lower valuation category shown above.

## 6. Gate 3C — operating-income direction

When latest quarter and prior-year quarter are positive:

```text
operating_income_yoy = latest / prior_year - 1
YoY >= 0 → EARNINGS_OK
YoY < 0  → EARNINGS_WEAK
```

Turnaround cases:

```text
prior-year <= 0 and latest > 0 → TURNAROUND_POSITIVE
prior-year > 0 and latest <= 0 → TURNAROUND_NEGATIVE
both <= 0                      → BOTH_NON_POSITIVE
```

`operating_income_yoy` is null for all turnaround/nonpositive cases. The system must not fabricate a growth percentage.

## 7. Primary action precedence

Resolve exactly one action in this order:

1. Invalid required data or unusable financial data → `DATA_REVIEW`
2. Eligibility not `ELIGIBLE` → `NOT_ELIGIBLE`
3. `FUNDAMENTAL_FAIL` → `EXCLUDE`
4. `FUNDAMENTAL_WATCH` → `FUNDAMENTAL_REVIEW`
5. `VALUATION_UNKNOWN` → `DATA_REVIEW`
6. PE above 30 / `VALUATION_NOT_CHEAP` → `VALUATION_WAIT`
7. `EARNINGS_WEAK`, `TURNAROUND_NEGATIVE`, or `BOTH_NON_POSITIVE` → `VALUE_TRAP_REVIEW`
8. PE at or below 15 with `EARNINGS_OK` or `TURNAROUND_POSITIVE` → `VALUE_CANDIDATE`
9. Remaining PE from above 15 through 30 → `VALUATION_WATCH`

A `VALUE_CANDIDATE` therefore requires:

```text
required_data_valid
AND financial_data_usable
AND ELIGIBLE
AND FUNDAMENTAL_PASS
AND 0 < PE <= 15
AND (EARNINGS_OK OR TURNAROUND_POSITIVE)
```

Historical PE actions are excluded from this sandbox.

## 8. Result separation

Every result separately retains:

```text
primary_action
trigger_reasons
warning_reasons
risk_flags
data_quality_flags
informational_tags
```

CSV serializes list fields with `|`; JSON retains arrays; HTML displays separate columns.

## 9. Explicit exclusions

This release does not implement:

```text
TWSE live data adapter
MOPS live data adapter
historical PE or PE river bands
technical analysis or breakout signals
portfolio monitoring
paper execution
SQLite
GitHub Actions
scheduled execution
API or authentication
Cloudflare or Astro integration
Telegram/email notifications
TWO, US, ADR, automated trading
```

## 10. Status statement

This sandbox is not production-ready, not a validated investment strategy, and not evidence that any screening rule generates excess returns. It exists to make rule iteration fast and auditable.
