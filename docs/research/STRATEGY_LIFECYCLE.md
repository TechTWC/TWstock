# TWStock Strategy Lifecycle

- Document ID: `TWSTOCK-RESEARCH-LIFECYCLE-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock strategy ideas, hypotheses, specifications, engineering implementations, experiments, validation decisions, paper trading, revision, promotion, and retirement

## 1. Purpose

本文件定義 TWStock 中每一個投資策略從最初想法到研究、實作、驗證、紙上交易、前瞻觀察、修訂、重測或淘汰的正式生命週期。

核心目的包括：

- 防止模糊投資想法直接進入工程實作
- 防止單次高報酬回測直接被描述為有效策略
- 確保每個階段都有明確輸入、輸出、責任角色與通過條件
- 確保策略、資料、設定、程式、實驗與決策均可追蹤
- 明確區分 `Revise` 與 `Retest`
- 明確區分新 Strategy ID、MAJOR、MINOR 與 PATCH
- 保存失敗、無效、被否證與被淘汰的策略紀錄
- 防止策略跳過 Point-in-Time、穩健性、Out-of-Sample 或 Paper Trading 驗證

本文件不保證任何策略未來獲利，也不授權真實資金交易。

## 2. Authority and Relationship to Other Documents

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`
3. `docs/data/POINT_IN_TIME_POLICY.md`

本文件將由以下文件進一步具體化：

- `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
- `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
- `docs/research/VALIDATION_PROTOCOL.md`
- Dataset-specific Data Contracts
- Strategy-specific Executable Specifications
- Strategy YAML Configs

若策略規格、YAML、工程實作、回測輸出或聊天紀錄與本文件衝突：

1. 不得靜默採用較方便或績效較好的版本。
2. 受影響的策略不得繼續升級。
3. 衝突必須進入正式紀錄。
4. 必須由適當工作模式決定修訂、重測或淘汰。
5. 修正後必須建立必要的新版本與新 Experiment ID。

## 3. Core Lifecycle Principles

### 3.1 No Stage Skipping

不得跳過必要階段。

禁止流程包括：

```text
Idea → Codex Implementation
Hypothesis → Historical Backtest
In-Sample Result → Paper Trading
High Historical Return → Live Capital
Backtest Result → Strategy Validated
```

### 3.2 Evidence Must Precede Promotion

策略只能因為符合事前定義的證據與 Gates 而升級，不能因為：

- 報酬率看起來很高
- 某位投資大師使用過
- 市場目前流行
- 使用者主觀喜歡
- 單一股票或單一年份表現突出
- 回測圖形看起來平滑

### 3.3 Failures Are Permanent Research Records

失敗實驗、無效實驗、資料錯誤、規格衝突、Retest、Revise 與 Retire 都必須保存。

不得刪除失敗紀錄後，把相同策略重新包裝成沒有研究歷史的新策略。

### 3.4 Promotion Is Stage-specific

`Promote` 只表示通過正式驗證關卡並進入下一個研究階段。

例如：

```text
Historical Backtest → Robustness Validation
Robustness Validation → Out-of-Sample
Out-of-Sample → Paper Trading
```

`Promote` 不代表：

- 未來必然獲利
- 已核准真實資金交易
- 不需要持續監控
- 策略永久有效

### 3.5 Strategy Behavior Must Be Versioned

任何會改變策略選股、排名、進出場、持股、權重、交易或風險行為的變更，都必須經版本管理。

不得用程式碼中的隱藏預設值改變策略行為。

### 3.6 Early-stage Decisions Are Not Audit Decisions

Idea、Hypothesis、Research Specification 與 Engineering Translation 階段尚未產生正式策略實驗證據。

因此：

- `01｜台股研究與策略大腦`負責 Idea 與 Hypothesis 的研究決策。
- `02｜台股研究規格轉譯`負責判斷規格是否可交付工程，或是否應退回 `01`。
- `03｜TWStock 工程轉譯`負責判斷工程拆分是否可執行，或是否應退回 `02`。
- `04｜台股策略驗證與審計`從正式 Historical Backtest 證據形成後，才擁有 `Promote / Revise / Retest / Retire` 的最終審計決策權。

早期階段不得使用 `Allowed Audit Decision` 造成責任誤解。

## 4. Canonical Lifecycle

TWStock 的標準策略生命週期為：

```text
Idea
→ Hypothesis
→ Research Specification
→ Engineering Translation
→ Engineering Implementation
→ Historical Backtest
→ Robustness Validation
→ Out-of-Sample Test
→ Paper Trading
→ Approved for Live Observation
→ Continuing Review / Revision / Retirement
```

### 4.1 Pre-evidence Decisions

在正式 Historical Backtest 前，各階段 Owner 使用符合該階段的工作決策，例如：

```text
Proceed
Revise
Park
Reject
Ready for Next Stage
Return to Previous Stage
Blocked
```

這些決策不屬於 `04` 的正式策略驗證結論。

### 4.2 Formal Validation Decisions

自 Historical Backtest 起，正式審計只能作出：

```text
Promote
Revise
Retest
Retire
```

其中：

- `Promote`：通過當前正式驗證 Gate，進入下一研究階段。
- `Revise`：核心研究內容或正式策略行為需要改變，退回 `01` 或 `02`。
- `Retest`：假設與正式策略行為暫時保留，但資料、程式、測試或證據需要重新執行。
- `Retire`：停止指定 Strategy Version 或整條 strategy lineage 的進一步升級。

