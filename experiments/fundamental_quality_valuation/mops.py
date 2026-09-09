from __future__ import annotations

from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from .pit import derive_financial_available_date, parse_date


MOPS_DOCUMENT_ENDPOINT = "https://doc.twse.com.tw/server-java/t57sb01"
MOPS_SOURCE_NAME = "MOPS official electronic document archive"
MOPS_SOURCE_PROVENANCE = "TWSE_MOPS_T57SB01_OFFICIAL_DOCUMENT_UPLOAD"
TAIPEI = ZoneInfo("Asia/Taipei")

_QUARTERS = {"一": 1, "二": 2, "三": 3, "四": 4}
_FISCAL_RE = re.compile(r"(?P<year>\d{3})\s*年\s*第(?P<quarter>[一二三四])季")
_UPLOAD_RE = re.compile(
    r"(?P<year>\d{3})/(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)


class MopsDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class MopsFilingRecord:
    symbol: str
    fiscal_year: int
    fiscal_quarter: int
    period_end: str
    announcement_date: str
    announcement_timestamp: str
    source: str
    source_url: str
    source_identifier: str
    source_provenance: str
    retrieval_timestamp: str
    response_sha256: str
    source_hash: str
    document_kind: str
    document_detail: str
    file_size_bytes: int | None
    correction_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MopsFetchResult:
    symbol: str
    fiscal_year: int | None
    source_url: str
    retrieval_timestamp: str
    response_sha256: str
    fetch_status: str
    reason_code: str
    records: tuple[MopsFilingRecord, ...]


@dataclass(frozen=True)
class MopsSelectionDecision:
    symbol: str
    fiscal_year: int
    fiscal_quarter: int
    period_end: str
    status: str
    reason_code: str
    candidate_count: int
    exact_duplicate_count: int
    multiple_vintage_count: int
    multiple_document_kind_count: int
    correction_candidate_count: int
    # Deprecated compatibility field.  Its legacy meaning is simply the
    # number of raw candidates beyond the first; it is not a bad-row count.
    duplicate_candidate_count: int
    conflict_candidate_count: int
    corrected_filing_case: bool
    selected: MopsFilingRecord | None


class _MopsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell = []
        elif self._in_cell and tag == "br":
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            text = " ".join("".join(self._cell).replace("\xa0", " ").split())
            self._row.append(text)
            self._cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                self.rows.append(self._row)
            self._row = []
            self._in_row = False


def _source_url(symbol: str, fiscal_year: int | None) -> str:
    # A blank year is an official documented-form value that returns the
    # company's complete available archive in one response.  It materially
    # reduces load and rate-limit risk versus one request per company-year.
    roc_year = "" if fiscal_year is None else str(fiscal_year - 1911)
    query = urlencode(
        {
            "step": "1",
            "colorchg": "1",
            # Financial holding companies first return a parent/subsidiary
            # chooser unless the form's self-company flag is supplied.
            "check2858": "Y",
            "co_id": symbol,
            "year": roc_year,
            "seamon": "",
            "mtype": "A",
        }
    )
    return f"{MOPS_DOCUMENT_ENDPOINT}?{query}"


def _parse_upload_timestamp(value: str) -> datetime | None:
    match = _UPLOAD_RE.search(value)
    if not match:
        return None
    parts = {name: int(raw) for name, raw in match.groupdict().items()}
    return datetime(
        parts["year"] + 1911,
        parts["month"],
        parts["day"],
        parts["hour"],
        parts["minute"],
        parts["second"],
        tzinfo=TAIPEI,
    )


def _record_hash(fields: dict[str, Any]) -> str:
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def parse_mops_filing_candidates(
    html: str,
    *,
    source_url: str,
    retrieval_timestamp: str,
    response_sha256: str,
) -> tuple[MopsFilingRecord, ...]:
    """Parse every eligible Chinese IFRS filing candidate without selecting a vintage."""

    parser = _MopsTableParser()
    parser.feed(html)
    candidates: list[MopsFilingRecord] = []
    for cells in parser.rows:
        if len(cells) < 11 or not cells[0].strip().isdigit():
            continue
        fiscal = _FISCAL_RE.search(cells[1])
        uploaded = _parse_upload_timestamp(cells[9])
        if not fiscal or uploaded is None or cells[2] != "財務報告書":
            continue
        detail = cells[5]
        if "IFRSs" not in detail or "英文版" in detail:
            continue
        if "合併財報" in detail:
            document_kind = "CONSOLIDATED"
        elif "個體財報" in detail or "個別財報" in detail:
            document_kind = "INDIVIDUAL"
        else:
            continue
        symbol = cells[0].strip()
        fiscal_year = int(fiscal.group("year")) + 1911
        fiscal_quarter = _QUARTERS[fiscal.group("quarter")]
        month = fiscal_quarter * 3
        period_end = date(fiscal_year, month, monthrange(fiscal_year, month)[1])
        filename = cells[7].strip()
        try:
            file_size = int(cells[8].replace(",", "").strip())
        except ValueError:
            file_size = None
        identity = {
            "symbol": symbol,
            "period_end": period_end.isoformat(),
            "announcement_timestamp": uploaded.isoformat(),
            "source_identifier": filename,
            "file_size_bytes": file_size,
            "correction_status": cells[10].strip(),
            "response_sha256": response_sha256,
        }
        record = MopsFilingRecord(
            symbol=symbol,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            period_end=period_end.isoformat(),
            announcement_date=uploaded.date().isoformat(),
            announcement_timestamp=uploaded.isoformat(),
            source=MOPS_SOURCE_NAME,
            source_url=source_url,
            source_identifier=filename,
            source_provenance=MOPS_SOURCE_PROVENANCE,
            retrieval_timestamp=retrieval_timestamp,
            response_sha256=response_sha256,
            source_hash=_record_hash(identity),
            document_kind=document_kind,
            document_detail=detail,
            file_size_bytes=file_size,
            correction_status=cells[10].strip(),
        )
        candidates.append(record)
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.symbol,
                item.period_end,
                item.document_kind,
                item.announcement_timestamp,
                item.source_identifier,
            ),
        )
    )


