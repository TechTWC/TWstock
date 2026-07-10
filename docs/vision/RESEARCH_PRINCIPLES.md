# TWStock Research Principles

- Document ID: `TWSTOCK-RESEARCH-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock investment research, data processing, strategy specifications, backtests, validation, paper trading, and research reporting

## 1. Purpose

本文件定義 TWStock 所有研究活動都不得違反的最低標準。

TWStock 的目標不是找到一條看起來漂亮的歷史績效曲線，而是建立一個可以持續提出、否證、重現、審計、修訂與淘汰策略的研究系統。

任何策略、資料集、特徵、回測或研究報告，只要違反本文件的核心原則，即使歷史報酬率很高，也不得被描述為可信、已驗證或可投入真實資金。

## 2. Authority and Document Hierarchy

GitHub Repository 是 TWStock 正式且永久的真相來源。

當不同文件、設定或程式行為互相衝突時，原則上依以下優先層級處理：

```text
1. SYSTEM_VISION.md
2. Approved policy documents
3. Approved strategy research specification
4. Approved strategy YAML config
5. Approved engineering contracts and interfaces
6. Implementation code
7. Backtest or experiment output
8. ChatGPT conversations, temporary notes, and Handoff Batons
```

其中 policy documents 包含但不限於：

- `RESEARCH_PRINCIPLES.md`
- `POINT_IN_TIME_POLICY.md`
- `STRATEGY_LIFECYCLE.md`
- `VALIDATION_PROTOCOL.md`
- Data Contracts

若低層文件或程式行為與高層正式文件衝突：

1. 不得靜默選擇其中一方。
2. 必須記錄衝突。
3. 必須停止受影響的研究結論升級。
4. 必須由適當工作模式決定修正方向。
5. 修正後必須建立新版本或新實驗紀錄。

ChatGPT 對話可以協助研究與轉譯，但不能取代已核准的 GitHub 文件。

## 3. Separation of Claims

所有 TWStock 研究必須清楚區分以下五類內容。

### 3.1 Decision

已由適當工作模式核准，並寫入正式文件的決策。

### 3.2 Hypothesis

尚待資料支持或否證的研究假設。

### 3.3 Evidence

由可追蹤的資料、程式、實驗或文件直接支持的結果。

### 3.4 Inference

研究者根據證據作出的推論，但證據本身不等於該結論。

### 3.5 Recommendation

基於目前證據提出的下一步建議，不代表事實或保證。

不得把 Hypothesis 寫成 Evidence，也不得把 Inference 寫成已驗證事實。

## 4. Falsifiability

每一個正式策略研究都必須具有可否證性。

至少必須回答：

1. 策略想捕捉什麼經濟、風險、資訊或行為現象？
2. 在哪些條件下預期有效？
3. 在哪些條件下預期失效？
4. 什麼結果會支持該假設？
5. 什麼結果會否證該假設？
6. 什麼證據不足以支持任何結論？

下列陳述不能直接成為正式研究假設：

- 好公司長期一定會漲
- 營收成長就值得買
- 法人買超代表後續看好
- 估值便宜一定會回歸
- 技術面轉強就會延續
- 投資大師使用過，所以策略有效

它們必須被轉換成可量化、可比較、有時間邊界且可被否證的研究命題。

## 5. Point-in-Time Integrity

歷史日期只能使用當時已公開、合理可取得且依規則允許使用的資料。

對具有公告事件的資料，至少必須區分：

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

不得：

- 在公告前使用月營收或財報數字
- 將收盤後公告視為可在同日收盤成交
- 用後續修訂值覆蓋歷史當時可見值
- 用今日股票清單、產業分類或指數成分回推歷史
- 用完整樣本期間的統計量計算早期訊號
- 用未來價格或未來成交量決定當期資格

對價格、成交量、指數行情等沒有公司公告事件的市場資料，其可用時間與交易時間規則必須由 `POINT_IN_TIME_POLICY.md` 另行定義，不得強行填入虛假的公告時間。

## 6. Historical Universe and Survivorship Bias

任何歷史回測都必須建立當時的可投資 Universe，而不是使用目前仍存在的股票清單。

Universe 至少要能處理：

- 上市日與下市日
- 上市、上櫃及轉板狀態
- 股票代號或名稱變更
- 合併、收購與消滅
- 停牌與恢復交易
- 全額交割或特殊交易狀態
- 處置股票
- 下市股票
- 曾經存在但目前已不存在的公司

不得因為資料難取得就直接排除失敗公司或下市股票，卻仍宣稱回測代表完整台股市場。

若歷史 Universe 或下市資料不完整，研究報告必須：

1. 明確揭露缺口。
2. 評估可能造成的偏誤方向。
3. 將結果標記為 Provisional。
4. 不得進入 Promote。

## 7. Data Lineage and Data Quality

每一個正式資料集都必須能追蹤：

- 資料來源
- 取得方式
- 取得時間
- Dataset Version
- 原始欄位
- 清理規則
- 欄位轉換
- 重複資料處理
- 缺值處理
- 修訂與重編處理
- 公司行動處理
- 異常資料處理
- 下游使用位置

不得靜默修改原始資料。

任何人工修正必須保存：

- 修改前值
- 修改後值
- 修改原因
- 修改時間
- 修改者或執行程序
- 影響範圍

缺值必須盡可能區分：

- 尚未公告
- 真正不適用
- 來源缺漏
- 取得失敗
- 清理失敗
- 無法識別

不同缺值原因不得在未說明情況下全部以零值或前值填補。

## 8. No Silent Failure

任何可能改變策略結果的資料或計算錯誤，都不得被靜默忽略。

系統應依錯誤類型明確選擇：

- Fail fast
- Quarantine
- Skip with warning
- Use documented fallback
- Block experiment promotion

錯誤紀錄至少包含：

- Error type
- Affected dataset or security
- Affected date range
- Severity
- Handling action
- Whether results remain valid

## 9. Strategy Specification Before Implementation

模糊的投資想法不得直接進入程式實作。

在工程實作前，正式策略規格至少必須定義：

- Strategy ID
- Strategy Version
- Parent Mode
- Universe
- Required data fields
- Point-in-Time rules
- Signal formula
- Eligibility filters
- Ranking method
- Entry rules
- Exit rules
- Rebalancing rules
- Portfolio construction
- Tradability Mask
- Transaction costs
- Benchmark
- Backtest design
- Sensitivity tests
- Robustness tests
- Acceptance and Rejection Gates

工程角色不得自行增加訊號、門檻或投資規則。

若規格不完整，工程應回報並停止，而不是用未記錄的預設值補齊。

## 10. Pre-registration and Change Control

在查看正式測試結果前，應盡可能事前固定：

- 核心假設
- 主要訊號
- Universe
- 主要參數
- Benchmark
- 成本假設
- In-Sample 區間
- Validation 區間
- Out-of-Sample 區間
- Acceptance Gates
- Rejection Gates

在看到結果後改變規則，必須記錄：

- 改變內容
- 改變原因
- 是否由結果驅動
- 影響哪些歷史測試
- 是否需要新 Strategy Version
- 是否需要新的未見樣本

不得看過 Out-of-Sample 後持續修改規則，卻仍將原區間稱為 Out-of-Sample。

## 11. In-Sample, Validation, and Out-of-Sample

### 11.1 In-Sample

可用於：

- 初步探索
- 規則開發
- 參數研究
- 錯誤排查

In-Sample 結果不得單獨支持策略升級至紙上交易。

### 11.2 Validation

用於：

- 參數敏感度
- 不同持股數
- 不同流動性門檻
- 不同交易成本
- 不同再平衡日
- 不同市場環境
- 排除極端年份
- 排除最大貢獻股票

### 11.3 Out-of-Sample

必須盡可能保持未參與策略調整。

若 OOS 被反覆查看、用於挑參數或用於修改規則，必須降低其證據等級。

### 11.4 Walk-forward

當策略需要滾動更新參數、模型或特徵時，應採用符合時間順序的 Walk-forward，而不是隨機切割時間序列。

## 12. Data Snooping and Multiple Testing

TWStock 必須保存所有重要實驗，包括失敗、無效及被否證的結果。

每次研究應記錄：

- 測試過的策略變體數
- 測試過的參數組合數
- 被放棄的規則
- 被否證的假設
- 人工篩選步驟
- OOS 被查看的次數

不得只保存最佳結果或只報告最漂亮的圖表。

當同時測試大量策略、因子或參數時，應視情況使用：

- False Discovery Rate
- Deflated Sharpe Ratio
- White’s Reality Check
- 新的保留樣本
- 更嚴格的 Walk-forward
- 更長期間的 Paper Trading

任何單一統計修正方法都不能替代完整的研究治理。

## 13. Overfitting Control

策略複雜度必須與樣本數、交易次數及經濟邏輯相稱。

必須特別警惕：

- 過多參數
- 過多條件分支
- 精確但缺乏經濟意義的門檻
- 只在單一參數點有效
- 只在單一年份有效
- 只靠少數股票有效
- In-Sample 與 OOS 差距過大
- 規則針對特定歷史事件事後設計
- 多次版本修改但未保留失敗紀錄

參數稍微改變就完全失效的策略，不應被視為穩健。

## 14. Transaction Feasibility

回測不得假設所有訊號都能以理想價格立即成交。

依策略性質，必須處理：

- 券商手續費
- 證券交易稅
- 手續費折扣假設
- Bid-ask spread
- Slippage
- Market impact
- 最低交易單位
- 整張與零股假設
- 現金限制
- 買進日漲停
- 賣出日跌停
- 停牌
- 零成交量
- 無有效報價
- 延遲成交
- 未成交訂單
- 下市持股處理

交易成本必須以買進與賣出方向分別處理，並與當時適用市場規則一致。

若無法可靠重建特定交易限制，必須採取保守假設並進行敏感度測試。

## 15. Liquidity and Capacity

流動性門檻不得只用現在的成交狀況回推歷史。

至少應使用當時可得的價格與成交量資料，評估：

- Average daily traded value
- Effective trading days
- Position size relative to liquidity
- Turnover
- Estimated market impact
- Failed-order probability

策略若只在極低流動性股票中有效，必須明確揭露容量限制，且不得以未限制資金規模的回測報酬宣稱可實際複製。

## 16. Fair Benchmarking

每個策略必須在測試前定義主要 Benchmark。

Benchmark 應考慮：

- 市場範圍
- 上市或上櫃比重
- Large-cap 或 small-cap 暴露
- 產業分布
- 股息與 Total Return
- 幣別
- 投資期間
- 現金部位
- 風險暴露

依策略性質，可使用：

- 臺灣加權股價報酬指數
- 櫃買市場報酬指數
- 同 Universe Equal-weight Benchmark
- Size-matched Benchmark
- Industry-matched Benchmark
- Cash or risk-free proxy

不得在結果出現後任意更換較容易勝過的 Benchmark。

## 17. Performance Evaluation

不得只報告 Total Return 或 CAGR。

正式結果至少應視策略性質涵蓋：

- Total Return
- CAGR
- Annualized Volatility
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Calmar Ratio
- Hit Rate
- Profit Factor
- Average Gain and Loss
- Turnover
- Exposure
- Time in Market
- Number of Trades
- Holding Period Distribution
- Tail Loss
- Benchmark Excess Return
- Tracking Error
- Information Ratio
- Transaction-cost-adjusted Return

必須同時揭露：

- 成本前結果
- 成本後結果
- 相對 Benchmark 結果
- In-Sample 與 OOS 結果
- 主要限制

## 18. Robustness Requirements

策略不得只在單一設定下被驗證。

正式穩健性測試至少應依策略性質包含：

- 相鄰參數區域
- 不同持股數
- 不同流動性門檻
- 不同成本假設
- 不同滑價假設
- 不同再平衡日
- 不同持有期間
- 不同市場 Regime
- 排除極端年份
- 排除最大貢獻股票
- 排除前五大貢獻股票
- 產業集中度限制
- Equal-weight 與替代權重方法

穩健性不代表所有測試都必須獲利，而是核心現象應在合理變動下仍可解釋，且不依賴單一偶然條件。

## 19. Concentration and Attribution

正式研究必須檢查：

- 單一股票最大權重
- 前五大持股集中度
- 單一產業集中度
- 單一年度報酬貢獻
- 單一股票總報酬貢獻
- 市值暴露
- 動能、價值、品質與流動性暴露

若總績效主要由少數股票或單一產業產生，報告不得將其描述為普遍存在的選股能力。

## 20. Reproducibility

每次正式實驗至少必須保存：

- Experiment ID
- Strategy ID
- Strategy Version
- Config Version
- Dataset Version
- Feature Version
- Code Commit SHA
- Runtime Environment
- Dependency Versions
- Run Timestamp
- Parameters
- Random Seed, if applicable
- Output Artifact Location
- Warning and Error Logs
- Result Summary
- Decision Status

相同版本與相同輸入應產生一致結果，或落在事前定義的數值容忍範圍內。

無法重現的高績效結果不得 Promote。

## 21. Experiment Registry

所有重要實驗都必須進入 Experiment Registry。

不得只記錄：

- 成功結果
- 最佳參數
- 最終版本

還必須保存：

- 失敗結果
- 被否證的版本
- 資料錯誤造成的無效結果
- 被 Retest 的結果
- 被 Retire 的策略
- 規格與實作不一致的實驗

Experiment Registry 的欄位與狀態由正式 Schema 文件另行定義。

## 22. Decision Snapshot

每一個重要策略決策點應保存 Decision Snapshot，以回答：

- 當時使用哪一個 Strategy Version？
- 當時有哪些資料可用？
- 當時的 Universe 是什麼？
- 哪些股票通過 Eligibility 與 Tradability Mask？
- 訊號與排名是多少？
- 風險旗標是什麼？
- 建議組合如何形成？
- 後續發生什麼結果？

Decision Snapshot 的目的不是事後合理化，而是保存當時決策環境。

## 23. Acceptance and Rejection Gates

每個策略必須在正式測試前定義 Gates。

Gates 不得只包含報酬率，至少應考慮：

- 成本後報酬
- 相對 Benchmark 表現
- 最大回撤
- 風險調整後報酬
- OOS 表現
- 參數敏感度
- Regime Dependence
- 交易可行性
- 產業與個股集中度
- PIT 完整性
- 可重現性

不得在看到結果後降低原 Gates，卻仍聲稱策略通過原標準。

若 Gates 本身需要修改，必須建立新版本並說明原因。

## 24. Validation Decisions

策略驗證與審計最終只能作出：

- Promote
- Revise
- Retest
- Retire

### Promote

只代表進入下一個研究階段，不代表可直接投入真實資金。

### Revise

代表核心假設或正式規格需要修改，必須退回研究或規格工作模式。

### Retest

代表假設可暫時保留，但資料、工程、測試或證據不足，必須回到適當驗證階段。

### Retire

代表目前證據不足以支持繼續投入研究成本，或策略存在不可接受的缺陷。

所有決策都必須寫入正式紀錄，不能只保留在對話中。

## 25. Paper Trading

Paper Trading 不是形式上的等待期，而是用即時或當下可得資料驗證：

- 資料是否準時到達
- PIT 規則是否可執行
- 訊號是否按規格生成
- Universe 是否正確
- 訂單是否可以形成
- 實際可成交性
- 滑價與未成交狀況
- 系統錯誤與人工介入
- Decision Snapshot 是否完整

通過 Paper Trading 仍不等於未來報酬保證，也不等於自動核准真實交易。

## 26. Research Reporting Language

允許：

> 本策略在指定歷史樣本、資料版本與成本假設下呈現正向風險調整後績效，但樣本外證據仍不足。

不允許：

> 這個策略穩賺。

允許：

> 目前結果支持進入下一階段測試。

不允許：

> 回測成功，所以可以買進。

允許：

> 報酬主要由少數股票貢獻，現有證據不足以支持廣泛有效性。

不允許：

> 報酬很好，所以策略有效。

## 27. Prohibited Research Practices

TWStock 禁止：

- 使用未來資料
- 使用今日存續公司清單回推歷史
- 刪除下市或失敗公司以改善結果
- 看過 OOS 後仍將其視為未見樣本
- 只保存成功實驗
- 隱藏人工篩選
- 事後更換 Benchmark
- 事後降低 Acceptance Gates
- 用最新修訂資料覆蓋歷史當時值
- 忽略交易成本與不可成交狀況
- 用單次回測宣稱策略有效
- 把書籍、名人或市場慣例當作驗證證據
- 讓工程實作自行改變投資規則
- 在沒有版本紀錄下修改資料、設定或程式
- 將研究結果包裝成保證獲利或明牌

## 28. Exceptions

任何偏離本文件的例外都必須：

1. 明確記錄。
2. 說明必要性。
3. 說明可能造成的偏誤。
4. 限定適用範圍。
5. 指定到期或重新審查條件。
6. 不得用例外結果直接支持 Promote。

例外不得成為長期隱藏預設。

## 29. Revision Policy

本文件是系統級研究基準。

以下變更需要建立新版本並透過 Pull Request 審查：

- 研究證據標準改變
- PIT 原則改變
- OOS 定義改變
- Benchmark 原則改變
- 交易成本原則改變
- Experiment 保存原則改變
- Validation Decisions 改變
- 文件優先層級改變

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Required Retest Scope

## 30. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/data/POINT_IN_TIME_POLICY.md`
2. `docs/research/STRATEGY_LIFECYCLE.md`
3. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
4. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
5. `docs/research/VALIDATION_PROTOCOL.md`

在 Point-in-Time Policy 與 Strategy Lifecycle 完成以前，不應開始大量策略工程實作。