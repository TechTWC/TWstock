# PE River Corporate Action Normalization v0.1 — Source Contract

This bounded module normalizes share-count changes for the historical PE river.
It is not a general corporate-action platform. The official TWSE adapters,
canonical event model, reference-period parser and normalization engine feed
the production PE-river CLI, PDF, CSV and metadata outputs. Long-history live
acceptance remains symbol-specific evidence rather than a market-wide claim.

## Official source contracts

### Stock dividend / bonus issue

- Summary: `https://www.twse.com.tw/rwd/zh/exRight/TWT49U`
- Detail: `https://www.twse.com.tw/rwd/zh/exRight/TWT49UDetail`
- Parameters: inclusive `startDate` / `endDate`; detail `STK_NO` / `T1`.
- TWSE states that the historical calculation table is available from
  2003-05-05.
- Required summary fields: effective date, symbol, pre-event close, official
  reference price, rights indicator and detail identity.
- Required detail fields: pro-rata bonus shares per thousand, employee bonus
  capitalization, cash issue shares and pro-rata cash-rights shares.
- `bonus_share_rate = bonus_shares_per_thousand / 1000`.
- `share_factor = 1 + bonus_share_rate`.

Cash-dividend-only rows are not share-changing events. Any employee bonus
capitalization or paid cash-rights component is retained as
`CORPORATE_ACTION_REVIEW_REQUIRED`; v0.1 does not guess a complete post/pre
share ratio.

`TWT48U` is the official forecast table and uses the same rate semantics, but
it is not the historical evidence source used by the adapter.

### Ordinary-share capital reduction

- Summary: `https://www.twse.com.tw/rwd/zh/reducation/TWTAUU`
- Detail: `https://www.twse.com.tw/rwd/zh/reducation/TWTAVUDetail`
- `reducation` is the current official route spelling.
- Parameters: inclusive `startDate` / `endDate`; detail `STK_NO` / `FILE_DATE`.
- TWSE states that the table is available from 2011-01-01.
- Required summary fields: resume date, symbol, pre-suspension close, official
  resume reference price, reduction reason and detail identity.
- Required detail fields: new shares per 1,000 old shares, cash returned per
  share and any accompanying paid cash issue.
- `share_factor = new_shares_per_thousand / 1000`.

`退還股款` maps to `CAPITAL_REDUCTION_CASH_RETURN`; `彌補虧損` maps to
`CAPITAL_REDUCTION_LOSS`. A paid issue or unknown reduction reason is review
required. The ratio is an explicit official shares-per-thousand field, so the
event is not tagged as price-derived.

## Evidence and integrity

Each event retains both official URLs, retrieval timestamp, a SHA-256 over the
paired summary/detail raw bodies, the official price fields and the source
fields used for the factor. Symbol/detail identity, date, row width, numeric
format and positive finite factor are validated. Conflicting same-date events
are marked review required. Unsupported or ambiguous events never enter the
normalization product.

Annual action summaries and immutable detail responses use the repository's
SHA-256-verified raw cache contract. Completed years are reused; the current
year is refreshed. A partial or hash-mismatched cache entry fails closed.

## Reference financial period

BWIBBU's optional `財報年/季` value is preserved verbatim. For example,
`115/2` maps to `2026-Q2`, whose `reference_period_end` is 2026-06-30. A
missing historical value remains unavailable; no announcement date or inferred
quarter is substituted.

## Normalization semantics

For a trade date, supported events after its reference-period end and on or
before the trade date form `pending_share_factor`. Official PE is multiplied by
that product. Events after the trade date and through the analysis end form
`future_share_factor`; close and normalized local EPS are divided by that
product so all output is on the latest share-count basis.

Cash capital reduction adjusts only the share basis. Returned cash remains an
economic gap; the result is not a total-return series. Missing official PE
remains missing throughout. Any relevant unresolved event or unavailable
reference period blocks a seemingly complete normalized percentile.

## Report outputs

`scripts/run_pe_river_report.py` performs this path:

`official PE/close history -> official actions -> normalization -> PDF/CSV/JSON`.

The PDF title is `SYMBOL | Corporate-Action Adjusted PE River`. Its primary
series are adjusted close and adjusted multiple bands, with vertical action
markers. The footer states: `Cash distributions are not total-return adjusted.`

The CSV retains official close and PE, raw implied EPS and raw rivers alongside
pending/future factors, normalized PE/EPS, adjusted close and adjusted rivers.
An unavailable official PE leaves every dependent raw and normalized field
blank. Metadata contains both raw and normalized distributions, complete event
evidence, action-request hashes, and an explicit unavailable-PE invariant.

## Session 1 source spot-checks

- 6669, 2026-09-02: TWT49U/TWT49UDetail reports 1,982.8 bonus shares per
  thousand, no cash-rights shares, `share_factor = 2.9828`, pre-event close
  7,800 and official reference price 2,614.99.
- 2603, 2022-09-19 resume date: TWTAUU/TWTAVUDetail reports a cash-return
  reduction, 400 new shares per thousand old shares, `share_factor = 0.4`,
  NT$6 cash return per old share, pre-event close 80.80 and official reference
  price 187.00.
