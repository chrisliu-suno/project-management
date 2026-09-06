"""Dashboard payloads and the HTTP layer."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

from spine.constants import DASHBOARD_PICK_BUDGET, SPINE_HOME_ENV_VAR
from spine.serve.api import ERROR_FIELD, PROJECTS_FIELD, pick_payload, projects_payload
from spine.serve.page import render_page
from spine.serve.server import build_server

EPHEMERAL_PORT = 0
LOOPBACK = "127.0.0.1"
UNKNOWN_SLUG = "no-such-project"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


@pytest.fixture
def running_server():
    server = build_server(host=LOOPBACK, port=EPHEMERAL_PORT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _base_url(*, server: ThreadingHTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}"


def _get(*, server: ThreadingHTTPServer, path: str):
    with urlopen(_base_url(server=server) + path) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_projects_payload_always_carries_the_projects_key() -> None:
    assert PROJECTS_FIELD in projects_payload()


def test_an_empty_task_is_an_error_not_a_selection() -> None:
    payload = pick_payload(project_slug="anything", task="   ", budget=DASHBOARD_PICK_BUDGET)
    assert ERROR_FIELD in payload


def test_an_unknown_project_is_an_error_not_a_crash() -> None:
    payload = pick_payload(project_slug=UNKNOWN_SLUG, task="do a thing", budget=DASHBOARD_PICK_BUDGET)
    assert ERROR_FIELD in payload


def test_the_page_references_nothing_external() -> None:
    page = render_page()
    assert "http://" not in page
    assert "https://" not in page
    assert "<!doctype html>" in page.lower()


def test_the_page_closes_its_document() -> None:
    assert render_page().rstrip().endswith("</html>")


def test_the_root_route_serves_html(running_server: ThreadingHTTPServer) -> None:
    with urlopen(_base_url(server=running_server) + "/") as response:
        assert response.status == 200
        assert "text/html" in response.headers["Content-Type"]


def test_the_projects_route_answers_json(running_server: ThreadingHTTPServer) -> None:
    status, payload = _get(server=running_server, path="/api/projects")
    assert status == 200
    assert PROJECTS_FIELD in payload


def test_an_unknown_route_is_a_json_404(running_server: ThreadingHTTPServer) -> None:
    try:
        _get(server=running_server, path="/nope")
    except Exception as caught:
        assert getattr(caught, "code", None) == 404
    else:
        raise AssertionError("expected a 404")


def test_pick_with_an_unknown_project_answers_200_with_an_error(
    running_server: ThreadingHTTPServer,
) -> None:
    status, payload = _get(
        server=running_server, path=f"/api/pick?project={UNKNOWN_SLUG}&task=anything"
    )
    assert status == 200
    assert ERROR_FIELD in payload


def test_pick_with_an_empty_task_answers_200_with_an_error(
    running_server: ThreadingHTTPServer,
) -> None:
    status, payload = _get(server=running_server, path="/api/pick?project=alpha&task=")
    assert status == 200
    assert ERROR_FIELD in payload


def test_cli_exposes_the_serve_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["serve", "--port", "9999"])
    assert parsed.port == 9999
