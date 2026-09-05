"""M4 — choose what a session gets within a line budget, and record every pick."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..cli import EXIT_OK
from ..constants import (
    EXACT_MATCH_CONFIDENCE,
    GRAPH_STORE_FACTORY_NAME,
    GRAPH_STORE_MODULE_NAME,
    INJECTION_LINE_BUDGET,
    PROJECT_REGISTRY_FACTORY_NAME,
    PROJECT_REGISTRY_MODULE_NAME,
    SPINE_SESSION_ID_ENV_VAR,
    UNKNOWN_SESSION_ID,
)
from ..model import Project, Selection
from .rank import NeighbourLookup, no_neighbours, rank_docs, score_doc, terms_in
from .record import PickSummary, SqlitePickRecorder, summarize_picks
from .select import BudgetedPicker, GroupFill, fill_group, group_allowance, reason_for

__all__ = [
    "BudgetedPicker",
    "GroupFill",
    "NeighbourLookup",
    "PickSummary",
    "SqlitePickRecorder",
    "fill_group",
    "group_allowance",
    "no_neighbours",
    "rank_docs",
    "reason_for",
    "register_subcommand",
    "score_doc",
    "summarize_picks",
    "terms_in",
]

EXIT_DEPENDENCY_MISSING = 3
EXIT_UNKNOWN_PROJECT = 4


def _sibling_factory(*, module_name: str, factory_name: str) -> Callable[[], Any] | None:
    """A sibling module's factory if that module has landed, else None."""
    try:
        module = __import__(f"spine.{module_name}", fromlist=[factory_name])
    except ImportError:
        return None
    return getattr(module, factory_name, None)


def _resolve_project(*, slug: str) -> Project | None:
    """The registered project, or a slug-only stand-in when no registry is reachable.

    None means a registry answered and does not know the slug.
    """
    load_registry = _sibling_factory(
        module_name=PROJECT_REGISTRY_MODULE_NAME, factory_name=PROJECT_REGISTRY_FACTORY_NAME
    )
    if load_registry is None:
        return Project(slug=slug, name=slug, docs_dir=Path.cwd())
    return load_registry().get(slug)


def _session_id() -> str:
    return os.environ.get(SPINE_SESSION_ID_ENV_VAR, UNKNOWN_SESSION_ID)


def _print_selection(*, selection: Selection) -> None:
    for doc in selection.chosen:
        print(doc.doc_id)
    print(f"lines: {selection.total_lines}")
    print(f"reason: {selection.reason}")
    for doc in selection.dropped:
        print(f"dropped: {doc.doc_id} ({doc.read_when})", file=sys.stderr)


def run_pick(args: argparse.Namespace) -> int:
    """Select context for one task, record the pick, print the chosen doc ids."""
    open_graph_store = _sibling_factory(
        module_name=GRAPH_STORE_MODULE_NAME, factory_name=GRAPH_STORE_FACTORY_NAME
    )
    if open_graph_store is None:
        print("spine pick needs the graph store from spine.index.", file=sys.stderr)
        return EXIT_DEPENDENCY_MISSING
    project = _resolve_project(slug=args.project)
    if project is None:
        print(f"No project registered under the slug {args.project!r}.", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    picker = BudgetedPicker(
        graph_store=open_graph_store(), should_include_rarely=args.should_include_rarely
    )
    selection = picker.pick(project=project, task_context=args.task, line_budget=args.budget)
    SqlitePickRecorder().record(
        session_id=_session_id(),
        project_slug=project.slug,
        selection=selection,
        confidence=EXACT_MATCH_CONFIDENCE,
    )
    _print_selection(selection=selection)
    return EXIT_OK


def run_picks_summary(args: argparse.Namespace) -> int:
    """Print the grouped pick categories."""
    summary = summarize_picks()
    print(f"total: {summary.total_picks}")
    print(f"low_confidence: {summary.low_confidence_picks}")
    print(f"every_time_dropped: {summary.every_time_dropped_picks}")
    print(f"no_in_area_match: {summary.no_in_area_match_picks}")
    return EXIT_OK


def _register_pick(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("pick", help="Choose the documents a session should be given.")
    parser.add_argument("--project", required=True, help="Slug of the project to pick from.")
    parser.add_argument("--task", required=True, help="What the session is about to work on.")
    parser.add_argument(
        "--budget",
        type=int,
        default=INJECTION_LINE_BUDGET,
        help="Line budget the selection must stay within.",
    )
    parser.add_argument(
        "--include-rarely",
        dest="should_include_rarely",
        action="store_true",
        help="Also consider the rarely-read group.",
    )
    parser.set_defaults(handler=run_pick)


def _register_picks(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("picks", help="Read back what the picker has recorded.")
    actions = parser.add_subparsers(dest="picks_command", metavar="ACTION")
    summary_parser = actions.add_parser("summary", help="Grouped counts across recorded picks.")
    summary_parser.set_defaults(handler=run_picks_summary)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine pick` and `spine picks summary` to the CLI."""
    _register_pick(subparsers=subparsers)
    _register_picks(subparsers=subparsers)
