"""Milestone headings, in the shapes the corpora already use."""

from __future__ import annotations

import re

from ..constants import PLAN_OPEN_QUESTION_HEADINGS

HEADING_PATTERN = re.compile(r"^(#{2,4})\s+(.*\S)\s*$")
TARGET_PATTERN = re.compile(r"\(\s*target\s+([^)]+?)\s*\)", re.IGNORECASE)
TITLE_SPLIT_PATTERN = re.compile(r"\s+[—–-]\s+")
EMPHASIS_PATTERN = re.compile(r"[*_`]+")

MILESTONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^phase\s+\d+\b", re.IGNORECASE),
    re.compile(r"^(?:[A-Z]{1,4}-)?M\d+\b"),
    re.compile(r"^(?:milestone|stage|ring)\s+\S+", re.IGNORECASE),
    re.compile(r"^(?:blocking|should-fix|must-fix|nice-to-have)\b", re.IGNORECASE),
)


def heading_at(*, line: str) -> tuple[int, str] | None:
    """Depth and text of a markdown heading, or None when the line is not one."""
    matched = HEADING_PATTERN.match(line)
    if matched is None:
        return None
    return len(matched.group(1)), matched.group(2)


def is_milestone(*, heading: str) -> bool:
    """Whether a heading names a stage of work rather than a prose section."""
    stripped = EMPHASIS_PATTERN.sub("", heading).strip()
    return any(pattern.match(stripped) for pattern in MILESTONE_PATTERNS)


def is_open_questions(*, heading: str) -> bool:
    lowered = heading.lower()
    return any(marker in lowered for marker in PLAN_OPEN_QUESTION_HEADINGS)


def target_in(*, heading: str) -> str | None:
    """The date a heading names as its target, when it names one."""
    matched = TARGET_PATTERN.search(heading)
    return matched.group(1).strip() if matched is not None else None


def milestone_title(*, heading: str) -> str:
    """The heading with emphasis and any target parenthetical removed."""
    without_target = TARGET_PATTERN.sub("", heading)
    cleaned = EMPHASIS_PATTERN.sub("", without_target).strip()
    return TITLE_SPLIT_PATTERN.sub(" — ", cleaned).strip(" —-")
