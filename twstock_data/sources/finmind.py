from __future__ import annotations
import json, os
from urllib.parse import urlencode
from ..http import HttpTransport, get_with_retry
from ..models import MarketDataRecord, SourceTier, SourceResult, SourceState
from ..normalization import parse_float, parse_int, raw_hash, utc_now_iso
from ..errors import MalformedSourceError, DuplicateTradeDateError, SourceUnavailableError

FINMIND_DAILY_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"

def build_url(source_symbol: str, start: str, end: str, token: str | None) -> str:
    params = {"dataset":"TaiwanStockPrice","data_id":source_symbol,"start_date":start,"end_date":end}
    if token: params["token"] = token
    return FINMIND_DAILY_ENDPOINT + "?" + urlencode(params)

def fetch_finmind_daily(source_symbol: str, canonical_symbol: str, start: str, end: str, transport: HttpTransport | None = None, timeout: float = 10, retries: int = 2, token_env: str = "FINMIND_TOKEN") -> SourceResult:
    token = os.environ.get(token_env)
    if not token: return SourceResult(SourceState.SOURCE_UNAVAILABLE, error=f"{token_env} is not set")
    url = build_url(source_symbol, start, end, token)
    try:
        response = get_with_retry(url, transport, timeout, retries)
        payload = json.loads(response.body.decode("utf-8"))
        records = parse_finmind_payload(payload, source_symbol, canonical_symbol, start, end, response.body, FINMIND_DAILY_ENDPOINT)
        return SourceResult(SourceState.SECONDARY_ONLY, records)
    except SourceUnavailableError as e:
        return SourceResult(SourceState.SOURCE_UNAVAILABLE, error=str(e))

def parse_finmind_payload(payload: dict, source_symbol: str, canonical_symbol: str, start: str, end: str, raw: bytes | None = None, source_reference: str = FINMIND_DAILY_ENDPOINT, retrieved_at: str | None = None) -> tuple[MarketDataRecord,...]:
    if not isinstance(payload, dict) or "data" not in payload or not isinstance(payload["data"], list):
        raise MalformedSourceError("unexpected FinMind TaiwanStockPrice schema")
    required = {"date","stock_id","Trading_Volume","Trading_money","open","max","min","close","Trading_turnover"}
    seen=set(); out=[]; h=raw_hash(raw or json.dumps(payload, ensure_ascii=False)); retrieved=retrieved_at or utc_now_iso()
    for item in payload["data"]:
        if not required.issubset(item): raise MalformedSourceError("missing FinMind field")
        if item["stock_id"] != source_symbol: raise MalformedSourceError("FinMind response stock_id mismatch")
        iso = item["date"]
        if not (start <= iso <= end): continue
        if iso in seen: raise DuplicateTradeDateError(f"duplicate FinMind trade date {iso}")
        seen.add(iso)
        out.append(MarketDataRecord("FinMind", SourceTier.SECONDARY, source_symbol, canonical_symbol, "TW", iso,
            parse_int(item["Trading_Volume"], "traded_share_volume"), parse_int(item["Trading_money"], "official_traded_value_twd"),
            parse_float(item["open"], "open_price"), parse_float(item["max"], "high_price"), parse_float(item["min"], "low_price"), parse_float(item["close"], "close_price"),
            parse_int(item["Trading_turnover"], "transaction_count"), retrieved, source_reference, h))
    return tuple(out)
