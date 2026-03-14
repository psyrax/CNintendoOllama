from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click
import fitz  # PyMuPDF

from cnintendo.commands.inspect import _detect_pdf_type
from cnintendo.ollama_client import OllamaClient


OCR_PROMPT = (
    "Eres un asistente que extrae texto de imágenes escaneadas de revistas de "
    "videojuegos. Transcribe todo el texto visible en esta página de forma exacta, "
    "manteniendo párrafos y estructura. Solo devuelve el texto, sin comentarios."
)


def _extract_page_native(page: fitz.Page) -> dict:
    """Extrae texto e imágenes de una página con texto nativo."""
    text = page.get_text()
    images = []
    for img_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        images.append({"xref": xref, "index": img_index})
    return {"text": text, "image_count": len(images), "images": images}


def _extract_page_scanned(
    page: fitz.Page, page_num: int, images_dir: Path, client: OllamaClient
) -> dict:
    """Extrae texto de una página escaneada usando Ollama vision."""
    mat = fitz.Matrix(2, 2)  # 2x zoom para mejor OCR
    clip = page.get_pixmap(matrix=mat)
    img_path = images_dir / f"page_{page_num:04d}_ocr.jpg"
    clip.save(str(img_path))

    text = client.generate_vision(OCR_PROMPT, img_path)
    return {"text": text, "image_count": 0, "images": [], "ocr_source": str(img_path)}


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Directorio de salida. Por defecto usa data/extracted/")
@click.option("--force", is_flag=True, help="Re-extrae aunque ya exista el JSON.")
def extract(pdf_path: Path, output_dir: Optional[Path], force: bool):
    """Extrae texto e imágenes de un PDF (nativo o escaneado)."""
    output_dir = output_dir or Path("data/extracted")
    output_dir.mkdir(parents=True, exist_ok=True)

    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    output_json = output_dir / f"{pdf_path.stem}_extracted.json"
    if output_json.exists() and not force:
        click.echo(f"Ya existe {output_json}, usa --force para re-extraer.", err=True)
        return

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        click.echo(f"Error al abrir PDF: {e}", err=True)
        sys.exit(1)

    pdf_type = _detect_pdf_type(doc)
    client = OllamaClient() if pdf_type in ("scanned", "mixed") else None

    pages_data = []
    with click.progressbar(range(len(doc)), label=f"Extrayendo {pdf_path.name}") as bar:
        for i in bar:
            page = doc[i]
            page_text = page.get_text().strip()

            if pdf_type == "scanned" or (pdf_type == "mixed" and len(page_text) < 50):
                page_data = _extract_page_scanned(page, i + 1, images_dir, client)
            else:
                page_data = _extract_page_native(page)

            page_data["page_number"] = i + 1
            pages_data.append(page_data)

    doc.close()

    result = {
        "filename": pdf_path.name,
        "pdf_type": pdf_type,
        "total_pages": len(pages_data),
        "pages": pages_data,
    }

    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    click.echo(f"Extraído: {output_json}", err=True)
