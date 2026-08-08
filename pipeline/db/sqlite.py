from __future__ import annotations

import json
import sqlite3
import fcntl
from pathlib import Path
from typing import Any, Iterable

from pipeline import config
from pipeline.models import now_iso
from pipeline.storage import PROJECT_ROOT, resolve_project_path

DEFAULT_DB_PATH = PROJECT_ROOT / ".synthpost" / "synthpost.sqlite3"
MIGRATIONS_DIR = PROJECT_ROOT / "pipeline" / "migrations"


def database_path(value: str | Path | None = None) -> Path:
    configured = value or config.get_settings().storage.database_path or DEFAULT_DB_PATH
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
        # Recover safely if an older build was interrupted after migration 004
        # added its column but before schema_migrations was updated.
        if version == "004_autonomy_runs":
            job_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(render_jobs)")
            }
            if "autonomy_run_id" in job_columns:
                sql = sql.replace(
                    "ALTER TABLE render_jobs ADD COLUMN autonomy_run_id TEXT;", ""
                )

        # sqlite3.executescript commits a transaction opened outside the
        # script. Put BEGIN/COMMIT and the migration marker in the same script
        # so a crash cannot leave a half-applied migration behind.
        quoted_version = version.replace("'", "''")
        quoted_applied_at = now_iso().replace("'", "''")
        script = (
            "BEGIN IMMEDIATE;\n"
            f"{sql}\n"
            "INSERT INTO schema_migrations(version, applied_at) "
            f"VALUES ('{quoted_version}', '{quoted_applied_at}');\n"
            "COMMIT;"
        )
        try:
            connection.executescript(script)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise


def init_db(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = database_path(path)
    # The API and three lane workers can cold-start simultaneously. Serialize
    # WAL activation and migrations so a fresh database cannot race on schema
    # creation or schema_migrations inserts.
    lock_path = db_path.with_suffix(db_path.suffix + ".init.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            connection = connect(db_path)
            apply_migrations(connection)
            return connection
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
