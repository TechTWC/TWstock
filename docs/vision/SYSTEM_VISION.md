# TWStock System Vision

- Document ID: `TWSTOCK-VISION-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: TWStock personal investment research and strategy validation platform

## 1. Purpose

TWStock 是一個以台灣股票市場為主要研究範圍的個人投資研究與策略驗證平台。

平台的核心目的不是提供即時買賣明牌，而是建立一套可以長期持續運作的研究系統，使投資想法能夠依序被：

```text
提出
→ 規格化
→ 實作
→ 回測
→ 驗證
→ 紙上交易
→ 升級、修訂或淘汰
```

TWStock 應讓每一個策略結論都能回溯到當時使用的資料、策略版本、設定版本、程式版本、實驗紀錄與決策依據。

## 2. Product Positioning

TWStock 的正式定位是：

> 可持續建立、規格化、回測、驗證、紙上交易、升級、修訂與淘汰投資策略的個人研究平台。

TWStock 不是：

- 選股明牌網站
- 保證獲利的交易系統
- 未經驗證即可直接下單的自動交易機器人
- 只展示漂亮績效曲線的回測工具
- 以目前存續股票回推歷史的選股器
- 以單次回測結果判定策略有效的系統
- 大眾投顧服務或投資建議平台

## 3. Primary User

目前主要使用者是平台擁有者本人。

主要使用情境包括：

- 將書籍、投資大師方法、市場現象或個人想法轉成可否證假設
- 建立母策略與多個子策略
- 研究台股基本面、估值、營收盈餘動能、價格動能、事件與風險條件
- 使用歷史資料進行 Point-in-Time 正確的回測
- 比較策略與適當 Benchmark
- 記錄成功及失敗實驗
- 進行 Out-of-Sample 與紙上交易驗證
- 根據證據決定 Promote、Revise、Retest 或 Retire

TWStock 現階段不預設為多人協作 SaaS，也不以公開銷售投資建議為產品目標。

## 4. Core Research Questions

平台必須能回答以下問題：

1. 這個策略想捕捉什麼經濟、風險、資訊或行為現象？
2. 策略規則是否明確到可以被另一個研究者重現？
3. 歷史日期是否只使用當時已公開且合理可取得的資料？
4. 當時有哪些股票實際符合上市、流動性與可交易條件？
5. 回測結果是否包含交易成本、滑價、漲跌停、停牌與下市？
6. 績效是否優於適當 Benchmark，而非只呈現絕對報酬？
7. 結果是否依賴單一股票、產業、年份、市場環境或精確參數？
8. Out-of-Sample 是否真正未參與規則調整？
9. 策略是否值得進入紙上交易或下一個研究階段？
10. 失敗策略是否被保留、解釋並正式淘汰？

## 5. Required Capabilities

TWStock 最終必須支援下列能力。

### 5.1 Research Governance

- Strategy Mode 與子策略管理
- Strategy ID 與語意化版本管理
- Research Proposal
- Executable Strategy Specification
- Assumption Register
- Acceptance and Rejection Gates
- Strategy Decision Log
- Strategy Lifecycle Status

### 5.2 Data Governance

- 資料來源與 lineage
- Dataset Version
- Data Dictionary
- Data Contract
- Data Quality Rules
- 公告時間、可用時間及有效日期
- 修訂值與重編資料處理
- 公司行動
- 上市、下市、轉板、停牌及代號變更
- 歷史 Universe

### 5.3 Point-in-Time Research

每筆具有研究意義的資料原則上必須區分：

- Observation Period
- Announcement Timestamp
- Available Timestamp
- Signal Formation Timestamp
- Execution Timestamp

並遵守：

```text
Announcement Timestamp
≤ Available Timestamp
≤ Signal Formation Timestamp
≤ Execution Timestamp
```

若公告發生於收盤後，系統不得假設能以當日收盤價成交。

### 5.4 Research Engine

- Universe Engine
- Tradability Mask
- Feature Engine
- Strategy Engine
- Ranking Engine
- Portfolio Construction
- Transaction Simulation
- Benchmark Engine
- Backtest Engine
- Performance Analytics

### 5.5 Validation

- In-Sample
- Validation Window
- Out-of-Sample
- Walk-forward Test
- Parameter Sensitivity
- Robustness Test
- Regime Analysis
- Concentration Analysis
- Transaction Feasibility
- Leakage Tests
- Paper Trading

### 5.6 Research Records

- Experiment Registry
- Decision Snapshot
- Backtest Artifacts
- Validation Report
- Failed Experiment Records
- Code Commit SHA
- Config Version
- Dataset Version
- Feature Version
- Runtime Environment

### 5.7 Thin Research Website

網站是研究操作與結果呈現層，不是平台的唯一核心。

初期資訊架構原則上包含：

- Dashboard
- Strategies
- Experiments
- Stocks
- Decision Snapshots
- Data Status

網站必須清楚區分：

- Historical Simulation
- Out-of-Sample Result
- Paper Trading Result
- Live Observation

不得以 UI 文案暗示歷史回測等於未來獲利保證。

## 6. Strategy Structure

TWStock 允許多個 Strategy Mode，且每個 Mode 下可以建立多個子策略。

概念結構如下：

```text
Strategy Mode
└── Strategy
    ├── Version 1.0.0
    ├── Version 1.1.0
    └── Version 2.0.0
