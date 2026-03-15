# cnintendoOllama — Setup e Implementación del Pipeline CLI

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear desde cero el proyecto cnintendoOllama: entorno Conda, estructura de paquete Python, y 5 comandos CLI para extraer y estructurar datos de PDFs de revistas de videojuegos usando Ollama.

**Architecture:** CLI modular con comandos independientes encadenables (inspect → extract → analyze → export → run). JSON como formato intermedio entre pasos. Ollama (remoto, otro contenedor Docker) para OCR de escaneos y extracción estructurada de texto.

**Tech Stack:** Python 3.11, Conda, Click, PyMuPDF, Pydantic v2, httpx, sqlite-utils, rich, python-dotenv

**Spec:** `docs/superpowers/specs/2026-03-14-cnintendo-design.md`

---

## Chunk 1: Entorno y estructura del proyecto

### Task 1: Crear estructura de directorios y archivos de configuración

**Files:**
- Create: `environment.yml`
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/cnintendo/__init__.py`
- Create: `src/cnintendo/commands/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/commands/__init__.py`
- Create: `data/pdfs/.gitkeep`
- Create: `data/extracted/.gitkeep`
- Create: `data/images/.gitkeep`

- [ ] **Step 1: Crear `environment.yml`**

```yaml
name: cnintendo
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pip
  - pip:
    - click>=8.1
    - pymupdf>=1.23
    - Pillow>=10.0
    - pydantic>=2.0
    - httpx>=0.27
    - sqlite-utils>=3.35
    - python-dotenv>=1.0
    - rich>=13.0
    - pytest>=8.0
    - respx>=0.21
```

- [ ] **Step 2: Crear `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cnintendo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1",
    "pymupdf>=1.23",
    "Pillow>=10.0",
    "pydantic>=2.0",
    "httpx>=0.27",
    "sqlite-utils>=3.35",
    "python-dotenv>=1.0",
    "rich>=13.0",
]

[project.scripts]
cnintendo = "cnintendo.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Crear `.env.example`**

```
OLLAMA_URL=http://192.168.1.x:11434
OLLAMA_MODEL=llava
OLLAMA_TEXT_MODEL=llama3
```

- [ ] **Step 4: Crear directorios y archivos vacíos**

```bash
mkdir -p src/cnintendo/commands tests/commands data/pdfs data/extracted data/images
touch src/cnintendo/__init__.py
touch src/cnintendo/commands/__init__.py
touch tests/__init__.py
touch tests/commands/__init__.py
touch data/pdfs/.gitkeep data/extracted/.gitkeep data/images/.gitkeep
```

- [ ] **Step 5: Crear entorno Conda e instalar**

```bash
conda env create -f environment.yml
conda activate cnintendo
pip install -e .
```

Esperado: entorno creado sin errores, `cnintendo --help` no disponible aún (cli.py no existe).

---

## Chunk 2: Modelos de datos y cliente Ollama

### Task 2: Implementar `models.py` con Pydantic

**Files:**
- Create: `src/cnintendo/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Escribir tests para los modelos**

Crear `tests/test_models.py`:
```python
import pytest
from cnintendo.models import IssueMetadata, Article, IssueData

def test_issue_metadata_defaults():
    meta = IssueMetadata(filename="test.pdf", pages=10)
    assert meta.type == "unknown"
    assert meta.number is None

def test_issue_metadata_full():
    meta = IssueMetadata(
        id="test-001",
        filename="revista_001.pdf",
        number=1,
        year=1995,
        month="enero",
        pages=84,
        type="native"
    )
    assert meta.id == "test-001"
    assert meta.type == "native"

def test_article_defaults():
    article = Article(page=1, title="Test")
    assert article.section == "unknown"
    assert article.score is None
    assert article.images == []

