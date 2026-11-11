"""Relationship attributes (0.19.0, D563 to D565): attributes on a relationship type (every allowed relationship of it)
or on one allowed relationship only (source type + relationship type + target type), their values, how they travel in
the metamodel workbook and the model package, the demo estate's seed, the commits op, MCP, the self-test check and the
ER diagram. No database needed."""

from __future__ import annotations

import io
import re
from pathlib import Path

from eax import commits as cm
from eax import diagram
from eax import metamodel_workbook as wb
from eax import model_ops as mo
from eax.seed import build as B
from eax.seed import demo_estate as D
from eax.testing import db_checks

API = Path(__file__).resolve().parents[1]
SQL = (API / "migrations" / "sql" / "0047_relationship_attributes.sql").read_text()
VERSION = (API / "migrations" / "versions" / "0047_relationship_attributes.py").read_text()


# ---------------------------------------------------------------- migration
def test_migration_is_rows_only_and_follows_0046():
    assert 'down_revision = "0046_industry_packs"' in VERSION and 'revision = "0047_relationship_attributes"' in VERSION
    assert "CREATE TABLE core.item_attribute_mappings" in SQL
    for col in ("item_attribute_id", "allowed_relationship_id", "is_required", "guid", "is_deleted"):
        assert col in SQL, col
    assert "item_attribute_mappings_uq" in SQL and "WHERE NOT is_deleted" in SQL
    assert "('0.19.0', '0047_relationship_attributes'" in SQL
    # no logic in the database (D248)
    assert not re.search(r"CREATE (OR REPLACE )?(FUNCTION|TRIGGER)", SQL, re.I)
    # every foreign key has an index (the self-test warns otherwise)
    for col in ("allowed_relationship_id", "model_id"):
        assert re.search(rf"ON core\.item_attribute_mappings \({col}\)", SQL), col


# ---------------------------------------------------------------- demo estate
def test_demo_estate_relationship_attributes_are_consistent():
    allowed = {(s, r, t) for s, r, t, _n in B.expand_allowed()}
    codes = {c for c, *_ in D.REL_ATTRS}
    for s, r, t, a, _req in D.REL_MAPPING_ATTRS:
        assert (s, r, t) in allowed and a in codes
    assert ("Node", "Association", "Node", "ConnectionProtocol", True) in D.REL_MAPPING_ATTRS
    assert {a for s, r, t, a, _q in D.REL_MAPPING_ATTRS
            if (s, r, t) == ("ApplicationComponent", "Flow", "ApplicationComponent")} == {"Frequency", "DataVolume"}
    assert ("Serving", "SLA", False) in D.REL_TYPE_ATTRS
    assert set(D.REL_PICK_LISTS["ConnectionProtocol"][1]) == {"HTTPS", "SFTP", "MQ", "JDBC"}
    types = {n: t for t, n, *_ in D.E}
    for (src, kind, tgt), values in D.REL_VALUES.items():
        assert (src, kind, tgt) in set(D.R)
        mine = {a for s, r, t, a, _q in D.REL_MAPPING_ATTRS if (s, r, t) == (types[src], kind, types[tgt])}
        mine |= {a for r, a, _q in D.REL_TYPE_ATTRS if r == kind}
        assert set(values) <= mine, (src, kind, tgt)
    # one required value left missing, so quality lists it
    missing = [(k, v) for k, v in D.REL_VALUES.items()
               if types[k[0]] == "Node" and types[k[2]] == "Node" and k[1] == "Association" and "ConnectionProtocol" not in v]
    assert missing
    # a physical element to a work package: an Association with no attributes of its own
    assert any(types[s] == "Equipment" and r == "Association" and types[t] == "WorkPackage" for s, r, t in D.R)
    assert not [m for m in D.REL_MAPPING_ATTRS if m[:3] == ("Equipment", "Association", "WorkPackage")]


def test_demo_estate_sql_has_items_mappings_and_values():
    sql = B.demo_relationship_attributes_sql(D.DEMO_KEY, B.gid("model", D.DEMO_KEY))
    assert "INSERT INTO core.item_attribute_mappings" in sql
    assert "INSERT INTO core.item_attributes" in sql and "relationship_type_id" in sql
    assert "'SFTP'" in sql and "'99.9% around the clock'" in sql
    # the mapping rows point at the item of their relationship type and attribute
    item = B.gid(D.DEMO_KEY, "item_attribute", "rel", "Association", "ConnectionProtocol")
    assert item in sql
    assert "demo_relationship_attributes_sql(k, m)" in (API / "eax" / "seed" / "build.py").read_text()


