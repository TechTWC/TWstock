# 0050 Fundamental Model v0.1 — OOS Shadow Validation

## Stage OOS-A: Frozen Contract and Immutable Ledger Foundation

Historical validation is not out-of-sample validation. The historical Stage B evidence was
produced from already-observed 2018–2026 data and remains **MODERATE**, with the label
`EXPLORATORY_PREDICTIVE_ASSOCIATION`. It is not a live OOS result and is not an investment
recommendation.

OOS v0.1 starts at the immutable boundary `2026-09-11T00:00:00+08:00`. A filing, source
observation, or signal with an information timestamp before this boundary is
`PRE_OOS_EXCLUDED` and can never enter the formal signal ledger. Missing historical data may
be retained for audit, but it cannot be backfilled into the OOS performance sample.

Stage OOS-A creates infrastructure only. It does not collect live MOPS, FinMind, Yahoo, price,
or session data; schedule a workflow; calculate future returns; or make an OOS performance
claim. The tracked signal and outcome ledgers therefore both start with zero records.

## Frozen identity

- Freeze head: `188aa8120a6c35b3b6377490f1ed9456566824bd`
- Model hash: `8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f`
- Universe hash: `aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46`
- Cohort: 50 current-0050 constituents frozen at the research baseline
- Predictive eligible: 38 non-financial issuers
- Excluded: 12 financial issuers
- Horizons: 60, 120, 252, and 504 trading days
- Benchmark: 0050

Quality, Fundamental State, State Detail, and Valuation remain frozen. OOS v0.1 cannot change
their rules, thresholds, taxonomy, benchmark, horizons, support gate, or universe, and cannot
introduce a composite score. Any later model change requires v0.2 and a new prospective OOS
start date; v0.2 observations must not contaminate v0.1.

Constituent changes after the freeze may be audited as `UNIVERSE_CHANGE_NOT_APPLIED`, but are
not applied to the v0.1 sample.

## Conservative information availability

A formal signal is generated only when all necessary frozen-model inputs are genuinely
available. The information cutoff is the maximum of:

1. MOPS announcement and retrieval availability;
2. financial numeric data retrieval availability;
3. valuation data retrieval availability; and
4. actual signal generation availability.

A MOPS announcement alone is insufficient. If normalized financial values are not reliably
available, the observation is `PENDING_DATA` and no predictive signal is written. Data obtained
later is never assigned retroactively to the earlier announcement timestamp.

`first_trade_date` is the first date strictly after the cutoff that is simultaneously a legal
frozen TWSE session and an accepted stock/0050 benchmark session. Weekend, holiday, missing
stock-price, and missing benchmark-price dates fail closed.

## Immutable ledgers

The signal ledger and outcome ledger are separate JSONL files. Each uses continuous sequence
numbers and a SHA-256 chain. `previous_record_hash` is `GENESIS` for the first record and the
prior canonical `record_hash` thereafter. The record hash covers all record content except the
self-referential `record_hash` field.

Writing uses append mode. Existing records are never rewritten. A correction appends a
`SUPERSEDING_EVENT` with `supersedes_event_id`; the original signal remains permanently in the
ledger. Chain verification detects modification, removal, insertion, duplication, or reordering.

Each signal has independent 60/120/252/504-day maturity. A `PENDING` outcome has null return
fields. A `MATURED` record may be appended only once the exact number of accepted common
trading sessions has elapsed. `UNAVAILABLE` is also allowed only after maturity and never
contains invented return values.

Future source material belongs under:

`artifacts/0050_fundamental_oos_v0_1/raw/<event_id>/`

MOPS metadata/raw response, financial numbers, valuation data, and market/session data each
retain retrieval time, source URL or identifier, SHA-256, and artifact path. Stage OOS-A tracks
only schemas and a synthetic fixture, not live snapshots.

## Bounded validation CLI

```bash
python scripts/run_0050_fundamental_oos_v0_1.py \
  --validate-freeze --validate-ledger --dry-run --fixture
```

The command performs no network requests and writes no signal. `--live` always fails closed
with `LIVE_COLLECTION_NOT_ENABLED_IN_OOS_A`. Enabling collection, source persistence, or a
scheduler belongs to a separately authorized Stage OOS-B.
