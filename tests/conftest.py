import pytest
from pathlib import Path
import fitz  # PyMuPDF


@pytest.fixture
def sample_native_pdf(tmp_path) -> Path:
    """Crea un PDF nativo simple con texto seleccionable."""
    pdf_path = tmp_path / "test_native.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Super Mario 64 - Review - Score: 97")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_scanned_pdf(tmp_path) -> Path:
    """Crea un PDF de solo imágenes (simula escaneado)."""
    from PIL import Image, ImageDraw
    import io

    pdf_path = tmp_path / "test_scanned.pdf"
    img = Image.new("RGB", (595, 842), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Texto escaneado de prueba", fill="black")

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PDF")
    pdf_path.write_bytes(img_bytes.getvalue())
    return pdf_path
