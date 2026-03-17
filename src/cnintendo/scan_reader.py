from __future__ import annotations
import io
import re
import unicodedata
import warnings
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


def _canonical_stem(ia_title: str, ia_date: str) -> str:
    """Genera un nombre de archivo canónico, legible por humanos y LLMs."""
    date_prefix = ia_date[:7] if ia_date else "0000-00"

    # Número regular: "Club Nintendo Año 01 Nº 02" / "Año 14 N° 07"
    m = re.search(r'[Aa]ño\s+(\d+)\s+[NnNº°][oº°]?\s*(\d+)', ia_title)
    if m:
        año = int(m.group(1))
        num = int(m.group(2))
        return f"club-nintendo_{date_prefix}_a{año:02d}-n{num:02d}"

    # Edición especial
    slug = ia_title
    slug = re.sub(r'^Club Nintendo\s*', '', slug, flags=re.IGNORECASE)
    slug = re.sub(r'Edici[oó]n Especial\s*', 'especial-', slug, flags=re.IGNORECASE)
    slug = re.sub(r'\[Ver\.\s*\d+\]', '', slug)
    slug = re.sub(r'\(M[eé]xico\)', '', slug)
    slug = unicodedata.normalize("NFD", slug)
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'[^a-zA-Z0-9\s]', ' ', slug)
    slug = re.sub(r'\s+', '-', slug.strip()).lower().strip('-')
    slug = re.sub(r'-+', '-', slug)[:50]
    return f"club-nintendo_{date_prefix}_{slug}"


def _output_subdir(ia_date: str) -> str:
    """Retorna subdirectorio YYYY/MM basado en ia_date."""
    parts = (ia_date or "").split("-")
    year = parts[0] if parts and parts[0].isdigit() else "0000"
    month = f"{int(parts[1]):02d}" if len(parts) > 1 and parts[1].isdigit() else "00"
    return f"{year}/{month}"


def parse_meta_xml(meta_file: Path) -> dict:
    """Parsea _meta.xml de Internet Archive. Retorna dict con title, date, subjects, identifier."""
    tree = ET.parse(meta_file)
    root = tree.getroot()
    subjects = [el.text for el in root.findall("subject") if el.text]

    import re as _re_local
    desc_el = root.find("description")
    if desc_el is not None:
        desc_raw = ET.tostring(desc_el, encoding="unicode", method="xml")
        # Remove outer <description>...</description> wrapper
        desc_raw = _re_local.sub(r'^<description[^>]*>', '', desc_raw).rstrip()
        desc_raw = _re_local.sub(r'</description>$', '', desc_raw)
        description = _re_local.sub(r'<[^>]+>', ' ', desc_raw).strip()
        description = _re_local.sub(r'\s+', ' ', description).strip() or None
    else:
        description = None

    clubnintendo = (root.findtext("clubnintendo") or "").strip() or None

    return {
        "identifier": (root.findtext("identifier") or "").strip(),
        "title": (root.findtext("title") or "").strip(),
        "date": (root.findtext("date") or "").strip(),
        "subjects": subjects,
        "description": description,
        "clubnintendo": clubnintendo,
    }


CLEAN_OCR_PROMPT = (
    "Eres un corrector de OCR para revistas en español de los años 90. "
    "Corrige errores de reconocimiento de caracteres (letras confundidas, palabras rotas, símbolos extraños). "
    "REGLA CRÍTICA: No inventes, no parafrasees, no agregues nada. "
    "Si no estás seguro de una corrección, deja el texto como está. "
    "Devuelve solo el texto corregido:\n\n{text}"
)


def _clean_ocr_text(client, text: str) -> str:
    """Limpia texto OCR usando gemma3n. Retorna original si falla o alucina."""
    if not text or not text.strip():
        return text
    try:
        result = client.generate(
            CLEAN_OCR_PROMPT.format(text=text),
            model=client.clean_model,
            prompt_id=client.clean_prompt_id,
            task="clean",
        ).strip()
        # Detectar alucinaciones: ratio muy diferente al original
        ratio = len(result) / max(len(text), 1)
        if not result or ratio < 0.5 or ratio > 2.0:
            return text
        return result
    except Exception:
        return text


