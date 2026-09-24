"""Renders the whole docs corpus as one page a person can read without a tool.

The session brief index addresses documents by absolute path because an agent opens them; this
addresses them relative to the page, because a human reads them on GitHub.
"""

from __future__ import annotations

from pathlib import Path

from ..constants import (
    README_DOC_LINE_TEMPLATE,
    README_GENERATED_NOTICE,
    README_HEADER,
    README_PROJECT_HEADING_PREFIX,
    README_SECTION_SEPARATOR,
    README_UNBRIEFED_LINE_TEMPLATE,
)
from ..model import Doc, Project

Corpus = tuple[Project, tuple[Doc, ...]]


def render_docs_readme(*, corpora: tuple[Corpus, ...], root: Path) -> str:
    """One section per project, one line per document, addressed relative to `root`."""
    sections = [
        render_project_section(project=project, docs=docs, root=root)
        for project, docs in sorted(corpora, key=lambda pair: pair[0].name)
        if docs
    ]
    return (
        README_SECTION_SEPARATOR.join((README_HEADER, README_GENERATED_NOTICE, *sections)) + "\n"
    )


def render_project_section(*, project: Project, docs: tuple[Doc, ...], root: Path) -> str:
    """A project's heading, its own brief where it has one, and its document lines."""
    lines = [f"{README_PROJECT_HEADING_PREFIX}{project.name}", ""]
    lines.extend(
        render_document_line(path=get_relative_path(path=doc.path, root=root), brief=doc.brief)
        for doc in sorted(docs, key=lambda entry: entry.path.name)
        if not doc.is_entry
    )
    return "\n".join(lines)


def render_document_line(*, path: str, brief: str | None) -> str:
    """A linked document and the purpose it states, or the link alone when it states none."""
    if not brief:
        return README_UNBRIEFED_LINE_TEMPLATE.format(path=path, name=Path(path).name)
    return README_DOC_LINE_TEMPLATE.format(path=path, name=Path(path).name, brief=brief)


def get_relative_path(*, path: Path, root: Path) -> str:
    """The document's path from the page, falling back to absolute when it sits outside."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
