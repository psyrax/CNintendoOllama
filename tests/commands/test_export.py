import json
import pytest
import sqlite3
from pathlib import Path
from click.testing import CliRunner
from cnintendo.cli import main


SAMPLE_STRUCTURED = {
    "issue": {
        "id": None,
        "filename": "revista_001.pdf",
        "number": 1,
        "year": 1995,
        "month": "enero",
        "pages": 84,
        "type": "native"
    },
    "articles": [
        {
            "page": 12,
            "section": "review",
            "title": "Super Mario 64",
            "game": "Super Mario 64",
            "platform": "N64",
            "score": 97,
            "text": "Un juego excelente",
            "images": []
        }
    ]
}


def test_export_creates_sqlite(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(json.dumps(SAMPLE_STRUCTURED))
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0
    assert db_path.exists()


def test_export_tables_exist(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(json.dumps(SAMPLE_STRUCTURED))
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    assert "issues" in tables
    assert "articles" in tables
    assert "games" in tables
    assert "images" in tables


def test_export_data_correct(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(json.dumps(SAMPLE_STRUCTURED))
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0

    conn = sqlite3.connect(db_path)
    articles = conn.execute("SELECT title, score FROM articles").fetchall()
    games = conn.execute("SELECT name, platform FROM games").fetchall()
    conn.close()

    assert len(articles) == 1
    assert articles[0][0] == "Super Mario 64"
    assert articles[0][1] == 97.0
    assert len(games) == 1
    assert games[0][0] == "Super Mario 64"
    assert games[0][1] == "N64"


def test_export_skips_bad_json(tmp_path):
    """Files with invalid JSON should be skipped gracefully, not crash."""
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "bad_structured.json").write_text("this is not valid json {{{")
    (input_dir / "revista_001_structured.json").write_text(json.dumps(SAMPLE_STRUCTURED))
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0  # should not crash

    conn = sqlite3.connect(db_path)
    articles = conn.execute("SELECT title FROM articles").fetchall()
    conn.close()
    assert len(articles) == 1  # only the valid file was processed