def ocr_jp2_zip(jp2_zip: Path, images_dir: Path, base_dir: Path, client=None) -> list[dict]:
    """Extrae imágenes de _jp2.zip, hace OCR con tesseract a full resolución.
    Guarda JPEGs a 1024px para el paso de describe. Retorna pages list."""
    import pytesseract
    from PIL import Image

    images_dir.mkdir(parents=True, exist_ok=True)
    pages = []

    with zipfile.ZipFile(jp2_zip) as zf:
        jp2_names = sorted(n for n in zf.namelist() if n.endswith(".jp2"))
        for jp2_name in jp2_names:
            m = re.search(r'_(\d+)\.jp2$', jp2_name)
            if not m:
                continue
            page_num = int(m.group(1))

            try:
                with zf.open(jp2_name) as f:
                    img = Image.open(io.BytesIO(f.read()))
                    img.load()

                # OCR a full resolución en escala de grises
                gray = img.convert("L")
                text_ocr = pytesseract.image_to_string(gray, lang="spa").strip()

                # Limpiar OCR con LLM si hay cliente disponible
                text_clean = _clean_ocr_text(client, text_ocr) if client else None

                # Guardar JPEG reducido para describe
                img_path = images_dir / f"page_{page_num:04d}.jpg"
                img.thumbnail((1024, 1024), Image.LANCZOS)
                img.convert("RGB").save(str(img_path), "JPEG", quality=85)

                rel_path = str(img_path.relative_to(base_dir))
                page = {
                    "page_number": page_num,
                    "text_ocr": text_ocr,
                    "images": [rel_path],
                }
                if text_clean is not None:
                    page["text_clean"] = text_clean
                pages.append(page)
            except Exception as e:
                warnings.warn(f"Error procesando {jp2_name}: {e}")

    return sorted(pages, key=lambda p: p["page_number"])


def extract_jp2_images(jp2_zip: Path, images_dir: Path, base_dir: Path) -> dict[int, str]:
    """Extrae imágenes de _jp2.zip, las convierte a JPEG redimensionadas a max 1024px.
    Retorna {page_number: relative_path_str}."""
    from PIL import Image

    images_dir.mkdir(parents=True, exist_ok=True)
    page_images: dict[int, str] = {}

    with zipfile.ZipFile(jp2_zip) as zf:
        jp2_names = sorted(n for n in zf.namelist() if n.endswith(".jp2"))
        for jp2_name in jp2_names:
            # Extraer número de página del nombre: ..._0001.jp2
            m = re.search(r'_(\d+)\.jp2$', jp2_name)
            if not m:
                continue
            page_num = int(m.group(1))
            img_path = images_dir / f"page_{page_num:04d}.jpg"

            try:
                with zf.open(jp2_name) as f:
                    img = Image.open(io.BytesIO(f.read()))
                    img.load()
                    # Redimensionar a max 1024px manteniendo aspecto
                    img.thumbnail((1024, 1024), Image.LANCZOS)
                    img.convert("RGB").save(str(img_path), "JPEG", quality=85)
                page_images[page_num] = str(img_path.relative_to(base_dir))
            except Exception as e:
                warnings.warn(f"Error extrayendo {jp2_name}: {e}")

    return page_images


