"""Decision-log entries and whether they have been seen."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..constants import DECISION_REVIEW_MAX_SHOWN, DECISIONS_DB_FILE_NAME
from ..model import Doc
from ..paths import ensure_spine_home, spine_home

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    entry_id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    acknowledged_at TEXT
)
"""
DECISION_LOG_KIND = "decision_log"


def decisions_db_path() -> Path:
    return spine_home() / DECISIONS_DB_FILE_NAME


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Decision:
    """One recorded decision, and whether it has been acknowledged."""

    entry_id: str
    project_slug: str
    title: str
    doc_id: str
    first_seen: str
    acknowledged_at: str | None = None

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "project_slug": self.project_slug,
            "title": self.title,
            "doc_id": self.doc_id,
            "first_seen": self.first_seen,
            "acknowledged_at": self.acknowledged_at,
        }


def decision_entries(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    """Entry nodes inside the project's decision logs."""
    log_ids = {doc.doc_id for doc in docs if str(doc.kind) == DECISION_LOG_KIND}
    return tuple(doc for doc in docs if doc.is_entry and doc.parent_doc_id in log_ids)


class DecisionStore:
    """Tracks which logged decisions a human has already seen."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else decisions_db_path()
        with self._connect() as connection:
            connection.execute(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def record(self, *, project_slug: str, entries: tuple[Doc, ...]) -> int:
        """Register entries not seen before; returns how many were new."""
        stamp = now_iso()
        rows = [
            (entry.doc_id, project_slug, entry.title, entry.parent_doc_id or "", stamp)
            for entry in entries
        ]
        with self._connect() as connection:
            cursor = connection.executemany(
                "INSERT OR IGNORE INTO decisions"
                " (entry_id, project_slug, title, doc_id, first_seen) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            return cursor.rowcount

    def pending(self, *, project_slug: str | None = None) -> tuple[Decision, ...]:
        """Decisions nobody has acknowledged, newest first."""
        query = "SELECT * FROM decisions WHERE acknowledged_at IS NULL"
        parameters: tuple[str, ...] = ()
        if project_slug is not None:
            query += " AND project_slug = ?"
            parameters = (project_slug,)
        query += " ORDER BY first_seen DESC, entry_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_row_to_decision(row=row) for row in rows[:DECISION_REVIEW_MAX_SHOWN])

    def acknowledge(self, *, entry_id: str) -> bool:
        """Mark one decision seen; False when it is unknown or already acknowledged."""
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE decisions SET acknowledged_at = ?"
                " WHERE entry_id = ? AND acknowledged_at IS NULL",
                (now_iso(), entry_id),
            )
            return cursor.rowcount > 0


def _row_to_decision(*, row: sqlite3.Row) -> Decision:
    return Decision(
        entry_id=row["entry_id"],
        project_slug=row["project_slug"],
        title=row["title"],
        doc_id=row["doc_id"],
        first_seen=row["first_seen"],
        acknowledged_at=row["acknowledged_at"],
    )
