"""Drafting proposals from facts, deciding them, and applying accepted edits."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import PROPOSAL_APPEND_HEADING, SPINE_HOME_ENV_VAR
from spine.facts.model import Fact, FactKind, PullRequestState
from spine.model import Doc, DocKind, Project, ReadWhen
from spine.proposals import decide_proposal
from spine.proposals.draft import apply_proposal, draft_from_drift, proposal_id_for
from spine.proposals.model import ProposalState
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


def test_a_corpus_with_no_suitable_target_proposes_nothing(corpus_dir: Path) -> None:
    docs = (_doc(stem="notes", kind=DocKind.AREA_DESIGN),)
    assert draft_from_drift(project=_project(docs_dir=corpus_dir), docs=docs, facts=(_merged(number=1),)) == ()


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


def test_cli_exposes_the_propose_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["propose", "list"])
    assert parsed.handler is not None
