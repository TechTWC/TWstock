from __future__ import annotations

import csv
import html
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .actions import PRIMARY_ACTION_ORDER
from .models import ScreeningResult


CSV_FIELD_ORDER = (
    "symbol",
    "name",
    "market",
    "security_type",
    "price_date",
    "is_synthetic",
    "source_note",
    "evaluation_status",
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
    "eligibility_status",
    "fundamental_status",
    "fundamental_warning_count",
    "debt_ratio",
    "current_ratio",
    "absolute_valuation_status",
    "pe_ttm",
    "earnings_status",
    "operating_income_yoy",
    "primary_action",
    "trigger_reasons",
    "warning_reasons",
    "risk_flags",
    "data_quality_flags",
    "informational_tags",
)

_LIST_FIELDS = {
    "trigger_reasons",
    "warning_reasons",
    "risk_flags",
    "data_quality_flags",
    "informational_tags",
}


def _csv_value(field: str, value: Any) -> Any:
    if field in _LIST_FIELDS:
        return "|".join(value)
    if isinstance(value, float) and math.isinf(value):
        return "Infinity"
    if value is None:
        return ""
    return value


def write_csv(results: Iterable[ScreeningResult], path: Path) -> None:
    records = [result.to_record() for result in results]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELD_ORDER)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {field: _csv_value(field, record[field]) for field in CSV_FIELD_ORDER}
            )


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if math.isnan(value):
            return None
        return value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def write_json(
    results: Iterable[ScreeningResult],
    path: Path,
    *,
    release_name: str,
    strategy_name: str,
    strategy_version: str,
) -> None:
    payload = {
        "release_name": release_name,
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "results": [result.to_record() for result in results],
    }
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _display_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if math.isinf(value):
        return "∞"
    return f"{value:.{digits}f}"


def _tags(values: list[str]) -> str:
    if not values:
        return "—"
    return "<br>".join(html.escape(value) for value in values)


def write_html(
    results: Iterable[ScreeningResult],
    path: Path,
    *,
    release_name: str,
    strategy_name: str,
    strategy_version: str,
) -> None:
    records = [result.to_record() for result in results]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["primary_action"]].append(record)

    sections: list[str] = []
    for action in PRIMARY_ACTION_ORDER:
        action_records = grouped.get(action, [])
        if not action_records:
            continue
        rows: list[str] = []
        for record in sorted(action_records, key=lambda item: item["symbol"]):
            rows.append(
                "<tr>"
                f"<td>{html.escape(record['symbol'])}</td>"
                f"<td>{html.escape(record['name'])}</td>"
                f"<td>{_display_number(record['pe_ttm'])}</td>"
                f"<td>{html.escape(record['absolute_valuation_status'])}</td>"
                f"<td>{html.escape(record['fundamental_status'])}</td>"
                f"<td>{html.escape(record['earnings_status'])}</td>"
                f"<td>{_tags(record['trigger_reasons'])}</td>"
                f"<td>{_tags(record['warning_reasons'])}</td>"
                f"<td>{_tags(record['risk_flags'])}</td>"
                f"<td>{_tags(record['data_quality_flags'])}</td>"
                f"<td>{_tags(record['informational_tags'])}</td>"
                "</tr>"
            )
        sections.append(
            f"<section><h2>{html.escape(action)} <span>{len(action_records)}</span></h2>"
            "<div class=table-wrap><table><thead><tr>"
            "<th>Symbol</th><th>Name</th><th>PE</th><th>Valuation</th>"
            "<th>Fundamental</th><th>Earnings</th><th>Triggers</th>"
            "<th>Warnings</th><th>Risk flags</th><th>Data flags</th>"
            "<th>Informational tags</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div></section>"
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(release_name)}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
body {{ margin: 0; background: #f4f5f7; color: #17191c; }}
main {{ max-width: 1500px; margin: 0 auto; padding: 28px; }}
header, section {{ background: white; border: 1px solid #d9dde3; border-radius: 10px; padding: 20px; margin-bottom: 18px; }}
h1 {{ margin: 0 0 8px; }}
p {{ margin: 4px 0; color: #4b5563; }}
h2 {{ margin: 0 0 14px; font-size: 1.15rem; }}
h2 span {{ font-size: .85rem; font-weight: 600; color: #6b7280; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 9px; text-align: left; vertical-align: top; }}
th {{ background: #f8fafc; white-space: nowrap; }}
code {{ background: #eef2f7; padding: 2px 5px; border-radius: 4px; }}
</style>
</head>
<body><main>
<header>
<h1>{html.escape(release_name)}</h1>
<p><code>{html.escape(strategy_name)}</code> · specification {html.escape(strategy_version)}</p>
<p>Experimental deterministic logic output. Synthetic sample data is not investment evidence.</p>
</header>
{''.join(sections)}
</main></body></html>
"""
    path.write_text(document, encoding="utf-8")