def select_mops_filings(
    candidates: Iterable[MopsFilingRecord],
) -> tuple[tuple[MopsFilingRecord, ...], tuple[MopsSelectionDecision, ...]]:
    """Apply the auditable consolidated/latest-vintage contract and fail closed on ties."""

    grouped: dict[tuple[str, int, int], list[MopsFilingRecord]] = {}
    for record in candidates:
        grouped.setdefault((record.symbol, record.fiscal_year, record.fiscal_quarter), []).append(record)

    selected: list[MopsFilingRecord] = []
    decisions: list[MopsSelectionDecision] = []
    for (symbol, fiscal_year, fiscal_quarter), raw_group in sorted(grouped.items()):
        # An exact duplicate HTML row is retained as an audited duplicate count but
        # cannot influence which filing is selected.
        unique: dict[tuple[str, str, str, str, int | None], MopsFilingRecord] = {}
        for record in raw_group:
            identity = (
                record.document_kind,
                record.announcement_timestamp,
                record.source_identifier,
                record.correction_status,
                record.file_size_bytes,
            )
            unique.setdefault(identity, record)
        group = list(unique.values())
        exact_duplicate_count = len(raw_group) - len(group)
        multiple_vintage_count = max(
            0,
            len({record.announcement_timestamp for record in group}) - 1,
        )
        multiple_document_kind_count = max(
            0,
            len({record.document_kind for record in group}) - 1,
        )
        correction_candidate_count = sum(
            record.correction_status not in {"", "無"} for record in group
        )
        preferred_kind = (
            "CONSOLIDATED"
            if any(record.document_kind == "CONSOLIDATED" for record in group)
            else "INDIVIDUAL"
        )
        preferred = [record for record in group if record.document_kind == preferred_kind]
        latest_timestamp = max(record.announcement_timestamp for record in preferred)
        latest = [record for record in preferred if record.announcement_timestamp == latest_timestamp]
        corrected = any(record.correction_status not in {"", "無"} for record in group) or len(preferred) > 1
        legacy_duplicate_count = max(0, len(raw_group) - 1)

        if len(latest) != 1:
            decisions.append(
                MopsSelectionDecision(
                    symbol=symbol,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    period_end=preferred[0].period_end,
                    status="CONFLICT_FAIL_CLOSED",
                    reason_code="MOPS_AMBIGUOUS_LATEST_VINTAGE",
                    candidate_count=len(raw_group),
                    exact_duplicate_count=exact_duplicate_count,
                    multiple_vintage_count=multiple_vintage_count,
                    multiple_document_kind_count=multiple_document_kind_count,
                    correction_candidate_count=correction_candidate_count,
                    duplicate_candidate_count=legacy_duplicate_count,
                    conflict_candidate_count=len(latest),
                    corrected_filing_case=corrected,
                    selected=None,
                )
            )
            continue

        chosen = latest[0]
        selected.append(chosen)
        reason = (
            "MOPS_LATEST_CORRECTION_VERSION"
            if corrected
            else (
                "MOPS_CONSOLIDATED_PREFERRED_OVER_INDIVIDUAL"
                if any(record.document_kind == "INDIVIDUAL" for record in group)
                else "MOPS_SINGLE_ELIGIBLE_FILING"
            )
        )
        decisions.append(
            MopsSelectionDecision(
                symbol=symbol,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                period_end=chosen.period_end,
                status="SELECTED",
                reason_code=reason,
                candidate_count=len(raw_group),
                exact_duplicate_count=exact_duplicate_count,
                multiple_vintage_count=multiple_vintage_count,
                multiple_document_kind_count=multiple_document_kind_count,
                correction_candidate_count=correction_candidate_count,
                duplicate_candidate_count=legacy_duplicate_count,
                conflict_candidate_count=0,
                corrected_filing_case=corrected,
                selected=chosen,
            )
        )
    return (
        tuple(sorted(selected, key=lambda item: (item.symbol, item.period_end))),
        tuple(decisions),
    )


