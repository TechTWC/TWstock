# TWStock Validation Protocol

- Document ID: `TWSTOCK-RESEARCH-VALIDATION-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: TWStock formal strategy validation, experiment audit, robustness review, Out-of-Sample review, Walk-forward review, Paper Trading review, Live Observation periodic review, evidence integrity, decision preparation, invalidation, Retest, Revise, Promote, and Retire

## 1. Purpose

本文件定義 TWStock 如何對正式研究實驗與策略證據執行一致、可重現、可追蹤、可機器驗證，且不可被單次高報酬結果取代的驗證與審計。

Validation Protocol 必須永久回答：

- 哪些證據可以進入正式審計？
- 實驗是否符合事前規格、Point-in-Time、版本與資料契約？
- 是否存在 Look-ahead Bias、Survivorship Bias、Data Snooping、Overfitting 或 OOS contamination？
- 交易成本、流動性、漲跌停、停牌、下市、部分成交與無法成交是否被合理處理？
- 結果是否可重現、可解釋，並能跨參數、期間與市場環境維持？
- 哪些問題構成 Warning、Error、Blocker、Retest、Revise 或 Retire？
- 當前證據是否足以支持進入下一個研究階段？
- 決策當下引用了哪些版本、實驗、Gate、限制與反證？
- 後續資料或實驗失效時，哪些 Review 與 Decision 受到影響？

核心原則：

> Validation 的目的，是主動尋找策略可能失效、被高估、無法重現或無法交易的原因，而不是替既有結果尋找通過理由。

本文件不保證任何策略未來獲利，不提供個股買賣建議，不授權真實資金交易、自動下單或券商串接。

## 2. Authority and Document Relationships

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`
4. `docs/research/STRATEGY_LIFECYCLE.md`
5. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
6. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`

策略實驗另外受下列版本化文件約束：

- Dataset-specific Data Contracts
- Strategy Research Proposal
- Executable Strategy Specification
- Strategy YAML Config
- Pre-registered Experiment Plan
- Versioned Acceptance Gate Contract
- Transaction and Execution Model
- Benchmark Contract
- Engineering implementation and test artifacts

權限邊界：

- Strategy Lifecycle 定義允許的階段與正式決策。
- Experiment Registry 保存實驗、版本、狀態、依賴與 artifacts。
- Decision Snapshot 固定決策當下的 evidence、rationale、conditions 與 transitions。
- Validation Protocol 定義審計程序、最低檢查、Evidence Package 與 decision readiness。
- Strategy-specific Specification 定義該策略的假設、公式、參數與事前數值 Gates。
- Validation Protocol 不得自行新增、放寬或改寫投資規則與策略 Gate。

若本文件與 Strategy-specific Gate 數值衝突：

1. 不得在看過結果後選擇較容易通過的版本。
2. 必須確認哪一份 Gate 在實驗前已正式鎖定。
3. 未事前鎖定的 Gate 不得用於聲稱 Confirmatory Pass。
4. 若需要改 Gate，必須依 Strategy Lifecycle 建立 Revise、必要的新版本與新 Experiment ID。
5. 原實驗與原 Gate evaluation 必須保留。

## 3. Scope and Non-goals

### 3.1 In Scope

本文件適用於：

- Entry Readiness
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
- Retrospective backfill of historical Validation Reviews

### 3.2 Out of Scope

本文件不直接定義：

- 投資假設內容
- Signal Formula
- Universe 規則
- Entry／Exit 規則
- Portfolio Construction 規則
- 特定策略的數值 Gate
- 特定資料庫、雲端或 UI 技術
- 真實資金配置
- 券商下單流程
- 法令遵循或投資人適合度核准

審計角色不得自行修改策略規則，使結果看起來可以通過。

## 4. Validation Authority and Role Separation

### 4.1 Formal Audit Owner

自正式 Historical Backtest 證據形成後：

- `04｜台股策略驗證與審計`是正式 Validation Owner。
- 正式策略審計決策只能為：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

### 4.2 Auditor May

Auditor 可以：

- 檢查 Evidence Package 完整性
- 重算 Metrics 與 Gates
- 執行 Leakage、Numerical、PIT、Tradability 與 Reproduction checks
- 要求補充實驗
- 判定 evidence readiness 與 evidence eligibility
- 建立 Finding、Issue、Dependency Impact 與 requested decision
- 作出 Promote／Revise／Retest／Retire
- 在證據失效時要求暫停 current approval display

### 4.3 Auditor Must Not

Auditor 不得：

- 修改 Signal、Universe、權重或進出場規則以改善績效
- 在看過 OOS 後重新定義 OOS
- 刪除失敗、負結果或不利 Regime
- 選擇性忽略交易成本或不可成交事件
- 把探索性結果重新命名為 Confirmatory
- 把 Completed execution 當成 Valid evidence
- 用 Conditional Pass 規避核心證據缺漏或 Blocker
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
EVP-{ULID}              # Evidence Package ID
CHK-{ULID}              # Validation Check ID
FND-{ULID}              # Finding ID
VAM-{ULID}              # Validation Amendment ID
VRL-{ULID}              # Validation Relationship ID
```

所有 ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 可作為資料庫主鍵或外鍵
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

每一 Review Type 必須套用 Universal Checks，並依第 11 節的 machine-validatable applicability matrix 加上 stage-specific checks。

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

### 7.3 Validation Outcome Status

