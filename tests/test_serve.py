"""Dashboard payloads and the HTTP layer."""

from __future__ import annotations

import argparse
import json
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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


def _post(*, server: ThreadingHTTPServer, path: str, fields: dict[str, str]):
    request = Request(
        _base_url(server=server) + path,
        data=urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _status_of_get(*, server: ThreadingHTTPServer, path: str) -> int:
    try:
        _get(server=server, path=path)
    except HTTPError as refused:
        return refused.code
    return 200


def test_projects_payload_always_carries_the_projects_key() -> None:
    assert PROJECTS_FIELD in projects_payload()


def test_an_empty_task_is_an_error_not_a_selection() -> None:
    payload = pick_payload(project_slug="anything", task="   ", budget=DASHBOARD_PICK_BUDGET)
    assert ERROR_FIELD in payload


def test_an_unknown_project_is_an_error_not_a_crash() -> None:
    payload = pick_payload(
        project_slug=UNKNOWN_SLUG, task="do a thing", budget=DASHBOARD_PICK_BUDGET
    )
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


def test_a_second_serve_reports_the_running_dashboard(
    running_server: ThreadingHTTPServer, capsys: pytest.CaptureFixture[str]
) -> None:
    from spine.serve import _handle_serve

    host, port = running_server.server_address[:2]
    args = argparse.Namespace(host=host, port=port)
    assert _handle_serve(args) != 0
    assert "already running" in capsys.readouterr().out


def test_a_port_held_by_something_else_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    from spine.serve import _handle_serve

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind((LOOPBACK, EPHEMERAL_PORT))
    blocker.listen(1)
    try:
        args = argparse.Namespace(host=LOOPBACK, port=blocker.getsockname()[1])
        assert _handle_serve(args) != 0
        assert "taken by something else" in capsys.readouterr().err
    finally:
        blocker.close()


def test_probing_an_unbound_port_is_false() -> None:
    from spine.serve import is_dashboard_at

    free = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    free.bind((LOOPBACK, EPHEMERAL_PORT))
    port = free.getsockname()[1]
    free.close()
    assert is_dashboard_at(host=LOOPBACK, port=port) is False


def test_the_sessions_route_answers_json(running_server: ThreadingHTTPServer) -> None:
    status, payload = _get(server=running_server, path="/api/sessions")
    assert status == 200
    assert "sessions" in payload


def test_steering_an_unnamed_session_is_an_error(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/steer", fields={"session": "", "action": "stop"}
    )
    assert status == 200
    assert ERROR_FIELD in payload


def test_an_unknown_steering_action_is_an_error(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/steer", fields={"session": "s1", "action": "explode"}
    )
    assert status == 200
    assert ERROR_FIELD in payload


def test_steering_a_session_succeeds(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/steer", fields={"session": "s1", "action": "pause"}
    )
    assert status == 200
    assert payload.get("ok") is True


def test_the_proposals_route_answers_json(running_server: ThreadingHTTPServer) -> None:
    status, payload = _get(server=running_server, path="/api/proposals")
    assert status == 200
    assert "proposals" in payload


def test_deciding_an_unnamed_proposal_is_an_error(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/decide", fields={"id": "", "accept": "true"}
    )
    assert status == 200
    assert ERROR_FIELD in payload


def test_deciding_an_unknown_proposal_is_an_error(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/decide", fields={"id": "nope", "accept": "true"}
    )
    assert status == 200
    assert ERROR_FIELD in payload


def test_steering_over_get_is_refused(running_server: ThreadingHTTPServer) -> None:
    assert _status_of_get(server=running_server, path="/api/steer?session=s1&action=stop") == 405


def test_deciding_over_get_is_refused(running_server: ThreadingHTTPServer) -> None:
    assert _status_of_get(server=running_server, path="/api/decide?id=x&accept=true") == 405


def test_posting_to_an_unknown_route_is_a_404(running_server: ThreadingHTTPServer) -> None:
    try:
        _post(server=running_server, path="/api/nope", fields={})
    except HTTPError as refused:
        assert refused.code == 404
        return
    raise AssertionError("expected a 404")


def test_a_post_reads_its_fields_from_the_body(running_server: ThreadingHTTPServer) -> None:
    status, payload = _post(
        server=running_server, path="/api/steer", fields={"session": "s2", "action": "pause"}
    )
    assert status == 200
    assert payload["message"]["session_id"] == "s2"


def test_the_page_carries_a_pending_decision_badge() -> None:
    page = render_page()
    assert 'id="pending"' in page
    assert 'id="proposals-card"' in page


def test_the_badge_starts_hidden_so_a_quiet_queue_shows_nothing() -> None:
    assert 'id="pending" class="pending" href="#proposals-card" hidden' in render_page()


def test_the_badge_counts_proposals_and_decisions_together() -> None:
    page = render_page()
    assert "refreshPendingTotal" in page
    assert "(p.proposals||[]).length+(d.decisions||[]).length" in page
    assert "decisions waiting on you" in page
