"""Link extraction, backlink derivation, and the sqlite graph store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from spine.cli import main
from spine.constants import (
    DOC_FILE_SUFFIX,
    DOC_ID_SEPARATOR,
    MODEL_INFERRED_LINK_CONFIDENCE,
    SPINE_HOME_ENV_VAR,
    TEXTUAL_LINK_CONFIDENCE,
)
from spine.index import SqliteGraphStore, TextualLinkExtractor, build_links, load_corpus
from spine.index.backlinks import backlinks, deduplicate_links, sweep_targets
from spine.model import Doc, DocKind, Link, LinkType, ReadWhen
from spine.paths import graph_db_path
from spine.ports import GraphStore, LinkExtractor

FIXTURE_CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "corpus-alpha"
PROJECT_SLUG = "alpha"
OTHER_PROJECT_SLUG = "beta"
ORPHAN_DOC_STEM = "audit-legacy-sweep"
EXPECTED_FIXTURE_LINK_COUNT = 23
CORPUS_DIR_STAND_IN = Path("/corpus")


def make_doc(
    *,
    stem: str,
    body: str,
    kind: DocKind = DocKind.AREA_DESIGN,
    project_slug: str = PROJECT_SLUG,
    read_when: ReadWhen = ReadWhen.IN_AREA,
) -> Doc:
    return Doc(
        doc_id=f"{project_slug}{DOC_ID_SEPARATOR}{stem}",
        path=CORPUS_DIR_STAND_IN / f"{stem}{DOC_FILE_SUFFIX}",
        kind=kind,
        read_when=read_when,
        title=stem,
        body=body,
        project_slug=project_slug,
    )


def extract_from(*, doc: Doc, corpus: tuple[Doc, ...]):
    return TextualLinkExtractor().extract(doc=doc, corpus=corpus)


@pytest.fixture()
def graph_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture()
def fixture_docs() -> tuple[Doc, ...]:
    return load_corpus(docs_dir=FIXTURE_CORPUS_DIR, project_slug=PROJECT_SLUG)


def test_implementations_satisfy_the_ports() -> None:
    assert isinstance(TextualLinkExtractor(), LinkExtractor)
    assert isinstance(SqliteGraphStore(), GraphStore)


def test_markdown_link_resolves_to_the_target_doc_id() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(stem="brief", body="See [the design](design-scheduler.md) for detail.")
    links = extract_from(doc=source, corpus=(source, target))
    assert [(link.src_id, link.dst_id) for link in links] == [(source.doc_id, target.doc_id)]
    assert links[0].confidence == TEXTUAL_LINK_CONFIDENCE


def test_bare_file_name_in_prose_is_a_link() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(stem="brief", body="The allocator lives in design-scheduler.md today.")
    links = extract_from(doc=source, corpus=(source, target))
    assert [link.dst_id for link in links] == [target.doc_id]


def test_external_url_is_not_a_link() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="brief", body="See [upstream](https://example.test/design-scheduler.md)."
    )
    assert extract_from(doc=source, corpus=(source, target)) == ()


def test_relative_paths_and_anchors_resolve_to_one_link() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="brief",
        body="See [a](./design-scheduler.md#what-lost) and [b](../uplink/design-scheduler.md).",
    )
    links = extract_from(doc=source, corpus=(source, target))
    assert [link.dst_id for link in links] == [target.doc_id]


def test_a_file_name_that_merely_contains_another_is_not_a_mention() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="brief", body="See legacy-design-scheduler.md and design-scheduler.markdown."
    )
    assert extract_from(doc=source, corpus=(source, target)) == ()


@pytest.mark.parametrize(
    ("kind", "sentence", "expected"),
    [
        (DocKind.PROJECT_RULES, "Rule 1 binds [x](design-scheduler.md).", LinkType.CONSTRAINS),
        (DocKind.CLASSIFICATION, "This classifies [x](design-scheduler.md).", LinkType.CLASSIFIES),
        (DocKind.MILESTONE, "Implements [x](design-scheduler.md).", LinkType.IMPLEMENTS),
        (DocKind.ROLLOUT, "Ramps [x](design-scheduler.md).", LinkType.RAMPS),
        (DocKind.TEST_COVERAGE, "Verifies [x](design-scheduler.md).", LinkType.VERIFIES),
        (DocKind.OPEN_QUESTIONS, "Blocks [x](design-scheduler.md).", LinkType.BLOCKS),
        (DocKind.OPEN_QUESTIONS, "Blocked by [x](design-scheduler.md).", LinkType.DEPENDS_ON),
        (DocKind.BRIEF, "Context in [x](design-scheduler.md).", LinkType.MENTIONS),
        (DocKind.AREA_DESIGN, "Ramps [x](design-scheduler.md).", LinkType.MENTIONS),
    ],
)
def test_link_type_follows_source_kind_and_phrasing(
    kind: DocKind, sentence: str, expected: LinkType
) -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(stem="source", body=sentence, kind=kind)
    links = extract_from(doc=source, corpus=(source, target))
    assert [link.link_type for link in links] == [expected]


def test_supersedes_phrasing_points_at_the_replaced_doc() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="decisions",
        body="Supersedes [the closed-interval design](design-scheduler.md).",
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
    )
    links = extract_from(doc=source, corpus=(source, target))
    assert [(link.src_id, link.dst_id, link.link_type) for link in links] == [
        (source.doc_id, target.doc_id, LinkType.SUPERSEDES)
    ]


def test_superseded_by_phrasing_inverts_the_direction() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="decisions",
        body="Superseded by [the half-open design](design-scheduler.md).",
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
    )
    links = extract_from(doc=source, corpus=(source, target))
    assert {(link.src_id, link.dst_id, link.link_type) for link in links} == {
        (target.doc_id, source.doc_id, LinkType.SUPERSEDES),
        (source.doc_id, target.doc_id, LinkType.MENTIONS),
    }


def test_cited_by_phrasing_inverts_the_direction() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="decisions",
        body="Cited by [design-scheduler.md](design-scheduler.md).",
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
    )
    links = extract_from(doc=source, corpus=(source, target))
    assert {(link.src_id, link.dst_id, link.link_type) for link in links} == {
        (target.doc_id, source.doc_id, LinkType.MENTIONS),
        (source.doc_id, target.doc_id, LinkType.MENTIONS),
    }


def test_sweep_still_reaches_a_doc_that_only_declares_an_inverse_citation() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="decisions",
        body="Cited by [design-scheduler.md](design-scheduler.md).",
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
    )
    links = extract_from(doc=source, corpus=(source, target))
    assert sweep_targets(links=links, superseded_doc_id=target.doc_id) == (source.doc_id,)


def test_a_doc_never_links_to_itself() -> None:
    source = make_doc(stem="brief", body="See [this file](brief.md) and brief.md again.")
    assert extract_from(doc=source, corpus=(source,)) == ()


def test_repeated_references_collapse_to_one_link() -> None:
    target = make_doc(stem="design-scheduler", body="Allocator notes.")
    source = make_doc(
        stem="brief",
        body=(
            "See [the design](design-scheduler.md).\n\n"
            "Also design-scheduler.md.\n\nAnd [again](design-scheduler.md)."
        ),
    )
    assert len(extract_from(doc=source, corpus=(source, target))) == 1


def test_deduplicate_keeps_the_most_confident_link() -> None:
    weak = Link(
        src_id="a",
        dst_id="b",
        link_type=LinkType.MENTIONS,
        confidence=MODEL_INFERRED_LINK_CONFIDENCE,
    )
    strong = Link(
        src_id="a", dst_id="b", link_type=LinkType.MENTIONS, confidence=TEXTUAL_LINK_CONFIDENCE
    )
    assert deduplicate_links(links=(weak, strong)) == (strong,)
    assert deduplicate_links(links=(strong, weak)) == (strong,)


def test_backlinks_invert_citations_and_skip_supersedes() -> None:
    citation = Link(src_id="a", dst_id="b", link_type=LinkType.CONSTRAINS)
    replacement = Link(src_id="a", dst_id="c", link_type=LinkType.SUPERSEDES)
    derived = backlinks(links=(citation, replacement))
    assert [(link.src_id, link.dst_id, link.link_type) for link in derived] == [
        ("b", "a", LinkType.CITED_BY)
    ]


def test_sweep_targets_finds_every_citer_of_a_superseded_doc(
    fixture_docs: tuple[Doc, ...],
) -> None:
    links = build_links(docs=fixture_docs)
    superseded = f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window"
    assert sweep_targets(links=links, superseded_doc_id=superseded) == (
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}brief",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}open-questions",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}project-rules",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}rollout-uplink",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}test-coverage-uplink",
    )


def test_sweep_targets_reads_derived_backlinks_too(fixture_docs: tuple[Doc, ...]) -> None:
    links = build_links(docs=fixture_docs)
    superseded = f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window"
    from_forward = sweep_targets(links=links, superseded_doc_id=superseded)
    from_inverse = sweep_targets(links=backlinks(links=links), superseded_doc_id=superseded)
    assert from_inverse == from_forward


def test_sweep_targets_never_returns_the_superseded_doc() -> None:
    self_citation = Link(src_id="a", dst_id="a", link_type=LinkType.MENTIONS)
    assert sweep_targets(links=(self_citation,), superseded_doc_id="a") == ()


def test_store_round_trips_docs_and_links(graph_home: Path, fixture_docs: tuple[Doc, ...]) -> None:
    store = SqliteGraphStore()
    links = build_links(docs=fixture_docs)
    store.replace_project(project_slug=PROJECT_SLUG, docs=fixture_docs, links=links)
    assert graph_db_path().exists()
    stored = store.docs_for_project(project_slug=PROJECT_SLUG)
    assert stored == tuple(sorted(fixture_docs, key=lambda doc: doc.doc_id))


def test_outbound_and_inbound_filter_by_link_type(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    store.replace_project(
        project_slug=PROJECT_SLUG, docs=fixture_docs, links=build_links(docs=fixture_docs)
    )
    milestone = f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window"
    assert {link.dst_id for link in store.outbound(doc_id=milestone)} == {
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}brief",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}rollout-uplink",
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}test-coverage-uplink",
    }
    assert {link.link_type for link in store.inbound(doc_id=milestone)} == {
        LinkType.CONSTRAINS,
        LinkType.MENTIONS,
        LinkType.BLOCKS,
        LinkType.RAMPS,
        LinkType.VERIFIES,
    }
    ramps = store.inbound(doc_id=milestone, link_type=LinkType.RAMPS)
    assert [link.src_id for link in ramps] == [f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}rollout-uplink"]
    assert store.outbound(doc_id=milestone, link_type=LinkType.RAMPS) == ()


def test_replace_project_is_idempotent(graph_home: Path, fixture_docs: tuple[Doc, ...]) -> None:
    store = SqliteGraphStore()
    links = build_links(docs=fixture_docs)
    store.replace_project(project_slug=PROJECT_SLUG, docs=fixture_docs, links=links)
    first = store.docs_for_project(project_slug=PROJECT_SLUG)
    first_links = store.inbound(doc_id=f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window")
    store.replace_project(project_slug=PROJECT_SLUG, docs=fixture_docs, links=links)
    assert store.docs_for_project(project_slug=PROJECT_SLUG) == first
    assert (
        store.inbound(doc_id=f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window")
        == first_links
    )


def test_failed_replace_leaves_the_previous_graph_intact(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    links = build_links(docs=fixture_docs)
    store.replace_project(project_slug=PROJECT_SLUG, docs=fixture_docs, links=links)
    colliding = (*fixture_docs, fixture_docs[0])
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_project(project_slug=PROJECT_SLUG, docs=colliding, links=())
    assert store.docs_for_project(project_slug=PROJECT_SLUG) == tuple(
        sorted(fixture_docs, key=lambda doc: doc.doc_id)
    )
    assert len(store.inbound(doc_id=f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}design-scheduler")) > 0


def test_orphans_finds_the_one_unlinked_fixture_doc(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    store.replace_project(
        project_slug=PROJECT_SLUG, docs=fixture_docs, links=build_links(docs=fixture_docs)
    )
    assert [doc.doc_id for doc in store.orphans(project_slug=PROJECT_SLUG)] == [
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}{ORPHAN_DOC_STEM}"
    ]


def test_derived_backlinks_do_not_hide_orphans(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    links = build_links(docs=fixture_docs)
    store.replace_project(
        project_slug=PROJECT_SLUG, docs=fixture_docs, links=(*links, *backlinks(links=links))
    )
    assert [doc.doc_id for doc in store.orphans(project_slug=PROJECT_SLUG)] == [
        f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}{ORPHAN_DOC_STEM}"
    ]


def test_two_projects_stay_separate_in_one_database(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    other_docs = load_corpus(docs_dir=FIXTURE_CORPUS_DIR, project_slug=OTHER_PROJECT_SLUG)
    store.replace_project(
        project_slug=PROJECT_SLUG, docs=fixture_docs, links=build_links(docs=fixture_docs)
    )
    store.replace_project(project_slug=OTHER_PROJECT_SLUG, docs=other_docs, links=())
    assert {doc.project_slug for doc in store.docs_for_project(project_slug=PROJECT_SLUG)} == {
        PROJECT_SLUG
    }
    assert len(store.docs_for_project(project_slug=OTHER_PROJECT_SLUG)) == len(other_docs)
    assert len(store.orphans(project_slug=OTHER_PROJECT_SLUG)) == len(
        [doc for doc in other_docs if not doc.is_entry]
    )
    assert len(store.orphans(project_slug=PROJECT_SLUG)) == 1


def test_reindexing_one_project_leaves_the_other_alone(
    graph_home: Path, fixture_docs: tuple[Doc, ...]
) -> None:
    store = SqliteGraphStore()
    other_docs = load_corpus(docs_dir=FIXTURE_CORPUS_DIR, project_slug=OTHER_PROJECT_SLUG)
    store.replace_project(
        project_slug=OTHER_PROJECT_SLUG, docs=other_docs, links=build_links(docs=other_docs)
    )
    store.replace_project(project_slug=PROJECT_SLUG, docs=(), links=())
    assert len(store.docs_for_project(project_slug=OTHER_PROJECT_SLUG)) == len(other_docs)
    assert store.docs_for_project(project_slug=PROJECT_SLUG) == ()


def test_fixture_corpus_extraction_is_stable(fixture_docs: tuple[Doc, ...]) -> None:
    links = build_links(docs=fixture_docs)
    files = list(FIXTURE_CORPUS_DIR.glob(f"*{DOC_FILE_SUFFIX}"))
    assert len([doc for doc in fixture_docs if not doc.is_entry]) == len(files)
    assert any(doc.is_entry for doc in fixture_docs)
    assert len(links) == EXPECTED_FIXTURE_LINK_COUNT
    assert all(link.src_id != link.dst_id for link in links)
    assert all(link.confidence == TEXTUAL_LINK_CONFIDENCE for link in links)


def test_cli_builds_indexes_and_sweeps(
    graph_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["index", "build", "--dir", str(FIXTURE_CORPUS_DIR), "--project", PROJECT_SLUG]) == 0
    )
    capsys.readouterr()
    assert main(["index", "orphans", "--project", PROJECT_SLUG]) == 0
    assert capsys.readouterr().out.strip() == f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}{ORPHAN_DOC_STEM}"
    milestone = f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}milestone-uplink-window"
    assert main(["index", "sweep", "--doc", milestone]) == 0
    assert f"{PROJECT_SLUG}{DOC_ID_SEPARATOR}rollout-uplink" in capsys.readouterr().out


def test_cli_build_reports_an_empty_corpus(graph_home: Path, tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert main(["index", "build", "--dir", str(empty_dir), "--project", PROJECT_SLUG]) != 0


def test_index_help_is_reachable() -> None:
    from spine.cli import build_parser

    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["index", "--help"])
    assert exit_info.value.code == 0
