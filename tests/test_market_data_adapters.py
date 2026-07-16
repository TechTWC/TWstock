from __future__ import annotations
import csv, json, os
from pathlib import Path
import pytest
from twstock_data.cli import main as cli_main
from twstock_data.http import HttpResponse
from twstock_data.normalization import canonical_symbol, source_symbol_from_input
from twstock_data.sources.twse import parse_twse_payload, fetch_twse_daily, TWSE_STOCK_DAY_ENDPOINT
from twstock_data.sources.finmind import parse_finmind_payload, fetch_finmind_daily, FINMIND_DAILY_ENDPOINT
from twstock_data.reconciliation import reconcile_market_data
from twstock_data.models import SourceState, SourceTier
from twstock_data.errors import MalformedSourceError, DataValidationError, DuplicateTradeDateError, SourceUnavailableError

FIXTURES = Path(__file__).parent / "fixtures"
TWSE = json.loads((FIXTURES / "twse_stock_day_2330_202607.json").read_text(encoding="utf-8"))
FIN = json.loads((FIXTURES / "finmind_2330_202607.json").read_text(encoding="utf-8"))
TWSE_JUNE = {**TWSE, "data": [["115/06/30", "10,000", "9,900,000", "98.00", "100.00", "97.00", "99.00", "0.00", "777"]]}
TWSE_JULY = TWSE
FIN_TWO = {"data": [
    {"date":"2026-06-30","stock_id":"2330","Trading_Volume":10000,"Trading_money":9900000,"open":98,"max":100,"min":97,"close":99,"Trading_turnover":777},
    FIN["data"][0],
]}

def test_canonical_mapping_generalizes_twse_codes_and_rejects_bad_inputs():
    assert canonical_symbol("2330") == "2330.TW"
    assert canonical_symbol("2317") == "2317.TW"
    assert canonical_symbol("2454") == "2454.TW"
    assert source_symbol_from_input("2330.TW") == "2330"
    for bad in ("", "2330.tw", "2330.TWO", "23A0", " 2330"):
        with pytest.raises(DataValidationError):
            source_symbol_from_input(bad)
    with pytest.raises(DataValidationError):
        canonical_symbol("2330", "TPEX")

def test_twse_success_comma_numbers_canonical_metadata_and_no_value_synthesis():
    r = parse_twse_payload(TWSE, "2330", "2026-07-01", "2026-07-31", b"raw", TWSE_STOCK_DAY_ENDPOINT, "2026-07-16T00:00:00+00:00")[0]
    assert r.source == "TWSE" and r.source_tier is SourceTier.PRIMARY
    assert r.canonical_symbol == "2330.TW"
    assert r.traded_share_volume == 20000
    assert r.official_traded_value_twd == 30000000
    assert r.official_traded_value_twd != int(r.close_price * r.traded_share_volume)
    assert r.raw_content_hash and r.source_reference == TWSE_STOCK_DAY_ENDPOINT

def test_twse_response_identity_mismatch_rejected():
    bad = json.loads(json.dumps(TWSE))
    bad["title"] = "115年07月 2317 鴻海 各日成交資訊"
    with pytest.raises(DataValidationError):
        parse_twse_payload(bad, "2330", "2026-07-01", "2026-07-31")

def test_finmind_rejects_inconsistent_canonical_symbol():
    with pytest.raises(DataValidationError):
        parse_finmind_payload(FIN, "2330", "2317.TW", "2026-07-01", "2026-07-31")

def test_twse_malformed_renamed_field_fails():
    bad = dict(TWSE); bad["fields"] = ["日期", "成交股數"]
    with pytest.raises(MalformedSourceError): parse_twse_payload(bad, "2330", "2026-07-01", "2026-07-31")

@pytest.mark.parametrize("value", ["", "0"])
def test_twse_blank_and_zero_transaction_value_fails(value):
    bad = json.loads(json.dumps(TWSE)); bad["data"][0][2] = value
    with pytest.raises(DataValidationError): parse_twse_payload(bad, "2330", "2026-07-01", "2026-07-31")

