import csv
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.run_pe_river_report import run
from twstock_data.http import HttpResponse
from twstock_data.sources.twse_valuation import ValuationObservation
from twstock_valuation.pe_river import build_metadata, calculate_rivers
from twstock_valuation.pe_river_pdf import write_report


def test_pdf_csv_metadata(tmp_path):
    observations = [ValuationObservation("2330", date(2005, 9, 2), 600, 20),
                    ValuationObservation("2330", date(2026, 9, 29), 610, None)]
    rows = calculate_rivers(observations)
    metadata = build_metadata(rows, requested_coverage="MAX", requested_start=date(2005, 9, 1))
    result = write_report(rows, metadata, tmp_path)
    pdf = Path(result["outputs"]["pdf"])
    assert pdf.is_file() and pdf.stat().st_size > 1000
    assert pdf.read_bytes().startswith(b"%PDF-")
    saved = json.loads((tmp_path / "report_metadata.json").read_text())
    assert saved["missing_pe_count"] == 1
    assert saved["latest_valid_pe_date"] == "2005-09-02"
    with (tmp_path / "historical_pe_river.csv").open() as handle:
        data = list(csv.DictReader(handle))
    assert data[0]["river_15x"] == "450.0"
    assert data[1]["reference_eps_twd"] == data[1]["river_15x"] == ""
    assert data[1]["pe_status"] == "PE_UNAVAILABLE"


def test_cli_offline_end_to_end(tmp_path):
    class FixtureTransport:
        def get(self, url, timeout):
            name = "twse_valuation_2330_200509.json" if "/BWIBBU?" in url else "twse_close_avg_2330_200509.json"
            body = (Path(__file__).parent / "fixtures" / name).read_bytes()
            return HttpResponse(url, 200, body)
    assert run(["--symbol", "2330", "--max", "--output-dir", str(tmp_path / "output"),
                "--cache-dir", str(tmp_path / "cache"), "--request-interval", "0"],
               transport=FixtureTransport(), now=datetime(2005, 9, 30, 12, tzinfo=ZoneInfo("Asia/Taipei"))) == 0
    assert (tmp_path / "output" / "2330_pe_river.pdf").exists()


def test_cli_rejects_etf_before_fetch(tmp_path):
    class NoNetwork:
        def get(self, *args):
            raise AssertionError("must not fetch")
    assert run(["--symbol", "0050", "--cache-dir", str(tmp_path)], transport=NoNetwork()) == 1
