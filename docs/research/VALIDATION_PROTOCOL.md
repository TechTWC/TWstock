# TWStock Validation Protocol

- Document ID: `TWSTOCK-RESEARCH-VALIDATION-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: TWStock formal strategy validation, experiment audit, robustness review, Out-of-Sample review, Paper Trading review, evidence integrity, decision preparation, invalidation, Retest, Revise, Promote, and Retire

## 1. Purpose

本文件定義 TWStock 如何對正式研究實驗與策略證據執行一致、可重現、可追蹤且不可被單次高報酬結果取代的驗證與審計。

Validation Protocol 必須回答：

- 哪些證據可進入正式審計？
- 實驗是否符合事前規格、Point-in-Time、版本與資料契約？
- 是否存在 Look-ahead Bias、Survivorship Bias、Data Snooping、Overfitting 或 OOS contamination？
- 交易成本、流動性、漲跌停、停牌、下市與無法成交是否被合理處理？
- 結果是否可重現、可解釋、可跨期間與市場環境維持？
- 哪些問題構成 Blocker、Retest、Revise 或 Retire？
- 當前證據是否足以支持進入下一個研究階段？
- 決策當下引用了哪些版本、實驗、Gate、限制與反證？

核心原則：

> Validation 的目的是主動尋找策略可能失效、被高估或無法交易的原因，不是替既有結果尋找通過理由。

本文件不保證任何策略未來獲利，不提供個股買賣建議，不授權真實資金交易、自動下單或券商串接。

## 2. Authority and Document Relationships

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`
4. `docs/research/STRATEGY_LIFECYCLE.md`
5. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
6. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`

後續與策略實驗必須另外受下列版本化文件約束：

- Dataset-specific Data Contracts
- Strategy Research Proposal
- Executable Strategy Specification
- Strategy YAML Config
- Pre-registered Experiment Plan
- Gate Definitions
- Transaction and Execution Model
- Benchmark Contract
- Engineering implementation and test artifacts

文件權限：

- Strategy Lifecycle 定義允許的階段與正式決策。
- Experiment Registry 保存實驗、版本、狀態、依賴與 artifacts。
- Decision Snapshot 固定決策當下的 evidence、rationale、conditions 與 transitions。
- Validation Protocol 定義審計程序、最低檢查與 decision readiness。
- Strategy-specific Specification 定義該策略的假設、公式、參數與事前數值 Gates。

若本文件與 Strategy-specific Gate 數值衝突：

1. 不得在看過結果後選擇較容易通過的版本。
2. 必須確認哪一份 Gate 在實驗前已正式鎖定。
3. 未事前鎖定的 Gate 不得用於聲稱 Confirmatory Pass。
4. 若需要改 Gate，必須依 Strategy Lifecycle 建立 Revise、必要的新版本與新 Experiment ID。

## 3. Scope and Non-goals

### 3.1 In Scope

本文件適用於：

- Data Quality experiments
- Feature Validation
- Numerical Tests
- Leakage Tests
- Implementation Verification
- Historical Backtest
- Robustness Validation
- Sensitivity Tests
- Multiple-testing review
- Out-of-Sample tests
- Walk-forward campaigns
- Reproduction experiments
- Retests
- Paper Trading campaigns
- Live Observation periodic review
- Experiment invalidation and downstream impact
- Promote／Revise／Retest／Retire audit preparation

### 3.2 Out of Scope

本文件不直接定義：

- 投資假設內容
- Signal Formula
- Universe 規則
- Entry／Exit 規則
- Portfolio Construction 規則
- 特定策略的數值 Gate
- 特定資料庫或雲端產品
- 真實資金配置
- 券商下單流程
- 法令遵循或投資人適合度核准

審計角色不得自行修改策略規則，使結果看起來可以通過。

## 4. Validation Authority and Role Separation

### 4.1 Formal Audit Owner

自正式 Historical Backtest 證據形成後：

- `04｜台股策略驗證與審計`是正式 validation owner。
- 正式結果只能為：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

### 4.2 What the Auditor May Do

Auditor 可以：

- 檢查 Evidence Package 完整性
- 重算 Metrics 與 Gates
- 執行 Leakage、Numerical、PIT 與 Reproduction checks
- 要求補充實驗
- 判定 evidence eligibility
- 建立 Finding、Issue、Decision Impact 與 requested decision
- 作出 Promote／Revise／Retest／Retire

### 4.3 What the Auditor Must Not Do

Auditor 不得：

- 修改 Signal、Universe、權重或進出場規則以改善績效
- 在看過 OOS 後重新定義 OOS
- 刪除失敗、負結果或不利 Regime
- 選擇性忽略交易成本或不可成交事件
- 把探索性結果重新命名為 Confirmatory
- 把 Completed execution 當成 Valid evidence
- 讓 GitHub Label 或 Project Status 取代正式 Decision Snapshot

### 4.4 Engineering and Automation Boundary

工程系統、Codex、網站或自動評分器可以：

- 執行測試
- 計算 Gate
- 產生 Evidence Package
- 偵測矛盾與缺漏
- 建議 requested decision

但不得自行作出正式 Promote／Revise／Retest／Retire，也不得直接改變 Strategy Lifecycle State。

## 5. Validation Objects and IDs

每次正式審計至少使用：

```text
VAL-{YYYYMMDD}-{ULID}   # Validation Review ID
FND-{ULID}              # Finding ID
CHK-{ULID}              # Validation Check ID
EVP-{ULID}              # Evidence Package ID
```

所有 ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 可追蹤到 Git Commit、Experiment、Artifact 與 Decision

一個 Validation Review 可以引用多個 Experiment，但不得把可獨立評估的 Experiment 合併成不可追蹤的單一結果。

## 6. Validation Review Types

```text
ENTRY_READINESS
DATA_AND_PIT_AUDIT
IMPLEMENTATION_AUDIT
HISTORICAL_BACKTEST_AUDIT
ROBUSTNESS_AUDIT
OUT_OF_SAMPLE_AUDIT
WALK_FORWARD_AUDIT
PAPER_TRADING_AUDIT
LIVE_OBSERVATION_REVIEW
REPRODUCTION_AUDIT
RETEST_AUDIT
INVALIDATION_REVIEW
PERIODIC_REVIEW
```

每一 Review Type 必須套用本文件的 Universal Checks，並加上對應 stage-specific checks。

## 7. Validation Status Axes

不得以單一 `validation_status` 混合不同語意。

### 7.1 Review Execution Status

```text
PLANNED
IN_PROGRESS
COMPLETED
ABORTED
```

### 7.2 Evidence Readiness Status

```text
NOT_ASSESSED
READY
READY_WITH_LIMITATIONS
NOT_READY
```

### 7.3 Finding Resolution Status

```text
OPEN
UNDER_REVIEW
REMEDIATED_PENDING_RETEST
RESOLVED
ACCEPTED_LIMITATION
WONT_FIX_RETIRED
```

### 7.4 Validation Outcome Status

```text
NOT_ASSESSED
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

