# Corporate Action Safety Guard v0.2

- Document ID: `TWSTOCK-CORPORATE-ACTION-GUARD-002`
- Status: Active bounded specification
- Effective date: `2026-08-10`
- Scope: TWSE-listed single-symbol raw daily-bar research

## 1. Goal

Prevent ex-dividend, ex-right, capital-reduction, split/reverse-split, and par-value
changes from being interpreted as genuine breakouts, drawdowns, rolling highs, or trend
changes. Prices remain raw and unadjusted. This package blocks contaminated analysis
windows; it does not manufacture adjusted prices.

## 2. Source contract

The first bounded implementation queries all four documented FinMind datasets for the
same symbol and requested date range:

- `TaiwanStockDividendResult`;
- `TaiwanStockCapitalReductionReferencePrice`;
- `TaiwanStockSplitPrice`;
- `TaiwanStockParValueChange`.

The source is explicitly `SECONDARY`. All four HTTP/API queries must succeed, including
valid JSON schema and successful API-level status. An empty `data` array is valid only
after a successful query. A missing token, failed query, malformed response, incomplete
dataset set, duplicate/conflicting normalized event, or detached provenance fails closed.
Authentication uses `Authorization: Bearer <token>`; credentials must never appear in a
request URL, source reference, raw-cache metadata, manifest, or error message.

The source choice follows the documented FinMind fundamental datasets. TWSE also publishes
official ex-right/dividend, capital-reduction, par-value-change, and ETF split result pages;
official per-event cross-checking is a later work package and must not be claimed by v0.2.

References:

- https://finmind.github.io/tutor/TaiwanMarket/Fundamental/
- https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html
- https://www.twse.com.tw/zh/announcement/reduction/twtauu.html
- https://www.twse.com.tw/zh/announcement/change/twtb7u.html
- https://www.twse.com.tw/zh/announcement/split/twtcau.html

## 3. Normalized event contract

Every event preserves:

- stable content-derived `event_id`;
- source, tier, source dataset, source/canonical symbol, and market;
- event type and effective date;
- conservative knowledge date equal to the effective date;
- before price and after-event reference price;
- source detail and raw-content hash.

`knowledge_basis = EFFECTIVE_DATE_CONSERVATIVE` means v0.2 never uses an event before its
effective date. It does not claim to reconstruct the historical announcement timestamp.
The event type must match its source dataset. Event content, evidence hashes, requested
range, or policy version changes the corporate-action dataset identity.

## 4. Guard policy

Each analyzer receives its own deterministic required-clean-history threshold:

- Continuous High reopens at `min(high_windows) + 1` bars. Longer-window fields remain
  unavailable until their own `window + 1` clean bars exist;
- Breakout Tracker: the maximum of
  `pivot_lookback + pivot_confirmation_bars` and `volume_lookback + 1`.

Before the first observed event, raw bars retain existing behavior. On an effective date,
the clean segment resets. The event-date bar is the first post-action-basis bar, but the
analyzer is `ANALYSIS_BLOCKED` until its entire required history is rebuilt inside that
segment. Engines run independently on clean segments, so no Pivot, moving average,
rolling high, volume average, or state can cross an action boundary.

For the default Continuous High parameters, 20-day observations can therefore resume
after 21 clean bars, while 60/120/250-day fields remain unavailable until their individual
history is complete. The run manifest separately reports whether the latest clean segment
is long enough for the 250-day window.

Historical results before a later event remain unchanged. If no event exists, both engine
results must be bit-for-bit identical to their v0.1 behavior.

## 5. Outputs and identity

The real-market runner additionally writes:

- `corporate_actions.csv`;
- `corporate_action_manifest.json`;
- `analysis_guard.csv`.

The CSV outputs retain all allowed historical segments. The standalone HTML chart shows
only the latest safe segment so it never draws a continuous price line across a corporate-
action boundary. If the latest segment is still blocked, the HTML renders an empty-data
state while `market_bars.csv` and `analysis_guard.csv` retain the complete evidence.

`research_input_hash` binds the raw market dataset hash, corporate-action dataset hash,
guard-policy version, Continuous High parameter hash, and Breakout configuration hash.
The run manifest reports event count, secondary coverage state, blocked row count, and
last-bar readiness for each analyzer.

## 6. Acceptance cases

- all four source queries are required, even when all return no events;
- HTTP success with API-level failure is rejected;
- future events do not change earlier guard decisions or engine results;
- reverse-split price jumps do not emit false `NEW_HIGH` or `NEW_TRIGGER` outputs;
- post-event signals reopen only after analyzer-specific clean history is rebuilt;
- no-event outputs remain bit-for-bit compatible;
- event, evidence, policy, or bar identity changes propagate to research input identity;
- existing market-data and engine tests remain passing.

## 7. Explicit exclusions

- adjusted prices, total-return series, return/holding adjustments, and tax treatment;
- official TWSE cross-source verification of all corporate-action event types;
- historical announcement-time reconstruction before effective dates;
- TPEx, whole-market scans, historical universes, backtests, optimization, scheduling,
  notifications, deployment, or investment-use approval.
