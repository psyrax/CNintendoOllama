# Sort Extracted by Publication Date — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ordenar el procesamiento del pipeline y la exportación a SQLite por año y mes de publicación (en lugar de orden alfabético).

**Architecture:** Añadir propiedad `date_sort_key` a `ScanItem` para parsear `ia_date` del meta.xml; ordenar `items` en `_run_scans_pipeline`; añadir `_date_sort_key()` en `export.py` para ordenar los archivos JSON antes de exportar.

**Tech Stack:** Python 3.11+, Pydantic, Click, pytest.

---

## Chunk 1: `ScanItem.date_sort_key` + ordenamiento en pipeline

### Task 1: Propiedad `date_sort_key` en `ScanItem`

**Files:**
- Modify: `src/cnintendo/scan_reader.py`
- Test: `tests/test_scan_reader.py`

- [ ] **Step 1: Escribir los tests que fallarán**

Añadir al final de `tests/test_scan_reader.py`:

```python
META_1991_01 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test01</identifier>
  <title>Test</title>
  <date>1991-01</date>
</metadata>"""

META_1992 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test02</identifier>
  <title>Test</title>
  <date>1992</date>
</metadata>"""

META_1993_06_15 = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test03</identifier>
  <title>Test</title>
  <date>1993-06-15</date>
</metadata>"""

META_NO_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test04</identifier>
  <title>Test</title>
</metadata>"""

META_EMPTY_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>Test05</identifier>
  <title>Test</title>
  <date></date>
</metadata>"""


def _make_scan_item(tmp_path, identifier, meta_xml_content):
    scan_dir = tmp_path / identifier
    scan_dir.mkdir()
    (scan_dir / f"{identifier}.pdf").write_text("")
    (scan_dir / f"{identifier}_djvu.txt").write_text("texto\x0cmas texto")
    meta = scan_dir / f"{identifier}_meta.xml"
    meta.write_text(meta_xml_content)
    return discover_scans(tmp_path)[0]


def test_date_sort_key_year_and_month(tmp_path):
    item = _make_scan_item(tmp_path, "Test01", META_1991_01)
    assert item.date_sort_key == (1991, 1)


def test_date_sort_key_year_only(tmp_path):
    item = _make_scan_item(tmp_path, "Test02", META_1992)
    assert item.date_sort_key == (1992, 0)


def test_date_sort_key_full_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test03", META_1993_06_15)
    assert item.date_sort_key == (1993, 6)


def test_date_sort_key_no_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test04", META_NO_DATE)
    assert item.date_sort_key == (9999, 0)


def test_date_sort_key_empty_date(tmp_path):
    item = _make_scan_item(tmp_path, "Test05", META_EMPTY_DATE)
    assert item.date_sort_key == (9999, 0)
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
conda run -n cnintendo pytest tests/test_scan_reader.py::test_date_sort_key_year_and_month -v
```

Esperado: `FAILED` con `AttributeError: 'ScanItem' object has no attribute 'date_sort_key'`

- [ ] **Step 3: Implementar `date_sort_key` en `ScanItem`**

En `src/cnintendo/scan_reader.py`, dentro del dataclass `ScanItem`, después de la propiedad `meta`:

```python
@property
def date_sort_key(self) -> tuple[int, int]:
    date = self.meta.get("date", "")
    parts = date.split("-")
    year = int(parts[0]) if parts and parts[0].isdigit() else 9999
    month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (year, month)
```

- [ ] **Step 4: Verificar que todos los nuevos tests pasan**

```bash
conda run -n cnintendo pytest tests/test_scan_reader.py -v
```

