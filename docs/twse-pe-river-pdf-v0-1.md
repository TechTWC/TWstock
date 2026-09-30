# TWSE Historical PE River PDF v0.1

This standalone report accepts one TWSE ordinary-share code. It does not
change the formal strategy engine or the existing experiment PR #21.

```bash
python -m pip install -r requirements-dev.txt
python scripts/run_pe_river_report.py --symbol 2330 --max
python scripts/run_pe_river_report.py --symbol 2330 --years 20
python scripts/run_pe_river_report.py --symbol 2330 --years 5 --multiples 10 15 20 25 30
```

Default coverage is MAX, starting at the first available official valuation
observation on or after 2005-09-01. `--years` accepts 5, 10 or 20 calendar
years anchored to the last available completed market observation. Shorter
company histories are accepted. Today's data is excluded before 14:30 Taipei
time to avoid using an intraday or unpublished session.

## Official observation contract

Live inspection confirmed that **BWIBBU does not have a close column or a
stock code in its title**, including both the 2005 and 2026 schemas. Its
historical date is ROC `094年09月02日`; the earnings-year/quarter and dividend
year fields were added later and are optional. STOCK_DAY rejects dates before
2010-01-04, so it cannot supply this report's 20-year close history.

The adapter therefore creates one paired historical observation contract:

- `https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU`
- `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_AVG`
- Query: `response=json&date=YYYYMM01&stockNo=2330`.
- STOCK_DAY_AVG's title must contain the requested four-digit stock code.
  BWIBBU's company name must exactly match STOCK_DAY_AVG's company name.
  Explicit code fields, if supplied, must also match.
- Close and PE are joined by the exact trading date, never by row position.
  STOCK_DAY_AVG's explicitly labeled monthly average row is excluded.
- Missing PE dates remain in the close series with blank EPS and river prices.
  A valuation date without a matching numeric official close fails closed.
  No interpolation, forward filling or price adjustment is performed.

TWSE's [official methodology](https://www.twse.com.tw/zh/trading/historical/bwibbu.html)
uses reference earnings from the most recent four filed quarters available at
calculation time and does not back-calculate historical PE. For a day without
a closing price, TWSE can substitute a reference price in its valuation
calculation; this report does not invent that price. The two source URLs and
raw payload hashes are retained in the cache and report provenance.

`reference_eps_twd = official_close / official_pe` is **TWSE-implied reference
EPS**, subject to rounding of published PE, not reported/diluted accounting
EPS. `river_price = reference_eps_twd * multiple`. Blank, `-`, `--`, zero and
negative PE are unavailable; malformed numeric text fails closed.

Percentile levels use linear interpolation at `(n-1)*p`. The current rank
uses the empirical CDF, `100 * count(PE <= latest valid PE) / valid count`,
including the current observation and all ties. Only positive official PE in
the selected report window enters the distribution. The latest market date
and latest valid PE date are reported separately, with both associated closes.

## Outputs and cache

Default `outputs/pe_river/2330/` contains:

- `2330_pe_river.pdf`: one landscape Matplotlib page with the price rivers,
  official close and summary.
- `historical_pe_river.csv`: all paired observations, status, implied EPS,
  configurable band prices and source URLs.
- `report_metadata.json`: actual coverage, counts, dates, distribution,
  methodology and monthly source provenance.

`--output-dir` and `--cache-dir` override defaults. Raw cache defaults to
`data/runtime/raw/pe_river/2330/`. It reuses the existing integrity-checked
monthly cache implementation in separate endpoint namespaces. SHA-256,
source URL, month and symbol identities are validated on read. Validated
months survive interrupted runs. The current month, immediately preceding
month and last requested month refresh; older stable months are reused.
The run manifest records completed/failed months and missing PE dates.
Historical raw data and generated outputs are excluded from git.

Requests are sequential with a default one-second minimum interval and bounded
retries. A failed response stops the report; rerun the same command to resume.
Explicit official no-data months are recorded; an empty `OK`, invalid schema,
malformed dates, wrong identity, nonnumeric close, duplicate/unordered dates
or a truncated response fails closed. Actual coverage does not certify
completeness against an independent trading calendar. No source history is
fabricated to reach 20 years.

## Offline validation

```bash
python -m pytest -q tests/test_twse_valuation.py tests/test_pe_river.py tests/test_pe_river_pdf.py
python -m pytest -q
python -m compileall -q twstock_data twstock_valuation scripts tests
git diff --check
```

Tests use saved official historical fixtures and synthetic mutations; ordinary
CI does not require live TWSE requests. This package contains no dashboard,
web server, TPEx integration, financial-statement backfill or trading signal.
