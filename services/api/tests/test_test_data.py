"""Test data (R2.11, D637): the self-test's models and projects are marked is_test_data and left out of the lists, each
run removes its own test data when it ends (passed, failed or stopped), and `eax test clean --dry-run` and the web's
Dry run list what would go without deleting anything."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]


def test_the_migration_adds_the_flag_and_nothing_else():
    sql = (API / "migrations" / "sql" / "0060_test_data_flag.sql").read_text(encoding="utf-8")
    assert "core.models ADD COLUMN IF NOT EXISTS is_test_data boolean NOT NULL DEFAULT false" in sql
    assert "proj.projects ADD COLUMN IF NOT EXISTS is_test_data boolean NOT NULL DEFAULT false" in sql
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()          # no logic in the database (D248)
    mig = (API / "migrations" / "versions" / "0060_test_data_flag.py").read_text(encoding="utf-8")
    assert 'down_revision = "0059_files_schema"' in mig and "DROP COLUMN IF EXISTS is_test_data" in mig


def test_only_the_self_tests_own_accounts_see_test_data_by_default():
    from eax import repository as repo
    assert repo.sees_test_data("svc-self-test-abc123-architect")
    assert repo.sees_test_data("SVC-SELF-TEST-x-super-admin")
    assert not repo.sees_test_data("alice") and not repo.sees_test_data("")


def test_the_model_list_leaves_test_data_out_unless_asked(monkeypatch):
    from eax import repository as repo
    seen = {}
    monkeypatch.setattr(repo, "_rows", lambda conn, sql, **p: seen.update(sql=sql, **p) or [])
    repo.list_models(None)
    assert "(:test_data OR NOT m.is_test_data)" in seen["sql"] and seen["test_data"] is False
    repo.list_models(None, test_data=True)
    assert seen["test_data"] is True
    assert "m.is_test_data" in repo._MODEL_SQL


def test_the_project_list_leaves_test_data_out_unless_asked(monkeypatch):
    from eax import projects as pj
    seen = {}
    monkeypatch.setattr(pj, "_rows", lambda conn, sql, **p: seen.update(sql=sql, **p) or [])
    monkeypatch.setattr(pj, "completion", lambda conn, ids: {})
    monkeypatch.setattr(pj, "_super", lambda u: True)
    user = type("U", (), {"username": "alice", "roles": ("super-admin",)})()
    pj.listing(None, user)
    assert "(:t OR NOT p.is_test_data)" in seen["sql"] and seen["t"] is False
    pj.listing(None, user, test_data=True)
    assert seen["t"] is True
    svc = type("U", (), {"username": "svc-self-test-abc-architect", "roles": ()})()
    pj.listing(None, svc)
    assert seen["t"] is True


def test_the_fixtures_are_marked_as_test_data():
    src = (API / "eax" / "testing" / "fixtures.py").read_text(encoding="utf-8")
    assert src.count("mark_model(engine, m") == 2                       # both models
    assert "UPDATE proj.projects SET is_test_data = true" in src         # and the project


class _Eng:
    def __init__(self):
        self.conn = object()

    def begin(self):
        return contextlib.nullcontext(self.conn)

    connect = begin


def test_each_run_removes_its_test_data_at_the_end(monkeypatch):
    from eax.testing import fixtures as fx
    calls, said = [], []
    monkeypatch.setattr(fx, "purge", lambda conn, rid, by: calls.append((rid, by)) or
                        {"models": 2, "projects": 1, "service_accounts": 3, "credentials": 3})
    out = fx.remove_at_end(_Eng(), 7, said.append)
    assert calls == [(7, "self-test (end of run)")] and out["models"] == 2 and "test data removed" in said[-1]
    monkeypatch.setenv("EAX_TEST_KEEP_DATA", "1")                      # kept to look into a failure
    assert fx.remove_at_end(_Eng(), 8, said.append) is None and len(calls) == 1 and "kept" in said[-1]
    monkeypatch.delenv("EAX_TEST_KEEP_DATA")

    def broken(*_a):
        raise RuntimeError("database gone")
    monkeypatch.setattr(fx, "purge", broken)
    assert fx.remove_at_end(_Eng(), 9, said.append) is None and "the next run removes it" in said[-1]


@pytest.mark.parametrize("error,stopped", [("", ""), ("boom", ""), ("", "Stopped by alice")])
def test_closing_a_run_removes_its_test_data_however_it_ended(monkeypatch, tmp_path, error, stopped):
    from eax.testing import fixtures as fx
    from eax.testing import run as R
    removed = []
    monkeypatch.setattr(fx, "remove_at_end", lambda repo, rid, log: removed.append(rid))
    monkeypatch.setattr(R.store, "finish", lambda conn, rid, e, s: "failed" if e else "stopped" if s else "passed")
    monkeypatch.setattr(R.repeat, "mark_followed_up", lambda conn, rid: False)
    monkeypatch.setattr(R.report, "to_html", lambda conn, rid: "")
    monkeypatch.setattr(R.report, "to_xlsx", lambda conn, rid: b"")
    monkeypatch.setattr(R.store, "run_detail", lambda conn, rid: (_ for _ in ()).throw(RuntimeError("no detail")))
    r = R.Run.__new__(R.Run)
    r.id, r.folder, r.dir, r.repo = 5, "f", tmp_path, _Eng()
    R._close(_Eng(), r, error, stopped)
    assert removed == [5]


def test_the_dry_run_lists_and_deletes_nothing():
    from eax.testing import fixtures as fx
    p = {"runs": [3], "running": [], "totals": {"model": 2, "project": 1},
         "fixtures": [{"id": 1, "run_id": 3, "kind": "model", "name": "self_test_x_1", "entities": 7, "relationships": 2,
                       "history_versions": 30},
                      {"id": 2, "run_id": 3, "kind": "project", "name": "self_test_x_3"}]}
    text = fx.preview_text(p)
    assert text.startswith("Dry run: nothing is deleted.") and "self_test_x_1 (7 entities, 2 relationships, 30 history" in text
    assert "2 model(s), 1 project(s)" in text
    assert fx.preview_text({"fixtures": []}) == "Dry run: no test data to remove."


def test_eax_test_clean_dry_run_does_not_purge(monkeypatch, capsys):
    from eax.testing import cli
    from eax.testing import fixtures as fx

    class Res:
        def __init__(self, v):
            self.v = v

        def all(self):
            return [(4,)]

        def scalar(self):
            return self.v

    class Conn:
        def execute(self, sql, params=None):
            return Res(3)
    eng = type("E", (), {"connect": lambda s: contextlib.nullcontext(Conn()), "begin": lambda s: contextlib.nullcontext(Conn())})()
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    monkeypatch.setattr(cli.store, "engine", lambda: eng)
    monkeypatch.setattr(cli.store, "runs", lambda conn, n: [])
    monkeypatch.setattr(fx, "purge", lambda *a, **k: pytest.fail("a dry run purged"))
    monkeypatch.setattr(fx, "preview", lambda conn, ids: {"runs": ids, "fixtures": [], "totals": {}, "running": []})
    src = (API / "eax" / "testing" / "cli.py").read_text(encoding="utf-8")
    assert '"--dry-run" in args' in src
    code = cli.main(["clean", "all", "--dry-run"])
    assert code == 0 and "Dry run" in capsys.readouterr().out


def test_the_web_purge_has_a_dry_run():
    src = (API / "eax" / "api" / "platform_tests.py").read_text(encoding="utf-8")
    i = src.index('if data.get("dry_run"):')
    assert i < src.index('if data.get("confirm") != "DELETE":')        # no DELETE needed, nothing queued
    assert "fx.preview(conn, runs)" in src[i:i + 1500] and "_task(" not in src[i:src.index('if data.get("confirm")')]
    web = (API.parent / "web" / "src" / "TestRuns.jsx").read_text(encoding="utf-8")
    assert "dry_run: true" in web and "Dry run (" in web
