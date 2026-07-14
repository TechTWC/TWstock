from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

REQUIRED_FIELDS = [
    "symbol", "name", "market", "security_type", "price_date",
    "required_data_valid", "financial_data_usable", "average_turnover_20d",
    "market_cap", "ttm_net_income", "ttm_operating_income",
    "ttm_operating_cash_flow", "latest_equity", "latest_total_assets",
    "latest_total_liabilities", "latest_current_assets",
    "latest_current_liabilities", "latest_q_operating_income",
    "previous_q_operating_income", "prior_year_q_operating_income",
]

NUMERIC_FIELDS = set(REQUIRED_FIELDS) - {"symbol", "name", "market", "security_type", "price_date", "required_data_valid", "financial_data_usable"}
BOOL_FIELDS = {"required_data_valid", "financial_data_usable"}

@dataclass(frozen=True)
class StockSnapshot:
    symbol: str
    name: str
    market: str
    security_type: str
    price_date: str
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

    @property
    def pe(self) -> float | None:
        if self.ttm_net_income <= 0:
            return None
        return self.market_cap / self.ttm_net_income


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def snapshot_from_row(row: dict[str, Any]) -> StockSnapshot:
    missing = [field for field in REQUIRED_FIELDS if field not in row or row[field] == ""]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    values: dict[str, Any] = {}
    for key in REQUIRED_FIELDS:
        if key in BOOL_FIELDS:
            values[key] = parse_bool(row[key])
        elif key in NUMERIC_FIELDS:
            values[key] = float(row[key])
        else:
            values[key] = str(row[key]).strip()
    return StockSnapshot(**values)

@dataclass
class ScreeningResult:
    symbol: str
    name: str
    market: str
    price_date: str
    eligibility_status: str
    fundamental_status: str
    valuation_status: str
    earnings_direction: str
    pe: float | None
    primary_action: str
    trigger_reasons: list[str] = field(default_factory=list)
    warning_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    data_quality_flags: list[str] = field(default_factory=list)
    informational_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
