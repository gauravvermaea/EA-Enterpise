"""Changing a model's metamodel (build phase 3), shared by the REST API and later the MCP server.

Every change is one operation (`op`) with its fields, applied in one transaction:
  1. the model's metamodel version moves on (core.publish_metamodel_version): each change
     publishes a new version at once, with a note saying what it was (D72); the history rows of the
     transaction are labelled "metamodel vN: note";
  2. the change is made;
  3. its impact is measured: the validation results of the entity types it touches before and
     after (D64: never blocked, only reported), plus counts of what it touches.
With dry_run the transaction is rolled back, so the screen can show the impact before saving.

Operations (payload fields in brackets; ids are guids; "type" means an entity type):
  entity_type.create   name, layer, [code, id_prefix, description, aspect]
  entity_type.update   id, [name, description, layer, id_prefix, aspect]
  entity_type.retire / entity_type.restore   id   (retired: no new entities, its entities read-only, D87)
  attribute.create     (entity_type | relationship_type), name, data_type,
                       [code, description, unit, pick_list | values, is_required, section, help_text,
                        default_value, apply_default_to_existing, existing_attribute]
  attribute.update     item, [name, description, unit, is_required, section, help_text, default_value,
                        apply_default_to_existing]
  attribute.remove     item     (the attribute leaves the type and its values are removed; they stay in history)
  lifecycle.create     entity_type, name, phases   (a phase pick list and a date per phase, D-MM-021)
  pick_list.create     name, values
  pick_list.add_value  pick_list, value
  pick_list.retire_value   value_id
  relationship_type.create   name, verb, [code, category, is_directed, description]
  relationship_type.update   id, [name, verb, category, is_directed, description]
  relationship_type.retire / relationship_type.restore   id   (retire: no longer offered; relationships kept)
  relationship_type.remove   id   (its relationships are removed too; they stay in history)
  mapping.add          relationship_type, source_type, target_type, [note]
  mapping.remove       id
  rule.create          rule_type, (attribute | field_name), [entity_type, param1, param2, severity, message]
                       (has_relationship: no attribute or field; param1 relationship type, param2 other entity type)
  rule.update          id, [param1, param2, severity, message]
  rule.remove          id
Model locks (D67) are set with set_lock / clear_lock; the database enforces them.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import repository as repo


class EditError(Exception):
    """A change that cannot be made; status is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _one(conn, sql: str, **params) -> dict | None:
    rows = repo._rows(conn, sql, **params)
    return rows[0] if rows else None


def _exec(conn, sql: str, **params):
    return conn.execute(text(sql), params)


def _guid(value, what: str) -> uuid.UUID:
    g = repo._as_guid(value)
    if not g:
        raise EditError(f"Give the {what} as a guid.")
    return g


def _need(p: dict, *names: str) -> None:
    missing = [n for n in names if p.get(n) in (None, "", [])]
    if missing:
        raise EditError("Missing: " + ", ".join(missing))


def code_from(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name)
    code = "".join(w[:1].upper() + w[1:] for w in words)
    if not code or not code[0].isalpha():
        code = "X" + code
    return code[:60]