### 7.5 Audit Integrity Status

```text
NOT_ASSESSED
VERIFIED
COMPROMISED
INVALIDATED
```

這些狀態不得自動轉換成正式 Strategy Decision；正式決策必須建立 Decision Snapshot。

## 8. Finding Severity and Materiality

### 8.1 Severity

```text
INFO
WARNING
ERROR
BLOCKER
```

- `INFO`：不影響 evidence eligibility 的紀錄或改善建議。
- `WARNING`：可能限制解讀、可重現性或適用範圍。
- `ERROR`：已影響重要結果、Gate、版本一致性或可重現性。
- `BLOCKER`：使目前證據不得支持 Promote，或要求立即停止相關 Campaign／Transition。

### 8.2 Materiality

```text
IMMATERIAL
LIMITED
MATERIAL
PERVASIVE
UNKNOWN
```

Materiality 必須根據：

- 影響的時間範圍
- 影響的股票與交易比例
- 對 Metrics 或 Gate 的可能方向
- 是否影響 OOS 身分
- 是否影響 Strategy behavior
- 是否可局部修復
- 是否影響多個下游 Experiment／Decision

### 8.3 Bias Direction

```text
UPWARD
DOWNWARD
MIXED
UNKNOWN
NOT_APPLICABLE
```

任何可能向上偏誤的未解決問題，原則上不得以「保守估計」為由忽略。

## 9. Entry Readiness Gate

正式 Validation 開始前，必須確認 Evidence Package 完整。

### 9.1 Required Identity and Versions

至少包括適用的：

- Strategy ID and Version
- Specification Version
- Config Version and Hash
- Code Commit SHA and Code Behavior Version
- Dataset Manifest IDs and Versions
- Data Contract Versions
- Feature Versions
- PIT Policy Version
- Availability Rule Versions
- Exchange Calendar Version
- Transaction Model Version
- Execution Model Version
- Benchmark Version
- Experiment IDs
- Design Manifest Hash

### 9.2 Required Evidence

至少包括：

- Pre-registration or Design Lock
- Experiment Registry records
- Input manifests
- Run logs
- Metrics and Gate records
- Core artifacts
- Numerical and leakage tests
- Known incidents
- Reproduction evidence，依 stage 適用
- Multiple-testing family，依適用性
- Requested decision

### 9.3 Entry Outcomes

- `READY`：可開始正式審計。
- `READY_WITH_LIMITATIONS`：可審計，但限制已知且不妨礙主要檢查。
- `NOT_READY`：缺少關鍵版本、evidence 或可重建輸入；不得形成 Promote Decision。

缺少核心版本時，不得要求 auditor 以推測方式補齊。

## 10. Universal Validation Sequence

每次正式 Review 必須依序執行：

```text
1. Freeze review scope and evidence cutoff
2. Verify authority and registration mode
3. Validate identity, versions and manifests
4. Validate data and Point-in-Time
5. Validate implementation and numerical correctness
6. Validate experiment design and sample roles
7. Validate costs, tradability and execution realism
8. Validate statistical and economic robustness
9. Validate OOS / forward evidence, when applicable
10. Reproduce key outputs
11. Evaluate Gates
12. Record counter-evidence and limitations
13. Classify findings and downstream impact
14. Prepare formal Decision Snapshot
```

若前置 Blocker 已使後續結果失去意義，可以停止部分績效檢查，但仍必須保存已完成的檢查、停止原因與未執行項目。

## 11. Data and Point-in-Time Audit

### 11.1 Required Time Axes

對時間敏感資料至少驗證：

- Period represented
- Source publication time
- Ingestion time
- First valid availability time
- Correction／revision time
- Signal formation time
- Decision as-of time
- Earliest executable order time
- Actual or simulated fill time

必須符合：

```text
publicly_available_at
≤ signal_formed_at
≤ order_eligible_at
≤ execution_at
```

實際欄位名稱由 Data Contract 定義。

### 11.2 PIT Checks

至少檢查：

- 歷史回測是否使用當時尚未公布的財報、月營收或公司事件
- 公告時間落在盤中、盤後、假日或非交易日時的可用日規則
- 修訂資料是否被錯誤回填到原始歷史日期
- Delayed／missing publication 的處理
- 資料切點與 Market Calendar 是否一致
- 跨資料來源 timezone 是否正確
- Signal 與 Ranking 是否只使用當時可得 constituent set

