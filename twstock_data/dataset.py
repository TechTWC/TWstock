from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
import re
from typing import Sequence

from .errors import DataValidationError, SourceUnavailableError
from .http import HttpTransport
from .models import (
    MarketBar,
    MarketDataRecord,
    ReconciliationIssue,
    ReconciliationResult,
    SourceState,
    SourceTier,
)
from .normalization import (
    canonical_symbol,
    source_symbol_from_input,
    stable_json_bytes,
    validate_date_range,
)
from .reconciliation import reconcile_market_data
from .sources.finmind import fetch_finmind_daily
from .sources.twse import fetch_twse_daily


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ResearchMarketDataset:
    requested_symbol: str
    source_symbol: str
    canonical_symbol: str
    requested_start: str
    requested_end: str
    source_state: SourceState
    selected_source: str
    cross_check_unavailable: bool
    bars: tuple[MarketBar, ...]
    records: tuple[MarketDataRecord, ...]
    reconciliation_issues: tuple[ReconciliationIssue, ...]
    dataset_hash: str
    raw_content_hashes: tuple[str, ...]
    retrieval_timestamps: tuple[str, ...]
    verification_sources: tuple[str, ...]
    verification_raw_content_hashes: tuple[str, ...]
    verification_retrieval_timestamps: tuple[str, ...]
    price_basis: str = "RAW_OFFICIAL_DAILY"
    adjustment_policy: str = "RAW_UNADJUSTED"
    corporate_actions_applied: bool = False

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": "TWSTOCK-RESEARCH-DATASET-001",
            "requested_symbol": self.requested_symbol,
            "source_symbol": self.source_symbol,
            "canonical_symbol": self.canonical_symbol,
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "source_state": self.source_state.value,
            "selected_source": self.selected_source,
            "cross_check_unavailable": self.cross_check_unavailable,
            "record_count": len(self.bars),
            "first_trade_date": self.bars[0].trade_date.isoformat(),
            "last_trade_date": self.bars[-1].trade_date.isoformat(),
            "dataset_hash": self.dataset_hash,
            "raw_content_hashes": list(self.raw_content_hashes),
            "retrieval_timestamps": list(self.retrieval_timestamps),
            "verification_sources": list(self.verification_sources),
            "verification_raw_content_hashes": list(
                self.verification_raw_content_hashes
            ),
            "verification_retrieval_timestamps": list(
                self.verification_retrieval_timestamps
            ),
            "reconciliation_issue_count": len(self.reconciliation_issues),
            "price_basis": self.price_basis,
            "adjustment_policy": self.adjustment_policy,
            "corporate_actions_applied": self.corporate_actions_applied,
            "research_warning": (
                "Raw unadjusted prices; corporate actions are not applied. "
                "Do not use across split/ex-right discontinuities without a separate policy."
            ),
        }


def fetch_research_dataset(
    requested_symbol: str,
    requested_start: str,
    requested_end: str,
    *,
    transport: HttpTransport | None = None,
    timeout: float = 10,
    retries: int = 2,
    token_env: str = "FINMIND_TOKEN",
    raw_cache_dir: Path | str | None = None,
    allow_secondary_only: bool = False,
) -> ResearchMarketDataset:
    """Fetch, reconcile, and promote daily market data into engine bars.

    TWSE is the primary source. FinMind is an optional secondary cross-check. A
    primary-only result is accepted and marked ``cross_check_unavailable``;
    mismatched sources fail closed. Secondary-only data requires an explicit opt-in.
    """

    validate_date_range(requested_start, requested_end)
    source_symbol = source_symbol_from_input(requested_symbol)
    expected_canonical = canonical_symbol(source_symbol)
    primary: tuple[MarketDataRecord, ...] = ()
    primary_error: str | None = None
    try:
        primary = fetch_twse_daily(
            source_symbol,
            requested_start,
            requested_end,
            transport=transport,
            timeout=timeout,
            retries=retries,
            raw_cache_dir=raw_cache_dir,
        )
        if not primary:
            primary_error = "TWSE returned no records for requested range"
    except SourceUnavailableError as error:
        primary_error = str(error)

    secondary = fetch_finmind_daily(
        source_symbol,
        expected_canonical,
        requested_start,
        requested_end,
        transport=transport,
        timeout=timeout,
        retries=retries,
        token_env=token_env,
        raw_cache_dir=raw_cache_dir,
    )
    reconciliation = reconcile_market_data(
        primary,
        secondary.records,
        primary_error,
    )
    return build_research_dataset(
        reconciliation,
        requested_symbol=requested_symbol,
        requested_start=requested_start,
        requested_end=requested_end,
        allow_secondary_only=allow_secondary_only,
        verification_records=(
            secondary.records
            if reconciliation.state is SourceState.PRIMARY_VERIFIED
            and not reconciliation.cross_check_unavailable
            else ()
        ),
    )


