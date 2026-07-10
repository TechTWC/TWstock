# TWStock Experiment Registry Schema

- Document ID: `TWSTOCK-RESEARCH-EXPERIMENT-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock exploratory studies, data and feature experiments, implementation verification, historical backtests, robustness tests, Out-of-Sample tests, reproductions, Retests, Paper Trading campaigns, failed runs, invalidated evidence, and related artifacts

## 1. Purpose

本文件定義 TWStock 如何建立、保存、查詢、重現、稽核與連結每一項研究實驗。

Experiment Registry 的核心目的不是只保存績效數字，而是永久回答：

- 為什麼執行這項實驗？
- 實驗在執行前承諾了哪些規則？
- 使用哪一個 Strategy、Specification、Config、Code、Data 與 Feature 版本？
- 哪些樣本被用於探索、驗證、OOS 或前瞻測試？
- 實際執行了什麼？
- 產生了哪些結果、錯誤、警告與 artifacts？
- 結果是否可重現？
- 是否存在 Point-in-Time、資料、程式、交易或 OOS 污染問題？
- 此實驗是否仍可作為正式證據？
- 它和先前實驗、Retest、Reproduction、Strategy Version、Campaign 與 Decision Record 有何關係？

核心原則是：

> 每一次可獨立評估的正式研究執行，都必須留下不可靜默刪除、不可重複使用 ID、可追蹤版本、可重建輸入、可驗證輸出與可解釋證據狀態的永久紀錄。

本文件不判定任何策略有效，也不授權真實資金交易。

## 2. Authority and Relationship to Other Documents

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`
4. `docs/research/STRATEGY_LIFECYCLE.md`

本文件將由以下文件進一步具體化：

