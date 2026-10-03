"""Evidence-bearing official current-universe compatibility audit for TPEx.

The current OpenAPI snapshots are bare arrays: they expose neither a declared
global total nor a pagination/completeness contract. A missing symbol is never
accepted as unavailable on snapshot absence alone. Missing symbols are resolved
against bounded official per-symbol monthly sources and remain unresolved
unless those sources provide affirmative evidence.
"""
from __future__ import annotations

from datetime import date
import json
import math
import re
from typing import Callable
from urllib.parse import urlencode

from ..errors import DataValidationError, MalformedSourceError, MarketDataError
from ..http import HttpResponse, HttpTransport, get_with_retry
from ..normalization import raw_hash, utc_now_iso
from .security_identity import TPEX, TPEX_MASTER_URL, SecurityIdentity, fetch_security_master
from .tpex_valuation import (
    build_url as build_history_url,
    parse_close_payload,
    parse_valuation_payload_with_period,
)

LATEST_CLOSE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
LATEST_PE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
TRADING_STATUS_BASE_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/chtm"
MISSING = {"", "-", "--", "---", "N/A", "NA", "null", "－", "—"}

AVAILABLE = "AVAILABLE"
LEGITIMATE_UNAVAILABLE_PROVEN = "LEGITIMATE_UNAVAILABLE_PROVEN"
UNRESOLVED = "UNRESOLVED"
FAILURE = "FAILURE"
_STATUSES = {AVAILABLE, LEGITIMATE_UNAVAILABLE_PROVEN, UNRESOLVED, FAILURE}
_PAGING_KEYS = {"next", "nextPage", "page", "pages", "offset", "cursor", "continuationToken"}


def _rows(body: bytes, required: set[str], source: str):
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError(f"invalid {source} JSON") from exc
    if isinstance(payload, dict):
        if _PAGING_KEYS & payload.keys():
            raise MalformedSourceError(f"unexpected {source} pagination contract")
        rows = payload.get("data")
        declared = payload.get("totalCount", payload.get("total"))
        if isinstance(rows, list) and declared is not None:
            text = str(declared).replace(",", "").strip()
            if not re.fullmatch(r"\d+", text) or int(text) != len(rows):
                raise MalformedSourceError(f"truncated {source} response")
        # Production is a bare array. Do not silently accept a new envelope,
        # even when its declared count happens to match.
        raise MalformedSourceError(f"{source} envelope contract is unsupported")
    if not isinstance(payload, list) or not payload:
        raise MalformedSourceError(&"{source} must be a nonempty array")
    for row in payload:
        if not isinstance(row, dict) or required - row.keys():
            raise MalformedSourceError(f"{source} schema mismatch")
        if _PAGING_KEYS & row.keys():
            raise MalformedSourceError(&"unexpected {source} paging field")
    return payload


def _date_key(value: object) -> date:
    text = str(value).strip()
    if re.fullmatch(r"\d{7}", text):
        year, tail = int(text[:3]) + 1911, text[3:]
    elif re.fullmatch(r"\d{8}", text):
        year, tail = int(text[:4]), text[4:]
    else:
        raise MalformedSourceError("invalid TPEx latest snapshot date")
    try:
        return date(year, int(tail[:2]), int(tail[2:]))
    except ValueError as exc:
        raise MalformedSourceError("invalid TPEx latest snapshot date") from exc


def _positive_or_missing(value: object, field: str, *, nonpositive_unavailable=False) -> bool:
    text = str(value).replace(",", "").strip()
    if text in MISSING:
        return False
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        raise MalformedSourceError(f"malformed TPEx latest {field}")
    number = float(text)
    if not math.isfinite(number):
        raise MalformedSourceError(&"nonfinite TPEx latest {field}")
    if number <= 0:
        if nonpositive_unavailable:
            return False
        raise DataValidationError(f"nonpositive TPEx latest {field}")
    return True


