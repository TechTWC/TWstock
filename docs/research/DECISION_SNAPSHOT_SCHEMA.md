# TWStock Decision Snapshot Schema

- Document ID: `TWSTOCK-RESEARCH-DECISION-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: TWStock research-stage decisions, formal validation decisions, periodic reviews, reopening decisions, lifecycle transitions, Paper Trading and Live Observation operational snapshots, conditions, expiration, supersession, correction, and evidence-impact handling

## 1. Purpose

本文件定義 TWStock 如何在決策當下建立不可靜默改寫、可重現、可審計、可回溯證據與版本的 Decision Snapshot。

Decision Snapshot 必須永久回答：

- 誰在什麼時間、依什麼權限作出決策？
- 決策適用於哪一個 Strategy ID、Strategy Version、Experiment、Campaign 或 lifecycle stage？
- 決策當時實際可見的資料、版本、實驗、Gate、限制與風險是什麼？
- 決策是正式 Promote、Revise、Retest、Retire，還是正式 Historical Backtest 前的階段性決策？
- 決策是否附帶條件、期限、監控要求或重新驗證觸發條件？
- 決策何時實際生效？是否仍在等待條件或延後啟動？
- 決策是否已被後續資料缺陷、實驗 invalidation、版本變更、expiration 或 retirement 影響？
- 同一策略版本目前的 authoritative governance record 是哪一筆？
- Paper Trading 或 Live Observation 的某一次訊號週期，當時使用了哪些資料與版本並產生什麼研究輸出？

核心原則：

> Decision Snapshot 保存決策當下的事實與證據狀態；未來資訊只能以新的事件、Impact Record、Superseding Decision 或 Reopening Decision 關聯，不得回寫成「當時早已知道」。

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
- Decision Snapshot 固定決策當下引用的證據、理由、條件與治理結論。
- Lifecycle Transition 是獨立實體，負責記錄狀態變動；它不是 Decision Class。
- Decision Snapshot 不得反向修改 Experiment Registry 的原始結果。
- Experiment Registry 的新結果不得靜默改寫既有 Decision Snapshot。
- 正式 Historical Backtest 證據形成後，只有 `04｜台股策略驗證與審計`可以作出 Promote、Revise、Retest 或 Retire。
- 早期 Research、Specification 與 Engineering 決策由對應工作模式負責，不得冒充正式 Validation Decision。
- Reopening 只重新啟動研究，不恢復原 Retired Version，也不代表原 Retirement Decision 失效。

若網站、報告、GitHub 說明或聊天內容與正式 Decision Snapshot 衝突，以版本化 Decision Snapshot、Experiment Registry、Lifecycle Record、Transition Records 與原始 artifacts 為準。

## 3. Scope and Non-goals

### 3.1 In Scope

本文件適用於：

- Idea 與 Hypothesis 階段決策
- Specification readiness decision
- Engineering readiness decision
- Historical Backtest 後的 Promote／Revise／Retest／Retire
- Periodic Review
- Lifecycle state transition
- Retirement and reopening references
- Conditional decision and activation
- Decision expiration and suspension
- Revalidation trigger
- Evidence invalidation impact
- Decision supersession and correction
- Paper Trading operational snapshots
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

`GOVERNANCE_DECISION` 保存研究、規格、工程、正式驗證、Periodic Review 或 Reopening 決策。

它可以：

- 允許或拒絕研究流程前進
- 記錄 Promote、Revise、Retest 或 Retire
- 記錄 Periodic Review outcome
- 記錄 Reopening decision
- 指定條件、期限、責任人與下一步
- 建立或引用 Lifecycle Transition Records

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
- 作出 Reopening Decision
- 改變 Lifecycle State
- 表示真實資金核准
- 被描述為投資建議或自動交易授權

### 4.3 Profiles Must Not Be Conflated

禁止：

- 用 Operational Snapshot 取代正式 Validation Decision
- 用 Governance Decision 保存每日大量訊號資料
- 用單一模糊 `decision_type` 混合治理決策與操作觀察
- 讓 Operational Snapshot 覆蓋 Governance Decision 的 current authority

## 5. Core Decision Principles

### 5.1 Point-in-Time Decision Record

每個 Snapshot 只可以使用 `evidence_cutoff_at` 或 `decision_as_of_at` 以前已公開、已取得且已登錄的資訊。

未來發生的 Experiment、資料修正或市場結果，只能透過：

- Decision Impact Record
- New Governance Decision
- Superseding Decision
- Invalidation Event
- Periodic Review
- Reopening Decision

進行關聯，不得回寫原決策理由。

### 5.2 Append-only and Immutable

正式 Snapshot 必須 append-only。

允許：

- 增加 event
- 增加 impact assessment
- 增加 correction record
- 增加 supersession relationship
- 增加 condition event
- 增加 activation、suspension、expiration 或 reversal event

禁止：

- 覆蓋原始 decision action
- 覆蓋原始 evidence snapshot
- 刪除失敗、被否決、Expired、Affected 或 Invalidated 決策
- 修改原 evidence snapshot 使決策看起來更合理
- 把失效決策改寫成從未存在

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
- Reopening 不會讓原 Retirement Decision 消失。

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

### 6.1 Canonical Snapshot ID

每筆 Snapshot 只使用一個 canonical primary key：`snapshot_id`。

- Governance Decision：`snapshot_id` 必須等於 `decision_record_id`。
- Operational Snapshot：`snapshot_id` 必須等於 `operational_snapshot_id`。

不得建立兩個可能不一致的主鍵值。

### 6.2 Governance Decision ID

建議格式：

```text
DEC-{YYYYMMDD}-{ULID}
```

### 6.3 Operational Snapshot ID

建議格式：

```text
OPS-{YYYYMMDD}-{ULID}
```

### 6.4 Related IDs

建議格式：

```text
EVS-{ULID}        # Evidence Snapshot
TRN-{ULID}        # Lifecycle Transition
TRG-{ULID}        # Transition Group
COND-{ULID}       # Decision Condition
CEV-{ULID}        # Condition Event
ACT-{ULID}        # Activation Event
DIM-{ULID}        # Decision Impact
AMD-{ULID}        # Decision Amendment or Correction
REL-{ULID}        # Decision Relationship
```

### 6.5 Identity Requirements

所有 ID 必須：

- 全域唯一
- 永久不變
- 不得重新使用
- 可作為資料庫主鍵或外鍵
- 不依賴可變更的 Strategy Name 或 PR title

### 6.6 New Snapshot Triggers

下列情況必須建立新 Governance Decision ID：

- 新的正式 Promote／Revise／Retest／Retire
- 新的 Periodic Review
- 新的 Reopening Decision
- 原 Decision 的 action、scope、stage target 或 authority 改變
- 條件失敗或到期後重新作出治理決策
- Evidence invalidation 後重新審計
- Expired Decision 重新核准
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

Retrospective backfill 不得偽造當時不存在的 evidence snapshot、approval、design lock、effectivity 或 timestamp precision。

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
FORMAL_VALIDATION
PERIODIC_REVIEW
REOPENING_DECISION
```

