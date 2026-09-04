---
document_id: TWSTOCK-0050-FQV-001
version: 0.1.1-correction-pass
status: provisional-shadow
as_of_date: 2026-09-03
adopted: false
---

# 0050 Fundamental Quality & Valuation Model v0.1

## 1. 目的與結論邊界

本模型以目前 0050 成分股為第一階段研究母體，分開回答三個問題：

1. `Business Quality`：公司是否具備持續獲利、成長與創造每股價值的能力。
2. `Fundamental State`：公司基本面目前正在改善、成長、減速或惡化。
3. `Valuation Context`：目前估值相對自身歷史、同業背景與簡化內含價值是否具有吸引力。

本模型不建立任何：

- Fundamental Score
- Quality Score
- Technical Score
- Total Score
- 加權排名

所有結論保留原始財務數據、狀態、原因碼與資料品質旗標。

本研究必須區分：

```text
模型能合理分析公司的財務品質與狀態
```

以及：

```text
模型能預測未來投資報酬
```

前者可由狀態辨識與財務持續性檢驗；後者仍須由調整後報酬、真實歷史成分、精確公告時間、樣本外測試及統計不確定性另行驗證。本 v0.1 不宣稱已建立投資預測能力。

## 2. 與技術模型的隔離

Technical Model `v0.6-adjusted-0050-fixed-b` 是 Frozen Baseline：

- 不新增技術指標。
- 不修改參數。
- 不以本研究結果回頭調整技術模型。
- 不與基本面模型混成總分。
- 只有在取得可驗證的既有輸出後，才可依 `ticker + as_of_date` 交叉展示。

本次檢查的 repository 沒有該 v0.6 artifact，因此 PDF 明確顯示 `NOT AVAILABLE`，沒有重建或猜測技術狀態。

## 3. 研究資料

### 3.1 來源

第一版使用 FinMind v4 取得：

- `TaiwanStockFinancialStatements`
- `TaiwanStockBalanceSheet`
- `TaiwanStockCashFlowsStatement`
- `TaiwanStockPER`
- `TaiwanStockPrice`
- `TaiwanStockInfo`

若匿名 FinMind 額度在一輪執行中耗盡，程式只對失敗股票使用 bounded fallback：
Yahoo Finance 短期季度財務／日價，加上 TWSE `BWIBBU_ALL` 當期 PE、P/B、殖利率。
fallback 不會補出不存在的 10 年財務或歷史估值，相關股票會明確標記
`SECONDARY_SOURCE_ONLY`、`YAHOO_FALLBACK_LIMITED_HISTORY` 與
`HISTORICAL_VALUATION_UNAVAILABLE`，並依資料充分性輸出 `UNKNOWN / N/M / INSUFFICIENT`。

原始 API 回應只保存在執行期 cache，不提交到 public repository；正式輸出保存可允許重散布的正規化資料、retrieval timestamp、source version、source hash 與 data snapshot identity。

### 3.2 目前限制

- FinMind 財報資料只有 `period_end`，沒有逐筆正式 `announcement_date`。
- 原始日價仍保存未還原收盤價；報酬計算另接 Yahoo adjusted close，並標記
  `ADJUSTED_RETURN_SECONDARY_SOURCE`。這改善分割／配息報酬，但仍不是正式交易所
  公司行動合約。
- 目前 0050 名單由 2025-09 清單依 2025-12、2026-03、2026-06 定審變動重建，須保留 `UNIVERSE_SOURCE_RECONSTRUCTED`。
- 未取得授權清楚且可審計的歷史 0050 成分快照；全部事件正式標記 `CURRENT_CONSTITUENTS_ONLY`。
- 銀行／保險所需 NIM、NPL、credit cost、capital adequacy 尚未納入。
- Forward P/E 沒有可靠歷史 PIT 資料，因此 v0.1 不使用。

`CURRENT_CONSTITUENTS_ONLY` 可能排除退場、衰退或品質較弱公司，因此可能高估 Quality persistence 與長期報酬。狀態定義、單一公司的 PIT 時序檢查與缺值 fail-closed 行為仍可研究；任何「歷史 0050 策略績效」、母體代表性或因果／預測結論均不可使用。由於缺少被排除公司的事件資料，本 correction pass 不捏造偏誤幅度。

受上述限制影響，本輪回測狀態為 `PROVISIONAL_SHADOW`，不得 Promote。

## 4. Point-in-Time 規則

每一筆財務觀察保存：