def build_research_dataset(
    reconciliation: ReconciliationResult,
    *,
    requested_symbol: str,
    requested_start: str,
    requested_end: str,
    allow_secondary_only: bool = False,
    verification_records: Sequence[MarketDataRecord] = (),
) -> ResearchMarketDataset:
    start, end = validate_date_range(requested_start, requested_end)
    source_symbol = source_symbol_from_input(requested_symbol)
    expected_canonical = canonical_symbol(source_symbol)

    if reconciliation.state is SourceState.SOURCE_MISMATCH:
        raise DataValidationError(
            "SOURCE_MISMATCH cannot be promoted to a research dataset"
        )
    if reconciliation.state is SourceState.SOURCE_UNAVAILABLE:
        raise DataValidationError(
            "SOURCE_UNAVAILABLE cannot be promoted to a research dataset"
        )
    if (
        reconciliation.state is SourceState.SECONDARY_ONLY
        and not allow_secondary_only
    ):
        raise DataValidationError(
            "SECONDARY_ONLY requires explicit allow_secondary_only opt-in"
        )
    if not reconciliation.records:
        raise DataValidationError("research dataset contains no market records")
    if (
        reconciliation.state is SourceState.PRIMARY_VERIFIED
        and not reconciliation.cross_check_unavailable
        and not verification_records
    ):
        raise DataValidationError(
            "PRIMARY_VERIFIED cross-check is missing secondary verification provenance"
        )
    if reconciliation.cross_check_unavailable and verification_records:
        raise DataValidationError(
            "cross_check_unavailable conflicts with verification provenance"
        )

    records = tuple(sorted(reconciliation.records, key=lambda item: item.trade_date))
    _validate_records(
        records,
        expected_source_symbol=source_symbol,
        expected_canonical=expected_canonical,
        start=start,
        end=end,
        state=reconciliation.state,
    )
    verified_records = tuple(
        sorted(verification_records, key=lambda item: item.trade_date)
    )
    if verified_records:
        _validate_records(
            verified_records,
            expected_source_symbol=source_symbol,
            expected_canonical=expected_canonical,
            start=start,
            end=end,
            state=SourceState.SECONDARY_ONLY,
        )
        verification_check = reconcile_market_data(records, verified_records)
        if verification_check.state is not SourceState.PRIMARY_VERIFIED:
            raise DataValidationError(
                "secondary verification provenance does not match selected primary records"
            )
    bars = tuple(_to_bar(item) for item in records)
    selected_source = records[0].source
    price_basis = (
        "RAW_SECONDARY_DAILY"
        if reconciliation.state is SourceState.SECONDARY_ONLY
        else "RAW_OFFICIAL_DAILY"
    )
    verification_sources = tuple(
        sorted({item.source for item in verified_records})
    )
    verification_hashes = tuple(
        sorted({item.raw_content_hash for item in verified_records})
    )
    dataset_hash = _compute_dataset_hash(
        canonical=expected_canonical,
        requested_start=requested_start,
        requested_end=requested_end,
        source_state=reconciliation.state,
        selected_source=selected_source,
        price_basis=price_basis,
        records=records,
        verification_sources=verification_sources,
        verification_raw_content_hashes=verification_hashes,
    )
    return ResearchMarketDataset(
        requested_symbol=requested_symbol,
        source_symbol=source_symbol,
        canonical_symbol=expected_canonical,
        requested_start=requested_start,
        requested_end=requested_end,
        source_state=reconciliation.state,
        selected_source=selected_source,
        cross_check_unavailable=reconciliation.cross_check_unavailable,
        bars=bars,
        records=records,
        reconciliation_issues=reconciliation.issues,
        dataset_hash=dataset_hash,
        raw_content_hashes=tuple(sorted({item.raw_content_hash for item in records})),
        retrieval_timestamps=tuple(sorted({item.retrieved_at for item in records})),
        verification_sources=verification_sources,
        verification_raw_content_hashes=verification_hashes,
        verification_retrieval_timestamps=tuple(
            sorted({item.retrieved_at for item in verified_records})
        ),
        price_basis=price_basis,
    )


