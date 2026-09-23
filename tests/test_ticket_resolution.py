"""A ticket key resolves a checkout that repo and branch signals leave tied."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from spine.index.store import SqliteGraphStore
from spine.model import Doc, DocKind, Project, ReadWhen
from spine.registry.resolve import SignalResolver, get_ticket_prefixes_from_text

REPO = "suno-ai/glockenspiel"

PERMISSIONS_V2 = Project(
    slug="permissions-v2",
    name="Permissions v2",
    docs_dir=Path("/docs/permissionsv2"),
    repos=(REPO,),
    branch_prefixes=("chris/feat/access",),
    ticket_prefixes=("COP",),
)
ACCESS_ENGINE = Project(
    slug="access-engine",
    name="Access Engine Refactor",
    docs_dir=Path("/docs/access-engine"),
    repos=(REPO,),
    ticket_prefixes=("EA",),
)


class _Registry:
    """Minimal ProjectRegistry holding the two projects that share a repo and a vocabulary."""

    def all_projects(self) -> tuple[Project, ...]:
        return (PERMISSIONS_V2, ACCESS_ENGINE)


def _resolve(*, task: str):
    return SignalResolver(registry=_Registry()).resolve(
        cwd=Path("/Users/someone/dev/glockenspiel"), repo=REPO, opening_prompt=task
    )


def test_a_ticket_key_picks_the_project_that_owns_it() -> None:
    """`EA-170` and `COP-412` are the only thing that separates these two."""
    assert _resolve(task="finish the EA-170 restructure")[0].project.slug == "access-engine"
    assert _resolve(task="fix COP-412 clip access")[0].project.slug == "permissions-v2"


def test_the_word_access_alone_still_ties() -> None:
    """A shared word must not pick a winner; that was the mis-routing this guards."""
    matches = _resolve(task="some access work")
    assert matches[0].confidence == matches[1].confidence


def test_a_branch_named_for_the_other_project_does_not_win_on_the_shared_word() -> None:
    """`chris/feat/access-engine-parity` must not resolve to permissions-v2 by prefix."""
    matches = SignalResolver(registry=_Registry()).resolve(
        cwd=Path("/Users/someone/dev/glockenspiel"),
        repo=REPO,
        branch="chris/feat/access-engine-parity",
        opening_prompt="EA-170 parity",
    )
    assert matches[0].project.slug == "access-engine"


def test_the_ticket_signal_names_itself_in_the_evidence() -> None:
    assert "ticket EA-" in _resolve(task="EA-170")[0].evidence


def test_ticket_keys_are_read_out_of_prose() -> None:
    assert get_ticket_prefixes_from_text(text="see COP-412 and ea-9") == ("COP",)
    assert get_ticket_prefixes_from_text(text="EA-170 blocks COP-1") == ("EA", "COP")
    assert get_ticket_prefixes_from_text(text="no keys here") == ()


def test_a_store_built_before_the_brief_column_gains_it(tmp_path: Path) -> None:
    """Every schema statement is CREATE TABLE IF NOT EXISTS, so an old store never changes shape."""
    db_path = tmp_path / "graph.sqlite3"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE docs (project_slug TEXT NOT NULL, doc_id TEXT NOT NULL, path TEXT NOT NULL,"
        " kind TEXT NOT NULL, read_when TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,"
        " area TEXT, lifecycle TEXT, frontmatter TEXT NOT NULL, is_generated INTEGER NOT NULL,"
        " parent_doc_id TEXT, PRIMARY KEY (project_slug, doc_id))"
    )
    legacy.commit()
    legacy.close()

    store = SqliteGraphStore(db_path=db_path)
    store.replace_project(
        project_slug="alpha",
        docs=(
            Doc(
                doc_id="alpha:one",
                path=Path("/docs/alpha/one.md"),
                kind=DocKind.AREA_DESIGN,
                read_when=ReadWhen.IN_AREA,
                title="One",
                body="",
                project_slug="alpha",
                brief="the stated purpose",
            ),
        ),
        links=(),
    )
    assert store.docs_for_project(project_slug="alpha")[0].brief == "the stated purpose"
