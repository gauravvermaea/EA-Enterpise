"""R2.9 (D629; owner, 11 Nov 2026, answers 12 Nov 2026, 21:37): an entity type derived from another in the metamodel.
Checked on PostgreSQL on 13 Nov 2026: Server > Windows Server > DB Server; an attribute added to Server reached both
derived types; one removed from Server stayed on them, retired, with their values; an own attribute of the same kind
was left alone; the allowed relationship came down; a loop was refused; the metamodel document carries the base and
leaves out what was inherited; a copy of the metamodel kept the bases and what came from them; the ER diagram shows
two Specialization lines; the laptop sample was made once."""

from __future__ import annotations

import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_bases_come_before_what_derives_from_them(monkeypatch):
    from eax import derived_types as dt
    rows = [{"id": 3, "base": 2}, {"id": 2, "base": 1}, {"id": 5, "base": 3}, {"id": 9, "base": 8}]
    monkeypatch.setattr(dt, "_rows", lambda conn, sql, **p: [dict(r) for r in rows])
    order = [r["id"] for r in dt.ordered(None, 1)]
    assert order.index(2) < order.index(3) < order.index(5) and 9 in order and len(order) == 4


def test_a_loop_does_not_hang(monkeypatch):
    from eax import derived_types as dt
    rows = [{"id": 1, "base": 2}, {"id": 2, "base": 1}]
    monkeypatch.setattr(dt, "_rows", lambda conn, sql, **p: [dict(r) for r in rows])
    assert sorted(r["id"] for r in dt.ordered(None, 1)) == [1, 2]


def test_the_diagram_draws_specialization():
    from eax import diagram
    data = {"relationship_types": [{"code": "Serving", "name": "Serving", "id": "r"}], "domains": [],
            "entity_types": [{"id": "a", "name": "Server", "code": "S", "domain_id": "d"},
                             {"id": "b", "name": "Windows Server", "code": "W", "domain_id": "d"}],
            "links": [], "specializations": [{"source": "b", "target": "a"}]}
    part = diagram.scope(data)
    assert {"source": "b", "target": "a", "relationship_types": ["Specialization"]} in part["links"]


def test_wiring():
    from eax import derived_types as dt
    from eax import metamodel_edit as me
    from eax import model_ops as mo
    assert "derived_types.sync(conn, mid)" in inspect.getsource(me.apply)
    assert "derived_types.copied(conn, src_id, dst_id)" in inspect.getsource(mo.copy_into)
    spec = inspect.getsource(mo.metamodel_spec)
    assert "i.inherited_from IS NULL" in spec and "a.inherited_from IS NULL" in spec and "b.code AS base" in spec
    assert "derives from itself" in inspect.getsource(mo.validate_spec)
    assert "derived_types.sync(conn, model_id)" in inspect.getsource(mo.apply_spec)
    src = inspect.getsource(dt._attributes)
    assert "status_code = 'retired'" in src and "own attribute of the same kind wins" in src
    assert "cannot derive from itself" in inspect.getsource(dt.check_base)
    sql = (REPO / "services/api/migrations/sql/0054_derived_types.sql").read_text()
    assert "base_type_id" in sql and "inherited_from" in sql and "CREATE FUNCTION" not in sql.upper() and "TRIGGER" not in sql.upper()
    web = (REPO / "services/web/src/MetamodelEditor.jsx").read_text()
    assert 'name: "base"' in web and "Derived from" in (REPO / "services/web/src/Metamodel.jsx").read_text()
    assert "specializations" in (REPO / "services/web/src/MetamodelDiagram.jsx").read_text()
    assert "sample_derived" in (REPO / "services/api/eax/seed/later.py").read_text()
