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
| Current close probe | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` | Current compatibility sweep only. All rows are schema-checked and the latest official date is selected. A company absent from that snapshot or carrying an official missing marker is a documented legitimate limitation, not fabricated data. |
| Current PE probe | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis` | Current compatibility sweep only. Positive PE parses; official missing markers or absence from the latest snapshot are legitimate PE-unavailable states. |
| Ex-right/ex-dividend | `https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ` | Range query; official page states current result coverage from 2008-01-02. The echoed interval, table schema, row count, identity, and row dates are validated. Cash-only dividends are ignored for share-count normalization. Because the summary does not distinguish every complex rights mechanism, rights rows remain review-required instead of entering normalization speculatively. |
| Capital reduction | `https://www.tpex.org.tw/www/zh-tw/bulletin/revivt` | Range query; official page states coverage from 2013/01. Loss reduction can use an explicit official exchange ratio or the official pre-close/reference-price ratio. Cash-return reduction is classified, but remains review-required unless both official ratio and cash return are present. Unknown reasons remain review-required. |
| Face-value reference result | `https://www.tpex.org.tw/www/zh-tw/bulletin/pvChgRslt` | Range query; supported from 2019-09-09. It supplies exchange-level reference-price evidence. Exact old/new par and exchange schedule proof comes from MOPS category 11 and takes precedence for a same-date face-value event. |
| Face-value proof | `https://mopsov.twse.com.tw/mops/web/t146sb10`, `ajax_t146sb10`, `ajax_t59sb09` | Existing exhaustive per-symbol category-11 proof, generalized with `typek=otc`. Terminal rowset, every detail identity, rowset hash, detail-manifest hash, result/detail counts, interval, and unknown-pagination detection are retained. Network/parser failure is incomplete coverage, never “no event.” |

## Coverage and reconciliation

`MAX` starts at the first positive official PE observation actually returned for
the company, not its listing date and not a company-specific constant.  The
adapter capability floor is 2012-09-01.  Official close and PE are joined only
for the same symbol, market, and trading date.  A PE date without a close fails
closed; a close without PE is preserved with `official_pe = None`.

The shared corporate-action engine consumes canonical `CorporateActionEvent`
objects for both exchanges.  TPEx history before 2013-01-01 remains explicitly
outside complete capital-reduction coverage.  Missing official financial
reference periods retain existing `REFERENCE_PERIOD_UNAVAILABLE` semantics.

## Cache identity

Every cache entry binds source market, source symbol, canonical symbol, source
URL, period, retrieval timestamp, HTTP status, and SHA-256.  `.TW` and `.TWO`
namespaces cannot be interchanged.  Any metadata or body tampering fails closed.
