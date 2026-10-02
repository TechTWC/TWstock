import csv
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.run_pe_river_report import run
from twstock_data.http import HttpResponse
from twstock_data.sources.mops_face_value_change import (
    FACE_VALUE_COVERAGE_PROVEN, FaceValueCoverageProof,
)
from twstock_data.sources.twse_corporate_actions import (
    FACE_VALUE_CHANGE_REVERSE_SPLIT, FACE_VALUE_CHANGE_SPLIT,
    NORMALIZATION_READY, STOCK_DIVIDEND, CorporateActionEvent,
)
from twstock_data.sources.twse_valuation import ValuationObservation
from twstock_valuation.corporate_actions import (
    NORMALIZED_PERCENTILE_INCOMPLETE, build_corporate_action_metadata,
    normalize_for_corporate_actions,
)
from twstock_valuation.pe_river import build_metadata, calculate_rivers
from twstock_valuation.pe_river_pdf import _event_marker_label, _summary_lines, write_report


def face_proof(symbol, start, end):
    return FaceValueCoverageProof(
        symbol=symbol, query_start=start, query_end=end,
        result_count=0, detail_count=0, rowset_hash="1" * 64,
        detail_manifest_hash="2" * 64,
        retrieved_at="2026-10-02T03:00:00Z",
        status=FACE_VALUE_COVERAGE_PROVEN,
    )


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
            if "/BWIBBU?" in url:
                body = (Path(__file__).parent / "fixtures" / "twse_valuation_2330_200509.json").read_bytes()
            elif "/STOCK_DAY_AVG?" in url:
                body = (Path(__file__).parent / "fixtures" / "twse_close_avg_2330_200509.json").read_bytes()
            elif "/TWT49U?" in url:
                body = json.dumps({"stat": "OK", "fields": [
                    "資料日期", "股票代號", "除權息前收盤價", "除權息參考價",
                    "權/息", "詳細資料"],
                                   "data": []}).encode()
            else:
                raise AssertionError(url)
            return HttpResponse(url, 200, body)
    assert run(["--symbol", "2330", "--max", "--output-dir", str(tmp_path / "output"),
                "--cache-dir", str(tmp_path / "cache"), "--request-interval", "0"],
               transport=FixtureTransport(), now=datetime(2005, 9, 30, 12, tzinfo=ZoneInfo("Asia/Taipei"))) == 0
    assert (tmp_path / "output" / "2330_pe_river.pdf").exists()


def test_adjusted_pdf_csv_metadata(tmp_path):
    observations = (
        ValuationObservation("6669", date(2026, 9, 1), 7800, 20,
                             financial_report_period_raw="115/2",
                             reference_period_end=date(2026, 6, 30)),
        ValuationObservation("6669", date(2026, 9, 3), 2615, 6.7,
                             financial_report_period_raw="115/2",
                             reference_period_end=date(2026, 6, 30)),
        ValuationObservation("6669", date(2026, 9, 4), 2620, None,
                             financial_report_period_raw="115/2",
                             reference_period_end=date(2026, 6, 30)),
    )
    action = CorporateActionEvent(
        symbol="6669", effective_date=date(2026, 9, 2), action_type=STOCK_DIVIDEND,
        share_factor=2.9828, cash_return_per_share=None, pre_event_close=7800,
        official_reference_price=2614.99,
        source_url="https://www.twse.com.tw/summary",
        detail_source_url="https://www.twse.com.tw/detail",
        retrieved_at="2026-10-01T00:00:00Z", raw_hash="0" * 64,
        status=NORMALIZATION_READY, bonus_share_rate=1.9828,
    )
    raw = calculate_rivers(observations)
    normalized = normalize_for_corporate_actions(
        observations, (action,), analysis_end_date=date(2026, 9, 30))
    metadata = build_metadata(
        raw, requested_coverage="MAX", requested_start=date(2005, 9, 1))
    metadata = build_corporate_action_metadata(
        normalized, (action,), metadata,
        face_value_proof=face_proof("6669", date(2019, 3, 27), date(2026, 9, 30)))
    result = write_report(
        raw, metadata, tmp_path, normalized_rows=normalized, events=(action,))
    saved = json.loads((tmp_path / "report_metadata.json").read_text())
    assert saved["report_title"] == "6669 | Corporate-Action Adjusted PE River"
    assert saved["pdf_event_marker_count"] == 1
    assert saved["unavailable_pe_invariant"]["passed"] is True
    assert Path(result["outputs"]["pdf"]).stat().st_size > 1000
    with (tmp_path / "historical_pe_river.csv").open() as handle:
        data = list(csv.DictReader(handle))
    assert float(data[0]["adjusted_close"]) == 7800 / 2.9828
    assert float(data[1]["normalized_pe"]) == 6.7 * 2.9828
    assert data[0]["reference_eps_twd"] == data[0]["raw_implied_reference_eps"]
    assert data[2]["official_pe"] == data[2]["normalized_pe"] == ""
    assert data[2]["raw_implied_reference_eps"] == ""
    assert data[2]["adjusted_reference_eps"] == data[2]["adjusted_river_15x"] == ""


