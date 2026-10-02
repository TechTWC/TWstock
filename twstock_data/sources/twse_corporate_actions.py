"""Bounded official TWSE corporate-action adapter for PE normalization.

The v0.1 contract intentionally supports only pro-rata stock dividends/bonus
issues and ordinary-share capital reductions.  Complex rights or ambiguous
events are retained as review-required evidence and are never normalized.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
from .twse_valuation import parse_date, validate_symbol

BASE_URL = "https://www.twse.com.tw/rwd/zh/"
EX_RIGHT_HISTORY_START = date(2003, 5, 5)
CAPITAL_REDUCTION_HISTORY_START = date(2011, 1, 1)
# Backward-compatible name retained for callers that imported the original
# v0.1 constant.
REDUCTION_HISTORY_START = CAPITAL_REDUCTION_HISTORY_START

STOCK_DIVIDEND = "STOCK_DIVIDEND"
CAPITAL_REDUCTION_CASH_RETURN = "CAPITAL_REDUCTION_CASH_RETURN"
CAPITAL_REDUCTION_LOSS = "CAPITAL_REDUCTION_LOSS"
COMPLEX_RIGHTS_ISSUE = "COMPLEX_RIGHTS_ISSUE"
UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"

SUPPORTED_NORMALIZATION_ACTION_TYPES = frozenset({
    STOCK_DIVIDEND,
    CAPITAL_REDUCTION_CASH_RETURN,
    CAPITAL_REDUCTION_LOSS,
})

NORMALIZATION_READY = "NORMALIZATION_READY"
CORPORATE_ACTION_REVIEW_REQUIRED = "CORPORATE_ACTION_REVIEW_REQUIRED"
NORMALIZATION_REVIEW_REQUIRED = "NORMALIZATION_REVIEW_REQUIRED"


@dataclass(frozen=True)
class CorporateActionEvent:
    symbol: str
    effective_date: date
    action_type: str
    share_factor: float | None
    cash_return_per_share: float | None
    pre_event_close: float | None
    official_reference_price: float | None
    source_url: str
    detail_source_url: str
    retrieved_at: str
    raw_hash: str
    status: str
    bonus_share_rate: float | None = None
    cash_rights_rate: float | None = None
    resume_date: date | None = None
    reduction_type: str | None = None
    derived: bool = False
    derivation_formula: str | None = None
    source_fields: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        validate_symbol(self.symbol)
        if not isinstance(self.effective_date, date):
            raise DataValidationError("corporate-action effective date is invalid")
        if self.status not in (
                NORMALIZATION_READY, CORPORATE_ACTION_REVIEW_REQUIRED,
                NORMALIZATION_REVIEW_REQUIRED):
            raise DataValidationError("unknown corporate-action status")
        if self.share_factor is not None and (
                not math.isfinite(self.share_factor) or self.share_factor <= 0):
            raise DataValidationError("corporate-action share factor must be positive and finite")
        if self.status == NORMALIZATION_READY and self.share_factor is None:
            raise DataValidationError("normalization-ready event requires a share factor")
        if (self.status == NORMALIZATION_READY
                and self.action_type not in SUPPORTED_NORMALIZATION_ACTION_TYPES):
            raise DataValidationError(
                "normalization-ready event has unsupported corporate-action type")
        if not re.fullmatch(r"[0-9a-f]{64}", self.raw_hash):
            raise DataValidationError("corporate-action raw hash is invalid")
        if not self.source_url.startswith("https://www.twse.com.tw/"):
            raise DataValidationError("corporate-action source must be official TWSE HTTPS")
        if not self.detail_source_url.startswith("https://www.twse.com.tw/"):
            raise DataValidationError("corporate-action detail source must be official TWSE HTTPS")
        for value, field in (
                (self.cash_return_per_share, "cash return"),
                (self.bonus_share_rate, "bonus share rate"),
                (self.cash_rights_rate, "cash rights rate")):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise DataValidationError(f"corporate-action {field} must be nonnegative and finite")
        for value, field in ((self.pre_event_close, "pre-event close"),
                             (self.official_reference_price, "official reference price")):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise DataValidationError(f"corporate-action {field} must be positive and finite")


@dataclass(frozen=True)
class CorporateActionHistory:
    events: tuple[CorporateActionEvent, ...]
    request_results: tuple[dict, ...]


def build_ex_right_url(start: date, end: date) -> str:
    return BASE_URL + "exRight/TWT49U?" + urlencode({
        "response": "json", "startDate": start.strftime("%Y%m%d"),
        "endDate": end.strftime("%Y%m%d"),
    })


def build_ex_right_detail_url(symbol: str, effective_date: date) -> str:
    validate_symbol(symbol)
    return BASE_URL + "exRight/TWT49UDetail?" + urlencode({
        "response": "json", "STK_NO": symbol,
        "T1": effective_date.strftime("%Y%m%d"),
    })


def build_reduction_url(start: date, end: date) -> str:
    # ``reducation`` is the current official TWSE route spelling.
    return BASE_URL + "reducation/TWTAUU?" + urlencode({
        "response": "json", "startDate": start.strftime("%Y%m%d"),
        "endDate": end.strftime("%Y%m%d"),
    })


def build_reduction_detail_url(symbol: str, file_date: str) -> str:
    validate_symbol(symbol)
    if not re.fullmatch(r"\d{8}", file_date):
        raise DataValidationError("invalid reduction detail file date")
    return BASE_URL + "reducation/TWTAVUDetail?" + urlencode({
        "response": "json", "STK_NO": symbol, "FILE_DATE": file_date,
    })


def _payload(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid TWSE corporate-action JSON") from exc
    if not isinstance(payload, dict) or str(payload.get("stat", "")).lower() != "ok":
        raise MalformedSourceError("unexpected TWSE corporate-action status")
    fields, rows = payload.get("fields"), payload.get("data")
    if (not isinstance(fields, list) or not all(isinstance(field, str) for field in fields)
            or len(fields) != len(set(fields)) or not isinstance(rows, list)):
        raise MalformedSourceError("invalid TWSE corporate-action schema")
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise MalformedSourceError("TWSE corporate-action row width mismatch")
    return payload


def _rows(payload: dict, required: tuple[str, ...]):
    fields = payload["fields"]
    if any(field not in fields for field in required):
        raise MalformedSourceError("missing required TWSE corporate-action field")
    for row in payload["data"]:
        yield {field: row[fields.index(field)] for field in required}


def _number(value: object, field: str, *, unavailable=False) -> float | None:
    if unavailable and isinstance(value, str) and value.strip() in ("", "-", "--"):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MalformedSourceError(f"invalid {field}")
    text = str(value).strip()
    match = re.fullmatch(r"(-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?)", text)
    if not match:
        raise MalformedSourceError(f"malformed {field}: {value!r}")
    result = float(match.group(1).replace(",", ""))
    if not math.isfinite(result):
        raise MalformedSourceError(f"nonfinite {field}")
    return result


def _unit_number(value: object, field: str, units: str) -> float:
    if not isinstance(value, str):
        raise MalformedSourceError(f"invalid {field}")
    match = re.fullmatch(
        rf"\s*(-?(?:\d+|\d{{1,3}}(?:,\d{{3}})+)(?:\.\d+)?)\s*(?:{units})\s*",
        value,
    )
    if not match:
        raise MalformedSourceError(f"malformed {field}: {value!r}")
    result = float(match.group(1).replace(",", ""))
    if not math.isfinite(result):
        raise MalformedSourceError(f"nonfinite {field}")
    return result


def _combined_hash(summary_body: bytes, detail_body: bytes) -> str:
    return raw_hash(summary_body + b"\x00" + detail_body)


def parse_ex_right_events(summary_body: bytes, detail_bodies: dict[tuple[str, date], bytes],
                          symbol: str, source_url: str, retrieved_at: str):
    validate_symbol(symbol)
    payload = _payload(summary_body)
    required = ("資料日期", "股票代號", "除權息前收盤價", "除權息參考價",
                "權/息", "詳細資料")
    events = []
    for values in _rows(payload, required):
        row_symbol = str(values["股票代號"]).strip()
        if row_symbol != symbol:
            continue
        effective = parse_date(values["資料日期"])
        detail_token = re.fullmatch(
            r"\s*(\d{4})\s*,\s*(\d{8})\s*", str(values["詳細資料"]))
        if (not detail_token or detail_token.group(1) != symbol
                or detail_token.group(2) != effective.strftime("%Y%m%d")):
            raise DataValidationError("TWSE ex-right detail identity mismatch")
        key = (symbol, effective)
        if key not in detail_bodies:
            raise MalformedSourceError("missing TWSE ex-right detail response")
        detail_body = detail_bodies[key]
        detail = _payload(detail_body)
        detail_required = ("股票代號", "A. 按普通股股東持股比例每千股無償配股",
                           "B. 員工紅利轉增資", "C. (有償) 現金增資",
                           "按股東持股比例每千股認購")
        detail_rows = list(_rows(detail, detail_required))
        if len(detail_rows) != 1 or str(detail_rows[0]["股票代號"]).strip() != symbol:
            raise DataValidationError("TWSE ex-right detail symbol identity mismatch")
        item = detail_rows[0]
        bonus_per_thousand = _unit_number(
            item["A. 按普通股股東持股比例每千股無償配股"], "bonus shares", "股")
        employee_shares = _unit_number(item["B. 員工紅利轉增資"], "employee bonus shares", "股")
        cash_issue_shares = _unit_number(item["C. (有償) 現金增資"], "cash issue shares", "股")
        cash_rights_per_thousand = _unit_number(
            item["按股東持股比例每千股認購"], "cash rights shares", "股")
        bonus_rate = bonus_per_thousand / 1000
        cash_rights_rate = cash_rights_per_thousand / 1000
        if (bonus_rate == 0 and employee_shares == 0
                and cash_issue_shares == 0 and cash_rights_rate == 0):
            # A cash-dividend-only row does not change the share basis.
            continue
        share_factor = 1 + bonus_rate if bonus_rate > 0 else None
        complex_rights = employee_shares != 0 or cash_issue_shares != 0 or cash_rights_rate != 0
        if bonus_rate > 0:
            action_type = STOCK_DIVIDEND
            status = CORPORATE_ACTION_REVIEW_REQUIRED if complex_rights else NORMALIZATION_READY
        else:
            action_type = COMPLEX_RIGHTS_ISSUE
            status = CORPORATE_ACTION_REVIEW_REQUIRED
        detail_url = build_ex_right_detail_url(symbol, effective)
        events.append(CorporateActionEvent(
            symbol=symbol, effective_date=effective, action_type=action_type,
            share_factor=share_factor, cash_return_per_share=None,
            pre_event_close=_number(values["除權息前收盤價"], "pre-event close", unavailable=True),
            official_reference_price=_number(values["除權息參考價"], "reference price", unavailable=True),
            source_url=source_url, detail_source_url=detail_url,
            retrieved_at=retrieved_at, raw_hash=_combined_hash(summary_body, detail_body),
            status=status, bonus_share_rate=bonus_rate, cash_rights_rate=cash_rights_rate,
            source_fields=tuple(sorted({
                "rights_indicator": str(values["權/息"]),
                "bonus_shares_per_thousand": str(bonus_per_thousand),
                "employee_bonus_shares": str(employee_shares),
                "cash_issue_shares": str(cash_issue_shares),
                "cash_rights_per_thousand": str(cash_rights_per_thousand),
            }.items())),
        ))
    return tuple(events)


def parse_reduction_events(summary_body: bytes, detail_bodies: dict[tuple[str, str], bytes],
                           symbol: str, source_url: str, retrieved_at: str):
    validate_symbol(symbol)
    payload = _payload(summary_body)
    required = ("恢復買賣日期", "股票代號", "停止買賣前收盤價格", "恢復買賣參考價",
                "減資原因", "詳細資料")
    events = []
    for values in _rows(payload, required):
        row_symbol = str(values["股票代號"]).strip()
        if row_symbol != symbol:
            continue
        resume_date = parse_date(values["恢復買賣日期"])
        detail_token = re.fullmatch(r"\s*(\d{4})\s*,\s*(\d{8})\s*", str(values["詳細資料"]))
        if not detail_token or detail_token.group(1) != symbol:
            raise DataValidationError("TWSE reduction detail identity mismatch")
        file_date = detail_token.group(2)
        key = (symbol, file_date)
        if key not in detail_bodies:
            raise MalformedSourceError("missing TWSE reduction detail response")
        detail_body = detail_bodies[key]
        detail = _payload(detail_body)
        detail_required = ("股票代號：", "每壹仟股換發新股票：", "每股退還股款：",
                           "減資並(有償)現金增資：", "按股東持股比例每千股認購：")
        detail_rows = list(_rows(detail, detail_required))
        if len(detail_rows) != 1 or str(detail_rows[0]["股票代號："]).strip() != symbol:
            raise DataValidationError("TWSE reduction detail symbol identity mismatch")
        item = detail_rows[0]
        new_shares = _unit_number(item["每壹仟股換發新股票："], "new shares per thousand", "股")
        share_factor = new_shares / 1000
        cash_return = _unit_number(item["每股退還股款："], "cash return", "元/股|元／股")
        cash_issue = _unit_number(item["減資並(有償)現金增資："], "cash issue", "股")
        cash_rights = _unit_number(item["按股東持股比例每千股認購："], "cash rights", "股")
        reduction_type = str(values["減資原因"]).strip()
        if reduction_type == "退還股款":
            action_type = CAPITAL_REDUCTION_CASH_RETURN
        elif reduction_type == "彌補虧損":
            action_type = CAPITAL_REDUCTION_LOSS
        else:
            action_type = UNSUPPORTED_ACTION
        if action_type == UNSUPPORTED_ACTION:
            status = CORPORATE_ACTION_REVIEW_REQUIRED
        elif cash_issue != 0 or cash_rights != 0:
            status = CORPORATE_ACTION_REVIEW_REQUIRED
        else:
            status = NORMALIZATION_READY
        detail_url = build_reduction_detail_url(symbol, file_date)
        events.append(CorporateActionEvent(
            symbol=symbol, effective_date=resume_date, action_type=action_type,
            share_factor=share_factor, cash_return_per_share=cash_return,
            pre_event_close=_number(values["停止買賣前收盤價格"], "pre-event close", unavailable=True),
            official_reference_price=_number(values["恢復買賣參考價"], "reference price", unavailable=True),
            source_url=source_url, detail_source_url=detail_url,
            retrieved_at=retrieved_at, raw_hash=_combined_hash(summary_body, detail_body),
            status=status, resume_date=resume_date, reduction_type=reduction_type,
            source_fields=tuple(sorted({
                "new_shares_per_thousand": str(new_shares),
                "cash_issue_shares": str(cash_issue),
                "cash_rights_per_thousand": str(cash_rights),
                "detail_file_date": file_date,
            }.items())),
        ))
    return tuple(events)


def mark_conflicting_duplicates(events):
    output = []
    groups = {}
    for event in events:
        groups.setdefault((event.symbol, event.effective_date), []).append(event)
    for group in groups.values():
        identities = {(event.action_type, event.share_factor, event.cash_return_per_share)
                      for event in group}
        if len(identities) > 1:
            output.extend(replace(event, status=CORPORATE_ACTION_REVIEW_REQUIRED)
                          for event in group)
        else:
            output.append(group[0])
    return tuple(sorted(output, key=lambda event: (event.effective_date, event.action_type)))


def fetch_ex_right_events(symbol: str, start: date, end: date, *,
                          transport: HttpTransport | None = None, timeout=30, retries=2):
    validate_symbol(symbol)
    if start < EX_RIGHT_HISTORY_START or start > end:
        raise DataValidationError("invalid TWSE ex-right history window")
    source_url = build_ex_right_url(start, end)
    summary = get_with_retry(source_url, transport, timeout, retries, backoff=2).body
    payload = _payload(summary)
    details = {}
    for values in _rows(payload, ("資料日期", "股票代號")):
        if str(values["股票代號"]).strip() == symbol:
            effective = parse_date(values["資料日期"])
            detail_url = build_ex_right_detail_url(symbol, effective)
            details[(symbol, effective)] = get_with_retry(
                detail_url, transport, timeout, retries, backoff=2).body
    return parse_ex_right_events(summary, details, symbol, source_url, utc_now_iso())


def fetch_reduction_events(symbol: str, start: date, end: date, *,
                           transport: HttpTransport | None = None, timeout=30, retries=2):
    validate_symbol(symbol)
    if start < CAPITAL_REDUCTION_HISTORY_START or start > end:
        raise DataValidationError("invalid TWSE reduction history window")
    source_url = build_reduction_url(start, end)
    summary = get_with_retry(source_url, transport, timeout, retries, backoff=2).body
    payload = _payload(summary)
    details = {}
    for values in _rows(payload, ("股票代號", "詳細資料")):
        if str(values["股票代號"]).strip() != symbol:
            continue
        token = re.fullmatch(r"\s*(\d{4})\s*,\s*(\d{8})\s*", str(values["詳細資料"]))
        if not token or token.group(1) != symbol:
            raise DataValidationError("TWSE reduction detail identity mismatch")
        file_date = token.group(2)
        detail_url = build_reduction_detail_url(symbol, file_date)
        details[(symbol, file_date)] = get_with_retry(
            detail_url, transport, timeout, retries, backoff=2).body
    return parse_reduction_events(summary, details, symbol, source_url, utc_now_iso())


def fetch_corporate_action_history(
        symbol: str, start: date, end: date, cache_dir: Path, *,
        transport: HttpTransport | None = None, timeout=30.0, retries=2,
        request_interval=1.0, refresh_date: date | None = None,
        progress=None) -> CorporateActionHistory:
    """Fetch integrity-checked annual TWSE action summaries and event details.

    Annual summaries keep requests bounded while covering the full report
    history.  Completed years and immutable detail responses are reused from
    the same SHA-256-verified cache contract as valuation history.  Only the
    current year is refreshed.
    """
    validate_symbol(symbol)
    if start > end:
        raise DataValidationError("invalid corporate-action history window")
    if (not math.isfinite(timeout) or timeout <= 0 or retries < 0
            or not math.isfinite(request_interval) or request_interval < 0):
        raise DataValidationError("invalid corporate-action request controls")
    root = Path(cache_dir)
    current_year = (refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()).year
    events: list[CorporateActionEvent] = []
    results: list[dict] = []
    last_request: float | None = None

    def request(namespace: str, identifier: str, url: str, *, refresh=False):
        nonlocal last_request
        cached = None
        if not refresh:
            cached = load_cached_month(
                root / namespace,
                source_symbol=symbol,
                canonical_symbol=f"{symbol}.TW",
                month_identifier=identifier,
                expected_source_url=url,
            )
        if cached is not None:
            return cached.body, cached.retrieved_at, "CACHE_HIT", cached.sha256
        if last_request is not None:
            time.sleep(max(0, request_interval - (time.monotonic() - last_request)))
        response = get_with_retry(url, transport, timeout, retries, backoff=2)
        last_request = time.monotonic()
        retrieved = utc_now_iso()
        store_cached_month(
            root / namespace,
            source_symbol=symbol,
            canonical_symbol=f"{symbol}.TW",
            month_identifier=identifier,
            source_url=url,
            retrieved_at=retrieved,
            http_status=response.status,
            body=response.body,
        )
        return response.body, retrieved, "FETCHED", raw_hash(response.body)

    def record(source: str, year: int, status: str, digest: str,
               event_count: int, source_url: str):
        result = {
            "source": source,
            "year": year,
            "status": status,
            "sha256": digest,
            "event_count": event_count,
            "source_url": source_url,
        }
        results.append(result)
        if progress:
            progress(result)

    for year in range(max(start.year, EX_RIGHT_HISTORY_START.year), end.year + 1):
        window_start = max(start, EX_RIGHT_HISTORY_START, date(year, 1, 1))
        window_end = min(end, date(year, 12, 31))
        if window_start > window_end:
            continue
        source_url = build_ex_right_url(window_start, window_end)
        summary, retrieved, status, digest = request(
            "corporate_actions/ex_right/summary",
            f"{window_start:%Y%m%d}_{window_end:%Y%m%d}", source_url,
            refresh=year == current_year,
        )
        payload = _payload(summary)
        details = {}
        for values in _rows(payload, ("資料日期", "股票代號")):
            if str(values["股票代號"]).strip() != symbol:
                continue
            effective = parse_date(values["資料日期"])
            detail_url = build_ex_right_detail_url(symbol, effective)
            body, _, _, _ = request(
                "corporate_actions/ex_right/detail",
                effective.strftime("%Y%m%d"), detail_url,
            )
            details[(symbol, effective)] = body
        parsed = parse_ex_right_events(summary, details, symbol, source_url, retrieved)
        events.extend(parsed)
        record("TWT49U", year, status, digest, len(parsed), source_url)

    for year in range(max(start.year, CAPITAL_REDUCTION_HISTORY_START.year), end.year + 1):
        window_start = max(start, CAPITAL_REDUCTION_HISTORY_START, date(year, 1, 1))
        window_end = min(end, date(year, 12, 31))
        if window_start > window_end:
            continue
        source_url = build_reduction_url(window_start, window_end)
        summary, retrieved, status, digest = request(
            "corporate_actions/reduction/summary",
            f"{window_start:%Y%m%d}_{window_end:%Y%m%d}", source_url,
            refresh=year == current_year,
        )
        payload = _payload(summary)
        details = {}
        for values in _rows(payload, ("股票代號", "詳細資料")):
            if str(values["股票代號"]).strip() != symbol:
                continue
            token = re.fullmatch(r"\s*(\d{4})\s*,\s*(\d{8})\s*", str(values["詳細資料"]))
            if not token or token.group(1) != symbol:
                raise DataValidationError("TWSE reduction detail identity mismatch")
            file_date = token.group(2)
            detail_url = build_reduction_detail_url(symbol, file_date)
            body, _, _, _ = request(
                "corporate_actions/reduction/detail", file_date, detail_url,
            )
            details[(symbol, file_date)] = body
        parsed = parse_reduction_events(summary, details, symbol, source_url, retrieved)
        events.extend(parsed)
        record("TWTAUU", year, status, digest, len(parsed), source_url)

    return CorporateActionHistory(mark_conflicting_duplicates(events), tuple(results))
