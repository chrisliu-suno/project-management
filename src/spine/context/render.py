"""Renders the always-read documents a session starts with."""

from __future__ import annotations

from ..constants import EVERY_TIME_RESERVED_LINES
from ..model import Doc, Project, ReadWhen

CONTEXT_HEADER = "# Project context"
NO_PROJECT_MESSAGE = ""
TRUNCATION_NOTE = "_(truncated to fit the always-read budget)_"
DOC_SEPARATOR = "\n\n"
AMBIGUITY_HEADER = "# Project context — which project is this?"
AMBIGUITY_BODY = (
    "Several projects match this checkout equally, so no context was loaded. "
    "Loading the wrong project's documents is worse than loading none, so pick one:"
)
AMBIGUITY_STAMP_HINT = (
    "Run the matching line, then the choice sticks for the rest of this session."
)
AMBIGUITY_WORKTREE_HINT = (
    "Run the matching line. This is a worktree, so the choice sticks for every session in it "
    "— `spine session forget` undoes that."
)

BRIEF_INDEX_HEADER = "# Documents available"
BRIEF_INDEX_BODY = (
    "Several projects match this checkout, so no document body was loaded. Below is one line "
    "per document across all of them. Read the ones the task calls for; they are paths, not "
    "summaries to answer from."
)
BRIEF_INDEX_PROJECT_PREFIX = "## "
BRIEF_INDEX_STAMP_HINT = (
    "To load a project's documents in full for the rest of this session: "
    "`spine session set --project <slug>`."
)
BRIEF_INDEX_LINE_TEMPLATE = "- `{path}` — {brief}"
BRIEF_INDEX_UNBRIEFED_TEMPLATE = "- `{path}`"


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


def render_task_context(*, project: Project, docs: tuple[Doc, ...]) -> str:
    """The documents the picker chose for a task, under one project heading."""
    if not docs:
        return NO_PROJECT_MESSAGE
    blocks = [f"## {project.name} (`{project.slug}`) — for this task"]
    blocks.extend(_render_doc(doc=doc) for doc in docs)
    return DOC_SEPARATOR.join(blocks)


def render_ambiguity(
    *, projects: tuple[Project, ...], is_worktree: bool = False
) -> str:
    """The prompt shown when several projects tie, listing the command that picks each."""
    if not projects:
        return NO_PROJECT_MESSAGE
    choices = "\n".join(
        f"- **{project.name}** — `spine session set --project {project.slug}`"
        for project in sorted(projects, key=lambda candidate: candidate.slug)
    )
    hint = AMBIGUITY_WORKTREE_HINT if is_worktree else AMBIGUITY_STAMP_HINT
    return DOC_SEPARATOR.join((AMBIGUITY_HEADER, AMBIGUITY_BODY, choices, hint))


def render_brief_index(*, corpora: tuple[tuple[Project, tuple[Doc, ...]], ...]) -> str:
    """One line per document across every tied project, in place of asking which one it is.

    A stated purpose costs a line where a document body costs hundreds, so the whole corpus
    fits in the budget a single project's always-read set would have spent.
    """
    populated = tuple((project, docs) for project, docs in corpora if docs)
    if not populated:
        return NO_PROJECT_MESSAGE
    sections = [
        DOC_SEPARATOR.join(
            (
                f"{BRIEF_INDEX_PROJECT_PREFIX}{project.name}",
                render_brief_lines(project=project, docs=docs),
            )
        )
        for project, docs in sorted(populated, key=lambda pair: pair[0].slug)
    ]
    return DOC_SEPARATOR.join(
        (BRIEF_INDEX_HEADER, BRIEF_INDEX_BODY, *sections, BRIEF_INDEX_STAMP_HINT)
    )


def render_brief_lines(*, project: Project, docs: tuple[Doc, ...]) -> str:
    """The document lines for one project, addressed by the path an agent would open."""
    return "\n".join(
        render_brief_line(path=str(project.docs_dir / doc.path.name), brief=doc.brief)
        for doc in sorted(docs, key=lambda entry: entry.path.name)
        if not doc.is_entry
    )


def render_brief_line(*, path: str, brief: str | None) -> str:
    """One index line. A document with no stated purpose is still listed, by path alone."""
    if not brief:
        return BRIEF_INDEX_UNBRIEFED_TEMPLATE.format(path=path)
    return BRIEF_INDEX_LINE_TEMPLATE.format(path=path, brief=brief)


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