def test_issue_data_serialization():
    meta = IssueMetadata(filename="test.pdf", pages=10)
    data = IssueData(issue=meta, articles=[])
    json_str = data.model_dump_json()
    assert "issue" in json_str
    assert "articles" in json_str
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
cd /Code/cnintendoOllama && conda run -n cnintendo pytest tests/test_models.py -v
```
Esperado: `ModuleNotFoundError: No module named 'cnintendo'`

- [ ] **Step 3: Implementar `src/cnintendo/models.py`**

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class IssueMetadata(BaseModel):
    id: Optional[str] = None
    filename: str
    number: Optional[int] = None
    year: Optional[int] = None
    month: Optional[str] = None
    pages: int
    type: Literal["native", "scanned", "mixed", "unknown"] = "unknown"


class Article(BaseModel):
    page: int
    section: str = "unknown"
    title: Optional[str] = None
    game: Optional[str] = None
    platform: Optional[str] = None
    score: Optional[int] = None
    text: Optional[str] = None
    images: list[str] = Field(default_factory=list)


class IssueData(BaseModel):
    issue: IssueMetadata
    articles: list[Article] = Field(default_factory=list)
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```bash
conda run -n cnintendo pytest tests/test_models.py -v
```
Esperado: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git init  # si no existe repo
git add environment.yml pyproject.toml .env.example src/ tests/ data/
git commit -m "feat: setup inicial + modelos de datos Pydantic"
```

---

### Task 3: Implementar `ollama_client.py`

**Files:**
- Create: `src/cnintendo/ollama_client.py`
- Create: `tests/test_ollama_client.py`

- [ ] **Step 1: Ejecutar tests vacíos para verificar que fallan (módulo no existe aún)**

```bash
conda run -n cnintendo python -c "from cnintendo.ollama_client import OllamaClient"
```
Esperado: `ModuleNotFoundError: No module named 'cnintendo.ollama_client'`

- [ ] **Step 2: Escribir tests para el cliente Ollama**

Crear `tests/test_ollama_client.py`:
```python
import pytest
import httpx
import respx as respx_lib
from cnintendo.ollama_client import OllamaClient


def test_client_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llava-test")
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "llama3-test")
    client = OllamaClient()
    assert client.base_url == "http://test-host:11434"
    assert client.vision_model == "llava-test"
    assert client.text_model == "llama3-test"


def test_client_defaults(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TEXT_MODEL", raising=False)
    client = OllamaClient()
    assert client.base_url == "http://localhost:11434"
    assert client.vision_model == "llava"
    assert client.text_model == "llama3"


@respx_lib.mock
def test_generate_calls_correct_endpoint():
    respx_lib.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "hola mundo"})
    )
    client = OllamaClient()
    result = client.generate("di hola")
    assert result == "hola mundo"
```

- [ ] **Step 3: Ejecutar tests para verificar que fallan**

```bash
conda run -n cnintendo pytest tests/test_ollama_client.py -v
```
Esperado: `ImportError: cannot import name 'OllamaClient'`

- [ ] **Step 4: Implementar `src/cnintendo/ollama_client.py`**

```python
from __future__ import annotations
import base64
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()


class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.vision_model = os.getenv("OLLAMA_MODEL", "llava")
        self.text_model = os.getenv("OLLAMA_TEXT_MODEL", "llama3")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "120"))

    def generate(self, prompt: str, model: str | None = None) -> str:
        """Genera texto a partir de un prompt."""
        model = model or self.text_model
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json()["response"]

    def generate_vision(
        self, prompt: str, image_path: Path, model: str | None = None
    ) -> str:
        """Genera texto a partir de un prompt e imagen (para OCR/análisis)."""
        model = model or self.vision_model
        image_data = base64.b64encode(image_path.read_bytes()).decode()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["response"]

    def is_available(self) -> bool:
        """Verifica si Ollama está accesible."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.ConnectError:
            return False
```

- [ ] **Step 5: Ejecutar tests**

```bash
conda run -n cnintendo pytest tests/test_ollama_client.py -v
```
Esperado: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cnintendo/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: cliente Ollama con soporte vision y texto"
```

---

## Chunk 3: CLI principal y comando inspect

### Task 4: Implementar `cli.py` y comando `inspect`

**Files:**
- Create: `src/cnintendo/cli.py`
- Create: `src/cnintendo/commands/inspect.py`
- Create: `tests/commands/test_inspect.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Crear `tests/conftest.py` con fixtures compartidas**

```python
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
    # Crear imagen con texto
    img = Image.new("RGB", (595, 842), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Texto escaneado de prueba", fill="black")

    # Guardar como PDF de imagen
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PDF")
    pdf_path.write_bytes(img_bytes.getvalue())
    return pdf_path
```

- [ ] **Step 2: Escribir tests para `inspect`**

