from __future__ import annotations

import html
from collections import defaultdict
from .models import ScreeningResult


def render_html(results: list[ScreeningResult], release_name: str) -> str:
    grouped: dict[str, list[ScreeningResult]] = defaultdict(list)
    for result in results:
        grouped[result.primary_action].append(result)
    parts = ["<!doctype html><html><head><meta charset='utf-8'>", f"<title>{html.escape(release_name)}</title>", "<style>body{font-family:sans-serif}table{border-collapse:collapse;width:100%;margin-bottom:2rem}td,th{border:1px solid #ccc;padding:.4rem;text-align:left}th{background:#f2f2f2}</style></head><body>", f"<h1>{html.escape(release_name)}</h1>"]
    for action in sorted(grouped):
        parts.append(f"<h2>{html.escape(action)}</h2><table><thead><tr><th>Symbol</th><th>Name</th><th>PE</th><th>Fundamental</th><th>Valuation</th><th>Earnings</th><th>Triggers</th><th>Warnings</th><th>Data quality</th><th>Info</th></tr></thead><tbody>")
        for r in grouped[action]:
            pe = "" if r.pe is None else f"{r.pe:.2f}"
            cells = [r.symbol, r.name, pe, r.fundamental_status, r.valuation_status, r.earnings_direction, "; ".join(r.trigger_reasons), "; ".join(r.warning_reasons), "; ".join(r.data_quality_flags), "; ".join(r.informational_tags)]
            parts.append("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in cells) + "</tr>")
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    return "\n".join(parts)
