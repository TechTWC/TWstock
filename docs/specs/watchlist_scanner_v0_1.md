# Watchlist Scanner v0.1

## Purpose

Scan several TWSE-listed symbols in one bounded run. The scanner reuses the
point-in-time-safe Breakout Tracker v5 and Continuous High Monitor, then emits a
candidate order, exact reason codes, a combined event timeline, evidence files,
and a standalone HTML report.

This is **Shadow Observation only**. `investment_use` is always `PROHIBITED`.

## Source and safety contract

- Price source: official TWSE `STOCK_DAY` raw daily prices only.
- FinMind is not contacted by this workflow, even if a token exists.
- Price basis is raw and unadjusted.
- Corporate-action coverage is absent, so every observation is explicitly
  `corporate_action_status=UNVERIFIED`.
- An ex-right, ex-dividend, split, or similar discontinuity can create a false
  breakout or high event. No output may be used for investment decisions.
- A data error in one symbol is isolated as `DATA_UNAVAILABLE`; other symbols
  continue scanning.
- A symbol with fewer than 251 bars is `INSUFFICIENT_HISTORY` and unranked.
- A symbol whose last trading date predates the latest successfully loaded date
  in the scan is `STALE_DATA` and unranked.

## Ranking contract

There is no opaque numeric score. Rank is a deterministic lexicographic
observation priority:

1. Candidate tier, in this order:
   `DUAL_TRIGGER`, `BREAKOUT_TRIGGER`, `EARLY_HIGH`, `STRENGTHENING`,
   `NEW_HIGH`, `RETEST`, `LEADER`, `SETUP`, `CONFIRMED`, `WATCH`, `EXTENDED`,
   `COOLING`, `WEAKENING`, `INACTIVE`.
2. Current volume ratio, descending. Missing volume ratio sorts last.
3. Absolute distance to the frozen pivot, ascending. Missing distance sorts last.
4. TWSE source symbol, ascending, as the stable final tie-break.

Only rows with `scan_status=OK` receive a rank. Rank means inspection priority,
not expected return, quality, safety, or a buy recommendation. Risk flags remain
visible and do not silently modify the ordering.

## Outputs

- `watchlist_candidates.csv`: all ranked and unranked observations with reasons.
- `watchlist_timeline.csv`: Continuous High events plus Breakout state changes.
- `watchlist_manifest.json`: inputs, hashes, policy, counts, output inventory,
  ranking contract, and warnings.
- `watchlist.html`: standalone human-readable summary. To keep the file bounded,
  it displays at most the latest 1,000 events; the timeline CSV remains complete.
- `symbols/<symbol>/`: official normalized bars and dataset manifest for each
  successfully loaded symbol.

Event IDs are stable hashes of the engine/config, symbol, date, event type, and
detail. The same inputs and engine parameters produce the same ordering and IDs.

## CLI

```bash
python scripts/run_watchlist_scanner.py \
  --watchlist config/watchlist_v0_1.json \
  --start 2025-01-01 \
  --end 2026-08-13 \
  --output-dir outputs/watchlist_v0_1 \
  --raw-cache-dir outputs/raw_watchlist_v0_1
```
