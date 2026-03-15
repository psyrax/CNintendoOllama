import json
import pytest
import respx
import httpx
from pathlib import Path
from click.testing import CliRunner
from cnintendo.commands.describe import describe


EXTRACTED_JSON = {
    "filename": "test.pdf",
    "total_pages": 2,
    "pdf_type": "scanned",
    "pages": [
        {"page_number": 1, "text": "Texto página 1",
         "images": ["data/images/test_p1_img0.png"]},
        {"page_number": 2, "text": "Texto página 2", "images": []},
    ]
}


@respx.mock
def test_describe_creates_json(tmp_path):
    extracted = tmp_path / "test_extracted.json"
    extracted.write_text(json.dumps(EXTRACTED_JSON))
    img_path = tmp_path / "data/images/test_p1_img0.png"
    img_path.parent.mkdir(parents=True)
    img_path.write_bytes(b"\x89PNG\r\n")  # minimal PNG header

    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={
            "response": "Pantalla de Super Mario World con Mario saltando."
        })
    )

    runner = CliRunner()
    result = runner.invoke(describe, [str(extracted)],
                           catch_exceptions=False,
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "llava:7b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0, result.output
    out_file = tmp_path / "test_described.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert len(data) == 1
    assert "Super Mario" in list(data.values())[0]


@respx.mock
def test_describe_skips_missing_images(tmp_path):
    extracted = tmp_path / "test_extracted.json"
    extracted.write_text(json.dumps(EXTRACTED_JSON))
    # No crear la imagen en disco

    runner = CliRunner()
    result = runner.invoke(describe, [str(extracted)],
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "llava:7b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0
    out_file = tmp_path / "test_described.json"
    data = json.loads(out_file.read_text())
    assert data == {}
