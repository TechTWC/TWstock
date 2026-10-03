from datetime import date
import json
from pathlib import Path

import pytest

from twstock_data.errors import MalformedSourceError
from twstock_data.http import HttpResponse
from twstock_data.sources.security_identity import TPEX, parse_security_master
from twstock_data.sources.tpex_universe import (
    AVAILABLE, FAILURE, LEGITIMATE_UNAVAILABLE_PROVEN, UNRESOLVED,
    LATEST_CLOSE_URL, LATEST_PE_URL, _index_latest, _rows,
    audit_current_tpex_universe, resolve_missing_tpex_observation,
)


FIXTURES = Path(__file__).parent / "fixtures"
MASTER = (FIXTURES / "tpex_security_master_multi.json").read_bytes()


def _snapshot(value_key, values):
    return json.dumps([{
        "Date": "1151002",
        "SecuritiesCompanyCode": symbol,
        "CompanyName": name,
        value_key: value,
    } for symbol, name, value in values], ensure_ascii=False).encode()


class SnapshotTransport:
    def __init__(self, close, pe):
        self.close = close
        self.pe = pe

    def get(self, url, timeout):
        if "mopsfin_t187ap03_O" in url:
            body = MASTER
        elif url == LATEST_CLOSE_URL:
            body = self.close
        elif url == LATEST_PE_URL:
            body = self.pe
        else:
            raise AssertionError(url)
        return HttpResponse(url, 200, body)


def _complete_snapshots():
    close = _snapshot("Close", [
        ("6488", "��球晶", "400"),
        ("6548", "長科*", "77"),
        ("8069", "元太", "153"),
    ])
    pe = _snapshot("PriceEarningRatio", [
        ("6488", "環球晶", "18.2"),
        ("6548", "長科*", "-"),
        ("8069", "元太", "14.25"),
    ])
    return close, pe


def test_complete_rows_are_classified_with_explicit_evidence():
    close, pe = _complete_snapshots()
    result = audit_current_tpex_universe(
        transport=SnapshotTransport(close, pe), retries=0)
    assert result["schema_version"] == "TWSTOCK-TPEX-UNIVERSE-AUDIT-002"
    assert result["universe_size"] == result["identity_pass_count"] == 3
    assert result["identity_failure_count"] == 0
    assert result["latest_close_available_count"] == 3
    assert result["latest_close_legitimate_unavailable_proven_count"] == 0
    assert result["latest_close_unresolved_count"] == 0
    assert result["latest_close_failure_count"] == 0
    assert result["latest_pe_available_count"] == 2
    assert result["latest_pe_legitimate_unavailable_proven_count"] == 1
    assert result["latest_pe_unresolved_count"] == 0
    assert result["latest_pe_failure_count"] == 0
    assert result["acceptance_gate_pass"] is True
    assert result["snapshot_completeness"]["global_completeness_proven"] is False
    unavailable = next(record for record in result["evidence_records"]
                       if record["status"] == LEGITIMATE_UNAVAILABLE_PROVEN)
    assert unavailable["symbol"] == "6548"
    assert unavailable["reason_code"] == "OFFICIAL_PE_UNAVAILABLE"
    assert unavailable["official_source"] == LATEST_PE_URL
    assert unavailable["source_date"] == "2026-10-02"
    assert unavailable["evidence"]["target_date_present"] is True


def test_partial_schema_valid_snapshot_is_unresolved_without_official_resolution():
    close, pe = _complete_snapshots()
    close_rows = json.loads(close)
    pe_rows = json.loads(pe)
    close = json.dumps(close_rows[:-1], ensure_ascii=False).encode()
    pe = json.dumps(pe_rows[:-1], ensure_ascii=False).encode()

    result = audit_current_tpex_universe(
        transport=SnapshotTransport(close, pe), retries=0,
        missing_resolver=lambda *args, **kwargs: None)
    assert result["latest_close_unresolved_count"] == 1
    assert result["latest_pe_unresolved_count"] == 1
    assert result["latest_close_legitimate_unavailable_proven_count"] == 0
    assert result["acceptance_gate_pass"] is False
    assert {record["symbol"] for record in result["unresolved_records"]} == {"8069"}
    assert all(record["reason_code"] ==
               "SNAPSHOT_MISSING_AND_NO_OFFICIAL_RESOLUTION_EVIDENCE"
               for record in result["unresolved_records"])


@pytest.mark.parametrize("payload,match", [
    ({"totalCount": 2, "data": [{"code": "6488"}]}, "truncated"),
    ({"nextPage": 2, "data": []}, "pagination"),
    ({"totalCount": 1, "data": [{"code": "6488"}]}, "unsupported"),
])
def test_snapshot_envelope_truncation_pagination_and_contract_drift_fail_closed(payload, match):
    with pytest.raises(MalformedSourceError, match=match):
        _rows(json.dumps(payload).encode(), {"code"}, "test snapshot")