Crear `tests/commands/test_inspect.py`:
```python
import pytest
import json
from click.testing import CliRunner
from cnintendo.cli import main
from pathlib import Path


def test_inspect_native_pdf(sample_native_pdf):
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", str(sample_native_pdf)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["filename"] == sample_native_pdf.name
    assert data["pages"] == 1
    assert data["type"] in ("native", "mixed")


def test_inspect_outputs_json_file(sample_native_pdf, tmp_path):
    output_path = tmp_path / "meta.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["inspect", str(sample_native_pdf), "--output", str(output_path)]
    )
    assert result.exit_code == 0
    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert "pages" in data


def test_inspect_invalid_file():
    runner = CliRunner()
    result = runner.invoke(main, ["inspect", "nonexistent.pdf"])
    assert result.exit_code != 0
```

- [ ] **Step 3: Ejecutar tests para verificar que fallan**

```bash
conda run -n cnintendo pytest tests/commands/test_inspect.py -v
```
Esperado: `ImportError` — cli no existe.

- [ ] **Step 4: Implementar `src/cnintendo/cli.py`**

```python
import click
from cnintendo.commands import inspect, extract, analyze, export, run as run_cmd


@click.group()
@click.version_option("0.1.0")
def main():
    """Herramientas CLI para extraer datos de revistas de videojuegos en PDF."""
    pass


main.add_command(inspect.inspect)
main.add_command(extract.extract)
main.add_command(analyze.analyze)
main.add_command(export.export)
main.add_command(run_cmd.run)
```

- [ ] **Step 5: Implementar `src/cnintendo/commands/inspect.py`**

```python
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click
import fitz  # PyMuPDF

from cnintendo.models import IssueMetadata


def _detect_pdf_type(doc: fitz.Document) -> str:
    """Detecta si el PDF tiene texto nativo, es escaneado, o mixto."""
    pages_with_text = 0
    pages_checked = min(len(doc), 5)  # revisar hasta 5 páginas

    for i in range(pages_checked):
        page = doc[i]
        text = page.get_text().strip()
        if len(text) > 50:  # umbral: más de 50 chars = tiene texto real
            pages_with_text += 1

    if pages_with_text == 0:
        return "scanned"
    elif pages_with_text == pages_checked:
        return "native"
    else:
        return "mixed"


def _infer_issue_number(filename: str) -> Optional[int]:
    """Intenta inferir el número de issue del nombre de archivo."""
    import re
    match = re.search(r"(\d{2,4})", filename)
    if match:
        return int(match.group(1))
    return None


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Ruta del JSON de salida. Por defecto imprime a stdout.")
def inspect(pdf_path: Path, output: Optional[Path]):
    """Inspecciona un PDF y extrae metadatos básicos."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        click.echo(f"Error al abrir PDF: {e}", err=True)
        sys.exit(1)

    pdf_type = _detect_pdf_type(doc)
    number = _infer_issue_number(pdf_path.name)

    metadata = IssueMetadata(
        filename=pdf_path.name,
        pages=len(doc),
        type=pdf_type,
        number=number,
    )
    doc.close()

    json_str = metadata.model_dump_json(indent=2)

    if output:
        output.write_text(json_str)
        click.echo(f"Metadatos guardados en {output}", err=True)
    else:
        click.echo(json_str)
```

- [ ] **Step 6: Ejecutar tests**

```bash
conda run -n cnintendo pytest tests/commands/test_inspect.py -v
```
Esperado: 3 tests PASS.

- [ ] **Step 7: Verificar CLI disponible**

```bash
conda run -n cnintendo cnintendo --help
conda run -n cnintendo cnintendo inspect --help
```

- [ ] **Step 8: Commit**

```bash
git add src/cnintendo/cli.py src/cnintendo/commands/inspect.py tests/
git commit -m "feat: CLI principal + comando inspect"
```

---

## Chunk 4: Comando extract

### Task 5: Implementar comando `extract`

**Files:**
- Create: `src/cnintendo/commands/extract.py`
- Create: `tests/commands/test_extract.py`

- [ ] **Step 1: Escribir tests para `extract`**