```

投資大師、書籍法則或市場慣例只能作為研究來源，不能直接被視為有效策略。

例如巴菲特、彼得林區、價值投資或動能投資方法，都必須被轉換為：

- 明確研究假設
- 可量化訊號
- 明確 Universe
- 明確再平衡與持有規則
- 明確交易成本
- 可否證條件
- 事前定義的驗證 Gates

所有 Mode 最終都可以研究，但不得同時進行全部策略工程開發。

## 7. Strategy Lifecycle

所有策略原則上必須依序經過：

```text
Idea
→ Hypothesis
→ Research Specification
→ Engineering Implementation
→ Historical Backtest
→ Robustness Validation
→ Out-of-Sample Test
→ Paper Trading
→ Promotion / Revision / Retirement
```

不得跳過 Research Specification，直接由模糊想法進入工程實作。

每一個階段都必須有明確輸入、產出、版本與通過條件。

### 7.1 Promotion Decisions

策略驗證與審計只能作出：

- Promote
- Revise
- Retest
- Retire

Promote 只表示進入下一個研究階段，不表示可以直接投入真實資金。

## 8. Fixed Operating Workspaces

ChatGPT Project 使用四個彼此分離的工作模式：

1. `01｜台股研究與策略大腦`
2. `02｜台股研究規格轉譯`
3. `03｜TWStock 工程轉譯`
4. `04｜台股策略驗證與審計`

角色邊界如下：

- 研究大腦負責判斷想法是否值得研究，不直接寫程式。
- 研究規格轉譯負責消除模糊語言，不自行發明投資理念。
- 工程轉譯負責拆分可驗收的 GitHub Issues，不自行改變研究規則。
- 策略審計負責檢查證據與偏誤，不自行修改策略使結果變好。

如果工作需要跨角色，必須使用明確 Handoff，而不是在同一項工作中混合決策與實作。

## 9. Source of Truth

GitHub Repository 是 TWStock 正式且永久的真相來源。

ChatGPT 對話是研究、規劃、轉譯與審查的工作檯，不是永久規格保存位置。

重要產出完成後必須寫入 Repository，包括：

- 系統願景
- 研究原則
- 資料契約
- Point-in-Time Policy
- 策略規格
- YAML Config
- Experiment Registry
- Decision Snapshot
- 回測與驗證結果
- 策略決策紀錄
- GitHub Issues
- Pull Requests

GitHub Project Status 是工程工作階段的唯一真相來源；Labels 只作為分類資訊。

## 10. Non-negotiable Research Principles

1. 歷史日期只能使用當時已公開且合理可取得的資料。
2. 不得使用今日存續公司清單回推歷史 Universe。
3. 必須保留下市、停牌、合併及失敗公司對歷史樣本的影響。
4. 必須納入合理交易成本、滑價與實際可成交限制。
5. 必須區分 In-Sample、Validation 與 Out-of-Sample。
6. 看過 Out-of-Sample 後修改規則，必須建立新策略版本。
7. 必須執行參數敏感度與不同市場環境測試。
8. 必須保存程式、設定、資料與實驗版本。
9. 必須保存失敗實驗，不能只保存最佳結果。
10. 回測結果只代表歷史模擬，不代表未來報酬保證。

## 11. Foundation-first Architecture

TWStock 不應先同時開發所有策略。

應先完成共用 Foundation Engine，再逐一完成策略垂直切片。

Foundation Engine 原則上包含：

1. Data Layer
2. Point-in-Time Layer
3. Universe Engine
4. Feature Engine
5. Strategy Engine
6. Backtest Engine
7. Experiment Registry
8. Decision Snapshot

第一個策略垂直切片原則上優先研究「台股月營收／盈餘動能」。

選擇它作為第一個垂直切片，不代表它已被證明最佳，而是因為它能同時驗證：

- 台股特色資料
- 公告日期
- Point-in-Time
- Universe
- 成長率與排名
- 流動性
- 月度再平衡
- 交易成本
- 回測輸出
- Experiment Registry
- Strategy Page

## 12. Build Order

目前正式建設順序為：

1. 固定系統願景與研究原則
2. 固定資料契約與 Point-in-Time Policy
3. 固定策略生命週期
4. 固定 Experiment Registry
5. 固定 Decision Snapshot
6. 建立薄網站資訊架構
7. 建立 Foundation Engine
8. 完成第一個端到端策略垂直切片
9. 執行策略驗證與審計
10. 再逐步增加其他 Strategy Modes 與子策略

初期不得因網站展示需求而跳過資料治理與研究治理。

## 13. Success Criteria

TWStock 的成功不以「找到一個回測報酬很高的策略」作為唯一標準。

平台成功的最低條件包括：

### 13.1 Traceability

任一研究結論都能追蹤到：

- Strategy ID and Version
- Config Version
- Dataset Version
- Feature Version
- Code Commit SHA
- Experiment ID
- Result Artifacts
- Decision Record

### 13.2 Point-in-Time Explainability

任一歷史訊號都能回答：

- 當時有哪些資料已公告？
- 系統何時取得資料？
- 何時形成訊號？
- 何時可以交易？
- 當時有哪些股票符合 Universe 與 Tradability Mask？

### 13.3 Reproducibility

相同版本、相同輸入及相同參數，應能產生相同結果或落在預先定義的數值容忍範圍內。

### 13.4 Honest Validation

系統能夠：

- 顯示失敗實驗
- 識別資料洩漏
- 拒絕不公平 Benchmark
- 識別集中度與 Regime 依賴
- 淘汰無法通過驗證的策略

### 13.5 Operational Readiness

策略只有在資料管線、訊號、交易模擬、紀錄與紙上交易流程都可穩定運作後，才具備進一步觀察資格。

## 14. Explicit Non-goals for the Initial Phase

初期不處理：

- 真實券商下單
- 自動實盤交易
- 保證獲利或報酬預測承諾
- 大眾投顧服務
- 全部 Strategy Modes 同時開發
- 複雜權限與多人組織管理
- 為展示效果而建立大量無研究基礎的選股頁面
- 在資料契約與 PIT Policy 完成前大規模接入資料
- 在回測與驗證規範完成前宣稱策略有效

## 15. Current Project State

截至本文件版本：

```text
Project stage: Foundation specification
Repository state: Initialized
Validated strategies: None
Paper-trading strategies: None
Live trading approval: None
Primary vertical slice: Monthly revenue / earnings momentum research
```

「Primary vertical slice」代表優先研究與工程驗證對象，不代表已核准或已驗證策略。

## 16. Key Risks

目前主要風險包括：

- 過早開發網站，資料與研究治理不足
- 資料來源無法提供可靠歷史公告時間
- 使用最新修訂值污染歷史回測
- 使用今日股票清單造成 Survivorship Bias
- 多策略、多參數測試後只保留最佳結果
- 交易成本與不可成交條件被低估
- 規格、YAML 與程式行為不一致
- 對話中的決策未同步回 GitHub
- 同時開發太多 Strategy Modes，導致 Foundation 無法完成

## 17. Revision Policy

本文件是系統層級基準，不應因單一策略需求隨意修改。

若發生以下情況，應建立新版本並透過 Pull Request 審查：

- 平台定位改變
- 主要使用者改變
- 策略生命週期改變
- 永久真相來源改變
- 研究治理原則改變
- Foundation-first 建設順序改變
- 真實交易或外部使用者正式納入範圍

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Follow-up Updates

## 18. Next Documents

本系統願景確立後，下一批基準文件依序為：

1. `docs/vision/RESEARCH_PRINCIPLES.md`
2. `docs/data/POINT_IN_TIME_POLICY.md`
3. `docs/research/STRATEGY_LIFECYCLE.md`
4. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
5. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`

在上述治理文件建立以前，不應開始大量策略工程實作。