"""R2.2 (D634; owner, 10 Nov 2026 and 12-13 Nov 2026): each person's remote instances (the site picker), opened in their
own screens; a Super Admin's recorded SSH session to the host; how they sign in to the host a configuration option.
Checked on PostgreSQL on 13 Nov 2026: an instance added, a second with the same name and an ftp address refused, listed,
SSH refused to a person who is not a Super Admin, the request built in ask mode, a key kept encrypted and read back in
stored mode and refused in ask mode, removed; the operations helper's ticket wrote the session's key 0600, refused a bad
host and pointed the transcript at work/ssh-sessions/<session>.log."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_the_mode_is_a_configuration_option(monkeypatch):
    from eax import remote_instances as ri
    monkeypatch.delenv("EAX_REMOTE_SSH_AUTH", raising=False)
    assert ri.auth_mode() == "ask"
    for m in ("stored", "server_key", "ask"):
        monkeypatch.setenv("EAX_REMOTE_SSH_AUTH", m)
        assert ri.auth_mode() == m
    monkeypatch.setenv("EAX_REMOTE_SSH_AUTH", "anything")
    assert ri.auth_mode() == "ask"
    for env in ("eaexplorer.laptop.env", "eaexplorer.server.env"):
        t = (REPO / "deploy/templates" / env).read_text()
        assert "EAX_REMOTE_SSH_AUTH=ask" in t and "EAX_REMOTE_SECRET_KEY=" in t


def test_a_kept_key_is_encrypted(monkeypatch):
    from eax import remote_instances as ri
    from eax.metamodel_edit import EditError
    monkeypatch.setenv("EAX_REMOTE_SECRET_KEY", "")
    with pytest.raises(EditError):
        ri.encrypt("x")
    monkeypatch.setenv("EAX_REMOTE_SECRET_KEY", "a-long-enough-secret")
    blob = ri.encrypt("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert b"PRIVATE" not in blob and ri.decrypt(blob) == "-----BEGIN OPENSSH PRIVATE KEY-----"


def test_what_is_checked():
    from eax import remote_instances as ri
    from eax.metamodel_edit import EditError
    assert ri._clean({"name": "Staging", "url": "https://staging.example.com/"})["url"] == "https://staging.example.com"
    for bad in ({"name": "", "url": "https://x.example"}, {"name": "A", "url": "ftp://x"}, {"name": "A", "url": "https://x", "ssh_host": "a b"},
                {"name": "A", "url": "https://x", "ssh_port": 70000}, {"name": "A", "url": "https://x", "ssh_user": "me;rm"}):
        with pytest.raises(EditError):
            ri._clean(bad)
    assert "Only a Super Admin" in inspect.getsource(ri.ssh_request)


def test_the_operations_helper_holds_and_records_the_session():
    ops = (REPO / "services/ops/ops.py").read_text()
    assert "def ssh_ticket(" in ops and '"StrictHostKeyChecking=accept-new"' in ops and "os.O_CREAT | os.O_TRUNC, 0o600" in ops
    assert 'os.path.join(SSH_LOGS, f"{sid}.log")' in ops and 'os.remove(t["cleanup"])' in ops
    assert '"/ssh/ticket"' in ops and '"/ssh/public-key"' in ops and '"/ssh/sessions/"' in ops
    assert "openssh-client" in (REPO / "services/ops/Dockerfile").read_text()


def test_the_routes_the_list_and_the_picker():
    api = (REPO / "services/api/eax/api/remote_instances.py").read_text()
    assert '@personal_blp.route("/remote-instances")' in api and '@blp.route("/remote-instances/<uuid:ident>/ssh")' in api
    assert "INSERT INTO operations.ssh_sessions" in api and '"remote.ssh.open"' in api
    sql = (REPO / "services/api/migrations/sql/0058_remote_instances.sql").read_text()
    assert "personal.remote_instances" in sql and "operations.ssh_sessions" in sql
    from eax import change_log, databases
    assert "remote.ssh.open" in change_log.ACTIONS and "remote.ssh.close" in change_log.ACTIONS
    assert "personal.remote_instances" in databases.TABLES["personal"] and "operations.ssh_sessions" in databases.TABLES["operations"]
    menu = (REPO / "services/web/src/menu.js").read_text()
    assert 'dynamic: "sites"' in menu
    assert '"/api/v1/me/remote-instances"' in (REPO / "services/web/src/TopMenu.jsx").read_text()