@dataclass
class ScanItem:
    identifier: str
    scan_dir: Path
    pdf: Path
    djvu_xml: Path | None
    djvu_txt: Path | None
    jp2_zip: Path | None
    meta_xml: Path
    _meta_cache: dict = field(default_factory=dict, repr=False, init=False)

    @property
    def meta(self) -> dict:
        if not self._meta_cache:
            self._meta_cache = parse_meta_xml(self.meta_xml)
        return self._meta_cache

    @property
    def canonical_stem(self) -> str:
        meta = self.meta
        return _canonical_stem(meta.get("title", ""), meta.get("date", ""))

    @property
    def output_subdir(self) -> str:
        return _output_subdir(self.meta.get("date", ""))

    @property
    def date_sort_key(self) -> tuple[int, int]:
        date = self.meta.get("date", "")
        parts = date.split("-")
        year = int(parts[0]) if parts and parts[0].isdigit() else 9999
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (year, month)

    def to_extracted_dict(self, images_dir: Path | None = None, base_dir: Path | None = None, client=None) -> dict:
        """Genera el dict del pipeline. Usa tesseract sobre jp2.zip como fuente principal."""
        meta = self.meta
        pages = []
        text_source = "none"

        # Prioridad 1: OCR con tesseract sobre jp2.zip (máxima calidad)
        if images_dir is not None and base_dir is not None and self.jp2_zip and self.jp2_zip.exists():
            try:
                pages = ocr_jp2_zip(self.jp2_zip, images_dir, base_dir, client=client)
                text_source = "tesseract_jp2"
            except Exception as e:
                warnings.warn(f"{self.identifier}: error en OCR jp2: {e}")

        # Fallback: renderizar PDF con fitz + tesseract
        if not pages and images_dir is not None and base_dir is not None:
            try:
                import fitz, pytesseract
                from PIL import Image as PILImage
                images_dir.mkdir(parents=True, exist_ok=True)
                doc = fitz.open(str(self.pdf))
                try:
                    for i in range(len(doc)):
                        pn = i + 1
                        pixmap = doc[i].get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = PILImage.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                        text = pytesseract.image_to_string(img.convert("L"), lang="spa").strip()
                        img_path = images_dir / f"page_{pn:04d}.jpg"
                        img.thumbnail((1024, 1024), PILImage.LANCZOS)
                        img.save(str(img_path), "JPEG", quality=85)
                        pages.append({"page_number": pn, "text": text, "images": [str(img_path.relative_to(base_dir))]})
                finally:
                    doc.close()
                text_source = "tesseract_pdf"
            except Exception as e:
                warnings.warn(f"{self.identifier}: error en OCR PDF: {e}")

        return {
            "filename": self.pdf.name,
            "total_pages": len(pages),
            "pdf_type": "scanned",
            "text_source": text_source,
            "pages": pages,
            "ia_title": meta.get("title", ""),
            "ia_date": meta.get("date", ""),
            "ia_subjects": meta.get("subjects", []),
            "ia_identifier": self.identifier,
        }


def discover_scans(scans_dir: Path) -> list[ScanItem]:
    """Descubre todos los items de Internet Archive en scans_dir.
    Requiere: _meta.xml + al menos un .pdf. djvu.xml/txt y jp2.zip son opcionales pero preferidos."""
    items = []
    for subdir in sorted(scans_dir.iterdir()):
        if not subdir.is_dir():
            continue
        identifier = subdir.name

        meta_files = list(subdir.glob(f"{identifier}_meta.xml"))
        pdf_files = sorted(p for p in subdir.glob("*.pdf") if not p.name.endswith("_text.pdf"))

        if not meta_files or not pdf_files:
            continue

        try:
            parse_meta_xml(meta_files[0])
        except ET.ParseError as exc:
            warnings.warn(f"Skipping {identifier}: malformed XML in {meta_files[0]}: {exc}")
            continue

        djvu_xml_files = list(subdir.glob("*_djvu.xml"))
        djvu_txt_files = list(subdir.glob("*_djvu.txt"))
        jp2_zip_files = list(subdir.glob("*_jp2.zip"))

        # Requiere jp2.zip o pdf para OCR
        if not jp2_zip_files and not pdf_files:
            continue

        items.append(ScanItem(
            identifier=identifier,
            scan_dir=subdir,
            pdf=pdf_files[0],
            djvu_xml=djvu_xml_files[0] if djvu_xml_files else None,
            djvu_txt=djvu_txt_files[0] if djvu_txt_files else None,
            jp2_zip=jp2_zip_files[0] if jp2_zip_files else None,
            meta_xml=meta_files[0],
        ))
    return items