`LIFECYCLE_TRANSITION` 不是 Decision Class。Lifecycle Transition 使用第 18 節的獨立 Transition Entity。

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
```

這些 action 不得被標記為正式 Validation Decision。

### 7.6 Formal Validation Actions

自 Historical Backtest 起，正式 Validation Decision 只能使用：

```text
PROMOTE
REVISE
RETEST
RETIRE
```

### 7.7 Reopening Action

Reopening Decision 只能使用：

```text
REOPEN_FOR_RESEARCH
DECLINE_REOPENING
```

Reopening Action 不屬於 Formal Validation Action，也不得直接把 Lifecycle State 從 `RETIRED` 改回 active stage。

### 7.8 Decision Scope Type

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

### 7.9 Effectivity Mode

```text
IMMEDIATE
CONDITIONALLY_EFFECTIVE
NOT_EFFECTIVE_UNTIL_CONDITIONS_MET
DEFERRED
```

Effectivity Mode 不會創造第五種 Validation Action。

### 7.10 Periodic Review Outcome

`decision_class = PERIODIC_REVIEW` 時，`decision_action` 必須為 null，並使用：

```text
CONTINUE_CURRENT_STAGE
TRIGGER_FORMAL_DECISION
SUSPEND_PENDING_REVIEW
NO_LONGER_APPLICABLE
```

若 outcome 為 `TRIGGER_FORMAL_DECISION`，必須另外建立一筆 Promote、Revise、Retest 或 Retire Decision；Periodic Review 本身不得改變 Lifecycle State。

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

### 8.3 Periodic Review Authority

正式 Historical Backtest 以後的 `PERIODIC_REVIEW`：

- Review owner 為 `04｜台股策略驗證與審計`。
- 可以得出 `CONTINUE_CURRENT_STAGE`、`TRIGGER_FORMAL_DECISION`、`SUSPEND_PENDING_REVIEW` 或 `NO_LONGER_APPLICABLE`。
- 不得直接使用 Periodic Review 改變 Lifecycle State。
- 需要狀態變更時，必須另建正式 Validation Decision 與 Transition Record。

### 8.4 Reopening Authority

`decision_domain = REOPENING` 時：

- `01｜台股研究與策略大腦`是研究重啟判斷 Owner，負責判斷是否出現值得重新研究的新證據，以及原經濟／行為機制是否仍相同。
- 必須有明確 Human Approver。
- 原 Retirement 若為 `LINEAGE`，必須取得 `04` 對原 Retirement evidence、未解決限制與禁止重用證據的書面 acknowledgement。
- `02` 只在 Reopening 核准後負責版本與規格轉譯，不得自行批准 reopening。
- Reopening 只建立新的 Research Proposal 或版本評估，不得直接恢復原 Retired Version，也不得直接建立 active Lifecycle Transition。

### 8.5 Human Accountability

每個正式 Governance Decision 必須保存：

- `decision_owner_workspace`
- `decision_actor`
- `reviewed_by`, when applicable
- `approved_by`, when required
- `authority_basis`
- `authority_verified_at`

自動化系統可以：

- 準備 evidence package
- 計算 Gate
- 偵測矛盾
- 建議 requested decision

但不得在沒有正式 authority 的情況下自行改變 Strategy Lifecycle State。

## 9. Time and Effectivity Model

### 9.1 Governance Decision — Prospective Registration

必須保存：

- `registry_registered_at`
- `evidence_cutoff_at`
- `decision_at`
- `recorded_at`
- `effectivity_mode`
- `planned_effective_at`, when applicable
- `effective_at`, when actually effective
- `activation_event_id`, when activated after creation
- `activated_at`, when activated after creation
- `expires_at`, when applicable
- `next_review_at`, when applicable

共同時間規則：

```text
evidence_cutoff_at
≤ decision_at
≤ recorded_at
```

### 9.2 Immediate Effectivity

`effectivity_mode = IMMEDIATE`：

- `effective_at` 必須存在。
- `effective_at >= decision_at`。
- 若建立 Lifecycle Transition，Transition 可以直接為 `ACTIVE`。

### 9.3 Conditionally Effective

`effectivity_mode = CONDITIONALLY_EFFECTIVE`：

- Decision 可以在條件尚未全部完成時生效。
- `effective_at` 必須存在。
- 必須有至少一個 Condition Record。
- 必須指定 condition failure consequence。
- failure consequence 若要求 suspension 或 reversal，必須建立對應事件與 Transition compensation。

### 9.4 Not Effective Until Conditions Met

`effectivity_mode = NOT_EFFECTIVE_UNTIL_CONDITIONS_MET`：

- 建立 Decision 時 `effective_at = null`。
- `planned_effective_at` 可以存在或為 null。
- Lifecycle Transition 必須為 `PENDING_CONDITIONS`。
- 所有必要條件達成後，建立 Activation Event。
- Activation Event 寫入 `activated_at` 與實際 `effective_at`。
- 只有 Transition 轉為 `ACTIVE` 後，才可以改變 Current Lifecycle State。

### 9.5 Deferred Effectivity

`effectivity_mode = DEFERRED`：

- `planned_effective_at` 必須存在。
- 建立 Decision 時 `effective_at = null`。
- Lifecycle Transition 必須為 `PENDING_ACTIVATION`。
- 到達時間不代表自動生效；必須通過 activation preconditions 並建立 Activation Event。
- Activation 後才寫入 `effective_at` 並把 Transition 轉為 `ACTIVE`。

### 9.6 Operational Snapshot — Prospective

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

### 9.7 Retrospective Backfill

必須分開保存：

- `original_decision_at`, if known
- `original_effective_at`, if known and evidenced
- `original_evidence_cutoff_at`, if known
- `backfilled_at`
- `timestamp_source`
- `timestamp_precision`
- `timestamp_confidence`
- `source_document_ids`
- `original_authority_evidence_ids`

不得把 `backfilled_at` 當成原決策時間，也不得因補登而改變目前 Lifecycle State。

原則上：

```text
original_decision_at
≤ backfilled_at
```

若時間不明，必須使用 null 與明確 confidence，不得虛構秒級時間。

Retrospective Backfill 只有在原 authority、scope 與 effectivity 有文件證據時，才能描述歷史上曾生效；若要影響目前治理狀態，必須建立新的 Prospective Governance Decision。

### 9.8 General Time Rules

- 所有 timestamp 必須帶時區。
- Decision 不得引用 `evidence_cutoff_at` 以後形成的 evidence。
- Correction、Impact、Supersession、Expiration、Suspension、Activation event 必須晚於原 Decision registration。
- Condition satisfaction time 不得早於 condition creation。
- Operational Snapshot 不得使用 `decision_as_of_at` 以後才取得的資料。
- `effective_at` 不得早於 `decision_at`。

## 10. Independent Decision Status Axes

單一 `current_standing` 不得取代底層狀態軸，因為條件、期限、supersession 與 impact 可以同時存在。

### 10.1 Effectivity Status

```text
NOT_EFFECTIVE
PENDING_CONDITIONS
PENDING_ACTIVATION
EFFECTIVE
SUSPENDED
REVERSED
ENDED
```

### 10.2 Condition Status Summary

```text
NOT_APPLICABLE
PENDING
SATISFIED
FAILED
EXPIRED
WAIVED_BY_NEW_POLICY
```

### 10.3 Expiration Status

```text
NOT_APPLICABLE
ACTIVE_WINDOW
DUE_FOR_REVIEW
EXPIRED
```

### 10.4 Supersession Status

```text
CURRENT
SUPERSEDED
```

### 10.5 Impact Status

```text
UNAFFECTED
POTENTIALLY_AFFECTED
UNDER_REVIEW
AFFECTED
INVALIDATED
```

### 10.6 Validity Status

```text
NOT_ASSESSED
VALID
PROCEDURALLY_INVALID
EVIDENCE_INVALID
```

### 10.7 Derived Display Standing

網站可以計算 `current_display_standing`，但不得人工覆蓋，也不得取代上述狀態軸。

建議顯示優先順序：

```text
INVALIDATED
PROCEDURALLY_INVALID
EVIDENCE_INVALID
SUPERSEDED
UNDER_REVIEW
POTENTIALLY_AFFECTED
SUSPENDED
EXPIRED
PENDING_CONDITIONS
PENDING_ACTIVATION
EFFECTIVE_WITH_CONDITIONS
EFFECTIVE_CURRENT
NOT_EFFECTIVE
```

若多個底層狀態同時成立，UI 必須能顯示複合原因，而不是只保存一個字串。

## 11. Common Snapshot Envelope

所有 Snapshot 至少包含：

### 11.1 Identity

- `snapshot_id`
- `snapshot_profile`
- `schema_version`
- `registration_mode`
- `snapshot_name`
- `content_hash`
- `hash_algorithm`

### 11.2 Subject

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

### 11.3 Provenance

- `created_by`
- `source_system`
- `source_reference_ids`
- `git_commit_sha`
- `working_tree_clean`, when generated from code
- `recorded_at`
- `timezone`

### 11.4 Integrity

- `evidence_snapshot_hash`, for Governance Decisions
- `frozen_version_manifest_hash`, for Campaign snapshots
- `integrity_status`
- `known_integrity_findings`

## 12. Governance Decision Record Schema

每個 Governance Decision 至少包含以下欄位。

### 12.1 Decision Identity and Classification

- `decision_record_id`
- `snapshot_id`, equal to `decision_record_id`
- `decision_domain`
- `decision_class`
- `decision_action`, when applicable
- `periodic_review_outcome`, when applicable
- `decision_scope_type`
- `decision_scope_ids`
- `effectivity_mode`
- `requested_decision`, when different from final decision

### 12.2 Strategy and Lifecycle Scope

依適用性保存：

- `strategy_id`
- `strategy_version`
- `affected_strategy_versions`
- `parent_mode`
- `target_workspace`
- `target_stage`
- `transition_ids`
- `transition_group_id`, when multiple transitions share one decision

單筆 Decision 可以沒有 Transition，也可以引用一筆或多筆 Transition；不得使用單數 `transition_id` 表達 lineage-level multi-version retirement。

### 12.3 Authority

- `decision_owner_workspace`
- `decision_actor`
- `reviewed_by`
- `approved_by`
- `authority_basis`
- `authority_verified_at`
- `required_acknowledgement_ids`, when applicable

### 12.4 Time and Effectivity

依第 9 節保存：

- Registry timestamps
- Decision timestamps
- Effectivity timestamps
- Activation event
- Expiration and review timestamps

### 12.5 Evidence

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

### 12.6 Rationale

- `decision_rationale`
- `primary_findings`
- `counter_evidence`
- `alternatives_considered`
- `uncertainty_assessment`
- `residual_risks`
- `known_limitations`
- `dissenting_view`, when applicable

### 12.7 Conditions and Follow-up

- `condition_ids`
- `monitoring_requirements`
- `revalidation_triggers`
- `next_required_action`
- `next_review_at`
- `expires_at`
- `handoff_reference`
- `github_issue_ids`
- `pull_request_ids`

### 12.8 Independent Status Axes

保存第 10 節所有適用軸：

- `effectivity_status`
- `condition_status_summary`
- `expiration_status`
- `supersession_status`
- `impact_status`
- `validity_status`

## 13. Evidence Snapshot Schema

### 13.1 Purpose

Evidence Snapshot 固定 Decision 當時可見的 Evidence Package，而不是只儲存動態查詢條件。

### 13.2 Identity

- `evidence_snapshot_id`
- `decision_record_id`
- `evidence_cutoff_at`
- `created_at`
- `content_hash`
- `hash_algorithm`

### 13.3 Version Manifest

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

### 13.4 Experiment Evidence Items

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

不得只保存 Experiment ID 後動態顯示最新狀態。

### 13.5 Gate Evidence

至少保存：

- `gate_id`
- `gate_version`
- `threshold`
- `observed_value`
- `gate_status`
- `evidence_artifact_ids`
- `evaluated_at`
- `evaluated_by`

### 13.6 Completeness

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

`PARTIAL` 或 `INSUFFICIENT` 不得支持 Promote。

## 14. Formal Validation Decision Profiles

### 14.1 Promote

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
- Effectivity Mode

Promote 必須符合：

- Evidence Snapshot `COMPLETE`
- 沒有 unresolved Blocker
- 適用的 Gates 已達成或有明確 Conditional Pass
- Evidence Eligibility 可支持該 stage transition
- 下一階段輸入已準備完成

Promote 不代表：

- 未來必然獲利
- 真實資金核准
- 永久有效
- 可以停止監控

### 14.2 Revise

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

### 14.3 Retest

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

### 14.4 Retire

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
- `transition_group_id`
- `transition_ids`

`VERSION`：

- 只停止指定 Strategy Version。
- 其他版本不會自動 Retire。
- 必須記錄 successor version，若存在。
- 通常只有一筆 version-level Transition。

`LINEAGE`：

- 停止整條 Strategy ID lineage。
- 所有尚未 Retired 的版本必須各自建立獨立 Transition Record。
- 每筆 Transition 保存自己的 `from_state`、`to_state=RETIRED` 與 `transition_at`。
- 同一 Retirement Decision 使用一個 `transition_group_id` 關聯全部 `transition_ids`。
- 必須建立 lineage-level retirement marker。
- 不得建立新版本規避 lineage retirement。

Retired records 不得刪除。

## 15. Early-stage Decision Profile

Historical Backtest 前的 Governance Decision 必須使用：

- `decision_domain = RESEARCH | SPECIFICATION | ENGINEERING`
- `decision_class = STAGE_DECISION`
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

## 16. Periodic Review Profile

### 16.1 Purpose

Periodic Review 檢查既有核准是否仍可維持，不創造第五種 Formal Validation Action。

### 16.2 Required Classification

```text
decision_domain: VALIDATION
decision_class: PERIODIC_REVIEW
decision_action: null
periodic_review_outcome: <required enum>
```

### 16.3 Outcomes

```text
CONTINUE_CURRENT_STAGE
TRIGGER_FORMAL_DECISION
SUSPEND_PENDING_REVIEW
NO_LONGER_APPLICABLE
```

### 16.4 Rules

- `CONTINUE_CURRENT_STAGE`：不建立 Lifecycle Transition，只更新下一次 review 與 revalidation triggers。
- `TRIGGER_FORMAL_DECISION`：必須建立獨立 Promote、Revise、Retest 或 Retire Decision。
- `SUSPEND_PENDING_REVIEW`：建立 Suspension Event；若需要狀態改變，另建正式 Decision。
- `NO_LONGER_APPLICABLE`：說明 review obligation 結束原因，不得用來隱藏 Retire。
- Periodic Review 不得直接改變 Current Lifecycle State。

## 17. Decision Conditions and Activation

### 17.1 Condition Record

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

### 17.2 Condition Status

```text
PENDING
SATISFIED
FAILED
EXPIRED
WAIVED_BY_NEW_POLICY
```

### 17.3 Condition Event

每次狀態改變建立：

- `condition_event_id`
- `condition_id`
- `from_status`
- `to_status`
- `occurred_at`
- `actor`
- `evidence_reference_ids`
- `reason`

條件達成不得修改原 Decision。

### 17.4 No Silent Conditional Pass

`CONDITIONALLY_EFFECTIVE` 或 `NOT_EFFECTIVE_UNTIL_CONDITIONS_MET` 必須：

- 有至少一個 Condition Record
- 指定 owner
- 指定 due date 或明確事件條件
- 指定未達成的後果
- 指定驗證 evidence

條件失敗或過期不得讓 Promote 繼續被顯示為無條件有效。

### 17.5 Activation Event

Activation Event 至少包含：

- `activation_event_id`
- `decision_record_id`
- `transition_ids`
- `activation_preconditions`
- `preconditions_verified_at`
- `activated_at`
- `activated_by`
- `effective_at`

只有有效 Activation Event 可以把 `PENDING_CONDITIONS` 或 `PENDING_ACTIVATION` Transition 轉為 `ACTIVE`。

## 18. Lifecycle Transition Contract

### 18.1 Transition Entity

Lifecycle Transition 是獨立實體，不是 Decision Class。

每次 Lifecycle State 改變或預定改變，必須建立：

- `transition_id`
- `transition_group_id`, when applicable
- `strategy_id`
- `strategy_version`
- `from_state`
- `to_state`
- `decision_record_id`
- `transition_created_at`
- `transition_at`, only when active
- `transition_actor`
- `transition_status`
- `condition_ids`
- `activation_event_id`, when applicable
- `reversal_event_id`, when applicable

### 18.2 Transition Status

```text
PENDING_CONDITIONS
PENDING_ACTIVATION
ACTIVE
CANCELLED
REVERSED
```

### 18.3 State Mutation Rule

只有 `transition_status = ACTIVE` 才能改變 Current Lifecycle State。

- `PENDING_CONDITIONS` 不得改變 Current Lifecycle State。
- `PENDING_ACTIVATION` 不得改變 Current Lifecycle State。
- `CANCELLED` 不得改變 Current Lifecycle State。
- `REVERSED` 必須有 compensation or reversal event，且不得刪除原 Transition。

### 18.4 Atomicity

Decision Record、ACTIVE Transition 與 Current Lifecycle State pointer 應採原子寫入或具補償事件的 transaction model。

禁止：

- Lifecycle State 已改變但沒有 Decision Record
- Transition 已 ACTIVE 但 current state pointer 未更新
- Decision 表示 Promote，但 Lifecycle State 靜默跳過中間階段
- 只移動 GitHub Project card 而沒有正式 transition

### 18.5 One Current Primary State

同一 Strategy Version 同一時點只能有一個 Current Lifecycle State。

### 18.6 Multi-transition Decisions and Group Atomicity

一筆 Decision 可以引用多筆 Transition，例如 lineage retirement。

- 使用 `transition_group_id` 關聯。
- 每筆 Transition 必須有獨立 `strategy_version` 與 `from_state`。
- Group aggregation 不得隱藏失敗、取消或尚未 ACTIVE 的 Transition。
- 需要整體生效的 Transition Group，只有在所有 required transitions 都可轉為 `ACTIVE` 時才可提交。
- 任一 required transition 無法啟動時，整個 group 必須維持 pending、取消，或執行補償；不得留下部分版本已 Retired、其他版本仍 active 而 Decision 卻顯示 lineage retirement 已完整生效。
- Lineage retirement marker 只能在全部 required version transitions 為 `ACTIVE` 後轉為 active。

### 18.7 Operational Snapshot Boundary

Operational Research Snapshot 不得建立 Lifecycle Transition。

## 19. Operational Research Snapshot Schema

每個 Operational Snapshot 至少包含以下內容。

### 19.1 Identity and Campaign

- `operational_snapshot_id`
- `snapshot_id`, equal to `operational_snapshot_id`
- `campaign_id`
- `observation_id`
- `experiment_id`
- `strategy_id`
- `strategy_version`
- `snapshot_profile = OPERATIONAL_RESEARCH_SNAPSHOT`
- `frozen_version_manifest_hash`

### 19.2 Point-in-Time Data

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

### 19.3 Version Consistency

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

### 19.4 Universe and Tradability

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

### 19.5 Signal and Portfolio Output

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

### 19.6 Execution Simulation

- `simulated_fill_artifact_id`
- `unfilled_order_artifact_id`
- `delayed_order_artifact_id`
- `estimated_slippage`
- `failed_order_reason_summary`
- `manual_intervention`
- `manual_intervention_reason`
- `override_actor`
- `override_at`

### 19.7 Incidents and Integrity

- `data_incident_ids`
- `code_incident_ids`
- `monitoring_alert_ids`
- `blocker_ids`
- `snapshot_integrity_status`
- `reproducibility_status`
- `rerun_diff_artifact_id`

### 19.8 Explicit Non-authorization

每個 Operational Snapshot 必須保存：

```text
real_capital_authorized: false
broker_execution_authorized: false
automated_order_submission_authorized: false
```

在目前 TWStock scope 中，上述欄位不得為 true。

## 20. Rationale, Counter-evidence, and Uncertainty

每個正式 Governance Decision 必須以結構化方式保存：

### 20.1 Primary Findings

- 支持 action 的主要 findings
- 對應 Experiment、Gate 或 artifact
- Materiality
- Bias direction

### 20.2 Counter-evidence

- 不支持 action 的實驗
- Failed or conditional Gates
- 不利 Regime
- 集中度或容量問題
- 未解決的資料限制

### 20.3 Alternatives Considered

至少說明適用的替代 action：

- Why not Promote
- Why not Revise
- Why not Retest
- Why not Retire

### 20.4 Uncertainty

使用：

```text
LOW
MODERATE
HIGH
UNKNOWN
```

並保存 uncertainty reason。

Decision Snapshot 不得使用「信心很高」取代可檢查證據。

## 21. Expiration, Periodic Review, and Revalidation

### 21.1 Required Review Fields

進入 Paper Trading 或 Live Observation 的 Decision 至少包含：

- `review_frequency`
- `next_review_at`
- `maximum_period_without_review`
- `expires_at`
- `revalidation_triggers`
- `data_incident_triggers`
- `code_incident_triggers`
- `market_rule_change_triggers`

### 21.2 Expiration

超過 `expires_at` 或最大未審查期間：

- `expiration_status = EXPIRED`。
- `effectivity_status` 必須變為 `SUSPENDED` 或 `ENDED`，依政策定義。
- 不得假設原 Promote 永久有效。
- 必須建立新的 Periodic Review 或正式 Retest／Revise／Retire Decision。
- 原 Decision 保留。

### 21.3 Revalidation Trigger

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

## 22. Retirement and Reopening

### 22.1 Retirement Linkage

Retirement Decision 必須連結：

- Version-level or lineage-level retirement marker
- Transition Group，若為 lineage retirement
- 所有 affected Strategy Version records
- Experiment evidence
- Failed Gates
- Successor reference
- Reopening conditions

### 22.2 Reopening Decision

Reopening 必須建立新 Governance Decision ID，使用：

```text
decision_domain: REOPENING
decision_class: REOPENING_DECISION
decision_action: REOPEN_FOR_RESEARCH | DECLINE_REOPENING
```

至少保存：

- Original Retirement Decision ID
- Original retirement scope
- New evidence or changed condition
- Whether economic mechanism remains the same
- Required Strategy ID／Version assessment
- Restart research stage
- Evidence that must not be reused
- `01` owner assessment
- Human approval
- `04` acknowledgement，若原 retirement scope 為 LINEAGE

### 22.3 Reopening Effect

`REOPEN_FOR_RESEARCH`：

- 建立新的 Research Proposal 或版本評估工作。
- 不恢復原 Retired Version。
- 不直接把 lifecycle state 從 `RETIRED` 改成 active。
- 不得刪除原失敗證據。
- 後續若建立新 Strategy ID 或 Version，必須重新經過適用生命週期。

## 23. Decision Impact and Invalidation

### 23.1 Impact Triggers

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

### 23.2 Decision Impact Record

至少包含：

- `decision_impact_id`
- `decision_record_id`
- `source_invalidation_id`
- `dependency_path`
- `impact_status`
- `materiality_assessment`
- `affected_conclusions`
- `affected_transition_ids`
- `required_action`
- `assessed_by`
- `assessed_at`
- `resolved_by_decision_id`, when applicable

### 23.3 Effect on Status Axes

- `POTENTIALLY_AFFECTED`：`impact_status` 更新，原 Decision 不得繼續無條件顯示為 current authoritative approval。
- `UNDER_REVIEW`：相關 Promote 應顯示 suspended pending review；必要時建立 Suspension Event。
- `AFFECTED`：必須限制受影響 conclusion 或 Transition。
- `INVALIDATED`：`impact_status = INVALIDATED`，且 `validity_status = EVIDENCE_INVALID`；原 Decision 不再具有治理效力。

不得只修正上游 Experiment 而保持下游 Promote Decision 看起來完全有效。

## 24. Correction, Amendment, and Supersession

### 24.1 Metadata Correction

僅限不影響 action、scope、evidence、rationale、authority、conditions 或 effectivity 的錯字與引用錯誤。

必須建立 Amendment Record：

- `amendment_id`
- `decision_record_id`
- `field_path`
- `old_value`
- `new_value`
- `reason`
- `actor`
- `amended_at`

### 24.2 Material Correction

若修正影響：

- Decision Action
- Periodic Review Outcome
- Decision Scope
- Strategy Version
- Lifecycle Transition
- Evidence Package
- Retirement scope
- Conditions
- Effectivity
- Rationale conclusion
- Authority

必須建立新 Decision ID，並以 `SUPERSEDES` 關聯原 Decision。

### 24.3 Supersession Is Not Invalidation

- Superseded：後續決策取代原決策的 current governance role。
- Invalidated：原決策依據或程序存在使其失去效力的缺陷。

不得用 Superseded 隱藏 Invalidated。

## 25. Decision Relationships and Precedence

### 25.1 Relationship Types

```text
SUPERSEDES
SUPERSEDED_BY
REOPENS_AFTER
RESOLVES_IMPACT_OF
TRIGGERS_FORMAL_DECISION
PERIODIC_REVIEW_OF
AMENDS_METADATA_OF
```

### 25.2 Current Authority Rules

當多個 Decision 涉及相同 Strategy scope 時：

1. `validity_status = PROCEDURALLY_INVALID | EVIDENCE_INVALID` 不具 current authority。
2. `supersession_status = SUPERSEDED` 不具 current authority，但保留歷史效力描述。
3. `impact_status = UNDER_REVIEW | INVALIDATED` 的 Promote 不得顯示為無條件 current approval。
4. `expiration_status = EXPIRED` 的核准不得顯示為 current effective approval。
5. Lineage-level Retirement 優先於同 lineage 的非 Retirement version decisions。
6. Version-level Retirement 只影響指定 Version。
7. Formal Validation Decision 優先於 Operational Snapshot。
8. Operational Snapshot 不得覆蓋 Governance Decision。
9. Early-stage Decision 不得覆蓋已存在的 Formal Validation Decision。
10. Periodic Review 的 `CONTINUE_CURRENT_STAGE` 只延續 review standing，不創造新的 stage transition。
11. Reopening Decision 不會恢復原 Retirement Decision 的治理效力。
12. 新 Decision 必須明確引用其 supersede、reopen、resolve 或 trigger 的舊 Decision。

## 26. Canonical Storage Model

工程實作至少支援：

```text
governance_decisions
operational_snapshots
evidence_snapshots
evidence_snapshot_experiments
evidence_snapshot_gates
decision_conditions
condition_events
activation_events
lifecycle_transition_groups
lifecycle_transitions
lineage_retirement_markers
decision_findings
decision_limitations
decision_alternatives
decision_impacts
decision_amendments
decision_relationships
decision_events
```

### 26.1 Required Constraints

至少包括：

- IDs unique and immutable
- `snapshot_id` equals the profile-specific primary ID
- No hard delete for formal records
- Append-only events
- Timestamp with timezone
- Enum validation
- Hash validation
- Foreign-key or equivalent integrity
- Decision authority validation
- Decision-domain／class／action compatibility
- Periodic Review outcome validation
- Reopening authority validation
- Scope validation
- Evidence cutoff validation
- Evidence Snapshot immutability
- Independent status-axis validation
- Effectivity-mode-specific time validation
- Transition-status-specific state-mutation validation
- Only ACTIVE Transition may mutate Current Lifecycle State
- One current primary lifecycle state per Strategy Version
- Retirement scope validation
- Lineage retirement transition completeness and group atomicity
- Conditional decision completeness
- Campaign manifest consistency
- Operational non-authorization constraints
- Backfill cannot mutate current lifecycle state without new Prospective Decision

### 26.2 Query Requirements

系統至少支援：

- 依 Strategy ID／Version 查詢所有 Governance Decisions
- 查詢 current authoritative Decision 與所有底層狀態軸
- 查詢所有 pending conditions、pending activations 與 expired decisions
- 查詢 Periodic Reviews 及其 triggered formal decisions
- 查詢 Retirement／Reopening lineage
- 查詢 lineage retirement 的全部 version transitions
- 查詢每個 Decision 的 frozen Evidence Snapshot
- 查詢引用某 Experiment、Dataset、Code、Config 或 Policy Version 的 Decisions
- 查詢 invalidation 的 Decision Impact path
- 查詢 Operational Snapshot 與 Campaign frozen manifest mismatch
- 重建某 Decision 的 rationale、counter-evidence、conditions、activation 與 transitions

## 27. YAML Examples

以下範例用於展示 profile-specific contract。除非明確標示為 null 或 N/A，第 11 至 13 節所定義的適用必填欄位仍必須存在；實作不得把範例未列出的共同欄位解讀為 optional。

### 27.1 Immediate Promote

```yaml
decision_record_id: DEC-20260710-01J2PROMOTE001
snapshot_id: DEC-20260710-01J2PROMOTE001
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
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
decision_at: 2026-07-10T20:30:00+08:00
recorded_at: 2026-07-10T20:35:00+08:00
effective_at: 2026-07-10T20:30:00+08:00
planned_effective_at: null
activation_event_id: null
decision_owner_workspace: workspace-04
decision_actor: human-auditor
authority_basis: TWSTOCK-RESEARCH-LIFECYCLE-001@1.0.0
evidence_snapshot_id: EVS-01J2PROMOTEEVIDENCE
evidence_snapshot_hash: sha256:example
transition_ids:
  - TRN-01J2PROMOTE001
