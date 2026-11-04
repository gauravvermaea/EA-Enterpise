"""Data entry (build phase 6): create and change entities, their values and relationships.

Every save is visible to everyone at once; there are no commits yet (D61). The database decides who may
change what (core.refuse_unpermitted: Architects, Model Sub Admins and Model Admins on the model; locked
models and retired types refuse). Validation rules warn, never block (D48): a value saved although it
fails a rule keeps the rules it fails (attribute_values.rule_override) and the answer lists the warnings.
A relationship the metamodel does not allow can still be added when asked: it adds the mapping to the
model's metamodel, flagged as added from content (D49, core.allow_from_content).

Functions take an open transaction (engine.begin()) and the signed-in person's name.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import repository as repo
from .metamodel_edit import EditError, _db_message

STORAGE = {"text": "value_text", "long_text": "value_text", "list": "value_text", "url": "value_text",
           "email": "value_text", "integer": "value_number", "decimal": "value_number", "currency": "value_number",
           "percent": "value_number", "date": "value_date", "boolean": "value_bool", "entity_ref": "value_ref"}


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    rows = _rows(conn, sql, **p)
    return rows[0] if rows else None


def _exec(conn, sql: str, **p):
    try:
        return conn.execute(text(sql), p)
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403 if "Not allowed" in str(exc.orig) else 409) from exc


def _model(conn, model: Any) -> dict:
    m = repo.get_model(conn, model)
    if m["kind"] == "template":
        raise EditError("A template model holds a metamodel only: it has no entities to enter.", 409)
    if m.get("is_locked"):
        raise EditError(f"Model {m['name']!r} is locked (read-only). Make a copy of it to work on.", 409)
    return m


def _entity_row(conn, m: dict, entity: Any) -> dict:
    e = repo._find_entity(conn, m, entity)
    return e


def _entity_id(conn, m: dict, ref: Any, what: str = "entity") -> int | None:
    if ref in (None, ""):
        return None
    guid = repo._as_guid(ref)
    row = _one(conn, f"""SELECT id FROM core.entities WHERE model_id = :m AND NOT is_deleted AND
                         {'guid = :r' if guid else '(lower(display_id) = lower(:r) OR lower(name) = lower(:r))'}
                         ORDER BY display_id LIMIT 1""", m=m["_id"], r=guid or str(ref))
    if not row:
        raise EditError(f"No {what} {ref!r} in this model.", 404)
    return row["id"]


# ---------------------------------------------------------------- the form: a type's fields
def form(conn, model: Any, entity_type: Any) -> dict:
    """What a form for one entity type shows: the built-in fields and every attribute of the type in
    its sections, with data type, unit, whether it is required, pick-list values and, for links to
    entities, which type they link to; plus the type's rules (to warn as people type) and whether the
    type is retired (no new entities, D87)."""
    m = repo.get_model(conn, model)
    et = repo._find_type(conn, m["_id"], entity_type)
    tid = et["_id"]
    attrs = _rows(conn, """
        SELECT at.code, at.name, at.description, at.data_type_code AS data_type, dt.name AS data_type_name, at.unit,
               ia.is_required, coalesce(nullif(ia.section, ''), 'General') AS section, at.pick_list_id AS _pick
          FROM core.item_attributes ia
          JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_types dt ON dt.code = at.data_type_code
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted
         ORDER BY ia.sort_order, at.name""", t=tid)
    picks: dict[int, list[str]] = {}
    ids = [a["_pick"] for a in attrs if a["_pick"]]
    if ids:
        for p in _rows(conn, """SELECT pick_list_id, array_agg(value ORDER BY sort_order) AS v FROM core.pick_list_values
                                 WHERE pick_list_id = ANY (:i) AND NOT is_deleted GROUP BY pick_list_id""", i=ids):
            picks[p["pick_list_id"]] = list(p["v"])
    for a in attrs:
        a["pick_list_values"] = picks.get(a.pop("_pick"), [])
    rules = repo._rules_for_type(conn, m["_id"], tid)
    status = _one(conn, "SELECT status_code FROM core.entity_types WHERE id = :t", t=tid)["status_code"]
    return {"model": {"id": m["id"], "name": m["name"], "is_locked": m.get("is_locked"), "kind": m["kind"]},
            "entity_type": {k: v for k, v in et.items() if not k.startswith("_")}, "retired": status == "retired",
            "attributes": attrs, "rules": rules,
            "fields": [{"code": "name", "name": "Name", "required": True}, {"code": "description", "name": "Description"},
                       {"code": "parent", "name": "Part of (parent)"}, {"code": "tags", "name": "Tags"}]}


# ---------------------------------------------------------------- values
def _coerce(attr: dict, value: Any) -> Any:
    """A value from a form, as the database stores it for the attribute's data type; None clears it."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    t, name = attr["data_type"], attr["name"]
    try:
        if t in ("integer", "decimal", "currency", "percent"):
            n = Decimal(str(value).replace(",", "").replace(" ", "").rstrip("%"))
            if t == "integer" and n != n.to_integral_value():
                raise EditError(f"{name} holds whole numbers.")
            return n
        if t == "date":
            return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value).strip()[:10])
        if t == "boolean":
            if isinstance(value, bool):
                return value
            v = str(value).strip().lower()
            if v in ("yes", "true", "1", "y"):
                return True
            if v in ("no", "false", "0", "n"):
                return False
            raise ValueError(value)
    except (InvalidOperation, ValueError) as exc:
        raise EditError(f"{name}: {value!r} is not a {attr.get('data_type_name') or t} value.") from exc
    if t == "list" and attr.get("pick_list_values") and str(value) not in attr["pick_list_values"]:
        raise EditError(f"{name}: {value!r} is not in its pick list ({', '.join(attr['pick_list_values'])}).")
    return str(value).strip() if isinstance(value, str) else value


