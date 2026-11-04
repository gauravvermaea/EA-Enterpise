"""Creating, copying and sharing models (build phase 4), shared by the REST API, the job runner and MCP.

  * metamodel_spec / validate_spec / spec_diff / apply_spec: a metamodel as one JSON document
    (format eax-metamodel/1), checked, compared and written into a model. Packages, metamodel drafts
    (D115) and moving to a new framework version all use it.
  * create_model: a root metamodel (from Root or a copy of another root), a project model (from a
    root, a library model or a model of yours, metamodel only or with its content, optionally with
    its history), or a library model (Library Admins, D118). Copying content runs as a background job.
  * archive / reactivate / delete_model (Super Admins; a package is written first as the backup, D121).
  * publish / withdraw / restore / promote: the library (Library Admins, D118).
  * export_package / read_package / analyse_package / import_package: one zip (manifest.json,
    metamodel.json, one CSV per entity type and relationships.csv) or one Excel workbook (D116).
    An upload is taken to come from another installation: it is placed under its root metamodel,
    matched by name and version and matching it completely, or under Root as a root of its own (D108).
  * framework_preview / framework_move: move a model to a new framework version, as a copy with a
    type mapping or in place as one metamodel version (D121).

The database decides who may do what (row-level security and triggers, 0006 and 0008); the checks
here give clear messages first.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import uuid
import zipfile
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import repository as repo
from .metamodel_edit import EditError, _db_message, code_from, snake_from

SPEC_FORMAT = "eax-metamodel/1"
PACKAGE_FORMAT = "eax-package/1"
NS = uuid.UUID("3f4b7c58-61a5-4b0b-9d7e-0c1d2e3f4a5b")   # keys that are not guids get a guid from it
BUILT_IN_FIELDS = ("name", "description", "display_id", "relationships")


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    rows = repo._rows(conn, sql, **p)
    return rows[0] if rows else None


def _exec(conn, sql: str, **p):
    return conn.execute(text(sql), p)


def _actor(conn, actor: str | None) -> None:
    if actor:
        conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})


def _label(conn, label: str) -> None:
    conn.execute(text("SELECT set_config('eax.history_label', :l, true)"), {"l": label[:200]})


def _guid_for(key: Any) -> str:
    """A package key as a guid: itself when it is one, else a stable guid made from it."""
    try:
        return str(uuid.UUID(str(key)))
    except (ValueError, AttributeError):
        return str(uuid.uuid5(NS, str(key)))


# ================================================================ the metamodel as a document

def metamodel_spec(conn, model: Any) -> dict:
    """A model's metamodel as one JSON document (eax-metamodel/1): layers, pick lists, attributes,
    entity types with their attributes, relationship types, allowed relationships and rules, by code."""
    m = repo.get_model(conn, model)
    mid = m["_id"]
    layers = _rows(conn, """SELECT code, name, colour, description FROM core.layers
                             WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    lists = _rows(conn, """SELECT id AS _id, code, name, description FROM core.pick_lists
                            WHERE model_id = :m AND NOT is_deleted ORDER BY code""", m=mid)
    values = _rows(conn, """SELECT pick_list_id AS _p, value FROM core.pick_list_values
                             WHERE model_id = :m AND NOT is_deleted AND status_code <> 'retired' ORDER BY sort_order, value""", m=mid)
    for pl in lists:
        pl["values"] = [v["value"] for v in values if v["_p"] == pl["_id"]]
        del pl["_id"]
    attrs = _rows(conn, """SELECT a.code, a.name, a.data_type_code AS data_type, pl.code AS pick_list, a.unit, a.description
                             FROM core.attribute_types a LEFT JOIN core.pick_lists pl ON pl.id = a.pick_list_id
                            WHERE a.model_id = :m AND NOT a.is_deleted ORDER BY a.code""", m=mid)
    items = _rows(conn, """SELECT i.entity_type_id AS _t, i.relationship_type_id AS _r, a.code AS attribute,
                                  i.is_required AS required, i.section, i.default_value AS "default", i.help_text AS help
                             FROM core.item_attributes i JOIN core.attribute_types a ON a.id = i.attribute_type_id
                            WHERE i.model_id = :m AND NOT i.is_deleted ORDER BY i.sort_order, a.name""", m=mid)
    types = _rows(conn, """SELECT t.id AS _id, t.code, t.name, l.code AS layer, t.id_prefix, t.aspect, t.description,
                                  t.status_code AS status
                             FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
                            WHERE t.model_id = :m AND NOT t.is_deleted ORDER BY l.sort_order, t.sort_order, t.name""", m=mid)
    rels = _rows(conn, """SELECT id AS _id, code, name, verb, category, is_directed AS directed, description, status_code AS status
                            FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    strip = lambda i: {k: v for k, v in i.items() if not k.startswith("_")}  # noqa: E731
    for t in types:
        t["attributes"] = [strip(i) for i in items if i["_t"] == t["_id"]]
        del t["_id"]
    for r in rels:
        r["attributes"] = [strip(i) for i in items if i["_r"] == r["_id"]]
        del r["_id"]
    allowed = _rows(conn, """SELECT s.code AS source, rt.code AS relationship, t.code AS target, a.note
                               FROM core.allowed_relationships a
                               JOIN core.entity_types s ON s.id = a.source_type_id
                               JOIN core.entity_types t ON t.id = a.target_type_id
                               JOIN core.relationship_types rt ON rt.id = a.relationship_type_id
                              WHERE a.model_id = :m AND NOT a.is_deleted ORDER BY 1, 2, 3""", m=mid)
    rules = _rows(conn, """SELECT et.code AS entity_type, at.code AS attribute, vr.field_name AS field,
                                  vr.rule_type_code AS rule_type, vr.param1, vr.param2, vr.severity, vr.message
                             FROM core.validation_rules vr
                             LEFT JOIN core.entity_types et ON et.id = vr.entity_type_id
                             LEFT JOIN core.attribute_types at ON at.id = vr.attribute_type_id
                            WHERE vr.model_id = :m AND NOT vr.is_deleted ORDER BY vr.sort_order""", m=mid)
    return {"format": SPEC_FORMAT, "name": m["name"], "framework": m["metamodel_name"], "version": m["version_label"],
            "layers": layers, "pick_lists": lists, "attributes": attrs, "entity_types": types,
            "relationship_types": rels, "allowed": allowed, "rules": rules}


def empty_spec(name: str = "", framework: str = "", version: str = "") -> dict:
    return {"format": SPEC_FORMAT, "name": name, "framework": framework, "version": version, "layers": [],
            "pick_lists": [], "attributes": [], "entity_types": [], "relationship_types": [], "allowed": [], "rules": []}


def _codes(items: list[dict]) -> dict[str, dict]:
    return {str(i.get("code", "")).lower(): i for i in items}


def validate_spec(conn, spec: dict) -> list[dict]:
    """Every problem in a metamodel document, as {level: error | warning, where, message}. Errors stop
    it being applied; warnings do not."""
    out: list[dict] = []

    def err(where, msg, level="error"):
        out.append({"level": level, "where": where, "message": msg})

    if not isinstance(spec, dict):
        return [{"level": "error", "where": "", "message": "The metamodel must be a JSON object."}]
    if spec.get("format") not in (None, SPEC_FORMAT):
        err("format", f"Unknown format {spec.get('format')!r}; expected {SPEC_FORMAT}.")
    data_types = {r["code"] for r in _rows(conn, "SELECT code FROM core.data_types")}
    rule_types = {r["code"] for r in _rows(conn, "SELECT code FROM core.rule_types")}
    seen: dict[str, set] = {}
    for section in ("layers", "pick_lists", "attributes", "entity_types", "relationship_types"):
        items = spec.get(section) or []
        if not isinstance(items, list):
            err(section, f"{section} must be a list.")
            continue
        seen[section] = set()
        for n, i in enumerate(items):
            where = f"{section}[{n}]"
            code, name = str(i.get("code") or "").strip(), str(i.get("name") or "").strip()
            if not code or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", code):
                err(where, f"Code {code!r} must start with a letter and hold letters, digits and _ only.")
            if not name:
                err(where, "A name is required.")
            if code.lower() in seen[section]:
                err(where, f"Code {code!r} is used twice in {section}.")
            seen[section].add(code.lower())
    layers, lists = _codes(spec.get("layers") or []), _codes(spec.get("pick_lists") or [])
    attrs, types = _codes(spec.get("attributes") or []), _codes(spec.get("entity_types") or [])
    rels = _codes(spec.get("relationship_types") or [])
    for code, layer in layers.items():
        if layer.get("colour") and not re.fullmatch(r"#?[0-9A-Fa-f]{6}", str(layer["colour"])):
            err(f"layers.{code}", f"Colour {layer['colour']!r} must be six hexadecimal digits, for example FFE680.")
    for code, pl in lists.items():
        if not [v for v in pl.get("values") or [] if str(v).strip()]:
            err(f"pick_lists.{code}", "A pick list needs at least one value.")
    for code, a in attrs.items():
        dtp = a.get("data_type")
        if dtp not in data_types:
            err(f"attributes.{code}", f"Data type {dtp!r} is not one of {', '.join(sorted(data_types))}.")
        if dtp == "list" and not a.get("pick_list"):
            err(f"attributes.{code}", "A list attribute needs a pick list.")
        if a.get("pick_list") and str(a["pick_list"]).lower() not in lists:
            err(f"attributes.{code}", f"Pick list {a['pick_list']!r} is not in the metamodel.")
    prefixes: dict[str, str] = {}
    for code, t in types.items():
        if str(t.get("layer") or "").lower() not in layers:
            err(f"entity_types.{code}", f"Layer {t.get('layer')!r} is not in the metamodel.")
        prefix = str(t.get("id_prefix") or "").upper()
        if prefix and not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}", prefix):
            err(f"entity_types.{code}", f"Display ID prefix {prefix!r} must be 1 to 6 capital letters or digits.")
        if prefix and prefix in prefixes:
            err(f"entity_types.{code}", f"Display ID prefix {prefix} is also used by {prefixes[prefix]}.", "warning")
        prefixes.setdefault(prefix, t.get("name", code))
    for owner_section, owners in (("entity_types", types), ("relationship_types", rels)):
        for code, o in owners.items():
            for i in o.get("attributes") or []:
                if str(i.get("attribute") or "").lower() not in attrs:
                    err(f"{owner_section}.{code}", f"Attribute {i.get('attribute')!r} is not in the metamodel.")
    for code, r in rels.items():
        if not str(r.get("verb") or "").strip():
            err(f"relationship_types.{code}", "A relationship type needs a verb (for example serves).")
    keys = set()
    for n, a in enumerate(spec.get("allowed") or []):
        where = f"allowed[{n}]"
        for k, pool in (("source", types), ("target", types), ("relationship", rels)):
            if str(a.get(k) or "").lower() not in pool:
                err(where, f"{k.capitalize()} {a.get(k)!r} is not in the metamodel.")
        key = (str(a.get("source")).lower(), str(a.get("relationship")).lower(), str(a.get("target")).lower())
        if key in keys:
            err(where, "This relationship is allowed twice.", "warning")
        keys.add(key)
    from .metamodel_edit import check_rule_params
    for n, r in enumerate(spec.get("rules") or []):
        where = f"rules[{n}]"
        rt = r.get("rule_type")
        if rt not in rule_types:
            err(where, f"Rule type {rt!r} is not one of {', '.join(sorted(rule_types))}.")
            continue
        if r.get("entity_type") and str(r["entity_type"]).lower() not in types:
            err(where, f"Entity type {r['entity_type']!r} is not in the metamodel.")
        if rt == "has_relationship":
            if r.get("attribute"):
                err(where, "A Has relationship rule checks relationships, not an attribute.")
        elif bool(r.get("attribute")) == bool(r.get("field")):
            err(where, "Give either the attribute or the built-in field (name, description, display_id) the rule checks.")
        elif r.get("attribute") and str(r["attribute"]).lower() not in attrs:
            err(where, f"Attribute {r['attribute']!r} is not in the metamodel.")
        elif r.get("field") and r["field"] not in BUILT_IN_FIELDS:
            err(where, f"Field {r['field']!r} is not one of name, description, display_id.")
        if r.get("severity", "error") not in ("error", "warning"):
            err(where, "Severity is error or warning.")
        try:
            check_rule_params(rt, r.get("param1"), r.get("param2"))
        except EditError as exc:
            err(where, str(exc))
    if not types:
        err("entity_types", "The metamodel has no entity types yet.", "warning")
    return out


_FIELDS = {
    "layers": ("name", "colour", "description"),
    "pick_lists": ("name", "description", "values"),
    "attributes": ("name", "data_type", "pick_list", "unit", "description"),
    "entity_types": ("name", "layer", "id_prefix", "aspect", "description", "attributes"),
    "relationship_types": ("name", "verb", "category", "directed", "description", "attributes"),
}


def _norm(v):
    if isinstance(v, str):
        return v.strip().lower() or None
    if isinstance(v, list):
        return sorted(json.dumps(_norm(x), sort_keys=True) if isinstance(x, dict) else str(_norm(x)) for x in v)
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items() if x not in (None, "", False, [])}
    return v if v not in (None, False, "") else None


def spec_diff(a: dict, b: dict) -> list[dict]:
    """What differs from metamodel document a to b: items added, removed or changed (with the fields),
    by code; allowed relationships and rules as whole rows. Order and letter case do not count."""
    out: list[dict] = []
    for section, fields in _FIELDS.items():
        ia, ib = _codes(a.get(section) or []), _codes(b.get(section) or [])
        for code in sorted(set(ia) | set(ib)):
            x, y = ia.get(code), ib.get(code)
            if x is None:
                out.append({"section": section, "code": y.get("code"), "name": y.get("name"), "change": "added", "fields": []})
            elif y is None:
                out.append({"section": section, "code": x.get("code"), "name": x.get("name"), "change": "removed", "fields": []})
            else:
                changed = [f for f in fields if _norm(x.get(f)) != _norm(y.get(f))]
                if changed:
                    out.append({"section": section, "code": y.get("code"), "name": y.get("name"), "change": "changed",
                                "fields": [{"field": f, "old": _show(x.get(f)), "new": _show(y.get(f))} for f in changed]})
    for section, key in (("allowed", ("source", "relationship", "target")),
                         ("rules", ("entity_type", "attribute", "field", "rule_type", "param1", "param2", "severity"))):
        row = lambda r, key=key: tuple(str(r.get(k) or "").strip().lower() for k in key)  # noqa: E731
        ka, kb = {row(r): r for r in a.get(section) or []}, {row(r): r for r in b.get(section) or []}
        for k in sorted(set(ka) - set(kb)):
            out.append({"section": section, "code": " ".join(x for x in k if x), "name": "", "change": "removed", "fields": []})
        for k in sorted(set(kb) - set(ka)):
            out.append({"section": section, "code": " ".join(x for x in k if x), "name": "", "change": "added", "fields": []})
    return out


def _show(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, list):
        return ", ".join(str(x.get("attribute", x)) if isinstance(x, dict) else str(x) for x in v)
    return str(v)


def apply_spec(conn, model_id: int, spec: dict, mode: str = "new", remove_missing: bool = False) -> dict:
    """Writes a metamodel document into a model. mode "new": the model has no metamodel yet. mode
    "merge": items whose code is already there are updated, the rest added; with remove_missing, entity
    and relationship types the document leaves out are retired and its missing mappings and rules
    removed. The caller publishes the metamodel version (merge) and has checked the document."""
    counts = {"added": 0, "changed": 0, "removed": 0}

    def have(table, code):
        return _one(conn, f"SELECT id FROM core.{table} WHERE model_id = :m AND lower(code) = lower(:c) AND NOT is_deleted",
                    m=model_id, c=code)

    def upsert(table, code, cols: dict):
        row = have(table, code) if mode == "merge" else None
        if row:
            sets = ", ".join(f"{k} = :{k}" for k in cols)
            old = _one(conn, f"SELECT {', '.join(cols)} FROM core.{table} WHERE id = :i", i=row["id"])
            if any(old[k] != v for k, v in cols.items()):
                _exec(conn, f"UPDATE core.{table} SET {sets} WHERE id = :i", i=row["id"], **cols)
                counts["changed"] += 1
            return row["id"]
        names = ", ".join(["model_id", "code", *cols])
        vals = ", ".join([":m", ":code", *(f":{k}" for k in cols)])
        counts["added"] += 1
        return _one(conn, f"INSERT INTO core.{table} ({names}) VALUES ({vals}) RETURNING id", m=model_id, code=code, **cols)["id"]

    ids: dict[str, dict[str, int]] = {"layers": {}, "pick_lists": {}, "attributes": {}, "entity_types": {}, "relationship_types": {}}
    taken = {"table_name": {r["n"] for r in _rows(conn, "SELECT lower(table_name) AS n FROM core.entity_types WHERE model_id = :m", m=model_id)},
             "column_name": {r["n"] for r in _rows(conn, "SELECT lower(column_name) AS n FROM core.attribute_types WHERE model_id = :m",
                                                   m=model_id)}}

    def free(kind: str, wanted: str) -> str:
        base = (wanted or "x")[:56]
        out, n = base, 2
        while out.lower() in taken[kind]:
            out, n = f"{base}_{n}", n + 1
        taken[kind].add(out.lower())
        return out
    for n, layer in enumerate(spec.get("layers") or []):
        ids["layers"][layer["code"].lower()] = upsert("layers", layer["code"], {
            "name": layer["name"].strip(), "colour": str(layer.get("colour") or "DDDDDD").lstrip("#").upper(),
            "description": layer.get("description") or "", "sort_order": (n + 1) * 10})
    for pl in spec.get("pick_lists") or []:
        pid = upsert("pick_lists", pl["code"], {"name": pl["name"].strip(), "description": pl.get("description") or ""})
        ids["pick_lists"][pl["code"].lower()] = pid
        existing = {r["value"]: r for r in _rows(conn, """SELECT id, value, is_deleted, status_code FROM core.pick_list_values
                                                          WHERE pick_list_id = :p""", p=pid)}
        for k, v in enumerate(pl.get("values") or []):
            v = str(v).strip()
            if not v:
                continue
            old = existing.get(v)
            if old is None:
                _exec(conn, "INSERT INTO core.pick_list_values (model_id, pick_list_id, value, sort_order) VALUES (:m, :p, :v, :s)",
                      m=model_id, p=pid, v=v, s=(k + 1) * 10)
                counts["added"] += 1
            elif old["is_deleted"] or old["status_code"] == "retired":
                _exec(conn, "UPDATE core.pick_list_values SET is_deleted = false, status_code = 'published' WHERE id = :i", i=old["id"])
                counts["changed"] += 1
    for a in spec.get("attributes") or []:
        ids["attributes"][a["code"].lower()] = upsert("attribute_types", a["code"], {
            "name": a["name"].strip(), "data_type_code": a["data_type"],
            "pick_list_id": ids["pick_lists"].get(str(a.get("pick_list") or "").lower()),
            "unit": a.get("unit") or "", "description": a.get("description") or "",
            **({} if mode == "merge" and have("attribute_types", a["code"]) else
               {"column_name": free("column_name", snake_from(a["name"]) or a["code"].lower())})})
    used_prefix: set[str] = set()
    for n, t in enumerate(spec.get("entity_types") or []):
        prefix = (str(t.get("id_prefix") or "").upper() or re.sub(r"[^A-Z]", "", t["name"].upper())[:3] or "ENT")[:6]
        while prefix in used_prefix:
            prefix = (prefix[:5] + "X")[:6]
        used_prefix.add(prefix)
        cols = {"name": t["name"].strip(), "layer_id": ids["layers"][t["layer"].lower()], "id_prefix": prefix,
                "aspect": t.get("aspect") or "", "description": t.get("description") or "", "sort_order": (n + 1) * 10}
        if mode == "new" or not have("entity_types", t["code"]):
            cols["table_name"] = free("table_name", snake_from(t["name"]) or t["code"].lower())
        tid = upsert("entity_types", t["code"], cols)
        ids["entity_types"][t["code"].lower()] = tid
        if mode == "merge" and t.get("status") != "retired":
            _exec(conn, "UPDATE core.entity_types SET status_code = 'published' WHERE id = :i AND status_code = 'retired'", i=tid)
    for n, r in enumerate(spec.get("relationship_types") or []):
        ids["relationship_types"][r["code"].lower()] = upsert("relationship_types", r["code"], {
            "name": r["name"].strip(), "verb": (r.get("verb") or "").strip(), "category": r.get("category") or "",
            "is_directed": bool(r.get("directed", True)), "description": r.get("description") or "", "sort_order": (n + 1) * 10})

    # attributes on types
    for owner_section, col in (("entity_types", "entity_type_id"), ("relationship_types", "relationship_type_id")):
        for o in spec.get(owner_section) or []:
            oid = ids[owner_section][o["code"].lower()]
            for k, i in enumerate(o.get("attributes") or []):
                aid = ids["attributes"][str(i["attribute"]).lower()]
                cols = {"is_required": bool(i.get("required")), "section": i.get("section") or "",
                        "default_value": None if i.get("default") in (None, "") else str(i["default"]),
                        "help_text": i.get("help") or "", "sort_order": (k + 1) * 10}
                old = _one(conn, f"""SELECT id, is_deleted FROM core.item_attributes WHERE {col} = :o AND attribute_type_id = :a""",
                           o=oid, a=aid)
                if old:
                    sets = ", ".join(f"{c} = :{c}" for c in cols)
                    _exec(conn, f"UPDATE core.item_attributes SET {sets}, is_deleted = false WHERE id = :i", i=old["id"], **cols)
                else:
                    _exec(conn, f"""INSERT INTO core.item_attributes (model_id, attribute_type_id, {col}, is_required, section,
                                     default_value, help_text, sort_order)
                                    VALUES (:m, :a, :o, :is_required, :section, :default_value, :help_text, :sort_order)""",
                          m=model_id, a=aid, o=oid, **cols)
                    counts["added"] += 1
    # allowed relationships
    wanted = set()
    for a in spec.get("allowed") or []:
        s, r, t = (ids["entity_types"][a["source"].lower()], ids["relationship_types"][a["relationship"].lower()],
                   ids["entity_types"][a["target"].lower()])
        wanted.add((r, s, t))
        old = _one(conn, """SELECT id, is_deleted FROM core.allowed_relationships
                             WHERE relationship_type_id = :r AND source_type_id = :s AND target_type_id = :t""", r=r, s=s, t=t)
        if not old:
            _exec(conn, """INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id, note)
                           VALUES (:m, :r, :s, :t, :n)""", m=model_id, r=r, s=s, t=t, n=a.get("note") or "")
            counts["added"] += 1
        elif old["is_deleted"]:
            _exec(conn, "UPDATE core.allowed_relationships SET is_deleted = false WHERE id = :i", i=old["id"])
            counts["added"] += 1
    # rules
    def rule_key(r):
        return (r.get("entity_type_id"), r.get("attribute_type_id"), r.get("field_name") or None, r["rule_type_code"],
                str(r.get("param1") or ""), str(r.get("param2") or ""))
    existing_rules = {rule_key(r): r for r in _rows(conn, """SELECT id, entity_type_id, attribute_type_id, field_name, rule_type_code,
                                                                     param1, param2 FROM core.validation_rules
                                                                WHERE model_id = :m AND NOT is_deleted""", m=model_id)}
    wanted_rules = set()
    for n, r in enumerate(spec.get("rules") or []):
        field = "relationships" if r["rule_type"] == "has_relationship" else (r.get("field") or None)
        row = {"entity_type_id": ids["entity_types"].get(str(r.get("entity_type") or "").lower()),
               "attribute_type_id": ids["attributes"].get(str(r.get("attribute") or "").lower()) if not field else None,
               "field_name": field, "rule_type_code": r["rule_type"], "param1": str(r.get("param1") or ""),
               "param2": str(r.get("param2") or "")}
        k = rule_key(row)
        wanted_rules.add(k)
        if k in existing_rules:
            _exec(conn, "UPDATE core.validation_rules SET severity = :s, message = :msg WHERE id = :i",
                  s=r.get("severity") or "error", msg=r.get("message") or r["rule_type"], i=existing_rules[k]["id"])
            continue
        _exec(conn, """INSERT INTO core.validation_rules (model_id, entity_type_id, attribute_type_id, field_name, rule_type_code,
                                                          param1, param2, severity, message, sort_order)
                       VALUES (:m, :entity_type_id, :attribute_type_id, :field_name, :rule_type_code, :param1, :param2, :sev,
                               :msg, :s)""",
              m=model_id, sev=r.get("severity") or "error",
              msg=(r.get("message") or "").strip() or f"{r.get('attribute') or field or 'value'}: {r['rule_type']}",
              s=1000 + n * 10, **row)
        counts["added"] += 1
    if mode == "merge" and remove_missing:
        keep_types = set(ids["entity_types"].values())
        keep_rels = set(ids["relationship_types"].values())
        counts["removed"] += _exec(conn, """UPDATE core.entity_types SET status_code = 'retired'
            WHERE model_id = :m AND NOT is_deleted AND status_code <> 'retired' AND NOT (id = ANY (:k))""",
                                   m=model_id, k=list(keep_types)).rowcount
        counts["removed"] += _exec(conn, """UPDATE core.relationship_types SET status_code = 'retired'
            WHERE model_id = :m AND NOT is_deleted AND status_code <> 'retired' AND NOT (id = ANY (:k))""",
                                   m=model_id, k=list(keep_rels)).rowcount
        for a in _rows(conn, """SELECT id, relationship_type_id AS r, source_type_id AS s, target_type_id AS t
                                  FROM core.allowed_relationships WHERE model_id = :m AND NOT is_deleted""", m=model_id):
            if (a["r"], a["s"], a["t"]) not in wanted:
                _exec(conn, "UPDATE core.allowed_relationships SET is_deleted = true WHERE id = :i", i=a["id"])
                counts["removed"] += 1
        for k, r in existing_rules.items():
            if k not in wanted_rules:
                _exec(conn, "UPDATE core.validation_rules SET is_deleted = true WHERE id = :i", i=r["id"])
                counts["removed"] += 1
    return counts


# ================================================================ creating and copying models

def _model_row(conn, guid) -> dict:
    return _one(conn, "SELECT * FROM core.models WHERE guid = CAST(:g AS uuid)", g=str(guid))


def _create_row(conn, *, name: str, kind: str, source_id: int | None, parent_id: int | None = None,
                description: str = "", metamodel_name: str = "", owner: str = "", industry: str = "",
                version_label: str = "", history_from_source: bool = False) -> dict:
    name = (name or "").strip()
    if not name:
        raise EditError("Give the new model a name.")
    if _one(conn, """SELECT 1 AS x FROM core.models WHERE NOT is_deleted AND lower(name) = lower(:n) AND version_label = :v""",
            n=name, v=version_label or ""):
        raise EditError(f"A model called {name!r}{' version ' + version_label if version_label else ''} already exists.", 409)
    try:
        return _one(conn, """INSERT INTO core.models (name, kind_code, source_model_id, parent_model_id, description,
                                                       metamodel_name, owner, industry, version_label, history_from_source)
                              VALUES (:n, :k, :s, :p, :d, :mm, :o, :i, :v, :h)
                              RETURNING id, guid, name, kind_code, library_state""",
                    n=name, k=kind, s=source_id, p=parent_id, d=description or "", mm=metamodel_name or "", o=owner or "",
                    i=industry or "", v=version_label or "", h=history_from_source)
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403 if "Not allowed" in str(exc.orig) else 409) from exc


def copy_into(conn, src_id: int, dst_id: int, content: bool) -> dict:
    """Copies src's metamodel (and with content its entities, values and relationships) into dst."""
    try:
        counts = conn.execute(text("SELECT core.copy_model(:s, :d, :c)"), {"s": src_id, "d": dst_id, "c": content}).scalar_one()
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    return dict(counts or {})


