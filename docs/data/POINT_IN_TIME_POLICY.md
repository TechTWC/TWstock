# TWStock Point-in-Time Policy

- Document ID: `TWSTOCK-DATA-PIT-001`
- Version: `1.0.0`
- Status: Baseline
- Effective date: `2026-07-10`
- Scope: All TWStock historical data, Universe construction, feature calculation, signal formation, backtesting, validation, paper trading, and Decision Snapshots

## 1. Purpose

本文件定義 TWStock 如何判斷一筆資料在某個歷史時點是否已經可以被研究系統使用。

核心原則是：

> 歷史模擬只能使用當時已公開、合理可取得、已完成必要處理，且依策略規格允許使用的資料版本。

Point-in-Time，以下簡稱 PIT，不只是避免「偷看未來價格」。它同時涵蓋：

- 公告時間
- 資料來源實際公開時間
- 資料供應商延遲
- 系統可用時間
- 收盤前後差異
- 修訂值與重編值
- 上市、下市、停牌及轉板狀態
- 歷史產業分類與指數成分
- Rolling feature 的資料視窗
- 訊號形成時間
- 可執行交易時間
- Benchmark 的歷史可得性

任何不符合本文件的回測結果，即使報酬率很高，也不得升級為可信研究證據。

## 2. Authority and Relationship to Other Documents

本文件受以下正式文件約束：

1. `docs/vision/SYSTEM_VISION.md`
2. `docs/vision/RESEARCH_PRINCIPLES.md`

本文件優先於：

- 個別策略 YAML 中未經核准的時間預設值
- 工程實作中的方便性預設
- Backtest output 中推導出的時間假設
- ChatGPT 對話、臨時筆記及 Handoff Baton

若策略規格、YAML、Data Contract 或程式行為與本文件衝突：

1. 受影響的實驗必須停止升級。
2. 衝突必須被記錄。
3. 不得由工程角色自行選擇較有利的時間規則。
4. 必須由「02｜台股研究規格轉譯」或正式政策修訂決定處理方式。
5. 修正後必須建立新資料版本、設定版本或實驗紀錄。

## 3. Scope

本政策適用於：

- 股票價格與成交量
- 月營收
- 財務報表
- 公司行動
- 股本與流通股數
- 上市櫃及交易狀態
- 產業分類
- 指數成分及 Benchmark
- 法人、籌碼及持股資料
- 估值資料
- 分析師預估及修正資料
- 事件資料
- 衍生特徵
- Universe 與 Tradability Mask
- Backtest execution
- Paper Trading
- Decision Snapshot

若未來新增新聞、社群、替代資料、逐筆行情或其他資料類型，必須先建立對應 Data Contract 與 PIT 規則，不能直接沿用不適用的預設值。

## 4. Core Time Model

TWStock 對重要資料不得只使用單一模糊的 `date` 欄位。

依資料性質，至少應區分下列時間概念。

### 4.1 Observation Period

資料所描述的經濟或市場期間。

例如：

- 2026 年 6 月月營收
- 2026 年第二季 EPS
- 2026-07-10 的日成交量

Observation Period 不代表資料已經公開。

### 4.2 Event Time

事件在真實世界中發生或生效的時間。

例如：

- 公司行動生效日
- 股票開始停牌時間
- 指數成分調整生效時間

### 4.3 Published At

原始來源正式公開該筆資料的時間。

可能是：

- 主管機關公告時間
- 交易所公開時間
- 公司正式發布時間
- 資料供應商標示的發布時間

### 4.4 Vendor Available At

資料供應商、API 或下載來源實際提供該筆資料的時間。

若沒有使用外部資料供應商，該欄位可為 `null`，但不得虛構。

### 4.5 Research Available At

在歷史模擬中，TWStock 允許研究程序首次使用該筆資料的最早時間。

`research_available_at` 必須：

- 不早於 `published_at`
- 不早於已知的 `vendor_available_at`
- 納入必要的資料取得、正規化及品質檢查延遲
- 遵守公告時間精度與保守回退規則

### 4.6 Ingested At

TWStock 實際把該版本資料寫入系統的時間。

歷史回補資料的 `ingested_at` 可能遠晚於 `research_available_at`。兩者不得混為一談。

