"""One sweep that brings every project's derived state up to date.

The pieces (observe, index, propose) each have their own subcommand. This runs
them in dependency order so a human never has to remember the sequence.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from ..cli import EXIT_OK

__all__ = ["ProjectRefresh", "refresh_all", "refresh_project", "register_subcommand"]

EXIT_UNKNOWN_PROJECT = 4
FIELD_SEPARATOR = "\t"


@dataclass(frozen=True, slots=True)
class ProjectRefresh:
    """What one project's sweep changed."""

    slug: str
    doc_count: int
    fact_count: int
    proposals_queued: int
    error: str | None = None

    def as_line(self) -> str:
        if self.error is not None:
            return FIELD_SEPARATOR.join((self.slug, "error", self.error))
        return FIELD_SEPARATOR.join(
            (
                self.slug,
                f"{self.doc_count} docs",
                f"{self.fact_count} facts",
                f"{self.proposals_queued} new proposal(s)",
            )
        )


def refresh_project(*, project) -> ProjectRefresh:
    """Observe what shipped, rebuild the graph, then draft any new proposals."""
    from ..facts import FactStore, observe_project
    from ..index import build_project
    from ..proposals import generate_for_project

    try:
        observe_project(project=project)
        docs, _ = build_project(docs_dir=project.docs_dir, project_slug=project.slug)
        queued = generate_for_project(project=project)
    except Exception as cause:  # noqa: BLE001 - one bad project must not abort the sweep
        return ProjectRefresh(
            slug=project.slug, doc_count=0, fact_count=0, proposals_queued=0, error=str(cause)
        )
    return ProjectRefresh(
        slug=project.slug,
        doc_count=len(docs),
        fact_count=len(FactStore().for_project(project_slug=project.slug)),
        proposals_queued=queued,
    )


def refresh_all(*, slug: str | None = None) -> tuple[ProjectRefresh, ...]:
    """Sweep every registered project, or just one."""
    from ..registry import load_registry

    registry = load_registry()
    if slug is not None:
        project = registry.get(slug)
        return (refresh_project(project=project),) if project is not None else ()
    return tuple(refresh_project(project=project) for project in registry.all_projects())


def _handle_refresh(args: argparse.Namespace) -> int:
    results = refresh_all(slug=args.project)
    if not results:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    for result in results:
        print(result.as_line())
    waiting = sum(result.proposals_queued for result in results)
    if waiting:
        from ..constants import DASHBOARD_HOST, DASHBOARD_PORT

        print(
            f"\n{waiting} decision(s) waiting at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}",
            file=sys.stderr,
        )
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine refresh` to the CLI."""
    parser = subparsers.add_parser(
        "refresh", help="Bring every project up to date: observe, index, propose."
    )
    parser.add_argument("--project", default=None, help="Limit the sweep to one project.")
    parser.set_defaults(handler=_handle_refresh)
