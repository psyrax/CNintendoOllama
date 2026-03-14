from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import re

import click
import fitz  # PyMuPDF

from cnintendo.models import IssueMetadata


def _detect_pdf_type(doc: fitz.Document) -> str:
    """Detecta si el PDF tiene texto nativo, es escaneado, o mixto."""
    pages_with_text = 0
    pages_checked = min(len(doc), 5)

    for i in range(pages_checked):
        page = doc[i]
        text = page.get_text().strip()
        if len(text) > 50:
            pages_with_text += 1

    if pages_with_text == 0:
        return "scanned"
    elif pages_with_text == pages_checked:
        return "native"
    else:
        return "mixed"


def _infer_issue_number(filename: str) -> Optional[int]:
    """Intenta inferir el número de issue del nombre de archivo."""
    match = re.search(r"(\d{2,4})", filename)
    if match:
        return int(match.group(1))
    return None


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Ruta del JSON de salida. Por defecto imprime a stdout.")
def inspect(pdf_path: Path, output: Optional[Path]):
    """Inspecciona un PDF y extrae metadatos básicos."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        click.echo(f"Error al abrir PDF: {e}", err=True)
        sys.exit(1)

    pdf_type = _detect_pdf_type(doc)
    number = _infer_issue_number(pdf_path.name)

    metadata = IssueMetadata(
        filename=pdf_path.name,
        pages=len(doc),
        type=pdf_type,
        number=number,
    )
    doc.close()

    json_str = metadata.model_dump_json(indent=2)

    if output:
        output.write_text(json_str)
        click.echo(f"Metadatos guardados en {output}", err=True)
    else:
        click.echo(json_str)