def snake_from(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "x_" + s
    return s[:50]


def _unique(conn, table: str, column: str, model_id: int, wanted: str, lower: bool = False) -> str:
    """wanted, or wanted2, wanted3... whichever is free in the model."""
    n, candidate = 1, wanted
    cmp = f"lower({column}) = lower(:v)" if lower else f"{column} = :v"
    while _one(conn, f"SELECT 1 AS x FROM core.{table} WHERE model_id = :m AND {cmp}", m=model_id, v=candidate):
        n += 1
        candidate = f"{wanted}{n}" if not wanted.endswith("_") else f"{wanted}{n}"
    return candidate


def _row(conn, table: str, model_id: int, guid, what: str) -> dict:
    r = _one(conn, f"SELECT * FROM core.{table} WHERE guid = :g AND model_id = :m", g=_guid(guid, what), m=model_id)
    if not r:
        raise EditError(f"No {what} {guid} in this model.", 404)
    return r


def _type_by_ref(conn, model_id: int, ref) -> dict:
    try:
        t = repo._find_type(conn, model_id, ref)
    except repo.NotFound as exc:
        raise EditError(str(exc), 404) from exc
    return _one(conn, "SELECT * FROM core.entity_types WHERE id = :i", i=t["_id"])


def _rel_type_by_ref(conn, model_id: int, ref) -> dict:
    try:
        r = repo._find_relationship_type(conn, model_id, ref)
    except repo.NotFound as exc:
        raise EditError(str(exc), 404) from exc
    return _one(conn, "SELECT * FROM core.relationship_types WHERE id = :i", i=r["_id"])


def _layer(conn, model_id: int, ref) -> dict:
    g = repo._as_guid(ref)
    r = _one(conn, f"""SELECT * FROM core.layers WHERE model_id = :m AND NOT is_deleted AND
                       {'guid = :r' if g else 'lower(:r) IN (lower(code), lower(name))'}""", m=model_id, r=g or str(ref))
    if not r:
        raise EditError(f"No layer {ref!r} in this model.", 404)
    return r


# ---------------------------------------------------------------- typed values

STORAGE = {"text": "value_text", "long_text": "value_text", "list": "value_text", "url": "value_text",
           "email": "value_text", "integer": "value_number", "decimal": "value_number", "currency": "value_number",
           "percent": "value_number", "date": "value_date", "boolean": "value_bool"}


def typed_default(data_type: str, value: Any, pick_values: list[str] | None = None):
    """A default value as the column and value it is stored in; None when there is no default.
    Raises EditError when the value does not fit the data type (those cannot be stored)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    column = STORAGE.get(data_type)
    if column is None:
        raise EditError(f"Attributes of type {data_type} take no default value.")
    v = str(value).strip()
    if column == "value_number":
        try:
            n = Decimal(v)
        except InvalidOperation as exc:
            raise EditError(f"The default {v!r} is not a number.") from exc
        if data_type == "integer" and n != n.to_integral_value():
            raise EditError(f"The default {v!r} is not a whole number.")
        return column, n
    if column == "value_date":
        try:
            return column, dt.date.fromisoformat(v[:10])
        except ValueError as exc:
            raise EditError(f"The default {v!r} is not a date (YYYY-MM-DD).") from exc
    if column == "value_bool":
        if v.lower() in ("yes", "true", "1", "y"):
            return column, True
        if v.lower() in ("no", "false", "0", "n"):
            return column, False
        raise EditError(f"The default {v!r} is not yes or no.")
    if data_type == "list" and pick_values is not None and v not in pick_values:
        raise EditError(f"The default {v!r} is not one of the pick list's values: {', '.join(pick_values)}.")
    return column, v


def _pick_values(conn, pick_list_id: int | None) -> list[str] | None:
    if not pick_list_id:
        return None
    return [r["value"] for r in repo._rows(conn, """SELECT value FROM core.pick_list_values
        WHERE pick_list_id = :p AND NOT is_deleted AND status_code <> 'retired' ORDER BY sort_order, value""", p=pick_list_id)]


def _apply_default(conn, model_id: int, entity_type_id: int, attr: dict, default) -> int:
    """Gives every entity of the type that has no value the default; returns how many."""
    if default is None:
        return 0
    column, value = default
    ids = [r["id"] for r in repo._rows(conn, """
        SELECT e.id FROM core.entities e
         WHERE e.model_id = :m AND e.entity_type_id = :t AND NOT e.is_deleted
           AND NOT EXISTS (SELECT 1 FROM core.attribute_values v
                            WHERE v.entity_id = e.id AND v.attribute_type_id = :a AND NOT v.is_deleted
                              AND num_nonnulls(v.value_text, v.value_number, v.value_date, v.value_bool, v.value_ref) > 0)""",
        m=model_id, t=entity_type_id, a=attr["id"])]
    if not ids:
        return 0
    # an empty value row may exist (soft): replace it
    _exec(conn, f"""UPDATE core.attribute_values SET {column} = :v
                     WHERE entity_id = ANY (:ids) AND attribute_type_id = :a AND NOT is_deleted""",
          ids=ids, a=attr["id"], v=value)
    _exec(conn, f"""INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, {column})
                    SELECT :m, :a, e, :v FROM unnest(CAST(:ids AS bigint[])) AS e
                     WHERE NOT EXISTS (SELECT 1 FROM core.attribute_values x
                                        WHERE x.entity_id = e AND x.attribute_type_id = :a AND NOT x.is_deleted)""",
          m=model_id, a=attr["id"], ids=ids, v=value)
    # the entities changed in this metamodel version
    _exec(conn, "UPDATE core.entities SET modified_at = now() WHERE id = ANY (:ids)", ids=ids)
    return len(ids)


# ---------------------------------------------------------------- impact

def _failing(conn, model: dict, type_ids: list[int]) -> dict[str, set]:
    """For each entity type: the set of (entity guid, rule, field) that fail a check now."""
    out: dict[str, set] = {}
    for tid in type_ids:
        tg = _one(conn, "SELECT guid FROM core.entity_types WHERE id = :i", i=tid)
        if not tg:
            continue
        try:
            table = repo.type_table(conn, model["id"], tg["guid"])
        except repo.NotFound:
            continue
        out[str(tg["guid"])] = {(str(r["id"]), c["rule"], c["field"], c["severity"], r["name"], r["display_id"])
                                for r in table["rows"] for c in r.get("checks", [])}
    return out


def _types_with_entities(conn, model_id: int) -> list[int]:
    return [r["entity_type_id"] for r in repo._rows(conn, """SELECT DISTINCT entity_type_id FROM core.entities
        WHERE model_id = :m AND NOT is_deleted""", m=model_id)]


# ---------------------------------------------------------------- the operations

def _op_entity_type_create(conn, m, p):
    _need(p, "name", "layer")
    mid = m["_id"]
    layer = _layer(conn, mid, p["layer"])
    code = _unique(conn, "entity_types", "code", mid, p.get("code") or code_from(p["name"]), lower=True)
    table = _unique(conn, "entity_types", "table_name", mid, snake_from(p["name"]))
    prefix = (p.get("id_prefix") or re.sub(r"[^A-Z]", "", p["name"].upper())[:3] or "ENT")[:6]
    sort = _one(conn, "SELECT coalesce(max(sort_order), 0) + 10 AS s FROM core.entity_types WHERE model_id = :m", m=mid)["s"]
    r = _one(conn, """INSERT INTO core.entity_types (model_id, layer_id, code, name, description, aspect, id_prefix, table_name, sort_order)
                      VALUES (:m, :l, :c, :n, :d, :a, :p, :t, :s) RETURNING guid""",
             m=mid, l=layer["id"], c=code, n=p["name"].strip(), d=p.get("description", ""), a=p.get("aspect", ""),
             p=prefix, t=table, s=sort)
    return {"id": r["guid"], "code": code}, f"Added entity type {p['name'].strip()}", []


def _op_entity_type_update(conn, m, p):
    _need(p, "id")
    t = _row(conn, "entity_types", m["_id"], p["id"], "entity type")
    fields = {k: p[k] for k in ("name", "description", "aspect", "id_prefix") if k in p and p[k] is not None}
    if "layer" in p and p["layer"]:
        fields["layer_id"] = _layer(conn, m["_id"], p["layer"])["id"]
    if not fields:
        raise EditError("Nothing to change.")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    _exec(conn, f"UPDATE core.entity_types SET {sets} WHERE id = :id", id=t["id"], **fields)
    return {"id": t["guid"]}, f"Changed entity type {fields.get('name', t['name'])}", [t["id"]]


def _op_entity_type_status(conn, m, p, status):
    _need(p, "id")
    t = _row(conn, "entity_types", m["_id"], p["id"], "entity type")
    _exec(conn, "UPDATE core.entity_types SET status_code = :s WHERE id = :id", s=status, id=t["id"])
    verb = "Retired" if status == "retired" else "Restored"
    return {"id": t["guid"]}, f"{verb} entity type {t['name']}", [t["id"]]


def _new_pick_list(conn, mid: int, name: str, values: list[str]) -> int:
    code = _unique(conn, "pick_lists", "code", mid, code_from(name), lower=True)
    pl = _one(conn, "INSERT INTO core.pick_lists (model_id, code, name) VALUES (:m, :c, :n) RETURNING id",
              m=mid, c=code, n=name)
    seen = []
    for i, v in enumerate(values):
        v = str(v).strip()
        if v and v not in seen:
            seen.append(v)
            _exec(conn, """INSERT INTO core.pick_list_values (model_id, pick_list_id, value, sort_order)
                           VALUES (:m, :p, :v, :s)""", m=mid, p=pl["id"], v=v, s=(i + 1) * 10)
    if not seen:
        raise EditError("A pick list needs at least one value.")
    return pl["id"]


def _op_attribute_create(conn, m, p):
    mid = m["_id"]
    owner_type = owner_rel = None
    if p.get("entity_type"):
        owner_type = _type_by_ref(conn, mid, p["entity_type"])
    elif p.get("relationship_type"):
        owner_rel = _rel_type_by_ref(conn, mid, p["relationship_type"])
    else:
        raise EditError("Give the entity type (or relationship type) the attribute belongs to.")
    if p.get("existing_attribute"):
        attr = _row(conn, "attribute_types", mid, p["existing_attribute"], "attribute")
    else:
        _need(p, "name", "data_type")
        dtype = p["data_type"]
        if not _one(conn, "SELECT 1 AS x FROM core.data_types WHERE code = :c", c=dtype):
            raise EditError(f"Unknown data type {dtype!r}.")
        pick_list_id = None
        if dtype == "list":
            if p.get("pick_list"):
                pick_list_id = _row(conn, "pick_lists", mid, p["pick_list"], "pick list")["id"]
            elif p.get("values"):
                pick_list_id = _new_pick_list(conn, mid, p["name"].strip(), p["values"])
            else:
                raise EditError("A pick-list attribute needs a pick list or its values.")
        code = _unique(conn, "attribute_types", "code", mid, p.get("code") or code_from(p["name"]), lower=True)
        column = _unique(conn, "attribute_types", "column_name", mid, snake_from(p["name"]))
        attr = _one(conn, """INSERT INTO core.attribute_types (model_id, code, name, description, data_type_code, pick_list_id, unit, column_name)
                             VALUES (:m, :c, :n, :d, :t, :p, :u, :col) RETURNING *""",
                    m=mid, c=code, n=p["name"].strip(), d=p.get("description", ""), t=dtype, p=pick_list_id,
                    u=p.get("unit", "") or "", col=column)
    default = typed_default(attr["data_type_code"], p.get("default_value"), _pick_values(conn, attr["pick_list_id"]))
    owner_col, owner_id = ("entity_type_id", owner_type["id"]) if owner_type else ("relationship_type_id", owner_rel["id"])
    if _one(conn, f"SELECT 1 AS x FROM core.item_attributes WHERE {owner_col} = :o AND attribute_type_id = :a AND NOT is_deleted",
            o=owner_id, a=attr["id"]):
        raise EditError(f"{attr['name']} is already an attribute of this type.", 409)
    sort = _one(conn, f"SELECT coalesce(max(sort_order), 0) + 10 AS s FROM core.item_attributes WHERE {owner_col} = :o",
                o=owner_id)["s"]
    item = _one(conn, f"""INSERT INTO core.item_attributes (model_id, attribute_type_id, {owner_col}, is_required, section,
                                                            sort_order, default_value, help_text)
                          VALUES (:m, :a, :o, :r, :s, :so, :dv, :h) RETURNING guid""",
                m=mid, a=attr["id"], o=owner_id, r=bool(p.get("is_required")), s=p.get("section") or "General", so=sort,
                dv=None if default is None else str(p.get("default_value")).strip(), h=p.get("help_text", "") or "")
    filled = 0
    if owner_type and p.get("apply_default_to_existing"):
        filled = _apply_default(conn, mid, owner_type["id"], attr, default)
    where = owner_type["name"] if owner_type else owner_rel["name"]
    req = " (mandatory)" if p.get("is_required") else ""
    return ({"item": item["guid"], "attribute": attr["guid"], "filled_with_default": filled},
            f"Added attribute {attr['name']}{req} to {where}", [owner_type["id"]] if owner_type else [])


def _item(conn, mid: int, guid) -> dict:
    r = _one(conn, """SELECT ia.*, at.name AS attr_name, at.data_type_code, at.pick_list_id, at.guid AS attr_guid,
                             et.name AS type_name, rt.name AS rel_name
                        FROM core.item_attributes ia JOIN core.attribute_types at ON at.id = ia.attribute_type_id
                        LEFT JOIN core.entity_types et ON et.id = ia.entity_type_id
                        LEFT JOIN core.relationship_types rt ON rt.id = ia.relationship_type_id
                       WHERE ia.guid = :g AND ia.model_id = :m AND NOT ia.is_deleted""", g=_guid(guid, "attribute"), m=mid)
    if not r:
        raise EditError(f"No attribute {guid} on a type in this model.", 404)
    return r


def _op_attribute_update(conn, m, p):
    _need(p, "item")
    mid = m["_id"]
    it = _item(conn, mid, p["item"])
    attr_fields = {k: p[k] for k in ("name", "description", "unit") if p.get(k) is not None}
    if attr_fields:
        sets = ", ".join(f"{k} = :{k}" for k in attr_fields)
        _exec(conn, f"UPDATE core.attribute_types SET {sets} WHERE id = :id", id=it["attribute_type_id"], **attr_fields)
    item_fields = {}
    for k in ("is_required", "section", "help_text"):
        if k in p and p[k] is not None:
            item_fields[k] = bool(p[k]) if k == "is_required" else p[k]
    default = None
    if "default_value" in p:
        default = typed_default(it["data_type_code"], p.get("default_value"), _pick_values(conn, it["pick_list_id"]))
        item_fields["default_value"] = None if default is None else str(p["default_value"]).strip()
    if item_fields:
        sets = ", ".join(f"{k} = :{k}" for k in item_fields)
        _exec(conn, f"UPDATE core.item_attributes SET {sets} WHERE id = :id", id=it["id"], **item_fields)
    if not attr_fields and not item_fields:
        raise EditError("Nothing to change.")
    filled = 0
    if it["entity_type_id"] and p.get("apply_default_to_existing"):
        if default is None and it["default_value"]:
            default = typed_default(it["data_type_code"], it["default_value"], _pick_values(conn, it["pick_list_id"]))
        attr = _one(conn, "SELECT * FROM core.attribute_types WHERE id = :i", i=it["attribute_type_id"])
        filled = _apply_default(conn, mid, it["entity_type_id"], attr, default)
    what = []
    if "is_required" in item_fields:
        what.append("mandatory" if item_fields["is_required"] else "optional")
    if "default_value" in item_fields:
        what.append("default " + (item_fields["default_value"] or "removed"))
    note = f"Changed attribute {attr_fields.get('name', it['attr_name'])} on {it['type_name'] or it['rel_name']}"
    return ({"item": it["guid"], "filled_with_default": filled}, note + (f" ({', '.join(what)})" if what else ""),
            [it["entity_type_id"]] if it["entity_type_id"] else [])


_VALUES_OF_ITEM = """core.attribute_values v WHERE v.model_id = :m AND v.attribute_type_id = :a AND NOT v.is_deleted
      AND (v.entity_id IN (SELECT id FROM core.entities WHERE entity_type_id = :t)
           OR v.relationship_id IN (SELECT id FROM core.relationships WHERE relationship_type_id = :r))"""


def _op_attribute_remove(conn, m, p):
    """The attribute leaves the type and its values are removed from every entity (or relationship) of
    the type. Each removed value stays in the history, so an entity's timeline still shows it."""
    _need(p, "item")
    it = _item(conn, m["_id"], p["item"])
    keys = dict(m=m["_id"], a=it["attribute_type_id"], t=it["entity_type_id"] or 0, r=it["relationship_type_id"] or 0)
    values = _one(conn, f"SELECT count(*) AS n FROM {_VALUES_OF_ITEM}", **keys)["n"]
    _exec(conn, f"UPDATE core.attribute_values SET is_deleted = true WHERE id IN (SELECT v.id FROM {_VALUES_OF_ITEM})", **keys)
    _exec(conn, "UPDATE core.item_attributes SET is_deleted = true WHERE id = :id", id=it["id"])
    return ({"item": it["guid"], "values_removed": values},
            f"Removed attribute {it['attr_name']} from {it['type_name'] or it['rel_name']}",
            [it["entity_type_id"]] if it["entity_type_id"] else [])


