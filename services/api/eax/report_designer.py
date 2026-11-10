"""The report designer (phase 24, D365, D434).

A person chooses an entity type of a model, its attributes, related types (through a relationship type, either way) with
their attributes, and filters. EA Explorer keeps the design and turns it into one SQL query over the report views
(rpt.t_<type> and rpt.relationships, D139), limited to the model. Opening it hands over to Superset: a small page there
(deploy/superset/eax_designer.py, signed in through Keycloak as the person) makes or refreshes the Superset dataset from
the design and opens Superset's chart builder on it. The designer builds datasets only: charts and dashboards are made in
Superset. Model access applies as on every report dataset (rpt.model_access, D138).

The SQL is made here from names checked against the report views' own columns, and values written as quoted literals:
nothing a person types reaches the query as SQL.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from . import repository as repo
from .metamodel_edit import EditError


def _maps(res) -> list[dict]:
    return [dict(r) for r in res.mappings()]

OPS = {"equals": "is", "not-equals": "is not", "contains": "contains", "empty": "is empty", "not-empty": "is not empty",
       "more-than": "is more than", "less-than": "is less than"}
BASE = ["display_id", "name", "description", "parent_name", "status", "modified_at", "modified_by"]
HIDDEN = {"model_id", "model_name", "entity_id", "entity_guid", "entity_type_code", "entity_type", "type_domain_code",
          "type_domain", "parent_id", "origin_guid", "created_at", "created_by", "link"}
MAX_RELATED = 4
MAX_FILTERS = 10


def snake(code: str) -> str:
    """rpt.snake(): the report name of a code (ApplicationComponent -> application_component)."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", code or "")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _q(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ident(name: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise EditError(f"'{name}' is not a report column.")
    return '"' + name + '"'


def view_columns(conn, type_code: str) -> dict[str, str]:
    """The columns of a type's report view and their types (rpt.t_<type>); {} when the view is not there."""
    view = "t_" + snake(type_code)
    return {r["column_name"]: r["data_type"] for r in conn.execute(text("""
        SELECT column_name::text AS column_name, data_type::text AS data_type FROM information_schema.columns
         WHERE table_schema = 'rpt' AND table_name = :v ORDER BY ordinal_position"""), {"v": view}).mappings()}


def choices(conn, model: Any) -> dict:
    """What the designer offers for a model: each entity type with its report columns (attributes named as in the model),
    and the relationship types each type has with others (both ways), from the model's allowed relationships."""
    m = repo.get_model(conn, model)
    types = _maps(conn.execute(text("""
        SELECT t.id, t.code, t.name, l.name AS domain FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
         WHERE t.model_id = :m AND NOT t.is_deleted AND NOT t.is_connector AND t.status_code <> 'retired'
         ORDER BY l.sort_order, t.sort_order, t.name"""), {"m": m["_id"]}))
    attrs: dict[int, list[dict]] = {}
    for r in conn.execute(text("""
            SELECT i.entity_type_id, a.code, a.name, a.data_type_code AS data_type FROM core.item_attributes i
              JOIN core.attribute_types a ON a.id = i.attribute_type_id
             WHERE i.model_id = :m AND NOT i.is_deleted AND NOT a.is_deleted ORDER BY i.sort_order, a.name"""), {"m": m["_id"]}).mappings():
        attrs.setdefault(r["entity_type_id"], []).append({"code": r["code"], "name": r["name"], "data_type": r["data_type"]})
    rels = _maps(conn.execute(text("""
        SELECT DISTINCT rt.code AS relationship_type, rt.name AS relationship_name, coalesce(rt.verb, '') AS verb,
               s.code AS source, t.code AS target
          FROM core.allowed_relationships al JOIN core.relationship_types rt ON rt.id = al.relationship_type_id
          JOIN core.entity_types s ON s.id = al.source_type_id JOIN core.entity_types t ON t.id = al.target_type_id
         WHERE al.model_id = :m AND NOT al.is_deleted AND NOT s.is_connector AND NOT t.is_connector"""), {"m": m["_id"]}))
    names = {t["code"]: t["name"] for t in types}
    out = []
    for t in types:
        cols = view_columns(conn, t["code"])
        fields = [{"column": c, "name": c.replace("_", " ").capitalize(), "data_type": cols[c]} for c in BASE if c in cols]
        for a in attrs.get(t["id"], []):
            col = snake(a["code"])
            col = col if col in cols and col not in HIDDEN | set(BASE) else ("a_" + col if "a_" + col in cols else None)
            if col:
                fields.append({"column": col, "name": a["name"], "data_type": cols[col], "attribute": a["code"]})
        related = []
        for r in rels:
            if r["source"] == t["code"] and r["target"] in names:
                related.append({"relationship_type": r["relationship_type"], "direction": "outgoing", "other_type": r["target"],
                                "label": f"{r['verb'] or r['relationship_name']} {names[r['target']]}"})
            if r["target"] == t["code"] and r["source"] in names:
                related.append({"relationship_type": r["relationship_type"], "direction": "incoming", "other_type": r["source"],
                                "label": f"{names[r['source']]} {r['verb'] or r['relationship_name']} it"})
        out.append({"code": t["code"], "name": t["name"], "domain": t["domain"], "has_view": bool(cols), "fields": fields,
                    "related": sorted(related, key=lambda x: x["label"].lower())})
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "types": out, "ops": OPS}


def _literal(value: Any, data_type: str) -> str:
    if data_type in ("numeric", "bigint", "integer"):
        try:
            return str(Decimal(str(value).replace(",", "").strip()))
        except InvalidOperation as exc:
            raise EditError(f"'{value}' is not a number.") from exc
    if data_type == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value).strip()):
            raise EditError(f"'{value}' is not a date (YYYY-MM-DD).")
        return f"DATE {_q(str(value).strip())}"
    return _q(str(value))


