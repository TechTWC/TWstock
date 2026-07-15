# Phase A1 first real-data trial — BLOCKED source report

This PR remains a **Draft** data-integration trial for the Phase A1 Logic Sandbox. It is not a backtest, validated strategy, production data pipeline, investment recommendation, or recommendation for any stock.

## Current status

**BLOCKED — no screenable real-data CSV is committed in this revision.**

The earlier placeholder-zero `data/trial/phase_a1_real_snapshot.csv` has been removed because placeholder numeric values must not be retained for real company symbols. The requested replacement is one genuinely reconciled row for TWSE common stock 2330 only, but the row was not created because all required official-source fields could not be reconciled in this environment.

## Trial universe after review

- Required real-data row: 2330 — 台灣積體電路製造股份有限公司 (Taiwan Semiconductor Manufacturing Company Limited)
- Removed from the trial snapshot scope: 2317, 2454, 2603, 1101

## Stop condition applied

The task requires official public sources only and says to stop if official source access is unavailable or any required field cannot be reconciled. This stop condition was applied because the required numeric fields for 2330 were not fully reconciled from official TWSE/MOPS source records.

As a result:

- `data/trial/phase_a1_real_snapshot.csv` is not committed with placeholder values.
- The Phase A1 screening engine was not run against a placeholder row.
- `required_data_valid=true` was not asserted.
- `financial_data_usable=true` was not asserted.
- No real-data trial success is claimed.


## Official references checked

- TWSE daily individual-security trading data page: `https://www.twse.com.tw/en/trading/historical/stock-day.html`
- TWSE Chinese daily individual-security trading data page: `https://www.twse.com.tw/zh/trading/historical/stock-day.html`
- TWSE 2330 company PDF fact sheet: `https://www.twse.com.tw/pdf/ch/2330_ch.pdf`
- MOPS entry point: `https://mops.twse.com.tw/`

These official references identify the intended source paths, but the complete set of required point-in-time records and accounting values was not reconciled from them in this environment.

## Official-source requirements not yet satisfied

A usable 2330 row still requires the following official-source reconciliation before `data/trial/phase_a1_real_snapshot.csv` can be restored:

1. **TWSE listing identity**
   - Confirm 2330 is a TWSE-listed common stock as of the selected common `price_date`.

2. **Completed TWSE trading date**
   - Select the latest completed TWSE trading day available at execution time.
   - Document the exact `price_date`.

3. **20-session turnover window**
   - Retrieve the 20 completed TWSE trading sessions ending on `price_date`.
   - Record each session date and official TWSE daily traded value.
   - Calculate `average_turnover_20d` as the arithmetic average of those 20 traded-value observations.

4. **Closing price and market capitalization**
   - Retrieve the official TWSE closing price for 2330 on `price_date`.
   - Reconcile a common-share count basis available as of `price_date`.
   - Calculate `market_cap = closing_price × common_share_count` in raw TWD.

5. **MOPS financial publication dates**
   - Identify the latest financial statements for 2330 that were published and publicly available no later than `price_date`.
   - Document each filing/publication date used.

6. **Standalone-quarter financial statement values**
   - Reconcile `latest_q_operating_income`, `previous_q_operating_income`, and `prior_year_q_operating_income` as standalone-quarter values.
   - If source statements are cumulative, use these formulas:
     - Q1 standalone = Q1 cumulative
     - Q2 standalone = H1 cumulative - Q1 cumulative
     - Q3 standalone = 9M cumulative - H1 cumulative
     - Q4 standalone = FY cumulative - 9M cumulative

7. **TTM values from non-overlapping standalone quarters**
   - Calculate `ttm_net_income`, `ttm_operating_income`, and `ttm_operating_cash_flow` from four non-overlapping standalone quarters.
   - Do not sum overlapping cumulative year-to-date values.

8. **Common-shareholder net-income basis**
   - Confirm that `ttm_net_income` uses a compatible common-shareholder earnings basis.
   - Reconcile any non-controlling-interest or ownership-basis presentation issue before marking the row usable.

9. **Latest balance-sheet values**
   - Reconcile raw-TWD values for:
     - `latest_equity`
     - `latest_total_assets`
     - `latest_total_liabilities`
     - `latest_current_assets`
     - `latest_current_liabilities`

## Canonical values

No canonical 2330 numeric values are provided in this revision. Required values remain unresolved and must not be substituted with zero or estimates.

## Runner status

The runner was intentionally **not** executed on `data/trial/phase_a1_real_snapshot.csv` in this revision because no reconciled real-data input CSV exists. This follows the stop condition and avoids treating placeholder values as a real-data trial.

## Recommended next iteration

- Obtain TWSE source records for 2330 daily trading data and share-count/market-cap basis using an access path that works in the execution environment.
- Obtain MOPS financial filing records and issuer financial reports for 2330, then reconcile publication dates and accounting presentation.
- Restore `data/trial/phase_a1_real_snapshot.csv` only after every canonical numeric field is populated with official-source, raw-TWD, point-in-time values.
- Run `python -m twstock_engine.runner --input data/trial/phase_a1_real_snapshot.csv --output-dir outputs/real_trial` only after the real row is fully reconciled and both `required_data_valid` and `financial_data_usable` are legitimately `true`.