```text
period_end
announcement_date
available_date
as_of_date
source
retrieval_date
source_version
source_hash
availability_method
timestamp_confidence
```

正式規則為：

```text
period_end <= announcement_date <= available_date <= as_of_date
```

由於第一版沒有正式公告日，`announcement_date = null`，並使用固定、保守、預先註冊的日期代理：

| 財報期別 | available_date proxy |
|---|---:|
| Q1 | period end + 60 days |
| Q2 | period end + 60 days |
| Q3 | period end + 60 days |
| Q4 / annual | period end + 90 days |

所有使用代理日的資料保留：

```text
availability_method = AVAILABLE_DATE_PROXY
timestamp_confidence = conservative_proxy
data_quality_flag = AVAILABLE_DATE_PROXY
```

歷史日期 `t` 只能使用 `available_date <= t` 的資料。公告日缺值若沒有明示 proxy method，程式必須 fail closed。

訊號形成日為代理可用日；價格回測的最早執行日為下一個實際存在的交易日，不使用同日收盤價倒推成交。

## 5. 正規化與衍生指標

### 5.1 現金流單季化

FinMind 現金流量表為年初至當季累計值：

```text
Q1 cash flow = reported Q1 YTD
Q2 cash flow = reported Q2 YTD - reported Q1 YTD
Q3 cash flow = reported Q3 YTD - reported Q2 YTD
Q4 cash flow = reported FY - reported Q3 YTD
```

### 5.2 TTM

```text
TTM metric(t) = sum of the latest four quarterly observations
```

適用於 Revenue、Gross Profit、Operating Income、Net Income、EPS、CFO、CapEx、FCF。

### 5.3 財務公式

```text
FCF = CFO - CapEx
Gross Margin = TTM Gross Profit / TTM Revenue
Operating Margin = TTM Operating Income / TTM Revenue
Net Margin = TTM Net Income / TTM Revenue
ROE = TTM Net Income / average equity
ROA = TTM Net Income / average total assets
NOPAT = TTM Operating Income × (1 - capped effective tax rate)
ROIC = NOPAT / average(Equity + Interest-bearing Debt - Cash)
CFO / Net Income = TTM CFO / TTM Net Income
Net Debt = Interest-bearing Debt - Cash
Debt / Equity = Interest-bearing Debt / Equity
Current Ratio = Current Assets / Current Liabilities
```

`ROIC` 只有在 Equity、Interest-bearing Debt、Cash 與 tax inputs 全部存在時才計算；Debt/Cash 不得補零。分母小於或等於零時輸出缺值，不產生虛假的正常數字。

### 5.4 成長

```text
YoY(t) = TTM(t) / TTM(t-4 quarters) - 1
CAGR(N years) = (latest / N-year-prior)^(1/N) - 1
```

若起點或終點不為正，或目標期間中缺少任一 calendar quarter，CAGR 輸出缺值。CAGR 依實際 fiscal quarter 間隔，不依 DataFrame row offset 假定季度連續。

## 6. Business Quality Model v0.1

輸出：

```text
GOOD
ACCEPTABLE
WEAK
UNKNOWN
```

### 6.1 一般公司命名閘門

#### PROFITABILITY_DURABLE

```text
5Y median ROE >= 10%
AND 5Y median ROIC >= 8%
AND current operating margin > 0
```

#### GROWTH_DURABLE

```text
3Y Revenue CAGR > 0
AND 3Y EPS CAGR > 0
AND (3Y FCF CAGR > 0 OR FCF CAGR unavailable)
```

FCF 缺值不會被視為通過 Cash Conversion；只避免在 Growth Gate 重複處罰同一缺值。

#### CASH_CONVERSION_SUPPORTED

```text
5Y median CFO / Net Income >= 0.80
AND 5Y positive-TTM-FCF ratio >= 70%
```

#### BALANCE_SHEET_RESILIENT

```text
(Net Debt / Equity <= 1.0 OR (Current Ratio >= 1.0 AND TTM FCF > 0))
AND (Net cash / no debt OR Interest Coverage >= 3.0)
```

#### 分類

```text
GOOD
= all four named gates pass

ACCEPTABLE
= Profitability + Balance Sheet pass
AND at least Growth or Cash Conversion passes

WEAK
= critical weakness exists
OR the above durable pattern is not established with otherwise sufficient data

UNKNOWN
= insufficient usable evidence
```

Critical weakness 包含：非正淨值、非正 TTM 營業利益、5Y median ROE 為負、5Y positive-FCF ratio 低於 50%。

這是明示布林閘門，不是分數，也沒有將通過項目加總排序。

