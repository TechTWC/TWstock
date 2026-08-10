from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from enum import Enum
import hashlib
import json
import math
from numbers import Real
import os
from pathlib import Path
import re
from typing import Iterable, Sequence
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import DataValidationError, DuplicateTradeDateError, SourceUnavailableError
from .http import HttpTransport, get_with_retry
from .models import MarketBar, SourceTier
from .normalization import (
    canonical_symbol,
    raw_hash,
    redact_tokens_in_text,
    sanitize_url,
    source_symbol_from_input,
    stable_json_bytes,
    utc_now_iso,
    validate_date_range,
)
from .raw_cache import preserve_raw_response


FINMIND_CORPORATE_ACTION_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"
CORPORATE_ACTION_POLICY_VERSION = "CA-GUARD-001"
REQUIRED_FINMIND_DATASETS = (
    "TaiwanStockCapitalReductionReferencePrice",
    "TaiwanStockDividendResult",
    "TaiwanStockParValueChange",
    "TaiwanStockSplitPrice",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class _RejectAuthenticatedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CorporateActionType(str, Enum):
    EX_DIVIDEND = "EX_DIVIDEND"
    EX_RIGHT = "EX_RIGHT"
    EX_RIGHT_DIVIDEND = "EX_RIGHT_DIVIDEND"
    CAPITAL_REDUCTION = "CAPITAL_REDUCTION"
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    PAR_VALUE_CHANGE = "PAR_VALUE_CHANGE"


class CorporateActionCoverageState(str, Enum):
    SECONDARY_COMPLETE = "SECONDARY_COMPLETE"


class AnalysisGuardState(str, Enum):
    ALLOWED = "ALLOWED"
    ANALYSIS_BLOCKED = "ANALYSIS_BLOCKED"


@dataclass(frozen=True)
class CorporateActionEvidence:
    source: str
    source_tier: SourceTier
    source_dataset: str
    source_symbol: str
    canonical_symbol: str
    requested_start: str
    requested_end: str
    retrieved_at: str
    source_reference: str
    raw_content_hash: str


@dataclass(frozen=True)
class CorporateActionEvent:
    event_id: str
    source: str
    source_tier: SourceTier
    source_dataset: str
    source_symbol: str
    canonical_symbol: str
    market: str
    event_type: CorporateActionType
    effective_date: str
    knowledge_date: str
    knowledge_basis: str
    before_price: float
    after_reference_price: float
    detail: str
    raw_content_hash: str


@dataclass(frozen=True)
class CorporateActionDataset:
    requested_symbol: str
    source_symbol: str
    canonical_symbol: str
    requested_start: str
    requested_end: str
    coverage_state: CorporateActionCoverageState
    events: tuple[CorporateActionEvent, ...]
    evidence: tuple[CorporateActionEvidence, ...]
    dataset_hash: str
    policy_version: str = CORPORATE_ACTION_POLICY_VERSION

    def manifest(self) -> dict[str, object]:
        expected = _validate_corporate_action_dataset_consistency(self)
        return {
            "schema_version": "TWSTOCK-CORPORATE-ACTIONS-001",
            "requested_symbol": expected.requested_symbol,
            "source_symbol": expected.source_symbol,
            "canonical_symbol": expected.canonical_symbol,
            "requested_start": expected.requested_start,
            "requested_end": expected.requested_end,
            "coverage_state": expected.coverage_state.value,
            "source": "FinMind",
            "source_tier": SourceTier.SECONDARY.value,
            "source_datasets": [item.source_dataset for item in expected.evidence],
            "source_evidence": [
                {
                    "source": item.source,
                    "source_tier": item.source_tier.value,
                    "source_dataset": item.source_dataset,
                    "retrieved_at": item.retrieved_at,
                    "source_reference": item.source_reference,
                    "raw_content_hash": item.raw_content_hash,
                }
                for item in expected.evidence
            ],
            "event_count": len(expected.events),
            "event_types": sorted({item.event_type.value for item in expected.events}),
            "dataset_hash": expected.dataset_hash,
            "raw_content_hashes": [item.raw_content_hash for item in expected.evidence],
            "retrieval_timestamps": [item.retrieved_at for item in expected.evidence],
            "policy_version": expected.policy_version,
            "knowledge_policy": "EFFECTIVE_DATE_CONSERVATIVE",
            "research_warning": (
                "Complete query coverage is secondary-source only. Events block raw-price "
                "analysis windows but do not adjust prices, returns, or holdings."
            ),
        }


@dataclass(frozen=True)
class AnalysisGuardDecision:
    symbol: str
    trade_date: date
    analyzer: str
    state: AnalysisGuardState
    reason: str
    latest_effective_date: date | None
    clean_segment_bars: int
    required_clean_bars: int


def build_finmind_corporate_action_url(
    dataset_name: str,
    source_symbol: str,
    start: str,
    end: str,
) -> str:
    if dataset_name not in REQUIRED_FINMIND_DATASETS:
        raise DataValidationError(f"unsupported corporate-action dataset: {dataset_name}")
    return FINMIND_CORPORATE_ACTION_ENDPOINT + "?" + urlencode(
        {
            "dataset": dataset_name,
            "data_id": source_symbol,
            "start_date": start,
            "end_date": end,
        }
    )


class FinMindBearerTransport:
    """Add bearer auth only to the exact HTTPS FinMind data endpoint."""

    def __init__(self, delegate: HttpTransport | None, token: str) -> None:
        if not token:
            raise SourceUnavailableError("FINMIND_TOKEN is required")
        self._delegate = delegate
        self._token = token

    def get(self, url: str, timeout: float):
        safe_url = _without_query_token(url)
        if not _is_finmind_data_endpoint(safe_url):
            if self._delegate is not None:
                return self._delegate.get(safe_url, timeout)
            request = urllib.request.Request(
                safe_url,
                headers={"User-Agent": "TWstock-data-adapter/0.2"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                from .http import HttpResponse

                return HttpResponse(response.geturl(), response.status, response.read())

        headers = {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "TWstock-data-adapter/0.2",
        }
        if self._delegate is not None:
            authenticated_get = getattr(self._delegate, "get_with_headers", None)
            if callable(authenticated_get):
                return authenticated_get(safe_url, timeout, headers)
            # Test and offline transports model source responses without making an
            # external request. They receive only the credential-free URL.
            return self._delegate.get(safe_url, timeout)
        request = urllib.request.Request(safe_url, headers=headers)
        opener = urllib.request.build_opener(_RejectAuthenticatedRedirects())
        with opener.open(request, timeout=timeout) as response:
            from .http import HttpResponse

            return HttpResponse(response.geturl(), response.status, response.read())


def _is_finmind_data_endpoint(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return (
            parts.scheme.lower() == "https"
            and (parts.hostname or "").lower() == "api.finmindtrade.com"
            and parts.port in (None, 443)
            and parts.path == "/api/v4/data"
        )
    except ValueError:
        return False


def _without_query_token(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parts.query) if key != "token"]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def fetch_finmind_corporate_actions(
    requested_symbol: str,
    requested_start: str,
    requested_end: str,
    *,
    transport: HttpTransport | None = None,
    timeout: float = 10,
    retries: int = 2,
    token_env: str = "FINMIND_TOKEN",
    raw_cache_dir: Path | str | None = None,
) -> CorporateActionDataset:
    validate_date_range(requested_start, requested_end)
    source_symbol = source_symbol_from_input(requested_symbol)
    canonical = canonical_symbol(source_symbol)
    token = os.environ.get(token_env)
    if not token:
        raise SourceUnavailableError(
            f"{token_env} is required for complete corporate-action guard coverage"
        )

    events: list[CorporateActionEvent] = []
    evidence: list[CorporateActionEvidence] = []
    for dataset_name in REQUIRED_FINMIND_DATASETS:
        url = build_finmind_corporate_action_url(
            dataset_name,
            source_symbol,
            requested_start,
            requested_end,
        )
        authenticated_transport = (
            transport
            if isinstance(transport, FinMindBearerTransport)
            else FinMindBearerTransport(transport, token)
        )
        try:
            response = get_with_retry(url, authenticated_transport, timeout, retries)
        except SourceUnavailableError as error:
            message = redact_tokens_in_text(str(error).replace(token, "<redacted>"))
            raise SourceUnavailableError(
                f"corporate-action source unavailable for {dataset_name}: {message}"
            ) from error
        retrieved_at = utc_now_iso()
        preserve_raw_response(
            raw_cache_dir,
            source="FinMind",
            source_tier=SourceTier.SECONDARY.value,
            source_symbol=source_symbol,
            canonical_symbol=canonical,
            requested_start=requested_start,
            requested_end=requested_end,
            retrieved_at=retrieved_at,
            source_url=response.url,
            http_status=response.status,
            body=response.body,
            request_identifier=f"corporate_{dataset_name}",
        )
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DataValidationError(
                f"invalid FinMind JSON for {dataset_name}"
            ) from error
        digest = raw_hash(response.body)
        batch = parse_finmind_corporate_action_payload(
            dataset_name,
            payload,
            source_symbol=source_symbol,
            canonical=canonical,
            start=requested_start,
            end=requested_end,
            raw_content_hash=digest,
        )
        events.extend(batch)
        evidence.append(
            CorporateActionEvidence(
                source="FinMind",
                source_tier=SourceTier.SECONDARY,
                source_dataset=dataset_name,
                source_symbol=source_symbol,
                canonical_symbol=canonical,
                requested_start=requested_start,
                requested_end=requested_end,
                retrieved_at=retrieved_at,
                source_reference=sanitize_url(response.url),
                raw_content_hash=digest,
            )
        )
    return build_corporate_action_dataset(
        requested_symbol=requested_symbol,
        requested_start=requested_start,
        requested_end=requested_end,
        events=events,
        evidence=evidence,
    )


def parse_finmind_corporate_action_payload(
    dataset_name: str,
    payload: object,
    *,
    source_symbol: str,
    canonical: str,
    start: str,
    end: str,
    raw_content_hash: str,
) -> tuple[CorporateActionEvent, ...]:
    validate_date_range(start, end)
    if dataset_name not in REQUIRED_FINMIND_DATASETS:
        raise DataValidationError(f"unsupported corporate-action dataset: {dataset_name}")
    if canonical != canonical_symbol(source_symbol):
        raise DataValidationError("corporate-action canonical symbol mismatch")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise DataValidationError(
            f"unexpected FinMind {dataset_name} schema"
        )
    if "status" in payload and payload["status"] != 200:
        raise SourceUnavailableError(
            f"FinMind {dataset_name} API status is not successful"
        )
    if "msg" in payload and str(payload["msg"]).strip().lower() != "success":
        raise SourceUnavailableError(
            f"FinMind {dataset_name} API message is not successful"
        )
    if not _SHA256_RE.fullmatch(raw_content_hash):
        raise DataValidationError("invalid corporate-action raw content hash")

    output: list[CorporateActionEvent] = []
    seen: set[tuple[str, CorporateActionType]] = set()
    for index, row in enumerate(payload["data"]):
        if not isinstance(row, dict):
            raise DataValidationError(f"{dataset_name} row {index} must be an object")
        if (
            dataset_name
            in {"TaiwanStockSplitPrice", "TaiwanStockParValueChange"}
            and row.get("stock_id") != source_symbol
        ):
            # These documented endpoints may return a full-market table even when
            # data_id is supplied. Filter explicitly while retaining the complete
            # raw response and its hash as evidence.
            continue
        event = _parse_finmind_event_row(
            dataset_name,
            row,
            source_symbol=source_symbol,
            canonical=canonical,
            start=start,
            end=end,
            raw_content_hash=raw_content_hash,
            index=index,
        )
        if event is None:
            continue
        key = (event.effective_date, event.event_type)
        if key in seen:
            raise DuplicateTradeDateError(
                f"duplicate {dataset_name} event {event.effective_date}/{event.event_type.value}"
            )
        seen.add(key)
        output.append(event)
    return tuple(sorted(output, key=lambda item: (item.effective_date, item.event_type.value)))


def _parse_finmind_event_row(
    dataset_name: str,
    row: dict[str, object],
    *,
    source_symbol: str,
    canonical: str,
    start: str,
    end: str,
    raw_content_hash: str,
    index: int,
) -> CorporateActionEvent | None:
    required_by_dataset = {
        "TaiwanStockDividendResult": (
            "date", "stock_id", "before_price", "after_price", "stock_or_cache_dividend"
        ),
        "TaiwanStockCapitalReductionReferencePrice": (
            "date", "stock_id", "ClosingPriceonTheLastTradingDay",
            "PostReductionReferencePrice", "ReasonforCapitalReduction"
        ),
        "TaiwanStockSplitPrice": (
            "date", "stock_id", "type", "before_price", "after_price"
        ),
        "TaiwanStockParValueChange": (
            "date", "stock_id", "before_close", "after_ref_close"
        ),
    }
    required = required_by_dataset[dataset_name]
    missing = [field for field in required if field not in row]
    if missing:
        raise DataValidationError(
            f"{dataset_name} row {index} missing fields: {missing}"
        )
    if row["stock_id"] != source_symbol:
        raise DataValidationError(f"{dataset_name} response stock_id mismatch")
    effective = _iso_date_text(row["date"], f"{dataset_name}.date")
    if not start <= effective <= end:
        return None

    if dataset_name == "TaiwanStockDividendResult":
        marker = str(row["stock_or_cache_dividend"]).strip()
        marker_map = {
            "息": CorporateActionType.EX_DIVIDEND,
            "權": CorporateActionType.EX_RIGHT,
            "權息": CorporateActionType.EX_RIGHT_DIVIDEND,
        }
        if marker not in marker_map:
            raise DataValidationError(f"unsupported dividend marker: {marker!r}")
        event_type = marker_map[marker]
        before = _positive_float(row["before_price"], "before_price")
        after = _positive_float(row["after_price"], "after_price")
        detail = marker
    elif dataset_name == "TaiwanStockCapitalReductionReferencePrice":
        event_type = CorporateActionType.CAPITAL_REDUCTION
        before = _positive_float(
            row["ClosingPriceonTheLastTradingDay"],
            "ClosingPriceonTheLastTradingDay",
        )
        after = _positive_float(
            row["PostReductionReferencePrice"],
            "PostReductionReferencePrice",
        )
        detail = str(row["ReasonforCapitalReduction"]).strip()
        if not detail:
            raise DataValidationError("blank ReasonforCapitalReduction")
    elif dataset_name == "TaiwanStockSplitPrice":
        marker = str(row["type"]).strip()
        split_map = {
            "分割": CorporateActionType.SPLIT,
            "反分割": CorporateActionType.REVERSE_SPLIT,
        }
        if marker not in split_map:
            raise DataValidationError(f"unsupported split marker: {marker!r}")
        event_type = split_map[marker]
        before = _positive_float(row["before_price"], "before_price")
        after = _positive_float(row["after_price"], "after_price")
        detail = marker
    else:
        event_type = CorporateActionType.PAR_VALUE_CHANGE
        before = _positive_float(row["before_close"], "before_close")
        after = _positive_float(row["after_ref_close"], "after_ref_close")
        detail = str(row.get("stock_name", "PAR_VALUE_CHANGE")).strip()
        if not detail:
            detail = "PAR_VALUE_CHANGE"

    event_id = _expected_event_id(
        source_dataset=dataset_name,
        canonical=canonical,
        event_type=event_type,
        effective_date=effective,
        before_price=before,
        after_reference_price=after,
        detail=detail,
    )
    return CorporateActionEvent(
        event_id=event_id,
        source="FinMind",
        source_tier=SourceTier.SECONDARY,
        source_dataset=dataset_name,
        source_symbol=source_symbol,
        canonical_symbol=canonical,
        market="TW",
        event_type=event_type,
        effective_date=effective,
        knowledge_date=effective,
        knowledge_basis="EFFECTIVE_DATE_CONSERVATIVE",
        before_price=before,
        after_reference_price=after,
        detail=detail,
        raw_content_hash=raw_content_hash,
    )


def build_corporate_action_dataset(
    *,
    requested_symbol: str,
    requested_start: str,
    requested_end: str,
    events: Sequence[CorporateActionEvent],
    evidence: Sequence[CorporateActionEvidence],
) -> CorporateActionDataset:
    start, end = validate_date_range(requested_start, requested_end)
    source_symbol = source_symbol_from_input(requested_symbol)
    canonical = canonical_symbol(source_symbol)
    ordered_evidence = tuple(sorted(evidence, key=lambda item: item.source_dataset))
    if tuple(item.source_dataset for item in ordered_evidence) != REQUIRED_FINMIND_DATASETS:
        raise DataValidationError(
            "corporate-action coverage requires all four FinMind datasets exactly once"
        )
    for index, item in enumerate(ordered_evidence):
        if item.source != "FinMind" or item.source_tier is not SourceTier.SECONDARY:
            raise DataValidationError(f"corporate-action evidence {index} has invalid source")
        if item.source_symbol != source_symbol or item.canonical_symbol != canonical:
            raise DataValidationError(f"corporate-action evidence {index} symbol mismatch")
        if item.requested_start != requested_start or item.requested_end != requested_end:
            raise DataValidationError(f"corporate-action evidence {index} range mismatch")
        if not _SHA256_RE.fullmatch(item.raw_content_hash):
            raise DataValidationError(f"corporate-action evidence {index} has invalid hash")
        _iso_timestamp(item.retrieved_at, f"evidence {index} retrieved_at")
        if not item.source_reference:
            raise DataValidationError(f"corporate-action evidence {index} source reference missing")
        if item.source_reference != sanitize_url(item.source_reference):
            raise DataValidationError(
                f"corporate-action evidence {index} source reference contains credentials"
            )

    hashes_by_dataset = {
        item.source_dataset: item.raw_content_hash for item in ordered_evidence
    }
    ordered_events = tuple(
        sorted(events, key=lambda item: (item.effective_date, item.event_type.value))
    )
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, CorporateActionType]] = set()
    for index, item in enumerate(ordered_events):
        if item.event_id in seen_ids:
            raise DataValidationError("corporate-action event ids must be unique")
        seen_ids.add(item.event_id)
        key = (item.effective_date, item.event_type)
        if key in seen_keys:
            raise DataValidationError("corporate-action date/type pairs must be unique")
        seen_keys.add(key)
        if (
            item.source != "FinMind"
            or item.source_tier is not SourceTier.SECONDARY
            or item.market != "TW"
        ):
            raise DataValidationError(f"corporate-action event {index} has invalid source")
        if item.source_symbol != source_symbol or item.canonical_symbol != canonical:
            raise DataValidationError(f"corporate-action event {index} symbol mismatch")
        if item.source_dataset not in hashes_by_dataset:
            raise DataValidationError(f"corporate-action event {index} lacks source evidence")
        permitted_types = {
            "TaiwanStockDividendResult": {
                CorporateActionType.EX_DIVIDEND,
                CorporateActionType.EX_RIGHT,
                CorporateActionType.EX_RIGHT_DIVIDEND,
            },
            "TaiwanStockCapitalReductionReferencePrice": {
                CorporateActionType.CAPITAL_REDUCTION,
            },
            "TaiwanStockSplitPrice": {
                CorporateActionType.SPLIT,
                CorporateActionType.REVERSE_SPLIT,
            },
            "TaiwanStockParValueChange": {
                CorporateActionType.PAR_VALUE_CHANGE,
            },
        }
        if item.event_type not in permitted_types[item.source_dataset]:
            raise DataValidationError(
                f"corporate-action event {index} type/dataset mismatch"
            )
        if item.raw_content_hash != hashes_by_dataset[item.source_dataset]:
            raise DataValidationError(f"corporate-action event {index} hash/evidence mismatch")
        effective = _parse_date(item.effective_date, f"event {index} effective_date")
        knowledge = _parse_date(item.knowledge_date, f"event {index} knowledge_date")
        if knowledge != effective or item.knowledge_basis != "EFFECTIVE_DATE_CONSERVATIVE":
            raise DataValidationError("corporate-action knowledge policy mismatch")
        if not start <= effective <= end:
            raise DataValidationError(f"corporate-action event {index} outside requested range")
        _positive_float(item.before_price, "before_price")
        _positive_float(item.after_reference_price, "after_reference_price")
        if not item.detail:
            raise DataValidationError(f"corporate-action event {index} has blank detail")
        expected_event_id = _expected_event_id(
            source_dataset=item.source_dataset,
            canonical=item.canonical_symbol,
            event_type=item.event_type,
            effective_date=item.effective_date,
            before_price=item.before_price,
            after_reference_price=item.after_reference_price,
            detail=item.detail,
        )
        if item.event_id != expected_event_id:
            raise DataValidationError(f"corporate-action event {index} id/content mismatch")

    dataset_hash = _corporate_action_dataset_hash(
        canonical=canonical,
        requested_start=requested_start,
        requested_end=requested_end,
        events=ordered_events,
        evidence=ordered_evidence,
    )
    return CorporateActionDataset(
        requested_symbol=requested_symbol,
        source_symbol=source_symbol,
        canonical_symbol=canonical,
        requested_start=requested_start,
        requested_end=requested_end,
        coverage_state=CorporateActionCoverageState.SECONDARY_COMPLETE,
        events=ordered_events,
        evidence=ordered_evidence,
        dataset_hash=dataset_hash,
    )


def _corporate_action_dataset_hash(
    *,
    canonical: str,
    requested_start: str,
    requested_end: str,
    events: Sequence[CorporateActionEvent],
    evidence: Sequence[CorporateActionEvidence],
) -> str:
    payload = {
        "schema_version": "TWSTOCK-CORPORATE-ACTIONS-001",
        "canonical_symbol": canonical,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "coverage_state": CorporateActionCoverageState.SECONDARY_COMPLETE.value,
        "policy_version": CORPORATE_ACTION_POLICY_VERSION,
        "source_evidence": [
            {
                "source": item.source,
                "source_tier": item.source_tier.value,
                "source_dataset": item.source_dataset,
                "source_symbol": item.source_symbol,
                "canonical_symbol": item.canonical_symbol,
                "requested_start": item.requested_start,
                "requested_end": item.requested_end,
                "retrieved_at": item.retrieved_at,
                "source_reference": item.source_reference,
                "raw_content_hash": item.raw_content_hash,
            }
            for item in evidence
        ],
        "events": [
            {
                "event_id": item.event_id,
                "source_dataset": item.source_dataset,
                "event_type": item.event_type.value,
                "effective_date": item.effective_date,
                "knowledge_date": item.knowledge_date,
                "knowledge_basis": item.knowledge_basis,
                "before_price": item.before_price,
                "after_reference_price": item.after_reference_price,
                "detail": item.detail,
                "raw_content_hash": item.raw_content_hash,
            }
            for item in events
        ],
    }
    return hashlib.sha256(stable_json_bytes(payload)).hexdigest()


def _expected_event_id(
    *,
    source_dataset: str,
    canonical: str,
    event_type: CorporateActionType,
    effective_date: str,
    before_price: float,
    after_reference_price: float,
    detail: str,
) -> str:
    identity_payload = {
        "source": "FinMind",
        "source_dataset": source_dataset,
        "canonical_symbol": canonical,
        "event_type": event_type.value,
        "effective_date": effective_date,
        "before_price": before_price,
        "after_reference_price": after_reference_price,
        "detail": detail,
    }
    return hashlib.sha256(stable_json_bytes(identity_payload)).hexdigest()[:20]


def _validate_corporate_action_dataset_consistency(
    dataset: CorporateActionDataset,
) -> CorporateActionDataset:
    try:
        expected = build_corporate_action_dataset(
            requested_symbol=dataset.requested_symbol,
            requested_start=dataset.requested_start,
            requested_end=dataset.requested_end,
            events=dataset.events,
            evidence=dataset.evidence,
        )
    except DataValidationError as error:
        raise DataValidationError(
            "corporate-action dataset metadata does not match retained evidence"
        ) from error
    if dataset != expected:
        raise DataValidationError(
            "corporate-action dataset metadata does not match retained evidence"
        )
    return expected


def write_corporate_action_dataset(
    dataset: CorporateActionDataset,
    output_dir: Path,
) -> None:
    expected = _validate_corporate_action_dataset_consistency(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = (
        "event_id",
        "source",
        "source_tier",
        "source_dataset",
        "source_symbol",
        "canonical_symbol",
        "market",
        "event_type",
        "effective_date",
        "knowledge_date",
        "knowledge_basis",
        "before_price",
        "after_reference_price",
        "detail",
        "raw_content_hash",
    )
    with (output_dir / "corporate_actions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in expected.events:
            writer.writerow(
                {
                    **item.__dict__,
                    "source_tier": item.source_tier.value,
                    "event_type": item.event_type.value,
                    "before_price": _format_number(item.before_price),
                    "after_reference_price": _format_number(
                        item.after_reference_price
                    ),
                }
            )
    (output_dir / "corporate_action_manifest.json").write_text(
        json.dumps(expected.manifest(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_analysis_guard_decisions(
    bars: Sequence[MarketBar],
    events: Sequence[CorporateActionEvent],
    *,
    analyzer: str,
    required_clean_bars: int,
) -> tuple[AnalysisGuardDecision, ...]:
    if not analyzer or not isinstance(analyzer, str):
        raise DataValidationError("analyzer must be a nonempty string")
    if (
        isinstance(required_clean_bars, bool)
        or not isinstance(required_clean_bars, int)
        or required_clean_bars < 1
    ):
        raise DataValidationError("required_clean_bars must be a positive integer")
    _validate_guard_inputs(bars, events)
    if not bars:
        return ()

    event_dates = sorted({date.fromisoformat(item.effective_date) for item in events})
    latest: date | None = None
    segment_count = 0
    event_index = 0
    output: list[AnalysisGuardDecision] = []
    for bar in bars:
        changed = False
        while event_index < len(event_dates) and event_dates[event_index] <= bar.trade_date:
            latest = event_dates[event_index]
            event_index += 1
            changed = True
        if changed:
            segment_count = 0
        segment_count += 1
        if latest is None:
            state = AnalysisGuardState.ALLOWED
            reason = "NO_CORPORATE_ACTION_IN_OBSERVED_HISTORY"
        elif segment_count < required_clean_bars:
            state = AnalysisGuardState.ANALYSIS_BLOCKED
            reason = "INSUFFICIENT_CLEAN_BARS_AFTER_CORPORATE_ACTION"
        else:
            state = AnalysisGuardState.ALLOWED
            reason = "CLEAN_HISTORY_REBUILT_AFTER_CORPORATE_ACTION"
        output.append(
            AnalysisGuardDecision(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                analyzer=analyzer,
                state=state,
                reason=reason,
                latest_effective_date=latest,
                clean_segment_bars=segment_count,
                required_clean_bars=required_clean_bars,
            )
        )
    return tuple(output)


def clean_bar_segments(
    bars: Sequence[MarketBar],
    events: Sequence[CorporateActionEvent],
) -> tuple[tuple[MarketBar, ...], ...]:
    _validate_guard_inputs(bars, events)
    if not bars:
        return ()
    event_dates = sorted({date.fromisoformat(item.effective_date) for item in events})
    event_index = 0
    current: list[MarketBar] = []
    segments: list[tuple[MarketBar, ...]] = []
    for bar in bars:
        boundary = False
        while event_index < len(event_dates) and event_dates[event_index] <= bar.trade_date:
            boundary = True
            event_index += 1
        if boundary and current:
            segments.append(tuple(current))
            current = []
        current.append(bar)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def write_analysis_guard_csv(
    path: Path,
    decisions: Iterable[AnalysisGuardDecision],
) -> None:
    fields = (
        "symbol",
        "trade_date",
        "analyzer",
        "state",
        "reason",
        "latest_effective_date",
        "clean_segment_bars",
        "required_clean_bars",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in decisions:
            writer.writerow(
                {
                    "symbol": item.symbol,
                    "trade_date": item.trade_date.isoformat(),
                    "analyzer": item.analyzer,
                    "state": item.state.value,
                    "reason": item.reason,
                    "latest_effective_date": (
                        item.latest_effective_date.isoformat()
                        if item.latest_effective_date
                        else ""
                    ),
                    "clean_segment_bars": item.clean_segment_bars,
                    "required_clean_bars": item.required_clean_bars,
                }
            )


def _validate_guard_inputs(
    bars: Sequence[MarketBar],
    events: Sequence[CorporateActionEvent],
) -> None:
    if not bars:
        if events:
            raise DataValidationError("corporate actions cannot guard an empty bar set")
        return
    symbol = bars[0].symbol
    previous: date | None = None
    for index, bar in enumerate(bars):
        if bar.symbol != symbol or not isinstance(bar.trade_date, date):
            raise DataValidationError(f"guard bar {index} symbol/date mismatch")
        if previous is not None and bar.trade_date <= previous:
            raise DataValidationError("guard bars must be strictly ascending")
        previous = bar.trade_date
    for index, event in enumerate(events):
        if event.canonical_symbol != symbol:
            raise DataValidationError(f"guard event {index} symbol mismatch")
        _parse_date(event.effective_date, f"guard event {index} effective_date")


def _iso_date_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise DataValidationError(f"invalid ISO date for {field}")
    return _parse_date(value, field).isoformat()


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"invalid ISO date for {field}") from error


def _iso_timestamp(value: object, field: str) -> None:
    if not isinstance(value, str) or "T" not in value:
        raise DataValidationError(f"invalid timestamp for {field}")
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise DataValidationError(f"invalid timestamp for {field}") from error
    if parsed.tzinfo is None:
        raise DataValidationError(f"timestamp must be timezone-aware for {field}")


def _positive_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (Real, str)):
        raise DataValidationError(f"invalid number for {field}")
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError as error:
        raise DataValidationError(f"invalid number for {field}") from error
    if not math.isfinite(number) or number <= 0:
        raise DataValidationError(f"nonpositive/nonfinite {field}")
    return number


def _format_number(value: float) -> str:
    return f"{value:.15g}"
