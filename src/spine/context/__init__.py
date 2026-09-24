"""Session-start project context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK
from ..constants import (
    AMBIGUOUS_PICK_CONFIDENCE,
    EXACT_MATCH_CONFIDENCE,
    INJECTION_LINE_BUDGET,
    PICK_REASON_AMBIGUOUS_INDEX,
    PICK_REASON_ATTACHED,
    SESSION_CONTEXT_TOTAL_BUDGET,
    SPINE_DISABLED_ENV_VAR,
    SPINE_SESSION_ID_ENV_VAR,
)
from ..model import Project, Selection
from .attach import (
    AMBIGUOUS_ATTACHMENT_SOURCE,
    Attachment,
    attach,
    current_branch,
    current_repo,
)
from .render import (
    DOC_SEPARATOR,
    always_read,
    render_ambiguity,
    render_brief_index,
    render_context,
    render_project,
    render_task_context,
)

__all__ = [
    "Attachment",
    "always_read",
    "attach",
    "context_for",
    "current_branch",
    "current_repo",
    "get_candidate_projects",
    "record_attachment",
    "register_subcommand",
    "render_ambiguity",
    "render_brief_index",
    "render_context",
    "render_project",
    "render_task_context",
    "task_context_for",
]


def context_for(*, cwd: Path, session_id: str | None, budget: int) -> str:
    """The injection payload for a session, the disambiguation prompt when several
    projects tie, or empty when none applies."""
    from ..index import load_corpus

    attachment = attach(cwd=cwd, session_id=session_id)
    attached = [
        project for project in attachment.projects if project.docs_dir.is_dir()
    ]
    if not attached:
        candidates = tuple(
            project for project in attachment.ambiguous if project.docs_dir.is_dir()
        )
        if not candidates:
            return render_ambiguity(projects=attachment.ambiguous)
        record_attachment(
            session_id=session_id,
            projects=candidates,
            confidence=AMBIGUOUS_PICK_CONFIDENCE,
            reason=PICK_REASON_AMBIGUOUS_INDEX,
        )
        return render_brief_index(
            corpora=tuple(
                (project, load_corpus(docs_dir=project.docs_dir, project_slug=project.slug))
                for project in candidates
            )
        )
    record_attachment(
        session_id=session_id,
        projects=tuple(attached),
        confidence=EXACT_MATCH_CONFIDENCE,
        reason=PICK_REASON_ATTACHED,
    )
    share = max(budget // len(attached), 1)
    blocks = [
        render_project(
            project=project,
            docs=load_corpus(docs_dir=project.docs_dir, project_slug=project.slug),
            budget=share,
        )
        for project in attached
    ]
    return render_context(rendered_projects=tuple(blocks), budget=budget)


def record_attachment(
    *,
    session_id: str | None,
    projects: tuple[Project, ...],
    confidence: float,
    reason: str,
) -> None:
    """Record which projects a session belongs to, one row each and no chosen documents.

    A resolved session records at full confidence; a tied one records every candidate at zero,
    which says the cluster is known and the project is not.
    """
    from ..picker.record import SqlitePickRecorder

    if not session_id:
        return
    recorder = SqlitePickRecorder()
    empty = Selection(chosen=(), dropped=(), total_lines=0, reason=reason)
    for project in projects:
        recorder.record(
            session_id=session_id,
            project_slug=project.slug,
            selection=empty,
            confidence=confidence,
        )


TASK_CONTEXT_HEADER = "# For this task"


def task_context_for(*, cwd: Path, session_id: str | None, task: str, budget: int) -> str:
    """Task-relevant documents for a session, chosen once per session and recorded.

    Returns empty when nothing attaches at all, when the session already had a pick,
    or when nothing scored above the floor.
    """
    from ..picker.record import has_pick_for_session

    if not session_id or not task.strip():
        return ""
    if has_pick_for_session(session_id=session_id):
        return ""
    attachment = attach(cwd=cwd, session_id=session_id, opening_prompt=task)
    attached = get_candidate_projects(attachment=attachment)
    if not attached:
        return ""
    is_resolved = bool(attachment.projects)
    blocks = _pick_across_projects(
        projects=tuple(attached),
        session_id=session_id,
        task=task,
        budget=budget,
        confidence=EXACT_MATCH_CONFIDENCE if is_resolved else AMBIGUOUS_PICK_CONFIDENCE,
    )
    if not blocks:
        return ""
    return DOC_SEPARATOR.join((TASK_CONTEXT_HEADER, *blocks))


def get_candidate_projects(*, attachment: Attachment) -> list[Project]:
    """The projects worth picking documents from: the resolved ones, else the tied candidates.

    A checkout that matches several projects equally is the normal case for a monorepo, and
    picking nothing there means the repo with the most work gets the least context.
    """
    resolved = [project for project in attachment.projects if project.docs_dir.is_dir()]
    if resolved:
        return resolved
    return [project for project in attachment.ambiguous if project.docs_dir.is_dir()]


def _pick_across_projects(
    *,
    projects: tuple[Project, ...],
    session_id: str,
    task: str,
    budget: int,
    confidence: float,
) -> list[str]:
    """Rendered blocks for every project that contributed, each selection recorded.

    The confidence is the attachment's, not the selection's: documents chosen for a session
    tied across projects are still the right documents to offer, but they do not place its cost.
    """
    from ..index import open_graph_store
    from ..picker import BudgetedPicker, SqlitePickRecorder

    picker = BudgetedPicker(graph_store=open_graph_store(), should_include_rarely=False)
    selections = picker.pick_across_projects(
        projects=projects, task_context=task, line_budget=budget
    )
    recorder = SqlitePickRecorder()
    blocks: list[str] = []
    for project in projects:
        selection = selections[project.slug]
        recorder.record(
            session_id=session_id,
            project_slug=project.slug,
            selection=selection,
            confidence=confidence,
        )
        if selection.chosen:
            blocks.append(render_task_context(project=project, docs=selection.chosen))
    return blocks


def _session_id_from(*, override: str | None) -> str | None:
    import os

    return override or os.environ.get(SPINE_SESSION_ID_ENV_VAR)


def _handle_context(args: argparse.Namespace) -> int:
    import os

    if os.environ.get(SPINE_DISABLED_ENV_VAR):
        return EXIT_OK
    try:
        payload = context_for(
            cwd=Path(args.cwd).expanduser() if args.cwd else Path.cwd(),
            session_id=_session_id_from(override=args.session),
            budget=args.budget,
        )
    except Exception as cause:
        print(f"spine: could not build project context: {cause}", file=sys.stderr)
        return EXIT_OK
    if payload:
        print(payload)
    return EXIT_OK


def _handle_which(args: argparse.Namespace) -> int:
    attachment = attach(
        cwd=Path(args.cwd).expanduser() if args.cwd else Path.cwd(),
        session_id=_session_id_from(override=args.session),
    )
    if not attachment.projects:
        if attachment.ambiguous:
            print("ambiguous — pick one:", file=sys.stderr)
            for project in sorted(attachment.ambiguous, key=lambda found: found.slug):
                print(f"{project.slug}\t{AMBIGUOUS_ATTACHMENT_SOURCE}")
                print(f"  spine session set --project {project.slug}", file=sys.stderr)
            return EXIT_OK
        print("no project", file=sys.stderr)
        return EXIT_OK
    for project in attachment.projects:
        print(f"{project.slug}\t{attachment.source}")
    for line in attachment.evidence:
        print(f"  {line}", file=sys.stderr)
    return EXIT_OK


def _handle_task(args: argparse.Namespace) -> int:
    import os

    if os.environ.get(SPINE_DISABLED_ENV_VAR):
        return EXIT_OK
    try:
        payload = task_context_for(
            cwd=Path(args.cwd).expanduser() if args.cwd else Path.cwd(),
            session_id=_session_id_from(override=args.session),
            task=args.task,
            budget=args.budget,
        )
    except Exception as cause:
        print(f"spine: could not build task context: {cause}", file=sys.stderr)
        return EXIT_OK
    if payload:
        print(payload)
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine context` to the CLI."""
    parser = subparsers.add_parser("context", help="Project context for a starting session.")
    parser.add_argument("--cwd", default=None, help="Directory to resolve from.")
    parser.add_argument("--session", default=None, help="Session id; defaults to the environment.")
    parser.add_argument(
        "--budget", type=int, default=SESSION_CONTEXT_TOTAL_BUDGET, help="Line budget."
    )
    parser.set_defaults(handler=_handle_context)

    verbs = parser.add_subparsers(dest="context_command", metavar="VERB")
    which = verbs.add_parser("which", help="Print which projects this session attaches to.")
    which.add_argument("--cwd", default=None)
    which.add_argument("--session", default=None)
    which.set_defaults(handler=_handle_which)

    task = verbs.add_parser("task", help="Documents for what this session is about to do.")
    task.add_argument("--task", required=True, help="What the session is about to work on.")
    task.add_argument("--cwd", default=None)
    task.add_argument("--session", default=None)
    task.add_argument("--budget", type=int, default=INJECTION_LINE_BUDGET, help="Line budget.")
    task.set_defaults(handler=_handle_task)
