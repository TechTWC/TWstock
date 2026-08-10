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

## Operating Model

TWStock 保留研究、規格、工程與獨立驗證的角色分離，但不再要求使用四個固定 ChatGPT Workspace，也不要求每一個探索性修改都走完整治理生命週期。

目前採雙軌流程：

- 探索性研究：短規格 → bounded implementation → 診斷測試 → 保存結果。
- 正式策略驗證：預先鎖定規格 → PIT 回測 → 穩健性／OOS → 影子運行 → 獨立驗證。

任何正式績效主張仍不得由策略設計者或單次回測自行核准。

## Current Development

目前優先開發 `Breakout Tracker v5`，先建立無未來資訊的 Pivot、首次突破事件與跨日狀態引擎，再接 Yahoo 探索資料、歷史逐日重播及正式市場資料驗證。

完整現況、文件效力與目前限制以 [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) 為準。

目前的合成資料事件引擎驗證可執行：

```bash
python -m unittest -v tests.test_breakout_tracker_v5
```

事件定義與明確排除項目見 [`docs/specs/breakout_tracker_v5.md`](docs/specs/breakout_tracker_v5.md)。

## Experimental Phase A1 Logic Sandbox

`Phase A1 Logic Sandbox v0.1` 是 `Fundamental_Valuation_Trend_Breakout_v1` 的最小可執行規則沙盒。它只讀取已標準化的合成／人工快照 CSV，執行流動性、財務生存、絕對 PE、營業利益方向與 Primary Action 規則。

```bash
python -m twstock_engine.runner \
  --input data/sample/phase_a1_snapshot.csv \
  --output-dir outputs/latest

python -m pytest tests/test_phase_a1_rules.py
```

此沙盒不是正式資料管線、不是 production-ready 系統，也不是已驗證的投資策略。

## Status

```text
Project stage: Research infrastructure + bounded strategy experiments
Production readiness: Not ready
Validated strategies: None
Live trading approval: None
```
