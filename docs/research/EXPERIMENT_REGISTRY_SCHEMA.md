# TWStock Experiment Registry Schema

- Document ID: `TWSTOCK-RESEARCH-EXPERIMENT-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock exploratory studies, data and feature experiments, implementation verification, historical backtests, robustness tests, Out-of-Sample tests, reproductions, Retests, Paper Trading campaigns, failed runs, invalidated evidence, and related artifacts

## 1. Purpose

本文件定義 TWStock 如何註冊、保存、查詢、重現、稽核與連結每一項研究實驗。

Experiment Registry 必須永久回答：

- 為什麼執行這項實驗？
- 執行前鎖定了哪些設計？
- 使用哪一個 Strategy、Specification、Config、Code、Data、Feature、PIT 與 Calendar 版本？
- 哪些樣本被用於探索、驗證、OOS 或前瞻測試？
- 實際執行了什麼？
- 產生了哪些結果、錯誤、警告與 artifacts？
- 結果是否可重現？
- 是否存在資料、PIT、程式、交易、依賴或 OOS 污染問題？
- 此實驗是否仍可作為正式證據？
- 它和 Family、Batch、Campaign、Retest、Reproduction、Decision Record 有何關係？

核心原則：

> 每一次可獨立評估的研究執行，都必須留下不可靜默刪除、不可重複使用 ID、可追蹤版本、可重建輸入、可驗證輸出與可解釋證據狀態的永久紀錄。

本文件不判定任何策略有效，也不授權真實資金交易。

## 2. Authority and Document Relationships

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`
4. `docs/research/STRATEGY_LIFECYCLE.md`

後續文件將進一步具體化：

