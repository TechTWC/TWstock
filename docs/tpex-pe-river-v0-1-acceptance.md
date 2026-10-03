# Stage A6 acceptance record — Generic TPEx PE River v0.1

Acceptance date: 2026-10-03.  The supported production universe is **TPEx
officially classified listed ordinary common shares**.  ETFs, ETNs, bonds,
warrants, preferred shares, convertible bonds, TDRs, emerging stocks,
structured products, and other non-equity instruments are excluded and fail
closed.

## Hosted acceptance

- Five-symbol TPEx/TPEX/MAX production run: GitHub Actions run
  `37112006186`, success.
- Routing controls: `6488/AUTO/MAX`, `8103/TWSE/MAX`, and expected rejection
  of `6488/TWSE/MAX` are recorded by run `37112553618`.
- Permanent CI on the implementation commits passed.  The temporary
  feature-branch push workflow is removed from the final tree.
- PDF render QA covered 6488, 8069, 3290, and 7856: title, canonical symbol,
  market, axes, close, river gaps, action markers, summary panel, and page
  bounds were visually checked.  No clipping, overlap, corruption, or fake
  zero-valued PE was found.

## Current TPEx universe probe

The probe used the official TPEx company master, latest-close OpenAPI feed,
and latest-PE OpenAPI feed.  Full-market snapshots were restricted by positive
company-master membership so ETFs, warrants, bonds, and other instruments in
the same feed could not enter the ordinary-share universe.

| Result | Count |
|---|---:|
| Official ordinary-share identities | 892 |
| Identity PASS | 892 |
| Latest close PASS | 868 |
| Latest close legitimately unavailable | 24 |
| Latest PE PASS | 672 |
| Latest PE legitimately unavailable | 220 |
| Unexpected failures | 0 |

## Cross-symbol MAX results

All five symbols used the same identity router, TPEx valuation adapter,
corporate-action adapter, MOPS face-value proof, shared normalization engine,
and PDF/CSV/JSON writer.  No production symbol special case exists.

| Symbol | Company | Actual/source start | Observations | Valid / unavailable PE | Latest close / PE | Actions | Normalization | Face-value proof |
|---|---|---:|---:|---:|---:|---:|---|---|
| 6488.TWO | 環球晶圓股份有限公司 | 2015-09-25 | 2,685 | 2,685 / 0 | 1,190.00 / 57.77 | 0 | NORMALIZED | PROVEN, 17/17 details |
| 8069.TWO | 元太科技工業股份有限公司 | 2012-09-03 | 3,442 | 2,997 / 445 | 143.50 / 13.96 | 0 | NORMALIZED_PERCENTILE_INCOMPLETE (pre-2013 source boundary) | PROVEN, 4/4 details |
| 3290.TWO | 東浦精密光電股份有限公司 | 2012-09-03 | 3,434 | 2,928 / 506 | 50.30 / 8.50 | 3 | NORMALIZED_PERCENTILE_INCOMPLETE (review-required rights/cash reduction) | PROVEN, 14/14 details |
| 6548.TWO | 長華科技股份有限公司 | 2016-09-13 | 2,433 | 2,433 / 0 | 76.70 / 34.55 | 9 | NORMALIZED_PERCENTILE_INCOMPLETE (review-required official announcements) | REVIEW_REQUIRED, 21/21 details |
| 7856.TWO | 漢民測試系統股份有限公司 | 2026-09-22 | 7 | 7 / 0 | 4,195.00 / 155.49 | 0 | NORMALIZED | PROVEN, verified zero rows/details |

All coverage ends on the latest completed session, 2026-10-02.  A differing
start per company is expected: `MAX` begins at that symbol's first positive,
officially provable PE observation, not a listing-date or symbol constant.

## 6488 primary artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `6488_pe_river.pdf` | 91,866 | `2b5db23e2ac3584bb46a1f787719d9b78f5b7a52f79b58453e5e6968b75d834a` |
| `historical_pe_river.csv` | 1,556,620 | `80e109d73cccf61107042989ff26c34ef0f01e20a7a3d835135bfc9374d4492a` |
| `report_metadata.json` | 177,019 | `1f87df81f35f7f5ac799b20b753173224fc9cdad971611d2ac52e76f9a13840f` |

6488 metadata records `6488.TWO`, TPEX, the official identity source/as-of
date, requested and actual coverage, 2,685 observations, latest official and
normalized PE 57.77, raw and normalized percentile 90.8379888268, complete
normalization, zero corporate-action events, and exhaustive MOPS row/detail
hash proof.

## Validation and remaining gap

Deterministic multi-symbol TPEx fixtures, identity/routing, valuation,
corporate actions, shared normalization, face-value proof, cache tampering,
PDF, workflow contract, and TWSE regression tests pass.  The preserved TWSE
controls include 6669 (`6.70 -> 19.98476` with factor `2.9828`), 2603
(`80.80 / 0.4 = 202.00`, `2.45 * 0.4 = 0.98`), and the existing 6949/2327
face-value behavior.  Full local pytest, compileall, JSON parsing, and
`git diff --check` pass.

The only deferred independent stage is historical financial-reference-period
backfill.  Stage A6 does not infer or reconstruct missing pre-source quarters.
