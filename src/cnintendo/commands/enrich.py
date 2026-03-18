from __future__ import annotations
import json
import os
import re
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from dotenv import load_dotenv


def _ollama_base_url() -> str:
    load_dotenv(override=False)
    return os.getenv("OLLAMA_BASE_URL", "http://192.168.50.113:11434")


def _ollama_model() -> str:
    load_dotenv(override=False)
    return os.getenv("OLLAMA_ENRICH_MODEL", "gemma3:4b")


ENRICH_PROMPT = """\
Eres un extractor de información para una revista de videojuegos de los años 90 (Club Nintendo, México).

Dado el contenido de una página de revista, extrae:
1. Todos los videojuegos mencionados (títulos exactos tal como aparecen, en Title Case)
2. Tópicos que describen el tipo y contenido de la página

Para page_type usa exactamente uno de: cover|ad|editorial|guide|review|preview|news|top_list|hardware|letters|contest|index|other
Para topics usa términos de esta lista: portada, editorial, publicidad, guía, trucos, reseña, preview, top_10, noticias, hardware, accesorios, carta_lectores, concurso, sumario, otro

Responde SOLO en JSON con este formato exacto:
{{
  "page_type": "<tipo>",
  "games": ["Título Juego 1", "Título Juego 2"],
  "topics": ["tópico1", "tópico2"]
}}

--- CONTENIDO DE LA PÁGINA ---
Resumen: {summary}

Bloques de texto: {text_blocks}

Descripciones visuales: {image_descriptions}
---

Responde únicamente con el JSON, sin texto adicional."""


def _call_ollama(prompt: str, base_url: str, model: str, timeout: int = 180) -> str:
    """Calls Ollama generate API. Returns raw response text."""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode()).get("response", "")


def _parse_enrichment(raw: str) -> dict | None:
    """Extracts JSON from Ollama response, handling think tags and fences."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Strip <think>...</think> blocks (lfm2.5-thinking style)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Find outermost JSON object
        block = re.search(r"\{.*\}", text, re.DOTALL)
        if block:
            text = block.group(0)
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return None
        # Normalize: ensure expected keys with safe defaults
        return {
            "page_type": result.get("page_type") or "other",
            "games": [g for g in (result.get("games") or []) if isinstance(g, str) and g.strip()],
            "topics": [t for t in (result.get("topics") or []) if isinstance(t, str) and t.strip()],
        }
    except (json.JSONDecodeError, Exception):
        return None


def enrich_pages_json(
    pages_json: Path,
    base_url: str,
    model: str,
    force: bool = False,
    start_page: int = 1,
) -> Path:
    """Enriches a _pages.json file using Ollama. Returns path to _enriched.json."""
    enriched_json = pages_json.with_name(pages_json.name.replace("_pages.json", "_enriched.json"))

    if enriched_json.exists() and not force:
        return enriched_json

    data = json.loads(pages_json.read_text())
    ia_identifier = data.get("ia_identifier", "")
    canonical_stem = data.get("canonical_stem", "")

    enriched_pages = []
    pages = data.get("pages", [])

    for page in pages:
        pn = page.get("page_number", 0)
        if pn < start_page:
            continue

        llm = page.get("llm") or {}
        if not llm:
            enriched_pages.append({"page_number": pn, "page_type": None, "games": [], "topics": []})
            continue

        prompt = ENRICH_PROMPT.format(
            summary=llm.get("summary") or "",
            text_blocks=json.dumps(llm.get("text_blocks") or [], ensure_ascii=False),
            image_descriptions=json.dumps(llm.get("image_descriptions") or [], ensure_ascii=False),
        )

        try:
            raw = _call_ollama(prompt, base_url, model)
            parsed = _parse_enrichment(raw)
        except Exception as e:
            warnings.warn(f"{ia_identifier} p{pn}: Ollama error: {e}")
            parsed = None

        enriched_pages.append({
            "page_number": pn,
            "page_type": parsed["page_type"] if parsed else None,
            "games": parsed["games"] if parsed else [],
            "topics": parsed["topics"] if parsed else [],
        })

    result = {
        "ia_identifier": ia_identifier,
        "canonical_stem": canonical_stem,
        "model": model,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "pages": enriched_pages,
    }
    enriched_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return enriched_json


@click.command("enrich")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--force", is_flag=True, help="Re-procesar aunque ya exista el _enriched.json.")
@click.option("--start-page", default=1, show_default=True,
              help="Página desde la que comenzar.")
@click.option("--model", default=None, help="Modelo Ollama a usar. Default: OLLAMA_ENRICH_MODEL env var.")
@click.option("--base-url", default=None, help="URL base de Ollama. Default: OLLAMA_BASE_URL env var.")
def enrich(input_path: Path, force: bool, start_page: int, model: Optional[str], base_url: Optional[str]):
    """Enriquece _pages.json con extracción de juegos y tópicos usando Ollama."""
    base_url = base_url or _ollama_base_url()
    model = model or _ollama_model()

    # Discover pages.json files
    if input_path.is_file():
        if not input_path.name.endswith("_pages.json"):
            click.echo(f"Error: el archivo debe ser un _pages.json", err=True)
            raise SystemExit(1)
        pages_files = [input_path]
    else:
        pages_files = sorted(input_path.rglob("*_pages.json"))

    if not pages_files:
        click.echo(f"No se encontraron _pages.json en {input_path}", err=True)
        raise SystemExit(1)

    click.echo(f"Enriqueciendo {len(pages_files)} archivo(s) con {model} @ {base_url}", err=True)

    for pages_json in pages_files:
        click.echo(f"  {pages_json.name}...", err=True, nl=False)
        try:
            enriched = enrich_pages_json(pages_json, base_url, model, force=force, start_page=start_page)
            data = json.loads(enriched.read_text())
            n_pages = len(data.get("pages", []))
            n_with_games = sum(1 for p in data["pages"] if p.get("games"))
            click.echo(f" {n_pages} páginas, {n_with_games} con juegos → {enriched.name}", err=True)
        except Exception as e:
            click.echo(f" ERROR: {e}", err=True)