def _compute_dataset_hash(
    *,
    canonical: str,
    requested_start: str,
    requested_end: str,
    source_state: SourceState,
    selected_source: str,
    price_basis: str,
    records: Sequence[MarketDataRecord],
    verification_sources: Sequence[str],
    verification_raw_content_hashes: Sequence[str],
) -> str:
    content_payload = {
        "schema_version": "TWSTOCK-RESEARCH-DATASET-001",
        "canonical_symbol": canonical,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "source_state": source_state.value,
        "selected_source": selected_source,
        "price_basis": price_basis,
        "adjustment_policy": "RAW_UNADJUSTED",
        "corporate_actions_applied": False,
        "verification_sources": list(verification_sources),
        "verification_raw_content_hashes": list(
            verification_raw_content_hashes
        ),
        "records": [
            {
                "trade_date": item.trade_date,
                "open": item.open_price,
                "high": item.high_price,
                "low": item.low_price,
                "close": item.close_price,
                "volume": item.traded_share_volume,
                "official_traded_value_twd": item.official_traded_value_twd,
                "source": item.source,
                "source_tier": item.source_tier.value,
                "raw_content_hash": item.raw_content_hash,
            }
            for item in records
        ],
    }
    return hashlib.sha256(stable_json_bytes(content_payload)).hexdigest()


