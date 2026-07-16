from __future__ import annotations
import hashlib, json, math, re
from datetime import date, datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .errors import DataValidationError

_SOURCE_CODE_RE = re.compile(r"^[0-9]{4,6}$")

def canonical_symbol(source_symbol: str, market: str = "TW") -> str:
    if market != "TW":
        raise DataValidationError(f"unsupported market: {market}")
    if not isinstance(source_symbol, str) or not _SOURCE_CODE_RE.fullmatch(source_symbol):
        raise DataValidationError(f"unsupported source-to-canonical mapping: {source_symbol}/{market}")
    return f"{source_symbol}.TW"

def source_symbol_from_input(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise DataValidationError("blank source symbol")
    if symbol.endswith(".TW"):
        return canonical_symbol(symbol[:-3], "TW").removesuffix(".TW")
    if "." in symbol or symbol != symbol.strip():
        raise DataValidationError(f"malformed TWSE symbol: {symbol}")
    canonical_symbol(symbol, "TW")
    return symbol

def parse_iso_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as e:
        raise DataValidationError(f"invalid ISO date for {field}: {value}") from e
    return parsed

def validate_date_range(start: str, end: str) -> tuple[date, date]:
    start_date = parse_iso_date(start, "start")
    end_date = parse_iso_date(end, "end")
    if start_date > end_date:
        raise DataValidationError("start must be before or equal to end")
    return start_date, end_date

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

def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    pairs = [(key, "<redacted>" if key.lower() == "token" else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))

def stable_json_bytes(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
