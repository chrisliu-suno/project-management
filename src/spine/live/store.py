"""Shared state for concurrent sessions.

Each session writes only its own row, so declaring intent and picking up
steering never contend. Only changing a shared conclusion takes a lease.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..constants import (
    MAX_BROADCAST_REPLAY,
    SESSION_LEASE_SECONDS,
    SESSION_STALE_SECONDS,
    SESSIONS_DB_FILE_NAME,
)
from ..paths import ensure_spine_home, spine_home
from .model import Broadcast, LiveSession, SessionState, SteeringAction, SteeringMessage

PROJECT_SLUG_SEPARATOR = ","
PATH_SEPARATOR = "\n"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS live_sessions (
    session_id TEXT PRIMARY KEY,
    project_slugs TEXT NOT NULL,
    intent TEXT NOT NULL,
    state TEXT NOT NULL,
    declared_paths TEXT NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steering (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    action TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS broadcasts (
    broadcast_id TEXT PRIMARY KEY,
    project_slug TEXT NOT NULL,
    headline TEXT NOT NULL,
    body TEXT NOT NULL,
    origin_session_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
    subject TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def sessions_db_path() -> Path:
    return spine_home() / SESSIONS_DB_FILE_NAME


class LiveStore:
    """Session declarations, steering messages, broadcasts, and leases."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else sessions_db_path()
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def declare(
        self,
        *,
        session_id: str,
        project_slugs: tuple[str, ...],
        intent: str,
        declared_paths: tuple[str, ...] = (),
        state: SessionState = SessionState.WORKING,
    ) -> LiveSession:
        """Record what a session says it is doing, replacing its previous line."""
        stamp = now_iso()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT started_at FROM live_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            started = existing["started_at"] if existing else stamp
            connection.execute(
                "INSERT OR REPLACE INTO live_sessions"
                " (session_id, project_slugs, intent, state, declared_paths,"
                "  started_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    PROJECT_SLUG_SEPARATOR.join(project_slugs),
                    intent,
                    str(state),
                    PATH_SEPARATOR.join(declared_paths),
                    started,
                    stamp,
                ),
            )
        return LiveSession(
            session_id=session_id,
            project_slugs=project_slugs,
            intent=intent,
            state=state,
            declared_paths=declared_paths,
            started_at=started,
            updated_at=stamp,
        )

    def _row_to_session(self, *, row: sqlite3.Row) -> LiveSession:
        slugs = row["project_slugs"]
        paths = row["declared_paths"]
        return LiveSession(
            session_id=row["session_id"],
            project_slugs=tuple(s for s in slugs.split(PROJECT_SLUG_SEPARATOR) if s),
            intent=row["intent"],
            state=SessionState(row["state"]),
            declared_paths=tuple(p for p in paths.split(PATH_SEPARATOR) if p),
            started_at=row["started_at"],
            updated_at=row["updated_at"],
        )

    def live_sessions(self, *, include_stale: bool = False) -> tuple[LiveSession, ...]:
        """Sessions that have reported recently, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM live_sessions ORDER BY updated_at DESC"
            ).fetchall()
        found = tuple(self._row_to_session(row=row) for row in rows)
        if include_stale:
            return found
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=SESSION_STALE_SECONDS)
        return tuple(
            session
            for session in found
            if datetime.fromisoformat(session.updated_at) >= cutoff
        )

    def steer(
        self, *, session_id: str, action: SteeringAction, body: str = ""
    ) -> SteeringMessage:
        """Queue an instruction for a session to pick up at its next boundary."""
        stamp = now_iso()
        message_id = f"{session_id}:{action}:{stamp}"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO steering"
                " (message_id, session_id, action, body, created_at, delivered_at)"
                " VALUES (?, ?, ?, ?, ?, NULL)",
                (message_id, session_id, str(action), body, stamp),
            )
        return SteeringMessage(
            message_id=message_id,
            session_id=session_id,
            action=action,
            body=body,
            created_at=stamp,
        )

    def drain_steering(self, *, session_id: str) -> tuple[SteeringMessage, ...]:
        """Undelivered instructions for a session, marked delivered as they are read."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM steering WHERE session_id = ? AND delivered_at IS NULL"
                " ORDER BY created_at",
                (session_id,),
            ).fetchall()
            if rows:
                connection.execute(
                    "UPDATE steering SET delivered_at = ?"
                    " WHERE session_id = ? AND delivered_at IS NULL",
                    (now_iso(), session_id),
                )
        return tuple(
            SteeringMessage(
                message_id=row["message_id"],
                session_id=row["session_id"],
                action=SteeringAction(row["action"]),
                body=row["body"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def broadcast(
        self, *, project_slug: str, headline: str, body: str, origin_session_id: str
    ) -> Broadcast:
        """Publish something every session on a project should know."""
        stamp = now_iso()
        broadcast_id = f"{project_slug}:{stamp}"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO broadcasts"
                " (broadcast_id, project_slug, headline, body, origin_session_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (broadcast_id, project_slug, headline, body, origin_session_id, stamp),
            )
        return Broadcast(
            broadcast_id=broadcast_id,
            project_slug=project_slug,
            headline=headline,
            body=body,
            origin_session_id=origin_session_id,
            created_at=stamp,
        )

    def broadcasts_for(self, *, project_slug: str) -> tuple[Broadcast, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM broadcasts WHERE project_slug = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (project_slug, MAX_BROADCAST_REPLAY),
            ).fetchall()
        return tuple(
            Broadcast(
                broadcast_id=row["broadcast_id"],
                project_slug=row["project_slug"],
                headline=row["headline"],
                body=row["body"],
                origin_session_id=row["origin_session_id"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def acquire_lease(self, *, subject: str, session_id: str) -> bool:
        """Take a lease on a shared conclusion; expired leases are reclaimable."""
        now = datetime.now(tz=UTC)
        expires = (now + timedelta(seconds=SESSION_LEASE_SECONDS)).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, expires_at FROM leases WHERE subject = ?", (subject,)
            ).fetchone()
            is_free = row is None or datetime.fromisoformat(row["expires_at"]) < now
            if not is_free and row["session_id"] != session_id:
                return False
            connection.execute(
                "INSERT OR REPLACE INTO leases (subject, session_id, expires_at)"
                " VALUES (?, ?, ?)",
                (subject, session_id, expires),
            )
        return True

    def lease_holder(self, *, subject: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id, expires_at FROM leases WHERE subject = ?", (subject,)
            ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(tz=UTC):
            return None
        return row["session_id"]

    def release_lease(self, *, subject: str, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM leases WHERE subject = ? AND session_id = ?", (subject, session_id)
            )
        return cursor.rowcount > 0
