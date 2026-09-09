"""Local dashboard over the registered projects."""

from __future__ import annotations

import argparse
import sys

from ..cli import EXIT_OK
from ..constants import DASHBOARD_HOST, DASHBOARD_PORT
from .api import pick_payload, projects_payload
from .page import render_page
from .server import PortInUseError, build_server, is_dashboard_at, serve_forever

__all__ = [
    "PortInUseError",
    "build_server",
    "is_dashboard_at",
    "pick_payload",
    "projects_payload",
    "register_subcommand",
    "render_page",
    "serve_forever",
]


EXIT_PORT_IN_USE = 1


def _handle_serve(args: argparse.Namespace) -> int:
    try:
        serve_forever(host=args.host, port=args.port)
    except PortInUseError as busy:
        if busy.is_ours:
            print(f"dashboard already running on http://{busy.host}:{busy.port}")
        else:
            print(
                f"port {busy.port} is taken by something else; start elsewhere with --port",
                file=sys.stderr,
            )
        return EXIT_PORT_IN_USE
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine serve` to the CLI."""
    parser = subparsers.add_parser("serve", help="Run the local project dashboard.")
    parser.add_argument("--host", default=DASHBOARD_HOST, help="Interface to bind.")
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT, help="Port to bind.")
    parser.set_defaults(handler=_handle_serve)
