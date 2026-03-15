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
