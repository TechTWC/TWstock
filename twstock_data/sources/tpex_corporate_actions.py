"""Bounded official TPEx corporate-action range adapter.

An empty result is accepted only after status, echoed query interval, table
schema, row widths, and official row count all validate.  The source has no
pagination controls; any pagination-shaped response is rejected.
"""
from __future__ import annotations

from datetime import date, datetime
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
from ..twse_incremental_cache import load_cached_month, store_cached_month
from .security_identity import TPEX, canonical_symbol, validate_symbol
from .twse_corporate_actions import (
    CAPITAL_REDUCTION_CASH_RETURN, CAPITAL_REDUCTION_LOSS,
    CORPORATE_ACTION_REVIEW_REQUIRED, FACE_VALUE_CHANGE_REVERSE_SPLIT,
    FACE_VALUE_CHANGE_SPLIT, NORMALIZATION_READY, STOCK_DIVIDEND,
    UNSUPPORTED_ACTION, CorporateActionEvent, CorporateActionHistory,
    mark_conflicting_duplicates,
)

BASE_URL = "https://www.tpex.org.tw/www/zh-tw/bulletin/"
EX_RIGHT_HISTORY_START = date(2008, 1, 2)
CAPITAL_REDUCTION_HISTORY_START = date(2013, 1, 1)
PAR_VALUE_HISTORY_START = date(2019, 9, 9)

FAMILIES = {
    "ex_right": ("exDailyQ", EX_RIGHT_HISTORY_START),
    "capital_reduction": ("revivt", CAPITAL_REDUCTION_HISTORY_START),
    "par_value_change": ("pvChgRslt", PAR_VALUE_HISTORY_START),
}


def build_url(family: str, start: date, end: date) -> str:
    if family not in FAMILIES or start > end:
        raise DataValidationError("invalid TPEx corporate-action request")
    endpoint, supported = FAMILIES[family]
    if start < supported:
        raise DataValidationError("TPEx corporate-action request precedes source history")
    return BASE_URL + endpoint + "?" + urlencode({
        "startDate": start.strftime("%Y/%m/%d"),
        "endDate": end.strftime("%Y/%m/%d"),
        "response": "json",
    })


def _roc_date(value: object) -> date:
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        except ValueError as exc:
            raise MalformedSourceError("invalid TPEx corporate-action calendar date") from exc
    match = re.fullmatch(r"(\d{2,3})(?:/)?(\d{2})(?:/)?(\d{2})", text)
    if not match:
        raise MalformedSourceError(f"malformed TPEx corporate-action date: {value!r}")
    try:
        return date(int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise MalformedSourceError("invalid TPEx corporate-action calendar date") from exc


def _number(value: object, field: str, *, unavailable=False) -> float | None:
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "--", "---", "N/A", "－"}:
        if unavailable:
            return None
        raise MalformedSourceError(f"missing TPEx {field}")
    if not re.fullmatch(r"-?(?:\d+)(?:\.\d+)?", text):
        raise MalformedSourceError(f"malformed TPEx {field}")
    result = float(text)
    if not math.isfinite(result):
        raise MalformedSourceError(f"nonfinite TPEx {field}")
    return result


def _payload(body: bytes, family: str, start: date, end: date):
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid TPEx corporate-action JSON") from exc
    if not isinstance(payload, dict) or str(payload.get("stat", "")).lower() != "ok":
        raise MalformedSourceError("unexpected TPEx corporate-action status")
    if any(key in payload for key in ("next", "nextPage", "page", "offset", "cursor")):
        raise MalformedSourceError("unknown TPEx corporate-action pagination contract")
    raw_range = payload.get("date")
    if not isinstance(raw_range, str) or raw_range.count("~") != 1:
        raise MalformedSourceError("missing TPEx corporate-action response interval")
    left, right = raw_range.split("~")
    if _roc_date(left) != start or _roc_date(right) != end:
        raise DataValidationError("TPEx corporate-action response interval mismatch")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        raise MalformedSourceError("TPEx corporate-action response omits tables")
    date_aliases = {
        "ex_right": {"除權息日期"},
        "capital_reduction": {"恢復買賣日期"},
        "par_value_change": {"恢復買賣日期"},
    }[family]
    candidates = []
    for raw in tables:
        if not isinstance(raw, dict):
            raise MalformedSourceError("invalid TPEx corporate-action table")
        fields, rows = raw.get("fields"), raw.get("data")
        if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
            raise MalformedSourceError("invalid TPEx corporate-action fields")
        if len(fields) != len(set(fields)) or not isinstance(rows, list):
            raise MalformedSourceError("invalid TPEx corporate-action schema")
        declared = str(raw.get("totalCount", "")).replace(",", "").strip()
        if not declared.isdigit() or int(declared) != len(rows):
            raise MalformedSourceError("truncated TPEx corporate-action response")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(fields):
                raise MalformedSourceError("TPEx corporate-action row width mismatch")
        if date_aliases.intersection(fields) and {"代號", "股票代號", "證券代號"}.intersection(fields):
            candidates.append((fields, rows, int(declared)))
    if len(candidates) != 1:
        raise MalformedSourceError("missing or ambiguous TPEx corporate-action table")
    return payload, candidates[0]


