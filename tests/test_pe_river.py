@pytest.mark.parametrize("multiples"

                         def test_all_unavailable_metadata_has_no_fabricated_pe_statistics():
    rows = calculate_rivers([
        observation("2026-09-01", close=100, pe=None),
        observation("2026-09-02", close=102, pe=None),
        observation("2026-09-03", close=105, pe=None),
    ])
    result = build_metadata(
        rows, requested_coverage="MAX", requested_start=date(2026, 9, 1))
    assert result["source_start"] == "2026-09-01"
    assert result["first_valid_pe_date"] is None
    assert result["latest_valid_pe_date"] is None
    assert result["latest_valid_pe_close"] is None
    assert result["latest_pe"] is None
    assert result["valid_pe_observation_count"] == 0
    assert result["missing_pe_count"] == 3
    assert set(result["percentiles"].values()) >= {None}
    assert all(result["percentiles"][key] is None
               for key in ("p10", "p25", "p50", "p75", "p90", "current_percentile"))