def _op_lifecycle_create(conn, m, p):
    _need(p, "entity_type", "name", "phases")
    phases = [str(x).strip() for x in p["phases"] if str(x).strip()]
    if len(phases) < 2:
        raise EditError("A lifecycle needs at least two phases.")
    t = _type_by_ref(conn, m["_id"], p["entity_type"])
    section = p["name"].strip()
    first, _, _ = _op_attribute_create(conn, m, {"entity_type": t["guid"], "name": f"{section} phase", "data_type": "list",
                                                 "values": phases, "section": section})
    items = [first["item"]]
    for ph in phases:
        r, _, _ = _op_attribute_create(conn, m, {"entity_type": t["guid"], "name": f"{section}: {ph}", "data_type": "date",
                                                 "section": section, "help_text": f"Date the {ph} phase starts"})
        items.append(r["item"])
    return {"items": items}, f"Added lifecycle {section} ({', '.join(phases)}) to {t['name']}", [t["id"]]


def _op_pick_list_create(conn, m, p):
    _need(p, "name", "values")
    pid = _new_pick_list(conn, m["_id"], p["name"].strip(), p["values"])
    g = _one(conn, "SELECT guid FROM core.pick_lists WHERE id = :i", i=pid)["guid"]
    return {"id": g}, f"Added pick list {p['name'].strip()}", []


