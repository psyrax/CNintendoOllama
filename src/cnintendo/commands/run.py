from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import track

from cnintendo.commands.inspect import _detect_pdf_type, _infer_issue_number
from cnintendo.commands.process import _process_item
from cnintendo.models import IssueMetadata

console = Console(stderr=True)


def _run_inspect(pdf: Path, metadata_json: Path) -> bool:
    """Runs the inspect step, returns True on success."""
    import fitz
    doc = fitz.open(str(pdf))
    try:
        pdf_type = _detect_pdf_type(doc)
        number = _infer_issue_number(pdf.name)
        metadata = IssueMetadata(filename=pdf.name, pages=len(doc), type=pdf_type, number=number)
    except Exception as e:
        console.print(f"  [red]Error en inspect:[/red] {e}")
        return False
    finally:
        doc.close()
    metadata_json.write_text(metadata.model_dump_json(indent=2))
    return True


def _load_failures(data_dir: Path) -> dict[str, str]:
    """Carga el registro de fallos previos. Retorna {identifier: step}."""
    failures_file = data_dir / "run_failures.json"
    if failures_file.exists():
        try:
            return json.loads(failures_file.read_text())
        except Exception:
            pass
    return {}


def _save_failures(data_dir: Path, failures: dict[str, str]) -> None:
    """Persiste el registro de fallos en run_failures.json."""
    failures_file = data_dir / "run_failures.json"
    if failures:
        failures_file.write_text(json.dumps(failures, indent=2, ensure_ascii=False))
    elif failures_file.exists():
        failures_file.unlink()


def _build_run_display(
    total_items: int,
    done_items: int,
    current_issue: str,
    page_done: int,
    page_total: int,
    issue_log: list[dict],
    global_stats: dict,
    start_ts: float,
) -> "rich.console.RenderableType":
    import time as _time
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from rich.console import Group

    elapsed = _time.monotonic() - start_ts
    eta_str = "—"
    if done_items > 0 and done_items < total_items:
        secs_left = int((elapsed / done_items) * (total_items - done_items))
        h, rem = divmod(secs_left, 3600)
        m, s = divmod(rem, 60)
        eta_str = f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

    pct = int(done_items / total_items * 100) if total_items else 0
    bar_filled = int(done_items / total_items * 32) if total_items else 0
    bar = "[bright_cyan]" + "█" * bar_filled + "[/bright_cyan]" + "[dim]" + "░" * (32 - bar_filled) + "[/dim]"

    # Inner page bar
    if page_total > 0:
        pg_filled = int(page_done / page_total * 28)
        pg_bar = "[cyan]" + "▪" * pg_filled + "[/cyan]" + "[dim]" + "·" * (28 - pg_filled) + "[/dim]"
        pg_pct = int(page_done / page_total * 100)
        page_line = (
            f"  [dim]▶[/dim] [bright_white]{current_issue}[/bright_white]\n"
            f"  {pg_bar}  [white]{page_done}[/white][dim]/{page_total}[/dim] pages  "
            f"[yellow]{pg_pct}%[/yellow]"
        )
    else:
        page_line = f"  [dim]▶[/dim] [bright_white]{current_issue}[/bright_white]  [dim]preparing…[/dim]"

    header = (
        f"[bold bright_cyan]◈ CNINTENDO FULL PIPELINE ◈[/bold bright_cyan]  "
        f"[bright_white]{total_items}[/bright_white] [dim]issues[/dim]\n"
        f"{bar}  [bright_white]{done_items}[/bright_white][dim]/{total_items}[/dim] issues  "
        f"[bright_yellow]{pct}%[/bright_yellow]  [dim]ETA:[/dim] [yellow]{eta_str}[/yellow]\n"
        f"{page_line}"
    )

    table = Table(box=box.SIMPLE_HEAD, show_footer=False, padding=(0, 1))
    table.add_column("ISSUE", width=42)
    table.add_column("STATUS", width=10)
    table.add_column("PAGES", width=7, justify="right")
    table.add_column("LLM", width=6, justify="right")
    table.add_column("TIME", width=8, justify="right")

    for entry in reversed(issue_log[-10:]):
        status = entry.get("status", "done")
        pages = entry.get("pages", 0)
        llm_ok = entry.get("llm_ok", 0)
        t = entry.get("elapsed", 0.0)
        mins_e, secs_e = divmod(int(t), 60)
        time_str = f"{mins_e}m{secs_e:02d}s"

        if status == "error":
            status_m = "[red]✗ error[/red]"
            label_m = f"[red dim]{entry['issue'][:42]}[/red dim]"
        elif status == "skipped":
            status_m = "[dim]↷ skip[/dim]"
            label_m = f"[dim]{entry['issue'][:42]}[/dim]"
        else:
            status_m = "[bright_green]✓ done[/bright_green]"
            label_m = f"[bright_white]{entry['issue'][:42]}[/bright_white]"

        table.add_row(label_m, status_m, f"[dim]{pages}[/dim]",
                      f"[bright_cyan]{llm_ok}[/bright_cyan]", f"[dim]{time_str}[/dim]")

    total_pages = global_stats.get("total_pages", 0)
    total_llm = global_stats.get("total_llm", 0)
    errors = global_stats.get("errors", 0)
    avg_t = global_stats.get("avg_issue_time", 0.0)

    footer_parts = [
        f"[bright_white]▸ ISSUES: {done_items}/{total_items}[/bright_white]",
        f"[bright_cyan]▸ PAGES: {total_pages}[/bright_cyan]",
        f"[cyan]▸ LLM CALLS: {total_llm}[/cyan]",
        f"[dim]▸ AVG: {avg_t:.0f}s/issue[/dim]",
    ]
    if errors:
        footer_parts.append(f"[red]▸ ERRORS: {errors}[/red]")

    return Panel(
        Group(Text.from_markup(header), table, Text.from_markup("  ".join(footer_parts))),
        border_style="bright_cyan",
        title="[bold bright_cyan]▓ PIPELINE CONTROLLER ▓[/bold bright_cyan]",
        title_align="left",
    )


