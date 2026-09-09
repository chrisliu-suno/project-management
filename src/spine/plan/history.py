"""Plan state over time, so progress is visible as a series and not just a number."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..constants import PLAN_HISTORY_DB_FILE_NAME, PLAN_HISTORY_MAX_POINTS
from ..paths import ensure_spine_home, spine_home
from .model import PlanState

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plan_points (
    project_slug TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    milestone TEXT,
    done_count INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    blocked_count INTEGER NOT NULL,
    PRIMARY KEY (project_slug, taken_at)
)
"""


def plan_history_db_path() -> Path:
    return spine_home() / PLAN_HISTORY_DB_FILE_NAME


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class PlanPoint:
    """One reading of a project's plan state."""

    project_slug: str
    taken_at: str
    done_count: int
    item_count: int
    blocked_count: int
    milestone: str | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.item_count - self.done_count)

    def as_dict(self) -> dict[str, object]:
        return {
            "project_slug": self.project_slug,
            "taken_at": self.taken_at,
            "milestone": self.milestone,
            "done_count": self.done_count,
            "item_count": self.item_count,
            "blocked_count": self.blocked_count,
            "remaining": self.remaining,
        }

    def same_reading_as(self, *, other: PlanPoint | None) -> bool:
        """Whether this says nothing new, ignoring when it was taken."""
        if other is None:
            return False
        return (
            self.milestone == other.milestone
            and self.done_count == other.done_count
            and self.item_count == other.item_count
            and self.blocked_count == other.blocked_count
        )


def point_from(*, state: PlanState, taken_at: str) -> PlanPoint:
    """A reading taken from current plan state."""
    current = state.current_milestone
    return PlanPoint(
        project_slug=state.project_slug,
        taken_at=taken_at,
        done_count=state.done_count,
        item_count=len(state.items),
        blocked_count=len(state.blocked),
        milestone=current.title if current is not None else None,
    )


class PlanHistoryStore:
    """Keeps one row per change in a project's plan state.

    An unchanged reading is dropped rather than stored: the sweep runs hourly, and a
    burn-down of identical points is noise that hides the days something moved.
    """

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else plan_history_db_path()
        with self._connect() as connection:
            connection.execute(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def latest(self, *, project_slug: str) -> PlanPoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM plan_points WHERE project_slug = ? ORDER BY taken_at DESC LIMIT 1",
                (project_slug,),
            ).fetchone()
        return _row_to_point(row=row) if row is not None else None

    def record(self, *, point: PlanPoint) -> bool:
        """Store a reading unless it repeats the last one; True when stored."""
        if point.same_reading_as(other=self.latest(project_slug=point.project_slug)):
            return False
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO plan_points"
                " (project_slug, taken_at, milestone, done_count, item_count, blocked_count)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    point.project_slug,
                    point.taken_at,
                    point.milestone,
                    point.done_count,
                    point.item_count,
                    point.blocked_count,
                ),
            )
        return True

    def series(self, *, project_slug: str) -> tuple[PlanPoint, ...]:
        """Every stored reading for a project, oldest first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM plan_points WHERE project_slug = ? ORDER BY taken_at",
                (project_slug,),
            ).fetchall()
        points = tuple(_row_to_point(row=row) for row in rows)
        return points[-PLAN_HISTORY_MAX_POINTS:]


def _row_to_point(*, row: sqlite3.Row) -> PlanPoint:
    return PlanPoint(
        project_slug=row["project_slug"],
        taken_at=row["taken_at"],
        milestone=row["milestone"],
        done_count=row["done_count"],
        item_count=row["item_count"],
        blocked_count=row["blocked_count"],
    )


def record_for_project(*, project, taken_at: str | None = None) -> bool:
    """Take a reading of one project's plan and store it if it changed."""
    from ..index import load_corpus
    from . import primary_plan

    if not project.docs_dir.is_dir():
        return False
    docs = load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)
    state = primary_plan(docs=docs, project_slug=project.slug)
    if not state.has_plan:
        return False
    point = point_from(state=state, taken_at=taken_at or now_iso())
    return PlanHistoryStore().record(point=point)
