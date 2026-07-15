# Phase A1 real-data trial preparation

## Purpose

This trial prepares a manually supplied input workflow for the merged Phase A1 Logic Sandbox. It lets a reviewer copy real Taiwan stock data into `data/trial/phase_a1_real_snapshot.csv`, inspect the canonical CSV through the existing runner, and generate deterministic Phase A1 outputs without adding live data fetching, adapters, databases, APIs, scheduling, or trading automation.

The committed template at `data/trial/phase_a1_real_snapshot_template.csv` is not a screenable real-data file. Its rows are placeholders only and contain no fabricated company financial values. Do not claim that any real stock has been screened unless the actual source data was explicitly supplied and retained outside or alongside the trial file.

## Canonical input file

Create a working file from the template:

```bash
cp data/trial/phase_a1_real_snapshot_template.csv data/trial/phase_a1_real_snapshot.csv
```

Then replace every placeholder row with manually sourced point-in-time records. The runner expects one stock per row and the exact canonical columns below. `is_synthetic` and `source_note` are optional parser fields already supported by the sandbox, but they are included in the trial template so data provenance and placeholder status remain explicit.

## Field meanings, units, and eventual sources

All money amounts are raw TWD unless a future source contract explicitly normalizes them differently. Do not mix TWD with thousands of TWD or millions of TWD in the same file. Ratios are not entered directly; the sandbox derives debt ratio and current ratio from balance-sheet fields.

