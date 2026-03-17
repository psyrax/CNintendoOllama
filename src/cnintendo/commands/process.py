from __future__ import annotations
import json
import re
import warnings
from pathlib import Path
from typing import Optional

import click

from cnintendo.models import IssuePages, PageProcessed
from cnintendo.ollama_client import OllamaClient
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
    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _process_item(
    item: ScanItem,
    output_dir: Path,
    client: OllamaClient,
    force: bool,
    start_page: int,
) -> Path:
    """Procesa un ScanItem: extrae imágenes, lee DJVU, llama LLM por página.
    Retorna la ruta al pages_json generado."""
    stem = item.canonical_stem
    item_dir = output_dir / item.output_subdir
    item_dir.mkdir(parents=True, exist_ok=True)
    pages_json = item_dir / f"{stem}_pages.json"

    if pages_json.exists() and not force:
        return pages_json

    meta = item.meta

    # Scandata: page count and page types
    scandata = {}
    if item.scandata_xml and item.scandata_xml.exists():
        try:
            scandata = parse_scandata_xml(item.scandata_xml)
        except Exception as e:
            warnings.warn(f"{item.identifier}: error leyendo scandata: {e}")

    leaf_count = scandata.get("leaf_count", 0)
    page_types: dict[int, str] = scandata.get("page_types", {})

    # DJVU text: per-page text dict
    djvu_pages: dict[int, str] = {}
    if item.djvu_txt and item.djvu_txt.exists():
        try:
            for entry in parse_djvu_text(item.djvu_txt):
                djvu_pages[entry["page_number"]] = entry["text"]
        except Exception as e:
            warnings.warn(f"{item.identifier}: error leyendo djvu_txt: {e}")

    # Image extraction from jp2_zip
    page_images: dict[int, str] = {}
    if item.jp2_zip:
        images_dir = item_dir / "images" / stem
        try:
            page_images = extract_jp2_images(item.jp2_zip, images_dir, item_dir)
        except Exception as e:
            warnings.warn(f"{item.identifier}: error extrayendo imágenes jp2: {e}")

    # Determine total pages: prefer scandata, fallback to max of known pages
    all_page_nums = set(page_images.keys()) | set(djvu_pages.keys())
    total_pages = leaf_count or (max(all_page_nums) if all_page_nums else 0)

    pages: list[PageProcessed] = []
    for page_num in range(start_page, total_pages + 1):
        img_path_str = page_images.get(page_num)
        djvu_text = djvu_pages.get(page_num) or None
        page_type_scan = page_types.get(page_num)

        llm_response = None
        if img_path_str and client.process_prompt_id:
            img_full = item_dir / img_path_str
            if img_full.exists():
                try:
                    raw = client.generate_vision(
                        "",
                        img_full,
                        prompt_id=client.process_prompt_id,
                        task="process",
                    )
                    llm_response = _parse_llm_json(raw)
                except Exception as e:
                    warnings.warn(f"{item.identifier} p{page_num}: error LLM: {e}")

        pages.append(PageProcessed(
            page_number=page_num,
            page_type_scandata=page_type_scan,
            image_path=img_path_str,
            djvu_text=djvu_text,
            llm=llm_response,
        ))

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


@click.command("process")
@click.argument("scan_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Directorio de salida. Default: junto a scan_dir.")
@click.option("--force", is_flag=True, help="Reprocesar aunque ya exista el archivo.")
@click.option("--start-page", default=1, show_default=True,
              help="Página desde la que comenzar (útil para reanudar).")
def process(scan_dir: Path, output: Optional[Path], force: bool, start_page: int):
    """Procesa un directorio de escaneo con visión LLM página por página."""
    output_dir = output or scan_dir.parent / "output"
    client = OllamaClient()

    if not client.is_available():
        click.echo("Error: API key no configurada.", err=True)
        raise SystemExit(1)

    meta_files = list(scan_dir.glob("*_meta.xml"))
    if not meta_files:
        click.echo(f"No se encontró _meta.xml en {scan_dir}", err=True)
        raise SystemExit(1)

    pdf_files = sorted(p for p in scan_dir.glob("*.pdf") if not p.name.endswith("_text.pdf"))
    if not pdf_files:
        click.echo(f"No se encontró PDF en {scan_dir}", err=True)
        raise SystemExit(1)

    jp2_files = list(scan_dir.glob("*_jp2.zip"))
    djvu_xml_files = list(scan_dir.glob("*_djvu.xml"))
    djvu_txt_files = list(scan_dir.glob("*_djvu.txt"))
    scandata_files = list(scan_dir.glob("*_scandata.xml"))

    item = ScanItem(
        identifier=scan_dir.name,
        scan_dir=scan_dir,
        pdf=pdf_files[0],
        djvu_xml=djvu_xml_files[0] if djvu_xml_files else None,
        djvu_txt=djvu_txt_files[0] if djvu_txt_files else None,
        jp2_zip=jp2_files[0] if jp2_files else None,
        scandata_xml=scandata_files[0] if scandata_files else None,
        meta_xml=meta_files[0],
    )
    pages_json = _process_item(item, output_dir, client, force=force, start_page=start_page)
    click.echo(f"Procesado: {pages_json}", err=True)
