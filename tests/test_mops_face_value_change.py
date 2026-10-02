from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from twstock_data.errors import DataValidationError
from twstock_data.http import HttpResponse
from twstock_data.sources.mops_face_value_change import (
    FACE_VALUE_COVERAGE_INCOMPLETE,
    FACE_VALUE_COVERAGE_PROVEN,
    FACE_VALUE_REVIEW_REQUIRED,
    MOPS_DETAIL_URL,
    MOPS_FORM_URL,
    MOPS_QUERY_URL,
    MopsAnnouncementRow,
    _reconcile_face_value_events,
    fetch_face_value_change_history,
    parse_dispatch_form,
    parse_face_value_detail,
    parse_terminal_rowset,
)
from twstock_data.sources.twse_corporate_actions import (
    CORPORATE_ACTION_REVIEW_REQUIRED,
    FACE_VALUE_CHANGE_REVERSE_SPLIT,
    FACE_VALUE_CHANGE_SPLIT,
    NORMALIZATION_READY,
)

FIXTURES = Path(__file__).parent / "fixtures"
RETRIEVED = "2026-10-02T03:00:00+00:00"


def fixture(name):
    return (FIXTURES / name).read_bytes()


def row(symbol="6949", company="沛爾生醫*-創", announced=date(2026, 8, 6),
        date1="20260806", skey="1"):
    return MopsAnnouncementRow(
        symbol, company, announced, date1, skey,
        "公告本公司股票面額變更相關事宜")


def test_dispatch_form_parses_official_hidden_contract():
    result = parse_dispatch_form(fixture("mops_dispatch_6949.html"))
    assert result["step"] == "2"
    assert result["co_id_1"] == "6949"
    assert result["SDATE"] == "20260101"
    assert result["EDATE"] == "20261002"
    assert result["noticeKind"] == "11"
    assert result["rpt"] == "bool_t59sb09"


def test_terminal_rowset_uses_official_detail_identity():
    rows = parse_terminal_rowset(fixture("mops_rowset_6949.html"), "6949")
    assert rows == (row(),)


def test_terminal_no_result_is_valid_empty_set():
    assert parse_terminal_rowset(fixture("mops_no_result.html"), "6669") == ()


def test_unknown_pagination_fails_closed():
    body = fixture("mops_rowset_6949.html").replace(
        b"</body>", '<a id="nextPage">下一頁</a></body>'.encode())
    with pytest.raises(Exception, match="pagination"):
        parse_terminal_rowset(body, "6949")


def test_6949_positive_split_parser():
    event = parse_face_value_detail(
        fixture("mops_detail_6949_20260806.html"), row(),
        fixture("mops_rowset_6949.html"), RETRIEVED)
    assert event.action_type == FACE_VALUE_CHANGE_SPLIT
    assert event.status == NORMALIZATION_READY
    assert event.old_par_value == 10
    assert event.new_par_value == .5
    assert event.share_factor == 20
    assert event.effective_date == event.resume_date == date(2026, 9, 7)
    assert event.mops_date1 == "20260806"
    assert event.mops_skey == "1"
    assert event.derived is False


def test_2327_historical_positive_split_parser():
    event = parse_face_value_detail(
        fixture("mops_detail_2327_20250729.html"),
        row("2327", "國巨", date(2025, 7, 29), "20250729"),
        b"2327-rowset", RETRIEVED)
    assert event.action_type == FACE_VALUE_CHANGE_SPLIT
    assert event.old_par_value == 10
    assert event.new_par_value == 2.5
    assert event.share_factor == 4
    assert event.effective_date == date(2025, 8, 25)


def test_reverse_split_factor_direction_is_decimal_derived():
    detail = fixture("mops_detail_2327_20250729.html")
    detail = detail.replace("新台幣2.5元".encode(), "新台幣25元".encode())
    detail = detail.replace("每1股換發4股".encode(), "每1股換發0.4股".encode())
    event = parse_face_value_detail(
        detail, row("2327", "國巨", date(2025, 7, 29), "20250729"),
        b"rowset", RETRIEVED)
    assert event.action_type == FACE_VALUE_CHANGE_REVERSE_SPLIT
    assert event.share_factor == .4


def test_factor_mismatch_fails_closed():
    detail = fixture("mops_detail_6949_20260806.html").replace(
        "每1股換發20股".encode(), "每1股換發19股".encode())
    with pytest.raises(DataValidationError, match="conflicts"):
        parse_face_value_detail(
            detail, row(), fixture("mops_rowset_6949.html"), RETRIEVED)


