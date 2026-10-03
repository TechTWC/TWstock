"""Official MOPS per-symbol face-value-change coverage and event adapter.

MOPS category 11 is broader than face-value changes.  A successful proof is
therefore the terminal symbol/date rowset plus every referenced detail, not a
keyword-search hit.  Session cookies remain inside the transient transport and
are never exposed to the cache or provenance payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import html
import json
import math
from pathlib import Path
import re
import time
from typing import Protocol
from urllib.parse import urlencode, urljoin
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from ..errors import (
    DataValidationError, MalformedSourceError, MarketDataError,
    SourceUnavailableError,
)
from ..http import HttpResponse
from ..normalization import raw_hash, stable_json_bytes, utc_now_iso
from ..twse_incremental_cache import load_cached_month, store_cached_month
from .twse_corporate_actions import (
    CORPORATE_ACTION_REVIEW_REQUIRED,
    FACE_VALUE_CHANGE_REVERSE_SPLIT,
    FACE_VALUE_CHANGE_SPLIT,
    NORMALIZATION_READY,
    UNSUPPORTED_ACTION,
    CorporateActionEvent,
    mark_conflicting_duplicates,
)
from .twse_valuation import validate_symbol
from .security_identity import TPEX, TWSE, canonical_symbol

MOPS_FORM_URL = "https://mopsov.twse.com.tw/mops/web/t146sb10"
MOPS_QUERY_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t146sb10"
MOPS_DETAIL_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t59sb09"
FACE_VALUE_LEGAL_START = date(2013, 12, 30)

FACE_VALUE_COVERAGE_PROVEN = "FACE_VALUE_COVERAGE_PROVEN"
FACE_VALUE_COVERAGE_INCOMPLETE = "FACE_VALUE_COVERAGE_INCOMPLETE"
FACE_VALUE_REVIEW_REQUIRED = "FACE_VALUE_REVIEW_REQUIRED"
_PROOF_STATUSES = frozenset({
    FACE_VALUE_COVERAGE_PROVEN,
    FACE_VALUE_COVERAGE_INCOMPLETE,
    FACE_VALUE_REVIEW_REQUIRED,
})
_FACTOR_TOLERANCE = Decimal("0.00000001")


class MopsTransport(Protocol):
    def get(self, url: str, timeout: float) -> HttpResponse: ...
    def post(self, url: str, data: bytes, timeout: float) -> HttpResponse: ...


class UrllibMopsTransport:
    """A public, cookie-aware MOPS session with no persistent cookie storage."""

    def __init__(self):
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()))

    def _open(self, request: urllib.request.Request, timeout: float) -> HttpResponse:
        with self._opener.open(request, timeout=timeout) as response:
            return HttpResponse(response.geturl(), response.status, response.read())

    def get(self, url: str, timeout: float) -> HttpResponse:
        return self._open(urllib.request.Request(
            url, headers={"User-Agent": "TWstock-data-adapter/0.1"}), timeout)

    def post(self, url: str, data: bytes, timeout: float) -> HttpResponse:
        return self._open(urllib.request.Request(url, data=data, headers={
            "User-Agent": "TWstock-data-adapter/0.1",
            "Content-Type": "application/x-www-form-urlencoded",
        }), timeout)


@dataclass(frozen=True)
class MopsAnnouncementRow:
    symbol: str
    company_name: str
    announcement_date: date
    detail_date1: str
    skey: str
    subject: str


@dataclass(frozen=True)
class FaceValueCoverageProof:
    symbol: str
    query_start: date
    query_end: date
    result_count: int
    detail_count: int
    rowset_hash: str | None
    detail_manifest_hash: str | None
    retrieved_at: str
    status: str
    source_url: str = MOPS_QUERY_URL
    failure_reason: str | None = None
    market: str = TWSE
    canonical_symbol: str = ""

    def __post_init__(self):
        validate_symbol(self.symbol)
        if self.market not in {TWSE, TPEX}:
            raise DataValidationError("face-value proof market is invalid")
        expected_canonical = canonical_symbol(self.symbol, self.market)
        if self.canonical_symbol and self.canonical_symbol != expected_canonical:
            raise DataValidationError("face-value proof canonical symbol mismatch")
        if self.query_start > self.query_end:
            raise DataValidationError("invalid face-value proof window")
        if self.status not in _PROOF_STATUSES:
            raise DataValidationError("unknown face-value proof status")
        if self.result_count < 0 or self.detail_count < 0:
            raise DataValidationError("negative face-value proof count")
        for digest in (self.rowset_hash, self.detail_manifest_hash):
            if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise DataValidationError("invalid face-value proof hash")
        if self.status == FACE_VALUE_COVERAGE_PROVEN:
            if self.detail_count != self.result_count:
                raise DataValidationError("proven face-value coverage requires all details")
            if self.rowset_hash is None or self.detail_manifest_hash is None:
                raise DataValidationError("proven face-value coverage requires hashes")


@dataclass(frozen=True)
class FaceValueChangeHistory:
    events: tuple[CorporateActionEvent, ...]
    proof: FaceValueCoverageProof
    request_results: tuple[dict, ...] = ()


class _DispatchParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.action: str | None = None
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("name") == "fm_show":
            self.in_form = True
            self.action = values.get("action")
        elif tag == "input" and self.in_form:
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.in_form:
            self.in_form = False


class _TableParser(HTMLParser):
    """Extract the structured MOPS result/detail table without scraping scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.in_target_table = False
        self.in_row = False
        self.cell_tag: str | None = None
        self.cell_parts: list[str] = []
        self.row_cells: list[tuple[str, str]] = []
        self.row_inputs: list[dict[str, str]] = []
        self.rows: list[tuple[list[tuple[str, str]], list[dict[str, str]]]] = []
        self.text_parts: list[str] = []
        self.control_tokens: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "table":
            if self.in_target_table:
                self.table_depth += 1
            elif "hasBorder" in values.get("class", "").split():
                self.in_target_table = True
                self.table_depth = 1
        elif self.in_target_table and tag == "tr":
            self.in_row = True
            self.row_cells = []
            self.row_inputs = []
        elif self.in_row and tag in ("th", "td"):
            self.cell_tag = tag
            self.cell_parts = []
        elif self.in_row and tag == "input":
            self.row_inputs.append(values)
        if tag in ("input", "button", "a", "select"):
            self.control_tokens.extend(
                values.get(key, "") for key in ("name", "id", "class", "value", "href"))
        if tag == "br" and self.cell_tag:
            self.cell_parts.append("\n")

    def handle_endtag(self, tag):
        if self.in_row and tag == self.cell_tag:
            value = html.unescape("".join(self.cell_parts))
            value = re.sub(r"[ \t\r\f\v]+", " ", value).strip()
            self.row_cells.append((self.cell_tag or "td", value))
            self.cell_tag = None
            self.cell_parts = []
        elif self.in_target_table and tag == "tr" and self.in_row:
            self.rows.append((self.row_cells, self.row_inputs))
            self.in_row = False
        elif self.in_target_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_target_table = False

    def handle_data(self, data):
        self.text_parts.append(data)
        if self.cell_tag:
            self.cell_parts.append(data)


