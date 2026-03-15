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
    page_number = 1
    for raw in raw_pages:
        text = raw.strip()
        if text:
            pages.append({"page_number": page_number, "text": text})
            page_number += 1
    return pages


@dataclass
class ScanItem:
    identifier: str
    scan_dir: Path
    pdf: Path
    djvu_txt: Path
    meta_xml: Path
    _meta_cache: dict = field(default_factory=dict, repr=False)

    @property
    def meta(self) -> dict:
        if not self._meta_cache:
            self._meta_cache = parse_meta_xml(self.meta_xml)
        return self._meta_cache

    def to_extracted_dict(self) -> dict:
        """Genera el dict compatible con el formato _extracted.json del pipeline."""
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
        pdf_files = list(subdir.glob("*.pdf"))
        # Excluir _text.pdf (versión de texto del IA, no el scan original)
        pdf_files = [p for p in pdf_files if not p.name.endswith("_text.pdf")]

        if not djvu_files or not meta_files or not pdf_files:
            continue

        items.append(ScanItem(
            identifier=identifier,
            scan_dir=subdir,
            pdf=pdf_files[0],
            djvu_txt=djvu_files[0],
            meta_xml=meta_files[0],
        ))
    return items
