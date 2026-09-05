"""Size-cap checks against the per-read-when-group line limits. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..constants import MAX_LINES_PER_READ_WHEN
from ..model import Doc, ReadWhen


@dataclass(frozen=True, slots=True)
class CapBreach:
    """One document over its read-when group's line cap, and by how much."""

    doc: Doc
    cap_lines: int
    line_count: int

    @property
    def excess_lines(self) -> int:
        return self.line_count - self.cap_lines


def cap_for(*, read_when: ReadWhen) -> int:
    return MAX_LINES_PER_READ_WHEN[read_when]


def find_cap_breaches(*, docs: Iterable[Doc]) -> tuple[CapBreach, ...]:
    """Documents exceeding their group's cap, worst overrun first."""
    found = (_breach_for_doc(doc=doc) for doc in docs)
    breaches = [breach for breach in found if breach is not None]
    return tuple(sorted(breaches, key=lambda breach: (-breach.excess_lines, breach.doc.doc_id)))


def _breach_for_doc(*, doc: Doc) -> CapBreach | None:
    cap_lines = cap_for(read_when=doc.read_when)
    if doc.line_count <= cap_lines:
        return None
    return CapBreach(doc=doc, cap_lines=cap_lines, line_count=doc.line_count)
