# Test Infrastructure and FinMind Live Smoke

- Document ID: `TWSTOCK-TEST-INFRA-LIVE-SMOKE-001`
- Status: Active operational control
- Effective date: `2026-08-10`

## Purpose

The regular CI workflow creates a reproducible Python 3.12 test environment from
`requirements-dev.txt`, runs the complete pytest suite (including unittest-based tests),
compiles Python sources, parses every tracked JSON file, checks changed lines for whitespace
errors, and verifies that the run did not modify tracked files.

The FinMind live smoke is deliberately separate. It is manual only, receives the token from
the `FINMIND_TOKEN` GitHub Actions secret, uses read-only repository permissions, retains no
artifact, and deletes its temporary output when the job exits.

## Secret setup

Create a protected GitHub Environment named `finmind-live-smoke`, restrict it to `main` and
`codex/corporate-action-guard-v0-2`, and create its Environment secret named
`FINMIND_TOKEN`. Never put the token in a workflow input, command argument, source file, PR
comment, issue, artifact, or chat message. The workflow exposes this secret only to the two
shell steps that require it; checkout, Python setup, and dependency installation do not receive
the secret.

## Running the live smoke

1. Merge this infrastructure PR into `main` first so GitHub can discover the manual workflow.
2. Update the Corporate Action Safety Guard v0.2 branch from that new `main`.
3. In **Actions → FinMind Live Smoke → Run workflow**, select the updated guard branch.
4. Run the workflow and require a green result before marking the guard PR ready.

Before Corporate Action Safety Guard v0.2 is present on the selected ref, the live workflow
must fail because the guarded output schema and four-dataset coverage do not yet exist. After
the guard is merged, the same workflow can run directly on `main`.

## Fail-closed acceptance contract

The validator requires all of the following:

- TWSE primary state is `PRIMARY_VERIFIED`;
- FinMind price cross-check is available and has zero reconciliation issues;
- all four required FinMind corporate-action datasets have complete secondary coverage;
- run, market-data, and corporate-action manifests agree on symbol, period, hashes, and counts;
- all guarded output files exist and have safe fixed paths;
- market-bar, event, and two-analyzer guard row counts agree with the manifests;
- no retained output or raw cache contains the configured token, an Authorization Bearer
  header, a token query parameter, a symlink, or an oversized unscanned file.

Any missing field, missing source, mismatch, unsafe path, credential trace, malformed file, or
unexpected schema fails the job. `--allow-secondary-only` is not used.

## Explicit limitations

This live smoke verifies transport, source reconciliation, corporate-action coverage, output
integrity, and credential hygiene for one bounded 13-month `2330.TW` run ending on the prior
UTC day. It is not official TWSE per-event corporate-action verification, performance
validation, backtesting, production
deployment, or investment-use approval.