def parse_mops_filing_html(
    html: str,
    *,
    source_url: str,
    retrieval_timestamp: str,
    response_sha256: str,
) -> tuple[MopsFilingRecord, ...]:
    """Compatibility wrapper returning only unambiguous selected filings."""

    candidates = parse_mops_filing_candidates(
        html,
        source_url=source_url,
        retrieval_timestamp=retrieval_timestamp,
        response_sha256=response_sha256,
    )
    selected, _ = select_mops_filings(candidates)
    return selected


def fetch_mops_filing_year(
    symbol: str,
    fiscal_year: int | None,
    cache_dir: Path,
    *,
    refresh: bool = False,
    timeout: int = 60,
    attempts: int = 3,
) -> MopsFetchResult:
    cache_dir.mkdir(parents=True, exist_ok=True)
    year_scope = "ALL_AVAILABLE_YEARS" if fiscal_year is None else str(fiscal_year)
    raw_path = cache_dir / f"{symbol}_{year_scope}_MOPS_t57sb01.html"
    metadata_path = raw_path.with_suffix(".metadata.json")
    source_url = _source_url(symbol, fiscal_year)
    retrieved_at: str
    raw: bytes
    if raw_path.exists() and not refresh:
        raw = raw_path.read_bytes()
        cached_html = raw.decode("big5", errors="replace")
        if "查詢過量" in cached_html or "電子資料查詢作業" not in cached_html:
            refresh = True
        elif metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("source_url") != source_url:
                refresh = True
            else:
                retrieved_at = str(metadata.get("retrieval_timestamp"))
        else:
            retrieved_at = datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).isoformat()
    if refresh or not raw_path.exists():
        error: Exception | None = None
        for attempt in range(attempts):
            try:
                # The legacy document server can cache its rate-limit response by
                # exact query string.  A non-semantic nonce forces a fresh official
                # response while the canonical provenance URL remains stable.
                request_url = f"{source_url}&request_nonce={time.time_ns()}_{attempt}"
                request = Request(
                    request_url,
                    headers={
                        "User-Agent": "TWstock-research/0.1 (MOPS PIT validation)",
                        "Accept": "text/html,application/xhtml+xml",
                        "Cache-Control": "no-cache",
                    },
                )
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                retrieved_at = datetime.now(timezone.utc).isoformat()
                html = raw.decode("big5", errors="replace")
                if "查詢過量" in html:
                    raise MopsDataError("MOPS rate-limit response")
                if "電子資料查詢作業" not in html:
                    raise MopsDataError("Unexpected MOPS response")
                temporary = raw_path.with_suffix(".html.part")
                temporary.write_bytes(raw)
                temporary.replace(raw_path)
                metadata_path.write_text(
                    json.dumps(
                        {"source_url": source_url, "retrieval_timestamp": retrieved_at},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                break
            except Exception as exc:  # network retries are bounded and fail closed
                error = exc
                if attempt + 1 < attempts:
                    time.sleep(1.5 * (attempt + 1))
        else:
            raise MopsDataError(f"Unable to fetch MOPS filing metadata {symbol}/{year_scope}: {error}")

    response_hash = sha256(raw).hexdigest()
    html = raw.decode("big5", errors="replace")
    if "查詢過量" in html or "電子資料查詢作業" not in html:
        raise MopsDataError(f"Unexpected MOPS response for {symbol}/{year_scope}")
    records = parse_mops_filing_html(
        html,
        source_url=source_url,
        retrieval_timestamp=retrieved_at,
        response_sha256=response_hash,
    )
    status = "ACTUAL_MOPS_RECORDS" if records else "NO_MATCHING_MOPS_REPORT"
    reason = "MOPS_DOCUMENT_UPLOAD_TIMESTAMP" if records else "MOPS_FILING_NOT_FOUND"
    return MopsFetchResult(
        symbol=symbol,
        fiscal_year=fiscal_year,
        source_url=source_url,
        retrieval_timestamp=retrieved_at,
        response_sha256=response_hash,
        fetch_status=status,
        reason_code=reason,
        records=records,
    )


def fetch_mops_filing_history(
    requests: Iterable[tuple[str, int]],
    cache_dir: Path,
    *,
    refresh: bool = False,
    workers: int = 4,
) -> tuple[MopsFetchResult, ...]:
    requested = sorted(set((str(symbol), int(year)) for symbol, year in requests))
    work = sorted({symbol for symbol, _ in requested})
    if workers < 1 or workers > 8:
        raise ValueError("MOPS workers must be between 1 and 8")
    results: list[MopsFetchResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                fetch_mops_filing_year,
                symbol,
                None,
                cache_dir,
                refresh=refresh,
            ): symbol
            for symbol in work
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    MopsFetchResult(
                        symbol=symbol,
                        fiscal_year=None,
                        source_url=_source_url(symbol, None),
                        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                        response_sha256="",
                        fetch_status="FETCH_FAILED",
                        reason_code=f"MOPS_FETCH_FAILED:{type(exc).__name__}",
                        records=(),
                    )
                )
    return tuple(sorted(results, key=lambda item: item.symbol))


def filing_lookup(results: Iterable[MopsFetchResult]) -> dict[tuple[str, str], MopsFilingRecord]:
    return {
        (record.symbol, record.period_end): record
        for result in results
        for record in result.records
    }


def apply_mops_pit(
    symbol: str,
    quarterly: pd.DataFrame,
    filings: dict[tuple[str, str], MopsFilingRecord],
    availability_lags: dict[str, int],
    *,
    as_of: date,
    fetch_statuses: dict[tuple[str, int], MopsFetchResult] | None = None,
) -> pd.DataFrame:
    output = quarterly.copy()
    output["period_end"] = output["period_end"].map(parse_date)
    records: list[dict[str, Any]] = []
    for _, row in output.iterrows():
        item = row.to_dict()
        period_end = parse_date(item["period_end"])
        filing = filings.get((str(symbol), period_end.isoformat()))
        if filing is not None:
            filing_date = date.fromisoformat(filing.announcement_date)
            item.update(
                {
                    "announcement_date": filing_date,
                    "announcement_timestamp": filing.announcement_timestamp,
                    "available_date": filing_date,
                    "availability_method": "MOPS_EXACT",
                    "timestamp_confidence": "official_timestamp_second_precision",
                    "pit_source": filing.source,
                    "source_url": filing.source_url,
                    "source_identifier": filing.source_identifier,
                    "source_provenance": filing.source_provenance,
                    "retrieval_timestamp": filing.retrieval_timestamp,
                    "mops_response_sha256": filing.response_sha256,
                    "mops_source_hash": filing.source_hash,
                    "mops_document_kind": filing.document_kind,
                    "mops_file_size_bytes": filing.file_size_bytes,
                    "mops_correction_status": filing.correction_status,
                    "pit_reason_code": (
                        "MOPS_UPLOAD_AFTER_AS_OF_UNUSABLE"
                        if filing_date > as_of
                        else (
                            "MOPS_LATEST_VERSION_UPLOAD_CORRECTION_AWARE"
                            if filing.correction_status not in {"", "無"}
                            else "MOPS_OFFICIAL_UPLOAD_TIMESTAMP"
                        )
                    ),
                }
            )
        else:
            fetch_result = (
                fetch_statuses.get((str(symbol), period_end.year))
                if fetch_statuses
                else None
            )
            proxy = derive_financial_available_date(
                period_end,
                q1_lag_days=int(availability_lags["q1"]),
                q2_lag_days=int(availability_lags["q2"]),
                q3_lag_days=int(availability_lags["q3"]),
                q4_lag_days=int(availability_lags["q4"]),
            )
            item.update(
                {
                    "announcement_date": None,
                    "announcement_timestamp": None,
                    "available_date": proxy,
                    "availability_method": "AVAILABLE_DATE_PROXY",
                    "timestamp_confidence": "conservative_proxy_fallback",
                    "pit_source": "pre-registered conservative availability-date proxy",
                    "source_url": fetch_result.source_url if fetch_result else None,
                    "source_identifier": None,
                    "source_provenance": "MOPS_QUERY_THEN_AVAILABLE_DATE_PROXY_FALLBACK",
                    "retrieval_timestamp": (
                        fetch_result.retrieval_timestamp if fetch_result else None
                    ),
                    "mops_response_sha256": (
                        fetch_result.response_sha256 or None if fetch_result else None
                    ),
                    "mops_source_hash": None,
                    "mops_document_kind": None,
                    "mops_file_size_bytes": None,
                    "mops_correction_status": None,
                    "pit_reason_code": (
                        fetch_result.reason_code
                        if fetch_result and fetch_result.fetch_status == "FETCH_FAILED"
                        else "MOPS_FILING_NOT_FOUND_PROXY_FALLBACK"
                    ),
                }
            )
        records.append(item)
    return pd.DataFrame(records).sort_values("period_end").reset_index(drop=True)


def provenance_frame(securities: Iterable[Any]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    columns = [
        "period_end",
        "announcement_date",
        "announcement_timestamp",
        "available_date",
        "availability_method",
        "timestamp_confidence",
        "pit_source",
        "source_url",
        "source_identifier",
        "source_provenance",
        "retrieval_timestamp",
        "mops_response_sha256",
        "mops_source_hash",
        "mops_document_kind",
        "mops_file_size_bytes",
        "mops_correction_status",
        "pit_reason_code",
    ]
    for security in securities:
        available = [column for column in columns if column in security.quarterly]
        frame = security.quarterly[available].copy()
        frame.insert(0, "sector_logic", security.sector_logic.value)
        frame.insert(0, "company", security.company)
        frame.insert(0, "symbol", security.symbol)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def summarize_mops_coverage(provenance: pd.DataFrame) -> pd.DataFrame:
    frame = provenance.copy()
    if frame.empty:
        return pd.DataFrame()
    frame["period_year"] = pd.to_datetime(frame["period_end"], errors="coerce").dt.year
    actual = frame["availability_method"] == "MOPS_EXACT"
    proxy = frame["availability_method"] == "AVAILABLE_DATE_PROXY"
    timestamp = frame["announcement_timestamp"].notna()
    missing = ~(actual | proxy)
    frame = frame.assign(_actual=actual, _proxy=proxy, _timestamp=timestamp, _missing=missing)

    rows: list[dict[str, Any]] = []

    def append(scope_type: str, scope_value: str, selected: pd.DataFrame) -> None:
        count = len(selected)
        actual_count = int(selected["_actual"].sum())
        proxy_count = int(selected["_proxy"].sum())
        timestamp_count = int(selected["_timestamp"].sum())
        missing_count = int(selected["_missing"].sum())
        rows.append(
            {
                "scope_type": scope_type,
                "scope_value": scope_value,
                "observations": count,
                "mops_actual_count": actual_count,
                "timestamp_count": timestamp_count,
                "proxy_fallback_count": proxy_count,
                "missing_count": missing_count,
                "mops_actual_coverage": actual_count / count if count else None,
                "timestamp_coverage": timestamp_count / count if count else None,
                "proxy_fallback_coverage": proxy_count / count if count else None,
                "missing_coverage": missing_count / count if count else None,
            }
        )

    append("OVERALL", "ALL_FIXED_COHORT", frame)
    eligible = frame[frame["sector_logic"] != "FINANCIAL"]
    append("RESEARCH_SAMPLE", "ELIGIBLE_NON_FINANCIAL", eligible)
    for sector_logic, selected in frame.groupby("sector_logic", sort=True):
        append("SECTOR_LOGIC", str(sector_logic), selected)
    for symbol, selected in frame.groupby("symbol", sort=True):
        append("SYMBOL", str(symbol), selected)
    for year, selected in frame.groupby("period_year", sort=True):
        append("FISCAL_YEAR", str(int(year)), selected)
    for year, selected in eligible.groupby("period_year", sort=True):
        append("ELIGIBLE_FISCAL_YEAR", str(int(year)), selected)
    return pd.DataFrame(rows)