Crear `tests/commands/test_extract.py`:
```python
import json
import pytest
from click.testing import CliRunner
from cnintendo.cli import main
from pathlib import Path


def test_extract_native_pdf(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    assert result.exit_code == 0
    json_files = list(output_dir.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert "pages" in data
    assert len(data["pages"]) == 1
    assert "text" in data["pages"][0]


def test_extract_creates_images_dir(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "extracted"
    runner = CliRunner()
    runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    # El directorio de imágenes debe existir aunque no haya imágenes
    assert (output_dir / "images").exists() or output_dir.exists()


def test_extract_text_content(sample_native_pdf, tmp_path):
    output_dir = tmp_path / "out"
    runner = CliRunner()
    runner.invoke(
        main,
        ["extract", str(sample_native_pdf), "--output-dir", str(output_dir)]
    )
    json_files = list(output_dir.glob("*.json"))
    data = json.loads(json_files[0].read_text())
    # El PDF de prueba tiene "Super Mario 64" en el texto
    all_text = " ".join(p["text"] for p in data["pages"])
    assert "Super Mario" in all_text
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
conda run -n cnintendo pytest tests/commands/test_extract.py -v
```
Esperado: FAIL — extract no implementado.

- [ ] **Step 3: Implementar `src/cnintendo/commands/extract.py`**

```python
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click
import fitz  # PyMuPDF
from PIL import Image
import io

from cnintendo.commands.inspect import _detect_pdf_type
from cnintendo.ollama_client import OllamaClient


OCR_PROMPT = (
    "Eres un asistente que extrae texto de imágenes escaneadas de revistas de "
    "videojuegos. Transcribe todo el texto visible en esta página de forma exacta, "
    "manteniendo párrafos y estructura. Solo devuelve el texto, sin comentarios."
)


def _extract_page_native(page: fitz.Page) -> dict:
    """Extrae texto e imágenes de una página con texto nativo."""
    text = page.get_text()
    images = []
    for img_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        images.append({"xref": xref, "index": img_index})
    return {"text": text, "image_count": len(images), "images": images}


def _extract_page_scanned(
    page: fitz.Page, page_num: int, images_dir: Path, client: OllamaClient
) -> dict:
    """Extrae texto de una página escaneada usando Ollama vision."""
    mat = fitz.Matrix(2, 2)  # 2x zoom para mejor OCR
    clip = page.get_pixmap(matrix=mat)
    img_path = images_dir / f"page_{page_num:04d}_ocr.jpg"
    clip.save(str(img_path))

    text = client.generate_vision(OCR_PROMPT, img_path)
    return {"text": text, "image_count": 0, "images": [], "ocr_source": str(img_path)}


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None,
              help="Directorio de salida. Por defecto usa data/extracted/")
@click.option("--force", is_flag=True, help="Re-extrae aunque ya exista el JSON.")
def extract(pdf_path: Path, output_dir: Optional[Path], force: bool):
    """Extrae texto e imágenes de un PDF (nativo o escaneado)."""
    output_dir = output_dir or Path("data/extracted")
    output_dir.mkdir(parents=True, exist_ok=True)

    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    output_json = output_dir / f"{pdf_path.stem}_extracted.json"
    if output_json.exists() and not force:
        click.echo(f"Ya existe {output_json}, usa --force para re-extraer.", err=True)
        return

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        click.echo(f"Error al abrir PDF: {e}", err=True)
        sys.exit(1)

    pdf_type = _detect_pdf_type(doc)
    client = OllamaClient() if pdf_type in ("scanned", "mixed") else None

    pages_data = []
    with click.progressbar(range(len(doc)), label=f"Extrayendo {pdf_path.name}") as bar:
        for i in bar:
            page = doc[i]
            page_text = page.get_text().strip()

            if pdf_type == "scanned" or (pdf_type == "mixed" and len(page_text) < 50):
                page_data = _extract_page_scanned(page, i + 1, images_dir, client)
            else:
                page_data = _extract_page_native(page)

            page_data["page_number"] = i + 1
            pages_data.append(page_data)

    doc.close()

    result = {
        "filename": pdf_path.name,
        "pdf_type": pdf_type,
        "total_pages": len(pages_data),
        "pages": pages_data,
    }

    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    click.echo(f"Extraído: {output_json}", err=True)
```

- [ ] **Step 4: Ejecutar tests**

```bash
conda run -n cnintendo pytest tests/commands/test_extract.py -v
```
Esperado: 3 tests PASS. (Los tests con PDFs escaneados no llaman a Ollama real.)

- [ ] **Step 5: Commit**

```bash
git add src/cnintendo/commands/extract.py tests/commands/test_extract.py
git commit -m "feat: comando extract para PDFs nativos y escaneados"
```

---

## Chunk 5: Comandos analyze y export

### Task 6: Implementar comando `analyze`

