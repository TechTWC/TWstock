from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from twstock_data.errors import DataValidationError, MalformedSourceError
from twstock_data.http import HttpResponse
from twstock_data.sources.twse_valuation import (
    NO_DATA, build_url, completed_session_cutoff, fetch_history,
    parse_close_payload, parse_valuation_payload, validate_symbol,
)

FIXTURES = Path(__file__).parent / "fixtures"
MONTH = date(2005, 9, 1)


def payload():
    return json.loads((FIXTURES / "twse_valuation_2330_200509.json").read_bytes())


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


def parse(value):
    return parse_valuation_payload(encode(value), "2330", "台積電", MONTH)


def test_official_historical_fixture():
    name, closes = parse_close_payload((FIXTURES / "twse_close_avg_2330_200509.json").read_bytes(), "2330", MONTH)
    pes = parse(payload())
    assert name == "台積電"
    assert closes[date(2005, 9, 2)] == 52.60
    assert pes[date(2005, 9, 2)] == 15.25
    assert len(pes) == len(closes) == 21


def test_current_schema_with_optional_financial_fields():
    body = (FIXTURES / "twse_valuation_2330_202609.json").read_bytes()
    values = parse_valuation_payload(body, "2330", "台積電", date(2026, 9, 1))
    assert values[date(2026, 9, 1)] == 28.28
    assert len(values) == 19


def test_unmatched_valuation_date_fails_closed(tmp_path):
    class Unmatched(FakeTransport):
        def get(self, url, timeout):
            r = super().get(url, timeout)
            if "/STOCK_DAY_AVG?" in url:
                p = json.loads(r.body)
                p["data"].pop(1)
                return HttpResponse(url, 200, encode(p))
            return r
    with pytest.raises(DataValidationError, match="no same-day"):
        fetch_history("2330", MONTH, date(2005, 9, 30), tmp_path,
                      transport=Unmatched(), request_interval=0)


@pytest.mark.parametrize("mode", ["wrong_name", "wrong_symbol", "missing_title"])
def test_identity_fails(mode):
    p = payload()
    if mode == "wrong_name":
        p["title"] = p["title"].replace("台積電", "聯電")
    elif mode == "wrong_symbol":
        p["stockNo"] = "2303"
    else:
        del p["title"]
    with pytest.raises((DataValidationError, MalformedSourceError)):
        parse(p)


def test_close_symbol_mismatch():
    body = (FIXTURES / "twse_close_avg_2330_200509.json").read_bytes()
    with pytest.raises(DataValidationError):
        parse_close_payload(body, "2303", MONTH)


@pytest.mark.parametrize("mode", ["duplicate", "unordered", "bad_calendar", "bad_format", "wrong_month",
                                  "bad_pe", "nonfinite", "bad_width", "empty_ok", "truncated", "bad_fields"])
def test_fail_closed(mode):
    p = payload()
    if mode == "duplicate":
        p["data"][1][0] = p["data"][0][0]
    elif mode == "unordered":
        p["data"][0], p["data"][1] = p["data"][1], p["data"][0]
    elif mode == "bad_calendar":
        p["data"][0][0] = "094年09月31日"
    elif mode == "bad_format":
        p["data"][0][0] = "yesterday"
    elif mode == "wrong_month":
        p["data"][0][0] = "094年08月31日"
    elif mode == "bad_pe":
        p["data"][0][1] = "20x"
    elif mode == "nonfinite":
        p["data"][0][1] = "NaN"
    elif mode == "bad_width":
        p["data"][0].pop()
    elif mode == "empty_ok":
        p["data"] = []
    elif mode == "truncated":
        p["total"] += 1
    else:
        p["fields"][1] = "unexpected"
    with pytest.raises((DataValidationError, MalformedSourceError)):
        parse(p)


@pytest.mark.parametrize("raw", ["-", "--", "", " ", "0", "-5", 0, -1])
def test_unavailable_pe(raw):
    p = payload()
    p["data"][0][1] = raw
    assert parse(p)[date(2005, 9, 2)] is None


@pytest.mark.parametrize("raw", [b"[]", b"not json", b'{"stat":"OK"}', b"\xff"])
def test_bad_json(raw):
    with pytest.raises(MalformedSourceError):
        parse_valuation_payload(raw, "2330", "台積電", MONTH)


@pytest.mark.parametrize("payload", [
    {"stat": NO_DATA},
    {"stat": NO_DATA, "total": 0},
    {"stat": NO_DATA, "total": 0, "data": []},
])
def test_official_no_data_schema_variants(payload):
    body = encode(payload)
    assert parse_close_payload(body, "6669", MONTH) == (None, {})
    assert parse_valuation_payload(body, "6669", None, MONTH) == {}


@pytest.mark.parametrize("payload", [
    {"stat": NO_DATA, "total": 1},
    {"stat": NO_DATA, "data": [["unexpected"]]},
    {"stat": NO_DATA, "fields": ["unexpected"]},
])
def test_contradictory_no_data_fails_closed(payload):
    with pytest.raises(MalformedSourceError, match="contradictory"):
        parse_close_payload(encode(payload), "6669", MONTH)


