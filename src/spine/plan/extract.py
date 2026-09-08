"""Reading plan state out of the documents a project already has."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..constants import (
    PLAN_DONE_WEIGHT,
    PLAN_MAX_OPEN_QUESTIONS,
)
from ..model import Doc
from .headings import (
    heading_at,
    is_milestone,
    is_open_questions,
    milestone_title,
    target_in,
)
from .model import ItemStatus, Milestone, PlanState, WorkItem
from .status import status_from
from .tables import (
    cells_in,
    evidence_column,
    is_separator_row,
    is_table_row,
    status_column,
    title_column,
)

CHECKBOX_PATTERN = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*\S)\s*$")
BULLET_PATTERN = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
CHECKED_MARKS = frozenset({"x", "X"})
TRAILING_REFERENCE_PATTERN = re.compile(r"\s*\(\d+(?:\.\d+)?\)\s*$")
EMPHASIS_PATTERN = re.compile(r"[*_`]+")


@dataclass
class _Cursor:
    """Where the walk currently is inside one document."""

    milestone: str | None = None
    is_in_questions: bool = False
    headers: tuple[str, ...] | None = None
    status_at: int | None = None


def _clean_title(*, text: str) -> str:
    without_reference = TRAILING_REFERENCE_PATTERN.sub("", text)
    return EMPHASIS_PATTERN.sub("", without_reference).strip()


def _checkbox_item(*, line: str, doc: Doc, number: int, cursor: _Cursor) -> WorkItem | None:
    matched = CHECKBOX_PATTERN.match(line)
    if matched is None:
        return None
    status = ItemStatus.DONE if matched.group(1) in CHECKED_MARKS else ItemStatus.NOT_STARTED
    return WorkItem(
        title=_clean_title(text=matched.group(2)),
        status=status,
        doc_id=doc.doc_id,
        line=number,
        milestone=cursor.milestone,
    )


def _table_item(*, line: str, doc: Doc, number: int, cursor: _Cursor) -> WorkItem | None:
    if cursor.headers is None or cursor.status_at is None:
        return None
    cells = cells_in(line=line)
    if len(cells) <= cursor.status_at:
        return None
    title_at = title_column(headers=cursor.headers, status_at=cursor.status_at)
    evidence_at = evidence_column(headers=cursor.headers)
    evidence = cells[evidence_at] if evidence_at is not None and evidence_at < len(cells) else ""
    return WorkItem(
        title=_clean_title(text=cells[title_at]) if title_at < len(cells) else "",
        status=status_from(text=cells[cursor.status_at]),
        doc_id=doc.doc_id,
        line=number,
        milestone=cursor.milestone,
        evidence=evidence,
    )


def _apply_heading(*, heading: str, doc: Doc, number: int, cursor: _Cursor, ordinal: int):
    """Update the cursor for a heading, returning a milestone when it names one."""
    cursor.headers = None
    cursor.status_at = None
    cursor.is_in_questions = is_open_questions(heading=heading)
    if cursor.is_in_questions or not is_milestone(heading=heading):
        return None
    title = milestone_title(heading=heading)
    cursor.milestone = title
    return Milestone(
        title=title,
        ordinal=ordinal,
        doc_id=doc.doc_id,
        line=number,
        target=target_in(heading=heading),
    )


def plan_in(*, doc: Doc) -> PlanState:
    """Milestones, work items, and open questions stated by one document."""
    cursor = _Cursor()
    milestones: list[Milestone] = []
    items: list[WorkItem] = []
    questions: list[str] = []

    for number, line in enumerate(doc.body.splitlines(), start=1):
        found_heading = heading_at(line=line)
        if found_heading is not None:
            milestone = _apply_heading(
                heading=found_heading[1],
                doc=doc,
                number=number,
                cursor=cursor,
                ordinal=len(milestones),
            )
            if milestone is not None:
                milestones.append(milestone)
            continue

        if is_table_row(line=line):
            if is_separator_row(line=line):
                continue
            if cursor.headers is None:
                cursor.headers = cells_in(line=line)
                cursor.status_at = status_column(headers=cursor.headers)
                continue
            row_item = _table_item(line=line, doc=doc, number=number, cursor=cursor)
            if row_item is not None and row_item.title:
                items.append(row_item)
            continue
        cursor.headers = None
        cursor.status_at = None

        checkbox = _checkbox_item(line=line, doc=doc, number=number, cursor=cursor)
        if checkbox is not None:
            items.append(checkbox)
            continue

        if cursor.is_in_questions:
            bullet = BULLET_PATTERN.match(line)
            if bullet is not None:
                questions.append(_clean_title(text=bullet.group(1)))

    return PlanState(
        project_slug=doc.project_slug,
        milestones=tuple(milestones),
        items=tuple(items),
        open_questions=tuple(questions),
    )


def plan_richness(*, state: PlanState) -> int:
    """How much decided plan a document carries.

    Completed work dominates: a document recording finished items is where the
    project actually is. Unticked boxes and unreadable rows count for nothing, so
    a long checklist nobody started cannot outrank a short status table.
    """
    moved = sum(
        1 for item in state.items if item.status not in (ItemStatus.UNKNOWN, ItemStatus.NOT_STARTED)
    )
    return state.done_count * PLAN_DONE_WEIGHT + moved + len(state.milestones)


def project_plans(*, docs: tuple[Doc, ...]) -> tuple[tuple[Doc, PlanState], ...]:
    """Every document that states a plan, richest first.

    Plans stay per-document rather than merged: two documents describe two
    different plans, and merging them invents milestones nobody wrote.
    """
    found = []
    for doc in docs:
        if doc.is_entry:
            continue
        state = plan_in(doc=doc)
        if state.has_plan:
            found.append((plan_richness(state=state), doc.doc_id, doc, state))
    ranked = sorted(found, key=lambda entry: (-entry[0], entry[1]))
    return tuple((doc, state) for _, _, doc, state in ranked)


def primary_plan(*, docs: tuple[Doc, ...], project_slug: str) -> PlanState:
    """The plan a session should be told about, or an empty state when there is none."""
    plans = project_plans(docs=docs)
    if not plans:
        return PlanState(project_slug=project_slug)
    return plans[0][1]


def open_questions_across(*, docs: tuple[Doc, ...]) -> tuple[str, ...]:
    """Open questions from anywhere in the corpus, deduplicated in reading order."""
    questions: list[str] = []
    for doc in docs:
        if doc.is_entry:
            continue
        questions.extend(plan_in(doc=doc).open_questions)
    return tuple(dict.fromkeys(questions))[:PLAN_MAX_OPEN_QUESTIONS]