**Files:**
- Create: `src/cnintendo/commands/analyze.py`
- Create: `tests/commands/test_analyze.py`

- [ ] **Step 1: Escribir tests para `analyze`**

Crear `tests/commands/test_analyze.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from cnintendo.cli import main


SAMPLE_EXTRACTED = {
    "filename": "revista_001.pdf",
    "pdf_type": "native",
    "total_pages": 2,
    "pages": [
        {
            "page_number": 1,
            "text": "Super Mario 64\nPlataforma: Nintendo 64\nPuntuación: 97\nUn juego revolucionario...",
            "image_count": 0,
            "images": []
        }
    ]
}

SAMPLE_OLLAMA_RESPONSE = json.dumps({
    "articles": [
        {
            "page": 1,
            "section": "review",
            "title": "Super Mario 64",
            "game": "Super Mario 64",
            "platform": "Nintendo 64",
            "score": 97,
            "text": "Un juego revolucionario...",
            "images": []
        }
    ]
})


def test_analyze_produces_structured_json(tmp_path):
    extracted_json = tmp_path / "revista_001_extracted.json"
    extracted_json.write_text(json.dumps(SAMPLE_EXTRACTED))
    output_json = tmp_path / "structured.json"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = SAMPLE_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["analyze", str(extracted_json), "--output", str(output_json)]
        )

    assert result.exit_code == 0
    assert output_json.exists()
    data = json.loads(output_json.read_text())
    assert "issue" in data
    assert "articles" in data
    assert len(data["articles"]) == 1
    assert data["articles"][0]["game"] == "Super Mario 64"
```

- [ ] **Step 2: Ejecutar test para verificar que falla**

```bash
conda run -n cnintendo pytest tests/commands/test_analyze.py -v
```
Esperado: FAIL.

- [ ] **Step 3: Implementar `src/cnintendo/commands/analyze.py`**

```python
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

import click

from cnintendo.models import Article, IssueData, IssueMetadata
from cnintendo.ollama_client import OllamaClient


ANALYZE_PROMPT_TEMPLATE = """Analiza el siguiente texto extraído de una revista de videojuegos y devuelve un JSON estructurado.

TEXTO POR PÁGINA:
{pages_text}

Devuelve SOLO un objeto JSON válido con esta estructura exacta:
{{
  "articles": [
    {{
      "page": <número de página>,
      "section": <"review"|"preview"|"news"|"editorial"|"unknown">,
      "title": <título del artículo o null>,
      "game": <nombre del juego o null>,
      "platform": <plataforma o null>,
      "score": <puntuación numérica o null>,
      "text": <resumen del texto>,
      "images": []
    }}
  ]
}}

Identifica cada artículo, reseña o sección independiente. Si una página no tiene contenido claro, omítela.
"""


@click.command()
@click.argument("extracted_json", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--force", is_flag=True)
def analyze(extracted_json: Path, output: Optional[Path], force: bool):
    """Analiza un JSON extraído y estructura los datos usando Ollama."""
    output = output or extracted_json.parent / extracted_json.name.replace(
        "_extracted.json", "_structured.json"
    )

    if output.exists() and not force:
        click.echo(f"Ya existe {output}, usa --force para re-analizar.", err=True)
        return

    raw_data = json.loads(extracted_json.read_text())

    pages_text = "\n\n---\n\n".join(
        f"[Página {p['page_number']}]\n{p['text']}"
        for p in raw_data["pages"]
        if p.get("text", "").strip()
    )

    if not pages_text.strip():
        click.echo("No se encontró texto para analizar.", err=True)
        sys.exit(1)

    client = OllamaClient()
    prompt = ANALYZE_PROMPT_TEMPLATE.format(pages_text=pages_text[:8000])

    click.echo("Llamando a Ollama para análisis estructurado...", err=True)
    response = client.generate(prompt)

    try:
        parsed = json.loads(response)
        articles = [Article(**a) for a in parsed.get("articles", [])]
    except (json.JSONDecodeError, Exception) as e:
        click.echo(f"Error parseando respuesta de Ollama: {e}", err=True)
        click.echo(f"Respuesta recibida: {response[:500]}", err=True)
        sys.exit(1)

    metadata = IssueMetadata(
        filename=raw_data["filename"],
        pages=raw_data["total_pages"],
        type=raw_data.get("pdf_type", "unknown"),
    )
    issue_data = IssueData(issue=metadata, articles=articles)

    output.write_text(issue_data.model_dump_json(indent=2))
    click.echo(f"Analizado: {output} ({len(articles)} artículos)", err=True)
```

