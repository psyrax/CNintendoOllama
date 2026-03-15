import json
import pytest
import sqlite3
from pathlib import Path
from click.testing import CliRunner
from cnintendo.cli import main
from cnintendo.commands.export import _date_sort_key


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


def test_date_sort_key_year_and_month(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1991-06"}, "articles": []}))
    assert _date_sort_key(f) == (1991, 6)


def test_date_sort_key_year_only(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1993"}, "articles": []}))
    assert _date_sort_key(f) == (1993, 0)


def test_date_sort_key_full_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1992-03-15"}, "articles": []}))
    assert _date_sort_key(f) == (1992, 3)


def test_date_sort_key_missing_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {}, "articles": []}))
    assert _date_sort_key(f) == (9999, 0)


def test_date_sort_key_none_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": None}, "articles": []}))
    assert _date_sort_key(f) == (9999, 0)


def test_date_sort_key_invalid_file(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not valid json {{{")
    assert _date_sort_key(f) == (9999, 0)


def test_export_chronological_order(tmp_path):
    """Export debe insertar issues en orden cronológico."""
    input_dir = tmp_path / "structured"
    input_dir.mkdir()

    issue_1993 = {
        "issue": {"id": None, "filename": "c_1993.pdf", "number": 3, "year": 1993,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1993-01",
                  "ia_identifier": None},
        "articles": []
    }
    issue_1991 = {
        "issue": {"id": None, "filename": "a_1991.pdf", "number": 1, "year": 1991,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1991-01",
                  "ia_identifier": None},
        "articles": []
    }
    issue_1992 = {
        "issue": {"id": None, "filename": "b_1992.pdf", "number": 2, "year": 1992,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1992-01",
                  "ia_identifier": None},
        "articles": []
    }

    # Escribir en orden C, A, B (alfabético ≠ cronológico)
    (input_dir / "c_1993_structured.json").write_text(json.dumps(issue_1993))
    (input_dir / "a_1991_structured.json").write_text(json.dumps(issue_1991))
    (input_dir / "b_1992_structured.json").write_text(json.dumps(issue_1992))

    db_path = tmp_path / "output.db"
    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0

    conn = sqlite3.connect(db_path)
    filenames = [row[0] for row in conn.execute("SELECT filename FROM issues ORDER BY id").fetchall()]
    conn.close()

    assert filenames == ["a_1991.pdf", "b_1992.pdf", "c_1993.pdf"], (
        f"Esperado orden cronológico, obtenido: {filenames}"
    )
