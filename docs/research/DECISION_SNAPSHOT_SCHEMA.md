# TWStock Decision Snapshot Schema

- Document ID: `TWSTOCK-RESEARCH-DECISION-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: TWStock research-stage decisions, formal validation decisions, lifecycle transitions, Paper Trading operational snapshots, Live Observation snapshots, decision conditions, expiration, supersession, correction, and evidence-impact handling

## 1. Purpose

本文件定義 TWStock 如何在決策當下建立不可靜默改寫、可重現、可審計、可回溯證據與版本的 Decision Snapshot。

Decision Snapshot 的核心目的不是只保存「結論」，而是永久回答：

- 誰在什麼時間、依什麼權限作出決策？
- 決策適用於哪一個 Strategy ID、Strategy Version、Experiment、Campaign 或 lifecycle stage？
- 決策當時實際可見的資料、版本、實驗、Gate、限制與風險是什麼？
- 決策是 Promote、Revise、Retest、Retire，還是正式 Historical Backtest 前的階段性決策？
- 決策是否附帶條件、期限、監控要求或重新驗證觸發條件？
- 決策是否已被後續資料缺陷、實驗 invalidation、版本變更或 retirement 影響？
- 決策是否已被 supersede、expire、suspend 或 invalidate？
- Paper Trading 或 Live Observation 的某一次訊號週期，當時使用了哪些資料與版本並產生什麼研究輸出？

核心原則：

> Decision Snapshot 必須保存決策當下的事實與證據狀態，不得由未來資訊回寫成「當時早已知道」。

本文件不判定任何策略必然有效，不提供個股買賣建議，也不授權真實資金交易、自動下單或券商串接。

## 2. Authority and Document Relationships

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`
4. `docs/research/STRATEGY_LIFECYCLE.md`
5. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`

後續文件將進一步具體化：

- `docs/research/VALIDATION_PROTOCOL.md`
- Dataset-specific Data Contracts
- Strategy-specific Executable Specifications
- Strategy YAML Configs
- Engineering storage and API contracts
- Website reporting contracts

權限邊界：

- Strategy Lifecycle 定義允許的階段、責任角色與正式決策。
- Experiment Registry 保存實驗事實、狀態、版本、依賴與 artifacts。
- Decision Snapshot 固定決策當下引用的證據與結論。
- Decision Snapshot 不得反向修改 Experiment Registry 的原始結果。
- Experiment Registry 的新結果不得靜默改寫既有 Decision Snapshot。
- 正式 Historical Backtest 形成後，只有 `04｜台股策略驗證與審計`可以作出 Promote、Revise、Retest 或 Retire。
- 早期 Research、Specification 與 Engineering 決策由對應工作模式負責，不得冒充正式 Validation Decision。

若網站、報告、GitHub 說明或聊天內容與正式 Decision Snapshot 衝突，以版本化 Decision Snapshot、Experiment Registry、Lifecycle Record 與原始 artifacts 為準。

## 3. Scope and Non-goals

### 3.1 In Scope

本文件適用於：

- Idea 與 Hypothesis 階段決策
- Specification readiness decision
- Engineering readiness decision
- Historical Backtest 後的 Promote／Revise／Retest／Retire
- Lifecycle state transition
- Retirement and reopening references
- Conditional decision and expiry
- Periodic review and revalidation trigger
- Evidence invalidation impact
- Decision supersession and correction
- Paper Trading operational decision snapshots
- Live Observation operational snapshots
- Retrospective backfill of historical decisions

### 3.2 Out of Scope

本文件不直接定義：

- 投資假設或策略規則
- Strategy acceptance thresholds
- Gate 的數值內容
- 特定資料庫、雲端或 UI 技術
- 真實資金配置
- 券商下單授權
- 投資人適合度或法令遵循核准
- 個股推薦、目標價或報酬保證

## 4. Snapshot Profiles

Decision Snapshot 使用兩個彼此分離的 profile。

### 4.1 Governance Decision Snapshot

`GOVERNANCE_DECISION` 保存研究、規格、工程或正式驗證決策。

它可以：

- 允許或拒絕階段轉移
- 記錄 Promote、Revise、Retest 或 Retire
- 記錄 retirement scope
- 指定條件、期限、責任人與下一步
- 建立正式 Lifecycle Transition

### 4.2 Operational Research Snapshot

`OPERATIONAL_RESEARCH_SNAPSHOT` 保存 Paper Trading 或 Live Observation 中某一訊號週期的 point-in-time 研究輸出。

它可以保存：

- 當時可得資料與 `as_of` 狀態
- Universe、eligibility 與 tradability
- Signal、ranking、proposed portfolio 與 proposed orders
- 模擬成交或未成交原因
- 資料事件、人工介入與版本偏離

它不得：

- 作出 Promote、Revise、Retest 或 Retire
- 改變 Lifecycle State
- 表示真實資金核准
- 被描述為投資建議或自動交易授權

### 4.3 Profiles Must Not Be Conflated

禁止：

- 用 Operational Snapshot 取代正式 Validation Decision
- 用 Governance Decision 保存每日大量訊號資料
- 用單一模糊 `decision_type` 混合治理決策與操作觀察

## 5. Core Decision Principles

### 5.1 Point-in-Time Decision Record

每個 Snapshot 只可以使用 `evidence_cutoff_at` 或 `decision_as_of_at` 以前已公開、已取得且已登錄的資訊。

未來發生的 Experiment、資料修正或市場結果，只能透過：

- Decision Impact Record
- New Decision Snapshot
- Superseding Decision
- Invalidation Event

進行關聯，不得回寫原決策理由。

### 5.2 Append-only and Immutable

正式 Snapshot 必須 append-only。

允許：

- 增加 event
- 增加 impact assessment
- 增加 correction record
- 增加 supersession relationship
- 增加 condition satisfaction record

禁止：

- 覆蓋原始 decision action
- 刪除失敗或被否決決策
- 修改原 evidence snapshot 使決策看起來更合理
- 把 expired、affected 或 invalidated 決策改寫成從未存在

### 5.3 Evidence Before Decision

正式 Validation Decision 必須引用完整 Evidence Package。

缺少關鍵 Strategy、Specification、Config、Code、Data、Feature、PIT、Experiment、Gate 或 artifact 版本時，不得 Promote。

### 5.4 Exact Scope

每個決策必須明確指定適用範圍。

禁止使用：

- 「這個策略可以」
- 「回測已經成功」
- 「整體看起來沒問題」

而不指定 Strategy ID、Version、Stage、Experiment 與 decision scope。

### 5.5 Decision Is Not Evidence

Decision Snapshot 保存治理結論，但不會把弱證據變成強證據。

- Promote 不會提高原 Experiment 的完整性或重現性。
- Retest 不會自動修復原實驗。
- Retire 不會刪除原證據。
- Supersede 不等於原決策 Invalidated。

### 5.6 Negative Evidence Must Be Visible

Decision Snapshot 必須保存：

- Failed Gates
- Counter-evidence
- Known limitations
- Dissent or unresolved uncertainty
- Negative or null experiments
- Missing evidence
- Material incidents

不得只引用支持結論的最佳實驗。

## 6. Identity and Immutability Rules

### 6.1 Governance Decision ID

建議格式：

```text
DEC-{YYYYMMDD}-{ULID}
```

### 6.2 Operational Snapshot ID

建議格式：

```text
OPS-{YYYYMMDD}-{ULID}
```

### 6.3 Related IDs

建議格式：

```text
EVS-{ULID}        # Evidence Snapshot
TRN-{ULID}        # Lifecycle Transition
COND-{ULID}       # Decision Condition
DIM-{ULID}        # Decision Impact
AMD-{ULID}        # Decision Amendment or Correction
```

### 6.4 Identity Requirements

所有 ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 可作為資料庫主鍵
- 不依賴可變更的 Strategy Name 或 PR title

### 6.5 New Snapshot Triggers

下列情況必須建立新 Governance Decision ID：

- 新的正式 Promote／Revise／Retest／Retire
- 原 Decision 的 action、scope、stage target 或 authority 改變
- 條件未達成後重新作出決策
- Evidence invalidation 後重新審計
- Expired Decision 重新核准
- Retirement 後重新開啟研究
- 原決策實質錯誤且需要替代結論

下列情況必須建立新 Operational Snapshot ID：

- 新訊號週期
- 新交易日或再平衡日
- Snapshot 形成後重新計算研究輸出
- 使用不同 frozen-version manifest
- 人工介入後形成新的正式研究輸出

## 7. Classification Axes

### 7.1 Snapshot Profile

```text
GOVERNANCE_DECISION
OPERATIONAL_RESEARCH_SNAPSHOT
```

### 7.2 Registration Mode

```text
PROSPECTIVE
RETROSPECTIVE_BACKFILL
```

Retrospective backfill 不得偽造當時不存在的 evidence snapshot、approval、design lock 或 timestamp precision。

### 7.3 Decision Domain

Governance Decision 使用：

```text
RESEARCH
SPECIFICATION
ENGINEERING
VALIDATION
REOPENING
```

### 7.4 Decision Class

```text
STAGE_DECISION
LIFECYCLE_TRANSITION
FORMAL_VALIDATION
REOPENING_DECISION
PERIODIC_REVIEW
```

### 7.5 Pre-evidence Actions

Historical Backtest 正式證據形成前，可使用：

```text
PROCEED
REVISE
PARK
REJECT
READY_FOR_NEXT_STAGE
RETURN_TO_PREVIOUS_STAGE
BLOCKED
REOPEN_FOR_RESEARCH
```

這些 action 不得被標記為正式 Validation Decision。

### 7.6 Formal Validation Actions

自 Historical Backtest 起，只能使用：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

### 7.7 Decision Scope Type

```text
STRATEGY_VERSION
STRATEGY_LINEAGE
LIFECYCLE_STAGE
EXPERIMENT_SET
CAMPAIGN
RESEARCH_PROPOSAL
SPECIFICATION_VERSION
ENGINEERING_SCOPE
```

### 7.8 Effectivity Mode

```text
IMMEDIATE
CONDITIONALLY_EFFECTIVE
NOT_EFFECTIVE_UNTIL_CONDITIONS_MET
DEFERRED
```

Effectivity Mode 不會創造第五種 Validation Action。

### 7.9 Current Decision Standing

Current standing 是由 append-only events 衍生，不得直接覆蓋原 Snapshot：

```text
CURRENT
CONDITION_PENDING
CONDITIONS_SATISFIED
EXPIRED
SUSPENDED
SUPERSEDED
POTENTIALLY_AFFECTED
UNDER_REVIEW
AFFECTED
INVALIDATED
```

## 8. Authority Matrix

### 8.1 Early-stage Authority

| Decision Domain | Owner | Allowed Scope |
|---|---|---|
| `RESEARCH` | `01｜台股研究與策略大腦` | Idea、Hypothesis、research priority、Park／Reject／Proceed |
| `SPECIFICATION` | `02｜台股研究規格轉譯` | Specification readiness、return to research |
| `ENGINEERING` | `03｜TWStock 工程轉譯` with human review | Engineering readiness、scope decomposition、return to specification |

### 8.2 Formal Validation Authority

`VALIDATION` domain 的 `PROMOTE / REVISE / RETEST / RETIRE`：

- 必須由 `04｜台股策略驗證與審計`作出。
- 必須存在正式 Experiment evidence。
- 必須引用 Evidence Snapshot。
- 不得由工程角色、Codex、網站或自動評分器單獨作出。

### 8.3 Human Accountability

每個正式 Decision 必須保存：

- `decision_owner_workspace`
- `decision_actor`
- `reviewed_by`, when applicable
- `approved_by`, when human approval is required
- `authority_basis`
- `authority_verified_at`

自動化系統可以：

- 準備 evidence package
- 計算 Gate
- 偵測矛盾
- 建議 requested decision

但不得在沒有正式 authority 的情況下自行把 Strategy Lifecycle State 改為已 Promote 或 Retired。

## 9. Time Model

### 9.1 Governance Decision — Prospective

必須保存：

- `registry_registered_at`
- `evidence_cutoff_at`
- `decision_at`
- `recorded_at`
- `effective_at`
- `expires_at`, when applicable
- `next_review_at`, when applicable

原則上：

```text
evidence_cutoff_at
≤ decision_at
≤ recorded_at
≤ effective_at
```

若 immediate effect，`effective_at` 可以等於 `decision_at`。

### 9.2 Operational Snapshot — Prospective

必須保存：

- `data_cutoff_at`
- `decision_as_of_at`
- `snapshot_formed_at`
- `recorded_at`
- `market_timezone`
- `trading_date`, when applicable

原則上：

```text
data_cutoff_at
≤ decision_as_of_at
≤ snapshot_formed_at
≤ recorded_at
```

### 9.3 Retrospective Backfill

必須分開保存：

- `original_decision_at`, if known
- `original_effective_at`, if known
- `original_evidence_cutoff_at`, if known
- `backfilled_at`
- `timestamp_source`
- `timestamp_precision`
- `timestamp_confidence`
- `source_document_ids`

不得把 `backfilled_at` 當成原決策時間。

原則上：

```text
original_decision_at
≤ backfilled_at
```

若時間不明，必須使用 null 與明確 confidence，不得虛構秒級時間。

### 9.4 General Time Rules

- 所有 timestamp 必須帶時區。
- Decision 不得引用 `evidence_cutoff_at` 以後形成的 evidence。
- Correction、Impact、Supersession event 必須晚於原 Decision registration。
- Condition satisfaction time 不得早於 condition creation。
- Operational Snapshot 不得使用 `decision_as_of_at` 以後才取得的資料。

## 10. Common Snapshot Envelope

所有 Snapshot 至少包含：

### 10.1 Identity

- `snapshot_id`
- `snapshot_profile`
- `schema_version`
- `registration_mode`
- `snapshot_name`
- `snapshot_hash`

### 10.2 Subject

依適用性保存：

- `strategy_id`
- `strategy_version`
- `parent_mode`
- `research_proposal_id`
- `specification_version`
- `config_version`
- `experiment_ids`
- `campaign_id`
- `observation_id`
- `lifecycle_record_id`

### 10.3 Provenance

- `created_by`
- `source_system`
- `source_reference_ids`
- `git_commit_sha`
- `working_tree_clean`, when generated from code
- `recorded_at`
- `timezone`

### 10.4 Integrity

- `content_hash`
- `hash_algorithm`
- `evidence_snapshot_hash`, for Governance Decisions
- `frozen_version_manifest_hash`, for Campaign snapshots
- `integrity_status`
- `known_integrity_findings`

## 11. Governance Decision Record Schema

每個 Governance Decision 至少包含以下欄位。

### 11.1 Decision Identity and Classification

- `decision_record_id`
- `decision_domain`
- `decision_class`
- `decision_action`
- `decision_scope_type`
- `decision_scope_ids`
- `effectivity_mode`
- `requested_decision`, when different from final decision

### 11.2 Strategy and Lifecycle Scope

依適用性保存：

- `strategy_id`
- `strategy_version`
- `affected_strategy_versions`
- `parent_mode`
- `from_lifecycle_state`
- `to_lifecycle_state`
- `target_workspace`
- `target_stage`
- `transition_id`

### 11.3 Authority

- `decision_owner_workspace`
- `decision_actor`
- `reviewed_by`
- `approved_by`
- `authority_basis`
- `authority_verified_at`

### 11.4 Time

依第 9 節保存：

- Registry timestamps
- Decision timestamps
- Effectivity timestamps
- Expiration and review timestamps

### 11.5 Evidence

- `evidence_snapshot_id`
- `evidence_snapshot_hash`
- `experiment_ids`
- `gate_evaluation_ids`
- `artifact_ids`
- `evidence_classification_summary`
- `evidence_eligibility_summary`
- `reproducibility_summary`
- `pit_quality_summary`
- `oos_contamination_summary`
- `dependency_impact_summary`

### 11.6 Rationale

- `decision_rationale`
- `primary_findings`
- `counter_evidence`
- `alternatives_considered`
- `uncertainty_assessment`
- `residual_risks`
- `known_limitations`
- `dissenting_view`, when applicable

### 11.7 Conditions and Follow-up

- `condition_ids`
- `monitoring_requirements`
- `revalidation_triggers`
- `next_required_action`
- `next_review_at`
- `expires_at`
- `handoff_reference`
- `github_issue_ids`
- `pull_request_ids`

### 11.8 Decision Standing

原 Snapshot 保存原始決策；Current standing 由以下關聯衍生：

- `superseded_by_decision_id`
- `decision_impact_ids`
- `condition_status_summary`
- `expiration_event_id`
- `suspension_event_id`
- `invalidation_event_id`

## 12. Evidence Snapshot Schema

### 12.1 Purpose

Evidence Snapshot 固定 Decision 當時可見的 Evidence Package，而不是只儲存動態查詢條件。

### 12.2 Evidence Snapshot Identity

- `evidence_snapshot_id`
- `decision_record_id`
- `evidence_cutoff_at`
- `created_at`
- `content_hash`
- `hash_algorithm`

### 12.3 Version Manifest

至少保存適用的：

- Strategy ID and Version
- Specification Version
- Config Version and Hash
- Code Commit SHA
- Code Behavior Version
- Dataset Manifest IDs and Versions
- Data Contract Versions
- Feature Versions
- PIT Policy Version
- Availability Rule Versions
- Exchange Calendar Version
- Transaction Model Version
- Execution Model Version
- Campaign Frozen Manifest Hash, when applicable

### 12.4 Experiment Evidence Items

每個引用 Experiment 至少保存當時的：

- `experiment_id`
- `experiment_purpose`
- `evidence_classification`
- `execution_status`
- `evidence_eligibility_status`
- `integrity_status`
- `reproducibility_status`
- `oos_contamination_status`
- `dependency_impact_status`
- `supersession_status`
- `registry_event_cutoff_id`
- `metric_record_ids`
- `artifact_ids`
- `issue_ids`

不得只保存 Experiment ID 後動態顯示最新狀態，否則無法知道決策當下實際引用的狀態。

### 12.5 Gate Evidence

至少保存：

- `gate_id`
- `gate_version`
- `threshold`
- `observed_value`
- `gate_status`
- `evidence_artifact_ids`
- `evaluated_at`
- `evaluated_by`

### 12.6 Completeness

Evidence Snapshot 必須記錄：

- `required_item_count`
- `present_item_count`
- `missing_items`
- `completeness_status`
- `completeness_assessed_at`

`completeness_status`：

```text
COMPLETE
PARTIAL
INSUFFICIENT
```

`PARTIAL` 或 `INSUFFICIENT` 原則上不得支持 Promote。

## 13. Formal Decision Profiles

### 13.1 Promote

Promote 必須保存：

- `promoted_from`
- `promoted_to`
- Evidence Snapshot
- Gate summary
- Remaining limitations
- Monitoring requirements
- Revalidation triggers
- Next review date
- Required inputs for next stage
- Whether effectivity is immediate or conditional

Promote 必須符合：

- Evidence Snapshot complete
- 沒有 unresolved Blocker
- 適用的 Gates 已達成或有明確 Conditional Pass
- Evidence Eligibility 可支持該 stage transition
- 下一階段輸入已準備完成

Promote 不代表：

- 未來必然獲利
- 真實資金核准
- 永久有效
- 可以停止監控

### 13.2 Revise

Revise 必須保存：

- `finding_ids`
- `revision_reason`
- `return_to_workspace`: `01` or `02`
- `return_to_stage`
- `revision_scope`
- `strategy_identity_assessment_status`
- `elements_may_be_preserved`
- `elements_must_not_be_preserved`
- `oos_evidence_reuse_prohibited`
- `paper_approval_reuse_prohibited`
- `required_new_strategy_or_version_assessment`
- `required_handoff`

Revise 不得由 `04` 直接修改策略規則使結果通過。

新 Strategy ID、MAJOR、MINOR 或 PATCH 必須依 Strategy Lifecycle 由 `01`／`02`判定。

### 13.3 Retest

Retest 必須保存：

- `finding_ids`
- `retest_reason`
- `retest_scope`
- `return_to_workspace`
- `return_to_stage`
- `strategy_version_preserved`
- `elements_may_be_preserved`
- `elements_must_be_recreated`
- `required_version_changes`
- `required_new_experiment_id = true`
- `original_experiment_ids`
- `replacement_experiment_plan`
- `required_evidence_for_reaudit`

Retest 不一定需要新 Strategy Version，但一定需要新 Experiment ID。

### 13.4 Retire

Retire 必須保存：

```text
retirement_scope: VERSION | LINEAGE
```

以及：

- `retirement_reason`
- `affected_strategy_id`
- `affected_strategy_versions`
- `supporting_experiment_ids`
- `failed_gate_ids`
- `final_strategy_version`
- `final_experiment_ids`
- `successor_strategy_id`, when applicable
- `successor_strategy_version`, when applicable
- `reopening_conditions`
- `retirement_effective_at`

`VERSION`：

- 只停止指定 Strategy Version。
- 其他版本不會自動 Retire。
- 必須記錄 successor version。

`LINEAGE`：

- 停止整條 Strategy ID lineage。
- 所有尚未 Retired 的版本必須建立關聯 transition。
- 不得建立新版本規避 lineage retirement。

Retired records 不得刪除。

## 14. Early-stage Decision Profile

Historical Backtest 前的 Governance Decision 必須使用：

- `decision_domain = RESEARCH | SPECIFICATION | ENGINEERING`
- `decision_class = STAGE_DECISION | LIFECYCLE_TRANSITION`
- Pre-evidence Action enum

至少保存：

- Current conclusion
- Decision rationale
- Responsible workspace
- From and target stage
- Required handoff
- Open questions
- Blocking findings
- Required next artifact
- Scope and out of scope

禁止：

- 使用 `PROMOTE` 冒充正式 Validation Decision
- 把 Idea Proceed 描述成策略已驗證
- 讓 Engineering readiness 決定投資規則是否有效

## 15. Decision Conditions

### 15.1 Condition Record

每個條件至少包含：

- `condition_id`
- `decision_record_id`
- `condition_description`
- `condition_category`
- `required_evidence`
- `responsible_owner`
- `due_at`
- `verification_method`
- `failure_consequence`
- `condition_status`
- `verified_by`
- `verified_at`
- `evidence_reference_ids`

### 15.2 Condition Status

```text
PENDING
SATISFIED
FAILED
EXPIRED
WAIVED_BY_NEW_POLICY
```

### 15.3 No Silent Conditional Pass

`CONDITIONALLY_EFFECTIVE` 或 `NOT_EFFECTIVE_UNTIL_CONDITIONS_MET` 必須：

- 有至少一個 Condition Record
- 指定 owner
- 指定 due date 或明確事件條件
- 指定未達成的後果
- 指定驗證 evidence

條件達成不得修改原 Decision；必須建立 Condition Satisfaction Event。

條件失敗或過期不得讓 Promote 繼續被顯示為無條件有效。

## 16. Lifecycle Transition Contract

### 16.1 Transition Record

每次 Lifecycle State 改變必須建立：

- `transition_id`
- `strategy_id`
- `strategy_version`
- `from_state`
- `to_state`
- `decision_record_id`
- `transition_at`
- `transition_actor`
- `transition_status`
- `conditions`

### 16.2 Atomicity

Decision Record 與 Lifecycle Transition 應採原子寫入或具補償事件的 transaction model。

禁止：

- Lifecycle State 已改變但沒有 Decision Record
- Decision 表示 Promote，但 Lifecycle State 靜默跳過中間階段
- 只移動 GitHub Project card 而沒有正式 transition

### 16.3 One Current Primary State

同一 Strategy Version 同一時點只能有一個 Current Lifecycle State。

### 16.4 Operational Snapshot Boundary

Operational Research Snapshot 不得建立 Lifecycle Transition。

## 17. Operational Research Snapshot Schema

每個 Operational Snapshot 至少包含以下內容。

### 17.1 Identity and Campaign

- `operational_snapshot_id`
- `campaign_id`
- `observation_id`
- `experiment_id`
- `strategy_id`
- `strategy_version`
- `snapshot_profile = OPERATIONAL_RESEARCH_SNAPSHOT`
- `frozen_version_manifest_hash`

### 17.2 Point-in-Time Data

- `trading_date`
- `market_timezone`
- `data_cutoff_at`
- `decision_as_of_at`
- `source_arrival_status`
- `pit_quality_status`
- `availability_rule_versions`
- `exchange_calendar_version`
- `dataset_manifest_ids`
- `input_manifest_hash`

### 17.3 Version Consistency

- `specification_version`
- `config_version`
- `config_hash`
- `code_commit_sha`
- `code_behavior_version`
- `data_contract_versions`
- `feature_versions`
- `transaction_model_version`
- `execution_model_version`
- `monitoring_policy_version`
- `version_consistency_status`

`version_consistency_status`：

```text
MATCHED
DEVIATION_RECORDED
BLOCKED
```

`BLOCKED` Snapshot 不得納入 Campaign 正式績效。

### 17.4 Universe and Tradability

- `universe_snapshot_id`
- `universe_definition_version`
- `eligible_security_count`
- `tradable_security_count`
- `excluded_security_count`
- `exclusion_reason_summary`
- `tradability_mask_version`
- `liquidity_rule_version`
- `limit_up_down_rule_version`
- `suspension_rule_version`

### 17.5 Signal and Portfolio Output

- `signal_artifact_id`
- `ranking_artifact_id`
- `proposed_holdings_artifact_id`
- `proposed_orders_artifact_id`
- `portfolio_weighting_version`
- `risk_constraint_version`
- `benchmark_reference`
- `cash_position`
- `turnover_estimate`
- `capacity_warning_summary`

### 17.6 Execution Simulation

- `simulated_fill_artifact_id`
- `unfilled_order_artifact_id`
- `delayed_order_artifact_id`
- `estimated_slippage`
- `failed_order_reason_summary`
- `manual_intervention`
- `manual_intervention_reason`
- `override_actor`
- `override_at`

### 17.7 Incidents and Integrity

- `data_incident_ids`
- `code_incident_ids`
- `monitoring_alert_ids`
- `blocker_ids`
- `snapshot_integrity_status`
- `reproducibility_status`
- `rerun_diff_artifact_id`

### 17.8 Explicit Non-authorization

每個 Operational Snapshot 必須保存：

```text
real_capital_authorized: false
broker_execution_authorized: false
automated_order_submission_authorized: false
```

在目前 TWStock scope 中，上述欄位不得為 true。

## 18. Rationale, Counter-evidence, and Uncertainty

每個正式 Governance Decision 必須以結構化方式保存：

### 18.1 Primary Findings

- 支持 action 的主要 findings
- 對應 Experiment、Gate 或 artifact
- Materiality
- Bias direction

### 18.2 Counter-evidence

- 不支持 action 的實驗
- Failed or conditional Gates
- 不利 Regime
- 集中度或容量問題
- 未解決的資料限制

### 18.3 Alternatives Considered

至少說明適用的替代 action：

- Why not Promote
- Why not Revise
- Why not Retest
- Why not Retire

### 18.4 Uncertainty

使用：

```text
LOW
MODERATE
HIGH
UNKNOWN
```

並保存 uncertainty reason。

Decision Snapshot 不得使用「信心很高」取代可檢查證據。

## 19. Expiration, Periodic Review, and Revalidation

### 19.1 Required Review Fields

進入 Paper Trading 或 Live Observation 的 Decision 至少包含：

- `review_frequency`
- `next_review_at`
- `maximum_period_without_review`
- `expires_at`
- `revalidation_triggers`
- `data_incident_triggers`
- `code_incident_triggers`
- `market_rule_change_triggers`

### 19.2 Expiration

超過 `expires_at` 或最大未審查期間：

- Decision standing 必須轉為 `EXPIRED` 或 `SUSPENDED`。
- 不得假設原 Promote 永久有效。
- 必須建立新 Periodic Review Decision 或 Retest Decision。
- 原 Decision 保留。

### 19.3 Revalidation Trigger

觸發條件至少包括：

- Data Contract 改變
- PIT rule 改變
- Market rule 改變
- Transaction cost 顯著改變
- Code behavior 改變
- Strategy long-term drift
- Signal or fill failure
- Concentration risk increase
- Major incident
- Economic rationale breakdown

## 20. Retirement and Reopening

### 20.1 Retirement Linkage

Retirement Decision 必須連結：

- Lifecycle retirement transition
- Affected Strategy Version records
- Experiment evidence
- Failed Gates
- Successor reference
- Reopening conditions

### 20.2 Reopening Decision

Reopening 必須建立新 Governance Decision ID，使用：

- `decision_domain = REOPENING`
- `decision_class = REOPENING_DECISION`
- `decision_action = REOPEN_FOR_RESEARCH`

至少保存：

- Original Retirement Decision ID
- Original retirement scope
- New evidence or changed condition
- Whether economic mechanism remains the same
- Required Strategy ID／Version assessment
- Restart lifecycle stage
- Evidence that must not be reused

Reopening 不會恢復原 Retired Version 為 active，也不得刪除原失敗證據。

## 21. Decision Impact and Invalidation

### 21.1 Impact Triggers

可能來源包括：

- Experiment invalidation
- Dataset defect
- PIT defect
- Code bug
- Config mismatch
- Feature error
- OOS contamination
- Reproduction failure
- Campaign manifest drift
- Gate calculation defect

### 21.2 Decision Impact Status

```text
UNAFFECTED
POTENTIALLY_AFFECTED
UNDER_REVIEW
AFFECTED
INVALIDATED
```

### 21.3 Decision Impact Record

至少包含：

- `decision_impact_id`
- `decision_record_id`
- `source_invalidation_id`
- `dependency_path`
- `impact_status`
- `materiality_assessment`
- `affected_conclusions`
- `affected_transition_id`
- `required_action`
- `assessed_by`
- `assessed_at`
- `resolved_by_decision_id`, when applicable

### 21.4 Effect on Decision Standing

- `POTENTIALLY_AFFECTED`：不得繼續無條件顯示為 current authoritative approval。
- `UNDER_REVIEW`：相關 Promote 應顯示 suspended pending review。
- `AFFECTED`：必須明確限制受影響 conclusion 或 transition。
- `INVALIDATED`：原 Decision 不再具有治理效力，必須重新審計。

不得只修正上游 Experiment 而保持下游 Promote Decision 看起來完全有效。

## 22. Correction, Amendment, and Supersession

### 22.1 Metadata Correction

僅限不影響 action、scope、evidence、rationale、authority 或 effectivity 的錯字與引用錯誤。

必須建立 Amendment Record：

- `amendment_id`
- `decision_record_id`
- `field_path`
- `old_value`
- `new_value`
- `reason`
- `actor`
- `amended_at`

### 22.2 Material Correction

若修正影響：

- Decision Action
- Decision Scope
- Strategy Version
- Lifecycle transition
- Evidence Package
- Retirement scope
- Conditions
- Rationale conclusion

必須建立新 Decision ID，並以 `SUPERSEDES` 關聯原 Decision。

### 22.3 Supersession Is Not Invalidation

- Superseded：後續決策取代原決策的 current governance role。
- Invalidated：原決策依據或程序存在使其失去效力的缺陷。

不得用 Superseded 隱藏 Invalidated。

## 23. Decision Precedence Rules

當多個 Decision 涉及相同 Strategy scope 時，依下列規則決定 current authoritative record：

1. `INVALIDATED` Decision 不具 current authority。
2. `SUPERSEDED` Decision 不具 current authority，但保留歷史效力描述。
3. 未解決的 `UNDER_REVIEW` Promote 不得顯示為無條件 current approval。
4. Lineage-level Retirement 優先於同 lineage 的非 Retirement version decisions。
5. Version-level Retirement 只影響指定 Version。
6. Formal Validation Decision 優先於 Operational Snapshot。
7. Operational Snapshot 不得覆蓋 Governance Decision。
8. Early-stage Decision 不得覆蓋已存在的 Formal Validation Decision。
9. 新 Decision 必須明確引用它 supersede、reopen 或 resolve 的舊 Decision。
10. 條件滿足事件不會自動改變 Decision Action，只改變 effectivity standing。

## 24. Canonical Storage Model

工程實作至少支援：

```text
governance_decisions
operational_snapshots
evidence_snapshots
evidence_snapshot_experiments
evidence_snapshot_gates
decision_conditions
condition_events
lifecycle_transitions
decision_findings
decision_limitations
decision_alternatives
decision_impacts
decision_amendments
decision_relationships
decision_events
```

### 24.1 Required Constraints

至少包括：

- IDs unique and immutable
- No hard delete for formal records
- Append-only events
- Timestamp with timezone
- Enum validation
- Hash validation
- Foreign-key or equivalent integrity
- Decision authority validation
- Decision-domain/action compatibility
- Scope validation
- Evidence cutoff validation
- Evidence snapshot immutability
- Lifecycle transition consistency
- Only one current primary lifecycle state
- Retirement scope validation
- Conditional decision completeness
- Registration-mode-specific time validation
- Operational snapshot frozen-manifest consistency
- Operational snapshot real-capital authorization fields fixed to false

### 24.2 Query Requirements

系統至少支援：

- 依 Strategy ID and Version 查詢所有 Decisions
- 查詢某 Lifecycle transition 的 Decision
- 查詢某 Experiment 被哪些 Decisions 引用
- 重建 Decision 當時的 Evidence Snapshot
- 查詢所有 Conditional、Expired、Affected 或 Invalidated Decisions
- 查詢 Retirement 與 Reopening lineage
- 查詢 Decision supersession chain
- 查詢受 Dataset／Code／PIT defect 影響的 Decisions
- 查詢 Campaign 下所有 Operational Snapshots
- 查詢某一 trading date 的 point-in-time Snapshot
- 查詢所有 manual intervention 或 manifest mismatch

## 25. Canonical YAML Examples

### 25.1 Formal Promote Decision

```yaml
decision_record_id: DEC-20260710-01J2PROMOTE0001
snapshot_profile: GOVERNANCE_DECISION
schema_version: 1.0.0
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: PROMOTE
decision_scope_type: STRATEGY_VERSION
decision_scope_ids:
  - TW-M03-MONTHLY-REVENUE-MOMENTUM@1.0.0