### 11.3 Data Revision Policy

若資料來源會事後修訂：

- 必須保存原始觀測版本或 revision lineage。
- 不得用最新修訂值冒充歷史可得值。
- 無法重建原始版本時，必須降低 Evidence Eligibility。
- 修訂是否影響 Gate，必須建立 sensitivity 或 Retest plan。

### 11.4 PIT Blockers

下列情況原則上構成 Blocker：

- 使用未公開資料形成歷史訊號
- Availability rule 與 Specification 不一致
- OOS 期間在鎖定前已被用於規則調整
- 無法識別關鍵資料的公告／可用時間
- Dataset manifest 無法重建主要輸入

## 12. Universe, Survivorship, and Security Master Audit

至少檢查：

- Universe 是否由歷史當時成分建立
- 下市、合併、停止交易與代碼變更是否保留
- 新上市／上櫃 eligibility delay 是否符合 Specification
- 暫停交易與長期無成交股票是否被錯誤保留為可交易
- Security type、market、industry 與 listing status 是否 Point-in-Time
- Corporate action、拆併股、減資、除權息與價格調整是否一致
- Benchmark constituent history 是否公平

禁止：

- 只使用目前仍上市股票回測歷史策略
- 刪除破產、下市或長期停牌標的後重算績效
- 用目前產業分類回填全部歷史而不揭露

## 13. Implementation and Numerical Audit

### 13.1 Code and Environment

至少驗證：

- Code Commit 與 Registry 一致
- Working tree 狀態
- Dependency lock
- Runtime and architecture
- Random seed
- Execution command
- Deterministic／non-deterministic behavior
- Config、Specification 與 code defaults 一致

### 13.2 Numerical Tests

至少涵蓋適用的：

- Signal formula unit tests
- Ranking tie behavior
- Missing-value handling
- Winsorization／normalization
- Rebalance date calculation
- Weight sum and cash handling
- Return aggregation
- Corporate action adjustment
- Benchmark alignment
- Transaction cost calculation
- Limit-up／limit-down handling
- Suspension and missing-price handling
- Delisting return handling
- Turnover calculation
- Exposure and concentration metrics

### 13.3 Golden Cases

重要策略行為必須有小型人工可驗證 Golden Case：

- 固定少量股票
- 固定資料日期
- 明確手算 Signal、Rank、Weight、Order 與 Return
- 程式結果與人工結果逐欄比對

Golden Case 不用於證明策略有效，只用於證明實作符合規格。

### 13.4 Implementation Blockers

- Code behavior 與 Specification 不一致
- Hidden default 改變策略行為
- 交易成本或不可成交規則未執行
- 主要 Metric 無法重算
- 相同輸入無法在容忍度內重現

## 14. Leakage Audit

至少檢查：

- Feature 是否使用未來值
- Label／target 是否進入 feature pipeline
- Standardization 是否用全期間統計量
- Missing-value imputation 是否跨越時間
- Universe selection 是否使用未來存活資訊
- Parameter selection 是否接觸 Test／OOS
- Walk-forward fold 是否正確 purge and embargo
- Cache、join、forward-fill 是否跨時間洩漏
- Corporate event effective date 是否錯置
- Benchmark 或 regime label 是否事後定義並回填

Leakage test 必須有：

- Test ID
- Tested code and dataset versions
- Synthetic or controlled scenario
- Expected failure behavior
- Actual result
- Artifact and log

任何 confirmed material leakage 原則上使受影響 Experiment `INELIGIBLE`，並觸發 Retest 或 Revise assessment。

## 15. Transaction Cost and Execution Realism Audit

### 15.1 Required Components

當實驗評估交易績效時，至少驗證：

- Commission
- Tax
- Slippage
- Market impact，依策略容量適用
- Borrowing／financing cost，依適用性
- Execution price rule
- Order delay
- Failed-order policy
- Partial fills
- Limit-up／limit-down
- Suspension
- Missing price
- Delisting／terminal value
- Odd-lot or board-lot constraints，依版本化市場規則
- Capacity assumptions

不得在本文件硬編碼可能變動的市場制度數值；實驗必須引用版本化 Market Rule／Transaction Contract。

### 15.2 Cost Stress

除 Base Case 外，至少應有事前定義的 Cost Stress 情境，檢查：

- 較高滑價
- 較低成交率
- 訂單延遲
- 較低容量
- 市場壓力期流動性惡化

Stress 數值由 Strategy Specification 或 Experiment Plan 事前定義。

### 15.3 Tradability Blockers

- 策略大量依賴無法成交的漲跌停價格
- 使用停牌期間不存在的成交
- 低流動性部位超過事前容量限制
- 交易成本後主要 Gate 失效但仍使用 gross result Promote
- 未成交訂單被當成已成交

## 16. Historical Backtest Audit

### 16.1 Purpose

Historical Backtest 用於檢查策略假設在歷史樣本中的可操作表現，不代表未來有效。

### 16.2 Minimum Checks

至少檢查：

- Sample window 與 market regimes
- Benchmark fairness
- Gross and net results
- Risk and drawdown
- Turnover and holding concentration
- Industry and security concentration
- Liquidity and capacity
- Exposure stability
- Failed／unfilled orders
- Parameter dependence
- Subperiod dependence
- Negative years and adverse regimes
- Multiple-testing family
- PIT and survivorship

### 16.3 Prohibited Conclusions

不得因下列單一結果 Promote：

- 高 CAGR
- 高 Sharpe
- 平滑 equity curve
- 某一牛市表現突出
- 少數個股貢獻大部分報酬
- 未扣成本的超額報酬

