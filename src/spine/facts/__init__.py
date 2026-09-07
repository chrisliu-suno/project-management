"""Observed facts and the drift they expose."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK
from ..dashboard import Severity
from .drift import (
    documented_but_unmerged,
    drift_findings,
    merged_but_undocumented,
    referenced_pull_requests,
)
from .model import Fact, FactKind, PullRequestState
from .observe import observe_commits, observe_pull_requests
from .store import FactStore, facts_db_path

__all__ = [
    "Fact",
    "FactKind",
    "FactStore",
    "PullRequestState",
    "documented_but_unmerged",
    "drift_findings",
    "drift_for_project",
    "facts_db_path",
    "merged_but_undocumented",
    "observe_commits",
    "observe_pull_requests",
    "observe_project",
    "referenced_pull_requests",
    "register_subcommand",
]

EXIT_UNKNOWN_PROJECT = 4
FIELD_SEPARATOR = "\t"


def observe_project(*, project, repo_dir: Path | None = None, branch: str = "HEAD") -> int:
    """Observe and store everything visible for a project; returns the fact count."""
    collected = list(observe_pull_requests(project=project))
    if repo_dir is not None:
        collected.extend(observe_commits(project=project, repo_dir=repo_dir, branch=branch))
    return FactStore().record(facts=tuple(collected))


def drift_for_project(*, project):
    """Findings where the project's documents and its observed facts disagree."""
    from ..index import load_corpus

    if not project.docs_dir.is_dir():
        return ()
    docs = load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)
    facts = FactStore().for_project(project_slug=project.slug)
    return drift_findings(docs=docs, facts=facts)


def _project_or_none(*, slug: str):
    from ..registry import load_registry

    return load_registry().get(slug)


def _handle_observe(args: argparse.Namespace) -> int:
    project = _project_or_none(slug=args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    written = observe_project(
        project=project,
        repo_dir=Path(args.repo_dir).expanduser() if args.repo_dir else None,
        branch=args.branch,
    )
    print(f"{project.slug}: recorded {written} fact(s)")
    return EXIT_OK


def _handle_drift(args: argparse.Namespace) -> int:
    project = _project_or_none(slug=args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    findings = drift_for_project(project=project)
    if not findings:
        print(f"{project.slug}: docs and facts agree")
        return EXIT_OK
    for finding in findings:
        print(FIELD_SEPARATOR.join((str(finding.severity), finding.code, finding.headline)))
        print(f"  {finding.detail}")
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine facts` to the CLI."""
    parser = subparsers.add_parser("facts", help="Observe what happened, and where docs disagree.")
    verbs = parser.add_subparsers(dest="facts_command", metavar="VERB")

    observer = verbs.add_parser("observe", help="Read commits and pull requests into the store.")
    observer.add_argument("--project", required=True)
    observer.add_argument("--repo-dir", default=None, help="Checkout to read commits from.")
    observer.add_argument("--branch", default="HEAD")
    observer.set_defaults(handler=_handle_observe)

    drifter = verbs.add_parser("drift", help="Report where documents and facts disagree.")
    drifter.add_argument("--project", required=True)
    drifter.set_defaults(handler=_handle_drift)
