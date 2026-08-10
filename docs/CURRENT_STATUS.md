# TWStock Current Status

- Document ID: `TWSTOCK-CURRENT-STATUS-001`
- Version: `1.1.0`
- Status: Active
- Effective date: `2026-08-10`
- Scope: Repository status, document applicability, and current development flow

## 1. Current direction

TWStock is a personal Taiwan-equity research repository. It currently contains reusable market-data adapters, an isolated Phase A1 sandbox, and research governance references. It is not a production trading system and has no validated strategy or live-capital approval.

The current bounded development priorities are `Breakout Tracker v5` and its independent
early-strength companion, `Continuous High Monitor v0.1`:

1. freeze a point-in-time-safe breakout definition;
2. implement Pivot, first-breakout event, and cross-day state tracking with synthetic data;
3. connect the existing TWSE primary adapter and optional FinMind cross-check through a
   fail-closed canonical research-dataset contract;
4. block raw-price analysis windows that cross a known corporate action;
5. replay historical dates using only information available at each date;
6. test parameters, robustness, and walk-forward behavior;
7. add official-market verification and historical-universe controls;
8. run daily shadow observation before any investment-use claim.

`Breakout Tracker v5` detects a close above a confirmed frozen resistance Pivot.
`Continuous High Monitor v0.1` detects rolling closing highs and preserves the first
discovery timeline even when a stock rises without forming a Pivot. Its first bounded
package contains only a parameterized synthetic-data event engine, deterministic timeline,
and standalone HTML/SVG chart. Real data, cross-sectional relative strength, performance
validation, notification delivery, and machine learning remain later work packages.

`Real Market Data Ingestion v0.1` now provides a bounded TWSE-listed-stock path into both
engines. It preserves raw responses, official traded value, reconciliation state, and
content hashes and rejects source mismatch. `Corporate Action Safety Guard v0.2` adds a
secondary-only, four-dataset FinMind event contract and prevents either engine from using
a lookback window across a known action. It does not adjust prices, returns, or holdings,
and it is not official TWSE event verification. Fixture-backed implementation is not a
live-network or strategy-validation claim.

## 2. Effective document rules

When documents conflict, use all of the following, in order:

1. an explicitly `Active` document beats a `Legacy`, `Superseded`, or `Deferred` document;
2. a narrower document beats a general document within the same status;
3. the latest effective version beats an older version within the same scope and status;
4. code and tests must match the effective scoped specification;
5. conflicts must be recorded and must not be resolved by choosing the best-looking result.

Chat history is not a repository source of truth.

## 3. Document applicability

| Document or area | Current status | Required use |
|---|---|---|
| `README.md` | Active overview | Repository entry point |
| `docs/CURRENT_STATUS.md` | Active | Current priority and document applicability |
| `docs/vision/RESEARCH_PRINCIPLES.md` | Active baseline | Research-integrity minimums |
| `docs/data/POINT_IN_TIME_POLICY.md` | Active baseline | PIT and availability rules |
| `docs/vision/SYSTEM_VISION.md` | Legacy baseline | Historical vision only; current operating model/build order are superseded |
| `docs/research/STRATEGY_LIFECYCLE.md` | Deferred formal reference | Apply fully only when entering confirmatory validation |
| `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md` | Deferred formal reference | Do not hand-fill during early exploration |
| `docs/research/DECISION_SNAPSHOT_SCHEMA.md` | Deferred formal reference | Use when formal promotion/retirement decisions begin |
| `docs/research/VALIDATION_PROTOCOL.md` | Deferred formal reference | Formal validation checklist, not an early prototype gate |
| Phase A1 plans/spec/config/engine | Legacy isolated experiment | Do not reuse as general Breakout v5 requirements |
| `docs/specs/continuous_high_monitor_v0_1.md` | Active exploratory specification | Continuous-high event, timeline, parameter, and chart contract |
| `docs/specs/real_market_data_ingestion_v0_1.md` | Active bounded specification | Canonical TWSE/FinMind research dataset and runner contract |
| `docs/specs/corporate_action_guard_v0_2.md` | Active bounded specification | Corporate-action provenance, segmentation, and analysis-blocking contract |

## 4. Lightweight exploratory governance

Each bounded exploratory work package needs only:

- a short scoped specification;
- explicit exclusions and acceptance cases;
- deterministic tests where practical;
- a lightweight experiment manifest containing `experiment_id`, `experiment_type`, `git_sha`, data reference/hash, config, period, universe, metrics, output path, status, and notes;
- preservation of failures and material rule changes.

The full Strategy Lifecycle, Experiment Registry, Decision Snapshot, and Validation Protocol become mandatory only before confirmatory performance claims, OOS promotion, paper trading, or live observation decisions.

## 5. Non-negotiable research controls

The governance refresh does not relax:

- Point-in-Time availability and no look-ahead;
- signal date versus earliest tradable date separation;
- historical-universe and survivorship-bias controls;
- raw versus adjusted price and corporate-action separation;
- data, config, code, and result versioning;
- failed/negative result preservation;
- transaction cost, liquidity, suspension, and limit-up feasibility;
- validation/OOS separation and clean walk-forward evidence before formal claims.

## 6. Known repository limitations

- TPEx and a complete historical Taiwan-market universe are not implemented.
- Corporate-action blocking is implemented with secondary-only source coverage; official
  TWSE cross-checking, adjusted prices, returns, and holding adjustments remain incomplete.
- The full governance schemas are documents, not implemented registry/decision systems.
- Yahoo-derived research, if added later, remains exploratory and separate from the
  official TWSE dataset contract.
- The existing Phase A1 settings and actions are not generic strategy infrastructure.
- A clean development dependency manifest is not yet present; do not assume `pytest` is installed.
