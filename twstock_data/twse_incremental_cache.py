from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence

from .errors import DataValidationError
from .normalization import sanitize_url


_CACHE_SCHEMA = "TWSTOCK-TWSE-MONTH-CACHE-001"
_RUN_SCHEMA = "TWSTOCK-TWSE-CACHE-RUN-001"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CachedMonthResponse:
    body: bytes
    source_url: str
    retrieved_at: str
    sha256: str
    origin: str


def load_cached_month(
    root: Path,
    *,
    source_symbol: str,
    canonical_symbol: str,
    month_identifier: str,
    expected_source_url: str,
) -> CachedMonthResponse | None:
    """Load an integrity-checked stable month, importing a valid v0.1 snapshot."""

    raw_path, metadata_path = _stable_paths(root, source_symbol, month_identifier)
    if raw_path.exists() or metadata_path.exists():
        if not raw_path.is_file() or not metadata_path.is_file():
            raise DataValidationError(
                f"incomplete TWSE month cache for {source_symbol} {month_identifier}"
            )
        return _read_entry(
            metadata_path,
            expected_raw_path=raw_path,
            source_symbol=source_symbol,
            canonical_symbol=canonical_symbol,
            month_identifier=month_identifier,
            expected_source_url=expected_source_url,
            expected_schema=_CACHE_SCHEMA,
            origin="STABLE_CACHE",
        )

    legacy_pattern = (
        f"twse_{source_symbol}_*_*_twse_{month_identifier}_*.metadata.json"
    )
    candidates: list[CachedMonthResponse] = []
    invalid_found = False
    for legacy_metadata in sorted(root.glob(legacy_pattern)):
        try:
            candidates.append(
                _read_entry(
                    legacy_metadata,
                    expected_raw_path=None,
                    source_symbol=source_symbol,
                    canonical_symbol=canonical_symbol,
                    month_identifier=month_identifier,
                    expected_source_url=expected_source_url,
                    expected_schema=None,
                    origin="LEGACY_V0_1_CACHE",
                )
            )
        except DataValidationError:
            invalid_found = True
    if candidates:
        selected = max(candidates, key=lambda item: item.retrieved_at)
        return CachedMonthResponse(
            body=selected.body,
            source_url=selected.source_url,
            retrieved_at=selected.retrieved_at,
            sha256=selected.sha256,
            origin="LEGACY_V0_1_CACHE",
        )
    if invalid_found:
        raise DataValidationError(
            f"invalid legacy TWSE month cache for {source_symbol} {month_identifier}"
        )
    return None


def store_cached_month(
    root: Path,
    *,
    source_symbol: str,
    canonical_symbol: str,
    month_identifier: str,
    source_url: str,
    retrieved_at: str,
    http_status: int,
    body: bytes,
) -> None:
    raw_path, metadata_path = _stable_paths(root, source_symbol, month_identifier)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(body).hexdigest()
    metadata = {
        "schema_version": _CACHE_SCHEMA,
        "source": "TWSE",
        "source_tier": "PRIMARY",
        "source_symbol": source_symbol,
        "canonical_symbol": canonical_symbol,
        "month_identifier": month_identifier,
        "retrieval_timestamp": retrieved_at,
        "sanitized_source_url": sanitize_url(source_url),
        "http_status": http_status,
        "sha256": digest,
        "raw_file": raw_path.name,
    }
    _atomic_write(raw_path, body)
    _atomic_write(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def write_cache_run_manifest(
    root: Path,
    *,
    source_symbol: str,
    requested_start: str,
    requested_end: str,
    refresh_month: str | None,
    month_results: Sequence[dict[str, object]],
    completed: bool,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _RUN_SCHEMA,
        "source": "TWSE",
        "source_symbol": source_symbol,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "refresh_month": refresh_month,
        "completed": completed,
        "resumable": True,
        "month_results": list(month_results),
    }
    _atomic_write(
        root / "twse_cache_run.json",
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def _stable_paths(
    root: Path, source_symbol: str, month_identifier: str
) -> tuple[Path, Path]:
    stem = f"twse_{source_symbol}_{month_identifier}"
    monthly = root / ".monthly"
    return monthly / f"{stem}.raw", monthly / f"{stem}.metadata.json"


def _read_entry(
    metadata_path: Path,
    *,
    expected_raw_path: Path | None,
    source_symbol: str,
    canonical_symbol: str,
    month_identifier: str,
    expected_source_url: str,
    expected_schema: str | None,
    origin: str,
) -> CachedMonthResponse:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DataValidationError("TWSE cache metadata is unreadable") from error
    if not isinstance(metadata, dict):
        raise DataValidationError("TWSE cache metadata must be an object")
    if expected_schema is not None and metadata.get("schema_version") != expected_schema:
        raise DataValidationError("TWSE cache schema mismatch")
    expected_identity = {
        "source": "TWSE",
        "source_tier": "PRIMARY",
        "source_symbol": source_symbol,
        "canonical_symbol": canonical_symbol,
    }
    if any(metadata.get(key) != value for key, value in expected_identity.items()):
        raise DataValidationError("TWSE cache identity mismatch")
    if expected_schema is not None and metadata.get("month_identifier") != month_identifier:
        raise DataValidationError("TWSE cache month mismatch")
    if metadata.get("http_status") != 200:
        raise DataValidationError("TWSE cache HTTP status is not successful")
    expected_url = sanitize_url(expected_source_url)
    if metadata.get("sanitized_source_url") != expected_url:
        raise DataValidationError("TWSE cache source URL mismatch")
    raw_name = metadata.get("raw_file")
    if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
        raise DataValidationError("TWSE cache raw file reference is unsafe")
    raw_path = metadata_path.parent / raw_name
    if expected_raw_path is not None and raw_path != expected_raw_path:
        raise DataValidationError("TWSE cache raw file identity mismatch")
    try:
        body = raw_path.read_bytes()
    except OSError as error:
        raise DataValidationError("TWSE cache raw file is unreadable") from error
    digest = metadata.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise DataValidationError("TWSE cache SHA-256 is invalid")
    if hashlib.sha256(body).hexdigest() != digest:
        raise DataValidationError("TWSE cache SHA-256 mismatch")
    retrieved_at = metadata.get("retrieval_timestamp")
    if not isinstance(retrieved_at, str) or not retrieved_at:
        raise DataValidationError("TWSE cache retrieval timestamp is missing")
    return CachedMonthResponse(
        body=body,
        source_url=expected_url,
        retrieved_at=retrieved_at,
        sha256=digest,
        origin=origin,
    )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
