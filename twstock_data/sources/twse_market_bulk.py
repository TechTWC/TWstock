from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..dataset import ResearchMarketDataset, build_research_dataset
from ..errors import (
    DataValidationError,
    MalformedSourceError,
    MarketDataError,
    SourceUnavailableError,
)
from ..http import HttpTransport, get_with_retry
from ..models import MarketDataRecord, ReconciliationResult, SourceState, SourceTier
from ..normalization import parse_float, parse_int, raw_hash, utc_now_iso, validate_date_range


TWSE_MI_INDEX_ENDPOINT = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
_TITLE_DATE_RE = re.compile(r"^(\d{2,3})年(\d{2})月(\d{2})日")
_SYMBOL_RE = re.compile(r"^[0-9]{4}$")
_NO_DATA_PREFIX = "很抱歉，沒有符合條件的資料"


def build_market_day_url(trade_date: date) -> str:
    return TWSE_MI_INDEX_ENDPOINT + "?" + urlencode(
        {
            "date": trade_date.strftime("%Y%m%d"),
            "type": "ALLBUT0999",
            "response": "json",
        }
    )


def parse_twse_market_day_payload(
    body: bytes,
    *,
    requested_date: date,
    source_url: str,
    retrieved_at: str,
) -> tuple[MarketDataRecord, ...]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MalformedSourceError("invalid TWSE MI_INDEX JSON") from error
    if not isinstance(payload, dict):
        raise MalformedSourceError("TWSE MI_INDEX payload must be an object")
    if str(payload.get("stat", "")).startswith(_NO_DATA_PREFIX):
        return ()
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise MalformedSourceError("TWSE MI_INDEX tables must be an array")
    required = (
        "證券代號",
        "證券名稱",
        "成交股數",
        "成交筆數",
        "成交金額",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
    )
    market_table = None
    for table in tables:
        if not isinstance(table, dict):
            continue
        fields = table.get("fields")
        if isinstance(fields, list) and all(field in fields for field in required):
            market_table = table
            break
    if market_table is None:
        raise DataValidationError("TWSE MI_INDEX daily-stock table is missing")
    title = str(market_table.get("title", "")).strip()
    match = _TITLE_DATE_RE.match(title)
    if match is None:
        raise DataValidationError("TWSE MI_INDEX title date is missing")
    title_date = date(int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3)))
    if title_date != requested_date:
        raise DataValidationError("TWSE MI_INDEX response date mismatch")
    fields = market_table["fields"]
    indexes = {field: fields.index(field) for field in required}
    rows = market_table.get("data")
    if not isinstance(rows, list):
        raise MalformedSourceError("TWSE MI_INDEX daily-stock data must be an array")
    content_hash = raw_hash(body)
    records: list[MarketDataRecord] = []
    for row in rows:
        if not isinstance(row, list):
            raise MalformedSourceError("TWSE MI_INDEX row must be an array")
        symbol = str(row[indexes["證券代號"]]).strip()
        if not _SYMBOL_RE.fullmatch(symbol):
            continue
        price_values = tuple(
            str(row[indexes[field]]).replace(",", "").strip()
            for field in ("開盤價", "最高價", "最低價", "收盤價")
        )
        if any(value in {"", "--"} for value in price_values):
            continue
        records.append(
            MarketDataRecord(
                source="TWSE",
                source_tier=SourceTier.PRIMARY,
                source_symbol=symbol,
                canonical_symbol=f"{symbol}.TW",
                market="TW",
                trade_date=requested_date.isoformat(),
                traded_share_volume=parse_int(row[indexes["成交股數"]], "成交股數"),
                official_traded_value_twd=parse_int(row[indexes["成交金額"]], "成交金額"),
                open_price=parse_float(row[indexes["開盤價"]], "開盤價"),
                high_price=parse_float(row[indexes["最高價"]], "最高價"),
                low_price=parse_float(row[indexes["最低價"]], "最低價"),
                close_price=parse_float(row[indexes["收盤價"]], "收盤價"),
                transaction_count=parse_int(row[indexes["成交筆數"]], "成交筆數"),
                retrieved_at=retrieved_at,
                source_reference=source_url,
                raw_content_hash=content_hash,
            )
        )
    if not records:
        raise DataValidationError("TWSE MI_INDEX trading-day table contains no common stocks")
    return tuple(sorted(records, key=lambda item: item.source_symbol))


