"""Link extraction and the persisted document graph."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK, EXIT_USAGE
from ..constants import DOC_FILE_SUFFIX
from ..docs import FilesystemDocSource
from ..classify.apply import apply_cached_classifications
from ..docs.entries import with_entries
from ..model import Doc, Link, Project
from .backlinks import backlinks, deduplicate_links, is_citation, sweep_targets
from .entry_links import entry_supersede_links
from .extract import TextualLinkExtractor
from .store import SqliteGraphStore

__all__ = [
    "open_graph_store",
    "SqliteGraphStore",
    "TextualLinkExtractor",
    "backlinks",
    "build_links",
    "deduplicate_links",
    "is_citation",
    "load_corpus",
    "register_subcommand",
    "sweep_targets",
]

EXIT_EMPTY_CORPUS = 1

def load_corpus(*, docs_dir: Path, project_slug: str) -> tuple[Doc, ...]:
    """Every document in a corpus directory, plus an entry node per log section.

    Cached classifications fill in kinds the documents do not declare. Reading the
    cache is offline; populating it is `spine classify run`.
    """
    project = Project(slug=project_slug, name=project_slug, docs_dir=docs_dir)
    loaded = FilesystemDocSource().load_all(project=project)
    return with_entries(docs=apply_cached_classifications(docs=loaded))


def build_links(*, docs: tuple[Doc, ...]) -> tuple[Link, ...]:
    """Run the textual extractor over a whole corpus and collapse duplicate edges."""
    extractor = TextualLinkExtractor()
    found: list[Link] = []
    for doc in docs:
        found.extend(extractor.extract(doc=doc, corpus=docs))
    found.extend(entry_supersede_links(corpus=docs))
    return deduplicate_links(links=tuple(found))


def _handle_build(args: argparse.Namespace) -> int:
    docs = load_corpus(docs_dir=args.dir, project_slug=args.project)
    if not docs:
        print(f"no {DOC_FILE_SUFFIX} documents under {args.dir}", file=sys.stderr)
        return EXIT_EMPTY_CORPUS
    links = build_links(docs=docs)
    SqliteGraphStore().replace_project(project_slug=args.project, docs=docs, links=links)
    print(f"{args.project}: indexed {len(docs)} docs, {len(links)} links")
    return EXIT_OK


def _handle_orphans(args: argparse.Namespace) -> int:
    for doc in SqliteGraphStore().orphans(project_slug=args.project):
        print(doc.doc_id)
    return EXIT_OK


def _handle_sweep(args: argparse.Namespace) -> int:
    citing_links = SqliteGraphStore().inbound(doc_id=args.doc)
    for doc_id in sweep_targets(links=citing_links, superseded_doc_id=args.doc):
        print(doc_id)
    return EXIT_OK


def _handle_missing_verb(*, parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return EXIT_USAGE


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine index` and its build, orphans, and sweep verbs."""
    parser = subparsers.add_parser("index", help="Extract links and query the document graph.")
    parser.set_defaults(handler=lambda _args: _handle_missing_verb(parser=parser))
    verbs = parser.add_subparsers(dest="index_command", metavar="VERB")

    build = verbs.add_parser("build", help="Index a corpus directory into the graph.")
    build.add_argument("--dir", required=True, type=Path, help="Directory of markdown documents.")
    build.add_argument("--project", required=True, help="Project slug the corpus belongs to.")
    build.set_defaults(handler=_handle_build)

    orphans = verbs.add_parser("orphans", help="List docs nothing links to.")
    orphans.add_argument("--project", required=True, help="Project slug to inspect.")
    orphans.set_defaults(handler=_handle_orphans)

    sweep = verbs.add_parser("sweep", help="List docs to update if a doc were superseded.")
    sweep.add_argument("--doc", required=True, help="Doc id being superseded.")
    sweep.set_defaults(handler=_handle_sweep)


def open_graph_store() -> SqliteGraphStore:
    """The graph store at its configured location."""
    return SqliteGraphStore()
