# Phase A1 Logic Sandbox v0.1 Plan

## Purpose

Provide the smallest runnable deterministic sandbox for rapidly testing and modifying `Fundamental_Valuation_Trend_Breakout_v1` Phase A1 screening logic.

## Scope

The sandbox reads one canonical CSV row per stock, applies deterministic pure rule functions, and writes CSV, JSON, and static HTML outputs. It is experimental and is not production-ready or a validated investment strategy.

## Input schema

Required columns are `symbol`, `name`, `market`, `security_type`, `price_date`, `required_data_valid`, `financial_data_usable`, `average_turnover_20d`, `market_cap`, `ttm_net_income`, `ttm_operating_income`, `ttm_operating_cash_flow`, `latest_equity`, `latest_total_assets`, `latest_total_liabilities`, `latest_current_assets`, `latest_current_liabilities`, `latest_q_operating_income`, `previous_q_operating_income`, and `prior_year_q_operating_income`.

## Rule flow

1. Validate the canonical CSV shape.
2. Apply Gate 1 liquidity.
3. Apply Gate 2 financial survival failures and warnings.
4. Apply Gate 3A absolute PE valuation.
5. Apply Gate 3C operating-income direction.
6. Resolve primary action with separate triggers, warnings, risk flags, data quality flags, and informational tags.
7. Generate CSV, JSON, and static HTML output.

## Run command

```bash
python -m twstock_engine.runner --input data/sample/phase_a1_snapshot.csv --output-dir outputs/latest
```

## Test command

```bash
python -m pytest tests/test_phase_a1_rules.py
```

## Known limitations

No TWSE/MOPS live adapters, historical PE, PE river bands, technical analysis, breakout signals, portfolio monitoring, database, API, notifications, scheduling, authentication, or web dashboard are included.

## Next iteration

Add a richer canonical snapshot fixture and refine action precedence against additional v1.10 examples before connecting any point-in-time data pipeline.