### 16.4 Exit Readiness

進入 Robustness Validation 至少要求：

- Historical Experiment evidence eligible
- 主要 Gate 可重算
- PIT、Universe、Cost 與 Implementation 無未解決 Blocker
- Multiple-testing family 已揭露
- Negative and null results 已保存
- Robustness plan 已事前註冊

## 17. Robustness Validation Protocol

### 17.1 Required Dimensions

依策略適用性，至少覆蓋：

- Parameter sensitivity
- Alternate but defensible definitions
- Rebalance timing sensitivity
- Holding-count sensitivity
- Cost and slippage stress
- Liquidity and capacity stress
- Subperiod stability
- Bull／bear／sideways or other predefined regimes
- Industry exclusion or concentration stress
- Top-contributor removal
- Data-source or feature-version sensitivity
- Bootstrap or resampling uncertainty
- Benchmark alternatives

### 17.2 Parameter Stability

不得只報告最佳參數。

必須保存：

- Tested parameter grid
- Planned versus executed variants
- Full result surface
- Neighboring parameter behavior
- Selection rule
- Whether results were inspected sequentially
- Multiple-testing adjustment，依適用性

若績效只存在於狹窄孤立參數點，必須視為 overfitting warning 或 material finding。

### 17.3 Economic Coherence

Robustness 不只是統計穩定，也要檢查：

- 結果是否符合原始經濟／行為邏輯
- 報酬是否集中在不符合假設的市場情境
- 主要收益是否來自未預期風險曝險
- 策略是否實際變成產業、規模、低流動性或市場 beta bet

若主要報酬機制與核准 Hypothesis 不一致，應進入 Revise assessment，而不是只視為參數問題。

### 17.4 Robustness Exit Readiness

進入 OOS 前至少要求：

- 事前要求的 robustness dimensions 已完成
- 主要結果不是單一參數、單一期間或少數股票驅動
- 成本與流動性 Stress 沒有否證可交易性
- 沒有 unresolved material data／implementation issue
- OOS Design Lock 已完成
- OOS 尚未被用於調整規則

## 18. Multiple Testing and Data Snooping Audit

### 18.1 Family Registration

包含多參數、多因子、多 Universe、多 window、多 benchmark 或多策略變體時，必須有：

- `multiple_testing_family_id`
- Family research question
- Planned variant count
- Executed variants
- Unexecuted variants
- Selection rule
- Primary hypothesis
- Adjustment method
- Sequential inspection record

### 18.2 Required Review

Auditor 必須檢查：

- 是否只展示最佳 variant
- 是否在看過結果後改 Primary metric
- 是否重複使用同一樣本挑選規則
- 是否停止測試於有利結果
- 是否將探索性 variant 冒充 confirmatory
- 是否以大量嘗試提高偶然成功機率

### 18.3 Statistical Method

本文件不強制單一統計方法，但方法必須：

- 與資料結構及假設相容
- 事前定義或明確標記 exploratory
- 考慮 autocorrelation、cross-sectional dependence 或 non-normality，依適用性
- 對多重比較提供合理控制或解釋
- 提供估計不確定性，而非只報 point estimate

方法、版本、參數與假設必須保存於 Experiment Registry。

## 19. Out-of-Sample Audit

### 19.1 OOS Identity

必須保存：

- OOS window
- Lock time
- First access time
- Strategy／Config／Code／Data hashes at lock
- Accessed-before-lock status
- Contamination status
- Replacement holdout plan

### 19.2 OOS Cleanliness

Clean OOS 要求：

- 未參與假設形成
- 未用於參數或版本選擇
- 未用於 Gate 修改
- 未被重複查看直到滿意
- 使用鎖定的 Strategy behavior
- 使用相容的成本、PIT 與 tradability rules

### 19.3 Contamination

下列情況原則上構成 confirmed contamination：

- 查看 OOS 後改 Signal、Universe、Weight、Entry／Exit 或 Risk rule
- 查看 OOS 後選擇 Strategy Version
- 查看 OOS 後改 Gate
- 反覆使用相同區間作為新版本 OOS

Contaminated OOS 必須保留，但不得再作為 clean OOS evidence。

### 19.4 OOS Interpretation

不得要求 OOS 複製 In-Sample 的單一點估計；應檢查：

- 是否嚴重否證原假設
- 是否符合事前 Gate
- 效果方向與 magnitude uncertainty
- 成本後可交易性
- Regime and concentration
- Data／code／PIT consistency

### 19.5 OOS Exit Readiness

進入 Paper Trading 至少要求：

- OOS identity clean or explicitly qualified
- 主要 OOS Gate 已評估
- 無未揭露 contamination
- Strategy、Config、Code 與 Data versions 一致
- 結果可重現
- Paper Trading plan and Campaign frozen manifest ready

## 20. Walk-forward Audit

### 20.1 Fold Requirements

每一 fold 必須保存：

- Train／Validation／Test windows
- Purge／embargo
- Parameter selection output
- Frozen test config
- Fold metrics
- Fold artifacts
- Fold status
- Campaign manifest hash

### 20.2 Audit Checks

- Fold boundaries 不重疊或洩漏
- Test fold 未參與 selection
- 參數更新規則事前固定
- Failed fold 不得從 aggregation 消失
- 聚合權重與計算方式事前定義
- 可獨立引用的 fold 具有 child Experiment ID

不得只保存 aggregate performance。

## 21. Reproduction and Reproducibility Audit

### 21.1 Minimum Reproduction

正式 Promote 前，應依 stage 要求完成：

- Same-environment reproduction，或
- Independent-environment reproduction，依事前規格

至少比較：

