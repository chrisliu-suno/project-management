"""Observed facts, their store, and the drift they expose."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest

from spine.constants import CLOSED_PR_ACKNOWLEDGED_WINDOW, FACTS_AUTHOR_PR_LIMIT, SPINE_HOME_ENV_VAR
from spine.dashboard import Severity
from spine.facts import observe as observe_module
from spine.facts.drift import (
    documented_but_unmerged,
    drift_findings,
    merged_but_undocumented,
    referenced_pull_requests,
)
from spine.facts.model import Fact, FactKind, PullRequestState
from spine.facts.observe import is_relevant, observe_commits, observe_pull_requests
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


def test_a_closed_pull_request_cited_as_closed_is_not_drift() -> None:
    docs = (_doc(stem="n", body="#4242 was closed and reopened as #4343."),)
    facts = (_pr(number=4242, state=PullRequestState.CLOSED),)
    assert documented_but_unmerged(docs=docs, facts=facts) == ()


def test_stating_the_fate_once_covers_the_other_mentions_in_that_document() -> None:
    docs = (_doc(stem="n", body="#4242 was superseded by #4343.\n\nWhat carried over from #4242 is below."),)
    facts = (_pr(number=4242, state=PullRequestState.CLOSED),)
    assert documented_but_unmerged(docs=docs, facts=facts) == ()


def test_stating_the_fate_in_one_document_does_not_cover_another() -> None:
    docs = (_doc(stem="a", body="#4242 was closed."), _doc(stem="b", body="The work lands in #4242."))
    facts = (_pr(number=4242, state=PullRequestState.CLOSED),)
    assert documented_but_unmerged(docs=docs, facts=facts)[0].code == "cites_closed_pr"


def test_a_release_train_from_main_belongs_to_no_project() -> None:
    """Merging main into a deploy branch touches every project's files."""
    entry = {"headRefName": "main", "baseRefName": "ui-prod", "title": "Deploy UI: merge main into ui-prod"}
    assert is_relevant(entry=entry, project=_project(prefixes=("chris/feat/access",))) is False


def test_a_stacked_pull_request_into_a_feature_branch_is_still_judged() -> None:
    entry = {"headRefName": "chris/feat/access-thing", "baseRefName": "chris/feat/access-base", "title": "x"}
    assert is_relevant(entry=entry, project=_project(prefixes=("chris/feat/access",))) is True


def test_an_unrelated_acknowledgment_far_along_the_line_does_not_hide_a_citation() -> None:
    padding = "x" * (CLOSED_PR_ACKNOWLEDGED_WINDOW + 20)
    docs = (_doc(stem="n", body=f"Work continues in #4242. {padding} This supersedes the old plan."),)
    facts = (_pr(number=4242, state=PullRequestState.CLOSED),)
    assert documented_but_unmerged(docs=docs, facts=facts)[0].code == "cites_closed_pr"


def test_unmerged_does_not_count_as_saying_a_pull_request_closed() -> None:
    docs = (_doc(stem="n", body="#4242 is open and unmerged."),)
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


def test_a_conventional_commit_type_is_not_a_project_term() -> None:
    engine = Project(
        slug="access-engine",
        name="Access Engine Refactor",
        docs_dir=Path("/tmp/access-engine"),
    )
    entry = {"headRefName": "someone/else", "title": "refactor: run hydration without a prefilter"}
    assert is_relevant(entry=entry, project=engine) is False


def _engine_with_code_paths() -> Project:
    return Project(
        slug="access-engine",
        name="Access Engine Refactor",
        docs_dir=Path("/tmp/access-engine"),
        code_path_globs=("studio_api/studio_api/access/*",),
    )


def test_a_declared_code_path_decides_relevance_without_the_title() -> None:
    entry = {
        "title": "chore: unrelated words",
        "files": [{"path": "studio_api/studio_api/access/entities/clip/rules.py"}],
    }
    assert is_relevant(entry=entry, project=_engine_with_code_paths()) is True


