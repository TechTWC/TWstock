# Watchlist Scanner v0.3 — Standalone Visual Report

## Purpose

Make one official-TWSE watchlist scan visually inspectable without changing
candidate ranking, Breakout Tracker v5, Continuous High Monitor, or the v0.2
incremental-cache contract.

This remains **Shadow Observation only**. Every visual report must show
`corporate_action_status=UNVERIFIED` and `investment_use=PROHIBITED`.

## Visual report contract

- `watchlist.html` is standalone UTF-8 HTML with inline SVG and no external
  script, stylesheet, font, CDN, or network dependency.
- The ranking visualization is ordinal only. Equal row geometry must not imply
  expected return, probability, strength magnitude, or an investment score.
- Every successfully loaded symbol receives one price-volume chart using the
  exact engine results created during that scan.
- The symbol chart marks Continuous High rolling-high and stage events and
  Breakout Tracker v5 Pivot-breakout events with distinct shapes and labels.
- The graphical cross-symbol timeline uses a shared date axis and distinct
  shapes for both engines. HTML may show the latest 1,000 events for legibility;
  `watchlist_timeline.csv` remains the complete event record.
- Every SVG has an accessible title, description, or `aria-label`; event marks
  expose their date and state in a native SVG title.
- The existing candidates table, event table, evidence datasets, manifest, and
  full CSV outputs remain present.

## Data and identity controls

- Charts use the same `ResearchMarketDataset`, Breakout snapshots, Continuous
  High result, and parameter identity used for candidate construction.
- Chart rendering validates bar identity, trading value, monitor parameter
  version/hash, and symbol identity before producing SVG.
- The deterministic `scan_id` remains based on request, dataset hashes, and
  engine parameter hashes. Presentation does not alter scan identity or rank.
- Prices remain raw official TWSE daily prices and are not adjusted for
  dividends, splits, ex-rights, or other corporate actions.

## Acceptance cases

- Two loaded symbols produce two price-volume SVGs and one shared ranking SVG.
- The report contains both Breakout and Continuous High event encodings.
- Unavailable symbols remain visible in the ordinal overview and receive no
  fabricated chart. A loaded but unranked symbol may receive its exact-data
  chart.
- HTML contains no executable script and opens without network access.
- Manifest records ordinal rank encoding, complete-event CSV location, raw
  price basis, `UNVERIFIED`, and `PROHIBITED`.

## CLI

```bash
python scripts/run_watchlist_scanner.py \
  --watchlist config/watchlist_v0_1.json \
  --start 2025-01-01 \
  --end 2026-08-14 \
  --output-dir outputs/watchlist_v0_3 \
  --raw-cache-dir outputs/raw_watchlist_v0_3 \
  --retries 2
```

Reuse the persistent raw-cache directory for later runs. Do not commit live
cache or generated observation reports.

## Exclusions

- No interactive trading control, price forecast, expected-return score,
  backtest, parameter optimization, notification, scheduler, database, or
  deployment.
- No corporate-action verification and no modification of PR #25.
- No claim that visual inspection validates either strategy.
