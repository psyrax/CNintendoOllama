from __future__ import annotations
import json
import re
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import click

from cnintendo.models import IssuePages, PageProcessed
from cnintendo.ollama_client import BillingError, OllamaClient
from cnintendo.scan_reader import (
    ScanItem,
    extract_jp2_images,
    parse_djvu_text,
    parse_scandata_xml,
)


def _parse_llm_json(raw: str) -> dict | None:
    """Parsea respuesta LLM como JSON. Maneja markdown fences. Retorna None si falla."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            result.pop("page_number", None)
            return result
        return None
    except json.JSONDecodeError:
        return None


def _process_item(
    item: ScanItem,
    output_dir: Path,
    client: OllamaClient,
    force: bool,
    start_page: int,
    on_page: Callable | None = None,
) -> Path:
    """Procesa un ScanItem: extrae imágenes, lee DJVU, llama LLM por página.
    Retorna la ruta al pages_json generado.

    on_page(page_num, total_pages, page_processed, elapsed_s, had_llm_call) llamado por página.
    """
    stem = item.canonical_stem
    item_dir = output_dir / item.output_subdir
    item_dir.mkdir(parents=True, exist_ok=True)
    pages_json = item_dir / f"{stem}_pages.json"

    if pages_json.exists() and not force:
        return pages_json

    meta = item.meta

    scandata = {}
    if item.scandata_xml and item.scandata_xml.exists():
        try:
            scandata = parse_scandata_xml(item.scandata_xml)
        except Exception as e:
            warnings.warn(f"{item.identifier}: error leyendo scandata: {e}")

    leaf_count = scandata.get("leaf_count", 0)
    page_types: dict[int, str] = scandata.get("page_types", {})

    djvu_pages: dict[int, str] = {}
    if item.djvu_txt and item.djvu_txt.exists():
        try:
            for entry in parse_djvu_text(item.djvu_txt):
                djvu_pages[entry["page_number"]] = entry["text"]
        except Exception as e:
            warnings.warn(f"{item.identifier}: error leyendo djvu_txt: {e}")

    page_images: dict[int, str] = {}
    if item.jp2_zip:
        images_dir = item_dir / "images" / stem
        try:
            page_images = extract_jp2_images(item.jp2_zip, images_dir, item_dir)
        except Exception as e:
            warnings.warn(f"{item.identifier}: error extrayendo imágenes jp2: {e}")

    all_page_nums = set(page_images.keys()) | set(djvu_pages.keys())
    total_pages = leaf_count or (max(all_page_nums) if all_page_nums else 0)

    pages: list[PageProcessed] = []
    for page_num in range(start_page, total_pages + 1):
        img_path_str = page_images.get(page_num)
        djvu_text = djvu_pages.get(page_num) or None
        page_type_scan = page_types.get(page_num)

        llm_response = None
        had_llm_call = False
        t0 = time.monotonic()

        if img_path_str and client.process_prompt_id:
            img_full = item_dir / img_path_str
            if img_full.exists():
                had_llm_call = True
                try:
                    user_text = (
                        f"Texto DJVU de esta página:\n{djvu_text}\n\nResponde en JSON."
                        if djvu_text
                        else "Analiza esta página y responde en JSON."
                    )
                    raw = client.generate_vision(
                        user_text,
                        img_full,
                        prompt_id=client.process_prompt_id,
                        task="process",
                    )
                    llm_response = _parse_llm_json(raw)
                except Exception as e:
                    warnings.warn(f"{item.identifier} p{page_num}: error LLM: {e}")

        elapsed = time.monotonic() - t0
        page = PageProcessed(
            page_number=page_num,
            page_type_scandata=page_type_scan,
            image_path=img_path_str,
            djvu_text=djvu_text,
            llm=llm_response,
        )
        pages.append(page)

        if on_page:
            on_page(page_num, total_pages, page, elapsed, had_llm_call)

    issue = IssuePages(
        ia_identifier=item.identifier,
        ia_title=meta.get("title"),
        ia_date=meta.get("date"),
        ia_description=meta.get("description"),
        ia_clubnintendo=meta.get("clubnintendo"),
        ia_subjects=meta.get("subjects", []),
        canonical_stem=stem,
        filename=item.pdf.name,
        total_pages=total_pages,
        pages=pages,
    )

    pages_json.write_text(issue.model_dump_json(indent=2))
    return pages_json


def _reprocess_single_page(pages_json: Path, page_number: int, item_dir: Path, client: OllamaClient) -> None:
    """Reprocesa solo una página en un _pages.json existente, actualizando su campo llm in-place."""
    data = json.loads(pages_json.read_text())
    pages = data.get("pages", [])

    page = next((p for p in pages if p["page_number"] == page_number), None)
    if page is None:
        raise click.ClickException(f"Página {page_number} no encontrada en {pages_json.name}")

    img_path_str = page.get("image_path")
    if not img_path_str:
        raise click.ClickException(f"Página {page_number} no tiene image_path — no se puede reprocesar")

    if not client.process_prompt_id:
        raise click.ClickException("OPENAI_PROMPT_ID_PROCESS no está configurado")

    img_full = item_dir / img_path_str
    if not img_full.exists():
        raise click.ClickException(f"Imagen no encontrada: {img_full}")

    djvu_text = page.get("djvu_text")
    user_text = (
        f"Texto DJVU de esta página:\n{djvu_text}\n\nResponde en JSON."
        if djvu_text
        else "Analiza esta página y responde en JSON."
    )

    raw = client.generate_vision(user_text, img_full, prompt_id=client.process_prompt_id, task="process")
    llm_response = _parse_llm_json(raw)
    page["llm"] = llm_response

    pages_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    click.echo(f"Página {page_number} actualizada → llm={'OK' if llm_response else 'null (respuesta inválida)'}", err=True)


# ── Live display helpers ───────────────────────────────────────────────────────

def _summary_preview(llm: dict | None) -> str:
    if not llm:
        return ""
    s = llm.get("summary") or ""
    if len(s) > 52:
        s = s[:49] + "…"
    return s


def _page_type_markup(llm: dict | None, scandata_type: str | None) -> str:
    pt = (llm or {}).get("page_type") or ""
    _STYLE = {
        "cover": "bold bright_yellow", "review": "bright_green",
        "guide": "bright_cyan", "preview": "cyan", "news": "bright_blue",
        "top_list": "bright_magenta", "index": "magenta", "ad": "dim white",
        "hardware": "blue", "editorial": "white", "other": "dim white",
    }
    _ICON = {
        "cover": "★", "review": "◆", "guide": "▶", "preview": "◈",
        "news": "◉", "top_list": "▲", "index": "≡", "ad": "◻",
        "hardware": "⊞", "editorial": "◇", "other": "·",
    }
    if pt:
        style = _STYLE.get(pt, "dim white")
        icon = _ICON.get(pt, "·")
        return f"[{style}]{icon} {pt}[/{style}]"
    if scandata_type:
        return f"[dim]{scandata_type[:10]}[/dim]"
    return "[dim]·[/dim]"


def build_process_display(
    issue_label: str,
    model: str,
    prompt_id: str | None,
    completed: int,
    total: int,
    scanning_page: int | None,
    log: list[dict],
    stats: dict,
    start_ts: float,
) -> "rich.console.RenderableType":
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from rich.console import Group

    elapsed = time.monotonic() - start_ts
    eta_str = "—"
    if completed > 0 and completed < total:
        eta_str_secs = int((elapsed / completed) * (total - completed))
        mins, secs = divmod(eta_str_secs, 60)
        eta_str = f"{mins}m {secs:02d}s"
    pct = int(completed / total * 100) if total else 0
    bar_filled = int(completed / total * 34) if total else 0
    bar = "[bright_cyan]" + "█" * bar_filled + "[/bright_cyan]" + "[dim]" + "░" * (34 - bar_filled) + "[/dim]"

    prompt_label = f"[dim]prompt:[/dim] [cyan]{prompt_id[:16]}…[/cyan]" if prompt_id else "[dim]no prompt[/dim]"
    header = (
        f"[bold bright_cyan]◈ OPENAI VISION PIPELINE ◈[/bold bright_cyan]  "
        f"[bright_white]{model}[/bright_white]  {prompt_label}\n"
        f"[dim]ISSUE:[/dim] [bright_white]{issue_label}[/bright_white]\n"
        f"{bar}  [bright_white]{completed}[/bright_white][dim]/{total}[/dim] pages  "
        f"[bright_yellow]{pct}%[/bright_yellow]  "
        f"[dim]ETA:[/dim] [yellow]{eta_str}[/yellow]"
    )

    table = Table(box=box.SIMPLE_HEAD, show_footer=False, padding=(0, 1))
    table.add_column("PAGE", style="dim", width=6, justify="right")
    table.add_column("TYPE", width=14)
    table.add_column("DJVU", width=5, justify="center")
    table.add_column("SUMMARY", width=52)
    table.add_column("TIME", width=7, justify="right")

    if scanning_page is not None and completed < total:
        table.add_row(
            f"[bold bright_yellow]► {scanning_page:03d}[/bold bright_yellow]",
            "[bright_yellow blink]◌ calling…[/bright_yellow blink]",
            "", "[dim]…[/dim]", "",
        )

    for entry in reversed(log[-12:]):
        pg = entry["page"]
        llm = entry.get("llm")
        scandata_type = entry.get("scandata_type")
        has_djvu = entry.get("has_djvu", False)
        elapsed_p = entry.get("elapsed", 0.0)
        had_llm = entry.get("had_llm", False)
        error = entry.get("error")

        djvu_mark = "[bright_green]✓[/bright_green]" if has_djvu else "[dim]—[/dim]"
        summary = _summary_preview(llm)

        if error:
            table.add_row(f"[dim]{pg:03d}[/dim]", "[red]✗ error[/red]", djvu_mark,
                          f"[red dim]{error[:52]}[/red dim]", f"[dim]{elapsed_p:.1f}s[/dim]")
        elif not had_llm:
            table.add_row(f"[dim]{pg:03d}[/dim]", _page_type_markup(None, scandata_type),
                          djvu_mark, "[dim]no image[/dim]", "[dim]—[/dim]")
        else:
            table.add_row(
                f"[dim]{pg:03d}[/dim]",
                _page_type_markup(llm, scandata_type),
                djvu_mark,
                f"[dim]{summary}[/dim]" if summary else "[dim]—[/dim]",
                f"[dim]{elapsed_p:.1f}s[/dim]",
            )

    llm_ok = stats.get("llm_ok", 0)
    llm_null = stats.get("llm_null", 0)
    with_djvu = stats.get("with_djvu", 0)
    avg_t = stats.get("avg_time", 0.0)
    errors = stats.get("errors", 0)

    footer_parts = [
        f"[bright_white]▸ PAGES: {completed}/{total}[/bright_white]",
        f"[bright_cyan]▸ LLM OK: {llm_ok}[/bright_cyan]",
        f"[cyan]▸ WITH DJVU: {with_djvu}[/cyan]",
        f"[dim]▸ AVG: {avg_t:.1f}s/pg[/dim]",
    ]
    if llm_null:
        footer_parts.append(f"[yellow]▸ NULL: {llm_null}[/yellow]")
    if errors:
        footer_parts.append(f"[red]▸ ERR: {errors}[/red]")

    return Panel(
        Group(Text.from_markup(header), table, Text.from_markup("  ".join(footer_parts))),
        border_style="bright_cyan",
        title="[bold bright_cyan]▓ VISION EXTRACTION ENGINE ▓[/bold bright_cyan]",
        title_align="left",
    )


@click.command("process")
@click.argument("scan_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Directorio de salida. Default: junto a scan_dir.")
@click.option("--force", is_flag=True, help="Reprocesar aunque ya exista el archivo.")
@click.option("--start-page", default=1, show_default=True,
              help="Página desde la que comenzar (útil para reanudar).")
@click.option("--page", "single_page", default=None, type=int,
              help="Reprocesar solo esta página en el JSON existente (sin tocar las demás).")
def process(scan_dir: Path, output: Optional[Path], force: bool, start_page: int, single_page: Optional[int]):
    """Procesa un directorio de escaneo con visión LLM página por página."""
    from rich.live import Live
    from rich.console import Console

    console = Console(stderr=True)
    output_dir = output or scan_dir.parent / "output"
    client = OllamaClient()

    if not client.is_available():
        console.print("[red]Error: API key no configurada.[/red]")
        raise SystemExit(1)

    meta_files = list(scan_dir.glob("*_meta.xml"))
    if not meta_files:
        console.print(f"[red]No se encontró _meta.xml en {scan_dir}[/red]")
        raise SystemExit(1)

    pdf_files = sorted(p for p in scan_dir.glob("*.pdf") if not p.name.endswith("_text.pdf"))
    if not pdf_files:
        console.print(f"[red]No se encontró PDF en {scan_dir}[/red]")
        raise SystemExit(1)

    item = ScanItem(
        identifier=scan_dir.name,
        scan_dir=scan_dir,
        pdf=pdf_files[0],
        djvu_xml=next(iter(scan_dir.glob("*_djvu.xml")), None),
        djvu_txt=next(iter(scan_dir.glob("*_djvu.txt")), None),
        jp2_zip=next(iter(scan_dir.glob("*_jp2.zip")), None),
        scandata_xml=next(iter(scan_dir.glob("*_scandata.xml")), None),
        meta_xml=meta_files[0],
    )

    if single_page is not None:
        stem = item.canonical_stem
        item_dir = output_dir / item.output_subdir
        pages_json = item_dir / f"{stem}_pages.json"
        if not pages_json.exists():
            console.print(f"[red]No existe {pages_json} — corré sin --page primero.[/red]")
            raise SystemExit(1)
        _reprocess_single_page(pages_json, single_page, item_dir, client)
        return

    # ── Live display state ────────────────────────────────────────────────────
    log: list[dict] = []
    stats = {"llm_ok": 0, "llm_null": 0, "with_djvu": 0, "errors": 0, "avg_time": 0.0}
    times: list[float] = []
    completed = 0
    scanning_page: int | None = start_page
    start_ts = time.monotonic()
    issue_label = item.canonical_stem
    model = client.vision_model
    prompt_id = client.process_prompt_id

    def on_page(page_num: int, total: int, page: PageProcessed, elapsed: float, had_llm: bool):
        nonlocal completed, scanning_page
        entry = {
            "page": page_num,
            "llm": page.llm,
            "scandata_type": page.page_type_scandata,
            "has_djvu": bool(page.djvu_text),
            "elapsed": elapsed,
            "had_llm": had_llm,
            "error": None,
        }
        if had_llm:
            if page.llm:
                stats["llm_ok"] += 1
                if elapsed > 0:
                    times.append(elapsed)
                    stats["avg_time"] = sum(times) / len(times)
            else:
                stats["llm_null"] += 1
        if page.djvu_text:
            stats["with_djvu"] += 1
        log.append(entry)
        completed += 1
        scanning_page = page_num + 1 if completed < total else None

    with Live(
        build_process_display(issue_label, model, prompt_id, 0, 1, start_page, log, stats, start_ts),
        console=console,
        refresh_per_second=4,
        vertical_overflow="visible",
    ) as live:
        def on_page_live(page_num, total, page, elapsed, had_llm):
            on_page(page_num, total, page, elapsed, had_llm)
            live.update(build_process_display(
                issue_label, model, prompt_id,
                completed, total, scanning_page, log, stats, start_ts,
            ))

        try:
            pages_json = _process_item(item, output_dir, client, force=force,
                                       start_page=start_page, on_page=on_page_live)
        except BillingError as e:
            from rich.panel import Panel
            live.update(Panel(
                f"[bold red]✗ BILLING / QUOTA ERROR — pipeline detenido[/bold red]\n\n"
                f"[red]{e}[/red]\n\n"
                f"[yellow]Páginas completadas antes del error: {completed}[/yellow]\n"
                f"[dim]Recargá créditos en platform.openai.com y reintentá con --start-page {completed + 1}[/dim]",
                border_style="red",
                title="[bold red]▓ QUOTA EXCEEDED ▓[/bold red]",
            ))
            raise SystemExit(1)

    elapsed_total = time.monotonic() - start_ts
    mins, secs = divmod(int(elapsed_total), 60)
    console.print(
        f"[bright_cyan]✓[/bright_cyan] [bright_white]{issue_label}[/bright_white]  "
        f"[bright_cyan]{stats['llm_ok']} LLM calls[/bright_cyan]  "
        f"[cyan]{stats['with_djvu']} with DJVU[/cyan]  "
        f"[dim]{mins}m {secs:02d}s[/dim]  "
        f"[dim]→[/dim] [bright_white]{pages_json}[/bright_white]"
    )
