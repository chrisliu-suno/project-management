"""Persists observed facts so drift can be compared without re-observing."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..constants import FACTS_DB_FILE_NAME
from ..paths import ensure_spine_home, spine_home
from .model import Fact, FactKind

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    kind TEXT NOT NULL,
    reference TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    state TEXT NOT NULL,
    url TEXT NOT NULL
)
"""

UPSERT_SQL = """
INSERT OR REPLACE INTO facts
    (fact_id, project_slug, kind, reference, title, author, occurred_at, state, url)
VALUES
    (:fact_id, :project_slug, :kind, :reference, :title, :author, :occurred_at, :state, :url)
"""

SELECT_SQL = """
SELECT fact_id, project_slug, kind, reference, title, author, occurred_at, state, url
FROM facts WHERE project_slug = :project_slug ORDER BY occurred_at DESC
"""

COUNT_SQL = "SELECT COUNT(*) FROM facts WHERE project_slug = :project_slug"


def facts_db_path() -> Path:
    return spine_home() / FACTS_DB_FILE_NAME


class FactStore:
    """SQLite store keyed by a source-stable fact id, so re-observing is idempotent."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else facts_db_path()
        with self._connect() as connection:
            connection.execute(CREATE_TABLE_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def record(self, *, facts: tuple[Fact, ...]) -> int:
        """Upsert every fact; returns how many were written."""
        if not facts:
            return 0
        with self._connect() as connection:
            connection.executemany(UPSERT_SQL, [fact.as_dict() for fact in facts])
        return len(facts)

    def for_project(self, *, project_slug: str) -> tuple[Fact, ...]:
        with self._connect() as connection:
            rows = connection.execute(SELECT_SQL, {"project_slug": project_slug}).fetchall()
        return tuple(
            Fact(
                fact_id=row["fact_id"],
                project_slug=row["project_slug"],
                kind=FactKind(row["kind"]),
                reference=row["reference"],
                title=row["title"],
                author=row["author"],
                occurred_at=row["occurred_at"],
                state=row["state"],
                url=row["url"],
            )
            for row in rows
        )

    def count(self, *, project_slug: str) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(COUNT_SQL, {"project_slug": project_slug}).fetchone()[0]
            )