```text
NOT_ASSESSED
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

### 7.4 Audit Integrity Status

```text
NOT_ASSESSED
VERIFIED
COMPROMISED
INVALIDATED
```

### 7.5 Finding Resolution Status

```text
OPEN
UNDER_REVIEW
REMEDIATED_PENDING_RETEST
RESOLVED
ACCEPTED_LIMITATION
WONT_FIX_RETIRED
```

這些狀態不得自動轉換成正式 Strategy Decision；正式決策必須建立 Decision Snapshot。

## 8. Cross-status Consistency Rules

### 8.1 Non-terminal Review

當 `review_execution_status = PLANNED | IN_PROGRESS`：

- `validation_outcome_status` 必須為 `NOT_ASSESSED`。
- `decision_record_id` 必須為 null。
- 不得宣稱 Review 已 Pass、Fail 或完成正式決策。

### 8.2 Aborted Review

當 `review_execution_status = ABORTED`：

- `validation_outcome_status` 必須為 `NOT_ASSESSED` 或 `NOT_DEMONSTRATED`。
- `requested_decision` 必須為 null；後續建議只能保存於 Finding 的 `recommended_action`。
- `decision_record_id` 必須為 null。
- 必須保存 abort reason、已完成 checks 與未完成 checks。

### 8.3 Completed Review

當 `review_execution_status = COMPLETED`：

- `review_completed_at` 必須存在。
- `validation_outcome_status` 不得為 `NOT_ASSESSED`。
- 所有 `REQUIRED` checks 必須完成，或以 Finding 明確記錄無法完成原因。
- Review artifact hash 必須存在。

### 8.4 Readiness Constraints

- `evidence_readiness_status = NOT_READY` 時，不得為 `PASS` 或 `CONDITIONAL_PASS`。
- `NOT_READY` 時不得 requested decision = `PROMOTE`。
- `READY_WITH_LIMITATIONS` 可以進行審計，但限制不得包含核心版本缺失、confirmed material leakage、缺少 OOS identity 或缺少 transaction model。
- Promote readiness 要求 Evidence Package `COMPLETE`。

### 8.5 Finding Constraints

- 存在 unresolved `BLOCKER` 時，不得為 `PASS` 或 `CONDITIONAL_PASS`。
- 存在 unresolved material `ERROR` 時，原則上不得為 `PASS`；若為 `CONDITIONAL_PASS`，必須證明該 Error 不影響主要 evidence、Gate、PIT、OOS identity 或 tradability。
- `ACCEPTED_LIMITATION` 不得用於 confirmed material leakage、PIT violation、invalid OOS identity 或不可重現 primary result。

### 8.6 Integrity Constraints

- `audit_integrity_status = COMPROMISED` 時：
  - `validation_outcome_status` 不得為 `PASS` 或 `CONDITIONAL_PASS`。
  - `requested_decision` 不得為 `PROMOTE`。
- `audit_integrity_status = INVALIDATED` 時：
  - `validation_outcome_status` 必須為 `FAIL` 或 `NOT_DEMONSTRATED`。
  - `requested_decision` 不得為 `PROMOTE`。
  - 原 Review 不得產生具治理效力的 Decision。
  - 必須建立 Invalidation／Impact record。

### 8.7 Promote Readiness

`requested_decision = PROMOTE` 只有在全部適用條件成立時允許：

- `review_execution_status = COMPLETED`
- `evidence_readiness_status = READY | READY_WITH_LIMITATIONS`
- `validation_outcome_status = PASS | CONDITIONAL_PASS`
- `audit_integrity_status = VERIFIED`
- Evidence Package `completeness_status = COMPLETE`
- 沒有 unresolved `BLOCKER`
- 沒有 confirmed material PIT／Leakage／OOS contamination 問題
- 適用的 Gate 已評估
- 適用的 Reproduction 已通過
- 下一階段必要輸入已準備

### 8.8 Decision Linkage

- `decision_record_id` 只有在 Review 已 `COMPLETED` 且 Decision Snapshot 已正式建立時才能存在。
- Fail Review 可以形成 `RETEST`、`REVISE` 或 `RETIRE` Decision。
- Review outcome 不得直接改變 Lifecycle State。
- Decision Snapshot 不得反向改寫 Review outcome、Finding 或 Evidence Package。

## 9. Finding Severity, Materiality, and Bias Direction

### 9.1 Severity

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

### 9.2 Materiality

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

### 9.3 Bias Direction

```text
UPWARD
DOWNWARD
MIXED
UNKNOWN
NOT_APPLICABLE
```

任何可能向上偏誤的未解決問題，不得以「保守估計」為由忽略。

## 10. Evidence Package Schema

### 10.1 Purpose

Evidence Package 是 Validation Review 在 `evidence_cutoff_at` 當下所引用之證據的不可變快照，不得只保存動態查詢條件。

### 10.2 Identity and Registration

每個 Evidence Package 至少包含：

- `evidence_package_id`
- `schema_version`
- `registration_mode`
- `package_type`
- `strategy_id`, when applicable
- `strategy_version`, when applicable
- `lifecycle_stage`
- `review_type`
- `evidence_cutoff_at`
- `created_at`
- `created_by`
- `source_system`
- `content_hash`
- `hash_algorithm`

`package_type` 使用：

```text
ENTRY_READINESS_EVIDENCE
DATA_AND_PIT_EVIDENCE
IMPLEMENTATION_EVIDENCE
HISTORICAL_BACKTEST_EVIDENCE
ROBUSTNESS_EVIDENCE
OUT_OF_SAMPLE_EVIDENCE
WALK_FORWARD_EVIDENCE
PAPER_TRADING_EVIDENCE
LIVE_OBSERVATION_EVIDENCE
REPRODUCTION_EVIDENCE
RETEST_EVIDENCE
INVALIDATION_EVIDENCE
PERIODIC_REVIEW_EVIDENCE
```

當 `registration_mode = RETROSPECTIVE_BACKFILL`，Evidence Package 另須保存：

- `original_package_created_at`, if known
- `backfilled_at`
- `source_document_ids`
- `source_evidence_confidence`
- `source_evidence_limitations`

Backfilled Evidence Package 不得偽造原始 artifact、hash、availability、authority 或完整性；無法證明的項目必須列入 `missing_items` 或 `known_limitations`。

### 10.3 Version Manifest

至少保存適用的：

- Specification Version
- Config Version and Hash
- Code Commit SHA
- Code Behavior Version
- Runtime and dependency lock versions
- Dataset Manifest IDs and Versions
- Source Versions
- Data Contract Versions
- Feature Versions
- PIT Policy Version
- Availability Rule Versions
- Exchange Calendar Version
- Transaction Model Version
- Execution Model Version
- Benchmark Version
- Campaign Frozen Manifest Hash
- Design Manifest Hash

### 10.4 Evidence References

至少保存適用的：

- `experiment_ids`
- `experiment_family_ids`
- `campaign_ids`
- `fold_ids`
- `observation_ids`
- `metric_record_ids`
- `gate_evaluation_ids`
- `artifact_ids`
- `issue_ids`
- `dependency_impact_ids`
- `decision_impact_ids`
- `multiple_testing_family_ids`
- `pre_registration_ids`

每個 Experiment reference 必須保存 Evidence Package cutoff 當下的：

- Execution Status
- Evidence Eligibility Status
- Integrity Status
- Reproducibility Status
- OOS Contamination Status
- Dependency Impact Status
- Supersession Status
- Registry event cutoff reference

### 10.5 Completeness

必須保存：

- `required_item_count`
- `present_item_count`
- `missing_items`
- `completeness_status`
- `completeness_assessed_at`
- `completeness_assessed_by`
- `known_limitations`

`completeness_status`：

```text
COMPLETE
PARTIAL
INSUFFICIENT
```

- `COMPLETE`：全部 required evidence 已存在。
- `PARTIAL`：可進行有限審計，但不得支持 Promote。
- `INSUFFICIENT`：不得開始正式 outcome assessment。
- Promote readiness 必須使用 `COMPLETE` Evidence Package。

### 10.6 Immutability and Lineage

Evidence Package 一旦被 Review 引用：

- 不得覆寫內容或 hash。
- Metadata correction 必須 append-only。
- 新增或替換 evidence 必須建立新 Evidence Package ID。
- 必須保存 `supersedes_evidence_package_id` 或 relationship record。
- cutoff 後的新 evidence 不得加入原 Package。

## 11. Review Type × Required Check Matrix

Applicability enum：

```text
REQUIRED
WHEN_APPLICABLE
NOT_APPLICABLE
```

Check Category enum：

```text
AUTHORITY_AND_IDENTITY
EVIDENCE_COMPLETENESS
DATA_AND_PIT
UNIVERSE_AND_SURVIVORSHIP
IMPLEMENTATION_AND_NUMERICAL
LEAKAGE
TRANSACTION_AND_TRADABILITY
STATISTICAL_AND_ROBUSTNESS
MULTIPLE_TESTING
OOS_IDENTITY
WALK_FORWARD
REPRODUCTION
CAMPAIGN_AND_OPERATIONAL
BENCHMARK
DEPENDENCY_AND_IMPACT
GATE_EVALUATION
```

縮寫：

- `R` = REQUIRED
- `W` = WHEN_APPLICABLE
- `N` = NOT_APPLICABLE

| Review Type | Auth/ID | Evidence | Data/PIT | Universe | Impl/Num | Leakage | Cost/Trade | Robust | Multi-test | OOS | WF | Repro | Campaign/Ops | Benchmark | Impact | Gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ENTRY_READINESS | R | R | W | W | W | W | W | W | W | W | W | W | W | W | W | R |
| DATA_AND_PIT_AUDIT | R | R | R | W | W | R | N | N | N | W | N | W | N | N | W | W |
| IMPLEMENTATION_AUDIT | R | R | W | W | R | R | W | N | N | N | N | R | N | W | W | W |
| HISTORICAL_BACKTEST_AUDIT | R | R | R | R | R | R | R | R | R | N | N | R | N | R | W | R |
| ROBUSTNESS_AUDIT | R | R | R | R | R | R | R | R | R | N | N | R | N | R | W | R |
| OUT_OF_SAMPLE_AUDIT | R | R | R | R | R | R | R | R | R | R | N | R | N | R | W | R |
| WALK_FORWARD_AUDIT | R | R | R | R | R | R | R | R | R | W | R | R | N | R | W | R |
| PAPER_TRADING_AUDIT | R | R | R | R | R | W | R | W | W | N | N | R | R | R | R | R |
| LIVE_OBSERVATION_REVIEW | R | R | R | W | W | W | R | W | W | N | N | W | R | W | R | W |
| REPRODUCTION_AUDIT | R | R | W | W | R | W | W | N | N | N | N | R | W | W | W | W |
| RETEST_AUDIT | R | R | R | W | R | R | W | W | W | W | W | R | W | W | R | R |
| INVALIDATION_REVIEW | R | R | W | W | W | W | W | W | W | W | W | W | W | W | R | W |
| PERIODIC_REVIEW | R | R | R | W | W | W | R | W | W | N | N | W | R | W | R | W |

規則：

- Matrix 必須以版本化 machine-readable config 實作。
- `NOT_APPLICABLE` 必須保存理由。
- 不得用 `WHEN_APPLICABLE` 規避困難或不利測試。
- Strategy-specific Validation Plan 可以把 `W` 提升為 `R`，不得在看過結果後把 `R` 降為 `W` 或 `N`。
- Formal Promote 前，當前 stage 的全部 `R` checks 必須完成。
- Reproduction 要求可由 Strategy Plan 指定 Same-environment 或 Independent-environment，但不得完全省略。

## 12. Entry Readiness Gate

正式 Validation 開始前，必須確認 Evidence Package 完整。

### 12.1 Required Identity and Versions

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

### 12.2 Required Evidence

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

### 12.3 Entry Outcomes

- `READY`：Evidence Package `COMPLETE`，可開始正式審計。
- `READY_WITH_LIMITATIONS`：Package 仍為 `COMPLETE`，但存在已揭露且不妨礙主要檢查的限制。
- `NOT_READY`：Package `PARTIAL` 或 `INSUFFICIENT`，或缺少關鍵版本、evidence 或可重建輸入。

缺少核心版本時，不得要求 auditor 以推測方式補齊。

## 13. Universal Validation Sequence

每次正式 Review 必須依序執行：

```text
1. Freeze review scope and evidence cutoff
2. Freeze Evidence Package and content hash
3. Verify authority and registration mode
4. Validate identity, versions and manifests
5. Apply Review Type × Required Check Matrix
6. Validate data and Point-in-Time
7. Validate implementation and numerical correctness
8. Validate experiment design and sample roles
9. Validate costs, tradability and execution realism
10. Validate statistical and economic robustness
11. Validate OOS / forward evidence, when applicable
12. Reproduce key outputs
13. Evaluate Gates
14. Record counter-evidence and limitations
15. Classify findings and downstream impact
16. Freeze Review outcome and artifact hash
17. Prepare formal Decision Snapshot
```

若前置 Blocker 已使後續績效檢查失去意義，可以停止部分測試，但仍必須保存：

- 已完成 checks
- 未執行 checks
- 停止原因
- 對 outcome 的限制
- Required next action

## 14. Data and Point-in-Time Audit

### 14.1 Required Time Axes

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

### 14.2 PIT Checks

至少檢查：

- 歷史回測是否使用當時尚未公布的財報、月營收或公司事件
- 公告時間落在盤中、盤後、假日或非交易日時的可用日規則
- 修訂資料是否被錯誤回填到原始歷史日期
- Delayed／missing publication 的處理
- 資料切點與 Market Calendar 是否一致
- 跨資料來源 timezone 是否正確
- Signal 與 Ranking 是否只使用當時可得 constituent set

### 14.3 Data Revision Policy

若資料來源會事後修訂：

- 必須保存原始觀測版本或 revision lineage。
- 不得用最新修訂值冒充歷史可得值。
- 無法重建原始版本時，必須降低 Evidence Eligibility。
- 修訂是否影響 Gate，必須建立 sensitivity 或 Retest plan。

### 14.4 PIT Blockers

下列情況原則上構成 Blocker：

- 使用未公開資料形成歷史訊號
- Availability rule 與 Specification 不一致
- OOS 期間在鎖定前已被用於規則調整
- 無法識別關鍵資料的公告／可用時間
- Dataset manifest 無法重建主要輸入

## 15. Universe, Survivorship, and Security Master Audit

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

## 16. Implementation and Numerical Audit

### 16.1 Code and Environment

至少驗證：

- Code Commit 與 Registry 一致
- Working tree 狀態
- Dependency lock
- Runtime and architecture
- Random seed
- Execution command
- Deterministic／non-deterministic behavior
- Config、Specification 與 code defaults 一致

### 16.2 Numerical Tests

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

### 16.3 Golden Cases

重要策略行為必須有小型人工可驗證 Golden Case：

- 固定少量股票
- 固定資料日期
- 明確手算 Signal、Rank、Weight、Order 與 Return
- 程式結果與人工結果逐欄比對

Golden Case 不用於證明策略有效，只用於證明實作符合規格。

### 16.4 Implementation Blockers

- Code behavior 與 Specification 不一致
- Hidden default 改變策略行為
- 交易成本或不可成交規則未執行
- 主要 Metric 無法重算
- 相同輸入無法在容忍度內重現

## 17. Leakage Audit

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

任何 confirmed material leakage 使受影響 Experiment `INELIGIBLE`，並觸發 Retest、Revise 或 Retire assessment。

## 18. Transaction Cost and Execution Realism Audit

### 18.1 Required Components

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

### 18.2 Cost Stress

除 Base Case 外，至少應有事前定義的 Cost Stress 情境：

- 較高滑價
- 較低成交率
- 訂單延遲
- 較低容量
- 市場壓力期流動性惡化

Stress 數值由 Strategy Specification 或 Experiment Plan 事前定義。

### 18.3 Tradability Blockers

- 策略大量依賴無法成交的漲跌停價格
- 使用停牌期間不存在的成交
- 低流動性部位超過事前容量限制
- 交易成本後主要 Gate 失效但仍使用 gross result Promote
- 未成交訂單被當成已成交

## 19. Historical Backtest Audit

### 19.1 Purpose

Historical Backtest 用於檢查策略假設在歷史樣本中的可操作表現，不代表未來有效。

### 19.2 Minimum Checks

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

### 19.3 Prohibited Conclusions

不得因下列單一結果 Promote：

- 高 CAGR
- 高 Sharpe
- 平滑 equity curve
- 某一牛市表現突出
- 少數個股貢獻大部分報酬
- 未扣成本的超額報酬

### 19.4 Exit Readiness

進入 Robustness Validation 至少要求：

- Historical Experiment evidence eligible
- 主要 Gate 可重算
- PIT、Universe、Cost 與 Implementation 無未解決 Blocker
- Multiple-testing family 已揭露
- Negative and null results 已保存
- Robustness plan 已事前註冊
- Required Reproduction check 已完成

## 20. Robustness Validation Protocol

### 20.1 Required Dimensions

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

### 20.2 Parameter Stability

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

### 20.3 Diagnostic Variant Boundary

任何改變 Signal、Universe、Entry／Exit、Portfolio Construction、Risk rule、Cost model 或其他正式行為的 diagnostic／sensitivity variant：

- 必須建立獨立 Experiment ID。
- 必須標記 `DIAGNOSTIC` 或 `EXPLORATORY` evidence classification。
- 不得自動取得 Confirmatory 或 OOS 資格。
- 不得靜默取代正式 Strategy Version。
- 若要成為正式規則，必須進入 Revise 與版本判定流程。

### 20.4 Economic Coherence

Robustness 不只是統計穩定，也要檢查：

- 結果是否符合原始經濟／行為邏輯
- 報酬是否集中在不符合假設的市場情境
- 主要收益是否來自未預期風險曝險
- 策略是否實際變成產業、規模、低流動性或市場 beta bet

若主要報酬機制與核准 Hypothesis 不一致，應進入 Revise assessment，而不是只視為參數問題。

### 20.5 Exit Readiness

進入 OOS 前至少要求：

- 事前要求的 robustness dimensions 已完成
- 主要結果不是單一參數、單一期間或少數股票驅動
- 成本與流動性 Stress 沒有否證可交易性
- 沒有 unresolved material data／implementation issue
- OOS Design Lock 已完成
- OOS 尚未被用於調整規則
- Required Reproduction 已完成

## 21. Multiple Testing and Data Snooping Audit

### 21.1 Family Registration

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

### 21.2 Required Review

Auditor 必須檢查：

- 是否只展示最佳 variant
- 是否在看過結果後改 Primary metric
- 是否重複使用同一樣本挑選規則
- 是否停止測試於有利結果
- 是否將探索性 variant 冒充 confirmatory
- 是否以大量嘗試提高偶然成功機率

### 21.3 Statistical Method

本文件不強制單一統計方法，但方法必須：

- 與資料結構及假設相容
- 事前定義或明確標記 exploratory
- 考慮 autocorrelation、cross-sectional dependence 或 non-normality，依適用性
- 對多重比較提供合理控制或解釋
- 提供估計不確定性，而非只報 point estimate

方法、版本、參數與假設必須保存於 Experiment Registry。

## 22. Out-of-Sample Audit

### 22.1 OOS Identity

必須保存：

- OOS window
- Lock time
- First access time
- Strategy／Config／Code／Data hashes at lock
- Accessed-before-lock status
- Contamination status
- Contamination reason
- Replacement holdout plan

### 22.2 OOS Cleanliness

Clean OOS 要求：

- 未參與假設形成
- 未用於參數或版本選擇
- 未用於 Gate 修改
- 未被重複查看直到滿意
- 使用鎖定的 Strategy behavior
- 使用相容的成本、PIT 與 tradability rules

### 22.3 Contamination

下列情況構成 confirmed contamination：

- 查看 OOS 後改 Signal、Universe、Weight、Entry／Exit 或 Risk rule
- 查看 OOS 後選擇 Strategy Version
- 查看 OOS 後改 Gate
- 反覆使用相同區間作為新版本 OOS

Confirmed-contaminated OOS：

- 必須永久保留。
- 只能作為 supplementary／diagnostic evidence。
- 不得滿足 clean-OOS promotion requirement。
- 不得單獨支持 Promote 至 Paper Trading。
- 不得重新命名為 clean OOS。
- 必須準備 replacement holdout、clean Walk-forward 或其他事前核准的獨立前瞻證據。

### 22.4 Qualified but Not Confirmed Contamination

只有在 contamination 尚未確認、影響範圍有限且有完整 Finding 時，才可標記 qualified evidence。

Qualified evidence：

- 不得隱藏 suspected contamination。
- Evidence Eligibility 必須依 Experiment Registry 降級。
- 是否可搭配其他 clean evidence，必須由事前 Validation Plan 與 locked Gate 明確允許。
- 不得用「已揭露」取代獨立 clean evidence requirement。

### 22.5 OOS Exit Readiness

進入 Paper Trading 至少要求：

- 至少一份可滿足 locked OOS Gate 的 clean OOS、clean Walk-forward test，或其他在 Validation Plan 事前明確定義的獨立前瞻證據
- 主要 OOS Gate 已評估
- 無未揭露 contamination
- Strategy、Config、Code 與 Data versions 一致
- 結果可重現
- Paper Trading plan and Campaign frozen manifest ready

Confirmed-contaminated OOS 不得單獨或主要支撐此 transition。

## 23. Walk-forward Audit

### 23.1 Fold Requirements

每一 fold 必須保存：

- Train／Validation／Test windows
- Purge／embargo
- Parameter selection output
- Frozen test config
- Fold metrics
- Fold artifacts
- Fold status
- Campaign manifest hash

### 23.2 Audit Checks

- Fold boundaries 不重疊或洩漏
- Test fold 未參與 selection
- 參數更新規則事前固定
- Failed fold 不得從 aggregation 消失
- 聚合權重與計算方式事前定義
- 可獨立引用的 fold 具有 child Experiment ID

不得只保存 aggregate performance。

## 24. Reproduction and Reproducibility Audit

### 24.1 Minimum Reproduction

Formal Promote 前，依第 11 節 matrix 與 Strategy Validation Plan 完成：

- Same-environment reproduction，或
- Independent-environment reproduction

至少比較：

- Input manifest
- Config hash
- Code behavior
- Metrics
- Holdings／orders，依適用性
- Gate outcomes
- Artifact hashes or semantic equivalence

### 24.2 Tolerances

Numerical tolerance 必須：

- 事前定義
- 與 floating-point、parallelism 或 stochastic behavior 相容
- 不得在看到差異後放寬以通過

### 24.3 Reproduction Failure

- 先判斷資料、環境、randomness 或 code version 差異。
- 保存差異 artifact。
- Material failure 阻止 Promote。
- 不得用新重跑結果覆蓋原 Experiment。

## 25. Paper Trading Audit

### 25.1 Purpose

Paper Trading 驗證前瞻資料到達、訊號形成、訂單模擬與營運流程，不只是觀察短期報酬。

### 25.2 Required Checks

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
- Operational Snapshot completeness

### 25.3 Campaign Drift

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

### 25.4 Exit Readiness

進入 Live Observation 至少要求：

- 最低期間與樣本要求已依 Strategy Plan 達成
- 資料與訊號流程穩定
- 主要市場限制被正確處理
- 無 unresolved operational Blocker
- 所有人工介入與偏離已揭露
- Paper evidence 沒有嚴重否證原假設
- Periodic review and revalidation triggers 已設定
- Required Reproduction 已完成

短期正報酬本身不得支持 Promote。

## 26. Live Observation Periodic Review

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

## 27. Benchmark Audit

至少檢查：

- Benchmark 是否符合市場、Universe、currency 與 return type
- Total return versus price return
- Reinvestment assumptions
- Calendar and timestamp alignment
- Tradability and cost asymmetry
- Benchmark selection 是否事前定義
- 是否選擇較弱 benchmark 美化結果

需要多 Benchmark 時，Primary benchmark 必須事前指定；其他為 supplementary。

## 28. Concentration, Regime, and Capacity Audit

### 28.1 Concentration

至少檢查：

- Top holdings contribution
- Top industries contribution
- Top periods contribution
- Single event contribution
- Exposure concentration
- Turnover concentration

### 28.2 Regime Dependence

Regime 必須事前定義或明確標記 exploratory。

不得使用事後最有利分段作為唯一證據。

至少檢查：

- 不同市場方向或波動環境
- 流動性壓力期
- 重大制度或結構變化
- 策略假設預期失效情境

### 28.3 Capacity

容量分析至少引用：

- Position size relative to traded value
- Participation assumptions
- Order delay
- Slippage／impact model
- Liquidity distribution
- Stress capacity

個人研究規模不代表可以忽略容量與可成交限制。

## 29. Gate Evaluation Protocol

### 29.1 Gate Source

數值 Gate 必須來自：

- Approved Strategy Specification
- Pre-registered Experiment Plan
- Versioned Acceptance Gate Contract

本文件不提供策略通用固定報酬率、Sharpe、Drawdown 或勝率門檻。

### 29.2 Gate Status

```text
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