def _field(fields: list[str], aliases: tuple[str, ...], label: str,
           *, optional=False) -> int | None:
    indices = [fields.index(item) for item in aliases if item in fields]
    if len(indices) > 1 or (not indices and not optional):
        raise MalformedSourceError(f"missing or ambiguous TPEx {label} field")
    return indices[0] if indices else None


def parse_events(body: bytes, family: str, symbol: str, start: date, end: date,
                 source_url: str, retrieved_at: str,
                 expected_name: str | None = None):
    validate_symbol(symbol)
    _, (fields, rows, _) = _payload(body, family, start, end)
    date_i = _field(fields, ("除權息日期",) if family == "ex_right" else ("恢復買賣日期",), "date")
    code_i = _field(fields, ("代號", "股票代號", "證券代號"), "symbol")
    name_i = _field(fields, ("名稱", "股票名稱", "證券名稱"), "name")
    pre_i = _field(fields, ("除權息前收盤價",) if family == "ex_right" else
                   ("最後交易日之收盤價格", "停止買賣前收盤價格"), "pre-event close")
    ref_i = _field(fields, ("除權息參考價",) if family == "ex_right" else
                   ("減資恢復買賣開始日參考價格", "恢復買賣開始參考價", "恢復買賣參考價"),
                   "reference price")
    type_i = (_field(fields, ("權/息",), "rights type") if family == "ex_right" else
              _field(fields, ("減資原因",), "reduction type") if family == "capital_reduction" else None)
    cash_i = _field(fields, ("現金股利",), "cash dividend", optional=True)
    ratio_i = _field(fields, ("減資換股率", "換股率", "每仟股換發新股數"),
                     "reduction ratio", optional=True)
    return_i = _field(fields, ("每股退還股款", "退還股款"), "cash return", optional=True)
    events = []
    previous: date | None = None
    for row in rows:
        effective = _roc_date(row[date_i])
        if not start <= effective <= end:
            raise DataValidationError("TPEx corporate-action row outside response interval")
        if previous is not None and effective < previous:
            raise DataValidationError("unordered TPEx corporate-action rows")
        previous = effective
        if str(row[code_i]).strip() != symbol:
            continue
        name = str(row[name_i]).strip()
        if expected_name and name.rstrip("*").strip() != expected_name.rstrip("*").strip():
            raise DataValidationError("TPEx corporate-action company identity mismatch")
        pre = _number(row[pre_i], "pre-event close", unavailable=True)
        ref = _number(row[ref_i], "reference price", unavailable=True)
        action = UNSUPPORTED_ACTION
        factor = None
        cash_return = None
        bonus_rate = None
        reduction_type = None
        status = CORPORATE_ACTION_REVIEW_REQUIRED
        raw_type = "變更股票面額" if type_i is None else str(row[type_i]).strip()
        if family == "ex_right":
            cash = (_number(row[cash_i], "cash dividend", unavailable=True)
                    if cash_i is not None else None)
            canonical_type = raw_type.replace(" ", "").removeprefix("除")
            if canonical_type == "息":
                continue
            if canonical_type not in {"權", "權息"}:
                raise MalformedSourceError("unknown TPEx rights classification")
            action = STOCK_DIVIDEND
            if pre is not None and ref is not None and (cash is not None or canonical_type == "權"):
                cash_value = cash or 0.0
                factor = (pre - cash_value) / ref
                if not math.isfinite(factor) or factor <= 0:
                    raise DataValidationError("invalid TPEx rights share factor")
                bonus_rate = factor - 1
            # exDailyQ does not distinguish a pro-rata bonus issue from paid or
            # otherwise complex rights.  Retain the canonical event, but do not
            # let that ambiguity enter normalization without detail evidence.
        elif family == "capital_reduction":
            reduction_type = raw_type
            if raw_type in {"彌補虧損", "虧損減資"}:
                action = CAPITAL_REDUCTION_LOSS
                if ratio_i is not None:
                    raw_ratio = _number(row[ratio_i], "reduction ratio")
                    factor = raw_ratio / 1000 if raw_ratio and raw_ratio > 10 else raw_ratio
                elif pre is not None and ref is not None:
                    factor = pre / ref
                status = NORMALIZATION_READY if factor is not None else status
            elif raw_type in {"現金減資", "退還股款"}:
                action = CAPITAL_REDUCTION_CASH_RETURN
                cash_return = (_number(row[return_i], "cash return", unavailable=True)
                               if return_i is not None else None)
                if ratio_i is not None:
                    raw_ratio = _number(row[ratio_i], "reduction ratio")
                    factor = raw_ratio / 1000 if raw_ratio and raw_ratio > 10 else raw_ratio
                if factor is not None and cash_return is not None:
                    status = NORMALIZATION_READY
            else:
                action = UNSUPPORTED_ACTION
        else:
            if pre is not None and ref is not None:
                factor = pre / ref
                if not math.isfinite(factor) or factor <= 0:
                    raise DataValidationError("invalid TPEx face-value factor")
                action = (FACE_VALUE_CHANGE_SPLIT if factor > 1
                          else FACE_VALUE_CHANGE_REVERSE_SPLIT if factor < 1
                          else UNSUPPORTED_ACTION)
                status = NORMALIZATION_READY if action != UNSUPPORTED_ACTION else status
        events.append(CorporateActionEvent(
            symbol=symbol, effective_date=effective, action_type=action,
            share_factor=factor, cash_return_per_share=cash_return,
            pre_event_close=pre, official_reference_price=ref,
            source_url=source_url, detail_source_url=source_url,
            retrieved_at=retrieved_at, raw_hash=raw_hash(body), status=status,
            bonus_share_rate=bonus_rate, resume_date=(effective if family != "ex_right" else None),
            reduction_type=reduction_type, derived=factor is not None,
            derivation_formula=(
                "(pre_event_close - cash_dividend) / official_reference_price"
                if family == "ex_right" else
                "pre_event_close / official_reference_price" if factor is not None else None),
            source_fields=tuple(sorted({"company_name": name, "raw_type": raw_type,
                                        "market": TPEX}.items())),
        ))
    return tuple(events)


