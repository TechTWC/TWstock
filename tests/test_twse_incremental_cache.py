from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from twstock_data.errors import DataValidationError, SourceUnavailableError
from twstock_data.http import HttpResponse
from twstock_data.sources.twse import fetch_twse_daily


def _payload(month_identifier: str, roc_trade_date: str, close: int) -> bytes:
    payload = {
        "stat": "OK",
        "date": month_identifier,
        "title": f"{roc_trade_date[:3]}年 {month_identifier[4:6]}月 2330 台積電 各日成交資訊",
        "fields": [
            "日期",
            "成交股數",
            "成交金額",
            "開盤價",
            "最高價",
            "最低價",
            "收盤價",
            "漲跌價差",
            "成交筆數",
        ],
        "data": [
            [
                roc_trade_date,
                "10,000",
                f"{close * 10_000:,}",
                str(close),
                str(close + 1),
                str(close - 1),
                str(close),
                "+1.00",
                "500",
            ]
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


MONTHS = {
    "20260601": _payload("20260601", "115/06/30", 100),
    "20260701": _payload("20260701", "115/07/31", 110),
    "20260801": _payload("20260801", "115/08/14", 120),
}
JULY_EARLY = _payload("20260701", "115/07/14", 109)


class ScriptedTransport:
    def __init__(self, responses: dict[str, bytes | Exception]):
        self.responses = responses
        self.months: list[str] = []

    def get(self, url: str, timeout: float) -> HttpResponse:
        del timeout
        month = url.split("date=", 1)[1].split("&", 1)[0]
        self.months.append(month)
        response = self.responses.get(month)
        if response is None:
            raise AssertionError(f"unexpected network request for {month}")
        if isinstance(response, Exception):
            raise response
        return HttpResponse(url=url, status=200, body=response)


class FlakyCurrentMonthTransport:
    def __init__(self):
        self.calls = 0

    def get(self, url: str, timeout: float) -> HttpResponse:
        del timeout
        self.calls += 1
        if self.calls < 3:
            raise TimeoutError("temporary outage")
        return HttpResponse(url=url, status=200, body=MONTHS["20260701"])


def _fetch(
    cache: Path,
    transport: ScriptedTransport,
    start: str,
    end: str,
    *,
    refresh_date: date,
):
    return fetch_twse_daily(
        "2330",
        start,
        end,
        transport=transport,
        retries=0,
        raw_cache_dir=cache,
        incremental_cache=True,
        cache_refresh_date=refresh_date,
    )


def _manifest(cache: Path) -> dict[str, object]:
    return json.loads((cache / "twse_cache_run.json").read_text(encoding="utf-8"))


def test_historical_month_hits_cache_while_current_month_refreshes(tmp_path):
    first = ScriptedTransport(
        {"20260601": MONTHS["20260601"], "20260701": MONTHS["20260701"]}
    )
    _fetch(
        tmp_path,
        first,
        "2026-06-01",
        "2026-07-31",
        refresh_date=date(2026, 7, 15),
    )
    assert first.months == ["20260601", "20260701"]

    second = ScriptedTransport({"20260701": MONTHS["20260701"]})
    records = _fetch(
        tmp_path,
        second,
        "2026-06-01",
        "2026-07-31",
        refresh_date=date(2026, 7, 16),
    )

    assert second.months == ["20260701"]
    assert [record.trade_date for record in records] == ["2026-06-30", "2026-07-31"]
    manifest = _manifest(tmp_path)
    assert manifest["completed"] is True
    assert manifest["refresh_month"] == "20260701"
    assert [item["status"] for item in manifest["month_results"]] == [
        "CACHE_HIT",
        "REFRESHED_CURRENT",
    ]


def test_only_missing_historical_months_are_fetched(tmp_path):
    _fetch(
        tmp_path,
        ScriptedTransport({"20260601": MONTHS["20260601"]}),
        "2026-06-01",
        "2026-06-30",
        refresh_date=date(2026, 9, 1),
    )

    transport = ScriptedTransport(
        {"20260701": MONTHS["20260701"], "20260801": MONTHS["20260801"]}
    )
    _fetch(
        tmp_path,
        transport,
        "2026-06-01",
        "2026-08-31",
        refresh_date=date(2026, 9, 1),
    )

    assert transport.months == ["20260701", "20260801"]
    assert [item["status"] for item in _manifest(tmp_path)["month_results"]] == [
        "CACHE_HIT",
        "FETCHED_MISSING",
        "FETCHED_MISSING",
    ]


def test_interrupted_run_resumes_after_last_completed_month(tmp_path):
    interrupted = ScriptedTransport(
        {
            "20260601": MONTHS["20260601"],
            "20260701": TimeoutError("temporary outage"),
        }
    )
    with pytest.raises(SourceUnavailableError):
        _fetch(
            tmp_path,
            interrupted,
            "2026-06-01",
            "2026-08-31",
            refresh_date=date(2026, 9, 1),
        )
    failed = _manifest(tmp_path)
    assert failed["completed"] is False
    assert [item["status"] for item in failed["month_results"]] == [
        "FETCHED_MISSING",
        "FAILED_FETCH",
    ]

    resumed = ScriptedTransport(
        {"20260701": MONTHS["20260701"], "20260801": MONTHS["20260801"]}
    )
    _fetch(
        tmp_path,
        resumed,
        "2026-06-01",
        "2026-08-31",
        refresh_date=date(2026, 9, 1),
    )
    assert resumed.months == ["20260701", "20260801"]
    assert _manifest(tmp_path)["completed"] is True


def test_corrupt_historical_cache_is_never_trusted(tmp_path):
    _fetch(
        tmp_path,
        ScriptedTransport({"20260601": MONTHS["20260601"]}),
        "2026-06-01",
        "2026-06-30",
        refresh_date=date(2026, 9, 1),
    )
    stable_raw = tmp_path / ".monthly" / "twse_2330_20260601.raw"
    stable_raw.write_bytes(b"corrupt")

    transport = ScriptedTransport({"20260601": MONTHS["20260601"]})
    _fetch(
        tmp_path,
        transport,
        "2026-06-01",
        "2026-06-30",
        refresh_date=date(2026, 9, 1),
    )

    assert transport.months == ["20260601"]
    assert _manifest(tmp_path)["month_results"][0]["status"] == "REFETCHED_INVALID"


def test_wrong_month_response_is_not_promoted_to_cache(tmp_path):
    wrong_month = _payload("20260501", "115/05/29", 90)
    with pytest.raises(
        DataValidationError,
        match="TWSE response month mismatch for requested month 20260601",
    ):
        _fetch(
            tmp_path,
            ScriptedTransport({"20260601": wrong_month}),
            "2026-06-01",
            "2026-06-30",
            refresh_date=date(2026, 9, 1),
        )

    assert not (tmp_path / ".monthly" / "twse_2330_20260601.raw").exists()
    manifest = _manifest(tmp_path)
    assert manifest["completed"] is False
    assert manifest["month_results"][0]["status"] == "FAILED_VALIDATION"


def test_current_month_refresh_never_falls_back_to_stale_cache(tmp_path):
    _fetch(
        tmp_path,
        ScriptedTransport({"20260701": MONTHS["20260701"]}),
        "2026-07-01",
        "2026-07-31",
        refresh_date=date(2026, 7, 15),
    )

    failing = ScriptedTransport({"20260701": TimeoutError("offline")})
    with pytest.raises(SourceUnavailableError):
        _fetch(
            tmp_path,
            failing,
            "2026-07-01",
            "2026-07-31",
            refresh_date=date(2026, 7, 16),
        )
    manifest = _manifest(tmp_path)
    assert manifest["completed"] is False
    assert manifest["month_results"][0]["status"] == "FAILED_FETCH"


def test_current_month_refreshes_even_when_requested_end_precedes_today(tmp_path):
    _fetch(
        tmp_path,
        ScriptedTransport({"20260701": JULY_EARLY}),
        "2026-07-01",
        "2026-07-15",
        refresh_date=date(2026, 7, 31),
    )

    transport = ScriptedTransport({"20260701": JULY_EARLY})
    _fetch(
        tmp_path,
        transport,
        "2026-07-01",
        "2026-07-15",
        refresh_date=date(2026, 7, 31),
    )
    assert transport.months == ["20260701"]
    assert _manifest(tmp_path)["month_results"][0]["status"] == "REFRESHED_CURRENT"


def test_incremental_current_month_uses_bounded_http_retries(tmp_path):
    transport = FlakyCurrentMonthTransport()
    records = fetch_twse_daily(
        "2330",
        "2026-07-01",
        "2026-07-31",
        transport=transport,
        retries=2,
        raw_cache_dir=tmp_path,
        incremental_cache=True,
        cache_refresh_date=date(2026, 7, 15),
    )

    assert transport.calls == 3
    assert [record.trade_date for record in records] == ["2026-07-31"]
    assert _manifest(tmp_path)["completed"] is True


def test_valid_v0_1_snapshot_is_imported_without_network(tmp_path):
    legacy_transport = ScriptedTransport({"20260601": MONTHS["20260601"]})
    fetch_twse_daily(
        "2330",
        "2026-06-01",
        "2026-06-30",
        transport=legacy_transport,
        retries=0,
        raw_cache_dir=tmp_path,
    )

    incremental = ScriptedTransport({})
    _fetch(
        tmp_path,
        incremental,
        "2026-06-01",
        "2026-06-30",
        refresh_date=date(2026, 9, 1),
    )

    assert incremental.months == []
    assert _manifest(tmp_path)["month_results"][0]["status"] == "IMPORTED_LEGACY_CACHE"
    assert (tmp_path / ".monthly" / "twse_2330_20260601.raw").is_file()