transition_group_id: null
effectivity_status: EFFECTIVE
condition_status_summary: NOT_APPLICABLE
expiration_status: ACTIVE_WINDOW
supersession_status: CURRENT
impact_status: UNAFFECTED
validity_status: VALID
```

Transition：

```yaml
transition_id: TRN-01J2PROMOTE001
transition_group_id: null
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
from_state: HISTORICAL_BACKTEST
to_state: ROBUSTNESS_VALIDATION
decision_record_id: DEC-20260710-01J2PROMOTE001
transition_status: ACTIVE
transition_created_at: 2026-07-10T20:35:00+08:00
transition_at: 2026-07-10T20:30:00+08:00
activation_event_id: null
```

### 27.2 Promote Not Effective Until Conditions Met

```yaml
decision_record_id: DEC-20260710-01J2CONDITIONAL
snapshot_id: DEC-20260710-01J2CONDITIONAL
snapshot_profile: GOVERNANCE_DECISION
schema_version: 1.0.0
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: PROMOTE
decision_scope_type: STRATEGY_VERSION
decision_scope_ids:
  - TW-M03-MONTHLY-REVENUE-MOMENTUM@1.0.0
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
effectivity_mode: NOT_EFFECTIVE_UNTIL_CONDITIONS_MET
evidence_cutoff_at: 2026-07-10T20:00:00+08:00
decision_at: 2026-07-10T20:30:00+08:00
recorded_at: 2026-07-10T20:35:00+08:00
planned_effective_at: null
effective_at: null
activation_event_id: null
condition_ids:
  - COND-01J2DATAFIX