def _op_pick_list_add_value(conn, m, p):
    _need(p, "pick_list", "value")
    pl = _row(conn, "pick_lists", m["_id"], p["pick_list"], "pick list")
    v = str(p["value"]).strip()
    old = _one(conn, "SELECT id, status_code, is_deleted FROM core.pick_list_values WHERE pick_list_id = :p AND value = :v",
               p=pl["id"], v=v)
    if old and not old["is_deleted"] and old["status_code"] != "retired":
        raise EditError(f"{v!r} is already in {pl['name']}.", 409)
    if old:
        _exec(conn, "UPDATE core.pick_list_values SET is_deleted = false, status_code = 'published' WHERE id = :i", i=old["id"])
    else:
        s = _one(conn, "SELECT coalesce(max(sort_order), 0) + 10 AS s FROM core.pick_list_values WHERE pick_list_id = :p",
                 p=pl["id"])["s"]
        _exec(conn, """INSERT INTO core.pick_list_values (model_id, pick_list_id, value, sort_order)
                       VALUES (:m, :p, :v, :s)""", m=m["_id"], p=pl["id"], v=v, s=s)
    return {"pick_list": pl["guid"]}, f"Added {v!r} to pick list {pl['name']}", _types_using_pick_list(conn, pl["id"])


def _types_using_pick_list(conn, pick_list_id: int) -> list[int]:
    return [r["t"] for r in repo._rows(conn, """SELECT DISTINCT ia.entity_type_id AS t FROM core.item_attributes ia
        JOIN core.attribute_types at ON at.id = ia.attribute_type_id
        WHERE at.pick_list_id = :p AND ia.entity_type_id IS NOT NULL AND NOT ia.is_deleted""", p=pick_list_id)]


