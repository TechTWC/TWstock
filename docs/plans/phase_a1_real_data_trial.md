# Phase A1 real-data trial preparation

## Purpose

This trial prepares a manually supplied input workflow for the merged Phase A1 Logic Sandbox. It lets a reviewer copy real Taiwan stock data into `data/trial/phase_a1_real_snapshot.csv`, inspect the canonical CSV through the existing runner, and generate deterministic Phase A1 outputs without adding live data fetching, adapters, databases, APIs, scheduling, or trading automation.

This release supports **TWSE-listed common stocks only**. TWO/TPEx support is excluded from this release and deferred to a future version. The committed template at `data/trial/phase_a1_real_snapshot_template.csv` is not a screenable real-data file. Its row is a placeholder only and contains no fabricated company financial values. Do not claim that any real stock has been screened unless the actual source data was explicitly supplied and retained outside or alongside the trial file.

## Canonical input file

Create a working file from the template:

```bash
cp data/trial/phase_a1_real_snapshot_template.csv data/trial/phase_a1_real_snapshot.csv
```

Then replace the placeholder row with manually sourced point-in-time records for TWSE-listed common stocks. The runner expects one stock per row and the exact canonical columns below. `is_synthetic` and `source_note` are optional parser fields already supported by the sandbox, but they are included in the trial template so data provenance and placeholder status remain explicit.

## Canonical symbol convention

For this release, every TWSE-listed common-stock row must use the `.TW` suffix in the canonical `symbol` field.

```text
TWSE source/exchange code: 2330
Canonical Phase A1 symbol: 2330.TW
```

Bare exchange codes may be used only when querying TWSE, MOPS, or issuer source systems. They must be converted to the canonical suffix form before joining source data, writing the trial CSV, running the engine, comparing outputs, or storing audit notes. Do not mix `2330` and `2330.TW` as row identities because that can split or miss the same security across datasets.

## Field meanings, units, and eventual sources

All money amounts are raw TWD unless a future source contract explicitly normalizes them differently. Do not mix TWD with thousands of TWD or millions of TWD in the same file. Ratios are not entered directly; the sandbox derives debt ratio and current ratio from balance-sheet fields.

| Field | Required | Unit / type | Time basis | Data category | Eventual source | Meaning and trial note |
|---|---:|---|---|---|---|---|
| `symbol` | yes | string | row identity | reference data | TWSE security master or manually verified TWSE listing reference | Canonical TWSE-listed stock identifier ending in `.TW`, for example `2330.TW`. Bare source codes such as `2330` are not valid canonical row identities. Must not be blank. |
| `name` | yes | string | row identity | reference data | TWSE security master or manually verified TWSE listing reference | Company display name. Must match the intended TWSE-listed symbol. |
| `market` | yes | string | snapshot | reference data | TWSE listing reference | Use `TW` for this Phase A1 sandbox release. |
| `security_type` | yes | string | snapshot | reference data | TWSE listing reference | Use `COMMON` for TWSE-listed common stocks supported by this release. |
| `price_date` | yes | ISO date `YYYY-MM-DD` | market close date | market data | TWSE daily market data or manually recorded market data source | Date for market capitalization and average turnover. |
| `required_data_valid` | yes | boolean | row validation | inspection flag | Manual data QA | Set `true` only when every required field is sourced, unit-checked, TWSE-listed common-stock scoped, canonically identified, and point-in-time acceptable. Set `false` to mark the row unusable. |
| `financial_data_usable` | yes | boolean | financial statement availability | inspection flag | Manual data QA based on published financial statements | Set `true` only when financial statement values were publicly available by the intended decision date and pass consistency checks. Set `false` to mark financial data unusable. |
| `average_turnover_20d` | yes | TWD numeric | trailing 20 trading sessions through `price_date` | market data | TWSE daily traded value data | Average daily traded value over the latest 20 trading sessions. Must be finite and nonnegative. |
| `market_cap` | yes | TWD numeric | `price_date` | market data | TWSE market price and common shares outstanding from exchange/company sources | Common-equity market capitalization as of `price_date`, on the same valuation basis as `ttm_net_income`. Must be finite. |
| `ttm_net_income` | yes | TWD numeric | trailing twelve months from standalone quarters | financial statements | Published quarterly financial statements, MOPS-derived filings, or audited source package | Net income for the latest four point-in-time available standalone quarters. Use a common-shareholder earnings basis compatible with `market_cap`. |
| `ttm_operating_income` | yes | TWD numeric | trailing twelve months from standalone quarters | financial statements | Published quarterly income statements | Operating income summed over the latest four point-in-time available standalone quarters. |
| `ttm_operating_cash_flow` | yes | TWD numeric | trailing twelve months from standalone quarters | financial statements | Published quarterly cash-flow statements | Operating cash flow summed over the latest four point-in-time available standalone quarters; do not sum overlapping YTD cumulative values. |
| `latest_equity` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total equity from the latest point-in-time available statement. |
| `latest_total_assets` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total assets from the latest point-in-time available statement. Must be finite and greater than zero. |
| `latest_total_liabilities` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Total liabilities from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_current_assets` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Current assets from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_current_liabilities` | yes | TWD numeric | latest available quarter | financial statements | Published balance sheet | Current liabilities from the latest point-in-time available statement. Must be finite and nonnegative. |
| `latest_q_operating_income` | yes | TWD numeric | latest available standalone quarter | financial statements | Published quarterly income statement after standalone-quarter derivation | Operating income for the latest point-in-time available standalone quarter. |
| `previous_q_operating_income` | yes | TWD numeric | immediately previous standalone quarter | financial statements | Published quarterly income statement after standalone-quarter derivation | Operating income for the standalone quarter immediately before `latest_q_operating_income`. |
| `prior_year_q_operating_income` | yes | TWD numeric | same standalone quarter one year earlier | financial statements | Published quarterly income statement after standalone-quarter derivation | Operating income for the comparable standalone quarter one year before `latest_q_operating_income`. |
| `is_synthetic` | no | boolean | provenance | inspection flag | Manual data QA | Use `false` for manually sourced real-data trial rows. Placeholder/template rows are examples only, not synthetic backtest records. |
| `source_note` | no | string | provenance | audit metadata | Manual data QA | Short source/provenance note, publication date note, or `UNUSABLE: <reason>` marker. |