- `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
- `docs/research/VALIDATION_PROTOCOL.md`
- Dataset-specific Data Contracts
- Strategy-specific Executable Specifications
- Strategy YAML Configs
- Engineering storage and API contracts

權限邊界：

- Experiment Registry 負責保存事實、狀態、版本、依賴與證據關係。
- Registry 不得自行把結果解讀為策略有效。
- `04｜台股策略驗證與審計`依 Evidence Package 作出正式 Promote、Revise、Retest 或 Retire 決策。
- Decision Record 可以引用 Registry；不得反向改寫原始實驗結果。
- 若網站、報告或聊天內容與 Registry 的版本化紀錄衝突，以 Registry、事件紀錄與原始 artifacts 為準。

## 3. Scope

本政策適用於：

- Exploratory research
- Data profiling and data-quality experiments
- Feature validation
- Leakage tests
- Numerical tests
- Implementation verification
- Historical Backtest
- Robustness Validation
- Sensitivity tests
- Diagnostic Variants
- Out-of-Sample tests
- Walk-forward tests
- Reproduction experiments
- Retests
- Paper Trading campaigns
- Live Observation research runs
- Failed, aborted, cancelled, invalidated, non-reproducible and superseded experiments

本文件不直接定義：

- 策略投資假設
- Strategy acceptance thresholds
- 特定資料庫產品
- 真實資金配置
- 券商串接或自動下單

## 4. Core Registry Principles

### 4.1 One Independently Evaluable Execution, One Experiment ID

每一個可被獨立檢視、比較、引用或審計的研究執行，必須使用獨立 Experiment ID。

即使 Strategy Version、Config、Code、Data、期間與參數完全相同，正式重新執行也不得覆蓋舊 Experiment ID。

### 4.2 Containers Do Not Replace Experiments

Family、Batch 與 Campaign 只負責分組與協調，不得取代子實驗紀錄。

禁止只保存 Batch 或 Campaign 聚合績效而遺失：

- 個別參數變體
- 失敗變體
- Walk-forward fold
- 被取消或未執行的 planned variant
- 個別狀態、警告與 artifacts

### 4.3 Append-only History

Experiment Registry 必須採 append-only audit model。

允許：

- 增加狀態事件
- 增加 artifact
- 增加 audit finding
- 增加 dependency impact
- 增加 invalidation 或 supersession 關係
- 修正 metadata 並保留 correction event

禁止：

- 刪除失敗實驗
- 覆蓋原始結果
- 靜默修改事前規格
- 把 invalidated 實驗改寫成從未發生
- 用新結果取代舊 Experiment ID

### 4.4 Separate Execution from Evidence

「程式有跑完」不等於「結果可作為證據」。Registry 必須分開保存：

- Execution Status
- Design Lock Status
- Evidence Eligibility Status
- Integrity Status
- Reproducibility Status
- Supersession Status
- OOS Contamination Status
- Dependency Impact Status
- Gate Results
- Formal Decision Reference

不得使用單一 `status` 欄位混合上述語意。

### 4.5 Preserve Negative and Null Results

結果不顯著、落後 Benchmark、成本後失效、OOS 失效、無法交易或執行失敗，都必須保存。

### 4.6 Inputs Must Be Reconstructable

依實驗性質，每個正式實驗必須能重建適用的：

- Strategy behavior
- Data snapshot
- PIT rules
- Feature calculation
- Test window
- Cost assumptions
- Randomness
- Code and environment
- Execution command

若不能重建，必須降低 Evidence Eligibility 或標記 Non-reproducible。

## 5. Canonical Research Unit Hierarchy

Registry 必須明確區分以下層級。

### 5.1 Experiment Family

`experiment_family_id` 代表同一研究問題、同一多重假設家族或同一策略研究 lineage 下的一組實驗。

Family 可以包含探索、確認性、OOS、Retest 與 Reproduction，但不具有自己的證據資格；證據資格屬於個別 Experiment。

### 5.2 Campaign

`campaign_id` 代表跨多次觀察或多個子實驗的持續性研究計畫，例如：

- Walk-forward campaign
- Paper Trading campaign
- Live Observation campaign

Campaign 必須保存其固定版本、開始時間、結束時間、子實驗與 Observation 清單。

### 5.3 Batch

`batch_id` 代表一次協調執行的參數網格或變體集合。

Batch 只是執行容器。每個可獨立比較的參數變體必須有獨立 Experiment ID。

### 5.4 Experiment

`experiment_id` 代表一個輸入、設計、版本與輸出可獨立評估的研究執行。

### 5.5 Run Attempt

`run_attempt_id` 代表同一 Experiment 的純技術執行嘗試。

Run Attempt 只適用於：

- 基礎設施中斷
- Worker crash
- 網路中斷
- 尚未產生研究輸出且輸入完全未變的技術重試

若研究輸出已產生、結果已被查看或任何輸入改變，重新執行必須建立新 Experiment ID。

### 5.6 Fold

`fold_id` 代表 Walk-forward campaign 中的一個 Train／Validation／Test 切分。

每個 fold 至少必須有獨立 input manifest、frozen test config、metrics、artifacts 與狀態。

若 fold 會被獨立引用、比較或作為 Decision Evidence，該 fold 必須同時建立 child Experiment ID；否則可以保存為 campaign 下的 fold subrecord。

### 5.7 Observation

`observation_id` 代表 Paper Trading 或 Live Observation campaign 中一次訊號週期、Decision Snapshot 或操作事件。

Observation 不等於 Experiment。當 Strategy、Config、Code behavior、Data Contract 或 Execution Model 改變時，必須終止原 Campaign 並建立新 Campaign 與新正式 Experiment。

## 6. Identity Rules

### 6.1 Experiment ID

Experiment ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 不依賴可變更名稱
- 可安全作為資料庫主鍵與 artifact path

建議格式：

```text
EXP-{YYYYMMDD}-{ULID}
```

### 6.2 Container IDs

建議格式：

```text
FAM-{ULID}
CAM-{ULID}
BAT-{ULID}
{experiment_id}-RUN-{NNN}
{campaign_id}-FOLD-{NNN}
{campaign_id}-OBS-{ULID}
```

### 6.3 New Experiment ID Triggers

下列行為必須建立新 Experiment ID：

- 改變研究參數
- 改變資料版本或 manifest
- 改變 Code Commit 或執行行為
- 改變 Config 或 Feature Version
- 改變測試期間
- 改變成本、滑價或執行模型
- 改變 Universe 或 Tradability rules
- 修正會影響結果的程式錯誤
- 重新執行已產生研究輸出的實驗
- Retest
- Reproduction
- Diagnostic Variant
- 參數 Batch 中的每個可獨立評估變體

## 7. Classification Axes

### 7.1 Research Subject Type

`research_subject_type`：

```text
STRATEGY
DATASET
FEATURE
ENGINE
POLICY
MARKET_EVENT
OTHER
```

### 7.2 Execution Mode

`execution_mode`：

```text
COMPUTATIONAL
MANUAL_REVIEW
DATA_INSPECTION
EXTERNAL_REPRODUCTION
HYBRID
```

### 7.3 Registration Mode

`registration_mode`：

```text
PROSPECTIVE
RETROSPECTIVE_BACKFILL
```

`RETROSPECTIVE_BACKFILL` 不得具有偽造的事前 Design Lock。

### 7.4 Lifecycle Stage

`lifecycle_stage`：

```text
IDEA
HYPOTHESIS
SPECIFICATION
ENGINEERING_TRANSLATION
IMPLEMENTATION
HISTORICAL_BACKTEST
ROBUSTNESS_VALIDATION
OUT_OF_SAMPLE
PAPER_TRADING
LIVE_OBSERVATION
```

正式計算型 Experiment 通常從 `IMPLEMENTATION` 或 `HISTORICAL_BACKTEST` 開始。

### 7.5 Experiment Purpose

`experiment_purpose`：

```text
EXPLORATORY
DATA_QUALITY
FEATURE_VALIDATION
NUMERICAL_TEST
LEAKAGE_TEST
IMPLEMENTATION_VERIFICATION
HISTORICAL_BACKTEST
ROBUSTNESS
SENSITIVITY
DIAGNOSTIC_VARIANT
OUT_OF_SAMPLE
WALK_FORWARD
REPRODUCTION
RETEST
PAPER_TRADING
LIVE_OBSERVATION
```

### 7.6 Evidence Classification

`evidence_classification`：

```text
NON_EVIDENTIARY
EXPLORATORY
DEVELOPMENT
CONFIRMATORY_IN_SAMPLE
VALIDATION
OUT_OF_SAMPLE
FORWARD_PAPER
FORWARD_OBSERVATION
```

### 7.7 Sample Role

`sample_role`：

```text
NOT_APPLICABLE
EXPLORATORY_SAMPLE
IN_SAMPLE
VALIDATION_SAMPLE
OUT_OF_SAMPLE
ROLLING_TRAIN
ROLLING_VALIDATION
ROLLING_TEST
PAPER_FORWARD
LIVE_FORWARD
```

### 7.8 Experiment Scope

`experiment_scope`：

```text
SINGLE_EXPERIMENT
CHILD_EXPERIMENT
```

Batch 與 Campaign 不得再冒充 Experiment Scope；它們使用獨立 `batch_id` 或 `campaign_id`。

## 8. Field Applicability Model

每個欄位對每種實驗目的必須使用下列適用值之一：

```text
REQUIRED
WHEN_APPLICABLE
NOT_APPLICABLE
PROHIBITED_NULL
```

- `REQUIRED`：該類型必須提供。
- `WHEN_APPLICABLE`：符合明確條件時必須提供。
- `NOT_APPLICABLE`：允許明確記錄 N/A，不得虛構值。
- `PROHIBITED_NULL`：該欄位屬核心主鍵或狀態，不得為 null。

### 8.1 Base Fields for All Experiments

所有 Experiment 均必須包含：

- Experiment identity
- Purpose and subject type
- Registration mode
- Execution mode
- Ownership
- Registered timestamp
- Execution status
- Evidence eligibility status
- Integrity status
- Reproducibility status
- Artifact or evidence references
- Event history

### 8.2 Purpose Applicability Matrix

| Field group | Strategy performance experiment | Data quality | Feature validation | Numerical / leakage test | Implementation verification | Manual review |
|---|---|---|---|---|---|---|
| Strategy ID / Version | REQUIRED | NOT_APPLICABLE unless strategy-scoped | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Specification / Config | REQUIRED | NOT_APPLICABLE unless strategy-scoped | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
| Code / Environment | REQUIRED | REQUIRED if computational | REQUIRED if computational | REQUIRED if computational | REQUIRED | NOT_APPLICABLE unless tools used |
| Dataset manifest | REQUIRED | REQUIRED | REQUIRED | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Feature versions | REQUIRED when features used | NOT_APPLICABLE | REQUIRED | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
| PIT policy / availability | REQUIRED | REQUIRED for time-sensitive data | REQUIRED for time-sensitive data | REQUIRED for PIT/leakage tests | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Transaction model | REQUIRED when trading performance evaluated | NOT_APPLICABLE | NOT_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
| Benchmark | REQUIRED when comparative performance evaluated | NOT_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE |
| Design lock | REQUIRED for formal confirmatory/OOS/robustness/Paper | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |

不得為了通過 Schema 而替非策略實驗虛構 Strategy ID、Config、Feature 或交易成本。

## 9. Status Axes

### 9.1 Execution Status

```text
PLANNED
QUEUED
RUNNING
COMPLETED
FAILED
ABORTED
CANCELLED
```

主要轉移：

```text
PLANNED → QUEUED → RUNNING → COMPLETED
PLANNED → CANCELLED
QUEUED → CANCELLED
RUNNING → FAILED
RUNNING → ABORTED
```

`COMPLETED` 不得回到 `RUNNING`。

### 9.2 Design Lock Status

```text
DRAFT
LOCKED_BEFORE_EXECUTION
EXECUTED_WITHOUT_LOCK
LOCK_BROKEN
NOT_APPLICABLE
```

### 9.3 Evidence Eligibility Status

```text
NOT_ASSESSED
ELIGIBLE
PROVISIONAL
RESTRICTED
INELIGIBLE
```

### 9.4 Integrity Status

```text
NOT_ASSESSED
VERIFIED
INVALIDATED
```

### 9.5 Reproducibility Status

```text
NOT_TESTED
REPRODUCIBLE
PARTIALLY_REPRODUCIBLE
NON_REPRODUCIBLE
NOT_APPLICABLE
```

### 9.6 Supersession Status

```text
CURRENT
SUPERSEDED
NOT_APPLICABLE
```

Superseded 不等於 Invalidated。

### 9.7 OOS Contamination Status

```text
NOT_APPLICABLE
CLEAN
SUSPECTED
CONFIRMED
```

### 9.8 Dependency Impact Status

```text
UNAFFECTED
POTENTIALLY_AFFECTED
AFFECTED
UNDER_REVIEW
INVALIDATED
```

Dependency Impact 是針對上游 defect 或 invalidation 的影響，不得和 Integrity Status 混為一談。

## 10. Cross-status Consistency Rules

### 10.1 Eligibility Preconditions

`evidence_eligibility_status = ELIGIBLE` 只有在全部適用條件成立時才允許：

- `execution_status = COMPLETED`
- `integrity_status = VERIFIED`
- 正式需鎖定的實驗為 `design_lock_status = LOCKED_BEFORE_EXECUTION`
- 沒有 unresolved `BLOCKER`
- 必要版本、manifest、metrics 與核心 artifacts 完整
- `dependency_impact_status` 不得為 `AFFECTED`、`UNDER_REVIEW` 或 `INVALIDATED`
- OOS 實驗不得為 `SUSPECTED` 或 `CONFIRMED`
- `reproducibility_status` 不得為 `NON_REPRODUCIBLE`

### 10.2 Non-terminal Execution

`PLANNED`、`QUEUED`、`RUNNING` 的 Evidence Eligibility 必須為 `NOT_ASSESSED`。

### 10.3 Failed Execution

`FAILED`、`ABORTED`、`CANCELLED` 不得為 `ELIGIBLE`。若已有部分可用輸出，最多標記 `RESTRICTED`，並明確限制範圍。

### 10.4 Broken or Missing Design Lock

對必須事前鎖定的實驗：

- `EXECUTED_WITHOUT_LOCK`：Evidence Eligibility 不得高於 `PROVISIONAL`。
- `LOCK_BROKEN`：Evidence Eligibility 必須為 `INELIGIBLE`，除非僅為不影響研究結果的 metadata correction 且有審計紀錄。

### 10.5 Invalidated and Non-reproducible

- `integrity_status = INVALIDATED` → Evidence Eligibility 必須為 `INELIGIBLE`。
- `reproducibility_status = NON_REPRODUCIBLE` → Evidence Eligibility 必須為 `INELIGIBLE`。

### 10.6 OOS Contamination

- `CONFIRMED` OOS 不得維持 `evidence_classification = OUT_OF_SAMPLE` 的 clean evidence 語意。
- Registry 必須保留原 sample role，但 Evidence Eligibility 必須降為 `RESTRICTED` 或 `INELIGIBLE`，並記錄 replacement holdout plan。

### 10.7 Supersession

`SUPERSEDED` 可以保持 `VERIFIED` 與歷史上的 `ELIGIBLE`，但網站必須顯示已有後續 Experiment，不得把它當作 current evidence。

## 11. Pre-registration and Design Lock

### 11.1 Mandatory Pre-registration

下列實驗在讀取結果前必須完成 Pre-registration：

- Confirmatory Historical Backtest
- Formal Validation
- OOS
- Walk-forward
- Formal Robustness test
- Paper Trading campaign

### 11.2 Required Fields

至少包括：

- Research question
- Hypothesis or test objective
- Strategy ID and Version，若適用
- Experiment purpose
- Evidence classification
- Sample roles and windows
- Universe reference
- Parameters
- Transaction cost assumptions，若適用
- Benchmark，若適用
- Metrics
- Gates
- Planned variants
- Multiple-testing family
- Stop or abort conditions
- Design owner
- Design locked at

### 11.3 Design Hash

鎖定時必須產生 `design_manifest_hash`，涵蓋適用的：

- Strategy and Config references
- Parameters
- Sample windows
- Cost assumptions
- Metrics
- Gates
- Planned variants

### 11.4 Post-lock Changes

任何影響結果解讀的變更都必須：

1. 建立 change event。
2. 將原實驗標記 `LOCK_BROKEN` 或取消。
3. 建立新 Experiment ID。
4. 不得把已查看結果包裝成事前設計。

## 12. Minimum Experiment Record

### 12.1 Identity

- `experiment_id`
- `experiment_family_id`, when applicable
- `campaign_id`, when applicable
- `batch_id`, when applicable
- `parent_experiment_id`, for child experiments
- `experiment_name`
- `research_subject_type`
- `experiment_purpose`
- `experiment_scope`
- `registration_mode`
- `execution_mode`
- `lifecycle_stage`
- `evidence_classification`
- `sample_role`

### 12.2 Ownership and Time

- `registered_at`
- `design_locked_at`, when applicable
- `queued_at`, when applicable
- `started_at`, when applicable
- `completed_at`, when applicable
- `registered_by`
- `execution_owner`
- `audit_owner`, when applicable

所有時間必須保存時區。

### 12.3 Strategy and Specification

依第 8 節適用矩陣保存：

- `strategy_id`
- `strategy_version`
- `parent_mode`
- `specification_version`
- `config_version`
- `config_uri`
- `config_hash`

### 12.4 Code and Environment

計算型實驗至少保存：

- `code_commit_sha`
- `repository`
- `working_tree_clean`
- `runtime_name`
- `runtime_version`
- `dependency_lock_hash`
- `container_image_digest`, when applicable
- `operating_system`
- `architecture`
- `execution_command`
- `random_seed`, when randomness exists

正式計算型實驗的 dirty working tree，Evidence Eligibility 不得高於 `PROVISIONAL`。

### 12.5 Data and PIT

依適用性保存：

- `dataset_manifest_id`
- `dataset_versions`
- `source_versions`
- `feature_versions`
- `pit_policy_version`
- `availability_rule_versions`
- `exchange_calendar_version`
- `data_cutoff_at`
- `as_of_rule`
- `pit_quality_status`
- `input_manifest_hash`

### 12.6 Research Design

- `hypothesis_reference`, when applicable
- `research_question` or test objective
- `primary_metric`, when applicable
- `secondary_metrics`
- `benchmark_ids`, when applicable
- `acceptance_gate_version`, when applicable
- `multiple_testing_family_id`, when applicable
- `planned_variant_count`, when applicable
- `design_manifest_hash`, when applicable

### 12.7 Sample Windows

每個 window 至少包含：

- `window_id`
- `window_role`
- `start_at`
- `end_at`
- `data_cutoff_rule`
- `embargo_period`
- `purge_period`
- `market_regime_tags`
- `accessed_before_lock`

### 12.8 Transaction Model

當實驗評估交易績效時，至少保存：

- Commission contract and version
- Tax contract and version
- Slippage model and version
- Market impact model and version
- Borrowing or financing cost
- Execution price rule
- Order delay
- Failed-order policy
- Limit-up and limit-down handling
- Suspension handling
- Missing-price handling
- Capacity assumptions

### 12.9 Parameters

每個 parameter 至少包含：

- `parameter_name`
- `parameter_value`
- `data_type`
- `unit`
- `source`: `SPECIFICATION` / `CONFIG` / `DIAGNOSTIC`
- `locked_before_execution`

## 13. Run Attempt Schema

每個 Run Attempt 至少包含：

- `run_attempt_id`
- `experiment_id`
- `attempt_number`
- `started_at`
- `ended_at`
- `worker_id`
- `execution_environment_hash`
- `exit_code`
- `attempt_status`
- `failure_category`
- `failure_message`
- `log_artifact_id`
- `produced_research_output`

若 `produced_research_output = true`，後續重跑原則上必須建立新 Experiment ID。

## 14. Campaign, Batch, Fold, and Observation Schemas

### 14.1 Campaign Record

至少包含：

- `campaign_id`
- `campaign_type`
- `experiment_family_id`
- `strategy_id` and `strategy_version`, when applicable
- `config_hash`, when applicable
- `campaign_started_at`
- `campaign_planned_end_at`
- `campaign_ended_at`
- `status`
- `child_experiment_ids`
- `fold_ids`
- `observation_ids`
- `termination_reason`

### 14.2 Batch Record

至少包含：

- `batch_id`
- `experiment_family_id`
- `planned_variant_ids`
- `child_experiment_ids`
- `unexecuted_variant_ids`
- `aggregation_rule`
- `batch_status`

Batch aggregation 不得隱藏 child Experiment 的失敗或負結果。

### 14.3 Fold Record

至少包含：

- `fold_id`
- `campaign_id`
- `child_experiment_id`, when independently evaluated
- Train, Validation and Test windows
- Purge and embargo
- Parameter selection output
- Frozen test configuration
- Fold metrics and artifacts
- Fold execution and integrity status

### 14.4 Observation Record

至少包含：

- `observation_id`
- `campaign_id`
- `observed_at`
- `decision_snapshot_id`, when applicable
- `signal_reference`
- `proposed_order_reference`
- `fill_reference`
- `data_incident_reference`
- `manual_intervention`

## 15. Experiment Lineage and Dependencies

### 15.1 Lineage Relationship Types

```text
RETEST_OF
REPRODUCTION_OF
SUPERSEDES
DIAGNOSTIC_VARIANT_OF
DERIVED_FROM
CONTINUATION_OF
CHILD_OF_BATCH
CHILD_OF_CAMPAIGN
INVALIDATES
```

### 15.2 Evidence Dependency Types

```text
DEPENDS_ON_EXPERIMENT
DEPENDS_ON_ARTIFACT
DEPENDS_ON_DATASET_VERSION
DEPENDS_ON_FEATURE_VERSION
DEPENDS_ON_CODE_VERSION
DEPENDS_ON_CONFIG_VERSION
DEPENDS_ON_POLICY_VERSION
DEPENDS_ON_CALENDAR_VERSION
```

每個 dependency edge 至少包含：

- `dependency_id`
- `downstream_entity_type`
- `downstream_entity_id`
- `dependency_type`
- `upstream_entity_id`
- `dependency_scope`
- `is_material`
- `registered_at`

### 15.3 Retest

Retest 必須：

- 建立新 Experiment ID
- 填入 `RETEST_OF`
- 記錄 Retest reason
- 記錄哪些版本改變
- 記錄哪些規則保持不變
- 保留原實驗及狀態

### 15.4 Reproduction

Reproduction 必須：

- 建立新 Experiment ID
- 填入 `REPRODUCTION_OF`
- 說明同環境或獨立環境
- 定義容忍度
- 保存差異報告

### 15.5 Diagnostic Variant

Diagnostic Variant 必須：

- 關聯正式基準 Experiment
- 使用獨立 Experiment ID
- 不得自動取得 Confirmatory 或 OOS 資格
- 不得靜默取代正式 Strategy Version

### 15.6 Lineage Integrity

必須：

- 禁止循環關係
- 禁止自我 supersede 或自我依賴
- 支援完整 lineage 回溯
- 區分研究 lineage 與 dependency graph

## 16. Multiple Testing and Experiment Families

包含多參數、多因子、多 Universe、多 window 或多策略變體的研究，必須保存：

- `multiple_testing_family_id`
- Family research question
- Planned variants
- Executed variants
- Unexecuted variants
- Child Experiment IDs
- Variant selection rule
- Primary hypothesis
- Adjustment method
- Whether results were inspected sequentially
- Whether testing stopped after favorable result

禁止把同一 family 中最佳實驗單獨呈現成唯一測試。

探索後選定正式策略時，必須建立新的 Confirmatory Experiment，且不得把探索樣本重新命名為 OOS。

## 17. OOS and Walk-forward Requirements

### 17.1 OOS Registration

至少保存：

- OOS window
- OOS lock time
- First access time
- Strategy and Config hashes at lock
- Whether OOS data was viewed before lock
- Contamination status
- Contamination reason
- Replacement holdout plan

### 17.2 Confirmed Contamination

下列情況原則上構成 `CONFIRMED`：

- 查看 OOS 後改參數
- 查看 OOS 後改 Universe
- 查看 OOS 後改 Gate
- 使用 OOS 挑選 Strategy Version
- 重複查看同一區間直到滿意

Contaminated OOS 必須保存，但不得再宣稱為 clean OOS evidence。

### 17.3 Walk-forward

Walk-forward Campaign 必須保存每一 fold，不得只保存總績效。

每個可獨立審計 fold 應建立 child Experiment；只作內部切分者至少保存完整 Fold Record。

## 18. Paper Trading Campaigns

每個 Paper Trading 計畫使用一個 `campaign_id`，並至少關聯一個正式 Paper Trading Experiment ID。

每日或每次訊號週期建立 Observation 或 Decision Snapshot，不需要每天建立 Experiment ID。

下列情況必須終止舊 Campaign 並建立新 Campaign 與新 Experiment ID：

- Strategy Version 改變
- Config 改變
- Code behavior 改變
- Data Contract 改變
- Execution model 改變
- 重大 incident 後需要正式 Retest

不得在同一 Campaign 中混用多個 Strategy Version 後報告單一績效。

## 19. Metric Schema

每個 metric 至少包含：

- `metric_id`
- `experiment_id`
- `metric_name`
- `metric_value`
- `data_type`
- `unit`
- `calculation_version`
- `window_id`
- `cost_basis`: `GROSS` / `NET`
- `benchmark_id`, when applicable
- `confidence_interval`, when applicable
- `sample_size`
- `is_primary_metric`
- `is_gate_metric`

每個報告數字必須回指 Metric Record 或 Artifact。

## 20. Artifact Schema

每個 artifact 至少包含：

- `artifact_id`
- `experiment_id` or container ID
- `artifact_type`
- `uri`
- `content_hash`
- `hash_algorithm`
- `media_type`
- `size_bytes`
- `generated_at`
- `generated_by_run_attempt_id`, when applicable
- `retention_class`
- `access_class`
- `contains_licensed_data`
- `contains_sensitive_data`

正式核心 artifacts 不得因 Retire、Supersede 或 Invalidated 而刪除。

Registry 與 artifacts 禁止保存 API secret、Password、Broker credential、Private key 或未經允許的個人資料。

## 21. Issue and Incident Schema

每個 issue 至少包含：

- `issue_id`
- `experiment_id` or campaign ID
- `severity`
- `category`
- `detected_at`
- `detected_by`
- `description`
- `affected_scope`
- `bias_direction`
- `resolution_status`
- `resolution_reference`
- `requires_retest`
- `requires_invalidation`

Severity：

```text
INFO
WARNING
ERROR
BLOCKER
```

任何 `ERROR` 或 `BLOCKER` 不得只寫入 log 而不更新 Registry。

## 22. Invalidation and Dependency Propagation

### 22.1 Invalidation Record

必須保存：

- Invalidated at
- Invalidated by
- Finding
- Root cause
- Affected outputs
- Upstream entity reference
- Bias direction
- Required Retest scope
- Replacement Experiment ID, if available

### 22.2 Propagation Procedure

當 Experiment、Artifact、Dataset Version、Feature、Code、Config、Policy 或 Calendar 被 invalidated：

1. 查詢全部直接 dependency edges。
2. 對直接下游建立 `POTENTIALLY_AFFECTED` impact record。
3. 若 dependency 標記 material，將下游設為 `UNDER_REVIEW`，Evidence Eligibility 不得為 `ELIGIBLE`。
4. 審計後更新為 `UNAFFECTED`、`AFFECTED` 或 `INVALIDATED`。
5. 對被判定 `AFFECTED` 或 `INVALIDATED` 的下游繼續遞迴傳遞。
6. 所有引用受影響實驗的 Decision Record 必須建立 Decision Impact Record。

### 22.3 Dependency Impact Record

至少包含：

- `impact_id`
- `source_invalidation_id`
- `affected_entity_type`
- `affected_entity_id`
- `dependency_path`
- `dependency_impact_status`
- `materiality_assessment`
- `assessed_by`
- `assessed_at`
- `required_action`

不得只修正上游紀錄而維持下游 Promote 決策不變。

## 23. Gate Evaluation Schema

每個 Gate Result 至少包含：

- `gate_id`
- `gate_version`
- `gate_category`
- `gate_name`
- `threshold`
- `observed_value`
- `status`
- `evidence_artifact_ids`
- `evaluation_at`
- `evaluated_by`
- `notes`

Gate status：

```text
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