def _set_values(conn, m: dict, eid: int, tid: int, values: dict[str, Any]) -> list[str]:
    """Writes the given attribute values (by attribute code); a missing or empty value clears it. Returns
    the codes changed."""
    if not values:
        return []
    attrs = {a["code"].lower(): a for a in _rows(conn, """
        SELECT at.id, at.code, at.name, at.data_type_code AS data_type, dt.name AS data_type_name, at.pick_list_id
          FROM core.item_attributes ia JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_types dt ON dt.code = at.data_type_code
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted""", t=tid)}
    changed = []
    for code, raw in values.items():
        a = attrs.get(str(code).lower())
        if not a:
            raise EditError(f"{code!r} is not an attribute of this entity's type.")
        if a["pick_list_id"]:
            a["pick_list_values"] = [r["value"] for r in _rows(conn, """SELECT value FROM core.pick_list_values
                                       WHERE pick_list_id = :p AND NOT is_deleted""", p=a["pick_list_id"])]
        column = STORAGE.get(a["data_type"], "value_text")
        value = _entity_id(conn, m, raw, "linked entity") if column == "value_ref" else _coerce(a, raw)
        current = _one(conn, f"""SELECT id, {column} AS v FROM core.attribute_values
                                  WHERE entity_id = :e AND attribute_type_id = :a AND NOT is_deleted""", e=eid, a=a["id"])
        if value is None:
            if current:
                _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE id = :i", i=current["id"])
                changed.append(a["code"])
            continue
        if current and current["v"] == value:
            continue
        if current:
            _exec(conn, f"UPDATE core.attribute_values SET {column} = :v, rule_override = NULL WHERE id = :i",
                  v=value, i=current["id"])
        else:
            _exec(conn, f"""INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, {column})
                            VALUES (:m, :a, :e, :v)""", m=m["_id"], a=a["id"], e=eid, v=value)
        changed.append(a["code"])
    return changed


