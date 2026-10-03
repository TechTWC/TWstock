# Moving-Average Trend-State Baseline v0.2

## Decision

Keep early direction detection and long-term background as separate outputs.
MA120, MA200, and MA240 must not become mandatory conditions for a core
`TURNING_UP` or `UPTREND` state.

This preserves the research objective: detect a stock near the beginning of a
move instead of waiting for every slow average to confirm after a large rise.

## Core state layer

The six mutually exclusive core states remain unchanged from v0.1 and use only
close, MA5, MA10, MA20, and MA60:

- `UNCLEAR`
- `BASE`
- `TURNING_UP`
- `UPTREND`
- `TURNING_DOWN`
- `DOWNTREND`

The new long averages therefore cannot delay or veto a core-state transition.

## Long-term background layer

Each point-in-time observation also receives exactly one background label:

- `INSUFFICIENT_HISTORY`: fewer than 245 bars are available;
- `LONG_TERM_BULL`: close > MA120 > MA240, MA120 rises by more than the
  declared flat tolerance, and MA240 rises;
- `LONG_TERM_BEAR`: the symmetric bearish structure;
- `LONG_TERM_BOTTOMING`: MA120 rises while MA240 is approximately flat;
- `LONG_TERM_REPAIR`: price is above MA120 without full long-term bullish
  confirmation;
- `LONG_TERM_BEAR_RALLY`: a core up-state remains below falling MA120 and
  MA240;
- `LONG_TERM_MIXED`: no preceding long-term rule dominates.

The default long-term flat tolerance is 0.2% over five trading days. It is an
unoptimized research default, not an approved investment threshold.

## MA200 versus MA240

MA240 is the primary annual reference because Taiwan equities have roughly 240
trading sessions per year. MA200 is retained only as a comparison diagnostic
for the widely used international convention. The report explicitly flags a
disagreement when MA200 and MA240 give different price-position or slope signs.

Neither average creates a score, rank, recommendation, or hard filter.

## Output changes

The latest-state CSV now includes MA120, MA200, MA240, their five-session
normalized slopes, price distances, the long-term context, and its supporting
and contrary evidence.

The standalone HTML adds:

- a long-term context glossary;
- a separate current-background table;
- a second chart for close and MA60/120/200/240;
- explicit explanations of MA200/MA240 disagreements.

The core-state transition timeline remains unchanged so v0.1 noise can be
compared directly. All data remains raw official TWSE evidence with company
actions `UNVERIFIED` and investment use `PROHIBITED`.
