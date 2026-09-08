"""Seeing and steering running sessions."""

from __future__ import annotations

import argparse
import os
import sys

from ..cli import EXIT_OK
from ..constants import SPINE_SESSION_ID_ENV_VAR
from .model import Broadcast, LiveSession, SessionState, SteeringAction, SteeringMessage
from .store import LiveStore, now_iso, sessions_db_path

__all__ = [
    "Broadcast",
    "LiveSession",
    "LiveStore",
    "SessionState",
    "SteeringAction",
    "SteeringMessage",
    "now_iso",
    "register_subcommand",
    "sessions_db_path",
]

EXIT_NO_SESSION = 1
EXIT_LEASE_HELD = 2
FIELD_SEPARATOR = "\t"
STOPPING_ACTIONS = {SteeringAction.PAUSE, SteeringAction.STOP}


def _session_id(*, override: str | None) -> str | None:
    return override or os.environ.get(SPINE_SESSION_ID_ENV_VAR)


def _require_session(*, override: str | None) -> str | None:
    session_id = _session_id(override=override)
    if session_id is None:
        print(f"no session id: pass --session or set {SPINE_SESSION_ID_ENV_VAR}", file=sys.stderr)
    return session_id


def _handle_declare(args: argparse.Namespace) -> int:
    session_id = _require_session(override=args.session)
    if session_id is None:
        return EXIT_NO_SESSION
    slugs = tuple(slug for slug in (args.project or "").split(",") if slug)
    declared = LiveStore().declare(
        session_id=session_id,
        project_slugs=slugs,
        intent=args.intent,
        declared_paths=tuple(args.path or ()),
    )
    print(f"{declared.session_id}\t{declared.state}\t{declared.intent}")
    return EXIT_OK


def _handle_list(args: argparse.Namespace) -> int:
    for session in LiveStore().live_sessions(include_stale=args.all):
        print(
            FIELD_SEPARATOR.join(
                (
                    session.session_id,
                    str(session.state),
                    ",".join(session.project_slugs),
                    session.intent,
                )
            )
        )
    return EXIT_OK


def _handle_steer(args: argparse.Namespace) -> int:
    message = LiveStore().steer(
        session_id=args.session, action=SteeringAction(args.action), body=args.body or ""
    )
    print(f"queued {message.action} for {message.session_id}")
    return EXIT_OK


def _handle_check(args: argparse.Namespace) -> int:
    session_id = _require_session(override=args.session)
    if session_id is None:
        return EXIT_NO_SESSION
    messages = LiveStore().drain_steering(session_id=session_id)
    for message in messages:
        line = f"[{message.action}] {message.body}".rstrip()
        print(line)
    return EXIT_OK


def _handle_broadcast(args: argparse.Namespace) -> int:
    session_id = _session_id(override=args.session) or "unknown"
    published = LiveStore().broadcast(
        project_slug=args.project,
        headline=args.headline,
        body=args.body or "",
        origin_session_id=session_id,
    )
    print(f"broadcast to {published.project_slug}: {published.headline}")
    return EXIT_OK


def _handle_news(args: argparse.Namespace) -> int:
    for item in LiveStore().broadcasts_for(project_slug=args.project):
        print(FIELD_SEPARATOR.join((item.created_at, item.origin_session_id, item.headline)))
    return EXIT_OK


def _handle_lease(args: argparse.Namespace) -> int:
    session_id = _require_session(override=args.session)
    if session_id is None:
        return EXIT_NO_SESSION
    store = LiveStore()
    if args.release:
        released = store.release_lease(subject=args.subject, session_id=session_id)
        print("released" if released else "not held by this session")
        return EXIT_OK
    if store.acquire_lease(subject=args.subject, session_id=session_id):
        print(f"holding {args.subject}")
        return EXIT_OK
    print(f"{args.subject} is held by {store.lease_holder(subject=args.subject)}", file=sys.stderr)
    return EXIT_LEASE_HELD


def _add_declare(verbs: argparse._SubParsersAction) -> None:
    parser = verbs.add_parser("declare", help="Say what this session is doing.")
    parser.add_argument("--intent", required=True)
    parser.add_argument("--project", default="", help="Comma-separated project slugs.")
    parser.add_argument(
        "--path", action="append", help="Repeatable path this session expects to touch."
    )
    parser.add_argument("--session", default=None)
    parser.set_defaults(handler=_handle_declare)


def _add_steering(verbs: argparse._SubParsersAction) -> None:
    steer = verbs.add_parser("steer", help="Send an instruction to a session.")
    steer.add_argument("--session", required=True)
    steer.add_argument("--action", required=True, choices=[str(a) for a in SteeringAction])
    steer.add_argument("--body", default="")
    steer.set_defaults(handler=_handle_steer)

    check = verbs.add_parser("check", help="Pick up instructions for this session.")
    check.add_argument("--session", default=None)
    check.set_defaults(handler=_handle_check)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine live` to the CLI."""
    parser = subparsers.add_parser("live", help="See and steer running sessions.")
    verbs = parser.add_subparsers(dest="live_command", metavar="VERB")

    _add_declare(verbs=verbs)
    _add_steering(verbs=verbs)

    lister = verbs.add_parser("list", help="One line per running session.")
    lister.add_argument("--all", action="store_true", help="Include stale sessions.")
    lister.set_defaults(handler=_handle_list)

    caster = verbs.add_parser("broadcast", help="Tell every session on a project something.")
    caster.add_argument("--project", required=True)
    caster.add_argument("--headline", required=True)
    caster.add_argument("--body", default="")
    caster.add_argument("--session", default=None)
    caster.set_defaults(handler=_handle_broadcast)

    news = verbs.add_parser("news", help="Recent broadcasts on a project.")
    news.add_argument("--project", required=True)
    news.set_defaults(handler=_handle_news)

    lease = verbs.add_parser("lease", help="Take or release a lease on a shared conclusion.")
    lease.add_argument("--subject", required=True)
    lease.add_argument("--session", default=None)
    lease.add_argument("--release", action="store_true")
    lease.set_defaults(handler=_handle_lease)
