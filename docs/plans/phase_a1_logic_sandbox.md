# Phase A1 Logic Sandbox v0.1

## Purpose

Provide the smallest runnable, deterministic implementation of the applicable Phase A1 rules from `Fundamental–Valuation–Technical Monitor v1.10`. The sandbox is designed for rapid modification of thresholds and action logic before any production data pipeline is built.

## Scope

Included:

- canonical one-row-per-stock CSV input
- strict input parsing and validation
- TW liquidity eligibility
- financial-survival fail/warning/context logic
- absolute PE classification
- operating-income direction classification
- v1.10 primary-action precedence
- CSV, JSON, and grouped static HTML output
- synthetic sample records and rule tests

Excluded functionality is listed in the specification and includes live market adapters, historical PE, technical signals, databases, scheduling, APIs, frontend integration, and trading.

## Input schema

Required fields:

| Field | Type | Meaning |
|---|---:|---|
| `symbol` | string | Stock identifier |
| `name` | string | Display name |
| `market` | string | This release supports `TW` only |
| `security_type` | string | This release supports `COMMON` only |
| `price_date` | ISO date | Snapshot price date |
| `required_data_valid` | boolean | Upstream required-data validation result |
| `financial_data_usable` | boolean | Upstream financial usability result |
| `average_turnover_20d` | number | Average 20-session turnover in TWD |
| `market_cap` | number | Market capitalization on the canonical basis |
| `ttm_net_income` | number | TTM net income on the same valuation basis |
| `ttm_operating_income` | number | TTM operating income |
| `ttm_operating_cash_flow` | number | TTM operating cash flow |
| `latest_equity` | number | Latest equity |
| `latest_total_assets` | number | Latest total assets |
| `latest_total_liabilities` | number | Latest total liabilities |
| `latest_current_assets` | number | Latest current assets |
| `latest_current_liabilities` | number | Latest current liabilities |
| `latest_q_operating_income` | number | Latest quarterly operating income |
| `previous_q_operating_income` | number | Previous quarterly operating income |
| `prior_year_q_operating_income` | number | Same quarter one year earlier |

The sample adds `is_synthetic` and `source_note` to make its non-production status explicit.

## Rule flow

```text
validate canonical row
→ evaluate_eligibility
→ evaluate_fundamental_status
→ calculate_absolute_pe_status
→ evaluate_earnings_direction
→ resolve_primary_action
→ preserve separated reason/tag arrays
→ render outputs
```

The rule functions are pure. All numerical boundaries are loaded from `config/settings.yaml`, which uses a dependency-free mapping-only YAML subset.

## Run command

```bash
python -m twstock_engine.runner \
  --input data/sample/phase_a1_snapshot.csv \
  --output-dir outputs/latest
```

Generated files:

```text
outputs/latest/screening_results.csv
outputs/latest/screening_results.json
outputs/latest/report.html
```

## Test command

```bash
python -m pytest tests/test_phase_a1_rules.py
```

## Known limitations

- Input is assumed to be normalized upstream; no TWSE/MOPS extraction or accounting mapping exists.
- Market cap and net income basis compatibility is represented only by `financial_data_usable`.
- Only TW common stocks are supported.
- No historical valuation, price context, technical timing, holding logic, execution model, database, or automation exists.
- The minimal YAML parser supports nested mappings and scalar values, not the complete YAML language.
- Output classifications are research labels, not trading instructions or validated alpha.

## Next iteration

Recommended next step: add a canonical snapshot builder with explicit source contracts and point-in-time financial availability, while keeping this decision engine unchanged behind a stable input contract. Historical PE and technical monitoring should remain separate follow-on slices so they cannot block Phase A1 rule testing.
