"""Normalising the status words that appear in plan prose."""

from __future__ import annotations

import re

from .model import ItemStatus

EMPHASIS_PATTERN = re.compile(r"[*_`]+")
PARENTHETICAL_PATTERN = re.compile(r"\([^)]*\)")

STATUS_PHRASES: tuple[tuple[str, ItemStatus], ...] = (
    ("not built", ItemStatus.NOT_STARTED),
    ("not started", ItemStatus.NOT_STARTED),
    ("not done", ItemStatus.NOT_STARTED),
    ("todo", ItemStatus.NOT_STARTED),
    ("to do", ItemStatus.NOT_STARTED),
    ("partial", ItemStatus.PARTIAL),
    ("in progress", ItemStatus.IN_PROGRESS),
    ("in flight", ItemStatus.IN_PROGRESS),
    ("underway", ItemStatus.IN_PROGRESS),
    ("wip", ItemStatus.IN_PROGRESS),
    ("blocked", ItemStatus.BLOCKED),
    ("blocking", ItemStatus.BLOCKED),
    ("shipped", ItemStatus.DONE),
    ("merged", ItemStatus.DONE),
    ("complete", ItemStatus.DONE),
    ("done", ItemStatus.DONE),
    ("built", ItemStatus.DONE),
    ("landed", ItemStatus.DONE),
)


def normalise(*, text: str) -> str:
    """Lowercased, stripped of emphasis marks and parentheticals."""
    without_emphasis = EMPHASIS_PATTERN.sub("", text)
    return PARENTHETICAL_PATTERN.sub(" ", without_emphasis).strip().lower()


def status_from(*, text: str) -> ItemStatus:
    """The status a cell or marker states.

    Negations are listed before their positive forms because "not built" contains
    "built" and the first match wins.
    """
    cleaned = normalise(text=text)
    if not cleaned:
        return ItemStatus.UNKNOWN
    for phrase, status in STATUS_PHRASES:
        if phrase in cleaned:
            return status
    return ItemStatus.UNKNOWN
