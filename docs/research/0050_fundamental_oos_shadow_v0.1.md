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

The command performs no network requests and writes no signal.

## Stage OOS-B: Live Collection Contract

OOS-B enables collection only when a human explicitly supplies `--live`. Normal CLI use,
tests, and CI remain offline; there is no cron, scheduled GitHub Action, external service, or
production deployment. Historical backfill and outcome calculation are disabled.

An **OOS signal** is the first immutable classification produced after the OOS boundary when
the official MOPS filing, the required frozen-model FinMind financial inputs, a permitted
FinMind/TWSE valuation snapshot, and an accepted common TWSE/stock/0050 session contract are
all genuinely available. A MOPS row by itself is only a candidate. `PENDING_FINANCIAL_DATA`,
`PENDING_VALUATION_DATA`, and `PENDING_SESSION` mean that one of these required inputs is not
yet observable; they are not signals and carry no investment conclusion.

The candidate registry is mutable so a later manual run can recheck missing sources. Its
identity is deterministic from the filing identity, frozen model hash, and frozen universe
hash. Financial issuers are retained only as `FINANCIAL_EXCLUDED` audit candidates and cannot
enter the predictive ledger. Any filing announced before `2026-09-11T00:00:00+08:00` is
`PRE_OOS_EXCLUDED`, even when retrieved after that time.

The **first-complete-data lock** captures the first financial and valuation snapshots and the
actual generation time as soon as the frozen model becomes executable. Later valuation or
price refreshes cannot create another ordinary `ACTIVE_SIGNAL` or move its information cutoff.
The cutoff is the maximum of announcement, MOPS retrieval, financial retrieval, valuation
retrieval, and actual signal generation timestamps. Backdating it to the filing announcement
would falsely claim knowledge that the collector did not yet possess.

Signal writes validate the frozen identity, existing SHA-256 chain, deterministic event ID,
sequence, source hashes, and first common legal session before an atomic replace. Existing
records are never rewritten. A genuine filing/source/data correction appends a distinct
`SUPERSEDING_EVENT` that points to the earlier event; the original remains in the chain.
Each source retrieval is stored in a content-addressed directory with raw bytes, normalized
data when applicable, a manifest, retrieval time, source identifier, and reproducible SHA-256.
Existing snapshots are never overwritten.

Manual collection is invoked with:

```bash
python scripts/run_0050_fundamental_oos_v0_1.py --live \
  --validate-freeze --validate-ledger --validate-snapshots
```

OOS-B makes no OOS performance claim. All 60/120/252/504-session outcomes remain immature,
their return fields remain null, and outcome calculation stays disabled. Scheduled collection
requires a separately authorized OOS-C stage.

## Stage OOS-C: Incremental Scheduled-Collection Architecture

OOS-C keeps one collection engine for explicit `--live` execution and `--scheduled-run`.
Every run verifies the frozen Fundamental head, model hash, universe hash, OOS start,
signal-ledger chain, outcome ledger, pending-candidate registry, and the machine-readable
collector code-freeze identity before scanning. Historical backfill and 60/120/252/504-session
outcome calculation remain disabled.

New source responses use a SHA-256 content-addressed store under
`artifacts/0050_fundamental_oos_v0_1/source_blobs/`. A body already present there—or in the
preserved OOS-B immutable snapshot tree—is `UNCHANGED_SOURCE` and is referenced rather than
stored again. A genuinely changed body creates one new immutable `<sha256>.bin`. Each scan
also emits at most one compact manifest under `artifacts/0050_fundamental_oos_v0_1/runs/`,
recording symbols, retrieval times, source hashes, prior references, candidate states, and
formal-signal results. A no-op scan therefore cannot reproduce dozens of historical archives.

Scheduled execution starts from a clean checkout and may modify only the signal ledger,
outcome ledger (which must remain unchanged while outcome calculation is disabled), pending
registry, content-addressed blobs, and bounded run manifests. Any code, configuration,
workflow, frozen-model, frozen-universe, or other non-allowlisted diff is
`NON_ALLOWLISTED_SCHEDULED_DIFF` and fails closed. Collector source drift is
`COLLECTOR_CODE_DRIFT` and also fails closed. Pushes must be ordinary fast-forward pushes to
`research/0050-fundamental-oos-shadow-v0-1`; force-push and writes to `main` are prohibited.

The scheduler bridge is intentionally a separate Draft PR targeting `main`, because GitHub
scheduled workflows run only when their workflow file exists on the default branch. It is
prepared for one run daily at 22:30 `Asia/Taipei`, retains `workflow_dispatch`, uses
`cancel-in-progress: false`, and grants only `contents: write`. Until that separate PR is
reviewed and merged, the exact status is **PREPARED_NOT_ACTIVE**:

- `scheduled_collection_prepared = true`
- `scheduled_collection_active = false`

Local fixture-backed dry simulation does not activate the GitHub schedule. A scheduled run
that encounters a source error, hash/freeze mismatch, ledger corruption, concurrent write,
non-allowlisted change, or push race fails without guessing, backdating, overwriting a ledger,
or force-pushing.