## 5. Lifecycle States

正式策略紀錄應使用下列主要狀態之一。

| Lifecycle State | Meaning |
|---|---|
| `IDEA` | 尚未形成可否證假設的研究想法 |
| `HYPOTHESIS` | 已形成研究假設，但尚未完成可執行規格 |
| `SPECIFICATION` | 正在建立或審查 Executable Strategy Specification |
| `ENGINEERING_TRANSLATION` | 已核准規格正在拆分為 GitHub Issues 與 Codex Plan |
| `IMPLEMENTATION` | 正在實作、測試或修正策略與依賴模組 |
| `HISTORICAL_BACKTEST` | 正在執行正式歷史回測 |
| `ROBUSTNESS_VALIDATION` | 正在執行敏感度、偏誤與不同環境測試 |
| `OUT_OF_SAMPLE` | 正在執行未見樣本或 Walk-forward 測試 |
| `PAPER_TRADING` | 使用當下可得資料進行無真實資金的前瞻性驗證 |
| `LIVE_OBSERVATION` | 只允許前瞻訊號觀察與營運監控，不代表實盤授權 |
| `RETIRED` | 已正式停止指定版本或 lineage 的進一步升級 |

可以另外使用下列操作狀態，但它們不能取代 Lifecycle State：

- `BLOCKED`
- `PARKED`
- `REJECTED_BEFORE_SPECIFICATION`
- `INVALIDATED_EXPERIMENT`
- `SUPERSEDED_VERSION`

## 6. Required Identity and Version Axes

每個正式策略及實驗必須能識別下列版本軸。

### 6.1 Strategy ID

識別一條具有一致核心投資假設、經濟或行為基礎及預期報酬機制的 strategy lineage。

建議格式：

```text
TW-{MODE}-{STRATEGY-NAME}
```

例如：

```text
TW-M03-MONTHLY-REVENUE-MOMENTUM
```

### 6.2 Strategy Version

識別同一 strategy lineage 內的策略行為版本，採語意化版本：

```text
MAJOR.MINOR.PATCH
```

### 6.3 Specification Version

識別 Executable Strategy Specification 文件版本。

### 6.4 Config Version

識別 YAML 或其他機器可讀設定版本。

### 6.5 Code Version

使用 Git Commit SHA 或可追蹤 Release 識別。

### 6.6 Dataset Version

識別每個正式資料集及其快照、來源與轉換版本。

### 6.7 Feature Version

識別特徵公式、缺值處理、標準化與計算方式。

### 6.8 Experiment ID

每次正式執行都必須有唯一 Experiment ID。

即使 Strategy Version 不變，只要重新執行正式測試，也必須建立新 Experiment ID。

### 6.9 Decision Record ID

自正式 Historical Backtest 起，每次 Promote、Revise、Retest 或 Retire 都必須建立可追蹤的 Decision Record。

早期研究決策亦須保留紀錄，但可以使用 Research Decision Record，不應冒充正式 Validation Decision。

## 7. Strategy ID Versus Strategy Version

### 7.1 Create a New Strategy ID

下列情況原則上必須建立新的 Strategy ID：

- 核心預期報酬機制改變
- 經濟或行為基礎改變
- Parent Mode 改變
- 新增具有獨立理論基礎的因子或交易機制
- 投資期限與交易機制改變到無法合理視為同一 lineage
- Retired lineage 以不同假設重新開啟研究

例如：

```text
原策略：月營收成長加速，捕捉資訊反應不足
新策略：月營收成長加速 + 短期價格反轉
```

若價格反轉代表新的獨立報酬機制，必須建立新 Strategy ID。

### 7.2 MAJOR Version

MAJOR Version 只適用於底層預期報酬機制、經濟或行為基礎與 Parent Mode 仍相同，但策略主要實作方式發生重大改變的情況，例如：

- 主要訊號的量化操作化方式重大改變，但仍衡量同一理論現象
- 主要進出場邏輯重大改變，但仍服務同一報酬機制
- 持有期限或執行設計重大改變，但仍可合理視為同一 lineage
- 研究問題重新表述，但沒有改變底層理論與報酬來源

MAJOR Version 不得用來掩蓋新的投資假設或新的報酬機制。

### 7.3 Decision Test

判斷順序如下：

```text
底層預期報酬機制、經濟／行為基礎或 Parent Mode 是否改變？
├── 是 → New Strategy ID
└── 否
    └── 主要策略行為是否重大改變？
        ├── 是 → MAJOR Version
        └── 否
            └── 是否為重要但非核心的策略行為改變？
                ├── 是 → MINOR Version
                └── 否 → PATCH 或非 Strategy Version 變更
```

若無法明確判斷，必須由 `01` 判斷是否仍為同一研究假設，再由 `02` 決定版本落點。工程角色不得自行決定。

## 8. Strategy Version Rules

### 8.1 MINOR

適用於會實質改變策略行為，但不改變核心報酬機制且未達 MAJOR 程度的變更，例如：

- Eligibility Filter 改變
- Ranking 組合或因子權重改變
- 持股數改變
- 權重方法改變
- 產業或個股上限改變
- 再平衡頻率改變
- 重要風控改變
- Tradability Mask 改變

### 8.2 PATCH

只適用於不改變策略行為的變更，例如：