Esperado: todos los tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_scan_reader.py src/cnintendo/scan_reader.py
git commit -m "feat: add date_sort_key property to ScanItem"
```

---

### Task 2: Ordenar items en `_run_scans_pipeline`

**Files:**
- Modify: `src/cnintendo/commands/run.py`
- Test: `tests/commands/test_run.py`

- [ ] **Step 1: Revisar el test existente**

Leer `tests/commands/test_run.py` para entender los fixtures existentes y evitar duplicar setup.

- [ ] **Step 2: Escribir el test que fallará**

Añadir al final de `tests/commands/test_run.py`:

```python
def _make_scan_dir(base: Path, identifier: str, date: str, djvu_content: str = "texto\x0cmas") -> None:
    """Helper: crea un directorio de scan válido."""
    d = base / identifier
    d.mkdir()
    (d / f"{identifier}.pdf").write_text("")
    (d / f"{identifier}_djvu.txt").write_text(djvu_content)
    (d / f"{identifier}_meta.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>{identifier}</identifier>
  <title>{identifier}</title>
  <date>{date}</date>
  <subject>videojuegos</subject>
</metadata>""")


def test_run_scans_processes_in_chronological_order(tmp_path, monkeypatch):
    """El pipeline debe procesar issues en orden cronológico, no alfabético."""
    scans_dir = tmp_path / "scans"
    scans_dir.mkdir()
    data_dir = tmp_path / "data"

    # Crear 3 scans: C (1993), A (1991), B (1992) — alfabético ≠ cronológico
    _make_scan_dir(scans_dir, "C_1993", "1993-01")
    _make_scan_dir(scans_dir, "A_1991", "1991-01")
    _make_scan_dir(scans_dir, "B_1992", "1992-01")

    processed_order = []

    # Interceptar to_extracted_dict para registrar orden de procesamiento
    from cnintendo import scan_reader as sr
    original_to_extracted = sr.ScanItem.to_extracted_dict

    def patched_to_extracted(self):
        processed_order.append(self.identifier)
        return original_to_extracted(self)

    monkeypatch.setattr(sr.ScanItem, "to_extracted_dict", patched_to_extracted)

    # Parchear analyze y summarize para no requerir Ollama
    from cnintendo.commands import run as run_mod
    monkeypatch.setattr(run_mod, "_invoke_analyze", lambda *a, **kw: None, raising=False)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--scans-dir", str(scans_dir), "--data-dir", str(data_dir),
         "--skip-export", "--no-summarize"],
    )

    assert processed_order == ["A_1991", "B_1992", "C_1993"], (
        f"Esperado orden cronológico, obtenido: {processed_order}"
    )
```

> **Nota:** Si el test es difícil de aislar por las dependencias de Ollama, simplificar usando `discover_scans` directamente y verificar el orden con `sorted(..., key=lambda i: i.date_sort_key)`.

- [ ] **Step 3: Alternativa más simple si el test anterior es frágil**

Verificar el orden directamente sobre `discover_scans` + `date_sort_key`:

```python
def test_sorted_discover_scans_chronological(tmp_path):
    scans_dir = tmp_path / "scans"
    scans_dir.mkdir()
    _make_scan_dir(scans_dir, "C_1993", "1993-01")
    _make_scan_dir(scans_dir, "A_1991", "1991-01")
    _make_scan_dir(scans_dir, "B_1992", "1992-01")

    from cnintendo.scan_reader import discover_scans
    items = sorted(discover_scans(scans_dir), key=lambda i: i.date_sort_key)
    assert [i.identifier for i in items] == ["A_1991", "B_1992", "C_1993"]
```

- [ ] **Step 4: Verificar que el test falla o no aplica aún**

```bash
conda run -n cnintendo pytest tests/commands/test_run.py::test_sorted_discover_scans_chronological -v
```

Esperado: `FAILED` (el sort aún no está en el pipeline).

- [ ] **Step 5: Aplicar el cambio en `run.py`**

En `src/cnintendo/commands/run.py`, función `_run_scans_pipeline`, reemplazar:

```python
all_items = discover_scans(scans_dir)
```

por:

```python
all_items = sorted(discover_scans(scans_dir), key=lambda i: i.date_sort_key)
```

- [ ] **Step 6: Verificar que los tests pasan**

```bash
conda run -n cnintendo pytest tests/commands/test_run.py -v
```

Esperado: todos los tests `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/cnintendo/commands/run.py tests/commands/test_run.py
git commit -m "feat: sort pipeline items chronologically by ia_date"
```

---

## Chunk 2: Ordenamiento cronológico en `export.py`

### Task 3: Función `_date_sort_key` en `export.py`

**Files:**
- Modify: `src/cnintendo/commands/export.py`
- Test: `tests/commands/test_export.py`

- [ ] **Step 1: Escribir los tests que fallarán**

Añadir al final de `tests/commands/test_export.py`:

```python
from cnintendo.commands.export import _date_sort_key


def test_date_sort_key_year_and_month(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1991-06"}, "articles": []}))
    assert _date_sort_key(f) == (1991, 6)


def test_date_sort_key_year_only(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1993"}, "articles": []}))
    assert _date_sort_key(f) == (1993, 0)


def test_date_sort_key_full_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": "1992-03-15"}, "articles": []}))
    assert _date_sort_key(f) == (1992, 3)


def test_date_sort_key_missing_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {}, "articles": []}))
    assert _date_sort_key(f) == (9999, 0)


def test_date_sort_key_none_date(tmp_path):
    f = tmp_path / "test_structured.json"
    f.write_text(json.dumps({"issue": {"ia_date": None}, "articles": []}))
    assert _date_sort_key(f) == (9999, 0)


def test_date_sort_key_invalid_file(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not valid json {{{")
    assert _date_sort_key(f) == (9999, 0)


def test_export_chronological_order(tmp_path):
    """Export debe insertar issues en orden cronológico."""
    input_dir = tmp_path / "structured"
    input_dir.mkdir()

    issue_1993 = {
        "issue": {"id": None, "filename": "c_1993.pdf", "number": 3, "year": 1993,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1993-01",
                  "ia_identifier": None},
        "articles": []
    }
    issue_1991 = {
        "issue": {"id": None, "filename": "a_1991.pdf", "number": 1, "year": 1991,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1991-01",
                  "ia_identifier": None},
        "articles": []
    }
    issue_1992 = {
        "issue": {"id": None, "filename": "b_1992.pdf", "number": 2, "year": 1992,
                  "month": "enero", "pages": 84, "type": "native",
                  "ia_title": None, "ia_subjects": [], "ia_date": "1992-01",
                  "ia_identifier": None},
        "articles": []
    }

    # Escribir en orden C, A, B (alfabético ≠ cronológico)
    (input_dir / "c_1993_structured.json").write_text(json.dumps(issue_1993))
    (input_dir / "a_1991_structured.json").write_text(json.dumps(issue_1991))
    (input_dir / "b_1992_structured.json").write_text(json.dumps(issue_1992))

    db_path = tmp_path / "output.db"
    runner = CliRunner()
    result = runner.invoke(main, ["export", "--input-dir", str(input_dir), "--db", str(db_path)])
    assert result.exit_code == 0

    import sqlite3
    conn = sqlite3.connect(db_path)
    filenames = [row[0] for row in conn.execute("SELECT filename FROM issues ORDER BY id").fetchall()]
    conn.close()

    assert filenames == ["a_1991.pdf", "b_1992.pdf", "c_1993.pdf"], (
        f"Esperado orden cronológico, obtenido: {filenames}"
    )
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
conda run -n cnintendo pytest tests/commands/test_export.py::test_date_sort_key_year_and_month -v
```

Esperado: `FAILED` con `ImportError` (función no existe aún).

- [ ] **Step 3: Implementar `_date_sort_key` y actualizar el sort en `export.py`**

En `src/cnintendo/commands/export.py`, añadir la función antes de `export`:

```python
def _date_sort_key(path: Path) -> tuple[int, int]:
    try:
        raw = json.loads(path.read_text())
        date = raw.get("issue", {}).get("ia_date", "") or ""
        parts = date.split("-")
        year = int(parts[0]) if parts and parts[0].isdigit() else 9999
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (year, month)
    except Exception:
        return (9999, 0)
```

Y reemplazar en la función `export`:

```python
json_files = sorted(input_dir.glob("*_structured.json"))
```

por:

```python
json_files = sorted(input_dir.glob("*_structured.json"), key=_date_sort_key)
```

- [ ] **Step 4: Verificar que todos los tests pasan**

```bash
conda run -n cnintendo pytest tests/commands/test_export.py -v
```

Esperado: todos los tests `PASSED`.

- [ ] **Step 5: Verificar suite completa**

```bash
conda run -n cnintendo pytest -v
```

Esperado: todos los tests existentes siguen `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add src/cnintendo/commands/export.py tests/commands/test_export.py
git commit -m "feat: sort export chronologically by ia_date"
```