def _op_pick_list_retire_value(conn, m, p):
    _need(p, "value_id")
    v = _row(conn, "pick_list_values", m["_id"], p["value_id"], "pick-list value")
    _exec(conn, "UPDATE core.pick_list_values SET status_code = 'retired' WHERE id = :i", i=v["id"])
    pl = _one(conn, "SELECT name FROM core.pick_lists WHERE id = :i", i=v["pick_list_id"])
    return {"value_id": v["guid"]}, f"Retired {v['value']!r} in pick list {pl['name']}", _types_using_pick_list(conn, v["pick_list_id"])


def _op_relationship_type_create(conn, m, p):
    _need(p, "name", "verb")
    mid = m["_id"]
    code = _unique(conn, "relationship_types", "code", mid, p.get("code") or code_from(p["name"]), lower=True)
    sort = _one(conn, "SELECT coalesce(max(sort_order), 0) + 10 AS s FROM core.relationship_types WHERE model_id = :m", m=mid)["s"]
    r = _one(conn, """INSERT INTO core.relationship_types (model_id, code, name, verb, category, is_directed, description, sort_order)
                      VALUES (:m, :c, :n, :v, :cat, :d, :desc, :s) RETURNING guid""",
             m=mid, c=code, n=p["name"].strip(), v=p["verb"].strip(), cat=p.get("category", "") or "",
             d=bool(p.get("is_directed", True)), desc=p.get("description", "") or "", s=sort)
    return {"id": r["guid"], "code": code}, f"Added relationship type {p['name'].strip()}", []


def _op_relationship_type_update(conn, m, p):
    _need(p, "id")
    r = _row(conn, "relationship_types", m["_id"], p["id"], "relationship type")
    fields = {k: p[k] for k in ("name", "verb", "category", "description", "is_directed") if k in p and p[k] is not None}
    if not fields:
        raise EditError("Nothing to change.")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    _exec(conn, f"UPDATE core.relationship_types SET {sets} WHERE id = :id", id=r["id"], **fields)
    return {"id": r["guid"]}, f"Changed relationship type {fields.get('name', r['name'])}", []


def _op_relationship_type_remove(conn, m, p):
    """Removes a relationship type: every relationship of the type (and its attribute values) is removed
    from the model; each stays in the history. The type is kept as retired, so it can be restored (its
    relationships are not: bring one back from its history)."""
    _need(p, "id")
    mid = m["_id"]
    r = _row(conn, "relationship_types", mid, p["id"], "relationship type")
    rels = _one(conn, "SELECT count(*) AS n FROM core.relationships WHERE model_id = :m AND relationship_type_id = :r AND NOT is_deleted",
                m=mid, r=r["id"])["n"]
    _exec(conn, """UPDATE core.attribute_values SET is_deleted = true WHERE model_id = :m AND NOT is_deleted
                     AND relationship_id IN (SELECT id FROM core.relationships WHERE relationship_type_id = :r)""", m=mid, r=r["id"])
    _exec(conn, "UPDATE core.relationships SET is_deleted = true WHERE model_id = :m AND relationship_type_id = :r AND NOT is_deleted",
          m=mid, r=r["id"])
    _exec(conn, "UPDATE core.relationship_types SET status_code = 'retired' WHERE id = :id", id=r["id"])
    return ({"id": r["guid"], "relationships_removed": rels},
            f"Removed relationship type {r['name']}" + (f" and its {rels} relationship{'s' if rels != 1 else ''}" if rels else ""), [])