### 6.2 成長品質旗標

```text
Revenue growth > 0
AND Operating Margin YoY change < 0
AND FCF YoY < 0
=> LOW_QUALITY_GROWTH
```

```text
EPS YoY > 0
AND latest CFO / Net Income < 0.80
=> EARNINGS_QUALITY_REVIEW
```

### 6.3 金融業

金融業分成 `BANK_HOLDING` 與 `INSURANCE_HEAVY`（另保留 diversified peer group），且不套用一般公司的 FCF、Operating Margin、Net Debt、ROIC。

本 v0.1 source contract 無法一致驗證 EPS／NI 的 standalone-quarter 或 cumulative basis，也缺少可靠 PIT 的 NIM、credit cost、NPL、capital adequacy、CSM、保險營運與資本欄位。因此 12 檔金融股一律輸出：

```text
Quality = UNKNOWN
Fundamental State = UNKNOWN
Data Quality = INSUFFICIENT
reason = FINANCIAL_STATE_UNSUPPORTED
```

即使部分 ROE／Equity／NI 欄位存在，也不得用三取四規則輸出 `ACCEPTABLE`。ROE 絕對值超過 50% 只觸發 mapping anomaly 與 fail-closed，不 cap、winsorize 或當成模型訊號。

### 6.4 景氣循環業

目前明示為 `CYCLICAL`：記憶體、航運、石化與載板中高度循環公司。品質仍檢查完整週期的現金流與報酬率；估值則使用 5Y median TTM EPS 作為 Normalized Earnings，避免 Current P/E 在盈餘高峰產生假低估。

## 7. Fundamental State Model v0.1

Primary output 是 canonical taxonomy：

```text
IMPROVING / STABLE / DETERIORATING / UNKNOWN
```

七階段狀態保留為 `state_detail`，只增加解釋細節，不取代 primary state。此 mapping 在 correction pass 前固定，沒有依股票報酬或 TOO_LATE 結果調門檻：

| state_detail | canonical Fundamental State |
|---|---|
| BOTTOMING | IMPROVING |
| TURNING_UP | IMPROVING |
| CONFIRMED_GROWTH | STABLE |
| MATURE_GROWTH | STABLE |
| DECELERATING | STABLE |
| DETERIORATING | DETERIORATING |
| UNKNOWN | UNKNOWN |

Signal 仍必須由 Revenue、EPS 與 Margin/FCF 至少兩個獨立基本面家族共同支持；canonical mapping 不改動七階段 signal rule。

### DETERIORATING

Revenue YoY 連續弱化，並且 EPS 弱化，或 Margin 與 FCF 同時弱化。

### BOTTOMING

Revenue 仍為負成長但衰退連續收斂，且 EPS 改善，或 Margin 與 FCF 同時改善。

### TURNING_UP

Revenue 由負轉正，或形成明確早期回升序列，且 EPS 改善，或 Margin 與 FCF 同時改善。單一月份／單一指標不能觸發。

### CONFIRMED_GROWTH

Revenue YoY 與 EPS YoY 至少連續三個觀察期為正。

### MATURE_GROWTH

Revenue YoY 與 EPS YoY 連續八個觀察期為正，且沒有先符合 Decelerating。

### DECELERATING

Revenue YoY 與 EPS YoY 仍為正，但各自連續三期下降，且 Margin momentum 不為正。

### UNKNOWN

歷史不足、核心方向缺值或混合方向不符合任何命名閘門。

## 8. Valuation Model v0.1

### 8.1 Historical Valuation

使用 as-of date 當時以前的 PE、P/B、Dividend Yield，保存：

- current
- P25
- median
- P75
- current percentile

至少需要 120 個有效日觀察。

一般公司：

```text
LOW
= PE percentile <= 25%
AND (P/B percentile <= 50% OR positive FCF yield)

HIGH
= PE percentile >= 75%
AND (P/B unavailable OR P/B percentile >= 75%)

NORMAL
= meaningful PE but neither LOW nor HIGH

N/M
= non-positive/missing PE or insufficient history
```

P/B 缺失本身絕不視為 LOW gate 通過；只有獨立的正 FCF yield 可在 P/B 缺失時提供 corroboration。每個 current PE／P/B／yield 均保存 observation date 與 staleness days；超過 10 calendar days 即不使用。

金融業以 P/B 為主要估值尺度；P/B 位於最低四分位但 Fundamental State 為 `DETERIORATING` 時，不判為 LOW。

景氣循環業：

