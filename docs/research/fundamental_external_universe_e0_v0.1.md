# Fundamental Model v0.1 — External-Universe Stage E0

This stage implements the data-and-cohort feasibility gate pre-registered in GitHub Issue #35. It does not test returns and does not change Fundamental Model v0.1.

## Frozen identity

- Research head: `188aa8120a6c35b3b6377490f1ed9456566824bd`
- Model/rules SHA-256: `8c83caa292899b89bc5cf1e56180e867c9fec2999809b19f47f9529d9d3b3a5f`
- Original 0050 universe SHA-256: `aac840ff8018358d5f317b5424f300ff02dc39e5d0e62f075f10a41632079f46`

## E0 boundary

The audit may read only:

1. the frozen model config and 0050 identity inputs;
2. the original normalized financial input and MOPS checkpoint for coverage inventory;
3. four explicitly named external E0 inputs.

It must not read predictive-event, backtest, return, price-outcome, or Stage B result artifacts. It performs no network requests. Outcome-like columns in any external E0 input fail closed.

## Required external inputs

Place reviewed CSV files under `data/research/fundamental_external_universe_e0_v0_1/`.

### `historical_external_membership.csv`

One row per PIT observation-date/security membership decision. Required columns:

`observation_date,symbol,company,index_name,sector_logic,cohort_eligible,is_0050_member,source_url,source_published_at,source_sha256`

The primary cohort is frozen as historical PIT Taiwan Mid-Cap 100, non-financial, and outside 0050. The source must be an official Taiwan Index Plus or FTSE Russell record and support membership as known at the observation date. A current-only constituent list is insufficient.

### `external_security_master.csv`

Required columns:

`symbol,listing_date,delisting_date,security_type,status,source_scope,source_url,source_as_of,source_sha256`

Removed, merged, suspended, and delisted securities must remain visible. Blank `delisting_date` is allowed for active issuers; absence of historical issuers is not.

### `external_mops_pit_coverage.csv`

Required columns:

`symbol,period_end,announcement_timestamp,availability_method,source_identifier,source_url,source_sha256`

This file records availability only. Financial values and model classifications are not generated during the initial readiness pass.

### `external_expected_support.csv`

Required columns:

`horizon,dimension,bucket,expected_observations,expected_unique_issuers,support_status`

It must contain the pre-outcome expected support for every primary State, Quality, and Valuation bucket at 60, 120, 252, and 504 trading-day horizons. Each cell must meet 30 observations and 5 unique issuers. Counts may use membership, filing availability, frozen signal classification, and session coverage; they must not use future returns.

## Current result

The frozen repository contains 50 current 0050 constituents, including 38 eligible non-financial issuers and 12 excluded financial issuers. The normalized financial input and MOPS checkpoint cover only those 50 symbols. No historical external membership, security master/delisting coverage, external MOPS PIT coverage, or expected-support input is present.

Therefore the initial E0 result is `DATA_NOT_READY` and E1 is `BLOCKED`. This is the required fail-closed outcome, not a failed model result.

## Reproduce

```bash
python scripts/audit_fundamental_external_universe_e0_v0_1.py
python -m pytest -q tests/test_fundamental_external_universe_e0.py
```

Re-running the audit after adding the four reviewed inputs may produce `READY_FOR_INDEPENDENT_E0_REVIEW`. It never authorizes E1 directly; an immutable pre-result checkpoint and independent E0 review remain mandatory.
