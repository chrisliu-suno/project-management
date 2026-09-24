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
    DOCS_DERIVED_BRIEF_PLACEHOLDER,
    DOCS_DIR_DEST,
    DOCS_DIR_OPTION,
    DOCS_INDEX_ACTION,
    DOCS_LIST_ACTION,
    DOCS_LIST_ROW_FORMAT,
    DOCS_MISSING_DIR_MESSAGE,
    DOCS_OUT_DEST,
    DOCS_OUT_OPTION,
    DOCS_README_WRITTEN_FORMAT,
    DOCS_ROOT_DEST,
    DOCS_ROOT_OPTION,
    DOCS_UNSTATED_ROW_FORMAT,
    DOCS_UNSTATED_SUMMARY_FORMAT,
    EXIT_BRIEF_GAP,
    EXIT_CAP_BREACH,
)
from ..model import Doc, Project
from ..registry import load_registry
from .frontmatter import FrontmatterParse, parse_frontmatter
from .limits import CapBreach, cap_for, find_cap_breaches
from .readme import render_docs_readme
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
    "render_docs_readme",
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
        parser=actions.add_parser(
            DOCS_CHECK_ACTION, help="Report documents over their cap or stating no purpose."
        ),
        handler=_handle_check,
    )
    _add_index_options(parser=actions.add_parser(DOCS_INDEX_ACTION, help=_INDEX_HELP))


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
    docs = _load_corpus(docs_dir=docs_dir)
    breaches = find_cap_breaches(docs=docs)
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
    unstated = find_unstated_briefs(docs=docs)
    for doc in unstated:
        print(
            DOCS_UNSTATED_ROW_FORMAT.format(
                path=doc.path.name, brief=doc.brief or DOCS_DERIVED_BRIEF_PLACEHOLDER
            )
        )
    if unstated:
        print(
            DOCS_UNSTATED_SUMMARY_FORMAT.format(unstated=len(unstated), total=len(docs)),
            file=sys.stderr,
        )
    if breaches:
        return EXIT_CAP_BREACH
    return EXIT_BRIEF_GAP if unstated else EXIT_OK


def find_unstated_briefs(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    """Documents whose purpose was guessed from their body rather than stated for them."""
    return tuple(doc for doc in docs if not doc.is_entry and not doc.is_brief_stated)


_INDEX_HELP = "Write one page indexing every document in every registered project."


def _add_index_options(*, parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        DOCS_OUT_OPTION, dest=DOCS_OUT_DEST, type=Path, default=None, help="Page to write."
    )
    parser.add_argument(
        DOCS_ROOT_OPTION,
        dest=DOCS_ROOT_DEST,
        type=Path,
        default=None,
        help="Directory document links are relative to; defaults to the page's directory.",
    )
    parser.set_defaults(handler=_handle_index)


def _handle_index(args: argparse.Namespace) -> int:
    out_path = getattr(args, DOCS_OUT_DEST)
    root = getattr(args, DOCS_ROOT_DEST) or (out_path.parent if out_path else Path.cwd())
    corpora = load_registered_corpora()
    page = render_docs_readme(corpora=corpora, root=root.resolve())
    if out_path is None:
        print(page, end="")
        return EXIT_OK
    out_path.write_text(page)
    print(
        DOCS_README_WRITTEN_FORMAT.format(
            path=out_path,
            documents=sum(len(docs) for _, docs in corpora),
            projects=len(corpora),
        ),
        file=sys.stderr,
    )
    return EXIT_OK


def load_registered_corpora() -> tuple[tuple[Project, tuple[Doc, ...]], ...]:
    """Every registered project that has a corpus on disk, with its documents loaded."""
    source = FilesystemDocSource()
    return tuple(
        (project, source.load_all(project=project))
        for project in load_registry().all_projects()
        if project.docs_dir.is_dir()
    )


def _load_corpus(*, docs_dir: Path) -> tuple[Doc, ...]:
    return FilesystemDocSource().load_all(project=project_for_dir(docs_dir=docs_dir))


def _report_missing_dir(*, docs_dir: Path) -> int:
    """Fail loudly on a bad --dir rather than reporting an empty corpus as clean."""
    print(DOCS_MISSING_DIR_MESSAGE.format(docs_dir=docs_dir), file=sys.stderr)
    return EXIT_USAGE
