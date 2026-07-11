# TWStock

TWStock 是一個以台灣股票市場為主要研究範圍的個人投資研究與策略驗證平台。

本專案不是選股明牌網站，也不以歷史回測結果保證未來獲利。

## Project Purpose

TWStock 用於持續建立、規格化、實作、回測、驗證、修訂及淘汰投資策略。

平台預計支援：

- 台股投資研究
- 策略假設與版本管理
- 母策略與子策略管理
- Point-in-Time 資料處理
- 歷史回測
- 穩健性測試
- Out-of-Sample 驗證
- 紙上交易
- Experiment Registry
- Decision Snapshot
- 策略升級、修訂與淘汰

## Research Lifecycle

所有策略原則上依序經過：

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

不得由模糊投資想法直接進入工程實作。

## Core Research Principles

1. 歷史日期只能使用當時已公開且合理可取得的資料。
2. 必須區分資料所屬期間、公告日、可用日、訊號形成日與可交易日。
3. 必須考慮 Look-ahead Bias、Survivorship Bias、Data Snooping 與 Overfitting。
4. 必須納入合理交易成本、滑價、流動性與實際可成交限制。
5. 必須區分 In-Sample、Validation 與 Out-of-Sample。
6. 必須保存策略、設定、資料、程式及實驗版本。
7. 成功與失敗實驗都必須保存。
8. 回測結果只代表歷史模擬，不代表未來報酬保證。

## Source of Truth

GitHub Repository 是本專案正式且永久的真相來源。

ChatGPT 專案與對話用於：

- 研究
- 規劃
- 規格轉譯
- 工程轉譯
- 驗證與審計

重要決策完成後，必須整理進本 Repository，不得只保存在聊天紀錄中。

## Fixed Workspaces

TWStock 使用四個分離的工作模式：

1. `01｜台股研究與策略大腦`
2. `02｜台股研究規格轉譯`
3. `03｜TWStock 工程轉譯`
4. `04｜台股策略驗證與審計`

不得在同一項工作中混合策略設計、工程實作及策略審計。

## Current Build Order

目前建設順序為：

1. 固定系統願景與研究原則
2. 固定資料契約與 Point-in-Time Policy
3. 固定策略生命週期
4. 固定 Experiment Registry
5. 固定 Decision Snapshot
6. 建立薄網站資訊架構
7. 建立 Foundation Engine
8. 完成第一個端到端策略垂直切片
9. 執行策略驗證與審計
10. 逐步增加其他 Strategy Modes 與子策略

第一個策略垂直切片原則上優先研究台股月營收／盈餘動能，但目前不得將其視為已驗證有效策略。


## Website Bootstrap

Issue #9 introduces the first minimal Astro static website scaffold for TWStock.
The website entry point is a bootstrap page for `TWStock Research Console v0.1`;
it does not contain strategy rules, backtesting, registry data, APIs, login,
authentication, deployment configuration, market data, analytics, or investment
recommendations.

Static production output is generated in `dist/`.

### Prerequisites

- Node.js `24.18.0`
- pnpm `11.11.0`

Enable the pinned package manager with Corepack:

```bash
corepack enable
corepack prepare pnpm@11.11.0 --activate
```

### Install

```bash
pnpm install --frozen-lockfile
```

### Development server

```bash
pnpm dev
```

### Typecheck

```bash
pnpm typecheck
```

### Build

```bash
pnpm build
```

### Preview production build

```bash
pnpm preview
```

## Status

```text
Project stage: Foundation specification
Production readiness: Not ready
Validated strategies: None
Live trading approval: None
```
