# 2330.TW Point-in-Time PE River Experiment MVP

## Purpose

This is an isolated exploratory implementation used to inspect how a traditional PE river changes when a newly reported quarter becomes research-available.

It does **not** modify Phase A1 screening rules, does not create a buy/sell signal, and does not claim validated alpha.

## What the first prototype shows

1. A pre-release TTM EPS snapshot using only observations available on 2026-07-16.
2. A post-release TTM EPS snapshot after 2026Q2 becomes available on 2026-07-17.
3. The same fixed reference close applied to both snapshots to isolate the EPS update.
4. A configurable PE ladder.
5. Editable bear/base/bull Forward EPS and exit-PE assumptions.
6. Implied EPS required by the current price at each PE multiple.
7. Explicit separation of official actual data and manual assumptions.

## Run

```bash
python -m twstock_experiments.pe_river
```

Default outputs:

```text
outputs/experiments/2330_pe_river/analysis.json
outputs/experiments/2330_pe_river/valuation_ladder.csv
outputs/experiments/2330_pe_river/report.html
```

## Inputs to edit

```text
data/experiments/2330_pe_river/eps_history.csv
data/experiments/2330_pe_river/reference_price.csv
data/experiments/2330_pe_river/river_multiples.csv
data/experiments/2330_pe_river/forward_scenarios.csv
```

`research_available_date` is the decisive Point-in-Time gate. A quarter cannot enter TTM EPS before that date.

The 2026-07-16 reference close is tagged `PUBLIC_REFERENCE_NOT_RECONCILED`. Replace it with the verified TWSE market-data adapter output after the live smoke test is accepted.

## Current deterministic bridge

Using the committed input rows:

```text
Before 2026Q2 is usable:
TTM EPS = 74.38
Reference P/E = 33.21x
28x river price = 2,082.64

After 2026Q2 is usable:
TTM EPS = 86.27
Reference P/E = 28.63x
28x river price = 2,415.56
```

This is not a return forecast. It demonstrates how much of an apparently extreme trailing valuation can be absorbed by an earnings update.

## Test

```bash
python -m pytest tests/test_pe_river_experiment.py
```

## Next experiment candidates

Do not add all items at once. Review the first HTML output, then choose the next research question:

1. Historical Forward P/E percentile bands.
2. Analyst EPS revision history with vintage preservation.
3. Revenue and margin confirmation.
4. Relative momentum and price confirmation.
5. Point-in-Time cross-sectional backtest.