def _condition(col: str, data_type: str, op: str, value: Any) -> str:
    if op == "empty":
        return f"({col} IS NULL OR {col}::text = '')"
    if op == "not-empty":
        return f"({col} IS NOT NULL AND {col}::text <> '')"
    if op in ("equals", "not-equals"):
        if data_type in ("text", "character varying", "boolean"):
            cmp = f"lower({col}::text) = lower({_q(value)})"
        else:
            cmp = f"{col} = {_literal(value, data_type)}"
        return cmp if op == "equals" else f"({col} IS NULL OR NOT ({cmp}))"
    if op == "contains":
        like = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{col}::text ILIKE {_q('%' + like + '%')}"
    if op in ("more-than", "less-than"):
        if data_type not in ("numeric", "bigint", "integer", "date"):
            raise EditError("More than and less than compare numbers and dates.")
        return f"{col} {'>' if op == 'more-than' else '<'} {_literal(value, data_type)}"
    raise EditError("Choose how the filter compares.")


def build_sql(conn, model_id: int, spec: dict) -> tuple[str, dict]:
    """The design's SQL over the report views, and the spec as checked (unknown names refused)."""
    tcode = (spec.get("entity_type") or "").strip()
    known = {r["code"]: r["name"] for r in conn.execute(text("""SELECT code, name FROM core.entity_types WHERE model_id = :m
                                                               AND NOT is_deleted AND NOT is_connector"""), {"m": model_id}).mappings()}
    if tcode not in known:
        raise EditError("Choose the entity type the report is about.")
    cols = view_columns(conn, tcode)
    if not cols:
        raise EditError(f"{known[tcode]} has no report view yet: its report views are made after the next metamodel change.")
    chosen = [c for c in spec.get("columns") or [] if c in cols and c not in HIDDEN]
    if not chosen:
        chosen = [c for c in ("display_id", "name") if c in cols]
    select = ['t."model_id"', 't."model_name"', 't."entity_guid"']
    select += [f't.{_ident(c)}' for c in chosen]
    select.append("t.\"link\"")
    names = ["model_id", "model_name", "entity_guid", *chosen, "link"]
    joins: list[str] = []
    clean_related = []
    aliases = set(chosen) | {"model_id", "model_name", "entity_guid", "link"}
    for i, rel in enumerate((spec.get("related") or [])[:MAX_RELATED], start=1):
        rtype, direction, other = rel.get("relationship_type") or "", rel.get("direction") or "outgoing", rel.get("other_type") or ""
        ok = conn.execute(text("""
            SELECT 1 FROM core.allowed_relationships al JOIN core.relationship_types rt ON rt.id = al.relationship_type_id
              JOIN core.entity_types s ON s.id = al.source_type_id JOIN core.entity_types t ON t.id = al.target_type_id
             WHERE al.model_id = :m AND NOT al.is_deleted AND rt.code = :r
               AND ((:d = 'outgoing' AND s.code = :a AND t.code = :b) OR (:d = 'incoming' AND s.code = :b AND t.code = :a))
             LIMIT 1"""), {"m": model_id, "r": rtype, "d": direction, "a": tcode, "b": other}).first()
        if not ok or other not in known or direction not in ("outgoing", "incoming"):
            raise EditError(f"{known.get(other, other)} is not related to {known[tcode]} by {rtype} in this model.")
        ocols = view_columns(conn, other)
        if not ocols:
            raise EditError(f"{known[other]} has no report view yet.")
        ochosen = [c for c in rel.get("columns") or ["name"] if c in ocols and c not in HIDDEN] or ["name"]
        here, there = ("source_id", "target_id") if direction == "outgoing" else ("target_id", "source_id")
        joins.append(f"LEFT JOIN rpt.relationships r{i} ON r{i}.model_id = t.model_id AND r{i}.{here} = t.entity_id "
                     f"AND r{i}.relationship_type_code = {_q(rtype)} AND r{i}.{'target' if direction == 'outgoing' else 'source'}"
                     f"_type_code = {_q(other)}")
        joins.append(f"LEFT JOIN rpt.{_ident('t_' + snake(other))} o{i} ON o{i}.entity_id = r{i}.{there}")
        prefix = snake(other)
        for c in ochosen:
            alias = f"{prefix}_{c}"
            while alias in aliases:
                alias = f"{alias}_{i}"
            aliases.add(alias)
            select.append(f"o{i}.{_ident(c)} AS {_ident(alias)}")
            names.append(alias)
        clean_related.append({"relationship_type": rtype, "direction": direction, "other_type": other, "columns": ochosen})
    where = [f"t.model_id = {int(model_id)}"]
    clean_filters = []
    for f in (spec.get("filters") or [])[:MAX_FILTERS]:
        field, op, value = f.get("field") or "", f.get("op") or "", f.get("value", "")
        if op not in OPS:
            raise EditError("Choose how each filter compares.")
        m = re.fullmatch(r"related:(\d+):([a-z0-9_]+)", field)
        if m:
            k = int(m.group(1))
            if not 1 <= k <= len(clean_related):
                raise EditError("A filter is on a related type the design no longer has.")
            ocols = view_columns(conn, clean_related[k - 1]["other_type"])
            if m.group(2) not in ocols or m.group(2) in HIDDEN - {"entity_type"}:
                raise EditError(f"'{m.group(2)}' is not a column of {clean_related[k - 1]['other_type']}.")
            col, dtype = f"o{k}.{_ident(m.group(2))}", ocols[m.group(2)]
        else:
            if field not in cols or field in HIDDEN:
                raise EditError(f"'{field}' is not a column of {known[tcode]}.")
            col, dtype = f"t.{_ident(field)}", cols[field]
        if op not in ("empty", "not-empty") and str(value).strip() == "":
            raise EditError("Give the value each filter compares with.")
        where.append(_condition(col, dtype, op, value))
        clean_filters.append({"field": field, "op": op, "value": "" if op in ("empty", "not-empty") else str(value)})
    sql = (f"SELECT {', '.join(select)}\n  FROM rpt.{_ident('t_' + snake(tcode))} t\n"
           + "".join(f"  {j}\n" for j in joins) + f" WHERE {' AND '.join(where)}")
    return sql, {"entity_type": tcode, "columns": chosen, "related": clean_related, "filters": clean_filters, "_names": names}


