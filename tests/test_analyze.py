import json
import pytest
import respx
import httpx
from pathlib import Path
from click.testing import CliRunner
from cnintendo.commands.analyze import analyze

EXTRACTED_JSON = {
    "filename": "test.pdf", "total_pages": 5, "pdf_type": "scanned",
    "pages": [{"page_number": 1, "text": "Super Mario World es un gran juego de SNES. Puntuación: 9.5"}]
}

OLLAMA_RESPONSE_WITH_IMAGES = json.dumps({
    "articles": [{
        "page": 1, "section": "review",
        "title": "Super Mario World", "game": "Super Mario World",
        "platform": "SNES", "score": 9.5,
        "text": "Un juego imprescindible.",
        "images": ["data/images/p1_img0.png"]
    }]
})


@respx.mock
def test_analyze_converts_image_strings_to_imageinfo(tmp_path):
    extracted = tmp_path / "test_extracted.json"
    extracted.write_text(json.dumps(EXTRACTED_JSON))

    # Mock analyze call (returns list of strings in images)
    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": OLLAMA_RESPONSE_WITH_IMAGES})
    )

    runner = CliRunner()
    result = runner.invoke(analyze, [str(extracted), "--no-clean"],
                           env={"OLLAMA_URL": "http://localhost:11434",
                                "OLLAMA_MODEL": "gemma3:4b",
                                "OLLAMA_TEXT_MODEL": "gemma3:4b"})
    assert result.exit_code == 0, result.output

    out_file = tmp_path / "test_structured.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    article = data["articles"][0]
    assert article["images"] == [{"path": "data/images/p1_img0.png", "description": None}]