def _check(conn, m: dict, eid: int, tid: int, actor: str, changed: list[str]) -> list[dict]:
    """Runs the type's rules on the saved entity (D48): the warnings, and on each value just saved that
    fails a rule, the override flag with the rules' details."""
    e = _one(conn, "SELECT name, description, display_id FROM core.entities WHERE id = :e", e=eid)
    attrs = repo._load_values(conn, "e.id = :e", e=eid).get(eid, [])
    rules = repo._rules_for_type(conn, m["_id"], tid)
    dup = _one(conn, """SELECT count(*) AS n FROM core.entities WHERE model_id = :m AND entity_type_id = :t
                         AND NOT is_deleted AND lower(name) = lower(:n) AND id <> :e""",
               m=m["_id"], t=tid, n=e["name"], e=eid)["n"] > 0
    rels = repo._relationships_by_entity(conn, [eid]).get(eid, []) \
        if any(r["rule_type_code"] == "has_relationship" for r in rules) else []
    warnings = repo._warnings({**e, "relationships": rels}, attrs, rules, {e["name"].lower()} if dup else set())
    if dup and not any(w["rule"] == "unique" and w["code"].lower() == "name" for w in warnings):
        warnings.append({"field": "Name", "code": "name", "rule": "duplicate", "severity": "warning",
                         "message": f"Another {_type_name(conn, tid)} in this model is also called {e['name']!r}"})
    by_code: dict[str, list[dict]] = {}
    for w in warnings:
        by_code.setdefault(w["code"].lower(), []).append(w)
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    for code in changed:
        failed = by_code.get(code.lower())
        if failed:
            _exec(conn, """UPDATE core.attribute_values av SET rule_override = CAST(:o AS jsonb)
                            FROM core.attribute_types at
                           WHERE av.entity_id = :e AND NOT av.is_deleted AND at.id = av.attribute_type_id
                             AND lower(at.code) = lower(:c)""",
                  o=json.dumps({"rules": failed, "by": actor, "at": now}), e=eid, c=code)
    return warnings


def _type_name(conn, tid: int) -> str:
    return _one(conn, "SELECT name FROM core.entity_types WHERE id = :t", t=tid)["name"]


def _answer(conn, m: dict, eid: int, warnings: list[dict]) -> dict:
    guid = _one(conn, "SELECT guid FROM core.entities WHERE id = :e", e=eid)["guid"]
    out = repo.get_entity_detail(conn, m["id"], str(guid))
    out["saved_warnings"] = warnings
    return out


# ---------------------------------------------------------------- entities
def create_entity(conn, model: Any, data: dict, actor: str) -> dict:
    """A new entity: entity_type, name, description, parent, tags, values {attribute code: value}."""
    m = _model(conn, model)
    et = repo._find_type(conn, m["_id"], data.get("entity_type"))
    name = (data.get("name") or "").strip()
    if not name:
        raise EditError("Give the entity a name.")
    parent = _entity_id(conn, m, data.get("parent"), "parent entity")
    row = _exec(conn, """INSERT INTO core.entities (model_id, entity_type_id, name, description, parent_entity_id, tags, display_id)
                         VALUES (:m, :t, :n, :d, :p, CAST(:tags AS text[]), coalesce(:did, '')) RETURNING id""",
                m=m["_id"], t=et["_id"], n=name, d=(data.get("description") or "").strip(), p=parent,
                tags=_tags(data.get("tags")), did=(data.get("display_id") or "").strip() or None)
    eid = row.scalar_one()
    changed = _set_values(conn, m, eid, et["_id"], data.get("values") or {})
    return _answer(conn, m, eid, _check(conn, m, eid, et["_id"], actor, changed))


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(t).strip() for t in value if str(t).strip()]