### 29.3 Gate Audit

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

### 29.4 Gate Integrity

禁止：

- 看過結果後降低門檻
- 替換 Primary metric
- 只引用 favorable window
- 用 gross metric 通過 net Gate
- 把 missing evidence 當 PASS

Gate 未能證明時使用 `NOT_DEMONSTRATED`，不得默認通過。

## 30. Decision Mapping Protocol

Validation finding 不會自動產生決策，但應依下列原則準備 requested decision。

### 30.1 Promote

適用於：

- 當前 stage 必要 evidence 完整
- 事前 Gates 達成或有正式 Conditional Pass
- 無 unresolved Blocker
- 重要限制已揭露
- 下一階段輸入已準備

Promote 只表示進入下一研究階段。

### 30.2 Retest

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

### 30.3 Revise

適用於需要改變研究假設或正式策略行為，例如：

- Signal Formula
- Universe
- Entry／Exit
- Portfolio Construction
- Risk rule
- Acceptance Gate design
- Economic mechanism interpretation

Auditor 只指出 revision scope，不得直接修改規則。

### 30.4 Retire

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

### 30.5 Decision Escalation Matrix

| Finding nature | Default assessment |
|---|---|
| Data／code／PIT issue，策略行為不變 | Retest candidate |
| 缺少必要 stress／regime／reproduction | Retest candidate |
| 需要改正式策略規則 | Revise candidate |
| 核心假設與證據矛盾 | Revise or Retire candidate |
| 不可修復 leakage／PIT／tradability | Retire candidate |
| 當前 stage evidence complete and acceptable | Promote candidate |

