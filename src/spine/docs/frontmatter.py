"""Parses the frontmatter dialect the corpus uses: scalars, nulls, booleans, inline lists.

Hand-rolled because the project carries no runtime dependencies. Anything the dialect
does not cover falls back to the raw string rather than raising.
"""

from __future__ import annotations

from typing import NamedTuple

from ..constants import (
    FRONTMATTER_COMMENT_PREFIX,
    FRONTMATTER_DELIMITER,
    FRONTMATTER_FALSE_LITERAL,
    FRONTMATTER_KEY_SEPARATOR,
    FRONTMATTER_LIST_CLOSE,
    FRONTMATTER_LIST_ITEM_SEPARATOR,
    FRONTMATTER_LIST_OPEN,
    FRONTMATTER_NULL_LITERAL,
    FRONTMATTER_QUOTE_CHARACTERS,
    FRONTMATTER_TRUE_LITERAL,
)

FIRST_LINE_NUMBER = 1


class FrontmatterParse(NamedTuple):
    """Parsed frontmatter, the body below it, and the body's 1-indexed start line."""

    mapping: dict[str, object]
    body: str
    body_start_line: int


class _DelimitedBlock(NamedTuple):
    entry_lines: list[str]
    body_lines: list[str]
    body_start_line: int


def parse_frontmatter(*, text: str) -> FrontmatterParse:
    """Split frontmatter from body. A file without frontmatter yields an empty mapping."""
    block = _split_at_delimiters(lines=text.splitlines())
    if block is None:
        return FrontmatterParse(mapping={}, body=text, body_start_line=FIRST_LINE_NUMBER)
    return FrontmatterParse(
        mapping=_parse_entries(lines=block.entry_lines),
        body="\n".join(block.body_lines),
        body_start_line=block.body_start_line,
    )


def _split_at_delimiters(*, lines: list[str]) -> _DelimitedBlock | None:
    """Locate the opening and closing delimiters. Returns None when either is missing."""
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None
    for offset, line in enumerate(lines[FIRST_LINE_NUMBER:], start=FIRST_LINE_NUMBER):
        if line.strip() != FRONTMATTER_DELIMITER:
            continue
        body_index = offset + FIRST_LINE_NUMBER
        return _DelimitedBlock(
            entry_lines=lines[FIRST_LINE_NUMBER:offset],
            body_lines=lines[body_index:],
            body_start_line=body_index + FIRST_LINE_NUMBER,
        )
    return None


def _parse_entries(*, lines: list[str]) -> dict[str, object]:
    """Build the mapping, skipping blanks, comments, and lines with no key separator."""
    mapping: dict[str, object] = {}
    for line in lines:
        entry = _parse_entry(line=line)
        if entry is not None:
            key, value = entry
            mapping[key] = value
    return mapping


def _parse_entry(*, line: str) -> tuple[str, object] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(FRONTMATTER_COMMENT_PREFIX):
        return None
    key, separator, raw_value = stripped.partition(FRONTMATTER_KEY_SEPARATOR)
    if not separator or not key.strip():
        return None
    return key.strip(), _parse_value(raw=raw_value.strip())


def _parse_value(*, raw: str) -> object:
    if _is_list_literal(raw=raw):
        return _parse_inline_list(raw=raw)
    return _parse_scalar(raw=raw)


def _is_list_literal(*, raw: str) -> bool:
    return raw.startswith(FRONTMATTER_LIST_OPEN) and raw.endswith(FRONTMATTER_LIST_CLOSE)


def _parse_inline_list(*, raw: str) -> list[str]:
    inner = raw.removeprefix(FRONTMATTER_LIST_OPEN).removesuffix(FRONTMATTER_LIST_CLOSE)
    items = (_unquote(raw=item.strip()) for item in inner.split(FRONTMATTER_LIST_ITEM_SEPARATOR))
    return [item for item in items if item]


def _parse_scalar(*, raw: str) -> object:
    unquoted = _unquote(raw=raw)
    if not unquoted or unquoted.lower() == FRONTMATTER_NULL_LITERAL:
        return None
    if unquoted.lower() == FRONTMATTER_TRUE_LITERAL:
        return True
    if unquoted.lower() == FRONTMATTER_FALSE_LITERAL:
        return False
    return unquoted


def _unquote(*, raw: str) -> str:
    for quote in FRONTMATTER_QUOTE_CHARACTERS:
        if raw != quote and raw.startswith(quote) and raw.endswith(quote):
            return raw.removeprefix(quote).removesuffix(quote)
    return raw