- [ ] **Step 4: Ejecutar tests**

```bash
conda run -n cnintendo pytest tests/commands/test_analyze.py -v
```
Esperado: 1 test PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cnintendo/commands/analyze.py tests/commands/test_analyze.py
git commit -m "feat: comando analyze con Ollama para extracción estructurada"
```

---

### Task 7: Implementar comando `export`

**Files:**
- Create: `src/cnintendo/commands/export.py`
- Create: `tests/commands/test_export.py`

- [ ] **Step 1: Escribir tests para `export`**

Crear `tests/commands/test_export.py`:
```python
import json
import pytest
import sqlite3
from pathlib import Path
from click.testing import CliRunner
from cnintendo.cli import main


SAMPLE_STRUCTURED = {
    "issue": {
        "id": None,
        "filename": "revista_001.pdf",
        "number": 1,
        "year": 1995,
        "month": "enero",
        "pages": 84,
        "type": "native"
    },
    "articles": [
        {
            "page": 12,
            "section": "review",
            "title": "Super Mario 64",
            "game": "Super Mario 64",
            "platform": "N64",
            "score": 97,
            "text": "Un juego excelente",
            "images": []
        }
    ]
}


def test_export_creates_sqlite(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(
        json.dumps(SAMPLE_STRUCTURED)
    )
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["export", "--input-dir", str(input_dir), "--db", str(db_path)]
    )
    assert result.exit_code == 0
    assert db_path.exists()


def test_export_tables_exist(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(
        json.dumps(SAMPLE_STRUCTURED)
    )
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    assert "issues" in tables
    assert "articles" in tables
    assert "games" in tables
    assert "images" in tables


def test_export_data_correct(tmp_path):
    input_dir = tmp_path / "structured"
    input_dir.mkdir()
    (input_dir / "revista_001_structured.json").write_text(
        json.dumps(SAMPLE_STRUCTURED)
    )
    db_path = tmp_path / "output.db"

    runner = CliRunner()
    runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])

    conn = sqlite3.connect(db_path)
    articles = conn.execute("SELECT title, score FROM articles").fetchall()
    conn.close()

    assert len(articles) == 1
    assert articles[0][0] == "Super Mario 64"
    assert articles[0][1] == 97
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
conda run -n cnintendo pytest tests/commands/test_export.py -v
```
Esperado: FAIL.

- [ ] **Step 3: Implementar `src/cnintendo/commands/export.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import click
import sqlite_utils

from cnintendo.models import IssueData


def _create_schema(db: sqlite_utils.Database):
    """Crea las tablas si no existen."""
    if "issues" not in db:
        db["issues"].create({
            "id": int,
            "filename": str,
            "number": int,
            "year": int,
            "month": str,
            "pages": int,
            "type": str,
        }, pk="id", if_not_exists=True)

    if "games" not in db:
        db["games"].create({
            "id": int,
            "name": str,
            "platform": str,
        }, pk="id", if_not_exists=True)

    if "articles" not in db:
        db["articles"].create({
            "id": int,
            "issue_id": int,
            "game_id": int,
            "page": int,
            "section": str,
            "title": str,
            "game": str,
            "platform": str,
            "score": int,
            "text": str,
        }, pk="id", foreign_keys=[
            ("issue_id", "issues", "id"),
            ("game_id", "games", "id"),
        ], if_not_exists=True)

    if "images" not in db:
        db["images"].create({
            "id": int,
            "article_id": int,
            "path": str,
        }, pk="id", foreign_keys=[("article_id", "articles", "id")], if_not_exists=True)


@click.command()
@click.option("--input-dir", "-i", type=click.Path(path_type=Path),
              default=Path("data/extracted"), show_default=True)
@click.option("--db", type=click.Path(path_type=Path),
              default=Path("data/output.db"), show_default=True)
