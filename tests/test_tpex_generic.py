from datetime import date
import json
from pathlib import Path

import pytest

from twstock_data.errors import DataValidationError, MalformedSourceError
from twstock_data.http import HttpResponse
from twstock_data.sources.security_identity import (
    AUTO, ORDINARY_COMMON_SHARE, TPEX, TWSE,
    parse_security_master, resolve_security_identity,
)
from twstock_data.sources.tpex_corporate_actions import parse_events
from twstock_data.sources.tpex_valuation import (
    fetch_history, parse_close_payload, parse_valuation_payload_with_period,
)
from twstock_data.sources.twse_corporate_actions import (
    CAPITAL_REDUCTION_CASH_RETURN, CAPITAL_REDUCTION_LOSS,
    CORPORATE_ACTION_REVIEW_REQUIRED, FACE_VALUE_CHANGE_SPLIT,
    NORMALIZATION_READY, STOCK_DIVIDEND,
)

FIXTURES = Path(__file__).parent / "fixtures"
MONTH = date(2026, 9, 1)


def fixture(name):
    return (FIXTURES / name).read_bytes()


@pytest.mark.parametrize(("symbol", "name", "valid", "unavailable"), [
    ("6488", "環球晶", 2, 1),
    ("6548", "長科*", 2, 0),
    ("8069", "元太", 1, 0),
])
def test_multiple_tpex_symbols_use_same_field_driven_valuation_path(
        symbol, name, valid, unavailable):
    closes_name, closes = parse_close_payload(
        fixture(f"tpex_close_{symbol}_202609.json"), symbol, MONTH, name)
    pes = parse_valuation_payload_with_period(
        fixture(f"tpex_pe_{symbol}_202609.json"), symbol, MONTH, name)
    assert closes_name == name
    assert len([point for point in pes.values() if point.official_pe is not None]) == valid
    assert len([point for point in pes.values() if point.official_pe is None]) == unavailable
    assert set(pes) <= set(closes)


