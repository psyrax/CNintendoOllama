from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import track

from cnintendo.commands.inspect import _detect_pdf_type, _infer_issue_number
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


def _run_scans_pipeline(ctx, scans_dir, data_dir, force, skip_export, with_describe, with_summarize):
    from cnintendo.scan_reader import discover_scans
    from cnintendo.commands.analyze import analyze as analyze_cmd
    from cnintendo.commands.summarize import summarize as summarize_cmd
    from cnintendo.commands.describe import describe as describe_cmd
    from cnintendo.commands.export import export as export_cmd
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    log_file = data_dir / "run_errors.log"
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(logging.ERROR)
    logger = logging.getLogger("cnintendo.run")
    # Avoid duplicate handlers (important for tests that run multiple invocations)
    logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
    logger.addHandler(file_handler)
    logger.setLevel(logging.ERROR)

    items = discover_scans(scans_dir)
    console.print(f"[bold]Encontrados {len(items)} items en {scans_dir}[/bold]")

    try:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      BarColumn(), MofNCompleteColumn(), console=console) as progress:
            task = progress.add_task("Procesando...", total=len(items))

            for item in items:
                stem = item.pdf.stem
                extracted_json = extracted_dir / f"{stem}_extracted.json"
                structured_json = extracted_dir / f"{stem}_structured.json"
                summary_txt = extracted_dir / f"{stem}_summary.txt"
                described_json = extracted_dir / f"{stem}_described.json"

                progress.update(task, description=f"[cyan]{item.identifier[:40]}[/cyan]")

                # Step 1: Extraer texto desde djvu.txt
                if not extracted_json.exists() or force:
                    try:
                        extracted_data = item.to_extracted_dict()
                        extracted_json.write_text(
                            json.dumps(extracted_data, indent=2, ensure_ascii=False)
                        )
                    except Exception as e:
                        logger.error(f"{item.identifier} extract: {e}")
                        progress.advance(task)
                        continue

                # Step 2: analyze
                if not structured_json.exists() or force:
                    try:
                        ctx.invoke(analyze_cmd, extracted_json=extracted_json,
                                   output=structured_json, force=force, no_clean=False)
                    except (Exception, SystemExit) as e:
                        logger.error(f"{item.identifier} analyze: {e}")
                        progress.advance(task)
                        continue

                # Step 3: summarize (optional)
                if with_summarize and structured_json.exists() and (not summary_txt.exists() or force):
                    try:
                        ctx.invoke(summarize_cmd, structured_json=structured_json,
                                   output=summary_txt, force=force)
                    except (Exception, SystemExit) as e:
                        logger.error(f"{item.identifier} summarize: {e}")

                # Step 4: describe images (optional, slow)
                if with_describe and extracted_json.exists() and (not described_json.exists() or force):
                    try:
                        ctx.invoke(describe_cmd, extracted_json=extracted_json,
                                   output=described_json, force=force)
                    except (Exception, SystemExit) as e:
                        logger.error(f"{item.identifier} describe: {e}")

                progress.advance(task)

        if not skip_export:
            console.print("\n[bold]Exportando a SQLite...[/bold]")
            try:
                db_path = data_dir / "output.db"
                ctx.invoke(export_cmd, input_dir=extracted_dir, db=db_path)
                console.print(f"[green]Base de datos:[/green] {db_path}")
            except Exception as e:
                console.print(f"[red]Error en export:[/red] {e}")

        console.print(f"\n[green]Completado.[/green] Errores (si hay): {log_file}")
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
def run(ctx: click.Context, pdf_dir: Optional[Path], data_dir: Optional[Path],
        force: bool, skip_export: bool, scans_dir: Optional[Path],
        with_describe: bool, with_summarize: bool):
    """Ejecuta el pipeline completo sobre una carpeta de PDFs."""
    data_dir = data_dir or Path("data")

    if scans_dir:
        _run_scans_pipeline(ctx, scans_dir, data_dir, force, skip_export, with_describe, with_summarize)
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