### 4.7 Recorded At

系統建立或保存該資料版本紀錄的時間，用於稽核與資料版本追蹤。

### 4.8 Signal Formation At

策略根據當時可用資料完成篩選、特徵、排名與組合建議的時間。

### 4.9 Execution At

回測或紙上交易假設訂單能被送出並開始成交的時間。

### 4.10 Superseded At

該資料版本被後續修訂值或新版本取代的時間。

舊版本不得被刪除；它仍可能是更早歷史時點的正確可見版本。

## 5. Mandatory Temporal Ordering

對具有正式發布事件的資料，原則上必須滿足：

```text
observation_period_end
≤ published_at
≤ research_available_at
≤ signal_formation_at
≤ execution_at
```

`ingested_at` 是實際系統載入時間，不能用來替代歷史可得性判定。

若某資料來源在公告前提供預估值，該預估值必須視為不同資料類型與不同版本，不能冒充正式公告值。

## 6. Canonical Time Zone and Timestamp Format

### 6.1 Canonical Time Zone

台股資料與交易規則的主要時區為：

```text
Asia/Taipei
```

所有含時間的欄位必須：

- 保存帶時區的 timestamp；或
- 保存 UTC timestamp，並保留原始時區資訊。

不得使用沒有時區且無法判定來源時區的 naive timestamp 作為正式 PIT 判斷依據。

### 6.2 Storage Format

建議使用 ISO 8601 格式，例如：

```text
2026-07-10T15:30:00+08:00
```

### 6.3 Date-only Values

若來源只提供日期、沒有時間：

- 不得假設為當日 00:00。
- 必須記錄時間精度為 `date_only`。
- 必須套用資料類型對應的保守可用時間規則。

### 6.4 Timestamp Precision

每筆資料應盡可能記錄：

- `timestamp_precision`: `second` / `minute` / `hour` / `date_only` / `unknown`
- `timestamp_source`
- `timestamp_confidence`: `verified` / `derived` / `conservative` / `unknown`

## 7. Exchange Calendar and Trading Sessions

TWStock 不得只用星期一到星期五推導交易日。

必須使用版本化的交易日曆，處理：

- 例假日
- 補假或特殊休市
- 颱風或臨時休市
- 特殊交易安排
- 市場別差異
- 交易制度變更

每個交易日應能識別：

- `session_date`
- `market`
- `session_open_at`
- `session_close_at`
- 是否正常交易
- 是否提早收盤
- 是否臨時休市
- 日曆版本

策略規格不得把固定時鐘時間當作永久不變的市場事實。實作應查詢正式交易日曆資料。

## 8. Market Data Without Announcement Events

價格、成交量及指數行情通常沒有公司公告事件。

這類資料不得強行填入虛假的 `published_at`。

### 8.1 Daily Open

當日開盤價只有在開盤成交發生後才存在。

使用當日開盤價作為訊號輸入時，不得同時假設以同一開盤價無摩擦成交，除非策略明確採用可重現的盤中資料與延遲模型。

### 8.2 Daily High, Low, Close, and Volume

完整的當日最高價、最低價、收盤價與成交量，原則上只有在該交易時段結束後才可用。

因此：

- 使用完整當日日資料形成訊號時，最早執行時間原則上是下一個可交易時點。
- 不得用當日完整成交量決定當日開盤前的股票資格。
- 不得用當日收盤價形成訊號後，再假設以同一收盤價成交。

### 8.3 Adjusted Prices

還原價格或調整後價格可能使用後續公司行動資訊。

正式回測必須：

- 說明調整方法
- 保存原始價格
- 保存公司行動資料版本
- 確保調整方法不會把未來事件資訊注入早期訊號

調整後價格可以用於報酬計算，但不得不加區分地用於模擬當時可交易價格。

### 8.4 Intraday Data

若未來使用盤中資料，必須另外定義：

- bar timestamp 的開始或結束語意
- 資料延遲
- 訊號計算延遲
- 下單延遲
- 撮合與滑價模型
- 當時可見的 order book 範圍

日資料回測不得假裝具有盤中精度。

## 9. Announcement-based Data

對月營收、財報、重大訊息及其他公告資料，至少應保存：