- 文字澄清
- 欄位命名修正
- 文件連結修正
- 不影響輸出的註解或格式修正

### 8.3 Code-only Fix

若修正程式錯誤但策略規則不變：

- Strategy Version 可維持不變
- 必須建立新 Code Version
- 必須建立新 Experiment ID
- 舊實驗應標記為 `Invalidated` 或保留原有效狀態，視錯誤影響而定
- 必須記錄是否需要重新執行全部歷史測試

### 8.4 Data-only Change

若資料來源、清理或版本改變，但策略規則不變：

- Strategy Version 可維持不變
- Dataset Version 必須改變
- 必須建立新 Experiment ID
- 必須進行影響評估與必要 Retest

## 9. Stage 1 — Idea

### 9.1 Purpose

保存值得評估的投資現象、書籍法則、市場觀察或新研究方向。

### 9.2 Owner

`01｜台股研究與策略大腦`

### 9.3 Required Input

至少一項：

- 市場現象
- 經濟或行為觀察
- 書籍或研究來源
- 投資方法概念
- 個人交易或研究經驗
- 已有策略的延伸問題

### 9.4 Required Output

Idea Record 至少包含：

- Idea title
- Source or origin
- Proposed Parent Mode
- Initial problem statement
- Potential return mechanism
- Initial risks
- Research value
- Duplicate or related strategies

### 9.5 Exit Gate

必須能回答：

- 研究問題是什麼？
- 為什麼可能值得研究？
- 是否與既有策略重複？
- 是否具有形成可否證假設的可能？

### 9.6 Owner Decision

由 `01` 決定：

- Proceed to Hypothesis
- Revise Idea
- Park
- Reject Before Specification

### 9.7 Prohibited Actions

不得：

- 直接要求 Codex 實作
- 直接設定回測參數並測到結果漂亮為止
- 將名人或書籍陳述視為已驗證證據
- 將 Idea 宣稱為有效策略

## 10. Stage 2 — Hypothesis

### 10.1 Purpose

將 Idea 轉成具有經濟或行為邏輯、適用範圍與可否證條件的研究假設。

### 10.2 Owner

`01｜台股研究與策略大腦`

### 10.3 Required Input

- Idea Record
- 初步理論或行為基礎
- 初步目標市場與投資期限

### 10.4 Required Output

Strategy Research Proposal 至少包含：

- Strategy concept
- Parent Mode
- Investment thesis
- Economic or behavioral rationale
- Target Universe concept
- Signal concept
- Expected holding horizon
- Expected return mechanism
- Risk and failure conditions
- Falsifiable hypothesis
- Required evidence
- Known unknowns
- Research priority
- Research Handoff

### 10.5 Exit Gate

只有在以下條件成立時，才能進入 Research Specification：

- 假設可被資料支持或否證
- 預期報酬機制不是純事後敘事
- 適用與失效情境已有概念性定義
- 所需資料在原則上可能取得
- 研究價值足以合理投入規格化成本
- 沒有與既有策略完全重複而無新增研究價值

### 10.6 Owner Decision

由 `01` 決定：

- Proceed to Specification
- Revise
- Park
- Reject

此階段停止研究表示拒絕或暫停研究方向，不代表已有回測證據證明其無效。

### 10.7 Prohibited Actions

不得：

- 將「成長很好」、「估值便宜」等模糊詞直接交工程實作
- 先看大量回測結果再反向撰寫假設
- 以未經證明的產業故事取代可否證命題

## 11. Stage 3 — Research Specification

### 11.1 Purpose

把已核准假設轉換成明確、可執行、可回測、可重現與可版本管理的策略規格。

### 11.2 Owner

`02｜台股研究規格轉譯`

### 11.3 Required Input

- Approved Strategy Research Proposal
- Research Handoff
- Applicable policy versions

### 11.4 Required Output

Executable Strategy Specification 至少包含：

- Strategy ID
- Strategy Version
- Parent Mode
- Scope and Out of Scope
- Universe Definition
- Required Data Fields
- Point-in-Time Rules
- Signal Formula
- Eligibility Filters
- Ranking Method
- Entry Rules
- Exit Rules
- Rebalancing Rules
- Portfolio Construction
- Tradability Mask
- Transaction Cost Assumptions
- Risk Controls
- Benchmarks
- Backtest Design
- In-Sample, Validation and OOS design
- Sensitivity Tests
- Robustness Tests
- Acceptance and Rejection Gates
- YAML Config Draft
- Assumption Register
- Open Questions
- Engineering Handoff

### 11.5 Exit Gate

只有在以下條件成立時，才能進入 Engineering Translation：

- 不存在會改變策略行為的模糊描述
- 所有必要時間點符合 Point-in-Time Policy
- Universe 與 Tradability 規則明確
- 交易成本與 Benchmark 已定義
- 成功與失敗 Gates 已事前定義
- YAML 與文字規格一致
- Provisional Assumptions 已明確標記
- 重大研究決策沒有被留給工程角色

### 11.6 Owner Decision

由 `02` 決定：

- Ready for Engineering Translation
- Provisional and Blocked
- Return to Research Brain
- Rejected as Non-executable

`02` 不得自行改變上游投資假設；需要改變核心研究內容時必須退回 `01`。

### 11.7 Prohibited Actions

不得：

- 為提高預期回測績效而調整規則
- 使用未來可得資訊
- 將工程便利性當成研究規則
- 隱藏預設參數

