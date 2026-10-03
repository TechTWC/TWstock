"""Generic official TPEx close/PE history for ordinary common shares.

The monthly per-security reports keep MAX retrieval bounded.  Every response
is tied back to the requested code/month, parsed by field name, checked for
declared-row truncation, and reconciled on the same trading date.
"""
from __future__ import annotations

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
from .security_identity import TPEX, canonical_symbol, validate_symbol
from .twse_valuation import (
    ValuationHistory, ValuationObservation, ValuationPoint,
    parse_financial_report_period,
)

HISTORY_START = date(2012, 9, 1)
CLOSE_HISTORY_START = date(1994, 1, 1)
BASE_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/"
MISSING = frozenset({"", "-", "--", "---", "—", "－", "N/A", "NA", "null"})


def build_url(endpoint: str, symbol: str, month: date) -> str:
    validate_symbol(symbol)
    if endpoint not in {"tradingStock", "peQryStock"}:
        raise DataValidationError("unsupported TPEx valuation endpoint")
    return BASE_URL + endpoint + "?" + urlencode({
        "code": symbol, "date": month.strftime("%Y/%m/01"), "response": "json",
    })


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise MalformedSourceError("TPEx date must be text")
    # TPEx appends an official asterisk footnote marker to some listing-period
    # dates.  It is presentation metadata, not part of the calendar identity.
    match = re.fullmatch(r"\s*(\d{2,3})/(\d{2})/(\d{2})[*＊]?\s*", value)
    if not match:
        raise MalformedSourceError(f"malformed TPEx date: {value!r}")
    try:
        return date(int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise MalformedSourceError("invalid TPEx calendar date") from exc


def _number(value: object, field: str, *, unavailable=False) -> float | None:
    if isinstance(value, str) and value.strip() in MISSING:
        if unavailable:
            return None
        raise MalformedSourceError(f"missing {field}")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MalformedSourceError(f"invalid {field}")
    text = str(value).strip()
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise MalformedSourceError(f"malformed {field}: {value!r}")
    result = float(text.replace(",", ""))
    if not math.isfinite(result):
        raise MalformedSourceError(f"nonfinite {field}")
    return result


def _declared_count(value: object, actual: int) -> None:
    if value is None or value == "":
        raise MalformedSourceError("TPEx table omits declared row count")
    text = str(value).replace(",", "").strip()
    if not re.fullmatch(r"\d+", text) or int(text) != actual:
        raise MalformedSourceError("truncated TPEx response")


def _payload(body: bytes, symbol: str, month: date, *, code_optional=False) -> dict:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid TPEx JSON") from exc
    if not isinstance(payload, dict):
        raise MalformedSourceError("TPEx payload must be an object")
    response_code = str(payload.get("code", "")).strip()
    # peQryStock's official historical envelope omits code/name even though
    # the request is per-code.  When absent, identity is established by the
    # exact request URL plus the paired, code-bearing tradingStock response.
    # A code that is present must always match.
    if response_code and response_code != symbol:
        raise DataValidationError("TPEx response symbol identity mismatch")
    if not response_code and not code_optional:
        raise DataValidationError("TPEx response omits symbol identity")
    response_date = str(payload.get("date", "")).strip()
    if response_date != month.strftime("%Y%m%d"):
        raise DataValidationError("TPEx response month identity mismatch")
    if str(payload.get("stat", "")).lower() != "ok":
        raise MalformedSourceError("unexpected TPEx response status")
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise MalformedSourceError("TPEx response omits tables")
    return payload


def _table(payload: dict, required: tuple[str, ...]) -> tuple[list[str], list[list]] | None:
    matches = []
    for raw in payload["tables"]:
        if not isinstance(raw, dict):
            raise MalformedSourceError("invalid TPEx table")
        source_fields, rows = raw.get("fields"), raw.get("data")
        if not isinstance(source_fields, list) or not all(isinstance(f, str) for f in source_fields):
            raise MalformedSourceError("invalid TPEx table fields")
        if not isinstance(rows, list):
            raise MalformedSourceError("invalid TPEx table rows")
        # The official historical close schema used `日 期`; the current
        # schema uses `日期`.  Whitespace is presentation-only, so normalize
        # it for every field rather than branching on a date or symbol.
        fields = [re.sub(r"\s+", "", field) for field in source_fields]
        if all(field in fields for field in required):
            # Some envelopes include an ancillary dividend-year legend whose
            # presentation headings are not a rectangular observation schema.
            # Completeness checks apply to the uniquely selected observation
            # table; unrelated tables cannot supply or alter observations.
            if any(not field for field in fields) or len(fields) != len(set(fields)):
                raise MalformedSourceError("invalid TPEx observation table schema")
            _declared_count(raw.get("totalCount"), len(rows))
            for row in rows:
                if not isinstance(row, list) or len(row) != len(fields):
                    raise MalformedSourceError("TPEx row width mismatch")
            matches.append((fields, rows))
    if len(matches) > 1:
        raise MalformedSourceError("ambiguous TPEx data table")
    if not matches:
        if all(not raw.get("data") for raw in payload["tables"] if isinstance(raw, dict)):
            return None
        raise MalformedSourceError("missing required TPEx fields")
    return matches[0]


def _identity_name(payload: dict, expected_name: str | None) -> str | None:
    raw = payload.get("name")
    name = raw.strip() if isinstance(raw, str) else None
    if expected_name and name and name.rstrip("*").strip() != expected_name.rstrip("*").strip():
        raise DataValidationError("TPEx company-name identity mismatch")
    return name


def _ordered_rows(fields: list[str], rows: list[list], month: date):
    previous = None
    for row in rows:
        day = _parse_date(row[fields.index("日期")])
        if (day.year, day.month) != (month.year, month.month):
            raise DataValidationError("TPEx observation outside requested month")
        if previous is not None and day <= previous:
            raise DataValidationError("duplicate or unordered TPEx trade dates")
        previous = day
        yield day, {field: row[index] for index, field in enumerate(fields)}


def parse_close_payload(body: bytes, symbol: str, month: date,
                        expected_name: str | None = None):
    payload = _payload(body, symbol, month)
    name = _identity_name(payload, expected_name)
    table = _table(payload, ("日期", "收盤"))
    if table is None:
        return name, {}
    fields, rows = table
    closes = {}
    for day, values in _ordered_rows(fields, rows, month):
        close = _number(values["收盤"], "official close", unavailable=True)
        if close is not None and close <= 0:
            raise DataValidationError("official close must be positive")
        closes[day] = close
    return name, closes


def parse_valuation_payload_with_period(body: bytes, symbol: str, month: date,
                                        expected_name: str | None = None):
    payload = _payload(body, symbol, month, code_optional=True)
    _identity_name(payload, expected_name)
    table = _table(payload, ("日期", "本益比"))
    if table is None:
        return {}
    fields, rows = table
    result = {}
    for day, values in _ordered_rows(fields, rows, month):
        raw = values["本益比"]
        parsed = _number(raw, "official PE", unavailable=True)
        pe = parsed if parsed is not None and parsed > 0 else None
        period_field = next((field for field in ("財報年/季", "財報年季") if field in fields), None)
        period_raw, period_end = parse_financial_report_period(
            values[period_field] if period_field else None)
        result[day] = ValuationPoint(pe, period_raw, period_end)
    return result


def parse_valuation_payload(body: bytes, symbol: str, month: date,
                            expected_name: str | None = None):
    return {day: point.official_pe for day, point in
            parse_valuation_payload_with_period(body, symbol, month, expected_name).items()}


def fetch_history(symbol: str, start: date, end: date, cache_dir: Path, *,
                  company_name: str | None = None,
                  transport: HttpTransport | None = None, timeout=30.0,
                  retries=2, request_interval=1.0, refresh_date: date | None = None,
                  progress=None) -> ValuationHistory:
    validate_symbol(symbol)
    if start < HISTORY_START or start > end:
        raise DataValidationError("invalid TPEx valuation history window")
    root = Path(cache_dir)
    current_month = (refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()).replace(day=1)
    refresh_months = {current_month, (current_month - timedelta(days=1)).replace(day=1),
                      end.replace(day=1)}
    month = start.replace(day=1)
    records: list[ValuationObservation] = []
    results: list[dict] = []
    incomplete: list[str] = []
    first_pe: date | None = None
    last_request: float | None = None
    canonical = canonical_symbol(symbol, TPEX)

    def request(endpoint: str, target: date):
        nonlocal last_request
        url = build_url(endpoint, symbol, target)
        namespace = root / endpoint
        cached = None if target in refresh_months else load_cached_month(
            namespace, source_symbol=symbol, canonical_symbol=canonical,
            month_identifier=target.strftime("%Y%m%d"), expected_source_url=url,
            source=TPEX)
        if cached is not None:
            return cached.body, url, cached.retrieved_at, "CACHE_HIT"
        if last_request is not None:
            time.sleep(max(0, request_interval - (time.monotonic() - last_request)))
        response = get_with_retry(url, transport, timeout, retries, backoff=2)
        last_request = time.monotonic()
        return response.body, url, utc_now_iso(), "FETCHED"

    def manifest(completed: bool):
        write_cache_run_manifest(
            root, source_symbol=symbol, canonical_symbol=canonical,
            requested_start=start.isoformat(), requested_end=end.isoformat(),
            refresh_month=end.replace(day=1).strftime("%Y%m%d"),
            month_results=results, completed=completed, source=TPEX)

    while month <= end:
        try:
            close_body, close_url, close_time, close_status = request("tradingStock", month)
            observed_name, closes = parse_close_payload(
                close_body, symbol, month, company_name)
            pe_body, pe_url, pe_time, pe_status = request("peQryStock", month)
            pes = parse_valuation_payload_with_period(
                pe_body, symbol, month, observed_name or company_name)
            if set(pes) - set(closes):
                raise DataValidationError("valuation date has no same-day official close")
            valid_dates = [day for day, point in pes.items() if point.official_pe is not None]
            if valid_dates and first_pe is None:
                first_pe = min(valid_dates)
            unavailable_close = sorted(day for day, value in closes.items() if value is None)
            numeric_close_dates = {day for day, value in closes.items() if value is not None}
            missing = sorted(numeric_close_dates - set(pes))
            if missing:
                incomplete.append(month.strftime("%Y-%m"))
            for endpoint, body, url, retrieved, status in (
                ("tradingStock", close_body, close_url, close_time, close_status),
                ("peQryStock", pe_body, pe_url, pe_time, pe_status),
            ):
                if status != "CACHE_HIT":
                    store_cached_month(
                        root / endpoint, source_symbol=symbol,
                        canonical_symbol=canonical,
                        month_identifier=month.strftime("%Y%m%d"), source_url=url,
                        retrieved_at=retrieved, http_status=200, body=body, source=TPEX)
            records.extend(ValuationObservation(
                symbol=symbol, trade_date=day, official_close=value,
                official_pe=pes[day].official_pe if day in pes else None,
                close_source_url=close_url, pe_source_url=pe_url,
                financial_report_period_raw=(
                    pes[day].financial_report_period_raw if day in pes else None),
                reference_period_end=(pes[day].reference_period_end if day in pes else None),
                canonical_symbol=canonical, market=TPEX,
                company_name=company_name or observed_name or "",
            ) for day, value in closes.items() if value is not None and start <= day <= end)
            result = {
                "month": month.strftime("%Y-%m"), "market": TPEX,
                "canonical_symbol": canonical, "close_status": close_status,
                "pe_status": pe_status, "close_count": len(numeric_close_dates),
                "source_close_row_count": len(closes), "pe_count": len(pes),
                "valid_pe_count": len(valid_dates),
                "unavailable_close_dates": [day.isoformat() for day in unavailable_close],
                "missing_pe_dates": [day.isoformat() for day in missing],
                "close_source_url": close_url, "pe_source_url": pe_url,
                "close_sha256": raw_hash(close_body), "pe_sha256": raw_hash(pe_body),
                "close_retrieved_at": close_time, "pe_retrieved_at": pe_time,
            }
            results.append(result)
        except Exception as exc:
            results.append({"month": month.strftime("%Y-%m"), "status": "FAILED",
                            "error_code": type(exc).__name__, "market": TPEX})
            manifest(False)
            raise
        manifest(False)
        if progress:
            progress(results[-1])
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    manifest(True)
    if not records or first_pe is None:
        raise DataValidationError("no official TPEx valuation history for requested symbol/window")
    records = [row for row in records if row.trade_date >= first_pe]
    return ValuationHistory(tuple(records), tuple(results), first_pe, tuple(incomplete))