def create_model(conn, actor: str, p: dict) -> dict:
    """A new model (D81, D97, D118):
      kind root        a root metamodel: from Root (empty) or a copy of another root's metamodel (`source`)
      kind project     from `source` (a root, a library model or a model you may read): `copy` metadata
                       (metamodel only), content (metamodel and content) or history (and its entities show
                       their source's history); `parent` makes it derive from (merge back into) that model
      kind library     a library model (Library Admins): a reference model built from `source` with its
                       content, left building (editable) until published
    Returns the model and, when content is copied, the background job that copies it (run here when
    `wait` is true)."""
    _actor(conn, actor)
    kind = p.get("kind") or "project"
    if kind not in ("root", "project", "library"):
        raise EditError("Kind is root, project or library.")
    src = repo.get_model(conn, p["source"]) if p.get("source") else None
    parent = repo.get_model(conn, p["parent"]) if p.get("parent") else None
    if parent:
        if parent["kind"] != "project":
            raise EditError("A model can derive (merge back) only from a project model; build on a root or library model instead.")
        src = src or parent
    copy = p.get("copy") or ("metamodel" if kind == "root" else "content")
    if copy not in ("metamodel", "content", "history"):
        raise EditError("Copy is metamodel, content or history.")
    if kind == "root":
        if src and src["kind"] != "template":
            raise EditError("A root metamodel starts from Root or from another root metamodel.")
        root_top = _one(conn, "SELECT id, guid, name FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL "
                              "AND NOT is_deleted ORDER BY id LIMIT 1")
        from_id = src["_id"] if src else root_top["id"]
        row = _create_row(conn, name=p.get("name"), kind="template", source_id=from_id, description=p.get("description", ""),
                          metamodel_name=p.get("framework") or p.get("name"), owner=p.get("owner", ""),
                          version_label=p.get("version_label", ""))
        counts = copy_into(conn, src["_id"], row["id"], False) if src and src["_id"] != root_top["id"] else {}
        _label(conn, f"Created root metamodel {row['name']}")
        return {"model": repo.get_model(conn, str(row["guid"])), "copied": counts, "job": None}
    if not src:
        raise EditError("Choose the root metamodel, library model or model to start from.")
    if kind == "library":
        row = _create_row(conn, name=p.get("name"), kind="reference", source_id=src["_id"], description=p.get("description", ""),
                          metamodel_name=src["metamodel_name"], owner=p.get("owner", ""), industry=p.get("industry", ""),
                          version_label=p.get("version_label") or "0.1")
        content = src["kind"] != "template"
    else:
        row = _create_row(conn, name=p.get("name"), kind="project", source_id=src["_id"], parent_id=parent["_id"] if parent else None,
                          description=p.get("description", ""), metamodel_name=src["metamodel_name"], owner=p.get("owner", ""),
                          industry=src.get("industry", ""), history_from_source=(copy == "history"))
        content = copy in ("content", "history") and src["kind"] != "template"
    if not content:
        counts = copy_into(conn, src["_id"], row["id"], False)
        return {"model": repo.get_model(conn, str(row["guid"])), "copied": counts, "job": None}
    # content: the metamodel now, the content in the background
    _exec(conn, "UPDATE core.models SET copy_state = 'copying', copy_note = :n WHERE id = :i",
          i=row["id"], n=f"Copying the content of {src['name']}")
    return {"model": repo.get_model(conn, str(row["guid"])), "copied": {}, "job": None,
            "_copy": {"source": str(src["id"]), "target": str(row["guid"])}}