def test_a_matching_title_cannot_rescue_a_pull_request_outside_the_code_paths() -> None:
    entry = {
        "title": "refactor: rework the access engine",
        "files": [{"path": "studio_api/studio_api/unified_feed/offline/metrics.py"}],
    }
    assert is_relevant(entry=entry, project=_engine_with_code_paths()) is False


def test_a_pull_request_with_no_file_list_is_not_claimed_by_a_code_path() -> None:
    entry = {"title": "refactor: rework the access engine"}
    assert is_relevant(entry=entry, project=_engine_with_code_paths()) is False


def test_a_branch_prefix_still_wins_over_the_code_paths() -> None:
    engine = Project(
        slug="access-engine",
        name="Access Engine Refactor",
        docs_dir=Path("/tmp/access-engine"),
        branch_prefixes=("chris/refactor/access",),
        code_path_globs=("studio_api/studio_api/access/*",),
    )
    entry = {
        "headRefName": "chris/refactor/access-loading",
        "title": "unrelated",
        "files": [{"path": "docs/notes.md"}],
    }
    assert is_relevant(entry=entry, project=engine) is True


def test_a_project_with_no_declared_paths_observes_no_commits(tmp_path: Path) -> None:
    project = Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=tmp_path)
    assert observe_commits(project=project, repo_dir=tmp_path, branch="HEAD") == ()


def test_commits_are_limited_to_the_declared_paths(tmp_path: Path) -> None:
    run = partial(subprocess.run, cwd=tmp_path, check=True, capture_output=True)
    run(["git", "init", "--quiet"])
    run(["git", "config", "user.email", "spine@example.com"])
    run(["git", "config", "user.name", "Spine"])
    (tmp_path / "mine.py").write_text("in scope\n", encoding="utf-8")
    run(["git", "add", "mine.py"])
    run(["git", "commit", "--quiet", "-m", "touch the declared path"])
    (tmp_path / "theirs.py").write_text("out of scope\n", encoding="utf-8")
    run(["git", "add", "theirs.py"])
    run(["git", "commit", "--quiet", "-m", "touch another path"])

    project = Project(
        slug=PROJECT_SLUG, name="Alpha", docs_dir=tmp_path, code_path_globs=("mine.py",)
    )
    facts = observe_commits(project=project, repo_dir=tmp_path, branch="HEAD")
    assert [fact.title for fact in facts] == ["touch the declared path"]


@pytest.fixture(autouse=True)
def forget_cached_queries() -> Iterator[None]:
    """Stop one test's fake pull-request list from answering the next one's query."""
    observe_module._cached_pull_requests.cache_clear()
    yield
    observe_module._cached_pull_requests.cache_clear()


def _record_queries(
    *, monkeypatch: pytest.MonkeyPatch, by_author: dict[str, list[dict]]
) -> list[tuple[str, ...]]:
    issued: list[tuple[str, ...]] = []

    def fake_run(*, command: tuple[str, ...], cwd: Path | None = None) -> str:
        issued.append(command)
        author = command[command.index("--author") + 1] if "--author" in command else None
        return json.dumps(by_author.get(author, []))

    monkeypatch.setattr(observe_module, "_run", fake_run)
    return issued


def _with_authors(*, authors: tuple[str, ...]) -> Project:
    return Project(
        slug=PROJECT_SLUG,
        name="Alpha",
        docs_dir=Path("/tmp/alpha"),
        repos=("owner/repo",),
        authors=authors,
        code_path_globs=("src/*",),
    )


def _entry(*, number: int) -> dict:
    return {
        "number": number,
        "title": f"change {number}",
        "author": {"login": "someone"},
        "state": "MERGED",
        "mergedAt": "2026-09-01T00:00:00Z",
        "files": [{"path": "src/thing.py"}],
    }