effectivity_mode: IMMEDIATE
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
from_lifecycle_state: HISTORICAL_BACKTEST
to_lifecycle_state: ROBUSTNESS_VALIDATION
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
decision_at: 2026-07-10T20:30:00+08:00
recorded_at: 2026-07-10T20:35:00+08:00
effective_at: 2026-07-10T20:30:00+08:00
decision_owner_workspace: workspace-04
decision_actor: human-auditor
authority_basis: TWSTOCK-RESEARCH-LIFECYCLE-001@1.0.0
evidence_snapshot_id: EVS-01J2PROMOTEEVIDENCE
evidence_snapshot_hash: sha256:example
experiment_ids:
  - EXP-20260710-01J2BASELINE
  - EXP-20260710-01J2REPRO
primary_findings:
  - historical backtest gates passed after transaction costs
counter_evidence:
  - concentration remains elevated in one industry
known_limitations:
  - OOS has not yet been executed
monitoring_requirements:
  - track industry concentration during robustness validation
revalidation_triggers:
  - dataset or PIT policy version change
next_required_action: execute preregistered robustness experiments
next_review_at: 2026-08-10T09:00:00+08:00
real_capital_authorized: false
```

### 25.2 Formal Retest Decision

```yaml
decision_record_id: DEC-20260710-01J2RETEST0001
snapshot_profile: GOVERNANCE_DECISION
schema_version: 1.0.0
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: RETEST
decision_scope_type: EXPERIMENT_SET
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
from_lifecycle_state: ROBUSTNESS_VALIDATION
to_lifecycle_state: IMPLEMENTATION
effectivity_mode: IMMEDIATE
evidence_cutoff_at: 2026-07-10T21:00:00+08:00
decision_at: 2026-07-10T21:15:00+08:00
recorded_at: 2026-07-10T21:20:00+08:00
effective_at: 2026-07-10T21:15:00+08:00
decision_owner_workspace: workspace-04
decision_actor: human-auditor
retest_reason: monthly revenue availability timestamp mapping defect
retest_scope:
  - rebuild affected dataset snapshot
  - rerun leakage tests
  - rerun historical and robustness experiments
