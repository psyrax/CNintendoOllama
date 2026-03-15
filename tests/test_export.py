import json
import sqlite_utils
import pytest
from pathlib import Path
from click.testing import CliRunner
from cnintendo.commands.export import export


STRUCTURED_WITH_IA = {
    "issue": {
        "filename": "test.pdf", "pages": 30, "type": "scanned",
        "ia_title": "Club Nintendo Año 01", "ia_subjects": ["videojuegos"],
        "ia_date": "1991-01", "ia_identifier": "ClubNintendoAo01N01Mxico"
    },
    "articles": [
        {"page": 1, "section": "review", "title": "Mario",
         "game": "Super Mario World", "platform": "SNES", "score": 9.5,
         "text": "Gran juego.", "images": [{"path": "img.png", "description": "Mario saltando"}]}
    ],
    "summary": "Número especial de Mario."
}

DESCRIBED_JSON = {"img.png": "Mario saltando en pantalla verde"}


def test_export_with_ia_fields(tmp_path):
    structured = tmp_path / "test_structured.json"
    structured.write_text(json.dumps(STRUCTURED_WITH_IA))
    described = tmp_path / "test_described.json"
    described.write_text(json.dumps(DESCRIBED_JSON))
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(export, ["--input-dir", str(tmp_path), "--db", str(db_path)])
    assert result.exit_code == 0, result.output

    db = sqlite_utils.Database(db_path)
    issue = list(db["issues"].rows)[0]
    assert issue["ia_title"] == "Club Nintendo Año 01"
    assert issue["summary"] == "Número especial de Mario."
    assert json.loads(issue["ia_subjects"]) == ["videojuegos"]

    img = list(db["images"].rows)[0]
    assert img["path"] == "img.png"
    assert img["description"] == "Mario saltando en pantalla verde"


def test_export_migration_adds_columns(tmp_path):
    """DB existente sin columnas IA → columnas se agregan automáticamente."""
    db_path = tmp_path / "output.db"
    # Crear DB con schema antiguo
    db = sqlite_utils.Database(db_path)
    db["issues"].create({"id": int, "filename": str, "pages": int}, pk="id")

    structured = tmp_path / "test_structured.json"
    structured.write_text(json.dumps(STRUCTURED_WITH_IA))

    runner = CliRunner()
    result = runner.invoke(export, ["--input-dir", str(tmp_path), "--db", str(db_path)])
    assert result.exit_code == 0, result.output

    # Verificar que las columnas nuevas existen
    cols = {col.name for col in db["issues"].columns}
    assert "ia_title" in cols
    assert "summary" in cols