def write_research_dataset(dataset: ResearchMarketDataset, output_dir: Path) -> None:
    if dataset.bars != tuple(_to_bar(item) for item in dataset.records):
        raise DataValidationError("dataset bars do not match source records")
    expected_hash = _compute_dataset_hash(
        canonical=dataset.canonical_symbol,
        requested_start=dataset.requested_start,
        requested_end=dataset.requested_end,
        source_state=dataset.source_state,
        selected_source=dataset.selected_source,
        price_basis=dataset.price_basis,
        records=dataset.records,
        verification_sources=dataset.verification_sources,
        verification_raw_content_hashes=dataset.verification_raw_content_hashes,
    )
    if dataset.dataset_hash != expected_hash:
        raise DataValidationError("dataset hash does not match dataset content")
    output_dir.mkdir(parents=True, exist_ok=True)
    bars_path = output_dir / "market_bars.csv"
    fieldnames = (
        "symbol",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "official_traded_value_twd",
        "source",
        "source_tier",
        "retrieved_at",
        "raw_content_hash",
    )
    with bars_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for bar, record in zip(dataset.bars, dataset.records, strict=True):
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "trade_date": bar.trade_date.isoformat(),
                    "open": _format_number(bar.open),
                    "high": _format_number(bar.high),
                    "low": _format_number(bar.low),
                    "close": _format_number(bar.close),
                    "volume": _format_number(bar.volume),
                    "official_traded_value_twd": _format_number(
                        bar.official_traded_value_twd
                    ),
                    "source": record.source,
                    "source_tier": record.source_tier.value,
                    "retrieved_at": record.retrieved_at,
                    "raw_content_hash": record.raw_content_hash,
                }
            )
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(dataset.manifest(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_research_bars_csv(path: Path) -> tuple[MarketBar, ...]:
    required = {
        "symbol",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "official_traded_value_twd",
    }
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = sorted(required.difference(fields))
        if missing:
            raise DataValidationError(f"market bars CSV missing fields: {missing}")
        bars = tuple(_bar_from_row(row, index) for index, row in enumerate(reader, 2))
    _validate_bars(bars)
    return bars


def _validate_records(
    records: Sequence[MarketDataRecord],
    *,
    expected_source_symbol: str,
    expected_canonical: str,
    start: date,
    end: date,
    state: SourceState,
) -> None:
    previous: date | None = None
    source = records[0].source
    for index, item in enumerate(records):
        if item.source_symbol != expected_source_symbol or item.market != "TW":
            raise DataValidationError(
                f"record {index} source symbol or market does not match request"
            )
        if item.canonical_symbol != expected_canonical:
            raise DataValidationError(
                f"record {index} canonical symbol does not match request"
            )
        if item.source != source:
            raise DataValidationError("selected research records mix data sources")
        try:
            parsed = date.fromisoformat(item.trade_date)
        except (TypeError, ValueError) as error:
            raise DataValidationError(
                f"record {index} contains invalid trade date"
            ) from error
        if not start <= parsed <= end:
            raise DataValidationError(f"record {index} lies outside requested range")
        if previous is not None and parsed <= previous:
            raise DataValidationError("market records must have unique ascending dates")
        _validate_record_values(item, index)
        previous = parsed

    expected_tier = (
        SourceTier.SECONDARY
        if state is SourceState.SECONDARY_ONLY
        else SourceTier.PRIMARY
    )
    if any(item.source_tier is not expected_tier for item in records):
        raise DataValidationError(
            f"{state.value} records have inconsistent source tier"
        )


def _validate_record_values(item: MarketDataRecord, index: int) -> None:
    prices = (item.open_price, item.high_price, item.low_price, item.close_price)
    if not all(_positive_real(value) for value in prices):
        raise DataValidationError(f"record {index} contains invalid OHLC")
    if item.low_price > min(item.open_price, item.close_price):
        raise DataValidationError(f"record {index} violates low-price bounds")
    if item.high_price < max(item.open_price, item.close_price):
        raise DataValidationError(f"record {index} violates high-price bounds")
    if not _positive_real(item.traded_share_volume):
        raise DataValidationError(f"record {index} contains invalid volume")
    if not _positive_real(item.official_traded_value_twd):
        raise DataValidationError(f"record {index} contains invalid traded value")
    if not isinstance(item.raw_content_hash, str) or not _SHA256_RE.fullmatch(
        item.raw_content_hash
    ):
        raise DataValidationError(f"record {index} contains invalid raw content hash")


def _to_bar(item: MarketDataRecord) -> MarketBar:
    return MarketBar(
        symbol=item.canonical_symbol,
        trade_date=date.fromisoformat(item.trade_date),
        open=item.open_price,
        high=item.high_price,
        low=item.low_price,
        close=item.close_price,
        volume=float(item.traded_share_volume),
        official_traded_value_twd=float(item.official_traded_value_twd),
    )


def _bar_from_row(row: dict[str, str], index: int) -> MarketBar:
    try:
        official = float(row["official_traded_value_twd"])
        return MarketBar(
            symbol=row["symbol"],
            trade_date=date.fromisoformat(row["trade_date"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            official_traded_value_twd=official,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DataValidationError(f"invalid market bars CSV row {index}") from error


def _validate_bars(bars: Sequence[MarketBar]) -> None:
    if not bars:
        raise DataValidationError("market bars CSV contains no rows")
    symbol = bars[0].symbol
    previous: date | None = None
    for index, bar in enumerate(bars):
        if not bar.symbol or bar.symbol != symbol:
            raise DataValidationError("market bars CSV must contain one symbol")
        if previous is not None and bar.trade_date <= previous:
            raise DataValidationError("market bars CSV dates must be strictly ascending")
        if not all(_positive_real(value) for value in (bar.open, bar.high, bar.low, bar.close)):
            raise DataValidationError(f"market bars CSV row {index + 2} has invalid OHLC")
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise DataValidationError(f"market bars CSV row {index + 2} violates OHLC bounds")
        if not _positive_real(bar.volume) or not _positive_real(
            bar.official_traded_value_twd
        ):
            raise DataValidationError(
                f"market bars CSV row {index + 2} has invalid volume or value"
            )
        previous = bar.trade_date


def _positive_real(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and math.isfinite(value)
        and value > 0
    )


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.15g}"
