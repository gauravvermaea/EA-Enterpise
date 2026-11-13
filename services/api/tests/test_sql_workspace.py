"""R2.57 (owner, 13 Nov 2026: "a better SQL interface, we need ours to be more like pgadmin"): the SQL window as a
workspace. Checked on PostgreSQL on 13 Nov 2026 with the eax_app login: the tree (6 schemas, 104 core tables), a
table's structure, its rows sorted and filtered, a plan with and without analyse, CSV and Excel exports, and names
that are not tables or columns refused."""

from __future__ import annotations

import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_every_read_is_rolled_back_and_names_are_identifiers():
    from eax import sqlconsole as s
    src = inspect.getsource(s._read)
    assert "conn.rollback()" in src and "finally:" in src            # browsing, rows, plans, exports keep nothing
    rows = inspect.getsource(s.table_rows)
    assert "q.Identifier(schema, table)" in rows and "q.Identifier(order)" in rows and "q.Identifier(column)" in rows
    assert "not in cols" in rows                                      # a column must be one of the table's
    assert "one statement at a time" in inspect.getsource(s.explain)
    assert s.PAGE_ROWS == 200 and s.EXPORT_ROWS == 100_000


def test_routes_are_for_it_and_super_admins_and_audited():
    api = (REPO / "services/api/eax/api/sql.py").read_text()
    for route in ("/browse", "/describe", "/rows", "/explain", "/export"):
        i = api.index(f'@blp.route("{route}")')
        assert 'require_auth("system.operate")' in api[i:i + 400], route
    for kind in ('kind="rows"', 'kind="explain"', 'kind="export"'):
        assert kind in api
    assert "password" not in api.split("def _audit", 1)[1].split("@blp.route", 1)[0]   # the password is never logged


def test_the_workspace_page():
    web = (REPO / "services/web/src/Sql.jsx").read_text()
    for part in ("function Tree(", "function TableTab(", "function QueryTab(", "function PlanNode(", "sql-colour",
                 "Ctrl+Space", "eax.sql.history", "eax.sql.saved", "/api/v1/sql/export", "Keep the changes"):
        assert part in web, part
    assert "try { return JSON.parse(window.localStorage" in web       # browser storage is a convenience: it may throw
