# Generic TPEx PE River v0.1 — official-source contract

## Supported universe

The production universe is the current company set returned by the official
TPEx/MOPS company master `mopsfin_t187ap03_O`, restricted to four-digit company
codes with a non-empty common-stock par-value field.  This is positive identity
evidence for TPEx listed ordinary common shares; it is not a maintained symbol
whitelist and it is not inferred from a failed TWSE query.

ETF, ETN, bond, warrant, preferred share, convertible bond, TDR, emerging stock,
structured product, and other non-company/non-ordinary instruments are outside
this contract and fail closed.  Historical delisted companies are not
artificially blocked by the adapters, but v0.1 does not reconstruct a complete
delisted identity master.

## Official endpoints

| Purpose | Official endpoint | Contract and coverage |
|---|---|---|
| TPEx identity | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O` | Current company master. Code, full/short company name, listing date, common-stock par value, preferred shares, and report date are validated. Duplicate or malformed identities fail closed. |
| TWSE identity | `https://openapi.twse.com.tw/v1/opendata/t187ap03_L` | Current listed-company master used by the same positive-evidence AUTO router. A code found on both exchanges is ambiguous and fails closed. |
| Historical close | `https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock` | Per-company, per-month history; official page states history from 1994/01. Request uses `code`, `date=YYYY/MM/01`, and `response=json`. Response `code`, month, status, fields, row widths, chronological order, and `totalCount` are validated. The monthly response has no pagination; pagination-shaped or truncated data fails closed. Missing official close remains unavailable and is not emitted as a priced observation. |
| Historical PE | `https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryStock` | Per-company, per-month history. The official query page states availability from ROC 101/09 (2012/09). The response is parsed by normalized field name, never row position; response month and declared row count are mandatory. The official historical envelope omits code/name, so identity is proven by the exact per-code request URL and its same-month paired `tradingStock` envelope, which must echo code/name; a PE response code, when present, must match. `-`, `--`, `N/A`, zero, and negative PE map to `None`. The source may omit financial-report-period fields; v0.1 never guesses a quarter. |
| Current close probe | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` | Current compatibility sweep only. All rows are schema-checked and the latest official date is selected. The response is a bare JSON array with no declared total or pagination metadata, so global completeness is explicitly **not proven**. A present official missing marker is proven unavailable; snapshot absence alone is unresolved and requires bounded per-symbol evidence. |
| Current PE probe | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis` | Current compatibility sweep only. Positive PE parses; an official missing/nonpositive value in a present row is proven unavailable. The bare-array response has no global completeness guarantee; absence never proves legitimate unavailability by itself. |
| Daily trading status | `https://www.tpex.org.tw/www/zh-tw/afterTrading/chtm` | Bounded resolution for a company omitted from a latest snapshot. Exact date/status, required fields, row widths, unique symbols, declared row count, company identity, and the official stop-trading flag are validated. A positive stop-trading row proves `SUSPENDED_TRADING`; no row does not prove another reason. |
| Ex-right/ex-dividend | `https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ` | Range query; official page states current result coverage from 2008-01-02. The echoed interval, table schema, row count, identity, and row dates are validated. Cash-only dividends are ignored for share-count normalization. Because the summary does not distinguish every complex rights mechanism, rights rows remain review-required instead of entering normalization speculatively. |
| Capital reduction | `https://www.tpex.org.tw/www/zh-tw/bulletin/revivt` | Range query; official page states coverage from 2013/01. Loss reduction can use an explicit official exchange ratio or the official pre-close/reference-price ratio. Cash-return reduction is classified, but remains review-required unless both official ratio and cash return are present. Unknown reasons remain review-required. |
| Face-value reference result | `https://www.tpex.org.tw/www/zh-tw/bulletin/pvChgRslt` | Range query; supported from 2019-09-09. It supplies exchange-level reference-price evidence. Exact old/new par and exchange schedule proof comes from MOPS category 11 and takes precedence for a same-date face-value event. |
| Face-value proof | `https://mopsov.twse.com.tw/mops/web/t146sb10`, `ajax_t146sb10`, `ajax_t59sb09` | Existing exhaustive per-symbol category-11 proof, generalized with `typek=otc`. Terminal rowset, every detail identity, rowset hash, detail-manifest hash, result/detail counts, interval, and unknown-pagination detection are retained. Network/parser failure is incomplete coverage, never “no event.” |

## Coverage and reconciliation

`MAX` starts at the earliest retained official valuation observation whose
source coverage and identity are proven, not at the first positive PE, listing
date, or a company-specific constant. `source_start` records that first
observation; `first_valid_pe_date` separately records the first positive
numeric PE and can be `null`. The adapter capability floor is 2012-09-01.
Official close and PE are joined only for the same symbol, market, and trading
date. A PE date without a close fails closed. A close date without a valuation
row also fails closed because row absence is not proof of an unavailable PE.
A present official valuation row carrying `-`, `--`, blank, zero, or a negative
PE is retained with `official_pe = null`.

An observation history with zero valid PE values is a legal bounded state: CSV
retains official closes, JSON reports positive `observation_count` and zero
`valid_pe_observation_count`, and the PDF displays unavailable current PE,
percentiles, implied EPS, and river bands. No zero or synthetic PE is emitted.

## Universe-audit evidence model

Every ordinary-share identity receives separate close and PE status:
`AVAILABLE`, `LEGITIMATE_UNAVAILABLE_PROVEN`, `UNRESOLVED`, or `FAILURE`.
Snapshot omissions enter bounded per-symbol resolution against the official
monthly close/PE sources and daily trading-status source. Every proven
unavailable record includes symbol, market, data type, reason code, official
source, source date/interval, and hashed evidence. In particular, an absent PE
row in an otherwise validated monthly rowset remains `UNRESOLVED` unless another
official source (for example a positive suspended-trading row) proves the
reason. The audit gate passes only when both close and PE have zero unresolved
and zero failure records.

The shared corporate-action engine consumes canonical `CorporateActionEvent`
objects for both exchanges.  TPEx history before 2013-01-01 remains explicitly
outside complete capital-reduction coverage.  Missing official financial
reference periods retain existing `REFERENCE_PERIOD_UNAVAILABLE` semantics.

## Cache identity

Every cache entry binds source market, source symbol, canonical symbol, source
URL, period, retrieval timestamp, HTTP status, and SHA-256.  `.TW` and `.TWO`
namespaces cannot be interchanged.  Any metadata or body tampering fails closed.
