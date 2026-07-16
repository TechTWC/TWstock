from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timezone
from .errors import DataValidationError

def canonical_symbol(source_symbol: str, market: str = "TW") -> str:
    if market == "TW" and source_symbol == "2330": return "2330.TW"
    raise DataValidationError(f"unsupported source-to-canonical mapping: {source_symbol}/{market}")

def parse_int(value: object, field: str) -> int:
    if value is None or str(value).strip() == "": raise DataValidationError(f"missing {field}")
    text = str(value).replace(",", "").strip()
    try: number = int(text)
    except ValueError as e: raise DataValidationError(f"invalid integer {field}: {value!r}") from e
    if number <= 0: raise DataValidationError(f"nonpositive {field}: {value!r}")
    return number

def parse_float(value: object, field: str) -> float:
    if value is None or str(value).strip() == "": raise DataValidationError(f"missing {field}")
    try: number = float(str(value).replace(",", "").strip())
    except ValueError as e: raise DataValidationError(f"invalid number {field}: {value!r}") from e
    if not math.isfinite(number) or number <= 0: raise DataValidationError(f"nonpositive/nonfinite {field}: {value!r}")
    return number

def raw_hash(content: bytes | str) -> str:
    if isinstance(content, str): content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()

def stable_json_bytes(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
