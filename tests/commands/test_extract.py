import json
import pytest
from click.testing import CliRunner
from cnintendo.cli import main
from pathlib import Path


def test_extract_native_pdf(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    assert result.exit_code == 0
    json_files = list(output_dir.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert "pages" in data
    assert len(data["pages"]) == 1
    assert "text" in data["pages"][0]


def test_extract_creates_images_dir(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    assert (output_dir / "images" / sample_native_pdf.stem).exists()


def test_extract_text_content(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "out"
    runner = CliRunner()
    runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    json_files = list(output_dir.glob("*.json"))
    data = json.loads(json_files[0].read_text())
    all_text = " ".join(p["text"] for p in data["pages"])
    assert "Super Mario" in all_text


def test_extract_idempotent(sample_native_pdf, tmp_path):
    """Second run without --force should skip re-extraction."""
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    runner.invoke(main, ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)])
    json_files = list(output_dir.glob("*.json"))
    first_mtime = json_files[0].stat().st_mtime

    # Second run — should skip
    runner.invoke(main, ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)])
    assert json_files[0].stat().st_mtime == first_mtime  # file not modified


def test_extract_force_overwrites(sample_native_pdf, tmp_path):
    """--force should re-extract even if JSON already exists."""
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    runner.invoke(main, ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)])
    json_files = list(output_dir.glob("*.json"))
    first_mtime = json_files[0].stat().st_mtime

    import time
    time.sleep(0.01)  # ensure mtime differs

    runner.invoke(main, ["extract", str(sample_native_pdf), "--output-dir", str(output_dir), "--force"])
    assert json_files[0].stat().st_mtime > first_mtime  # file was updated
