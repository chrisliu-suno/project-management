"""Guards on the shared contracts. Modules are written against these."""

from __future__ import annotations

from pathlib import Path

from spine.constants import (
    EVERY_TIME_RESERVED_LINES,
    INJECTION_LINE_BUDGET,
    MAX_LINES_PER_READ_WHEN,
)
from spine.model import DEFAULT_READ_WHEN, DocKind, ReadWhen

FIXTURE_CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "corpus-alpha"


def test_every_doc_kind_has_a_read_when_group() -> None:
    assert set(DEFAULT_READ_WHEN) == set(DocKind)


def test_every_read_when_group_has_a_size_cap() -> None:
    assert set(MAX_LINES_PER_READ_WHEN) == set(ReadWhen)


def test_every_time_group_is_capped_hardest() -> None:
    every_time_cap = MAX_LINES_PER_READ_WHEN[ReadWhen.EVERY_TIME]
    others = [cap for group, cap in MAX_LINES_PER_READ_WHEN.items() if group is not ReadWhen.EVERY_TIME]
    assert all(every_time_cap <= cap for cap in others)


def test_every_time_reservation_fits_inside_the_injection_budget() -> None:
    assert EVERY_TIME_RESERVED_LINES < INJECTION_LINE_BUDGET


def test_every_time_reservation_covers_its_own_cap() -> None:
    assert EVERY_TIME_RESERVED_LINES >= MAX_LINES_PER_READ_WHEN[ReadWhen.EVERY_TIME]


def test_fixture_corpus_is_present() -> None:
    docs = list(FIXTURE_CORPUS_DIR.glob("*.md"))
    assert len(docs) >= len(DocKind) - 2


def test_cli_builds_without_any_module_registered() -> None:
    from spine.cli import build_parser

    assert build_parser().prog == "spine"
