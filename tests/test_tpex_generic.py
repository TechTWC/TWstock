def test_official_historical_schema_versions

def test_tpex_max_retains_leading_official_unavailable_pe(tmp_path):
    pe = json.loads(fixture("tpex_pe_6488_202609.json"))
    pe["tables"][0]["data"][0][1] = "-"
    pe["tables"][0]["data"][1][1] = "--"

    class Transport:
        def get(self, url, timeout):
            body = (json.dumps(pe, ensure_ascii=False).encode()
                    if "peQryStock" in url else fixture("tpex_close_6488_202609.json"))
            return HttpResponse(url, 200, body)

    result = fetch_history(
        "6488", MONTH, date(2026, 9, 30), tmp_path,
        company_name="環球晶", transport=Transport(), request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert [row.trade_date for row in result.observations] == [
        date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    assert [row.official_pe for row in result.observations] == [None, None, 18.66]
    assert result.source_start == date(2026, 9, 1)
    metadata = build_metadata(
        calculate_rivers(result.observations), requested_coverage="MAX",
        requested_start=MONTH, source_start=result.source_start)
    assert metadata["first_valid_pe_date"] == "2026-09-03"
    assert metadata["latest_pe"] == 18.66


def test_tpex_all_official_pe_unavailable_is_valid_history(tmp_path):
    pe = json.loads(fixture("tpex_pe_6488_202609.json"))
    for row in pe["tables"][0]["data"]:
        row[1] = "-"

    class Transport:
        def get(self, url, timeout):
            body = (json.dumps(pe, ensure_ascii=False).encode()
                    if "peQryStock" in url else fixture("tpex_close_6488_202609.json"))
            return HttpResponse(url, 200, body)

    result = fetch_history(
        "6488", MONTH, date(2026, 9, 30), tmp_path,
        company_name="環球晶", transport=Transport(), request_interval=0,
        refresh_date=date(2026, 10, 2))
    assert len(result.observations) == 3
    assert all(row.official_pe is None for row in result.observations)
    assert result.source_start == date(2026, 9, 1)
    rows = calculate_rivers(result.observations)
    assert all(row.reference_eps_twd is None for row in rows)
    assert all(row.band_prices == (None,) * 5 for row in rows)
    metadata = build_metadata(
        rows, requested_coverage="MAX", requested_start=MONTH,
        source_start=result.source_start)
    assert metadata["observation_count"] == 3
    assert metadata["valid_pe_observation_count"] == 0
    assert metadata["first_valid_pe_date"] is None
    assert metadata["latest_pe"] is None
    assert metadata["latest_valid_pe_date"] is None
    assert all(metadata["percentiles"][key] is None
               for key in ("p10", "p25", "p50", "p75", "p90", "current_percentile"))


def test_tpex_missing_unproven_valuation_row_fails_closed(tmp_path):
    class Transport:
        def get(self, url, timeout):
            name = ("tpex_pe_8069_202609.json" if "peQryStock" in url
                    else "tpex_close_8069_202609.json")
            return HttpResponse(url, 200, fixture(name))

    with pytest.raises(DataValidationError, match="lack proven valuation rows"):
        fetch_history(
            "8069", MONTH, date(2026, 9, 30), tmp_path,
            company_name="元太", transport=Transport(), request_interval=0,
            refresh_date=date(2026, 10, 2))


