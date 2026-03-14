from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import click
import sqlite_utils

from cnintendo.models import IssueData


def _create_schema(db: sqlite_utils.Database) -> None:
    """Crea las tablas si no existen."""
    existing = set(db.table_names())

    if "issues" not in existing:
        db["issues"].create({
            "id": int,
            "filename": str,
            "number": int,
            "year": int,
            "month": str,
            "pages": int,
            "type": str,
        }, pk="id", if_not_exists=True)

    if "games" not in existing:
        db["games"].create({
            "id": int,
            "name": str,
            "platform": str,
        }, pk="id", if_not_exists=True)

    if "articles" not in existing:
        db["articles"].create({
            "id": int,
            "issue_id": int,
            "game_id": int,
            "page": int,
            "section": str,
            "title": str,
            "game": str,
            "platform": str,
            "score": float,
            "text": str,
        }, pk="id", foreign_keys=[
            ("issue_id", "issues", "id"),
            ("game_id", "games", "id"),
        ], if_not_exists=True)

    if "images" not in existing:
        db["images"].create({
            "id": int,
            "article_id": int,
            "path": str,
        }, pk="id", foreign_keys=[("article_id", "articles", "id")], if_not_exists=True)


def _get_or_create_game(db: sqlite_utils.Database, name: str, platform: Optional[str]) -> int:
    """Finds or inserts a game, returns its id."""
    rows = list(db.execute(
        "SELECT id FROM games WHERE name = ? AND platform IS ?",
        [name, platform]
    ).fetchall())
    if rows:
        return rows[0][0]
    db["games"].insert({"name": name, "platform": platform})
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


@click.command()
@click.option("--input-dir", "-i", type=click.Path(path_type=Path),
              default=Path("data/extracted"), show_default=True)
@click.option("--db", type=click.Path(path_type=Path),
              default=Path("data/output.db"), show_default=True)
def export(input_dir: Path, db: Path):
    """Exporta JSONs estructurados a una base de datos SQLite."""
    json_files = sorted(input_dir.glob("*_structured.json"))
    if not json_files:
        click.echo(f"No se encontraron archivos *_structured.json en {input_dir}", err=True)
        return

    database = sqlite_utils.Database(db)
    _create_schema(database)

    total_issues = 0
    total_articles = 0

    for json_file in json_files:
        try:
            raw = json.loads(json_file.read_text())
            issue_data = IssueData(**raw)
        except Exception as e:
            click.echo(f"  ✗ {json_file.name}: {e}", err=True)
            continue

        issue_row = issue_data.issue.model_dump()
        issue_row.pop("id")
        database["issues"].insert(issue_row)
        issue_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]

        for article in issue_data.articles:
            article_row = article.model_dump()
            images = article_row.pop("images", [])

            game_id = None
            if article_row.get("game"):
                game_id = _get_or_create_game(
                    database, article_row["game"], article_row.get("platform")
                )

            article_row["issue_id"] = issue_id
            article_row["game_id"] = game_id
            database["articles"].insert(article_row)
            article_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]

            for img_path in images:
                database["images"].insert({"article_id": article_id, "path": img_path})

            total_articles += 1

        total_issues += 1
        click.echo(f"  ✓ {json_file.name}", err=True)

    click.echo(f"\nExportado: {total_issues} números, {total_articles} artículos → {db}")
