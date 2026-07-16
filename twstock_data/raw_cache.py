from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .normalization import raw_hash, sanitize_url

def preserve_raw_response(
    raw_cache_dir: Path | str | None,
    *,
    source: str,
    source_tier: str,
    source_symbol: str,
    canonical_symbol: str,
    requested_start: str,
    requested_end: str,
    retrieved_at: str,
    source_url: str,
    http_status: int,
    body: bytes,
) -> dict[str, Any] | None:
    if raw_cache_dir is None:
        return None
    root = Path(raw_cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    digest = raw_hash(body)
    stem = f"{source.lower()}_{source_symbol}_{requested_start}_{requested_end}_{digest[:12]}"
    raw_path = root / f"{stem}.raw"
    meta_path = root / f"{stem}.metadata.json"
    raw_path.write_bytes(body)
    metadata = {
        "source": source,
        "source_tier": source_tier,
        "source_symbol": source_symbol,
        "canonical_symbol": canonical_symbol,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "retrieval_timestamp": retrieved_at,
        "sanitized_source_url": sanitize_url(source_url),
        "http_status": http_status,
        "sha256": digest,
        "raw_file": raw_path.name,
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
