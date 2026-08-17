# Double-Slope Turning Comparison v0.1

## Research status

This is a transparent, paper-inspired baseline, not an exact reproduction of
Bramante, Facchinetti, and Zappa (2019). The publicly accessible abstract
confirms hypothesis testing on the difference between two consecutive slopes
in rolling regressions, but the complete paywalled methodology and calibrated
parameters were not available to this implementation.

Source: <https://onlinelibrary.wiley.com/doi/10.1002/sam.11411>

## Point-in-time detector

For every trading date with at least 40 bars:

1. transform closes to natural logarithms;
2. fit OLS price-on-time slopes to two adjacent, non-overlapping 20-bar windows;
3. convert each log slope to an approximate daily percentage slope;
4. compute the recent-minus-prior slope difference;
5. divide the log-slope difference by the square root of the two OLS slope
   standard errors squared;
6. treat |z| >= 1.96 as the uncalibrated, approximate 95% research threshold;
7. require the directional condition on two consecutive observation dates.

An upward turn requires the prior daily slope to be no more than +0.05%, the
recent slope to exceed +0.05%, and z >= 1.96. A downward turn is symmetric.

The normal approximation is diagnostic only. Price observations are serially
dependent, the segment estimates are not guaranteed independent, and the
threshold has not been calibrated for Taiwan equities.

## Fair comparison with the MA baseline

The existing MA v0.2 core state is rerun from the same immutable bars and
configuration. MA120, MA200, and MA240 remain background diagnostics and do not
affect the MA `TURNING_UP` date.

For each symbol, double-slope and MA upward events within plus or minus 20
trading bars are paired one-to-one by closest distance. The reported lead is:

`MA event index - double-slope event index`

A positive value means double-slope detected earlier. Matching is a descriptive
comparison, not proof that the paired events represent one true economic turn.

## False-alarm outcome contract

Only events with 20 complete future trading bars are evaluated. Later events
are `PENDING` and excluded from rates.

Three outcomes are retained separately:

- `NO_FOLLOW_THROUGH_20D`: maximum closing-price gain in the following 20 bars
  is less than 5%; this is the primary provisional false-alarm proxy;
- `NEGATIVE_AT_20D`: close-to-close return at bar 20 is zero or negative;
- `DOWNSIDE_FIRST`: a closing-price loss of 5% occurs before a gain of 5%.

The 20-bar and 5% values are transparent exploratory defaults, not optimized
or approved thresholds. Reporting all three avoids hiding the result inside a
single score.

## Controls and exclusions

- every detection uses information dated no later than the event date;
- forward prices are used only by the separate retrospective evaluator;
- no score, rank, recommendation, order, optimization, or performance claim;
- no volume, relative strength, Breakout, Continuous High, BOCPD, or HMM;
- raw official TWSE prices, company actions `UNVERIFIED`, investment use
  `PROHIBITED`.