| Field | Required | Unit / type | Time basis | Data category | Eventual source | Meaning and trial note |
|---|---:|---|---|---|---|---|
| `symbol` | yes | string | row identity | reference data | TWSE/TPEx security master or manually verified listing reference | Taiwan stock identifier such as an exchange suffix convention selected by the project. Must not be blank. |
| `name` | yes | string | row identity | reference data | TWSE/TPEx security master or manually verified listing reference | Company display name. Must match the intended symbol. |
| `market` | yes | string | snapshot | reference data | TWSE/TPEx listing reference | Use `TW` for this Phase A1 sandbox release. |
| `security_type` | yes | string | snapshot | reference data | TWSE/TPEx listing reference | Use `COMMON` for common stocks supported by this release. |
| `price_date` | yes | ISO date `YYYY-MM-DD` | market close date | market data | TWSE/TPEx daily market data or manually recorded market data source | Date for market capitalization and average turnover. |
| `required_data_valid` | yes | boolean | row validation | inspection flag | Manual data QA | Set `true` only when every required field is sourced, unit-checked, and point-in-time acceptable. Set `false` to mark the row unusable. |
| `financial_data_usable` | yes | boolean | financial statement availability | inspection flag | Manual data QA based on published financial statements | Set `true` only when financial statement values were publicly available by the intended decision date and pass consistency checks. Set `false` to mark financial data unusable. |
| `average_turnover_20d` | yes | TWD numeric | trailing 20 trading sessions through `price_date` | market data | TWSE/TPEx daily traded value data | Average daily traded value over the latest 20 trading sessions. Must be finite and nonnegative. |
| `market_cap` | yes | TWD numeric | `price_date` | market data | Market price and shares outstanding from exchange/company sources | Market capitalization on the same valuation basis as TTM net income. Must be finite. |
| `ttm_net_income` | yes | TWD numeric | trailing twelve months | financial statements | Published quarterly financial statements, MOPS-derived filings, or audited source package | Net income summed over the latest four available quarters. Use point-in-time available quarters only. |
| `ttm_operating_income` | yes | TWD numeric | trailing twelve months | financial statements | Published quarterly income statements | Operating income summed over the latest four available quarters. |
| `ttm_operating_cash_flow` | yes | TWD numeric | trailing twelve months | financial statements | Published quarterly cash-flow statements | Operating cash flow summed over the latest four available quarters. |
| `latest_equity` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total equity from the latest point-in-time available statement. |
| `latest_total_assets` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total assets from the latest point-in-time available statement. Must be finite and greater than zero. |
| `latest_total_liabilities` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total liabilities from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_current_assets` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Current assets from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_current_liabilities` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Current liabilities from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_q_operating_income` | yes | TWD numeric | latest available quarter | financial statements | Published quarterly income statement | Operating income for the latest point-in-time available quarter. |
| `previous_q_operating_income` | yes | TWD numeric | immediately previous quarter | financial statements | Published quarterly income statement | Operating income for the quarter immediately before `latest_q_operating_income`. |
| `prior_year_q_operating_income` | yes | TWD numeric | same quarter one year earlier | financial statements | Published quarterly income statement | Operating income for the comparable quarter one year before `latest_q_operating_income`. |
| `is_synthetic` | no | boolean | provenance | inspection flag | Manual data QA | Use `false` for manually sourced real-data trial rows. Placeholder/template rows are examples only, not synthetic backtest records. |
| `source_note` | no | string | provenance | audit metadata | Manual data QA | Short source/provenance note, publication date note, or `UNUSABLE: <reason>` marker. |

## Fields requiring market data

- `price_date`
- `average_turnover_20d`
- `market_cap`
- Market/reference validation for `symbol`, `name`, `market`, and `security_type`

## Fields requiring financial statements

- `financial_data_usable`
- `ttm_net_income`
- `ttm_operating_income`
- `ttm_operating_cash_flow`
- `latest_equity`
- `latest_total_assets`
- `latest_total_liabilities`
- `latest_current_assets`
- `latest_current_liabilities`
- `latest_q_operating_income`
- `previous_q_operating_income`
- `prior_year_q_operating_income`

## Point-in-time and publication-date risks

- Do not use a quarter in TTM or latest-quarter fields unless that statement had already been published by the intended decision date.
- Keep market data as of `price_date`; do not combine a later market capitalization with an earlier liquidity window.
- Restatements, late filings, corrections, and consolidated versus parent-only statements can create look-ahead bias if the value was not available at the time.
- TTM values must use the latest four available quarters as of the decision date, not the latest four quarters known today unless those are the same point-in-time set.
- If a publication date is uncertain, mark the row unusable rather than guessing.

## Marking data as unusable

A row can be structurally valid but intentionally unusable:

- Set `required_data_valid` to `false` when required inputs are missing, unit-conflicted, stale, or fail manual QA.
- Set `financial_data_usable` to `false` when financial statements are unavailable, publication dates are uncertain, statement bases conflict, or values cannot be reconciled.
- Add `UNUSABLE: <reason>` to `source_note` for auditability.
- Keep required numeric cells finite and structurally valid even for unusable rows so the runner can inspect and report the row instead of failing CSV parsing.

## Run command

After creating `data/trial/phase_a1_real_snapshot.csv` with real manually supplied records, run:

```bash
python -m twstock_engine.runner \
  --input data/trial/phase_a1_real_snapshot.csv \
  --output-dir outputs/real_trial
```

The runner performs input inspection before screening and fails clearly for missing required columns, blank required values, invalid numeric fields, nonpositive `latest_total_assets`, non-finite numeric values, or an input file with no records.

## Expected output files

The command writes these files under `outputs/real_trial/`:

- `screening_results.csv`
- `screening_results.json`
- `report.html`

## Validation checklist

Before treating any output as a real-data trial result:

- [ ] The working CSV is named `data/trial/phase_a1_real_snapshot.csv`, not the template file.
- [ ] Every placeholder row was removed.
- [ ] Every required field is present and nonblank.
- [ ] All numeric fields are finite raw TWD values, except booleans and identifiers.
- [ ] `latest_total_assets` is greater than zero for every row.
- [ ] Market-data fields were sourced as of `price_date`.
- [ ] Financial-statement fields were available by the intended decision date.
- [ ] TTM fields use exactly the latest four point-in-time available quarters.
- [ ] Unusable rows are marked with `required_data_valid=false` and/or `financial_data_usable=false` plus a `source_note` reason.
- [ ] No output is described as screening a real stock unless the actual source data was explicitly supplied.