這是審計起點，不是自動決策規則。

## 31. Conditional Pass

Conditional Pass 只可用於：

- 未完成項目不改變已觀察的主要證據完整性
- 條件、責任人、期限、驗證方法與失敗後果清楚
- 條件未達成前不會錯誤改變 Lifecycle State，依 Decision Snapshot effectivity mode

不得用 Conditional Pass 規避：

- Missing critical PIT evidence
- Confirmed material leakage
- Unresolved Blocker
- Incomplete OOS identity
- Confirmed OOS contamination used as primary promotion evidence
- Missing transaction cost model
- Unreproducible primary result
- Evidence Package not COMPLETE

## 32. Validation Finding Record

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

## 33. Validation Check Record

每個 Check 至少包含：

- `check_id`
- `validation_review_id`
- `check_category`
- `check_name`
- `check_version`
- `applicability_status`
- `applicability_reason`
- `method`
- `input_references`
- `expected_result`
- `actual_result`
- `outcome_status`
- `finding_ids`
- `artifact_ids`
- `executed_by`
- `executed_at`

`NOT_APPLICABLE` 必須有理由，不能用來跳過困難測試。

## 34. Validation Review Time Model

### 34.1 Registration Mode

```text
PROSPECTIVE
RETROSPECTIVE_BACKFILL
```

