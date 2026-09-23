"""Session project attachment."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime

from pathlib import Path

from ..constants import SPINE_SESSION_ID_ENV_VAR
from ..model import SessionStamp
from .checkout import FileCheckoutStore, linked_worktree_root, remember_choice
from .stamp import (
    FileSessionStore,
    MalformedStampError,
    stamp_from_environment,
    stamp_path,
)

__all__ = [
    "FileCheckoutStore",
    "FileSessionStore",
    "MalformedStampError",
    "register_subcommand",
    "resolve_stamp",
    "stamp_from_environment",
    "stamp_path",
]

EXIT_OK = 0
EXIT_NO_STAMP = 1
EXIT_MALFORMED = 3
PROJECT_LIST_SEPARATOR = ","
STAMPED_INTENT = "stamped by hand"


def resolve_stamp(*, session_id: str, store: FileSessionStore | None = None) -> SessionStamp | None:
    """Return the session's stamp, falling back to the launch environment."""
    active_store = store if store is not None else FileSessionStore()
    written = active_store.read(session_id=session_id)
    if written is not None:
        return written
    return stamp_from_environment()


def _current_session_id(*, override: str | None) -> str | None:
    return override or os.environ.get(SPINE_SESSION_ID_ENV_VAR)


def _declare_to_dashboard(*, session_id: str, slugs: tuple[str, ...], intent: str | None) -> None:
    """Register the stamped session as live. Never raises: a stamp must survive a dead store."""
    try:
        from ..live import LiveStore

        LiveStore().declare(
            session_id=session_id,
            project_slugs=slugs,
            intent=intent or STAMPED_INTENT,
            declared_paths=(),
        )
    except Exception:
        pass


def _handle_set(args: argparse.Namespace) -> int:
    session_id = _current_session_id(override=args.session)
    if session_id is None:
        print(f"no session id: pass --session or set {SPINE_SESSION_ID_ENV_VAR}")
        return EXIT_NO_STAMP
    slugs = tuple(slug.strip() for slug in args.project.split(PROJECT_LIST_SEPARATOR) if slug.strip())
    stamp = SessionStamp(
        session_id=session_id,
        project_slugs=slugs,
        started_at=datetime.now(tz=UTC),
        intent=args.intent,
    )
    FileSessionStore().write(stamp=stamp)
    _declare_to_dashboard(session_id=session_id, slugs=slugs, intent=args.intent)
    print(f"{session_id} -> {', '.join(slugs)}")
    if not args.session_only:
        remembered = remember_choice(cwd=Path.cwd(), project_slugs=slugs)
        if remembered is not None:
            print(f"remembered for {remembered}; `spine session forget` undoes it")
    return EXIT_OK


def _handle_forget(args: argparse.Namespace) -> int:
    """Drop this worktree's remembered choice so the next session is asked again."""
    root = linked_worktree_root(cwd=Path.cwd())
    if root is None:
        print("not a linked worktree: nothing is remembered for a primary checkout")
        return EXIT_NO_STAMP
    if not FileCheckoutStore().clear(root=root):
        print(f"nothing remembered for {root}")
        return EXIT_NO_STAMP
    print(f"forgot {root}")
    return EXIT_OK


def _handle_show(args: argparse.Namespace) -> int:
    session_id = _current_session_id(override=args.session)
    if session_id is None:
        print(f"no session id: pass --session or set {SPINE_SESSION_ID_ENV_VAR}")
        return EXIT_NO_STAMP
    try:
        stamp = resolve_stamp(session_id=session_id)
    except MalformedStampError as cause:
        print(str(cause))
        return EXIT_MALFORMED
    if stamp is None:
        return EXIT_NO_STAMP
    print(f"{stamp.session_id}\t{','.join(stamp.project_slugs)}\t{stamp.source}")
    return EXIT_OK


def _handle_clear(args: argparse.Namespace) -> int:
    session_id = _current_session_id(override=args.session)
    if session_id is None:
        return EXIT_NO_STAMP
    return EXIT_OK if FileSessionStore().clear(session_id=session_id) else EXIT_NO_STAMP


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine session` to the CLI."""
    parser = subparsers.add_parser("session", help="Read and write a session's project stamp.")
    nested = parser.add_subparsers(dest="session_command", metavar="ACTION")

    setter = nested.add_parser("set", help="Attach this session to one or more projects.")
    setter.add_argument("--project", required=True, help="Project slug, comma separated for several.")
    setter.add_argument("--session", default=None, help="Session id; defaults to the environment.")
    setter.add_argument("--intent", default=None, help="What this session is doing.")
    setter.add_argument(
        "--session-only",
        action="store_true",
        help="Do not remember this choice for the worktree.",
    )
    setter.set_defaults(handler=_handle_set)

    shower = nested.add_parser("show", help="Print this session's attachment.")
    shower.add_argument("--session", default=None)
    shower.set_defaults(handler=_handle_show)

    clearer = nested.add_parser("clear", help="Detach this session.")
    clearer.add_argument("--session", default=None)
    clearer.set_defaults(handler=_handle_clear)

    forgetter = nested.add_parser(
        "forget", help="Drop this worktree's remembered project choice."
    )
    forgetter.set_defaults(handler=_handle_forget)