def test_twse_duplicate_dates_and_bad_range_fail():
    dup = json.loads(json.dumps(TWSE)); dup["data"].append(dup["data"][0])
    with pytest.raises(DuplicateTradeDateError): parse_twse_payload(dup, "2330", "2026-07-01", "2026-07-31")
    with pytest.raises(DataValidationError): fetch_twse_daily("2330", "2026-07-31", "2026-07-01")

class MonthlyTransport:
    def __init__(self): self.urls=[]
    def get(self, url, timeout):
        self.urls.append(url)
        if "date=20260601" in url: return HttpResponse(url, 200, json.dumps(TWSE_JUNE, ensure_ascii=False).encode())
        if "date=20260701" in url: return HttpResponse(url, 200, json.dumps(TWSE_JULY, ensure_ascii=False).encode())
        raise AssertionError(url)

def test_twse_fetches_every_month_inclusive_range():
    transport = MonthlyTransport()
    records = fetch_twse_daily("2330", "2026-06-01", "2026-07-15", transport)
    assert [r.trade_date for r in records] == ["2026-06-30", "2026-07-15"]
    assert len(transport.urls) == 2
    assert "date=20260601" in transport.urls[0]
    assert "date=20260701" in transport.urls[1]

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

def test_finmind_http_failure_redacts_token(monkeypatch):
    token = "KNOWN_FAKE_TOKEN_123"
    monkeypatch.setenv("FINMIND_TOKEN", token)
    class FailingTransport:
        def get(self, url, timeout):
            raise SourceUnavailableError(f"failed {url}")
    result = fetch_finmind_daily("2330", "2330.TW", "2026-07-01", "2026-07-31", FailingTransport(), retries=0)
    assert result.state is SourceState.SOURCE_UNAVAILABLE
    assert token not in (result.error or "")
    assert "<redacted>" in (result.error or "")

def test_finmind_parsing_secondary_tagging_and_symbol_check():
    r = parse_finmind_payload(FIN, "2330", "2330.TW", "2026-07-01", "2026-07-31", b"raw", FINMIND_DAILY_ENDPOINT)[0]
    assert r.source == "FinMind" and r.source_tier is SourceTier.SECONDARY
    bad = json.loads(json.dumps(FIN)); bad["data"][0]["stock_id"] = "2317"
    with pytest.raises(MalformedSourceError): parse_finmind_payload(bad, "2330", "2330.TW", "2026-07-01", "2026-07-31")

def test_reconciliation_matching_mismatches_and_exact_date_alignment():
    p = parse_twse_payload(TWSE, "2330", "2026-07-01", "2026-07-31")
    s = parse_finmind_payload(FIN, "2330", "2330.TW", "2026-07-01", "2026-07-31")
    assert reconcile_market_data(p, s).state is SourceState.PRIMARY_VERIFIED
    vol = json.loads(json.dumps(FIN)); vol["data"][0]["Trading_Volume"] = 1
    result = reconcile_market_data(p, parse_finmind_payload(vol, "2330", "2330.TW", "2026-07-01", "2026-07-31"))
    assert result.state is SourceState.SOURCE_MISMATCH and result.issues[0].field == "traded_share_volume"
    primary_two = parse_twse_payload(TWSE_JUNE, "2330", "2026-06-01", "2026-06-30") + p
    missing_secondary = reconcile_market_data(primary_two, s)
    assert missing_secondary.state is SourceState.SOURCE_MISMATCH
    assert any(i.field == "trade_date_only_in_twse" for i in missing_secondary.issues)
    secondary_two = parse_finmind_payload(FIN_TWO, "2330", "2330.TW", "2026-06-01", "2026-07-31")
    extra_secondary = reconcile_market_data(p, secondary_two)
    assert extra_secondary.state is SourceState.SOURCE_MISMATCH
    assert any(i.field == "trade_date_only_in_finmind" for i in extra_secondary.issues)
    assert reconcile_market_data((), s).state is SourceState.SECONDARY_ONLY