def test_invalid_close():
    p = json.loads((FIXTURES / "twse_close_avg_2330_200509.json").read_bytes())
    for raw in ("0", "-1", "1,23.45"):
        bad = deepcopy(p)
        bad["data"][0][1] = raw
        with pytest.raises((DataValidationError, MalformedSourceError)):
            parse_close_payload(encode(bad), "2330", MONTH)


@pytest.mark.parametrize("raw", ["--", "-", ""])
def test_official_unavailable_close_is_preserved_without_fabrication(raw):
    p = json.loads((FIXTURES / "twse_close_avg_2330_200509.json").read_bytes())
    p["data"][0][1] = raw
    _, closes = parse_close_payload(encode(p), "2330", MONTH)
    assert date(2005, 9, 2) in closes
    assert closes[date(2005, 9, 2)] is None


@pytest.mark.parametrize("symbol", ["0050", "2330.TW", "123456", "../2330", "abcd"])
def test_symbol_scope(symbol):
    with pytest.raises(DataValidationError):
        validate_symbol(symbol)


class FakeTransport:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def get(self, url, timeout):
        self.calls.append(url)
        if self.fail and "20051001" in url:
            raise OSError("fixture interruption")
        if "20050901" not in url:
            body = encode({"stat": NO_DATA, "total": 0})
        else:
            name = "twse_valuation_2330_200509.json" if "/BWIBBU?" in url else "twse_close_avg_2330_200509.json"
            body = (FIXTURES / name).read_bytes()
        return HttpResponse(url, 200, body)


def test_cache_resume_and_refresh(tmp_path):
    first = FakeTransport(fail=True)
    kwargs = dict(symbol="2330", start=MONTH, end=date(2005, 10, 31), cache_dir=tmp_path,
                  refresh_date=date(2006, 1, 5), retries=0, request_interval=0)
    with pytest.raises(Exception, match="fixture interruption"):
        fetch_history(transport=first, **kwargs)
    assert json.loads((tmp_path / "twse_cache_run.json").read_text())["completed"] is False
    second = FakeTransport()
    history = fetch_history(transport=second, **kwargs)
    assert len(history.observations) == 21
    assert history.month_results[0]["pe_status"] == "CACHE_HIT"
    assert not any("20050901" in url for url in second.calls)
    third = FakeTransport()
    fetch_history(transport=third, **kwargs)
    # Latest requested period is deliberately refreshed even if historical.
    assert len(third.calls) == 2
    assert all("20051001" in url for url in third.calls)


def test_cache_integrity_fails_closed(tmp_path):
    kwargs = dict(symbol="2330", start=MONTH, end=date(2005, 10, 31), cache_dir=tmp_path,
                  refresh_date=date(2006, 1, 5), retries=0, request_interval=0)
    fetch_history(transport=FakeTransport(), **kwargs)
    path = next((tmp_path / "BWIBBU" / ".monthly").glob("*20050901.raw"))
    path.write_bytes(b"tampered")
    with pytest.raises(DataValidationError, match="SHA-256"):
        fetch_history(transport=FakeTransport(), **kwargs)


def test_missing_pe_date_preserved(tmp_path):
    class Missing(FakeTransport):
        def get(self, url, timeout):
            r = super().get(url, timeout)
            if "/BWIBBU?" in url:
                p = json.loads(r.body)
                p["data"].pop(1)
                p["total"] -= 1
                return HttpResponse(url, 200, encode(p))
            return r
    result = fetch_history("2330", MONTH, date(2005, 9, 30), tmp_path,
                           transport=Missing(), request_interval=0)
    assert len(result.observations) == 21
    assert result.observations[1].official_pe is None
    assert result.incomplete_months == ("2005-09",)


def test_unavailable_close_date_is_skipped_without_losing_other_rows(tmp_path):
    class UnavailableClose(FakeTransport):
        def get(self, url, timeout):
            r = super().get(url, timeout)
            if "/STOCK_DAY_AVG?" in url:
                p = json.loads(r.body)
                p["data"][0][1] = "--"
                return HttpResponse(url, 200, encode(p))
            return r
    result = fetch_history("2330", MONTH, date(2005, 9, 30), tmp_path,
                           transport=UnavailableClose(), request_interval=0)
    assert len(result.observations) == 20
    assert all(row.trade_date != date(2005, 9, 2) for row in result.observations)
    month = result.month_results[0]
    assert month["source_close_row_count"] == 21
    assert month["close_count"] == 20
    assert month["unavailable_close_dates"] == ["2005-09-02"]
    assert month["missing_pe_dates"] == []


def test_completed_session_excludes_intraday():
    tz = ZoneInfo("Asia/Taipei")
    assert completed_session_cutoff(datetime(2026, 9, 30, 12, 57, tzinfo=tz)) == date(2026, 9, 29)
    assert completed_session_cutoff(datetime(2026, 9, 30, 15, 0, tzinfo=tz)) == date(2026, 9, 30)


def test_url_contract():
    assert build_url("BWIBBU", "2330", MONTH).endswith("response=json&date=20050901&stockNo=2330")