def update_entity(conn, model: Any, entity: Any, data: dict, actor: str) -> dict:
    """Changes the given fields (name, description, parent, tags, display_id) and values. When
    row_version is given and the entity changed since, the save is refused (someone else saved first)."""
    m = _model(conn, model)
    e = _entity_row(conn, m, entity)
    eid, tid = e["_id"], e["_type"]
    if data.get("row_version") is not None and int(data["row_version"]) != int(e["row_version"]):
        raise EditError(f"{e['name']} was changed by {e['modified_by']} since you opened it. Reload it and make your change again.", 409)
    sets, params = [], {"e": eid}
    if "name" in data:
        if not (data["name"] or "").strip():
            raise EditError("The name cannot be empty.")
        sets.append("name = :n"), params.update(n=data["name"].strip())
    if "description" in data:
        sets.append("description = :d"), params.update(d=(data["description"] or "").strip())
    if "parent" in data:
        p = _entity_id(conn, m, data["parent"], "parent entity")
        if p == eid:
            raise EditError("An entity cannot be part of itself.")
        if p and _one(conn, """WITH RECURSIVE up AS (SELECT id, parent_entity_id FROM core.entities WHERE id = :p
                                UNION ALL SELECT e.id, e.parent_entity_id FROM core.entities e JOIN up ON e.id = up.parent_entity_id)
                               SELECT 1 AS x FROM up WHERE id = :e LIMIT 1""", p=p, e=eid):
            raise EditError("That would make the entity part of one of its own parts.")
        sets.append("parent_entity_id = :p"), params.update(p=p)
    if "tags" in data:
        sets.append("tags = CAST(:tags AS text[])"), params.update(tags=_tags(data["tags"]))
    if (data.get("display_id") or "").strip():
        sets.append("display_id = :did"), params.update(did=data["display_id"].strip())
    if sets:
        _exec(conn, f"UPDATE core.entities SET {', '.join(sets)} WHERE id = :e", **params)
    changed = _set_values(conn, m, eid, tid, data.get("values") or {})
    if not sets and not changed:
        return _answer(conn, m, eid, [])
    return _answer(conn, m, eid, _check(conn, m, eid, tid, actor, changed))


def set_status(conn, model: Any, entity: Any, status: str) -> dict:
    """Retire an entity (kept, shown as retired) or restore it (published again)."""
    m = _model(conn, model)
    e = _entity_row(conn, m, entity)
    _exec(conn, "UPDATE core.entities SET status_code = :s WHERE id = :e", s=status, e=e["_id"])
    return _answer(conn, m, e["_id"], [])


def delete_entity(conn, model: Any, entity: Any) -> dict:
    """Deletes an entity with its values and relationships (kept in history; the history phase restores).
    Refused while other entities are part of it or link to it in an attribute."""
    m = _model(conn, model)
    e = _entity_row(conn, m, entity)
    eid = e["_id"]
    kids = _rows(conn, "SELECT name FROM core.entities WHERE parent_entity_id = :e AND NOT is_deleted ORDER BY name LIMIT 5", e=eid)
    if kids:
        raise EditError(f"{e['name']} has parts ({', '.join(k['name'] for k in kids)}...): move or delete them first.", 409)
    refs = _rows(conn, """SELECT x.name FROM core.attribute_values av JOIN core.entities x ON x.id = av.entity_id
                           WHERE av.value_ref = :e AND NOT av.is_deleted AND NOT x.is_deleted LIMIT 5""", e=eid)
    if refs:
        raise EditError(f"{', '.join(r['name'] for r in refs)} link to {e['name']} in an attribute: change them first.", 409)
    rels = _exec(conn, """UPDATE core.relationships SET is_deleted = true
                           WHERE (source_entity_id = :e OR target_entity_id = :e) AND NOT is_deleted""", e=eid).rowcount
    _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE entity_id = :e AND NOT is_deleted", e=eid)
    _exec(conn, "UPDATE core.entities SET is_deleted = true WHERE id = :e", e=eid)
    return {"deleted": str(e["id"]), "name": e["name"], "relationships_removed": rels}


