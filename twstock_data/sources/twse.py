from __future__ import annotations
import json
from datetime import date, datetime
from urllib.parse import urlencode
from ..http import HttpTransport, get_with_retry
from ..models import MarketDataRecord, SourceTier
from ..normalization import canonical_symbol, parse_float, parse_int, raw_hash, utc_now_iso
from ..errors import MalformedSourceError, DataValidationError, DuplicateTradeDateError

TWSE_STOCK_DAY_ENDPOINT = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
FIELDS = ("日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","成交筆數")

def _roc_to_iso(text: str) -> str:
    y,m,d = [int(p) for p in text.split("/")]
    return date(y+1911,m,d).isoformat()

def build_url(source_symbol: str, month: str) -> str:
    return TWSE_STOCK_DAY_ENDPOINT + "?" + urlencode({"response":"json","date":month,"stockNo":source_symbol})

def fetch_twse_daily(source_symbol: str, start: str, end: str, transport: HttpTransport | None = None, timeout: float = 10, retries: int = 2) -> tuple[MarketDataRecord,...]:
    month = start[:7].replace("-", "") + "01"
    url = build_url(source_symbol, month)
    response = get_with_retry(url, transport, timeout, retries)
    payload = json.loads(response.body.decode("utf-8-sig"))
    return parse_twse_payload(payload, source_symbol, start, end, response.body, response.url)

def parse_twse_payload(payload: dict, source_symbol: str, start: str, end: str, raw: bytes | None = None, source_reference: str = TWSE_STOCK_DAY_ENDPOINT, retrieved_at: str | None = None) -> tuple[MarketDataRecord,...]:
    if not isinstance(payload, dict) or payload.get("stat") not in ("OK", "很抱歉，沒有符合條件的資料!") or "fields" not in payload or "data" not in payload:
        raise MalformedSourceError("unexpected TWSE STOCK_DAY schema")
    fields = tuple(payload["fields"])
    for f in FIELDS:
        if f not in fields: raise MalformedSourceError(f"missing TWSE field {f}")
    idx = {f: fields.index(f) for f in FIELDS}; seen=set(); out=[]; h=raw_hash(raw or json.dumps(payload, ensure_ascii=False))
    canonical = canonical_symbol(source_symbol, "TW")
    retrieved = retrieved_at or utc_now_iso()
    for row in payload["data"]:
        iso = _roc_to_iso(row[idx["日期"]])
        if not (start <= iso <= end): continue
        if iso in seen: raise DuplicateTradeDateError(f"duplicate TWSE trade date {iso}")
        seen.add(iso)
        out.append(MarketDataRecord("TWSE", SourceTier.PRIMARY, source_symbol, canonical, "TW", iso,
            parse_int(row[idx["成交股數"]], "traded_share_volume"), parse_int(row[idx["成交金額"]], "official_traded_value_twd"),
            parse_float(row[idx["開盤價"]], "open_price"), parse_float(row[idx["最高價"]], "high_price"), parse_float(row[idx["最低價"]], "low_price"), parse_float(row[idx["收盤價"]], "close_price"),
            parse_int(row[idx["成交筆數"]], "transaction_count"), retrieved, source_reference, h))
    return tuple(out)
