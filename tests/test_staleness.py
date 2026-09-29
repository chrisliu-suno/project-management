"""Drift the graph and the filesystem expose."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.dashboard import Severity
from spine.facts.staleness import unswept_supersessions
from spine.model import Doc, DocKind, Link, LinkType, ReadWhen

PROJECT_SLUG = "alpha"
SUPERSEDED_ID = f"{PROJECT_SLUG}:decisions#old"
REPLACEMENT_ID = f"{PROJECT_SLUG}:decisions#new"
CITER_ID = f"{PROJECT_SLUG}:design"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _doc(*, doc_id: str, stem: str, parent: str | None = None) -> Doc:
    return Doc(
        doc_id=doc_id,
        path=Path(f"{stem}.md"),
        kind=DocKind.AREA_DESIGN,
        read_when=ReadWhen.IN_AREA,
        title=stem,
        body="# T\n\nProse.",
        project_slug=PROJECT_SLUG,
        parent_doc_id=parent,
    )


def _supersedes() -> Link:
    return Link(src_id=REPLACEMENT_ID, dst_id=SUPERSEDED_ID, link_type=LinkType.SUPERSEDES)


def _citation() -> Link:
    return Link(src_id=CITER_ID, dst_id=SUPERSEDED_ID, link_type=LinkType.MENTIONS)


def test_a_superseded_decision_with_citers_is_flagged() -> None:
    docs = (
        _doc(doc_id=SUPERSEDED_ID, stem="decisions", parent=f"{PROJECT_SLUG}:decisions"),
        _doc(doc_id=CITER_ID, stem="design"),
    )
    found = unswept_supersessions(docs=docs, links=(_supersedes(), _citation()))
    assert found[0].code == "unswept_supersession"
    assert found[0].doc_ids == (CITER_ID,)
    assert found[0].severity is Severity.WARN


def test_a_superseded_decision_nobody_cites_is_not_flagged() -> None:
    docs = (_doc(doc_id=SUPERSEDED_ID, stem="decisions", parent=f"{PROJECT_SLUG}:decisions"),)
    assert unswept_supersessions(docs=docs, links=(_supersedes(),)) == ()


def test_a_citer_that_also_cites_the_replacement_is_swept() -> None:
    docs = (
        _doc(doc_id=SUPERSEDED_ID, stem="decisions", parent=f"{PROJECT_SLUG}:decisions"),
        _doc(doc_id=REPLACEMENT_ID, stem="decisions", parent=f"{PROJECT_SLUG}:decisions"),
        _doc(doc_id=CITER_ID, stem="design"),
    )
    cites_replacement = Link(
        src_id=CITER_ID, dst_id=REPLACEMENT_ID, link_type=LinkType.MENTIONS
    )
    links = (_supersedes(), _citation(), cites_replacement)
    assert unswept_supersessions(docs=docs, links=links) == ()


def test_citing_a_different_document_does_not_count_as_sweeping() -> None:
    other_id = f"{PROJECT_SLUG}:unrelated"
    docs = (
        _doc(doc_id=SUPERSEDED_ID, stem="decisions", parent=f"{PROJECT_SLUG}:decisions"),
        _doc(doc_id=CITER_ID, stem="design"),
        _doc(doc_id=other_id, stem="unrelated"),
    )
    cites_other = Link(src_id=CITER_ID, dst_id=other_id, link_type=LinkType.MENTIONS)
    links = (_supersedes(), _citation(), cites_other)
    assert unswept_supersessions(docs=docs, links=links)[0].doc_ids == (CITER_ID,)


def test_no_supersessions_flag_nothing() -> None:
    assert unswept_supersessions(docs=(_doc(doc_id=CITER_ID, stem="design"),), links=()) == ()



def test_two_documents_sharing_a_title_stay_distinguishable() -> None:
    docs = (
        _doc(doc_id=SUPERSEDED_ID, stem="prd-product", parent=f"{PROJECT_SLUG}:decisions"),
        _doc(doc_id=CITER_ID, stem="design"),
    )
    found = unswept_supersessions(docs=docs, links=(_supersedes(), _citation()))
    assert "prd-product.md" in found[0].detail


def test_a_superseded_document_missing_from_the_corpus_is_named_by_id() -> None:
    docs = (_doc(doc_id=CITER_ID, stem="design"),)
    found = unswept_supersessions(docs=docs, links=(_supersedes(), _citation()))
    assert SUPERSEDED_ID in found[0].detail
