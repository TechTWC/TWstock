"""Lightweight official current-universe compatibility audit for TPEx."""
from __future__ import annotations

from datetime import date
import json
import math
import re

from ..errors import DataValidationError, MalformedSourceError
from ..http import HttpTransport, get_with_retry
from ..normalization import raw_hash, utc_now_iso
from .security_identity import TPEX, TPEX_MASTER_URL, fetch_security_master

LATEST_CLOSE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
LATEST_PE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
MISSING = {"", "-", "--", "---", "N/A", "NA", "null", "－"}


def _rows(body: bytes, required: set[str], source: str):
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError(f"invalid {source} JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise MalformedSourceError(f"{source} must be a nonempty array")
    for row in payload:
        if not isinstance(row, dict) or required - row.keys():
            raise MalformedSourceError(f"{source} schema mismatch")
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


def _positive_or_missing(value: object, field: str) -> bool:
    text = str(value).replace(",", "").strip()
    if text in MISSING:
        return False
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        raise MalformedSourceError(f"malformed TPEx latest {field}")
    number = float(text)
    if not math.isfinite(number) or number <= 0:
        raise DataValidationError(f"nonpositive TPEx latest {field}")
    return True


def _official_name_compatible(snapshot_name: object, master_name: str) -> bool:
    snapshot = str(snapshot_name).strip().rstrip("*").strip()
    master = master_name.strip().rstrip("*").strip()
    # TPEx's company master sometimes keeps a legal-name qualifier (公司、精密、
    # 科技、電腦...) while quote/valuation snapshots publish the exchange short
    # name.  Exact code identity remains mandatory; the two official names must
    # still have a nonempty prefix relationship.
    return bool(snapshot and master and (snapshot == master or
                                         snapshot.startswith(master) or
                                         master.startswith(snapshot)))


def audit_current_tpex_universe(*, transport: HttpTransport | None = None,
                                timeout=30.0, retries=2) -> dict:
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

    def index(rows, source):
        output = {}
        for row in rows:
            code = str(row["SecuritiesCompanyCode"]).strip()
            # Full-market snapshots intentionally include ETFs, ETNs, bonds,
            # warrants and other excluded instruments.  Positive company-master
            # membership, not four-digit shape, selects the supported universe.
            if code not in eligible_symbols:
                continue
            if code in output:
                raise MalformedSourceError(f"duplicate {source} ordinary-share symbol")
            output[code] = row
        return output

    close_by_code = index(close_latest, "TPEx latest close")
    pe_by_code = index(pe_latest, "TPEx latest PE")
    close_pass = close_unavailable = pe_pass = pe_unavailable = 0
    limitations = []
    failures = []
    for identity in identities:
        close = close_by_code.get(identity.symbol)
        if close is None:
            close_unavailable += 1
            limitations.append({"symbol": identity.symbol, "source": "latest_close",
                                "reason": "no row in latest official snapshot"})
        else:
            try:
                if not _official_name_compatible(
                        close["CompanyName"], identity.company_short_name):
                    raise DataValidationError("latest close company identity mismatch")
                if _positive_or_missing(close["Close"], "close"):
                    close_pass += 1
                else:
                    close_unavailable += 1
                    limitations.append({"symbol": identity.symbol, "source": "latest_close",
                                        "reason": "official close unavailable"})
            except (DataValidationError, MalformedSourceError) as exc:
                failures.append({"symbol": identity.symbol, "source": "latest_close",
                                 "reason": str(exc)})
        pe = pe_by_code.get(identity.symbol)
        if pe is None:
            pe_unavailable += 1
            limitations.append({"symbol": identity.symbol, "source": "latest_pe",
                                "reason": "no row in latest official snapshot"})
        else:
            try:
                if not _official_name_compatible(pe["CompanyName"], identity.company_short_name):
                    raise DataValidationError("latest PE company identity mismatch")
                if _positive_or_missing(pe["PriceEarningRatio"], "PE"):
                    pe_pass += 1
                else:
                    pe_unavailable += 1
            except (DataValidationError, MalformedSourceError) as exc:
                failures.append({"symbol": identity.symbol, "source": "latest_pe",
                                 "reason": str(exc)})
    return {
        "schema_version": "TWSTOCK-TPEX-UNIVERSE-AUDIT-001",
        "generated_at": utc_now_iso(),
        "market": TPEX,
        "supported_security_type": "ORDINARY_COMMON_SHARE",
        "universe_size": len(identities),
        "identity_pass_count": len(identities),
        "latest_close_date": latest_close_date.isoformat(),
        "latest_close_pass_count": close_pass,
        "latest_close_legitimate_unavailable_count": close_unavailable,
        "latest_pe_date": latest_pe_date.isoformat(),
        "latest_pe_pass_count": pe_pass,
        "latest_pe_legitimate_unavailable_count": pe_unavailable,
        "unexpected_failure_count": len(failures),
        "unexpected_failures": failures,
        "legitimate_limitations": limitations,
        "sources": [
            {"purpose": "identity", "url": TPEX_MASTER_URL},
            {"purpose": "latest_close", "url": LATEST_CLOSE_URL,
             "sha256": raw_hash(responses["close"].body)},
            {"purpose": "latest_pe", "url": LATEST_PE_URL,
             "sha256": raw_hash(responses["pe"].body)},
        ],
    }
