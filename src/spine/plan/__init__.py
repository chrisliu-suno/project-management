"""Plan state derived from the documents a project already has."""

from __future__ import annotations

import argparse
import sys

from ..cli import EXIT_OK
from .extract import (
    open_questions_across,
    plan_in,
    plan_richness,
    primary_plan,
    project_plans,
)
from .model import ItemStatus, Milestone, PlanState, WorkItem

__all__ = [
    "ItemStatus",
    "Milestone",
    "PlanState",
    "WorkItem",
    "open_questions_across",
    "plan_in",
    "plan_richness",
    "primary_plan",
    "project_plans",
    "register_subcommand",
]

EXIT_UNKNOWN_PROJECT = 4
FIELD_SEPARATOR = "\t"


def _corpus_for(*, slug: str):
    from ..index import load_corpus
    from ..registry import load_registry

    project = load_registry().get(slug)
    if project is None:
        return None, ()
    return project, load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)


def _handle_show(args: argparse.Namespace) -> int:
    from .render import render_plan

    project, docs = _corpus_for(slug=args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    state = primary_plan(docs=docs, project_slug=project.slug)
    if not state.has_plan:
        print(f"{project.slug}: no document states a plan", file=sys.stderr)
        return EXIT_OK
    print(render_plan(state=state, open_questions=open_questions_across(docs=docs)))
    return EXIT_OK


def _handle_sources(args: argparse.Namespace) -> int:
    project, docs = _corpus_for(slug=args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    for doc, state in project_plans(docs=docs):
        print(
            FIELD_SEPARATOR.join(
                (
                    doc.path.name,
                    f"{len(state.milestones)} milestones",
                    f"{len(state.items)} items",
                    f"{state.done_count} done",
                )
            )
        )
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine plan` to the CLI."""
    parser = subparsers.add_parser("plan", help="Where a project stands, read from its documents.")
    verbs = parser.add_subparsers(dest="plan_command", metavar="VERB")

    shower = verbs.add_parser("show", help="The current milestone and open work.")
    shower.add_argument("--project", required=True)
    shower.set_defaults(handler=_handle_show)

    sources = verbs.add_parser("sources", help="Which documents state a plan, richest first.")
    sources.add_argument("--project", required=True)
    sources.set_defaults(handler=_handle_sources)