strategy_version_preserved: true
required_new_experiment_id: true
original_experiment_ids:
  - EXP-20260709-01J2INVALID
required_version_changes:
  dataset_version: required
  code_version: when implementation changes
elements_may_be_preserved:
  - strategy hypothesis
  - signal formula
elements_must_be_recreated:
  - dataset manifest
  - affected experiment outputs
required_evidence_for_reaudit:
  - clean leakage test
  - reproducible replacement experiments
```

### 25.3 Retire Lineage Decision

```yaml
decision_record_id: DEC-20260710-01J2RETIRE0001
snapshot_profile: GOVERNANCE_DECISION
schema_version: 1.0.0
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: RETIRE
decision_scope_type: STRATEGY_LINEAGE
retirement_scope: LINEAGE
strategy_id: TW-M06-MEAN-REVERSION-X
strategy_version: 2.1.0
affected_strategy_versions:
  - 1.0.0
  - 2.0.0
  - 2.1.0
from_lifecycle_state: OUT_OF_SAMPLE
to_lifecycle_state: RETIRED
retirement_reason: repeated OOS failure after costs and unacceptable liquidity concentration
supporting_experiment_ids:
  - EXP-20260601-01J2OOS1
  - EXP-20260701-01J2OOS2
failed_gate_ids:
  - GATE-OOS-NET-EXCESS
  - GATE-LIQUIDITY-STRESS
