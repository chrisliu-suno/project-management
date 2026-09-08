"""Assembles the per-project view the dashboard renders."""

from __future__ import annotations

from collections import Counter

from ..dashboard import Finding, ProjectSnapshot, Severity
from ..index import build_links, load_corpus
from ..model import Doc, Project
from ..ports import ProjectRegistry
from .findings import all_findings

MISSING_DIR_CODE = "missing_docs_dir"


def _counts_by(*, docs: tuple[Doc, ...], attribute: str) -> dict[str, int]:
    return dict(
        Counter(str(getattr(doc, attribute)) for doc in docs if not doc.is_entry).most_common()
    )


def _missing_dir_snapshot(*, project: Project) -> ProjectSnapshot:
    return ProjectSnapshot(
        slug=project.slug,
        name=project.name,
        docs_dir=str(project.docs_dir),
        doc_count=0,
        entry_count=0,
        link_count=0,
        total_lines=0,
        findings=(
            Finding(
                code=MISSING_DIR_CODE,
                severity=Severity.PROBLEM,
                headline="Docs directory is missing",
                detail=f"Nothing found at {project.docs_dir}.",
            ),
        ),
    )


def _drift(*, project: Project) -> tuple[Finding, ...]:
    """Drift findings, or nothing when facts have not been observed yet."""
    try:
        from ..facts import drift_for_project

        return drift_for_project(project=project)
    except Exception:
        return ()


def _plan_summary(*, docs, project: Project) -> dict[str, object]:
    """Where the project stands, for the dashboard card."""
    from ..plan import open_questions_across, primary_plan

    state = primary_plan(docs=docs, project_slug=project.slug)
    summary = state.as_dict()
    summary["open_questions"] = list(open_questions_across(docs=docs))
    summary["blocked"] = [item.as_dict() for item in state.blocked]
    return summary


def build_snapshot(*, project: Project) -> ProjectSnapshot:
    """One project's counts and findings, or a problem snapshot if its docs are gone."""
    if not project.docs_dir.is_dir():
        return _missing_dir_snapshot(project=project)
    docs = load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)
    links = build_links(docs=docs)
    addressable = tuple(doc for doc in docs if not doc.is_entry)
    return ProjectSnapshot(
        slug=project.slug,
        name=project.name,
        docs_dir=str(project.docs_dir),
        doc_count=len(addressable),
        entry_count=len(docs) - len(addressable),
        link_count=len(links),
        total_lines=sum(doc.line_count for doc in addressable),
        kind_counts=_counts_by(docs=docs, attribute="kind"),
        read_when_counts=_counts_by(docs=docs, attribute="read_when"),
        findings=all_findings(docs=docs, links=links) + _drift(project=project),
        plan=_plan_summary(docs=docs, project=project),
    )


def build_all_snapshots(*, registry: ProjectRegistry) -> tuple[ProjectSnapshot, ...]:
    """Every registered project, ordered by slug."""
    projects = sorted(registry.all_projects(), key=lambda project: project.slug)
    return tuple(build_snapshot(project=project) for project in projects)
