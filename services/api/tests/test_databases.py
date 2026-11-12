"""R2.50 (D611; owner, 12 Nov 2026: "Keep it in same postgres DB, but ensure you have separate connection string for easy
to migrate. We need a setting in config for all the different DBs to have same or separate container")."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_every_database_has_a_setting_in_both_templates():
    from eax import databases as dbs
    for t in ("laptop", "server"):
        env = (REPO / f"deploy/templates/eaexplorer.{t}.env").read_text()
        for d in dbs.DATABASES:
            if d.key != "repository":
                assert f"\n{d.setting}=" in env or f"{d.setting}" in env, (t, d.setting)


def test_empty_means_the_shared_server_and_a_url_its_own(monkeypatch):
    from eax import databases as dbs
    t = dbs.BY_KEY["tests"]
    monkeypatch.delenv("EAX_TESTS_DB_URL", raising=False)
    assert not dbs.own(t) and dbs.where(t).startswith("shared server")
    monkeypatch.setenv("EAX_TESTS_DB_URL", "postgresql://u:secret@dbtests:5433/eaxtests")
    assert dbs.own(t) and dbs.where(t) == "dbtests:5433/eaxtests (its own)" and "secret" not in dbs.where(t)
    monkeypatch.setenv("EAX_TESTS_DB_URL", "postgresql://u:p@db:5432/eaexplorer")
    assert not dbs.own(t)                                           # the same database, written out
    monkeypatch.setenv("EAX_KEYCLOAK_DB_HOST", "kcdb")
    assert dbs.own(dbs.BY_KEY["keycloak"])
    assert dbs.sqlalchemy_url("postgresql://a:b@h/x") == "postgresql+psycopg://a:b@h/x"


def test_backups_find_every_database_on_its_own_server():
    env = {**os.environ, "PGHOST": "db", "PGPORT": "5432", "EAX_TESTS_DB_URL": "postgresql://u:p%5E@dbtests:5433/eaxtests",
           "EAX_ARCHIVE_DB_URL": "postgresql://u:p@db:5432/eaxarchive", "EAX_KEYCLOAK_DB_HOST": "kcdb", "EAX_MAYAN_DB_HOST": ""}
    out = subprocess.run(["sh", "-c", f". {REPO}/services/backup/servers.sh; own_servers"], capture_output=True, text=True, env=env)
    assert out.stdout.split("\n")[:2] == ["eaxtests dbtests 5433", "keycloak kcdb 5432"]
    backup = (REPO / "services/backup/backup.sh").read_text()
    restore = (REPO / "services/backup/restore.sh").read_text()
    assert ". /usr/local/bin/servers.sh" in backup and "own_servers >" in backup
    assert ". /usr/local/bin/servers.sh" in restore and "OWN=$(own_servers)" in restore


def test_the_services_take_their_database_host():
    compose = (REPO / "docker-compose.yml").read_text()
    assert "${EAX_KEYCLOAK_DB_HOST:-db}" in compose and "${EAX_MAYAN_DB_HOST:-db}" in compose and "EAX_SUPERSET_DB_HOST:" in compose
    assert "env('EAX_SUPERSET_DB_HOST')" in (REPO / "deploy/superset/superset_config.py").read_text()


def test_shown_on_the_web_and_the_command_line():
    assert '@blp.route("/admin/databases")' in (REPO / "services/api/eax/api/admin.py").read_text()
    assert '["databases", "Databases"' in (REPO / "services/web/src/Admin.jsx").read_text()
    for f in ("eax.sh", "eax.ps1", "eaxcli/main.py"):                       # eax in sync (D331)
        assert "eax.databases" in (REPO / f).read_text(), f
    assert "### databases" in (REPO / "eaxcli/help.txt").read_text()
    assert (REPO / "docs/databases.md").is_file()
