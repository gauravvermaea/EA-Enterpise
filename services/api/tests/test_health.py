"""Service health checks, against small local stand-ins for the real services."""

import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eax import health


class _Handler(BaseHTTPRequestHandler):
    status = 200
    body = b"OK"

    def _answer(self):
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.body)

    do_GET = do_POST = _answer

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    def start(status=200, body=b"OK"):
        handler = type("H", (_Handler,), {"status": status, "body": body})
        srv = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return srv.server_address[1]
    started = []
    yield start
    for srv in started:
        srv.shutdown()


def test_http_up_down_and_unreachable(server):
    port = server(200, b"OK")
    assert health._http("X", "k", "127.0.0.1", port, "/")["status"] == "up"
    port = server(500)
    r = health._http("X", "k", "127.0.0.1", port, "/")
    assert r["status"] == "down" and "500" in r["detail"]
    with socket.socket() as s:  # a port nobody listens on
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert health._http("X", "k", "127.0.0.1", free, "/")["status"] == "down"


def test_custom_ok_rule(server):
    port = server(401)
    assert health._http("MCP", "k", "127.0.0.1", port, "/mcp", method="POST", ok=lambda s, b: s == 401)["status"] == "up"


def test_valkey_ping(monkeypatch):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                conn.sendall(b"+OK\r\n" if b"AUTH" in data else b"+PONG\r\n")
    threading.Thread(target=serve, daemon=True).start()
    real = socket.create_connection
    monkeypatch.setattr(health.socket, "create_connection",
                        lambda addr, timeout=None: real(("127.0.0.1", port), timeout=timeout))
    monkeypatch.setenv("EAX_DMS_BROKER_PASSWORD", "secret")
    assert health.check_dms_broker()["status"] == "up"
    srv.close()


def test_backup_age(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "BACKUP_DIR", tmp_path)
    assert health.check_backup()["status"] == "warning"  # no backup yet
    old = tmp_path / "20260101T020000Z"
    old.mkdir()
    (old / "manifest.json").write_text("{}")
    os.utime(old / "manifest.json", (time.time() - 72 * 3600,) * 2)
    r = health.check_backup()
    assert r["status"] == "warning" and "72 h ago" in r["detail"]
    new = tmp_path / "20260104T020000Z"
    new.mkdir()
    (new / "manifest.json").write_text("{}")
    assert health.check_backup()["status"] == "up"


def test_mcp_off(monkeypatch):
    monkeypatch.setenv("EAX_MCP_ENABLED", "false")
    assert health.check_mcp()["status"] == "off"


def test_overall_status(monkeypatch):
    def svc(name, status):
        return lambda: {"name": name, "kind": "", "status": status, "detail": "", "target": "", "response_ms": 1}
    monkeypatch.setattr(health, "CHECKS", [svc("Database", "up"), svc("Sign-in", "up"), svc("MCP server", "off")])
    assert health.check_all()["status"] == "ok"
    monkeypatch.setattr(health, "CHECKS", [svc("Database", "up"), svc("Backup", "warning")])
    r = health.check_all()
    assert r["status"] == "degraded" and r["counts"]["warning"] == 1
    monkeypatch.setattr(health, "CHECKS", [svc("Database", "down"), svc("Sign-in", "up")])
    assert health.check_all()["status"] == "down"