def test_incomplete_normalized_distribution_never_falls_back_to_raw_in_pdf():
    observations = (
        ValuationObservation("2603", date(2005, 9, 2), 20, 10,
                             financial_report_period_raw="94/2",
                             reference_period_end=date(2005, 6, 30)),
        ValuationObservation("2603", date(2022, 9, 19), 169, 2.45,
                             financial_report_period_raw="111/2",
                             reference_period_end=date(2022, 6, 30)),
    )
    raw = calculate_rivers(observations)
    normalized = normalize_for_corporate_actions(observations, ())
    metadata = build_metadata(
        raw, requested_coverage="MAX", requested_start=date(2005, 9, 1))
    metadata = build_corporate_action_metadata(
        normalized, (), metadata,
        face_value_proof=face_proof("2603", date(2013, 12, 30), date(2022, 9, 19)))
    assert metadata["normalized_pe_distribution"] is None
    assert metadata["normalization_status"] == NORMALIZED_PERCENTILE_INCOMPLETE
    assert metadata["normalization_coverage_start"] == "2011-01-01"
    assert metadata["normalization_incomplete_reason"] == (
        "capital reduction official source coverage begins 2011-01-01")

    lines = _summary_lines(metadata, 0, adjusted=True)
    rendered = "\n".join(lines)
    assert "Official PE     2.45x" in rendered
    assert "Raw PE percentile 50.00%" in rendered
    assert "Normalized PE   Unavailable" in rendered
    assert "Norm percentile Incomplete" in rendered
    assert "Norm P10        Unavailable" in rendered
    assert "Norm P90        Unavailable" in rendered
    assert "Coverage:\n  AVAILABLE_HISTORY" in rendered
    assert "Normalization coverage:\n  2011-01-01 onward" in rendered
    assert "Normalization:\n  NORMALIZED_PERCENTILE_INCOMPLETE" in rendered


def test_cli_rejects_etf_before_fetch(tmp_path):
    class NoNetwork:
        def get(self, *args):
            raise AssertionError("must not fetch")
    assert run(["--symbol", "0050", "--cache-dir", str(tmp_path)], transport=NoNetwork()) == 1


@pytest.mark.parametrize(("action_type", "factor", "expected"), [
    (FACE_VALUE_CHANGE_SPLIT, 20, "Face Value Split\n20x"),
    (FACE_VALUE_CHANGE_REVERSE_SPLIT, .4, "Face Value Reverse Split\n0.4x"),
])
def test_face_value_pdf_marker_labels(action_type, factor, expected):
    action = CorporateActionEvent(
        symbol="6949", effective_date=date(2026, 9, 7), action_type=action_type,
        share_factor=factor, cash_return_per_share=None, pre_event_close=None,
        official_reference_price=None,
        source_url="https://mopsov.twse.com.tw/mops/web/ajax_t146sb10",
        detail_source_url="https://mopsov.twse.com.tw/mops/web/ajax_t59sb09",
        retrieved_at="2026-10-02T03:00:00Z", raw_hash="0" * 64,
        status=NORMALIZATION_READY,
    )
    assert _event_marker_label(action) == expected