transition_ids:
  - TRN-01J2PENDINGPROMOTE
effectivity_status: PENDING_CONDITIONS
condition_status_summary: PENDING
expiration_status: ACTIVE_WINDOW
supersession_status: CURRENT
impact_status: UNAFFECTED
validity_status: VALID
```

```yaml
transition_id: TRN-01J2PENDINGPROMOTE
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
from_state: OUT_OF_SAMPLE
to_state: PAPER_TRADING
decision_record_id: DEC-20260710-01J2CONDITIONAL
transition_status: PENDING_CONDITIONS
transition_at: null
condition_ids:
  - COND-01J2DATAFIX
activation_event_id: null
```

### 27.3 Periodic Review — Continue Current Stage

```yaml
decision_record_id: DEC-20261001-01J2REVIEW001
snapshot_id: DEC-20261001-01J2REVIEW001
snapshot_profile: GOVERNANCE_DECISION
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: PERIODIC_REVIEW
decision_action: null
periodic_review_outcome: CONTINUE_CURRENT_STAGE
decision_scope_type: STRATEGY_VERSION
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
transition_ids: []
evidence_cutoff_at: 2026-10-01T17:00:00+08:00
decision_at: 2026-10-01T18:00:00+08:00
recorded_at: 2026-10-01T18:05:00+08:00
effectivity_mode: IMMEDIATE
effective_at: 2026-10-01T18:00:00+08:00
next_review_at: 2027-01-01T09:00:00+08:00
effectivity_status: EFFECTIVE
impact_status: UNAFFECTED
validity_status: VALID
```

### 27.4 Retest Decision

```yaml
decision_record_id: DEC-20260710-01J2RETEST0001
snapshot_id: DEC-20260710-01J2RETEST0001
snapshot_profile: GOVERNANCE_DECISION
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: RETEST
decision_scope_type: EXPERIMENT_SET
strategy_id: TW-M03-MONTHLY-REVENUE-MOMENTUM
strategy_version: 1.0.0
effectivity_mode: IMMEDIATE
evidence_cutoff_at: 2026-07-10T21:00:00+08:00
decision_at: 2026-07-10T21:15:00+08:00
recorded_at: 2026-07-10T21:20:00+08:00
effective_at: 2026-07-10T21:15:00+08:00
decision_owner_workspace: workspace-04
retest_reason: monthly revenue availability timestamp mapping defect
strategy_version_preserved: true
required_new_experiment_id: true
original_experiment_ids:
  - EXP-20260709-01J2INVALID
