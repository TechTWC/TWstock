from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence


DECISION_LOGIC_VERSION = "TW-DECISION-CHECKLIST-0.1"


@dataclass(frozen=True)
class DecisionInputs:
    investment_horizon_years: int
    has_emergency_fund: bool
    uses_borrowed_money: bool
    needs_cash_within_three_years: bool
    drawdown_tolerance_pct: int
    current_position_weight_pct: Decimal
    target_position_weight_pct: Decimal


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price_twd: Decimal
    pe_ttm: Decimal
    trailing_pe_percentile: Decimal
    price_vs_ma200_pct: Decimal | None
    latest_three_month_revenue_yoy_pct: Decimal | None
    latest_operating_margin_pct: Decimal | None
    forward_pe_status: str
    forward_pe_available: bool


@dataclass(frozen=True)
class DecisionResult:
    dca_action: str
    dca_multiplier: Decimal
    tactical_add_action: str
    decision_confidence: str
    fundamental_state: str
    valuation_state: str
    trend_state: str
    allocation_headroom_pct: Decimal
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise ValueError(f"{field} must be numeric: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    parsed = _decimal(value, field="optional value")
    return parsed


def market_snapshot_from_analysis(payload: dict[str, Any]) -> MarketSnapshot:
    quote = payload.get("quote")
    valuation = payload.get("current_valuation")
    technical = payload.get("technical_context")
    fundamental = payload.get("fundamental_context")
    forward = payload.get("historical_forward_pe")
    if not all(isinstance(item, dict) for item in (quote, valuation, technical, fundamental, forward)):
        raise ValueError("analysis payload is missing required decision-checklist sections")

    latest_quarter = fundamental.get("latest_quarter")
    if not isinstance(latest_quarter, dict):
        latest_quarter = {}
    forward_status = str(forward.get("status", "UNKNOWN"))
    return MarketSnapshot(
        symbol=str(payload.get("symbol", "UNKNOWN")),
        price_twd=_decimal(quote.get("price_twd"), field="quote.price_twd"),
        pe_ttm=_decimal(valuation.get("pe_ttm"), field="current_valuation.pe_ttm"),
        trailing_pe_percentile=_decimal(
            valuation.get("historical_trailing_pe_percentile"),
            field="current_valuation.historical_trailing_pe_percentile",
        ),
        price_vs_ma200_pct=_optional_decimal(technical.get("price_vs_ma200_pct")),
        latest_three_month_revenue_yoy_pct=_optional_decimal(
            fundamental.get("latest_3m_average_revenue_yoy_pct")
        ),
        latest_operating_margin_pct=_optional_decimal(
            latest_quarter.get("operating_margin_pct")
        ),
        forward_pe_status=forward_status,
        forward_pe_available=forward_status == "AVAILABLE",
    )


def valuation_multiplier(percentile: Decimal) -> Decimal:
    if percentile <= Decimal("25"):
        return Decimal("1.50")
    if percentile <= Decimal("60"):
        return Decimal("1.00")
    if percentile <= Decimal("80"):
        return Decimal("0.75")
    if percentile <= Decimal("90"):
        return Decimal("0.50")
    return Decimal("0.25")


def valuation_state(percentile: Decimal) -> str:
    if percentile <= Decimal("25"):
        return "LOW"
    if percentile <= Decimal("60"):
        return "FAIR"
    if percentile <= Decimal("80"):
        return "UPPER_MIDDLE"
    if percentile <= Decimal("90"):
        return "HIGH"
    return "EXTREME_HIGH"


def fundamental_state(market: MarketSnapshot) -> str:
    margin = market.latest_operating_margin_pct
    revenue = market.latest_three_month_revenue_yoy_pct
    if margin is None or revenue is None:
        return "DATA_REVIEW"
    if margin <= 0 or revenue <= Decimal("-10"):
        return "FAIL"
    if revenue < 0:
        return "WATCH"
    return "STRONG"


def trend_state(market: MarketSnapshot) -> str:
    if market.price_vs_ma200_pct is None:
        return "DATA_REVIEW"
    return "POSITIVE" if market.price_vs_ma200_pct >= 0 else "NEGATIVE"


def evaluate_decision(market: MarketSnapshot, inputs: DecisionInputs) -> DecisionResult:
    reasons: list[str] = []
    warnings: list[str] = []
    headroom = inputs.target_position_weight_pct - inputs.current_position_weight_pct
    fundamental = fundamental_state(market)
    valuation = valuation_state(market.trailing_pe_percentile)
    trend = trend_state(market)

    hard_blocks: list[str] = []
    if inputs.investment_horizon_years < 5:
        hard_blocks.append("投資期間低於五年")
    if not inputs.has_emergency_fund:
        hard_blocks.append("尚未建立緊急預備金")
    if inputs.uses_borrowed_money:
        hard_blocks.append("使用借款或融資資金")
    if inputs.needs_cash_within_three_years:
        hard_blocks.append("三年內可能需要動用這筆資金")
    if headroom <= 0:
        hard_blocks.append("目前部位已達或超過目標配置")
    if fundamental == "FAIL":
        hard_blocks.append("基本面檢核未通過")

    if hard_blocks:
        warnings.extend(hard_blocks)
        return DecisionResult(
            dca_action="PAUSE",
            dca_multiplier=Decimal("0"),
            tactical_add_action="NONE",
            decision_confidence="LOW",
            fundamental_state=fundamental,
            valuation_state=valuation,
            trend_state=trend,
            allocation_headroom_pct=headroom,
            reasons=("先處理資金用途、風險承受或配置問題，再評估進場。",),
            warnings=tuple(warnings),
        )

    multiplier = valuation_multiplier(market.trailing_pe_percentile)
    reasons.append(
        f"五年Trailing P/E百分位為{market.trailing_pe_percentile:.1f}%，基礎定期定額倍率為{multiplier:.2f}倍。"
    )

    if fundamental == "WATCH":
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("近期營收方向偏弱，定期定額倍率上限降至0.50倍。")
    elif fundamental == "DATA_REVIEW":
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("基本面資料不足，定期定額倍率保守降至0.50倍。")
    else:
        reasons.append("最新營業利益率與近三月營收方向通過基本面檢核。")

    if trend == "NEGATIVE":
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("價格低於MA200，策略加碼暫停，定期定額倍率上限為0.50倍。")
    elif trend == "DATA_REVIEW":
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("MA200資料不足，暫不允許策略加碼。")
    else:
        reasons.append("價格仍位於MA200之上，長期價格趨勢未破壞。")

    if inputs.drawdown_tolerance_pct < 20:
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("可承受回撤低於20%，投入倍率上限降至0.50倍。")

    if headroom < Decimal("2"):
        multiplier = min(multiplier, Decimal("0.50"))
        warnings.append("距離目標配置不足2個百分點，新增部位應保守。")

    if multiplier >= Decimal("1.25"):
        dca_action = "INCREASE"
    elif multiplier >= Decimal("0.75"):
        dca_action = "CONTINUE"
    elif multiplier > 0:
        dca_action = "REDUCE"
    else:
        dca_action = "PAUSE"

    tactical = "NONE"
    if (
        market.trailing_pe_percentile <= Decimal("30")
        and trend == "POSITIVE"
        and fundamental == "STRONG"
        and market.forward_pe_available
        and inputs.drawdown_tolerance_pct >= 30
        and headroom >= Decimal("5")
    ):
        tactical = "STRONG"
    elif (
        market.trailing_pe_percentile <= Decimal("60")
        and trend == "POSITIVE"
        and fundamental == "STRONG"
        and market.forward_pe_available
        and inputs.drawdown_tolerance_pct >= 25
        and headroom >= Decimal("3")
    ):
        tactical = "MODERATE"
    elif (
        market.trailing_pe_percentile <= Decimal("80")
        and trend == "POSITIVE"
        and fundamental == "STRONG"
        and inputs.drawdown_tolerance_pct >= 20
        and headroom > 0
    ):
        tactical = "SMALL"

    if not market.forward_pe_available:
        warnings.append(
            "歷史Forward P/E百分位尚不可用，策略加碼最高只能評為SMALL，不能評為MODERATE或STRONG。"
        )
        if tactical in {"MODERATE", "STRONG"}:
            tactical = "SMALL"

    confidence = "MEDIUM"
    if not market.forward_pe_available or fundamental == "DATA_REVIEW" or trend == "DATA_REVIEW":
        confidence = "MEDIUM_LOW"
    if market.forward_pe_available and fundamental == "STRONG" and trend == "POSITIVE":
        confidence = "MEDIUM_HIGH"

    reasons.append(f"目前部位距離目標配置尚有{headroom:.2f}個百分點。")
    if tactical == "SMALL":
        reasons.append("基本面與長期趨勢通過，但估值仍非低檔，因此只允許小額分批。")
    elif tactical == "NONE":
        reasons.append("目前估值、趨勢、證據或配置條件不足以支持額外策略加碼。")

    return DecisionResult(
        dca_action=dca_action,
        dca_multiplier=multiplier,
        tactical_add_action=tactical,
        decision_confidence=confidence,
        fundamental_state=fundamental,
        valuation_state=valuation,
        trend_state=trend,
        allocation_headroom_pct=headroom,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _read_analysis(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"analysis JSON not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("analysis JSON must contain an object")
    return payload


def _default_inputs() -> DecisionInputs:
    return DecisionInputs(
        investment_horizon_years=5,
        has_emergency_fund=True,
        uses_borrowed_money=False,
        needs_cash_within_three_years=False,
        drawdown_tolerance_pct=30,
        current_position_weight_pct=Decimal("0"),
        target_position_weight_pct=Decimal("10"),
    )


def write_decision_page(analysis: dict[str, Any], output_path: Path) -> DecisionResult:
    market = market_snapshot_from_analysis(analysis)
    defaults = _default_inputs()
    initial = evaluate_decision(market, defaults)
    market_json = json.dumps(_json_value(asdict(market)), ensure_ascii=False)
    thresholds_json = json.dumps(
        {
            "logic_version": DECISION_LOGIC_VERSION,
            "valuation_bands": [25, 60, 80, 90],
            "dca_multipliers": [1.5, 1.0, 0.75, 0.5, 0.25],
            "minimum_long_term_years": 5,
            "minimum_tactical_drawdown_tolerance": 20,
        },
        ensure_ascii=False,
    )
    initial_json = json.dumps(_json_value(asdict(initial)), ensure_ascii=False)

    template = r'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>2330 定期定額與加碼檢核</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#111827;background:#f3f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:24px 18px 60px}nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}nav a{display:inline-block;text-decoration:none;color:#334155;background:#fff;border:1px solid #dbe3ed;border-radius:999px;padding:8px 13px;font-weight:750;font-size:.85rem}nav a.active{background:#1d4ed8;color:#fff;border-color:#1d4ed8}header,section{background:#fff;border:1px solid #dbe3ed;border-radius:16px;padding:22px;margin-bottom:17px;box-shadow:0 6px 20px rgba(15,23,42,.035)}h1{margin:6px 0 8px}h2{margin:0 0 15px;font-size:1.2rem}h3{margin:0 0 7px;font-size:.82rem;color:#64748b}.eye{font-weight:850;font-size:.74rem;letter-spacing:.08em;color:#1d4ed8}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.card{border:1px solid #e2e8f0;border-radius:13px;padding:15px;background:#fbfdff}.metric{font-weight:850;font-size:1.55rem}.muted{color:#64748b;font-size:.82rem;line-height:1.55}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.field{display:flex;flex-direction:column;gap:7px}.field label{font-weight:750;font-size:.88rem}.field small{color:#64748b;line-height:1.45}.field select,.field input{font:inherit;border:1px solid #cbd5e1;border-radius:10px;padding:10px;background:#fff}.results{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.result{border-radius:14px;padding:16px;background:#f8fafc;border:1px solid #e2e8f0}.result strong{font-size:1.45rem;display:block;margin-top:6px}.pill{display:inline-block;border-radius:999px;padding:4px 9px;font-size:.72rem;font-weight:850;background:#eef2f7;color:#475569}.good{background:#dcfce7;color:#166534}.warn{background:#fef3c7;color:#92400e}.danger{background:#fee2e2;color:#991b1b}.callout{border-left:4px solid #2563eb;background:#eff6ff;color:#1e3a8a;padding:13px 15px;border-radius:8px;line-height:1.65}.warning-box{border-left:4px solid #d97706;background:#fffbeb;color:#92400e;padding:13px 15px;border-radius:8px;line-height:1.65}ul{line-height:1.7;color:#475569}.logic-table{width:100%;border-collapse:collapse;font-size:.86rem}.logic-table th,.logic-table td{border-bottom:1px solid #e5e7eb;padding:9px;text-align:left}.logic-table th{background:#f8fafc;color:#475569}@media(max-width:850px){.grid,.results{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.grid,.results,.form-grid{grid-template-columns:1fr}}
</style>
</head>
<body><main>
<nav><a href="index.html">研究首頁</a><a href="live_report.html">五年估值河流</a><a class="active" href="decision_checklist.html">定期定額／加碼檢核</a></nav>
<header><div class="eye">TWSTOCK DECISION SUPPORT · __LOGIC_VERSION__</div><h1>2330.TW 定期定額與加碼進場檢核</h1><p class="muted">把「公司是否值得長期持有」、「目前估值」、「價格趨勢」與「你的資金及配置條件」分開處理。頁面只提供研究分類，不是個人化投資建議或下單指令。</p></header>
<section><h2>系統目前讀到的市場狀態</h2><div class="grid">
<div class="card"><h3>最新可用價格</h3><div class="metric">NT$ <span id="market-price"></span></div><div class="muted">延遲行情或TWSE完成交易日備援</div></div>
<div class="card"><h3>Trailing P/E</h3><div class="metric"><span id="market-pe"></span>x</div><div class="muted">五年百分位 <span id="market-percentile"></span>%</div></div>
<div class="card"><h3>長期趨勢</h3><div class="metric"><span id="market-trend"></span></div><div class="muted">價格相對MA200 <span id="market-ma200"></span>%</div></div>
<div class="card"><h3>Forward證據</h3><div class="metric" style="font-size:1rem"><span id="market-forward"></span></div><div class="muted">未有可驗證歷史版本時，禁止輸出強力加碼</div></div>
</div></section>
<section><h2>輸入你的資金與配置條件</h2><div class="form-grid">
<div class="field"><label for="horizon">預計持有期間</label><select id="horizon"><option value="1">1年</option><option value="3">3年</option><option value="5" selected>5年</option><option value="10">10年以上</option></select><small>單一股票的定期定額原則上要求至少五年。</small></div>
<div class="field"><label for="drawdown">可承受最大回撤</label><select id="drawdown"><option value="10">10%</option><option value="20">20%</option><option value="30" selected>30%</option><option value="40">40%以上</option></select><small>不是預測最大跌幅，而是檢查你的心理及資金承受能力。</small></div>
<div class="field"><label for="emergency">是否已有緊急預備金</label><select id="emergency"><option value="true" selected>有</option><option value="false">沒有</option></select></div>
<div class="field"><label for="borrowed">是否使用融資或借款</label><select id="borrowed"><option value="false" selected>沒有</option><option value="true">有</option></select></div>
<div class="field"><label for="cash-need">三年內是否需要這筆錢</label><select id="cash-need"><option value="false" selected>不需要</option><option value="true">可能需要</option></select></div>
<div class="field"><label for="current-weight">目前2330占投資組合（%）</label><input id="current-weight" type="number" min="0" max="100" step="0.1" value="0"></div>
<div class="field"><label for="target-weight">目標配置上限（%）</label><input id="target-weight" type="number" min="0" max="100" step="0.1" value="10"></div>
</div></section>
<section><h2>檢核結果</h2><div class="results">
<div class="result"><span class="pill">定期定額</span><strong id="dca-action"></strong><div class="muted">建議倍率 <span id="dca-multiplier"></span>倍</div></div>
<div class="result"><span class="pill">策略加碼</span><strong id="tactical-action"></strong><div class="muted">與固定月投資分開管理</div></div>
<div class="result"><span class="pill">判斷信心</span><strong id="confidence"></strong><div class="muted">Forward歷史證據會影響上限</div></div>
<div class="result"><span class="pill">配置餘額</span><strong id="headroom"></strong><div class="muted">目標配置－目前部位</div></div>
</div><div id="summary" class="callout" style="margin-top:15px"></div></section>
<section><h2>支持理由</h2><ul id="reasons"></ul><div id="warnings-wrap" class="warning-box"><strong>限制與警示</strong><ul id="warnings"></ul></div></section>
<section><h2>系統如何判斷</h2><div style="overflow:auto"><table class="logic-table"><thead><tr><th>檢核層</th><th>核心問題</th><th>用途</th></tr></thead><tbody>
<tr><td>資金Gate</td><td>五年以上、預備金、非借款、三年內不用錢</td><td>不符合時直接暫停，不用估值補救</td></tr>
<tr><td>配置Gate</td><td>目前部位是否低於目標上限</td><td>好公司也不能無限集中</td></tr>
<tr><td>基本面</td><td>營業利益率與近期營收方向</td><td>避免把衰退誤判為便宜</td></tr>
<tr><td>估值</td><td>五年Trailing P/E百分位</td><td>決定定期定額倍率，不單獨形成買賣訊號</td></tr>
<tr><td>趨勢</td><td>價格是否仍在MA200之上</td><td>估值便宜但趨勢破壞時降低投入速度</td></tr>
<tr><td>Forward證據</td><td>是否有可驗證法人共識歷史版本</td><td>沒有時禁止輸出中度或強力加碼</td></tr>
</tbody></table></div></section>
<script>
const market = __MARKET_JSON__;
const thresholds = __THRESHOLDS_JSON__;
const initial = __INITIAL_JSON__;
const $ = (id) => document.getElementById(id);
const asBool = (value) => value === 'true';
const number = (id) => Number($(id).value);
const fmt = (value, digits=1) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

function valuationMultiplier(p){if(p<=25)return 1.5;if(p<=60)return 1.0;if(p<=80)return .75;if(p<=90)return .5;return .25}
function valuationState(p){if(p<=25)return 'LOW';if(p<=60)return 'FAIR';if(p<=80)return 'UPPER_MIDDLE';if(p<=90)return 'HIGH';return 'EXTREME_HIGH'}
function fundamentalState(){if(market.latest_operating_margin_pct==null||market.latest_three_month_revenue_yoy_pct==null)return 'DATA_REVIEW';if(market.latest_operating_margin_pct<=0||market.latest_three_month_revenue_yoy_pct<=-10)return 'FAIL';if(market.latest_three_month_revenue_yoy_pct<0)return 'WATCH';return 'STRONG'}
function trendState(){if(market.price_vs_ma200_pct==null)return 'DATA_REVIEW';return market.price_vs_ma200_pct>=0?'POSITIVE':'NEGATIVE'}

function evaluate(){
  const input={horizon:number('horizon'),emergency:asBool($('emergency').value),borrowed:asBool($('borrowed').value),cashNeed:asBool($('cash-need').value),drawdown:number('drawdown'),current:number('current-weight'),target:number('target-weight')};
  localStorage.setItem('twstock-2330-decision-inputs',JSON.stringify(input));
  const fundamental=fundamentalState(), trend=trendState(), valuation=valuationState(market.trailing_pe_percentile), headroom=input.target-input.current;
  const blocks=[]; if(input.horizon<5)blocks.push('投資期間低於五年');if(!input.emergency)blocks.push('尚未建立緊急預備金');if(input.borrowed)blocks.push('使用借款或融資資金');if(input.cashNeed)blocks.push('三年內可能需要動用這筆資金');if(headroom<=0)blocks.push('目前部位已達或超過目標配置');if(fundamental==='FAIL')blocks.push('基本面檢核未通過');
  let dca='PAUSE', multiplier=0, tactical='NONE', confidence='LOW', reasons=[], warnings=[];
  if(blocks.length){warnings=blocks;reasons=['先處理資金用途、風險承受或配置問題，再評估進場。'];}
  else{
    multiplier=valuationMultiplier(market.trailing_pe_percentile);reasons.push(`五年Trailing P/E百分位為${fmt(market.trailing_pe_percentile,1)}%，基礎定期定額倍率為${multiplier.toFixed(2)}倍。`);
    if(fundamental==='WATCH'){multiplier=Math.min(multiplier,.5);warnings.push('近期營收方向偏弱，定期定額倍率上限降至0.50倍。')}else if(fundamental==='DATA_REVIEW'){multiplier=Math.min(multiplier,.5);warnings.push('基本面資料不足，定期定額倍率保守降至0.50倍。')}else reasons.push('最新營業利益率與近三月營收方向通過基本面檢核。');
    if(trend==='NEGATIVE'){multiplier=Math.min(multiplier,.5);warnings.push('價格低於MA200，策略加碼暫停，定期定額倍率上限為0.50倍。')}else if(trend==='DATA_REVIEW'){multiplier=Math.min(multiplier,.5);warnings.push('MA200資料不足，暫不允許策略加碼。')}else reasons.push('價格仍位於MA200之上，長期價格趨勢未破壞。');
    if(input.drawdown<20){multiplier=Math.min(multiplier,.5);warnings.push('可承受回撤低於20%，投入倍率上限降至0.50倍。')}
    if(headroom<2){multiplier=Math.min(multiplier,.5);warnings.push('距離目標配置不足2個百分點，新增部位應保守。')}
    dca=multiplier>=1.25?'INCREASE':multiplier>=.75?'CONTINUE':multiplier>0?'REDUCE':'PAUSE';
    if(market.trailing_pe_percentile<=30&&trend==='POSITIVE'&&fundamental==='STRONG'&&market.forward_pe_available&&input.drawdown>=30&&headroom>=5)tactical='STRONG';
    else if(market.trailing_pe_percentile<=60&&trend==='POSITIVE'&&fundamental==='STRONG'&&market.forward_pe_available&&input.drawdown>=25&&headroom>=3)tactical='MODERATE';
    else if(market.trailing_pe_percentile<=80&&trend==='POSITIVE'&&fundamental==='STRONG'&&input.drawdown>=20&&headroom>0)tactical='SMALL';
    if(!market.forward_pe_available){warnings.push('歷史Forward P/E百分位尚不可用，策略加碼最高只能評為SMALL，不能評為MODERATE或STRONG。');if(tactical==='MODERATE'||tactical==='STRONG')tactical='SMALL'}
    confidence=(!market.forward_pe_available||fundamental==='DATA_REVIEW'||trend==='DATA_REVIEW')?'MEDIUM_LOW':(market.forward_pe_available&&fundamental==='STRONG'&&trend==='POSITIVE')?'MEDIUM_HIGH':'MEDIUM';
    reasons.push(`目前部位距離目標配置尚有${fmt(headroom,2)}個百分點。`);reasons.push(tactical==='SMALL'?'基本面與長期趨勢通過，但估值仍非低檔，因此只允許小額分批。':'目前估值、趨勢、證據或配置條件不足以支持額外策略加碼。');
  }
  $('dca-action').textContent=dca;$('dca-multiplier').textContent=multiplier.toFixed(2);$('tactical-action').textContent=tactical;$('confidence').textContent=confidence;$('headroom').textContent=`${fmt(headroom,2)}%`;
  $('reasons').innerHTML=reasons.map(x=>`<li>${x}</li>`).join('');$('warnings').innerHTML=warnings.map(x=>`<li>${x}</li>`).join('');$('warnings-wrap').style.display=warnings.length?'block':'none';
  const dcaText={INCREASE:'估值與個人條件允許提高固定投入',CONTINUE:'維持正常或略低的固定投入',REDUCE:'降低固定投入速度',PAUSE:'暫停新增資金'}[dca];
  const tacticalText={NONE:'不額外加碼',SMALL:'只考慮小額分批',MODERATE:'可考慮中度分批',STRONG:'符合強力分批研究條件'}[tactical];
  $('summary').innerHTML=`<strong>${dcaText}；${tacticalText}。</strong><br>這是依目前市場資料與你輸入條件形成的研究分類，仍須自行確認未來EPS情境、集中度與可承受損失。`;
}

$('market-price').textContent=fmt(market.price_twd,0);$('market-pe').textContent=fmt(market.pe_ttm,2);$('market-percentile').textContent=fmt(market.trailing_pe_percentile,1);$('market-ma200').textContent=fmt(market.price_vs_ma200_pct,2);$('market-trend').textContent=trendState();$('market-forward').textContent=market.forward_pe_status;
try{const saved=JSON.parse(localStorage.getItem('twstock-2330-decision-inputs'));if(saved){$('horizon').value=String(saved.horizon);$('emergency').value=String(saved.emergency);$('borrowed').value=String(saved.borrowed);$('cash-need').value=String(saved.cashNeed);$('drawdown').value=String(saved.drawdown);$('current-weight').value=String(saved.current);$('target-weight').value=String(saved.target)}}catch(e){}
['horizon','emergency','borrowed','cash-need','drawdown','current-weight','target-weight'].forEach(id=>$(id).addEventListener('input',evaluate));evaluate();
</script>
</main></body></html>'''

    document = (
        template.replace("__LOGIC_VERSION__", html.escape(DECISION_LOGIC_VERSION))
        .replace("__MARKET_JSON__", market_json.replace("</", "<\\/"))
        .replace("__THRESHOLDS_JSON__", thresholds_json.replace("</", "<\\/"))
        .replace("__INITIAL_JSON__", initial_json.replace("</", "<\\/"))
    )
    output_path.write_text(document, encoding="utf-8")
    return initial


def write_site_index(analysis: dict[str, Any], output_path: Path) -> None:
    market = market_snapshot_from_analysis(analysis)
    document = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>2330研究控制台</title><style>:root{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#111827}}main{{max-width:980px;margin:auto;padding:40px 20px}}header,.card{{background:#fff;border:1px solid #dbe3ed;border-radius:18px;padding:24px;box-shadow:0 7px 22px rgba(15,23,42,.04)}}header{{margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}a.card{{display:block;text-decoration:none;color:inherit}}a.card:hover{{border-color:#2563eb;transform:translateY(-1px)}}h1{{margin:7px 0}}h2{{margin:0 0 8px}}p{{color:#64748b;line-height:1.65}}.eye{{color:#1d4ed8;font-weight:850;font-size:.75rem;letter-spacing:.08em}}.metric{{font-weight:850;font-size:1.4rem;color:#1d4ed8}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}}}</style></head><body><main><header><div class="eye">TWSTOCK EXPERIMENT</div><h1>2330.TW 投資研究控制台</h1><p>最新可用價格 NT$ {market.price_twd:.0f} · Trailing P/E {market.pe_ttm:.2f}x · 五年百分位 {market.trailing_pe_percentile:.1f}%</p></header><div class="grid"><a class="card" href="live_report.html"><div class="metric">01</div><h2>五年Point-in-Time估值河流</h2><p>查看價格、TTM EPS、Trailing P/E百分位、Forward資料狀態、技術與多期間超額報酬診斷。</p></a><a class="card" href="decision_checklist.html"><div class="metric">02</div><h2>定期定額／加碼進場檢核</h2><p>輸入持有期間、資金用途、回撤承受與目前配置，分開產生定期定額與策略加碼分類。</p></a></div></main></body></html>'''
    output_path.write_text(document, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the interactive DCA and tactical-add checklist page."
    )
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--index-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    analysis = _read_analysis(args.analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = write_decision_page(analysis, args.output)
    if args.index_output:
        write_site_index(analysis, args.index_output)
    print(f"Decision page: {args.output}")
    print(f"Default DCA: {result.dca_action} x{result.dca_multiplier}")
    print(f"Default tactical add: {result.tactical_add_action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
