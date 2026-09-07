"""Boundary checks and steering pickup for running sessions."""

from __future__ import annotations

import argparse
import os
import sys

from ..cli import EXIT_OK
from ..constants import SPINE_DISABLED_ENV_VAR, SPINE_SESSION_ID_ENV_VAR
from ..live.model import LiveSession, SessionState, SteeringAction
from .checks import ALLOWED, GuardVerdict, check_edit, check_publish

__all__ = [
    "ALLOWED",
    "GuardVerdict",
    "apply_steering",
    "check_edit",
    "check_publish",
    "register_subcommand",
]

EXIT_BLOCKED = 2
STATE_BY_ACTION = {
    SteeringAction.PAUSE: SessionState.PAUSED,
    SteeringAction.STOP: SessionState.STOPPED,
    SteeringAction.RESUME: SessionState.WORKING,
}


def _session_id(*, override: str | None) -> str | None:
    return override or os.environ.get(SPINE_SESSION_ID_ENV_VAR)


def _live_session(*, session_id: str) -> LiveSession | None:
    from ..live import LiveStore

    for session in LiveStore().live_sessions(include_stale=True):
        if session.session_id == session_id:
            return session
    return None


def apply_steering(*, session_id: str) -> tuple[str, ...]:
    """Drain instructions, apply any state change, and return lines to show."""
    from ..live import LiveStore

    store = LiveStore()
    messages = store.drain_steering(session_id=session_id)
    if not messages:
        return ()
    session = _live_session(session_id=session_id)
    lines: list[str] = []
    for message in messages:
        lines.append(f"[{message.action}] {message.body}".rstrip())
        new_state = STATE_BY_ACTION.get(message.action)
        if new_state is not None and session is not None:
            store.declare(
                session_id=session_id,
                project_slugs=session.project_slugs,
                intent=session.intent,
                declared_paths=session.declared_paths,
                state=new_state,
            )
            session = _live_session(session_id=session_id)
    return tuple(lines)


def _report(*, verdict: GuardVerdict) -> int:
    if verdict.has_message:
        print(f"spine: {verdict.message}", file=sys.stderr)
    return EXIT_OK if verdict.is_allowed else EXIT_BLOCKED


def _handle_edit(args: argparse.Namespace) -> int:
    if os.environ.get(SPINE_DISABLED_ENV_VAR):
        return EXIT_OK
    session_id = _session_id(override=args.session)
    session = _live_session(session_id=session_id) if session_id else None
    return _report(verdict=check_edit(session=session, path=args.path))


def _handle_publish(args: argparse.Namespace) -> int:
    if os.environ.get(SPINE_DISABLED_ENV_VAR):
        return EXIT_OK
    session_id = _session_id(override=args.session)
    session = _live_session(session_id=session_id) if session_id else None
    return _report(verdict=check_publish(session=session))


def _handle_steering(args: argparse.Namespace) -> int:
    session_id = _session_id(override=args.session)
    if session_id is None:
        return EXIT_OK
    for line in apply_steering(session_id=session_id):
        print(line)
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine guard` to the CLI."""
    parser = subparsers.add_parser("guard", help="Checks that fire at work boundaries.")
    verbs = parser.add_subparsers(dest="guard_command", metavar="VERB")

    editor = verbs.add_parser("edit", help="Check an edit against the session's declared scope.")
    editor.add_argument("--path", required=True)
    editor.add_argument("--session", default=None)
    editor.set_defaults(handler=_handle_edit)

    publisher = verbs.add_parser("publish", help="Check work about to leave the session.")
    publisher.add_argument("--session", default=None)
    publisher.set_defaults(handler=_handle_publish)

    steering = verbs.add_parser("steering", help="Pick up and apply queued instructions.")
    steering.add_argument("--session", default=None)
    steering.set_defaults(handler=_handle_steering)