class CliTransport:
    def __init__(self, fail_twse=False): self.urls=[]; self.fail_twse=fail_twse
    def get(self, url, timeout):
        self.urls.append(url)
        if "twse.com.tw" in url:
            if self.fail_twse: raise SourceUnavailableError(f"blocked {url}")
            if "date=20260601" in url: return HttpResponse(url, 200, json.dumps(TWSE_JUNE, ensure_ascii=False).encode())
            return HttpResponse(url, 200, json.dumps(TWSE_JULY, ensure_ascii=False).encode())
        return HttpResponse(url, 200, json.dumps(FIN_TWO).encode())

def test_cli_multi_month_raw_cache_manifest_and_csv(monkeypatch, tmp_path):
    import twstock_data.sources.twse as twse_mod, twstock_data.sources.finmind as fin_mod
    transport = CliTransport()
    monkeypatch.setattr(twse_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setattr(fin_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setenv("FINMIND_TOKEN", "SECRET_TOKEN")
    out, raw = tmp_path / "out", tmp_path / "raw"
    assert cli_main(["fetch-market", "--symbol", "2330", "--start", "2026-06-01", "--end", "2026-07-15", "--output-dir", str(out), "--raw-cache-dir", str(raw)]) == 0
    rows = list(csv.DictReader((out / "twse_normalized.csv").open(encoding="utf-8")))
    assert [row["trade_date"] for row in rows] == ["2026-06-30", "2026-07-15"]
    assert {row["source_tier"] for row in rows} == {"PRIMARY"}
    fin_rows = list(csv.DictReader((out / "finmind_normalized.csv").open(encoding="utf-8")))
    assert {row["source_tier"] for row in fin_rows} == {"SECONDARY"}
    manifest = json.loads((out / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["twse_state"] == "PRIMARY_VERIFIED"
    assert manifest["finmind_state"] == "SECONDARY_ONLY"
    assert manifest["reconciliation_state"] == "PRIMARY_VERIFIED"
    assert manifest["cross_check_unavailable"] is False
    assert manifest["finmind_secondary_available"] is True
    assert "SECRET_TOKEN" not in (out / "source_manifest.json").read_text(encoding="utf-8")
    metadata = [json.loads(path.read_text(encoding="utf-8")) for path in raw.glob("*.metadata.json")]
    assert len(metadata) == 3
    raw_hashes = {m["sha256"] for m in metadata}
    assert {row["raw_content_hash"] for row in rows}.issubset(raw_hashes)
    for m in metadata:
        assert "SECRET_TOKEN" not in m["sanitized_source_url"]
        assert (raw / m["raw_file"]).read_bytes()

def test_cli_writes_manifest_after_twse_failure_and_redacts(monkeypatch, tmp_path):
    import twstock_data.sources.twse as twse_mod, twstock_data.sources.finmind as fin_mod
    token = "SECRET_TOKEN"
    transport = CliTransport(fail_twse=True)
    monkeypatch.setattr(twse_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setattr(fin_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setenv("FINMIND_TOKEN", token)
    out = tmp_path / "out"
    assert cli_main(["fetch-market", "--symbol", "2330", "--start", "2026-06-01", "--end", "2026-07-15", "--output-dir", str(out)]) == 0
    manifest_text = (out / "source_manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["twse_state"] == "SOURCE_UNAVAILABLE"
    assert manifest["finmind_secondary_available"] is True
    assert manifest["finmind_state"] == "SECONDARY_ONLY"
    assert manifest["reconciliation_state"] == "SECONDARY_ONLY"
    assert manifest["cross_check_unavailable"] is False
    assert token not in manifest_text
    assert json.loads((out / "reconciliation.json").read_text(encoding="utf-8"))["state"] == "SECONDARY_ONLY"

class IdenticalMonthlyTransport:
    def __init__(self): self.urls=[]
    def get(self, url, timeout):
        self.urls.append(url)
        return HttpResponse(url, 200, json.dumps(TWSE, ensure_ascii=False).encode())

def test_raw_cache_unique_files_for_identical_twse_monthly_bytes(tmp_path):
    transport = IdenticalMonthlyTransport()
    records = fetch_twse_daily("2330", "2026-06-01", "2026-07-31", transport, raw_cache_dir=tmp_path)
    raw_files = sorted(tmp_path.glob("*.raw"))
    metadata_files = sorted(tmp_path.glob("*.metadata.json"))
    assert len(raw_files) == 2
    assert len(metadata_files) == 2
    metadata = [json.loads(path.read_text(encoding="utf-8")) for path in metadata_files]
    assert len({m["sanitized_source_url"] for m in metadata}) == 2
    assert all((tmp_path / m["raw_file"]).exists() for m in metadata)
    hashes = {m["sha256"] for m in metadata}
    assert {record.raw_content_hash for record in records}.issubset(hashes)

def test_cli_manifest_states_twse_success_finmind_mismatch(monkeypatch, tmp_path):
    import twstock_data.sources.twse as twse_mod, twstock_data.sources.finmind as fin_mod
    class MismatchTransport(CliTransport):
        def get(self, url, timeout):
            if "twse.com.tw" in url:
                return HttpResponse(url, 200, json.dumps(TWSE_JULY, ensure_ascii=False).encode())
            bad = json.loads(json.dumps(FIN)); bad["data"][0]["Trading_Volume"] = 1
            return HttpResponse(url, 200, json.dumps(bad).encode())
    transport = MismatchTransport()
    monkeypatch.setattr(twse_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setattr(fin_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.setenv("FINMIND_TOKEN", "SECRET_TOKEN")
    out = tmp_path / "out"
    assert cli_main(["fetch-market", "--symbol", "2330", "--start", "2026-07-01", "--end", "2026-07-31", "--output-dir", str(out)]) == 0
    manifest = json.loads((out / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["twse_state"] == "PRIMARY_VERIFIED"
    assert manifest["finmind_state"] == "SECONDARY_ONLY"
    assert manifest["reconciliation_state"] == "SOURCE_MISMATCH"

def test_cli_manifest_states_twse_success_finmind_unavailable(monkeypatch, tmp_path):
    import twstock_data.sources.twse as twse_mod
    transport = CliTransport()
    monkeypatch.setattr(twse_mod, "get_with_retry", lambda url, transport_arg, timeout, retries: transport.get(url, timeout))
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    out = tmp_path / "out"
    assert cli_main(["fetch-market", "--symbol", "2330", "--start", "2026-07-01", "--end", "2026-07-31", "--output-dir", str(out)]) == 0
    manifest = json.loads((out / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["twse_state"] == "PRIMARY_VERIFIED"
    assert manifest["finmind_state"] == "SOURCE_UNAVAILABLE"
    assert manifest["reconciliation_state"] == "PRIMARY_VERIFIED"
    assert manifest["cross_check_unavailable"] is True

def test_http_redacts_token_from_underlying_transport_exception():
    from twstock_data.http import get_with_retry
    token = "FAKE_HTTP_TOKEN"
    class TokenFailTransport:
        def get(self, url, timeout):
            raise OSError(f"blocked https://api.finmindtrade.com/api/v4/data?token={token}&data_id=2330")
    with pytest.raises(SourceUnavailableError) as exc:
        get_with_retry(f"https://api.finmindtrade.com/api/v4/data?token={token}&data_id=2330", TokenFailTransport(), retries=0)
    assert token not in str(exc.value)
    assert "<redacted>" in str(exc.value)
