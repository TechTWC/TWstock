# Watchlist Radar v0.4

- Status: Active bounded implementation
- Effective date: 2026-08-17
- Use: Shadow Observation only

## Research question

Detect stocks moving from consolidation into an early, orderly uptrend before they
become substantially extended. The report allocates research attention; it does not
produce a buy/sell action, success probability, expected return, or composite score.

## Seven mutually exclusive states

The seven-state layer is a transparent translation of the point-in-time MA baseline.
Core direction uses MA5/10/20/60. MA120/200/240 describe long-term context only.

| State | Testable default rule |
|---|---|
| `NOISE` | Insufficient history or mixed MA evidence with no dominant structure. |
| `BASE` | MA20 and MA60 are approximately flat, MA5/10/20/60 spread is at most 3%, and close is near MA20. |
| `TURNING_UP` | Close above MA20, MA5 above MA10, and MA20 slope positive, without full confirmed alignment. |
| `TREND_CONFIRMED` | Close > MA5 > MA10 > MA20 > MA60 and both MA20/MA60 slopes exceed the MA baseline tolerance, for fewer than 10 consecutive bars. |
| `PERSISTING` | After full trend confirmation, the core bullish structure remains intact for at least 10 bars and close is less than 12% above MA20. A temporary MA-slope slowdown may return the raw MA state to `TURNING_UP` without resetting persistence. |
| `EXTENDED` | An early-up or confirmed-up configuration with close at least 12% above MA20. |
| `WEAKENING` | The MA baseline is turning down/downtrend, or a previously bullish radar state loses a dominant bullish structure. |

The 10-bar persistence and 12% extension thresholds are public research defaults. They
are not calibrated success probabilities and must later compete in walk-forward tests.

## Independent methods

1. `MA_BASELINE`: point-in-time MA5/10/20/60 direction plus MA120/200/240 context.
2. `DOUBLE_SLOPE`: adjacent 20-day log-price OLS slopes with a standardized difference
   threshold and two consecutive confirmations.
3. `SEVEN_STATE_RADAR`: translates only the MA baseline into the seven human-readable
   states above.

The latest MA and double-slope outputs are displayed side by side. Relationship labels
(`ALIGNED_UP`, `ALIGNED_WEAKENING`, disagreement, mixed, or not comparable) are
descriptions, not scores. Neither method modifies the other.

## Daily report contract

- Seven-state counts for every successfully loaded symbol.
- Today's `BASE->TURNING_UP`, `TURNING_UP->TREND_CONFIRMED`, up-state-to-`EXTENDED`,
  and up-state-to-`WEAKENING` transitions.
- Complete CSV with seven-state, MA, double-slope, long-term context, CB metadata, and
  auxiliary Breakout/Continuous High evidence.
- Deterministic observation order: state bucket, target transition types first, other
  today transitions second, state age ascending, then symbol. No score or magnitude
  encoding. `BASE->TURNING_UP` is therefore first within the early-turn bucket.
- Per-symbol close chart with seven-state and double-slope events on event-day close.
- Separate core MA chart (close with MA5/10/20/60) and long-term context chart
  (close with MA60/120/200/240); MA200 is diagnostic only.
- Breakout Tracker and Continuous High remain visible only as auxiliary evidence and do
  not affect the observation order.
- Backward-compatible output filenames remain `watchlist.html`,
  `watchlist_candidates.csv`, and `watchlist_timeline.csv`.

## Data and CB scope

- Official TWSE listed-company universe and official raw/unadjusted daily prices.
- Current-universe-on-history survivorship bias remains explicit.
- Official TPEx current/recent CB classification is issuer metadata only.
- `NOT_FOUND_CURRENT_OR_RECENT` is not evidence that the issuer never issued a CB.
- Missing CB source data is `UNVERIFIED`.

## Exclusions

- TPEx equity universe and price history.
- Corporate-action-adjusted prices and verified corporate-action events.
- Relative market/industry strength, fundamentals, BOCPD, HMM, optimization, backtest
  performance claims, alerts, scheduling, deployment, or live capital.

All prices remain raw/unadjusted. Corporate actions remain `UNVERIFIED`; investment use
remains `PROHIBITED`.