def run_copy(conn, source: str, target: str, actor: str, publish: bool = False) -> dict:
    """The background part of a copy: fills `target` from `source` (metamodel and content), then marks it
    done (or failed with the reason). With publish, a Library Admin's promotion is locked into the library."""
    _actor(conn, actor)
    src, dst = _model_row(conn, source), _model_row(conn, target)
    if not src or not dst:
        raise EditError("The model to copy from or into is gone.", 404)
    _label(conn, f"Copied from {src['name']}")
    counts = copy_into(conn, src["id"], dst["id"], src["kind_code"] != "template")
    note = "Copied from {}: {}".format(src["name"], ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items() if v))
    _exec(conn, "UPDATE core.models SET copy_state = '', copy_note = :n WHERE id = :i", i=dst["id"], n=note[:500])
    if publish:
        _exec(conn, "UPDATE core.models SET is_locked = true, library_state = 'published' WHERE id = :i", i=dst["id"])
    return counts


def copy_failed(conn, target: str, reason: str) -> None:
    _exec(conn, "UPDATE core.models SET copy_state = 'failed', copy_note = :n WHERE guid = CAST(:g AS uuid)",
          g=target, n=f"The copy failed: {reason}"[:500])


# ================================================================ lifecycle

def set_lifecycle(conn, model: Any, archived: bool, actor: str) -> dict:
    _actor(conn, actor)
    m = repo.get_model(conn, model)
    if m["is_locked"]:
        raise EditError(f"{m['name']} is a published library model: a Library Admin withdraws it instead.", 409)
    try:
        _exec(conn, "UPDATE core.models SET lifecycle = :l WHERE id = :i", i=m["_id"], l="archived" if archived else "active")
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403 if "Not allowed" in str(exc.orig) else 409) from exc
    return repo.get_model(conn, model)


