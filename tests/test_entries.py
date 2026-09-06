"""Log segmentation into addressable entries."""

from __future__ import annotations

from pathlib import Path

from spine.constants import ENTRY_ANCHOR_SEPARATOR
from spine.docs.entries import entry_doc_id, slugify_heading, split_into_entries, with_entries
from spine.model import DocKind, Doc, ReadWhen

PROJECT_SLUG = "alpha"
LOG_BODY = """# Decision log

## First decision
Status: decided.

## Second decision
Status: superseded.
"""


def _doc(*, kind: DocKind, body: str, stem: str = "decisions") -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=kind,
        read_when=ReadWhen.LOG,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
    )


def test_slugify_collapses_punctuation_and_runs() -> None:
    assert slugify_heading(heading="Windows are  half-open intervals!") == (
        "windows-are-half-open-intervals"
    )


def test_entry_doc_id_anchors_onto_the_parent() -> None:
    assert entry_doc_id(parent_doc_id="alpha:decisions", heading="First decision") == (
        f"alpha:decisions{ENTRY_ANCHOR_SEPARATOR}first-decision"
    )


def test_a_log_splits_at_second_level_headings() -> None:
    entries = split_into_entries(doc=_doc(kind=DocKind.DECISION_LOG, body=LOG_BODY))
    assert [entry.title for entry in entries] == ["First decision", "Second decision"]


def test_entries_carry_their_parent_and_report_as_entries() -> None:
    entries = split_into_entries(doc=_doc(kind=DocKind.DECISION_LOG, body=LOG_BODY))
    assert all(entry.parent_doc_id == f"{PROJECT_SLUG}:decisions" for entry in entries)
    assert all(entry.is_entry for entry in entries)


def test_an_entry_body_stops_at_the_next_heading() -> None:
    first, second = split_into_entries(doc=_doc(kind=DocKind.DECISION_LOG, body=LOG_BODY))
    assert "Second decision" not in first.body
    assert "First decision" not in second.body


def test_non_log_kinds_are_never_segmented() -> None:
    assert split_into_entries(doc=_doc(kind=DocKind.AREA_DESIGN, body=LOG_BODY)) == ()


def test_an_entry_is_not_segmented_again() -> None:
    entries = split_into_entries(doc=_doc(kind=DocKind.DECISION_LOG, body=LOG_BODY))
    assert split_into_entries(doc=entries[0]) == ()


def test_a_log_with_no_headings_yields_no_entries() -> None:
    assert split_into_entries(doc=_doc(kind=DocKind.DECISION_LOG, body="# Log\n\nProse only.")) == ()


def test_with_entries_keeps_originals_and_appends_entries() -> None:
    log = _doc(kind=DocKind.DECISION_LOG, body=LOG_BODY)
    design = _doc(kind=DocKind.AREA_DESIGN, body="# Design\n\nProse.", stem="design")
    expanded = with_entries(docs=(log, design))
    assert expanded[0] is log
    assert design in expanded
    assert len([doc for doc in expanded if doc.is_entry]) == 2


def test_entries_are_always_in_the_log_group() -> None:
    log = _doc(kind=DocKind.DECISION_LOG, body=LOG_BODY)
    log.read_when = ReadWhen.IN_AREA
    entries = split_into_entries(doc=log)
    assert entries
    assert all(entry.read_when is ReadWhen.LOG for entry in entries)