## 12. Stage 4 — Engineering Translation

### 12.1 Purpose

把已核准策略規格拆分為小型、可獨立驗收的 GitHub Issues 與 Codex Plan-only Prompts。

### 12.2 Owner

`03｜TWStock 工程轉譯`

### 12.3 Required Input

- Approved Executable Strategy Specification
- Approved YAML Config
- Data Contract requirements
- PIT and Leakage requirements

### 12.4 Required Output

至少包含：

- Issue Decomposition Plan
- GitHub Issue Drafts
- Dependencies
- Engineering Scope
- Data Contracts
- Numerical Tests
- Leakage Tests
- Edge Cases
- Manual Tests
- Acceptance Criteria
- Out of Scope
- Codex Plan-only Prompt
- Human Review Notes

### 12.5 Exit Gate

只有在以下條件成立時，才能進入 Engineering Implementation：

- 每個 Issue 只有一個主要工程結果
- 依賴順序明確
- 資料與 PIT 要求可測試
- 有數值測試與 Leakage Tests
- 沒有自行改變策略規則
- Codex 被要求先產生 Plan，不立即實作
- 人工已審查並核准 Plan

### 12.6 Owner Decision

由 `03` 與 Human Reviewer 決定：

- Ready for Implementation
- Rework Engineering Decomposition
- Return to Specification
- Blocked

這些不是正式策略審計決策。

若需要改變研究規則，必須退回 `02`，不得在本階段自行修改。

## 13. Stage 5 — Engineering Implementation

### 13.1 Purpose

依核准的 Issue 與 Plan 實作資料、特徵、策略、回測或呈現能力。

### 13.2 Owner

- Codex or engineering implementation agent
- Human reviewer
- `03｜TWStock 工程轉譯`負責規格一致性，不負責投資決策

### 13.3 Required Input

- Approved GitHub Issue
- Approved Codex Plan
- Applicable specifications and policies
- Existing Repository architecture

### 13.4 Required Output

- Code changes
- Automated tests
- Numerical tests
- Leakage tests
- Documentation updates
- Pull Request
- Test evidence
- Code Commit SHA

### 13.5 Exit Gate

只有在以下條件成立時，才能進入 Historical Backtest：

- PR 已通過人工審查並合併
- 實作行為與規格及 YAML 一致
- 所有必要自動測試通過
- Leakage Tests 通過
- 錯誤不會被靜默忽略
- 執行環境與依賴可重現
- 尚未解決的限制已記錄
- 沒有未核准的策略行為變更

### 13.6 Implementation Defect Handling

若發現程式錯誤：

```text
Implementation defect
→ Engineering correction
→ 新 Code Commit
→ 新 Experiment ID
→ 重跑受影響測試
```

若錯誤改變了過去實驗結果，舊實驗必須標記為 `Invalidated`，不得刪除。

在尚未形成正式回測證據前，此流程屬工程修正；正式回測後才由 `04` 作出 Retest 決定。

## 14. Stage 6 — Historical Backtest

### 14.1 Purpose

在正式規格、指定資料版本與成本假設下，建立第一份可重現的歷史模擬證據。

### 14.2 Execution Owner

- Backtest execution process
- Engineering implementation

### 14.3 Audit Owner

`04｜台股策略驗證與審計`

### 14.4 Required Input

- Strategy ID and Version
- Specification Version
- Config Version
- Code Commit SHA
- Dataset Versions
- Feature Versions
- PIT Policy Version
- Exchange Calendar Version
- Predefined Backtest Window
- Predefined Gates

### 14.5 Required Output

- Experiment ID
- Full run metadata
- In-Sample results
- Cost-before and cost-after results
- Benchmark comparison
- Trade log
- Holdings history
- Turnover
- Exposure
- Error and warning logs
- Result artifacts
- Reproducibility evidence

### 14.6 Exit Gate

不得因單次報酬良好直接 Promote。

至少必須確認：

- 結果可重現
- PIT 規則通過
- Benchmark 公平
- 交易成本已納入
- 下市與不可成交狀態已處理
- 績效不是明顯計算錯誤
- 資料與程式版本完整
- 沒有 Blocker 級 Leakage

### 14.7 Formal Audit Decision

由 `04` 作出：

- Promote to Robustness Validation
- Retest
- Revise
- Retire

## 15. Stage 7 — Robustness Validation

### 15.1 Purpose

檢查策略結果是否依賴單一參數、股票、產業、年份、市場環境或過度樂觀成本假設。

### 15.2 Required Input

- Historical Backtest evidence package
- Predefined sensitivity ranges
- Validation Protocol

### 15.3 Required Tests

依策略性質至少包括：

- 相鄰參數區域
- 不同持股數
- 不同流動性門檻
- 不同成本與滑價
- 不同再平衡日
- 不同持有期間
- 不同市場 Regime
- 排除極端年份
- 排除最大貢獻股票
- 排除前五大貢獻股票
- 產業與個股集中度
- 容量與市場衝擊
- 可能的 Multiple-testing 調整

### 15.4 Diagnostic Variant Rule

穩健性測試中的替代參數、持股數或權重方法屬於 `Diagnostic Variant`。

它們不能靜默取代正式 Strategy Version。

若決定採用其中一個 Diagnostic Variant 作為新正式規則：

