# Fundamental Model v0.1 — External-Universe Stage E0-B1

This checkpoint attempts only historical PIT Taiwan 50 / Taiwan Mid-Cap 100 membership and security-lifecycle reconstruction. It never reads or computes outcomes and it does not alter the frozen model.

## Official-source discovery completed

- Authority: Taiwan Index Plus Corporation.
- Public archive: `https://taiwanindex.com.tw/downloads/technical_notice`.
- Observation window: 2019-01-01 through 2026-09-03.
- Official membership-related notices discovered: 58.
- Regular-review source candidates: 31, including the 2018 Q4 roll-forward anchor event.
- Interim or extraordinary source candidates: 27.
- The rendered official archive index is preserved under `raw_membership_sources/` with its SHA-256 and a source-discovery manifest.

The linked notice documents were not treated as acquired merely because their official URLs were discovered. Their raw bodies, effective dates, and normalized events remain absent and are explicitly marked `DISCOVERED_NOT_RETRIEVED`.

## Fail-closed result

No public official full-constituent seed snapshot was established. Additions and deletions alone cannot prove a complete historical universe. Therefore:

- `historical_external_membership.csv` is a header-only, non-claiming output under the isolated E0-B1 data root.
- `external_security_master.csv` is a header-only, non-claiming output under that root because no historical cohort symbols are frozen.
- all 31 calendar-quarter intervals are `MEMBERSHIP_INTERVAL_NOT_VERIFIED`;
- Taiwan 50 and Taiwan Mid-Cap 100 PIT reconstruction both fail;
- interval count and overlap reconciliation fail;
- Stage E0-B1 remains `DATA_NOT_READY` and E0-B2 remains blocked.

This does not populate the original E0 formal-input directory, overwrite its artifacts, or reinterpret the original E0 `DATA_NOT_READY` checkpoint. The isolated E0-B1 files append acquisition evidence and narrow the unresolved work.

## Acquisition contract

The dedicated config enables only bounded official acquisition. It restricts hosts, accepted content types, response size, redirects, request count, timeouts, and retry count. Raw bodies must be content-addressed and verified before normalized membership rows may cite them. A non-official source may only be used as a cross-check and cannot establish primary PIT membership.

## Reproduce

```bash
python scripts/reconstruct_fundamental_external_universe_e0_b1_v0_1.py
python -m pytest -q tests/test_fundamental_external_universe_e0_b1.py
```

The only allowed continuation is further E0-B1 official evidence acquisition: obtain a trustworthy full seed, preserve and normalize all membership-changing notices, reconcile every interval, and then build the historical security master. Do not start E0-B2 or E1.