看過結果後修改 Gate，必須建立適用的新版本與新 Experiment ID。

## 24. Decision Record Linkage

Registry 必須能關聯：

- `requested_decision`
- `decision_record_id`
- `decision_type`
- `decision_at`
- `decision_scope`
- `decision_impact_status`, when affected by dependency propagation

正式 decision type：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

Experiment 不得自行產生 Promote 結論。

## 25. Registry Event Log and Timestamp Ordering

每個狀態或重要欄位變動必須建立 event：

- `event_id`
- `entity_type`
- `entity_id`
- `event_type`
- `occurred_at`
- `actor`
- `previous_value`
- `new_value`
- `reason`
- `source_reference`

### 25.1 Timestamp Monotonicity

原則上必須滿足：

```text
registered_at
≤ design_locked_at
≤ queued_at
≤ started_at
≤ completed_at
```

只對適用欄位檢查。若技術重試存在，多個 Run Attempt 各自維持時間順序。

規則：

- `completed_at` 不得早於 `started_at`。
- Event `occurred_at` 不得早於其所引用事件的發生時間。
- Correction event 必須晚於被修正紀錄。
- Invalidation、Supersession 與 Decision linkage 不得早於相關 Experiment registration。
- 所有 timestamp 必須帶時區。

## 26. Correction Policy

