from pathlib import Path

WORKFLOW = Path(".github/workflows/generate-pe-river.yml")


def _workflow_text() -> str:
    assert WORKFLOW.is_file()
    return WORKFLOW.read_text(encoding="utf-8")


def test_generate_pe_river_workflow_manual_contract():
    text = _workflow_text()
    assert "name: Generate PE River" in text
    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text
    assert "symbol:" in text
    assert "coverage:" in text
    for value in ("MAX", "5Y", "10Y", "20Y"):
        assert f"- {value}" in text


def test_generate_pe_river_workflow_uses_production_cli_and_read_only_permissions():
    text = _workflow_text()
    assert "permissions:\n  contents: read" in text
    assert "python scripts/run_pe_river_report.py" in text
    assert "--symbol" in text
    assert "--output-dir" in text
    assert "--cache-dir" in text
    assert "requirements-dev.txt" in text


def test_generate_pe_river_workflow_validates_and_uploads_exact_outputs():
    text = _workflow_text()
    assert '[[ "$SYMBOL" =~ ^[0-9]{4}$ ]]' in text
    assert '"$OUTPUT_DIR/${SYMBOL}_pe_river.pdf"' in text
    assert '"$OUTPUT_DIR/historical_pe_river.csv"' in text
    assert '"$OUTPUT_DIR/report_metadata.json"' in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text
    assert "if-no-files-found: error" in text