## Scope exclusions

- This release supports TWSE-listed common stocks only.
- TWO/TPEx securities are excluded and deferred to a future version.
- Do not include TWO/TPEx placeholder records or real TWO/TPEx trial rows in `data/trial/phase_a1_real_snapshot.csv` for this release.

## Standalone-quarter derivation from cumulative statements

The runner requires standalone-quarter values for `latest_q_operating_income`, `previous_q_operating_income`, and `prior_year_q_operating_income`. If the published source presents cumulative year-to-date values, derive standalone quarters before entering them:

```text
Q1 standalone = Q1 cumulative
Q2 standalone = H1 cumulative - Q1 cumulative
Q3 standalone = 9M cumulative - H1 cumulative
Q4 standalone = FY cumulative - 9M cumulative
```

The same standalone-quarter discipline applies to TTM fields. Calculate `ttm_net_income`, `ttm_operating_income`, and especially `ttm_operating_cash_flow` from four standalone quarters. Do **not** sum overlapping YTD cumulative values such as Q1 + H1 + 9M + FY.

## PE basis consistency

The absolute PE calculation depends on a consistent numerator and denominator:

- `market_cap` must be common-equity market capitalization as of `price_date`.
- `ttm_net_income` must use a compatible common-shareholder earnings basis.
- If the ownership basis, parent/common-shareholder basis, or non-controlling-interest treatment cannot be reconciled, set `financial_data_usable=false` and explain the issue in `source_note`.

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
- TTM values must use the latest four available standalone quarters as of the decision date, not the latest four quarters known today unless those are the same point-in-time set.
- If a publication date is uncertain, mark the row unusable rather than guessing.

## Marking data as unusable

A row can be structurally valid but intentionally unusable:

- Set `required_data_valid` to `false` when required inputs are missing, unit-conflicted, out of TWSE-listed common-stock scope, use a noncanonical symbol, are stale, or fail manual QA.
- Set `financial_data_usable` to `false` when financial statements are unavailable, publication dates are uncertain, statement bases conflict, PE basis cannot be reconciled, cumulative values cannot be converted to standalone quarters, or values cannot be reconciled.
- Add `UNUSABLE: <reason>` to `source_note` for auditability.
- Keep required numeric cells finite and structurally valid even for unusable rows so the runner can inspect and report the row instead of failing CSV parsing.

## Run command

After creating `data/trial/phase_a1_real_snapshot.csv` with real manually supplied TWSE-listed common-stock records, run:

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
- [ ] Every row is a TWSE-listed common stock; TWO/TPEx rows are excluded for this release.
- [ ] Every `symbol` uses the canonical `.TW` suffix, such as `2330.TW`; no bare exchange code is used as a row identity.
- [ ] Every required field is present and nonblank.
- [ ] All numeric fields are finite raw TWD values, except booleans and identifiers.
- [ ] `latest_total_assets` is greater than zero for every row.
- [ ] Market-data fields were sourced as of `price_date`.
- [ ] `market_cap` and `ttm_net_income` use compatible common-equity/common-shareholder bases.
- [ ] Financial-statement fields were available by the intended decision date.
- [ ] Standalone-quarter values were derived from cumulative statements before populating quarterly operating-income fields.
- [ ] TTM fields use exactly the latest four point-in-time available standalone quarters and do not sum overlapping YTD cumulative values.
- [ ] Unusable rows are marked with `required_data_valid=false` and/or `financial_data_usable=false` plus a `source_note` reason.
- [ ] No output is described as screening a real stock unless the actual source data was explicitly supplied.