def _decode_html(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MalformedSourceError("MOPS response is not UTF-8") from error


def _roc_date(value: str, field: str) -> date:
    match = re.fullmatch(r"\s*(?:民國)?(\d{2,3})[年/]\s*(\d{1,2})[月/]\s*(\d{1,2})日?\s*[。.]?\s*", value)
    if not match:
        raise MalformedSourceError(f"invalid MOPS {field}")
    try:
        return date(int(match.group(1)) + 1911, int(match.group(2)), int(match.group(3)))
    except ValueError as error:
        raise MalformedSourceError(f"invalid MOPS {field}") from error


def _decimal(value: str, field: str) -> Decimal:
    try:
        number = Decimal(value.replace(",", "").strip())
    except InvalidOperation as error:
        raise MalformedSourceError(f"invalid MOPS {field}") from error
    if not number.is_finite() or number <= 0:
        raise MalformedSourceError(f"nonpositive MOPS {field}")
    return number


def parse_dispatch_form(body: bytes) -> dict[str, str]:
    parser = _DispatchParser()
    parser.feed(_decode_html(body))
    if parser.action != "/mops/web/ajax_t146sb10":
        raise MalformedSourceError("missing MOPS fm_show dispatch form")
    required = {
        "step", "typek", "co_id_1", "SDATE", "EDATE", "YEAR1", "YEAR2",
        "MONTH1", "MONTH2", "SDAY", "EDAY", "scope", "sort", "rpt",
        "firstin", "noticeKind", "noticeDate", "date",
    }
    if required - parser.fields.keys() or parser.fields.get("step") != "2":
        raise MalformedSourceError("incomplete MOPS dispatch contract")
    fields = dict(parser.fields)
    # The official autoRunScript assigns this value immediately before POST.
    fields["rpt"] = "bool_t59sb09"
    return fields


def parse_terminal_rowset(body: bytes, symbol: str) -> tuple[MopsAnnouncementRow, ...]:
    validate_symbol(symbol)
    parser = _TableParser()
    parser.feed(_decode_html(body))
    visible = " ".join(parser.text_parts)
    control_text = " ".join(parser.control_tokens).lower()
    if re.search(r"(?:下一頁|上一頁|最後一頁|第一頁)", visible) or re.search(
            r"(?:^|[^a-z])(page|pager|offset|next|previous)(?:[^a-z]|$)", control_text):
        raise MalformedSourceError("unknown MOPS pagination contract")
    if "查無所需資料" in visible:
        return ()

    headers: tuple[str, ...] | None = None
    output = []
    for cells, inputs in parser.rows:
        kinds = tuple(kind for kind, _ in cells)
        values = tuple(value for _, value in cells)
        if kinds and all(kind == "th" for kind in kinds):
            headers = values
            continue
        if not cells:
            continue
        # The source currently renders 主　　旨 with full-width spaces.
        normalized_headers = tuple(
            re.sub(r"\s+", " ", item).strip() for item in (headers or ()))
        if normalized_headers[:4] != ("公司代號", "公司簡稱", "公告日期", "主 旨"):
            raise MalformedSourceError("unexpected MOPS terminal rowset schema")
        if len(values) < 4:
            raise MalformedSourceError("malformed MOPS terminal row")
        row_symbol = values[0].strip()
        if row_symbol != symbol:
            raise DataValidationError("MOPS rowset symbol identity mismatch")
        onclick = next((item.get("onclick", "") for item in inputs
                        if item.get("value") == "詳細資料"), "")
        identity = re.search(
            r'co_id\.value="([0-9]{4,6})";.*?DATE1\.value="(\d{8})";.*?SKEY\.value="(\d+)";',
            onclick,
        )
        if not identity or identity.group(1) != symbol:
            raise MalformedSourceError("missing MOPS detail identity")
        output.append(MopsAnnouncementRow(
            symbol=symbol,
            company_name=values[1].strip(),
            announcement_date=_roc_date(values[2], "announcement date"),
            detail_date1=identity.group(2),
            skey=identity.group(3),
            subject=values[3].strip(),
        ))
    if headers is None:
        raise MalformedSourceError("missing MOPS terminal rowset")
    identities = {(row.symbol, row.detail_date1, row.skey) for row in output}
    if len(identities) != len(output):
        raise DataValidationError("duplicate MOPS detail identity")
    return tuple(output)


def _detail_fields(body: bytes) -> dict[str, str]:
    parser = _TableParser()
    parser.feed(_decode_html(body))
    result = {}
    for cells, _ in parser.rows:
        if len(cells) >= 2 and cells[0][0] == "th" and cells[1][0] == "td":
            key = re.sub(r"\s+", " ", cells[0][1]).strip()
            result[key] = cells[1][1].strip()
    required = {"公司代號", "公告序號", "主旨", "公告內容"}
    if required - result.keys():
        raise MalformedSourceError("unexpected MOPS detail schema")
    return result


def _labeled_date(content: str, labels: tuple[str, ...]) -> date | None:
    for label in labels:
        match = re.search(
            rf"{label}\s*[:：]\s*((?:民國)?\d{{2,3}}[年/]\s*\d{{1,2}}[月/]\s*\d{{1,2}}日?)",
            content,
        )
        if match:
            return _roc_date(match.group(1), label)
    return None


def _review_event(row: MopsAnnouncementRow, fields: dict[str, str], body: bytes,
                  rowset_body: bytes, retrieved_at: str, reason: str, *,
                  old_par: Decimal | None = None,
                  new_par: Decimal | None = None,
                  candidate_factor: Decimal | None = None,
                  candidate_effective_date: date | None = None):
    source_fields = {
        "announcement_date": row.announcement_date.isoformat(),
        "company_name": row.company_name,
        "parser_review_reason": reason,
        "subject": fields.get("主旨", row.subject),
    }
    if candidate_effective_date is not None:
        source_fields["candidate_effective_date"] = candidate_effective_date.isoformat()
    return CorporateActionEvent(
        symbol=row.symbol,
        effective_date=candidate_effective_date or row.announcement_date,
        action_type=UNSUPPORTED_ACTION,
        share_factor=float(candidate_factor) if candidate_factor is not None else None,
        cash_return_per_share=None,
        pre_event_close=None,
        official_reference_price=None,
        source_url=MOPS_QUERY_URL,
        detail_source_url=MOPS_DETAIL_URL,
        retrieved_at=retrieved_at,
        raw_hash=raw_hash(rowset_body + b"\x00" + body),
        status=CORPORATE_ACTION_REVIEW_REQUIRED,
        mops_date1=row.detail_date1,
        mops_skey=row.skey,
        coverage_proof_status=FACE_VALUE_REVIEW_REQUIRED,
        source_fields=tuple(sorted(source_fields.items())),
        old_par_value=float(old_par) if old_par is not None else None,
        new_par_value=float(new_par) if new_par is not None else None,
    )


def parse_face_value_detail(body: bytes, row: MopsAnnouncementRow,
                            rowset_body: bytes, retrieved_at: str):
    fields = _detail_fields(body)
    if fields["公司代號"].strip() != row.symbol:
        raise DataValidationError("MOPS detail symbol identity mismatch")
    if fields["公告序號"].strip() != row.skey:
        raise DataValidationError("MOPS detail SKEY identity mismatch")
    subject = fields["主旨"]
    content = fields["公告內容"]
    face_semantics = (
        "股票面額變更" in subject
        or "變更股票面額" in subject
        or "原有股票面額" in content
        or "股票面額之變更" in content
    )
    if not face_semantics:
        return None

    par = re.search(
        r"原有股票面額(?:新台幣|新臺幣)?\s*([0-9][0-9,.]*)\s*元\s*"
        r"變更為(?:新台幣|新臺幣)?\s*([0-9][0-9,.]*)\s*元",
        content,
    )
    ratio = re.search(r"每\s*1\s*股\s*換發\s*([0-9][0-9,.]*)\s*股", content)
    if not par:
        return _review_event(row, fields, body, rowset_body, retrieved_at,
                             "missing old/new par values")
    old_par = _decimal(par.group(1), "old par value")
    new_par = _decimal(par.group(2), "new par value")
    derived = old_par / new_par
    official = _decimal(ratio.group(1), "official exchange ratio") if ratio else None
    if official is not None and abs(derived - official) > _FACTOR_TOLERANCE:
        raise DataValidationError("MOPS official factor conflicts with par-value ratio")

    last_trading = _labeled_date(content, ("舊股票最後交易日",))
    stop_match = re.search(
        r"舊股票停止交易期間\s*[:：]\s*((?:民國)?\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日)"
        r"\s*起至\s*((?:民國)?\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日)",
        content,
    )
    stop_start = _roc_date(stop_match.group(1), "stop trading start") if stop_match else None
    stop_end = _roc_date(stop_match.group(2), "stop trading end") if stop_match else None
    exchange_date = _labeled_date(content, ("有價證券換發日",))
    listing_date = _labeled_date(content, (
        "新股票上市買賣日及舊股票終止上市買賣日", "新股票上市買賣日",
    ))
    if listing_date is None:
        listing_match = re.search(
            r"(?:自|訂於)\s*((?:民國)?\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日)"
            r"\s*(?:上市買賣|以新股上市)", content)
        if listing_match:
            listing_date = _roc_date(listing_match.group(1), "new listing date")
    required_dates = (last_trading, stop_start, stop_end, exchange_date, listing_date)
    if any(value is None for value in required_dates):
        return _review_event(row, fields, body, rowset_body, retrieved_at,
                             "missing official exchange schedule",
                             old_par=old_par, new_par=new_par,
                             candidate_factor=derived,
                             candidate_effective_date=listing_date)
    if exchange_date != listing_date:
        return _review_event(row, fields, body, rowset_body, retrieved_at,
                             "exchange/listing date conflict")
    if not (last_trading < stop_start <= stop_end < listing_date):
        return _review_event(row, fields, body, rowset_body, retrieved_at,
                             "inconsistent exchange schedule")
    if derived == Decimal("1"):
        return None

    action = (FACE_VALUE_CHANGE_SPLIT if derived > 1
              else FACE_VALUE_CHANGE_REVERSE_SPLIT)
    company_match = re.search(r"公司名稱\s*[:：]\s*([^\n。]+)", content)
    company_name = company_match.group(1).strip() if company_match else row.company_name
    source_fields = {
        "announcement_date": row.announcement_date.isoformat(),
        "company_name": company_name,
        "detail_DATE1": row.detail_date1,
        "SKEY": row.skey,
        "old_par_value": str(old_par),
        "new_par_value": str(new_par),
        "derived_exchange_ratio": str(derived),
        "official_exchange_ratio": str(official) if official is not None else "",
        "last_trading_date": last_trading.isoformat(),
        "stop_trading_start": stop_start.isoformat(),
        "stop_trading_end": stop_end.isoformat(),
        "exchange_date": exchange_date.isoformat(),
        "resume_trading_date": listing_date.isoformat(),
        "new_listing_date": listing_date.isoformat(),
        "subject": subject,
    }
    return CorporateActionEvent(
        symbol=row.symbol,
        effective_date=listing_date,
        action_type=action,
        share_factor=float(derived),
        cash_return_per_share=None,
        pre_event_close=None,
        official_reference_price=None,
        source_url=MOPS_QUERY_URL,
        detail_source_url=MOPS_DETAIL_URL,
        retrieved_at=retrieved_at,
        raw_hash=raw_hash(rowset_body + b"\x00" + body),
        status=NORMALIZATION_READY,
        resume_date=listing_date,
        derived=official is None,
        derivation_formula="old_par_value / new_par_value",
        source_fields=tuple(sorted(source_fields.items())),
        old_par_value=float(old_par),
        new_par_value=float(new_par),
        mops_date1=row.detail_date1,
        mops_skey=row.skey,
        coverage_proof_status=FACE_VALUE_COVERAGE_PROVEN,
    )


def _request(transport: MopsTransport, method: str, url: str, *, data: bytes | None,
             timeout: float, retries: int) -> HttpResponse:
    last: object = None
    for attempt in range(retries + 1):
        try:
            if method == "GET":
                response = transport.get(url, timeout)
            else:
                post = getattr(transport, "post", None)
                if post is None:
                    raise SourceUnavailableError("transport does not support MOPS POST")
                response = post(url, data or b"", timeout)
            if 200 <= response.status < 300:
                return response
            last = f"HTTP {response.status}"
        except (TimeoutError, urllib.error.URLError, OSError, SourceUnavailableError) as error:
            last = type(error).__name__
        if attempt < retries:
            time.sleep(.25 * (2 ** attempt))
    raise SourceUnavailableError(f"MOPS {method} failed: {last}")


def _roc_compact(day: date) -> str:
    return f"{day.year - 1911:03d}{day.month:02d}{day.day:02d}"


def _cache_response(root: Path, symbol: str, identifier: str, url: str,
                    response: HttpResponse, retrieved_at: str, market: str = TWSE):
    store_cached_month(
        root,
        source_symbol=symbol,
        canonical_symbol=canonical_symbol(symbol, market),
        month_identifier=identifier,
        source_url=url,
        retrieved_at=retrieved_at,
        http_status=response.status,
        body=response.body,
        source=market,
    )


def _proof_manifest_path(root: Path, symbol: str, start: date, end: date) -> Path:
    return root / f"mops_{symbol}_{start:%Y%m%d}_{end:%Y%m%d}_proof.json"


def _write_proof_manifest(root: Path, proof: FaceValueCoverageProof,
                          detail_manifest: list[dict[str, str]]):
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "TWSTOCK-MOPS-FACE-VALUE-PROOF-001",
        "symbol": proof.symbol,
        "canonical_symbol": proof.canonical_symbol or canonical_symbol(proof.symbol, proof.market),
        "market": proof.market,
        "query_start": proof.query_start.isoformat(),
        "query_end": proof.query_end.isoformat(),
        "endpoint": proof.source_url,
        "result_count": proof.result_count,
        "detail_count": proof.detail_count,
        "rowset_hash": proof.rowset_hash,
        "detail_manifest_hash": proof.detail_manifest_hash,
        "retrieved_at": proof.retrieved_at,
        "status": proof.status,
        "detail_manifest": detail_manifest,
    }
    path = _proof_manifest_path(root, proof.symbol, proof.query_start, proof.query_end)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reconcile_face_value_events(events):
    """Collapse a corroborating short listing notice into its full notice."""
    ready_identities = {
        (event.symbol, event.effective_date, event.old_par_value,
         event.new_par_value, event.share_factor)
        for event in events if event.status == NORMALIZATION_READY
    }
    retained = [
        event for event in events
        if not (
            event.status == CORPORATE_ACTION_REVIEW_REQUIRED
            and event.old_par_value is not None
            and event.new_par_value is not None
            and (event.symbol, event.effective_date, event.old_par_value,
                 event.new_par_value, event.share_factor) in ready_identities
        )
    ]
    return mark_conflicting_duplicates(retained)


