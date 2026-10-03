"""Official positive-evidence security identity and market routing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re

from ..errors import DataValidationError, MalformedSourceError
from ..http import HttpTransport, get_with_retry

TWSE = "TWSE"
TPEX = "TPEX"
AUTO = "AUTO"
ORDINARY_COMMON_SHARE = "ORDINARY_COMMON_SHARE"

TWSE_MASTER_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_MASTER_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


@dataclass(frozen=True)
class SecurityIdentity:
    symbol: str
    canonical_symbol: str
    market: str
    security_type: str
    company_name: str
    company_short_name: str
    identity_source: str
    identity_as_of: date
    listing_date: date | None


def validate_symbol(symbol: str) -> None:
    if not re.fullmatch(r"[1-9][0-9]{3}", symbol):
        raise DataValidationError("symbol must be a four-digit ordinary-share code")


def canonical_symbol(symbol: str, market: str) -> str:
    validate_symbol(symbol)
    if market == TWSE:
        return f"{symbol}.TW"
    if market == TPEX:
        return f"{symbol}.TWO"
    raise DataValidationError("market must be TWSE or TPEX")


def _compact_date(value: object, field: str) -> date:
    text = str(value).strip()
    if not re.fullmatch(r"\d{7,8}", text):
        raise MalformedSourceError(f"invalid official identity {field}")
    year_text, tail = (text[:3], text[3:]) if len(text) == 7 else (text[:4], text[4:])
    year = int(year_text) + 1911 if len(text) == 7 else int(year_text)
    try:
        return date(year, int(tail[:2]), int(tail[2:]))
    except ValueError as exc:
        raise MalformedSourceError(f"invalid official identity {field}") from exc


def _decode(body: bytes, market: str) -> tuple[SecurityIdentity, ...]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedSourceError("invalid official security-master JSON") from exc
    if not isinstance(payload, list) or not payload:
        raise MalformedSourceError("official security master must be a nonempty array")
    mapping = ({
        "symbol": "公司代號", "name": "公司名稱", "short": "公司簡稱",
        "as_of": "出表日期", "listing": "上市日期", "par": "普通股每股面額",
        "preferred": "特別股", "industry": "產業別",
    } if market == TWSE else {
        "symbol": "SecuritiesCompanyCode", "name": "CompanyName",
        "short": "CompanyAbbreviation", "as_of": "Date",
        "listing": "DateOfListing", "par": "ParValueOfCommonStock",
        "preferred": "PreferredStock.shares",
    })
    required = set(mapping.values())
    output: list[SecurityIdentity] = []
    seen: set[str] = set()
    source = TWSE_MASTER_URL if market == TWSE else TPEX_MASTER_URL
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict) or required - raw.keys():
            raise MalformedSourceError(f"official {market} security-master schema mismatch")
        symbol = str(raw[mapping["symbol"]]).strip()
        # These MOPS company-register datasets enumerate listed companies, not
        # ETFs, ETNs, warrants, bonds, or emerging-board instruments.  TWSE's
        # dataset does also contain depositary receipts: official industry 91
        # is the TDR classification.  Exclude those before applying the
        # ordinary-share contract.  Non-four-digit company codes are likewise
        # outside this stage's input universe, not a malformed master row.
        if market == TWSE and str(raw[mapping["industry"]]).strip() == "91":
            continue
        if not re.fullmatch(r"[1-9][0-9]{3}", symbol):
            continue
        if symbol in seen:
            raise MalformedSourceError(f"duplicate {market} company identity")
        seen.add(symbol)
        name = str(raw[mapping["name"]]).strip()
        short = str(raw[mapping["short"]]).strip()
        par = str(raw[mapping["par"]]).strip()
        if not name or not short or not par or par in {"-", "--", "－"}:
            raise MalformedSourceError(f"incomplete {market} ordinary-share identity")
        listing_raw = str(raw[mapping["listing"]]).strip()
        output.append(SecurityIdentity(
            symbol=symbol,
            canonical_symbol=canonical_symbol(symbol, market),
            market=market,
            security_type=ORDINARY_COMMON_SHARE,
            company_name=name,
            company_short_name=short,
            identity_source=source,
            identity_as_of=_compact_date(raw[mapping["as_of"]], "as-of date"),
            listing_date=_compact_date(listing_raw, "listing date") if listing_raw else None,
        ))
    return tuple(output)


def parse_security_master(body: bytes, market: str) -> tuple[SecurityIdentity, ...]:
    if market not in {TWSE, TPEX}:
        raise DataValidationError("market must be TWSE or TPEX")
    return _decode(body, market)


def fetch_security_master(market: str, *, transport: HttpTransport | None = None,
                          timeout=30.0, retries=2) -> tuple[SecurityIdentity, ...]:
    url = TWSE_MASTER_URL if market == TWSE else TPEX_MASTER_URL
    return parse_security_master(
        get_with_retry(url, transport, timeout, retries, backoff=2).body, market)


def resolve_security_identity(symbol: str, requested_market: str = AUTO, *,
                              transport: HttpTransport | None = None,
                              timeout=30.0, retries=2) -> SecurityIdentity:
    validate_symbol(symbol)
    requested_market = requested_market.upper()
    if requested_market not in {AUTO, TWSE, TPEX}:
        raise DataValidationError("market must be AUTO, TWSE, or TPEX")
    markets = (TWSE, TPEX) if requested_market == AUTO else (requested_market,)
    matches = []
    for market in markets:
        by_symbol = {item.symbol: item for item in fetch_security_master(
            market, transport=transport, timeout=timeout, retries=retries)}
        if symbol in by_symbol:
            matches.append(by_symbol[symbol])
    if requested_market == AUTO:
        if len(matches) != 1:
            reason = "ambiguous" if len(matches) > 1 else "unavailable"
            raise DataValidationError(f"official security identity is {reason} for {symbol}")
        return matches[0]
    if not matches:
        # Positive identity is mandatory; explicit market selection never falls
        # through to the other exchange.
        raise DataValidationError(
            f"{symbol} is not an officially identified {requested_market} ordinary common share")
    return matches[0]
