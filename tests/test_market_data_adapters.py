from __future__ import annotations
import json, os
import pytest
from twstock_data.http import HttpResponse
from twstock_data.sources.twse import parse_twse_payload, fetch_twse_daily, TWSE_STOCK_DAY_ENDPOINT
from twstock_data.sources.finmind import parse_finmind_payload, fetch_finmind_daily, FINMIND_DAILY_ENDPOINT
from twstock_data.reconciliation import reconcile_market_data
from twstock_data.models import SourceState, SourceTier
from twstock_data.errors import MalformedSourceError, DataValidationError, DuplicateTradeDateError, SourceUnavailableError

from pathlib import Path
FIXTURES = Path(__file__).parent / "fixtures"
TWSE = json.loads((FIXTURES / "twse_stock_day_2330_202607.json").read_text(encoding="utf-8"))
FIN = json.loads((FIXTURES / "finmind_2330_202607.json").read_text(encoding="utf-8"))

def test_twse_success_comma_numbers_canonical_metadata_and_no_value_synthesis():
    r = parse_twse_payload(TWSE, "2330", "2026-07-01", "2026-07-31", b"raw", TWSE_STOCK_DAY_ENDPOINT, "2026-07-16T00:00:00+00:00")[0]
    assert r.source == "TWSE" and r.source_tier is SourceTier.PRIMARY
    assert r.canonical_symbol == "2330.TW"
    assert r.traded_share_volume == 20000
    assert r.official_traded_value_twd == 30000000
    assert r.official_traded_value_twd != int(r.close_price * r.traded_share_volume)
    assert r.raw_content_hash and r.source_reference == TWSE_STOCK_DAY_ENDPOINT

def test_twse_malformed_renamed_field_fails():
    bad = dict(TWSE); bad["fields"] = ["日期", "成交股數"]
    with pytest.raises(MalformedSourceError): parse_twse_payload(bad, "2330", "2026-07-01", "2026-07-31")

@pytest.mark.parametrize("value", ["", "0"])
def test_twse_blank_and_zero_transaction_value_fails(value):
    bad = json.loads(json.dumps(TWSE)); bad["data"][0][2] = value
    with pytest.raises(DataValidationError): parse_twse_payload(bad, "2330", "2026-07-01", "2026-07-31")

def test_twse_duplicate_dates_and_wrong_symbol_mapping_fail():
    dup = json.loads(json.dumps(TWSE)); dup["data"].append(dup["data"][0])
    with pytest.raises(DuplicateTradeDateError): parse_twse_payload(dup, "2330", "2026-07-01", "2026-07-31")
    with pytest.raises(DataValidationError): parse_twse_payload(TWSE, "9999", "2026-07-01", "2026-07-31")

class FlakyTransport:
    def __init__(self): self.calls = 0
    def get(self, url, timeout):
        self.calls += 1
        if self.calls < 3: raise TimeoutError("boom")
        return HttpResponse(url, 200, json.dumps(TWSE).encode())

def test_bounded_retry_timeout_behavior():
    t = FlakyTransport(); records = fetch_twse_daily("2330", "2026-07-01", "2026-07-31", t, retries=2)
    assert len(records) == 1 and t.calls == 3
    with pytest.raises(SourceUnavailableError): fetch_twse_daily("2330", "2026-07-01", "2026-07-31", FlakyTransport(), retries=1)

def test_finmind_token_absent(monkeypatch):
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    result = fetch_finmind_daily("2330", "2330.TW", "2026-07-01", "2026-07-31")
    assert result.state is SourceState.SOURCE_UNAVAILABLE

def test_finmind_parsing_secondary_tagging_and_symbol_check():
    r = parse_finmind_payload(FIN, "2330", "2330.TW", "2026-07-01", "2026-07-31", b"raw", FINMIND_DAILY_ENDPOINT)[0]
    assert r.source == "FinMind" and r.source_tier is SourceTier.SECONDARY
    bad = json.loads(json.dumps(FIN)); bad["data"][0]["stock_id"] = "2317"
    with pytest.raises(MalformedSourceError): parse_finmind_payload(bad, "2330", "2330.TW", "2026-07-01", "2026-07-31")

def test_reconciliation_matching_and_mismatches_and_secondary_only():
    p = parse_twse_payload(TWSE, "2330", "2026-07-01", "2026-07-31")
    s = parse_finmind_payload(FIN, "2330", "2330.TW", "2026-07-01", "2026-07-31")
    assert reconcile_market_data(p, s).state is SourceState.PRIMARY_VERIFIED
    vol = json.loads(json.dumps(FIN)); vol["data"][0]["Trading_Volume"] = 1
    result = reconcile_market_data(p, parse_finmind_payload(vol, "2330", "2330.TW", "2026-07-01", "2026-07-31"))
    assert result.state is SourceState.SOURCE_MISMATCH and result.issues[0].field == "traded_share_volume"
    money = json.loads(json.dumps(FIN)); money["data"][0]["Trading_money"] = 1
    result = reconcile_market_data(p, parse_finmind_payload(money, "2330", "2330.TW", "2026-07-01", "2026-07-31"))
    assert any(i.field == "official_traded_value_twd" for i in result.issues)
    assert reconcile_market_data((), s).state is SourceState.SECONDARY_ONLY
