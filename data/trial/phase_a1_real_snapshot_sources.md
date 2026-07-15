# Phase A1 first real-data trial source notes

This snapshot is a **classification plausibility and data-integration trial only**. It is not a backtest, validated strategy, production data pipeline, or investment recommendation. The trial universe is limited to the requested TWSE-listed common stocks: 2330, 2317, 2454, 2603, and 1101.

## Common as-of rule

- Common `price_date`: 2026-07-15.
- Intended market-data source: TWSE daily individual-security trading data for close price and daily traded value, with `average_turnover_20d` defined as the arithmetic average of daily traded value over the 20 completed TWSE trading sessions ending on `price_date`.
- Intended listing/source identity source: TWSE listed-company/security identity records.
- Intended financial-statement source: MOPS published issuer financial statements available no later than `price_date`.
- Execution result: official source data was **not fully reconciled into canonical numeric fields** during this manual trial. Every row is intentionally marked `required_data_valid=false` and `financial_data_usable=false` so the Phase A1 runner routes the row to `DATA_REVIEW` rather than producing a valuation or eligibility conclusion.

## Accounting method required before a row can become usable

All monetary fields must be raw TWD. `latest_q_operating_income`, `previous_q_operating_income`, and `prior_year_q_operating_income` must be standalone-quarter values. Where a source statement is cumulative, standalone quarters must be derived as follows:

- Q1 standalone = Q1 cumulative
- Q2 standalone = H1 cumulative - Q1 cumulative
- Q3 standalone = 9M cumulative - H1 cumulative
- Q4 standalone = FY cumulative - 9M cumulative

TTM net income, TTM operating income, and TTM operating cash flow must each be calculated from four non-overlapping standalone quarters. Overlapping cumulative year-to-date values must not be summed. `ttm_net_income` must use a compatible common-shareholder earnings basis, and `market_cap` must represent common-equity market capitalization as of `price_date` using a documented common-share count basis.

## Per-stock reconciliation status

### 2330 — 台灣積體電路製造股份有限公司

- Price date: 2026-07-15
- Market-data source: TWSE intended; not reconciled into canonical values.
- Financial-statement source: MOPS intended; not reconciled into canonical values.
- Financial publication date: unresolved.
- Latest financial quarter available as of price date: unresolved.
- Quarters used in each TTM calculation: unresolved; no TTM value is usable.
- Source statement basis: unresolved; standalone vs cumulative not confirmed.
- Standalone-quarter formulas used: none applied because source periods were not reconciled.
- Common-shareholder net-income basis: unresolved.
- Market-cap calculation: unresolved; close price and common-share count basis were not reconciled.
- Uncertainty/reconciliation issue: official market and financial source fields remain unresolved, so `required_data_valid=false` and `financial_data_usable=false`.

### 2317 — 鴻海精密工業股份有限公司

- Price date: 2026-07-15
- Market-data source: TWSE intended; not reconciled into canonical values.
- Financial-statement source: MOPS intended; not reconciled into canonical values.
- Financial publication date: unresolved.
- Latest financial quarter available as of price date: unresolved.
- Quarters used in each TTM calculation: unresolved; no TTM value is usable.
- Source statement basis: unresolved; standalone vs cumulative not confirmed.
- Standalone-quarter formulas used: none applied because source periods were not reconciled.
- Common-shareholder net-income basis: unresolved.
- Market-cap calculation: unresolved; close price and common-share count basis were not reconciled.
- Uncertainty/reconciliation issue: official market and financial source fields remain unresolved, so `required_data_valid=false` and `financial_data_usable=false`.

### 2454 — 聯發科技股份有限公司

- Price date: 2026-07-15
- Market-data source: TWSE intended; not reconciled into canonical values.
- Financial-statement source: MOPS intended; not reconciled into canonical values.
- Financial publication date: unresolved.
- Latest financial quarter available as of price date: unresolved.
- Quarters used in each TTM calculation: unresolved; no TTM value is usable.
- Source statement basis: unresolved; standalone vs cumulative not confirmed.
- Standalone-quarter formulas used: none applied because source periods were not reconciled.
- Common-shareholder net-income basis: unresolved.
- Market-cap calculation: unresolved; close price and common-share count basis were not reconciled.
- Uncertainty/reconciliation issue: official market and financial source fields remain unresolved, so `required_data_valid=false` and `financial_data_usable=false`.

### 2603 — 長榮海運股份有限公司

- Price date: 2026-07-15
- Market-data source: TWSE intended; not reconciled into canonical values.
- Financial-statement source: MOPS intended; not reconciled into canonical values.
- Financial publication date: unresolved.
- Latest financial quarter available as of price date: unresolved.
- Quarters used in each TTM calculation: unresolved; no TTM value is usable.
- Source statement basis: unresolved; standalone vs cumulative not confirmed.
- Standalone-quarter formulas used: none applied because source periods were not reconciled.
- Common-shareholder net-income basis: unresolved.
- Market-cap calculation: unresolved; close price and common-share count basis were not reconciled.
- Uncertainty/reconciliation issue: official market and financial source fields remain unresolved, so `required_data_valid=false` and `financial_data_usable=false`.

### 1101 — 台灣水泥股份有限公司

- Price date: 2026-07-15
- Market-data source: TWSE intended; not reconciled into canonical values.
- Financial-statement source: MOPS intended; not reconciled into canonical values.
- Financial publication date: unresolved.
- Latest financial quarter available as of price date: unresolved.
- Quarters used in each TTM calculation: unresolved; no TTM value is usable.
- Source statement basis: unresolved; standalone vs cumulative not confirmed.
- Standalone-quarter formulas used: none applied because source periods were not reconciled.
- Common-shareholder net-income basis: unresolved.
- Market-cap calculation: unresolved; close price and common-share count basis were not reconciled.
- Uncertainty/reconciliation issue: official market and financial source fields remain unresolved, so `required_data_valid=false` and `financial_data_usable=false`.