- `observation_period_start`
- `observation_period_end`
- `published_at`
- `research_available_at`
- `source_id`
- `source_document_id` 或可追蹤識別碼
- `version_id`
- `revision_number`
- `supersedes_version_id`
- `timestamp_precision`
- `timestamp_confidence`

### 9.1 Before Market Open

若公告在當日市場開盤前已經公開，且資料來源、時間精度與處理延遲均可證明，策略規格可以允許在當日較晚的可交易時點使用。

不得自動假設能以開盤價成交。

### 9.2 During Trading Session

盤中公告只有在公告時間之後才可用。

使用盤中公告的策略必須具備：

- 足夠時間精度
- 盤中市場資料
- 合理訊號與下單延遲
- 可重現的成交模型

若上述條件不足，應延後到下一個交易時段處理。

### 9.3 After Market Close

收盤後公告不得用於當日收盤成交。

原則上最早只能在下一個可交易時點使用，並仍需遵守策略定義的資料處理延遲。

### 9.4 Date-only Announcement

若只知道公告日期，不知道時間：

- 不得假設為開盤前公告。
- 預設 `research_available_at` 應落在下一個交易日的策略允許時點。
- 若採用更保守延遲，應由 Data Contract 明確定義。

## 10. Research Availability Derivation

`research_available_at` 必須能說明如何推導。

建議保存：

- `availability_method`
- `availability_rule_version`
- `availability_delay_seconds`
- `availability_reason`

常見方法包括：

### 10.1 Verified Timestamp

來源有可信且可追蹤的正式時間戳。

### 10.2 Vendor Timestamp

使用資料供應商明確提供的可得時間，且資料授權與歷史涵蓋允許研究使用。

### 10.3 Conservative Date-only Rule

來源只有日期，依本文件延後到下一個交易時點。

### 10.4 Batch Publication Rule

來源以批次形式公開。必須使用該批次實際可得時間或保守延遲，不得用資料內部的觀察日期當作可用時間。

### 10.5 Unknown Availability

若無法合理重建資料可得時間：

- 該欄位不得被標記為 PIT-verified。
- 受影響實驗必須標記為 `Provisional` 或 `Invalid`。
- 不得用該結果支持 Promote。

## 11. Historical Backfill

歷史資料通常是在今日批次取得，但回測需要重建當時可得性。

因此必須同時保留：

- `research_available_at`: 歷史當時最早合理可用時間
- `ingested_at`: 今日實際寫入 TWStock 的時間

不得把今日 `ingested_at` 改寫成歷史日期。

歷史可得時間的重建方法必須：

- 有來源依據
- 有規則版本
- 有信心等級
- 可被審計
- 對不確定性採保守處理

## 12. Revisions, Restatements, and Corrections

同一觀察期間可能有多個公開版本。

每個版本必須保存：

- 原始值
- 版本識別碼
- 發布時間
- 可用時間
- 修訂原因，如可取得
- 被哪個版本取代
- 取代時間

As-of 查詢必須回傳在指定歷史時點當時可見的版本，而不是最新版本。

### 12.1 Original Release

原始公告版本在其 `research_available_at` 之後才可使用。

### 12.2 Later Correction

修正值只能從修正版本的 `research_available_at` 起生效。

### 12.3 Restated Financial Statements

後續重編財報不得覆蓋歷史當時使用的原始版本。

研究若使用「最新重編後資料」進行純橫斷面分析，必須明確標記為非 PIT 回測，不得與 PIT 回測混用。

### 12.4 Silent Vendor Replacement

若資料供應商只提供最新值、無法保存歷史版本：

- 資料集必須標記 revision risk。
- 回測不得被標記為 PIT-verified。
- 必須進行偏誤評估或尋找可保存版本的來源。

## 13. Monthly Revenue

月營收資料至少必須區分：

- 營收所屬月份
- 公司正式公告時間
- TWStock 研究可用時間
- 原始公告值
- 後續修正值

不得：

- 在公告前使用營收值
- 只依「所屬月份月底」判定可用
- 用後續修正值回填原訊號
- 將同一天全部公告公司假設為同一時間可得，除非來源證明如此

若來源只有公告日期，預設採下一個交易日可用的保守規則。

