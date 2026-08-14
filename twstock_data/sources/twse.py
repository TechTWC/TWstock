from __future__ import annotations
import json, re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from ..http import HttpTransport, get_with_retry
from ..models import MarketDataRecord, SourceTier
from ..normalization import canonical_symbol, parse_float, parse_int, raw_hash, utc_now_iso, validate_date_range
from ..raw_cache import preserve_raw_response
from ..errors import (
    DataValidationError,
    DuplicateTradeDateError,
    MalformedSourceError,
    MarketDataError,
)
from ..twse_incremental_cache import (
    load_cached_month,
    store_cached_month,
    write_cache_run_manifest,
)

TWSE_STOCK_DAY_ENDPOINT = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
FIELDS = ("日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "成交筆數")

def _is_official_non_trading_row(row: list[object], idx: dict[str, int]) -> bool:
    """Identify TWSE's internally consistent placeholder for a day without trades."""
    try:
        zero_fields = ("成交股數", "成交金額", "成交筆數")
        price_fields = ("開盤價", "最高價", "最低價", "收盤價")
        return all(
            str(row[idx[field]]).replace(",", "").strip() == "0"
            for field in zero_fields
        ) and all(str(row[idx[field]]).strip() == "--" for field in price_fields)
    except IndexError:
        return False

def _roc_to_iso(text: str) -> str:
    y, m, d = [int(p) for p in text.split("/")]
    return date(y + 1911, m, d).isoformat()

def _month_starts(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = start.replace(day=1)
    last = end.replace(day=1)
    while current <= last:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months

def _verify_response_identity(payload: dict, source_symbol: str) -> None:
    candidates = []
    for key in ("stockNo", "stock_no", "stock_id", "stockCode", "stock_code"):
        value = payload.get(key)
        if value is not None:
            candidates.append(str(value).strip())
    title = str(payload.get("title", ""))
    title_match = re.search(r"(?:^|[^0-9])([0-9]{4,6})(?:[^0-9]|$)", title)
    if title_match:
        candidates.append(title_match.group(1))
    if not candidates:
        raise MalformedSourceError("missing TWSE response identity")
    if source_symbol not in candidates:
        raise DataValidationError(f"TWSE response identity mismatch for requested symbol {source_symbol}")

def build_url(source_symbol: str, month: str) -> str:
    return TWSE_STOCK_DAY_ENDPOINT + "?" + urlencode({"response": "json", "date": month, "stockNo": source_symbol})


def _parse_month_response(
    body: bytes,
    *,
    source_symbol: str,
    month_identifier: str,
    window_start: str,
    window_end: str,
    source_url: str,
    retrieved_at: str,
    require_month_identity: bool,
) -> tuple[MarketDataRecord, ...]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MalformedSourceError(
            f"invalid TWSE JSON for {source_symbol} {month_identifier}"
        ) from error
    if (
        require_month_identity
        and str(payload.get("date", "")).strip() != month_identifier
    ):
        raise DataValidationError(
            f"TWSE response month mismatch for requested month {month_identifier}"
        )
    try:
        return parse_twse_payload(
            payload,
            source_symbol,
            window_start,
            window_end,
            body,
            source_url,
            retrieved_at,
        )
    except MarketDataError:
        raise
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise MalformedSourceError(
            f"invalid TWSE payload for {source_symbol} {month_identifier}"
        ) from error

def fetch_twse_daily(
    source_symbol: str,
    start: str,
    end: str,
    transport: HttpTransport | None = None,
    timeout: float = 10,
    retries: int = 2,
    raw_cache_dir: Path | str | None = None,
    incremental_cache: bool = False,
    cache_refresh_date: date | None = None,
) -> tuple[MarketDataRecord, ...]:
    start_date, end_date = validate_date_range(start, end)
    canonical = canonical_symbol(source_symbol, "TW")
    cache_root = (
        Path(raw_cache_dir)
        if incremental_cache and raw_cache_dir is not None
        else None
    )
    refresh_date = cache_refresh_date or datetime.now(
        ZoneInfo("Asia/Taipei")
    ).date()
    requested_first_month = start_date.replace(day=1)
    requested_last_month = end_date.replace(day=1)
    actual_current_month = refresh_date.replace(day=1)
    refresh_month = (
        actual_current_month
        if requested_first_month <= actual_current_month <= requested_last_month
        else None
    )
    cache_results: list[dict[str, object]] = []
    combined: list[MarketDataRecord] = []
    seen: set[str] = set()
    for month in _month_starts(start_date, end_date):
        month_param = month.strftime("%Y%m%d")
        url = build_url(source_symbol, month_param)
        next_month = month.replace(year=month.year + 1, month=1) if month.month == 12 else month.replace(month=month.month + 1)
        month_end = next_month - timedelta(days=1)
        window_start = max(start_date, month).isoformat()
        window_end = min(end_date, month_end).isoformat()
        cached = None
        cached_records: tuple[MarketDataRecord, ...] | None = None
        invalid_cache = False
        if cache_root is not None and month != refresh_month:
            try:
                cached = load_cached_month(
                    cache_root,
                    source_symbol=source_symbol,
                    canonical_symbol=canonical,
                    month_identifier=month_param,
                    expected_source_url=url,
                )
            except DataValidationError:
                invalid_cache = True
            if cached is not None:
                try:
                    cached_records = _parse_month_response(
                        cached.body,
                        source_symbol=source_symbol,
                        month_identifier=month_param,
                        window_start=window_start,
                        window_end=window_end,
                        source_url=cached.source_url,
                        retrieved_at=cached.retrieved_at,
                        require_month_identity=True,
                    )
                except MarketDataError:
                    cached = None
                    invalid_cache = True

        fetched = cached is None
        if cached is not None:
            body = cached.body
            source_url = cached.source_url
            retrieved_at = cached.retrieved_at
            month_records = cached_records or ()
            cache_status = (
                "IMPORTED_LEGACY_CACHE"
                if cached.origin == "LEGACY_V0_1_CACHE"
                else "CACHE_HIT"
            )
        else:
            try:
                response = get_with_retry(url, transport, timeout, retries)
            except MarketDataError as error:
                cache_results.append(
                    {
                        "month": month_param,
                        "status": "FAILED_FETCH",
                        "error_code": type(error).__name__,
                    }
                )
                _write_incremental_manifest(
                    cache_root,
                    source_symbol,
                    start,
                    end,
                    refresh_month,
                    cache_results,
                    completed=False,
                )
                raise
            body = response.body
            source_url = response.url
            retrieved_at = utc_now_iso()
            cache_status = (
                "REFRESHED_CURRENT"
                if month == refresh_month
                else "REFETCHED_INVALID"
                if invalid_cache
                else "FETCHED_MISSING"
            )
            preserve_raw_response(
                raw_cache_dir,
                source="TWSE",
                source_tier=SourceTier.PRIMARY.value,
                source_symbol=source_symbol,
                canonical_symbol=canonical,
                requested_start=start,
                requested_end=end,
                retrieved_at=retrieved_at,
                source_url=source_url,
                http_status=response.status,
                body=body,
                request_identifier=f"twse_{month_param}",
            )
            try:
                month_records = _parse_month_response(
                    body,
                    source_symbol=source_symbol,
                    month_identifier=month_param,
                    window_start=window_start,
                    window_end=window_end,
                    source_url=source_url,
                    retrieved_at=retrieved_at,
                    require_month_identity=incremental_cache,
                )
            except MarketDataError as error:
                cache_results.append(
                    {
                        "month": month_param,
                        "status": "FAILED_VALIDATION",
                        "error_code": type(error).__name__,
                    }
                )
                _write_incremental_manifest(
                    cache_root,
                    source_symbol,
                    start,
                    end,
                    refresh_month,
                    cache_results,
                    completed=False,
                )
                raise

        if cache_root is not None and (
            fetched or cache_status == "IMPORTED_LEGACY_CACHE"
        ):
            store_cached_month(
                cache_root,
                source_symbol=source_symbol,
                canonical_symbol=canonical,
                month_identifier=month_param,
                source_url=source_url,
                retrieved_at=retrieved_at,
                http_status=response.status if fetched else 200,
                body=body,
            )
        cache_results.append(
            {
                "month": month_param,
                "status": cache_status,
                "record_count": len(month_records),
                "sha256": raw_hash(body),
            }
        )
        _write_incremental_manifest(
            cache_root,
            source_symbol,
            start,
            end,
            refresh_month,
            cache_results,
            completed=False,
        )
        for record in month_records:
            if record.trade_date in seen:
                raise DuplicateTradeDateError(f"duplicate TWSE trade date across monthly responses {record.trade_date}")
            seen.add(record.trade_date)
            combined.append(record)
    _write_incremental_manifest(
        cache_root,
        source_symbol,
        start,
        end,
        refresh_month,
        cache_results,
        completed=True,
    )
    return tuple(sorted(combined, key=lambda r: r.trade_date))


def _write_incremental_manifest(
    cache_root: Path | None,
    source_symbol: str,
    requested_start: str,
    requested_end: str,
    refresh_month: date | None,
    cache_results: list[dict[str, object]],
    *,
    completed: bool,
) -> None:
    if cache_root is None:
        return
    write_cache_run_manifest(
        cache_root,
        source_symbol=source_symbol,
        requested_start=requested_start,
        requested_end=requested_end,
        refresh_month=(
            refresh_month.strftime("%Y%m%d") if refresh_month is not None else None
        ),
        month_results=cache_results,
        completed=completed,
    )

def parse_twse_payload(
    payload: dict,
    source_symbol: str,
    start: str,
    end: str,
    raw: bytes | None = None,
    source_reference: str = TWSE_STOCK_DAY_ENDPOINT,
    retrieved_at: str | None = None,
) -> tuple[MarketDataRecord, ...]:
    validate_date_range(start, end)
    if not isinstance(payload, dict) or payload.get("stat") not in ("OK", "很抱歉，沒有符合條件的資料!") or "fields" not in payload or "data" not in payload:
        raise MalformedSourceError("unexpected TWSE STOCK_DAY schema")
    _verify_response_identity(payload, source_symbol)
    fields = tuple(payload["fields"])
    for field in FIELDS:
        if field not in fields:
            raise MalformedSourceError(f"missing TWSE field {field}")
    idx = {field: fields.index(field) for field in FIELDS}
    seen: set[str] = set()
    out: list[MarketDataRecord] = []
    h = raw_hash(raw or json.dumps(payload, ensure_ascii=False))
    canonical = canonical_symbol(source_symbol, "TW")
    retrieved = retrieved_at or utc_now_iso()
    for row in payload["data"]:
        iso = _roc_to_iso(row[idx["日期"]])
        if not (start <= iso <= end):
            continue
        if iso in seen:
            raise DuplicateTradeDateError(f"duplicate TWSE trade date {iso}")
        seen.add(iso)
        if _is_official_non_trading_row(row, idx):
            continue
        out.append(MarketDataRecord(
            "TWSE", SourceTier.PRIMARY, source_symbol, canonical, "TW", iso,
            parse_int(row[idx["成交股數"]], "traded_share_volume"),
            parse_int(row[idx["成交金額"]], "official_traded_value_twd"),
            parse_float(row[idx["開盤價"]], "open_price"),
            parse_float(row[idx["最高價"]], "high_price"),
            parse_float(row[idx["最低價"]], "low_price"),
            parse_float(row[idx["收盤價"]], "close_price"),
            parse_int(row[idx["成交筆數"]], "transaction_count"),
            retrieved,
            source_reference,
            h,
        ))
    return tuple(out)
