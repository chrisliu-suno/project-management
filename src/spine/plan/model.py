"""Plan state derived from prose: milestones, the work under them, and progress."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..constants import PLAN_SETTLED_STATUSES, PLAN_STALLED_STATUSES


class ItemStatus(StrEnum):
    """Where one piece of work stands."""

    DONE = "done"
    PARTIAL = "partial"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    NOT_STARTED = "not_started"
    UNKNOWN = "unknown"

    @property
    def is_settled(self) -> bool:
        return self.value in PLAN_SETTLED_STATUSES

    @property
    def needs_attention(self) -> bool:
        return self.value in PLAN_STALLED_STATUSES


@dataclass(frozen=True, slots=True)
class WorkItem:
    """One unit of work named in a plan document."""

    title: str
    status: ItemStatus
    doc_id: str
    line: int
    milestone: str | None = None
    evidence: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "status": str(self.status),
            "doc_id": self.doc_id,
            "line": self.line,
            "milestone": self.milestone,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class Milestone:
    """A named stage of a project, in the order the document presents it."""

    title: str
    ordinal: int
    doc_id: str
    line: int
    target: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "ordinal": self.ordinal,
            "doc_id": self.doc_id,
            "line": self.line,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class PlanState:
    """Everything derived about where a project stands."""

    project_slug: str
    milestones: tuple[Milestone, ...] = field(default=())
    items: tuple[WorkItem, ...] = field(default=())
    open_questions: tuple[str, ...] = field(default=())

    @property
    def has_plan(self) -> bool:
        return bool(self.milestones or self.items)

    def items_for(self, *, milestone: str | None) -> tuple[WorkItem, ...]:
        return tuple(item for item in self.items if item.milestone == milestone)

    @property
    def done_count(self) -> int:
        return sum(1 for item in self.items if item.status is ItemStatus.DONE)

    @property
    def blocked(self) -> tuple[WorkItem, ...]:
        return tuple(item for item in self.items if item.status.needs_attention)

    @property
    def current_milestone(self) -> Milestone | None:
        """The earliest milestone with work still unsettled."""
        for milestone in self.milestones:
            unsettled = [
                item
                for item in self.items_for(milestone=milestone.title)
                if not item.status.is_settled
            ]
            if unsettled:
                return milestone
        return None

    def as_dict(self) -> dict[str, object]:
        return {
            "project_slug": self.project_slug,
            "milestones": [milestone.as_dict() for milestone in self.milestones],
            "items": [item.as_dict() for item in self.items],
            "open_questions": list(self.open_questions),
            "done_count": self.done_count,
            "item_count": len(self.items),
            "current_milestone": (
                self.current_milestone.title if self.current_milestone is not None else None
            ),
        }