def _op_relationship_type_status(conn, m, p, status):
    _need(p, "id")
    r = _row(conn, "relationship_types", m["_id"], p["id"], "relationship type")
    _exec(conn, "UPDATE core.relationship_types SET status_code = :s WHERE id = :id", s=status, id=r["id"])
    verb = "Retired" if status == "retired" else "Restored"
    return {"id": r["guid"]}, f"{verb} relationship type {r['name']}", []


def _op_mapping_add(conn, m, p):
    _need(p, "relationship_type", "source_type", "target_type")
    mid = m["_id"]
    rt = _rel_type_by_ref(conn, mid, p["relationship_type"])
    s, t = _type_by_ref(conn, mid, p["source_type"]), _type_by_ref(conn, mid, p["target_type"])
    old = _one(conn, """SELECT id, guid, is_deleted FROM core.allowed_relationships
                         WHERE relationship_type_id = :r AND source_type_id = :s AND target_type_id = :t""",
               r=rt["id"], s=s["id"], t=t["id"])
    if old and not old["is_deleted"]:
        raise EditError(f"{s['name']} {rt['verb']} {t['name']} is already allowed.", 409)
    if old:
        _exec(conn, "UPDATE core.allowed_relationships SET is_deleted = false, note = :n WHERE id = :i",
              i=old["id"], n=p.get("note", "") or "")
        g = old["guid"]
    else:
        g = _one(conn, """INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id, note)
                          VALUES (:m, :r, :s, :t, :n) RETURNING guid""",
                 m=mid, r=rt["id"], s=s["id"], t=t["id"], n=p.get("note", "") or "")["guid"]
    return {"id": g}, f"Allowed {s['name']} {rt['verb']} {t['name']} ({rt['name']})", [s["id"], t["id"]]


def _op_mapping_remove(conn, m, p):
    _need(p, "id")
    a = _row(conn, "allowed_relationships", m["_id"], p["id"], "mapping")
    names = _one(conn, """SELECT s.name AS s, t.name AS t, rt.name AS r, rt.verb FROM core.allowed_relationships a
        JOIN core.entity_types s ON s.id = a.source_type_id JOIN core.entity_types t ON t.id = a.target_type_id
        JOIN core.relationship_types rt ON rt.id = a.relationship_type_id WHERE a.id = :i""", i=a["id"])
    used = _one(conn, """SELECT count(*) AS n FROM core.relationships r
        JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
        WHERE r.relationship_type_id = :r AND s.entity_type_id = :s AND t.entity_type_id = :t AND NOT r.is_deleted""",
                r=a["relationship_type_id"], s=a["source_type_id"], t=a["target_type_id"])["n"]
    _exec(conn, "UPDATE core.allowed_relationships SET is_deleted = true WHERE id = :i", i=a["id"])
    return ({"id": a["guid"], "relationships_now_outside_the_rules": used},
            f"No longer allowed: {names['s']} {names['verb']} {names['t']} ({names['r']})",
            [a["source_type_id"], a["target_type_id"]])


def check_rule_params(rule_type: str, p1: Any, p2: Any) -> None:
    """Refuses parameters a rule could never use: a regular expression that does not compile, a date
    that is not YYYY-MM-DD, a number that is not a number."""
    p1, p2 = str(p1 or "").strip(), str(p2 or "").strip()
    if rule_type == "regex":
        if not p1:
            raise EditError("Give the regular expression the value must match.")
        try:
            re.compile(p1)
        except re.error as exc:
            raise EditError(f"The regular expression {p1!r} is not valid: {exc}.") from exc
    elif rule_type == "date_range":
        for v in (p1, p2):
            if v:
                try:
                    dt.date.fromisoformat(v)
                except ValueError as exc:
                    raise EditError(f"{v!r} is not a date (YYYY-MM-DD).") from exc
        if not (p1 or p2):
            raise EditError("Give a from date, a to date or both.")
        if p1 and p2 and p1 > p2:
            raise EditError("The from date is after the to date.")
    elif rule_type in ("min_value", "max_value", "range", "min_length", "max_length"):
        for v in (p1, p2) if rule_type == "range" else (p1,):
            try:
                Decimal(v)
            except InvalidOperation as exc:
                raise EditError(f"{v!r} is not a number.") from exc
        if rule_type == "range" and Decimal(p1) > Decimal(p2):
            raise EditError("The from value is more than the to value.")


