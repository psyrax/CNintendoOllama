import pytest
import json
from click.testing import CliRunner
from cnintendo.cli import main
from pathlib import Path


def test_inspect_native_pdf(sample_native_pdf):
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", str(sample_native_pdf)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["filename"] == sample_native_pdf.name
    assert data["pages"] == 1
    assert data["type"] in ("native", "mixed")


def test_inspect_outputs_json_file(sample_native_pdf, tmp_path):
    output_path = tmp_path / "meta.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["inspect", str(sample_native_pdf), "--output", str(output_path)]
    )
    assert result.exit_code == 0
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "pages" in data


def test_inspect_invalid_file():
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "nonexistent.pdf"])
    assert result.exit_code != 0


def test_inspect_scanned_pdf(sample_scanned_pdf):
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", str(sample_scanned_pdf)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["type"] == "scanned"
