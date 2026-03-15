# CNintendoOllama

> Extract, analyze, and archive **Club Nintendo** magazine issues using local LLMs via [Ollama](https://ollama.com).

Club Nintendo was a beloved Mexican gaming magazine published from the early 1990s. This tool turns scanned PDFs and Internet Archive downloads into structured, searchable data — articles, game reviews, scores, and images — stored in a local SQLite database.

---

## Features

- **PDF extraction** — handles both native (text-selectable) and scanned (image-only) PDFs
- **OCR via Ollama vision** — uses local vision models to transcribe scanned pages
- **Structured analysis** — LLM extracts articles, game names, platforms, scores, and sections
- **Narrative summaries** — generates a human-readable summary for each issue
- **Image descriptions** — optionally describes images using a vision model
- **SQLite export** — everything lands in a clean, queryable database
- **Internet Archive support** — processes bulk downloads from archive.org (djvu.txt + meta.xml)
- **Chronological ordering** — pipeline and export follow publication date, not filename order

---

## Architecture

```
PDF / Internet Archive scan
        │
        ▼
   [ extract ]  ──▶  _extracted.json   (raw text per page)
        │
        ▼
   [ analyze ]  ──▶  _structured.json  (articles, scores, metadata)
        │
        ├──▶ [ summarize ]  ──▶  _summary.txt
        │
        ├──▶ [ describe ]   ──▶  _described.json  (image descriptions)
        │
        ▼
   [ export ]   ──▶  output.db (SQLite)
```

All intermediate files live in `data/extracted/`. The final database has four tables: `issues`, `articles`, `games`, `images`.

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally or on your network
- A text model (e.g. `gemma3`, `llama3`, `qwen`) for analysis and summarization
- A vision model (e.g. `llava`, `gemma3`) for OCR and image description

---

## Installation

```bash
# Clone the repo
git clone git@github.com:psyrax/CNintendoOllama.git
cd CNintendoOllama

# Create conda environment
conda env create -f environment.yml
conda activate cnintendo

# Install the CLI
pip install -e .

# Configure Ollama connection
cp .env.example .env
# Edit .env with your Ollama URL and model names
```

### `.env` configuration

```env
OLLAMA_URL=http://192.168.1.x:11434
OLLAMA_MODEL=gemma3:4b
OLLAMA_TEXT_MODEL=gemma3:4b
OLLAMA_TIMEOUT=300
```

---

## Usage

### Full pipeline (recommended)

Run the entire pipeline on a folder of Internet Archive scans:

```bash
cnintendo run --scans-dir scans/ --data-dir data/
```

With optional summarization and image description:

```bash
cnintendo run --scans-dir scans/ --with-summarize --with-describe
```

Re-process only previously failed items:

```bash
cnintendo run --scans-dir scans/ --retry-failed
```

---

### Individual commands

**Inspect** a PDF to detect its type (native/scanned/mixed):

```bash
cnintendo inspect magazine.pdf
```

**Extract** text from a PDF:

```bash
cnintendo extract magazine.pdf --output-dir data/extracted/
```

**Analyze** extracted text into structured JSON:

```bash
cnintendo analyze data/extracted/magazine_extracted.json
```

**Summarize** a structured issue:

```bash
cnintendo summarize data/extracted/magazine_structured.json
```

**Describe** images in an extracted file:

```bash
cnintendo describe data/extracted/magazine_extracted.json
```

**Export** all structured JSONs to SQLite:

```bash
cnintendo export --input-dir data/extracted/ --db data/output.db
```

---

## Internet Archive structure

The `--scans-dir` mode expects subdirectories in the format downloaded by `ia` (Internet Archive CLI):

```
scans/
  ClubNintendoAo01N01Mxico/
    ClubNintendoAo01N01Mxico_djvu.txt
    ClubNintendoAo01N01Mxico_meta.xml
    ClubNintendoAo01N01Mxico.pdf
  ClubNintendoAo01N02Mxico/
    ...
```

Download issues with:

```bash
pip install internetarchive
ia download ClubNintendoAo01N01Mxico --glob="*_djvu.txt" --glob="*_meta.xml" --glob="*.pdf"
```

---

## Database schema

| Table | Key columns |
|---|---|
| `issues` | `id`, `filename`, `number`, `year`, `month`, `pages`, `type`, `ia_title`, `ia_date` |
| `articles` | `id`, `issue_id`, `page`, `section`, `title`, `game`, `platform`, `score`, `text` |
| `games` | `id`, `name`, `platform` |
| `images` | `id`, `article_id`, `path`, `description` |

Query example — all game reviews with scores:

```sql
SELECT i.ia_title, a.game, a.platform, a.score
FROM articles a
JOIN issues i ON a.issue_id = i.id
WHERE a.section = 'review' AND a.score IS NOT NULL
ORDER BY a.score DESC;
```

---

## Development

```bash
# Run tests
conda run -n cnintendo pytest

# Run a specific test file
conda run -n cnintendo pytest tests/test_scan_reader.py -v
```

Branching follows [gitflow](https://nvie.com/posts/a-successful-git-branching-model/):
- `main` — stable releases
- `develop` — integration branch
- `feature/*` — new features branched from `develop`

---

## Project structure

```
src/cnintendo/
  cli.py              # CLI entry point
  models.py           # Pydantic models (IssueData, Article, IssueMetadata)
  ollama_client.py    # HTTP client for Ollama
  scan_reader.py      # Internet Archive scan discovery and parsing
  commands/
    inspect.py        # PDF type detection
    extract.py        # Text and image extraction
    analyze.py        # LLM-based structuring
    summarize.py      # Narrative summary generation
    describe.py       # Image description
    export.py         # SQLite export
    run.py            # Full pipeline orchestration
tests/                # pytest test suite (61 tests)
tools/                # Benchmarking scripts for model comparison
docs/                 # Design specs and implementation plans
```

---

## License

MIT