## 14. Financial Statements

財報資料至少應保存：

- 財報期間
- 報表類型
- 合併或個別
- 公告時間
- 版本
- 重編狀態
- 研究可用時間

不得以財報期間結束日作為資料可用日。

TTM、YoY、QoQ、ROE、ROIC、EPS growth 等衍生特徵，只能使用 `research_available_at` 不晚於訊號時間的財報版本。

若同一公司不同報表欄位在不同時間更新，系統不得假設整份報表在最早欄位到達時已完整可用。

## 15. Corporate Actions

公司行動應至少保存：

- 宣告時間
- 除權息或生效時間
- 實際交易影響日
- 已知日與生效日的區別
- 現金或股票調整內容
- 版本與修正

回測中：

- 交易價格應使用當時市場實際可成交價格。
- 報酬與持股數調整應根據公司行動規則處理。
- 不得用未來才公告的公司行動改變更早的交易訊號。

## 16. Security Master and Historical Universe

歷史 Universe 必須依歷史時點重建，不得使用今日證券清單回推。

每檔證券至少應能追蹤：

- 永久 security identifier
- 歷史股票代號
- 歷史公司名稱
- 市場別
- 上市日
- 下市日
- 轉板日
- 停牌期間
- 恢復交易時間
- 特殊交易狀態期間
- 合併、收購或消滅事件
- 證券類型

### 16.1 Effective Interval

狀態資料應以有效區間保存，例如：

```text
valid_from <= as_of_time < valid_to
```

### 16.2 Knowledge Interval

若狀態事後才被公開或修正，還必須保存何時被市場知道。

### 16.3 Delisted Securities

下市股票不得從歷史資料集中刪除。

持有中的下市股票必須依正式 Backtest Contract 處理，不得永久沿用最後價格製造虛假資產價值。

### 16.4 Initial Public Offering

新上市股票只有在正式可交易後，且滿足策略定義的最短歷史與流動性要求時，才能進入 Universe。

## 17. Trading Status and Tradability Mask

Tradability Mask 必須使用訊號或執行時點當時已知的資訊。

可能包含：

- 是否有有效交易時段
- 是否停牌
- 是否無成交
- 是否漲跌停且無法成交
- 是否處於特殊交易狀態
- 是否有足夠歷史流動性
- 是否有有效價格
- 是否符合最低交易單位

不得用執行日收盤後才知道的完整成交狀況，決定執行日開盤前是否可交易。

## 18. Industry Classification

產業分類可能隨時間改變。

正式研究必須：

- 保存分類體系名稱與版本
- 保存分類有效期間
- 保存何時公開或可得
- 避免用今日分類回推全部歷史

若無可靠歷史分類：

- 必須揭露限制
- 產業中性化或產業上限結果應標記 Provisional
- 不得假裝分類完全 PIT-correct

## 19. Index Constituents and Benchmarks

指數成分資料必須區分：

- 公告時間
- 生效時間
- 成分版本
- 權重生效時間

不得使用今日指數成分回推歷史 Benchmark 或 Universe。

Benchmark 回報資料也必須符合：

- 正確交易日曆
- 正確 Total Return 或 Price Return 定義
- 正確股息處理
- 正確資料可得時間

## 20. Ownership, Institutional, and Position Data

法人買賣、持股、融資融券及其他籌碼資料，必須明確定義：

- 所屬交易日或統計期間
- 官方或供應商發布時間
- 研究可用時間
- 修訂與回補規則

不得只因資料標記為某交易日，就假設當日開盤前已可取得。

## 21. Estimates and Analyst Revisions

分析師預估、共識值及目標價是版本化資料。

至少應保存：

- estimate_as_of
- vendor_available_at
- research_available_at
- contributor universe，如可取得
- estimate horizon
- currency and unit
- revision version

不得使用今日最新共識值回填歷史日期。

若資料供應商無法提供歷史快照，該資料不得用於聲稱 PIT-correct 的歷史回測。

## 22. Derived Features

所有衍生特徵都必須具有：

- feature name
- feature version
- input dataset versions
- calculation timestamp
- as-of timestamp
- lookback window
- missing-value rule
- normalization rule
- winsorization rule

### 22.1 Rolling Windows