### 34.2 Prospective Review

必須保存：

- `registry_registered_at`
- `evidence_cutoff_at`
- `review_started_at`
- `review_completed_at`, when completed

時間規則：

```text
registry_registered_at ≤ review_started_at ≤ review_completed_at
evidence_cutoff_at ≤ review_started_at
```

`registry_registered_at` 與 `evidence_cutoff_at` 不要求彼此固定先後；Review 可以在資料截止時間之後才完成註冊，但不得使用 cutoff 後形成的 evidence。只對已存在的 applicable timestamps 檢查。

### 34.3 Retrospective Backfill

必須分開保存：

- `original_evidence_cutoff_at`, if known
- `original_review_started_at`, if known
- `original_review_completed_at`, if known
- `backfilled_at`
- `timestamp_source`
- `timestamp_precision`
- `timestamp_confidence`
- `source_document_ids`
- `original_authority_source`
- `original_outcome_source`

時間規則：

```text
original_review_started_at
≤ original_review_completed_at
≤ backfilled_at
```

若原始 evidence cutoff 可取得，必須不晚於原 Review started time。

Backfill：

- 不得偽造原始 evidence、authority、outcome 或秒級時間。
- 不得因補登提高 Evidence Readiness 或 Integrity。
- 不得直接改變 Current Lifecycle State。
- 不得建立新的 current Promote authority。
- 任何目前有效的治理決策，必須由新的 Prospective Decision Snapshot 確認。

## 35. Validation Review Record

每個正式 Review 至少包含：

### 35.1 Identity and Scope

- `validation_review_id`
- `schema_version`
- `registration_mode`
- `review_type`
- `strategy_id`, when applicable
- `strategy_version`, when applicable
- `lifecycle_stage`
- `review_scope`
- `evidence_package_id`
- `experiment_ids`

### 35.2 Authority

- `review_owner_workspace`
- `review_actor`
- `authority_basis`
- `authority_verified_at`

