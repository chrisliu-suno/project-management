"""Session-start project context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK
from ..constants import (
    SESSION_CONTEXT_TOTAL_BUDGET,
    SPINE_DISABLED_ENV_VAR,
    SPINE_SESSION_ID_ENV_VAR,
)
from .attach import Attachment, attach, current_branch, current_repo
from .render import always_read, render_context, render_project

__all__ = [
    "Attachment",
    "always_read",
    "attach",
    "context_for",
    "current_branch",
    "current_repo",
    "register_subcommand",
    "render_context",
    "render_project",
]


def context_for(*, cwd: Path, session_id: str | None, budget: int) -> str:
    """The injection payload for a session, or empty when no project applies."""
    from ..index import load_corpus

    attachment = attach(cwd=cwd, session_id=session_id)
    attached = [
        project for project in attachment.projects if project.docs_dir.is_dir()
    ]
    if not attached:
        return ""
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
        print("no project", file=sys.stderr)
        return EXIT_OK
    for project in attachment.projects:
        print(f"{project.slug}\t{attachment.source}")
    for line in attachment.evidence:
        print(f"  {line}", file=sys.stderr)
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