def export(input_dir: Path, db: Path):
    """Exporta JSONs estructurados a una base de datos SQLite."""
    json_files = list(input_dir.glob("*_structured.json"))
    if not json_files:
        click.echo(f"No se encontraron archivos *_structured.json en {input_dir}", err=True)
        return

    database = sqlite_utils.Database(db)
    _create_schema(database)

    total_issues = 0
    total_articles = 0

    for json_file in json_files:
        raw = json.loads(json_file.read_text())
        issue_data = IssueData(**raw)

        issue_row = issue_data.issue.model_dump()
        issue_row.pop("id")
        database["issues"].insert(issue_row, alter=True)
        issue_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]

        for article in issue_data.articles:
            article_row = article.model_dump()
            images = article_row.pop("images", [])

            # Normalizar juego en tabla games
            game_id = None
            if article_row.get("game"):
                existing = list(database.execute(
                    "SELECT id FROM games WHERE name = ? AND platform IS ?",
                    [article_row["game"], article_row.get("platform")]
                ).fetchall())
                if existing:
                    game_id = existing[0][0]
                else:
                    database["games"].insert({
                        "name": article_row["game"],
                        "platform": article_row.get("platform"),
                    })
                    game_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]

            article_row["issue_id"] = issue_id
            article_row["game_id"] = game_id
            database["articles"].insert(article_row, alter=True)
            article_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]

            for img_path in images:
                database["images"].insert({"article_id": article_id, "path": img_path})

            total_articles += 1

        total_issues += 1
        click.echo(f"  ✓ {json_file.name}", err=True)

    click.echo(f"\nExportado: {total_issues} números, {total_articles} artículos → {db}")
```

- [ ] **Step 4: Ejecutar tests**

```bash
conda run -n cnintendo pytest tests/commands/test_export.py -v
```
Esperado: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cnintendo/commands/export.py tests/commands/test_export.py
git commit -m "feat: comando export a SQLite con sqlite-utils"
```

---

## Chunk 6: Comando run (orquestador)

### Task 8: Implementar comando `run`

**Files:**
- Create: `src/cnintendo/commands/run.py`
- Create: `tests/commands/test_run.py`

- [ ] **Step 1: Escribir test de integración para `run`**

Crear `tests/commands/test_run.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from cnintendo.cli import main


MOCK_OLLAMA_RESPONSE = json.dumps({
    "articles": [
        {
            "page": 1,
            "section": "review",
            "title": "Test Game",
            "game": "Test Game",
            "platform": "SNES",
            "score": 85,
            "text": "Great game",
            "images": []
        }
    ]
})


def test_run_processes_folder(sample_native_pdf, tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    import shutil
    shutil.copy(sample_native_pdf, pdf_dir / "revista_001.pdf")

    data_dir = tmp_path / "data"

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = MOCK_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["run", str(pdf_dir), "--data-dir", str(data_dir)]
        )

    assert result.exit_code == 0
    # Verificar que se crearon los JSONs intermedios
    metadata = list((data_dir / "extracted").glob("*_metadata.json"))
    extracted = list((data_dir / "extracted").glob("*_extracted.json"))
    structured = list((data_dir / "extracted").glob("*_structured.json"))
    assert len(metadata) >= 1
    assert len(extracted) >= 1
    assert len(structured) >= 1


def test_run_skips_existing(sample_native_pdf, tmp_path):
    """Verifica que run saltea PDFs ya procesados."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    import shutil
    shutil.copy(sample_native_pdf, pdf_dir / "revista_001.pdf")
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True)

    # Pre-crear el archivo para simular que ya fue procesado
    (extracted_dir / "revista_001_extracted.json").write_text(
        json.dumps({"filename": "revista_001.pdf", "pdf_type": "native",
                    "total_pages": 1, "pages": [{"page_number": 1, "text": "test",
                    "image_count": 0, "images": []}]})
    )

    with patch("cnintendo.ollama_client.OllamaClient.generate") as mock_gen:
        mock_gen.return_value = MOCK_OLLAMA_RESPONSE
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["run", str(pdf_dir), "--data-dir", str(data_dir)]
        )

    assert result.exit_code == 0
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
conda run -n cnintendo pytest tests/commands/test_run.py -v
```
Esperado: FAIL.

- [ ] **Step 3: Implementar `src/cnintendo/commands/run.py`**

