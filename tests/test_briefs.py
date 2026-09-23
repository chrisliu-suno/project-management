"""The per-document brief: harvested from a start-here table, or the document's own opening."""

from __future__ import annotations

from pathlib import Path

from spine.context.render import render_brief_index, render_brief_line
from spine.docs.briefs import (
    check_is_metadata_line,
    get_briefs_from_body,
    get_document_stem_from_cell,
    get_fallback_brief_from_body,
    get_first_sentence,
)
from spine.docs.loader import FilesystemDocSource
from spine.model import DocKind, Project, ReadWhen

START_HERE_BODY = """
# Start here

## Read next, in this order

| Read | For |
|---|---|
| `glossary.md` | the vocabulary. Read it before anything else here |
| `code-map.md` | where the code lives and which file owns what |

## Procedure

| Read | When |
|---|---|
| `sop-migration.md` | centralizing one more authorization check |
"""


def test_a_table_row_becomes_the_brief_for_the_document_it_names() -> None:
    """The `| Read | For |` table is the stated purpose, one row per document."""
    briefs = get_briefs_from_body(body=START_HERE_BODY)
    assert briefs["glossary"] == "the vocabulary. Read it before anything else here"
    assert briefs["code-map"] == "where the code lives and which file owns what"


def test_every_table_in_the_document_contributes_not_just_the_first() -> None:
    """A start-here doc lists procedure documents under a second heading."""
    assert "sop-migration" in get_briefs_from_body(body=START_HERE_BODY)


def test_the_header_and_rule_rows_are_not_read_as_documents() -> None:
    """`| Read | For |` and `|---|---|` name no document."""
    briefs = get_briefs_from_body(body=START_HERE_BODY)
    assert set(briefs) == {"glossary", "code-map", "sop-migration"}


def test_the_first_row_wins_when_a_document_is_listed_twice() -> None:
    """A document introduced up front is often repeated under a narrower heading."""
    body = (
        "| `a.md` | the first statement |\n"
        "| `a.md` | a later, narrower one |\n"
    )
    assert get_briefs_from_body(body=body)["a"] == "the first statement"


def test_a_cell_naming_no_document_is_skipped() -> None:
    """A table of plain prose is not a document index."""
    assert get_briefs_from_body(body="| every clip | gets an audience |\n") == {}


def test_a_qualified_reference_still_resolves_to_the_document() -> None:
    """Cells qualify a name with a directory or a trailing parenthetical."""
    assert (
        get_document_stem_from_cell(cell="`studio_api/access/AGENTS.md` (in glockenspiel)")
        == "AGENTS"
    )
    assert get_document_stem_from_cell(cell="`matrix.html`") == "matrix"
    assert get_document_stem_from_cell(cell="the vocabulary") is None


def test_a_document_no_table_names_falls_back_to_its_opening_sentence() -> None:
    body = "# Tracker\n\nTracker, opened 2026-09-22. Source of truth for the work.\n"
    assert get_fallback_brief_from_body(body=body) == "Tracker, opened 2026-09-22."


def test_the_fallback_skips_header_fields_rather_than_describing_a_doc_by_its_owner() -> None:
    body = "# Plan\n\n**Owner:** Core Platform\nSource: a link\n\nThe access plane governs roles.\n"
    assert get_fallback_brief_from_body(body=body) == "The access plane governs roles."


def test_the_fallback_joins_a_wrapped_sentence_rather_than_cutting_it() -> None:
    body = "# Map\n\nWhere the access code lives and\nwhich file owns what. More detail.\n"
    assert (
        get_fallback_brief_from_body(body=body)
        == "Where the access code lives and which file owns what."
    )


def test_metadata_lines_are_recognised_in_both_spellings() -> None:
    assert check_is_metadata_line(line="**Owner:** Core Platform") is True
    assert check_is_metadata_line(line="Source: https://example.test") is True
    assert check_is_metadata_line(line="The engine decides every read.") is False


def test_a_decimal_does_not_end_a_sentence() -> None:
    assert get_first_sentence(text="Ships in v2.1 of the engine. Then more.") == (
        "Ships in v2.1 of the engine."
    )


