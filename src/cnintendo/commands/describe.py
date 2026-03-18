from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click

from cnintendo.ollama_client import OllamaClient


DESCRIBE_PROMPT = """Describe brevemente en español esta imagen de una revista de videojuegos.
Menciona: qué se ve (personaje, juego, menú, artwork, publicidad, etc.),
colores dominantes, y cualquier texto visible.
Responde en 1-2 oraciones concisas."""


@click.command()
@click.argument("extracted_json", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True)
def describe(extracted_json: Path, output: Optional[Path], force: bool):
    """Genera descripciones de imágenes usando el modelo de visión de Ollama."""
    output = output or extracted_json.parent / extracted_json.name.replace(
        "_extracted.json", "_described.json"
    )

    try:
        raw = json.loads(extracted_json.read_text())
    except Exception as e:
        click.echo(f"Error leyendo JSON extraído: {e}", err=True)
        sys.exit(1)

    # Cargar descripciones existentes para modo incremental
    existing: dict[str, str] = {}
    if output.exists() and not force:
        try:
            existing = json.loads(output.read_text())
        except Exception:
            existing = {}

    # Recopilar rutas de imágenes de todas las páginas
    image_paths: list[str] = []
    for page in raw.get("pages", []):
        image_paths.extend(page.get("images", []))

    if not image_paths:
        click.echo("No se encontraron imágenes en el JSON extraído.", err=True)
        output.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        return

    client = OllamaClient()
    results = dict(existing)
    processed = 0

    for img_path_str in image_paths:
        if img_path_str in results and not force:
            continue
        # Resolve relative to extracted_json.parent
        img_path = Path(img_path_str)
        if not img_path.is_absolute():
            img_path = extracted_json.parent / img_path_str
        if not img_path.exists():
            click.echo(f"  Imagen no encontrada: {img_path}", err=True)
            continue
        click.echo(f"  Describiendo {img_path.name}...", err=True)
        try:
            description = client.generate_vision(
                DESCRIBE_PROMPT, img_path, prompt_id=client.describe_prompt_id, task="describe"
            ).strip()
            results[img_path_str] = description
            processed += 1
        except Exception as e:
            click.echo(f"  Error describiendo {img_path.name}: {e}", err=True)

    output.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    click.echo(f"Descripciones guardadas: {output} ({processed} nuevas)", err=True)
