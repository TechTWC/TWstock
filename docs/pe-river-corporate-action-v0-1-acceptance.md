# PE River Corporate-Action v0.1 — Acceptance Evidence

This file records the compact, reproducible evidence reviewed through
`b3a6bb8b8d46a5945e304720f10704d82b63f5e0`. It intentionally does not embed
generated PDFs or long-history caches. Deterministic source fixtures and tests
remain the reproducible repository evidence; the observation counts and
percentiles below came from the bounded live acceptance recorded on PR #38.

## 6669

- Observations: `1,829`
- Event: `2026-09-02`, `STOCK_DIVIDEND`
- Official bonus shares per 1,000: `1,982.8`
- Share factor: `2.9828`
- Latest raw PE: `6.70x`
- Latest normalized PE: `19.98476x`
- Raw percentile: `0.0547%`
- Normalized percentile: `68.6167%`
- Deterministic paired-fixture SHA-256:
  `f8856e72e545237aafb795750786ddf8ab7b2114c29ee14ce30dbdd47055e862`
- MOPS face-value coverage: `FACE_VALUE_COVERAGE_PROVEN`
- MOPS interval: `2019-03-27` through `2026-09-01`
- Category-11 row/detail count: `18 / 18`
- Face-value events: `0`
- Live rowset SHA-256:
  `d37137d04fcf59be8316d17c354e75f1ba1925d9f5e5524c0fa2b437c5447214`

Reproduce the event factor and normalization arithmetic with:

```bash
python -m pytest -q tests/test_corporate_actions.py -k '6669 or three_for_one or post_2019'
```

## 2603

- Observations: `5,176`
- Valid official PE: `3,645`
- Unavailable official PE: `1,531`
- Unavailable-PE invariant violations: `0`
- Event: `2022-09-19`, `CAPITAL_REDUCTION_CASH_RETURN`
- Official exchange ratio: `400` new shares per `1,000` old shares
- Share factor: `0.4`
- Deterministic paired-fixture SHA-256:
  `dd500eac32c3830015f657abe15feabc4717b0cd495f776705dbedeee1f68a72`

Around the event:

| Date | Official close | Official PE | Period | Pending factor | Normalized PE | Future factor | Adjusted close |
|---|---:|---:|---|---:|---:|---:|---:|
| 2022-09-06 | 80.80 | 1.17 | 111/2 | 1.0 | 1.17 | 0.4 | 202.00 |
| 2022-09-19 | 169.00 | 2.45 | 111/2 | 0.4 | 0.98 | 1.0 | 169.00 |
| 2022-11-07 | 143.50 | 0.79 | 111/3 | 1.0 | 0.79 | 1.0 | 143.50 |

Reproduce the parser, factor, missing-PE, and around-event invariants with:

```bash
python -m pytest -q tests/test_corporate_actions.py -k '2603 or reduction or missing_pe or cash_return'
```

## Source-coverage boundary

- TWSE PE history: `2005+`
- TWSE ex-right history: `2003-05-05+`
- TWSE capital-reduction history: `2011-01-01+`
- Complete v0.1 normalization coverage therefore begins `2011-01-01`.
- Face-value-change coverage is not a global start date; it is proven per
  symbol from `max(symbol history start, 2013-12-30)` through report end.
- A MAX report spanning pre-2011 history retains raw observations, leaves the
  uncertified adjusted fields blank, and does not publish a normalized MAX
  distribution.

## Face-value positive controls

### 6949

- MOPS row/detail count: `4 / 4`
- Coverage status: `FACE_VALUE_COVERAGE_PROVEN`
- Event: `2026-09-07`, `FACE_VALUE_CHANGE_SPLIT`
- Par value: `10 -> 0.5`
- Factor: `20`
- Rowset SHA-256:
  `6d36d07c39d6b6e9f362be2d1784d9b0b791b62f70bd38b55b718d90d0e4954d`

### 2327

- MOPS row/detail count: `3 / 3`
- Coverage status: `FACE_VALUE_COVERAGE_PROVEN`
- Event: `2025-08-25`, `FACE_VALUE_CHANGE_SPLIT`
- Par value: `10 -> 2.5`
- Factor: `4`
- Rowset SHA-256:
  `ee60d2fb00fd4df808c687e1793c053ef8470dc20b7dcdaa3b099200bd39cd8e`

The later “new shares listed” notices for both symbols are retained in the
coverage detail manifest. They are collapsed only when their symbol, par
values, factor and listing date match the fully parsed primary notice; a
standalone incomplete notice remains review-required.
