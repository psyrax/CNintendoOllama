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


META_1991_01 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test01</identifier>
  <title>Test</title>
  <date>1991-01</date>
</metadata>"""

META_1992 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test02</identifier>
  <title>Test</title>
  <date>1992</date>
</metadata>"""

META_1993_06_15 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test03</identifier>
  <title>Test</title>
  <date>1993-06-15</date>
</metadata>"""

META_NO_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test04</identifier>
  <title>Test</title>
</metadata>"""

META_EMPTY_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test05</identifier>
  <title>Test</title>
  <date></date>
</metadata>"""


def _make_scan_item(tmp_path, identifier, meta_xml_content):
    scan_dir = tmp_path / identifier
    scan_dir.mkdir()
    (scan_dir / f"{identifier}.pdf").write_text("")
    (scan_dir / f"{identifier}_djvu.txt").write_text("texto\x0cmas texto")
    meta = scan_dir / f"{identifier}_meta.xml"
    meta.write_text(meta_xml_content)
    return discover_scans(tmp_path)[0]


def test_date_sort_key_year_and_month(tmp_path):
    item = _make_scan_item(tmp_path, "Test01", META_1991_01)
    assert item.date_sort_key == (1991, 1)


def test_date_sort_key_year_only(tmp_path):
    item = _make_scan_item(tmp_path, "Test02", META_1992)
    assert item.date_sort_key == (1992, 0)


def test_date_sort_key_full_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test03", META_1993_06_15)
    assert item.date_sort_key == (1993, 6)


def test_date_sort_key_no_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test04", META_NO_DATE)
    assert item.date_sort_key == (9999, 0)


def test_date_sort_key_empty_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test05", META_EMPTY_DATE)
    assert item.date_sort_key == (9999, 0)


def test_parse_meta_xml_new_fields():
    xml = """<metadata>
      <identifier>ClubNintendoMxicoAAo14N08</identifier>
      <title>Club Nintendo Año 14 N° 08 (México)</title>
      <date>2005-08</date>
      <subject>Mario</subject>
      <clubnintendo>No1408</clubnintendo>
      <description>Club Nintendo Año 14 N° 8 (México)<div>Agosto de 2005</div></description>
    </metadata>"""
    import tempfile, os
    from pathlib import Path
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(xml)
        path = Path(f.name)
    try:
        result = parse_meta_xml(path)
        assert result["clubnintendo"] == "No1408"
        assert "Agosto de 2005" in result["description"]
        assert "<div>" not in result["description"]
    finally:
        os.unlink(path)


def test_parse_scandata_xml():
    from cnintendo.scan_reader import parse_scandata_xml
    xml = """<book>
      <bookData><leafCount>3</leafCount></bookData>
      <pageData>
        <page leafNum="0"><pageType>Title</pageType></page>
        <page leafNum="1"><pageType>Normal</pageType></page>
        <page leafNum="2"><pageType>Normal</pageType></page>
      </pageData>
    </book>"""
    import tempfile, os
    from pathlib import Path
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(xml)
        path = Path(f.name)
    try:
        result = parse_scandata_xml(path)
        assert result["leaf_count"] == 3
        assert result["page_types"] == {1: "Title", 2: "Normal", 3: "Normal"}
    finally:
        os.unlink(path)