- `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
- `docs/research/VALIDATION_PROTOCOL.md`
- Dataset-specific Data Contracts
- Strategy-specific Executable Specifications
- Strategy YAML Configs
- Engineering storage and API contracts

權限邊界：

- Registry 保存事實、版本、狀態、依賴與證據關係。
- Registry 不得自行把結果解讀為策略有效。
- `04｜台股策略驗證與審計`依 Evidence Package 作出正式 Promote、Revise、Retest 或 Retire 決策。
- Decision Record 可以引用 Registry，但不得反向改寫原始實驗結果。
- 若網站、報告或聊天內容與 Registry 衝突，以 Registry、事件紀錄與原始 artifacts 為準。

## 3. Scope and Non-goals

本文件適用於：

- Exploratory research
- Data profiling and data-quality experiments
- Feature validation
- Numerical tests
- Leakage tests
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

- 投資假設或策略規則
- Strategy acceptance thresholds
- 特定資料庫或雲端產品
- 真實資金配置
- 券商串接或自動下單

## 4. Core Registry Principles

### 4.1 One Independently Evaluable Execution, One Experiment ID

每個可被獨立比較、引用、檢視或審計的研究執行，必須使用獨立 Experiment ID。

即使 Strategy Version、Config、Code、Data、期間與參數完全相同，正式重跑也不得覆蓋舊 Experiment ID。

### 4.2 Containers Do Not Replace Experiments

Family、Batch 與 Campaign 只負責分組與協調，不得取代子實驗紀錄。

禁止只保存聚合績效而遺失：

- 個別參數變體
- 失敗或負結果變體
- 被取消或未執行的 planned variant
- Walk-forward fold
- 個別狀態、警告與 artifacts

### 4.3 Append-only History

Registry 必須採 append-only audit model。

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
- 靜默修改事前設計
- 把 invalidated 實驗改寫成從未發生
- 用新結果取代舊 Experiment ID

### 4.4 Execution Is Not Evidence

Registry 必須分開保存：

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

結果不顯著、落後 Benchmark、成本後失效、OOS 失效、無法交易、執行失敗或無法重現，都必須保存。

### 4.6 Inputs Must Be Reconstructable

依實驗性質，正式實驗必須能重建適用的：

- Strategy behavior
- Data snapshot
- PIT rules
- Feature calculation
- Test window
- Cost assumptions
- Randomness
- Code and environment
- Execution command

無法重建時，必須降低 Evidence Eligibility 或標記 Non-reproducible。

## 5. Canonical Research Unit Hierarchy

### 5.1 Experiment Family

`experiment_family_id` 代表同一研究問題、多重假設家族或策略研究 lineage 下的一組實驗。

Family 不具有自己的證據資格；證據資格屬於個別 Experiment。

### 5.2 Campaign

`campaign_id` 代表持續性研究計畫，例如：

- Walk-forward campaign
- Paper Trading campaign
- Live Observation campaign

Campaign 必須保存 frozen-version manifest、期間、子實驗、fold 與 Observation 清單。

### 5.3 Batch

`batch_id` 代表一次協調執行的參數網格或變體集合。

Batch 只是執行容器；每個可獨立評估變體必須有 Experiment ID。

### 5.4 Experiment

`experiment_id` 代表一個輸入、設計、版本與輸出可獨立評估的研究執行。

### 5.5 Run Attempt

`run_attempt_id` 代表同一 Experiment 的純技術執行嘗試。

Run Attempt 只適用於：

- 基礎設施中斷
- Worker crash
- 網路中斷
- 尚未產生研究輸出且輸入完全未變的技術重試

若研究輸出已產生、結果已被查看或任何輸入改變，重跑必須建立新 Experiment ID。

### 5.6 Fold

`fold_id` 代表 Walk-forward campaign 中的一個 Train／Validation／Test 切分。

每個 fold 至少保存 input manifest、frozen test config、metrics、artifacts 與狀態。

若 fold 會被獨立引用、比較或作為 Decision Evidence，必須同時建立 child Experiment ID；否則可以保存為 campaign 下的 fold subrecord。

### 5.7 Observation

`observation_id` 代表 Paper Trading 或 Live Observation campaign 中的一次訊號週期、Decision Snapshot 或操作事件。

Observation 不等於 Experiment。

## 6. Identity and Immutability Rules

### 6.1 Experiment ID

Experiment ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 不依賴可變更名稱
- 可作為資料庫主鍵與 artifact path

建議格式：

```text
EXP-{YYYYMMDD}-{ULID}
```

### 6.2 Container and Child IDs

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
- 重跑已產生研究輸出的實驗
- Retest
- Reproduction
- Diagnostic Variant
- Batch 中每個可獨立評估變體

## 7. Classification Axes

### 7.1 Research Subject Type

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

```text
COMPUTATIONAL
MANUAL_REVIEW
DATA_INSPECTION
EXTERNAL_REPRODUCTION
HYBRID
```

### 7.3 Registration Mode

```text
PROSPECTIVE
RETROSPECTIVE_BACKFILL
```

`RETROSPECTIVE_BACKFILL` 不得偽造事前 Design Lock。

### 7.4 Lifecycle Stage

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

```text
SINGLE_EXPERIMENT
CHILD_EXPERIMENT
```

Batch 與 Campaign 使用獨立 `batch_id` 或 `campaign_id`，不得冒充 Experiment Scope。

## 8. Field Applicability Model

每個欄位對每種實驗目的必須使用：

```text
REQUIRED
WHEN_APPLICABLE
NOT_APPLICABLE
PROHIBITED_NULL
```

- `REQUIRED`：該類型必須提供。
- `WHEN_APPLICABLE`：符合條件時必須提供。
- `NOT_APPLICABLE`：明確記錄 N/A，不得虛構。
- `PROHIBITED_NULL`：核心主鍵或狀態不得為 null。

### 8.1 Base Fields

所有 Experiment 均必須包含：

- Experiment identity
- Research subject type
- Experiment purpose
- Registration mode
- Execution mode
- Lifecycle stage
- Ownership
- Registry timestamps
- Execution status
- Evidence eligibility status
- Integrity status
- Reproducibility status
- Dependency impact status
- Artifact or evidence references
- Event history

### 8.2 Purpose Applicability Matrix

| Field group | Strategy performance | Data quality | Feature validation | Numerical / leakage | Implementation verification | Manual review |
|---|---|---|---|---|---|---|
| Strategy ID / Version | REQUIRED | NOT_APPLICABLE unless strategy-scoped | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Specification / Config | REQUIRED | NOT_APPLICABLE unless strategy-scoped | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
| Code / Environment | REQUIRED | REQUIRED if computational | REQUIRED if computational | REQUIRED if computational | REQUIRED | WHEN_APPLICABLE |
| Dataset manifest | REQUIRED | REQUIRED | REQUIRED | WHEN_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Feature versions | REQUIRED when used | NOT_APPLICABLE | REQUIRED | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
| PIT / availability | REQUIRED | REQUIRED for time-sensitive data | REQUIRED for time-sensitive data | REQUIRED for PIT tests | WHEN_APPLICABLE | WHEN_APPLICABLE |
| Transaction model | REQUIRED when trading evaluated | NOT_APPLICABLE | NOT_APPLICABLE | WHEN_APPLICABLE | WHEN_APPLICABLE | NOT_APPLICABLE |
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

Dependency Impact 不得與 Integrity Status 混為一談。

## 10. Cross-status Consistency Rules

### 10.1 Eligibility Preconditions

`evidence_eligibility_status = ELIGIBLE` 只有在全部適用條件成立時允許：

- `execution_status = COMPLETED`
- `integrity_status = VERIFIED`
- 需要設計鎖定者為 `LOCKED_BEFORE_EXECUTION`
- 沒有 unresolved `BLOCKER`
- 必要版本、manifest、metrics 與核心 artifacts 完整
- `dependency_impact_status = UNAFFECTED`
- OOS 實驗為 `CLEAN`
- `reproducibility_status` 不得為 `NON_REPRODUCIBLE`

### 10.2 Non-terminal Execution

`PLANNED`、`QUEUED`、`RUNNING` 的 Evidence Eligibility 必須為 `NOT_ASSESSED`。

### 10.3 Failed Execution

`FAILED`、`ABORTED`、`CANCELLED` 不得為 `ELIGIBLE`。

若已有部分可用輸出，最多為 `RESTRICTED`，且必須定義限制範圍。

### 10.4 Broken or Missing Design Lock

對必須事前鎖定的實驗：

- `EXECUTED_WITHOUT_LOCK`：Evidence Eligibility 不得高於 `PROVISIONAL`。
- `LOCK_BROKEN`：Evidence Eligibility 必須為 `INELIGIBLE`，除非只是有稽核紀錄且不影響結果的 metadata correction。

### 10.5 Invalidated and Non-reproducible

- `integrity_status = INVALIDATED` → `INELIGIBLE`
- `reproducibility_status = NON_REPRODUCIBLE` → `INELIGIBLE`

### 10.6 Dependency Impact

- `POTENTIALLY_AFFECTED`：Evidence Eligibility 必須降為 `NOT_ASSESSED` 或 `PROVISIONAL`，不得維持 `ELIGIBLE`。
- `UNDER_REVIEW`：不得維持 `ELIGIBLE`。
- `AFFECTED`：不得高於 `RESTRICTED`。
- `INVALIDATED`：必須為 `INELIGIBLE`。

### 10.7 OOS Contamination

- `SUSPECTED`：不得標記 clean OOS ELIGIBLE。
- `CONFIRMED`：Evidence Eligibility 必須為 `RESTRICTED` 或 `INELIGIBLE`，並記錄 replacement holdout plan。
- 原 Sample Role 必須保留，不能改寫歷史用途。

### 10.8 Supersession

`SUPERSEDED` 可以保持歷史上的 `VERIFIED` 與 `ELIGIBLE`，但網站必須顯示已有後續 Experiment，且不得作為 current evidence。

## 11. Time Model

### 11.1 Registry Time Fields

所有 Experiment 均保存：

- `registry_registered_at`
- `registry_last_updated_at`
- `registration_mode`
- `backfilled_at`, when retrospective

### 11.2 Prospective Execution Time Fields

`registration_mode = PROSPECTIVE` 時，適用欄位包括：

- `design_locked_at`
- `queued_at`
- `started_at`
- `completed_at`

原則上：

```text
registry_registered_at
≤ design_locked_at
≤ queued_at
≤ started_at
≤ completed_at
```

只對適用欄位檢查。

### 11.3 Retrospective Backfill Time Fields

`registration_mode = RETROSPECTIVE_BACKFILL` 時，必須分開保存：

- `original_started_at`
- `original_completed_at`
- `original_design_locked_at`, only when documentary evidence exists
- `original_execution_date_precision`
- `timestamp_source`
- `timestamp_confidence`
- `backfilled_at`

不得把 `backfilled_at` 當成原始執行時間，也不得偽造原始 Design Lock。

時間規則：

```text
original_started_at
≤ original_completed_at
≤ backfilled_at
```

若原始時間精度不足，必須標記 precision 與 confidence，不得虛構秒級時間。

### 11.4 General Timestamp Rules

- `completed_at` 不得早於 `started_at`。
- Correction event 必須晚於被修正紀錄。
- Invalidation、Supersession、Decision linkage 不得早於相關 Experiment registration。
- Event `occurred_at` 不得早於其引用事件。
- 所有 timestamp 必須帶時區。

## 12. Pre-registration and Design Lock

### 12.1 Mandatory Pre-registration

下列實驗在讀取結果前必須完成 Pre-registration：

- Confirmatory Historical Backtest
- Formal Validation
- OOS
- Walk-forward
- Formal Robustness test
- Paper Trading campaign

### 12.2 Required Design Fields

至少包括：

- Research question
- Hypothesis or test objective
- Strategy ID and Version, when applicable
- Experiment purpose
- Evidence classification
- Sample roles and windows
- Universe reference
- Parameters
- Transaction cost assumptions, when applicable
- Benchmark, when applicable
- Metrics
- Gates
- Planned variants
- Multiple-testing family
- Stop or abort conditions
- Design owner
- Design locked at

### 12.3 Design Hash

鎖定時必須產生 `design_manifest_hash`，涵蓋適用的：

- Strategy and Config references
- Parameters
- Sample windows
- Cost assumptions
- Metrics
- Gates
- Planned variants

### 12.4 Post-lock Changes

任何影響結果解讀的變更都必須：

1. 建立 change event。
2. 將原實驗標記 `LOCK_BROKEN` 或取消。
3. 建立新 Experiment ID。
4. 不得把已查看結果包裝成事前設計。

## 13. Minimum Experiment Record

### 13.1 Identity

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

### 13.2 Ownership

- `registered_by`
- `execution_owner`
- `audit_owner`, when applicable

### 13.3 Time

依第 11 節保存 Registry、Prospective 或 Retrospective 時間欄位。

### 13.4 Strategy and Specification

依適用矩陣保存：

- `strategy_id`
- `strategy_version`
- `parent_mode`
- `specification_version`
- `config_version`
- `config_uri`
- `config_hash`

### 13.5 Code and Environment

計算型實驗至少保存：

- `code_commit_sha`
- `code_behavior_version`
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

正式計算型實驗 dirty tree 時，Evidence Eligibility 不得高於 `PROVISIONAL`。

### 13.6 Data and PIT

依適用性保存：

- `dataset_manifest_id`
- `dataset_versions`
- `source_versions`
- `data_contract_versions`
- `feature_versions`
- `pit_policy_version`
- `availability_rule_versions`
- `exchange_calendar_version`
- `data_cutoff_at`
- `as_of_rule`
- `pit_quality_status`
- `input_manifest_hash`

### 13.7 Research Design

- `hypothesis_reference`, when applicable
- `research_question` or test objective
- `primary_metric`, when applicable
- `secondary_metrics`
- `benchmark_ids`, when applicable
- `acceptance_gate_version`, when applicable
- `multiple_testing_family_id`, when applicable
- `planned_variant_count`, when applicable
- `design_manifest_hash`, when applicable

### 13.8 Sample Windows

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

### 13.9 Transaction and Execution Model

當實驗評估交易績效時，至少保存：

- `transaction_model_version`
- `execution_model_version`
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

### 13.10 Parameters

每個 parameter 至少包含：

- `parameter_name`
- `parameter_value`
- `data_type`
- `unit`
- `source`: `SPECIFICATION` / `CONFIG` / `DIAGNOSTIC`
- `locked_before_execution`

## 14. Run Attempt Schema

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

若 `produced_research_output = true`，後續重跑必須建立新 Experiment ID。

## 15. Campaign Frozen-version Contract

### 15.1 Campaign Record

每個 Campaign 至少包含：

- `campaign_id`
- `campaign_type`
- `experiment_family_id`
- `campaign_started_at`
- `campaign_planned_end_at`
- `campaign_ended_at`
- `campaign_status`
- `child_experiment_ids`
- `fold_ids`
- `observation_ids`
- `termination_reason`
- `frozen_version_manifest`
- `frozen_version_manifest_hash`

### 15.2 Frozen Version Manifest

適用時必須包含：

- `strategy_id`
- `strategy_version`
- `specification_version`
- `config_version`
- `config_hash`
- `code_commit_sha`
- `code_behavior_version`
- `data_contract_versions`
- `dataset_versions` or live dataset contract references
- `feature_versions`
- `pit_policy_version`
- `availability_rule_versions`
- `exchange_calendar_version`
- `transaction_model_version`
- `execution_model_version`
- `monitoring_policy_version`
- `incident_policy_version`

### 15.3 Campaign Consistency

每個 Observation、Fold 與 Child Experiment 必須：

- 引用 `campaign_id`
- 引用 `frozen_version_manifest_hash`
- 通過版本一致性檢查
- 保存任何偏離紀錄

下列任一項發生 material change 時，必須終止舊 Campaign，建立新 Campaign 與新正式 Experiment：

- Strategy Version
- Specification or Config
- Code behavior
- Data Contract
- Feature behavior
- PIT or availability rule
- Exchange Calendar
- Transaction or Execution Model
- Monitoring or Incident Policy

同一 Campaign 不得混用不同 frozen-version manifest 後報告單一績效。

## 16. Batch, Fold, and Observation Schemas

### 16.1 Batch Record

至少包含：

- `batch_id`
- `experiment_family_id`
- `planned_variant_ids`
- `child_experiment_ids`
- `unexecuted_variant_ids`
- `aggregation_rule`
- `batch_status`

Batch aggregation 不得隱藏 child Experiment 的失敗或負結果。

### 16.2 Fold Record

至少包含：

- `fold_id`
- `campaign_id`
- `frozen_version_manifest_hash`
- `child_experiment_id`, when independently evaluated
- Train, Validation and Test windows
- Purge and embargo
- Parameter selection output
- Frozen test configuration
- Fold metrics and artifacts
- Fold execution and integrity status

### 16.3 Observation Record

至少包含：

- `observation_id`
- `campaign_id`
- `frozen_version_manifest_hash`
- `observed_at`
- `decision_snapshot_id`, when applicable
- `signal_reference`
- `proposed_order_reference`
- `fill_reference`
- `data_incident_reference`
- `manual_intervention`
- `version_consistency_status`

## 17. Experiment Lineage and Dependencies

### 17.1 Lineage Relationship Types

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

### 17.2 Evidence Dependency Types

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

### 17.3 Retest

Retest 必須：

- 建立新 Experiment ID
- 填入 `RETEST_OF`
- 記錄 Retest reason
- 記錄哪些版本改變
- 記錄哪些規則保持不變
- 保留原實驗及狀態

### 17.4 Reproduction

Reproduction 必須：

- 建立新 Experiment ID
- 填入 `REPRODUCTION_OF`
- 說明同環境或獨立環境
- 定義容忍度
- 保存差異報告

### 17.5 Diagnostic Variant

Diagnostic Variant 必須：

- 關聯正式基準 Experiment
- 使用獨立 Experiment ID
- 不得自動取得 Confirmatory 或 OOS 資格
- 不得靜默取代正式 Strategy Version

### 17.6 Lineage Integrity

必須：

- 禁止循環關係
- 禁止自我 supersede 或自我依賴
- 支援完整 lineage 回溯
- 區分研究 lineage 與 dependency graph

## 18. Multiple Testing and Experiment Families

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

## 19. OOS and Walk-forward Requirements

### 19.1 OOS Registration

至少保存：

- OOS window
- OOS lock time
- First access time
- Strategy and Config hashes at lock
- Whether OOS data was viewed before lock
- Contamination status
- Contamination reason
- Replacement holdout plan

### 19.2 Confirmed Contamination

下列情況原則上構成 `CONFIRMED`：

- 查看 OOS 後改參數
- 查看 OOS 後改 Universe
- 查看 OOS 後改 Gate
- 使用 OOS 挑選 Strategy Version
- 重複查看同一區間直到滿意

Contaminated OOS 必須保存，但不得再宣稱為 clean OOS evidence。

### 19.3 Walk-forward

Walk-forward Campaign 必須保存每一 fold，不得只保存總績效。

每個可獨立審計 fold 應建立 child Experiment；內部切分至少保存完整 Fold Record。

## 20. Paper Trading and Live Observation Campaigns

每個 Paper Trading 或 Live Observation 計畫使用一個 `campaign_id`，並至少關聯一個正式 Experiment ID。

每日或每次訊號週期建立 Observation 或 Decision Snapshot，不需要每天建立 Experiment ID。

Campaign 必須遵守第 15 節 frozen-version contract。

不得在同一 Campaign 混用多個版本後報告單一績效。

## 21. Metric Schema

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

## 22. Artifact Schema

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

## 23. Issue and Incident Schema

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

## 24. Invalidation and Dependency Propagation

### 24.1 Invalidation Record

必須保存：

- `invalidation_id`
- Invalidated at
- Invalidated by
- Finding
- Root cause
- Affected outputs
- Upstream entity reference
- Bias direction
- Required Retest scope
- Replacement Experiment ID, if available

### 24.2 Propagation Procedure

當 Experiment、Artifact、Dataset、Feature、Code、Config、Policy 或 Calendar 被 invalidated：

1. 查詢全部直接 dependency edges。
2. 對直接下游建立 `POTENTIALLY_AFFECTED` impact record。
3. `POTENTIALLY_AFFECTED` 不得維持 ELIGIBLE。
4. 若 dependency 為 material，將下游設為 `UNDER_REVIEW`。
5. 審計後更新為 `UNAFFECTED`、`AFFECTED` 或 `INVALIDATED`。
6. 對 `AFFECTED` 或 `INVALIDATED` 的下游繼續遞迴傳遞。
7. 所有引用受影響實驗的 Decision Record 必須建立 Decision Impact Record。

### 24.3 Dependency Impact Record

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

## 25. Gate Evaluation Schema

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

## 26. Decision Record Linkage

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

## 27. Registry Event Log and Corrections

每個重要欄位或狀態變動必須建立 event：

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

純 metadata 錯誤可以修正，但必須保存原值、新值、原因、actor 與 timestamp。

若修正影響結果、設計或結論，必須建立新 Experiment ID。

## 28. Canonical Storage Model

至少支援：

```text
experiment_families
campaigns
campaign_version_manifests
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

