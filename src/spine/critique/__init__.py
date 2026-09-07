"""Critique-and-revise, and the style gate it runs first."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK
from ..constants import CRITIQUE_MAX_ROUNDS
from ..style.rules import StyleNote, review
from .loop import Reviser, refine
from .model import Refinement, Round

__all__ = [
    "Refinement",
    "Reviser",
    "Round",
    "StyleNote",
    "refine",
    "register_subcommand",
    "review",
]

EXIT_MISSING_FILE = 4
EXIT_STYLE_FAILED = 3
EXIT_MODEL_UNAVAILABLE = 5
NOTE_LINE_TEMPLATE = "{code}\t{detail}\t{excerpt}"


def _read_or_none(*, path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _print_notes(*, notes: tuple[StyleNote, ...]) -> None:
    for note in notes:
        print(NOTE_LINE_TEMPLATE.format(**note.as_dict()), file=sys.stderr)


def _handle_check(args: argparse.Namespace) -> int:
    text = _read_or_none(path=Path(args.file))
    if text is None:
        print(f"no such file: {args.file}", file=sys.stderr)
        return EXIT_MISSING_FILE
    notes = review(text=text)
    if not notes:
        return EXIT_OK
    _print_notes(notes=notes)
    return EXIT_STYLE_FAILED if args.strict else EXIT_OK


def _reviser_or_none(*, use_model: bool) -> Reviser | None:
    if not use_model:
        return None
    from .client import AnthropicReviser

    return AnthropicReviser()


def _handle_revise(args: argparse.Namespace) -> int:
    target = Path(args.file)
    text = _read_or_none(path=target)
    if text is None:
        print(f"no such file: {args.file}", file=sys.stderr)
        return EXIT_MISSING_FILE
    from ..classify.client import ModelUnavailableError

    try:
        result = refine(
            text=text, reviser=_reviser_or_none(use_model=not args.no_model), max_rounds=args.rounds
        )
    except ModelUnavailableError as unavailable:
        print(f"spine: {unavailable}; falling back to --no-model", file=sys.stderr)
        result = refine(text=text, reviser=None, max_rounds=args.rounds)
        _print_notes(notes=result.remaining)
        return EXIT_MODEL_UNAVAILABLE
    for line in result.summary_lines():
        print(line, file=sys.stderr)
    _print_notes(notes=result.remaining)
    if args.write and result.text != text:
        target.write_text(result.text, encoding="utf-8")
        print(f"rewrote {target}")
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine critique` to the CLI."""
    parser = subparsers.add_parser("critique", help="Review a draft before a human reads it.")
    verbs = parser.add_subparsers(dest="critique_command", metavar="VERB")

    checker = verbs.add_parser("check", help="Mechanical style notes only; no model call.")
    checker.add_argument("--file", required=True)
    checker.add_argument("--strict", action="store_true", help="Exit non-zero when notes exist.")
    checker.set_defaults(handler=_handle_check)

    reviser = verbs.add_parser("revise", help="Critique and revise until clean or out of rounds.")
    reviser.add_argument("--file", required=True)
    reviser.add_argument("--rounds", type=int, default=CRITIQUE_MAX_ROUNDS)
    reviser.add_argument("--write", action="store_true", help="Save the revision over the file.")
    reviser.add_argument("--no-model", action="store_true", help="Style gate only.")
    reviser.set_defaults(handler=_handle_revise)
