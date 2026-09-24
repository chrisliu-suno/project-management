"""The generated one-page index of the whole corpus."""

from __future__ import annotations

from pathlib import Path

from spine.docs.readme import get_relative_path, render_docs_readme, render_document_line
from spine.model import Doc, DocKind, Project, ReadWhen

ROOT = Path("/corpus")


def _doc(*, name: str, brief: str | None, directory: str = "alpha") -> Doc:
    return Doc(
        doc_id=f"{directory}:{Path(name).stem}",
        path=ROOT / directory / name,
        kind=DocKind.AREA_DESIGN,
        read_when=ReadWhen.IN_AREA,
        title=Path(name).stem,
        body="",
        project_slug=directory,
        brief=brief,
    )


def _project(*, slug: str, name: str) -> Project:
    return Project(slug=slug, name=name, docs_dir=ROOT / slug)


def test_a_document_is_linked_relative_to_the_page() -> None:
    """The page is read on GitHub, so an absolute path would not resolve."""
    page = render_docs_readme(
        corpora=((_project(slug="alpha", name="Alpha"), (_doc(name="one.md", brief="the first"),)),),
        root=ROOT,
    )
    assert "[`one.md`](alpha/one.md) — the first" in page


def test_projects_are_ordered_by_name_not_slug() -> None:
    """The reader scans headings, and the heading shows the name."""
    page = render_docs_readme(
        corpora=(
            (_project(slug="zulu", name="Alpha"), (_doc(name="z.md", brief="z", directory="zulu"),)),
            (_project(slug="alpha", name="Zulu"), (_doc(name="a.md", brief="a"),)),
        ),
        root=ROOT,
    )
    assert page.index("## Alpha") < page.index("## Zulu")


def test_a_project_with_no_documents_gets_no_heading() -> None:
    page = render_docs_readme(corpora=((_project(slug="alpha", name="Alpha"), ()),), root=ROOT)
    assert "## Alpha" not in page


def test_a_document_with_no_brief_is_still_linked() -> None:
    assert render_document_line(path="alpha/one.md", brief=None) == "- [`one.md`](alpha/one.md)"


def test_a_document_outside_the_root_keeps_its_absolute_path() -> None:
    assert get_relative_path(path=Path("/elsewhere/a.md"), root=ROOT) == "/elsewhere/a.md"