def test_a_declared_brief_beats_a_harvested_one(tmp_path: Path) -> None:
    """Frontmatter is the document's own statement about itself."""
    (tmp_path / "start-here.md").write_text(
        "---\nkind: brief\n---\n\n| Read | For |\n|---|---|\n| `topic.md` | the harvested line |\n"
    )
    (tmp_path / "topic.md").write_text("---\nbrief: the declared line\n---\n\n# Topic\n")
    project = Project(slug="alpha", name="Alpha", docs_dir=tmp_path)

    docs = {doc.path.stem: doc for doc in FilesystemDocSource().load_all(project=project)}
    assert docs["topic"].brief == "the declared line"


def test_a_harvested_brief_beats_the_document_s_own_opening(tmp_path: Path) -> None:
    (tmp_path / "start-here.md").write_text(
        "---\nkind: brief\n---\n\n| Read | For |\n|---|---|\n| `topic.md` | the harvested line |\n"
    )
    (tmp_path / "topic.md").write_text("# Topic\n\nAn opening sentence. And another.\n")
    project = Project(slug="alpha", name="Alpha", docs_dir=tmp_path)

    docs = {doc.path.stem: doc for doc in FilesystemDocSource().load_all(project=project)}
    assert docs["topic"].brief == "the harvested line"


def test_only_brief_documents_are_scanned_for_tables(tmp_path: Path) -> None:
    """A table inside an ordinary document is data, not a document index."""
    (tmp_path / "report.md").write_text(
        "# Report\n\n| Read | For |\n|---|---|\n| `topic.md` | a claim in a report |\n"
    )
    (tmp_path / "topic.md").write_text("# Topic\n\nIts own opening.\n")
    project = Project(slug="alpha", name="Alpha", docs_dir=tmp_path)

    docs = {doc.path.stem: doc for doc in FilesystemDocSource().load_all(project=project)}
    assert docs["topic"].brief == "Its own opening."


def _doc(*, name: str, brief: str | None, project_slug: str = "alpha"):
    from spine.model import Doc

    return Doc(
        doc_id=f"{project_slug}:{Path(name).stem}",
        path=Path(f"/corpus/{name}"),
        kind=DocKind.AREA_DESIGN,
        read_when=ReadWhen.IN_AREA,
        title=Path(name).stem,
        body="",
        project_slug=project_slug,
        brief=brief,
    )


def test_the_index_lists_every_document_across_every_tied_project() -> None:
    """The point of the index is that no project has to win for context to load."""
    first = Project(slug="alpha", name="Alpha", docs_dir=Path("/docs/alpha"))
    second = Project(slug="beta", name="Beta", docs_dir=Path("/docs/beta"))
    rendered = render_brief_index(
        corpora=(
            (first, (_doc(name="one.md", brief="the first"),)),
            (second, (_doc(name="two.md", brief="the second", project_slug="beta"),)),
        )
    )
    assert "/docs/alpha/one.md" in rendered
    assert "/docs/beta/two.md" in rendered
    assert "the first" in rendered
    assert "the second" in rendered


def test_the_index_addresses_a_document_by_a_path_that_can_be_opened() -> None:
    """An agent reads the index to decide what to open, so the path has to be real."""
    project = Project(slug="alpha", name="Alpha", docs_dir=Path("/docs/alpha"))
    rendered = render_brief_index(corpora=((project, (_doc(name="one.md", brief="x"),)),))
    assert "`/docs/alpha/one.md`" in rendered


def test_a_document_with_no_brief_is_still_listed() -> None:
    """Dropping it would hide a document that exists."""
    assert render_brief_line(path="/docs/a.md", brief=None) == "- `/docs/a.md`"


def test_an_empty_corpus_renders_nothing() -> None:
    project = Project(slug="alpha", name="Alpha", docs_dir=Path("/docs/alpha"))
    assert render_brief_index(corpora=((project, ()),)) == ""
    assert render_brief_index(corpora=()) == ""
