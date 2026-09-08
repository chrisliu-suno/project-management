"""Renders the always-read documents a session starts with."""

from __future__ import annotations

from ..constants import EVERY_TIME_RESERVED_LINES
from ..model import Doc, Project, ReadWhen

CONTEXT_HEADER = "# Project context"
NO_PROJECT_MESSAGE = ""
TRUNCATION_NOTE = "_(truncated to fit the always-read budget)_"
DOC_SEPARATOR = "\n\n"


def always_read(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    """The documents that load on every task, largest last so small ones survive."""
    group = [
        doc for doc in docs if doc.read_when is ReadWhen.EVERY_TIME and not doc.is_entry
    ]
    return tuple(sorted(group, key=lambda doc: (doc.line_count, doc.doc_id)))


def _within_budget(*, docs: tuple[Doc, ...], budget: int) -> tuple[tuple[Doc, ...], bool]:
    kept: list[Doc] = []
    spent = 0
    for doc in docs:
        if spent + doc.line_count > budget:
            return tuple(kept), True
        kept.append(doc)
        spent += doc.line_count
    return tuple(kept), False


def _render_doc(*, doc: Doc) -> str:
    return f"## {doc.title}\n\n_{doc.doc_id} · {doc.kind}_\n\n{doc.body.strip()}"


def _plan_block(*, docs: tuple[Doc, ...], project: Project) -> str:
    """Where the project stands, when its documents say."""
    from ..plan import open_questions_across, primary_plan
    from ..plan.render import render_plan

    return render_plan(
        state=primary_plan(docs=docs, project_slug=project.slug),
        open_questions=open_questions_across(docs=docs),
    )


def render_project(*, project: Project, docs: tuple[Doc, ...], budget: int) -> str:
    """One project's plan position and always-read documents, trimmed to the budget."""
    selected, was_truncated = _within_budget(docs=always_read(docs=docs), budget=budget)
    plan = _plan_block(docs=docs, project=project)
    if not selected and not plan:
        return ""
    blocks = [f"## Project: {project.name} (`{project.slug}`)"]
    if plan:
        blocks.append(plan)
    blocks.extend(_render_doc(doc=doc) for doc in selected)
    if was_truncated:
        blocks.append(TRUNCATION_NOTE)
    return DOC_SEPARATOR.join(blocks)


def render_context(
    *,
    rendered_projects: tuple[str, ...],
    budget: int = EVERY_TIME_RESERVED_LINES,
) -> str:
    """The whole injection payload, or empty when no project applies."""
    populated = tuple(block for block in rendered_projects if block.strip())
    if not populated:
        return NO_PROJECT_MESSAGE
    return DOC_SEPARATOR.join((CONTEXT_HEADER, *populated))
