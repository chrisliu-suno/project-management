"""Harvests the one-line purpose each start-here document already states per doc.

A brief document's two-column tables name a sibling document on the left and say what it is
for on the right. That sentence is the cheapest useful description of a document that exists,
and it is written by hand, so it is preferred over anything derived from the body.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..constants import (
    BODY_STRUCTURE_LINE_PREFIXES,
    BODY_WRAPPING_LINE_PREFIXES,
    BRIEF_REFERENCE_SUFFIXES,
    BRIEF_TABLE_MIN_CELLS,
    BRIEF_TEXT_MAX_CHARACTERS,
    MARKDOWN_FRAGMENT_SEPARATOR,
    MARKDOWN_LINK_TARGET_PATTERN,
    MARKDOWN_TABLE_CELL_SEPARATOR,
    MARKDOWN_TABLE_RULE_CHARACTERS,
    METADATA_BOLD_FIELD_PREFIX,
    METADATA_BOLD_FIELD_SUFFIX,
    METADATA_FIELD_SUFFIX,
    PURPOSE_FIELD_PREFIXES,
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
    """Every table row where one of the first two cells names a document and the other says why."""
    rows: list[BriefRow] = []
    for line in body.splitlines():
        cells = get_cells_from_table_line(line=line)
        if cells is None:
            continue
        row = get_brief_row_from_cells(cells=cells)
        if row:
            rows.append(row)
    return tuple(rows)


def get_brief_row_from_cells(*, cells: tuple[str, ...]) -> BriefRow | None:
    """The document and its purpose, whichever column each is in.

    A `| Read | For |` table names the document first; a `| Question | Read |` table names it
    second, and there the question is the better statement of purpose.
    """
    for reference_index, brief_index in ((0, 1), (1, 0)):
        stem = get_document_stem_from_cell(cell=cells[reference_index])
        brief = truncate_brief(text=cells[brief_index])
        if stem and brief and not get_document_stem_from_cell(cell=cells[brief_index]):
            return BriefRow(stem=stem, brief=brief)
    return None


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

    A cell names its document either bare — in backticks, qualified by a directory or a trailing
    parenthetical — or as a markdown link, whose label is prose and whose target is the reference.
    The link target wins, because a label like "Project status and PRs" names no file.
    """
    linked = get_link_target_from_cell(cell=cell)
    if linked:
        return linked
    for token in cell.replace("`", " ").split():
        if check_names_a_document(reference=token.strip("()[],;")):
            return Path(token.strip("()[],;")).stem
    return None


def get_link_target_from_cell(*, cell: str) -> str | None:
    """The document stem a markdown link in the cell points at, ignoring any `#anchor`."""
    match = MARKDOWN_LINK_TARGET_PATTERN.search(cell)
    if not match:
        return None
    reference = strip_fragment(reference=match.group(1).strip())
    return Path(reference).stem if check_names_a_document(reference=reference) else None


def strip_fragment(*, reference: str) -> str:
    """A link target without its `#section` suffix, which names a heading rather than a file."""
    return reference.split(MARKDOWN_FRAGMENT_SEPARATOR, maxsplit=1)[0]


def check_names_a_document(*, reference: str) -> bool:
    """Whether a reference ends in a suffix the corpus keeps documents under."""
    return reference.endswith(BRIEF_REFERENCE_SUFFIXES)


def truncate_brief(*, text: str) -> str:
    """Collapse a cell to a single line, cut to the length a brief index can afford."""
    collapsed = " ".join(text.replace("`", "").split())
    return collapsed[:BRIEF_TEXT_MAX_CHARACTERS]


def get_fallback_brief_from_body(*, body: str) -> str | None:
    """A document's own account of itself, for one no brief table names.

    A `**Purpose:**` line is the document saying what it is for and is taken whole; otherwise
    the opening sentence, skipping header fields so a plan is not described by its owner.
    """
    declared = get_purpose_field_from_body(body=body)
    if declared:
        return truncate_brief(text=declared)
    paragraph = get_first_prose_paragraph(body=body)
    if not paragraph:
        return None
    return truncate_brief(text=get_first_sentence(text=paragraph))


def get_purpose_field_from_body(*, body: str) -> str | None:
    """The text of a `**Purpose:**` header field, including the lines it wraps onto."""
    collected: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if collected:
            if not stripped or check_is_metadata_line(line=stripped):
                break
            collected.append(stripped)
            continue
        for prefix in PURPOSE_FIELD_PREFIXES:
            if stripped.lower().startswith(prefix.lower()):
                collected.append(stripped[len(prefix) :].strip())
                break
    if not collected:
        return None
    return get_first_sentence(text=" ".join(collected))


def get_first_prose_paragraph(*, body: str) -> str:
    """The first run of consecutive prose lines, so a wrapped sentence is not cut mid-clause.

    A skipped header field takes its wrapped continuation lines with it; otherwise the
    paragraph starts mid-clause on whatever line the field ran onto.
    """
    collected: list[str] = []
    is_inside_skipped_field = False
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            is_inside_skipped_field = False
            if collected:
                break
            continue
        if stripped.startswith(BODY_STRUCTURE_LINE_PREFIXES):
            is_inside_skipped_field = False
            if collected:
                break
            continue
        if stripped.startswith(BODY_WRAPPING_LINE_PREFIXES) or check_is_metadata_line(
            line=stripped
        ):
            is_inside_skipped_field = True
            if collected:
                break
            continue
        if is_inside_skipped_field:
            continue
        collected.append(stripped)
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
