from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from pipeline.models import now_iso
from pipeline.storage import PROJECT_ROOT, resolve_project_path

DEFAULT_DB_PATH = PROJECT_ROOT / ".synthpost" / "synthpost.sqlite3"
MIGRATIONS_DIR = PROJECT_ROOT / "pipeline" / "migrations"


def database_path(value: str | Path | None = None) -> Path:
    configured = value or os.environ.get("SYNTHPOST_DB_PATH") or DEFAULT_DB_PATH
    return resolve_project_path(configured)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = database_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        row["version"]
        for row in connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    }
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration.stem
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8")
        with connection:
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now_iso()),
            )


def init_db(path: str | Path | None = None) -> sqlite3.Connection:
    connection = connect(path)
    apply_migrations(connection)
    return connection


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def loads(value: str | bytes | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


def row_data(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return loads(row["data"])


def rows_data(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [loads(row["data"]) for row in rows]