純 metadata 錯字或錯誤引用可以修正，但必須保存：

- 原值
- 新值
- Correction reason
- Actor and timestamp

若修正影響結果、設計或結論，必須建立新 Experiment ID。

## 27. Canonical Storage Model

至少支援下列邏輯集合：

```text
experiment_families
campaigns
batches
experiment_records
run_attempts
campaign_folds
campaign_observations
experiment_windows
experiment_parameters
experiment_inputs
experiment_metrics
experiment_artifacts
experiment_issues
experiment_gate_results
experiment_lineage
experiment_dependencies
dependency_impacts
decision_impacts
experiment_events
```

### 27.1 Required Constraints

至少包括：

- IDs unique and immutable
- Foreign-key or equivalent integrity
- Lineage and dependency cycle prevention
- No hard delete for formal records
- Timestamp with timezone
- Enum validation
- Hash format validation
- Field applicability validation
- Cross-status consistency validation
- Completed experiments require terminal timestamps
- Formal experiments require applicable version manifests
- Campaign aggregate cannot exist without child or observation references

### 27.2 Query Requirements

系統至少支援：

- 依 Strategy ID and Version 查詢所有實驗
- 查詢同 Family、Batch 或 Campaign 的全部子實驗
- 查詢所有 failed、invalidated 或 non-reproducible experiments
- 查詢 Retest and Reproduction lineage
- 查詢 OOS contamination
- 查詢使用特定 Dataset、Feature、Code、Config 或 Policy Version 的全部實驗
- 查詢 defect 的完整下游 dependency graph
- 查詢受影響 Decision Records
- 重建 Evidence Package

