# cnintendoOllama — Spec de Diseño

**Fecha:** 2026-03-14
**Estado:** Aprobado

---

## Problema

Se necesita extraer y estructurar información de PDFs de una revista de videojuegos (una publicación, múltiples números). Los PDFs son mixtos: algunos nativos con texto seleccionable, otros son escaneos que requieren OCR.

## Objetivo

Herramientas CLI en Python que procesen PDFs de revistas de videojuegos y produzcan:
1. **Catálogo** — base de datos SQLite con juegos, reseñas, puntuaciones, artículos
2. **Archivo** — JSONs estructurados por número de revista
3. **Análisis** — datos normalizados para explorar tendencias

## Arquitectura: CLI Modular

Múltiples comandos CLI independientes encadenables. Cada uno lee/escribe JSON intermedios. Un comando `run` coordina el pipeline completo sobre carpetas.

```
PDF → [inspect] → metadata.json
    → [extract] → extracted.json + images/
    → [analyze] → structured.json
    → [export]  → output.db (SQLite)
```

## Stack Tecnológico

- **Python 3.11**, Conda para entorno aislado
- **Click** — framework CLI
- **PyMuPDF (fitz)** — extracción de texto e imágenes de PDFs nativos
- **Pillow** — manipulación de imágenes para OCR
- **httpx** — cliente HTTP async para Ollama
- **Pydantic v2** — validación y serialización del schema de datos
- **sqlite-utils** — operaciones SQLite con upsert
- **rich** — output de consola legible con progreso
- **python-dotenv** — configuración via `.env`

## Configuración de Ollama

Ollama corre en un contenedor Docker separado en el mismo host. Configuración via env vars:

```
OLLAMA_URL=http://192.168.1.x:11434
OLLAMA_MODEL=llava          # modelo vision para OCR de escaneos
OLLAMA_TEXT_MODEL=llama3    # modelo texto para análisis estructurado
```

## Comandos CLI

| Comando | Input | Output |
|---|---|---|
| `cnintendo inspect <pdf>` | PDF | `metadata.json` |
| `cnintendo extract <pdf>` | PDF | `extracted.json` + imágenes |
| `cnintendo analyze <json>` | extracted JSON | `structured.json` |
| `cnintendo export [--input-dir]` | carpeta de structured JSONs | `output.db` |
| `cnintendo run <carpeta>` | carpeta de PDFs | todo lo anterior |

## Schema de Datos

### JSON por número (output de `analyze`)
```json
{
  "issue": {
    "id": "revista-042",
    "filename": "revista_042.pdf",
    "number": 42,
    "year": 1996,
    "month": "octubre",
    "pages": 84,
    "type": "scanned"
  },
  "articles": [
    {
      "page": 12,
      "section": "review",
      "title": "Super Mario 64",
      "game": "Super Mario 64",
      "platform": "N64",
      "score": 97,
      "text": "...",
      "images": ["images/042_p12_001.jpg"]
    }
  ]
}
```

### SQLite — 4 tablas
- `issues` — metadatos de cada número
- `articles` — artículos/reseñas con FK a issue
- `games` — juegos únicos normalizados
- `images` — imágenes extraídas con FK a article

## Estructura del Proyecto

```
cnintendoOllama/
├── environment.yml
├── pyproject.toml
├── .env.example
├── src/
│   └── cnintendo/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py
│       ├── ollama_client.py
│       └── commands/
│           ├── __init__.py
│           ├── inspect.py
│           ├── extract.py
│           ├── analyze.py
│           ├── export.py
│           └── run.py
├── data/
│   ├── pdfs/
│   ├── extracted/
│   ├── images/
│   └── .gitkeep
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── commands/
```

## Idempotencia

El comando `run` detecta JSONs intermedios ya existentes y los saltea. Flag `--force` para re-procesar. Esto permite reanudar pipelines interrumpidos.
