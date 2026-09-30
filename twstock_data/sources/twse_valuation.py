"""Official contemporaneous PE paired with same-symbol/date unadjusted close.

BWIBBU does not include close (or a symbol code in its title). STOCK_DAY_AVG
supplies the code and name; the BWIBBU name must match exactly. No EPS,
adjusted prices, or financial statement reconstruction is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..errors import DataValidationError, MalformedSourceError
from ..http import HttpTransport, get_with_retry
from ..normalization import raw_hash, utc_now_iso
from ..twse_incremental_cache import (
    load_cached_month, store_cached_month, write_cache_run_manifest,
)

HISTORY_START = date(2005, 9, 1)
BASE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/"
NO_DATA = "很抱歉，沒有符合條件的資料!"


@dataclass(frozen=True)
class ValuationObservation:
    symbol: str
    trade_date: date
    official_close: float
    official_pe: float | None
    close_source_url: str = ""
    pe_source_url: str = ""


@dataclass(frozen=True)
class ValuationHistory:
    observations: tuple[ValuationObservation, ...]
    month_results: tuple[dict, ...]
    source_start: date | None
    incomplete_months: tuple[str, ...]


def validate_symbol(symbol: str) -> None:
    # TWSE ordinary shares have four-digit codes; ETFs/ETNs are excluded.
    if not re.fullmatch(r"[1-9][0-9]{3}", symbol):
        raise DataValidationError("symbol must be a four-digit TWSE ordinary-share code")


def build_url(endpoint: str, symbol: str, month: date) -> str:
    return BASE_URL + endpoint + "?" + urlencode(
        {"response": "json", "date": month.strftime("%Y%m%d"), "stockNo": symbol}
    )


def parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise MalformedSourceError("TWSE date must be text")
    match = re.fullmatch(r"\s*(\d{2,3})(?:年|/)(\d{2})(?:月|/)(\d{2})日?\s*", value)
    if not match:
        raise MalformedSourceError(f"malformed TWSE date: {value!r}")
    try:
        year, month, day = map(int, match.groups())
        return date(year + 1911, month, day)
    except ValueError as exc:
        raise MalformedSourceError("invalid TWSE calendar date") from exc


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MalformedSourceError(f"invalid {field}")
    text = str(value).strip()
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise MalformedSourceError(f"malformed {field}: {value!r}")
    number = float(text.replace(",", ""))
    if not math.isfinite(number):
        raise MalformedSourceError(f"nonfinite {field}")
    return number


def _payload(body: bytes, month: date) -> dict:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid TWSE JSON") from exc
    if not isinstance(payload, dict):
        raise MalformedSourceError("TWSE payload must be an object")
    if payload.get("stat") == NO_DATA:
        # TWSE's no-data schemas differ by endpoint: BWIBBU includes
        # ``total: 0`` while STOCK_DAY_AVG omits ``total`` entirely.
        if (payload.get("total", 0) != 0
                or payload.get("data") not in (None, [])
                or payload.get("fields") not in (None, [])):
            raise MalformedSourceError("contradictory no-data response")
        return payload
    if payload.get("stat") != "OK" or payload.get("date") != month.strftime("%Y%m%d"):
        raise MalformedSourceError("TWSE status or requested month mismatch")
    fields, rows = payload.get("fields"), payload.get("data")
    if (not isinstance(fields, list) or not all(isinstance(f, str) for f in fields)
            or len(set(fields)) != len(fields) or not isinstance(rows, list) or not rows):
        raise MalformedSourceError("unexpected empty response or invalid TWSE schema")
    if "total" in payload and payload["total"] != len(rows):
        raise MalformedSourceError("truncated TWSE response")
    if not isinstance(payload.get("title"), str):
        raise MalformedSourceError("missing TWSE response title")
    return payload


def _rows(payload: dict, month: date, required: tuple[str, ...], *, average=False):
    fields = payload["fields"]
    if any(field not in fields for field in required):
        raise MalformedSourceError("missing required TWSE fields")
    previous = None
    summary_seen = False
    for row in payload["data"]:
        if not isinstance(row, list) or len(row) != len(fields):
            raise MalformedSourceError("TWSE row width mismatch")
        values = {field: row[fields.index(field)] for field in required}
        if average and values["日期"] == "月平均收盤價":
            if summary_seen:
                raise MalformedSourceError("duplicate monthly average")
            summary_seen = True
            _number(values["收盤價"], "monthly average")
            continue
        if summary_seen:
            raise MalformedSourceError("observation after monthly summary")
        day = parse_date(values["日期"])
        if (day.year, day.month) != (month.year, month.month):
            raise DataValidationError("observation outside requested month")
        if previous is not None and day <= previous:
            raise DataValidationError("duplicate or unordered TWSE trade dates")
        previous = day
        yield day, values


def parse_close_payload(body: bytes, symbol: str, month: date):
    validate_symbol(symbol)
    payload = _payload(body, month)
    if payload["stat"] == NO_DATA:
        return None, {}
    match = re.fullmatch(r"\d{2,3}年\d{2}月\s+(\d{4})\s+(.+?)\s+日收盤價及月平均收盤價", payload["title"])
    if not match or match.group(1) != symbol:
        raise DataValidationError("TWSE close symbol identity mismatch")
    name = match.group(2).strip()
    closes = {}
    for day, values in _rows(payload, month, ("日期", "收盤價"), average=True):
        close = _number(values["收盤價"], "official close")
        if close <= 0:
            raise DataValidationError("official close must be positive")
        closes[day] = close
    if not closes:
        raise MalformedSourceError("no daily close observations")
    return name, closes


def parse_valuation_payload(body: bytes, symbol: str, name: str | None, month: date):
    validate_symbol(symbol)
    payload = _payload(body, month)
    if payload["stat"] == NO_DATA:
        return {}
    match = re.fullmatch(r"\d{2,3}年\d{2}月\s+(.+?)\s+個股日本益比、殖利率及股價淨值比\(以個股月查詢\)", payload["title"])
    if name is None or not match or match.group(1).strip() != name:
        raise DataValidationError("TWSE valuation name/symbol identity mismatch")
    for key in ("stockNo", "stockCode"):
        if key in payload and str(payload[key]) != symbol:
            raise DataValidationError("TWSE valuation explicit symbol mismatch")
    result = {}
    for day, values in _rows(payload, month, ("日期", "本益比", "殖利率(%)", "股價淨值比")):
        raw = values["本益比"]
        if isinstance(raw, str) and raw.strip() in ("", "-", "--"):
            pe = None
        else:
            parsed = _number(raw, "official PE")
            pe = parsed if parsed > 0 else None
        result[day] = pe
    return result


def completed_session_cutoff(now: datetime | None = None) -> date:
    local = (now or datetime.now(ZoneInfo("Asia/Taipei"))).astimezone(ZoneInfo("Asia/Taipei"))
    # Conservative release cutoff: exclude today's intraday or unpublished rows.
    return local.date() if (local.hour, local.minute) >= (14, 30) else local.date() - timedelta(days=1)


def fetch_history(symbol: str, start: date, end: date, cache_dir: Path, *,
                  transport: HttpTransport | None = None, timeout=30.0,
                  retries=2, request_interval=1.0, refresh_date: date | None = None,
                  progress=None) -> ValuationHistory:
    validate_symbol(symbol)
    if start < HISTORY_START or start > end:
        raise DataValidationError("invalid valuation history window")
    root = Path(cache_dir)
    current_month = (refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()).replace(day=1)
    # Also refresh the most recently requested month, including a prior month
    # when run on the first day. Never trust a formerly partial current month.
    refresh_months = {current_month, current_month - timedelta(days=1), end.replace(day=1)}
    refresh_months = {d.replace(day=1) for d in refresh_months}
    month = start.replace(day=1)
    records, results, incomplete = [], [], []
    first_pe = None
    last_request = None

    def request(endpoint, month):
        nonlocal last_request
        url = build_url(endpoint, symbol, month)
        namespace = root / endpoint
        cached = None
        if month not in refresh_months:
            cached = load_cached_month(namespace, source_symbol=symbol,
                canonical_symbol=f"{symbol}.TW", month_identifier=month.strftime("%Y%m%d"),
                expected_source_url=url)
        if cached is not None:
            return cached.body, url, cached.retrieved_at, "CACHE_HIT"
        if last_request is not None:
            time.sleep(max(0, request_interval - (time.monotonic() - last_request)))
        response = get_with_retry(url, transport, timeout, retries, backoff=2)
        last_request = time.monotonic()
        return response.body, url, utc_now_iso(), "FETCHED"

    def manifest(completed):
        write_cache_run_manifest(root, source_symbol=symbol,
            requested_start=start.isoformat(), requested_end=end.isoformat(),
            refresh_month=end.replace(day=1).strftime("%Y%m%d"),
            month_results=results, completed=completed)

    while month <= end:
        try:
            close_body, close_url, close_time, close_status = request("STOCK_DAY_AVG", month)
            name, closes = parse_close_payload(close_body, symbol, month)
            pe_body, pe_url, pe_time, pe_status = request("BWIBBU", month)
            pes = parse_valuation_payload(pe_body, symbol, name, month)
            if set(pes) - set(closes):
                raise DataValidationError("valuation date has no same-day official close")
            if pes and first_pe is None:
                first_pe = min(pes)
            missing = sorted(set(closes) - set(pes))
            if missing:
                incomplete.append(month.strftime("%Y-%m"))
            # Cache only fully parsed, identity-validated pairs. Namespace keeps
            # these raw responses separate from the existing STOCK_DAY cache.
            for endpoint, body, url, retrieved, status in (
                ("STOCK_DAY_AVG", close_body, close_url, close_time, close_status),
                ("BWIBBU", pe_body, pe_url, pe_time, pe_status),
            ):
                if status != "CACHE_HIT":
                    store_cached_month(root / endpoint, source_symbol=symbol,
                        canonical_symbol=f"{symbol}.TW", month_identifier=month.strftime("%Y%m%d"),
                        source_url=url, retrieved_at=retrieved, http_status=200, body=body)
            records.extend(ValuationObservation(symbol, day, close, pes.get(day), close_url, pe_url)
                           for day, close in closes.items() if start <= day <= end)
            results.append({"month": month.strftime("%Y-%m"), "close_status": close_status,
                "pe_status": pe_status, "close_count": len(closes), "pe_count": len(pes),
                "missing_pe_dates": [d.isoformat() for d in missing],
                "close_source_url": close_url, "pe_source_url": pe_url,
                "close_sha256": raw_hash(close_body), "pe_sha256": raw_hash(pe_body),
                "close_retrieved_at": close_time, "pe_retrieved_at": pe_time})
        except Exception as exc:
            results.append({"month": month.strftime("%Y-%m"), "status": "FAILED",
                            "error_code": type(exc).__name__})
            manifest(False)
            raise
        manifest(False)
        if progress:
            progress(results[-1])
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    manifest(True)
    if not records or first_pe is None:
        raise DataValidationError("no official valuation history for requested symbol/window")
    # MAX begins at the first available official valuation observation.
    records = [r for r in records if r.trade_date >= first_pe]
    return ValuationHistory(tuple(records), tuple(results), first_pe, tuple(incomplete))
