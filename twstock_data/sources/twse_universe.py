from __future__ import annotations

from dataclasses import dataclass
import json
import re

from ..errors import DataValidationError, MalformedSourceError
from ..http import HttpTransport, get_with_retry


TWSE_LISTED_COMPANY_ENDPOINT = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
_COMMON_STOCK_CODE = re.compile(r"^[0-9]{4}$")


@dataclass(frozen=True)
class ListedCompany:
    symbol: str
    name: str
    industry_code: str
    listing_date: str


def fetch_twse_listed_common_stock_universe(
    *,
    transport: HttpTransport | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> tuple[ListedCompany, ...]:
    response = get_with_retry(
        TWSE_LISTED_COMPANY_ENDPOINT,
        transport=transport,
        timeout=timeout,
        retries=retries,
    )
    return parse_twse_listed_company_payload(response.body)


def parse_twse_listed_company_payload(body: bytes) -> tuple[ListedCompany, ...]:
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MalformedSourceError("invalid TWSE listed-company JSON") from error
    if not isinstance(payload, list):
        raise MalformedSourceError("TWSE listed-company payload must be an array")
    companies: list[ListedCompany] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise MalformedSourceError("TWSE listed-company row must be an object")
        symbol = str(row.get("公司代號", "")).strip()
        short_name = str(row.get("公司簡稱", "")).strip()
        if not _COMMON_STOCK_CODE.fullmatch(symbol) or "-DR" in short_name.upper():
            continue
        if symbol in seen:
            raise DataValidationError(f"duplicate TWSE listed-company symbol: {symbol}")
        name = str(row.get("公司名稱", "")).strip()
        if not name or not short_name:
            raise DataValidationError(f"missing TWSE company name for {symbol}")
        seen.add(symbol)
        companies.append(
            ListedCompany(
                symbol=symbol,
                name=short_name,
                industry_code=str(row.get("產業別", "")).strip(),
                listing_date=str(row.get("上市日期", "")).strip(),
            )
        )
    if not companies:
        raise DataValidationError("TWSE common-stock universe is empty")
    return tuple(sorted(companies, key=lambda item: item.symbol))
