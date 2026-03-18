from __future__ import annotations
import json
import os
import re
import time
import urllib.request
import warnings
from collections.abc import Callable
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
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        block = re.search(r"\{.*\}", text, re.DOTALL)
        if block:
            text = block.group(0)
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return None
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
    on_page: Callable | None = None,
) -> Path:
    """Enriches a _pages.json file using Ollama. Returns path to _enriched.json.

    on_page(page_number, total_pages, result_dict, elapsed_s, error) called after each page.
    """
    enriched_json = pages_json.with_name(pages_json.name.replace("_pages.json", "_enriched.json"))

    if enriched_json.exists() and not force:
        return enriched_json

    data = json.loads(pages_json.read_text())
    ia_identifier = data.get("ia_identifier", "")
    canonical_stem = data.get("canonical_stem", "")

    enriched_pages = []
    pages = [p for p in data.get("pages", []) if p.get("page_number", 0) >= start_page]
    total = len(pages)

    for page in pages:
        pn = page.get("page_number", 0)
        llm = page.get("llm") or {}

        if not llm:
            entry = {"page_number": pn, "page_type": None, "games": [], "topics": []}
            enriched_pages.append(entry)
            if on_page:
                on_page(pn, total, entry, 0.0, None)
            continue

        prompt = ENRICH_PROMPT.format(
            summary=llm.get("summary") or "",
            text_blocks=json.dumps(llm.get("text_blocks") or [], ensure_ascii=False),
            image_descriptions=json.dumps(llm.get("image_descriptions") or [], ensure_ascii=False),
        )

        t0 = time.monotonic()
        error = None
        parsed = None
        try:
            raw = _call_ollama(prompt, base_url, model)
            parsed = _parse_enrichment(raw)
        except Exception as e:
            error = str(e)
            warnings.warn(f"{ia_identifier} p{pn}: Ollama error: {e}")
        elapsed = time.monotonic() - t0

        entry = {
            "page_number": pn,
            "page_type": parsed["page_type"] if parsed else None,
            "games": parsed["games"] if parsed else [],
            "topics": parsed["topics"] if parsed else [],
        }
        enriched_pages.append(entry)

        if on_page:
            on_page(pn, total, entry, elapsed, error)

    result = {
        "ia_identifier": ia_identifier,
        "canonical_stem": canonical_stem,
        "model": model,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "pages": enriched_pages,
    }
    enriched_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return enriched_json


# ── Page type color mapping ────────────────────────────────────────────────────

_TYPE_STYLE = {
    "cover":     "bold bright_yellow",
    "review":    "bright_green",
    "guide":     "bright_cyan",
    "preview":   "cyan",
    "news":      "bright_blue",
    "top_list":  "bright_magenta",
    "index":     "magenta",
    "ad":        "dim white",
    "hardware":  "blue",
    "editorial": "white",
    "letters":   "dim cyan",
    "contest":   "yellow",
    "other":     "dim white",
}

_TYPE_ICON = {
    "cover":     "★",
    "review":    "◆",
    "guide":     "▶",
    "preview":   "◈",
    "news":      "◉",
    "top_list":  "▲",
    "index":     "≡",
    "ad":        "◻",
    "hardware":  "⊞",
    "editorial": "◇",
    "letters":   "✉",
    "contest":   "⊕",
    "other":     "·",
}


def _type_markup(page_type: str | None) -> str:
    pt = (page_type or "other").lower()
    style = _TYPE_STYLE.get(pt, "dim white")
    icon = _TYPE_ICON.get(pt, "·")
    return f"[{style}]{icon} {pt}[/{style}]"


def _games_markup(games: list[str]) -> str:
    if not games:
        return "[dim]—[/dim]"
    joined = ", ".join(games)
    if len(joined) > 46:
        joined = joined[:43] + "…"
    return f"[bright_green]{joined}[/bright_green]"


