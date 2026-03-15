from pathlib import Path
import pytest
from cnintendo.scan_reader import ScanItem, discover_scans, parse_djvu_text, parse_meta_xml

SAMPLE_META = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>ClubNintendoAo01N01Mxico</identifier>
  <title>Club Nintendo Año 01 Nº 01 (México)</title>
  <date>1991-01</date>
  <subject>videojuegos</subject>
  <subject>nintendo</subject>
</metadata>"""

SAMPLE_DJVU = "Página uno texto.\n\nMás texto.\x0cPágina dos texto.\x0cPágina tres."


def test_parse_meta_xml(tmp_path):
    meta_file = tmp_path / "test_meta.xml"
    meta_file.write_text(SAMPLE_META, encoding="utf-8")
    meta = parse_meta_xml(meta_file)
    assert meta["title"] == "Club Nintendo Año 01 Nº 01 (México)"
    assert meta["date"] == "1991-01"
    assert meta["subjects"] == ["videojuegos", "nintendo"]
    assert meta["identifier"] == "ClubNintendoAo01N01Mxico"


def test_parse_djvu_text():
    pages = parse_djvu_text(SAMPLE_DJVU)
    assert len(pages) == 3
    assert pages[0]["page_number"] == 1
    assert "Página uno texto" in pages[0]["text"]
    assert pages[1]["page_number"] == 2
    assert "Página dos" in pages[1]["text"]


def test_parse_djvu_text_empty():
    assert parse_djvu_text("") == []
    assert parse_djvu_text("   \x0c  \x0c  ") == []


def test_discover_scans(tmp_path):
    # Crear estructura mínima
    scan_dir = tmp_path / "ClubNintendoAo01N01Mxico"
    scan_dir.mkdir()
    (scan_dir / "Club Nintendo.pdf").write_text("")
    (scan_dir / "Club Nintendo_djvu.txt").write_text(SAMPLE_DJVU)
    (scan_dir / "ClubNintendoAo01N01Mxico_meta.xml").write_text(SAMPLE_META)

    items = discover_scans(tmp_path)
    assert len(items) == 1
    item = items[0]
    assert item.identifier == "ClubNintendoAo01N01Mxico"
    assert item.djvu_txt.exists()
    assert item.meta_xml.exists()


def test_discover_scans_skips_incomplete(tmp_path):
    # Dir sin djvu.txt → ignorado
    incomplete = tmp_path / "Incomplete"
    incomplete.mkdir()
    (incomplete / "test.pdf").write_text("")

    items = discover_scans(tmp_path)
    assert len(items) == 0


def test_scan_item_to_extracted_dict(tmp_path):
    scan_dir = tmp_path / "ClubNintendoAo01N01Mxico"
    scan_dir.mkdir()
    pdf = scan_dir / "Club Nintendo.pdf"
    pdf.write_text("")
    djvu = scan_dir / "Club Nintendo_djvu.txt"
    djvu.write_text(SAMPLE_DJVU)
    meta = scan_dir / "ClubNintendoAo01N01Mxico_meta.xml"
    meta.write_text(SAMPLE_META)

    item = discover_scans(tmp_path)[0]
    extracted = item.to_extracted_dict()
    assert extracted["filename"] == "Club Nintendo.pdf"
    assert extracted["total_pages"] == 3
    assert len(extracted["pages"]) == 3
    assert extracted["pdf_type"] == "scanned"
    assert extracted["ia_title"] == "Club Nintendo Año 01 Nº 01 (México)"
    assert extracted["ia_subjects"] == ["videojuegos", "nintendo"]
