# Diseño: Ordenamiento de data/extracted por año y mes de publicación

**Fecha:** 2026-03-15
**Estado:** Aprobado

## Objetivo

Ordenar el procesamiento del pipeline y la exportación a SQLite por año y mes de publicación de cada número, en lugar del orden alfabético actual.

## Contexto

- `discover_scans()` retorna `ScanItem`s ordenados alfabéticamente por nombre de directorio.
- `export.py` ordena `*_structured.json` alfabéticamente.
- El campo `ia_date` (formato `"YYYY"`, `"YYYY-MM"` o `"YYYY-MM-DD"`) ya está disponible en `_meta.xml` y en los JSONs estructurados.
- `IssueMetadata.year` y `IssueMetadata.month` existen en el modelo pero no se pueblan actualmente.

## Decisiones de diseño

- **No se modifican modelos ni schema de DB.** El ordenamiento es de comportamiento, no de datos.
- **Items sin fecha quedan al final** (`(9999, 0)`) para no romper el pipeline.
- **La lógica de parseo de fecha se duplica mínimamente** entre `scan_reader.py` y `export.py` — ambos módulos tienen responsabilidades distintas y la función es trivial (3 líneas).

## Cambios

### 1. `src/cnintendo/scan_reader.py`

Agregar propiedad `date_sort_key` a `ScanItem`:

```python
@property
def date_sort_key(self) -> tuple[int, int]:
    date = self.meta.get("date", "")
    parts = date.split("-")
    year = int(parts[0]) if parts and parts[0].isdigit() else 9999
    month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (year, month)
```

### 2. `src/cnintendo/commands/run.py`

En `_run_scans_pipeline`, reemplazar:

```python
all_items = discover_scans(scans_dir)
```

por:

```python
all_items = sorted(discover_scans(scans_dir), key=lambda i: i.date_sort_key)
```

### 3. `src/cnintendo/commands/export.py`

Agregar función auxiliar `_date_sort_key` y usarla al ordenar `json_files`:

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

json_files = sorted(input_dir.glob("*_structured.json"), key=_date_sort_key)
```

## Testing

- Tests unitarios para `date_sort_key` con los tres formatos de fecha (`"1992"`, `"1992-01"`, `"1992-01-15"`).
- Test de integración: verificar que `_run_scans_pipeline` procesa en orden cronológico.
- Test en `export.py`: verificar que `_date_sort_key` retorna `(9999, 0)` para fechas inválidas o ausentes.
