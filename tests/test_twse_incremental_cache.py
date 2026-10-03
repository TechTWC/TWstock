def test_semantically_invalid_stable_cache_is_refetched

def test_cross_market_month_cache_is_never_loaded(tmp_path):
    twse_url = "https://example.test/twse?symbol=2330&date=20260601"
    tpex_url = "https://example.test/tpex?symbol=2330&date=20260601"
    store_cached_month(
        tmp_path, source_symbol="2330", canonical_symbol="2330.TW",
        month_identifier="20260601", source_url=twse_url,
        retrieved_at="2026-07-01T00:00:00+00:00", http_status=200,
        body=b"twse", source="TWSE")
    assert load_cached_month(
        tmp_path, source_symbol="2330", canonical_symbol="2330.TWO",
        month_identifier="20260601", expected_source_url=tpex_url,
        source="TPEX") is None

    store_cached_month(
        tmp_path, source_symbol="2330", canonical_symbol="2330.TWO",
        month_identifier="20260601", source_url=tpex_url,
        retrieved_at="2026-07-01T00:00:00+00:00", http_status=200,
        body=b"tpex", source="TPEX")
    with pytest.raises(DataValidationError, match="identity mismatch"):
        load_cached_month(
            tmp_path, source_symbol="2330", canonical_symbol="2330.TW",
            month_identifier="20260601", expected_source_url=tpex_url,
            source="TPEX")


