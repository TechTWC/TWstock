from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
import time
from typing import Protocol
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from ..errors import DataValidationError, MalformedSourceError, SourceUnavailableError


TPEX_CURRENT_CB_ENDPOINT = "https://www.tpex.org.tw/www/zh-tw/bond/convSearch"
TPEX_RECENT_DELISTED_CB_ENDPOINT = "https://www.tpex.org.tw/www/zh-tw/bond/convDelist"
_ISSUER_RE = re.compile(r"^[0-9]{4,6}$")
_CB_CODE_RE = re.compile(r"^[0-9]{5,7}$")


@dataclass(frozen=True)
class CbIssue:
    issuer_code: str
    issuer_name: str
    bond_code: str
    bond_name: str
    event_date: date
    listing_status: str
    instrument_type: str = "UNVERIFIED"
    source_url: str = ""


@dataclass(frozen=True)
class CbIssuerClassification:
    status: str
    current_issue_count: int
    recent_delisted_count: int
    issue_names: tuple[str, ...]
    data_as_of: date
    source_status: str = "OFFICIAL_TPEX_CURRENT_AND_RECENT"


@dataclass(frozen=True)
class CbMarketSnapshot:
    current_issues: tuple[CbIssue, ...]
    recently_delisted_issues: tuple[CbIssue, ...]
    data_as_of: date
    source_status: str = "OFFICIAL_TPEX_CURRENT_AND_RECENT"

    def classify(self, issuer_code: str) -> CbIssuerClassification:
        listed = tuple(
            issue for issue in self.current_issues if issue.issuer_code == issuer_code
        )
        current = tuple(issue for issue in listed if issue.event_date <= self.data_as_of)
        upcoming = tuple(issue for issue in listed if issue.event_date > self.data_as_of)
        recent = tuple(
            issue
            for issue in self.recently_delisted_issues
            if issue.issuer_code == issuer_code
        )
        current_cb = tuple(
            issue for issue in current if issue.instrument_type == "CONVERTIBLE_BOND"
        )
        upcoming_cb = tuple(
            issue for issue in upcoming if issue.instrument_type == "CONVERTIBLE_BOND"
        )
        if current_cb:
            status = "CURRENT_CB"
            names = tuple(issue.bond_name for issue in current_cb)
        elif current:
            status = "CURRENT_NON_CB_ONLY"
            names = tuple(issue.bond_name for issue in current)
        elif upcoming_cb:
            status = "UPCOMING_CB"
            names = tuple(issue.bond_name for issue in upcoming)
        elif upcoming:
            status = "UPCOMING_NON_CB_ONLY"
            names = tuple(issue.bond_name for issue in upcoming)
        elif recent:
            status = "RECENTLY_DELISTED_CB_OR_EB"
            names = tuple(issue.bond_name for issue in recent)
        else:
            status = "NOT_FOUND_CURRENT_OR_RECENT"
            names = ()
        return CbIssuerClassification(
            status=status,
            current_issue_count=len(current_cb),
            recent_delisted_count=len(recent),
            issue_names=names,
            data_as_of=self.data_as_of,
        )


@dataclass(frozen=True)
class PostResponse:
    url: str
    status: int
    body: bytes


class PostTransport(Protocol):
    def post(self, url: str, data: bytes, timeout: float) -> PostResponse: ...


class UrllibPostTransport:
    def post(self, url: str, data: bytes, timeout: float) -> PostResponse:
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "TWstock-data-adapter/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return PostResponse(response.geturl(), response.status, response.read())


def fetch_tpex_cb_market_snapshot(
    *,
    transport: PostTransport | None = None,
    timeout: float = 10.0,
    retries: int = 2,
    retrieved_date: date | None = None,
) -> CbMarketSnapshot:
    client = transport or UrllibPostTransport()
    current_response = _post_with_retry(
        TPEX_CURRENT_CB_ENDPOINT,
        urllib.parse.urlencode(
            {"name": "bondIssuer", "searchNo": "", "response": "json"}
        ).encode("ascii"),
        client,
        timeout,
        retries,
    )
    delisted_response = _post_with_retry(
        TPEX_RECENT_DELISTED_CB_ENDPOINT,
        urllib.parse.urlencode({"response": "json"}).encode("ascii"),
        client,
        timeout,
        retries,
    )
    current = parse_current_cb_payload(current_response.body)
    delisted, reported_date = parse_recent_delisted_cb_payload(
        delisted_response.body
    )
    as_of = reported_date or retrieved_date or datetime.now(
        ZoneInfo("Asia/Taipei")
    ).date()
    return CbMarketSnapshot(current, delisted, as_of)


