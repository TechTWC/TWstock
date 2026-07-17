# 2330.TW Point-in-Time PE River Experiment

## Purpose

This isolated experiment turns the traditional PE river into a reviewable research console. It does not modify Phase A1 rules, produce a buy/sell instruction, or claim validated alpha.

## v0.1 deterministic earnings bridge

The first report applies the same fixed 2026-07-16 reference close before and after 2026Q2 becomes research-available. It isolates the earnings update effect:

```text
Before 2026Q2 usable: TTM EPS 74.38, P/E 33.21x, 28x river 2,082.64
After  2026Q2 usable: TTM EPS 86.27, P/E 28.63x, 28x river 2,415.56
```

Run:

```bash
python -m twstock_experiments.pe_river
```

## v0.2 delayed live valuation console

The live layer added:

1. A delayed secondary quote from Yahoo Finance, clearly tagged `SECONDARY_DELAYED_QUOTE`.
2. Automatic fallback to the latest official completed TWSE session close.
3. Official TWSE daily history for `2330.TW` and benchmark `0050.TW`.
4. PIT historical trailing P/E, fixed-multiple river history, MA50, MA200, momentum, quarterly margins and current monthly-revenue context.
5. A first 63-session single-stock diagnostic.

## v0.3 complete five-year PIT river

The current revision adds the requested research depth without changing the formal strategy engine.

### Five-year trailing-P/E river

- Quarterly diluted EPS history now starts at 2020Q1.
- Every quarter carries `publication_date` and conservative `research_available_date`.
- The displayed five-year window is calculated from the quote date.
- An additional 450-calendar-day fetch buffer supports MA200, 12-1 momentum and early-window calculations.
- Each historical trading day uses only EPS that had become research-available on that date.
- The live report and `historical_pe.csv` show official TWSE close, PIT TTM EPS, trailing P/E and every configured river multiple.

### Historical Forward P/E contract

Historical Forward P/E is kept separate from manual Forward scenarios.

Input contract:

```text
data/experiments/2330_pe_river/forward_eps_vintages.csv
```

Required fields:

```text
as_of_date
ntm_eps_twd
source_name
data_status
source_url
source_note
```

Every usable row must have:

```text
VERIFIED_ANALYST_CONSENSUS_VINTAGE
```

The loader rejects manual assumptions, missing source attribution, duplicate vintage dates and nonpositive NTM EPS. A header-only file is a valid fail-closed state: the report shows that historical Forward P/E percentile is unavailable rather than substituting current consensus or ex-post actual earnings.

A Forward P/E percentile is labelled fully available only after at least:

- 252 daily Forward P/E observations; and
- 8 distinct verified consensus vintages.

### Multi-horizon excess-return diagnostic

Month-end observations are evaluated against `0050.TW` over:

| Approximate horizon | Trading sessions |
|---|---:|
| 1 month | 21 |
| 3 months | 63 |
| 6 months | 126 |
| 9 months | 189 |
| 1 year | 252 |

For each horizon and valuation/trend bucket, the output includes:

- observation count;
- average 2330 return;
- average 0050 return;
- average excess return;
- median excess return; and
- percentage of observations with positive excess return.

The report also includes an `ALL` row for each horizon.

These observations overlap because signals are monthly while holding periods may be up to one year. They are not independent statistical samples and cannot establish alpha.

## Run

```bash
python -m twstock_experiments.pe_river_live \
  --analysis-years 5 \
  --output-dir outputs/experiments/2330_pe_river_live
```

Optional exact window controls:

```bash
python -m twstock_experiments.pe_river_live \
  --analysis-start 2021-07-17 \
  --history-start 2020-05-01
```

## Outputs

```text
outputs/experiments/2330_pe_river_live/live_report.html
outputs/experiments/2330_pe_river_live/live_analysis.json
outputs/experiments/2330_pe_river_live/historical_pe.csv
outputs/experiments/2330_pe_river_live/historical_forward_pe.csv
outputs/experiments/2330_pe_river_live/multi_horizon_backtest.csv
```

The workflow `.github/workflows/pe-river-live.yml` runs deterministic tests, compiles the experiment code, fetches current data, validates all expected outputs and uploads a 14-day artifact.

## Point-in-Time boundaries

- `research_available_date` is the decisive quarterly EPS and margin gate.
- Historical trailing P/E uses actual EPS only after publication availability.
- Historical Forward P/E requires dated analyst-consensus vintages; current estimates cannot be backfilled into the past.
- Manual Bear/Base/Bull scenarios remain pressure tests and never enter the historical Forward P/E dataset.
- Monthly revenue remains current context until historical availability timestamps are completed.
- Delayed Yahoo quotes are secondary data; official completed TWSE closes are the fallback.

## Tests

```bash
python -m pytest tests/test_pe_river_experiment.py tests/test_pe_river_live.py
python -m compileall -q twstock_experiments twstock_data tests
```

## Still intentionally incomplete

1. A defensible licensed or archived source of historical analyst-consensus vintages.
2. PIT-certified monthly-revenue publication timestamps.
3. Cross-sectional portfolio backtests with transaction costs.
4. Robustness, non-overlapping inference, multiple-testing control and clean out-of-sample validation.
5. Any real-capital or automated-trading authorization.