def test_factor_one_face_value_notice_is_no_op():
    detail = fixture("mops_detail_6949_20260806.html")
    detail = detail.replace("新台幣0.5元".encode(), "新台幣10元".encode())
    detail = detail.replace("每1股換發20股".encode(), "每1股換發1股".encode())
    assert parse_face_value_detail(
        detail, row(), fixture("mops_rowset_6949.html"), RETRIEVED) is None


def test_unknown_face_value_notice_is_review_required():
    detail = fixture("mops_detail_6949_20260806.html")
    detail = detail.replace("原有股票面額新台幣10元變更為新台幣0.5元".encode(),
                            "股票面額之變更尚待確認".encode())
    event = parse_face_value_detail(
        detail, row(), fixture("mops_rowset_6949.html"), RETRIEVED)
    assert event.status == CORPORATE_ACTION_REVIEW_REQUIRED
    assert event.coverage_proof_status == FACE_VALUE_REVIEW_REQUIRED


def test_short_listing_notice_is_collapsed_only_when_full_notice_matches():
    full = parse_face_value_detail(
        fixture("mops_detail_6949_20260806.html"), row(),
        fixture("mops_rowset_6949.html"), RETRIEVED)
    followup = parse_face_value_detail(
        fixture("mops_detail_6949_20260826.html"),
        row(announced=date(2026, 8, 31), date1="20260826"),
        fixture("mops_rowset_6949.html"), RETRIEVED)
    assert followup.status == CORPORATE_ACTION_REVIEW_REQUIRED
    assert followup.effective_date == date(2026, 9, 7)
    assert followup.old_par_value == 10
    assert followup.new_par_value == .5
    assert _reconcile_face_value_events([followup]) == (followup,)
    assert _reconcile_face_value_events([full, followup]) == (full,)


def _dispatch(symbol, start, end):
    roc_start = start.year - 1911
    roc_end = end.year - 1911
    return f"""<form name='fm_show' action='/mops/web/ajax_t146sb10' method='post'>
    <input name='step' value='2'><input name='typek' value='all'>
    <input name='co_id_1' value='{symbol}'><input name='SDATE' value='{start:%Y%m%d}'>
    <input name='EDATE' value='{end:%Y%m%d}'><input name='YEAR1' value='{roc_start}'>
    <input name='YEAR2' value='{roc_end}'><input name='MONTH1' value='{start.month}'>
    <input name='MONTH2' value='{end.month}'><input name='SDAY' value='{start.day}'>
    <input name='EDAY' value='{end.day}'><input name='scope' value='1'>
    <input name='sort' value='1'><input name='rpt'><input name='firstin' value='1'>
    <input name='noticeKind' value='11'><input name='noticeDate' value='1'>
    <input name='date' value='4'></form>""".encode()


def _rowset(symbol, count, year=2026):
    rows = []
    roc_year = year - 1911
    for index in range(1, count + 1):
        rows.append(
            f"<tr><td>{symbol}</td><td>測試公司</td><td>{roc_year}/01/{index:02d}</td>"
            f"<td>一般發行公告 {index}</td><td><input value='詳細資料' "
            f"onclick='document.fm_t59sb09.co_id.value=\"{symbol}\";"
            f"document.fm_t59sb09.DATE1.value=\"{year}01{index:02d}\";"
            f"document.fm_t59sb09.SKEY.value=\"{index}\";'></td></tr>")
    return ("<table class='hasBorder'><tr><th>公司代號</th><th>公司簡稱</th>"
            "<th>公告日期</th><th>主　　旨</th><th></th></tr>" +
            "".join(rows) + "</table>").encode()


def _ordinary_detail(symbol, skey):
    return f"""<table class='hasBorder'>
    <tr><th>公司代號</th><td>{symbol}</td></tr>
    <tr><th>公告序號</th><td>{skey}</td></tr>
    <tr><th>主旨</th><td>一般發行公告</td></tr>
    <tr><th>公告內容</th><td>普通股每股面額10元，無面額變更。</td></tr>
    </table>""".encode()


class FixtureTransport:
    def __init__(self, symbol="6669", start=date(2019, 3, 27),
                 end=date(2026, 9, 1), count=18, detail_mutator=None,
                 malformed_form=False, pagination=False):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.count = count
        self.detail_mutator = detail_mutator
        self.malformed_form = malformed_form
        self.pagination = pagination
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(("GET", url))
        body = (b"<html>bad</html>" if self.malformed_form else
                b'<form action="/mops/web/ajax_t146sb10"></form>')
        return HttpResponse(url, 200, body)

    def post(self, url, data, timeout):
        params = {key: values[0] for key, values in parse_qs(
            data.decode(), keep_blank_values=True).items()}
        self.calls.append(("POST", url, params))
        if url == MOPS_QUERY_URL and params.get("step") == "1":
            body = _dispatch(self.symbol, self.start, self.end)
        elif url == MOPS_QUERY_URL:
            body = _rowset(self.symbol, self.count, self.end.year)
            if self.pagination:
                body += '<a id="nextPage">下一頁</a>'.encode()
        elif url == MOPS_DETAIL_URL:
            body = _ordinary_detail(self.symbol, params["SKEY"])
            if self.detail_mutator:
                body = self.detail_mutator(params, body)
        else:
            raise AssertionError(url)
        return HttpResponse(url, 200, body)


