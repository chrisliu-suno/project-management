"""Harvests the one-line purpose each start-here document already states per doc.

A brief document's two-column tables name a sibling document on the left and say what it is
for on the right. That sentence is the cheapest useful description of a document that exists,
and it is written by hand, so it is preferred over anything derived from the body.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..constants import (
    BODY_SKIPPED_LINE_PREFIXES,
    BRIEF_REFERENCE_SUFFIXES,
    BRIEF_TABLE_MIN_CELLS,
    BRIEF_TEXT_MAX_CHARACTERS,
    MARKDOWN_TABLE_CELL_SEPARATOR,
    MARKDOWN_TABLE_RULE_CHARACTERS,
    METADATA_BOLD_FIELD_PREFIX,
    METADATA_BOLD_FIELD_SUFFIX,
    METADATA_FIELD_SUFFIX,
    SENTENCE_END_CHARACTERS,
)


@dataclass(frozen=True, slots=True)
class BriefRow:
    """One harvested table row: which document, and the purpose stated for it."""

    stem: str
    brief: str


def get_briefs_from_body(*, body: str) -> dict[str, str]:
    """Document stem to its stated purpose, for every table row naming a document.

    The first row wins when a document is listed twice, because a start-here doc introduces a
    document before it lists it again under a narrower heading.
    """
    briefs: dict[str, str] = {}
    for row in get_brief_rows_from_body(body=body):
        briefs.setdefault(row.stem, row.brief)
    return briefs


def get_brief_rows_from_body(*, body: str) -> tuple[BriefRow, ...]:
    """Every table row whose first cell names a document file."""
    rows: list[BriefRow] = []
    for line in body.splitlines():
        cells = get_cells_from_table_line(line=line)
        if cells is None:
            continue
        stem = get_document_stem_from_cell(cell=cells[0])
        brief = truncate_brief(text=cells[1])
        if stem and brief:
            rows.append(BriefRow(stem=stem, brief=brief))
    return tuple(rows)


def get_cells_from_table_line(*, line: str) -> tuple[str, ...] | None:
    """Cells of a markdown table row, or None when the line is not one."""
    stripped = line.strip()
    if not stripped.startswith(MARKDOWN_TABLE_CELL_SEPARATOR):
        return None
    cells = tuple(cell.strip() for cell in stripped.strip(MARKDOWN_TABLE_CELL_SEPARATOR).split(
        MARKDOWN_TABLE_CELL_SEPARATOR
    ))
    if len(cells) < BRIEF_TABLE_MIN_CELLS or check_is_rule_row(cells=cells):
        return None
    return cells


def check_is_rule_row(*, cells: tuple[str, ...]) -> bool:
    """Whether the row is the `|---|---|` rule under a table header."""
    return all(
        cell and set(cell) <= MARKDOWN_TABLE_RULE_CHARACTERS for cell in cells
    )


def get_document_stem_from_cell(*, cell: str) -> str | None:
    """The document stem a cell refers to, or None when it names no document.

    A cell often wraps the name in backticks and qualifies it with a directory or a trailing
    parenthetical, so the reference is taken as the first token that ends in a known suffix.
    """
    for token in cell.replace("`", " ").split():
        candidate = token.strip("()[],;")
        if candidate.endswith(BRIEF_REFERENCE_SUFFIXES):
            return Path(candidate).stem
    return None


def truncate_brief(*, text: str) -> str:
    """Collapse a cell to a single line, cut to the length a brief index can afford."""
    collapsed = " ".join(text.replace("`", "").split())
    return collapsed[:BRIEF_TEXT_MAX_CHARACTERS]


def get_fallback_brief_from_body(*, body: str) -> str | None:
    """The document's own opening sentence, for a document no brief table names.

    Weaker than a stated purpose and used only in its absence, so header metadata lines and
    bare source links are skipped rather than presented as a description.
    """
    paragraph = get_first_prose_paragraph(body=body)
    if not paragraph:
        return None
    return truncate_brief(text=get_first_sentence(text=paragraph))


def get_first_prose_paragraph(*, body: str) -> str:
    """The first run of consecutive prose lines, so a wrapped sentence is not cut mid-clause."""
    collected: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        is_prose = bool(stripped) and not stripped.startswith(BODY_SKIPPED_LINE_PREFIXES)
        if is_prose and not check_is_metadata_line(line=stripped):
            collected.append(stripped)
        elif collected:
            break
    return " ".join(collected)


def get_first_sentence(*, text: str) -> str:
    """Text up to the first sentence end, or all of it when there is none."""
    for index, character in enumerate(text):
        if character in SENTENCE_END_CHARACTERS and _check_ends_sentence(text=text, index=index):
            return text[: index + 1]
    return text


def _check_ends_sentence(*, text: str, index: int) -> bool:
    """A terminator followed by a space and a capital, not a version or an abbreviation."""
    tail = text[index + 1 :]
    return not tail or (tail[0].isspace() and tail.lstrip()[:1].isupper())


def check_is_metadata_line(*, line: str) -> bool:
    """Whether a line opens with a field label (`**Owner:**`, `Source:`) rather than prose."""
    if line.startswith(METADATA_BOLD_FIELD_PREFIX):
        return METADATA_BOLD_FIELD_SUFFIX in line
    return line.split(maxsplit=1)[0].endswith(METADATA_FIELD_SUFFIX)