def fetch_face_value_change_history(
        symbol: str, history_start: date, end: date, cache_dir: Path, *,
        market: str = TWSE,
        transport: MopsTransport | None = None, timeout=30.0, retries=2,
        request_interval=1.0, refresh_date: date | None = None) -> FaceValueChangeHistory:
    """Return face-value events and a fail-closed per-symbol coverage proof."""
    validate_symbol(symbol)
    if market not in {TWSE, TPEX}:
        raise DataValidationError("market must be TWSE or TPEX")
    canonical = canonical_symbol(symbol, market)
    start = max(history_start, FACE_VALUE_LEGAL_START)
    if start > end:
        if end < FACE_VALUE_LEGAL_START:
            empty_hash = raw_hash(b"FACE_VALUE_LEGAL_NOT_APPLICABLE")
            return FaceValueChangeHistory((), FaceValueCoverageProof(
                symbol=symbol, query_start=end, query_end=end,
                result_count=0, detail_count=0,
                rowset_hash=empty_hash,
                detail_manifest_hash=raw_hash(stable_json_bytes([])),
                retrieved_at=utc_now_iso(), status=FACE_VALUE_COVERAGE_PROVEN,
                market=market, canonical_symbol=canonical,
            ))
        raise DataValidationError("invalid MOPS face-value history window")
    if (not math.isfinite(timeout) or timeout <= 0 or retries < 0
            or not math.isfinite(request_interval) or request_interval < 0):
        raise DataValidationError("invalid MOPS request controls")
    root = Path(cache_dir) / "corporate_actions" / "face_value"
    session = transport or UrllibMopsTransport()
    retrieved_at = utc_now_iso()
    rowset_body: bytes | None = None
    rows: tuple[MopsAnnouncementRow, ...] = ()
    detail_count = 0
    detail_manifest: list[dict[str, str]] = []
    events: list[CorporateActionEvent] = []
    results: list[dict] = []
    current_year = (refresh_date or datetime.now(ZoneInfo("Asia/Taipei")).date()).year
    rowset_id = f"rowset_{start:%Y%m%d}_{end:%Y%m%d}"
    refresh_rowset = end.year >= current_year

    try:
        cached = None if refresh_rowset else load_cached_month(
            root / "rowset",
            source_symbol=symbol,
            canonical_symbol=canonical,
            month_identifier=rowset_id,
            expected_source_url=MOPS_QUERY_URL,
            source=market,
        )
        if cached is not None:
            rowset_body = cached.body
            retrieved_at = cached.retrieved_at
            rowset_origin = "CACHE_HIT"
        else:
            form = _request(session, "GET", MOPS_FORM_URL, data=None,
                            timeout=timeout, retries=retries)
            form_text = _decode_html(form.body)
            if ('action="/mops/web/ajax_t146sb10"' not in form_text
                    and "action='/mops/web/ajax_t146sb10'" not in form_text):
                raise MalformedSourceError("unexpected MOPS initial form")
            first = {
                "step": "1", "firstin": "ture", "off": "1", "keyword4": "",
                "code1": "", "TYPEK2": "", "checkbtn": "",
                "queryName": "co_id_1", "inpuType": "co_id", "scope": "1",
                "co_id_1": symbol,
                "typek": "otc" if market == TPEX else "sii",
                "selecttype": "2",
                "noticeDate": "1", "date": "4", "yymmdd1": _roc_compact(start),
                "yymmdd2": _roc_compact(end), "noticeKind": "11", "sort": "1",
            }
            dispatch_response = _request(
                session, "POST", MOPS_QUERY_URL,
                data=urlencode(first).encode(), timeout=timeout, retries=retries)
            dispatch = parse_dispatch_form(dispatch_response.body)
            if (dispatch["co_id_1"] != symbol
                    or dispatch["SDATE"] != start.strftime("%Y%m%d")
                    or dispatch["EDATE"] != end.strftime("%Y%m%d")
                    or dispatch["noticeKind"] != "11"):
                raise DataValidationError("MOPS dispatch identity mismatch")
            rowset_response = _request(
                session, "POST", urljoin(MOPS_QUERY_URL, "/mops/web/ajax_t146sb10"),
                data=urlencode(dispatch).encode(), timeout=timeout, retries=retries)
            retrieved_at = utc_now_iso()
            rowset_body = rowset_response.body
            _cache_response(root / "rowset", symbol, rowset_id, MOPS_QUERY_URL,
                            rowset_response, retrieved_at, market)
            rowset_origin = "FETCHED"
        rows = parse_terminal_rowset(rowset_body, symbol)
        results.append({
            "source": "MOPS_T146SB10", "status": rowset_origin,
            "source_url": MOPS_QUERY_URL, "query_start": start.isoformat(),
            "query_end": end.isoformat(), "result_count": len(rows),
            "sha256": raw_hash(rowset_body),
        })

        for index, row in enumerate(rows):
            if index and request_interval:
                time.sleep(request_interval)
            detail_id = f"detail_{row.detail_date1}_{row.skey}"
            refresh_detail = row.announcement_date.year >= current_year
            cached_detail = None if refresh_detail else load_cached_month(
                root / "detail",
                source_symbol=symbol,
                canonical_symbol=canonical,
                month_identifier=detail_id,
                expected_source_url=MOPS_DETAIL_URL,
                source=market,
            )
            if cached_detail is not None:
                detail_body = cached_detail.body
                detail_retrieved = cached_detail.retrieved_at
                detail_origin = "CACHE_HIT"
            else:
                detail_response = _request(
                    session, "POST", MOPS_DETAIL_URL,
                    data=urlencode({
                        "co_id": row.symbol, "TYPEK": "all", "ST": "1",
                        "DATE1": row.detail_date1, "SKEY": row.skey,
                        "step": "2", "firstin": "1",
                    }).encode(), timeout=timeout, retries=retries)
                detail_body = detail_response.body
                detail_retrieved = utc_now_iso()
                _cache_response(root / "detail", symbol, detail_id, MOPS_DETAIL_URL,
                                detail_response, detail_retrieved, market)
                detail_origin = "FETCHED"
            event = parse_face_value_detail(
                detail_body, row, rowset_body, detail_retrieved)
            detail_count += 1
            digest = raw_hash(detail_body)
            detail_manifest.append({
                "co_id": row.symbol, "DATE1": row.detail_date1,
                "SKEY": row.skey, "sha256": digest,
            })
            if event is not None:
                events.append(event)
            results.append({
                "source": "MOPS_T59SB09", "status": detail_origin,
                "source_url": MOPS_DETAIL_URL, "DATE1": row.detail_date1,
                "SKEY": row.skey, "sha256": digest,
            })

        # MOPS commonly publishes a complete change notice followed by a
        # shorter listing notice for the same exchange.  The latter remains
        # review-required when seen alone, but is corroborating (not a second
        # event) when its par values, factor and effective date match a fully
        # parsed notice in this exhaustive result set.
        events = list(_reconcile_face_value_events(events))
        review = any(event.status != NORMALIZATION_READY for event in events)
        status = FACE_VALUE_REVIEW_REQUIRED if review else FACE_VALUE_COVERAGE_PROVEN
        manifest_hash = raw_hash(stable_json_bytes(detail_manifest))
        proof = FaceValueCoverageProof(
            symbol=symbol, query_start=start, query_end=end,
            result_count=len(rows), detail_count=detail_count,
            rowset_hash=raw_hash(rowset_body),
            detail_manifest_hash=manifest_hash,
            retrieved_at=retrieved_at, status=status,
            failure_reason="review-required face-value announcement" if review else None,
            market=market, canonical_symbol=canonical,
        )
        _write_proof_manifest(root, proof, detail_manifest)
        return FaceValueChangeHistory(tuple(events), proof, tuple(results))
    except (MarketDataError, ValueError, OSError) as error:
        proof = FaceValueCoverageProof(
            symbol=symbol, query_start=start, query_end=end,
            result_count=len(rows), detail_count=detail_count,
            rowset_hash=raw_hash(rowset_body) if rowset_body is not None else None,
            detail_manifest_hash=(raw_hash(stable_json_bytes(detail_manifest))
                                  if rowset_body is not None else None),
            retrieved_at=retrieved_at,
            status=FACE_VALUE_COVERAGE_INCOMPLETE,
            failure_reason=type(error).__name__,
            market=market, canonical_symbol=canonical,
        )
        return FaceValueChangeHistory(tuple(events), proof, tuple(results))
