from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from twstock_data.errors import DataValidationError, MalformedSourceError, SourceUnavailableError
from twstock_data.http import HttpTransport, get_with_retry
from twstock_data.models import MarketDataRecord, SourceTier
from twstock_data.normalization import source_symbol_from_input
from twstock_data.sources.twse import fetch_twse_daily

from .pe_river import ExperimentInputError

TAIPEI = ZoneInfo("Asia/Taipei")
YAHOO_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
VERIFIED_FORWARD_VINTAGE_STATUS = "VERIFIED_ANALYST_CONSENSUS_VINTAGE"


@dataclass(frozen=True)
class DelayedQuote:
    symbol: str
    price_twd: Decimal
    observed_at: str
    market_state: str
    previous_close_twd: Decimal | None
    source: str
    source_tier: str
    data_status: str
    source_url: str


@dataclass(frozen=True)
class FundamentalObservation:
    period: str
    period_end: date
    publication_date: date
    research_available_date: date
    gross_margin_pct: Decimal
    operating_margin_pct: Decimal
    diluted_eps_twd: Decimal
    data_status: str
    source_note: str
    source_url: str


@dataclass(frozen=True)
class MonthlyRevenueObservation:
    month: str
    revenue_million_twd: Decimal
    data_status: str
    source_note: str
    source_url: str


@dataclass(frozen=True)
class ForwardEPSVintage:
    as_of_date: date
    ntm_eps_twd: Decimal
    source_name: str
    data_status: str
    source_url: str
    source_note: str


class LiveExperimentError(RuntimeError):
    """Raised when the live experiment cannot obtain a defensible input."""


