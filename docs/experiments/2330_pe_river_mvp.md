# 2330.TW Point-in-Time PE River Experiment

## Purpose

This isolated experiment turns the traditional PE river into a reviewable research console. It does not modify Phase A1 rules, produce a buy/sell instruction, or claim validated alpha.

## v0.1 deterministic bridge

The first report applies the same fixed 2026-07-16 reference close before and after 2026Q2 becomes research-available. It isolates the earnings update effect:

```text
Before 2026Q2 usable: TTM EPS 74.38, P/E 33.21x, 28x river 2,082.64
After  2026Q2 usable: TTM EPS 86.27, P/E 28.63x, 28x river 2,415.56
```

Run:

```bash
python -m twstock_experiments.pe_river
```

Outputs:

```text
outputs/experiments/2330_pe_river/analysis.json
outputs/experiments/2330_pe_river/valuation_ladder.csv
outputs/experiments/2330_pe_river/report.html
```

## v0.2 delayed live report

The live layer adds:

1. A delayed secondary quote from Yahoo Finance, clearly tagged `SECONDARY_DELAYED_QUOTE`.
2. Automatic fallback to the latest official completed TWSE session close when the delayed quote is unavailable.
3. Official TWSE daily history for `2330.TW` and benchmark `0050.TW` through the merged `twstock_data` adapter.
4. Point-in-Time historical trailing P/E and fixed-multiple river history.
5. Current trailing-P/E historical percentile.
6. MA50, MA200, 60-session range, 12-1 momentum, and relative 12-1 momentum versus 0050.
7. PIT quarterly gross-margin and operating-margin context.
8. Official monthly-revenue YoY context.
9. A 63-session single-stock diagnostic grouped by valuation/trend state.
10. Optional ingestion of a previously generated normalized TWSE CSV through `--stock-history-csv` or `--benchmark-history-csv`.

Run:

```bash
python -m twstock_experiments.pe_river_live \
  --history-start 2024-01-01 \
  --output-dir outputs/experiments/2330_pe_river_live
```

Outputs:

```text
outputs/experiments/2330_pe_river_live/live_report.html
outputs/experiments/2330_pe_river_live/live_analysis.json
outputs/experiments/2330_pe_river_live/historical_pe.csv
outputs/experiments/2330_pe_river_live/diagnostic_backtest.csv
```

The workflow `.github/workflows/pe-river-live.yml` runs deterministic tests, fetches current data, builds the report, and uploads a 14-day artifact.

## Point-in-Time boundaries

- `research_available_date` is the decisive quarterly EPS and margin gate.
- The historical percentile is **Trailing P/E**, not historical Forward P/E.
- Monthly revenue is currently used only as current fundamental context because historical `research_available_at` has not yet been completed.
- Analyst-consensus history is not reconstructed from current estimates or manual assumptions.
- The diagnostic is based on one stock and short history. It cannot establish alpha.

## Tests

```bash
python -m pytest tests/test_pe_river_experiment.py tests/test_pe_river_live.py
python -m compileall -q twstock_experiments twstock_data tests
```

## Still intentionally incomplete

1. Full ten-year PIT EPS and price history.
2. Licensed or otherwise defensible historical analyst-consensus vintages.
3. Historical Forward P/E percentiles.
4. PIT-certified monthly-revenue publication timestamps.
5. Cross-sectional portfolio backtests, costs, robustness, and clean out-of-sample validation.
