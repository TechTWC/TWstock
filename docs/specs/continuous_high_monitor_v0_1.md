# Continuous High Monitor v0.1 — Event, Timeline, and Chart Specification

- Document ID: `TWSTOCK-CONTINUOUS-HIGH-001`
- Version: `0.1.0`
- Status: Active exploratory specification
- Effective date: `2026-08-10`
- Evidence level: Implementation definition only; no performance claim

## 1. Objective

Detect a stock that is accumulating price strength even when it rises without forming a
traditional Pivot. The monitor records when the stock first becomes observable, how its
stage changes, which rolling closing highs it makes, and which independent risk flags are
active. It complements, rather than replaces, Breakout Tracker v5.

This work package answers an implementation question. It does not claim that any stage,
event, parameter, or chart earns excess return.

## 2. Point-in-time rules

For a closing-price window `N`, the prior high on date `t` is:

```text
prior_high_N(t) = max(close[t-N], ..., close[t-1])
```

The current close is never included in its own comparison window. A new high occurs only
when `close[t] > prior_high_N(t)`. All moving averages and volume averages likewise use
only the observations explicitly defined by the feature. Historical replay must produce
the same prefix through date `t` whether it is run alone or as part of a longer history.

## 3. Parameters

All thresholds live in one validated `MonitorConfig` and a versioned JSON file. The engine
rejects unknown keys, booleans supplied as numbers, non-finite values, duplicate or
unsorted windows, inconsistent window references, and invalid percentage ranges.

The canonical serialized parameter payload has a SHA-256 hash. Reports and experiment
manifests display both `parameter_version` and the hash so changed rules cannot silently
overwrite earlier results.

Initial values are research defaults only. They are not optimized or validated.

## 4. Features

The engine calculates, when sufficient prior observations exist:

- prior closing high and new-high status for each configured window;
- percentage distance from the configured near-high window;
- count of base-window new highs in the recent count window;
- current volume divided by the preceding volume average;
- close divided by the current moving average minus one;
- drawdown from the rolling weakening-window closing high;
- daily trading value approximation (`close * volume`).

## 5. Stages

Stages are mutually exclusive observations:

| Stage | v0.1 definition |
|---|---|
| `WATCH` | Within the configured distance of the prior near-high-window close |
| `EMERGING` | New base-window closing high |
| `STRENGTHENING` | New strengthening-window high or enough recent base-window highs |
| `LEADER` | New leader-window closing high |
| `COOLING` | Previously discovered, but no current strength condition remains |
| `WEAKENING` | A previously discovered stock reaches the weakening drawdown threshold |

Precedence is `WEAKENING → LEADER → STRENGTHENING → EMERGING → WATCH → COOLING`.
`LEADER` means long-window price leadership within this single-symbol experiment. It is
not yet a cross-sectional market-leader rank; market and industry relative strength are
explicitly deferred until benchmark and historical-universe data are added.

To avoid one-day stage flicker, `EMERGING`, `STRENGTHENING`, and `LEADER` persist while the
stock remains inside the near-high band. A higher stage can still be reached immediately;
leaving the band moves the stock to `COOLING`, and the weakening threshold has first
precedence. Parameter changes can alter these transitions and therefore require a new
parameter version/hash.

## 6. Risk flags

Risk flags are independent of stage:

- `VOLUME_SURGE`: volume ratio reaches its threshold;
- `ACCELERATING`: enough base-window highs occurred in the short acceleration window;
- `EXTENDED`: close is sufficiently above its moving average;
- `PULLBACK`: drawdown reaches the pullback threshold;
- `LOW_LIQUIDITY`: estimated daily trading value is below the configured minimum.

A stock can therefore be `LEADER + ACCELERATING + EXTENDED`. Strength is not treated as
an instruction to buy.

## 7. Timeline and identity

The result stores:

- one objective feature row for every input date, including dates that never enter the
  radar, so later research retains negative/control observations;
- immutable first discovery date and close;
- one snapshot per date after discovery;
- deterministic `DISCOVERED`, `STAGE_CHANGED`, `NEW_HIGH`, `RISK_ADDED`, and
  `RISK_CLEARED` events;
- a stable event ID derived from symbol, date, event type, and detail.

Rerunning the same data and parameters must reproduce the same events and IDs. A consumer
can therefore persist event IDs and suppress duplicate notifications.

## 8. Chart and outputs

The standard-library-only report writes:

- a standalone HTML document with inline SVG;
- a structured feature CSV with parameter provenance and one column per high window;
- daily close and moving-average lines;
- stage-change markers and each new-high tier's first chart marker, preserving the first
  discovery marker while the CSV retains every daily new-high event;
- optional Breakout Tracker v5 `NEW_TRIGGER` markers;
- daily volume and prior-volume-average panel;
- moving-average-extension panel;
- event timeline table and parameter provenance.

Event calculations always use daily data. Visual downsampling is not implemented in v0.1;
if added later, it must preserve every event date.

## 9. Acceptance cases

- A monotonic rise without a Pivot is discovered through rolling highs.
- A high on date `t` compares only with dates before `t`.
- First discovery date and close do not change when future bars are appended.
- Full replay and every daily prefix produce identical historical snapshots and events.
- The same run produces stable, unique event IDs.
- Simultaneous 20/60/120/250-day highs are all retained.
- Stage changes and risk additions/removals are explicit.
- Invalid bars, ordering, mixed symbols, and invalid parameters fail loudly.
- The HTML report escapes symbols/text and contains the chart, first discovery, timeline,
  parameter version, and parameter hash.

## 10. Explicit exclusions

v0.1 does not add Yahoo/TWSE/TPEx ingestion, adjusted-price or corporate-action handling,
market/industry relative-strength ranks, full-market scans, a database, notification
delivery, parameter optimization, performance backtesting, portfolio simulation,
machine learning, deployment, or an investment recommendation.

The feature CSV deliberately excludes future-return labels. Those may be joined only in a
separate offline research dataset so no future outcome can enter the daily monitor.
Unavailable rolling-window fields are blank rather than `0`, preserving the difference
between insufficient history and a valid non-high observation.
