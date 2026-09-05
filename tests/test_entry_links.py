"""Supersession between entries of one log, and the sweep it enables."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.index import backlinks, build_links, load_corpus, sweep_targets
from spine.index.entry_links import entry_supersede_links, score_against, title_terms
from spine.model import Doc, LinkType

FIXTURE_CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "corpus-alpha"
PROJECT_SLUG = "alpha"
SUPERSEDED_ENTRY_ID = f"{PROJECT_SLUG}:decisions#windows-are-closed-intervals"
REPLACEMENT_ENTRY_ID = f"{PROJECT_SLUG}:decisions#windows-are-half-open-intervals"
CITING_DOC_ID = f"{PROJECT_SLUG}:design-scheduler"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


@pytest.fixture
def fixture_docs() -> tuple[Doc, ...]:
    return load_corpus(docs_dir=FIXTURE_CORPUS_DIR, project_slug=PROJECT_SLUG)


def test_title_terms_drop_short_words_and_plurals() -> None:
    assert title_terms(title="Windows are closed intervals") == {"window", "closed", "interval"}


def test_scoring_ignores_the_entries_own_terms() -> None:
    sentence = "Status: superseded."
    assert score_against(sentence=sentence, title="Windows are closed intervals") == 0


def test_one_supersede_link_in_the_right_direction(fixture_docs: tuple[Doc, ...]) -> None:
    links = entry_supersede_links(corpus=fixture_docs)
    assert [(link.src_id, link.dst_id) for link in links] == [
        (REPLACEMENT_ENTRY_ID, SUPERSEDED_ENTRY_ID)
    ]
    assert links[0].link_type is LinkType.SUPERSEDES


def test_an_entry_never_supersedes_itself(fixture_docs: tuple[Doc, ...]) -> None:
    assert all(link.src_id != link.dst_id for link in entry_supersede_links(corpus=fixture_docs))


def test_a_log_with_one_entry_produces_no_supersede_links(fixture_docs: tuple[Doc, ...]) -> None:
    lone = tuple(doc for doc in fixture_docs if doc.doc_id == SUPERSEDED_ENTRY_ID)
    assert entry_supersede_links(corpus=lone) == ()


def test_an_anchored_link_resolves_to_the_entry_not_the_file(
    fixture_docs: tuple[Doc, ...],
) -> None:
    links = build_links(docs=fixture_docs)
    targets = {link.dst_id for link in links if link.src_id == CITING_DOC_ID}
    assert SUPERSEDED_ENTRY_ID in targets


def test_superseding_an_entry_sweeps_the_docs_citing_it(fixture_docs: tuple[Doc, ...]) -> None:
    links = build_links(docs=fixture_docs)
    with_backlinks = links + backlinks(links=links)
    assert sweep_targets(
        links=with_backlinks, superseded_doc_id=SUPERSEDED_ENTRY_ID
    ) == (CITING_DOC_ID,)


def test_entries_are_not_reported_as_orphans(fixture_docs: tuple[Doc, ...]) -> None:
    from spine.index import SqliteGraphStore

    store = SqliteGraphStore()
    store.replace_project(
        project_slug=PROJECT_SLUG, docs=fixture_docs, links=build_links(docs=fixture_docs)
    )
    orphan_ids = [doc.doc_id for doc in store.orphans(project_slug=PROJECT_SLUG)]
    assert all("#" not in doc_id for doc_id in orphan_ids)
