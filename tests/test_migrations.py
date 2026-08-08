from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.db.sqlite import apply_migrations


class MigrationSafetyTests(unittest.TestCase):
    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def test_failed_migration_rolls_back_schema_and_marker_together(self) -> None:
        connection = self._connection()
        self.addCleanup(connection.close)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "001_broken.sql").write_text(
                "CREATE TABLE leaked_state(id TEXT);\nTHIS IS NOT SQL;\n",
                encoding="utf-8",
            )
            with patch("pipeline.db.sqlite.MIGRATIONS_DIR", root):
                with self.assertRaises(sqlite3.OperationalError):
                    apply_migrations(connection)

        leaked = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='leaked_state'"
        ).fetchone()
        marker = connection.execute(
            "SELECT version FROM schema_migrations WHERE version='001_broken'"
        ).fetchone()
        self.assertIsNone(leaked)
        self.assertIsNone(marker)

    def test_interrupted_autonomy_column_addition_is_recoverable(self) -> None:
        connection = self._connection()
        self.addCleanup(connection.close)
        connection.executescript(
            """
            CREATE TABLE projects(project_id TEXT PRIMARY KEY);
            CREATE TABLE episodes(episode_id TEXT PRIMARY KEY);
            CREATE TABLE render_jobs(
              job_id TEXT PRIMARY KEY,
              job_type TEXT NOT NULL,
              autonomy_run_id TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        migration = (
            Path(__file__).parents[1]
            / "pipeline"
            / "migrations"
            / "004_autonomy_runs.sql"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "004_autonomy_runs.sql").write_text(
                migration, encoding="utf-8"
            )
            with patch("pipeline.db.sqlite.MIGRATIONS_DIR", root):
                apply_migrations(connection)

        marker = connection.execute(
            "SELECT version FROM schema_migrations WHERE version='004_autonomy_runs'"
        ).fetchone()
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(render_jobs)")
        }
        self.assertIsNotNone(marker)
        self.assertIn("autonomy_run_id", columns)


if __name__ == "__main__":
    unittest.main()