def _op_rule_create(conn, m, p):
    _need(p, "rule_type")
    mid = m["_id"]
    rtype = _one(conn, "SELECT code, name FROM core.rule_types WHERE code = :c", c=p["rule_type"])
    if not rtype:
        raise EditError(f"Unknown rule type {p['rule_type']!r}.")
    attr_id, field, label = None, None, None
    if rtype["code"] == "has_relationship":   # D113: about the entity's relationships, not a value
        field, label = "relationships", "Relationships"
        if p.get("param1") and not _one(conn, """SELECT 1 AS x FROM core.relationship_types WHERE model_id = :m
                AND NOT is_deleted AND lower(:r) IN (lower(code), lower(name))""", m=mid, r=str(p["param1"])):
            raise EditError(f"No relationship type {p['param1']!r} in this model.", 404)
        if p.get("param2") and not _one(conn, """SELECT 1 AS x FROM core.entity_types WHERE model_id = :m
                AND NOT is_deleted AND lower(:t) IN (lower(code), lower(name))""", m=mid, t=str(p["param2"])):
            raise EditError(f"No entity type {p['param2']!r} in this model.", 404)
    elif p.get("attribute"):
        g = repo._as_guid(p["attribute"])
        a = _one(conn, f"""SELECT id, name FROM core.attribute_types WHERE model_id = :m AND
                            {'guid = :a' if g else 'lower(:a) IN (lower(code), lower(name))'}""", m=mid, a=g or str(p["attribute"]))
        if not a:
            raise EditError(f"No attribute {p['attribute']!r} in this model.", 404)
        attr_id, label = a["id"], a["name"]
    elif p.get("field_name") in ("name", "description", "display_id"):
        field, label = p["field_name"], p["field_name"].replace("_", " ").capitalize()
    elif p.get("field_name") == "relationships":
        raise EditError("Relationships take the rule Has relationship.")
    else:
        raise EditError("Give the attribute the rule checks, or the field (name, description or display_id).")
    check_rule_params(rtype["code"], p.get("param1"), p.get("param2"))
    type_id = _type_by_ref(conn, mid, p["entity_type"])["id"] if p.get("entity_type") else None
    severity = p.get("severity") or "error"
    if severity not in ("error", "warning"):
        raise EditError("Severity is error or warning.")
    message = (p.get("message") or "").strip() or f"{label}: {rtype['name'].lower()} rule"
    sort = _one(conn, "SELECT coalesce(max(sort_order), 0) + 10 AS s FROM core.validation_rules WHERE model_id = :m", m=mid)["s"]
    r = _one(conn, """INSERT INTO core.validation_rules (model_id, attribute_type_id, field_name, entity_type_id, rule_type_code,
                                                         param1, param2, severity, message, sort_order)
                      VALUES (:m, :a, :f, :t, :rt, :p1, :p2, :sev, :msg, :s) RETURNING guid""",
             m=mid, a=attr_id, f=field, t=type_id, rt=rtype["code"], p1=str(p.get("param1") or ""),
             p2=str(p.get("param2") or ""), sev=severity, msg=message, s=sort)
    affected = [type_id] if type_id else _types_with_entities(conn, mid)
    return {"id": r["guid"]}, f"Added rule {rtype['name']} on {label}", affected


def _op_rule_update(conn, m, p):
    _need(p, "id")
    r = _row(conn, "validation_rules", m["_id"], p["id"], "rule")
    fields = {k: (str(p[k]) if k in ("param1", "param2") else p[k])
              for k in ("param1", "param2", "severity", "message") if k in p and p[k] is not None}
    if not fields:
        raise EditError("Nothing to change.")
    if fields.get("severity") not in (None, "error", "warning"):
        raise EditError("Severity is error or warning.")
    check_rule_params(r["rule_type_code"], fields.get("param1", r["param1"]), fields.get("param2", r["param2"]))
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    _exec(conn, f"UPDATE core.validation_rules SET {sets} WHERE id = :id", id=r["id"], **fields)
    affected = [r["entity_type_id"]] if r["entity_type_id"] else _types_with_entities(conn, m["_id"])
    return {"id": r["guid"]}, f"Changed rule: {fields.get('message', r['message'])}", affected


def _op_rule_remove(conn, m, p):
    _need(p, "id")
    r = _row(conn, "validation_rules", m["_id"], p["id"], "rule")
    affected = [r["entity_type_id"]] if r["entity_type_id"] else _types_with_entities(conn, m["_id"])
    _exec(conn, "UPDATE core.validation_rules SET is_deleted = true WHERE id = :id", id=r["id"])
    return {"id": r["guid"]}, f"Removed rule: {r['message']}", affected


OPS = {
    "entity_type.create": _op_entity_type_create,
    "entity_type.update": _op_entity_type_update,
    "entity_type.retire": lambda c, m, p: _op_entity_type_status(c, m, p, "retired"),
    "entity_type.restore": lambda c, m, p: _op_entity_type_status(c, m, p, "published"),
    "attribute.create": _op_attribute_create,
    "attribute.update": _op_attribute_update,
    "attribute.remove": _op_attribute_remove,
    "lifecycle.create": _op_lifecycle_create,
    "pick_list.create": _op_pick_list_create,
    "pick_list.add_value": _op_pick_list_add_value,
    "pick_list.retire_value": _op_pick_list_retire_value,
    "relationship_type.create": _op_relationship_type_create,
    "relationship_type.update": _op_relationship_type_update,
    "relationship_type.retire": lambda c, m, p: _op_relationship_type_status(c, m, p, "retired"),
    "relationship_type.remove": _op_relationship_type_remove,
    "relationship_type.restore": lambda c, m, p: _op_relationship_type_status(c, m, p, "published"),
    "mapping.add": _op_mapping_add,
    "mapping.remove": _op_mapping_remove,
    "rule.create": _op_rule_create,
    "rule.update": _op_rule_update,
    "rule.remove": _op_rule_remove,
}

