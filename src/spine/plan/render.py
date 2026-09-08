"""The short plan block a session is given at the top of its context."""

from __future__ import annotations

from ..constants import PLAN_CONTEXT_MAX_ITEMS
from .model import ItemStatus, PlanState

PLAN_HEADING = "### Where this sits in the plan"
NO_PLAN = ""
STATUS_MARK = {
    ItemStatus.DONE: "done",
    ItemStatus.PARTIAL: "partial",
    ItemStatus.IN_PROGRESS: "in progress",
    ItemStatus.BLOCKED: "blocked",
    ItemStatus.NOT_STARTED: "open",
    ItemStatus.UNKNOWN: "unstated",
}


def _progress_line(*, state: PlanState) -> str:
    return f"{state.done_count} of {len(state.items)} tracked items done"


def _milestone_line(*, state: PlanState) -> str | None:
    current = state.current_milestone
    if current is None:
        return None
    position = f"{current.ordinal + 1} of {len(state.milestones)}"
    target = f", target {current.target}" if current.target else ""
    return f"Current milestone: **{current.title}** ({position}{target})"


def _item_lines(*, state: PlanState) -> tuple[str, ...]:
    current = state.current_milestone
    scope = (
        state.items_for(milestone=current.title)
        if current is not None
        else tuple(item for item in state.items if not item.status.is_settled)
    )
    open_items = [item for item in scope if not item.status.is_settled]
    return tuple(
        f"- {item.title} ({STATUS_MARK[item.status]})"
        for item in open_items[:PLAN_CONTEXT_MAX_ITEMS]
    )


def render_plan(*, state: PlanState, open_questions: tuple[str, ...] = ()) -> str:
    """A compact statement of where the project stands, or empty when there is no plan."""
    if not state.has_plan:
        return NO_PLAN
    lines = [PLAN_HEADING, ""]
    milestone = _milestone_line(state=state)
    if milestone is not None:
        lines.append(milestone)
    if state.items:
        lines.append(_progress_line(state=state))
    blocked = state.blocked
    if blocked:
        lines.append(f"Blocked: {blocked[0].title}")
    item_lines = _item_lines(state=state)
    if item_lines:
        lines.extend(("", *item_lines))
    if open_questions:
        lines.extend(("", "Open questions:"))
        lines.extend(f"- {question}" for question in open_questions[:PLAN_CONTEXT_MAX_ITEMS])
    return "\n".join(lines)
