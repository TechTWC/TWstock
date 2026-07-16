from __future__ import annotations
import json, os
from pathlib import Path
from urllib.parse import urlencode
from ..http import HttpTransport, get_with_retry
from ..models import MarketDataRecord, SourceTier, SourceResult, SourceState
from ..normalization import canonical_symbol as to_canonical_symbol, parse_float, parse_int, raw_hash, redact_tokens_in_text, sanitize_url, utc_now_iso, validate_date_range
from ..raw_cache import preserve_raw_response
from ..errors import MalformedSourceError, DuplicateTradeDateError, SourceUnavailableError, DataValidationError

FINMIND_DAILY_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"

def build_url(source_symbol: str, start: str, end: str, token: str | None) -> str:
    params = {"dataset": "TaiwanStockPrice", "data_id": source_symbol, "start_date": start, "end_date": end}
    if token:
        params["token"] = token
    return FINMIND_DAILY_ENDPOINT + "?" + urlencode(params)

def fetch_finmind_daily(
    source_symbol: str,
    canonical_symbol: str,
    start: str,
    end: str,
    transport: HttpTransport | None = None,
    timeout: float = 10,
    retries: int = 2,
    token_env: str = "FINMIND_TOKEN",
    raw_cache_dir: Path | str | None = None,
) -> SourceResult:
    validate_date_range(start, end)
    expected_canonical = to_canonical_symbol(source_symbol, "TW")
    if canonical_symbol != expected_canonical:
        raise DataValidationError("FinMind canonical symbol mismatch")
    token = os.environ.get(token_env)
    if not token:
        return SourceResult(SourceState.SOURCE_UNAVAILABLE, error=f"{token_env} is not set")
    url = build_url(source_symbol, start, end, token)
    try:
        response = get_with_retry(url, transport, timeout, retries)
        retrieved_at = utc_now_iso()
        preserve_raw_response(
            raw_cache_dir,
            source="FinMind",
            source_tier=SourceTier.SECONDARY.value,
            source_symbol=source_symbol,
            canonical_symbol=canonical_symbol,
            requested_start=start,
            requested_end=end,
            retrieved_at=retrieved_at,
            source_url=response.url,
            http_status=response.status,
            body=response.body,
            request_identifier=raw_hash(sanitize_url(url))[:12],
        )
        payload = json.loads(response.body.decode("utf-8"))
        records = parse_finmind_payload(payload, source_symbol, canonical_symbol, start, end, response.body, FINMIND_DAILY_ENDPOINT, retrieved_at)
        return SourceResult(SourceState.SECONDARY_ONLY, records)
    except SourceUnavailableError as e:
        return SourceResult(SourceState.SOURCE_UNAVAILABLE, error=redact_tokens_in_text(str(e).replace(token, "<redacted>")))

def parse_finmind_payload(
    payload: dict,
    source_symbol: str,
    canonical_symbol: str,
    start: str,
    end: str,
    raw: bytes | None = None,
    source_reference: str = FINMIND_DAILY_ENDPOINT,
    retrieved_at: str | None = None,
) -> tuple[MarketDataRecord, ...]:
    validate_date_range(start, end)
    if canonical_symbol != to_canonical_symbol(source_symbol, "TW"):
        raise DataValidationError("FinMind canonical symbol mismatch")
    if not isinstance(payload, dict) or "data" not in payload or not isinstance(payload["data"], list):
        raise MalformedSourceError("unexpected FinMind TaiwanStockPrice schema")
    required = {"date", "stock_id", "Trading_Volume", "Trading_money", "open", "max", "min", "close", "Trading_turnover"}
    seen: set[str] = set()
    out: list[MarketDataRecord] = []
    h = raw_hash(raw or json.dumps(payload, ensure_ascii=False))
    retrieved = retrieved_at or utc_now_iso()
    for item in payload["data"]:
        if not required.issubset(item):
            raise MalformedSourceError("missing FinMind field")
        if item["stock_id"] != source_symbol:
            raise MalformedSourceError("FinMind response stock_id mismatch")
        iso = item["date"]
        if not (start <= iso <= end):
            continue
        if iso in seen:
            raise DuplicateTradeDateError(f"duplicate FinMind trade date {iso}")
        seen.add(iso)
        out.append(MarketDataRecord(
            "FinMind", SourceTier.SECONDARY, source_symbol, canonical_symbol, "TW", iso,
            parse_int(item["Trading_Volume"], "traded_share_volume"),
            parse_int(item["Trading_money"], "official_traded_value_twd"),
            parse_float(item["open"], "open_price"),
            parse_float(item["max"], "high_price"),
            parse_float(item["min"], "low_price"),
            parse_float(item["close"], "close_price"),
            parse_int(item["Trading_turnover"], "transaction_count"),
            retrieved,
            sanitize_url(source_reference),
            h,
        ))
    return tuple(out)