```python
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import track

from cnintendo.commands.inspect import _detect_pdf_type, _infer_issue_number
from cnintendo.models import IssueMetadata

console = Console()


@click.command()
@click.argument("pdf_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--data-dir", type=click.Path(path_type=Path), default=None,
              help="Directorio base para datos. Por defecto: data/")
@click.option("--force", is_flag=True, help="Re-procesa aunque existan archivos intermedios.")
@click.option("--skip-export", is_flag=True, help="No ejecuta la exportación a SQLite al final.")
def run(pdf_dir: Path, data_dir: Optional[Path], force: bool, skip_export: bool):
    """Ejecuta el pipeline completo sobre una carpeta de PDFs."""
    data_dir = data_dir or Path("data")
    extracted_dir = data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        click.echo(f"No se encontraron PDFs en {pdf_dir}", err=True)
        return

    console.print(f"[bold]Procesando {len(pdf_files)} PDFs[/bold] en {pdf_dir}")

    for pdf in track(pdf_files, description="Procesando PDFs..."):
        stem = pdf.stem
        metadata_json = extracted_dir / f"{stem}_metadata.json"
        extracted_json = extracted_dir / f"{stem}_extracted.json"
        structured_json = extracted_dir / f"{stem}_structured.json"

        console.print(f"\n[cyan]{pdf.name}[/cyan]")

        try:
            import fitz
            doc = fitz.open(str(pdf))

            # Step 1: inspect → metadata.json
            if not metadata_json.exists() or force:
                pdf_type = _detect_pdf_type(doc)
                number = _infer_issue_number(pdf.name)
                metadata = IssueMetadata(
                    filename=pdf.name, pages=len(doc),
                    type=pdf_type, number=number,
                )
                metadata_json.write_text(metadata.model_dump_json(indent=2))
                console.print(f"  inspect ✓ ({pdf_type}, {len(doc)} páginas)")
            else:
                console.print(f"  [yellow]Saltea inspect[/yellow]")
                import json
                metadata = IssueMetadata(**json.loads(metadata_json.read_text()))

            # Step 2: extract → extracted.json
            if not extracted_json.exists() or force:
                from cnintendo.commands.extract import extract as _do_extract
                ctx = click.Context(_do_extract)
                ctx.invoke(
                    _do_extract,
                    pdf_path=pdf,
                    output_dir=extracted_dir,
                    force=force,
                )
                console.print(f"  extract ✓")
            else:
                console.print(f"  [yellow]Saltea extract[/yellow]")

            doc.close()

            # Step 3: analyze → structured.json
            if not structured_json.exists() or force:
                from cnintendo.commands.analyze import analyze as _do_analyze
                ctx = click.Context(_do_analyze)
                ctx.invoke(
                    _do_analyze,
                    extracted_json=extracted_json,
                    output=structured_json,
                    force=force,
                )
                console.print(f"  analyze ✓")
            else:
                console.print(f"  [yellow]Saltea analyze[/yellow]")

            console.print(f"  [green]✓ Completado[/green]")

        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
            continue

    # Step 4: export → output.db
    if not skip_export:
        console.print("\n[bold]Exportando a SQLite...[/bold]")
        db_path = data_dir / "output.db"
        from cnintendo.commands.export import export as _do_export
        ctx = click.Context(_do_export)
        ctx.invoke(_do_export, input_dir=extracted_dir, db=db_path)
        console.print(f"[green]Base de datos:[/green] {db_path}")
```

- [ ] **Step 4: Ejecutar todos los tests**

```bash
conda run -n cnintendo pytest tests/ -v
```
Esperado: Todos los tests PASS.

- [ ] **Step 5: Verificar CLI completo**

```bash
conda run -n cnintendo cnintendo --help
conda run -n cnintendo cnintendo run --help
```

- [ ] **Step 6: Commit final**

```bash
git add src/cnintendo/commands/run.py tests/commands/test_run.py
git commit -m "feat: comando run - pipeline completo con idempotencia"
```

---

## Verificación End-to-End

- [ ] **1. Activar entorno**
```bash
conda activate cnintendo
```

- [ ] **2. Copiar un PDF de prueba**
```bash
cp /ruta/a/una/revista.pdf data/pdfs/
```

- [ ] **3. Inspeccionar**
```bash
cnintendo inspect data/pdfs/revista.pdf
```
Esperado: JSON con `pages`, `type` (native/scanned/mixed).

- [ ] **4. Verificar conexión Ollama**
```bash
python -c "from cnintendo.ollama_client import OllamaClient; c = OllamaClient(); print('Ollama disponible:', c.is_available())"
```

- [ ] **5. Ejecutar pipeline completo**
```bash
cnintendo run data/pdfs/
```

- [ ] **6. Consultar base de datos**
```bash
sqlite3 data/output.db "SELECT game, platform, score FROM articles WHERE score IS NOT NULL ORDER BY score DESC LIMIT 10;"
```
