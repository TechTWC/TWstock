from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from .actions import resolve_primary_action
from .models import REQUIRED_FIELDS, ScreeningResult, snapshot_from_row
from .report import render_html
from .rules import calculate_absolute_pe_status, evaluate_earnings_direction, evaluate_eligibility, evaluate_fundamental_status


def load_settings(path: str = "config/settings.yaml") -> dict:
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except ModuleNotFoundError:
        # Minimal parser sufficient for this repository's simple settings file.
        settings: dict = {"phase_a1": {"liquidity": {"TW": {}}, "fundamentals": {}, "valuation": {}}}
        section: list[str] = []
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.strip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip())
            key, value = [part.strip() for part in raw.split(":", 1)]
            level = indent // 2
            section = section[:level]
            if value == "":
                section.append(key)
                continue
            target = settings
            for part in section:
                target = target[part]
            target[key] = value.strip('"') if not value.replace(".", "", 1).isdigit() else float(value)
        return settings


def screen(input_path: str, settings: dict) -> list[ScreeningResult]:
    with open(input_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [field for field in REQUIRED_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"input CSV missing columns: {', '.join(missing)}")
        results = []
        for row in reader:
            snapshot = snapshot_from_row(row)
            eligibility, eligibility_reasons = evaluate_eligibility(snapshot, settings)
            fundamental, fund_triggers, warnings, info = evaluate_fundamental_status(snapshot, settings)
            valuation, pe = calculate_absolute_pe_status(snapshot, settings)
            earnings = evaluate_earnings_direction(snapshot, settings)
            action, action_triggers, data_flags = resolve_primary_action(snapshot, eligibility, fundamental, valuation, earnings, settings)
            trigger_reasons = eligibility_reasons + fund_triggers + action_triggers
            risk_flags = list(dict.fromkeys(fund_triggers + ([earnings] if earnings in {"EARNINGS_WEAK", "TURNAROUND_NEGATIVE", "BOTH_NON_POSITIVE"} else [])))
            results.append(ScreeningResult(snapshot.symbol, snapshot.name, snapshot.market, snapshot.price_date, eligibility, fundamental, valuation, earnings, pe, action, list(dict.fromkeys(trigger_reasons)), warnings, risk_flags, data_flags, info))
    return results


def write_outputs(results: list[ScreeningResult], output_dir: str, settings: dict) -> None:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in results]
    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, list): row[key] = ";".join(value)
    with open(out / "screening_results.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    (out / "screening_results.json").write_text(json.dumps([r.to_dict() for r in results], indent=2), encoding="utf-8")
    release = settings["phase_a1"].get("release_name", "Phase A1 Logic Sandbox")
    (out / "report.html").write_text(render_html(results, release), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--settings", default="config/settings.yaml")
    args = parser.parse_args()
    settings = load_settings(args.settings)
    results = screen(args.input, settings)
    write_outputs(results, args.output_dir, settings)

if __name__ == "__main__":
    main()
