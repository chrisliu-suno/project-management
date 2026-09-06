"""Corpus health analysis."""

from __future__ import annotations

import argparse
import sys

from ..cli import EXIT_OK
from ..dashboard import Severity
from .findings import (
    all_findings,
    brief_findings,
    cap_breach_findings,
    duplicate_findings,
    every_time_findings,
    orphan_findings,
    unclassified_findings,
)
from .snapshot import build_all_snapshots, build_snapshot

__all__ = [
    "all_findings",
    "brief_findings",
    "build_all_snapshots",
    "build_snapshot",
    "cap_breach_findings",
    "duplicate_findings",
    "every_time_findings",
    "orphan_findings",
    "register_subcommand",
    "unclassified_findings",
]

EXIT_PROBLEMS_FOUND = 1
EXIT_UNKNOWN_PROJECT = 4
FIELD_SEPARATOR = "\t"


def _snapshots_for(*, slug: str | None):
    from ..registry import load_registry

    registry = load_registry()
    if slug is None:
        return build_all_snapshots(registry=registry)
    project = registry.get(slug)
    if project is None:
        return None
    return (build_snapshot(project=project),)


def _handle_check(args: argparse.Namespace) -> int:
    snapshots = _snapshots_for(slug=args.project)
    if snapshots is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    has_problem = False
    for snapshot in snapshots:
        print(f"# {snapshot.slug}  ({snapshot.doc_count} docs, {snapshot.link_count} links)")
        for finding in snapshot.findings:
            has_problem = has_problem or finding.severity is Severity.PROBLEM
            print(FIELD_SEPARATOR.join((str(finding.severity), finding.code, finding.headline)))
    return EXIT_PROBLEMS_FOUND if has_problem else EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine health` to the CLI."""
    parser = subparsers.add_parser("health", help="Report corpus problems per project.")
    verbs = parser.add_subparsers(dest="health_command", metavar="VERB")
    checker = verbs.add_parser("check", help="List findings, exiting non-zero on a problem.")
    checker.add_argument("--project", default=None, help="Limit to one project slug.")
    checker.set_defaults(handler=_handle_check)
    parser.set_defaults(handler=_handle_check, project=None)
