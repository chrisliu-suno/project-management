"""Splits append-only logs into individually addressable entries.

Supersession happens between entries inside one log file, so entries need node
identity of their own for the citation graph to express it.
"""

from __future__ import annotations

from dataclasses import replace

from ..constants import (
    ENTRY_ANCHOR_SEPARATOR,
    ENTRY_HEADING_PREFIX,
    ENTRY_SLUG_ALLOWED_EXTRA,
    ENTRY_SLUG_SEPARATOR,
    SEGMENTED_DOC_KINDS,
)
from ..model import Doc


def slugify_heading(*, heading: str) -> str:
    """A stable anchor for an entry heading."""
    kept = [
        character.lower() if character.isalnum() else ENTRY_SLUG_SEPARATOR
        for character in heading.strip()
    ]
    collapsed = "".join(kept)
    while ENTRY_SLUG_SEPARATOR * 2 in collapsed:
        collapsed = collapsed.replace(ENTRY_SLUG_SEPARATOR * 2, ENTRY_SLUG_SEPARATOR)
    return collapsed.strip(ENTRY_SLUG_ALLOWED_EXTRA)


def entry_doc_id(*, parent_doc_id: str, heading: str) -> str:
    return f"{parent_doc_id}{ENTRY_ANCHOR_SEPARATOR}{slugify_heading(heading=heading)}"


def _heading_spans(*, lines: list[str]) -> list[tuple[str, int, int]]:
    """Each second-level heading with the line range of its section body."""
    starts = [
        (line.removeprefix(ENTRY_HEADING_PREFIX).strip(), index)
        for index, line in enumerate(lines)
        if line.startswith(ENTRY_HEADING_PREFIX)
    ]
    spans: list[tuple[str, int, int]] = []
    for position, (heading, start) in enumerate(starts):
        is_last = position == len(starts) - 1
        end = len(lines) if is_last else starts[position + 1][1]
        spans.append((heading, start, end))
    return spans


def split_into_entries(*, doc: Doc) -> tuple[Doc, ...]:
    """Entry docs for a log, or an empty tuple when the doc is not segmented."""
    if doc.kind not in SEGMENTED_DOC_KINDS or doc.is_entry:
        return ()
    lines = doc.body.splitlines()
    entries = [
        replace(
            doc,
            doc_id=entry_doc_id(parent_doc_id=doc.doc_id, heading=heading),
            title=heading,
            body="\n".join(lines[start:end]).strip(),
            parent_doc_id=doc.doc_id,
        )
        for heading, start, end in _heading_spans(lines=lines)
    ]
    return tuple(entry for entry in entries if entry.body)


def with_entries(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    """The corpus plus an entry node for every section of every log."""
    expanded: list[Doc] = []
    for doc in docs:
        expanded.append(doc)
        expanded.extend(split_into_entries(doc=doc))
    return tuple(expanded)