replacement_experiment_plan:
  new_experiment_ids_required: true
  registration_status: PLANNED
```

### 27.5 Lineage Retirement with Multiple Transitions

```yaml
decision_record_id: DEC-20260710-01J2RETIRE0001
snapshot_id: DEC-20260710-01J2RETIRE0001
snapshot_profile: GOVERNANCE_DECISION
registration_mode: PROSPECTIVE
decision_domain: VALIDATION
decision_class: FORMAL_VALIDATION
decision_action: RETIRE
decision_scope_type: STRATEGY_LINEAGE
retirement_scope: LINEAGE
strategy_id: TW-M06-MEAN-REVERSION-X
affected_strategy_versions:
  - 1.0.0
  - 2.0.0
  - 2.1.0
transition_group_id: TRG-01J2LINEAGERETIRE
transition_ids:
  - TRN-01J2RETIRE100
  - TRN-01J2RETIRE200
  - TRN-01J2RETIRE210
lineage_retirement_marker_id: LRM-01J2MEANREVERSION
retirement_reason: repeated OOS failure after costs and unacceptable liquidity concentration
effectivity_mode: IMMEDIATE
effectivity_status: EFFECTIVE
```

```yaml
transitions:
  - transition_id: TRN-01J2RETIRE100
    transition_group_id: TRG-01J2LINEAGERETIRE
    strategy_version: 1.0.0
    from_state: HISTORICAL_BACKTEST
    to_state: RETIRED
    transition_status: ACTIVE
  - transition_id: TRN-01J2RETIRE200
    transition_group_id: TRG-01J2LINEAGERETIRE
    strategy_version: 2.0.0
    from_state: OUT_OF_SAMPLE
    to_state: RETIRED
    transition_status: ACTIVE
  - transition_id: TRN-01J2RETIRE210
    transition_group_id: TRG-01J2LINEAGERETIRE
    strategy_version: 2.1.0
    from_state: PAPER_TRADING
    to_state: RETIRED
    transition_status: ACTIVE
