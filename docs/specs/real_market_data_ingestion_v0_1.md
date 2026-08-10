# Real Market Data Ingestion v0.1 — Research Dataset Contract

- Document ID: `TWSTOCK-REAL-MARKET-DATA-001`
- Version: `0.1.0`
- Status: Active bounded implementation specification
- Effective date: `2026-08-10`
- Evidence level: Data plumbing only; no strategy or performance claim

## 1. Objective

Connect the existing Taiwan daily-market adapters to `Breakout Tracker v5` and
`Continuous High Monitor v0.1` without discarding source provenance or silently accepting
cross-source conflicts. The output is one canonical, content-addressed daily-bar dataset
that both engines can replay.

This package establishes a research input contract. It does not validate either strategy.

## 2. Source and trust policy

- TWSE `STOCK_DAY` is the primary source for listed Taiwan stocks.
- FinMind `TaiwanStockPrice` is an optional secondary cross-check when `FINMIND_TOKEN` is
  available.
- Matching primary and secondary data produces `PRIMARY_VERIFIED`.
- Primary data without a secondary response remains usable, but the dataset records
  `cross_check_unavailable=true`.
- `SOURCE_MISMATCH` and `SOURCE_UNAVAILABLE` fail closed.
- `SECONDARY_ONLY` fails closed unless the caller explicitly enables
  `allow_secondary_only`; that state remains visible in every manifest.
- Tokens must not appear in source references, errors, raw-cache metadata, or outputs.

This v0.1 contract supports TWSE-listed symbols only. TPEx is not silently mapped to
`.TW` and remains out of scope.

## 3. Canonical bar

Each bar contains:

- canonical symbol and ISO trade date;
- raw daily open, high, low, and close;
- traded share volume;
- official traded value in TWD when supplied by the market source.

Official traded value is preserved end to end. `Continuous High Monitor` uses it for the
liquidity feature; synthetic bars without an official value retain the prior
`close × volume` fallback.

Bars must contain exactly one symbol, strictly ascending unique dates, valid OHLC bounds,
positive volume and traded value, and dates inside the requested interval.

## 4. Price basis and point-in-time boundary

The dataset is explicitly:

```text
price_basis = RAW_OFFICIAL_DAILY
adjustment_policy = RAW_UNADJUSTED
corporate_actions_applied = false
```

No split, ex-right, ex-dividend, total-return, or survivorship adjustment is inferred.
Therefore this package is suitable for ingestion and replay diagnostics, but not yet for
long-horizon return claims or signals that cross an untreated corporate-action break.

The requested end date is the latest permissible observation. Both engines retain their
existing prefix-replay/no-future-data behavior. Retrieval time is provenance, not a market
observation and is excluded from the dataset content hash.

## 5. Reproducibility and outputs

`market_bars.csv` contains canonical engine bars plus source tier, retrieval timestamp,
and raw content hash. `dataset_manifest.json` records:

- query identity and interval;
- reconciliation state and cross-check availability;
- selected source and record range;
- raw response hashes and retrieval timestamps;
- secondary verification source, raw hashes, and retrieval timestamps when a cross-check
  is claimed;
- price/adjustment policy;
- SHA-256 dataset content hash.

The dataset hash changes with market content, requested interval, source state, selected
source, price policy, selected-source raw identity, or secondary verification raw identity.
It does not change solely because the same payload was retrieved later. A dataset cannot
claim an available cross-check without preserving secondary verification provenance.

The bounded runner also writes:

- Continuous High event and feature CSVs;
- a standalone Continuous High HTML/SVG report with Pivot markers;
- Pivot snapshot CSV;
- `run_manifest.json` linking dataset and parameter/config hashes.

## 6. Command

```bash
python scripts/run_real_market_monitor.py \
  --symbol 2330 \
  --start 2025-01-01 \
  --end 2026-08-10 \
  --output-dir outputs/real_market/2330 \
  --raw-cache-dir outputs/raw_market/2330
```

FinMind is optional. Set `FINMIND_TOKEN` to enable the cross-check. Do not pass tokens on
the command line.

The default Continuous High configuration needs 251 daily bars before its 250-day
comparison can become available. Shorter inputs still run, but the run manifest marks the
history as insufficient and unavailable long-window fields remain blank.

## 7. Acceptance cases

- Matching TWSE and FinMind fixtures create a primary verified dataset.
- TWSE data without a FinMind token remains usable and is visibly un-cross-checked.
- Cross-source date, volume, traded-value, or close mismatches block promotion.
- Secondary-only input requires explicit opt-in.
- Raw responses and metadata are preserved for both sources.
- Official traded value survives dataset creation, CSV round trip, feature calculation,
  and report consistency checks.
- Dataset and run manifests link data hashes and parameter/config hashes.
- Existing synthetic-data engine tests remain unchanged and passing.

## 8. Explicit exclusions

This package does not add TPEx, Yahoo, adjusted prices, corporate-action processing,
full-market universes, delisted securities, scheduling, databases, incremental updates,
notifications, performance backtests, parameter optimization, machine learning,
deployment, or investment recommendations.

A live network smoke test is a separate gate. Fixture success must not be reported as
proof that TWSE or FinMind is reachable from a deployment environment.