- Input manifest
- Config hash
- Code behavior
- Metrics
- Holdings／orders，依適用性
- Gate outcomes
- Artifact hashes or semantic equivalence

### 21.2 Tolerances

Numerical tolerance 必須：

- 事前定義
- 與 floating-point、parallelism 或 stochastic behavior 相容
- 不得在看到差異後放寬以通過

### 21.3 Reproduction Failure

- 先判斷資料、環境、randomness 或 code version 差異
- 保存差異 artifact
- material failure 原則上阻止 Promote
- 不得用新重跑結果覆蓋原 Experiment

## 22. Paper Trading Audit

### 22.1 Purpose

Paper Trading 驗證前瞻資料到達、訊號形成、訂單模擬與營運流程，不只是觀察短期報酬。

### 22.2 Required Checks

至少檢查：

- Campaign frozen-version manifest
- Source arrival timing
- PIT availability
- Universe and Tradability Mask
- Signal and ranking reproducibility
- Proposed holdings and orders
- Simulated fills, partial fills and unfilled orders
- Actual market constraints
- Data and code incidents
- Manual intervention
- Deviation from Specification
- Slippage estimate
- Operational uptime and timeliness
- Decision Snapshot completeness

### 22.3 Campaign Drift

下列 material change 必須終止舊 Campaign：

- Strategy or Specification behavior
- Config
- Code behavior
- Data Contract
- Feature behavior
- PIT or availability rule
- Exchange Calendar
- Transaction／Execution Model
- Monitoring／Incident Policy

不得在同一 Campaign 混用版本後報告單一績效。

### 22.4 Paper Trading Exit Readiness

進入 Live Observation 至少要求：

- 最低期間與樣本要求已依 Strategy Plan 達成
- 資料與訊號流程穩定
- 主要市場限制被正確處理
- 無 unresolved operational Blocker
- 所有人工介入與偏離已揭露
- Paper evidence 沒有嚴重否證原假設
- Periodic review and revalidation triggers 已設定

短期正報酬本身不得支持 Promote。

## 23. Live Observation Periodic Review

Live Observation 不等於真實資金核准。

Periodic Review 至少檢查：

- Current Strategy／Config／Code／Data versions
- Campaign and Snapshot consistency
- Data arrival and incident trend
- Signal generation and fill simulation failures
- Drift from historical assumptions
- Cost and liquidity changes
- Concentration and capacity
- Market rule changes
- Economic rationale deterioration
- Expiration and review deadline
- New Experiment or Decision Impact

Periodic Review outcome 依 Decision Snapshot Schema 使用：

```text
CONTINUE_CURRENT_STAGE
TRIGGER_FORMAL_DECISION
SUSPEND_PENDING_REVIEW
NO_LONGER_APPLICABLE
```

需要改變 Lifecycle State 時，必須另外建立 Promote／Revise／Retest／Retire Decision。

## 24. Benchmark Audit

至少檢查：

- Benchmark 是否符合市場、Universe、currency 與 return type
- Total return versus price return
- Reinvestment assumptions
- Calendar and timestamp alignment
- Tradability and cost asymmetry
- Benchmark selection 是否事前定義
- 是否選擇較弱 benchmark 美化結果

需要多 Benchmark 時，Primary benchmark 必須事前指定；其他為 supplementary。

## 25. Concentration, Regime, and Capacity Audit

### 25.1 Concentration

至少檢查：

- Top holdings contribution
- Top industries contribution
- Top periods contribution
- Single event contribution
- Exposure concentration
- Turnover concentration

### 25.2 Regime Dependence

Regime 必須事前定義或明確標記 exploratory。

不得使用事後最有利分段作為唯一證據。

至少檢查：

- 不同市場方向或波動環境
- 流動性壓力期
- 重大制度或結構變化
- 策略假設預期失效情境

### 25.3 Capacity

容量分析至少引用：

- Position size relative to traded value
- Participation assumptions
- Order delay
- Slippage／impact model
- Liquidity distribution
- Stress capacity

個人研究規模不代表可以忽略容量與可成交限制。

## 26. Gate Evaluation Protocol

### 26.1 Gate Source

數值 Gate 必須來自：

- Approved Strategy Specification
- Pre-registered Experiment Plan
- Versioned Acceptance Gate Contract

本文件不提供策略通用固定報酬率、Sharpe、Drawdown 或勝率門檻。

### 26.2 Gate Status

使用：