def _official_name_compatible(snapshot_name: object, master_name: str) -> bool:
    snapshot = str(snapshot_name).strip().rstrip("*").strip()
    master = master_name.strip().rstrip("*").strip()
    if snapshot and master and (snapshot == master or snapshot.startswith(master)
                                or master.startswith(snapshot)):
        return True

    def presentation_key(value: str) -> str:
        # Some official TPEx/MOPS feeds encode an unavailable CJK glyph as a
        # parenthesized radical sequence, while another official feed emits a
        # shortened radical rendering (for example ``(方方土)`` vs ``方土``).
        # Normalize only duplicated characters inside parentheses; do not
        # broadly collapse repeated characters in ordinary company names.
        value = value.replace("（", "(").replace("）", ")")
        value = re.sub(
            r"\(([^()]*)\)",
            lambda match: re.sub(r"(.)\1+", r"\1", match.group(1)),
            value,
        )
        return re.sub(r"\s+", "", value).rstrip("*")

    left, right = presentation_key(snapshot), presentation_key(master)
    return bool(left and right and (left == right or left.startswith(right)
                                    or right.startswith(left)))


def _trading_status_url(day: date) -> str:
    return TRADING_STATUS_BASE_URL + "?" + urlencode({
        "date": day.strftime("%Y/%m/%d"), "response": "json",
    })