### 35.3 Time

依第 34 節保存 Prospective 或 Retrospective fields。

### 35.4 Status Axes

- `review_execution_status`
- `evidence_readiness_status`
- `validation_outcome_status`
- `audit_integrity_status`

### 35.5 Checks and Findings

- `required_check_ids`
- `completed_check_ids`
- `not_applicable_check_ids`
- `missing_required_check_ids`
- `finding_ids`
- `blocker_ids`
- `gate_evaluation_ids`
- `counter_evidence_summary`
- `known_limitations`

### 35.6 Decision and Integrity

- `requested_decision`
- `decision_record_id`, when completed
- `review_artifact_ids`
- `review_artifact_hash`
- `content_hash`
- `hash_algorithm`
- `supersedes_validation_review_id`, when applicable
- `amendment_ids`

## 36. Validation Amendment and Correction

### 36.1 Allowed Amendment Scope

Amendment 只允許修正不影響下列內容的 metadata／引用錯誤：

- Review scope
- Evidence cutoff
- Evidence Package contents
- Required or completed checks
- Finding substance or severity
- Validation outcome
- Audit Integrity
- Requested decision
- Decision linkage
- Authority
- Strategy or Experiment identity

允許範例：

- 拼字錯誤
- 不影響實體識別的顯示名稱
- 錯誤但可唯一確認的 URI label
- 非實質註解

### 36.2 Amendment Record

每筆 Amendment 至少包含：

- `validation_amendment_id`
- `validation_review_id`
- `field_path`
- `old_value`
- `new_value`
- `reason`
- `actor`
- `amended_at`
- `materiality = IMMATERIAL`
- `source_reference`

### 36.3 Material Change

任何涉及下列項目的變更，必須建立新 Validation Review ID：

- Scope
- Evidence cutoff
- Evidence Package
- Check applicability or result
- Finding category、severity、materiality or conclusion
- Validation outcome
- Evidence readiness
- Audit integrity
- Requested decision
- Authority
- Strategy／Experiment identity
- Review artifact hash

新 Review 必須：

- 引用原 Review。
- 使用新 Evidence Package ID，若 evidence 有變。
- 保存 `SUPERSEDES` 或 `REPLACES_AFTER_CORRECTION` relationship。
- 不得覆蓋原 Review。

## 37. Invalidation and Downstream Impact

當上游 Experiment、Dataset、Feature、Code、Config、Policy、Calendar、Gate 或 Evidence Package 被 invalidated：

1. 查詢全部 dependency edges。
2. 建立 `POTENTIALLY_AFFECTED` impact。
3. 暫停把受影響 Promote 顯示為無條件 current approval。
4. 評估 materiality 與 bias direction。
5. 更新為 `UNAFFECTED`、`AFFECTED` 或 `INVALIDATED`。
6. 對 material downstream 繼續遞迴傳遞。
7. 建立或更新 Validation Impact 與 Decision Impact。
8. 判斷 Retest、Revise 或 Retire。

不得只修正上游資料後，維持下游 Decision 看起來完全有效。

## 38. Canonical Storage and Query Model

### 38.1 Storage Collections

工程實作至少支援：

```text
validation_reviews
evidence_packages
evidence_package_versions
validation_checks
validation_findings
validation_amendments
validation_relationships
validation_events
validation_artifacts
validation_impacts
review_check_requirements
```

### 38.2 Required Constraints

至少包括：

- IDs unique and immutable
- No hard delete for formal records
- Append-only events
- Timestamp with timezone
- Enum validation
- Hash validation
- Foreign-key or equivalent integrity
- Registration-mode-specific time validation
- Cross-status consistency validation
- Evidence Package immutability
- Review Type × Check applicability validation
- Required checks completion validation
- Promote readiness validation
- OOS contamination promotion restriction
- Amendment scope validation
- Decision linkage validation

### 38.3 Query Requirements

系統至少支援：

- 依 Strategy ID／Version 查詢全部 Reviews
- 查詢 Review 的 frozen Evidence Package
- 查詢 Required／Completed／Missing checks
- 查詢全部 unresolved Blockers
- 查詢 Backfilled Reviews 與來源可信度
- 查詢 OOS contamination 與 replacement evidence
- 查詢 Multiple-testing family 的全部 variants
- 查詢 Reproduction lineage
- 查詢 invalidation 的 downstream Review／Experiment／Decision path
- 重建 Review、Checks、Findings、Gates、Artifacts 與 Decision linkage

## 39. Validation Artifact Requirements

至少保存適用的：

- Review manifest
- Evidence Package manifest
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

## 40. Reporting Requirements

正式 Validation Report 至少顯示：

- Strategy ID／Version
- Lifecycle stage
- Review ID and type
- Registration mode
- Evidence cutoff
- Evidence Package ID and completeness
- Experiment IDs
- Version manifest summary
- Evidence readiness
- Review outcome
- Audit integrity
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

## 41. Prohibited Practices

TWStock 禁止：

- 以單次高報酬取代完整驗證
- 在看過結果後修改 Gate 並宣稱原實驗通過
- 刪除失敗、負結果或不利 Regime
- 用目前存活股票回測全部歷史
- 使用未公開資料形成歷史訊號
- 把修訂後資料回填成原始可得資料
- 把 In-Sample 或反覆查看樣本稱為 OOS
- 用 confirmed-contaminated OOS 滿足 clean-OOS promotion requirement
- 只保存最佳參數
- 隱藏 multiple-testing family
- 忽略交易成本、未成交、停牌、下市或市場限制
- 把 gross result 當成 net Gate evidence
- 用 Run Attempt 覆蓋新 Experiment requirement
- 用 Amendment 補入新 evidence 或改變 Review outcome
- 用 Backfill 建立 current Lifecycle authority
- Auditor 自行修改策略規則
- 工程或自動系統自行 Promote／Retire
- 讓 Conditional Pass 規避 Blocker
- 讓 invalidated evidence 繼續支持無條件 current approval
- 將 Historical Backtest 描述為未來獲利保證

## 42. Canonical YAML Examples

### 42.1 Evidence Package

```yaml
evidence_package_id: EVP-01J2EVIDENCE001
schema_version: 1.0.0
registration_mode: PROSPECTIVE
package_type: HISTORICAL_BACKTEST_EVIDENCE
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
lifecycle_stage: HISTORICAL_BACKTEST
review_type: HISTORICAL_BACKTEST_AUDIT
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
created_at: 2026-07-10T20:05:00+08:00
created_by: evidence-builder
version_manifest:
  specification_version: 1.0.0
  config_version: 1.0.0
  config_hash: sha256:config
  code_commit_sha: abcdef1234567890
  code_behavior_version: 1.0.0
  dataset_manifest_ids:
    - DSM-20260710-001
  pit_policy_version: 1.0.0
  exchange_calendar_version: 1.0.0
  transaction_model_version: 1.0.0
experiment_ids:
  - EXP-20260710-01J2BASELINE
artifact_ids:
  - ART-REPORT-001
gate_evaluation_ids:
  - GATE-EVAL-001
required_item_count: 12
present_item_count: 12
missing_items: []
completeness_status: COMPLETE
content_hash: sha256:evidence
hash_algorithm: SHA-256
```

