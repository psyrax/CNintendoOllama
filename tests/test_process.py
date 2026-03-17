import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def make_scan_item(tmp_path, identifier="ClubTest", with_jp2=False,
                   with_djvu_txt=False, with_scandata=False):
    """Creates a minimal ScanItem for testing."""
    from cnintendo.scan_reader import ScanItem
    scan_dir = tmp_path / identifier
    scan_dir.mkdir(exist_ok=True)
    meta = scan_dir / f"{identifier}_meta.xml"
    meta.write_text("""<metadata>
      <identifier>ClubTest</identifier>
      <title>Club Nintendo Año 01 Nº 01 (México)</title>
      <date>1991-01</date>
      <clubnintendo>No0101</clubnintendo>
      <description>Enero de 1991</description>
    </metadata>""")
    pdf = scan_dir / f"{identifier}.pdf"
    pdf.write_bytes(b"")
    scandata = None
    if with_scandata:
        scandata = scan_dir / f"{identifier}_scandata.xml"
        scandata.write_text("""<book>
          <bookData><leafCount>2</leafCount></bookData>
          <pageData>
            <page leafNum="0"><pageType>Title</pageType></page>
            <page leafNum="1"><pageType>Normal</pageType></page>
          </pageData>
        </book>""")
    djvu_txt = None
    if with_djvu_txt:
        djvu_txt = scan_dir / f"{identifier}_djvu.txt"
        djvu_txt.write_text("Texto página 1\x0cTexto página 2")
    return ScanItem(
        identifier=identifier,
        scan_dir=scan_dir,
        pdf=pdf,
        djvu_xml=None,
        djvu_txt=djvu_txt,
        jp2_zip=None,
        scandata_xml=scandata,
        meta_xml=meta,
    )


# --- Tests for _parse_llm_json ---

def test_parse_llm_json_valid():
    from cnintendo.commands.process import _parse_llm_json
    result = _parse_llm_json('{"page_type": "review", "score": 9.5}')
    assert result == {"page_type": "review", "score": 9.5}


def test_parse_llm_json_with_fences():
    from cnintendo.commands.process import _parse_llm_json
    result = _parse_llm_json('```json\n{"page_type": "cover"}\n```')
    assert result == {"page_type": "cover"}


def test_parse_llm_json_invalid():
    from cnintendo.commands.process import _parse_llm_json
    result = _parse_llm_json("Esta página es una reseña de Mario.")
    assert result is None


def test_parse_llm_json_empty():
    from cnintendo.commands.process import _parse_llm_json
    assert _parse_llm_json("") is None
    assert _parse_llm_json("  ") is None


# --- Tests for _process_item ---

def test_process_item_no_jp2_no_prompt(tmp_path):
    """Without jp2 or prompt_id: produces pages.json based on scandata."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = None
    out_dir = tmp_path / "out"
    result = _process_item(item, out_dir, client, force=False, start_page=1)
    assert result.exists()
    data = json.loads(result.read_text())
    assert data["ia_identifier"] == "ClubTest"
    assert data["total_pages"] == 2  # from scandata leafCount
    assert isinstance(data["pages"], list)


def test_process_item_djvu_text_populated(tmp_path):
    """DJVU text should appear in page djvu_text field."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_djvu_txt=True, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = None
    out_dir = tmp_path / "out"
    result = _process_item(item, out_dir, client, force=False, start_page=1)
    data = json.loads(result.read_text())
    pages = {p["page_number"]: p for p in data["pages"]}
    assert pages[1]["djvu_text"] == "Texto página 1"
    assert pages[2]["djvu_text"] == "Texto página 2"


def test_process_item_llm_called_per_page(tmp_path):
    """When process_prompt_id set and image exists, generate_vision called per page."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = "pmpt_test123"
    client.generate_vision.return_value = '{"page_type": "cover", "summary": "Test"}'

    out_dir = tmp_path / "out"
    # Create fake page images in the expected location
    stem = item.canonical_stem  # e.g. "club-nintendo_1991-01_a01-n01"
    images_dir = out_dir / "1991" / "01" / "images" / stem
    images_dir.mkdir(parents=True)
    (images_dir / "page_0001.jpg").write_bytes(b"fake")
    (images_dir / "page_0002.jpg").write_bytes(b"fake")

    with patch("cnintendo.commands.process.extract_jp2_images") as mock_extract:
        mock_extract.return_value = {
            1: f"images/{stem}/page_0001.jpg",
            2: f"images/{stem}/page_0002.jpg",
        }
        item.jp2_zip = Path("/fake/jp2.zip")
        result = _process_item(item, out_dir, client, force=False, start_page=1)

    assert client.generate_vision.call_count == 2
    data = json.loads(result.read_text())
    assert data["pages"][0]["llm"]["page_type"] == "cover"


def test_process_item_idempotent(tmp_path):
    """Second call does not invoke generate_vision."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = "pmpt_test"
    out_dir = tmp_path / "out"
    _process_item(item, out_dir, client, force=False, start_page=1)
    client.generate_vision.reset_mock()
    _process_item(item, out_dir, client, force=False, start_page=1)
    client.generate_vision.assert_not_called()


def test_process_item_force_reruns(tmp_path):
    """force=True reruns even when file exists."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_djvu_txt=True, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = None
    out_dir = tmp_path / "out"
    _process_item(item, out_dir, client, force=False, start_page=1)
    _process_item(item, out_dir, client, force=True, start_page=1)
    # No crash — file was overwritten


def test_process_item_bad_llm_response(tmp_path):
    """Bad LLM JSON response stores llm=None without crashing."""
    from cnintendo.commands.process import _process_item
    item = make_scan_item(tmp_path, with_scandata=True)
    client = MagicMock()
    client.process_prompt_id = "pmpt_test"
    client.generate_vision.return_value = "Esta página muestra a Mario en un castillo."

    out_dir = tmp_path / "out"
    stem = item.canonical_stem
    img_dir = out_dir / "1991" / "01" / "images" / stem
    img_dir.mkdir(parents=True)
    (img_dir / "page_0001.jpg").write_bytes(b"fake")

    with patch("cnintendo.commands.process.extract_jp2_images") as mock_extract:
        mock_extract.return_value = {1: f"images/{stem}/page_0001.jpg"}
        item.jp2_zip = Path("/fake/jp2.zip")
        result = _process_item(item, out_dir, client, force=False, start_page=1)

    data = json.loads(result.read_text())
    page = data["pages"][0]
    assert page["llm"] is None