def test_snapshot_duplicate_and_malformed_symbols_fail_closed():
    eligible = {"6488"}
    duplicate = [
        {"SecuritiesCompanyCode": "6488"},
        {"SecuritiesCompanyCode": "6488"},
    ]
    with pytest.raises(MalformedSourceError, match="duplicate"):
        _index_latest(duplicate, eligible, "test snapshot")
    with pytest.raises(MalformedSourceError, match="malformed"):
        _index_latest([{"SecuritiesCompanyCode": "64 88"}], eligible, "test snapshot")


class HistoryTransport:
    def __init__(self, symbol, *, stopped=False, status_name=None):
        self.symbol = symbol
        self.stopped = stopped
        self.status_name = status_name

    def get(self, url, timeout):
        if "afterTrading/chtm" in url:
            data = [self.symbol, self.status_name or self.symbol,
                    "", "", "", "", "Ｙ", "", "", ""]
            rows = [data] if self.stopped else []
            body = json.dumps({
                "date": "20260902", "stat": "ok", "tables": [{
                    "totalCount": len(rows),
                    "fields": ["證券代號", "證券名稱", "變更交易", "分盤交易",
                               "屬管理股票", "分盤或管理股票撮合循環時間(分鐘)",
                               "停止交易", "財務資訊重點專區", "公告連結",
                               "財務重點專區連結"],
                    "data": rows,
                }],
            }, ensure_ascii=False).encode()
            return HttpResponse(url, 200, body)
        endpoint = "pe" if "peQryStock" in url else "close"
        body = (FIXTURES / f"tpex_{endpoint}_{self.symbol}_202609.json").read_bytes()
        return HttpResponse(url, 200, body)


def _identity(symbol):
    return next(identity for identity in parse_security_master(MASTER, TPEX)
                if identity.symbol == symbol)


def test_per_symbol_resolution_proves_explicit_unavailable_pe_row():
    result = resolve_missing_tpex_observation(
        _identity("6488"), "LATEST_PE", date(2026, 9, 2),
        transport=HistoryTransport("6488"), retries=0)
    assert result["status"] == LEGITIMATE_UNAVAILABLE_PROVEN
    assert result["reason_code"] == "OFFICIAL_PE_UNAVAILABLE"
    assert result["evidence"]["target_date_present"] is True
    assert len(result["evidence"]["sha256"]) == 64


def test_per_symbol_resolution_keeps_absent_pe_row_unresolved():
    result = resolve_missing_tpex_observation(
        _identity("8069"), "LATEST_PE", date(2026, 9, 2),
        transport=HistoryTransport("8069"), retries=0)
    assert result["status"] == UNRESOLVED
    assert result["reason_code"] == (
        "OFFICIAL_PE_ROW_ABSENT_WITHOUT_UNAVAILABLE_SEMANTICS")
    assert result["evidence"]["declared_rowset_validated"] is True


def test_per_symbol_resolution_proves_no_close_observation_on_target_date():
    result = resolve_missing_tpex_observation(
        _identity("8069"), "LATEST_CLOSE", date(2026, 9, 2),
        transport=HistoryTransport("8069"), retries=0)
    assert result["status"] == AVAILABLE
    assert result["reason_code"] == "OFFICIAL_CLOSE_AVAILABLE"


def test_official_suspension_proves_snapshot_unavailability_with_name_presentation_variant():
    identity = _identity("8069")
    identity = identity.__class__(
        **{**identity.__dict__, "company_short_name": "元元太",
           "company_name": "(元元太)科技股份有限公司"})
    result = resolve_missing_tpex_observation(
        identity, "LATEST_PE", date(2026, 9, 2),
        transport=HistoryTransport("8069", stopped=True, status_name="元太"), retries=0)
    assert result["status"] == LEGITIMATE_UNAVAILABLE_PROVEN
    assert result["reason_code"] == "SUSPENDED_TRADING"
    assert result["evidence"]["stopped_trading"] is True


def test_invalid_resolution_evidence_is_failure_not_legitimate_unavailable():
    close, pe = _complete_snapshots()
    close = json.dumps(json.loads(close)[:-1], ensure_ascii=False).encode()

    def invalid(identity, data_type, snapshot_date, **kwargs):
        return {"symbol": "6488", "data_type": data_type, "status": AVAILABLE}

    result = audit_current_tpex_universe(
        transport=SnapshotTransport(close, pe), retries=0,
        missing_resolver=invalid)
    assert result["latest_close_failure_count"] == 1
    assert result["latest_close_legitimate_unavailable_proven_count"] == 0
    assert result["acceptance_gate_pass"] is False
    assert result["failure_records"][0]["status"] == FAILURE