### 28.1 Required Constraints

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
- Registration-mode-specific time validation
- Completed experiments require terminal timestamps
- Formal experiments require applicable version manifests
- Campaign aggregate cannot exist without child or observation references
- Campaign children must match frozen-version manifest

### 28.2 Query Requirements

系統至少支援：

- 依 Strategy ID and Version 查詢所有實驗
- 查詢同 Family、Batch 或 Campaign 的全部子實驗
- 查詢所有 failed、invalidated 或 non-reproducible experiments
- 查詢 Retest and Reproduction lineage
- 查詢 OOS contamination
- 查詢使用特定 Dataset、Feature、Code、Config、Policy 或 Calendar Version 的實驗
- 查詢 defect 的完整下游 dependency graph
- 查詢受影響 Decision Records
- 重建 Evidence Package
- 查詢 Campaign frozen-version manifest 與所有偏離

## 29. Canonical YAML Examples

### 29.1 Formal Strategy Experiment

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
registry_registered_at: 2026-07-10T19:00:00+08:00
registry_last_updated_at: 2026-07-10T22:00:00+08:00
design_locked_at: 2026-07-10T19:30:00+08:00
queued_at: 2026-07-10T20:00:00+08:00
started_at: 2026-07-10T20:05:00+08:00
completed_at: 2026-07-10T21:30:00+08:00
registered_by: research-system
execution_owner: backtest-runner
audit_owner: workspace-04
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
  code_behavior_version: 1.0.0
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
  data_contract_versions:
    market_daily: 1.0.0
    monthly_revenue: 1.0.0
  feature_versions:
    revenue_momentum: 1.0.0
  pit_policy_version: 1.0.0
  availability_rule_versions:
    monthly_revenue: 1.0.0
  exchange_calendar_version: 1.0.0
  data_cutoff_at: 2026-07-09T23:59:59+08:00
  pit_quality_status: PIT_PROVISIONAL
  input_manifest_hash: sha256:example