```text
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

### 26.3 Gate Audit

每個 Gate 必須保存：

- Gate ID and Version
- Threshold and direction
- Metric source
- Observed value
- Confidence or uncertainty，依適用性
- Evidence artifact
- Evaluation time
- Evaluator
- Status
- Limitations

### 26.4 Gate Integrity

禁止：

- 看過結果後降低門檻
- 替換 Primary metric
- 只引用 favorable window
- 用 gross metric 通過 net Gate
- 把 missing evidence 當 PASS

Gate 未能證明時使用 `NOT_DEMONSTRATED`，不得默認通過。

## 27. Decision Mapping Protocol

Validation finding 不會自動產生決策，但應依下列原則準備 requested decision。

### 27.1 Promote

適用於：

- 當前 stage 必要 evidence 完整
- 事前 Gates 達成或有正式 Conditional Pass
- 無 unresolved Blocker
- 重要限制已揭露
- 下一階段輸入已準備

Promote 只表示進入下一研究階段。

### 27.2 Retest

適用於策略假設與正式策略行為暫時保留，但證據需要重新取得，例如：

- Data defect
- PIT mapping defect
- Code bug
- Missing test
- Reproduction failure
- Insufficient Paper Trading duration
- Incomplete regime or cost test

Retest 必須：

- 保留原 Experiment
- 建立新 Experiment ID
- 指定修正版本
- 指定不得重用的 artifact
- 重新審計

### 27.3 Revise

適用於需要改變研究假設或正式策略行為，例如：

- Signal Formula
- Universe
- Entry／Exit
- Portfolio Construction
- Risk rule
- Acceptance Gate design
- Economic mechanism interpretation

Auditor 只指出 revision scope，不得直接修改規則。

### 27.4 Retire

適用於：

- 核心經濟邏輯被否證
- OOS／Paper evidence 持續失效
- 成本後無研究價值
- PIT／data problem 不可修復
- 可交易性或容量不可接受
- 結果嚴重依賴少數股票、期間或不可重現行為
- 多次 Retest／Revise 仍無法通過最低標準

Retire 必須指定：

```text
retirement_scope: VERSION | LINEAGE
```

### 27.5 Decision Escalation Matrix

| Finding nature | Default assessment |
|---|---|
| Data／code／PIT issue，策略行為不變 | Retest candidate |
| 缺少必要 stress／regime／reproduction | Retest candidate |
| 需要改正式策略規則 | Revise candidate |
| 核心假設與證據矛盾 | Revise or Retire candidate |
| 不可修復 leakage／PIT／tradability | Retire candidate |
| 當前 stage evidence complete and acceptable | Promote candidate |

這是審計起點，不是自動決策規則。

## 28. Conditional Pass

Conditional Pass 只可用於：

- 未完成項目不改變已觀察的主要證據完整性
- 條件、責任人、期限、驗證方法與失敗後果清楚
- 條件未達成前不會錯誤改變 Lifecycle State，依 Decision Snapshot effectivity mode

不得用 Conditional Pass 規避：

- Missing critical PIT evidence
- Confirmed material leakage
- Unresolved Blocker
- Incomplete OOS identity
- Missing transaction cost model
- Unreproducible primary result

## 29. Validation Finding Record

每個 Finding 至少包含：

- `finding_id`
- `validation_review_id`
- `check_id`
- `finding_category`
- `severity`
- `materiality`
- `bias_direction`
- `affected_entity_type`
- `affected_entity_ids`
- `affected_time_range`
- `description`
- `evidence_artifact_ids`
- `root_cause`
- `recommended_action`
- `resolution_status`
- `owner`
- `due_at`, when applicable
- `requires_retest`
- `requires_revision_assessment`
- `requires_invalidation`
- `created_at`
- `resolved_at`, when applicable

Finding 不得只存在於 log、聊天或 PR comment。

## 30. Validation Check Record

每個 Check 至少包含：

- `check_id`
- `validation_review_id`
- `check_category`
- `check_name`
- `check_version`
- `applicability_status`
- `method`
- `input_references`
- `expected_result`
- `actual_result`
- `outcome_status`
- `finding_ids`
- `artifact_ids`
- `executed_by`
- `executed_at`

Applicability 使用：

```text
REQUIRED
WHEN_APPLICABLE
NOT_APPLICABLE
```

`NOT_APPLICABLE` 必須有理由，不能用來跳過困難測試。

## 31. Validation Review Record

每個正式 Review 至少包含：

- `validation_review_id`
- `review_type`
- `strategy_id`
- `strategy_version`
- `lifecycle_stage`
- `evidence_cutoff_at`
- `evidence_package_id`
- `experiment_ids`
- `review_owner_workspace`
- `review_actor`
- `review_started_at`
- `review_completed_at`
- `review_execution_status`
- `evidence_readiness_status`
- `audit_integrity_status`
- `required_check_ids`
- `completed_check_ids`
- `finding_ids`
- `blocker_ids`
- `gate_evaluation_ids`
- `counter_evidence_summary`
- `known_limitations`
- `requested_decision`
- `decision_record_id`, when completed
- `review_artifact_hash`

## 32. Invalidation and Downstream Impact

當上游 Experiment、Dataset、Feature、Code、Config、Policy、Calendar 或 Gate 被 invalidated：

1. 查詢全部 dependency edges。
2. 建立 `POTENTIALLY_AFFECTED` impact。
3. 暫停把受影響 Promote 顯示為無條件 current approval。
4. 評估 materiality 與 bias direction。
5. 更新為 `UNAFFECTED`、`AFFECTED` 或 `INVALIDATED`。
6. 對 material downstream 繼續遞迴傳遞。
7. 建立或更新 Decision Impact。
8. 判斷 Retest、Revise 或 Retire。

不得只修正上游資料後，維持下游 Decision 看起來完全有效。

## 33. Evidence Cutoff and Audit Immutability

正式 Review 必須保存 `evidence_cutoff_at`。

- cutoff 後形成的結果不得靜默加入原 Review。
- 新 evidence 必須建立 Review Amendment、New Review 或後續 Decision，依 materiality。
- 原 Review artifact hash 不得覆寫。
- Metadata correction 必須 append-only。
- 影響 outcome、scope、evidence 或 decision 的修正必須建立新 Review／Decision lineage。

## 34. Validation Artifact Requirements

至少保存適用的：

- Review manifest
- Check results
- Finding records
- Recalculated metrics
- Gate evaluation
- PIT audit report
- Leakage test report
- Reproduction diff
- Sensitivity surface
- Cost／liquidity stress report
- Regime and concentration report
- OOS contamination assessment
- Paper Trading operational audit
- Decision-ready evidence summary

Artifacts 必須有：

- Artifact ID
- URI
- Content hash
- Media type
- Generated at
- Generated by
- Input references
- Retention class

正式核心 artifacts 不得因策略 Retire 或結果失效而刪除。

## 35. Reporting Requirements

正式 Validation Report 至少顯示：

- Strategy ID／Version
- Lifecycle stage
- Review ID and type
- Evidence cutoff
- Experiment IDs
- Version manifest summary
- Evidence readiness
- Completed and missing checks
- Gate summary
- Blockers and material findings
- Counter-evidence
- PIT／Leakage／Reproducibility status
- Cost／Liquidity／Capacity status
- OOS／Paper status
- Known limitations
- Requested decision
- Formal Decision ID，完成後

報告不得只顯示最佳績效圖。

## 36. Prohibited Practices

TWStock 禁止：

- 以單次高報酬取代完整驗證
- 在看過結果後修改 Gate 並宣稱原實驗通過
- 刪除失敗、負結果或不利 Regime
- 用目前存活股票回測全部歷史
- 使用未公開資料形成歷史訊號
- 把修訂後資料回填成原始可得資料
- 把 In-Sample 或反覆查看樣本稱為 OOS
- 只保存最佳參數
- 隱藏 multiple-testing family
- 忽略交易成本、未成交、停牌、下市或市場限制
- 把 gross result 當成 net Gate evidence
- 用 Run Attempt 覆蓋新 Experiment requirement
- Auditor 自行修改策略規則
- 工程或自動系統自行 Promote／Retire
- 讓 Conditional Pass 規避 Blocker
- 讓 invalidated evidence 繼續支持無條件 current approval
- 將 Historical Backtest 描述為未來獲利保證

## 37. Canonical YAML Example

以下為 Validation Review 結構示例；實際欄位依 applicability 補齊。

```yaml
validation_review_id: VAL-20260710-01J2VALIDATE001
review_type: HISTORICAL_BACKTEST_AUDIT
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
lifecycle_stage: HISTORICAL_BACKTEST
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
evidence_package_id: EVP-01J2EVIDENCE001
experiment_ids:
  - EXP-20260710-01J2BASELINE
