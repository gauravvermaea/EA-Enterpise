"""R2.42 (D633; owner, 12 Nov 2026, 21:25 and 13 Nov 2026: the full split, schemas only): the library models' content in
the library_models schema, read from there by every screen. Checked on PostgreSQL on 13 Nov 2026: 12 library models
moved in 9 seconds (3,684 entities, 67,203 history rows; none left in core); a library model's metamodel, entity type,
history and ER diagram read on the library route; compared from a working model's request (766 entities); a working
model made from it with its content (766 entities, 575 relationships) in core with its own ids; the same with
EAX_LIBRARY_MODELS_DB_URL pointing at another existing database (ensure, copy, the directory copied beside it)."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_statements_are_rewritten_to_the_library_schema():
    from eax import library_models as lm
    sql = """SELECT e.name, m.name FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
             JOIN core.models m ON m.id = e.model_id LEFT JOIN history.row_versions h ON h.row_id = e.id
             WHERE core.can_read_model(e.model_id) AND e.name <> 'core.entities_x'"""
    out = lm.rewrite(sql)
    assert "library_models.entities e" in out and "library_models.entity_types t" in out
    assert "library_models.row_versions h" in out
    assert "core.models m" in out                              # the directory stays where it is
    assert "core.can_read_model(e.model_id)" in out            # same database: the repository's function
    assert "(e.model_id IS NOT NULL OR true)" in lm.rewrite(sql, apart=True)   # elsewhere: everyone signed in reads it
    assert "core.entities_x" in out                            # a longer name is not touched


def test_the_content_tables_match_the_migration_and_databases():
    from eax import databases as dbs
    from eax import library_models as lm
    sql = (REPO / "services/api/migrations/sql/0057_library_models.sql").read_text()
    for t in lm.CONTENT:
        assert f"'{t}'" in sql, t
    assert "LIKE history.row_versions INCLUDING ALL" in sql and "RESTART WITH 1000000000" in sql
    assert "content_schema" in sql and "CREATE DATABASE" not in sql.upper() and "CREATE TRIGGER" not in sql.upper()
    assert dbs.TABLES["library_models"] == tuple(f"library_models.{t}" for t in (*lm.CONTENT, "row_versions"))
    assert "core.models" in dbs.DIRECTORY and "core.commits" in dbs.DIRECTORY


def test_the_route_gives_the_library_engine(monkeypatch):
    from eax import db
    from eax import library_models as lm
    sentinel_lib, sentinel_base = object(), object()
    monkeypatch.setattr(lm, "engine", lambda: sentinel_lib)
    monkeypatch.setattr(db, "base_engine", lambda: sentinel_base)
    assert db.get_engine() is sentinel_base
    with lm.route(True):
        assert db.get_engine() is sentinel_lib
        with lm.route(False):
            assert db.get_engine() is sentinel_base
    assert db.get_engine() is sentinel_base
    assert lm.model_of({"model_id": "abc"}) == "abc" and lm.model_of({}, {"model": "x"}) == "x" and lm.model_of({}) is None


def test_requests_tasks_and_tools_are_routed():
    app = (REPO / "services/api/eax/app.py").read_text()
    assert "library_models.model_of(request.view_args, request.args)" in app and "reset_route(token)" in app
    tasks = (REPO / "services/api/eax/tasks.py").read_text()
    assert "library_models.route(lib)" in tasks and '"compare.run"' in tasks and '"project.created"' in tasks
    assert "library_models.route(library_models.is_library(model_arg) and not begin)" in (REPO / "services/api/eax/mcp_server.py").read_text()


def test_copies_and_comparisons_read_each_side_where_it_is():
    from eax import model_ops as mo
    from eax import tags
    assert "lm.copy_from_library(conn, src_guid, dst_id, content)" in inspect.getsource(mo.copy_into)
    assert "lm.reading(conn, src[\"id\"])" in inspect.getsource(mo.run_copy)
    assert "lm.move_in(conn, dst[\"id\"], actor)" in inspect.getsource(mo.run_copy)     # a new library model moves in
    assert "lm.reading(conn, model)" in inspect.getsource(tags.side_of_model)


def test_moving_is_all_or_nothing_and_by_the_installer():
    from eax import library_models as lm
    src = inspect.getsource(lm.move_all)
    assert "installer_engine().begin()" in src and "drop_core_history" in src
    mv = inspect.getsource(lm.move_in)
    assert mv.index("_copy(") < mv.index("_remove(") < mv.index("UPDATE core.models SET content_schema")
    assert "only library models move" in mv
    later = (REPO / "services/api/eax/seed/later.py").read_text()
    assert "library_models_in" in later and "eax.library_models_move" in (REPO / "services/api/eax/jobs.py").read_text()


def test_engines_cached_elsewhere_never_take_the_route():
    src = (REPO / "services/api/eax/databases.py").read_text()
    assert re.search(r"def engine_for.*?return base_engine\(\)", src, re.S)
    assert "return base_engine()" in (REPO / "services/api/eax/db.py").read_text().split("def get_projects_engine")[1]
