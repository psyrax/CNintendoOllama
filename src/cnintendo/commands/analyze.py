from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from cnintendo.models import Article, IssueData, IssueMetadata
from cnintendo.ollama_client import OllamaClient


ANALYZE_PROMPT_TEMPLATE = """Analiza el siguiente texto extraído de una revista de videojuegos.

TEXTO POR PÁGINA:
{pages_text}

INSTRUCCIONES ESTRICTAS:
- Responde ÚNICAMENTE con el objeto JSON, sin texto adicional, sin markdown, sin bloques de código.
- No uses ``` ni ```json. Solo el JSON puro.
- Los campos "game" y "platform" deben ser strings simples (no listas), toma el juego/plataforma principal.
- Si hay varios juegos en una página, crea un artículo separado por cada juego relevante.

Estructura exacta requerida:
{{"articles": [{{"page": <int>, "section": <"review"|"preview"|"news"|"editorial"|"unknown">, "title": <string o null>, "game": <string o null>, "platform": <string o null>, "score": <número o null>, "text": <resumen breve>, "images": []}}]}}

Identifica cada artículo o reseña independiente. Omite páginas sin contenido claro."""

CLEAN_TEXT_PROMPT = """Corrige y mejora el siguiente texto extraído de una revista de videojuegos en español.

TEXTO ORIGINAL:
{text}

INSTRUCCIONES:
- Corrige errores de OCR (letras mal reconocidas, palabras cortadas, caracteres extraños).
- Asegúrate de que el texto esté en español correcto y sea fluido y legible.
- Mantén el significado y la información original, no inventes datos.
- Devuelve ÚNICAMENTE el texto corregido, sin explicaciones ni comentarios."""


def _strip_fences(response: str) -> str:
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response, re.DOTALL)
    return fence_match.group(1) if fence_match else response


def _clean_article_text(client: OllamaClient, text: str) -> str:
    if not text or not text.strip():
        return text
    prompt = CLEAN_TEXT_PROMPT.format(text=text)
    result = client.generate(prompt)
    return result.strip() or text


@click.command()
@click.argument("extracted_json", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True)
@click.option("--no-clean", is_flag=True, help="Omitir paso de corrección de texto.")
def analyze(extracted_json: Path, output: Optional[Path], force: bool, no_clean: bool):
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

    cleaned = _strip_fences(response.strip())

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        click.echo(f"Ollama no devolvió JSON válido: {e}", err=True)
        click.echo(f"Respuesta recibida: {response[:500]}", err=True)
        sys.exit(1)

    # Normalize fields that models sometimes return as lists
    raw_articles = parsed.get("articles", [])
    for a in raw_articles:
        if isinstance(a.get("game"), list):
            a["game"] = ", ".join(a["game"]) if a["game"] else None
        if isinstance(a.get("platform"), list):
            a["platform"] = ", ".join(a["platform"]) if a["platform"] else None
        # Normalizar images: list[str] → list[{"path": str, "description": None}]
        raw_images = a.get("images", [])
        normalized_images = []
        for img in raw_images:
            if isinstance(img, str):
                normalized_images.append({"path": img, "description": None})
            elif isinstance(img, dict) and "path" in img:
                normalized_images.append(img)
        a["images"] = normalized_images

    try:
        articles = [Article(**a) for a in raw_articles]
    except ValidationError as e:
        click.echo(f"Datos de Ollama no coinciden con el esquema: {e}", err=True)
        sys.exit(1)

    if not no_clean:
        click.echo(f"Corrigiendo texto de {len(articles)} artículos...", err=True)
        for i, article in enumerate(articles):
            if article.text:
                article.text = _clean_article_text(client, article.text)
                click.echo(f"  [{i+1}/{len(articles)}] {article.title or article.game or 'artículo'}", err=True)

    try:
        metadata = IssueMetadata(
            filename=raw_data["filename"],
            pages=raw_data["total_pages"],
            type=raw_data.get("pdf_type", "unknown"),
            ia_title=raw_data.get("ia_title"),
            ia_date=raw_data.get("ia_date"),
            ia_subjects=raw_data.get("ia_subjects", []),
            ia_identifier=raw_data.get("ia_identifier"),
        )
    except KeyError as e:
        click.echo(f"Campo requerido faltante en JSON extraído: {e}", err=True)
        sys.exit(1)
    issue_data = IssueData(issue=metadata, articles=articles)

    output.write_text(issue_data.model_dump_json(indent=2))
    click.echo(f"Analizado: {output} ({len(articles)} artículos)", err=True)
