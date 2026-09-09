"""Whether a corpus can bring a reader up to speed."""

from __future__ import annotations

from pathlib import Path

from spine.health.onboarding import (
    entry_points,
    newest_date,
    onboarding_findings,
    reachable_from,
)
from spine.model import Doc, DocKind, Link, LinkType, ReadWhen

PROJECT_SLUG = "alpha"


def _doc(
    *,
    stem: str,
    body: str = "# T\n\nProse.",
    read_when: ReadWhen = ReadWhen.IN_AREA,
    parent: str | None = None,
) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=DocKind.AREA_DESIGN,
        read_when=read_when,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
        parent_doc_id=parent,
    )


def _mentions(*, src: str, dst: str) -> Link:
    return Link(
        src_id=f"{PROJECT_SLUG}:{src}",
        dst_id=f"{PROJECT_SLUG}:{dst}",
        link_type=LinkType.MENTIONS,
    )


def _codes(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> list[str]:
    return [finding.code for finding in onboarding_findings(docs=docs, links=links)]


def test_a_corpus_with_no_every_time_document_has_no_entry_point() -> None:
    docs = (_doc(stem="design"), _doc(stem="rollout"))
    assert "no_entry_point" in _codes(docs=docs, links=())


def test_an_every_time_document_is_the_entry_point() -> None:
    entry = _doc(stem="brief", read_when=ReadWhen.EVERY_TIME)
    assert entry_points(docs=(entry, _doc(stem="design"))) == (entry,)


def test_an_empty_corpus_reports_nothing() -> None:
    assert onboarding_findings(docs=(), links=()) == ()


def test_an_entry_point_far_behind_the_corpus_is_stale() -> None:
    entry = _doc(stem="brief", body="# B\n\n**Date:** 2026-06-17\n", read_when=ReadWhen.EVERY_TIME)
    later = _doc(stem="design", body="# D\n\nWork through 2026-09-08 landed.\n")
    links = (_mentions(src="brief", dst="design"),)
    assert "stale_entry_point" in _codes(docs=(entry, later), links=links)


def test_an_entry_point_in_step_with_the_corpus_is_not_stale() -> None:
    entry = _doc(stem="brief", body="# B\n\n**Date:** 2026-09-07\n", read_when=ReadWhen.EVERY_TIME)
    later = _doc(stem="design", body="# D\n\nWork through 2026-09-08 landed.\n")
    links = (_mentions(src="brief", dst="design"),)
    assert "stale_entry_point" not in _codes(docs=(entry, later), links=links)


def test_an_undated_entry_point_is_not_called_stale() -> None:
    entry = _doc(stem="brief", body="# B\n\nNo dates here.\n", read_when=ReadWhen.EVERY_TIME)
    later = _doc(stem="design", body="# D\n\n2026-09-08 landed.\n")
    assert "stale_entry_point" not in _codes(docs=(entry, later), links=())


def test_the_newest_date_is_read_across_the_corpus() -> None:
    docs = (_doc(stem="a", body="2026-01-02"), _doc(stem="b", body="2026-09-08"))
    assert newest_date(docs=docs) == "2026-09-08"


def test_a_document_linked_from_the_entry_point_is_reachable() -> None:
    entry = _doc(stem="brief", read_when=ReadWhen.EVERY_TIME)
    design = _doc(stem="design")
    seen = reachable_from(docs=(entry, design), links=(_mentions(src="brief", dst="design"),))
    assert design.doc_id in seen


def test_reachability_follows_more_than_one_hop() -> None:
    entry = _doc(stem="brief", read_when=ReadWhen.EVERY_TIME)
    middle = _doc(stem="design")
    far = _doc(stem="rollout")
    links = (_mentions(src="brief", dst="design"), _mentions(src="design", dst="rollout"))
    assert far.doc_id in reachable_from(docs=(entry, middle, far), links=links)


def test_a_document_nothing_links_to_is_never_reached() -> None:
    entry = _doc(stem="brief", read_when=ReadWhen.EVERY_TIME)
    stranded = _doc(stem="audit")
    codes = _codes(docs=(entry, stranded), links=())
    assert "unreachable_from_entry" in codes


def test_an_entry_of_a_reachable_log_is_reachable_through_its_parent() -> None:
    entry = _doc(stem="brief", read_when=ReadWhen.EVERY_TIME)
    log = _doc(stem="decisions")
    item = _doc(stem="decisions-one", parent=log.doc_id)
    links = (_mentions(src="brief", dst="decisions"),)
    assert item.doc_id in reachable_from(docs=(entry, log, item), links=links)


def test_reachability_is_not_reported_without_an_entry_point() -> None:
    docs = (_doc(stem="design"), _doc(stem="audit"))
    assert "unreachable_from_entry" not in _codes(docs=docs, links=())