```text
Normalized EPS = median of the latest 20 quarterly TTM EPS observations
Normalized PE = Current Price / Normalized EPS
```

每個歷史 PIT date 都以同一套 rolling 20-quarter median TTM EPS 建立 historical normalized PE distribution；current normalized PE 只與這個相同定義的分布比較，不再和 raw historical PE 混用。Current PE 若比 Normalized PE 低逾約三分之一，標記 `CYCLICAL_LOW_PE_TRAP_RISK`。

### 8.2 Peer Relative Context

使用研究 universe 中明示的 business-model peer group（例如 Foundry、Memory、IC Design、Telecom、PCB、Bank Holding、Insurance-heavy Financial Holding），不再以粗略「電子工業」混組。輸出 PE、P/B、ROE、ROIC、Revenue YoY 的同業百分位；這是描述性 context，不直接改寫 LOW/NORMAL/HIGH，也不使用「PE 最低 = 最便宜」。

### 8.3 Simplified DCF

僅在一般公司且 FCF per share 為正時建立 Bear/Base/Bull：

```text
discount rate = 10%
terminal growth = 3%
projection = 5 years
base growth = clamp(3Y FCF CAGR, 0%, 15%)
bear growth = max(-3%, base - 5%)
bull growth = min(20%, base + 5%)
```

```text
Intrinsic Value = sum(FCF_t / (1+r)^t) + Terminal Value / (1+r)^5
Margin of Safety = Base Value / Current Price - 1
```

Reverse DCF 以二分法反推使 DCF 等於目前價格的成長率，搜尋區間為 -10% 至 30%；若價格不在可解範圍則輸出缺值。

DCF 是情境工具，不是單一目標價；金融業不使用一般 FCF DCF。

## 9. Investment Research Classification

```text
VALUE_RECOVERY
= GOOD + canonical IMPROVING / detail TURNING_UP + LOW/NORMAL

QUALITY_AT_FAIR_PRICE
= GOOD + canonical STABLE / detail CONFIRMED_GROWTH + NORMAL

POSSIBLE_VALUE_TRAP
= (WEAK OR DETERIORATING) + LOW

HIGH_EXPECTATION_RISK
= GOOD + (MATURE_GROWTH OR DECELERATING) + HIGH
```

其餘為 `UNCLASSIFIED_RESEARCH_CASE`。這些是研究標籤，不是交易訊號。

## 10. 歷史驗證

### 10.1 Layer 1：Fundamental State Identification Accuracy

Signal 在時間 `t` 只使用 `available_date <= t` 的資料。獨立 `realized_fundamental_state` 函式只在 evaluation 階段讀取後四季，從下列六個家族形成 ex-post label：Revenue、EPS/NI、Operating Margin、ROE/ROIC、CFO/FCF、Balance Sheet。至少四個家族可用，且至少三個家族同向並有二票淨優勢，才標 `IMPROVING` 或 `DETERIORATING`；其餘充分資料為 `STABLE`，不足為 `UNKNOWN`。這些 evaluation thresholds 不回流 signal。

輸出完整 4×4 confusion matrix，以及 IMPROVING／STABLE／DETERIORATING 各自的 precision、recall、false-positive rate、false-negative rate、support、lead/lag quarters、transition confirmation 與 realized persistence。金融股因 sector-specific PIT 欄位不足，realized label 也為 `UNKNOWN`。

### 10.1.1 Legacy TURNING_UP timing labels

每次 `TURNING_UP` 觀察後檢查未來四季 Revenue YoY 與 EPS YoY：

- `CORRECT`：前兩個後續觀察均維持或改善，且沒有明顯再惡化。
- `TOO_EARLY`：第一期未確認，但較後期才改善。
- `FALSE_RECOVERY`：未改善，或短期改善後到第四期重新低於觸發時。
- `TOO_LATE`：觸發前兩期已同時維持正 Revenue/EPS growth。

Reviewed head `97819a9...` 的 TOO_LATE 為 153/320 = 47.8125%。Correction pass 不為降低此值調參；另列 quarterly reporting cadence、TTM rolling window、multi-period corroboration 與 available-date proxy timing uncertainty 作診斷 contributor，不把 observational decomposition 誤稱因果歸因。

### 10.2 Quality Persistence

依 `GOOD / ACCEPTABLE / WEAK / UNKNOWN` 比較未來 1Y、3Y、5Y：

- ROE
- ROIC
- EPS growth
- FCF positive share
- Operating margin change

### 10.3 Layer 2：Investment Relevance（downstream diagnostic only）

