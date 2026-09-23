"""Session-start project context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK
from ..constants import (
    EXACT_MATCH_CONFIDENCE,
    INJECTION_LINE_BUDGET,
    SESSION_CONTEXT_TOTAL_BUDGET,
    SPINE_DISABLED_ENV_VAR,
    SPINE_SESSION_ID_ENV_VAR,
)
from ..model import Project
from .attach import Attachment, attach, current_branch, current_repo
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
        return render_brief_index(
            corpora=tuple(
                (project, load_corpus(docs_dir=project.docs_dir, project_slug=project.slug))
                for project in candidates
            )
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


TASK_CONTEXT_HEADER = "# For this task"


def task_context_for(*, cwd: Path, session_id: str | None, task: str, budget: int) -> str:
    """Task-relevant documents for a session, chosen once per session and recorded.

    Returns empty when no project is attached, when the session already had a pick,
    or when nothing scored above the floor.
    """
    from ..picker.record import has_pick_for_session

    if not session_id or not task.strip():
        return ""
    if has_pick_for_session(session_id=session_id):
        return ""
    attachment = attach(cwd=cwd, session_id=session_id)
    attached = [project for project in attachment.projects if project.docs_dir.is_dir()]
    if not attached:
        return ""
    blocks = [
        rendered
        for project in attached
        if (
            rendered := _pick_for_project(
                project=project,
                session_id=session_id,
                task=task,
                budget=max(budget // len(attached), 1),
            )
        )
    ]
    if not blocks:
        return ""
    return DOC_SEPARATOR.join((TASK_CONTEXT_HEADER, *blocks))


def _pick_for_project(*, project: Project, session_id: str, task: str, budget: int) -> str:
    """One project's task selection, rendered and recorded. Empty when nothing was chosen."""
    from ..index import open_graph_store
    from ..picker import BudgetedPicker, SqlitePickRecorder

    picker = BudgetedPicker(graph_store=open_graph_store(), should_include_rarely=False)
    selection = picker.pick(project=project, task_context=task, line_budget=budget)
    SqlitePickRecorder().record(
        session_id=session_id,
        project_slug=project.slug,
        selection=selection,
        confidence=EXACT_MATCH_CONFIDENCE,
    )
    return render_task_context(project=project, docs=selection.chosen)


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
