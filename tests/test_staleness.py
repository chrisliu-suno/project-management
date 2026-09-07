"""Drift the graph and the filesystem expose."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.dashboard import Severity
from spine.facts.model import Fact, FactKind, PullRequestState
from spine.facts.staleness import stale_since_shipped, unswept_supersessions
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


def test_no_supersessions_flag_nothing() -> None:
    assert unswept_supersessions(docs=(_doc(doc_id=CITER_ID, stem="design"),), links=()) == ()


def _merged(*, when: datetime) -> Fact:
    return Fact(
        fact_id=f"{PROJECT_SLUG}:pr:1",
        project_slug=PROJECT_SLUG,
        kind=FactKind.PULL_REQUEST,
        reference="#1",
        title="shipped",
        author="someone",
        occurred_at=when.isoformat(),
        state=str(PullRequestState.MERGED),
    )


def _corpus_with(*, docs_dir: Path, age_seconds: int) -> tuple[Doc, ...]:
    target = docs_dir / "design.md"
    target.write_text("# Design\n\nProse.\n", encoding="utf-8")
    stamp = (datetime.now(tz=UTC) - timedelta(seconds=age_seconds)).timestamp()
    os.utime(target, (stamp, stamp))
    return (_doc(doc_id=CITER_ID, stem="design"),)


def test_a_document_older_than_the_last_merge_is_stale(tmp_path: Path) -> None:
    docs = _corpus_with(docs_dir=tmp_path, age_seconds=3600)
    facts = (_merged(when=datetime.now(tz=UTC)),)
    found = stale_since_shipped(docs=docs, facts=facts, docs_dir=tmp_path)
    assert found[0].code == "stale_since_shipped"
    assert found[0].doc_ids == (CITER_ID,)


def test_a_document_newer_than_the_last_merge_is_not_stale(tmp_path: Path) -> None:
    docs = _corpus_with(docs_dir=tmp_path, age_seconds=0)
    facts = (_merged(when=datetime.now(tz=UTC) - timedelta(hours=2)),)
    assert stale_since_shipped(docs=docs, facts=facts, docs_dir=tmp_path) == ()


def test_no_merges_mean_nothing_is_stale(tmp_path: Path) -> None:
    docs = _corpus_with(docs_dir=tmp_path, age_seconds=3600)
    assert stale_since_shipped(docs=docs, facts=(), docs_dir=tmp_path) == ()


def test_a_missing_file_is_not_reported_as_stale(tmp_path: Path) -> None:
    docs = (_doc(doc_id=CITER_ID, stem="gone"),)
    facts = (_merged(when=datetime.now(tz=UTC)),)
    assert stale_since_shipped(docs=docs, facts=facts, docs_dir=tmp_path) == ()


def test_log_entries_are_never_reported_as_stale(tmp_path: Path) -> None:
    _corpus_with(docs_dir=tmp_path, age_seconds=3600)
    entry = _doc(doc_id=SUPERSEDED_ID, stem="design", parent=f"{PROJECT_SLUG}:decisions")
    facts = (_merged(when=datetime.now(tz=UTC)),)
    assert stale_since_shipped(docs=(entry,), facts=facts, docs_dir=tmp_path) == ()
