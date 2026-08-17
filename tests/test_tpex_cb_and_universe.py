from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from twstock_data.errors import DataValidationError
from twstock_data.http import HttpResponse
from twstock_data.sources.tpex_cb import (
    CbIssue,
    CbMarketSnapshot,
    parse_current_cb_payload,
    parse_recent_delisted_cb_payload,
)
from twstock_data.sources.twse_universe import parse_twse_listed_company_payload
from twstock_data.sources.twse_market_bulk import (
    fetch_twse_bulk_research_datasets,
    parse_twse_market_day_payload,
)


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class TpexCbAndUniverseTests(unittest.TestCase):
    @staticmethod
    def _market_day_payload(day_title: str = "115年08月14日") -> bytes:
        fields = [
            "證券代號",
            "證券名稱",
            "成交股數",
            "成交筆數",
            "成交金額",
            "開盤價",
            "最高價",
            "最低價",
            "收盤價",
        ]
        return _body(
            {
                "tables": [
                    {
                        "title": f"{day_title} 每日收盤行情",
                        "fields": fields,
                        "data": [
                            ["2330", "台積電", "1,000", "10", "2,395,000", "2,380", "2,410", "2,370", "2,395"],
                            ["0050", "元大台灣50", "2,000", "20", "100,000", "50", "51", "49", "50"],
                        ],
                    }
                ]
            }
        )

    def test_bulk_market_day_keeps_common_stock_and_rejects_wrong_date(self) -> None:
        records = parse_twse_market_day_payload(
            self._market_day_payload(),
            requested_date=date(2026, 8, 14),
            source_url="https://www.twse.com.tw/example",
            retrieved_at="2026-08-14T09:00:00+00:00",
        )
        self.assertEqual([item.source_symbol for item in records], ["0050", "2330"])
        self.assertEqual(records[1].close_price, 2395.0)
        with self.assertRaisesRegex(DataValidationError, "date mismatch"):
            parse_twse_market_day_payload(
                self._market_day_payload(),
                requested_date=date(2026, 8, 13),
                source_url="https://www.twse.com.tw/example",
                retrieved_at="2026-08-14T09:00:00+00:00",
            )

    def test_bulk_market_cache_reuses_immutable_history_and_has_fetch_guard(self) -> None:
        class Transport:
            def __init__(self, body: bytes):
                self.body = body
                self.calls = 0

            def get(self, url: str, timeout: float) -> HttpResponse:
                del timeout
                self.calls += 1
                return HttpResponse(url, 200, self.body)

        transport = Transport(self._market_day_payload())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = fetch_twse_bulk_research_datasets(
                ["2330"],
                "2026-08-14",
                "2026-08-14",
                cache_dir=root,
                transport=transport,
                retries=0,
                max_new_market_days=1,
                refresh_date=date(2026, 8, 17),
            )
            second = fetch_twse_bulk_research_datasets(
                ["2330"],
                "2026-08-14",
                "2026-08-14",
                cache_dir=root,
                transport=transport,
                retries=0,
                max_new_market_days=0,
                refresh_date=date(2026, 8, 17),
            )
            raw_path = (
                root
                / ".daily-mi-index"
                / "twse_mi_index_20260814.raw"
            )
            raw_path.write_bytes(b"corrupted")
            with self.assertRaisesRegex(DataValidationError, "exceeding"):
                fetch_twse_bulk_research_datasets(
                    ["2330"],
                    "2026-08-14",
                    "2026-08-14",
                    cache_dir=root,
                    transport=transport,
                    retries=0,
                    max_new_market_days=0,
                    refresh_date=date(2026, 8, 17),
                )
            repaired = fetch_twse_bulk_research_datasets(
                ["2330"],
                "2026-08-14",
                "2026-08-14",
                cache_dir=root,
                transport=transport,
                retries=0,
                max_new_market_days=1,
                refresh_date=date(2026, 8, 17),
            )
            with self.assertRaisesRegex(DataValidationError, "exceeding"):
                fetch_twse_bulk_research_datasets(
                    ["2330"],
                    "2026-08-12",
                    "2026-08-14",
                    cache_dir=root,
                    transport=transport,
                    retries=0,
                    max_new_market_days=1,
                    refresh_date=date(2026, 8, 17),
                )

        self.assertEqual(transport.calls, 2)
        self.assertEqual(first["2330"].bars, second["2330"].bars)
        self.assertEqual(first["2330"].bars, repaired["2330"].bars)

    def test_current_and_recent_cb_payloads_classify_without_false_never_claim(self) -> None:
        current = parse_current_cb_payload(
            _body(
                {
                    "stat": "ok",
                    "tables": [
                        {
                            "fields": [
                                "發行機構代碼",
                                "發行機構名稱",
                                "債券名稱",
                                "掛牌日期",
                                "發行資料",
                            ],
                            "data": [
                                [
                                    "2303",
                                    "聯華電子股份有限公司",
                                    "聯華電子股份有限公司國內第一次無擔保轉換公司債",
                                    "115/08/07",
                                    "https://mopsov.twse.com.tw/mops/web/t120sg01?bond_id=23031",
                                ]
                            ],
                        }
                    ],
                }
            )
        )
        recent, report_date = parse_recent_delisted_cb_payload(
            _body(
                {
                    "stat": "ok",
                    "tables": [
                        {
                            "date": "115/08/17",
                            "fields": ["代碼", "簡稱", "下櫃日期"],
                            "data": [["64145", "樺漢五", "115/08/17"]],
                        }
                    ],
                }
            )
        )
        self.assertEqual(report_date, date(2026, 8, 17))
        snapshot = CbMarketSnapshot(current, recent, report_date)

        self.assertEqual(snapshot.classify("2303").status, "CURRENT_CB")
        self.assertEqual(snapshot.classify("2303").current_issue_count, 1)
        self.assertEqual(
            snapshot.classify("6414").status,
            "RECENTLY_DELISTED_CB_OR_EB",
        )
        self.assertEqual(snapshot.classify("2330").status, "NOT_FOUND_CURRENT_OR_RECENT")
        upcoming = CbMarketSnapshot(
            current_issues=(
                CbIssue(
                    issuer_code="4967",
                    issuer_name="十銓",
                    bond_code="49675",
                    bond_name="十銓科技股份有限公司國內第五次無擔保轉換公司債",
                    event_date=date(2026, 8, 18),
                    listing_status="CURRENT",
                    instrument_type="CONVERTIBLE_BOND",
                ),
            ),
            recently_delisted_issues=(),
            data_as_of=date(2026, 8, 17),
        )
        self.assertEqual(upcoming.classify("4967").status, "UPCOMING_CB")
        self.assertEqual(upcoming.classify("4967").current_issue_count, 0)


    def test_cb_payload_requires_official_schema_and_valid_bond_identity(self) -> None:
        with self.assertRaisesRegex(DataValidationError, "fields missing"):
            parse_current_cb_payload(
                _body({"stat": "ok", "tables": [{"fields": [], "data": []}]})
            )


    def test_twse_universe_keeps_common_stocks_and_excludes_tdr(self) -> None:
        companies = parse_twse_listed_company_payload(
            _body(
                [
                    {
                        "公司代號": "2330",
                        "公司名稱": "台灣積體電路製造股份有限公司",
                        "公司簡稱": "台積電",
                        "產業別": "24",
                        "上市日期": "19940905",
                    },
                    {
                        "公司代號": "9103",
                        "公司名稱": "美德向邦醫療國際股份有限公司",
                        "公司簡稱": "美德醫療-DR",
                        "產業別": "",
                        "上市日期": "20091218",
                    },
                    {
                        "公司代號": "910322",
                        "公司名稱": "康師傅控股有限公司",
                        "公司簡稱": "康師傅-DR",
                        "產業別": "",
                        "上市日期": "20091216",
                    },
                ]
            )
        )

        self.assertEqual([item.symbol for item in companies], ["2330"])
        self.assertEqual(companies[0].name, "台積電")


if __name__ == "__main__":
    unittest.main()
