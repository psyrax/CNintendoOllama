import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner
from cnintendo.cli import main


SAMPLE_PAGES_JSON = {
    "ia_identifier": "ClubTest",
    "ia_title": "Club Nintendo Test",
    "ia_date": "1991-01",
    "ia_description": "Enero 1991",
    "ia_clubnintendo": "No0101",
    "ia_subjects": ["videojuegos"],
    "canonical_stem": "club-nintendo_1991-01_a01-n01",
    "filename": "test.pdf",
    "total_pages": 2,
    "pages": [
        {
            "page_number": 1,
            "page_type_scandata": "Title",
            "image_path": "1991/01/images/page_0001.jpg",
            "djvu_text": "Portada Club Nintendo",
            "llm": {
                "page_type": "cover",
                "summary": "Portada",
                "game": None,
                "platform": None,
                "score": None,
                "text_blocks": ["Club Nintendo"],
                "image_descriptions": ["Mario en portada"]
            }
        },
        {
            "page_number": 5,
            "page_type_scandata": "Normal",
            "image_path": "1991/01/images/page_0005.jpg",
            "djvu_text": "Mega Man reseña NES",
            "llm": {
                "page_type": "review",
                "summary": "Reseña Mega Man",
                "game": "Mega Man",
                "platform": "NES",
                "score": 9.5,
                "text_blocks": ["RESEÑA", "Mega Man"],
                "image_descriptions": ["Screenshot NES"]
            }
        }
    ]
}


def test_export_pages_json(tmp_path):
    """Test that export reads _pages.json and populates issues, pages, and articles tables."""
    pages_file = tmp_path / "1991" / "01"
    pages_file.mkdir(parents=True)
    (pages_file / "club-nintendo_1991-01_a01-n01_pages.json").write_text(
        json.dumps(SAMPLE_PAGES_JSON)
    )
    db_path = tmp_path / "output.db"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(tmp_path), "--db", str(db_path)])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    conn = sqlite3.connect(db_path)
    issues = conn.execute("SELECT * FROM issues").fetchall()
    assert len(issues) == 1
    assert issues[0][1] == "test.pdf"  # filename column

    pages = conn.execute("SELECT page_number, djvu_text FROM pages ORDER BY page_number").fetchall()
    assert len(pages) == 2
    assert pages[1][0] == 5  # page_number of second page
    assert pages[1][1] == "Mega Man reseña NES"  # djvu_text

    articles = conn.execute("SELECT game FROM articles").fetchall()
    assert len(articles) == 1  # only review page → 1 article
    assert articles[0][0] == "Mega Man"  # game
    conn.close()


def test_export_fallback_to_structured_json(tmp_path):
    """When no _pages.json exists, falls back to _structured.json."""
    structured = {
        "issue": {
            "filename": "old.pdf",
            "pages": 10,
            "type": "scanned",
            "ia_title": "Old",
            "ia_date": "1991-01",
            "ia_subjects": [],
            "ia_identifier": "Old"
        },
        "articles": []
    }
    (tmp_path / "old_structured.json").write_text(json.dumps(structured))
    db_path = tmp_path / "output.db"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(tmp_path), "--db", str(db_path)])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    conn = sqlite3.connect(db_path)
    issues = conn.execute("SELECT filename FROM issues").fetchall()
    assert len(issues) == 1
    assert issues[0][0] == "old.pdf"
    conn.close()


def test_export_pages_json_prioritized_over_structured(tmp_path):
    """When both _pages.json and _structured.json exist, _pages.json takes priority."""
    subdir = tmp_path / "1991" / "01"
    subdir.mkdir(parents=True)
    (subdir / "club-nintendo_1991-01_a01-n01_pages.json").write_text(
        json.dumps(SAMPLE_PAGES_JSON)
    )
    # Also create a structured.json that would have different data
    structured = {
        "issue": {
            "filename": "should-not-appear.pdf",
            "pages": 5,
            "type": "scanned",
            "ia_title": "Wrong",
            "ia_date": "1991-01",
            "ia_subjects": [],
            "ia_identifier": "ClubTest"
        },
        "articles": []
    }
    (subdir / "club-nintendo_1991-01_a01-n01_structured.json").write_text(json.dumps(structured))
    db_path = tmp_path / "output.db"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(tmp_path), "--db", str(db_path)])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    conn = sqlite3.connect(db_path)
    issues = conn.execute("SELECT filename FROM issues").fetchall()
    assert len(issues) == 1
    assert issues[0][0] == "test.pdf"  # from pages.json, NOT structured.json
    conn.close()