### 42.2 Prospective Validation Review

```yaml
validation_review_id: VAL-20260710-01J2VALIDATE001
schema_version: 1.0.0
registration_mode: PROSPECTIVE
review_type: HISTORICAL_BACKTEST_AUDIT
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
lifecycle_stage: HISTORICAL_BACKTEST
review_scope: formal baseline historical audit
registry_registered_at: 2026-07-10T20:10:00+08:00
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
review_started_at: 2026-07-10T20:30:00+08:00
review_completed_at: null
evidence_package_id: EVP-01J2EVIDENCE001
experiment_ids:
  - EXP-20260710-01J2BASELINE
review_owner_workspace: workspace-04
review_actor: human-auditor
authority_basis: TWSTOCK-RESEARCH-LIFECYCLE-001@1.0.0
review_execution_status: IN_PROGRESS
evidence_readiness_status: READY
validation_outcome_status: NOT_ASSESSED
audit_integrity_status: NOT_ASSESSED
required_check_ids:
  - CHK-PIT-001
  - CHK-SURVIVORSHIP-001
  - CHK-LEAKAGE-001
  - CHK-COST-001
  - CHK-REPRO-001
completed_check_ids: []
not_applicable_check_ids: []
missing_required_check_ids:
  - CHK-PIT-001
  - CHK-SURVIVORSHIP-001
  - CHK-LEAKAGE-001
  - CHK-COST-001
  - CHK-REPRO-001
finding_ids: []
blocker_ids: []
gate_evaluation_ids: []
requested_decision: null
decision_record_id: null
review_artifact_ids: []
review_artifact_hash: null
```

### 42.3 Retrospective Backfill Review

```yaml
validation_review_id: VAL-20260710-01J2BACKFILL
schema_version: 1.0.0
registration_mode: RETROSPECTIVE_BACKFILL
review_type: HISTORICAL_BACKTEST_AUDIT
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 0.9.0
lifecycle_stage: HISTORICAL_BACKTEST
evidence_package_id: EVP-01J2LEGACY
original_evidence_cutoff_at: null
original_review_started_at: 2025-12-20T09:00:00+08:00
original_review_completed_at: 2025-12-20T11:00:00+08:00
backfilled_at: 2026-07-10T22:00:00+08:00
timestamp_source: archived-review-note
timestamp_precision: MINUTE
timestamp_confidence: MODERATE
source_document_ids:
  - DOC-LEGACY-20251220
original_authority_source: archived-signoff
original_outcome_source: archived-review-note
review_execution_status: COMPLETED
evidence_readiness_status: READY_WITH_LIMITATIONS
validation_outcome_status: NOT_DEMONSTRATED
audit_integrity_status: COMPROMISED
requested_decision: null
decision_record_id: null
may_mutate_current_lifecycle_state: false
```

### 42.4 Metadata Amendment

```yaml
validation_amendment_id: VAM-01J2TYPOFIX
validation_review_id: VAL-20260710-01J2VALIDATE001
field_path: display_title
old_value: Historial Backtest Audit
new_value: Historical Backtest Audit
reason: typographical correction
actor: registry-admin
amended_at: 2026-07-10T22:30:00+08:00
materiality: IMMATERIAL
source_reference: PR-7
```

## 43. Validation Rules

1. Formal Review must have a unique immutable Review ID.
2. Review scope and evidence cutoff must be frozen before outcome assessment.
3. Evidence Package must have a unique immutable ID and content hash.
4. Evidence Package linked to a Review cannot be overwritten.
5. Missing core versions makes Evidence Package `PARTIAL` or `INSUFFICIENT`.
6. Evidence Package not `COMPLETE` cannot support Promote.
7. Review Type must use the versioned Required Check Matrix.
8. Every `REQUIRED` Check must be completed before a terminal Pass outcome.
9. `NOT_APPLICABLE` Check requires a reason.
10. Non-terminal Review cannot have terminal outcome or Decision ID.
11. `NOT_READY` cannot pair with Pass／Conditional Pass／Promote.
12. Unresolved Blocker prevents Pass、Conditional Pass and Promote.
13. Compromised or Invalidated Audit cannot support Promote.
14. Formal Promote requires Verified Audit Integrity.
15. Strategy-specific Gate values must come from a pre-locked version.
16. Gate changes after result access require a new Experiment and applicable Strategy revision.
17. Confirmed material PIT error makes affected evidence ineligible pending Retest.
18. Confirmed material leakage makes affected evidence ineligible.
19. Historical Universe must include delisted and otherwise failed securities when applicable.
20. Gross performance cannot satisfy a net-performance Gate.
21. Failed or unfilled orders cannot be treated as fills.
22. All independently evaluated parameter variants must remain visible.
23. Diagnostic variants require a separate Experiment ID and cannot inherit Confirmatory／OOS classification.
24. Multiple-testing family must be registered and auditable.
25. OOS accessed before lock cannot remain CLEAN.
26. Confirmed-contaminated OOS cannot satisfy clean-OOS promotion requirement.
27. Promote to Paper Trading requires independent clean forward evidence defined before access.
28. Walk-forward aggregation cannot hide failed folds.
29. Material reproduction failure blocks Promote.
30. Paper Trading version drift terminates the old Campaign.
31. Operational Snapshot with manifest mismatch cannot enter formal Campaign performance.
32. Retest requires a new Experiment ID.
33. Revise must return strategy-rule decisions to workspace 01 or 02.
34. Retire must specify VERSION or LINEAGE scope.
35. Invalidation must propagate through dependency, Validation Impact and Decision Impact records.
36. Backfilled Review or Evidence Package cannot fabricate original evidence, timing, authority, completeness or outcome.
37. Backfilled Review cannot mutate current lifecycle state.
38. Amendment can change only immaterial metadata.
39. Material Review change requires a new Review ID.
40. Formal records and artifacts cannot be hard-deleted.

## 44. Engineering Acceptance Criteria

第一版 Validation Engine／Registry integration 至少達成：

- [ ] Validation Review、Evidence Package、Check、Finding 與 Amendment 分開儲存。
- [ ] Review ID、Package ID、Finding ID、Check ID 與 Amendment ID 唯一且不可重用。
- [ ] Review scope and evidence cutoff 可被鎖定。
- [ ] Evidence Package 可以 hash、freeze 與重建。
- [ ] Evidence completeness 可機器驗證。
- [ ] Review Type × Required Check Matrix 可機器驗證。
- [ ] Cross-status rules 阻止矛盾組合。
- [ ] Missing core evidence 阻止 Promote readiness。
- [ ] PIT、Leakage、Numerical、Cost、Tradability 與 Reproduction checks 可追蹤。
- [ ] Findings 保存 severity、materiality 與 bias direction。
- [ ] Unresolved Blocker 阻止 Pass／Conditional Pass／Promote。
- [ ] Gate 只能引用事前鎖定版本。
- [ ] Multiple-testing family、variants 與 negative results 可查詢。
- [ ] OOS contamination 可標記並阻止 clean promotion claim。
- [ ] Walk-forward fold 不會被 aggregate 隱藏。
- [ ] Paper Campaign manifest drift 可偵測。
- [ ] Diagnostic Variant 強制新 Experiment ID。
- [ ] Retest 強制新 Experiment ID。
- [ ] Revise、Retest、Retire handoff scope 可生成。
- [ ] Backfill 使用獨立時間與來源模型。
- [ ] Backfill 不會改變 current lifecycle state。
- [ ] Amendment 不可加入新 evidence 或改變 outcome。
- [ ] Invalidation 可傳遞到 downstream Review、Experiment and Decision。
- [ ] Validation Report 可重建全部 evidence、checks、findings、gates and limitations。
- [ ] Formal artifact hash 不可靜默覆寫。
- [ ] Failed、Aborted、Invalidated、Retired reviews 永久保存。