```text
Diagnostic finding
→ Revise
→ 依第 7 節判斷 New Strategy ID、MAJOR 或 MINOR
→ 更新 Specification and Config
→ 重新執行正式測試
```

### 15.5 Exit Gate

只有在以下條件成立時，才能 Promote 至 OOS：

- 核心現象在合理參數區域仍可解釋
- 結果不依賴單一股票或單一年份
- 成本與流動性壓力測試後仍具研究價值
- 主要偏誤已被處理或清楚揭露
- 沒有重大不可重現問題
- OOS 區間尚未被用來調整策略

### 15.6 Formal Audit Decision

由 `04` 作出：

- Promote to Out-of-Sample
- Retest
- Revise
- Retire

## 16. Stage 8 — Out-of-Sample Test

### 16.1 Purpose

使用未參與策略設計與參數選擇的歷史資料，評估策略是否具有樣本外延續性。

### 16.2 OOS Integrity Requirements

OOS 必須：

- 事前定義
- 未參與規則調整
- 未被用來挑選參數
- 使用與正式策略一致的規格
- 使用一致的成本與資料品質標準
- 保存所有結果，不只保存成功結果

### 16.3 OOS Contamination

若 OOS 被反覆查看或用於修改策略：

- 必須降低證據等級
- 原區間不得再稱為未見樣本
- 規則改變時必須依第 7 節建立新 Strategy ID 或新 Strategy Version
- 必須準備新的保留樣本或進入更長 Paper Trading

### 16.4 Exit Gate

只有在以下條件成立時，才能 Promote 至 Paper Trading：

- OOS 沒有與原假設嚴重矛盾
- OOS 結果符合事前 Gates 或獲得有條件通過
- PIT、成本、流動性與集中度問題可接受
- 規格、Config、程式與輸出一致
- 結果可重現
- 沒有未揭露的 OOS 污染

### 16.5 Formal Audit Decision

由 `04` 作出：

- Promote to Paper Trading
- Retest
- Revise
- Retire

## 17. Stage 9 — Paper Trading

### 17.1 Purpose

使用當下可得資料與真實資料到達流程，在不投入真實資金的情況下驗證策略的前瞻性運作能力。

Paper Trading 不只是觀察報酬，也要驗證：

- 資料是否準時到達
- PIT 規則是否可執行
- Universe 是否正確
- 訊號是否按規格形成
- 排名是否可重現
- 訂單是否能形成
- 漲跌停、停牌與未成交如何處理
- 實際資料延遲與滑價估計
- 系統錯誤與人工介入
- Decision Snapshot 是否完整

### 17.2 Required Input

- Approved OOS evidence
- Paper Trading plan
- Current Strategy, Config and Code versions
- Live data contracts
- Monitoring and incident rules

### 17.3 Required Output

- Paper Trading Experiment IDs
- Daily or periodic Decision Snapshots
- Generated signals
- Proposed orders
- Simulated fills
- Missed and delayed orders
- Data arrival logs
- Operational incidents
- Manual interventions
- Estimated realized slippage
- Deviations from specification
- Paper Trading performance

### 17.4 Minimum Evidence Principle

Paper Trading 期間與樣本數必須足以涵蓋策略頻率與主要操作情境。

不得只因短期正報酬就 Promote。

### 17.5 Exit Gate

只有在以下條件成立時，才能 Promote 至 Approved for Live Observation：

- 資料管線與訊號生成穩定
- 訊號與正式規格一致
- 主要交易限制可被正確處理
- Decision Snapshot 完整
- 沒有未解決的 Blocker 級操作風險
- Paper Trading 證據沒有嚴重否證原始假設
- 所有偏離與人工介入已揭露

### 17.6 Formal Audit Decision

由 `04` 作出：

- Promote to Live Observation
- Retest
- Revise
- Retire

## 18. Stage 10 — Approved for Live Observation

### 18.1 Meaning

`LIVE_OBSERVATION` 只代表策略可以持續產生前瞻訊號供研究與監控。

它不代表：

- 核准投入真實資金
- 自動下單授權
- 投資建議
- 未來報酬保證
- 不需要再次驗證

### 18.2 Allowed Activities

- 持續產生前瞻訊號
- 持續建立 Decision Snapshots
- 監控資料與程式事件
- 比較模擬成交與市場實際可成交狀況
- 執行定期策略健康檢查
- 觸發 Revalidation

### 18.3 Out of Scope

真實資金配置、券商串接、自動下單與 Live Capital Approval 不在本文件目前範圍。

若未來要納入，必須先建立獨立政策、風險治理與核准流程。

### 18.4 Revalidation Triggers

至少下列情況應觸發 Retest 或 Revise：

- 資料來源或資料規則改變
- 市場制度改變
- 交易成本顯著改變
- 策略長期偏離歷史預期
- 訊號或成交頻繁失敗
- 產業或個股集中度升高
- 重大程式或資料事件
- 原始經濟邏輯被破壞
- 定期審查到期

## 19. Formal Validation Decisions

本節只適用於 Stage 6 以後的正式審計。

### 19.1 Promote

適用於：

- 當前階段的必要證據完整
- 事前 Gates 達成
- 沒有 Blocker 級問題
- 下一階段所需輸入已準備完成

必須記錄：

- Promoted from
- Promoted to
- Evidence package
- Remaining limitations
- Monitoring requirements
- Revalidation trigger

### 19.2 Revise

適用於需要改變策略研究內容或行為的情況，例如：

