"""M1 — which projects exist, and which of them a session belongs to."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_ERROR, EXIT_OK, EXIT_USAGE
from ..constants import MIN_CONFIDENCE_FOR_AUTO_ATTACH
from ..model import Project, ProjectMatch
from .resolve import SignalResolver
from .store import RegistryError, TomlProjectRegistry

__all__ = [
    "AUTO_ATTACH_MARKER",
    "RegistryError",
    "SignalResolver",
    "TomlProjectRegistry",
    "register_subcommand",
]

FIELD_SEPARATOR = "\t"
AUTO_ATTACH_MARKER = "auto-attach"


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine registry` and its actions to the top level parser."""
    parser = subparsers.add_parser("registry", help="Project definitions and session resolution.")
    parser.set_defaults(handler=lambda args: _print_help(parser=parser))
    actions = parser.add_subparsers(dest="registry_action", metavar="ACTION")
    actions.add_parser("list", help="List registered projects.").set_defaults(handler=_handle_list)
    _add_add_action(actions=actions)
    _add_resolve_action(actions=actions)


def _add_add_action(*, actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser("add", help="Register a project, replacing any same-slug entry.")
    parser.add_argument("slug", help="Stable identifier, used as the table key.")
    parser.add_argument("--name", help="Display name. Defaults to the slug.")
    parser.add_argument("--docs-dir", required=True, help="Directory holding the project corpus.")
    parser.add_argument("--repo", action="append", default=[], help="Repeatable owner/name.")
    parser.add_argument("--path-glob", action="append", default=[], help="Repeatable path glob.")
    parser.add_argument(
        "--branch-prefix", action="append", default=[], help="Repeatable branch prefix."
    )
    parser.add_argument("--linear-project", help="Linear project key.")
    parser.set_defaults(handler=_handle_add)


def _add_resolve_action(*, actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser("resolve", help="Show which projects a session's signals match.")
    parser.add_argument("--cwd", default=None, help="Working directory. Defaults to the shell's.")
    parser.add_argument("--branch", default=None, help="Current git branch.")
    parser.add_argument("--repo", default=None, help="Current repo as owner/name.")
    parser.add_argument("--prompt", default=None, help="Opening prompt of the session.")
    parser.set_defaults(handler=_handle_resolve)


def _handle_list(args: argparse.Namespace) -> int:
    try:
        projects = TomlProjectRegistry().all_projects()
    except RegistryError as error:
        return _report_error(error=error)
    if not projects:
        print("no projects registered")
        return EXIT_OK
    for project in projects:
        print(FIELD_SEPARATOR.join((project.slug, project.name, str(project.docs_dir))))
    return EXIT_OK


def _handle_add(args: argparse.Namespace) -> int:
    project = Project(
        slug=args.slug,
        name=args.name or args.slug,
        docs_dir=Path(args.docs_dir).expanduser(),
        repos=tuple(args.repo),
        path_globs=tuple(args.path_glob),
        branch_prefixes=tuple(args.branch_prefix),
        linear_project=args.linear_project,
    )
    registry = TomlProjectRegistry()
    try:
        registry.add_project(project=project)
    except (RegistryError, OSError) as error:
        return _report_error(error=error)
    print(f"registered {project.slug} at {registry.path}")
    return EXIT_OK


def _handle_resolve(args: argparse.Namespace) -> int:
    resolver = SignalResolver(registry=TomlProjectRegistry())
    try:
        matches = resolver.resolve(
            cwd=Path(args.cwd).expanduser() if args.cwd else Path.cwd(),
            branch=args.branch,
            repo=args.repo,
            opening_prompt=args.prompt,
        )
    except RegistryError as error:
        return _report_error(error=error)
    if not matches:
        print("no project matched")
        return EXIT_OK
    for match in matches:
        print(_format_match(match=match))
    return EXIT_OK


def _format_match(*, match: ProjectMatch) -> str:
    fields = [match.project.slug, f"{match.confidence:.2f}", "; ".join(match.evidence)]
    if match.confidence >= MIN_CONFIDENCE_FOR_AUTO_ATTACH:
        fields.append(AUTO_ATTACH_MARKER)
    return FIELD_SEPARATOR.join(fields)


def _print_help(*, parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return EXIT_USAGE


def _report_error(*, error: Exception) -> int:
    print(str(error), file=sys.stderr)
    return EXIT_ERROR