def parse_current_cb_payload(body: bytes) -> tuple[CbIssue, ...]:
    table = _single_table(body, "current CB")
    required = ("發行機構代碼", "發行機構名稱", "債券名稱", "掛牌日期", "發行資料")
    indexes = _field_indexes(table, required)
    issues: list[CbIssue] = []
    for raw_row in _rows(table):
        issuer_code = str(raw_row[indexes["發行機構代碼"]]).strip()
        if not _ISSUER_RE.fullmatch(issuer_code):
            raise DataValidationError("invalid TPEx CB issuer code")
        source_url = str(raw_row[indexes["發行資料"]]).strip()
        bond_code = _bond_code_from_url(source_url)
        issues.append(
            CbIssue(
                issuer_code=issuer_code,
                issuer_name=str(raw_row[indexes["發行機構名稱"]]).strip(),
                bond_code=bond_code,
                bond_name=str(raw_row[indexes["債券名稱"]]).strip(),
                event_date=_roc_date(str(raw_row[indexes["掛牌日期"]])),
                listing_status="CURRENT",
                instrument_type=_instrument_type(
                    str(raw_row[indexes["債券名稱"]]).strip()
                ),
                source_url=source_url,
            )
        )
    return tuple(sorted(issues, key=lambda item: (item.issuer_code, item.bond_code)))


def parse_recent_delisted_cb_payload(
    body: bytes,
) -> tuple[tuple[CbIssue, ...], date | None]:
    table = _single_table(body, "recent delisted CB")
    required = ("代碼", "簡稱", "下櫃日期")
    indexes = _field_indexes(table, required)
    issues: list[CbIssue] = []
    for raw_row in _rows(table):
        bond_code = str(raw_row[indexes["代碼"]]).strip()
        if not _CB_CODE_RE.fullmatch(bond_code):
            raise DataValidationError("invalid TPEx delisted CB code")
        issues.append(
            CbIssue(
                issuer_code=bond_code[:4],
                issuer_name="",
                bond_code=bond_code,
                bond_name=str(raw_row[indexes["簡稱"]]).strip(),
                event_date=_roc_date(str(raw_row[indexes["下櫃日期"]])),
                listing_status="RECENTLY_DELISTED",
                instrument_type="UNVERIFIED",
            )
        )
    report_date = None
    raw_report_date = str(table.get("date", "")).strip()
    if raw_report_date:
        report_date = _roc_date(raw_report_date)
    return (
        tuple(sorted(issues, key=lambda item: (item.issuer_code, item.bond_code))),
        report_date,
    )


def _post_with_retry(
    url: str,
    data: bytes,
    transport: PostTransport,
    timeout: float,
    retries: int,
) -> PostResponse:
    if retries < 0:
        raise ValueError("retries must be nonnegative")
    last: object = "unknown error"
    for attempt in range(retries + 1):
        try:
            response = transport.post(url, data, timeout)
            if 200 <= response.status < 300:
                return response
            last = f"HTTP {response.status}"
        except (TimeoutError, urllib.error.URLError, OSError) as error:
            last = error
        if attempt < retries:
            time.sleep(0.25 * (2**attempt))
    raise SourceUnavailableError(f"failed to fetch official TPEx CB data: {last}")


def _single_table(body: bytes, label: str) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MalformedSourceError(f"invalid TPEx {label} JSON") from error
    if not isinstance(payload, dict) or payload.get("stat") != "ok":
        raise DataValidationError(f"TPEx {label} response is not ok")
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], dict):
        raise MalformedSourceError(f"TPEx {label} response must contain one table")
    return tables[0]


def _field_indexes(
    table: dict[str, object], required: tuple[str, ...]
) -> dict[str, int]:
    fields = table.get("fields")
    if not isinstance(fields, list) or any(not isinstance(item, str) for item in fields):
        raise MalformedSourceError("TPEx CB fields must be a string array")
    missing = [field for field in required if field not in fields]
    if missing:
        raise DataValidationError(f"TPEx CB fields missing: {','.join(missing)}")
    return {field: fields.index(field) for field in required}


def _rows(table: dict[str, object]) -> tuple[list[object], ...]:
    data = table.get("data")
    if data is None:
        return ()
    if not isinstance(data, list) or any(not isinstance(row, list) for row in data):
        raise MalformedSourceError("TPEx CB data must be a row array")
    return tuple(data)


def _bond_code_from_url(source_url: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(source_url).query)
    bond_ids = query.get("bond_id", [])
    if len(bond_ids) != 1 or not _CB_CODE_RE.fullmatch(bond_ids[0]):
        raise DataValidationError("missing or invalid TPEx current CB bond_id")
    return bond_ids[0]


def _roc_date(value: str) -> date:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise DataValidationError("invalid TPEx ROC date")
    try:
        year, month, day = (int(part) for part in parts)
        return date(year + 1911, month, day)
    except ValueError as error:
        raise DataValidationError("invalid TPEx ROC date") from error


def _instrument_type(bond_name: str) -> str:
    if "轉換公司債" in bond_name:
        return "CONVERTIBLE_BOND"
    if "交換公司債" in bond_name:
        return "EXCHANGEABLE_BOND"
    return "UNVERIFIED"
