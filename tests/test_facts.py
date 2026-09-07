"""Observed facts, their store, and the drift they expose."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.dashboard import Severity
from spine.facts.drift import (
    documented_but_unmerged,
    drift_findings,
    merged_but_undocumented,
    referenced_pull_requests,
)
from spine.facts.model import Fact, FactKind, PullRequestState
from spine.facts.observe import is_relevant
from spine.facts.store import FactStore
from spine.model import Doc, DocKind, Project, ReadWhen

PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _doc(*, stem: str, body: str) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=DocKind.AREA_DESIGN,
        read_when=ReadWhen.IN_AREA,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
    )


def _pr(*, number: int, state: PullRequestState = PullRequestState.MERGED) -> Fact:
    return Fact(
        fact_id=f"{PROJECT_SLUG}:pr:{number}",
        project_slug=PROJECT_SLUG,
        kind=FactKind.PULL_REQUEST,
        reference=f"#{number}",
        title=f"pr {number}",
        author="someone",
        occurred_at="2026-01-01T00:00:00Z",
        state=str(state),
    )


def _project(*, prefixes: tuple[str, ...] = ()) -> Project:
    return Project(
        slug=PROJECT_SLUG,
        name="Alpha Access",
        docs_dir=Path("/tmp/alpha"),
        branch_prefixes=prefixes,
    )


def test_pull_request_numbers_are_read_out_of_prose() -> None:
    docs = (_doc(stem="notes", body="Fixed in #12345 and #67890."),)
    assert referenced_pull_requests(docs=docs) == {f"{PROJECT_SLUG}:notes": ("12345", "67890")}


def test_short_numbers_are_not_pull_requests() -> None:
    assert referenced_pull_requests(docs=(_doc(stem="n", body="rule #3 applies"),)) == {}


def test_a_merged_pull_request_nobody_documented_is_drift() -> None:
    found = merged_but_undocumented(docs=(_doc(stem="n", body="nothing"),), facts=(_pr(number=99),))
    assert found[0].code == "merged_undocumented"
    assert found[0].severity is Severity.WARN


def test_a_documented_merge_is_not_drift() -> None:
    docs = (_doc(stem="n", body="shipped in #99123"),)
    assert merged_but_undocumented(docs=docs, facts=(_pr(number=99123),)) == ()


def test_citing_a_closed_pull_request_is_drift() -> None:
    docs = (_doc(stem="n", body="see #4242"),)
    facts = (_pr(number=4242, state=PullRequestState.CLOSED),)
    assert documented_but_unmerged(docs=docs, facts=facts)[0].code == "cites_closed_pr"


def test_citing_an_open_pull_request_is_not_drift() -> None:
    docs = (_doc(stem="n", body="see #4242"),)
    facts = (_pr(number=4242, state=PullRequestState.OPEN),)
    assert documented_but_unmerged(docs=docs, facts=facts) == ()


def test_no_facts_means_no_drift_claims() -> None:
    assert drift_findings(docs=(_doc(stem="n", body="see #4242"),), facts=()) == ()


def test_a_branch_prefix_makes_a_pull_request_relevant() -> None:
    entry = {"headRefName": "chris/feat/access-thing", "title": "unrelated words"}
    assert is_relevant(entry=entry, project=_project(prefixes=("chris/feat/access",))) is True


def test_a_title_term_makes_a_pull_request_relevant() -> None:
    entry = {"headRefName": "someone/else", "title": "tighten access checks"}
    assert is_relevant(entry=entry, project=_project()) is True


def test_an_unrelated_pull_request_is_filtered_out() -> None:
    entry = {"headRefName": "someone/else", "title": "bump lockfile"}
    assert is_relevant(entry=entry, project=_project()) is False


def test_facts_round_trip_through_the_store() -> None:
    store = FactStore()
    assert store.record(facts=(_pr(number=1), _pr(number=2))) == 2
    assert {fact.reference for fact in store.for_project(project_slug=PROJECT_SLUG)} == {"#1", "#2"}


def test_re_observing_the_same_fact_does_not_duplicate_it() -> None:
    store = FactStore()
    store.record(facts=(_pr(number=1),))
    store.record(facts=(_pr(number=1),))
    assert store.count(project_slug=PROJECT_SLUG) == 1


def test_recording_nothing_writes_nothing() -> None:
    assert FactStore().record(facts=()) == 0


def test_cli_exposes_the_facts_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["facts", "drift", "--project", PROJECT_SLUG])
    assert parsed.handler is not None
