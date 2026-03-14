from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from cnintendo.models import Article, IssueData, IssueMetadata
from cnintendo.ollama_client import OllamaClient


ANALYZE_PROMPT_TEMPLATE = """Analiza el siguiente texto extraído de una revista de videojuegos y devuelve un JSON estructurado.

TEXTO POR PÁGINA:
{pages_text}

Devuelve SOLO un objeto JSON válido con esta estructura exacta:
{{
  "articles": [
    {{
      "page": <número de página>,
      "section": <"review"|"preview"|"news"|"editorial"|"unknown">,
      "title": <título del artículo o null>,
      "game": <nombre del juego o null>,
      "platform": <plataforma o null>,
      "score": <puntuación numérica o null>,
      "text": <resumen del texto>,
      "images": []
    }}
  ]
}}

Identifica cada artículo, reseña o sección independiente. Si una página no tiene contenido claro, omítela.
"""


@click.command()
@click.argument("extracted_json", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True)
def analyze(extracted_json: Path, output: Optional[Path], force: bool):
    """Analiza un JSON extraído y estructura los datos usando Ollama."""
    output = output or extracted_json.parent / extracted_json.name.replace(
        "_extracted.json", "_structured.json"
    )

    if output.exists() and not force:
        click.echo(f"Ya existe {output}, usa --force para re-analizar.", err=True)
        return

    try:
        raw_data = json.loads(extracted_json.read_text())
        pages = raw_data["pages"]
    except (json.JSONDecodeError, KeyError) as e:
        click.echo(f"Error leyendo JSON extraído: {e}", err=True)
        sys.exit(1)

    pages_text = "\n\n---\n\n".join(
        f"[Página {p['page_number']}]\n{p['text']}"
        for p in pages
        if p.get("text", "").strip()
    )

    if not pages_text.strip():
        click.echo("No se encontró texto para analizar.", err=True)
        sys.exit(1)

    client = OllamaClient()
    prompt = ANALYZE_PROMPT_TEMPLATE.format(pages_text=pages_text[:8000])

    click.echo("Llamando a Ollama para análisis estructurado...", err=True)
    response = client.generate(prompt)

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as e:
        click.echo(f"Ollama no devolvió JSON válido: {e}", err=True)
        click.echo(f"Respuesta recibida: {response[:500]}", err=True)
        sys.exit(1)

    try:
        articles = [Article(**a) for a in parsed.get("articles", [])]
    except ValidationError as e:
        click.echo(f"Datos de Ollama no coinciden con el esquema: {e}", err=True)
        sys.exit(1)

    try:
        metadata = IssueMetadata(
            filename=raw_data["filename"],
            pages=raw_data["total_pages"],
            type=raw_data.get("pdf_type", "unknown"),
        )
    except KeyError as e:
        click.echo(f"Campo requerido faltante en JSON extraído: {e}", err=True)
        sys.exit(1)
    issue_data = IssueData(issue=metadata, articles=articles)

    output.write_text(issue_data.model_dump_json(indent=2))
    click.echo(f"Analizado: {output} ({len(articles)} artículos)", err=True)