Rolling feature 只能使用 as-of 時點以前已可用的資料。

不得：

- 使用 centered window
- 使用未來值補前期缺值
- 使用全期間均值與標準差標準化早期資料
- 使用完整樣本分位數決定歷史門檻，除非明確標記為非 PIT 探索

### 22.2 Cross-sectional Features

橫斷面排名只能使用該 as-of 時點符合 Universe 且資料可用的股票。

不得用後來才上市或當時資料尚未公告的股票參與歷史排名。

### 22.3 Forward-looking Labels

未來報酬可以作為研究標籤，但必須與當期特徵嚴格分離，不能進入訊號計算或資料正規化。

## 23. Signal Formation Rules

每個正式策略必須明確定義：

- data cutoff time
- signal formation time
- ranking time
- portfolio construction time
- execution time
- failed-order handling

### 23.1 Daily Strategy Default

若策略使用完整日資料或收盤後公告資料，預設流程為：

```text
Data becomes available
→ Signal forms after availability
→ Execution begins at the next strategy-permitted tradable time
```

### 23.2 Same-bar Execution Prohibition

除非有經核准的盤中資料與成交模型，不得：

- 用當日收盤價形成訊號並以同一收盤價成交
- 用完整當日成交量決定當日成交資格
- 用當日最高價或最低價觸發後假設以該極值成交

### 23.3 Deterministic Cutoff

相同資料版本、交易日曆與策略設定，Signal Formation 必須可重現。

## 24. Execution Timing

Execution 模型至少應定義：

- execution session
- price field or pricing rule
- order delay
- unfilled-order policy
- limit-up and limit-down handling
- suspension handling
- missing-price handling
- transaction cost timing

PIT 正確不等於成交可行。策略仍必須通過交易模擬與流動性檢查。

## 25. As-of Query Contract

所有 PIT-sensitive 資料介面應支援明確的 as-of 查詢。

概念介面：

```text
get_records(
  dataset_id,
  as_of_time,
  observation_filter,
  version_policy="latest_known_as_of"
)
```

回傳資料必須滿足：

```text
research_available_at <= as_of_time
and
superseded_at is null or superseded_at > as_of_time
```

對有效區間資料，還必須滿足：

```text
valid_from <= target_time
and
valid_to is null or target_time < valid_to
```

不得以 SQL 中簡單選取最新紀錄，取代 as-of 版本判定。

## 26. Minimum PIT Data Contract

所有 PIT-sensitive dataset 至少應考慮下列欄位：

| Field | Requirement | Purpose |
|---|---|---|
| `dataset_id` | Required | 資料集識別 |
| `dataset_version` | Required | 資料版本 |
| `record_id` | Required | 紀錄識別 |
| `security_id` | When applicable | 永久證券識別 |
| `observation_start` | When applicable | 觀察期間開始 |
| `observation_end` | When applicable | 觀察期間結束 |
| `event_at` | When applicable | 事件發生或生效時間 |
| `published_at` | Announcement data | 原始公開時間 |
| `vendor_available_at` | When applicable | 供應商可得時間 |
| `research_available_at` | Required for PIT | 研究最早可用時間 |
| `ingested_at` | Required | 系統實際載入時間 |
| `recorded_at` | Required | 系統版本紀錄時間 |
| `valid_from` | State data | 真實狀態生效開始 |
| `valid_to` | State data | 真實狀態生效結束 |
| `revision_number` | Versioned data | 修訂序號 |
| `supersedes_record_id` | When applicable | 被取代版本 |
| `superseded_at` | When applicable | 版本失效時間 |
| `timestamp_precision` | Required | 時間精度 |
| `timestamp_confidence` | Required | 時間可信度 |
| `availability_method` | Required | 可用時間推導方式 |
| `source_id` | Required | 資料來源 |
| `source_record_id` | When available | 原始來源識別 |
| `lineage_hash` | Recommended | 來源與轉換追蹤 |

個別 Data Contract 可以增加欄位，但不得刪除必要的 PIT 語意。

## 27. Missing or Uncertain Timestamps

### 27.1 Missing Time, Known Date

使用 date-only 保守規則，不得假設為開盤前。

### 27.2 Missing Published Date

若連正式公開日期都無法確認：