- 核心假設需要修改
- Signal Formula 需要修改
- Universe 需要修改
- Entry or Exit rules 需要修改
- Portfolio Construction 需要修改
- Acceptance Gates 本身需要修改

Revise 流程：

```text
Finding
→ Revise Decision by 04
→ 回到 01 或 02
→ 依第 7 節判斷 New Strategy ID、MAJOR 或 MINOR
→ 保留舊版本與舊 lineage 證據
→ 重新 Engineering Translation
→ 重新測試
```

Revise 後不得沿用舊版本的 OOS 身分或 Paper Trading 核准。

### 19.3 Retest

適用於策略假設與正式規格暫時保留，但證據、資料、程式或測試需要重新執行的情況，例如：

- 資料缺漏或錯誤
- 程式 Bug
- 測試未完整
- 缺少特定 Regime
- 缺少交易成本情境
- 結果無法重現
- Paper Trading 期間不足
- Data Contract 或 PIT 實作修正

Retest 流程：

```text
Finding
→ Retest Decision by 04
→ 回到 Data / Engineering / Backtest / Validation
→ 修正問題
→ 新 Dataset / Code / Config version，如適用
→ 新 Experiment ID
→ 保留原實驗
→ 再次審計
```

Retest 不一定需要新 Strategy Version。

只要策略行為沒有改變，就可以維持同一 Strategy Version，但必須建立新 Experiment ID。

### 19.4 Retire

Retire 必須明確指定：

```text
retirement_scope: VERSION | LINEAGE
```

#### VERSION

只停止特定 Strategy Version 的進一步升級：

- 其他版本不會自動被 Retire。
- 必須記錄是否存在 successor version。
- 該版本的實驗與決策紀錄永久保留。

#### LINEAGE

停止整條 Strategy ID lineage 的進一步升級：

- 所有尚未 Retired 的版本都必須被關聯到該 Retirement Record。
- 不得只建立新版本規避 lineage retirement。
- 重新研究必須遵守第 29 節的 Reopening Rules。

適用情況包括：

- 核心經濟邏輯不成立
- 成本後無研究價值
- OOS 持續失效
- 嚴重依賴少數股票或期間
- 資料無法可靠取得
- PIT 問題不可修復
- 交易容量不可接受
- 多次 Revise 或 Retest 仍無法通過最低標準
- 特定版本已被更合理版本取代

Retire 必須保存：

- `retirement_scope`
- Retirement reason
- Supporting evidence
- Failed Gates
- Affected Strategy ID and Versions
- Final Strategy and Experiment versions
- Reopening conditions
- Related successor strategy or version, if any

Retired 策略或版本不得刪除。

## 20. Retest and Revise Decision Test

判斷原則：

```text
是否需要改變底層報酬機制或研究假設？
├── 是 → Revise → New Strategy ID 或 MAJOR，由 01／02 依第 7 節判定
└── 否
    └── 是否需要改變正式策略行為？
        ├── 是 → Revise → MAJOR 或 MINOR
        └── 否
            └── 是否需要重新取得資料、修程式或補測試？
                ├── 是 → Retest
                └── 否 → Promote 或 Retire
```

範例：

| Finding | Decision |
|---|---|
| 月營收公告時間欄位錯置，但訊號公式不變 | Retest |
| 排名因子需要新增毛利率，且代表新的品質報酬機制 | Revise + New Strategy ID |
| 回測 Bug 導致交易成本未扣除 | Retest |
| 需要把持股數從 20 改為 10 作為正式規則 | Revise + MINOR |
| 主要訊號操作化方式重構，但仍衡量相同月營收動能 | Revise + MAJOR |
| 缺少 2008 年市場環境測試 | Retest |
| 核心假設在 OOS 與 Paper Trading 均持續失效 | Retire |

## 21. Gate Model

每個階段 Gate 必須在進入正式測試前定義。

Gate 狀態只能是：

- `PASS`
- `CONDITIONAL_PASS`
- `FAIL`
- `NOT_DEMONSTRATED`
- `NOT_APPLICABLE`

`NOT_DEMONSTRATED` 不得被當作 PASS。

### 21.1 Gate Categories

至少考慮：

- Research logic
- Specification completeness
- Data quality
- PIT integrity
- Reproducibility
- Benchmark fairness
- Transaction feasibility
- Performance
- Robustness
- Concentration
- OOS integrity
- Operational readiness

### 21.2 Gate Changes

看過結果後修改 Gate：

- 必須記錄
- 必須建立新版本
- 原結果不得聲稱通過舊 Gate
- 必須重新執行適用測試

## 22. Evidence Package Requirements

每次正式階段審計應提供 Evidence Package。

至少包含：

- Strategy ID and Version
- Specification Version
- Config Version
- Code Commit SHA
- Dataset Versions
- Feature Versions
- PIT Policy Version
- Experiment IDs
- Result artifacts
- Error and warning logs
- Gate evaluation
- Known limitations
- Proposed next stage

缺少關鍵版本或證據時，原則上不得 Promote。

## 23. Handoff Requirements

跨工作模式時必須建立明確 Handoff。

### 23.1 Research to Specification

至少包含：

- Current Conclusion
- Strategy Concept
- Parent Mode
- Hypothesis
- Target Universe Concept
- Signal Concept
- Holding Horizon
- Risk Principles
- Required Data Concepts
- Required Validation
- Out of Scope
- Open Questions