def _run_scans_pipeline(ctx, scans_dir, data_dir, force, skip_export,
                        with_describe, with_summarize, retry_failed, with_enrich):
    import time as _time
    from rich.live import Live
    from cnintendo.scan_reader import discover_scans
    from cnintendo.commands.analyze import analyze as analyze_cmd
    from cnintendo.commands.summarize import summarize as summarize_cmd
    from cnintendo.commands.describe import describe as describe_cmd
    from cnintendo.commands.export import export as export_cmd
    from cnintendo.ollama_client import OllamaClient

    ollama_client = OllamaClient()
    use_process_pipeline = bool(ollama_client.process_prompt_id)

    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    log_file = data_dir / "run_errors.log"
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    file_handler.setLevel(logging.ERROR)
    logger = logging.getLogger("cnintendo.run")
    logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
    logger.addHandler(file_handler)
    logger.setLevel(logging.ERROR)

    all_items = sorted(discover_scans(scans_dir), key=lambda i: i.date_sort_key)

    failures = _load_failures(data_dir)
    if retry_failed:
        if not failures:
            console.print("[yellow]No hay fallos registrados en run_failures.json.[/yellow]")
            return
        items = [i for i in all_items if i.identifier in failures]
    else:
        items = all_items

    # ── Live display state ────────────────────────────────────────────────────
    issue_log: list[dict] = []
    global_stats = {"total_pages": 0, "total_llm": 0, "errors": 0, "avg_issue_time": 0.0}
    issue_times: list[float] = []
    done_items = 0
    page_done = 0
    page_total = 0
    current_issue = items[0].canonical_stem if items else ""
    start_ts = _time.monotonic()

    try:
        with Live(
            _build_run_display(len(items), 0, current_issue, 0, 0, issue_log, global_stats, start_ts),
            console=console,
            refresh_per_second=4,
            vertical_overflow="visible",
        ) as live:

            def refresh():
                live.update(_build_run_display(
                    len(items), done_items, current_issue,
                    page_done, page_total, issue_log, global_stats, start_ts,
                ))

            for item in items:
                nonlocal_page_done = [0]
                nonlocal_page_total = [0]

                stem = item.canonical_stem
                item_dir = extracted_dir / item.output_subdir
                item_dir.mkdir(parents=True, exist_ok=True)

                # Update current issue label
                current_issue = stem
                page_done = 0
                page_total = 0
                refresh()

                issue_t0 = _time.monotonic()

                if use_process_pipeline:
                    llm_ok_this = [0]

                    def on_page_run(page_num, total, page, elapsed, had_llm):
                        nonlocal page_done, page_total
                        page_total = total
                        page_done = page_num - 1 + 1  # completed count
                        if had_llm and page.llm:
                            llm_ok_this[0] += 1
                        refresh()

                    try:
                        pages_json = _process_item(
                            item, extracted_dir, ollama_client,
                            force=force, start_page=1, on_page=on_page_run,
                        )
                        if with_enrich:
                            from cnintendo.commands.enrich import enrich_pages_json, _ollama_base_url, _ollama_model
                            enrich_pages_json(pages_json, _ollama_base_url(), _ollama_model(), force=force)
                        if item.identifier in failures:
                            del failures[item.identifier]
                            _save_failures(data_dir, failures)
                        issue_elapsed = _time.monotonic() - issue_t0
                        issue_times.append(issue_elapsed)
                        global_stats["avg_issue_time"] = sum(issue_times) / len(issue_times)
                        global_stats["total_pages"] += page_total
                        global_stats["total_llm"] += llm_ok_this[0]
                        issue_log.append({
                            "issue": stem, "status": "done",
                            "pages": page_total, "llm_ok": llm_ok_this[0],
                            "elapsed": issue_elapsed,
                        })
                    except Exception as e:
                        msg = f"[process] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "process"
                        _save_failures(data_dir, failures)
                        global_stats["errors"] += 1
                        issue_log.append({
                            "issue": stem, "status": "error",
                            "pages": 0, "llm_ok": 0,
                            "elapsed": _time.monotonic() - issue_t0,
                        })

                    done_items += 1
                    refresh()
                    continue  # Skip the old OCR pipeline

                # Old OCR pipeline (extract → analyze → summarize → describe)
                extracted_json = item_dir / f"{stem}_extracted.json"
                structured_json = item_dir / f"{stem}_structured.json"
                summary_txt = item_dir / f"{stem}_summary.txt"
                described_json = item_dir / f"{stem}_described.json"

                failed_step = failures.get(item.identifier)
                force_extract   = force or (retry_failed and failed_step == "extract")
                force_analyze   = force or (retry_failed and failed_step in ("extract", "analyze"))
                force_summarize = force or (retry_failed and failed_step in ("extract", "analyze", "summarize"))
                force_describe  = force or (retry_failed and failed_step == "describe")

                step_ok = True
                if not extracted_json.exists() or force_extract:
                    try:
                        images_dir = item_dir / "images" / stem
                        extracted_data = item.to_extracted_dict(
                            images_dir=images_dir, base_dir=item_dir, client=ollama_client
                        )
                        for page in extracted_data.get("pages", []):
                            pn = page["page_number"]
                            page_json = item_dir / f"page_{pn:04d}.json"
                            page_out = {"issue": stem, "page_number": pn,
                                        "text_ocr": page.get("text_ocr", ""),
                                        "image": page.get("images", [None])[0]}
                            if "text_clean" in page:
                                page_out["text_clean"] = page["text_clean"]
                            page_json.write_text(json.dumps(page_out, indent=2, ensure_ascii=False))
                        extracted_json.write_text(json.dumps(extracted_data, indent=2, ensure_ascii=False))
                    except Exception as e:
                        logger.error(f"{item.identifier} [extract] {e}")
                        failures[item.identifier] = "extract"
                        _save_failures(data_dir, failures)
                        global_stats["errors"] += 1
                        issue_log.append({"issue": stem, "status": "error", "pages": 0,
                                          "llm_ok": 0, "elapsed": _time.monotonic() - issue_t0})
                        done_items += 1
                        refresh()
                        step_ok = False

                if step_ok:
                    if not structured_json.exists() or force_analyze:
                        try:
                            ctx.invoke(analyze_cmd, extracted_json=extracted_json,
                                       output=structured_json, force=force_analyze, no_clean=False)
                        except (Exception, SystemExit) as e:
                            logger.error(f"{item.identifier} [analyze] {e}")
                            failures[item.identifier] = "analyze"
                            _save_failures(data_dir, failures)
                            global_stats["errors"] += 1
                            issue_log.append({"issue": stem, "status": "error", "pages": 0,
                                              "llm_ok": 0, "elapsed": _time.monotonic() - issue_t0})
                            done_items += 1
                            refresh()
                            step_ok = False

                if step_ok:
                    if with_summarize and structured_json.exists() and (not summary_txt.exists() or force_summarize):
                        try:
                            ctx.invoke(summarize_cmd, structured_json=structured_json,
                                       output=summary_txt, force=force_summarize)
                        except (Exception, SystemExit) as e:
                            logger.error(f"{item.identifier} [summarize] {e}")
                            failures[item.identifier] = "summarize"
                            _save_failures(data_dir, failures)

                    if with_describe and extracted_json.exists() and (not described_json.exists() or force_describe):
                        try:
                            ctx.invoke(describe_cmd, extracted_json=extracted_json,
                                       output=described_json, force=force_describe)
                        except (Exception, SystemExit) as e:
                            logger.error(f"{item.identifier} [describe] {e}")
                            failures[item.identifier] = "describe"
                            _save_failures(data_dir, failures)

                    if item.identifier in failures:
                        del failures[item.identifier]
                        _save_failures(data_dir, failures)
                    issue_elapsed = _time.monotonic() - issue_t0
                    issue_times.append(issue_elapsed)
                    global_stats["avg_issue_time"] = sum(issue_times) / len(issue_times)
                    issue_log.append({"issue": stem, "status": "done", "pages": 0,
                                      "llm_ok": 0, "elapsed": issue_elapsed})
                    done_items += 1
                    refresh()

        if not skip_export:
            console.print("\n[bold bright_cyan]▓ Exportando a SQLite...[/bold bright_cyan]")
            try:
                db_path = data_dir / "output.db"
                ctx.invoke(export_cmd, input_dir=extracted_dir, db=db_path)
                console.print(f"[bright_green]✓ Base de datos:[/bright_green] [bright_white]{db_path}[/bright_white]")
            except Exception as e:
                console.print(f"[red]Error en export:[/red] {e}")

        elapsed_total = _time.monotonic() - start_ts
        h, rem = divmod(int(elapsed_total), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"
        if failures:
            console.print(
                f"\n[yellow]Completado con {len(failures)} fallo(s).[/yellow] "
                f"Usa --retry-failed para reintentar. Log: {log_file}"
            )
        else:
            console.print(
                f"\n[bright_green]✓ Pipeline completado sin errores[/bright_green]  "
                f"[dim]{global_stats['total_pages']} páginas  {global_stats['total_llm']} LLM calls  {time_str}[/dim]"
            )
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()


@click.command()
@click.pass_context
@click.argument("pdf_dir", type=click.Path(file_okay=False, path_type=Path), required=False, default=None)
@click.option("--data-dir", type=click.Path(path_type=Path), default=None,
              help="Directorio base para datos intermedios y output. Por defecto: data/")
@click.option("--force", is_flag=True, help="Re-procesa aunque existan archivos intermedios.")
@click.option("--skip-export", is_flag=True, help="No ejecuta la exportación a SQLite al final.")
@click.option("--scans-dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None, help="Directorio con subdirectorios de Internet Archive.")
@click.option("--with-describe", is_flag=True,
              help="Ejecuta descripción de imágenes (requiere modelo de visión, lento).")
@click.option("--with-summarize/--no-summarize", default=True,
              help="Genera resumen narrativo de cada número.")
@click.option("--retry-failed", is_flag=True,
              help="Re-procesa solo los items que fallaron en la última ejecución.")
@click.option("--with-enrich", is_flag=True,
              help="Ejecuta enriquecimiento con Ollama (juegos y tópicos) después del proceso.")
def run(ctx: click.Context, pdf_dir: Optional[Path], data_dir: Optional[Path],
        force: bool, skip_export: bool, scans_dir: Optional[Path],
        with_describe: bool, with_summarize: bool, retry_failed: bool, with_enrich: bool):
    """Ejecuta el pipeline completo sobre una carpeta de PDFs."""
    data_dir = data_dir or Path("data")

    if scans_dir:
        _run_scans_pipeline(ctx, scans_dir, data_dir, force, skip_export,
                            with_describe, with_summarize, retry_failed, with_enrich)
        return

    if pdf_dir is None:
        click.echo("Error: Se requiere pdf_dir o --scans-dir.", err=True)
        ctx.exit(1)
        return

    from cnintendo.commands.extract import extract as extract_cmd
    from cnintendo.commands.analyze import analyze as analyze_cmd
    from cnintendo.commands.export import export as export_cmd

    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        click.echo(f"No se encontraron PDFs en {pdf_dir}", err=True)
        return

    console.print(f"[bold]Procesando {len(pdf_files)} PDF(s)[/bold] desde {pdf_dir}")

    for pdf in track(pdf_files, description="Procesando...", console=console):
        stem = pdf.stem
        metadata_json = extracted_dir / f"{stem}_metadata.json"
        extracted_json = extracted_dir / f"{stem}_extracted.json"
        structured_json = extracted_dir / f"{stem}_structured.json"

        console.print(f"\n[cyan]{pdf.name}[/cyan]")

        # Step 1: inspect
        if not metadata_json.exists() or force:
            if not _run_inspect(pdf, metadata_json):
                continue
            console.print(f"  inspect ✓")
        else:
            console.print(f"  [yellow]inspect: ya existe[/yellow]")

        # Step 2: extract
        if not extracted_json.exists() or force:
            try:
                ctx.invoke(extract_cmd, pdf_path=pdf, output_dir=extracted_dir, force=force)
                console.print(f"  extract ✓")
            except Exception as e:
                console.print(f"  [red]Error en extract:[/red] {e}")
                continue
        else:
            console.print(f"  [yellow]extract: ya existe[/yellow]")

        # Step 3: analyze
        if not structured_json.exists() or force:
            try:
                ctx.invoke(analyze_cmd, extracted_json=extracted_json, output=structured_json, force=force)
                console.print(f"  analyze ✓")
            except Exception as e:
                console.print(f"  [red]Error en analyze:[/red] {e}")
                continue
        else:
            console.print(f"  [yellow]analyze: ya existe[/yellow]")

        console.print(f"  [green]✓ Completado[/green]")

    # Step 4: export
    if not skip_export:
        console.print("\n[bold]Exportando a SQLite...[/bold]")
        try:
            db_path = data_dir / "output.db"
            ctx.invoke(export_cmd, input_dir=extracted_dir, db=db_path)
            console.print(f"[green]Base de datos:[/green] {db_path}")
        except Exception as e:
            console.print(f"[red]Error en export:[/red] {e}")