def test_tpex_unavailable_pe_and_missing_pe_date_are_distinct(tmp_path):
    class Transport:
        def get(self, url, timeout):
            name = "tpex_pe_6488_202609.json" if "peQryStock" in url else "tpex_close_6488_202609.json"
            return HttpResponse(url, 200, fixture(name))

    result = fetch_history(
        "6488", MONTH, date(2026, 9, 30), tmp_path,
        company_name="環球晶", transport=Transport(), request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert [row.official_pe for row in result.observations] == [18.2, None, 18.66]
    assert result.observations[0].canonical_symbol == "6488.TWO"
    assert result.observations[0].market == TPEX
    assert result.month_results[0]["missing_pe_dates"] == []
    assert result.source_start == date(2026, 9, 1)


@pytest.mark.parametrize("mutation", ["wrong_code", "wrong_month", "truncated", "schema"])
def test_tpex_valuation_schema_and_identity_drift_fail_closed(mutation):
    payload = json.loads(fixture("tpex_pe_6488_202609.json"))
    if mutation == "wrong_code":
        payload["code"] = "8069"
    elif mutation == "wrong_month":
        payload["date"] = "20260801"
    elif mutation == "truncated":
        payload["tables"][0]["totalCount"] += 1
    else:
        payload["tables"][0]["fields"][1] = "估值"
    with pytest.raises((DataValidationError, MalformedSourceError)):
        parse_valuation_payload_with_period(
            json.dumps(payload, ensure_ascii=False).encode(), "6488", MONTH, "環球晶")


def test_official_tpex_security_master_classifies_multiple_ordinary_shares():
    identities = parse_security_master(fixture("tpex_security_master_multi.json"), TPEX)
    assert {item.symbol for item in identities} == {"6488", "6548", "8069"}
    assert {item.canonical_symbol for item in identities} == {
        "6488.TWO", "6548.TWO", "8069.TWO"}
    assert all(item.security_type == ORDINARY_COMMON_SHARE for item in identities)
    assert len({item.listing_date for item in identities}) == 3


def test_auto_routing_requires_positive_unambiguous_official_identity():
    twse = json.dumps([{
        "公司代號": "2330", "公司名稱": "台灣積體電路製造股份有限公司",
        "公司簡稱": "台積電", "出表日期": "1151002", "上市日期": "19940905",
        "普通股每股面額": "新台幣10元", "特別股": "0",
    }], ensure_ascii=False).encode()

    class Transport:
        def get(self, url, timeout):
            body = twse if "t187ap03_L" in url else fixture("tpex_security_master_multi.json")
            return HttpResponse(url, 200, body)

    identity = resolve_security_identity("6488", AUTO, transport=Transport())
    assert identity.market == TPEX
    assert identity.company_short_name == "環球晶"
    with pytest.raises(DataValidationError, match="not an officially identified TWSE"):
        resolve_security_identity("6488", TWSE, transport=Transport())


def test_tpex_corporate_actions_map_generic_families_fail_closed():
    payload = json.loads(fixture("tpex_corporate_actions_multi.json"))
    source = "https://www.tpex.org.tw/www/zh-tw/bulletin/example"
    start, end = date(2026, 9, 1), date(2026, 9, 30)
    ex = parse_events(
        json.dumps(payload["exRight"], ensure_ascii=False).encode(),
        "ex_right", "8069", start, end, source, "2026-10-03T00:00:00Z", "元太")
    assert len(ex) == 1
    assert ex[0].action_type == STOCK_DIVIDEND
    assert ex[0].share_factor == pytest.approx(150 / 135)
    assert ex[0].status == CORPORATE_ACTION_REVIEW_REQUIRED

    reductions = parse_events(
        json.dumps(payload["capitalReduction"], ensure_ascii=False).encode(),
        "capital_reduction", "6548", start, end, source,
        "2026-10-03T00:00:00Z", "長科*")
    assert reductions[0].action_type == CAPITAL_REDUCTION_LOSS
    assert reductions[0].share_factor == pytest.approx(.8)
    assert reductions[0].status == NORMALIZATION_READY

    cash = parse_events(
        json.dumps(payload["capitalReduction"], ensure_ascii=False).encode(),
        "capital_reduction", "6488", start, end, source,
        "2026-10-03T00:00:00Z", "環球晶")
    assert cash[0].action_type == CAPITAL_REDUCTION_CASH_RETURN
    assert cash[0].status == CORPORATE_ACTION_REVIEW_REQUIRED
    assert cash[0].share_factor is None

    face = parse_events(
        json.dumps(payload["parValueChange"], ensure_ascii=False).encode(),
        "par_value_change", "6548", start, end, source,
        "2026-10-03T00:00:00Z", "長科*")
    assert face[0].action_type == FACE_VALUE_CHANGE_SPLIT
    assert face[0].share_factor == 10
    assert face[0].status == NORMALIZATION_READY


def test_verified_empty_tpex_action_interval_is_not_network_empty():
    payload = {
        "date": "20260901~20260930", "stat": "ok",
        "tables": [{
            "totalCount": 0,
            "fields": ["除權息日期", "代號", "名稱", "除權息前收盤價",
                       "除權息參考價", "權/息", "現金股利"],
            "data": [],
        }],
    }
    assert parse_events(
        json.dumps(payload, ensure_ascii=False).encode(), "ex_right", "6488",
        date(2026, 9, 1), date(2026, 9, 30),
        "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ",
        "2026-10-03T00:00:00Z", "環球晶") == ()
    payload["date"] = "20260901~20260929"
    with pytest.raises(DataValidationError, match="interval"):
        parse_events(
            json.dumps(payload, ensure_ascii=False).encode(), "ex_right", "6488",
            date(2026, 9, 1), date(2026, 9, 30),
            "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ",
            "2026-10-03T00:00:00Z", "環球晶")