# ---------------------------------------------------------------- relationships
def relationship_options(conn, model: Any, entity: Any) -> dict:
    """What an entity may be related to: each allowed relationship type and direction with the entity
    type at the other end (from the metamodel), and every relationship type of the model (for one
    outside the metamodel, D49)."""
    m = repo.get_model(conn, model)
    e = _entity_row(conn, m, entity)
    allowed = _rows(conn, """
        SELECT 'outgoing' AS direction, rt.guid AS relationship_type_id, rt.name AS relationship_type, rt.verb,
               o.guid AS other_type_id, o.name AS other_type, l.colour, ar.from_content
          FROM core.allowed_relationships ar JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
          JOIN core.entity_types o ON o.id = ar.target_type_id JOIN core.layers l ON l.id = o.layer_id
         WHERE ar.source_type_id = :t AND NOT ar.is_deleted AND NOT rt.is_deleted
        UNION ALL
        SELECT 'incoming', rt.guid, rt.name, rt.verb, o.guid, o.name, l.colour, ar.from_content
          FROM core.allowed_relationships ar JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
          JOIN core.entity_types o ON o.id = ar.source_type_id JOIN core.layers l ON l.id = o.layer_id
         WHERE ar.target_type_id = :t AND NOT ar.is_deleted AND NOT rt.is_deleted
         ORDER BY 1 DESC, 3, 6""", t=e["_type"])
    types = _rows(conn, """SELECT guid AS id, name, verb FROM core.relationship_types
                            WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=m["_id"])
    entity_types = _rows(conn, """SELECT t.guid AS id, t.name, l.name AS layer FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
                                   WHERE t.model_id = :m AND NOT t.is_deleted AND t.status_code <> 'retired'
                                   ORDER BY l.sort_order, t.sort_order, t.name""", m=m["_id"])
    return {"entity": {"id": e["id"], "name": e["name"], "entity_type": e["entity_type"]},
            "allowed": allowed, "relationship_types": types, "entity_types": entity_types}


def find_entities(conn, model: Any, q: str = "", entity_types: list[str] | None = None, limit: int = 50) -> list[dict]:
    """Existing entities to relate to or to pick as a parent: by name or display ID, of the given types."""
    m = repo.get_model(conn, model)
    type_ids = [repo._find_type(conn, m["_id"], t)["_id"] for t in (entity_types or []) if t]
    return _rows(conn, f"""
        SELECT e.guid AS id, e.display_id, e.name, t.name AS entity_type, t.guid AS entity_type_id, l.colour,
               e.status_code AS status
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id JOIN core.layers l ON l.id = t.layer_id
         WHERE e.model_id = :m AND NOT e.is_deleted
           AND (:q = '' OR e.name ILIKE '%' || :q || '%' OR e.display_id ILIKE :q || '%')
           {"AND e.entity_type_id = ANY (:types)" if type_ids else ""}
         ORDER BY (lower(e.name) = lower(:q)) DESC, e.name LIMIT :n""",
                 m=m["_id"], q=(q or "").strip(), types=type_ids, n=min(int(limit or 50), 200))


def add_relationship(conn, model: Any, data: dict, actor: str) -> dict:
    """Relates two existing entities: source, target, relationship_type, name. When the metamodel does
    not allow it, the answer says so (409) unless allow_outside is true: then the mapping is added to the
    metamodel, flagged as added from content (D49), and the relationship saved."""
    m = _model(conn, model)
    src = _entity_id(conn, m, data.get("source"), "source entity")
    tgt = _entity_id(conn, m, data.get("target"), "target entity")
    if not src or not tgt:
        raise EditError("Choose the entities at both ends.")
    rt = repo._find_relationship_type(conn, m["_id"], data.get("relationship_type"))
    st = _one(conn, "SELECT entity_type_id AS type_id FROM core.entities WHERE id = :e", e=src)["type_id"]
    tt = _one(conn, "SELECT entity_type_id AS type_id FROM core.entities WHERE id = :e", e=tgt)["type_id"]
    allowed = _one(conn, """SELECT 1 AS x FROM core.allowed_relationships WHERE relationship_type_id = :r
                             AND source_type_id = :s AND target_type_id = :t AND NOT is_deleted""", r=rt["_id"], s=st, t=tt)
    outside = None
    if not allowed:
        names = _one(conn, """SELECT (SELECT name FROM core.entity_types WHERE id = :s) AS source_type,
                                     (SELECT name FROM core.entity_types WHERE id = :t) AS target_type""", s=st, t=tt)
        if not data.get("allow_outside"):
            raise EditError(f"The metamodel does not allow {rt['name']} from {names['source_type']} to {names['target_type']}. "
                            "Add it anyway to add this relationship to the metamodel, flagged for a Model Admin to review (D49).", 409)
        outside = _exec(conn, "SELECT core.allow_from_content(:m, :r, :s, :t)", m=m["_id"], r=rt["_id"], s=st, t=tt).scalar_one()
    if _one(conn, """SELECT 1 AS x FROM core.relationships WHERE relationship_type_id = :r AND source_entity_id = :s
                      AND target_entity_id = :t AND NOT is_deleted""", r=rt["_id"], s=src, t=tgt):
        raise EditError("These two entities already have this relationship.", 409)
    rid = _exec(conn, """INSERT INTO core.relationships (model_id, relationship_type_id, source_entity_id, target_entity_id, name)
                         VALUES (:m, :r, :s, :t, :n) RETURNING guid""",
                m=m["_id"], r=rt["_id"], s=src, t=tgt, n=(data.get("name") or "").strip()).scalar_one()
    out = {"id": str(rid), "relationship_type": rt["name"], "outside_metamodel": outside is not None}
    if outside is not None:
        out["metamodel_version"] = outside
        out["note"] = (f"The metamodel did not allow this; {rt['name']} between these types was added to it as "
                       f"version {outside}, flagged for a Model Admin to review (D49).")
    return out


def delete_relationship(conn, model: Any, relationship: Any) -> dict:
    m = _model(conn, model)
    guid = repo._as_guid(relationship)
    row = _one(conn, "SELECT id FROM core.relationships WHERE guid = :g AND model_id = :m AND NOT is_deleted",
               g=guid, m=m["_id"]) if guid else None
    if not row:
        raise EditError("No such relationship in this model.", 404)
    _exec(conn, "UPDATE core.relationships SET is_deleted = true WHERE id = :i", i=row["id"])
    return {"deleted": str(guid)}


# ---------------------------------------------------------------- roll back (REP: a new version, history kept)
def roll_back(conn, model: Any, entity: Any, event: int, actor: str) -> dict:
    """Sets an entity back to how it was just after history event `event`: its fields and tags, its
    attribute values and its relationships (those removed since come back, those added since go). It is
    saved as a new version; the history keeps everything in between."""
    m = _model(conn, model)
    e = _entity_row(conn, m, entity)
    eid = e["_id"]
    rows, *_ = repo._history_rows(conn, m, eid)
    chrono = sorted(rows, key=lambda r: (r["changed_at"], r["id"]))
    point = next((r for r in chrono if r["id"] == int(event)), None)
    if point is None:
        raise EditError(f"History event {event} does not belong to this entity.", 404)
    # a moment is one person's changes within one second (as the History tab groups them): the whole
    # moment of the chosen event counts, so a new entity comes back with the values saved with it
    def moment(r):
        return int(repo._as_datetime(r["changed_at"]).timestamp()), r["changed_by"]
    state: dict[tuple, dict] = {}
    for r in chrono:
        if (r["changed_at"], r["id"]) <= (point["changed_at"], point["id"]) or moment(r) == moment(point):
            state[(r["table_name"], r["row_id"])] = r

    def alive(r):
        return r is not None and r["operation"] != "delete" and not r["data"].get("is_deleted")
    then = state.get(("entities", eid))
    if not alive(then):
        raise EditError("The entity did not exist at that point.", 409)
    d = then["data"]
    _exec(conn, """UPDATE core.entities SET name = :n, description = :d, parent_entity_id = :p, status_code = :s,
                                            tags = CAST(:tags AS text[]) WHERE id = :e""",
          n=d.get("name") or e["name"], d=d.get("description") or "", e=eid,
          p=int(d["parent_entity_id"]) if d.get("parent_entity_id") else None,
          s=d.get("status_code") or "published", tags=list(d.get("tags") or []))
    # attribute values: the value each attribute had then
    then_values = {int(r["data"]["attribute_type_id"]): r["data"] for (t, _), r in state.items()
                   if t == "attribute_values" and alive(r)}
    now_values = {r["attribute_type_id"]: r for r in _rows(conn, """
        SELECT id, attribute_type_id, value_text, value_number, value_date, value_bool, value_ref
          FROM core.attribute_values WHERE entity_id = :e AND NOT is_deleted""", e=eid)}
    cols = ("value_text", "value_number", "value_date", "value_bool", "value_ref")
    for attr, row in now_values.items():
        if attr not in then_values:
            _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE id = :i", i=row["id"])
    for attr, data in then_values.items():
        want = {c: data.get(c) for c in cols}
        cur = now_values.get(attr)
        if cur and all(str(cur[c]) == str(want[c]) if want[c] is not None else cur[c] is None for c in cols):
            continue
        params = {c: want[c] for c in cols}
        if cur:
            _exec(conn, f"UPDATE core.attribute_values SET {', '.join(f'{c} = :{c}' for c in cols)}, rule_override = NULL WHERE id = :i",
                  i=cur["id"], **params)
        else:
            _exec(conn, f"""INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, {', '.join(cols)})
                            VALUES (:m, :a, :e, {', '.join(':' + c for c in cols)})""", m=m["_id"], a=attr, e=eid, **params)
    # relationships: back if they were there then, gone if added since
    then_rels = {rid for (t, rid), r in state.items() if t == "relationships" and alive(r)}
    now_rels = {r["id"] for r in _rows(conn, """SELECT id FROM core.relationships WHERE NOT is_deleted
                                                 AND (source_entity_id = :e OR target_entity_id = :e)""", e=eid)}
    restored = removed = 0
    for rid in then_rels - now_rels:
        if _one(conn, """SELECT 1 AS x FROM core.relationships r JOIN core.entities s ON s.id = r.source_entity_id
                          JOIN core.entities t ON t.id = r.target_entity_id
                         WHERE r.id = :r AND NOT s.is_deleted AND NOT t.is_deleted""", r=rid):
            _exec(conn, "UPDATE core.relationships SET is_deleted = false WHERE id = :r", r=rid)
            restored += 1
    for rid in now_rels - then_rels:
        _exec(conn, "UPDATE core.relationships SET is_deleted = true WHERE id = :r", r=rid)
        removed += 1
    out = _answer(conn, m, eid, _check(conn, m, eid, e["_type"], actor, []))
    out["rolled_back_to"] = {"event_id": point["id"], "at": point["changed_at"], "by": point["changed_by"],
                             "relationships_restored": restored, "relationships_removed": removed}
    return out


# ---------------------------------------------------------------- the data entry page (D79)
def entry_table(conn, model: Any, entity_type: Any) -> dict:
    """The data entry page for one type: its form (columns) and its entities with their values, tags,
    parent and relationship count; each row's warnings."""
    f = form(conn, model, entity_type)
    t = repo.type_table(conn, model, entity_type)
    m = repo.get_model(conn, model)
    tid = repo._find_type(conn, m["_id"], entity_type)["_id"]
    tags = {str(r["guid"]): list(r["tags"]) for r in _rows(conn, """SELECT guid, tags FROM core.entities
                                                                     WHERE model_id = :m AND entity_type_id = :t AND NOT is_deleted""",
                                                           m=m["_id"], t=tid)}
    overrides = {}
    for r in _rows(conn, """SELECT e.guid, at.code, av.rule_override FROM core.attribute_values av
                              JOIN core.entities e ON e.id = av.entity_id JOIN core.attribute_types at ON at.id = av.attribute_type_id
                             WHERE e.model_id = :m AND e.entity_type_id = :t AND NOT av.is_deleted AND av.rule_override IS NOT NULL""",
                     m=m["_id"], t=tid):
        overrides.setdefault(str(r["guid"]), {})[r["code"]] = r["rule_override"]
    for row in t["rows"]:
        row["tags"] = tags.get(str(row["id"]), [])
        row["overrides"] = overrides.get(str(row["id"]), {})
    return {**f, "rows": t["rows"]}