status:
  execution_status: COMPLETED
  design_lock_status: LOCKED_BEFORE_EXECUTION
  evidence_eligibility_status: PROVISIONAL
  integrity_status: VERIFIED
  reproducibility_status: NOT_TESTED
  supersession_status: CURRENT
  oos_contamination_status: NOT_APPLICABLE
  dependency_impact_status: UNAFFECTED
```

### 29.2 Retrospective Backfill

```yaml
experiment_id: EXP-20260710-01J2BACKFILL
experiment_name: legacy-backtest-backfill
research_subject_type: STRATEGY
experiment_purpose: HISTORICAL_BACKTEST
experiment_scope: SINGLE_EXPERIMENT
registration_mode: RETROSPECTIVE_BACKFILL
execution_mode: COMPUTATIONAL
lifecycle_stage: HISTORICAL_BACKTEST
evidence_classification: DEVELOPMENT
sample_role: IN_SAMPLE
registry_registered_at: 2026-07-10T21:00:00+08:00
registry_last_updated_at: 2026-07-10T21:00:00+08:00
backfilled_at: 2026-07-10T21:00:00+08:00
original_started_at: 2025-12-15T10:00:00+08:00
original_completed_at: 2025-12-15T10:30:00+08:00
original_design_locked_at: null
original_execution_date_precision: SECOND
timestamp_source: archived-run-log
timestamp_confidence: HIGH
status:
  execution_status: COMPLETED
  design_lock_status: EXECUTED_WITHOUT_LOCK
  evidence_eligibility_status: PROVISIONAL
  integrity_status: NOT_ASSESSED
  reproducibility_status: NOT_TESTED
  supersession_status: CURRENT
  oos_contamination_status: NOT_APPLICABLE
  dependency_impact_status: UNAFFECTED