# ---------------------------------------------------------------- the metamodel workbook and the package
def _spec():
    s = mo.empty_spec("Test", "", "")
    s["attributes"] = [{"code": "Port", "name": "Port", "data_type": "integer"},
                       {"code": "SLA", "name": "SLA", "data_type": "text"}]
    s["entity_types"] = [{"code": "Node", "name": "Node", "domain": "tech", "attributes": []},
                         {"code": "WorkPackage", "name": "Work package", "domain": "impl", "attributes": []}]
    s["relationship_types"] = [{"code": "Association", "name": "Association", "directed": False,
                                "attributes": [{"attribute": "SLA", "required": False}]}]
    s["allowed"] = [{"source": "Node", "relationship": "Association", "target": "Node", "note": "",
                     "attributes": [{"attribute": "Port", "required": True}]},
                    {"source": "Node", "relationship": "Association", "target": "WorkPackage", "note": ""}]
    return s


class _Conn:
    def execute(self, *_a, **_k):
        class R:
            def mappings(self):
                return self

            def all(self):
                return []
        return R()


def test_metamodel_workbook_round_trips_mapping_attributes(monkeypatch):
    monkeypatch.setattr(mo, "metamodel_spec", lambda conn, model: _spec())
    monkeypatch.setattr(wb.repo, "get_model", lambda conn, model: {"name": "Test", "description": ""})
    data, _name = wb.template(_Conn(), "m")
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(data))
    assert "Relationship attributes" in book.sheetnames
    back = wb.read(data)
    node_node = next(a for a in back["allowed"] if a["target"] == "Node")
    assert node_node["attributes"] == [{"attribute": "Port", "required": True}]
    assert not next(a for a in back["allowed"] if a["target"] == "WorkPackage").get("attributes")
    assert [i["attribute"] for i in back["relationship_types"][0]["attributes"]] == ["SLA"]


def test_workbook_merge_adds_mapping_attributes_and_never_takes_away():
    base = _spec()
    base["allowed"][0]["attributes"] = []
    add = _spec()
    out, what = wb.merge_specs(base, add)
    nn = next(a for a in out["allowed"] if a["target"] == "Node")
    assert nn["attributes"] == [{"attribute": "Port", "required": True}]
    assert what["allowed"]["changed"] == ["Node Association Node"]
    # an upload without them takes nothing away
    out2, _ = wb.merge_specs(out, mo.empty_spec())
    assert next(a for a in out2["allowed"] if a["target"] == "Node")["attributes"]


def test_model_package_xlsx_carries_mapping_attributes():
    spec = _spec()
    manifest = {"model": {"name": "Test"}, "format": mo.PACKAGE_FORMAT}
    data = mo._to_xlsx(manifest, spec, {"entities": {}, "relationships": []})
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(data))
    rows = list(book["Relationship attributes"].iter_rows(values_only=True))
    assert rows[0] == ("source", "relationship", "target", "attribute", "required")
    assert rows[1] == ("Node", "Association", "Node", "Port", "yes")


# ---------------------------------------------------------------- commits, MCP, self-test, diagram
def test_commit_op_touches_name_and_values():
    after = {"values": {"Port": 22}}
    assert cm._touched("relationship.rename", {"relationship": "x", "name": "n"}, after) == ["name"]
    assert cm._touched("relationship.rename", {"relationship": "x", "values": {"port": 23}}, after) == ["value:Port"]
    assert cm._touched("relationship.rename", {"relationship": "x", "name": "", "values": {"SLA": "1"}}, after) == \
        ["name", "value:SLA"]


def test_mcp_has_relationship_tools():
    from eax import mcp_server as ms
    names = {t.name for t in ms.mcp._tool_manager.list_tools()}
    assert {"get_relationship", "change_relationships"} <= names


def test_self_test_checks_mappings():
    assert any("relationship attributes" in name for name, _sql, _bad in db_checks.CHECKS)


def test_diagram_scope_keeps_mapping_attributes():
    data = {"entity_types": [{"id": "a", "name": "Node", "code": "Node", "domain": "tech", "domain_id": "d", "attributes": []}],
            "relationship_types": [{"code": "Association", "name": "Association"}, {"code": "Serving", "name": "Serving"}],
            "links": [{"source": "a", "target": "a", "relationship_types": ["Association", "Serving"],
                       "mapping_attributes": ["Connection protocol, Port", ""]}],
            "domains": []}
    part = diagram.scope(data, include_generic=True)
    link = part["links"][0]
    assert link["mapping_attributes"] == {"Association": "Connection protocol, Port"}


def test_ends_changing_keeps_values():
    src = (API / "eax" / "content.py").read_text()
    assert "def carry_values(" in src and '"carry_values_from": r["id"]' in src
    assert '"carry_values_from": r["id"]' in (API / "eax" / "commits.py").read_text()
