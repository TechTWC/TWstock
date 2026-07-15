from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping


REQUIRED_INPUT_FIELDS = (
    "symbol",
    "name",
    "market",
    "security_type",
    "price_date",
    "required_data_valid",
    "financial_data_usable",
    "average_turnover_20d",
    "market_cap",
    "ttm_net_income",
    "ttm_operating_income",
    "ttm_operating_cash_flow",
    "latest_equity",
    "latest_total_assets",
    "latest_total_liabilities",
    "latest_current_assets",
    "latest_current_liabilities",
    "latest_q_operating_income",
    "previous_q_operating_income",
    "prior_year_q_operating_income",
)


class InputValidationError(ValueError):
    """Raised when the canonical snapshot input cannot be parsed safely."""


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith(("'", '"', "[", "{")):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise InputValidationError(f"Invalid YAML scalar: {value}") from exc
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_mapping_yaml(path: str | Path) -> dict[str, Any]:
    """Load the mapping-only YAML subset used by this dependency-free sandbox.

    The parser intentionally supports nested mappings and scalar values only.
    This keeps the runnable sandbox on the Python standard library while still
    allowing all thresholds to live in ``config/settings.yaml``.
    """

    settings_path = Path(path)
    if not settings_path.exists():
        raise InputValidationError(f"Settings file not found: {settings_path}")

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, original in enumerate(
        settings_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        uncommented = _strip_comment(original).rstrip()
        if not uncommented.strip():
            continue

        indent = len(uncommented) - len(uncommented.lstrip(" "))
        if indent % 2 != 0:
            raise InputValidationError(
                f"Settings indentation must use multiples of two spaces at line {line_number}"
            )

        stripped = uncommented.strip()
        key, separator, raw_value = stripped.partition(":")
        if not separator or not key.strip():
            raise InputValidationError(f"Invalid settings line {line_number}: {original}")

        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        normalized_key = key.strip()

        if raw_value.strip() == "":
            child: dict[str, Any] = {}
            parent[normalized_key] = child
            stack.append((indent, child))
        else:
            parent[normalized_key] = _parse_scalar(raw_value)

    return root


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            dotted = ".".join(keys)
            raise InputValidationError(f"Missing settings key: {dotted}")
        current = current[key]
    return current


@dataclass(frozen=True)
class Settings:
    release_name: str
    strategy_name: str
    strategy_version: str
    supported_market: str
    supported_security_type: str
    tw_min_average_turnover_20d: float
    equity_failure_threshold: float
    ttm_operating_income_failure_threshold: float
    negative_quarter_threshold: float
    nonpositive_ocf_threshold: float
    debt_ratio_warning_threshold: float
    current_ratio_threshold: float
    warning_watch_min_count: int
    net_income_positive_threshold: float
    market_cap_positive_threshold: float
    very_low_pe_max: float
    absolute_cheap_pe_max: float
    fair_pe_max: float
    earnings_positive_threshold: float
    earnings_yoy_ok_threshold: float

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = load_mapping_yaml(path)
        return cls(
            release_name=str(_nested(raw, "release", "name")),
            strategy_name=str(_nested(raw, "strategy", "name")),
            strategy_version=str(_nested(raw, "strategy", "version")),
            supported_market=str(_nested(raw, "scope", "supported_market")),
            supported_security_type=str(
                _nested(raw, "scope", "supported_security_type")
            ),
            tw_min_average_turnover_20d=float(
                _nested(raw, "liquidity", "tw_min_average_turnover_20d")
            ),
            equity_failure_threshold=float(
                _nested(raw, "fundamental", "equity_failure_threshold")
            ),
            ttm_operating_income_failure_threshold=float(
                _nested(
                    raw,
                    "fundamental",
                    "ttm_operating_income_failure_threshold",
                )
            ),
            negative_quarter_threshold=float(
                _nested(raw, "fundamental", "negative_quarter_threshold")
            ),
            nonpositive_ocf_threshold=float(
                _nested(raw, "fundamental", "nonpositive_ocf_threshold")
            ),
            debt_ratio_warning_threshold=float(
                _nested(raw, "fundamental", "debt_ratio_warning_threshold")
            ),
            current_ratio_threshold=float(
                _nested(raw, "fundamental", "current_ratio_threshold")
            ),
            warning_watch_min_count=int(
                _nested(raw, "fundamental", "warning_watch_min_count")
            ),
            net_income_positive_threshold=float(
                _nested(raw, "valuation", "net_income_positive_threshold")
            ),
            market_cap_positive_threshold=float(
                _nested(raw, "valuation", "market_cap_positive_threshold")
            ),
            very_low_pe_max=float(_nested(raw, "valuation", "very_low_pe_max")),
            absolute_cheap_pe_max=float(
                _nested(raw, "valuation", "absolute_cheap_pe_max")
            ),
            fair_pe_max=float(_nested(raw, "valuation", "fair_pe_max")),
            earnings_positive_threshold=float(
                _nested(raw, "earnings", "positive_threshold")
            ),
            earnings_yoy_ok_threshold=float(
                _nested(raw, "earnings", "yoy_ok_threshold")
            ),
        )


def _parse_bool(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise InputValidationError(f"Invalid boolean for {field_name}: {value!r}")


def _parse_finite_float(value: str, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"Invalid number for {field_name}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise InputValidationError(f"Non-finite number for {field_name}: {value!r}")
    return parsed


def _validate_canonical_symbol(symbol: str, market: str) -> None:
    if market == "TW" and (not symbol.endswith(".TW") or not symbol[:-3]):
        raise InputValidationError(
            "Invalid canonical symbol for market TW: symbol must use the exact "
            "uppercase .TW suffix with a non-blank prefix"
        )


@dataclass(frozen=True)
class StockSnapshot:
    symbol: str
    name: str
    market: str
    security_type: str
    price_date: date
    required_data_valid: bool
    financial_data_usable: bool
    average_turnover_20d: float
    market_cap: float
    ttm_net_income: float
    ttm_operating_income: float
    ttm_operating_cash_flow: float
    latest_equity: float
    latest_total_assets: float
    latest_total_liabilities: float
    latest_current_assets: float
    latest_current_liabilities: float
    latest_q_operating_income: float
    previous_q_operating_income: float
    prior_year_q_operating_income: float
    is_synthetic: bool = False
    source_note: str = ""

    @classmethod
    def from_csv_row(cls, row: Mapping[str, str]) -> "StockSnapshot":
        missing = [field for field in REQUIRED_INPUT_FIELDS if field not in row]
        if missing:
            raise InputValidationError(
                "Missing required CSV fields: " + ", ".join(sorted(missing))
            )
        blank = [field for field in REQUIRED_INPUT_FIELDS if not str(row[field]).strip()]
        if blank:
            raise InputValidationError(
                "Blank required CSV values: " + ", ".join(sorted(blank))
            )

        symbol = row["symbol"].strip()
        market = row["market"].strip()
        _validate_canonical_symbol(symbol, market)

        try:
            parsed_date = date.fromisoformat(row["price_date"].strip())
        except ValueError as exc:
            raise InputValidationError(
                f"Invalid ISO price_date: {row['price_date']!r}"
            ) from exc

        snapshot = cls(
            symbol=symbol,
            name=row["name"].strip(),
            market=market,
            security_type=row["security_type"].strip(),
            price_date=parsed_date,
            required_data_valid=_parse_bool(
                row["required_data_valid"], "required_data_valid"
            ),
            financial_data_usable=_parse_bool(
                row["financial_data_usable"], "financial_data_usable"
            ),
            average_turnover_20d=_parse_finite_float(
                row["average_turnover_20d"], "average_turnover_20d"
            ),
            market_cap=_parse_finite_float(row["market_cap"], "market_cap"),
            ttm_net_income=_parse_finite_float(
                row["ttm_net_income"], "ttm_net_income"
            ),
            ttm_operating_income=_parse_finite_float(
                row["ttm_operating_income"], "ttm_operating_income"
            ),
            ttm_operating_cash_flow=_parse_finite_float(
                row["ttm_operating_cash_flow"], "ttm_operating_cash_flow"
            ),
            latest_equity=_parse_finite_float(
                row["latest_equity"], "latest_equity"
            ),
            latest_total_assets=_parse_finite_float(
                row["latest_total_assets"], "latest_total_assets"
            ),
            latest_total_liabilities=_parse_finite_float(
                row["latest_total_liabilities"], "latest_total_liabilities"
            ),
            latest_current_assets=_parse_finite_float(
                row["latest_current_assets"], "latest_current_assets"
            ),
            latest_current_liabilities=_parse_finite_float(
                row["latest_current_liabilities"], "latest_current_liabilities"
            ),
            latest_q_operating_income=_parse_finite_float(
                row["latest_q_operating_income"], "latest_q_operating_income"
            ),
            previous_q_operating_income=_parse_finite_float(
                row["previous_q_operating_income"], "previous_q_operating_income"
            ),
            prior_year_q_operating_income=_parse_finite_float(
                row["prior_year_q_operating_income"],
                "prior_year_q_operating_income",
            ),
            is_synthetic=_parse_bool(row.get("is_synthetic", "false"), "is_synthetic"),
            source_note=row.get("source_note", "").strip(),
        )

        if snapshot.average_turnover_20d < 0:
            raise InputValidationError("average_turnover_20d must not be negative")
        if snapshot.latest_total_assets <= 0:
            raise InputValidationError("latest_total_assets must be positive")
        if snapshot.latest_total_liabilities < 0:
            raise InputValidationError("latest_total_liabilities must not be negative")
        if snapshot.latest_current_assets < 0:
            raise InputValidationError("latest_current_assets must not be negative")
        if snapshot.latest_current_liabilities < 0:
            raise InputValidationError("latest_current_liabilities must not be negative")
        return snapshot


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FundamentalResult:
    status: str
    warning_reasons: tuple[str, ...]
    risk_flags: tuple[str, ...]
    informational_tags: tuple[str, ...]
    warning_count: int
    debt_ratio: float
    current_ratio: float


@dataclass(frozen=True)
class ValuationResult:
    status: str
    pe_ttm: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EarningsDirectionResult:
    status: str
    operating_income_yoy: float | None


@dataclass(frozen=True)
class ActionResolution:
    primary_action: str
    trigger_reasons: tuple[str, ...]
    data_quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class ScreeningResult:
    snapshot: StockSnapshot
    eligibility: EligibilityResult
    fundamental: FundamentalResult
    valuation: ValuationResult
    earnings: EarningsDirectionResult
    action: ActionResolution
    risk_flags: tuple[str, ...]
    informational_tags: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "symbol": self.snapshot.symbol,
            "name": self.snapshot.name,
            "market": self.snapshot.market,
            "security_type": self.snapshot.security_type,
            "price_date": self.snapshot.price_date.isoformat(),
            "is_synthetic": self.snapshot.is_synthetic,
            "source_note": self.snapshot.source_note,
            "evaluation_status": "EVALUATED",
            "required_data_valid": self.snapshot.required_data_valid,
            "financial_data_usable": self.snapshot.financial_data_usable,
            "average_turnover_20d": self.snapshot.average_turnover_20d,
            "market_cap": self.snapshot.market_cap,
            "ttm_net_income": self.snapshot.ttm_net_income,
            "ttm_operating_income": self.snapshot.ttm_operating_income,
            "ttm_operating_cash_flow": self.snapshot.ttm_operating_cash_flow,
            "latest_equity": self.snapshot.latest_equity,
            "latest_total_assets": self.snapshot.latest_total_assets,
            "latest_total_liabilities": self.snapshot.latest_total_liabilities,
            "latest_current_assets": self.snapshot.latest_current_assets,
            "latest_current_liabilities": self.snapshot.latest_current_liabilities,
            "latest_q_operating_income": self.snapshot.latest_q_operating_income,
            "previous_q_operating_income": self.snapshot.previous_q_operating_income,
            "prior_year_q_operating_income": self.snapshot.prior_year_q_operating_income,
            "eligibility_status": self.eligibility.status,
            "fundamental_status": self.fundamental.status,
            "fundamental_warning_count": self.fundamental.warning_count,
            "debt_ratio": self.fundamental.debt_ratio,
            "current_ratio": self.fundamental.current_ratio,
            "absolute_valuation_status": self.valuation.status,
            "pe_ttm": self.valuation.pe_ttm,
            "earnings_status": self.earnings.status,
            "operating_income_yoy": self.earnings.operating_income_yoy,
            "primary_action": self.action.primary_action,
            "trigger_reasons": list(self.action.trigger_reasons),
            "warning_reasons": list(self.fundamental.warning_reasons),
            "risk_flags": list(self.risk_flags),
            "data_quality_flags": list(self.action.data_quality_flags),
            "informational_tags": list(self.informational_tags),
        }