```

### 29.3 Campaign Frozen Manifest

```yaml
campaign_id: CAM-01J2PAPER
campaign_type: PAPER_TRADING
experiment_family_id: FAM-01J2FAMILY
campaign_started_at: 2026-08-01T00:00:00+08:00
campaign_planned_end_at: 2026-11-01T00:00:00+08:00
campaign_ended_at: null
campaign_status: ACTIVE
frozen_version_manifest:
  strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
  strategy_version: 1.0.0
  specification_version: 1.0.0
  config_version: 1.0.0
  config_hash: sha256:config
  code_commit_sha: abcdef1234567890
  code_behavior_version: 1.0.0
  data_contract_versions:
    monthly_revenue_live: 1.0.0
  feature_versions:
    revenue_momentum: 1.0.0
  pit_policy_version: 1.0.0
  availability_rule_versions:
    monthly_revenue: 1.0.0
  exchange_calendar_version: 1.0.0
  transaction_model_version: 1.0.0
  execution_model_version: 1.0.0
  monitoring_policy_version: 1.0.0
  incident_policy_version: 1.0.0
frozen_version_manifest_hash: sha256:campaign
child_experiment_ids:
  - EXP-20260801-01J2PAPEREXP
observation_ids: []
fold_ids: []
```

範例示範本文件所述 profile 的必要欄位；實際 Data Contract 可以增加欄位，但不得刪除必要語意。

## 30. Validation Rules

1. 所有 ID 重複必須拒絕。
2. 依 subject、purpose、execution mode 套用欄位適用矩陣。
3. Batch／Campaign 不得取代 child experiments。
4. 可獨立比較 variant 必須有 Experiment ID。
5. OOS 在 design lock 前已存取時不能標記 CLEAN。
6. `COMPLETED` 必須有適用的有效終止時間。
7. RETEST 與 REPRODUCTION 必須有父實驗關係。
8. 所有狀態組合必須符合第 10 節。
9. 正式計算型實驗 dirty tree 時不得高於 PROVISIONAL。
10. Registry、Config、Specification 與 artifacts 的 Strategy Version 必須一致。
11. unresolved BLOCKER 時不得 ELIGIBLE。
12. `POTENTIALLY_AFFECTED`、`UNDER_REVIEW` 時不得維持 ELIGIBLE。
13. 正式 Experiment hard delete 必須拒絕。
14. Lineage 或 dependency cycle 必須拒絕。
15. 看過結果後修改 Gate 的實驗不得聲稱通過原事前 Gate。
16. PROSPECTIVE 與 RETROSPECTIVE_BACKFILL 使用不同時間驗證規則。
17. Backfill 不得偽造 Design Lock。
18. Campaign 子紀錄必須引用並符合 frozen-version manifest hash。
19. Campaign frozen manifest material change 必須終止舊 Campaign。
20. Event 與 timestamp 順序必須有效。

## 31. Engineering Acceptance Criteria

第一版實作至少必須達成：

- [ ] 每個可獨立評估執行自動產生唯一 Experiment ID。
- [ ] Experiment ID 不可修改或重複使用。
- [ ] Family、Batch、Campaign、Fold、Observation 與 Experiment 分開儲存。
- [ ] 非策略實驗不需要虛構 Strategy metadata。
- [ ] Field applicability 可以 machine-validate。
- [ ] Registry 使用多軸狀態。
- [ ] Cross-status rules 阻止矛盾組合。
- [ ] PROSPECTIVE 與 RETROSPECTIVE_BACKFILL 時間模型分離。
- [ ] Backfill 不可偽造事前註冊。
- [ ] Strategy、Config、Code、Data、Feature、PIT 與 Calendar 版本可追蹤。
- [ ] Campaign frozen-version manifest 可被驗證。
- [ ] Observation 與 Child Experiment 必須符合 Campaign manifest。
- [ ] Retest、Reproduction、Diagnostic Variant 與 Supersession 關係可查詢。
- [ ] Failed、Invalidated、Non-reproducible 與 Superseded 實驗永久保存。
- [ ] OOS contamination 阻止錯誤 clean OOS 標示。
- [ ] Run Attempt 與新 Experiment 的邊界受到驗證。
- [ ] Dependency graph 支援遞迴 invalidation propagation。
- [ ] `POTENTIALLY_AFFECTED` 不得維持 ELIGIBLE。
- [ ] Decision Impact Records 可追蹤。
- [ ] BLOCKER 阻止 ELIGIBLE。
- [ ] 可由 Experiment ID 重建完整 Evidence Package。

## 32. Manual Acceptance Tests

### Test A: Duplicate ID

Given：Experiment ID 已存在。

Expected：再次建立相同 ID 時拒絕寫入。

### Test B: Batch Variant Preservation

Given：Batch 包含成功、失敗與未執行變體。

Expected：每個可獨立評估變體均有 child Experiment 或 planned variant record，聚合結果不得隱藏失敗。

### Test C: Non-strategy Experiment

Given：DATA_QUALITY 實驗與任何策略無關。

Expected：Strategy ID 為 N/A，不得要求虛構值。

### Test D: Running plus Eligible

Given：`execution_status = RUNNING`。

Expected：Evidence Eligibility 必須為 `NOT_ASSESSED`。

### Test E: Potential Dependency Impact

Given：上游 Dataset 被 invalidated，下游為 `POTENTIALLY_AFFECTED`。

Expected：下游不得維持 ELIGIBLE，並進入 materiality review。

### Test F: Campaign Version Drift

Given：Paper Trading Campaign 進行中，Code Behavior Version 改變。

Expected：舊 Campaign 終止；建立新 Campaign、新 frozen manifest 與新 Experiment ID。

### Test G: Observation Manifest Mismatch

Given：Observation 引用的 manifest hash 與 Campaign 不一致。

Expected：寫入被拒絕或標記 BLOCKER，不得納入 Campaign 績效。

### Test H: Retrospective Backfill Time

Given：2025 年執行的實驗於 2026 年補登。

Expected：保存 original execution timestamps 與 backfilled_at；不得要求 registry registration 早於原始執行。

### Test I: Fabricated Backfill Lock

Given：補登實驗沒有事前鎖定證據。

Expected：`original_design_locked_at = null`，不得標記 `LOCKED_BEFORE_EXECUTION`。

### Test J: OOS Contamination

Given：OOS 在鎖定前已被查看。

Expected：不能標記 CLEAN 或 ELIGIBLE clean OOS。

### Test K: Invalidation Propagation

Given：上游資料缺陷影響多個實驗與決策。

Expected：可查出完整 dependency path、impact status 與 affected Decision Records。

### Test L: Failed Experiment Retention

Given：Experiment execution failed。

Expected：Registry 仍可搜尋、顯示與統計該實驗。

## 33. Research Reporting Requirements

正式研究頁面至少顯示：

- Experiment ID
- Experiment purpose
- Strategy ID and Version, when applicable
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

報告不得只顯示最佳實驗而隱藏同 family 的其他 variants。

## 34. Prohibited Practices

TWStock 禁止：

- 重複使用 Experiment ID
- 覆蓋舊結果
- 刪除失敗或無效實驗
- 只登錄成功實驗
- 用 Run Attempt 規避新 Experiment ID
- 用 Batch／Campaign 隱藏 child failures
- 先看結果再偽造 design lock
- 補登時偽造原始執行時間或鎖定時間
- 把 exploratory result 標記為 confirmatory
- 把反覆查看的樣本標記為 clean OOS
- 用 Superseded 隱藏 Invalidated
- 用 Completed 代表 Valid
- 讓 `POTENTIALLY_AFFECTED` 實驗維持 ELIGIBLE
- 在同一 Campaign 混用不同 frozen manifest
- 不保存 Dataset、Code、Config 或 Policy Version
- 手動修改 metric 而不保存來源
- 靜默忽略 BLOCKER
- 讓 Decision Record 改寫原始實驗結果
- 將回測結果描述為未來獲利保證

## 35. Exceptions and Backfill

任何例外都必須：

1. 明確記錄。
2. 指定 Experiment、Campaign 或實驗類型。
3. 說明必要性。
4. 評估對重現性與偏誤的影響。
5. 設定到期或重審條件。
6. Evidence Eligibility 不得高於 Provisional，除非正式政策修訂另有規定。
7. 不得用例外結果直接支持 Promote。

歷史補登必須：

- `registration_mode = RETROSPECTIVE_BACKFILL`
- 保存 `backfilled_at`
- 保存原始執行時間與來源，如可取得
- 保存 timestamp precision and confidence
- 不得偽造事前 Design Lock
- 缺少版本或 artifact 時標記 Provisional、Restricted 或 Ineligible
- 不得因補登提高原證據等級

## 36. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Experiment ID 規則
- Research unit hierarchy
- Classification enums
- Field applicability rules
- Status axes or cross-status rules
- Time model
- Design lock rules
- Campaign frozen-version contract
- Retest or Reproduction lineage
- OOS contamination rules
- Dependency propagation
- Artifact retention
- Gate linkage
- Engineering acceptance criteria

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Migration
- Affected Experiments and Campaigns
- Required Reclassification or Retest

## 37. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
2. `docs/research/VALIDATION_PROTOCOL.md`
3. Dataset-specific Data Contracts
4. Thin Website Information Architecture
5. Foundation Engine implementation contracts

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
