"""Drafting proposals from facts, deciding them, and applying accepted edits."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from spine.constants import (
    PROPOSAL_APPEND_HEADING,
    SHIPPED_LOG_FILE_NAME,
    SHIPPED_LOG_STEM,
    SPINE_HOME_ENV_VAR,
)
from spine.facts.model import Fact, FactKind, PullRequestState
from spine.model import Doc, DocKind, Project, ReadWhen
from spine.proposals import decide_proposal, generate_for_project
from spine.proposals.draft import apply_proposal, draft_from_drift, proposal_id_for
from spine.proposals.model import ProposalKind, ProposalState
from spine.proposals.store import ProposalStore

PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "brief.md").write_text("# Brief\n\nProse.\n", encoding="utf-8")
    return docs


def _project(*, docs_dir: Path) -> Project:
    return Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=docs_dir)


def _doc(*, stem: str, kind: DocKind = DocKind.BRIEF, body: str = "# B\n\nProse.") -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=kind,
        read_when=ReadWhen.EVERY_TIME,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
    )


def _merged(*, number: int, title: str = "did a thing") -> Fact:
    return Fact(
        fact_id=f"{PROJECT_SLUG}:pr:{number}",
        project_slug=PROJECT_SLUG,
        kind=FactKind.PULL_REQUEST,
        reference=f"#{number}",
        title=title,
        author="someone",
        occurred_at="2026-01-01T00:00:00Z",
        state=str(PullRequestState.MERGED),
    )


def test_merged_work_nobody_documented_becomes_a_proposal(corpus_dir: Path) -> None:
    drafted = draft_from_drift(
        project=_project(docs_dir=corpus_dir), docs=(_doc(stem="brief"),), facts=(_merged(number=11),)
    )
    assert len(drafted) == 1
    assert "#11" in drafted[0].body
    assert PROPOSAL_APPEND_HEADING in drafted[0].body


def test_already_documented_work_proposes_nothing(corpus_dir: Path) -> None:
    docs = (_doc(stem="brief", body="# B\n\nshipped in #11223"),)
    assert draft_from_drift(project=_project(docs_dir=corpus_dir), docs=docs, facts=(_merged(number=11223),)) == ()


def test_no_facts_propose_nothing(corpus_dir: Path) -> None:
    assert draft_from_drift(project=_project(docs_dir=corpus_dir), docs=(_doc(stem="brief"),), facts=()) == ()


def test_shipped_work_goes_to_the_shipped_log_not_the_brief(corpus_dir: Path) -> None:
    """The brief loads into every session; a growing list of pull requests would crowd it out."""
    drafted = draft_from_drift(
        project=_project(docs_dir=corpus_dir), docs=(_doc(stem="brief"),), facts=(_merged(number=11),)
    )
    assert drafted[0].doc_id == f"{PROJECT_SLUG}:{SHIPPED_LOG_STEM}"
    assert drafted[0].doc_path == SHIPPED_LOG_FILE_NAME


def test_a_corpus_with_no_brief_still_gets_a_shipped_log(corpus_dir: Path) -> None:
    docs = (_doc(stem="notes", kind=DocKind.AREA_DESIGN),)
    drafted = draft_from_drift(project=_project(docs_dir=corpus_dir), docs=docs, facts=(_merged(number=1),))
    assert drafted[0].doc_path == SHIPPED_LOG_FILE_NAME


def test_the_same_edit_gets_the_same_id() -> None:
    assert proposal_id_for(doc_id="a:b", body="x") == proposal_id_for(doc_id="a:b", body="x")


def test_a_different_edit_gets_a_different_id() -> None:
    assert proposal_id_for(doc_id="a:b", body="x") != proposal_id_for(doc_id="a:b", body="y")


def _queued(*, corpus_dir: Path):
    drafted = draft_from_drift(
        project=_project(docs_dir=corpus_dir), docs=(_doc(stem="brief"),), facts=(_merged(number=11),)
    )
    from spine.proposals.model import Proposal

    resolved = Proposal(
        **{
            **drafted[0].as_dict(),
            "doc_path": str(corpus_dir / "brief.md"),
            "kind": drafted[0].kind,
            "state": drafted[0].state,
        }
    )
    store = ProposalStore()
    store.add(proposals=(resolved,))
    return store, resolved


def test_drafting_the_same_proposal_twice_queues_it_once(corpus_dir: Path) -> None:
    store, proposal = _queued(corpus_dir=corpus_dir)
    assert store.add(proposals=(proposal,)) == 0
    assert len(store.pending(project_slug=PROJECT_SLUG)) == 1


def test_accepting_appends_to_the_document(corpus_dir: Path) -> None:
    store, proposal = _queued(corpus_dir=corpus_dir)
    succeeded, message = decide_proposal(proposal_id=proposal.proposal_id, accept=True)
    assert succeeded is True
    assert "#11" in (corpus_dir / "brief.md").read_text(encoding="utf-8")
    assert "applied" in message


def test_an_accepted_proposal_leaves_the_queue(corpus_dir: Path) -> None:
    store, proposal = _queued(corpus_dir=corpus_dir)
    decide_proposal(proposal_id=proposal.proposal_id, accept=True)
    assert store.pending(project_slug=PROJECT_SLUG) == ()


def test_deciding_twice_is_refused(corpus_dir: Path) -> None:
    _, proposal = _queued(corpus_dir=corpus_dir)
    decide_proposal(proposal_id=proposal.proposal_id, accept=True)
    succeeded, message = decide_proposal(proposal_id=proposal.proposal_id, accept=True)
    assert succeeded is False
    assert "already" in message


def test_rejecting_leaves_the_document_alone(corpus_dir: Path) -> None:
    _, proposal = _queued(corpus_dir=corpus_dir)
    before = (corpus_dir / "brief.md").read_text(encoding="utf-8")
    succeeded, _ = decide_proposal(proposal_id=proposal.proposal_id, accept=False)
    assert succeeded is True
    assert (corpus_dir / "brief.md").read_text(encoding="utf-8") == before


def test_deciding_an_unknown_proposal_fails_cleanly() -> None:
    succeeded, message = decide_proposal(proposal_id="nope", accept=True)
    assert succeeded is False
    assert "no proposal" in message


def test_applying_to_a_missing_file_fails_rather_than_raising(corpus_dir: Path) -> None:
    _, proposal = _queued(corpus_dir=corpus_dir)
    (corpus_dir / "brief.md").unlink()
    assert apply_proposal(proposal=proposal) is False


def test_applying_twice_keeps_one_heading(corpus_dir: Path) -> None:
    """A proposal drafted before an earlier one landed must not restate the section."""
    _, first = _queued(corpus_dir=corpus_dir)
    assert apply_proposal(proposal=first) is True
    second = replace(first, body=f"{PROPOSAL_APPEND_HEADING}\n\n- #99 \u2014 later work")
    assert apply_proposal(proposal=second) is True
    written = (corpus_dir / "brief.md").read_text(encoding="utf-8")
    assert written.count(PROPOSAL_APPEND_HEADING) == 1
    assert "- #99 \u2014 later work" in written


def test_reapplying_the_same_proposal_writes_nothing(corpus_dir: Path) -> None:
    _, proposal = _queued(corpus_dir=corpus_dir)
    assert apply_proposal(proposal=proposal) is True
    before = (corpus_dir / "brief.md").read_text(encoding="utf-8")
    assert apply_proposal(proposal=proposal) is False
    assert (corpus_dir / "brief.md").read_text(encoding="utf-8") == before


def test_appending_lands_under_the_heading_not_at_the_end(corpus_dir: Path) -> None:
    _, first = _queued(corpus_dir=corpus_dir)
    assert apply_proposal(proposal=first) is True
    brief = corpus_dir / "brief.md"
    brief.write_text(
        brief.read_text(encoding="utf-8") + "\n## Where the parts live\n\nA table.\n",
        encoding="utf-8",
    )
    second = replace(first, body=f"{PROPOSAL_APPEND_HEADING}\n\n- #99 \u2014 later work")
    assert apply_proposal(proposal=second) is True
    lines = brief.read_text(encoding="utf-8").splitlines()
    assert lines.index("- #99 \u2014 later work") < lines.index("## Where the parts live")


def test_cli_exposes_the_propose_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["propose", "list"])
    assert parsed.handler is not None


BRIEF_WITH_FRONTMATTER = "---\ntitle: Alpha\nkind: brief\nread_when: every_time\n---\n\n# Alpha\n\nProse.\n"


def _shipped_proposal(*, corpus_dir: Path, number: int = 11):
    drafted = draft_from_drift(
        project=_project(docs_dir=corpus_dir), docs=(_doc(stem="brief"),), facts=(_merged(number=number),)
    )
    return replace(drafted[0], doc_path=str(corpus_dir / drafted[0].doc_path))


def test_accepting_creates_the_shipped_log_as_a_looked_up_generated_doc(corpus_dir: Path) -> None:
    (corpus_dir / "brief.md").write_text(BRIEF_WITH_FRONTMATTER, encoding="utf-8")
    assert apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir)) is True
    written = (corpus_dir / SHIPPED_LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "kind: generated" in written
    assert "read_when: looked_up" in written
    assert "#11" in written
    assert "#11" not in (corpus_dir / "brief.md").read_text(encoding="utf-8")


def test_the_brief_links_the_shipped_log_once(corpus_dir: Path) -> None:
    brief = corpus_dir / "brief.md"
    brief.write_text(BRIEF_WITH_FRONTMATTER, encoding="utf-8")
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir, number=11))
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir, number=12))
    assert brief.read_text(encoding="utf-8").count(f"]({SHIPPED_LOG_FILE_NAME})") == 1


def test_a_document_that_only_mentions_brief_in_its_body_is_not_linked(corpus_dir: Path) -> None:
    notes = corpus_dir / "notes.md"
    notes.write_text("---\nkind: area_design\n---\n\nkind: brief is a word here.\n", encoding="utf-8")
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir))
    assert SHIPPED_LOG_FILE_NAME not in notes.read_text(encoding="utf-8")


def test_a_brief_named_like_an_entry_point_is_linked_without_frontmatter(corpus_dir: Path) -> None:
    brief = corpus_dir / "alpha-start-here.md"
    brief.write_text("# Alpha\n\nProse.\n", encoding="utf-8")
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir))
    assert f"]({SHIPPED_LOG_FILE_NAME})" in brief.read_text(encoding="utf-8")


def test_the_brief_link_is_retried_when_the_log_already_exists(corpus_dir: Path) -> None:
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir, number=11))
    brief = corpus_dir / "brief.md"
    brief.write_text(BRIEF_WITH_FRONTMATTER, encoding="utf-8")
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir, number=12))
    assert f"]({SHIPPED_LOG_FILE_NAME})" in brief.read_text(encoding="utf-8")


def test_the_shipped_log_is_titled_with_the_project_name(corpus_dir: Path) -> None:
    apply_proposal(proposal=_shipped_proposal(corpus_dir=corpus_dir), project_name="Alpha Project")
    assert "# Alpha Project" in (corpus_dir / SHIPPED_LOG_FILE_NAME).read_text(encoding="utf-8")


def _registered_project(*, corpus_dir: Path) -> Project:
    (corpus_dir / "brief.md").write_text(BRIEF_WITH_FRONTMATTER, encoding="utf-8")
    return _project(docs_dir=corpus_dir)


def test_a_newer_draft_supersedes_the_pending_one(corpus_dir: Path) -> None:
    from spine.facts.store import FactStore

    project = _registered_project(corpus_dir=corpus_dir)
    FactStore().record(facts=(_merged(number=11),))
    generate_for_project(project=project)
    FactStore().record(facts=(_merged(number=11), _merged(number=12)))
    generate_for_project(project=project)
    pending = ProposalStore().pending(project_slug=PROJECT_SLUG)
    assert len(pending) == 1
    assert "#12" in pending[0].body


def test_a_draft_seen_again_after_being_superseded_is_pending_again(corpus_dir: Path) -> None:
    from spine.facts.store import FactStore

    project = _registered_project(corpus_dir=corpus_dir)
    FactStore().record(facts=(_merged(number=11),))
    generate_for_project(project=project)
    first = ProposalStore().pending(project_slug=PROJECT_SLUG)[0]
    ProposalStore().supersede_others(project_slug=PROJECT_SLUG, kind=ProposalKind.APPEND, keep=())
    assert ProposalStore().pending(project_slug=PROJECT_SLUG) == ()
    generate_for_project(project=project)
    assert [proposal.proposal_id for proposal in ProposalStore().pending(project_slug=PROJECT_SLUG)] == [first.proposal_id]


def test_a_rejected_draft_stays_rejected_when_drafted_again(corpus_dir: Path) -> None:
    from spine.facts.store import FactStore

    project = _registered_project(corpus_dir=corpus_dir)
    FactStore().record(facts=(_merged(number=11),))
    generate_for_project(project=project)
    first = ProposalStore().pending(project_slug=PROJECT_SLUG)[0]
    decide_proposal(proposal_id=first.proposal_id, accept=False)
    generate_for_project(project=project)
    assert ProposalStore().pending(project_slug=PROJECT_SLUG) == ()
    assert ProposalStore().get(proposal_id=first.proposal_id).state is ProposalState.REJECTED