def test_6669_complete_negative_proof_has_18_details(tmp_path):
    result = fetch_face_value_change_history(
        "6669", date(2019, 3, 27), date(2026, 9, 1), tmp_path,
        transport=FixtureTransport(), request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert result.events == ()
    assert result.proof.status == FACE_VALUE_COVERAGE_PROVEN
    assert result.proof.result_count == result.proof.detail_count == 18
    assert result.proof.rowset_hash
    assert result.proof.detail_manifest_hash


def test_missing_detail_is_incomplete_not_assumed_empty(tmp_path):
    def fail_second(params, body):
        if params["SKEY"] == "2":
            raise TimeoutError("fixture timeout")
        return body
    result = fetch_face_value_change_history(
        "6669", date(2019, 3, 27), date(2026, 9, 1), tmp_path,
        transport=FixtureTransport(count=2, detail_mutator=fail_second),
        retries=0, request_interval=0, refresh_date=date(2026, 10, 2))
    assert result.proof.status == FACE_VALUE_COVERAGE_INCOMPLETE
    assert result.proof.detail_count == 1
    assert result.proof.result_count == 2


def test_detail_identity_mismatch_is_incomplete(tmp_path):
    def wrong_symbol(params, body):
        return body.replace(b">6669<", b">2330<")
    result = fetch_face_value_change_history(
        "6669", date(2019, 3, 27), date(2026, 9, 1), tmp_path,
        transport=FixtureTransport(count=1, detail_mutator=wrong_symbol),
        request_interval=0, refresh_date=date(2026, 10, 2))
    assert result.proof.status == FACE_VALUE_COVERAGE_INCOMPLETE


@pytest.mark.parametrize("transport", [
    FixtureTransport(malformed_form=True),
    FixtureTransport(pagination=True),
])
def test_unexpected_contract_is_incomplete(tmp_path, transport):
    result = fetch_face_value_change_history(
        "6669", date(2019, 3, 27), date(2026, 9, 1), tmp_path,
        transport=transport, request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert result.proof.status == FACE_VALUE_COVERAGE_INCOMPLETE


def test_historical_cache_reuses_validated_rowset_and_details(tmp_path):
    first_transport = FixtureTransport(
        symbol="2327", start=date(2025, 1, 1), end=date(2025, 12, 31), count=1)
    first = fetch_face_value_change_history(
        "2327", date(2025, 1, 1), date(2025, 12, 31), tmp_path,
        transport=first_transport, request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert first.proof.status == FACE_VALUE_COVERAGE_PROVEN

    class NoNetwork:
        def get(self, *args):
            raise AssertionError("unexpected network")
        def post(self, *args):
            raise AssertionError("unexpected network")

    cached = fetch_face_value_change_history(
        "2327", date(2025, 1, 1), date(2025, 12, 31), tmp_path,
        transport=NoNetwork(), request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert cached.proof.status == FACE_VALUE_COVERAGE_PROVEN
    assert {item["status"] for item in cached.request_results} == {"CACHE_HIT"}


def test_cache_hash_mismatch_fails_closed(tmp_path):
    transport = FixtureTransport(
        symbol="2327", start=date(2025, 1, 1), end=date(2025, 12, 31), count=1)
    first = fetch_face_value_change_history(
        "2327", date(2025, 1, 1), date(2025, 12, 31), tmp_path,
        transport=transport, request_interval=0, refresh_date=date(2026, 10, 2))
    assert first.proof.status == FACE_VALUE_COVERAGE_PROVEN
    raw = next((tmp_path / "corporate_actions" / "face_value" / "rowset").rglob("*.raw"))
    raw.write_bytes(raw.read_bytes() + b"tampered")
    result = fetch_face_value_change_history(
        "2327", date(2025, 1, 1), date(2025, 12, 31), tmp_path,
        transport=transport, request_interval=0, refresh_date=date(2026, 10, 2))
    assert result.proof.status == FACE_VALUE_COVERAGE_INCOMPLETE
    assert result.proof.failure_reason == "DataValidationError"
