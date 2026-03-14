import json
import pytest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from cnintendo.cli import main


SAMPLE_EXTRACTED = {
    "filename": "revista_001.pdf",
    "pdf_type": "native",
    "total_pages": 2,
    "pages": [
        {
            "page_number": 1,
            "text": "Super Mario 64\nPlataforma: Nintendo 64\nPuntuación: 97\nUn juego revolucionario...",
            "image_count": 0,
            "images": []
        }
    ]
}

SAMPLE_OLLAMA_RESPONSE = json.dumps({
    "articles": [
        {
            "page": 1,
            "section": "review",
            "title": "Super Mario 64",
            "game": "Super Mario 64",
            "platform": "Nintendo 64",
            "score": 97,
            "text": "Un juego revolucionario...",
            "images": []
        }
    ]
})


def test_analyze_produces_structured_json(tmp_path):
    extracted_json = tmp_path / "revista_001_extracted.json"
    extracted_json.write_text(json.dumps(SAMPLE_EXTRACTED))
    output_json = tmp_path / "structured.json"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = SAMPLE_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["analyze", str(extracted_json), "--output", str(output_json)]
        )

    assert result.exit_code == 0
    assert output_json.exists()
    data = json.loads(output_json.read_text())
    assert "issue" in data
    assert "articles" in data
    assert len(data["articles"]) == 1
    assert data["articles"][0]["game"] == "Super Mario 64"


def test_analyze_idempotent(tmp_path):
    """Second run without --force should skip re-analysis."""
    extracted_json = tmp_path / "revista_001_extracted.json"
    extracted_json.write_text(json.dumps(SAMPLE_EXTRACTED))
    output_json = tmp_path / "structured.json"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = SAMPLE_OLLAMA_RESPONSE
        runner = CliRunner()
        runner.invoke(main, ["analyze", str(extracted_json), "--output", str(output_json)])

        # Second run — should skip (Ollama not called again)
        mock_gen.reset_mock()
        runner.invoke(main, ["analyze", str(extracted_json), "--output", str(output_json)])
        mock_gen.assert_not_called()


def test_analyze_default_output_path(tmp_path):
    """Without --output, default path should be alongside extracted JSON."""
    extracted_json = tmp_path / "revista_001_extracted.json"
    extracted_json.write_text(json.dumps(SAMPLE_EXTRACTED))
    expected_output = tmp_path / "revista_001_structured.json"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = SAMPLE_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", str(extracted_json)])

    assert result.exit_code == 0
    assert expected_output.exists()