review_owner_workspace: workspace-04
review_actor: human-auditor
review_started_at: 2026-07-10T20:30:00+08:00
review_completed_at: null
review_execution_status: IN_PROGRESS
evidence_readiness_status: READY
audit_integrity_status: NOT_ASSESSED
required_check_ids:
  - CHK-PIT-001
  - CHK-SURVIVORSHIP-001
  - CHK-LEAKAGE-001
  - CHK-COST-001
  - CHK-REPRO-001
completed_check_ids: []
finding_ids: []
blocker_ids: []
gate_evaluation_ids: []
requested_decision: null
decision_record_id: null
review_artifact_hash: null
```

Finding example：

```yaml
finding_id: FND-01J2PIT001
validation_review_id: VAL-20260710-01J2VALIDATE001
check_id: CHK-PIT-001
finding_category: POINT_IN_TIME
severity: BLOCKER
materiality: PERVASIVE
bias_direction: UPWARD
affected_entity_type: EXPERIMENT
affected_entity_ids:
  - EXP-20260710-01J2BASELINE
description: monthly revenue records became available one trading day earlier than the approved availability rule
recommended_action: RETEST
resolution_status: OPEN
requires_retest: true
requires_revision_assessment: false
requires_invalidation: true
```

## 38. Validation Rules

1. Formal Review must have a unique immutable Review ID.
2. Review scope and evidence cutoff must be frozen before outcome assessment.
3. Missing core versions makes Evidence Package `NOT_READY`.
4. Formal Promote cannot proceed with unresolved Blocker.
5. Strategy-specific Gate values must come from a pre-locked version.
6. Gate changes after result access require a new Experiment and applicable Strategy revision.
7. Confirmed material PIT error makes affected evidence ineligible pending Retest.
8. Confirmed material leakage makes affected evidence ineligible.
9. Historical Universe must include delisted and otherwise failed securities when applicable.
10. Gross performance cannot satisfy a net-performance Gate.
11. Failed or unfilled orders cannot be treated as fills.
12. All independently evaluated parameter variants must remain visible.
13. Multiple-testing family must be registered and auditable.
14. OOS accessed before lock cannot remain CLEAN.
15. Contaminated OOS cannot support a clean-OOS claim.
16. Walk-forward aggregation cannot hide failed folds.
17. Material reproduction failure blocks Promote.
18. Paper Trading version drift terminates the old Campaign.
19. Operational Snapshot with manifest mismatch cannot enter formal Campaign performance.
20. Retest requires a new Experiment ID.
21. Revise must return strategy-rule decisions to workspace 01 or 02.
22. Retire must specify VERSION or LINEAGE scope.
23. Invalidation must propagate through dependency and Decision Impact records.
24. Backfilled Review cannot fabricate original evidence, timing, authority, or effectivity.
25. Formal records and artifacts cannot be hard-deleted.

## 39. Engineering Acceptance Criteria

第一版 Validation Engine／Registry integration 至少達成：

- [ ] Validation Review、Check、Finding 與 Evidence Package 分開儲存。
- [ ] Review ID、Finding ID 與 Check ID 唯一且不可重用。
- [ ] Review scope and evidence cutoff 可被鎖定。
- [ ] Applicable check matrix 可機器驗證。
- [ ] Missing core evidence 阻止 Promote readiness。
- [ ] PIT、Leakage、Numerical、Cost、Tradability 與 Reproduction checks 可追蹤。
- [ ] Findings 保存 severity、materiality 與 bias direction。
- [ ] Unresolved Blocker 阻止 Promote。
- [ ] Gate 只能引用事前鎖定版本。
- [ ] Multiple-testing family、variants 與 negative results 可查詢。
- [ ] OOS contamination 可標記並阻止 clean claim。
- [ ] Walk-forward fold 不會被 aggregate 隱藏。
- [ ] Paper Campaign manifest drift 可偵測。
- [ ] Retest 強制新 Experiment ID。
- [ ] Revise、Retest、Retire handoff scope 可生成。
- [ ] Invalidation 可傳遞到 downstream Experiment and Decision。
- [ ] Validation Report 可重建全部 evidence、checks、findings、gates and limitations。
- [ ] Formal artifact hash 不可靜默覆寫。
- [ ] Failed、Rejected、Invalidated、Retired reviews 永久保存。

## 40. Manual Acceptance Tests

### Test A: Missing Core Version

Given：Historical Backtest 缺少 Dataset Manifest Version。

Expected：Evidence Package 為 `NOT_READY`，不得形成 Promote Decision。

### Test B: Future Data Leakage

Given：月營收資料在公告前即被用於形成訊號。

Expected：建立 BLOCKER Finding，受影響 Experiment ineligible，要求 invalidation and Retest。

### Test C: Survivorship Bias

Given：歷史 Universe 只包含目前仍上市股票。

Expected：審計失敗，要求重建 Security Master／Universe and Retest。

### Test D: Gross Versus Net

Given：gross performance 通過，但 net performance 未通過事前 Gate。

Expected：不得 Promote；Gate 依 net metric 評估。

### Test E: Unfilled Order

Given：跌停或停牌股票的訂單被當成成交。

Expected：交易結果被判定不符合 Execution Model，要求 Retest。

### Test F: Narrow Parameter Peak

Given：只有單一孤立參數點產生高績效，鄰近參數失效。

Expected：建立 overfitting finding，至少阻止直接 Promote，並要求適用 robustness／Revise assessment。

### Test G: Hidden Variants

Given：Batch 測試 50 個 variants，只報告最佳 3 個。

Expected：Review 失敗；要求完整 family、failed and unexecuted variants。

### Test H: OOS Contamination

Given：查看 OOS 後調整 Universe。

Expected：OOS 標記 confirmed contamination，不得作為 clean OOS evidence。

### Test I: Reproduction Failure

Given：相同版本與輸入無法在事前 tolerance 內重現主要 Metric。

Expected：material finding 阻止 Promote，要求 root-cause and Retest。

### Test J: Walk-forward Failed Fold

Given：一個 fold 失敗但 aggregate report 排除該 fold。

Expected：聚合結果不得接受；failed fold 必須顯示並重新評估。

### Test K: Paper Campaign Drift

Given：Paper Trading 途中 Code Behavior Version 改變。

Expected：終止舊 Campaign，建立新 Campaign、new frozen manifest and formal Experiment。

### Test L: Auditor Rule Change

Given：Auditor 為讓結果通過而修改持股數。

Expected：拒絕；Auditor 建立 Revise finding 並交回 workspace 01／02。

### Test M: Retest Reuses Experiment ID

Given：資料修正後重跑仍使用舊 Experiment ID。

Expected：寫入或審計被拒絕，必須建立新 Experiment ID。

### Test N: Upstream Invalidation

Given：主要 Dataset 被 invalidated，已有多個 downstream Promote Decisions。

Expected：建立 dependency impacts，暫停無條件 approval display，逐一重新審計。

### Test O: Conditional Pass with Blocker

Given：存在 confirmed material leakage，但 Review 嘗試 Conditional Pass。

Expected：拒絕 Conditional Pass；必須 Retest、Revise or Retire assessment。

## 41. Revision Policy

下列變更需要建立本文件新版本並經 Pull Request 審查：

- Formal validation authority
- Review Types
- Status axes
- Finding severity or materiality
- Universal validation sequence
- PIT／Leakage minimum checks
- Historical／Robustness／OOS／Paper protocols
- Gate integrity rules
- Decision mapping
- Invalidation propagation
- Engineering acceptance criteria

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Migration
- Affected Reviews／Experiments／Decisions
- Required Retest or Reclassification

## 42. Core Governance Baseline Completion

本文件合併後，下列核心治理基準即告完成：

1. System Vision
2. Research Principles
3. Point-in-Time Policy
4. Strategy Lifecycle
5. Experiment Registry Schema
6. Decision Snapshot Schema
7. Validation Protocol

核心治理基準完成不代表平台或策略已完成，也不代表任何策略已被驗證。

## 43. Minimum Remaining Markdown Roadmap to First Vertical Slice

為避免過度文件化，完成第一個可執行、可回測、可審計的「月營收／盈餘動能策略」前，建議只再建立下列 **6 份必要 Markdown**：

1. `docs/data/DATA_CONTRACT_STANDARD.md`
2. `docs/architecture/THIN_WEBSITE_INFORMATION_ARCHITECTURE.md`
3. `docs/architecture/FOUNDATION_ENGINE_ARCHITECTURE.md`
4. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/RESEARCH_PROPOSAL.md`
5. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/EXECUTABLE_SPECIFICATION.md`
6. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/VALIDATION_PLAN.md`

其他內容優先採：

- Dataset contracts：YAML／JSON machine-readable contracts
- Strategy Config：YAML
- Engineering work：GitHub Issues and Pull Requests
- Experiment results：Registry records and artifacts
- Formal decisions：Decision Snapshots

不應先替所有 Strategy Modes 建立大量空白 Markdown。第一個垂直切片完成並通過審計後，再依實際需求新增其他 Strategy Proposal、Specification 與 Validation Plan。

## 44. Next Document

本文件合併後，下一份正式文件為：

```text
docs/data/DATA_CONTRACT_STANDARD.md
```

之後才進入 Thin Website Information Architecture、Foundation Engine Architecture 與第一個策略垂直切片。