def delete_model(conn, model: Any, confirm_name: str, actor: str, backup_dir: str | None) -> dict:
    """Deletes a model (Super Admins): after the name is typed, a package of it is written to the
    exports folder as its backup; the database refuses while other models depend on it (D121)."""
    _actor(conn, actor)
    m = repo.get_model(conn, model)
    if (confirm_name or "").strip() != m["name"]:
        raise EditError(f"Type the model's name exactly ({m['name']}) to delete it.")
    if m["is_locked"]:
        raise EditError(f"{m['name']} is a published library model: withdraw it instead.", 409)
    deps = _rows(conn, """SELECT name FROM core.models WHERE NOT is_deleted AND id <> :i
                           AND (parent_model_id = :i OR source_model_id = :i) ORDER BY name""", i=m["_id"])
    if deps:
        raise EditError(f"{m['name']} cannot be deleted: {', '.join(d['name'] for d in deps)} "
                        f"{'is' if len(deps) == 1 else 'are'} built on it. Archive it instead.", 409)
    backup = None
    if backup_dir:
        import os
        data, filename, _ = export_package(conn, model, "zip")
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, f"deleted-{stamp}-{filename}")
        with open(backup, "wb") as f:
            f.write(data)
    try:
        _label(conn, f"Deleted model {m['name']}")
        _exec(conn, "UPDATE core.models SET is_deleted = true WHERE id = :i", i=m["_id"])
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403 if "Not allowed" in str(exc.orig) else 409) from exc
    return {"deleted": m["name"], "backup": backup}


# ================================================================ the library (D118)

def publish(conn, model: Any, actor: str) -> dict:
    """A Library Admin publishes a root or library model that was being built: it is locked (read-only)."""
    _actor(conn, actor)
    m = repo.get_model(conn, model)
    if m["kind"] not in ("template", "reference"):
        raise EditError("Only root metamodels and library (reference) models are published.")
    if m["is_locked"]:
        raise EditError(f"{m['name']} is already published.", 409)
    if m["copy_state"] == "copying":
        raise EditError(f"{m['name']} is still being copied; publish it when the copy is done.", 409)
    try:
        _exec(conn, "UPDATE core.models SET is_locked = true, library_state = 'published' WHERE id = :i", i=m["_id"])
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403) from exc
    return repo.get_model(conn, model)


def withdraw(conn, model: Any, actor: str, restore: bool = False) -> dict:
    _actor(conn, actor)
    m = repo.get_model(conn, model)
    if m["kind"] not in ("template", "reference"):
        raise EditError("Only library models are withdrawn.")
    if m["name"] == "Root" and m["source_model_id"] is None:
        raise EditError("The Root model is the top of the hierarchy and stays.", 409)
    state = ("published" if m["is_locked"] else "building") if restore else "withdrawn"
    try:
        _exec(conn, "UPDATE core.models SET library_state = :s WHERE id = :i", i=m["_id"], s=state)
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403) from exc
    return repo.get_model(conn, model)


def promote(conn, model: Any, p: dict, actor: str) -> dict:
    """A Library Admin promotes a model into the library: a copy of it (metamodel and content) becomes a
    library model (a root when the model is a root), published once the copy is done."""
    m = repo.get_model(conn, model)
    kind = "root" if m["kind"] == "template" else "library"
    out = create_model(conn, actor, {"kind": kind, "source": str(m["id"]), "name": p.get("name") or m["name"],
                                     "version_label": p.get("version_label") or "1.0", "industry": p.get("industry", ""),
                                     "description": p.get("description") or m["description"], "owner": p.get("owner", "")})
    if out.get("_copy"):
        out["_copy"]["publish"] = True
    else:
        out["model"] = publish(conn, str(out["model"]["id"]), actor)
    return out


# ================================================================ packages (D116, D108)

def _value_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v)


def package_content(conn, model: Any) -> dict:
    """A model's content by entity type code: rows of key, display_id, name, description, parent, status
    and one column per attribute code; and its relationships."""
    m = repo.get_model(conn, model)
    mid = m["_id"]
    ents = _rows(conn, """SELECT e.id AS _id, e.guid AS key, e.display_id, e.name, e.description, p.guid AS parent,
                                 e.status_code AS status, t.code AS _type
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                            LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                           WHERE e.model_id = :m AND NOT e.is_deleted ORDER BY t.code, e.display_id""", m=mid)
    vals = _rows(conn, """SELECT v.entity_id AS e, v.relationship_id AS r, a.code, v.value_text, v.value_number, v.value_date,
                                 v.value_bool, ref.guid AS ref
                            FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                            LEFT JOIN core.entities ref ON ref.id = v.value_ref
                           WHERE v.model_id = :m AND NOT v.is_deleted""", m=mid)
    by_owner: dict[tuple, dict] = {}
    for v in vals:
        x = next((y for y in (v["value_text"], v["value_number"], v["value_date"], v["value_bool"], v["ref"]) if y is not None), None)
        by_owner.setdefault(("e", v["e"]) if v["e"] else ("r", v["r"]), {})[v["code"]] = _value_text(x)
    types: dict[str, list[dict]] = {}
    for e in ents:
        row = {k: _value_text(e[k]) for k in ("key", "display_id", "name", "description", "parent", "status")}
        row.update(by_owner.get(("e", e["_id"]), {}))
        types.setdefault(e["_type"], []).append(row)
    rels = _rows(conn, """SELECT r.id AS _id, r.guid AS key, rt.code AS type, s.guid AS source, t.guid AS target, r.name,
                                 r.description, r.status_code AS status
                            FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                            JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted
                            JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted
                           WHERE r.model_id = :m AND NOT r.is_deleted ORDER BY rt.code, s.display_id""", m=mid)
    rel_rows = []
    for r in rels:
        row = {k: _value_text(r[k]) for k in ("key", "type", "source", "target", "name", "description", "status")}
        row.update(by_owner.get(("r", r["_id"]), {}))
        rel_rows.append(row)
    return {"entities": types, "relationships": rel_rows}


def _manifest(conn, m: dict, spec: dict, content: dict, actor: str | None = None) -> dict:
    root = None
    chain = _rows(conn, """WITH RECURSIVE up AS (SELECT id, source_model_id, 0 AS d FROM core.models WHERE id = :i
                             UNION ALL SELECT x.id, x.source_model_id, up.d + 1 FROM core.models x JOIN up ON x.id = up.source_model_id)
                           SELECT m.guid, m.name, m.version_label, m.kind_code, m.source_model_id, up.d
                             FROM up JOIN core.models m ON m.id = up.id ORDER BY up.d""", i=m["_id"])
    for c in chain:   # the root metamodel it is built on: the last template before Root
        if c["kind_code"] == "template" and c["source_model_id"] is not None:
            root = {"name": c["name"], "version": c["version_label"], "guid": str(c["guid"])}
    return {"format": PACKAGE_FORMAT, "exported_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "exported_by": actor or "", "product": "EA Explorer",
            "model": {"name": m["name"], "kind": m["kind"], "description": m["description"], "industry": m["industry"],
                      "version": m["version_label"], "owner": m["owner"], "framework": m["metamodel_name"]},
            "built_on": root,
            "counts": {"entity_types": len(spec["entity_types"]), "entities": sum(len(v) for v in content["entities"].values()),
                       "relationships": len(content["relationships"])}}


def _csv(rows: list[dict], first: list[str]) -> bytes:
    cols = list(first) + sorted({k for r in rows for k in r} - set(first))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in cols})
    return buf.getvalue().encode("utf-8-sig")


ENTITY_COLS = ["key", "display_id", "name", "description", "parent", "status"]
REL_COLS = ["key", "type", "source", "target", "name", "description", "status"]


def export_package(conn, model: Any, fmt: str = "zip", actor: str | None = None) -> tuple[bytes, str, str]:
    """One model as a package: a zip (manifest.json, metamodel.json, entities/<TypeCode>.csv,
    relationships.csv) or one Excel workbook (D116). Returns (bytes, file name, content type)."""
    m = repo.get_model(conn, model)
    spec = metamodel_spec(conn, model)
    content = package_content(conn, model) if m["kind"] != "template" else {"entities": {}, "relationships": []}
    manifest = _manifest(conn, m, spec, content, actor)
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{m['name']} {m['version_label']}".strip()).strip("-") or "model"
    if fmt == "xlsx":
        return _to_xlsx(manifest, spec, content), f"{base}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        z.writestr("metamodel.json", json.dumps(spec, indent=2, ensure_ascii=False, default=str))
        for code, rows in content["entities"].items():
            z.writestr(f"entities/{code}.csv", _csv(rows, ENTITY_COLS))
        if content["relationships"]:
            z.writestr("relationships.csv", _csv(content["relationships"], REL_COLS))
        z.writestr("README.txt", "EA Explorer model package (eax-package/1). manifest.json says what it is and what it is built "
                                 "on; metamodel.json is the metamodel (eax-metamodel/1); entities/<TypeCode>.csv hold the "
                                 "entities of each type (key, display_id, name, description, parent, status, then one column per "
                                 "attribute code); relationships.csv the relationships (key, type, source, target, ...).\n")
    return buf.getvalue(), f"{base}.zip", "application/zip"


