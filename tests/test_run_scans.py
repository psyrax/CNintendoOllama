import json
from pathlib import Path
import pytest
import respx
import httpx
from click.testing import CliRunner
from cnintendo.commands.run import run

SAMPLE_META = """<?xml version="1.0"?>
<metadata>
  <identifier>TestItem01</identifier>
  <title>Test Magazine No. 1</title>
  <date>1991-01</date>
</metadata>"""

SAMPLE_DJVU = "Texto de la revista.\x0cMás contenido del número."

OLLAMA_ANALYZE_RESPONSE = json.dumps({
    "articles": [{"page": 1, "section": "news", "title": "Noticia",
                  "game": None, "platform": None, "score": None,
                  "text": "Contenido.", "images": []}]
})


@respx.mock
def test_run_scans_dir_processes_items(tmp_path):
    scans_dir = tmp_path / "scans"
    scans_dir.mkdir()
    data_dir = tmp_path / "data"

    # Crear item IA
    item_dir = scans_dir / "TestItem01"
    item_dir.mkdir()
    (item_dir / "Test Magazine.pdf").write_bytes(b"%PDF-1.4")
    (item_dir / "Test Magazine_djvu.txt").write_text(SAMPLE_DJVU)
    (item_dir / "TestItem01_meta.xml").write_text(SAMPLE_META)

    # Mock: analyze
    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": OLLAMA_ANALYZE_RESPONSE})
    )

    runner = CliRunner()
    result = runner.invoke(run, [
        "--scans-dir", str(scans_dir),
        "--data-dir", str(data_dir),
        "--skip-export",
        "--no-summarize",
    ], env={"OLLAMA_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "gemma3:4b",
            "OLLAMA_TEXT_MODEL": "gemma3:4b"})

    assert result.exit_code == 0, result.output
    extracted = data_dir / "extracted" / "Test Magazine_extracted.json"
    structured = data_dir / "extracted" / "Test Magazine_structured.json"
    assert extracted.exists(), f"extracted not found, output: {result.output}"
    assert structured.exists(), f"structured not found, output: {result.output}"


@respx.mock
def test_run_scans_idempotent(tmp_path):
    """Segunda ejecución saltea items ya procesados."""
    scans_dir = tmp_path / "scans"
    scans_dir.mkdir()
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True)

    item_dir = scans_dir / "TestItem01"
    item_dir.mkdir()
    (item_dir / "Test Magazine.pdf").write_bytes(b"%PDF-1.4")
    (item_dir / "Test Magazine_djvu.txt").write_text(SAMPLE_DJVU)
    (item_dir / "TestItem01_meta.xml").write_text(SAMPLE_META)

    # Pre-crear archivos intermedios
    (extracted_dir / "Test Magazine_extracted.json").write_text("{}")
    (extracted_dir / "Test Magazine_structured.json").write_text("{}")

    call_count = 0

    def mock_handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"response": OLLAMA_ANALYZE_RESPONSE})

    respx.post("http://localhost:11434/api/generate").mock(side_effect=mock_handler)

    runner = CliRunner()
    result = runner.invoke(run, [
        "--scans-dir", str(scans_dir),
        "--data-dir", str(data_dir),
        "--skip-export", "--no-summarize",
    ], env={"OLLAMA_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "gemma3:4b",
            "OLLAMA_TEXT_MODEL": "gemma3:4b"})

    assert result.exit_code == 0
    assert call_count == 0  # No llamadas a Ollama porque ya existe


def test_run_scans_uses_process_when_prompt_set(tmp_path, monkeypatch):
    """When OPENAI_PROMPT_ID_PROCESS is set, _process_item should be called."""
    monkeypatch.setenv("OPENAI_PROMPT_ID_PROCESS", "pmpt_abc123")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # Create a minimal scan structure
    scan_dir = tmp_path / "ClubTest"
    scan_dir.mkdir()
    (scan_dir / "ClubTest_meta.xml").write_text(
        "<metadata><identifier>ClubTest</identifier><title>Club Nintendo Año 01 Nº 01 (México)</title><date>1991-01</date></metadata>"
    )
    (scan_dir / "ClubTest.pdf").write_bytes(b"")
    (scan_dir / "ClubTest_djvu.txt").write_text("page1\x0cpage2")
    (scan_dir / "ClubTest_scandata.xml").write_text(
        "<book><bookData><leafCount>2</leafCount></bookData><pageData>"
        "<page leafNum='0'><pageType>Title</pageType></page>"
        "<page leafNum='1'><pageType>Normal</pageType></page>"
        "</pageData></book>"
    )

    data_dir = tmp_path / "data"

    from unittest.mock import patch, MagicMock
    from click.testing import CliRunner
    from cnintendo.cli import main

    with patch("cnintendo.commands.run._process_item") as mock_process:
        # Make the mock return a valid pages.json path
        pages_json = data_dir / "1991" / "01" / "club-nintendo_1991-01_a01-n01_pages.json"
        pages_json.parent.mkdir(parents=True, exist_ok=True)
        pages_json.write_text('{"ia_identifier": "ClubTest", "canonical_stem": "club-nintendo_1991-01_a01-n01", "filename": "ClubTest.pdf", "total_pages": 2, "pages": [], "ia_subjects": []}')
        mock_process.return_value = pages_json

        runner = CliRunner()
        result = runner.invoke(main, [
            "run", "--scans-dir", str(tmp_path), "--data-dir", str(data_dir),
            "--skip-export"
        ])

    assert mock_process.called, f"_process_item should have been called. Output: {result.output}"
