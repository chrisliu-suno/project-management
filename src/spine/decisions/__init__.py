"""Decisions an agent logged, and whether a human has seen them."""

from __future__ import annotations

import argparse
import sys

from ..cli import EXIT_OK
from .store import Decision, DecisionStore, decision_entries, decisions_db_path

__all__ = [
    "Decision",
    "DecisionStore",
    "decision_entries",
    "decisions_db_path",
    "record_for_project",
    "register_subcommand",
]

EXIT_UNKNOWN_PROJECT = 4
EXIT_UNKNOWN_DECISION = 5
FIELD_SEPARATOR = "\t"


def record_for_project(*, project) -> int:
    """Register any decision entries in a project's logs; returns how many were new."""
    from ..index import load_corpus

    if not project.docs_dir.is_dir():
        return 0
    docs = load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)
    entries = decision_entries(docs=docs)
    return DecisionStore().record(project_slug=project.slug, entries=entries)


def _handle_list(args: argparse.Namespace) -> int:
    for decision in DecisionStore().pending(project_slug=args.project):
        print(FIELD_SEPARATOR.join((decision.entry_id, decision.project_slug, decision.title)))
    return EXIT_OK


def _handle_ack(args: argparse.Namespace) -> int:
    if DecisionStore().acknowledge(entry_id=args.id):
        print(f"acknowledged {args.id}")
        return EXIT_OK
    print(f"no unacknowledged decision {args.id!r}", file=sys.stderr)
    return EXIT_UNKNOWN_DECISION


def _handle_scan(args: argparse.Namespace) -> int:
    from ..registry import load_registry

    project = load_registry().get(args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    print(f"{project.slug}: {record_for_project(project=project)} new decision(s)")
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine decisions` to the CLI."""
    parser = subparsers.add_parser("decisions", help="Decisions logged, awaiting review.")
    verbs = parser.add_subparsers(dest="decisions_command", metavar="VERB")

    lister = verbs.add_parser("list", help="Decisions nobody has acknowledged.")
    lister.add_argument("--project", default=None)
    lister.set_defaults(handler=_handle_list)

    scanner = verbs.add_parser("scan", help="Register decision entries from a project's logs.")
    scanner.add_argument("--project", required=True)
    scanner.set_defaults(handler=_handle_scan)

    acker = verbs.add_parser("ack", help="Mark one decision as seen.")
    acker.add_argument("--id", required=True)
    acker.set_defaults(handler=_handle_ack)