- 該資料不得被視為 PIT-verified。
- 原則上不得用於正式策略升級證據。

### 27.3 Conflicting Sources

若多個來源的公告時間不一致：

- 保存各來源證據
- 採用可解釋的保守時間
- 標記衝突
- 進行人工審查

不得選擇最早時間只為增加可交易機會。

### 27.4 Imputed Availability

任何推估的可用時間都必須：

- 標記 `derived` 或 `conservative`
- 保存推估規則版本
- 允許敏感度測試
- 不得偽裝為 verified timestamp

## 28. Data Quality Status for PIT

每個正式資料集應被標記為下列之一：

### PIT-Verified

關鍵時間欄位與版本歷史有足夠證據，可用於正式驗證。

### PIT-Provisional

時間規則大致可重建，但仍有重大缺口或部分推估。

可用於探索與 Retest，不得單獨支持 Promote。

### PIT-Restricted

只有部分期間、部分證券或部分欄位符合 PIT。

必須限制研究範圍。

### PIT-Invalid

存在不可接受的未來資料、版本覆蓋或時間不可辨識問題。

不得用於正式回測結論。

## 29. Required Leakage Tests

涉及 PIT 的工程與策略至少應依適用性執行以下測試。

### Test 1: Future Availability Exclusion

Given：資料的 `research_available_at` 晚於 as-of time。

Expected：資料不得出現在查詢、特徵或訊號中。

### Test 2: Post-close Announcement

Given：公告發生於交易時段結束後。

Expected：不得用於同日收盤成交。

### Test 3: Date-only Announcement

Given：來源只有公告日期。

Expected：套用下一交易時點或更保守規則，不得假設當日開盤前可用。

### Test 4: Restatement Isolation

Given：財報後續重編。

Expected：早期 as-of 查詢仍回傳當時版本，不得回傳最新重編值。

### Test 5: Historical Universe

Given：股票在歷史當時尚未上市或已下市。

Expected：Universe 依當時狀態正確納入或排除。

### Test 6: Delisted Security Preservation

Given：股票目前已不存在。

Expected：其歷史資料與持倉處理仍保留。

### Test 7: Rolling Window Boundary

Given：Rolling feature 的下一期資料已存在於資料庫。

Expected：當期計算不得使用未來值。

### Test 8: Full-period Normalization Leakage

Given：資料集包含完整歷史期間。

Expected：早期特徵不得使用未來期間計算的平均數、標準差或分位數。

### Test 9: Same-close Execution

Given：訊號使用當日完整收盤資料。

Expected：不得假設以同一收盤價成交。

### Test 10: Revision Supersession

Given：同一觀察期間存在多個版本。

Expected：不同 as-of time 回傳對應的當時最新可見版本。

### Test 11: Market Calendar Exception

Given：工作日因特殊原因休市。

Expected：不得產生交易或錯誤推進到虛構交易日。

### Test 12: Timestamp Conflict

Given：兩來源時間戳衝突。

Expected：系統標記衝突並採保守或阻擋處理，不得靜默選擇。

每個測試必須包含：

- Given
- When
- Expected
- Failure Meaning
- Affected Research Scope

## 30. Reproducibility and Audit Trail

每次正式實驗必須保存：

- PIT policy version
- Dataset version
- Availability rule version
- Exchange calendar version
- Strategy version
- Config version
- Feature version
- Code commit SHA
- Experiment ID
- Run timestamp
- As-of cutoff rules
- Warning and error logs

相同版本與輸入應產生相同 as-of 資料集合。

若資料供應商後續改寫歷史資料，TWStock 必須能透過資料快照、版本或雜湊辨識差異。

## 31. Decision Snapshot Requirements

每個重要 Decision Snapshot 至少應保存：

- snapshot timestamp
- data cutoff timestamp
- PIT policy version
- dataset versions
- availability rule versions
- exchange calendar version
- Universe as of timestamp
- input records or reproducible references
- signal formation timestamp
- proposed execution timestamp
- timestamp warnings
- PIT quality status

Decision Snapshot 必須能回答：

> 在該時點，哪些資料已經可用？哪些尚未可用？為什麼？

## 32. Paper Trading

