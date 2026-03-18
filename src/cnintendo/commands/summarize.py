from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click

from cnintendo.models import IssueData
from cnintendo.ollama_client import OllamaClient


SUMMARIZE_PROMPT = """Eres un editor de la revista Club Nintendo. Escribe un resumen editorial en español de este número.

TÍTULO DE LA REVISTA: {title}
NÚMERO DE ARTÍCULOS: {count}

ARTÍCULOS DEL NÚMERO:
{articles_text}

INSTRUCCIONES:
- Escribe un párrafo narrativo de 3-5 oraciones resumiendo el contenido del número.
- Menciona los juegos más destacados, sus plataformas y puntuaciones si las hay.
- Usa un tono editorial entusiasta pero objetivo.
- Responde SOLO con el texto del resumen, sin títulos ni encabezados."""


@click.command()
@click.argument("structured_json", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True)
def summarize(structured_json: Path, output: Optional[Path], force: bool):
    """Genera un resumen narrativo del número de revista usando Ollama."""
    output = output or structured_json.parent / structured_json.name.replace(
        "_structured.json", "_summary.txt"
    )

    if output.exists() and not force:
        click.echo(f"Ya existe {output}, usa --force para regenerar.", err=True)
        return

    try:
        raw = json.loads(structured_json.read_text())
        issue_data = IssueData(**raw)
    except Exception as e:
        click.echo(f"Error leyendo JSON estructurado: {e}", err=True)
        sys.exit(1)

    articles_text = "\n".join(
        f"- [{a.section}] {a.title or a.game or 'Sin título'}"
        f"{f' ({a.platform})' if a.platform else ''}"
        f"{f' — {a.score}/10' if a.score else ''}"
        f"{f': {a.text[:100]}' if a.text else ''}"
        for a in issue_data.articles
    )

    title = issue_data.issue.ia_title or issue_data.issue.filename
    prompt = SUMMARIZE_PROMPT.format(
        title=title,
        count=len(issue_data.articles),
        articles_text=articles_text or "(sin artículos identificados)",
    )

    client = OllamaClient()
    click.echo("Generando resumen...", err=True)
    summary = client.generate(prompt, prompt_id=client.summarize_prompt_id, task="summarize").strip()

    if not summary:
        click.echo("Ollama devolvió respuesta vacía.", err=True)
        sys.exit(1)

    output.write_text(summary, encoding="utf-8")
    click.echo(f"Resumen guardado: {output}", err=True)
