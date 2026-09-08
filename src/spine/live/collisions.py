"""Sessions working the same ground at the same time."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ..constants import COLLISION_MAX_REPORTED
from .model import LiveSession, SessionState

WORKING_STATES = frozenset({str(SessionState.WORKING)})


@dataclass(frozen=True, slots=True)
class Collision:
    """Two live sessions that declared overlapping paths on a shared project."""

    left_session_id: str
    right_session_id: str
    project_slug: str
    path: str
    left_intent: str = ""
    right_intent: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "left_session_id": self.left_session_id,
            "right_session_id": self.right_session_id,
            "project_slug": self.project_slug,
            "path": self.path,
            "left_intent": self.left_intent,
            "right_intent": self.right_intent,
        }


def paths_overlap(*, left: str, right: str) -> bool:
    """Whether two declared paths cover any of the same files.

    One path containing the other counts: a session that declared a package
    collides with one that declared a module inside it.
    """
    if not left or not right:
        return False
    left_parts = PurePosixPath(left.strip("/")).parts
    right_parts = PurePosixPath(right.strip("/")).parts
    shortest = min(len(left_parts), len(right_parts))
    return left_parts[:shortest] == right_parts[:shortest]


def _shared_projects(*, left: LiveSession, right: LiveSession) -> tuple[str, ...]:
    return tuple(sorted(set(left.project_slugs) & set(right.project_slugs)))


def _first_overlap(*, left: LiveSession, right: LiveSession) -> str | None:
    for left_path in left.declared_paths:
        for right_path in right.declared_paths:
            if paths_overlap(left=left_path, right=right_path):
                return left_path if len(left_path) >= len(right_path) else right_path
    return None


def _is_active(*, session: LiveSession) -> bool:
    return str(session.state) in WORKING_STATES


def collisions_among(*, sessions: tuple[LiveSession, ...]) -> tuple[Collision, ...]:
    """Every pair of working sessions whose declared paths overlap on a shared project."""
    active = [session for session in sessions if _is_active(session=session)]
    found: list[Collision] = []
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            shared = _shared_projects(left=left, right=right)
            if not shared:
                continue
            overlap = _first_overlap(left=left, right=right)
            if overlap is None:
                continue
            found.append(
                Collision(
                    left_session_id=left.session_id,
                    right_session_id=right.session_id,
                    project_slug=shared[0],
                    path=overlap,
                    left_intent=left.intent,
                    right_intent=right.intent,
                )
            )
    return tuple(found[:COLLISION_MAX_REPORTED])
