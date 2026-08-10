# Breakout Tracker v5 — Event Engine Specification

- Document ID: `TWSTOCK-BREAKOUT-V5-001`
- Version: `0.1.0`
- Status: Active exploratory specification
- Effective date: `2026-08-10`
- Evidence level: Implementation definition only; no performance claim

## 1. Objective

Replace the v4.2 same-day ranking/classification logic with a deterministic, point-in-time-safe event tracker that answers:

- which resistance Pivot was knowable on each date;
- when price first closed above that frozen Pivot;
- how the same breakout cycle changed state on later dates;
- whether a result is new, confirmed, retesting, extended/aged, or failed.

This work package does not select parameters for profit and does not claim that breakouts earn excess returns.

## 2. Input contract

One `PriceBar` contains:

```text
symbol
trade_date
open
high
low
close
volume
```

Bars must be strictly date-ascending, contain one symbol, use finite positive OHLC values, satisfy `low <= open/close <= high`, and have nonnegative volume.

This engine intentionally receives already-normalized bars. Yahoo, TWSE, TPEx, adjusted-price, company-action, calendar, and historical-universe rules belong to later data-adapter work packages.

## 3. Pivot definition

For provisional parameters:

- `pivot_lookback = L`
- `pivot_confirmation_bars = C`

A bar at index `p` becomes a confirmed Pivot only on index `p + C` when:

1. its high is strictly greater than every high in the preceding `L - 1` bars; and
2. none of the following `C` bars trades above that high.

The engine therefore cannot know or emit the Pivot before the confirmation date. Once adopted, the Pivot is frozen for that setup/breakout cycle; later bars cannot rewrite its price or date.

Only one cycle is active per symbol in v0.1. Setup age is zero on the Pivot confirmation date; a setup expires only after `max_setup_bars` later bars have elapsed without a breakout. An expiring cycle must not hide a different Pivot that becomes confirmed on the same date.

## 4. First-breakout event

The first breakout occurs on the first bar after Pivot confirmation whose close is strictly greater than:

```text
pivot_price * (1 + breakout_buffer_pct)
```

Volume ratio is:

```text
current volume / mean(previous volume_lookback bars)
```

The current bar is excluded from the denominator. Volume ratio is recorded as a feature; it gates the event only when `min_breakout_volume_ratio` is explicitly configured.

`breakout_date` is immutable within the cycle. Later qualifying closes cannot create another `NEW_TRIGGER` event.

## 5. Mutually exclusive states

| State | Definition |
|---|---|
| `SETUP` | Confirmed frozen Pivot exists; no first breakout yet |
| `NEW_TRIGGER` | First qualifying close above the Pivot; emitted once |
| `CONFIRMED` | A later bar remains above failure level and is neither retesting nor extended |
| `RETEST` | Low revisits the configured Pivot band while close remains above failure level |
| `EXTENDED` | Close exceeds the extension threshold, or the cycle exceeds its maximum tracking age without failing |
| `FAILED` | Close falls strictly below the configured failure level; terminal for that cycle |

After the first breakout, precedence is:

```text
FAILED
→ RETEST
→ EXTENDED
→ CONFIRMED
```

`NEW_TRIGGER` is handled separately because it can occur only once. State names describe observation, not an instruction to buy, hold, or sell.

## 6. Point-in-time and execution rules

- A snapshot at date `t` may use only bars through `t`.
- Pivot confirmation necessarily waits `C` bars; it is never backdated as known on the Pivot date.
- A close-based signal formed at `t` cannot assume execution at the same close.
- This engine produces research events only and contains no trade simulator.
- Historical replay must later scan the universe that existed on each historical date, not today's survivors.

## 7. Acceptance cases for v0.1

- no Pivot is emitted before confirmation;
- Pivot price/date remain frozen throughout a cycle;
- exactly one first-breakout event is emitted;
- state order respects failure/retest/extension precedence;
- replaying any historical prefix produces the same snapshots as the corresponding prefix of a full replay;
- malformed or mixed-symbol bars fail loudly;
- optional volume gating uses only prior volume.
- setup age starts on the Pivot confirmation date, not the original Pivot date;
- non-integer bar counts and non-finite thresholds fail loudly.

## 8. Explicit exclusions

- Yahoo download or caching;
- TWSE/TPEx reconciliation;
- adjusted-price and corporate-action handling;
- full-market scanning and historical universe;
- parameter optimization, ranking, scoring, and v4 A1/A2 labels;
- return, MFE/MAE, costs, slippage, limit-up, or portfolio backtesting;
- website, Colab UI, scheduler, notifications, or live trading.

## 9. Next work packages

1. Yahoo exploratory price adapter and fixed real-stock diagnostic cases.
2. Historical daily replay and event-outcome table.
3. Parameter sensitivity and walk-forward design.
4. Official-source/TPEx/historical-universe/corporate-action controls.
5. Daily shadow report before any strategy-use claim.