# what each op touches, for the impact check, before it runs (the type ids it names)
def _types_named(conn, mid: int, op: str, p: dict) -> list[int]:
    try:
        if op.startswith("attribute.") and p.get("item"):
            return [x for x in [_item(conn, mid, p["item"])["entity_type_id"]] if x]
        if p.get("entity_type"):
            return [_type_by_ref(conn, mid, p["entity_type"])["id"]]
        if op.startswith("entity_type.") and p.get("id"):
            return [_row(conn, "entity_types", mid, p["id"], "entity type")["id"]]
        if op == "mapping.add":
            return [_type_by_ref(conn, mid, p["source_type"])["id"], _type_by_ref(conn, mid, p["target_type"])["id"]]
        if op == "mapping.remove":
            a = _row(conn, "allowed_relationships", mid, p["id"], "mapping")
            return [a["source_type_id"], a["target_type_id"]]
        if op.startswith("rule.") and p.get("id"):
            r = _row(conn, "validation_rules", mid, p["id"], "rule")
            return [r["entity_type_id"]] if r["entity_type_id"] else _types_with_entities(conn, mid)
        if op == "rule.create":
            return _types_with_entities(conn, mid)
        if op == "pick_list.retire_value":
            v = _row(conn, "pick_list_values", mid, p["value_id"], "pick-list value")
            return _types_using_pick_list(conn, v["pick_list_id"])
    except EditError:
        return []
    return []


def _db_message(exc: DBAPIError) -> str:
    diag = getattr(exc.orig, "diag", None)
    msg = getattr(diag, "message_primary", None) or str(exc.orig).strip().splitlines()[0]
    hint = getattr(diag, "message_hint", None)
    return f"{msg} {hint}" if hint else msg


def apply(conn, model: Any, op: str, payload: dict, actor: str, dry_run: bool = False) -> dict:
    """Applies one metamodel change in the open transaction (engine.begin()); the caller rolls back
    when dry_run. Returns the new version, its note, what was made and the impact."""
    if op not in OPS:
        raise EditError(f"Unknown change {op!r}. Known: {', '.join(sorted(OPS))}.")
    m = repo.get_model(conn, model)
    if m["kind"] not in ("project", "template") or m["is_locked"]:
        raise EditError(f"Model {m['name']!r} is read-only ({m['kind_name'].lower()}): change the metamodel of a working model or of your own root metamodel.", 409)
    mid = m["_id"]
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})
    before_types = _types_named(conn, mid, op, payload)
    before = _failing(conn, m, before_types)
    try:
        # history rows of this change are labelled "metamodel vN"; the note goes on the version row
        version = conn.execute(text("SELECT core.publish_metamodel_version(:m, '')"), {"m": mid}).scalar_one()
        result, note, touched = OPS[op](conn, m, payload)
        conn.execute(text("UPDATE core.metamodel_versions SET note = :n WHERE model_id = :m AND version = :v"),
                     {"n": note, "m": mid, "v": version})
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    after = _failing(conn, m, sorted(set(before_types) | set(touched or [])))
    impact = _impact(before, after)
    if not dry_run:
        from .reports import refresh_typed_views
        refresh_typed_views(conn)   # the typed report views follow the metamodel (D139)
    return {"model": m["name"], "op": op, "version": version, "note": note, "dry_run": dry_run,
            "result": result, "impact": impact}


def _impact(before: dict[str, set], after: dict[str, set]) -> dict:
    new, fixed = [], []
    for t in set(before) | set(after):
        b, a = before.get(t, set()), after.get(t, set())
        new += [x for x in a - b]
        fixed += [x for x in b - a]

    def rows(items):
        return [{"entity_id": x[0], "rule": x[1], "field": x[2], "severity": x[3], "name": x[4], "display_id": x[5]}
                for x in sorted(items, key=lambda x: (x[5], x[1]))[:200]]
    entities_new = len({x[0] for x in new})
    lines = []
    if new:
        lines.append(f"{entities_new} entit{'y' if entities_new == 1 else 'ies'} will fail {len(new)} more check{'s' if len(new) != 1 else ''} "
                     "(saved anyway; they appear on the failing-checks screen)")
    if fixed:
        n = len({x[0] for x in fixed})
        lines.append(f"{n} entit{'y' if n == 1 else 'ies'} will pass {len(fixed)} check{'s' if len(fixed) != 1 else ''} they fail now")
    if not lines:
        lines.append("No change to any entity's check results")
    return {"summary": lines, "newly_failing": rows(new), "now_passing": rows(fixed),
            "newly_failing_count": len(new), "now_passing_count": len(fixed)}


# ---------------------------------------------------------------- model locks (D67)

LOCK_LEVELS = ("metamodel", "content", "maintenance")


def set_lock(conn, model: Any, level: str, reason: str, actor: str) -> dict:
    if level not in LOCK_LEVELS:
        raise EditError(f"Lock level is one of {', '.join(LOCK_LEVELS)}.")
    m = repo.get_model(conn, model)
    if m["kind"] not in ("project", "template") or m["is_locked"]:
        raise EditError(f"Model {m['name']!r} is already read-only ({m['kind_name'].lower()}).", 409)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})
    try:
        conn.execute(text("UPDATE core.models SET lock_level = :l, lock_reason = :r WHERE id = :m"),
                     {"l": level, "r": (reason or "").strip()[:500], "m": m["_id"]})
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    return repo.get_model(conn, m["id"])


def clear_lock(conn, model: Any, actor: str) -> dict:
    m = repo.get_model(conn, model)
    if m.get("lock_level", "none") == "none":
        raise EditError(f"Model {m['name']!r} is not locked.", 409)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})
    try:
        conn.execute(text("UPDATE core.models SET lock_level = 'none' WHERE id = :m"), {"m": m["_id"]})
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    return repo.get_model(conn, m["id"])
