"""What the sidecar does when it finds the API port already taken."""

import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

# Nothing here should get as far as importing the app, but if a regression lets it, it must not open
# the developer's own database.
_SANDBOX_HOME = tempfile.mkdtemp(prefix="alembic-tests-")
os.environ["HOME"] = _SANDBOX_HOME
os.environ["USERPROFILE"] = _SANDBOX_HOME

app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "app"))
sys.path.append(app_dir)
import run_server  # noqa: E402

ALEMBIC_HOME_PAGE = json.dumps({"status": "ok", "message": "Alembic API"}).encode()


@pytest.fixture
def http_server():
    """Start a loopback server on a free port that answers every GET with `body`; returns the port."""
    servers = []

    def start(body):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_address[1]

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_a_sidecar_left_behind_is_recognised(http_server):
    port = http_server(ALEMBIC_HOME_PAGE)

    assert run_server.already_serving(port)
    assert run_server.is_alembic(port)


@pytest.mark.parametrize("body", [b"<html>a dev server</html>", b'{"message": "some other API"}', b"[]"])
def test_another_program_on_the_port_is_not_taken_for_alembic(http_server, body):
    port = http_server(body)

    assert run_server.already_serving(port)
    assert not run_server.is_alembic(port)


def test_a_listener_that_never_answers_is_not_taken_for_alembic():
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()  # the backlog completes the connection; nothing ever replies

        assert not run_server.is_alembic(silent.getsockname()[1], timeout=0.5)


def refuse_to_serve():
    raise AssertionError("must not start a second server")


def test_the_sidecar_steps_aside_for_one_left_behind(monkeypatch):
    monkeypatch.setattr(run_server, "already_serving", lambda port=run_server.PORT: True)
    monkeypatch.setattr(run_server, "is_alembic", lambda port=run_server.PORT, timeout=None: True)
    monkeypatch.setattr(run_server, "listening_sockets", refuse_to_serve)

    assert run_server.main() is None


def test_the_sidecar_fails_loudly_when_another_program_has_the_port(monkeypatch):
    """Stepping aside here would leave the window talking to a program that has never heard of
    Alembic, waiting minutes on a "Starting" screen with nothing in the log to say why."""
    monkeypatch.setattr(run_server, "already_serving", lambda port=run_server.PORT: True)
    monkeypatch.setattr(run_server, "is_alembic", lambda port=run_server.PORT, timeout=None: False)
    monkeypatch.setattr(run_server, "listening_sockets", refuse_to_serve)

    with pytest.raises(SystemExit) as exit_info:
        run_server.main()

    assert exit_info.value.code not in (0, None)