```

### 27.6 Reopening Decision

```yaml
decision_record_id: DEC-20270115-01J2REOPEN001
snapshot_id: DEC-20270115-01J2REOPEN001
snapshot_profile: GOVERNANCE_DECISION
registration_mode: PROSPECTIVE
decision_domain: REOPENING
decision_class: REOPENING_DECISION
decision_action: REOPEN_FOR_RESEARCH
decision_owner_workspace: workspace-01
decision_actor: research-owner
approved_by: human-governance-owner
original_retirement_decision_id: DEC-20260710-01J2RETIRE0001
original_retirement_scope: LINEAGE
required_acknowledgement_ids:
  - ACK-WORKSPACE04-20270115
restart_research_stage: IDEA
transition_ids: []
restores_retired_version: false
creates_active_lifecycle_state: false
```

### 27.7 Operational Research Snapshot

```yaml
operational_snapshot_id: OPS-20260801-01J2PAPER0001
snapshot_id: OPS-20260801-01J2PAPER0001
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
real_capital_authorized: false
broker_execution_authorized: false
automated_order_submission_authorized: false
```

### 27.8 Retrospective Decision Backfill

```yaml
decision_record_id: DEC-20260710-01J2BACKFILL01
snapshot_id: DEC-20260710-01J2BACKFILL01
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
may_mutate_current_lifecycle_state: false
```

## 28. Validation Rules

1. Governance and Operational profiles must not share incompatible action fields.
2. `snapshot_id` must equal the profile-specific primary ID.
3. Formal Validation Action must be one of Promote／Revise／Retest／Retire.
4. Formal Validation Decision must have `decision_domain = VALIDATION` and owner `workspace-04`.
5. Pre-evidence Decision must not use Formal Validation Action.
6. `PERIODIC_REVIEW` must use `decision_action = null` and a valid periodic review outcome.
7. Periodic Review must not directly create Lifecycle Transition.
8. `REOPENING_DECISION` must use a valid Reopening Action and owner `workspace-01`.
9. Lineage reopening requires human approval and workspace-04 acknowledgement.
10. Reopening must not restore a retired version or directly create active lifecycle state.
11. Promote requires complete Evidence Snapshot and valid Gate evidence.
12. Promote requires exact scope and target stage.
13. Revise requires return workspace, revision scope and preservation restrictions.
14. Retest requires `required_new_experiment_id = true` and original Experiment references.
15. Retire requires `retirement_scope: VERSION | LINEAGE`.
16. Lineage Retirement must identify all affected active versions.
17. Lineage Retirement requires one Transition per affected Strategy Version.
18. Multi-transition Decision must use a Transition Group and satisfy group atomicity.
19. Conditional effectivity requires complete Condition Records.
20. `NOT_EFFECTIVE_UNTIL_CONDITIONS_MET` requires `effective_at = null` until Activation Event.
21. `DEFERRED` requires planned effective time and Activation Event before effectivity.
22. Only ACTIVE Transition may mutate Current Lifecycle State.
23. Pending, Cancelled or Reversed Transition must not silently mutate Current Lifecycle State.
24. Expired conditions must not leave Decision as unconditionally effective.
25. Decision must not reference evidence formed after `evidence_cutoff_at`.
26. Evidence Snapshot must preserve Experiment statuses as of decision time.
27. Operational Snapshot must not create Lifecycle Transition.
28. Operational Snapshot must match Campaign frozen-version manifest.
29. `version_consistency_status = BLOCKED` must exclude Snapshot from formal Campaign performance.
30. Operational real-capital authorization fields must remain false.
31. Independent decision status axes must be stored separately.
32. Derived display standing must not overwrite status axes.
33. Decision Impact `POTENTIALLY_AFFECTED` or `UNDER_REVIEW` must prevent unconditional current approval display.
34. Invalidated Decision must not remain authoritative.
35. Material correction requires new Decision ID.
36. Superseded must not hide Invalidated.
37. Registration mode must select the correct time-validation profile.
38. Retrospective Backfill must not mutate current lifecycle state without a new Prospective Decision.
39. No formal Decision or Transition hard delete.

## 29. Engineering Acceptance Criteria

第一版實作至少必須達成：

- [ ] Governance Decision 與 Operational Snapshot 分開儲存。
- [ ] Canonical `snapshot_id` 與 profile-specific ID 保持一致。
- [ ] 每個正式 Decision／Snapshot 自動產生唯一 immutable ID。
- [ ] Decision 使用 append-only events，不覆蓋原結論。
- [ ] Early-stage、Formal Validation、Periodic Review 與 Reopening authority 可以 machine-validate。
- [ ] Promote／Revise／Retest／Retire 使用固定 enum。
- [ ] Periodic Review 使用獨立 outcome，不創造第五種 Validation Action。
- [ ] Reopening 只啟動研究，不恢復原 Retired Version。
- [ ] Decision scope 必須指定 Strategy、Version、Stage、Experiment 或 Campaign。
- [ ] Evidence Snapshot 固定 Decision 當下的 Experiment 狀態與 artifact hashes。
- [ ] Evidence cutoff 阻止引用未來 evidence。
- [ ] Promote 缺少必要 Evidence Package 時被拒絕。
- [ ] Conditional Decision 強制保存 owner、due date、evidence 與 failure consequence。
- [ ] `effective_at` 只在實際生效後存在。
- [ ] Pending Transition 不會改變 Current Lifecycle State。
- [ ] Activation Event 可原子啟動 Decision 與 Transition。
- [ ] Retest 強制新 Experiment ID。
- [ ] Retire 強制 VERSION／LINEAGE scope。
- [ ] Lineage Retirement 為每個 active version 建立獨立 Transition，並具 group atomicity。
- [ ] 同一 Strategy Version 只有一個 current primary lifecycle state。
- [ ] Effectivity、condition、expiration、supersession、impact、validity 分軸儲存。
- [ ] Operational Snapshot 驗證 Campaign frozen manifest。
- [ ] Operational Snapshot 不得授權真實資金或券商下單。
- [ ] Expiration 與 periodic review 可被排程與查詢。
- [ ] Experiment invalidation 可傳遞到 Decision Impact。
- [ ] Affected／Invalidated Promote 不會繼續顯示為無條件 current approval。
- [ ] Supersession、Correction、Reopening 與 Retirement lineage 可回溯。
- [ ] Backfill 不會改變 current lifecycle state。
- [ ] Failed、Rejected、Retired、Expired 與 Invalidated records 永久保留。
- [ ] 可由 Decision ID 重建完整 Evidence Snapshot、Rationale、Conditions、Activation 與 Transitions。

## 30. Manual Acceptance Tests

### Test A: Invalid Authority

Given：Engineering workspace 嘗試建立 formal Promote。

Expected：寫入被拒絕。

### Test B: Future Evidence

Given：Decision cutoff 為 20:00，引用 21:00 完成的 Experiment。

Expected：Decision 寫入被拒絕。

### Test C: Incomplete Promote Evidence

Given：Promote 缺少 Dataset Version 或 Gate evidence。

Expected：Promote 被拒絕，不得改變 Lifecycle State。

### Test D: Conditional Promote Pending

Given：Promote 使用 `NOT_EFFECTIVE_UNTIL_CONDITIONS_MET`，條件尚未達成。

Expected：`effective_at = null`、Transition 為 `PENDING_CONDITIONS`，Current Lifecycle State 不變。

### Test E: Activation Event

Given：所有必要條件已滿足。

Expected：建立 Activation Event、寫入 `effective_at`，Transition 原子轉為 ACTIVE，Current Lifecycle State 才改變。

### Test F: Deferred Decision

Given：Decision 有 planned effective time，但尚未 activation。

Expected：不得僅因時間到達就改變 Lifecycle State。

### Test G: Periodic Review Continue

Given：定期審查結論為維持現階段。

Expected：保存 `CONTINUE_CURRENT_STAGE`，不建立 Transition，不使用第五種 Validation Action。

### Test H: Periodic Review Trigger

Given：Periodic Review 發現需 Retest。

Expected：建立 linked Retest Decision；Periodic Review 本身不改變 Lifecycle State。

### Test I: Reopening Authority

Given：workspace-03 嘗試重新開啟 Retired lineage。

Expected：寫入被拒絕。

### Test J: Lineage Reopening

Given：原 Retirement scope 為 LINEAGE。

Expected：需要 workspace-01 owner、human approval 與 workspace-04 acknowledgement；不得恢復原版本。

### Test K: Retest Without New Experiment Requirement

Given：Retest 未設定新 Experiment ID requirement。

Expected：寫入被拒絕。

### Test L: Retire Without Scope

Given：Retire 未指定 VERSION 或 LINEAGE。

Expected：寫入被拒絕。

### Test M: Lineage Retirement

Given：Lineage 有三個 active versions，分別處於不同 Lifecycle State。

Expected：建立一個 Retirement Decision、一個 Transition Group、三筆各自帶 from-state 的 ACTIVE Transitions，以及 lineage retirement marker。

### Test N: Partial Lineage Retirement Failure

Given：三筆 required retirement transitions 中有一筆無法啟動。

Expected：整個 Transition Group 不得被標記完整生效；lineage retirement marker 不得 active，並執行 pending、cancel 或 compensation 流程。

### Test O: Mixed Status Axes

Given：Decision 同時 condition pending 且 potentially affected。

Expected：兩個底層狀態軸都被保存；不得用單一 standing 覆蓋其中一個。

### Test P: Condition Expiration

Given：Promote condition 到期未達成。

Expected：Condition 狀態為 EXPIRED，Effectivity 依 failure consequence 變為 NOT_EFFECTIVE、SUSPENDED 或 REVERSED，不得顯示無條件有效。

### Test Q: Experiment Invalidation

Given：Promote 引用的主要 Experiment 被 invalidated。

Expected：建立 Decision Impact，更新 impact／validity 軸，要求重新審計。

### Test R: Material Correction

Given：使用者想把原 Retest action 改成 Promote。

Expected：不得修改原 Decision；必須建立新 Decision 並 supersede 原 Decision。

### Test S: Operational Snapshot Manifest Mismatch

Given：Operational Snapshot Code Behavior Version 與 Campaign manifest 不一致。

Expected：標記 BLOCKED 或拒絕寫入，不得納入 Campaign 績效。

### Test T: Operational Snapshot Capital Authorization

Given：Snapshot 嘗試設定 `real_capital_authorized = true`。

Expected：寫入被拒絕。

### Test U: Retrospective Backfill

Given：2025 年 Decision 於 2026 年補登。

Expected：保存 original timestamps、source、precision 與 confidence；不改變 current lifecycle state。

### Test V: Canonical Snapshot ID

Given：Governance Decision 的 `snapshot_id` 與 `decision_record_id` 不同。

Expected：寫入被拒絕。

## 31. Research Reporting Requirements

正式策略頁面至少顯示：

- Strategy ID and Version
- Decision ID
- Decision Class and Action／Periodic Review Outcome
- Decision Scope
- Current Lifecycle State
- Decision owner and authority
- Evidence cutoff and decision time
- Evidence Snapshot completeness
- Independent status axes
- Derived display standing
- Conditions and activation status
- Expiration and next review
- Primary findings
- Counter-evidence
- Known limitations
- Decision Impact
- Supersession reference
- Transition IDs and status
- Retirement or reopening reference, when applicable
- Explicit statement that Live Observation／Paper Trading is not real-capital approval

網站不得：

- 只顯示 Promote 而隱藏已 Expired、Suspended、Affected 或 Invalidated
- 用 current display standing 取代底層狀態軸
- 用 Operational Snapshot 冒充 Formal Validation Decision
- 把回測或 Paper Trading 描述為未來獲利保證

## 32. Prohibited Practices

TWStock 禁止：

- 重複使用 Decision or Snapshot ID
- 使用兩個不一致的 Snapshot primary keys
- 覆蓋原 Decision action
- 刪除被拒絕、Expired、Retired、Affected 或 Invalidated Decision
- 使用未來 evidence 回寫原決策
- 用單一 standing 混合 effectivity、condition、expiration、supersession、impact 與 validity
- 用 Pending Transition 改變 Current Lifecycle State
- 條件未達成卻寫入實際 `effective_at`
- 延後生效時間到達後未驗證條件就自動改變 Lifecycle State
- 用 Periodic Review 創造第五種 Formal Validation Action
- 用 Periodic Review 直接改變 Lifecycle State
- 未經 workspace-01 與 Human Approval 重新開啟 Retired research
- 用 Reopening 恢復原 Retired Version
- Lineage Retirement 只建立一筆模糊 Transition
- 讓 lineage retirement Transition Group 部分生效卻顯示完整退休
- 工程、Codex 或網站自行 Promote／Retire
- Retest 不要求新 Experiment ID
- Retire 不指定 VERSION／LINEAGE
- 用 Operational Snapshot 改變 Lifecycle State
- Operational Snapshot 授權真實資金或券商下單
- 用 Superseded 隱藏 Invalidated
- Backfill 偽造 authority、effectivity、evidence 或 timestamp
- Backfill 直接改變 current lifecycle state
- 將歷史回測描述為未來獲利保證

## 33. Exceptions and Backfill

任何例外都必須：

1. 明確記錄。
2. 指定 Decision、Snapshot、Strategy、Version 與適用範圍。
3. 說明必要性。
4. 評估對治理、證據、PIT 與可重現性的影響。
5. 設定到期或重審條件。
6. 不得繞過正式 authority。
7. 不得用例外直接授權真實資金。

歷史補登必須：

- `registration_mode = RETROSPECTIVE_BACKFILL`
- 保存 `backfilled_at`
- 保存原始決策時間與來源，如可取得
- 保存 timestamp precision and confidence
- 保存原 authority evidence，如可取得
- 不得偽造原 Evidence Snapshot、Design Lock 或 effectivity
- 不得因補登提高原證據等級
- 不得直接改變 current lifecycle state

## 34. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Snapshot profiles
- Decision domains、classes or actions
- Periodic Review outcomes
- Authority matrix
- Reopening authority
- Effectivity modes
- Independent status axes
- Evidence Snapshot requirements
- Transition status or activation rules
- Retirement and transition-group rules
- Decision Impact rules
- Operational Snapshot non-authorization rules
- Storage constraints
- Engineering acceptance criteria

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Migration
- Affected Decisions、Snapshots、Transitions and Strategies
- Required Reclassification or Retest

## 35. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/VALIDATION_PROTOCOL.md`
2. Dataset-specific Data Contracts
3. Thin Website Information Architecture
4. Foundation Engine implementation contracts

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