def fetch_corporate_action_history(
        symbol: str, start: date, end: date, cache_dir: Path, *,
        company_name: str | None = None, transport: HttpTransport | None = None,
        timeout=30.0, retries=2, request_interval=1.0,
        refresh_date: date | None = None, progress=None) -> CorporateActionHistory:
    validate_symbol(symbol)
    if start > end:
        raise DataValidationError("invalid TPEx corporate-action history window")
    root = Path(cache_dir)
    canonical = canonical_symbol(symbol, TPEX)
    current_year = (refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()).year
    events = []
    results = []
    last_request: float | None = None

    def request(namespace: str, identifier: str, url: str, refresh: bool):
        nonlocal last_request
        cached = None if refresh else load_cached_month(
            root / namespace, source_symbol=symbol, canonical_symbol=canonical,
            month_identifier=identifier, expected_source_url=url, source=TPEX)
        if cached is not None:
            return cached.body, cached.retrieved_at, "CACHE_HIT", cached.sha256
        if last_request is not None:
            time.sleep(max(0, request_interval - (time.monotonic() - last_request)))
        response = get_with_retry(url, transport, timeout, retries, backoff=2)
        last_request = time.monotonic()
        retrieved = utc_now_iso()
        store_cached_month(
            root / namespace, source_symbol=symbol, canonical_symbol=canonical,
            month_identifier=identifier, source_url=url, retrieved_at=retrieved,
            http_status=response.status, body=response.body, source=TPEX)
        return response.body, retrieved, "FETCHED", raw_hash(response.body)

    for family, (_, supported) in FAMILIES.items():
        for year in range(max(start.year, supported.year), end.year + 1):
            window_start = max(start, supported, date(year, 1, 1))
            window_end = min(end, date(year, 12, 31))
            if window_start > window_end:
                continue
            url = build_url(family, window_start, window_end)
            body, retrieved, status, digest = request(
                f"corporate_actions/{family}/summary",
                f"{window_start:%Y%m%d}_{window_end:%Y%m%d}", url,
                year == current_year)
            parsed = parse_events(body, family, symbol, window_start, window_end,
                                  url, retrieved, company_name)
            events.extend(parsed)
            result = {
                "source": FAMILIES[family][0], "family": family,
                "market": TPEX, "year": year, "status": status,
                "sha256": digest, "event_count": len(parsed),
                "source_url": url, "query_start": window_start.isoformat(),
                "query_end": window_end.isoformat(), "coverage_verified": True,
            }
            results.append(result)
            if progress:
                progress(result)
    return CorporateActionHistory(mark_conflicting_duplicates(events), tuple(results))