### 23.2 Specification to Engineering

至少包含：

- Strategy ID and Version
- Approved Specification
- Data Requirements
- PIT Requirements
- Signal Requirements
- Portfolio Rules
- Transaction Rules
- Backtest Requirements
- Numerical Tests
- Leakage Tests
- Acceptance Criteria
- Out of Scope
- Known Risks

### 23.3 Experiment to Audit

至少包含：

- Experiment ID
- Strategy, Config, Code and Data versions
- Test window and classification
- Result artifacts
- Reproducibility evidence
- Gate results
- Known incidents
- Requested decision

### 23.4 Audit to Upstream

Revise 或 Retest 必須指定：

- Finding
- Required action
- Destination workspace
- Required evidence
- Retest or revision scope
- Elements that may be preserved
- Elements that must not be preserved

## 24. Four-workspace Responsibility Matrix

| Activity | 01 Research Brain | 02 Spec Translator | 03 Engineering Translator | 04 Strategy Auditor |
|---|---:|---:|---:|---:|
| Define investment problem | Owner | Consulted | No | Reviewer |
| Approve or reject Idea / Hypothesis | Owner | No | No | No |
| Define executable formula | No | Owner | No | Reviewer |
| Decide specification readiness | Consulted | Owner | No | No |
| Define PIT and transaction assumptions | Consulted | Owner | Translate only | Audit |
| Create GitHub engineering issues | No | No | Owner | No |
| Decide engineering readiness | No | No | Owner with Human Review | No |
| Direct Codex implementation | No | No | Plan and handoff | No |
| Implement code | No | No | Engineering process | No |
| Execute backtests | No | No | Engineering process | Audit evidence |
| Decide formal Promote / Revise / Retest / Retire after experiments | No | No | No | Owner |
| Change strategy rules after results | Research decision | Version specification | Never independently | Never independently |

## 25. GitHub Workflow Relationship

Lifecycle State 與 GitHub Project Status 是相關但不同的概念。

- Lifecycle State 描述策略研究處於哪個階段。
- GitHub Project Status 描述某個工作項目的工程流程。

建議工程工作階段：

```text
Triage
→ Research Review
→ Specification Ready
→ Engineering Translation
→ Codex Plan
→ Codex Implementation
→ PR Review
→ Validation
→ Done
```

另可使用：

- Blocked
- Parked
- Rejected

GitHub Labels 只作分類，不代表工作階段或策略生命週期。

## 26. Lifecycle Record Minimum Fields

每個正式 Strategy Lifecycle Record 至少包含：

- Strategy ID
- Strategy Name
- Strategy Version
- Parent Mode
- Current Lifecycle State
- Previous Lifecycle State
- State entered at
- Current decision status
- Research Decision Record ID, if applicable
- Validation Decision Record ID, if applicable
- Responsible workspace
- Specification Version
- Config Version
- Latest Code Commit SHA
- Latest Dataset Versions
- Latest Feature Versions
- Latest Experiment IDs
- PIT quality status
- Gate summary
- Blocking findings
- Next required action
- Next review date, if applicable
- `retirement_scope`, if retired
- Retirement or supersession reference, if applicable

## 27. Lifecycle Transition Rules

### 27.1 Only One Current Primary State

同一 Strategy Version 在同一時點只能有一個主要 Lifecycle State。

可以同時存在多個實驗，但它們必須明確標示所屬測試類型與狀態。

### 27.2 Historical State Preservation

狀態轉移後，不得覆蓋舊狀態紀錄。

每次轉移必須保存：

- From state
- To state
- Decision
- Decision type: `RESEARCH / SPECIFICATION / ENGINEERING / VALIDATION`
- Decision time
- Evidence
- Actor or workspace
- Conditions

### 27.3 No Silent Backward Transition

退回前一階段必須透過正式階段決策或 `Revise / Retest` 紀錄，不能只在 GitHub 中移動卡片而不記錄原因。

### 27.4 Superseded Versions

新 Strategy Version 建立後：

- 舊版本必須保留
- 舊版本可標記 `SUPERSEDED_VERSION`
- 舊版本的 Experiment 與 Decision Records 不得移轉成新版本證據
- 新版本必須重新通過適用 Gates

### 27.5 Retirement Transition

當 `retirement_scope=VERSION`：

- 只有指定 Strategy Version 轉為 `RETIRED`。
- 其他版本維持各自原狀態。

當 `retirement_scope=LINEAGE`：

- 同一 Strategy ID 下尚未 Retired 的版本必須建立關聯 retirement transition。
- Strategy lineage registry 必須標記為 retired。
- 後續重新研究必須走第 29 節。

## 28. Special Handling of Exploratory Research

探索性研究可以用於：

- 發現候選現象
- 估計合理參數範圍
- 找出資料問題
- 形成正式假設

但探索性結果：

- 必須標記 `Exploratory`
- 不得冒充 Confirmatory Evidence
- 不得直接支持 Promote 至 Paper Trading
- 不得把反覆查看的樣本稱為 OOS
- 必須記錄測試過的主要變體

正式規格確立後，才可建立確認性測試計畫。

## 29. Strategy Reopening Rules

Retired 策略可以重新研究，但必須先識別原本的 retirement scope。

### 29.1 Reopen a Retired Version

若 `retirement_scope=VERSION`，重新研究該版本原則上應：

