"""Persists proposed edits and their decisions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..constants import PROPOSAL_MAX_PER_PROJECT, PROPOSALS_DB_FILE_NAME
from ..live.store import now_iso
from ..paths import ensure_spine_home, spine_home
from .model import Proposal, ProposalKind, ProposalState

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    doc_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    headline TEXT NOT NULL,
    rationale TEXT NOT NULL,
    body TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT ''
)
"""

UPSERT_SQL = """
INSERT OR IGNORE INTO proposals
    (proposal_id, project_slug, doc_id, doc_path, kind, headline, rationale,
     body, state, created_at, decided_at)
VALUES
    (:proposal_id, :project_slug, :doc_id, :doc_path, :kind, :headline, :rationale,
     :body, :state, :created_at, :decided_at)
"""

SELECT_PENDING_SQL = """
SELECT * FROM proposals WHERE project_slug = :project_slug AND state = :state
ORDER BY created_at DESC LIMIT :limit
"""

SELECT_ALL_PENDING_SQL = """
SELECT * FROM proposals WHERE state = :state ORDER BY created_at DESC
"""

SELECT_ONE_SQL = "SELECT * FROM proposals WHERE proposal_id = :proposal_id"
DECIDE_SQL = """
UPDATE proposals SET state = :state, decided_at = :decided_at
WHERE proposal_id = :proposal_id AND state = :pending
"""


def proposals_db_path() -> Path:
    return spine_home() / PROPOSALS_DB_FILE_NAME


def _row_to_proposal(*, row: sqlite3.Row) -> Proposal:
    return Proposal(
        proposal_id=row["proposal_id"],
        project_slug=row["project_slug"],
        doc_id=row["doc_id"],
        doc_path=row["doc_path"],
        kind=ProposalKind(row["kind"]),
        headline=row["headline"],
        rationale=row["rationale"],
        body=row["body"],
        state=ProposalState(row["state"]),
        created_at=row["created_at"],
        decided_at=row["decided_at"],
    )


class ProposalStore:
    """SQLite store keyed by a content-stable proposal id, so drafting twice is safe."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else proposals_db_path()
        with self._connect() as connection:
            connection.execute(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, *, proposals: tuple[Proposal, ...]) -> int:
        """Insert proposals, ignoring any already drafted or already decided."""
        if not proposals:
            return 0
        with self._connect() as connection:
            cursor = connection.executemany(
                UPSERT_SQL, [proposal.as_dict() for proposal in proposals]
            )
        return cursor.rowcount

    def pending(self, *, project_slug: str | None = None) -> tuple[Proposal, ...]:
        with self._connect() as connection:
            if project_slug is None:
                rows = connection.execute(
                    SELECT_ALL_PENDING_SQL, {"state": str(ProposalState.PENDING)}
                ).fetchall()
            else:
                rows = connection.execute(
                    SELECT_PENDING_SQL,
                    {
                        "project_slug": project_slug,
                        "state": str(ProposalState.PENDING),
                        "limit": PROPOSAL_MAX_PER_PROJECT,
                    },
                ).fetchall()
        return tuple(_row_to_proposal(row=row) for row in rows)

    def get(self, *, proposal_id: str) -> Proposal | None:
        with self._connect() as connection:
            row = connection.execute(SELECT_ONE_SQL, {"proposal_id": proposal_id}).fetchone()
        return None if row is None else _row_to_proposal(row=row)

    def decide(self, *, proposal_id: str, state: ProposalState) -> bool:
        """Record a decision; returns False when it was already decided."""
        with self._connect() as connection:
            cursor = connection.execute(
                DECIDE_SQL,
                {
                    "proposal_id": proposal_id,
                    "state": str(state),
                    "decided_at": now_iso(),
                    "pending": str(ProposalState.PENDING),
                },
            )
        return cursor.rowcount > 0