_XL_SHEETS = [  # sheet, section, columns
    ("Layers", "layers", ["code", "name", "colour", "description"]),
    ("Pick lists", "pick_lists", ["code", "name", "description", "values"]),
    ("Attributes", "attributes", ["code", "name", "data_type", "pick_list", "unit", "description"]),
    ("Entity types", "entity_types", ["code", "name", "layer", "id_prefix", "aspect", "description", "status"]),
    ("Relationship types", "relationship_types", ["code", "name", "verb", "category", "directed", "description", "status"]),
    ("Allowed", "allowed", ["source", "relationship", "target", "note"]),
    ("Rules", "rules", ["entity_type", "attribute", "field", "rule_type", "param1", "param2", "severity", "message"]),
]
_XL_ITEMS = ["owner", "code", "attribute", "required", "section", "default", "help"]


def _to_xlsx(manifest: dict, spec: dict, content: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Manifest"
    ws.append(["EA Explorer model package", PACKAGE_FORMAT])
    ws.append(["manifest", json.dumps(manifest, ensure_ascii=False)])
    for k, v in manifest["model"].items():
        ws.append([k, v])
    if manifest.get("built_on"):
        ws.append(["built on", f"{manifest['built_on']['name']} {manifest['built_on']['version']}".strip()])
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")

    def sheet(title, cols, rows):
        s = wb.create_sheet(title[:31])
        s.append(cols)
        for c in s[1]:
            c.font, c.fill = bold, fill
        for r in rows:
            s.append([("\n".join(r[c]) if isinstance(r.get(c), list) and c == "values" else
                       ("yes" if r.get(c) is True else "no" if r.get(c) is False else r.get(c))) for c in cols])
        s.freeze_panes = "A2"
        return s
    for title, section, cols in _XL_SHEETS:
        sheet(title, cols, spec.get(section) or [])
    items = [{"owner": "entity_type", "code": t["code"], **i} for t in spec["entity_types"] for i in t.get("attributes") or []]
    items += [{"owner": "relationship_type", "code": r["code"], **i} for r in spec["relationship_types"] for i in r.get("attributes") or []]
    sheet("Type attributes", _XL_ITEMS, items)
    used = set(wb.sheetnames)
    for code, rows in content["entities"].items():
        title = f"E {code}"[:31]
        while title in used:
            title = title[:29] + str(len(used))
        used.add(title)
        cols = ENTITY_COLS + sorted({k for r in rows for k in r} - set(ENTITY_COLS))
        s = sheet(title, cols, rows)
        s["A1"].comment = None
    if content["relationships"]:
        rows = content["relationships"]
        sheet("Relationships", REL_COLS + sorted({k for r in rows for k in r} - set(REL_COLS)), rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def read_package(data: bytes, filename: str = "") -> dict:
    """A package file (zip or Excel) as {manifest, spec, entities: {type code: rows}, relationships}."""
    if data[:2] != b"PK":
        raise EditError("This is not a package: upload the .zip or .xlsx that EA Explorer made.")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if "manifest.json" in names and "metamodel.json" in names:
            manifest = json.loads(z.read("manifest.json"))
            spec = json.loads(z.read("metamodel.json"))
            ents: dict[str, list[dict]] = {}
            for n in names:
                if n.startswith("entities/") and n.endswith(".csv"):
                    ents[n[len("entities/"):-4]] = list(csv.DictReader(io.StringIO(z.read(n).decode("utf-8-sig"))))
            rels = list(csv.DictReader(io.StringIO(z.read("relationships.csv").decode("utf-8-sig")))) \
                if "relationships.csv" in names else []
            return {"manifest": manifest, "spec": spec, "entities": ents, "relationships": rels, "format": "zip"}
        if "xl/workbook.xml" in names:
            return _from_xlsx(data)
    raise EditError("This zip is not an EA Explorer package: it has no manifest.json and metamodel.json.")


def _from_xlsx(data: bytes) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    if "Manifest" not in wb.sheetnames:
        raise EditError("This workbook is not an EA Explorer package: it has no Manifest sheet.")
    manifest = None
    for row in wb["Manifest"].iter_rows(values_only=True):
        if row and row[0] == "manifest" and row[1]:
            manifest = json.loads(row[1])
    if not manifest:
        raise EditError("The Manifest sheet has no manifest row.")

    def rows_of(title):
        if title not in wb.sheetnames:
            return []
        it = wb[title].iter_rows(values_only=True)
        head = [str(h) if h is not None else "" for h in next(it, [])]
        out = []
        for r in it:
            if r is None or all(v in (None, "") for v in r):
                continue
            out.append({h: ("" if v is None else v) for h, v in zip(head, r, strict=False) if h})
        return out
    spec = empty_spec(manifest["model"]["name"], manifest["model"].get("framework", ""), manifest["model"].get("version", ""))
    for title, section, _cols in _XL_SHEETS:
        spec[section] = [{k: v for k, v in r.items()} for r in rows_of(title)]
    for pl in spec["pick_lists"]:
        pl["values"] = [v for v in str(pl.get("values") or "").split("\n") if v.strip()]
    for r in spec["relationship_types"]:
        r["directed"] = str(r.get("directed", "yes")).lower() in ("yes", "true", "1")
    for section in ("entity_types", "relationship_types"):
        for o in spec[section]:
            o["attributes"] = []
    owners = {("entity_type", t["code"].lower()): t for t in spec["entity_types"]}
    owners.update({("relationship_type", r["code"].lower()): r for r in spec["relationship_types"]})
    for i in rows_of("Type attributes"):
        o = owners.get((i.get("owner"), str(i.get("code", "")).lower()))
        if o is not None:
            o["attributes"].append({"attribute": i.get("attribute"), "required": str(i.get("required")).lower() in ("yes", "true", "1"),
                                    "section": i.get("section") or "", "default": i.get("default") or None, "help": i.get("help") or ""})
    for r in spec["rules"]:
        for k in ("entity_type", "attribute", "field"):
            r[k] = r.get(k) or None
    ents = {}
    for title in wb.sheetnames:
        if title.startswith("E "):
            rows = rows_of(title)
            ents[title[2:]] = [{k: ("" if v is None else (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v)))
                                for k, v in r.items()} for r in rows]
    # sheet names may be cut short: match them to type codes
    codes = {t["code"]: t["code"] for t in spec["entity_types"]}
    fixed = {}
    for k, rows in ents.items():
        code = codes.get(k) or next((c for c in codes if c.startswith(k[:28])), k)
        fixed[code] = rows
    rels = [{k: str(v) for k, v in r.items()} for r in rows_of("Relationships")]
    return {"manifest": manifest, "spec": spec, "entities": fixed, "relationships": rels, "format": "xlsx"}


def _roots(conn) -> list[dict]:
    return _rows(conn, """SELECT id AS _id, guid AS id, name, version_label, metamodel_name, library_state, source_model_id IS NULL AS top
                            FROM core.models WHERE kind_code = 'template' AND NOT is_deleted AND library_state <> 'withdrawn'
                           ORDER BY name, version_label""")


def analyse_package(conn, pkg: dict) -> dict:
    """What a package holds and where it can go (D108): under a root metamodel its metamodel matches
    completely (every root is listed, the one with the package's root name and version first, with the
    differences of those that do not match), or under Root as a root of its own with everything it carries."""
    man = pkg["manifest"]
    spec = pkg["spec"]
    findings = validate_spec(conn, spec)
    built_on = man.get("built_on") or {}
    places = []
    missing = None
    kind = man.get("model", {}).get("kind", "project")
    if kind != "template":
        want_name = str(built_on.get("name") or "").lower()
        want_version = built_on.get("version") or ""
        for root in _roots(conn):
            if root["top"]:
                continue
            diff = spec_diff(metamodel_spec(conn, str(root["id"])), spec)
            named = bool(want_name) and root["name"].lower() == want_name and (root["version_label"] or "") == want_version
            places.append({"code": "root", "root_id": root["id"], "root": f"{root['name']} {root['version_label'] or ''}".strip(),
                           "named": named, "matches": not diff, "differences": diff[:200], "difference_count": len(diff),
                           "library_state": root["library_state"]})
        places.sort(key=lambda p: (not p["named"], not p["matches"], p["difference_count"], p["root"].lower()))
        if want_name and not any(p["named"] for p in places):
            missing = (f"This installation has no root metamodel called {built_on.get('name')}"
                       f"{' version ' + want_version if want_version else ''}.")
    places.append({"code": "own_root", "root_id": None, "root": "Root", "named": False, "matches": True, "differences": [],
                   "difference_count": 0})
    counts = {"entity_types": len(spec.get("entity_types") or []),
              "entities": sum(len(v) for v in pkg["entities"].values()), "relationships": len(pkg["relationships"])}
    return {"manifest": man, "format": pkg["format"], "counts": counts, "findings": findings, "missing": missing,
            "errors": sum(1 for f in findings if f["level"] == "error"), "placements": places}


def import_package(conn, pkg: dict, placement: str, actor: str, name: str | None = None, as_kind: str | None = None,
                   root: str | None = None) -> dict:
    """Loads a package (D108): placement root (under the root metamodel `root`, which its metamodel must
    match completely; without `root`, the matching one named in the package) or own_root (its
    metamodel becomes a root of its own under Root, with the model under that root). as_kind: library
    (a reference model, published) or project (a working model); a package of a root makes a root."""
    _actor(conn, actor)
    man, spec = pkg["manifest"], pkg["spec"]
    errors = [f for f in validate_spec(conn, spec) if f["level"] == "error"]
    if errors:
        raise EditError("The package's metamodel has errors: " + "; ".join(f"{e['where']}: {e['message']}" for e in errors[:5]))
    info = analyse_package(conn, pkg)
    mm = man.get("model", {})
    kind = mm.get("kind", "project")
    target_name = (name or mm.get("name") or "Imported model").strip()
    _label(conn, f"Uploaded package {mm.get('name')}")
    if kind == "template":
        row = _create_row(conn, name=target_name, kind="template",
                          source_id=_one(conn, "SELECT id FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL "
                                               "AND NOT is_deleted ORDER BY id LIMIT 1")["id"],
                          description=mm.get("description", ""), metamodel_name=mm.get("framework") or target_name,
                          owner=mm.get("owner", ""), version_label=mm.get("version", ""))
        counts = apply_spec(conn, row["id"], spec, "new")
        return {"model": repo.get_model(conn, str(row["guid"])), "root": None, "counts": counts}
    root_model = None
    if placement == "root":
        roots = [p for p in info["placements"] if p["code"] == "root"]
        place = next((p for p in roots if str(p["root_id"]) == str(root)), None) if root else \
            next((p for p in roots if p["named"] and p["matches"]), None) or next((p for p in roots if p["named"]), None)
        if not place:
            raise EditError(("That root metamodel was not found." if root else info.get("missing")
                             or "The package does not say which root metamodel it is built on; choose one."), 409)
        if not place["matches"]:
            raise EditError(f"The package's metamodel does not match {place['root']}: {place['difference_count']} differences. "
                            "Place it under Root as a root of its own instead.", 409)
        root_model = repo.get_model(conn, str(place["root_id"]))
    elif placement == "own_root":
        root_row = _create_row(conn, name=f"{target_name} metamodel", kind="template",
                               source_id=_one(conn, "SELECT id FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL "
                                                    "AND NOT is_deleted ORDER BY id LIMIT 1")["id"],
                               description=f"The metamodel of the uploaded package {mm.get('name')}",
                               metamodel_name=mm.get("framework") or target_name, version_label=mm.get("version", ""))
        apply_spec(conn, root_row["id"], spec, "new")
        root_model = repo.get_model(conn, str(root_row["guid"]))
    else:
        raise EditError("Placement is root or own_root.")
    want = as_kind or ("library" if kind == "reference" else "project")
    row = _create_row(conn, name=target_name, kind="reference" if want == "library" else "project", source_id=root_model["_id"],
                      description=mm.get("description", ""), metamodel_name=root_model["metamodel_name"], owner=mm.get("owner", ""),
                      industry=mm.get("industry", ""), version_label=(mm.get("version") or "1.0") if want == "library" else "")
    copy_into(conn, root_model["_id"], row["id"], False)
    counts = load_content(conn, row["id"], pkg["entities"], pkg["relationships"], spec)
    if want == "library":
        publish(conn, str(row["guid"]), actor)
    return {"model": repo.get_model(conn, str(row["guid"])), "root": root_model, "counts": counts}


def load_content(conn, model_id: int, entities: dict[str, list[dict]], relationships: list[dict], spec: dict) -> dict:
    """Loads a package's entities, values and relationships into a model whose metamodel has the same
    codes. Keys become origin guids; display IDs are kept (the counters follow)."""
    conn.execute(text("SELECT set_config('eax.copy_into', :m, true)"), {"m": str(model_id)})
    types = {r["code"].lower(): r for r in _rows(conn, "SELECT id, code FROM core.entity_types WHERE model_id = :m AND NOT is_deleted",
                                                   m=model_id)}
    attrs = {r["code"].lower(): r for r in _rows(conn, """SELECT a.id, a.code, a.data_type_code AS dt, d.storage
                                                             FROM core.attribute_types a JOIN core.data_types d ON d.code = a.data_type_code
                                                            WHERE a.model_id = :m AND NOT a.is_deleted""", m=model_id)}
    rtypes = {r["code"].lower(): r for r in _rows(conn, "SELECT id, code FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted",
                                                    m=model_id)}
    n = {"entities": 0, "values": 0, "relationships": 0, "skipped": 0}
    rows, values, parents = [], [], []
    for code, ents in entities.items():
        t = types.get(code.lower())
        if not t:
            n["skipped"] += len(ents)
            continue
        for e in ents:
            key = _guid_for(e.get("key") or f"{code}:{e.get('display_id')}:{e.get('name')}")
            rows.append({"t": t["id"], "k": key, "d": (e.get("display_id") or "").strip(), "n": (e.get("name") or "").strip() or "(no name)",
                         "x": e.get("description") or "", "s": (e.get("status") or "published").strip() or "published"})
            if e.get("parent"):
                parents.append({"k": key, "p": _guid_for(e["parent"])})
            for col, v in e.items():
                if col in ENTITY_COLS or v in (None, ""):
                    continue
                if col.lower() in attrs:
                    values.append({"owner": "e", "k": key, "a": col.lower(), "v": str(v)})
    statuses = {r["code"] for r in _rows(conn, "SELECT code FROM core.item_statuses")}
    for r in rows:
        if r["s"] not in statuses:
            r["s"] = "published"
    if rows:
        n["entities"] = _exec(conn, """
            INSERT INTO core.entities (model_id, entity_type_id, display_id, name, description, origin_guid, status_code)
            SELECT :m, x.t, coalesce(x.d, ''), x.n, x.x, x.k::uuid, x.s
              FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(t bigint, k text, d text, n text, x text, s text)""",
                              m=model_id, rows=json.dumps(rows)).rowcount
    if parents:
        _exec(conn, """UPDATE core.entities c SET parent_entity_id = p.id
                         FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(k text, p text)
                         JOIN core.entities p ON p.model_id = :m AND p.origin_guid = x.p::uuid
                        WHERE c.model_id = :m AND c.origin_guid = x.k::uuid""", m=model_id, rows=json.dumps(parents))
    # counters follow the display IDs that came in
    _exec(conn, """INSERT INTO core.display_id_counters (model_id, entity_type_id, last_number)
                   SELECT :m, e.entity_type_id, max(coalesce(nullif(substring(e.display_id FROM '([0-9]+)$'), '')::int, 0))
                     FROM core.entities e WHERE e.model_id = :m GROUP BY e.entity_type_id
                   ON CONFLICT (model_id, entity_type_id) DO UPDATE SET last_number = greatest(core.display_id_counters.last_number,
                                                                                                EXCLUDED.last_number)""", m=model_id)
    rel_rows = []
    for r in relationships:
        rt = rtypes.get(str(r.get("type") or "").lower())
        if not rt or not r.get("source") or not r.get("target"):
            n["skipped"] += 1
            continue
        key = _guid_for(r.get("key") or f"{r.get('type')}:{r.get('source')}:{r.get('target')}")
        rel_rows.append({"t": rt["id"], "k": key, "s": _guid_for(r["source"]), "g": _guid_for(r["target"]),
                         "n": r.get("name") or "", "x": r.get("description") or ""})
        for col, v in r.items():
            if col not in REL_COLS and v not in (None, "") and col.lower() in attrs:
                values.append({"owner": "r", "k": key, "a": col.lower(), "v": str(v)})
    if rel_rows:
        n["relationships"] = _exec(conn, """
            INSERT INTO core.relationships (model_id, relationship_type_id, source_entity_id, target_entity_id, name, description, origin_guid)
            SELECT :m, x.t, s.id, g.id, x.n, x.x, x.k::uuid
              FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(t bigint, k text, s text, g text, n text, x text)
              JOIN core.entities s ON s.model_id = :m AND s.origin_guid = x.s::uuid
              JOIN core.entities g ON g.model_id = :m AND g.origin_guid = x.g::uuid""", m=model_id, rows=json.dumps(rel_rows)).rowcount
        n["skipped"] += len(rel_rows) - n["relationships"]
    if values:
        typed = []
        for v in values:
            a = attrs[v["a"]]
            row = {"owner": v["owner"], "k": v["k"], "a": a["id"], "t": None, "num": None, "d": None, "b": None, "ref": None}
            raw = v["v"].strip()
            try:
                if a["storage"] == "number":
                    row["num"] = str(Decimal(raw))
                elif a["storage"] == "date":
                    row["d"] = dt.date.fromisoformat(raw[:10]).isoformat()
                elif a["storage"] == "boolean":
                    row["b"] = raw.lower() in ("true", "yes", "1")
                elif a["storage"] == "ref":
                    row["ref"] = _guid_for(raw)
                else:
                    row["t"] = raw
            except Exception:  # a value that does not fit its type is left out, and counted
                n["skipped"] += 1
                continue
            typed.append(row)
        n["values"] = _exec(conn, """
            INSERT INTO core.attribute_values (model_id, attribute_type_id, entity_id, relationship_id, value_text, value_number,
                                               value_date, value_bool, value_ref)
            SELECT :m, x.a, e.id, r.id, x.t, x.num::numeric, x.d::date, x.b, ref.id
              FROM jsonb_to_recordset(CAST(:rows AS jsonb))
                   AS x(owner text, k text, a bigint, t text, num text, d text, b boolean, ref text)
              LEFT JOIN core.entities e ON x.owner = 'e' AND e.model_id = :m AND e.origin_guid = x.k::uuid
              LEFT JOIN core.relationships r ON x.owner = 'r' AND r.model_id = :m AND r.origin_guid = x.k::uuid
              LEFT JOIN core.entities ref ON x.ref IS NOT NULL AND ref.model_id = :m AND ref.origin_guid = x.ref::uuid
             WHERE (e.id IS NOT NULL OR r.id IS NOT NULL) AND (x.ref IS NULL OR ref.id IS NOT NULL)""",
                            m=model_id, rows=json.dumps(typed)).rowcount
        n["skipped"] += len(typed) - n["values"]
    conn.execute(text("SELECT set_config('eax.copy_into', '', true)"))
    return n


# ================================================================ moving to a new framework version (D121)

def framework_preview(conn, model: Any, target: Any, type_map: dict | None = None) -> dict:
    """What moving a model onto another root metamodel would do: each entity type of the model with the
    type it maps to (same code, else same name, else as given; None leaves its entities out), the
    relationship types likewise, and what would be left out."""
    m = repo.get_model(conn, model)
    t = repo.get_model(conn, target)
    if t["kind"] != "template":
        raise EditError("Move to a root metamodel (a framework version such as ArchiMate 5).")
    a, b = metamodel_spec(conn, model), metamodel_spec(conn, target)
    bt = {x["code"].lower(): x for x in b["entity_types"]}
    bt_names = {x["name"].lower(): x for x in b["entity_types"]}
    counts = {r["code"]: r["n"] for r in _rows(conn, """SELECT t.code, count(e.id) AS n FROM core.entity_types t
        LEFT JOIN core.entities e ON e.entity_type_id = t.id AND NOT e.is_deleted WHERE t.model_id = :m GROUP BY t.code""", m=m["_id"])}
    type_map = {k.lower(): v for k, v in (type_map or {}).items()}
    types = []
    for x in a["entity_types"]:
        k = x["code"].lower()
        if k in type_map:
            to = type_map[k]
            how = "chosen"
        elif k in bt:
            to, how = bt[k]["code"], "same code"
        elif x["name"].lower() in bt_names:
            to, how = bt_names[x["name"].lower()]["code"], "same name"
        else:
            to, how = None, "no match"
        types.append({"code": x["code"], "name": x["name"], "entities": counts.get(x["code"], 0), "to": to,
                      "to_name": bt[to.lower()]["name"] if to and to.lower() in bt else None, "how": how})
    br = {x["code"].lower(): x for x in b["relationship_types"]}
    br_names = {x["name"].lower(): x for x in b["relationship_types"]}
    rels = []
    for x in a["relationship_types"]:
        to = br.get(x["code"].lower()) or br_names.get(x["name"].lower())
        rels.append({"code": x["code"], "name": x["name"], "to": to["code"] if to else None})
    attrs_b = {x["code"].lower() for x in b["attributes"]}
    lost_attrs = [x["code"] for x in a["attributes"] if x["code"].lower() not in attrs_b]
    left_out = sum(t_["entities"] for t_ in types if not t_["to"])
    return {"model": m["name"], "target": f"{t['name']} {t['version_label']}".strip(), "types": types, "relationship_types": rels,
            "attributes_left_out": lost_attrs, "entities_left_out": left_out,
            "target_types": [{"code": x["code"], "name": x["name"]} for x in b["entity_types"]]}


def framework_move(conn, model: Any, target: Any, mode: str, actor: str, type_map: dict | None = None,
                   name: str | None = None) -> dict:
    """Moves a model onto another root metamodel (D121). mode copy: a new model under the target root
    with the content mapped across (the old model stays as it is). mode in_place: the model takes the
    target's metamodel as one metamodel version: the target's items are added, entities move to their
    mapped types, types with no mapping are retired, values whose attribute the new type lacks are
    removed (kept in history)."""
    _actor(conn, actor)
    prev = framework_preview(conn, model, target, type_map)
    m, t = repo.get_model(conn, model), repo.get_model(conn, target)
    tmap = {x["code"].lower(): x["to"] for x in prev["types"]}
    rmap = {x["code"].lower(): x["to"] for x in prev["relationship_types"]}
    if mode == "copy":
        row = _create_row(conn, name=name or f"{m['name']} ({t['name']} {t['version_label']})".replace(" )", ")"), kind="project",
                          source_id=t["_id"], description=m["description"], metamodel_name=t["metamodel_name"], owner=m["owner"],
                          industry=m["industry"])
        copy_into(conn, t["_id"], row["id"], False)
        content = package_content(conn, model)
        ents = {}
        for code, rows in content["entities"].items():
            to = tmap.get(code.lower())
            if to:
                ents.setdefault(to, []).extend(rows)
        rels = [dict(r, type=rmap.get(r["type"].lower()) or "") for r in content["relationships"]]
        _label(conn, f"Moved from {m['name']} to {t['name']}")
        counts = load_content(conn, row["id"], ents, [r for r in rels if r["type"]], metamodel_spec(conn, target))
        # relationships the target does not allow are left out: load_content copies faithfully, so drop them here
        dropped = _exec(conn, """UPDATE core.relationships r SET is_deleted = true
             FROM core.entities s, core.entities g
            WHERE r.model_id = :m AND s.id = r.source_entity_id AND g.id = r.target_entity_id AND NOT r.is_deleted
              AND NOT EXISTS (SELECT 1 FROM core.allowed_relationships a WHERE a.relationship_type_id = r.relationship_type_id
                                 AND a.source_type_id = s.entity_type_id AND a.target_type_id = g.entity_type_id AND NOT a.is_deleted)""",
                        m=row["id"]).rowcount
        counts["relationships_not_allowed"] = dropped
        return {"model": repo.get_model(conn, str(row["guid"])), "mode": "copy", "counts": counts, "preview": prev}
    if mode != "in_place":
        raise EditError("Mode is copy or in_place.")
    if m["kind"] != "project" or m["is_locked"]:
        raise EditError("Only a working (project) model is moved in place.", 409)
    try:
        version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                               {"m": m["_id"], "n": f"Moved to {t['name']} {t['version_label']}".strip()}).scalar_one()
        # a sanctioned restructure: values are removed after their entity changes type
        conn.execute(text("SELECT set_config('eax.copy_into', :m, true)"), {"m": str(m["_id"])})
        tspec = metamodel_spec(conn, target)
        counts = apply_spec(conn, m["_id"], tspec, "merge")
        types = {r["code"].lower(): r["id"] for r in _rows(conn, "SELECT id, code FROM core.entity_types WHERE model_id = :m AND NOT is_deleted",
                                                             m=m["_id"])}
        moved = 0
        for frm, to in tmap.items():
            if to and frm != to.lower() and frm in types and to.lower() in types:
                _exec(conn, "UPDATE core.entity_types SET status_code = 'published' WHERE id = :t", t=types[to.lower()])
                moved += _exec(conn, """UPDATE core.entities SET entity_type_id = :to WHERE model_id = :m AND entity_type_id = :fr
                                        AND NOT is_deleted""", m=m["_id"], fr=types[frm], to=types[to.lower()]).rowcount
        rtypes = {r["code"].lower(): r["id"] for r in _rows(conn, "SELECT id, code FROM core.relationship_types WHERE model_id = :m",
                                                              m=m["_id"])}
        for frm, to in rmap.items():
            if to and frm != to.lower() and frm in rtypes and to.lower() in rtypes:
                _exec(conn, "UPDATE core.relationship_types SET status_code = 'published' WHERE id = :t", t=rtypes[to.lower()])
                _exec(conn, """UPDATE core.relationships SET relationship_type_id = :to WHERE model_id = :m AND relationship_type_id = :fr
                               AND NOT is_deleted""", m=m["_id"], fr=rtypes[frm], to=rtypes[to.lower()])
        keep = {to.lower() for to in tmap.values() if to} | {x["code"].lower() for x in tspec["entity_types"]}
        retired = _exec(conn, """UPDATE core.entity_types SET status_code = 'retired' WHERE model_id = :m AND NOT is_deleted
                                  AND status_code <> 'retired' AND NOT (lower(code) = ANY (:k))""", m=m["_id"], k=list(keep)).rowcount
        removed_values = _exec(conn, """UPDATE core.attribute_values v SET is_deleted = true FROM core.entities e
             WHERE v.model_id = :m AND e.id = v.entity_id AND NOT v.is_deleted
               AND NOT EXISTS (SELECT 1 FROM core.item_attributes i WHERE i.entity_type_id = e.entity_type_id
                                 AND i.attribute_type_id = v.attribute_type_id AND NOT i.is_deleted)""", m=m["_id"]).rowcount
        _exec(conn, "UPDATE core.models SET source_model_id = :t, metamodel_name = :n WHERE id = :m",
              t=t["_id"], n=t["metamodel_name"], m=m["_id"])
        conn.execute(text("SELECT set_config('eax.copy_into', '', true)"))
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    counts.update({"entities_moved": moved, "types_retired": retired, "values_removed": removed_values, "version": version})
    return {"model": repo.get_model(conn, model), "mode": "in_place", "counts": counts, "preview": prev}


