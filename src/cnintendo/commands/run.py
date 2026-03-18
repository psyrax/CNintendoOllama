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


def _run_scans_pipeline(ctx, scans_dir, data_dir, force, skip_export,
                        with_describe, with_summarize, retry_failed, with_enrich):
    from cnintendo.scan_reader import discover_scans
    from cnintendo.commands.analyze import analyze as analyze_cmd
    from cnintendo.commands.summarize import summarize as summarize_cmd
    from cnintendo.commands.describe import describe as describe_cmd
    from cnintendo.commands.export import export as export_cmd
    from cnintendo.ollama_client import OllamaClient
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

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

    # En modo retry, filtrar solo los items que fallaron anteriormente
    failures = _load_failures(data_dir)
    if retry_failed:
        if not failures:
            console.print("[yellow]No hay fallos registrados en run_failures.json.[/yellow]")
            return
        items = [i for i in all_items if i.identifier in failures]
        console.print(f"[bold]Reintentando {len(items)} items fallidos[/bold] (de {len(all_items)} totales)")
    else:
        items = all_items
        console.print(f"[bold]Encontrados {len(items)} items en {scans_dir}[/bold]")

    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), MofNCompleteColumn(), console=console) as progress:
            task = progress.add_task("Procesando...", total=len(items))

            for item in items:
                stem = item.canonical_stem
                item_dir = extracted_dir / item.output_subdir
                item_dir.mkdir(parents=True, exist_ok=True)
                extracted_json = item_dir / f"{stem}_extracted.json"
                structured_json = item_dir / f"{stem}_structured.json"
                summary_txt = item_dir / f"{stem}_summary.txt"
                described_json = item_dir / f"{stem}_described.json"

                progress.update(task, description=f"[cyan]{item.identifier[:40]}[/cyan]")

                if use_process_pipeline:
                    try:
                        pages_json = _process_item(item, extracted_dir, ollama_client, force=force, start_page=1)
                        progress.update(task, description=f"[cyan]{item.identifier[:40]}[/cyan]")
                        if with_enrich:
                            from cnintendo.commands.enrich import enrich_pages_json, _ollama_base_url, _ollama_model
                            enrich_pages_json(pages_json, _ollama_base_url(), _ollama_model(), force=force)
                        if item.identifier in failures:
                            del failures[item.identifier]
                            _save_failures(data_dir, failures)
                    except Exception as e:
                        msg = f"[process] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "process"
                        _save_failures(data_dir, failures)
                    finally:
                        progress.advance(task)
                    continue  # Skip the old OCR pipeline

                # En retry, forzar re-proceso del paso que falló
                failed_step = failures.get(item.identifier)
                force_extract  = force or (retry_failed and failed_step == "extract")
                force_analyze  = force or (retry_failed and failed_step in ("extract", "analyze"))
                force_summarize = force or (retry_failed and failed_step in ("extract", "analyze", "summarize"))
                force_describe  = force or (retry_failed and failed_step == "describe")

                # Step 1: Extraer texto (tesseract) + limpiar OCR (gemma3n) + guardar por página
                if not extracted_json.exists() or force_extract:
                    try:
                        images_dir = item_dir / "images" / stem
                        extracted_data = item.to_extracted_dict(
                            images_dir=images_dir, base_dir=item_dir,
                            client=ollama_client
                        )
                        # Guardar JSON por página
                        for page in extracted_data.get("pages", []):
                            pn = page["page_number"]
                            page_json = item_dir / f"page_{pn:04d}.json"
                            page_out = {
                                "issue": stem,
                                "page_number": pn,
                                "text_ocr": page.get("text_ocr", ""),
                                "image": page.get("images", [None])[0],
                            }
                            if "text_clean" in page:
                                page_out["text_clean"] = page["text_clean"]
                            page_json.write_text(
                                json.dumps(page_out, indent=2, ensure_ascii=False)
                            )
                        extracted_json.write_text(
                            json.dumps(extracted_data, indent=2, ensure_ascii=False)
                        )
                    except Exception as e:
                        msg = f"[extract] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "extract"
                        _save_failures(data_dir, failures)
                        progress.advance(task)
                        continue

                # Step 2: analyze
                if not structured_json.exists() or force_analyze:
                    try:
                        ctx.invoke(analyze_cmd, extracted_json=extracted_json,
                                   output=structured_json, force=force_analyze, no_clean=False)
                    except (Exception, SystemExit) as e:
                        msg = f"[analyze] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "analyze"
                        _save_failures(data_dir, failures)
                        progress.advance(task)
                        continue

                # Step 3: summarize (optional)
                if with_summarize and structured_json.exists() and (not summary_txt.exists() or force_summarize):
                    try:
                        ctx.invoke(summarize_cmd, structured_json=structured_json,
                                   output=summary_txt, force=force_summarize)
                    except (Exception, SystemExit) as e:
                        msg = f"[summarize] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "summarize"
                        _save_failures(data_dir, failures)

                # Step 4: describe images (optional, slow)
                if with_describe and extracted_json.exists() and (not described_json.exists() or force_describe):
                    try:
                        ctx.invoke(describe_cmd, extracted_json=extracted_json,
                                   output=described_json, force=force_describe)
                    except (Exception, SystemExit) as e:
                        msg = f"[describe] {e}"
                        logger.error(f"{item.identifier} {msg}")
                        failures[item.identifier] = "describe"
                        _save_failures(data_dir, failures)

                # Item completado: eliminar de fallos si estaba ahí
                if item.identifier in failures:
                    del failures[item.identifier]
                    _save_failures(data_dir, failures)

                progress.advance(task)

        if not skip_export:
            console.print("\n[bold]Exportando a SQLite...[/bold]")
            try:
                db_path = data_dir / "output.db"
                ctx.invoke(export_cmd, input_dir=extracted_dir, db=db_path)
                console.print(f"[green]Base de datos:[/green] {db_path}")
            except Exception as e:
                console.print(f"[red]Error en export:[/red] {e}")

        if failures:
            console.print(f"\n[yellow]Completado con {len(failures)} fallo(s).[/yellow] "
                          f"Usa --retry-failed para reintentar. Log: {log_file}")
        else:
            console.print(f"\n[green]Completado sin errores.[/green]")
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
