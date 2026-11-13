"""R2.44 (D635; owner, 12 Nov 2026, 21:28-21:47): EA Explorer on a container platform with no local file system and no
Docker socket, with the same code on one laptop. Checked on PostgreSQL on 13 Nov 2026: with EAX_FILE_STORE=database a
run's folder (a log and a video in a sub-folder) went into the file store, was listed, read and deleted, and a name
with .. was refused."""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def test_settings_come_from_the_environment_or_docker_secrets(tmp_path, monkeypatch):
    from eax import config
    monkeypatch.setattr(config, "SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("EAX_TEST_SECRET_X", raising=False)
    monkeypatch.delenv("EAX_TEST_SECRET_X_FILE", raising=False)
    assert config._env("EAX_TEST_SECRET_X", "d") == "d"
    (tmp_path / "EAX_TEST_SECRET_X").write_text("from-secret\n")
    assert config._env("EAX_TEST_SECRET_X") == "from-secret"
    f = tmp_path / "other"
    f.write_text("from-file")
    monkeypatch.setenv("EAX_TEST_SECRET_X_FILE", str(f))
    assert config._env("EAX_TEST_SECRET_X") == "from-file"
    monkeypatch.setenv("EAX_TEST_SECRET_X", "from-env")
    assert config._env("EAX_TEST_SECRET_X") == "from-env"          # the environment first


def test_the_file_store_setting(monkeypatch):
    from eax import filestore
    monkeypatch.delenv("EAX_FILE_STORE", raising=False)
    assert filestore.mode() == "folder"
    monkeypatch.setenv("EAX_FILE_STORE", "database")
    assert filestore.in_database()
    for bad in ("../x", "/etc/passwd", ""):
        with pytest.raises(ValueError):
            filestore._check("tests", bad)
    with pytest.raises(ValueError):
        filestore._check("backups", "x")                        # backups never go into a database
    sql = (REPO / "services/api/migrations/sql/0059_files_schema.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS files.store" in sql and "CREATE DATABASE" not in sql.upper()
    from eax import databases
    assert databases.TABLES["files"] == ("files.store",)


def test_the_screens_and_the_runner_use_the_store():
    src = (REPO / "services/api/eax/testing/run.py").read_text()
    assert "filestore.put_folder('tests', r.dir, r.folder)" in src
    pt = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert 'filestore.get("tests", f"{folder}/{name}")' in pt and 'filestore.listing("tests", pre)' in pt
    assert 'filestore.delete("tests", f)' in pt
    assert 'filestore.put("exports"' in (REPO / "services/api/eax/model_ops.py").read_text()


def test_no_socket_the_runner_waits_for_runs(monkeypatch):
    from eax.testing import waiter
    monkeypatch.setenv("EAX_PLATFORM", "managed")
    assert waiter.platform_managed()
    monkeypatch.setenv("EAX_PLATFORM", "compose")
    assert not waiter.platform_managed()
    argv = waiter.argv_for({"id": 7, "level": "detailed", "suites": ["api", "security"], "role": "", "area": "", "watch": False,
                            "journeys": [], "pages_only": False, "repeat_of": None, "repeat_warnings": False,
                            "started_by": "sa"}, "20261113T000000Z-run7")
    assert "--run-id" in argv and "7" in argv and "api" in argv[argv.index("--suites") + 1]
    assert "security" not in argv[argv.index("--suites") + 1]       # the scanners need the Docker socket
    assert "FOR UPDATE SKIP LOCKED" in inspect.getsource(waiter.take)
    pt = (REPO / "services/api/eax/api/platform_tests.py").read_text()
    assert pt.count("waiter.platform_managed()") == 2
    import yaml
    svc = yaml.safe_load((REPO / "docker-compose.yml").read_text())["services"]["testrunner-service"]
    assert svc["profiles"] == ["platform"] and svc["entrypoint"][-1] == "eax.testing.waiter"
    for f in ("CommandCentre.jsx", "ContainerConsole.jsx"):
        assert "<PlatformNotice />" in (REPO / "services/web/src" / f).read_text()


def test_backups_need_a_folder_on_a_server(monkeypatch):
    from eax import backup_folder, config
    config.get_settings.cache_clear() if hasattr(config.get_settings, "cache_clear") else None
    monkeypatch.setenv("EAX_DEPLOYMENT", "server")
    monkeypatch.delenv("EAX_BACKUP_DIR", raising=False)
    if hasattr(config.get_settings, "cache_clear"):
        config.get_settings.cache_clear()
    ok, why = backup_folder.ready()
    assert not ok and "EAX_BACKUP_DIR" in why
    monkeypatch.setenv("EAX_BACKUP_DIR", "/mnt/backups")
    assert backup_folder.ready()[0]
    monkeypatch.setenv("EAX_DEPLOYMENT", "laptop")
    monkeypatch.delenv("EAX_BACKUP_DIR", raising=False)
    if hasattr(config.get_settings, "cache_clear"):
        config.get_settings.cache_clear()
    assert backup_folder.ready()[0]
    os.environ.pop("EAX_DEPLOYMENT", None)
    if hasattr(config.get_settings, "cache_clear"):
        config.get_settings.cache_clear()
    assert "backup_folder.ready()" in (REPO / "services/api/eax/api/backups.py").read_text()
    assert "backup_folder.ready()" in (REPO / "services/api/eax/jobs.py").read_text()
    compose = (REPO / "docker-compose.yml").read_text()
    assert compose.count("${EAX_BACKUP_DIR:-./work/backups}") == 3
    for cli in ("eax.sh", "eax.ps1", "eaxcli/main.py"):
        assert "EAX_BACKUP_DIR" in (REPO / cli).read_text(), cli