## 28. Canonical YAML Examples

### 28.1 Formal Strategy Experiment

```yaml
experiment_id: EXP-20260710-01J2TWSTOCKA7M4K9Z8Q6P
experiment_family_id: FAM-01J2FAMILY
campaign_id: null
batch_id: null
parent_experiment_id: null
experiment_name: monthly-revenue-momentum-baseline-is
research_subject_type: STRATEGY
experiment_purpose: HISTORICAL_BACKTEST
experiment_scope: SINGLE_EXPERIMENT
registration_mode: PROSPECTIVE
execution_mode: COMPUTATIONAL
lifecycle_stage: HISTORICAL_BACKTEST
evidence_classification: CONFIRMATORY_IN_SAMPLE
sample_role: IN_SAMPLE

strategy:
  strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
  strategy_version: 1.0.0
  specification_version: 1.0.0
  config_version: 1.0.0
  config_uri: configs/strategies/tw-m03-monthly-revenue-momentum/1.0.0.yaml
  config_hash: sha256:example

code:
  repository: TechTWC/TWstock
  code_commit_sha: abcdef1234567890
  working_tree_clean: true
  runtime_name: python
  runtime_version: 3.13.0
  dependency_lock_hash: sha256:example
  operating_system: linux
  architecture: arm64
  execution_command: twstock backtest --experiment EXP-20260710-01J2TWSTOCKA7M4K9Z8Q6P
  random_seed: 20260710

data:
  dataset_manifest_id: DSM-20260710-001
  dataset_versions:
    market_daily: 1.0.0
    monthly_revenue: 1.0.0
    security_master: 1.0.0
  feature_versions:
    revenue_momentum: 1.0.0
  pit_policy_version: 1.0.0
  availability_rule_versions:
    monthly_revenue: 1.0.0
  exchange_calendar_version: 1.0.0
  data_cutoff_at: 2026-07-09T23:59:59+08:00
  pit_quality_status: PIT_PROVISIONAL
  input_manifest_hash: sha256:example

design:
  research_question: Does point-in-time monthly revenue acceleration predict subsequent Taiwan equity returns after costs?
  primary_metric: net_excess_cagr
  acceptance_gate_version: 1.0.0
  design_lock_status: LOCKED_BEFORE_EXECUTION
  design_locked_at: 2026-07-10T20:00:00+08:00
  design_manifest_hash: sha256:example

status:
  execution_status: COMPLETED
  evidence_eligibility_status: PROVISIONAL
  integrity_status: VERIFIED
  reproducibility_status: NOT_TESTED
  supersession_status: CURRENT
  oos_contamination_status: NOT_APPLICABLE
  dependency_impact_status: UNAFFECTED
```

