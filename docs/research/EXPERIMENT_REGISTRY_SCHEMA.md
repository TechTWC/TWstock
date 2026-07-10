# TWStock Experiment Registry Schema

- Document ID: `TWSTOCK-RESEARCH-EXPERIMENT-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock exploratory studies, formal backtests, robustness tests, Out-of-Sample tests, reproductions, Retests, Paper Trading campaigns, failed runs, invalidated evidence, and related artifacts

## 1. Purpose

本文件定義 TWStock 如何建立、保存、查詢、重現、稽核與連結每一項研究實驗。

Experiment Registry 的核心目的不是只保存績效數字，而是永久回答：

- 為什麼執行這項實驗？
- 實驗在執行前承諾了哪些規則？
- 使用哪一個 Strategy、Specification、Config、Code、Data 與 Feature 版本？
- 哪些樣本被用於探索、訓練、驗證、OOS 或前瞻測試？
- 實際執行了什麼？
- 產生了哪些結果、錯誤、警告與 artifacts？
- 結果是否可重現？
- 是否存在 Point-in-Time、資料、程式、交易或 OOS 污染問題？
- 此實驗是否仍可作為正式證據？
- 它和先前實驗、Retest、Reproduction、Strategy Version 與 Decision Record 有何關係？

核心原則是：

> 每一次正式研究執行都必須留下不可靜默刪除、不可重複使用 ID、可追蹤版本、可重建輸入、可驗證輸出與可解釋證據狀態的永久紀錄。

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

- Experiment Registry 負責保存事實與狀態。
- Registry 不得自行把結果解讀為策略有效。
- `04｜台股策略驗證與審計`依 Evidence Package 作出正式 Promote、Revise、Retest 或 Retire 決策。
- Decision Record 可以引用 Experiment Registry；不得反向改寫原始實驗結果。

若實驗紀錄、報告、網站顯示或聊天內容與 Registry 的版本化紀錄衝突，以正式 Registry 與原始 artifacts 為準。

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

- 策略的投資假設
- Strategy acceptance thresholds
- 特定資料表實作
- 特定雲端或資料庫產品
- 真實資金配置
- 券商串接或自動下單

## 4. Core Registry Principles

### 4.1 One Formal Execution, One Experiment ID

每次正式執行原則上都必須建立新的 Experiment ID。

即使下列項目完全相同，也不得重複使用舊 Experiment ID：

- Strategy Version
- Config Version
- Code Commit
- Dataset Version
- Test window
- Parameters

重新執行的結果必須可以和舊實驗並列比較，而不是覆蓋舊紀錄。

### 4.2 Append-only History

Experiment Registry 必須採 append-only audit model。

允許：

- 增加狀態事件
- 增加 artifact
- 增加 audit finding
- 增加 invalidation 或 supersession 關係
- 修正明顯的紀錄錯誤並保留 correction event

禁止：

- 刪除失敗實驗
- 覆蓋原始結果
- 靜默修改事前規格
- 把 invalidated 實驗改寫成從未發生
- 用新結果取代舊 Experiment ID

### 4.3 Separate Execution from Evidence

「程式有跑完」不等於「結果可作為證據」。

因此 Registry 必須分開保存：

- Execution Status
- Design Lock Status
- Evidence Eligibility Status
- Integrity Status
- Reproducibility Status
- Supersession Status
- OOS Contamination Status
- Gate Results
- Formal Decision Reference

不得只使用單一 `status` 欄位混合上述語意。

### 4.4 Preserve Negative and Null Results

結果不顯著、落後 Benchmark、成本後失效、OOS 失效或無法交易，都必須保存。

不得只登錄成功實驗。

### 4.5 Registry Is Not a Marketing Layer

Registry 中的描述必須保持研究語言。

不得使用：

- Guaranteed return
- Proven winner
- 必賺
- 已找到聖杯
- 回測成功所以可以買

### 4.6 Inputs Must Be Reconstructable

每個正式實驗必須能重建：

- Strategy behavior
- Data snapshot
- PIT rules
- Feature calculation
- Test window
- Cost assumptions
- Randomness
- Code and environment
- Execution command

若不能重建，必須降低證據資格或標記 Non-reproducible。

## 5. Canonical Registry Entities

Experiment Registry 至少由下列邏輯實體構成。

### 5.1 Experiment Record

代表一項已註冊的研究執行。

### 5.2 Run Attempt

代表同一 Experiment ID 下的技術執行嘗試。

Run Attempt 只適用於：

- 基礎設施中斷
- Worker crash
- 網路中斷
- 尚未產生可使用研究輸出的純技術重試

若任何研究輸出已產生、輸入已改變、參數已改變或結果已被查看，重新執行必須建立新 Experiment ID，不能只增加 Run Attempt。

### 5.3 Input Manifest

保存資料、設定、程式、特徵、日曆、政策與執行環境版本。

### 5.4 Artifact Manifest

保存實驗產出位置、類型、雜湊、大小、生成時間與保留規則。

### 5.5 Metric Record

保存標準化績效、風險、交易、容量與資料品質指標。

### 5.6 Issue and Incident Record

保存 warning、error、blocker、資料事件、程式事件與人工介入。

### 5.7 Gate Evaluation

保存每個事前 Gate 的結果與證據。

### 5.8 Experiment Lineage

保存 Retest、Reproduction、Supersession、Diagnostic Variant 與其他實驗關係。

### 5.9 Registry Event

保存所有狀態變更、修正、稽核、invalidations、decision links 與 actor。

## 6. Experiment Identity

### 6.1 Experiment ID

Experiment ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 不依賴可變更的 Strategy Name
- 可安全作為資料庫主鍵與 artifact path

建議格式：

```text
EXP-{YYYYMMDD}-{ULID}
```

例如：

```text
EXP-20260710-01J2TWSTOCKA7M4K9Z8Q6P
```

日期部分只供閱讀；唯一性由 ULID、UUID 或等價機制保證。

### 6.2 Experiment Family ID

用於連結同一研究問題下的多個實驗或參數變體。

例如：

```text
FAM-TW-M03-REV-MOM-V1-001
```

用途包括：

- Multiple-testing 記錄
- Diagnostic Variant 群組
- 參數網格
- Walk-forward 批次
- 同一研究問題的探索與確認性階段

### 6.3 Run Attempt ID

建議格式：

```text
{experiment_id}-RUN-{NNN}
```

例如：

```text
EXP-20260710-01J2TWSTOCKA7M4K9Z8Q6P-RUN-001
```

### 6.4 Experiment ID Immutability

下列行為必須建立新 Experiment ID：

- 改變任何研究參數
- 改變資料版本
- 改變 Code Commit
- 改變 Config
- 改變 Feature Version
- 改變測試期間
- 改變成本或滑價假設
- 改變 Universe 或 Tradability rules
- 修正會影響結果的程式錯誤
- 重新執行已產生研究輸出的實驗
- Retest
- Reproduction

## 7. Experiment Classification

Registry 必須使用多軸分類，不得只用一個模糊的 `experiment_type`。

### 7.1 Lifecycle Stage

`lifecycle_stage` 必須使用：

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

### 7.2 Experiment Purpose

`experiment_purpose` 使用：

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

### 7.3 Evidence Classification

`evidence_classification` 使用：

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

### 7.4 Sample Role

`sample_role` 使用：

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

### 7.5 Experiment Scope

`experiment_scope` 使用：

```text
SINGLE_RUN
PARAMETER_BATCH
WALK_FORWARD_CAMPAIGN
PAPER_TRADING_CAMPAIGN
LIVE_OBSERVATION_CAMPAIGN
```

## 8. Status Axes

### 8.1 Execution Status

`execution_status` 使用：

```text
PLANNED
QUEUED
RUNNING
COMPLETED
FAILED
ABORTED
CANCELLED
```

允許的主要轉移：

```text
PLANNED → QUEUED → RUNNING → COMPLETED
PLANNED → CANCELLED
QUEUED → CANCELLED
RUNNING → FAILED
RUNNING → ABORTED
```

`COMPLETED` 不得回到 `RUNNING`。重新執行必須建立新 Experiment ID，除非符合純技術 Run Attempt 例外。

### 8.2 Design Lock Status

`design_lock_status` 使用：

```text
DRAFT
LOCKED_BEFORE_EXECUTION
EXECUTED_WITHOUT_LOCK
LOCK_BROKEN
NOT_APPLICABLE
```

正式 Confirmatory、OOS、Walk-forward 與 Paper Trading 設計必須在執行前鎖定。

### 8.3 Evidence Eligibility Status

`evidence_eligibility_status` 使用：

```text
NOT_ASSESSED
ELIGIBLE
PROVISIONAL
RESTRICTED
INELIGIBLE
```

定義：

- `ELIGIBLE`：可依適用 Gate 進入正式審計。
- `PROVISIONAL`：可供探索或 Retest，但不足以單獨支持 Promote。
- `RESTRICTED`：只限特定期間、證券、欄位或結論。
- `INELIGIBLE`：不得作為正式升級證據。

### 8.4 Integrity Status

`integrity_status` 使用：

```text
NOT_ASSESSED
VERIFIED
INVALIDATED
```

`INVALIDATED` 表示資料、程式、PIT、版本、計算或執行缺陷使原結果失去證據資格。

Invalidated 不代表紀錄應被刪除。

### 8.5 Reproducibility Status

`reproducibility_status` 使用：

```text
NOT_TESTED
REPRODUCIBLE
PARTIALLY_REPRODUCIBLE
NON_REPRODUCIBLE
NOT_APPLICABLE
```

### 8.6 Supersession Status

`supersession_status` 使用：

```text
CURRENT
SUPERSEDED
NOT_APPLICABLE
```

Superseded 不等於 Invalidated。

一項實驗可能有效且可重現，但已被更近期資料或版本的實驗取代。

### 8.7 OOS Contamination Status

`oos_contamination_status` 使用：

```text
NOT_APPLICABLE
CLEAN
SUSPECTED
CONFIRMED
```

`CONFIRMED` 表示 OOS 已被用於規則、參數、Gate 或策略版本調整，原區間不得再稱為未見樣本。

### 8.8 Registry Summary Status

網站可以顯示衍生的 `registry_summary_status`，但它必須由上述狀態軸計算，不能人工覆蓋。

建議優先順序：

```text
INVALIDATED
NON_REPRODUCIBLE
OOS_CONTAMINATED
INELIGIBLE
RESTRICTED
PROVISIONAL
ELIGIBLE_SUPERSEDED
ELIGIBLE_CURRENT
NOT_ASSESSED
```

## 9. Pre-registration and Design Lock

### 9.1 Mandatory Pre-registration

下列實驗在讀取結果前必須完成 Pre-registration：

- Confirmatory Historical Backtest
- Validation
- OOS
- Walk-forward
- Formal Robustness test
- Paper Trading campaign

### 9.2 Pre-registration Fields

至少包含：

- Research question
- Hypothesis
- Strategy ID and Version
- Experiment purpose
- Evidence classification
- Sample role
- Test windows
- Universe definition reference
- Signal and portfolio references
- Parameters
- Transaction cost assumptions
- Benchmark
- Metrics
- Gates
- Planned sensitivity tests
- Planned variants
- Multiple-testing family
- Stop or abort conditions
- Design owner
- Design locked at

### 9.3 Design Hash

設計鎖定時必須產生：

```text
design_manifest_hash
```

Hash 至少涵蓋：

- Strategy and Config references
- Parameters
- Sample windows
- Cost assumptions
- Metrics
- Gates
- Planned variants

### 9.4 Post-lock Changes

任何會影響研究結果解讀的變更都必須：

1. 記錄 change event。
2. 將目前實驗標記 `LOCK_BROKEN` 或取消。
3. 建立新 Experiment ID。
4. 不得把已查看的結果包裝成事前設計。

## 10. Minimum Experiment Record

每個 Experiment Record 至少包含以下欄位。

### 10.1 Identity

| Field | Requirement | Meaning |
|---|---|---|
| `experiment_id` | Required | 全域唯一實驗識別 |
| `experiment_family_id` | When applicable | 實驗家族 |
| `experiment_name` | Required | 人類可讀名稱 |
| `experiment_purpose` | Required | 實驗目的 |
| `experiment_scope` | Required | 單次或 campaign |
| `lifecycle_stage` | Required | 策略生命週期階段 |
| `evidence_classification` | Required | 證據分類 |
| `sample_role` | Required | 樣本用途 |

### 10.2 Ownership and Time

| Field | Requirement | Meaning |
|---|---|---|
| `registered_at` | Required | 建立 Registry 紀錄時間 |
| `design_locked_at` | When applicable | 設計鎖定時間 |
| `queued_at` | When applicable | 進入執行佇列時間 |
| `started_at` | When applicable | 開始執行時間 |
| `completed_at` | When applicable | 結束時間 |
| `registered_by` | Required | 建立者或系統 |
| `execution_owner` | Required | 執行責任 |
| `audit_owner` | When applicable | 審計責任，正式階段通常為 `04` |

所有時間必須使用帶時區 timestamp。

### 10.3 Strategy and Specification

| Field | Requirement |
|---|---|
| `strategy_id` | Required for strategy experiments |
| `strategy_version` | Required for strategy experiments |
| `parent_mode` | Required for strategy experiments |
| `specification_version` | Required for formal experiments |
| `config_version` | Required for formal experiments |
| `config_uri` | Required for formal experiments |
| `config_hash` | Required for formal experiments |

### 10.4 Code and Environment

| Field | Requirement |
|---|---|
| `code_commit_sha` | Required |
| `repository` | Required |
| `working_tree_clean` | Required |
| `runtime_name` | Required |
| `runtime_version` | Required |
| `dependency_lock_hash` | Required |
| `container_image_digest` | When applicable |
| `operating_system` | Required |
| `architecture` | Required |
| `execution_command` | Required |
| `random_seed` | When randomness exists |

正式實驗的 `working_tree_clean` 必須為 `true`。若不是，Evidence Eligibility 原則上不得高於 Provisional。

### 10.5 Data and PIT

| Field | Requirement |
|---|---|
| `dataset_manifest_id` | Required |
| `dataset_versions` | Required |
| `source_versions` | Required |
| `feature_versions` | Required |
| `pit_policy_version` | Required |
| `availability_rule_versions` | Required |
| `exchange_calendar_version` | Required |
| `data_cutoff_at` | Required |
| `as_of_rule` | Required |
| `pit_quality_status` | Required |
| `input_manifest_hash` | Required |

### 10.6 Research Design

| Field | Requirement |
|---|---|
| `hypothesis_reference` | Required for formal strategy research |
| `research_question` | Required |
| `primary_metric` | Required for formal research |
| `secondary_metrics` | Required |
| `benchmark_ids` | Required when performance is evaluated |
| `acceptance_gate_version` | Required for formal research |
| `multiple_testing_family_id` | When applicable |
| `planned_variant_count` | When applicable |
| `design_manifest_hash` | Required when design lock applies |

### 10.7 Sample Windows

每個 window 必須包含：

- `window_id`
- `window_role`
- `start_at`
- `end_at`
- `data_cutoff_rule`
- `embargo_period`
- `purge_period`
- `market_regime_tags`
- `accessed_before_lock`

不得只保存單一模糊的 `backtest_period`。

### 10.8 Transaction Model

至少包含：

- Commission model and version
- Tax model and version
- Slippage model and version
- Market impact model and version
- Borrowing or financing cost, when applicable
- Execution price rule
- Order delay
- Failed-order policy
- Limit-up and limit-down handling
- Suspension handling
- Missing-price handling
- Capacity assumptions

實際費率或市場規則不得硬編碼為永久事實，必須引用版本化 contract。

### 10.9 Parameters

每個 parameter 至少包含：

- `parameter_name`
- `parameter_value`
- `data_type`
- `unit`
- `source`: `SPECIFICATION` / `CONFIG` / `DIAGNOSTIC`
- `locked_before_execution`

禁止只保存無型別字串。

### 10.10 Status Fields

必須保存第 8 節所有適用狀態軸，以及每次狀態變更事件。

## 11. Run Attempt Schema

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

## 12. Experiment Lineage

### 12.1 Supported Relationship Types

`relationship_type` 使用：

```text
RETEST_OF
REPRODUCTION_OF
SUPERSEDES
DIAGNOSTIC_VARIANT_OF
DERIVED_FROM
CONTINUATION_OF
PAPER_CAMPAIGN_SUCCESSOR_OF
INVALIDATES
```

### 12.2 Retest

Retest 必須：

- 建立新 Experiment ID
- 填入 `retest_of_experiment_id`
- 記錄 Retest reason
- 記錄哪些版本改變
- 記錄哪些策略規則保持不變
- 保留原實驗及其狀態

若策略行為改變，必須先依 Strategy Lifecycle 建立新 Strategy ID 或 Version，再建立 Retest Experiment。

### 12.3 Reproduction

Reproduction 必須：

- 建立新 Experiment ID
- 填入 `reproduction_of_experiment_id`
- 說明是同環境或獨立環境重現
- 定義預期一致性容忍度
- 保存差異報告

### 12.4 Diagnostic Variant

Diagnostic Variant 必須：

- 關聯正式基準 Experiment
- 標記 `DIAGNOSTIC_VARIANT`
- 不得自動取得 Confirmatory 或 OOS 證據資格
- 不得靜默取代正式 Strategy Version

### 12.5 Lineage Integrity

Experiment lineage 必須：

- 禁止循環關係
- 禁止實驗 supersede 自己
- 保留所有父子關係
- 支援由任一 Experiment 回溯完整 lineage

## 13. Multiple Testing and Experiment Families

每個包含多參數、多因子、多 Universe、多 window 或多策略變體的研究，必須保存：

- `multiple_testing_family_id`
- Family research question
- Planned variants
- Executed variants
- Unexecuted variants
- Variant selection rule
- Primary hypothesis
- Adjustment method
- Whether results were inspected sequentially
- Whether testing stopped after a favorable result

禁止把同一 family 中最好的實驗單獨呈現成唯一測試。

若探索後選定正式策略，必須：

1. 保存全部探索 variants。
2. 建立新的正式 Strategy Version 或 Specification。
3. 建立新的 Confirmatory Experiment。
4. 不得把探索樣本重新命名為 OOS。

## 14. OOS and Walk-forward Requirements

### 14.1 OOS Registration

OOS 實驗至少保存：

- OOS window
- OOS lock time
- First access time
- Strategy and Config hashes at lock
- Whether any OOS data was viewed before lock
- Contamination status
- Contamination reason
- Replacement holdout plan, if contaminated

### 14.2 OOS Contamination

下列任一情況原則上構成 confirmed contamination：

- 查看 OOS 結果後改參數
- 查看 OOS 結果後改 Universe
- 查看 OOS 結果後改 Gate
- 使用 OOS 挑選 Strategy Version
- 重複查看同一區間直到結果滿意

Contaminated OOS 結果仍須保存，但不得再宣稱為 clean OOS evidence。

### 14.3 Walk-forward

Walk-forward campaign 必須保存每一 fold：

- Train window
- Validation window
- Test window
- Purge or embargo
- Parameter selection output
- Frozen test configuration
- Fold results
- Aggregation rule

不得只保存聚合後總績效。

## 15. Paper Trading Campaigns

### 15.1 Campaign Identity

每個 Paper Trading campaign 使用一個 Experiment ID。

每日或每次訊號週期可以建立 Observation 或 Decision Snapshot，不必每天建立新 Experiment ID。

但下列情況必須終止舊 campaign 並建立新 Experiment ID：

- Strategy Version 改變
- Config 改變
- Code behavior 改變
- Data Contract 改變
- Execution model 改變
- 重大 incident 後需要正式 Retest

### 15.2 Required Fields

Paper Trading Experiment 至少保存：

- Campaign start and planned end
- Strategy, Config, Code and Data versions
- Live data arrival contract
- Decision Snapshot references
- Signal count
- Proposed order count
- Simulated fill count
- Missed order count
- Delayed order count
- Manual intervention count
- Data incident count
- Model deviation count
- Estimated slippage
- Monitoring coverage

### 15.3 Campaign Integrity

不得在同一 Paper Trading Experiment 中混用多個 Strategy Version 後再報告單一績效。

## 16. Metric Schema

### 16.1 Generic Metric Record

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

### 16.2 Performance Metrics

依策略性質可包含：

- Total Return
- CAGR
- Annualized Volatility
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Calmar Ratio
- Hit Rate
- Profit Factor
- Alpha
- Beta
- Information Ratio
- Tracking Error
- Excess Return

### 16.3 Portfolio and Trading Metrics

可包含：

- Turnover
- Number of holdings
- Average holding period
- Gross exposure
- Net exposure
- Concentration
- Industry exposure
- Top contributor share
- Trade count
- Fill rate
- Unfilled rate
- Slippage
- Capacity estimate
- Participation rate

### 16.4 Robustness Metrics

可包含：

- Parameter neighborhood stability
- Regime consistency
- Year contribution dispersion
- Security contribution concentration
- Cost stress survival
- Liquidity stress survival
- Exclusion-test results

### 16.5 Metric Integrity

每個報告中的數字必須能回指 Metric Record 或 Artifact。

不得手動複製數字而失去來源。

## 17. Artifact Schema

每個 artifact 至少包含：

- `artifact_id`
- `experiment_id`
- `artifact_type`
- `uri`
- `content_hash`
- `hash_algorithm`
- `media_type`
- `size_bytes`
- `generated_at`
- `generated_by_run_attempt_id`
- `retention_class`
- `access_class`
- `contains_licensed_data`
- `contains_sensitive_data`

### 17.1 Artifact Types

建議使用：

```text
CONFIG
INPUT_MANIFEST
DATASET_MANIFEST
FEATURE_MANIFEST
RUN_LOG
ERROR_LOG
TRADE_LOG
HOLDINGS
PORTFOLIO_RETURNS
BENCHMARK_RETURNS
METRICS
CHART
REPORT
GATE_EVALUATION
REPRODUCTION_REPORT
DIFF_REPORT
DECISION_SNAPSHOT_REFERENCE
```

### 17.2 Artifact Retention

正式實驗的核心 artifacts 不得因策略 Retire、Supersede 或 Invalidated 而刪除。

若授權限制禁止保存原始資料，必須至少保存：

- Source reference
- Dataset version
- Retrieval time
- Manifest
- Hash
- Reproduction instructions
- License limitation

### 17.3 Secret and Sensitive Data

Registry 與 artifacts 禁止保存：

- API secret
- Password
- Broker credential
- Private key
- 未經允許的個人資料

## 18. Issue, Warning, and Incident Schema

每個 issue 至少包含：

- `issue_id`
- `experiment_id`
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

### 18.1 Severity

```text
INFO
WARNING
ERROR
BLOCKER
```

### 18.2 Categories

```text
DATA_QUALITY
PIT
SURVIVORSHIP
LOOKAHEAD
IMPLEMENTATION
REPRODUCIBILITY
TRANSACTION_COST
LIQUIDITY
BENCHMARK
OOS_CONTAMINATION
MULTIPLE_TESTING
OPERATIONAL
SECURITY
OTHER
```

### 18.3 No Silent Failure

任何 `ERROR` 或 `BLOCKER` 不得只寫入 log 而不更新 Registry。

## 19. Invalidation

### 19.1 Invalidation Triggers

可能包括：

- Look-ahead leakage
- Wrong announcement date
- Wrong Universe
- Missing delisted securities
- Incorrect transaction costs
- Material code bug
- Dataset silently overwritten
- Wrong Config used
- Results cannot be reproduced
- Output does not match Specification

### 19.2 Invalidation Record

必須保存：

- Invalidated at
- Invalidated by
- Finding
- Root cause
- Affected outputs
- Affected downstream experiments
- Affected Decision Records
- Bias direction
- Required Retest scope
- Replacement Experiment ID, if available

### 19.3 Downstream Propagation

若某 Experiment 被 invalidated，所有依賴其輸出或證據的下游實驗與 Decision Records 必須被標記為：

- Affected
- Under review
- Invalidated，若影響實質結論

不得只修正最上游紀錄而保持下游 Promote 決策不變。

## 20. Non-reproducible Experiments

若在相同版本與輸入下無法重現主要結果：

- `reproducibility_status = NON_REPRODUCIBLE`
- `evidence_eligibility_status = INELIGIBLE`，除非審計有更嚴格處理
- 必須保存 reproduction attempts
- 必須記錄差異範圍
- 必須建立 Retest 或 Retire decision request

不得以「大致差不多」掩蓋超出事前 tolerance 的差異。

## 21. Supersession

Supersession 用於表示有更適合的後續實驗，但不否定舊實驗當時的完整性。

必須保存：

- `superseded_by_experiment_id`
- Supersession reason
- Superseded at
- Whether old evidence remains historically valid

禁止用 Superseded 隱藏 Invalidated。

## 22. Gate Evaluation Schema

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

Gate status 只能使用：

```text
PASS
CONDITIONAL_PASS
FAIL
NOT_DEMONSTRATED
NOT_APPLICABLE
```

`NOT_DEMONSTRATED` 不得被計算為 PASS。

實驗執行後修改 Gate 必須建立新 Strategy／Specification／Gate Version 與新 Experiment ID，依變更性質處理。

## 23. Decision Record Linkage

Experiment Registry 必須能關聯：

- `requested_decision`
- `decision_record_id`
- `decision_type`
- `decision_at`
- `decision_scope`

但正式決策內容屬於 Decision Record，不應複製成可被獨立修改的 Registry 欄位。

允許的正式 decision type：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

一個 Decision Record 可以引用多個 Experiment ID。

一個 Experiment 不得自行產生 Promote 結論。

## 24. Registry Event Log

每個狀態或重要欄位變動必須建立 event：

- `event_id`
- `experiment_id`
- `event_type`
- `occurred_at`
- `actor`
- `previous_value`
- `new_value`
- `reason`
- `source_reference`

Event types 至少包括：

```text
REGISTERED
DESIGN_LOCKED
QUEUED
STARTED
COMPLETED
FAILED
ABORTED
CANCELLED
ARTIFACT_ADDED
ISSUE_ADDED
STATUS_CHANGED
CORRECTED
INVALIDATED
REPRODUCIBILITY_UPDATED
SUPERSEDED
OOS_CONTAMINATION_UPDATED
DECISION_LINKED
RETEST_LINKED
```

## 25. Correction Policy

純 metadata 錯字或錯誤引用可以修正，但必須：

- 保存原值
- 保存新值
- 保存 correction reason
- 保存 actor and timestamp
- 不得改變原始 research output

若修正會影響結果或結論，必須建立新 Experiment ID，而不是 metadata correction。

## 26. Canonical Storage Model

工程實作可以採 relational database、document store 或 hybrid model，但至少應支援下列邏輯集合：

```text
experiment_records
run_attempts
experiment_windows
experiment_parameters
experiment_inputs
experiment_metrics
experiment_artifacts
experiment_issues
experiment_gate_results
experiment_lineage
experiment_events
```

### 26.1 Required Constraints

至少包括：

- `experiment_id` unique and immutable
- `run_attempt_id` unique
- Foreign-key or equivalent integrity
- Lineage cycle prevention
- No hard delete for formal records
- Timestamp with timezone
- Enum validation
- Hash format validation
- Completed experiments require terminal timestamps
- Formal experiments require version manifests

### 26.2 Query Requirements

系統至少應支援：

- 依 Strategy ID and Version 查詢所有實驗
- 依 lifecycle stage 查詢
- 依 evidence status 查詢
- 查詢所有 failed or invalidated experiments
- 查詢 Retest lineage
- 查詢 OOS contamination
- 查詢使用特定 Dataset or Code Version 的所有實驗
- 查詢某 defect 影響的下游 experiments
- 重建某 Decision Record 的 Evidence Package

## 27. Canonical YAML Example

```yaml
experiment_id: EXP-20260710-01J2TWSTOCKA7M4K9Z8Q6P
experiment_family_id: FAM-TW-M03-REV-MOM-V1-001
experiment_name: monthly-revenue-momentum-baseline-is
experiment_purpose: HISTORICAL_BACKTEST
experiment_scope: SINGLE_RUN
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