def fetch_twse_bulk_research_datasets(
    symbols: Iterable[str],
    requested_start: str,
    requested_end: str,
    *,
    cache_dir: Path,
    transport: HttpTransport | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    max_new_market_days: int = 10,
    refresh_date: date | None = None,
) -> dict[str, ResearchMarketDataset]:
    start, end = validate_date_range(requested_start, requested_end)
    wanted = frozenset(symbols)
    if not wanted or any(not _SYMBOL_RE.fullmatch(symbol) for symbol in wanted):
        raise DataValidationError("bulk TWSE symbols must be nonempty four-digit codes")
    if max_new_market_days < 0:
        raise ValueError("max_new_market_days must be nonnegative")
    today = refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()
    end = min(end, today)
    dates = tuple(_weekdays(start, end))
    cache_root = cache_dir / ".daily-mi-index"
    cached_days: dict[date, tuple[MarketDataRecord, ...]] = {}
    missing_days: list[date] = []
    for day in dates:
        if day == today:
            missing_days.append(day)
            continue
        cached = _try_load_cached_day(cache_root, day)
        if cached is None:
            missing_days.append(day)
        else:
            cached_days[day] = cached
    missing = tuple(missing_days)
    if len(missing) > max_new_market_days:
        raise DataValidationError(
            "bulk TWSE cache needs "
            f"{len(missing)} new weekdays, exceeding --max-new-market-days "
            f"{max_new_market_days}; raise the explicit bootstrap limit"
        )
    grouped: dict[str, list[MarketDataRecord]] = defaultdict(list)
    for day in dates:
        if day in cached_days:
            records = cached_days[day]
        else:
            records = _load_or_fetch_day(
                day,
                cache_root=cache_root,
                transport=transport,
                timeout=timeout,
                retries=retries,
                force_refresh=day == today,
            )
        for record in records:
            if record.source_symbol in wanted:
                grouped[record.source_symbol].append(record)
    datasets: dict[str, ResearchMarketDataset] = {}
    for symbol, records in grouped.items():
        datasets[symbol] = build_research_dataset(
            ReconciliationResult(
                SourceState.PRIMARY_VERIFIED,
                tuple(records),
                cross_check_unavailable=True,
            ),
            requested_symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
        )
    return datasets


def _load_or_fetch_day(
    day: date,
    *,
    cache_root: Path,
    transport: HttpTransport | None,
    timeout: float,
    retries: int,
    force_refresh: bool = False,
) -> tuple[MarketDataRecord, ...]:
    raw_path, metadata_path = _cache_paths(cache_root, day)
    url = build_market_day_url(day)
    if not force_refresh:
        cached = _try_load_cached_day(cache_root, day)
        if cached is not None:
            return cached
    response = get_with_retry(url, transport, timeout, retries)
    retrieved_at = utc_now_iso()
    records = parse_twse_market_day_payload(
        response.body,
        requested_date=day,
        source_url=url,
        retrieved_at=retrieved_at,
    )
    metadata = json.dumps(
        {
            "schema_version": "TWSTOCK-TWSE-MI-INDEX-CACHE-001",
            "requested_date": day.isoformat(),
            "source_url": url,
            "retrieved_at": retrieved_at,
            "http_status": response.status,
            "sha256": hashlib.sha256(response.body).hexdigest(),
            "record_count": len(records),
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    _atomic_write(raw_path, response.body)
    _atomic_write(metadata_path, metadata)
    return records


def _try_load_cached_day(
    cache_root: Path, day: date
) -> tuple[MarketDataRecord, ...] | None:
    raw_path, metadata_path = _cache_paths(cache_root, day)
    if not raw_path.is_file() or not metadata_path.is_file():
        return None
    url = build_market_day_url(day)
    try:
        body = raw_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            not isinstance(metadata, dict)
            or metadata.get("schema_version")
            != "TWSTOCK-TWSE-MI-INDEX-CACHE-001"
            or metadata.get("http_status", 200) != 200
            or metadata.get("sha256") != hashlib.sha256(body).hexdigest()
            or metadata.get("requested_date") != day.isoformat()
            or metadata.get("source_url") != url
        ):
            return None
        retrieved_at = metadata.get("retrieved_at")
        if not isinstance(retrieved_at, str) or not retrieved_at:
            return None
        records = parse_twse_market_day_payload(
            body,
            requested_date=day,
            source_url=url,
            retrieved_at=retrieved_at,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, MarketDataError):
        return None
    if metadata.get("record_count") != len(records):
        return None
    return records


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _cache_paths(cache_root: Path, day: date) -> tuple[Path, Path]:
    stem = f"twse_mi_index_{day.strftime('%Y%m%d')}"
    return cache_root / f"{stem}.raw", cache_root / f"{stem}.metadata.json"


def _weekdays(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)