def test_each_declared_author_gets_their_own_query(monkeypatch: pytest.MonkeyPatch) -> None:
    issued = _record_queries(
        monkeypatch=monkeypatch,
        by_author={"ada": [_entry(number=1)], "grace": [_entry(number=2)]},
    )
    facts = observe_pull_requests(project=_with_authors(authors=("ada", "grace")))
    assert sorted(fact.reference for fact in facts) == ["#1", "#2"]
    assert [command[command.index("--author") + 1] for command in issued] == ["ada", "grace"]
    assert all(str(FACTS_AUTHOR_PR_LIMIT) in command for command in issued)


def test_a_pull_request_returned_for_two_authors_is_recorded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = _entry(number=7)
    _record_queries(monkeypatch=monkeypatch, by_author={"ada": [shared], "grace": [shared]})
    facts = observe_pull_requests(project=_with_authors(authors=("ada", "grace")))
    assert [fact.reference for fact in facts] == ["#7"]


def test_two_projects_on_one_repository_share_a_query(monkeypatch: pytest.MonkeyPatch) -> None:
    issued = _record_queries(monkeypatch=monkeypatch, by_author={"ada": [_entry(number=3)]})
    first = _with_authors(authors=("ada",))
    second = Project(
        slug="beta",
        name="Beta",
        docs_dir=Path("/tmp/beta"),
        repos=("owner/repo",),
        authors=("ada",),
        code_path_globs=("src/*",),
    )
    observe_pull_requests(project=first)
    observe_pull_requests(project=second)
    assert len(issued) == 1


def test_a_project_with_no_declared_authors_asks_once_without_a_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = _record_queries(monkeypatch=monkeypatch, by_author={None: [_entry(number=4)]})
    project = Project(
        slug=PROJECT_SLUG,
        name="Alpha",
        docs_dir=Path("/tmp/alpha"),
        repos=("owner/repo",),
        code_path_globs=("src/*",),
    )
    assert [fact.reference for fact in observe_pull_requests(project=project)] == ["#4"]
    assert len(issued) == 1
    assert "--author" not in issued[0]


def test_declared_title_terms_replace_the_terms_taken_from_the_name() -> None:
    rbac = Project(
        slug="rbac",
        name="RBAC Access Plane",
        docs_dir=Path("/tmp/rbac"),
        title_terms=("rbac",),
    )
    assert is_relevant(entry={"title": "check workspace access at submit"}, project=rbac) is False
    assert is_relevant(entry={"title": "rbac role assignment"}, project=rbac) is True


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


def test_replacing_a_kind_drops_facts_the_filter_no_longer_claims() -> None:
    store = FactStore()
    store.record(facts=(_pr(number=1), _pr(number=2), _pr(number=3)))
    store.replace_kind(
        project_slug=PROJECT_SLUG, kind=FactKind.PULL_REQUEST, facts=(_pr(number=2),)
    )
    assert {f.reference for f in store.for_project(project_slug=PROJECT_SLUG)} == {"#2"}


def test_replacing_one_kind_leaves_the_other_alone() -> None:
    store = FactStore()
    commit = Fact(
        fact_id=f"{PROJECT_SLUG}:commit:abc",
        project_slug=PROJECT_SLUG,
        kind=FactKind.COMMIT,
        reference="abc",
        title="a commit",
        author="someone",
        occurred_at="2026-01-01T00:00:00Z",
    )
    store.record(facts=(commit, _pr(number=1)))
    store.replace_kind(project_slug=PROJECT_SLUG, kind=FactKind.PULL_REQUEST, facts=())
    assert {f.reference for f in store.for_project(project_slug=PROJECT_SLUG)} == {"abc"}


def test_replacing_leaves_other_projects_alone() -> None:
    store = FactStore()
    store.record(facts=(_pr(number=1),))
    other = Fact(
        fact_id="beta:pr:9",
        project_slug="beta",
        kind=FactKind.PULL_REQUEST,
        reference="#9",
        title="theirs",
        author="someone",
        occurred_at="2026-01-01T00:00:00Z",
    )
    store.record(facts=(other,))
    store.replace_kind(project_slug=PROJECT_SLUG, kind=FactKind.PULL_REQUEST, facts=())
    assert len(store.for_project(project_slug="beta")) == 1
