from __future__ import annotations
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


@click.command()
@click.pass_context
@click.argument("pdf_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--data-dir", type=click.Path(path_type=Path), default=None,
              help="Directorio base para datos intermedios y output. Por defecto: data/")
@click.option("--force", is_flag=True, help="Re-procesa aunque existan archivos intermedios.")
@click.option("--skip-export", is_flag=True, help="No ejecuta la exportación a SQLite al final.")
def run(ctx: click.Context, pdf_dir: Path, data_dir: Optional[Path], force: bool, skip_export: bool):
    """Ejecuta el pipeline completo sobre una carpeta de PDFs."""
    from cnintendo.commands.extract import extract as extract_cmd
    from cnintendo.commands.analyze import analyze as analyze_cmd
    from cnintendo.commands.export import export as export_cmd

    data_dir = data_dir or Path("data")
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