# ================================================================ metamodel drafts (D115, D120)

def _draft(conn, draft: Any) -> dict:
    g = repo._as_guid(draft)
    d = _one(conn, """SELECT d.*, b.guid AS base_guid, b.name AS base_name, t.guid AS target_guid, t.name AS target_name,
                             a.guid AS applied_guid, a.name AS applied_name
                        FROM core.metamodel_drafts d
                        LEFT JOIN core.models b ON b.id = d.base_model_id
                        LEFT JOIN core.models t ON t.id = d.target_model_id
                        LEFT JOIN core.models a ON a.id = d.applied_model_id
                       WHERE d.guid = CAST(:g AS uuid)""", g=str(g)) if g else None
    if not d:
        raise EditError(f"No metamodel draft {draft!r}.", 404)
    return d


def draft_out(d: dict, conn=None) -> dict:
    spec = d["spec"] or {}
    out = {"id": d["guid"], "name": d["name"], "kind": d["kind"], "status": d["status"], "note": d["note"],
           "proposed_by": d["proposed_by"], "proposed_via": d["proposed_via"], "created_at": d["created_at"],
           "modified_at": d["modified_at"], "decided_at": d["decided_at"], "decided_by": d["decided_by"],
           "base_model_id": d.get("base_guid"), "base_model": d.get("base_name"),
           "target_model_id": d.get("target_guid"), "target_model": d.get("target_name"),
           "applied_model_id": d.get("applied_guid"), "applied_model": d.get("applied_name"),
           "spec": spec, "checks": d["checks"] or [],
           "counts": {k: len(spec.get(k) or []) for k in ("layers", "pick_lists", "attributes", "entity_types",
                                                           "relationship_types", "allowed", "rules")}}
    return out


