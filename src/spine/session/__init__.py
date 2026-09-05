"""Session project attachment."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime

from ..constants import SPINE_SESSION_ID_ENV_VAR
from ..model import SessionStamp
from .stamp import (
    FileSessionStore,
    MalformedStampError,
    stamp_from_environment,
    stamp_path,
)

__all__ = [
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


def resolve_stamp(*, session_id: str, store: FileSessionStore | None = None) -> SessionStamp | None:
    """Return the session's stamp, falling back to the launch environment."""
    active_store = store if store is not None else FileSessionStore()
    written = active_store.read(session_id=session_id)
    if written is not None:
        return written
    return stamp_from_environment()


def _current_session_id(*, override: str | None) -> str | None:
    return override or os.environ.get(SPINE_SESSION_ID_ENV_VAR)


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
    print(f"{session_id} -> {', '.join(slugs)}")
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
    setter.set_defaults(handler=_handle_set)

    shower = nested.add_parser("show", help="Print this session's attachment.")
    shower.add_argument("--session", default=None)
    shower.set_defaults(handler=_handle_show)

    clearer = nested.add_parser("clear", help="Detach this session.")
    clearer.add_argument("--session", default=None)
    clearer.set_defaults(handler=_handle_clear)
