"""Work items read out of a markdown status table."""

from __future__ import annotations

from ..constants import PLAN_EVIDENCE_COLUMN_NAMES, PLAN_STATUS_COLUMN_NAMES
from .status import normalise

ROW_PREFIX = "|"
SEPARATOR_CHARS = set("|-: ")
COLUMN_SEPARATOR = "|"


def is_table_row(*, line: str) -> bool:
    return line.strip().startswith(ROW_PREFIX)


def is_separator_row(*, line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= SEPARATOR_CHARS and "-" in stripped


def cells_in(*, line: str) -> tuple[str, ...]:
    """Cell texts of one row, without the leading and trailing pipes."""
    trimmed = line.strip().strip(COLUMN_SEPARATOR)
    return tuple(cell.strip() for cell in trimmed.split(COLUMN_SEPARATOR))


def _index_of(*, headers: tuple[str, ...], names: frozenset[str]) -> int | None:
    for position, header in enumerate(headers):
        if normalise(text=header) in names:
            return position
    return None


def status_column(*, headers: tuple[str, ...]) -> int | None:
    """Which column states the status, when the table has one."""
    return _index_of(headers=headers, names=PLAN_STATUS_COLUMN_NAMES)


def evidence_column(*, headers: tuple[str, ...]) -> int | None:
    return _index_of(headers=headers, names=PLAN_EVIDENCE_COLUMN_NAMES)


def title_column(*, headers: tuple[str, ...], status_at: int) -> int:
    """The first column that is neither an index nor the status.

    Tables here open with a narrow `#` column, so the widest earlier header is a
    better title than "1".
    """
    candidates = [
        position
        for position in range(len(headers))
        if position != status_at and len(normalise(text=headers[position])) > 1
    ]
    return candidates[0] if candidates else 0