def _may_draft(user, kind: str, conn, target: dict | None) -> None:
    from . import permissions as perms
    if user is None or perms.SUPER_ADMIN in user.roles:
        return
    if kind == "root" and perms.MODEL_CREATOR not in user.roles and perms.LIBRARY_ADMIN not in user.roles:
        raise EditError("Drafting a new root metamodel needs the Model Creator role (D120).", 403)
    if kind == "changes" and perms.MODEL_ADMIN not in perms.model_roles(conn, user.username, target["id"]):
        raise EditError(f"Drafting changes to {target['name']} needs its Model Admin role (D120).", 403)


def draft_create(conn, user, p: dict, via: str = "mcp") -> dict:
    """A new metamodel draft: kind root (a new root metamodel, starting empty or from a copy of `base`,
    a root) or changes (to `target`, a model the person is Model Admin of; starts as its metamodel)."""
    kind = p.get("kind") or "root"
    if kind not in ("root", "changes"):
        raise EditError("Kind is root (a new root metamodel) or changes (to a model's metamodel).")
    base = target = None
    if kind == "changes":
        if not p.get("target"):
            raise EditError("Give the model the changes are for (target).")
        target = repo.get_model(conn, p["target"])
        if target["kind"] not in ("project", "template") or target["is_locked"]:
            raise EditError(f"{target['name']} is read-only: draft changes to a working model or your own root.", 409)
        spec = metamodel_spec(conn, str(target["id"]))
    else:
        if p.get("base"):
            base = repo.get_model(conn, p["base"])
            if base["kind"] != "template":
                raise EditError("A new root starts empty or from another root metamodel (base).")
            spec = metamodel_spec(conn, str(base["id"])) if base["source_model_id"] else empty_spec()
        else:
            spec = empty_spec()
        spec.update({"name": p.get("name") or "", "framework": p.get("framework") or p.get("name") or "",
                     "version": p.get("version") or ""})
    if isinstance(p.get("spec"), dict):
        spec = p["spec"]
    _may_draft(user, kind, conn, target)
    name = (p.get("name") or (f"Changes to {target['name']}" if target else "")).strip()
    if not name:
        raise EditError("Give the draft a name (for a root: the metamodel's name).")
    checks = validate_spec(conn, spec)
    d = _one(conn, """INSERT INTO core.metamodel_drafts (name, kind, base_model_id, target_model_id, spec, checks, note, proposed_via)
                      VALUES (:n, :k, :b, :t, CAST(:s AS jsonb), CAST(:c AS jsonb), :note, :via) RETURNING guid""",
             n=name, k=kind, b=base["_id"] if base else None, t=target["_id"] if target else None,
             s=json.dumps(spec, default=str), c=json.dumps(checks), note=p.get("note") or "", via=via)
    return draft_out(_draft(conn, d["guid"]))


