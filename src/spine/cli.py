"""Command line entry point.

Each module registers its own subparser here so the hooks have one stable binary
to call regardless of which module does the work.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from . import __version__

SubcommandRegistrar = Callable[[argparse._SubParsersAction], None]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _registrars() -> tuple[SubcommandRegistrar, ...]:
    """Collect subcommand registrars from modules that provide one.

    Imported lazily and defensively so a module still under construction cannot
    break the whole CLI, which the session hooks depend on.
    """
    found: list[SubcommandRegistrar] = []
    for module_name in ("registry", "docs", "index", "picker", "session", "classify", "health", "serve", "context", "facts", "live", "guard", "proposals"):
        try:
            module = __import__(f"spine.{module_name}", fromlist=["register_subcommand"])
        except ImportError:
            continue
        registrar = getattr(module, "register_subcommand", None)
        if registrar is not None:
            found.append(registrar)
    return tuple(found)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spine", description="Project context for agent sessions.")
    parser.add_argument("--version", action="version", version=f"spine {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for register in _registrars():
        register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    return int(handler(args) or EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
