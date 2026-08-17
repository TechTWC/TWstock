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

持續創高的早期雷達為獨立實驗，可執行：

```bash
python -m unittest -v tests.test_continuous_high_monitor
python scripts/run_continuous_high_demo.py
```

第二個指令會在 `outputs/experiments/continuous_high_monitor/` 產生獨立 HTML/SVG
強勢發展圖、完整事件時間線 CSV，以及包含未進雷達日期的客觀特徵 CSV。規則、參數治理與 v0.1 排除項目見
[`docs/specs/continuous_high_monitor_v0_1.md`](docs/specs/continuous_high_monitor_v0_1.md)。

真實日線資料的第一個 bounded 接入工作包使用既有 TWSE primary adapter 與可選的
FinMind secondary cross-check，產生兩個監控器共用的 canonical bars 與資料／執行
manifest：

```bash
python -m unittest -v tests.test_research_market_dataset

python scripts/run_real_market_monitor.py \
  --symbol 2330 \
  --start 2025-01-01 \
  --end 2026-08-10 \
  --output-dir outputs/real_market/2330 \
  --raw-cache-dir outputs/raw_market/2330
```

資料仍為未還原權值、未處理公司行動的 raw daily bars；來源信任、fail-closed
規則、內容雜湊與明確排除項見
[`docs/specs/real_market_data_ingestion_v0_1.md`](docs/specs/real_market_data_ingestion_v0_1.md)。

多檔及全市場 Shadow Observation 已整合為 `Watchlist Radar v0.4`。
主分類為透明的七狀態均線雷達，雙斜率方法獨立並排，不合成分數；Breakout／
Continuous High只作輔助證據，不再影響觀察順序。報告包含七狀態分布、今日重要
轉換、完整方法並排表、每檔事件疊加股價圖、核心與長期均線圖及跨股票時間線；完全離線可開啟。持續使用同一個
raw cache 目錄時，已驗證歷史月份會直接續用，只補抓缺月，實際當月則每次強制刷新：

```bash
python -m unittest -v tests.test_watchlist_scanner

python scripts/run_watchlist_scanner.py \
  --watchlist config/watchlist_v0_1.json \
  --start 2025-01-01 \
  --end 2026-08-14 \
  --output-dir outputs/watchlist_radar_v0_4 \
  --raw-cache-dir outputs/raw_watchlist_radar_v0_4
```

公司行動資料未接入，因此每一列固定標示 `UNVERIFIED`，`investment_use` 固定為
`PROHIBITED`。順序只代表研究優先次序，不是投資評分。

全部上市普通股的每日 Shadow Observation 可改用官方全市場日資料。第一次建立
歷史需明確放寬下載天數；完成後每日只新增／刷新當日。`--include-cb` 會加入櫃買中心
官方「目前有 CB／近期下櫃／目前與近期未查得／未驗證」分類：

```bash
python scripts/run_watchlist_scanner.py \
  --all-listed \
  --start 2025-08-01 \
  --end 2026-08-17 \
  --output-dir outputs/watchlist_radar_v0_4/2026-08-17 \
  --raw-cache-dir data/runtime/raw/watchlist_radar_v0_4 \
  --include-cb \
  --max-new-market-days 400
```

後續每日沿用相同 `--raw-cache-dir`，將 `--max-new-market-days` 恢復為預設 10。
`NOT_FOUND_CURRENT_OR_RECENT` 不代表公司從未發行 CB。完整邊界見
[`docs/specs/watchlist_radar_v0_4.md`](docs/specs/watchlist_radar_v0_4.md)。

## Test Infrastructure

固定的 Python 3.12 開發測試依賴與完整測試可執行：

```bash
python -m pip install --requirement requirements-dev.txt
python -m pytest -q
```

一般 CI 不取得 FinMind Secret，也不執行 live network call。受控的 13 個月
FinMind live smoke 僅能由 GitHub Actions 手動啟動；Secret 設定、執行順序、
fail-closed 驗證條件與限制見
[`docs/operations/test_infrastructure_live_smoke.md`](docs/operations/test_infrastructure_live_smoke.md)。

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
