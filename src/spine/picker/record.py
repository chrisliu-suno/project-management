"""Durable record of every context selection, and the grouped view over it."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..constants import (
    DOC_ID_LIST_SEPARATOR,
    MIN_CONFIDENCE_FOR_SILENT_PICK,
    PICKS_DB_BUSY_TIMEOUT_SECONDS,
    PICKS_TABLE_NAME,
)
from ..model import Doc, ReadWhen, Selection
from ..paths import picks_db_path

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PICKS_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    chosen_doc_ids TEXT NOT NULL,
    dropped_doc_ids TEXT NOT NULL,
    total_lines INTEGER NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    has_dropped_every_time INTEGER NOT NULL,
    has_in_area_match INTEGER NOT NULL
)
"""

_INSERT_SQL = f"""
INSERT INTO {PICKS_TABLE_NAME} (
    session_id, project_slug, recorded_at, chosen_doc_ids, dropped_doc_ids,
    total_lines, reason, confidence, has_dropped_every_time, has_in_area_match
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SUMMARY_SQL = f"""
SELECT
    COUNT(*),
    COALESCE(SUM(confidence < ?), 0),
    COALESCE(SUM(has_dropped_every_time), 0),
    COALESCE(SUM(has_in_area_match = 0), 0)
FROM {PICKS_TABLE_NAME}
"""


@dataclass(frozen=True, slots=True)
class PickSummary:
    """Grouped counts across recorded picks. Categories only, never rows."""

    total_picks: int
    low_confidence_picks: int
    every_time_dropped_picks: int
    no_in_area_match_picks: int


EMPTY_PICK_SUMMARY = PickSummary(
    total_picks=0,
    low_confidence_picks=0,
    every_time_dropped_picks=0,
    no_in_area_match_picks=0,
)


def joined_doc_ids(*, docs: Iterable[Doc]) -> str:
    """Doc ids as one delimited field."""
    return DOC_ID_LIST_SEPARATOR.join(doc.doc_id for doc in docs)


def has_dropped_every_time(*, selection: Selection) -> bool:
    """Whether the budget forced out a doc the session was supposed to always get."""
    return any(doc.read_when == ReadWhen.EVERY_TIME for doc in selection.dropped)


def has_in_area_doc(*, selection: Selection) -> bool:
    """Whether the chosen set holds anything from the in-area group."""
    return any(doc.read_when == ReadWhen.IN_AREA for doc in selection.chosen)


def _connect(*, db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=PICKS_DB_BUSY_TIMEOUT_SECONDS)
    try:
        connection.execute(_CREATE_TABLE_SQL)
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _resolved_db_path(*, db_path: Path | None) -> Path:
    return db_path if db_path is not None else picks_db_path()


class SqlitePickRecorder:
    """Writes one row per selection. Recording is unconditional and prints nothing."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        """Resolved late so the state root can move between construction and use."""
        return _resolved_db_path(db_path=self._db_path)

    def record(
        self,
        *,
        session_id: str,
        project_slug: str,
        selection: Selection,
        confidence: float,
    ) -> None:
        """Persist one selection with the flags the grouped summary counts on.

        Swallows storage errors: a pick that cannot be recorded must still be used.
        """
        row = (
            session_id,
            project_slug,
            datetime.now(tz=UTC).isoformat(),
            joined_doc_ids(docs=selection.chosen),
            joined_doc_ids(docs=selection.dropped),
            selection.total_lines,
            selection.reason,
            confidence,
            int(has_dropped_every_time(selection=selection)),
            int(has_in_area_doc(selection=selection)),
        )
        try:
            connection = _connect(db_path=self.db_path)
        except (OSError, sqlite3.Error):
            return
        try:
            connection.execute(_INSERT_SQL, row)
            connection.commit()
        except sqlite3.Error:
            return
        finally:
            connection.close()


def summarize_picks(*, db_path: Path | None = None) -> PickSummary:
    """Counts per category for the daily page. Nothing recorded yet reads as zeros."""
    resolved_path = _resolved_db_path(db_path=db_path)
    if not resolved_path.exists():
        return EMPTY_PICK_SUMMARY
    connection = _connect(db_path=resolved_path)
    try:
        counts = connection.execute(_SUMMARY_SQL, (MIN_CONFIDENCE_FOR_SILENT_PICK,)).fetchone()
    finally:
        connection.close()
    return PickSummary(
        total_picks=int(counts[0]),
        low_confidence_picks=int(counts[1]),
        every_time_dropped_picks=int(counts[2]),
        no_in_area_match_picks=int(counts[3]),
    )