def _build_display(
    issue_label: str,
    model: str,
    host: str,
    completed: int,
    total: int,
    scanning_page: int | None,
    log: list[dict],   # [{page, page_type, games, elapsed, error}]
    stats: dict,
    start_ts: float,
) -> "rich.console.RenderableType":
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    from rich.console import Group

    elapsed_total = time.monotonic() - start_ts
    eta_str = "—"
    if completed > 0 and completed < total:
        rate = elapsed_total / completed
        remaining = (total - completed) * rate
        mins, secs = divmod(int(remaining), 60)
        eta_str = f"{mins}m {secs:02d}s"
    pct = int(completed / total * 100) if total else 0
    bar_filled = int(completed / total * 32) if total else 0
    bar = "[bright_cyan]" + "█" * bar_filled + "[/bright_cyan]" + "[dim]" + "░" * (32 - bar_filled) + "[/dim]"

    # ── Header ────────────────────────────────────────────────────────────────
    host_short = host.replace("http://", "").replace("https://", "")
    header = (
        f"[bold bright_cyan]◈ CNINTENDO ENRICHMENT ENGINE ◈[/bold bright_cyan]  "
        f"[bright_white]{model}[/bright_white]  [dim]@[/dim]  [cyan]{host_short}[/cyan]\n"
        f"[dim]ISSUE:[/dim] [bright_white]{issue_label}[/bright_white]\n"
        f"{bar}  [bright_white]{completed}[/bright_white][dim]/{total}[/dim] pages  "
        f"[bright_yellow]{pct}%[/bright_yellow]  "
        f"[dim]ETA:[/dim] [yellow]{eta_str}[/yellow]"
    )

    # ── Page log table ─────────────────────────────────────────────────────────
    table = Table(box=box.SIMPLE_HEAD, show_footer=False, padding=(0, 1))
    table.add_column("PAGE", style="dim", width=6, justify="right")
    table.add_column("TYPE", width=14)
    table.add_column("GAMES DETECTED", width=50)
    table.add_column("TIME", width=7, justify="right")

    # Current scanning row
    if scanning_page is not None and completed < total:
        table.add_row(
            f"[bold bright_yellow]► {scanning_page:03d}[/bold bright_yellow]",
            "[bright_yellow blink]◌ scanning…[/bright_yellow blink]",
            "[dim]…[/dim]",
            "",
        )

    # Recent completed rows (most recent first, show last 12)
    for entry in reversed(log[-12:]):
        pg = entry["page"]
        pt = entry.get("page_type")
        games = entry.get("games", [])
        elapsed = entry.get("elapsed", 0.0)
        err = entry.get("error")

        if err:
            table.add_row(
                f"[dim]{pg:03d}[/dim]",
                "[red]✗ error[/red]",
                f"[red dim]{err[:46]}[/red dim]",
                f"[dim]{elapsed:.1f}s[/dim]",
            )
        else:
            table.add_row(
                f"[dim]{pg:03d}[/dim]",
                _type_markup(pt),
                _games_markup(games),
                f"[dim]{elapsed:.1f}s[/dim]",
            )

    # ── Stats footer ──────────────────────────────────────────────────────────
    total_games = stats.get("total_games", 0)
    unique_games = stats.get("unique_games", 0)
    pages_ok = stats.get("pages_ok", 0)
    pages_err = stats.get("pages_err", 0)
    avg_t = stats.get("avg_time", 0.0)

    footer_parts = [
        f"[bright_green]▸ GAMES INDEXED: {total_games}[/bright_green]",
        f"[cyan]▸ UNIQUE: {unique_games}[/cyan]",
        f"[bright_white]▸ OK: {pages_ok}[/bright_white]",
        f"[dim]▸ AVG: {avg_t:.1f}s/pg[/dim]",
    ]
    if pages_err:
        footer_parts.append(f"[red]▸ ERR: {pages_err}[/red]")
    footer = "  ".join(footer_parts)

    return Panel(
        Group(Text.from_markup(header), table, Text.from_markup(footer)),
        border_style="bright_cyan",
        title="[bold bright_cyan]▓ ENRICHMENT SUBSYSTEM ▓[/bold bright_cyan]",
        title_align="left",
    )