Paper Trading 應使用真實資料到達流程，而不是回測式重播未來已知資料。

必須記錄：

- 原始資料到達時間
- 正規化完成時間
- 訊號形成時間
- 訂單形成時間
- 實際延遲
- 資料中斷
- 遲到資料
- 修訂資料
- 人工介入

Paper Trading 可以驗證歷史假設的操作可行性，但仍不代表策略未來獲利。

## 33. Prohibited Practices

TWStock 禁止：

- 用 observation date 取代 published time
- 把 date-only 公告視為當日開盤前可用
- 用收盤後公告在同日收盤成交
- 用完整當日日資料在當日開盤交易
- 用最新修訂值覆蓋歷史版本
- 用今日股票清單回推歷史 Universe
- 刪除已下市或失敗公司
- 用今日產業分類回填全部歷史
- 用今日指數成分回填歷史 Benchmark
- 使用 centered rolling window
- 用全樣本統計量標準化早期資料
- 將 `ingested_at` 偽造成歷史可用時間
- 在時間來源衝突時選擇最有利的時間
- 以未知時間資料聲稱 PIT-verified
- 讓工程實作自行縮短資料延遲
- 靜默忽略時間欄位錯誤

## 34. Exceptions

任何偏離本政策的例外都必須：

1. 明確記錄。
2. 說明原因。
3. 指定適用資料集、欄位、期間與策略。
4. 評估可能偏誤方向。
5. 設定到期或重審條件。
6. 標記受影響實驗為 Provisional。
7. 不得用例外結果直接支持 Promote。

例外不得成為長期隱藏預設。

## 35. Engineering Acceptance Criteria

PIT 基礎實作至少必須達成：

- [ ] 所有 PIT-sensitive records 具有 `research_available_at` 或明確阻擋狀態。
- [ ] 歷史回補的 `ingested_at` 與 `research_available_at` 分開保存。
- [ ] As-of 查詢不會回傳未來才可得的資料。
- [ ] 修訂值不會覆蓋早期歷史可見版本。
- [ ] 日資料訊號無法以同一收盤價成交，除非策略有核准例外。
- [ ] Date-only 公告套用保守規則。
- [ ] 交易日曆可以處理特殊休市。
- [ ] 歷史 Universe 包含下市及已不存在證券。
- [ ] 時間來源、精度、可信度及推導方法可追蹤。
- [ ] Leakage Tests 自動化並在失敗時阻擋研究升級。
- [ ] Experiment Registry 保存 PIT policy 與 availability rule version。
- [ ] Decision Snapshot 能重建當時可見資料。

## 36. Research Reporting Requirements

正式研究報告必須揭露：

- PIT policy version
- PIT quality status
- 資料來源及時間精度
- 公告時間缺口
- 使用的保守延遲
- 修訂值處理方式
- Universe 歷史完整性
- 是否通過 Leakage Tests
- 已知限制及可能偏誤方向

允許：

> 本次回測使用 PIT-Provisional 月營收公告日期，公告時間缺失時延後至下一交易日，因此結果可供探索，但不足以支持 Promote。

不允許：

> 資料日期看起來正確，所以沒有未來函數。

## 37. Revision Policy

以下變更需要建立新版本並透過 Pull Request 審查：

- 核心時間欄位定義改變
- `research_available_at` 推導原則改變
- Date-only 保守規則改變
- 市場資料可用時間改變
- 收盤與執行規則改變
- 修訂值處理改變
- Historical Universe 規則改變
- As-of query contract 改變
- PIT quality status 定義改變
- Leakage Test 要求改變

版本變更必須記錄：

- Previous Version
- New Version
- Change Summary
- Change Reason
- Expected Impact
- Affected Datasets
- Required Retest Scope

## 38. Next Documents

本文件確立後，下一批基準文件依序為：

1. `docs/research/STRATEGY_LIFECYCLE.md`
2. `docs/research/EXPERIMENT_REGISTRY_SCHEMA.md`
3. `docs/research/DECISION_SNAPSHOT_SCHEMA.md`
4. `docs/research/VALIDATION_PROTOCOL.md`
5. Dataset-specific Data Contracts

在 PIT Policy 與 Strategy Lifecycle 完成以前，不應開始大量策略工程實作。