def positive_decimal(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LiveExperimentError(f"{field} must be numeric: {value!r}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise LiveExperimentError(f"{field} must be positive and finite")
    return parsed


def optional_positive_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def build_yahoo_chart_url(symbol: str) -> str:
    query = urlencode(
        {
            "interval": "1m",
            "range": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    return f"{YAHOO_CHART_ENDPOINT.format(symbol=symbol)}?{query}"


def parse_yahoo_quote_payload(
    payload: dict[str, object], *, expected_symbol: str, source_url: str = ""
) -> DelayedQuote:
    chart = payload.get("chart")
    if not isinstance(chart, dict) or chart.get("error"):
        raise LiveExperimentError(f"Yahoo chart error or missing chart: {chart!r}")
    result = chart.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise LiveExperimentError("Yahoo chart payload has no result")
    first = result[0]
    meta = first.get("meta")
    if not isinstance(meta, dict):
        raise LiveExperimentError("Yahoo chart result is missing meta")
    symbol = str(meta.get("symbol", "")).strip()
    if symbol != expected_symbol:
        raise LiveExperimentError(
            f"Yahoo symbol mismatch: expected {expected_symbol}, got {symbol or 'blank'}"
        )
    currency = str(meta.get("currency", "")).strip().upper()
    if currency and currency != "TWD":
        raise LiveExperimentError(f"Yahoo currency mismatch: expected TWD, got {currency}")
    raw_price = meta.get("regularMarketPrice")
    if raw_price in (None, ""):
        indicators = first.get("indicators")
        quotes = indicators.get("quote") if isinstance(indicators, dict) else None
        closes = (
            quotes[0].get("close")
            if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict)
            else None
        )
        if isinstance(closes, list):
            raw_price = next((item for item in reversed(closes) if item is not None), None)
    price = positive_decimal(raw_price, field="Yahoo regularMarketPrice")
    raw_timestamp = meta.get("regularMarketTime")
    if raw_timestamp is None and isinstance(first.get("timestamp"), list) and first["timestamp"]:
        raw_timestamp = first["timestamp"][-1]
    try:
        timestamp = int(raw_timestamp)
    except (TypeError, ValueError) as exc:
        raise LiveExperimentError("Yahoo quote has no usable timestamp") from exc
    observed = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(TAIPEI)
    return DelayedQuote(
        symbol=symbol,
        price_twd=price,
        observed_at=observed.isoformat(timespec="seconds"),
        market_state=str(meta.get("marketState", "UNKNOWN") or "UNKNOWN"),
        previous_close_twd=optional_positive_decimal(
            meta.get("previousClose", meta.get("chartPreviousClose"))
        ),
        source="YAHOO_FINANCE_CHART",
        source_tier="SECONDARY",
        data_status="SECONDARY_DELAYED_QUOTE",
        source_url=source_url,
    )


def fetch_yahoo_delayed_quote(
    symbol: str,
    *,
    transport: HttpTransport | None = None,
    timeout: float = 10,
    retries: int = 2,
) -> DelayedQuote:
    url = build_yahoo_chart_url(symbol)
    response = get_with_retry(url, transport=transport, timeout=timeout, retries=retries)
    try:
        payload = json.loads(response.body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveExperimentError("Yahoo quote response is not valid JSON") from exc
    return parse_yahoo_quote_payload(
        payload, expected_symbol=symbol, source_url=response.url
    )


def _record_from_csv_row(row: dict[str, str]) -> MarketDataRecord:
    try:
        return MarketDataRecord(
            source=row["source"].strip(),
            source_tier=SourceTier(row["source_tier"].strip()),
            source_symbol=row["source_symbol"].strip(),
            canonical_symbol=row["canonical_symbol"].strip(),
            market=row["market"].strip(),
            trade_date=row["trade_date"].strip(),
            traded_share_volume=int(row["traded_share_volume"]),
            official_traded_value_twd=int(row["official_traded_value_twd"]),
            open_price=float(row["open_price"]),
            high_price=float(row["high_price"]),
            low_price=float(row["low_price"]),
            close_price=float(row["close_price"]),
            transaction_count=int(row["transaction_count"]),
            retrieved_at=row.get("retrieved_at", "").strip(),
            source_reference=row.get("source_reference", "").strip(),
            raw_content_hash=row.get("raw_content_hash", "").strip(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveExperimentError(f"Invalid normalized market-data row: {exc}") from exc


def load_normalized_market_csv(
    path: Path, *, expected_symbol: str
) -> tuple[MarketDataRecord, ...]:
    if not path.is_file():
        raise LiveExperimentError(f"Normalized market-data CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        records = [_record_from_csv_row(row) for row in reader]
    if not records:
        raise LiveExperimentError(f"Normalized market-data CSV has no rows: {path}")
    for record in records:
        if record.canonical_symbol != expected_symbol:
            raise LiveExperimentError(
                f"Market CSV symbol mismatch: {record.canonical_symbol} != {expected_symbol}"
            )
        if record.source != "TWSE" or record.source_tier is not SourceTier.PRIMARY:
            raise LiveExperimentError("Market CSV must contain TWSE PRIMARY records")
    records.sort(key=lambda item: item.trade_date)
    dates = [record.trade_date for record in records]
    if len(dates) != len(set(dates)):
        raise LiveExperimentError("Market CSV contains duplicate trade dates")
    return tuple(records)


def official_close_fallback(records: Sequence[MarketDataRecord]) -> DelayedQuote:
    if not records:
        raise LiveExperimentError("No official completed-session price is available")
    latest = records[-1]
    return DelayedQuote(
        symbol=latest.canonical_symbol,
        price_twd=positive_decimal(latest.close_price, field="TWSE close_price"),
        observed_at=f"{latest.trade_date}T13:30:00+08:00",
        market_state="COMPLETED_SESSION",
        previous_close_twd=(
            optional_positive_decimal(records[-2].close_price)
            if len(records) >= 2
            else None
        ),
        source="TWSE_STOCK_DAY",
        source_tier="PRIMARY",
        data_status="OFFICIAL_COMPLETED_SESSION_CLOSE_FALLBACK",
        source_url=latest.source_reference,
    )


def resolve_quote(
    symbol: str,
    official_records: Sequence[MarketDataRecord],
    *,
    transport: HttpTransport | None = None,
) -> tuple[DelayedQuote, str | None]:
    try:
        return fetch_yahoo_delayed_quote(symbol, transport=transport), None
    except (LiveExperimentError, SourceUnavailableError) as exc:
        return official_close_fallback(official_records), str(exc)


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ExperimentInputError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ExperimentInputError(f"CSV has no data rows: {path}")
    return rows


def _iso(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ExperimentInputError(f"{field} must be ISO YYYY-MM-DD: {raw!r}") from exc


def load_quarterly_fundamentals(path: Path) -> list[FundamentalObservation]:
    observations: list[FundamentalObservation] = []
    for row_number, row in enumerate(_rows(path), start=2):
        try:
            item = FundamentalObservation(
                period=row["period"].strip(),
                period_end=_iso(row["period_end"], "period_end"),
                publication_date=_iso(row["publication_date"], "publication_date"),
                research_available_date=_iso(
                    row["research_available_date"], "research_available_date"
                ),
                gross_margin_pct=positive_decimal(
                    row["gross_margin_pct"], field="gross_margin_pct"
                ),
                operating_margin_pct=positive_decimal(
                    row["operating_margin_pct"], field="operating_margin_pct"
                ),
                diluted_eps_twd=positive_decimal(
                    row["diluted_eps_twd"], field="diluted_eps_twd"
                ),
                data_status=row.get("data_status", "UNKNOWN").strip() or "UNKNOWN",
                source_note=row.get("source_note", "").strip(),
                source_url=row.get("source_url", "").strip(),
            )
        except KeyError as exc:
            raise ExperimentInputError(
                f"Row {row_number}: missing {exc.args[0]}"
            ) from exc
        if item.research_available_date < item.publication_date:
            raise ExperimentInputError(
                f"Row {row_number}: research_available_date precedes publication_date"
            )
        observations.append(item)
    return sorted(observations, key=lambda item: item.period_end)


def load_monthly_revenue(path: Path) -> list[MonthlyRevenueObservation]:
    observations: list[MonthlyRevenueObservation] = []
    seen: set[str] = set()
    for row_number, row in enumerate(_rows(path), start=2):
        month = row.get("month", "").strip()
        try:
            date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise ExperimentInputError(
                f"Row {row_number}: month must be YYYY-MM"
            ) from exc
        if month in seen:
            raise ExperimentInputError(f"Row {row_number}: duplicate month {month}")
        seen.add(month)
        observations.append(
            MonthlyRevenueObservation(
                month=month,
                revenue_million_twd=positive_decimal(
                    row.get("revenue_million_twd"), field="revenue_million_twd"
                ),
                data_status=row.get("data_status", "UNKNOWN").strip() or "UNKNOWN",
                source_note=row.get("source_note", "").strip(),
                source_url=row.get("source_url", "").strip(),
            )
        )
    return sorted(observations, key=lambda item: item.month)


def load_forward_eps_vintages(path: Path) -> list[ForwardEPSVintage]:
    """Load only genuine point-in-time analyst-consensus vintages.

    A header-only file is valid and means the historical Forward P/E feature must
    fail closed. Manual scenarios and ex-post actual EPS are prohibited here.
    """
    if not path.is_file():
        raise ExperimentInputError(f"Input file not found: {path}")
    required = {
        "as_of_date",
        "ntm_eps_twd",
        "source_name",
        "data_status",
        "source_url",
        "source_note",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ExperimentInputError(
                "forward_eps_vintages.csv is missing required columns"
            )
        rows = list(reader)
    observations: list[ForwardEPSVintage] = []
    seen_dates: set[date] = set()
    for row_number, row in enumerate(rows, start=2):
        as_of_date = _iso(row.get("as_of_date", ""), "as_of_date")
        if as_of_date in seen_dates:
            raise ExperimentInputError(
                f"Row {row_number}: duplicate Forward EPS vintage date {as_of_date}"
            )
        seen_dates.add(as_of_date)
        status = row.get("data_status", "").strip()
        if status != VERIFIED_FORWARD_VINTAGE_STATUS:
            raise ExperimentInputError(
                f"Row {row_number}: historical Forward EPS requires "
                f"{VERIFIED_FORWARD_VINTAGE_STATUS}; got {status or 'blank'}"
            )
        source_name = row.get("source_name", "").strip()
        source_url = row.get("source_url", "").strip()
        if not source_name or not source_url:
            raise ExperimentInputError(
                f"Row {row_number}: source_name and source_url are required"
            )
        observations.append(
            ForwardEPSVintage(
                as_of_date=as_of_date,
                ntm_eps_twd=positive_decimal(
                    row.get("ntm_eps_twd"), field="ntm_eps_twd"
                ),
                source_name=source_name,
                data_status=status,
                source_url=source_url,
                source_note=row.get("source_note", "").strip(),
            )
        )
    return sorted(observations, key=lambda item: item.as_of_date)


def fetch_history(
    symbol: str,
    start: date,
    end: date,
    *,
    csv_path: Path | None = None,
) -> tuple[MarketDataRecord, ...]:
    if csv_path is not None:
        return load_normalized_market_csv(csv_path, expected_symbol=symbol)
    try:
        records = fetch_twse_daily(
            source_symbol_from_input(symbol), start.isoformat(), end.isoformat()
        )
    except (SourceUnavailableError, DataValidationError, MalformedSourceError) as exc:
        raise LiveExperimentError(
            f"TWSE history fetch failed for {symbol}: {exc}"
        ) from exc
    if not records:
        raise LiveExperimentError(f"TWSE returned no history for {symbol}")
    return records
