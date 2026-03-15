import json
import pytest
import respx
import httpx
from pathlib import Path
from click.testing import CliRunner
from cnintendo.commands.summarize import summarize


STRUCTURED_JSON = {
    "issue": {
        "filename": "test.pdf", "pages": 30, "type": "scanned",
        "ia_title": "Club Nintendo Año 01 Nº 01"
    },
    "articles": [
        {"page": 1, "section": "review", "title": "Super Mario World",
         "game": "Super Mario World", "platform": "SNES", "score": 9.5,
         "text": "Un juego imprescindible.", "images": []},
        {"page": 5, "section": "news", "title": "Noticias Nintendo",
         "game": None, "platform": None, "score": None,
         "text": "Novedades del mes.", "images": []},
    ]
}


@respx.mock
def test_summarize_creates_txt(tmp_path):
    structured = tmp_path / "test_structured.json"
    structured.write_text(json.dumps(STRUCTURED_JSON))
    expected_out = tmp_path / "test_summary.txt"

    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={
            "response": "Este número destaca la reseña de Super Mario World."
        })
    )

    runner = CliRunner()
    result = runner.invoke(summarize, [str(structured)],
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "gemma3:4b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0, result.output
    assert expected_out.exists()
    assert "Super Mario World" in expected_out.read_text()


@respx.mock
def test_summarize_skips_if_exists(tmp_path):
    structured = tmp_path / "test_structured.json"
    structured.write_text(json.dumps(STRUCTURED_JSON))
    summary_out = tmp_path / "test_summary.txt"
    summary_out.write_text("Ya existe.")

    runner = CliRunner()
    result = runner.invoke(summarize, [str(structured)],
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "gemma3:4b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0
    assert summary_out.read_text() == "Ya existe."


@respx.mock
def test_summarize_force_overwrites(tmp_path):
    structured = tmp_path / "test_structured.json"
    structured.write_text(json.dumps(STRUCTURED_JSON))
    summary_out = tmp_path / "test_summary.txt"
    summary_out.write_text("Texto viejo.")

    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "Texto nuevo."})
    )

    runner = CliRunner()
    result = runner.invoke(summarize, [str(structured), "--force"],
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "gemma3:4b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0
    assert summary_out.read_text() == "Texto nuevo."