@click.command("enrich")
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--force", is_flag=True, help="Re-procesar aunque ya exista el _enriched.json.")
@click.option("--start-page", default=1, show_default=True, help="Página desde la que comenzar.")
@click.option("--model", default=None, help="Modelo Ollama. Default: OLLAMA_ENRICH_MODEL env var.")
@click.option("--base-url", default=None, help="URL base de Ollama. Default: OLLAMA_BASE_URL env var.")
def enrich(input_path: Path, force: bool, start_page: int, model: Optional[str], base_url: Optional[str]):
    """Enriquece _pages.json con extracción de juegos y tópicos usando Ollama."""
    from rich.live import Live
    from rich.console import Console

    base_url = base_url or _ollama_base_url()
    model = model or _ollama_model()
    console = Console(stderr=True)

    if input_path.is_file():
        if not input_path.name.endswith("_pages.json"):
            console.print("[red]Error: el archivo debe ser un _pages.json[/red]")
            raise SystemExit(1)
        pages_files = [input_path]
    else:
        pages_files = sorted(input_path.rglob("*_pages.json"))

    if not pages_files:
        console.print(f"[red]No se encontraron _pages.json en {input_path}[/red]")
        raise SystemExit(1)

    host_display = base_url.replace("http://", "").replace("https://", "")

    for pages_json in pages_files:
        # Per-issue state
        log: list[dict] = []
        stats = {"total_games": 0, "unique_games": 0, "pages_ok": 0, "pages_err": 0, "avg_time": 0.0}
        all_games: set[str] = set()
        times: list[float] = []
        completed = 0
        scanning_page: int | None = None

        # Count total pages upfront
        raw_data = json.loads(pages_json.read_text())
        total_pages = len([p for p in raw_data.get("pages", []) if p.get("page_number", 0) >= start_page])
        issue_label = raw_data.get("canonical_stem", pages_json.stem)
        start_ts = time.monotonic()

        def on_page(pn: int, total: int, result: dict, elapsed: float, error: str | None):
            nonlocal completed, scanning_page
            log.append({"page": pn, **result, "elapsed": elapsed, "error": error})
            if error:
                stats["pages_err"] += 1
            else:
                stats["pages_ok"] += 1
                games = result.get("games") or []
                stats["total_games"] += len(games)
                all_games.update(games)
                stats["unique_games"] = len(all_games)
                if elapsed > 0:
                    times.append(elapsed)
                    stats["avg_time"] = sum(times) / len(times)
            completed += 1
            scanning_page = pn + 1 if completed < total else None

        # Set scanning_page to first page before starting
        first_pages = [p for p in raw_data.get("pages", []) if p.get("page_number", 0) >= start_page]
        if first_pages:
            scanning_page = first_pages[0].get("page_number")

        with Live(
            _build_display(issue_label, model, host_display, 0, total_pages, scanning_page, log, stats, start_ts),
            console=console,
            refresh_per_second=4,
            vertical_overflow="visible",
        ) as live:
            def on_page_live(pn, total, result, elapsed, error):
                on_page(pn, total, result, elapsed, error)
                live.update(_build_display(
                    issue_label, model, host_display,
                    completed, total_pages, scanning_page,
                    log, stats, start_ts,
                ))

            try:
                enrich_pages_json(pages_json, base_url, model, force=force,
                                  start_page=start_page, on_page=on_page_live)
            except Exception as e:
                console.print(f"[red]ERROR procesando {pages_json.name}: {e}[/red]")
                continue

        # Final summary line
        elapsed_total = time.monotonic() - start_ts
        mins, secs = divmod(int(elapsed_total), 60)
        console.print(
            f"[bright_cyan]✓[/bright_cyan] [bright_white]{issue_label}[/bright_white]  "
            f"[bright_green]{stats['pages_ok']} páginas[/bright_green]  "
            f"[bright_green]{stats['total_games']} juegos[/bright_green] "
            f"[cyan]({stats['unique_games']} únicos)[/cyan]  "
            f"[dim]{mins}m {secs:02d}s[/dim]"
        )