### 28.2 Non-strategy Data-quality Experiment

```yaml
experiment_id: EXP-20260710-01J2DATAQUALITY
experiment_family_id: null
campaign_id: null
batch_id: null
parent_experiment_id: null
experiment_name: monthly-revenue-announcement-timestamp-coverage
research_subject_type: DATASET
experiment_purpose: DATA_QUALITY
experiment_scope: SINGLE_EXPERIMENT
registration_mode: PROSPECTIVE
execution_mode: COMPUTATIONAL
lifecycle_stage: IMPLEMENTATION
evidence_classification: DEVELOPMENT
sample_role: NOT_APPLICABLE

strategy: null

code:
  repository: TechTWC/TWstock
  code_commit_sha: 1234567890abcdef
  working_tree_clean: true
  runtime_name: python
  runtime_version: 3.13.0
  dependency_lock_hash: sha256:example
  operating_system: linux
  architecture: arm64
  execution_command: twstock data-audit monthly-revenue-timestamps

data:
  dataset_manifest_id: DSM-20260710-002
  dataset_versions:
    monthly_revenue: 1.0.0
  feature_versions: {}
  pit_policy_version: 1.0.0
  availability_rule_versions:
    monthly_revenue: 1.0.0
  exchange_calendar_version: 1.0.0
  input_manifest_hash: sha256:example

status:
  execution_status: COMPLETED
  design_lock_status: NOT_APPLICABLE
  evidence_eligibility_status: NOT_ASSESSED
  integrity_status: VERIFIED
  reproducibility_status: NOT_TESTED
  supersession_status: CURRENT
  oos_contamination_status: NOT_APPLICABLE
  dependency_impact_status: UNAFFECTED
```