windows:
  - window_id: IS-001
    window_role: IN_SAMPLE
    start_at: 2012-01-01T00:00:00+08:00
    end_at: 2020-12-31T23:59:59+08:00
    embargo_period: P0D
    purge_period: P0D
    accessed_before_lock: false

status:
  execution_status: COMPLETED
  evidence_eligibility_status: PROVISIONAL
  integrity_status: VERIFIED
  reproducibility_status: NOT_TESTED
  supersession_status: CURRENT
  oos_contamination_status: NOT_APPLICABLE

lineage:
  retest_of_experiment_id: null
  reproduction_of_experiment_id: null
  superseded_by_experiment_id: null
```

範例只示範欄位結構，不代表該策略、資料或日期已獲核准。

## 28. Validation Rules

Registry 寫入至少必須執行下列規則。

### Rule 1: Unique Experiment ID

重複 Experiment ID 必須拒絕。

### Rule 2: Formal Version Completeness

正式實驗缺少 Strategy、Config、Code、Dataset、Feature 或 PIT 版本時必須阻擋。

### Rule 3: OOS Lock

OOS 在 design lock 前已被存取時，不能標記 CLEAN。

### Rule 4: Completed Timestamp

`COMPLETED` 必須有 `started_at` 與 `completed_at`，且時間順序有效。

### Rule 5: Retest Link

`experiment_purpose = RETEST` 必須有 `retest_of_experiment_id`。

### Rule 6: Reproduction Link

`experiment_purpose = REPRODUCTION` 必須有 `reproduction_of_experiment_id`。

### Rule 7: Invalidated Evidence

`integrity_status = INVALIDATED` 時，Evidence Eligibility 必須為 `INELIGIBLE`。

### Rule 8: Non-reproducible Evidence

`reproducibility_status = NON_REPRODUCIBLE` 時，Evidence Eligibility 不得為 `ELIGIBLE`。

### Rule 9: Dirty Working Tree

正式實驗 `working_tree_clean = false` 時，Evidence Eligibility 不得高於 `PROVISIONAL`。

### Rule 10: Strategy Version Consistency

Registry、Config、Specification 與 artifact manifest 的 Strategy Version 必須一致。

### Rule 11: No Silent Errors

存在 unresolved `BLOCKER` 時，不得標記 Evidence Eligibility 為 `ELIGIBLE`。

### Rule 12: Paper Campaign Version Freeze

同一 Paper Trading Experiment 不得跨 Strategy Version。

### Rule 13: No Hard Delete

正式 Experiment Record 的 hard delete 必須被系統禁止。

### Rule 14: Lineage Cycle

任何 lineage cycle 必須拒絕。

### Rule 15: Gate Integrity

看過結果後修改 Gate 的實驗不得聲稱通過原事前 Gate。

## 29. Engineering Acceptance Criteria

Experiment Registry 的第一版實作至少必須達成：

- [ ] 每次正式執行自動產生唯一 Experiment ID。
- [ ] Experiment ID 不可修改或重複使用。
- [ ] Registry 使用多軸狀態，不以單一 status 混合語意。
- [ ] 正式實驗在執行前可以鎖定 design manifest。
- [ ] Strategy、Specification、Config、Code、Data、Feature、PIT 與 Calendar 版本可追蹤。
- [ ] 所有 parameters 有型別、單位與來源。
- [ ] IS、Validation、OOS、Walk-forward 與 Paper Trading windows 可分開保存。
- [ ] Retest、Reproduction、Diagnostic Variant 與 Supersession 關係可查詢。
- [ ] Failed、Cancelled、Invalidated、Non-reproducible 與 Superseded 實驗永久保存。
- [ ] OOS contamination 可記錄並阻止錯誤標示為 clean OOS。
- [ ] Run Attempt 與新 Experiment 的邊界受到驗證。
- [ ] Registry 支援 artifact hash 與 manifest。
- [ ] BLOCKER 會阻止 Evidence Eligibility 變成 ELIGIBLE。
- [ ] Invalidated experiment 的下游影響可以追蹤。
- [ ] Gate Results 使用固定 enum。
- [ ] Decision Record 只能引用 Registry，不得改寫 Registry 結果。
- [ ] Paper Trading campaign 在版本改變時強制建立新 Experiment ID。
- [ ] 所有重要變更產生 append-only Registry Event。
- [ ] 系統禁止正式 Experiment hard delete。
- [ ] 可由 Experiment ID 重建完整 Evidence Package。

## 30. Manual Acceptance Tests

### Test A: Duplicate ID

Given：已存在 Experiment ID。

When：再次建立相同 ID。

Expected：寫入被拒絕。

### Test B: Retest Preservation

Given：原實驗因資料錯誤需要 Retest。

When：建立修正後實驗。

Expected：新 Experiment ID、正確 `RETEST_OF` 關係，原實驗保留並標記適當狀態。

### Test C: Invalidated Propagation

Given：上游 Dataset defect invalidates 多個 experiments。

When：登錄 invalidation。

Expected：可查出所有下游 experiments 與 affected decisions。

### Test D: OOS Contamination

Given：OOS 在設計鎖定前已被查看。

When：嘗試標記 CLEAN。

Expected：系統拒絕並要求 SUSPECTED 或 CONFIRMED。

### Test E: Paper Version Change

Given：Paper Trading campaign 進行中。

When：Strategy Version 改變。

Expected：舊 campaign 結束，建立新 Experiment ID。

### Test F: Failed Experiment Retention

Given：Experiment execution failed。

When：研究頁面只篩選成功結果。

Expected：Registry 仍可搜尋、顯示與統計失敗實驗。

### Test G: Reproduction Failure

Given：Reproduction 超出 tolerance。

When：更新 reproducibility status。

Expected：標記 NON_REPRODUCIBLE，Evidence Eligibility 不得維持 ELIGIBLE。

### Test H: Dirty Tree

Given：正式實驗在未提交程式碼下執行。

Expected：Registry 記錄 dirty tree，Evidence Eligibility 不得高於 PROVISIONAL。

## 31. Research Reporting Requirements

正式研究頁面或報告至少應顯示：

- Experiment ID
- Experiment purpose
- Strategy ID and Version
- Evidence classification
- Execution status
- Evidence eligibility
- Integrity status
- Reproducibility status
- Supersession status
- OOS contamination status
- Code and Dataset versions
- Test windows
- Primary metrics
- Gate summary
- Known issues
- Decision Record reference

報告不得只顯示最佳實驗而隱藏同 family 的其他 variants。

允許：

> 此 OOS 實驗已完成，但因樣本被用於後續規則修改，污染狀態為 Confirmed，結果保留供審計，不再視為 clean OOS evidence。

不允許：

> 這次回測表現最好，所以它就是正式策略。

## 32. Prohibited Practices

TWStock 禁止：

- 重複使用 Experiment ID
- 覆蓋舊結果
- 刪除失敗或無效實驗
- 只登錄成功實驗
- 把 Run Attempt 當作規避新 Experiment ID 的方式
- 先看結果再偽造 design lock
- 把 exploratory result 標記為 confirmatory
- 把反覆查看的樣本標記為 OOS
- 用 Superseded 隱藏 Invalidated
- 用 Completed 代表 Valid
- 在同一 Paper Trading Experiment 混用多個 Strategy Version
- 不保存 Dataset 或 Code Version
- 手動修改 metric 而不保存來源
- 靜默忽略 BLOCKER
- 讓 Decision Record 改寫原始實驗結果
- 將回測結果描述為未來獲利保證

## 33. Exceptions

任何偏離本文件的例外都必須：

1. 明確記錄。
2. 指定 Experiment ID 或適用實驗類型。
3. 說明必要性。
4. 評估對重現性與偏誤的影響。
5. 設定到期或重審條件。
6. Evidence Eligibility 不得高於 Provisional，除非正式政策修訂另有規定。
7. 不得用例外結果直接支持 Promote。

例外不得成為隱藏預設。

## 34. Migration and Backfill

若將既有歷史回測補登至 Registry：

- 必須標記 `registration_mode = RETROSPECTIVE_BACKFILL`
- 保存原執行日期，如可取得
- 保存補登日期
- 不得偽造事前 design lock
- 缺少版本或 artifact 時標記 Provisional、Restricted 或 Ineligible
- 不得因補登而提高原證據等級

## 35. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Experiment ID 規則改變
- Classification enums 改變
- Status axes 改變
- Design lock 規則改變
- Mandatory fields 改變
- Retest or Reproduction lineage 規則改變
- OOS contamination 規則改變
- Invalidation propagation 改變
- Artifact retention 改變
- Gate linkage 改變
- Engineering acceptance criteria 改變

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Migration
- Affected Experiments
- Required Reclassification or Retest

## 36. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
2. `docs/research/VALIDATION_PROTOCOL.md`
3. Dataset-specific Data Contracts
4. Thin Website Information Architecture
5. Foundation Engine implementation contracts

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
