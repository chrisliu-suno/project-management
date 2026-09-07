"""Stdlib HTTP server for the dashboard."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..constants import (
    DASHBOARD_HOST,
    DASHBOARD_PICK_BUDGET,
    DASHBOARD_PORT,
    DASHBOARD_PROBE_TIMEOUT_SECONDS,
)
from .api import ERROR_FIELD, PROJECTS_FIELD, pick_payload, projects_payload
from .page import render_page

ROOT_PATH = "/"
PROJECTS_PATH = "/api/projects"
PICK_PATH = "/api/pick"
PROJECT_PARAM = "project"
TASK_PARAM = "task"

HTTP_OK = 200
HTTP_NOT_FOUND = 404
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
RESPONSE_ENCODING = "utf-8"


class PortInUseError(OSError):
    """The port is taken. `is_ours` says whether a dashboard already answers there."""

    def __init__(self, *, host: str, port: int, is_ours: bool) -> None:
        self.host = host
        self.port = port
        self.is_ours = is_ours
        super().__init__(f"cannot bind {host}:{port}")


def is_dashboard_at(*, host: str, port: int) -> bool:
    """Whether a spine dashboard already answers on this address."""
    import json as _json
    from urllib.error import URLError
    from urllib.request import urlopen

    try:
        with urlopen(
            f"http://{host}:{port}{PROJECTS_PATH}", timeout=DASHBOARD_PROBE_TIMEOUT_SECONDS
        ) as response:
            return PROJECTS_FIELD in _json.loads(response.read().decode(RESPONSE_ENCODING))
    except (URLError, ValueError, OSError):
        return False


class DashboardHandler(BaseHTTPRequestHandler):
    """Serves the page and its two read-only JSON endpoints."""

    def log_message(self, *_args: object) -> None:
        return

    def _send(self, *, status: int, body: str, content_type: str) -> None:
        encoded = body.encode(RESPONSE_ENCODING)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, *, status: int, payload: dict[str, object]) -> None:
        self._send(status=status, body=json.dumps(payload), content_type=JSON_CONTENT_TYPE)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == ROOT_PATH:
            self._send(status=HTTP_OK, body=render_page(), content_type=HTML_CONTENT_TYPE)
            return
        if parsed.path == PROJECTS_PATH:
            self._send_json(status=HTTP_OK, payload=projects_payload())
            return
        if parsed.path == PICK_PATH:
            query = parse_qs(parsed.query)
            self._send_json(
                status=HTTP_OK,
                payload=pick_payload(
                    project_slug=(query.get(PROJECT_PARAM) or [""])[0],
                    task=(query.get(TASK_PARAM) or [""])[0],
                    budget=DASHBOARD_PICK_BUDGET,
                ),
            )
            return
        self._send_json(status=HTTP_NOT_FOUND, payload={ERROR_FIELD: f"no route {parsed.path}"})


def build_server(
    *, host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT
) -> ThreadingHTTPServer:
    """A server bound and ready, so tests can drive it without blocking."""
    try:
        return ThreadingHTTPServer((host, port), DashboardHandler)
    except OSError as cause:
        raise PortInUseError(
            host=host, port=port, is_ours=is_dashboard_at(host=host, port=port)
        ) from cause


def serve_forever(*, host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT) -> None:
    """Block serving the dashboard until interrupted."""
    server = build_server(host=host, port=port)
    bound_host, bound_port = server.server_address[:2]
    print(f"spine dashboard on http://{bound_host}:{bound_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