範例只示範結構，不代表策略或資料已獲核准。

## 29. Validation Rules

### Rule 1: Unique IDs

所有 ID 重複必須拒絕。

### Rule 2: Applicability Validation

依 `research_subject_type`、`experiment_purpose` 與 `execution_mode` 套用第 8 節矩陣；不得要求不適用欄位，也不得接受缺少 REQUIRED 欄位。

### Rule 3: Container Integrity

Batch／Campaign 不能取代 child experiments；可獨立比較的 variant 必須有 Experiment ID。

### Rule 4: OOS Lock

OOS 在 design lock 前已存取時，不能標記 CLEAN。

### Rule 5: Terminal Timestamps

`COMPLETED` 必須有有效的 `started_at` 與 `completed_at`。

### Rule 6: Retest and Reproduction Links

RETEST 與 REPRODUCTION 必須有對應父實驗關係。

### Rule 7: Invalidated Evidence

`INVALIDATED` 必須對應 `INELIGIBLE`。

### Rule 8: Cross-status Consistency

所有狀態組合必須符合第 10 節。

### Rule 9: Dirty Working Tree

正式計算型實驗 dirty tree 時，Evidence Eligibility 不得高於 PROVISIONAL。

### Rule 10: Strategy Version Consistency

Registry、Config、Specification 與 artifacts 的 Strategy Version 必須一致。

### Rule 11: No Silent Blocker

存在 unresolved BLOCKER 時不得 ELIGIBLE。

### Rule 12: Campaign Version Freeze

同一 Paper Trading Campaign 不得跨 Strategy Version。

### Rule 13: No Hard Delete

正式紀錄 hard delete 必須被禁止。

### Rule 14: Graph Integrity

Lineage 與 dependency cycle 必須拒絕。

### Rule 15: Gate Integrity

看過結果後修改 Gate 的實驗不得聲稱通過原事前 Gate。

### Rule 16: Dependency Propagation

上游 invalidation 必須建立 impact records，並阻止受影響下游 Evidence 維持 ELIGIBLE。

### Rule 17: Timestamp Monotonicity

時間欄位與事件順序必須符合第 25 節。

### Rule 18: Retrospective Registration

`RETROSPECTIVE_BACKFILL` 不得標記 `LOCKED_BEFORE_EXECUTION`，除非有可驗證的原始事前註冊證據並引用其 artifact。

## 30. Engineering Acceptance Criteria

第一版實作至少必須達成：

