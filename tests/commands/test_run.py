import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from cnintendo.cli import main


MOCK_OLLAMA_RESPONSE = json.dumps({
    "articles": [
        {
            "page": 1,
            "section": "review",
            "title": "Test Game",
            "game": "Test Game",
            "platform": "SNES",
            "score": 85,
            "text": "Great game",
            "images": []
        }
    ]
})


def test_run_processes_folder(sample_native_pdf, tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    shutil.copy(sample_native_pdf, pdf_dir / "revista_001.pdf")
    data_dir = tmp_path / "data"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = MOCK_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(pdf_dir), "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    extracted = list((data_dir / "extracted").glob("*_extracted.json"))
    structured = list((data_dir / "extracted").glob("*_structured.json"))
    metadata = list((data_dir / "extracted").glob("*_metadata.json"))
    assert len(extracted) >= 1
    assert len(structured) >= 1
    assert len(metadata) >= 1


def test_run_skips_existing(sample_native_pdf, tmp_path):
    """run should skip steps where intermediate files already exist."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    shutil.copy(sample_native_pdf, pdf_dir / "revista_001.pdf")
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True)

    # Pre-create extracted JSON to simulate already processed
    existing_extracted = extracted_dir / "revista_001_extracted.json"
    existing_extracted.write_text(
        json.dumps({
            "filename": "revista_001.pdf",
            "pdf_type": "native",
            "total_pages": 1,
            "pages": [{"page_number": 1, "text": "test content here", "image_count": 0, "images": []}]
        })
    )
    pre_mtime = existing_extracted.stat().st_mtime

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = MOCK_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(pdf_dir), "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    # The extracted file must not have been rewritten (extract was skipped)
    assert existing_extracted.stat().st_mtime == pre_mtime
    # But structured.json should be created (analyze still runs)
    structured = list(extracted_dir.glob("*_structured.json"))
    assert len(structured) >= 1


def test_run_creates_sqlite(sample_native_pdf, tmp_path):
    """run should create output.db after processing."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    shutil.copy(sample_native_pdf, pdf_dir / "revista_001.pdf")
    data_dir = tmp_path / "data"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = MOCK_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(pdf_dir), "--data-dir", str(data_dir)])

    assert result.exit_code == 0
    assert (data_dir / "output.db").exists()
