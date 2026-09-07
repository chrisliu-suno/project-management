"""Checks that fire at the moments work actually happens.

A rule attached to a moment fires on its own; a rule that has to be remembered
does not, so these are written to be called from hooks rather than by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from ..constants import GUARD_OUTSIDE_SCOPE_MESSAGE, GUARD_UNDECLARED_MESSAGE
from ..live.model import LiveSession, SessionState


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """Whether a boundary check passed, and what to say when it did not."""

    is_allowed: bool
    message: str = ""

    @property
    def has_message(self) -> bool:
        return bool(self.message)


ALLOWED = GuardVerdict(is_allowed=True)


def _is_within(*, edited: str, declared: str) -> bool:
    edited_path = PurePath(edited)
    declared_path = PurePath(declared)
    if edited_path == declared_path:
        return True
    return declared_path in edited_path.parents


def check_edit(*, session: LiveSession | None, path: str) -> GuardVerdict:
    """Whether an edit sits inside what the session said it would touch."""
    if session is None or not session.intent.strip():
        return GuardVerdict(is_allowed=True, message=GUARD_UNDECLARED_MESSAGE)
    if session.state is SessionState.STOPPED:
        return GuardVerdict(is_allowed=False, message="this session was stopped")
    if session.state is SessionState.PAUSED:
        return GuardVerdict(is_allowed=False, message="this session is paused")
    if not session.declared_paths:
        return ALLOWED
    if any(_is_within(edited=path, declared=declared) for declared in session.declared_paths):
        return ALLOWED
    declared = ", ".join(session.declared_paths)
    return GuardVerdict(
        is_allowed=True,
        message=f"{GUARD_OUTSIDE_SCOPE_MESSAGE}: {path} is outside {declared}",
    )


def check_publish(*, session: LiveSession | None) -> GuardVerdict:
    """Whether work about to leave the session is attached to a project."""
    if session is None or not session.project_slugs:
        return GuardVerdict(
            is_allowed=True,
            message="this work is not attached to any project, so it maps to no requirement",
        )
    if session.state is SessionState.STOPPED:
        return GuardVerdict(is_allowed=False, message="this session was stopped")
    return ALLOWED
