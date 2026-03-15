from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


def parse_meta_xml(meta_file: Path) -> dict:
    """Parsea _meta.xml de Internet Archive. Retorna dict con title, date, subjects, identifier."""
    tree = ET.parse(meta_file)
    root = tree.getroot()
    subjects = [el.text for el in root.findall("subject") if el.text]
    return {
        "identifier": (root.findtext("identifier") or "").strip(),
        "title": (root.findtext("title") or "").strip(),
        "date": (root.findtext("date") or "").strip(),
        "subjects": subjects,
    }


def parse_djvu_text(content: str) -> list[dict]:
    """Divide el texto djvu en páginas usando el separador form-feed (\\f).
    Retorna lista de dicts con page_number y text."""
    if not content or not content.strip():
        return []
    raw_pages = content.split("\x0c")
    pages = []
    for physical_page, raw in enumerate(raw_pages, start=1):
        text = raw.strip()
        if text:
            pages.append({"page_number": physical_page, "text": text})
    return pages


@dataclass
class ScanItem:
    identifier: str
    scan_dir: Path
    pdf: Path
    djvu_txt: Path
    meta_xml: Path
    _meta_cache: dict = field(default_factory=dict, repr=False, init=False)

    @property
    def meta(self) -> dict:
        if not self._meta_cache:
            self._meta_cache = parse_meta_xml(self.meta_xml)
        return self._meta_cache

    def to_extracted_dict(self) -> dict:
        """Genera el dict compatible con el formato _extracted.json del pipeline.
        Incluye campos extra de IA (ia_title, ia_date, ia_subjects, ia_identifier)
        no presentes en el formato base de extract.py — el downstream los ignora si no los usa."""
        content = self.djvu_txt.read_text(encoding="utf-8", errors="replace")
        pages = parse_djvu_text(content)
        meta = self.meta
        return {
            "filename": self.pdf.name,
            "total_pages": len(pages),
            "pdf_type": "scanned",
            "pages": pages,
            "ia_title": meta.get("title", ""),
            "ia_date": meta.get("date", ""),
            "ia_subjects": meta.get("subjects", []),
            "ia_identifier": self.identifier,
        }


def discover_scans(scans_dir: Path) -> list[ScanItem]:
    """Descubre y valida todos los items de Internet Archive en scans_dir.
    Un item válido debe tener: _djvu.txt + _meta.xml + al menos un .pdf."""
    items = []
    for subdir in sorted(scans_dir.iterdir()):
        if not subdir.is_dir():
            continue
        identifier = subdir.name
        # Buscar archivos requeridos
        djvu_files = list(subdir.glob("*_djvu.txt"))
        meta_files = list(subdir.glob(f"{identifier}_meta.xml"))
        pdf_files = sorted(p for p in subdir.glob("*.pdf") if not p.name.endswith("_text.pdf"))

        if not djvu_files or not meta_files or not pdf_files:
            continue

        try:
            parse_meta_xml(meta_files[0])
        except ET.ParseError as exc:
            import warnings
            warnings.warn(f"Skipping {identifier}: malformed XML in {meta_files[0]}: {exc}")
            continue

        items.append(ScanItem(
            identifier=identifier,
            scan_dir=subdir,
            pdf=pdf_files[0],
            djvu_txt=djvu_files[0],
            meta_xml=meta_files[0],
        ))
    return items