def _parse_trading_status(body: bytes, snapshot_date: date) -> dict[str, dict]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid TPEx trading-status JSON") from exc
    if not isinstance(payload, dict) or _PAGING_KEYS & payload.keys():
        raise MalformedSourceError("invalid TPEx trading-status envelope")
    if (str(payload.get("stat", "")).lower() != "ok"
            or str(payload.get("date", "")) != snapshot_date.strftime("%Y%m%d")):
        raise DataValidationError("TPEx trading-status date/status mismatch")
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise MalformedSourceError("TPEx trading-status tables missing")
    matches = []
    required = {"證券代號", "證券名稱", "停止交易"}
    for table in tables:
        if not isinstance(table, dict):
            raise MalformedSourceError("invalid TPEx trading-status table")
        fields, rows = table.get("fields"), table.get("data")
        if not isinstance(fields, list) or not isinstance(rows, list):
            raise MalformedSourceError("invalid TPEx trading-status schema")
        if required <= set(fields):
            declared = str(table.get("totalCount", "")).replace(",", "").strip()
            if not re.fullmatch(r"\d+", declared) or int(declared) != len(rows):
                raise MalformedSourceError("truncated TPEx trading-status response")
            if len(fields) != len(set(fields)):
                raise MalformedSourceError("duplicate TPEx trading-status field")
            matches.append((fields, rows))
    if len(matches) != 1:
        raise MalformedSourceError("ambiguous TPEx trading-status table")
    fields, rows = matches[0]
    output = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise MalformedSourceError("TPEx trading-status row width mismatch")
        values = dict(zip(fields, row))
        code = str(values["證券代號"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9]+", code) or code in output:
            raise MalformedSourceError("invalid or duplicate TPEx trading-status symbol")
        stopped = str(values["停止交易"]).strip().upper()
        if stopped not in {"", "Y", "Ｙ"}:
            raise MalformedSourceError("unknown TPEx trading-status flag")
        output[code] = {
            "company_name": str(values["證券名稱"]).strip(),
            "stopped": stopped in {"Y", "Ｙ"},
        }
    return output


def _index_latest(rows: list[dict], eligible_symbols: set[str], source: str):
    output = {}
    seen = set()
    for row in rows:
        raw_code = row["SecuritiesCompanyCode"]
        if not isinstance(raw_code, (str, int)):
            raise MalformedSourceError(f"malformed {source} symbol")
        code = str(raw_code).strip()
        if not re.fullmatch(r"[A-Za-z0-9]+", code):
            raise MalformedSourceError(&"malformed {source} symbol")
        if code in seen:
            raise MalformedSourceError(f"duplicate {source} symbol")
        seen.add(code)
        # Full-market snapshots include excluded instruments. Positive company-
        # master membership selects the supported ordinary-share universe.
        if code in eligible_symbols:
            output[code] = row
    return output


def _record(identity: SecurityIdentity, data_type: str, status: str,
            reason_code: str, official_source: str, source_date: date, evidence: dict,
            *, source_interval: str | None = None) -> dict:
    if status not in _STATUSES:
        raise DataValidationError("invalid TPEx universe resolution status")
    return {
        "symbol": identity.symbol,
        "canonical_symbol": identity.canonical_symbol,
        "market": identity.market,
        "data_type": data_type,
        "status": status,
        "reason_code": reason_code,
        "official_source": official_source,
        "source_date": source_date.isoformat(),
        "source_interval": source_interval,
        "evidence": evidence,
    }


def resolve_missing_tpex_observation(
        identity: SecurityIdentity, data_type: str, snapshot_date: date, *,
        transport: HttpTransport | None = None, timeout=30.0, retries=2,
        response_cache: dict[tuple[str, str, str], HttpResponse] | None = None) -> dict:
    """Resolve one snapshot omission using official per-symbol monthly data."""
    if data_type not in {"LATEST_CLOSE", "LATEST_PE"}:
        raise DataValidationError("unsupported TPEx universe data type")
    cache = response_cache if response_cache is not None else {}
    month = snapshot_date.replace(day=1)

    def request(endpoint: str) -> tuple[HttpResponse, str]:
        if endpoint == "tradingStatus":
            url = _trading_status_url(snapshot_date)
            key = (endpoint, "ALL", snapshot_date.isoformat())
        else:
            url = build_history_url(endpoint, identity.symbol, month)
            key = (endpoint, identity.symbol, month.isoformat())
        if key not in cache:
            cache[key] = get_with_retry(url, transport, timeout, retries, backoff=2)
        return cache[key], url

    status_response, status_url = request("tradingStatus")
    status = _parse_trading_status(status_response.body, snapshot_date).get(identity.symbol)
    if status is not None and status["stopped"]:
        if not (_official_name_compatible(
                    status["company_name"], identity.company_short_name)
                or _official_name_compatible(
                    status["company_name"], identity.company_name)):
            raise DataValidationError("TPEx trading-status company identity mismatch")
        return _record(
            identity, data_type, LEGITIMATE_UNAVAILABLE_PROVEN,
            "SUSPENDED_TRADING", status_url, snapshot_date, {
                "method": "OFFICIAL_DAILY_TRADING_STATUS_ROW",
                "stopped_trading": True,
                "official_company_name": status["company_name"],
                "declared_rowset_validated": True,
                "sha256": raw_hash(status_response.body),
            }, source_interval=snapshot_date.isoformat())

    # The code-bearing close response also supplies paired positive identity
    # when the historical PE envelope omits code/name.
    close_response, close_url = request("tradingStock")
    observed_name, closes = parse_close_payload(
        close_response.body, identity.symbol, month, identity.company_short_name)
    interval = month.strftime("%Y-%m")
    if data_type == "LATEST_CLOSE":
        if snapshot_date not in closes:
            return _record(
                identity, data_type, LEGITIMATE_UNAVAILABLE_PROVEN,
                "NO_OFFICIAL_CLOSE_OBSERVATION_ON_SNAPSHOT_DATE", close_url,
                snapshot_date, {
                    "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROWSET",
                    "target_date_present": False,
                    "declared_rowset_validated": True,
                    "monthly_row_count": len(closes),
                    "sha256": raw_hash(close_response.body),
                }, source_interval=interval)
        close = closes[snapshot_date]
        if close is None:
            return _record(
                identity, data_type, LEGITIMATE_UNAVAILABLE_PROVEN,
                "OFFICIAL_CLOSE_UNAVAILABLE", close_url, snapshot_date, {
                    "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROW",
                    "target_date_present": True,
                    "official_value_state": "UNAVAILABLE",
                    "sha256": raw_hash(close_response.body),
                }, source_interval=interval)
        return _record(
            identity, data_type, AVAILABLE, "OFFICIAL_CLOSE_AVAILABLE",
            close_url, snapshot_date, {
                "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROW",
                "target_date_present": True,
                "official_value_state": "POSITIVE",
                "sha256": raw_hash(close_response.body),
            }, source_interval=interval)

    pe_response, pe_url = request("peQryStock")
    pes = parse_valuation_payload_with_period(
        pe_response.body, identity.symbol, month,
        observed_name or identity.company_short_name)
    if snapshot_date not in pes:
        # A complete rowset proves absence, but the published source contract
        # does not prove that absence means a legitimately unavailable PE.
        return _record(
            identity, data_type, UNRESOLVED,
            "OFFICIAL_PE_ROW_ABSENT_WITHOUT_UNAVAILABLE_SEMANTICS", pe_url,
            snapshot_date, {
                "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROWSET",
                "target_date_present": False,
                "declared_rowset_validated": True,
                "monthly_row_count": len(pes),
                "paired_close_identity_sha256": raw_hash(close_response.body),
                "sha256": raw_hash(pe_response.body),
            }, source_interval=interval)
    point = pes[snapshot_date]
    if point.official_pe is None:
        return _record(
            identity, data_type, LEGITIMATE_UNAVAILABLE_PROVEN,
            "OFFICIAL_PE_UNAVAILABLE", pe_url, snapshot_date, {
                "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROW",
                "target_date_present": True,
                "official_value_state": "UNAVAILABLE",
                "paired_close_identity_sha256": raw_hash(close_response.body),
                "sha256": raw_hash(pe_response.body),
            }, source_interval=interval)
    return _record(
        identity, data_type, AVAILABLE, "OFFICIAL_PE_AVAILABLE",
        pe_url, snapshot_date, {
            "method": "OFFICIAL_PER_SYMBOL_MONTHLY_ROW",
            "target_date_present": True,
            "official_value_state": "POSITIVE",
            "paired_close_identity_sha256": raw_hash(close_response.body),
            "sha256": raw_hash(pe_response.body),
        }, source_interval=interval)


def audit_current_tpex_universe(
        *, transport: HttpTransport | None = None, timeout=30.0, retries=2,
        missing_resolver: Callable[..., dict | None] | None = None) -> dict:
    identities = fetch_security_master(
        TPEX, transport=transport, timeout=timeout, retries=retries)
    responses = {}
    for key, url in (("close", LATEST_CLOSE_URL), ("pe", LATEST_PE_URL)):
        responses[key] = get_with_retry(url, transport, timeout, retries, backoff=2)
    close_rows = _rows(responses["close"].body, {
        "Date", "SecuritiesCompanyCode", "CompanyName", "Close"}, "TPEx latest close")
    pe_rows = _rows(responses["pe"].body, {
        "Date", "SecuritiesCompanyCode", "CompanyName", "PriceEarningRatio"},
        "TPEx latest PE")
    latest_close_date = max(_date_key(row["Date"]) for row in close_rows)
    latest_pe_date = max(_date_key(row["Date"]) for row in pe_rows)
    close_latest = [row for row in close_rows if _date_key(row["Date"]) == latest_close_date]
    pe_latest = [row for row in pe_rows if _date_key(row["Date"]) == latest_pe_date]

    eligible_symbols = {item.symbol for item in identities}
    close_by_code = _index_latest(close_latest, eligible_symbols, "TPEx latest close")
    pe_by_code = _index_latest(pe_latest, eligible_symbols, "TPEx latest PE")
    resolver = missing_resolver or resolve_missing_tpex_observation
    response_cache: dict[tuple[str, str, str], HttpResponse] = {}
    records = []

    def snapshot_record(identity: SecurityIdentity, data_type: str, row: dict,
                        snapshot_date: date, source_url: str, digest: str) -> dict:
        value_key = "Close" if data_type == "LATEST_CLOSE" else "PriceEarningRatio"
        field = "close" if data_type == "LATEST_CLOSE" else "PE"
        if not _official_name_compatible(row["CompanyName"], identity.company_short_name):
            raise DataValidationError(f"latest {field} company identity mismatch")
        available = _positive_or_missing(
            row[value_key], field, nonpositive_unavailable=(data_type == "LATEST_PE"))
        return _record(
            identity, data_type,
            AVAILABLE if available else LEGITIMATE_UNAVAILABLE_PROVEN,
            (f"OFFICIAL_{field.upper()}_AVAILABLE" if available
             else f"OFFICIAL_{field.upper()}_UNAVAILABLE"),
            source_url, snapshot_date, {
                "method": "LATEST_OFFICIAL_SNAPSHOT_ROW",
                "target_date_present": True,
                "official_value_state": "POSITIVE" if available else "UNAVAILABLE",
                "snapshot_global_completeness_proven": False,
                "sha256": digest,
            }, source_interval=snapshot_date.isoformat())

    for identity in identities:
        for data_type, by_code, snapshot_date, source_url, digest in (
            ("LATEST_CLOSE", close_by_code, latest_close_date, LATEST_CLOSE_URL,
             raw_hash(responses["close"].body)),
            ("LATEST_PE", pe_by_code, latest_pe_date, LATEST_PE_URL,
             raw_hash(responses["pe"].body)),
        ):
            row = by_code.get(identity.symbol)
            try:
                if row is not None:
                    record = snapshot_record(
                        identity, data_type, row, snapshot_date, source_url, digest)
                else:
                    record = resolver(
                        identity, data_type, snapshot_date,
                        transport=transport, timeout=timeout, retries=retries,
                        response_cache=response_cache)
                    if record is None:
                        record = _record(
                            identity, data_type, UNRESOLVED,
                            "SNAPSHOT_MISSING_AND_NO_OFFICIAL_RESOLUTION_EVIDENCE",
                            source_url, snapshot_date, {
                                "method": "BOUNDED_PER_SYMBOL_RESOLUTION",
                                "snapshot_global_completeness_proven": False,
                                "resolution_evidence_available": False,
                            })
                    if (record.get("symbol") != identity.symbol
                            or record.get("data_type") != data_type
                            or record.get("status") not in _STATUSES):
                        raise DataValidationError("invalid per-symbol resolution evidence")
                records.append(record)
            except MarketDataError as exc:
                records.append(_record(
                    identity, data_type, FAILURE, type(exc).__name__.upper(),
                    source_url, snapshot_date, {
                        "method": "BOUNDED_PER_SYMBOL_RESOLUTION",
                        "error": str(exc),
                    }))

    def count(data_type: str, status: str) -> int:
        return sum(record["data_type"] == data_type and record["status"] == status
                   for record in records)

    close_counts = {status: count("LATEST_CLOSE", status) for status in _STATUSES}
    pe_counts = {status: count("LATEST_PE", status) for status in _STATUSES}
    gate_pass = (close_counts[UNRESOLVED] == close_counts[FAILURE] == 0
                 and pe_counts[UNRESOLVED] == pe_counts[FAILURE] == 0)
    return {
        "schema_version": "TWSTOCK-TPEX-UNIVERSE-AUDIT-002",
        "generated_at": utc_now_iso(),
        "market": TPEX,
        "supported_security_type": "ORDINARY_COMMON_SHARE",
        "universe_size": len(identities),
        "identity_pass_count": len(identities),
        "identity_failure_count": 0,
        "latest_close_date": latest_close_date.isoformat(),
        "latest_close_available_count": close_counts[AVAILABLE],
        "latest_close_legitimate_unavailable_proven_count": close_counts[
            LEGITIMATE_UNAVAILABLE_PROVEN],
        "latest_close_unresolved_count": close_counts[UNRESOLVED],
        "latest_close_failure_count": close_counts[FAILURE],
        "latest_pe_date": latest_pe_date.isoformat(),
        "latest_pe_available_count": pe_counts[AVAILABLE],
        "latest_pe_legitimate_unavailable_proven_count": pe_counts[
            LEGITIMATE_UNAVAILABLE_PROVEN],
        "latest_pe_unresolved_count": pe_counts[UNRESOLVED],
        "latest_pe_failure_count": pe_counts[FAILURE],
        "acceptance_gate_pass": gate_pass,
        "snapshot_completeness": {
            "global_completeness_proven": False,
            "contract": "BARE_JSON_ARRAY_WITHOUT_DECLARED_TOTAL_OR_PAGINATION_METADATA",
            "latest_close_response_row_count": len(close_rows),
            "latest_close_date_row_count": len(close_latest),
            "latest_pe_response_row_count": len(pe_rows),
            "latest_pe_date_row_count": len(pe_latest),
            "missing_symbol_policy": (
                "Snapshot absence is not evidence of legitimate unavailability; "
                "bounded official per-symbol resolution is mandatory."),
        },
        "evidence_records": records,
        "unresolved_records": [record for record in records
                               if record["status"] == UNRESOLVED],
        "failure_records": [record for record in records
                            if record["status"] == FAILURE],
        "sources": [
            {"purpose": "identity", "url": TPEX_MASTER_URL},
            {"purpose": "latest_close", "url": LATEST_CLOSE_URL,
             "sha256": raw_hash(responses["close"].body)},
            {"purpose": "latest_pe", "url": LATEST_PE_URL,
             "sha256": raw_hash(responses["pe"].body)},
        ],
    }