- 引用原 Retirement Record
- 說明新的證據或可修復條件
- 建立新 Strategy Version，而不是直接恢復原版本
- 重新經過適用生命週期階段

### 29.2 Reopen a Retired Lineage

若 `retirement_scope=LINEAGE`，只有下列情況才可重新研究：

- 出現足以改變原結論的新經濟或行為證據
- 出現可修復原重大限制的全新資料來源
- 市場制度發生重大變化
- 原本不可交易的限制已實質改變

重新開啟時必須：

- 引用原 Lineage Retirement Record
- 由 `01` 判斷原報酬機制是否仍相同
- 若假設或報酬機制改變，建立新 Strategy ID
- 若底層機制仍相同但研究設計重大重構，建立新 MAJOR Version
- 不得刪除原失敗證據
- 重新經過適用生命週期階段

## 30. Expiration and Periodic Review

任何已進入 Paper Trading 或 Live Observation 的策略都必須設定：

- Review frequency
- Next review date
- Revalidation triggers
- Data and code incident triggers
- Maximum period without review

若超過審查期限：

- 不得假設原核准永久有效
- 應進入 Retest 或暫停狀態
- 必須更新 Decision Record

## 31. Prohibited Practices

TWStock 禁止：

- 從 Idea 直接進入 Codex
- 未完成正式規格就執行確認性回測
- 用 In-Sample 取代 OOS
- 看過 OOS 後仍將其視為未見樣本
- 用單次高報酬支持 Paper Trading 或實盤
- 省略交易成本、漲跌停、停牌與下市處理
- 工程角色自行新增投資規則
- 審計角色自行修改策略使結果通過
- 改變報酬機制卻只升級 MAJOR Version
- 修改策略行為但不升級適當 Strategy Version
- 重跑實驗但沿用同一 Experiment ID
- 程式錯誤後刪除舊實驗
- 刪除被 Retire 的策略或版本
- 只保存成功版本
- 用 GitHub Label 代替正式 Lifecycle State
- 把 Live Observation 描述為 Live Capital Approval
- 將歷史回測描述為未來獲利保證
- 讓 `04` 取代 `01` 或 `02` 作出早期研究與規格決策

## 32. Exceptions

任何偏離本文件的例外都必須：

1. 明確記錄。
2. 說明必要性。
3. 指定 Strategy ID、Version、Stage 與適用範圍。
4. 評估可能偏誤。
5. 設定到期或重審條件。
6. 標記受影響證據為 Provisional。
7. 不得用例外結果直接支持 Promote。

例外不得成為隱藏預設。

## 33. Engineering Acceptance Criteria

未來生命週期與研究紀錄系統至少必須達成：

- [ ] 每個 Strategy Version 具有唯一 Current Lifecycle State。
- [ ] 每次狀態轉移都保存 From、To、Decision、Decision Type、Evidence 與 Timestamp。
- [ ] 早期 Research／Specification／Engineering 決策與正式 Validation Decision 分開儲存。
- [ ] Formal Promote、Revise、Retest、Retire 只能由 `04` 在正式實驗形成後作出。
- [ ] Retest 強制建立新 Experiment ID。
- [ ] Revise 強制依第 7 節判定 New Strategy ID、MAJOR 或 MINOR。
- [ ] Retire 強制指定 `retirement_scope: VERSION | LINEAGE`。
- [ ] Retired 與 Superseded records 不得被刪除。
- [ ] Lifecycle State 與 GitHub Project Status 分開儲存。
- [ ] 缺少必要 Evidence Package 時系統不得標記 Promote。
- [ ] OOS 污染可以被標記並降低證據等級。
- [ ] Diagnostic Variants 不會靜默取代正式策略規則。
- [ ] Live Observation 不會被誤標為 Live Capital Approval。
- [ ] 狀態與版本紀錄可被 Experiment Registry 及 Decision Snapshot 引用。

## 34. Research Reporting Requirements

正式策略頁面或報告至少應顯示：

- Strategy ID and Version
- Current Lifecycle State
- Latest Research Decision, if pre-backtest
- Latest Validation Decision, if applicable
- Evidence classification
- Latest Experiment IDs
- PIT quality status
- OOS status
- Paper Trading status
- Known limitations
- Next required action
- Last review date
- Retirement scope and successor reference, if applicable

允許：

> 本策略版本已通過歷史回測與穩健性檢查，目前進入 Out-of-Sample 測試；尚未取得 Paper Trading 或真實資金核准。

不允許：

> 這個策略已經回測成功，可以直接買進。

## 35. Revision Policy

下列變更需要建立本文件新版本並透過 Pull Request 審查：

- Lifecycle stages 改變
- Promotion Gates 改變
- Promote、Revise、Retest、Retire 定義改變
- Strategy ID 與 Strategy Version 判準改變
- OOS 或 Paper Trading 進出條件改變
- Live Observation 定義改變
- 四個工作模式責任邊界改變
- Evidence Package 最低要求改變
- Lifecycle Record 欄位改變
- Retirement scope 規則改變

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Affected Strategies
- Required Migration
- Required Retest Scope

## 36. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
2. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
3. `docs/research/VALIDATION_PROTOCOL.md`
4. Dataset-specific Data Contracts
5. Thin Website Information Architecture

在 Experiment Registry、Decision Snapshot 與 Validation Protocol 完成以前，不應將任何策略描述為完整可審計或可進入真實資金階段。