reopening_conditions:
  - materially new economic evidence
  - independently sourced tradable dataset
successor_strategy_id: null
successor_strategy_version: null
```

### 25.4 Operational Research Snapshot

```yaml
operational_snapshot_id: OPS-20260801-01J2PAPER0001
snapshot_profile: OPERATIONAL_RESEARCH_SNAPSHOT
schema_version: 1.0.0
registration_mode: PROSPECTIVE
campaign_id: CAM-01J2PAPER
observation_id: CAM-01J2PAPER-OBS-01J2ABC
experiment_id: EXP-20260801-01J2PAPEREXP
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
frozen_version_manifest_hash: sha256:campaign
data_cutoff_at: 2026-08-01T17:00:00+08:00
decision_as_of_at: 2026-08-01T18:00:00+08:00
snapshot_formed_at: 2026-08-01T18:01:00+08:00
recorded_at: 2026-08-01T18:01:30+08:00
trading_date: 2026-08-01
market_timezone: Asia/Taipei
version_consistency_status: MATCHED
pit_quality_status: PIT_VERIFIED
eligible_security_count: 742
tradable_security_count: 701
excluded_security_count: 41
signal_artifact_id: ART-SIGNAL-0001
ranking_artifact_id: ART-RANK-0001
proposed_holdings_artifact_id: ART-HOLD-0001
proposed_orders_artifact_id: ART-ORDER-0001
manual_intervention: false
snapshot_integrity_status: VERIFIED
reproducibility_status: NOT_TESTED
real_capital_authorized: false
broker_execution_authorized: false
automated_order_submission_authorized: false
```

### 25.5 Retrospective Decision Backfill

```yaml
decision_record_id: DEC-20260710-01J2BACKFILL01
snapshot_profile: GOVERNANCE_DECISION
schema_version: 1.0.0
registration_mode: RETROSPECTIVE_BACKFILL
decision_domain: RESEARCH
decision_class: STAGE_DECISION
decision_action: PARK
original_decision_at: 2025-12-20T09:00:00+08:00
original_effective_at: null
original_evidence_cutoff_at: null
backfilled_at: 2026-07-10T22:00:00+08:00
timestamp_source: archived-research-note
timestamp_precision: DAY
timestamp_confidence: MODERATE
source_document_ids:
  - DOC-LEGACY-20251220