- [ ] Experiment、Family、Batch、Campaign、Fold、Observation 與 Run Attempt 分開儲存。
- [ ] 每個可獨立評估的 variant 具有 Experiment ID。
- [ ] Experiment ID 不可修改或重複使用。
- [ ] Registry 使用多軸狀態。
- [ ] Field applicability matrix 可機器驗證。
- [ ] 非策略實驗不需虛構 Strategy ID。
- [ ] Cross-status consistency rules 會阻擋矛盾狀態。
- [ ] 正式實驗可鎖定 design manifest。
- [ ] 所有適用版本可追蹤。
- [ ] IS、Validation、OOS、Walk-forward 與 Paper windows 可分開保存。
- [ ] Retest、Reproduction、Diagnostic Variant 與 Supersession 可查詢。
- [ ] Failed、Invalidated、Non-reproducible 與 Superseded 永久保存。
- [ ] OOS contamination 可阻止錯誤標示 clean evidence。
- [ ] Run Attempt 無法規避新 Experiment ID。
- [ ] Dependency graph 可追蹤 Dataset／Code／Artifact 對實驗與決策的影響。
- [ ] Invalidation propagation 會建立 impact records。
- [ ] Decision Record 不得改寫 Registry。
- [ ] Campaign 版本改變時強制建立新 Campaign 與 Experiment。
- [ ] 所有重要變更產生 append-only Event。
- [ ] Timestamp ordering 可驗證。
- [ ] 正式紀錄禁止 hard delete。
- [ ] 可由 Experiment ID 重建 Evidence Package。

## 31. Manual Acceptance Tests

### Test A: Parameter Batch Preservation

Given：Batch 有十個參數變體，其中兩個失敗。

Expected：十個 child Experiment 均存在，失敗變體不可只消失在聚合結果中。

### Test B: Non-strategy Data Experiment

Given：Foundation Engine 的 Data Quality 實驗不屬於任何策略。

Expected：不需 Strategy ID；Code、Dataset 與 PIT 欄位依矩陣驗證。

### Test C: Contradictory Status

Given：Execution Status 為 RUNNING。

When：嘗試設定 Evidence Eligibility 為 ELIGIBLE。

Expected：拒絕。

### Test D: Broken Design Lock

Given：正式 OOS 實驗為 LOCK_BROKEN。

When：嘗試設定 ELIGIBLE。

Expected：拒絕並要求新 Experiment ID。

### Test E: Invalidation Propagation

Given：Dataset Version 被 invalidated，且三個 Experiment 與兩個 Decision Record 依賴它。

Expected：全部建立 dependency impact，material dependency 進入 UNDER_REVIEW，原 ELIGIBLE 狀態被阻擋。

### Test F: Walk-forward Fold Preservation

Given：Campaign 有十二個 fold。

Expected：每個 fold 有獨立狀態、metrics 與 artifacts；不可只保存聚合績效。

### Test G: Retrospective Backfill

Given：補登舊回測但沒有原始事前鎖定證據。

Expected：registration mode 為 RETROSPECTIVE_BACKFILL，禁止偽造 LOCKED_BEFORE_EXECUTION。

### Test H: Paper Version Change

Given：Paper Trading Campaign 進行中。

When：Strategy Version 改變。

Expected：舊 Campaign 結束，建立新 Campaign 與新 Experiment ID。

## 32. Research Reporting Requirements

正式頁面或報告至少顯示：

- Experiment ID
- Family／Batch／Campaign references
- Experiment purpose and subject type
- Strategy ID and Version，若適用
- Registration mode
- Evidence classification
- Execution status
- Evidence eligibility
- Integrity status
- Reproducibility status
- Supersession status
- OOS contamination status
- Dependency impact status
- Code and Dataset versions
- Test windows
- Primary metrics
- Gate summary
- Known issues
- Decision Record reference

報告不得只顯示最佳實驗而隱藏同 Family 或 Batch 的其他 variants。

## 33. Prohibited Practices

TWStock 禁止：

- 重複使用 Experiment ID
- 覆蓋舊結果
- 刪除失敗或無效實驗
- 只登錄成功實驗
- 用 Batch 或 Campaign 隱藏 child results
- 把 Run Attempt 當作規避新 Experiment ID 的方式
- 先看結果再偽造 design lock
- 把 exploratory result 標記為 confirmatory
- 把反覆查看的樣本標記為 clean OOS
- 用 Superseded 隱藏 Invalidated
- 用 Completed 代表 Valid
- 接受矛盾的多軸狀態
- 讓非策略實驗虛構 Strategy ID
- 忽略上游 invalidation 的 dependency propagation
- 在同一 Paper Campaign 混用多個 Strategy Version
- 不保存 Dataset 或 Code Version
- 手動修改 metric 而不保存來源
- 靜默忽略 BLOCKER
- 讓 Decision Record 改寫原始結果
- 將回測描述為未來獲利保證

## 34. Exceptions

任何例外都必須：

1. 明確記錄。
2. 指定 Experiment 或類型。
3. 說明必要性。
4. 評估重現性與偏誤。
5. 設定到期或重審條件。
6. Evidence Eligibility 不得高於 Provisional，除非正式政策修訂另有規定。
7. 不得用例外結果直接支持 Promote。

## 35. Migration and Backfill

補登既有歷史回測時：

- `registration_mode = RETROSPECTIVE_BACKFILL`
- 保存原執行日期，如可取得
- 保存補登日期
- 不得偽造事前 design lock
- 有原始 preregistration artifact 時才可引用其原始 lock time
- 缺少版本或 artifact 時標記 Provisional、Restricted 或 Ineligible
- 不得因補登提高證據等級

## 36. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Identity hierarchy 改變
- Experiment ID 規則改變
- Classification enums 改變
- Field applicability matrix 改變
- Status axes 或 cross-status constraints 改變
- Design lock 規則改變
- Dependency types 或 propagation 改變
- Retest or Reproduction lineage 改變
- OOS contamination 規則改變
- Artifact retention 改變
- Engineering acceptance criteria 改變

## 37. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
2. `docs/research/VALIDATION_PROTOCOL.md`
3. Dataset-specific Data Contracts
4. Thin Website Information Architecture
5. Foundation Engine implementation contracts

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
