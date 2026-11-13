"""R2.28 (D613): the self-test's runs, results and fixtures records in the tests database (EAX_TESTS_DB_URL); empty =
the shared PostgreSQL, the same connection as before. Checked on PostgreSQL on 13 Nov 2026 with a database of its own:
its tables made identical to the shared ones (pg_dump -s), 34 runs and 9,022 results copied, runs read, reported,
deleted and their fixtures purged, the shared copies untouched."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services/api/eax"


def test_tests_is_the_same_connection_when_shared(monkeypatch):
    from eax.testing import store
    monkeypatch.delenv("EAX_TESTS_DB_URL", raising=False)
    conn = object()
    with store.tests(conn) as tc:
        assert tc is conn                                   # one transaction, as before R2.28
    monkeypatch.setenv("EAX_TESTS_DB_URL", "postgresql://u:p@dbtests:5432/eaxtests")
    assert store.separate()


class _Q:
    """A connection answering the catalogue queries of databases.plan from fixed rows."""
    def __init__(self, cols, cons, idx):
        self.cols, self.cons, self.idx = cols, cons, idx

    def execute(self, stmt, params=None):
        q, t = str(stmt), (params or {}).get("t")
        rows = (self.cols if "pg_attribute" in q else self.cons if "pg_constraint" in q and "conindid" not in q
                else self.idx).get(t, [])

        class R:
            def all(self_inner):
                return rows
        return R()


def test_plan_makes_and_aligns_the_tables():
    from eax import databases as dbs
    cols = {"core.a": [("id", "bigint", True, None, "a"), ("state", "text", True, "'queued'::text", "")],
            "core.b": [("id", "bigint", True, None, "a"), ("a_id", "bigint", True, None, "")]}
    cons = {"core.a": [("a_pkey", "PRIMARY KEY (id)", "p"), ("a_state_check", "CHECK ((state = 'x'::text))", "c")],
            "core.b": [("b_pkey", "PRIMARY KEY (id)", "p"), ("b_a_fkey", "FOREIGN KEY (a_id) REFERENCES core.a(id)", "f")]}
    idx = {"core.a": [("a_recent_idx", "CREATE INDEX a_recent_idx ON core.a USING btree (state)")]}
    shared = _Q(cols, cons, idx)
    fresh = dbs.plan(shared, _Q({}, {}, {}), ("core.a", "core.b"))
    assert fresh[0] == "CREATE SCHEMA IF NOT EXISTS core"
    assert 'CREATE TABLE core.a ("id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL, "state" text DEFAULT \'queued\'::text NOT NULL)' in fresh
    assert fresh[-1].startswith('ALTER TABLE core.b ADD CONSTRAINT "b_a_fkey" FOREIGN KEY')     # foreign keys last
    assert dbs.plan(shared, shared, ("core.a", "core.b")) == ["CREATE SCHEMA IF NOT EXISTS core"]   # in line: nothing
    # a later migration: a column, a changed check (a new suite, as 0052) and a dropped index
    old = _Q({"core.a": cols["core.a"][:1], "core.b": cols["core.b"]},
             {"core.a": [("a_pkey", "PRIMARY KEY (id)", "p"), ("a_state_check", "CHECK ((state = 'old'::text))", "c")],
              "core.b": cons["core.b"]},
             {"core.a": [("a_gone_idx", "CREATE INDEX a_gone_idx ON core.a USING btree (id)")]})
    steps = dbs.plan(shared, old, ("core.a", "core.b"))
    assert 'ALTER TABLE core.a ADD COLUMN "state" text DEFAULT \'queued\'::text NOT NULL' in steps
    assert steps.index('ALTER TABLE core.a DROP CONSTRAINT "a_state_check"') < steps.index(
        'ALTER TABLE core.a ADD CONSTRAINT "a_state_check" CHECK ((state = \'x\'::text))')
    assert 'DROP INDEX core."a_gone_idx"' in steps and idx["core.a"][0][1] in steps
    assert not any("DROP COLUMN" in x or "DROP TABLE" in x for x in steps)


def test_the_test_tables_are_reached_only_through_the_tests_database():
    """Every module that reads or writes core.test_* does it through store.engine() or store.tests(conn)."""
    from eax import databases as dbs
    assert dbs.TABLES["tests"] == ("tests.test_runs", "tests.test_results", "tests.test_fixtures")
    for f in sorted(API.rglob("*.py")):
        src = f.read_text()
        if "core.test_" not in src or "migrations" in str(f):
            continue
        if f.name in ("store.py", "repeat.py", "report.py", "test_lock.py", "__init__.py", "databases.py"):
            assert "get_engine" not in src or f.name == "databases.py", f   # these take the tests database's connection
            continue
        assert "store.engine()" in src or "store.tests(" in src, f
    run = inspect.getsource(__import__("eax.testing.run", fromlist=["x"]).cmd_run)
    assert "engine, repo = store.engine(), get_engine()" in run and "fixtures.models_and_project(repo" in run
    for f in ("auth.py", "api/heartbeat.py", "api/selftest_session.py", "jobs.py"):
        assert "store.engine()" in (API / f).read_text(), f


def test_every_start_makes_its_tables_and_copy_is_on_the_command_line():
    entry = (REPO / "services/api/entrypoint.sh").read_text()
    assert re.search(r"alembic upgrade head && python -m eax\.databases ensure &&", entry)
    assert "$ {eax} databases copy tests" in (REPO / "eaxcli/help.txt").read_text()
    assert "EAX_TESTS_DB_URL" in (REPO / "docs/databases.md").read_text()