```

## 26. Validation Rules

1. Governance and Operational profiles must not share incompatible action fields.
2. Formal Validation Action must be one of Promote／Revise／Retest／Retire.
3. Formal Validation Decision must have `decision_domain = VALIDATION` and owner `workspace-04`.
4. Pre-evidence Decision must not use formal Validation Action.
5. Promote requires complete Evidence Snapshot and valid Gate evidence.
6. Promote requires exact from-state and to-state.
7. Revise requires return workspace, revision scope and preservation restrictions.
8. Retest requires `required_new_experiment_id = true` and original Experiment references.
9. Retire requires `retirement_scope: VERSION | LINEAGE`.
10. Lineage Retirement must identify all affected active versions.
11. Conditional effectivity requires complete Condition Records.
12. Expired conditions must not leave Decision standing as unconditionally current.
13. Decision must not reference evidence formed after `evidence_cutoff_at`.
14. Evidence Snapshot must preserve Experiment statuses as of decision time.
15. Lifecycle Transition must reference a valid Governance Decision.
16. Operational Snapshot must not create Lifecycle Transition.
17. Operational Snapshot must match Campaign frozen-version manifest.
18. `version_consistency_status = BLOCKED` must exclude Snapshot from formal Campaign performance.
19. Operational real-capital authorization fields must remain false.
20. Decision Impact `POTENTIALLY_AFFECTED` or `UNDER_REVIEW` must prevent unconditional current approval display.
21. Invalidated Decision must not remain authoritative.
22. Material correction requires new Decision ID.
23. Superseded must not hide Invalidated.
24. Registration mode must select the correct time-validation profile.
25. No formal Decision hard delete.

## 27. Engineering Acceptance Criteria

第一版實作至少必須達成：

- [ ] Governance Decision 與 Operational Snapshot 分開儲存。
- [ ] 每個正式 Decision／Snapshot 自動產生唯一 immutable ID。
- [ ] Decision 使用 append-only events，不覆蓋原結論。
- [ ] Early-stage authority 與 formal Validation authority 可以 machine-validate。
- [ ] Promote／Revise／Retest／Retire 使用固定 enum。
- [ ] Decision scope 必須指定 Strategy、Version、Stage、Experiment 或 Campaign。
- [ ] Evidence Snapshot 固定 Decision 當下的 Experiment 狀態與 artifact hashes。
- [ ] Evidence cutoff 阻止引用未來 evidence。
- [ ] Promote 缺少必要 Evidence Package 時被拒絕。
- [ ] Conditional Decision 強制保存 owner、due date、evidence 與 failure consequence。
- [ ] Retest 強制新 Experiment ID。
- [ ] Retire 強制 VERSION／LINEAGE scope。
- [ ] Lifecycle transition 與 Decision 保持一致。
- [ ] 同一 Strategy Version 只有一個 current primary lifecycle state。
- [ ] Operational Snapshot 驗證 Campaign frozen manifest。
- [ ] Operational Snapshot 不得授權真實資金或券商下單。
- [ ] Expiration 與 periodic review 可被排程與查詢。
- [ ] Experiment invalidation 可傳遞到 Decision Impact。
- [ ] Affected／Invalidated Promote 不會繼續顯示為無條件 current approval。
- [ ] Supersession、Correction、Reopening 與 Retirement lineage 可回溯。
- [ ] Failed、Rejected、Retired、Expired 與 Invalidated records 永久保留。
- [ ] 可由 Decision ID 重建完整 Evidence Snapshot、Rationale、Conditions 與 Transition。

## 28. Manual Acceptance Tests

### Test A: Invalid Authority

Given：Engineering workspace 嘗試建立 formal Promote。

Expected：寫入被拒絕。

### Test B: Future Evidence

Given：Decision cutoff 為 2026-07-10 20:00，引用 21:00 完成的 Experiment。

Expected：Decision 寫入被拒絕。

### Test C: Incomplete Promote Evidence

Given：Promote 缺少 Dataset Version 或 Gate evidence。

Expected：Promote 被拒絕或只能建立非有效 Draft record，不得改變 Lifecycle State。

### Test D: Retest Without New Experiment Requirement

Given：Retest 未設定新 Experiment ID requirement。

Expected：寫入被拒絕。

### Test E: Retire Without Scope

Given：Retire 未指定 VERSION 或 LINEAGE。

Expected：寫入被拒絕。

### Test F: Lineage Retirement

Given：Lineage 有三個 active versions。

Expected：Retire Decision 關聯全部版本並阻止建立新版本規避 retirement。

### Test G: Conditional Promote

Given：Decision 為 conditionally effective，但沒有 owner 或 due date。

Expected：寫入被拒絕。

### Test H: Condition Expiration

Given：Promote condition 到期未達成。

Expected：Decision standing 轉為 expired／suspended，不得繼續顯示為無條件 current Promote。

### Test I: Experiment Invalidation

Given：Promote 引用的主要 Experiment 被 invalidated。

Expected：建立 Decision Impact，Promote 轉為 potentially affected／under review，並要求重新審計。

### Test J: Material Correction

Given：使用者想把原 Retest action 改成 Promote。

Expected：不得修改原 Decision；必須建立新 Decision 並 supersede 原 Decision。

### Test K: Operational Snapshot Manifest Mismatch

Given：Operational Snapshot Code Behavior Version 與 Campaign manifest 不一致。

Expected：標記 BLOCKED 或拒絕寫入，不得納入 Campaign 績效。

### Test L: Operational Snapshot Capital Authorization

Given：Snapshot 嘗試設定 `real_capital_authorized = true`。

Expected：在目前 policy 下寫入被拒絕。

### Test M: Retrospective Backfill

Given：2025 年決策於 2026 年補登。

Expected：原決策時間與 backfilled_at 分開保存，不要求 registry time 早於原決策，也不得偽造 evidence cutoff。

### Test N: Superseded Versus Invalidated

Given：舊 Decision 同時存在新 Decision 與 evidence defect。

Expected：分別保存 Supersession 與 Invalidation，不得只標記 Superseded 隱藏缺陷。

### Test O: Operational Snapshot Cannot Promote

Given：Paper Trading 日 Snapshot 嘗試設定 `decision_action = PROMOTE`。

Expected：寫入被拒絕。

## 29. Research and Website Reporting Requirements

正式策略頁面至少顯示：

- Strategy ID and Version
- Current Lifecycle State
- Latest applicable Governance Decision
- Decision Action and Scope
- Decision owner and date
- Evidence Snapshot ID
- Evidence classification and eligibility summary
- Gate summary
- Known limitations
- Conditions and due dates
- Expiration and next review date
- Decision standing
- Decision Impact status
- Retirement scope and successor, when applicable

Paper Trading／Live Observation 頁面至少顯示：

- Campaign ID
- Frozen-version manifest hash
- Latest Operational Snapshot ID
- Decision as-of time
- PIT quality and version consistency
- Signal and proposed portfolio artifacts
- Simulated fill status
- Incidents and manual interventions
- Explicit statement that real capital is not authorized

允許：

> Strategy Version 1.0.0 已由正式 Decision Record Promote 至 Out-of-Sample；此決策附有集中度監控條件，尚未取得 Paper Trading 或真實資金核准。

不允許：

> 這個策略已回測成功，可以直接買進。

## 30. Prohibited Practices

TWStock 禁止：

- 修改原 Decision Action 而不建立新 Decision ID
- 刪除被 Reject、Retest、Retire、Expire 或 Invalidate 的 Decision
- 用未來 Experiment 回寫過去 Decision rationale
- 只保存支持結論的最佳 Experiment
- 用 Operational Snapshot 取代 formal Validation Decision
- 用 formal Validation Action 包裝早期研究決策
- 讓 Engineering 或 Codex 單獨 Promote／Retire 策略
- Promote 時省略 Evidence Snapshot
- Retest 時沿用原 Experiment ID
- Retire 時不指定 VERSION／LINEAGE
- 用新 Strategy Version 規避 Lineage Retirement
- 條件過期後仍顯示無條件核准
- 用 Superseded 隱藏 Invalidated
- 只更新 Lifecycle State 而沒有 Decision Record
- Campaign 版本漂移後繼續使用同一 Operational Snapshot lineage
- 將 Live Observation 描述為 Live Capital Approval
- 在目前 policy 下把 Operational Snapshot 設為真實下單授權
- 將回測或 Paper Trading 描述為未來獲利保證

## 31. Exceptions and Backfill

任何例外都必須：

1. 明確記錄。
2. 指定 Decision／Snapshot ID 與適用範圍。
3. 說明必要性。
4. 評估對證據、PIT、重現性與偏誤的影響。
5. 指定 owner。
6. 設定到期或重審條件。
7. 不得用例外直接支持 Promote。

歷史 Decision 補登必須：

- `registration_mode = RETROSPECTIVE_BACKFILL`
- 保存 `backfilled_at`
- 保存原 Decision time 與來源，如可取得
- 保存 timestamp precision and confidence
- 不得偽造 Evidence Snapshot、authority 或 conditions
- 缺少 evidence 時標記 Partial／Insufficient
- 不得因補登提高原證據等級

## 32. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Snapshot profiles
- Decision authority matrix
- Formal action enums
- Decision scope rules
- Evidence Snapshot requirements
- Time model
- Conditional decision rules
- Lifecycle transition contract
- Retirement or reopening rules
- Operational Snapshot contract
- Expiration and periodic review rules
- Decision impact propagation
- Supersession and correction rules
- Engineering acceptance criteria

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Migration
- Affected Decisions and Strategies
- Required Reclassification or Retest

## 33. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/VALIDATION_PROTOCOL.md`
2. Dataset-specific Data Contracts
3. Thin Website Information Architecture
4. Foundation Engine implementation contracts
5. First monthly revenue／earnings momentum vertical slice specification

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
