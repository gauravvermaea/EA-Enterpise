"""Phase 9: the change log (no database needed; the database side is tests/sql/phase9_checks.sql)."""

import pathlib

from eax import change_log as cl

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_describe_rows():
    data = {"source": "data", "action": "Changed", "item_type": "Entity", "item_name": "CRM",
            "details": [{"field": "Owner", "old": "Sales", "new": "Service"}]}
    assert cl.describe(data) == "Changed entity 'CRM': Owner: Sales -> Service"
    api = {"source": "api", "action": "Tagged the model", "item_type": "Tag", "item_name": "Baseline 2026", "details": []}
    assert cl.describe(api) == "Tagged the model 'Baseline 2026'"


def test_logged_actions_are_not_row_changes():
    # rows the database logs (entities, values, relationships, metamodel parts) are never logged twice from the API
    for a in cl.ACTIONS:
        assert not a.startswith(("entity.", "attribute.", "relationship.", "rule.", "pick_list.", "metamodel.", "grid."))
    for a in ("sql.query", "model.downloaded", "merge.analyse", "heartbeat.recorded"):
        assert a not in cl.ACTIONS
    assert {"tag.create", "gap.create", "merge.apply", "changes.commit", "model.lock"} <= set(cl.ACTIONS)


def test_who_sees_what():
    class U:
        def __init__(self, roles):
            self.username, self.roles = "someone", roles
    where, p = cl._where(U([]), {"all": False, "models": [{"id": 7}]}, {})
    assert "lower(l.username) = :me" in where and p["admin"] == [7]
    where, _ = cl._where(U(["super-admin"]), {"all": True, "models": []}, {})
    assert where == "true"
    where, p = cl._where(U([]), {"all": True, "models": []}, {"user": "Bob", "from": "2026-11-01", "q": "crm", "mine": True})
    assert p["user"] == "bob" and ":from" in where and ":q" in where and "= :me" in where


def test_history_rows_become_entries():
    names = {"entity": {1: {"guid": "g-1", "name": "CRM", "type_name": "Application Component"},
                        2: {"guid": "g-2", "name": "Billing", "type_name": "Application Component"}},
             "etype": {5: {"name": "Application Component"}}, "rtype": {9: {"name": "Flow", "verb": "flows to"}},
             "attr": {3: {"name": "Owner"}}, "model": {7: {"guid": "m-7", "name": "Protea"}}, "rel": {}}
    base = {"row_guid": "x", "model_id": 7, "changed_at": "2026-11-05 10:00", "changed_by": "Bob"}
    v = cl.entry_of({**base, "table_name": "attribute_values", "operation": "update",
                     "data": {"entity_id": 1, "attribute_type_id": 3, "value_text": "Service"},
                     "prev": {"entity_id": 1, "attribute_type_id": 3, "value_text": "Sales"}}, names)
    assert v["item_name"] == "CRM" and v["item_type"] == "Entity" and v["details"] == [{"field": "Owner", "old": "Sales", "new": "Service"}]
    assert v["username"] == "bob" and v["model_name"] == "Protea"
    e = cl.entry_of({**base, "table_name": "entities", "operation": "update", "row_guid": "g-1",
                     "data": {"name": "CRM 2", "entity_type_id": 5, "modified_at": "b"},
                     "prev": {"name": "CRM", "entity_type_id": 5, "modified_at": "a"}}, names)
    assert e["action"] == "Changed" and e["details"] == [{"field": "Name", "old": "CRM", "new": "CRM 2"}]
    assert cl.entry_of({**base, "table_name": "entities", "operation": "update", "data": {"name": "A", "modified_at": "b"},
                        "prev": {"name": "A", "modified_at": "a"}}, names) is None   # only technical fields: no entry
    r = cl.entry_of({**base, "table_name": "relationships", "operation": "insert",
                     "data": {"relationship_type_id": 9, "source_entity_id": 1, "target_entity_id": 2}}, names)
    assert r["action"] == "Added" and r["item_name"] == "CRM flows to Billing"
    merged = cl._merge({**e, "action": "Created", "details": []}, v)
    assert merged["action"] == "Created" and len(merged["details"]) == 1


def test_web_and_migration():
    src = (WEB / "ChangeLog.jsx").read_text(encoding="utf-8")
    for bit in ("/api/v1/change-log", "/change-log/export", "/change-log/delete", "Type DELETE to confirm"):
        assert bit in src, bit
    assert "#/change-log" in (WEB / "App.jsx").read_text(encoding="utf-8")
    sql = (ROOT / "migrations" / "sql" / "0015_change_log.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN tx" in sql and "'0.9.0'" in sql and "CREATE TABLE" not in sql   # the log itself: its own database
    assert "python -m eax.change_log" in (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
