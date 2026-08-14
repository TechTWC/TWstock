# Watchlist Scanner v0.2 — Daily Run Foundation

## Purpose

Make the official-TWSE Watchlist Scanner safe and practical to rerun each day
without changing either analysis engine or the deterministic ranking contract.
The first run fills a month cache; later runs reuse validated historical months,
fetch missing months, and always refresh the actual current month.

This remains **Shadow Observation only**. `corporate_action_status` is always
`UNVERIFIED`, and `investment_use` is always `PROHIBITED`.

## Incremental cache contract

- The scanner remains TWSE `STOCK_DAY` only and never contacts FinMind.
- Each symbol has an independent persistent cache under
  `<raw-cache-dir>/<symbol>/.monthly/`.
- A historical month is reused only after its metadata identity, official source
  URL, HTTP status, raw filename, and SHA-256 all validate.
- A missing or invalid historical month is fetched again. Invalid bytes are
  never promoted into the research dataset.
- When the requested range intersects today's Asia/Taipei calendar month, that
  month is always fetched from TWSE. A failed refresh never falls back to a
  stale copy.
- A valid v0.1 append-only raw snapshot can be imported once into the stable
  month cache after the same integrity checks.
- Successful months are committed atomically as soon as they validate. If a
  later month fails, rerunning the same command resumes from those completed
  months.
- `twse_cache_run.json` records each month's outcome and whether the requested
  range completed. It contains no credential or investment authorization.
- `--retries` remains a bounded per-month HTTP retry count; it cannot create an
  unbounded retry loop.

## Cache outcomes

- `CACHE_HIT`: validated stable historical month reused.
- `IMPORTED_LEGACY_CACHE`: validated v0.1 snapshot promoted and reused.
- `FETCHED_MISSING`: absent historical month fetched and cached.
- `REFETCHED_INVALID`: invalid historical cache ignored and replaced only after
  a valid official response.
- `REFRESHED_CURRENT`: actual current month fetched regardless of cached state.
- `FAILED_FETCH` / `FAILED_VALIDATION`: run remains incomplete and resumable;
  the affected symbol is unavailable to the scanner.

## Unchanged contracts

- Breakout Tracker v5 and Continuous High Monitor parameters and event logic.
- Candidate ranking, stale-date handling, insufficient-history handling, and
  per-symbol failure isolation.
- Raw, unadjusted official prices and exact `UNVERIFIED` disclosure.
- CSV, dataset evidence, event timeline, manifest, and standalone HTML outputs.

## CLI

```bash
python scripts/run_watchlist_scanner.py \
  --watchlist config/watchlist_v0_1.json \
  --start 2025-01-01 \
  --end 2026-08-14 \
  --output-dir outputs/watchlist_v0_2 \
  --raw-cache-dir outputs/raw_watchlist_v0_2 \
  --retries 2
```

Use the same persistent `--raw-cache-dir` on later daily runs. Do not commit
live cache or report outputs to the repository.

## Exclusions

- No scheduler, notification, deployment, database, adjusted prices, TPEx,
  backtest, optimization, or investment recommendation.
- No modification of the independent corporate-action work in PR #25.
- No claim that cache integrity verifies corporate actions or signal quality.
