"""Corpus health findings and snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import EVERY_TIME_RESERVED_LINES, SPINE_HOME_ENV_VAR
from spine.dashboard import Severity
from spine.health.findings import (
    all_findings,
    brief_findings,
    duplicate_findings,
    every_time_findings,
    orphan_findings,
    unclassified_findings,
)
from spine.health.snapshot import build_snapshot
from spine.model import Doc, DocKind, Link, LinkType, Project, ReadWhen

PROJECT_SLUG = "alpha"
FIXTURE_CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "corpus-alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _doc(
    *,
    stem: str,
    kind: DocKind = DocKind.AREA_DESIGN,
    read_when: ReadWhen = ReadWhen.IN_AREA,
    title: str | None = None,
    body: str = "# Title\n\nProse.",
    parent: str | None = None,
) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=kind,
        read_when=read_when,
        title=title if title is not None else stem,
        body=body,
        project_slug=PROJECT_SLUG,
        parent_doc_id=parent,
    )


def _codes(findings) -> list[str]:
    return [finding.code for finding in findings]


def test_one_brief_reads_as_ok() -> None:
    docs = (_doc(stem="brief", kind=DocKind.BRIEF, read_when=ReadWhen.EVERY_TIME),)
    found = brief_findings(docs=docs)
    assert _codes(found) == ["brief"]
    assert found[0].severity is Severity.OK


def test_no_brief_is_a_problem() -> None:
    found = brief_findings(docs=(_doc(stem="design"),))
    assert _codes(found) == ["no_brief"]
    assert found[0].severity is Severity.PROBLEM


def test_several_briefs_are_a_problem() -> None:
    docs = (
        _doc(stem="one", kind=DocKind.BRIEF, read_when=ReadWhen.EVERY_TIME),
        _doc(stem="two", kind=DocKind.BRIEF, read_when=ReadWhen.EVERY_TIME),
    )
    found = brief_findings(docs=docs)
    assert _codes(found) == ["many_briefs"]
    assert len(found[0].doc_ids) == 2


def test_an_oversized_every_time_group_is_a_problem() -> None:
    big = "x\n" * (EVERY_TIME_RESERVED_LINES + 10)
    docs = (_doc(stem="huge", read_when=ReadWhen.EVERY_TIME, body=big),)
    assert _codes(every_time_findings(docs=docs)) == ["every_time_over_reserve"]


def test_a_small_every_time_group_reports_nothing() -> None:
    docs = (_doc(stem="small", read_when=ReadWhen.EVERY_TIME),)
    assert every_time_findings(docs=docs) == ()


def test_orphans_are_documents_nothing_points_at() -> None:
    docs = (_doc(stem="linked"), _doc(stem="lonely"))
    links = (
        Link(
            src_id=f"{PROJECT_SLUG}:lonely",
            dst_id=f"{PROJECT_SLUG}:linked",
            link_type=LinkType.MENTIONS,
        ),
    )
    found = orphan_findings(docs=docs, links=links)
    assert found[0].doc_ids == (f"{PROJECT_SLUG}:lonely",)


def test_log_entries_are_never_orphans() -> None:
    entry = _doc(stem="decisions", parent=f"{PROJECT_SLUG}:decisions")
    assert orphan_findings(docs=(entry,), links=()) == ()


def test_agent_suffixed_variants_cluster_as_duplicates() -> None:
    docs = (
        _doc(stem="rbac-access-plane-plan", title="RBAC plan"),
        _doc(stem="rbac-access-plane-plan--codex", title="Access plane, codex draft"),
        _doc(stem="rbac-access-plane-plan--grok", title="Something else entirely"),
    )
    found = duplicate_findings(docs=docs)
    assert len(found) == 1
    assert len(found[0].doc_ids) == 3


def test_unrelated_documents_do_not_cluster() -> None:
    docs = (_doc(stem="caching", title="Caching"), _doc(stem="rollout", title="Rollout ramp"))
    assert duplicate_findings(docs=docs) == ()


def test_unclassified_documents_are_flagged() -> None:
    docs = (_doc(stem="mystery", kind=DocKind.GENERATED, read_when=ReadWhen.LOOKED_UP),)
    assert _codes(unclassified_findings(docs=docs)) == ["unclassified"]


def test_all_findings_leads_with_the_brief() -> None:
    docs = (_doc(stem="design"),)
    assert all_findings(docs=docs, links=())[0].code == "no_brief"


def test_a_missing_docs_dir_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    project = Project(slug="gone", name="Gone", docs_dir=tmp_path / "nope")
    snapshot = build_snapshot(project=project)
    assert snapshot.worst_severity is Severity.PROBLEM
    assert _codes(snapshot.findings) == ["missing_docs_dir"]


def test_the_fixture_corpus_snapshots_cleanly() -> None:
    project = Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=FIXTURE_CORPUS_DIR)
    snapshot = build_snapshot(project=project)
    assert snapshot.doc_count == len(list(FIXTURE_CORPUS_DIR.glob("*.md")))
    assert snapshot.entry_count > 0
    assert snapshot.link_count > 0
    assert snapshot.kind_counts["brief"] == 1


def test_worst_severity_reflects_the_findings() -> None:
    project = Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=FIXTURE_CORPUS_DIR)
    snapshot = build_snapshot(project=project)
    assert snapshot.worst_severity in {Severity.OK, Severity.WARN, Severity.PROBLEM}


def test_cli_exposes_the_health_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["health", "check"])
    assert parsed.handler is not None


SHARED_BODY = "# Audit\n\n" + "".join(f"finding {n} holds\n" for n in range(20))
DIVERGENT_BODY = "# Audit\n\n" + "".join(f"different point {n}\n" for n in range(20))


def test_documents_sharing_a_title_and_their_content_are_duplicates() -> None:
    from spine.health.findings import duplicate_findings

    docs = (
        _doc(stem="a", title="Clip access audit", body=SHARED_BODY),
        _doc(stem="b", title="Clip access audit", body=SHARED_BODY),
    )
    codes = [finding.code for finding in duplicate_findings(docs=docs)]
    assert codes == ["duplicate_titles"]


def test_documents_sharing_only_a_title_are_not_duplicates() -> None:
    from spine.health.findings import duplicate_findings

    docs = (
        _doc(stem="a", title="Clip access audit", body=SHARED_BODY),
        _doc(stem="b", title="Clip access audit", body=DIVERGENT_BODY),
    )
    found = duplicate_findings(docs=docs)
    assert [finding.code for finding in found] == ["same_title"]
    assert "Retitle" in found[0].detail


def test_a_same_title_finding_does_not_advise_deletion() -> None:
    from spine.health.findings import duplicate_findings

    docs = (
        _doc(stem="a", title="Same", body=SHARED_BODY),
        _doc(stem="b", title="Same", body=DIVERGENT_BODY),
    )
    assert "delete" not in duplicate_findings(docs=docs)[0].detail.lower()


def test_overlap_of_identical_bodies_is_total() -> None:
    from spine.health.findings import body_overlap

    left = _doc(stem="a", body=SHARED_BODY)
    assert body_overlap(left=left, right=_doc(stem="b", body=SHARED_BODY)) == 1.0


def test_overlap_with_an_empty_body_is_zero() -> None:
    from spine.health.findings import body_overlap

    assert body_overlap(left=_doc(stem="a", body=""), right=_doc(stem="b")) == 0.0


def test_a_short_document_inside_a_long_one_counts_as_overlapping() -> None:
    from spine.health.findings import body_overlap

    short = _doc(stem="a", body="finding 1 holds\nfinding 2 holds")
    assert body_overlap(left=short, right=_doc(stem="b", body=SHARED_BODY)) == 1.0
