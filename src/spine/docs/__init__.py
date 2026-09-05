"""M2 — the document corpus: frontmatter, kinds, read-when groups, and size caps."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from ..cli import EXIT_OK, EXIT_USAGE
from ..constants import (
    DOCS_ACTION_DEST,
    DOCS_BREACH_ROW_FORMAT,
    DOCS_CHECK_ACTION,
    DOCS_COMMAND_NAME,
    DOCS_DIR_DEST,
    DOCS_DIR_OPTION,
    DOCS_LIST_ACTION,
    DOCS_LIST_ROW_FORMAT,
    DOCS_MISSING_DIR_MESSAGE,
    EXIT_CAP_BREACH,
)
from ..model import Doc
from .frontmatter import FrontmatterParse, parse_frontmatter
from .limits import CapBreach, cap_for, find_cap_breaches
from .loader import (
    FilesystemDocSource,
    corpus_paths,
    doc_id_for,
    first_h1,
    infer_kind_from_filename,
    project_for_dir,
    resolve_kind,
    resolve_read_when,
    resolve_title,
)

__all__ = [
    "CapBreach",
    "FilesystemDocSource",
    "FrontmatterParse",
    "cap_for",
    "corpus_paths",
    "doc_id_for",
    "find_cap_breaches",
    "first_h1",
    "infer_kind_from_filename",
    "parse_frontmatter",
    "project_for_dir",
    "register_subcommand",
    "resolve_kind",
    "resolve_read_when",
    "resolve_title",
]


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine docs list` and `spine docs check` to the CLI."""
    parser = subparsers.add_parser(DOCS_COMMAND_NAME, help="Inspect a project's document corpus.")
    parser.set_defaults(handler=_make_help_handler(parser=parser))
    actions = parser.add_subparsers(dest=DOCS_ACTION_DEST, metavar="ACTION")
    _add_dir_option(
        parser=actions.add_parser(DOCS_LIST_ACTION, help="List every document in a corpus."),
        handler=_handle_list,
    )
    _add_dir_option(
        parser=actions.add_parser(DOCS_CHECK_ACTION, help="Report documents over their cap."),
        handler=_handle_check,
    )


SubcommandHandler = Callable[[argparse.Namespace], int]


def _add_dir_option(*, parser: argparse.ArgumentParser, handler: SubcommandHandler) -> None:
    parser.add_argument(
        DOCS_DIR_OPTION,
        dest=DOCS_DIR_DEST,
        type=Path,
        required=True,
        help="Directory holding the corpus.",
    )
    parser.set_defaults(handler=handler)


def _make_help_handler(*, parser: argparse.ArgumentParser) -> SubcommandHandler:
    """Handler used when `spine docs` is invoked without an action."""

    def show_help(_args: argparse.Namespace) -> int:
        parser.print_help()
        return EXIT_USAGE

    return show_help


def _handle_list(args: argparse.Namespace) -> int:
    docs_dir = getattr(args, DOCS_DIR_DEST)
    if not docs_dir.is_dir():
        return _report_missing_dir(docs_dir=docs_dir)
    for doc in _load_corpus(docs_dir=docs_dir):
        print(
            DOCS_LIST_ROW_FORMAT.format(
                doc_id=doc.doc_id,
                kind=doc.kind,
                read_when=doc.read_when,
                line_count=doc.line_count,
                title=doc.title,
            )
        )
    return EXIT_OK


def _handle_check(args: argparse.Namespace) -> int:
    docs_dir = getattr(args, DOCS_DIR_DEST)
    if not docs_dir.is_dir():
        return _report_missing_dir(docs_dir=docs_dir)
    breaches = find_cap_breaches(docs=_load_corpus(docs_dir=docs_dir))
    for breach in breaches:
        print(
            DOCS_BREACH_ROW_FORMAT.format(
                doc_id=breach.doc.doc_id,
                read_when=breach.doc.read_when,
                line_count=breach.line_count,
                cap_lines=breach.cap_lines,
                excess_lines=breach.excess_lines,
            )
        )
    return EXIT_CAP_BREACH if breaches else EXIT_OK


def _load_corpus(*, docs_dir: Path) -> tuple[Doc, ...]:
    return FilesystemDocSource().load_all(project=project_for_dir(docs_dir=docs_dir))


def _report_missing_dir(*, docs_dir: Path) -> int:
    """Fail loudly on a bad --dir rather than reporting an empty corpus as clean."""
    print(DOCS_MISSING_DIR_MESSAGE.format(docs_dir=docs_dir), file=sys.stderr)
    return EXIT_USAGE