以代理資料可用日後下一交易日收盤為 entry，計算：

```text
20D / 60D (3M) / 120D (6M) / 252D (12M) / 504D (24M) / 756D
```

輸出：Mean、Median、Positive Rate、Excess Return vs 0050、sample size、unique issuer count、max close-to-close favorable/adverse return 與 Worst Max Drawdown。因只用 adjusted close，不使用 MFE／MAE 名稱。

事件包含同公司重複訊號、重疊 return windows 與橫斷面相關，不視為 IID；同時報 ordinary estimate、issuer-cluster 與 signal-quarter time-cluster standard error／interval。回報普通與 robust estimate 的差異，不以顯著性挑參。

報酬優先使用 Yahoo adjusted close；估值與圖表仍保存原始 close。因調整資料屬次級來源、
目前 universe 有存活者偏誤且公告日仍為代理，本輪仍僅可作診斷，不可作正式績效主張。

### 10.4 必要 Baselines

| ID | Baseline |
|---|---|
| A | 0050 buy-and-hold／無主動選股（每個 unique signal date 一筆 benchmark return） |
| B | Current constituent unconditional average |
| C | Fundamental State only：IMPROVING |
| D | Quality only：GOOD |
| E | Valuation only：LOW |
| F | Quality + Valuation：GOOD + LOW/NORMAL |
| G | State + Valuation：IMPROVING + LOW/NORMAL |
| H | Full model：GOOD + IMPROVING + LOW/NORMAL |

沒有找最佳 threshold，也沒有依結果回頭調參。

## 11. Data Quality

每檔輸出：

```text
OK
PARTIAL
INSUFFICIENT
```

本輪因公告日代理與 current-universe 限制，正常情況也只能是 `PARTIAL`。核心資料不足則為 `INSUFFICIENT`。每檔 coverage matrix 保存 history/expected/missing quarters、missing metrics、EPS/ROE/FCF/valuation/price/PIT actual/PIT proxy coverage、financial completeness、current usability 與 reason codes。缺值不補零、不以前值假裝正常。

`7769` 的短歷史屬於實際掛牌／可觀察歷史限制。`8046` 在 reviewed head 使用的 fallback 只有 5 季，本次 refresh 雖從另一 vendor path 取得 42 季，但無法驗證跨 source vintage 的連續性，因此標記 `REVIEWED_HEAD_SOURCE_HISTORY_INSUFFICIENT` 與 `SOURCE_HISTORY_PROVENANCE_UNSTABLE`，並 fail closed 為 `UNKNOWN / INSUFFICIENT`；不得描述為公司歷史不足。

## 12. Machine-readable Outputs

執行結果包含：

- `0050_current_state_matrix_v0.1.csv`
- `0050_normalized_financials_pit_v0.1.csv`
- `0050_backtest_events_v0.1.csv`
- `0050_baseline_comparison_v0.1.csv`
- `0050_state_validation_v0.1.csv`
- `0050_state_confusion_matrix_v0.1.csv`
- `0050_state_accuracy_metrics_v0.1.csv`
- `0050_too_late_diagnosis_v0.1.csv`
- `0050_quality_persistence_v0.1.csv`
- `0050_return_diagnostics_v0.1.csv`
- `0050_robustness_diagnostics_v0.1.csv`
- `0050_financial_mapping_audit_v0.1.csv`
- `0050_peer_context_v0.1.csv`
- `0050_data_quality_report_v0.1.csv`
- `0050_fundamental_quality_valuation_backtest_v0.1.json`
- `0050_fundamental_quality_valuation_backtest_v0.1.pdf`
- `artifact_manifest.json`

PDF 包含 Executive Summary、全體矩陣、50 檔各一頁 5–10 年線圖、代表案例、歷史驗證、baseline、技術模型缺件邊界與六項研究問題。

## 13. 重現方式

```bash
python -m pip install --requirement requirements-dev.txt
python -m pytest -q tests/test_fundamental_quality_valuation.py
python scripts/run_0050_fundamental_v0_1.py --workers 4
```

重新抓取 vendor data：

```bash
python scripts/run_0050_fundamental_v0_1.py --workers 4 --refresh
```

## 14. 本輪明確禁止

- 不調整 Technical v0.6。
- 不建立任何分數或加權排名。
- 不最佳化 PE、ROE、growth 或 TURNING_UP threshold。
- 不宣稱目前歷史結果代表正式 0050 策略績效。
- 不自動進入 v0.2。
- 不合併 main。
- 不部署 Production。
