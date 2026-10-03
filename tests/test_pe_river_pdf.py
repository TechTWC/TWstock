def test_cli_offline_end_to_end

def test_all_unavailable_adjusted_report_writes_pdf_csv_and_json_without_fake_river(tmp_path):
    observations = (
        ValuationObservation(
            "6488", date(2026, 9, 1), 100, None,
            canonical_symbol="6488.TWO", market="TPEX", company_name="環球晶"),
        ValuationObservation(
            "6488", date(2026, 9, 2), 102, None,
            canonical_symbol="6488.TWO", market="TPEX", company_name="環球晶"),
        ValuationObservation(
            "6488", date(2026, 9, 3), 105, None,
            canonical_symbol="6488.TWO", market="TPEX", company_name="環球晶"),
    )
    raw = calculate_rivers(observations)
    normalized = normalize_for_corporate_actions(
        observations, (), analysis_end_date=date(2026, 9, 3))
    metadata = build_metadata(
        raw, requested_coverage="MAX", requested_start=date(2026, 9, 1),
        cutoff=date(2026, 9, 3), source_start=date(2026, 9, 1))
    proof = FaceValueCoverageProof(
        symbol="6488", query_start=date(2026, 9, 1), query_end=date(2026, 9, 3),
        result_count=0, detail_count=0, rowset_hash="1" * 64,
        detail_manifest_hash="2" * 64, retrieved_at="2026-10-03T00:00:00Z",
        status=FACE_VALUE_COVERAGE_PROVEN, market="TPEX",
        canonical_symbol="6488.TWO")
    metadata = build_corporate_action_metadata(
        normalized, (), metadata, face_value_proof=proof)
    result = write_report(
        raw, metadata, tmp_path, normalized_rows=normalized, events=())

    assert Path(result["outputs"]["pdf"]).read_bytes().startswith(b"%PDF-")
    saved = json.loads((tmp_path / "report_metadata.json").read_text())
    assert saved["observation_count"] == 3
    assert saved["valid_pe_observation_count"] == 0
    assert saved["latest_official_pe"] is None
    assert saved["latest_normalized_pe"] is None
    assert saved["raw_pe_percentile"] is None
    assert saved["normalized_pe_percentile"] is None
    with (tmp_path / "historical_pe_river.csv").open() as handle:
        data = list(csv.DictReader(handle))
    assert len(data) == 3
    assert all(row["official_pe"] == row["normalized_pe"] == "" for row in data)
    assert all(row["raw_river_15x"] == row["adjusted_river_15x"] == "" for row in data)
    rendered = "
".join(_summary_lines(saved, 0, adjusted=True))
    assert "Official PE     Unavailable" in rendered
    assert "Raw PE percentile Unavailable" in rendered