## 45. Manual Acceptance Tests

### Test A: Missing Core Version

Given：Historical Backtest 缺少 Dataset Manifest Version。

Expected：Evidence Package 為 `PARTIAL` 或 `INSUFFICIENT`，Review `NOT_READY`，不得形成 Promote Decision。

### Test B: Non-terminal Pass

Given：Review 為 `IN_PROGRESS`，但 outcome 嘗試設為 `PASS`。

Expected：寫入被拒絕。

### Test C: Not-ready Promote

Given：Review 為 `NOT_READY`，requested decision 為 `PROMOTE`。

Expected：寫入被拒絕。

### Test D: Future Data Leakage

Given：月營收資料在公告前即被用於形成訊號。

Expected：建立 BLOCKER Finding，受影響 Experiment ineligible，要求 invalidation and Retest。

### Test E: Survivorship Bias

Given：歷史 Universe 只包含目前仍上市股票。

Expected：審計失敗，要求重建 Security Master／Universe and Retest。

### Test F: Gross Versus Net

Given：gross performance 通過，但 net performance 未通過事前 Gate。

Expected：不得 Promote；Gate 依 net metric 評估。

### Test G: Unfilled Order

Given：跌停或停牌股票的訂單被當成成交。

Expected：交易結果不符合 Execution Model，要求 Retest。

### Test H: Narrow Parameter Peak

Given：只有單一孤立參數點產生高績效，鄰近參數失效。

Expected：建立 overfitting finding，阻止直接 Promote，要求 robustness／Revise assessment。

### Test I: Hidden Variants

Given：Batch 測試 50 個 variants，只報告最佳 3 個。

Expected：Review 失敗；要求完整 family、failed and unexecuted variants。

### Test J: Diagnostic Variant Reuses Formal Experiment

Given：Robustness 改變持股數，仍沿用原 Experiment ID 並聲稱 confirmatory。

Expected：拒絕；建立新 Diagnostic Experiment ID，且不得繼承 confirmatory classification。

### Test K: Confirmed OOS Contamination

Given：查看 OOS 後調整 Universe，仍嘗試 Promote 至 Paper Trading。

Expected：OOS 標記 confirmed contamination，不得滿足 promotion requirement；要求 replacement clean forward evidence。

### Test L: Reproduction Failure

Given：相同版本與輸入無法在事前 tolerance 內重現主要 Metric。

Expected：material finding 阻止 Promote，要求 root-cause and Retest。

### Test M: Walk-forward Failed Fold

Given：一個 fold 失敗但 aggregate report 排除該 fold。

Expected：聚合結果不得接受；failed fold 必須顯示並重新評估。

### Test N: Paper Campaign Drift

Given：Paper Trading 途中 Code Behavior Version 改變。

Expected：終止舊 Campaign，建立新 Campaign、new frozen manifest and formal Experiment。

### Test O: Auditor Rule Change

Given：Auditor 為讓結果通過而修改持股數。

Expected：拒絕；Auditor 建立 Revise finding 並交回 workspace 01／02。

### Test P: Retest Reuses Experiment ID

Given：資料修正後重跑仍使用舊 Experiment ID。

Expected：寫入或審計被拒絕，必須建立新 Experiment ID。

### Test Q: Upstream Invalidation

Given：主要 Dataset 被 invalidated，已有多個 downstream Promote Decisions。

Expected：建立 Validation and Decision impacts，暫停無條件 approval display，逐一重新審計。

### Test R: Conditional Pass with Blocker

Given：存在 confirmed material leakage，但 Review 嘗試 Conditional Pass。

Expected：拒絕 Conditional Pass；必須 Retest、Revise or Retire assessment。

### Test S: Backfill Mutates Current State

Given：歷史 Review 補登後嘗試直接改變 current lifecycle state。

Expected：拒絕；必須建立新的 Prospective Decision。

### Test T: Material Amendment

Given：Amendment 嘗試加入新 Experiment evidence 並把 FAIL 改成 PASS。

Expected：拒絕；必須建立新 Evidence Package、新 Validation Review ID 與 relationship。

## 46. Revision Policy

下列變更需要建立本文件新版本並經 Pull Request 審查：

- Formal validation authority
- Review Types
- Status axes and cross-status rules
- Evidence Package Schema
- Review Type × Required Check Matrix
- Finding severity or materiality
- Universal validation sequence
- PIT／Leakage minimum checks
- Historical／Robustness／OOS／Paper protocols
- Gate integrity rules
- Decision mapping
- Backfill and Amendment rules
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

## 47. Core Governance Baseline Completion

本文件合併後，下列核心治理基準即告完成：

1. System Vision
2. Research Principles
3. Point-in-Time Policy
4. Strategy Lifecycle
5. Experiment Registry Schema
6. Decision Snapshot Schema
7. Validation Protocol

核心治理基準完成不代表平台或策略已完成，也不代表任何策略已被驗證。

## 48. Minimum Remaining Markdown Roadmap to First Vertical Slice

為避免過度文件化，完成第一個可執行、可回測、可審計的「月營收／盈餘動能策略」前，只再建立下列 **6 份必要 Markdown**：

1. `docs/data/DATA_CONTRACT_STANDARD.md`
2. `docs/architecture/THIN_WEBSITE_INFORMATION_ARCHITECTURE.md`
3. `docs/architecture/FOUNDATION_ENGINE_ARCHITECTURE.md`
4. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/RESEARCH_PROPOSAL.md`
5. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/EXECUTABLE_SPECIFICATION.md`
6. `docs/strategies/TW-M03-MONTHLY-REVENUE-MOMENTUM/VALIDATION_PLAN.md`

其他內容優先採：

- Dataset contracts：YAML／JSON machine-readable contracts
- Strategy Config：YAML
- Check applicability matrix：YAML／JSON
- Engineering work：GitHub Issues and Pull Requests
- Experiment results：Registry records and artifacts
- Formal decisions：Decision Snapshots

不應先替所有 Strategy Modes 建立大量空白 Markdown。第一個垂直切片完成並通過審計後，再依實際需求新增其他 Strategy Proposal、Specification 與 Validation Plan。

## 49. Next Document

本文件合併後，下一份正式文件為：

```text
docs/data/DATA_CONTRACT_STANDARD.md
```

之後才進入 Thin Website Information Architecture、Foundation Engine Architecture 與第一個策略垂直切片。