def _out(r: dict) -> dict:
    from .reports import reports_base_url
    spec = r["spec"] if isinstance(r["spec"], dict) else json.loads(r["spec"])
    return {"id": r["guid"], "name": r["name"], "spec": spec, "sql": r["sql"], "created_by": r["created_by"],
            "created_at": r["created_at"], "modified_at": r["modified_at"],
            "open_url": f"{reports_base_url()}/login/keycloak?next=/eax/designs/{r['guid']}/open"}


def list_designs(conn, model: Any) -> dict:
    m = repo.get_model(conn, model)
    rows = conn.execute(text("""SELECT guid::text AS guid, name, spec, sql, created_by, created_at, modified_at
                                  FROM core.report_designs WHERE model_id = :m AND NOT is_deleted ORDER BY lower(name)"""),
                        {"m": m["_id"]}).mappings().all()
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "designs": [_out(dict(r)) for r in rows]}


def save_design(conn, model_id: int, name: str, spec: dict, actor: str, design: str | None = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise EditError("Give the report a name, for example Applications and the capabilities they serve.")
    if len(name) > 120:
        raise EditError("Keep the name under 120 characters.")
    sql, clean = build_sql(conn, model_id, spec)
    clean.pop("_names", None)
    if design:
        row = conn.execute(text("""UPDATE core.report_designs SET name = :n, spec = CAST(:s AS jsonb), sql = :q, modified_at = now(),
                                          modified_by = :u
                                    WHERE model_id = :m AND guid = CAST(:g AS uuid) AND NOT is_deleted
                                RETURNING guid::text AS guid, name, spec, sql, created_by, created_at, modified_at"""),
                           {"n": name, "s": json.dumps(clean), "q": sql, "u": actor.lower(), "m": model_id, "g": design}).mappings().first()
        if not row:
            raise EditError("No such report design on this model.", 404)
    else:
        row = conn.execute(text("""INSERT INTO core.report_designs (model_id, name, spec, sql, created_by, modified_by)
                                   VALUES (:m, :n, CAST(:s AS jsonb), :q, :u, :u)
                                RETURNING guid::text AS guid, name, spec, sql, created_by, created_at, modified_at"""),
                           {"n": name, "s": json.dumps(clean), "q": sql, "u": actor.lower(), "m": model_id}).mappings().first()
    return _out(dict(row))


def _may_change(conn, user, m: dict, design: str) -> None:
    from . import quality as q
    by = conn.execute(text("SELECT created_by FROM core.report_designs WHERE model_id = :m AND guid = CAST(:g AS uuid) AND NOT is_deleted"),
                      {"m": m["_id"], "g": design}).scalar()
    if by is None:
        raise EditError("No such report design on this model.", 404)
    if by != user.username.lower() and not q.is_model_admin(conn, user, m):
        raise EditError("Only the person who made a report design, or a Model Admin, changes it.", 403)


def create(conn, model: Any, user, body: dict) -> dict:
    m = repo.get_model(conn, model)
    return save_design(conn, m["_id"], body.get("name") or "", body.get("spec") or {}, user.username)


def update(conn, model: Any, user, design: str, body: dict) -> dict:
    m = repo.get_model(conn, model)
    _may_change(conn, user, m, str(design))
    return save_design(conn, m["_id"], body.get("name") or "", body.get("spec") or {}, user.username, str(design))


def delete(conn, model: Any, user, design: str) -> dict:
    """The design goes; a dataset already made in Superset from it stays there until its charts no longer use it."""
    m = repo.get_model(conn, model)
    _may_change(conn, user, m, str(design))
    conn.execute(text("UPDATE core.report_designs SET is_deleted = true, modified_at = now(), modified_by = :u "
                      "WHERE model_id = :m AND guid = CAST(:g AS uuid)"), {"m": m["_id"], "g": str(design), "u": user.username.lower()})
    return {"deleted": str(design)}


def preview(conn, model: Any, body: dict, limit: int = 20) -> dict:
    """The first rows the design gives now (as the person: they read only what they may), before it goes to Superset."""
    m = repo.get_model(conn, model)
    sql, clean = build_sql(conn, m["_id"], body.get("spec") or {})
    cols = [c for c in clean.pop("_names") if c not in ("model_id", "model_name", "entity_guid", "link")]
    conn.execute(text("SET LOCAL statement_timeout = '15s'"))
    found = [dict(r) for r in conn.execute(text(f"SELECT * FROM ({sql}) d LIMIT {int(limit)}")).mappings()]
    rows = [[(str(r.get(c)) if r.get(c) is not None else None) for c in cols] for r in found]
    count = conn.execute(text(f"SELECT count(*) AS n FROM ({sql}) d")).scalar()
    return {"sql": sql, "spec": clean, "columns": cols, "rows": rows, "count": count}