def draft_list(conn, user, status: str | None = None) -> list[dict]:
    from . import permissions as perms
    rows = _rows(conn, """SELECT d.*, b.guid AS base_guid, b.name AS base_name, t.guid AS target_guid, t.name AS target_name,
                                 a.guid AS applied_guid, a.name AS applied_name
                            FROM core.metamodel_drafts d
                            LEFT JOIN core.models b ON b.id = d.base_model_id
                            LEFT JOIN core.models t ON t.id = d.target_model_id
                            LEFT JOIN core.models a ON a.id = d.applied_model_id
                           WHERE (CAST(:s AS text) IS NULL OR d.status = :s)
                           ORDER BY d.modified_at DESC""", s=status)
    out = []
    for d in rows:
        mine = user is None or perms.SUPER_ADMIN in user.roles or d["proposed_by"] == user.username
        if not mine and d["target_guid"]:
            mine = perms.MODEL_ADMIN in perms.model_roles(conn, user.username, d["target_guid"])
        if mine:
            x = draft_out(d)
            x.pop("spec")
            out.append(x)
    return out


def draft_get(conn, user, draft: Any) -> dict:
    d = _draft(conn, draft)
    _may_see(conn, user, d)
    out = draft_out(d)
    if d["kind"] == "changes" and d["target_guid"]:
        out["differences"] = spec_diff(metamodel_spec(conn, str(d["target_guid"])), d["spec"])
    elif d["base_guid"]:
        base = metamodel_spec(conn, str(d["base_guid"]))
        out["differences"] = spec_diff(base, d["spec"]) if base["entity_types"] else []
    else:
        out["differences"] = []
    return out


def _may_see(conn, user, d: dict) -> None:
    from . import permissions as perms
    if user is None or perms.SUPER_ADMIN in user.roles or d["proposed_by"] == user.username:
        return
    if d["target_guid"] and perms.MODEL_ADMIN in perms.model_roles(conn, user.username, d["target_guid"]):
        return
    raise EditError("This draft is someone else's.", 404)


SECTIONS = ("layers", "pick_lists", "attributes", "entity_types", "relationship_types", "allowed", "rules")


def _remove_references(s: dict, section: str, gone: str) -> None:
    """When an item leaves a draft, what only made sense with it leaves too: an entity type's allowed
    relationships and rules; a relationship type's allowed relationships; an attribute's places on types
    and its rules. Pick lists and layers still in use stay, and the checks say where."""
    low = lambda v: str(v or "").lower()  # noqa: E731
    if section == "entity_types":
        s["allowed"] = [a for a in s.get("allowed") or [] if gone not in (low(a.get("source")), low(a.get("target")))]
        s["rules"] = [r for r in s.get("rules") or [] if low(r.get("entity_type")) != gone]
    elif section == "relationship_types":
        s["allowed"] = [a for a in s.get("allowed") or [] if low(a.get("relationship")) != gone]
    elif section == "attributes":
        for t in (s.get("entity_types") or []) + (s.get("relationship_types") or []):
            t["attributes"] = [a for a in t.get("attributes") or [] if low(a.get("attribute") if isinstance(a, dict) else a) != gone]
        s["rules"] = [r for r in s.get("rules") or [] if low(r.get("attribute")) != gone]


def draft_edit(conn, user, draft: Any, action: str, section: str | None = None, item: dict | None = None,
               code: str | None = None, spec: dict | None = None) -> dict:
    """Changes a draft, one step at a time or all at once (D120), and checks it again:
      set     section, item     add the item to the section, or replace the one with the same code
                                (allowed: same source, relationship and target; rules: same rule)
      remove  section, code     take the item out (allowed and rules: by position, code = its index)
      replace spec              the whole metamodel document at once
    Returns the draft with its checks."""
    d = _draft(conn, draft)
    _may_see(conn, user, d)
    if d["status"] != "draft":
        raise EditError(f"This draft was {d['status']}; start a new one.", 409)
    s = d["spec"] or empty_spec()
    if action == "replace":
        if not isinstance(spec, dict):
            raise EditError("Give the whole metamodel document (spec).")
        s = spec
    elif action in ("set", "remove"):
        if section not in SECTIONS:
            raise EditError(f"Section is one of {', '.join(SECTIONS)}.")
        items = list(s.get(section) or [])
        if action == "set":
            if not isinstance(item, dict):
                raise EditError("Give the item to add or replace.")
            if section in ("allowed", "rules"):
                keys = ("source", "relationship", "target") if section == "allowed" else \
                    ("entity_type", "attribute", "field", "rule_type", "param1", "param2")
                same = lambda x: all(str(x.get(k) or "").lower() == str(item.get(k) or "").lower() for k in keys)  # noqa: E731
            else:
                if not item.get("code") and item.get("name"):
                    item["code"] = code_from(item["name"])
                same = lambda x: str(x.get("code", "")).lower() == str(item.get("code", "")).lower()  # noqa: E731
            idx = next((i for i, x in enumerate(items) if same(x)), None)
            if idx is None:
                items.append(item)
            else:
                items[idx] = item
        else:
            if section in ("allowed", "rules"):
                try:
                    items.pop(int(code))
                except (TypeError, ValueError, IndexError) as exc:
                    raise EditError(f"No {section} item at position {code!r}.", 404) from exc
            else:
                before = len(items)
                gone = str(code or "").lower()
                items = [x for x in items if str(x.get("code", "")).lower() != gone]
                if len(items) == before:
                    raise EditError(f"No {section} item with code {code!r}.", 404)
                _remove_references(s, section, gone)
        s[section] = items
    else:
        raise EditError("Action is set, remove or replace.")
    checks = validate_spec(conn, s)
    _exec(conn, """UPDATE core.metamodel_drafts SET spec = CAST(:s AS jsonb), checks = CAST(:c AS jsonb), modified_at = now()
                    WHERE id = :i""", s=json.dumps(s, default=str), c=json.dumps(checks), i=d["id"])
    return draft_out(_draft(conn, d["guid"]))


def draft_apply(conn, user, draft: Any, actor: str, p: dict) -> dict:
    """A person applies a draft after reviewing it (D115): a root draft becomes a new root metamodel
    (under Root, or a copy of its base); a changes draft becomes one new metamodel version of its model
    (remove_missing also retires what the draft leaves out). Optionally a project model is created
    from a new root (create_model: its name)."""
    d = _draft(conn, draft)
    _may_see(conn, user, d)
    if d["status"] != "draft":
        raise EditError(f"This draft was already {d['status']}.", 409)
    spec = d["spec"]
    errors = [c for c in validate_spec(conn, spec) if c["level"] == "error"]
    if errors:
        raise EditError("Fix the draft's errors first: " + "; ".join(f"{e['where']}: {e['message']}" for e in errors[:5]), 409)
    _actor(conn, actor)
    try:
        if d["kind"] == "root":
            _may_draft(user, "root", conn, None)
            top = _one(conn, "SELECT id FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL AND NOT is_deleted "
                             "ORDER BY id LIMIT 1")
            row = _create_row(conn, name=p.get("name") or spec.get("name") or d["name"], kind="template",
                              source_id=d["base_model_id"] or top["id"], description=p.get("description") or d["note"],
                              metamodel_name=spec.get("framework") or spec.get("name") or d["name"],
                              version_label=p.get("version_label") or spec.get("version") or "")
            _label(conn, f"Metamodel draft {d['name']} applied")
            counts = apply_spec(conn, row["id"], spec, "new")
            applied = row["id"]
            out = {"model": repo.get_model(conn, str(row["guid"])), "counts": counts}
            if p.get("create_model"):
                made = create_model(conn, actor, {"kind": "project", "source": str(row["guid"]), "name": p["create_model"],
                                                  "copy": "metamodel"})
                out["created"] = made["model"]
        else:
            target = repo.get_model(conn, str(d["target_guid"]))
            _may_draft(user, "changes", conn, target)
            version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                                   {"m": target["_id"], "n": f"Metamodel draft {d['name']}"}).scalar_one()
            counts = apply_spec(conn, target["_id"], spec, "merge", bool(p.get("remove_missing")))
            counts["version"] = version
            applied = target["_id"]
            out = {"model": repo.get_model(conn, str(target["id"])), "counts": counts}
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 403 if "Not allowed" in str(exc.orig) else 409) from exc
    _exec(conn, """UPDATE core.metamodel_drafts SET status = 'applied', decided_at = now(), decided_by = :a, applied_model_id = :m,
                   modified_at = now() WHERE id = :i""", a=actor, m=applied, i=d["id"])
    out["draft"] = draft_out(_draft(conn, d["guid"]))
    return out


def draft_reject(conn, user, draft: Any, actor: str, reason: str) -> dict:
    d = _draft(conn, draft)
    _may_see(conn, user, d)
    if d["status"] != "draft":
        raise EditError(f"This draft was already {d['status']}.", 409)
    _exec(conn, """UPDATE core.metamodel_drafts SET status = 'rejected', decided_at = now(), decided_by = :a,
                   note = trim(note || E'\\n' || 'Rejected: ' || :r), modified_at = now() WHERE id = :i""",
          a=actor, r=reason or "no reason given", i=d["id"])
    return draft_out(_draft(conn, d["guid"]))
