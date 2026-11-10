"""Read access to the repository, shared by the REST API and the MCP server.

Every function takes an open SQLAlchemy connection and returns plain Python data. Identifiers
going in and out are guids; the bigint keys stay inside the database. Each build phase adds its
functions here first, so the REST API and the MCP server stay in step.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import links, notation


class NotFound(Exception):
    """A model, type or entity that does not exist or may not be read."""


def _rows(conn, sql: str, **params) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _as_guid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- models

_MODEL_SQL = """
    SELECT m.id AS _id, m.guid AS id, m.name, m.description, m.kind_code AS kind, k.name AS kind_name,
           p.guid AS parent_model_id, p.name AS parent_model_name,
           s.guid AS source_model_id, s.name AS source_model_name, s.kind_code AS source_model_kind, m.source_tag_name, m.metamodel_name,
           m.metamodel_version, m.is_locked, m.status_code AS status,
           m.owner, m.lifecycle, m.industry, m.version_label,
           m.lock_level, m.lock_reason, m.locked_at, m.locked_by, m.frozen_at, m.frozen_by, m.frozen_note,
           m.library_state, m.copy_state, m.copy_note, m.history_from_source, m.is_draft, m.approval_state, m.published_at, m.published_by,
           m.created_at, m.created_by, m.modified_at, m.modified_by,
           CASE WHEN ic.library IS NOT NULL THEN 'lib:' || ic.library WHEN ic.data IS NOT NULL THEN 'upload' END AS icon,
           CAST(extract(epoch FROM ic.set_at) AS bigint) AS icon_version,
           (SELECT count(*) FROM core.entity_types t WHERE t.model_id = m.id AND NOT t.is_deleted AND NOT t.is_connector) AS entity_type_count,
           (SELECT count(*) FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
             WHERE e.model_id = m.id AND NOT e.is_deleted AND NOT t.is_connector) AS entity_count,     -- junctions are not elements (D397)
           (SELECT count(*) FROM core.relationships r WHERE r.model_id = m.id AND NOT r.is_deleted) AS relationship_count
      FROM core.models m
      JOIN core.model_kinds k ON k.code = m.kind_code
      LEFT JOIN core.models p ON p.id = m.parent_model_id
      LEFT JOIN core.models s ON s.id = m.source_model_id
      LEFT JOIN core.model_icons ic ON ic.model_id = m.id
     WHERE NOT m.is_deleted AND core.can_read_model(m.id)"""


def list_models(conn, search: str | None = None, kind: str | None = None,
                include_archived: bool = True) -> list[dict]:
    """Every readable model: templates first, then reference models, then project models.
    search matches the name, description, owner or industry; kind is template, reference or project."""
    return _rows(conn, _MODEL_SQL + """
       AND (CAST(:kind AS text) IS NULL OR m.kind_code = :kind)
       AND (:archived OR m.lifecycle = 'active')
       AND (CAST(:q AS text) IS NULL OR concat_ws(' ', m.name, m.description, m.owner, m.industry) ILIKE :q)
     ORDER BY CASE m.kind_code WHEN 'template' THEN 1 WHEN 'reference' THEN 2
              WHEN 'project' THEN 3 ELSE 4 END, m.name, m.version_label DESC""",
                 kind=kind or None, archived=include_archived, q=f"%{search.strip()}%" if search and search.strip() else None)


def get_library(conn, include_withdrawn: bool = False) -> list[dict]:
    """The model library: the root metamodels (the Root model, ArchiMate 4, an organisation's own) and
    the reference models (read-only industry content), each with the root it is built on and its counts
    by entity type, for browsing before copying one (D81, D101)."""
    models = [m for m in list_models(conn, kind="template") + list_models(conn, kind="reference")
              if m["library_state"] != "withdrawn" or include_withdrawn]
    by_id = {str(m["id"]): m for m in models}
    for m in models:
        # the root metamodel it is built on: up the created-from chain to the one just below the Root
        # model (the top of the hierarchy: the only template created from nothing)
        top = lambda x: x["kind"] == "template" and not x.get("source_model_id")
        up, root = m, None
        for _ in range(20):
            src = by_id.get(str(up.get("source_model_id")))
            if not src or top(src):
                break
            root, up = src, src
        m["is_top"] = top(m)
        m["built_on"] = root["name"] if root else (None if top(m) else m["name"] if m["kind"] == "template" else None)
        m["counts_by_type"] = _rows(conn, """
            SELECT et.name AS entity_type, l.name AS domain, l.colour, count(e.id) AS count
              FROM core.entity_types et
              JOIN core.layers l ON l.id = et.layer_id
              LEFT JOIN core.entities e ON e.entity_type_id = et.id AND NOT e.is_deleted
             WHERE et.model_id = :m AND NOT et.is_deleted AND NOT et.is_connector
             GROUP BY et.name, l.name, l.colour, l.sort_order, et.sort_order
             HAVING count(e.id) > 0 OR :tpl
             ORDER BY count(e.id) DESC, l.sort_order, et.sort_order""", m=m["_id"], tpl=m["kind"] == "template")
        m["relationship_counts"] = _rows(conn, """
            SELECT rt.name AS relationship_type, count(*) AS count
              FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
             WHERE r.model_id = :m AND NOT r.is_deleted
             GROUP BY rt.name, rt.sort_order ORDER BY count(*) DESC, rt.sort_order""", m=m["_id"])
        m["domains"] = _rows(conn, """SELECT l.name, l.colour, count(et.id) AS types FROM core.layers l
              LEFT JOIN core.entity_types et ON et.layer_id = l.id AND NOT et.is_deleted AND NOT et.is_connector
             WHERE l.model_id = :m GROUP BY l.name, l.colour, l.sort_order ORDER BY l.sort_order""", m=m["_id"])
        m["relationship_type_count"] = _rows(conn, "SELECT count(*) AS n FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted",
                                             m=m["_id"])[0]["n"]
    return models


def get_model(conn, model: Any) -> dict:
    """A model by guid or by name (case-insensitive)."""
    guid = _as_guid(model)
    if guid:
        rows = _rows(conn, _MODEL_SQL + " AND m.guid = :m", m=guid)
    else:
        rows = _rows(conn, _MODEL_SQL + " AND lower(m.name) = lower(:m)", m=str(model))
    if not rows:
        raise NotFound(f"No model {model!r}, or you may not read it.")
    return rows[0]


# ---------------------------------------------------------------- metamodel

def get_metamodel(conn, model: Any) -> dict:
    """Domains with their entity types, and the relationship types."""
    m = get_model(conn, model)
    mid = m["_id"]
    domains = _rows(conn, """
        SELECT guid AS id, code, name, description, colour FROM core.layers
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    types = _rows(conn, """
        SELECT et.guid AS id, l.guid AS domain_id, et.code, et.name, et.description, et.aspect, et.content_area, et.repository_area, et.id_prefix,
               et.table_name, et.status_code AS status, et.notation, et.fill_colour, et.is_connector, l.colour AS domain_colour,
               (SELECT count(*) FROM core.item_attributes ia
                 WHERE ia.entity_type_id = et.id AND NOT ia.is_deleted) AS attribute_count,
               (SELECT count(*) FROM core.entities e
                 WHERE e.entity_type_id = et.id AND NOT e.is_deleted) AS entity_count
          FROM core.entity_types et
          JOIN core.layers l ON l.id = et.layer_id
         WHERE et.model_id = :m AND NOT et.is_deleted ORDER BY et.sort_order, et.name""", m=mid)
    rel_types = _rows(conn, """
        SELECT guid AS id, code, name, verb, category, is_directed, description, status_code AS status
          FROM core.relationship_types
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    for t in types:
        _cf_defaults(t)
        t["drawio"] = notation.type_look(t)          # how it looks on a drawn view (phase 28, D354)
    for domain in domains:
        domain["entity_types"] = [t for t in types if t["domain_id"] == domain["id"]]
    return {"model": m, "domains": domains, "relationship_types": rel_types}


def _cf_defaults(t: dict) -> dict:
    """Where an entity type sits by default (D317, D318): its content framework areas and Repository Area as built in."""
    from .content_framework import area_of_type, repo_of_type
    dflt = area_of_type(t["code"], t["name"])[0]
    t["content_default"] = ",".join(dflt)
    t["repository_default"] = repo_of_type(t["code"], t["name"], "", area_of_type(t["code"], t["name"], t.get("content_area") or "")[0])[0]
    return t


def _find_type(conn, model_id: int, entity_type: Any) -> dict:
    """An entity type of a model by guid, or by name, code or table name (case-insensitive)."""
    guid = _as_guid(entity_type)
    where = "et.guid = :t" if guid else "lower(:t) IN (lower(et.code), lower(et.name), lower(et.table_name))"
    rows = _rows(conn, f"""
        SELECT et.id AS _id, et.guid AS id, et.code, et.name, et.description, et.aspect, et.content_area, et.repository_area, et.id_prefix,
               et.table_name, l.name AS domain, l.guid AS domain_id, l.colour, et.status_code AS status,
               et.notation, et.fill_colour, et.is_connector, l.colour AS domain_colour
          FROM core.entity_types et JOIN core.layers l ON l.id = et.layer_id
         WHERE {where} AND et.model_id = :m AND NOT et.is_deleted""", t=guid or str(entity_type), m=model_id)
    if not rows:
        raise NotFound(f"No entity type {entity_type!r} in this model.")
    rows[0]["drawio"] = notation.type_look(rows[0])
    return rows[0]


_ALLOWED_SQL = """
    SELECT ar.guid AS id, rt.name AS relationship_type, rt.guid AS relationship_type_id, rt.verb,
           o.guid AS other_type_id, o.name AS other_type, ar.note,
           ar.source_multiplicity, ar.target_multiplicity
      FROM core.allowed_relationships ar
      JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
      JOIN core.entity_types o ON o.id = ar.{other}
     WHERE ar.{this} = :t AND NOT ar.is_deleted
     ORDER BY rt.sort_order, o.sort_order"""


def get_entity_type(conn, model: Any, entity_type: Any) -> dict:
    """One entity type with its attributes, validation rules and allowed relationships."""
    mid = get_model(conn, model)["_id"]
    et = _cf_defaults(_find_type(conn, mid, entity_type))
    tid = et["_id"]
    et["attributes"] = _rows(conn, """
        SELECT ia.guid AS item_id, at.guid AS attribute_id, at.code, at.name, at.description, at.column_name,
               at.data_type_code AS data_type, dt.name AS data_type_name, at.unit, ia.is_required, ia.section,
               ia.default_value, ia.help_text, pl.guid AS pick_list_id,
               at.quality_weight AS attribute_quality_weight, ia.quality_weight AS item_quality_weight,
               coalesce(ia.quality_weight, at.quality_weight, CASE WHEN ia.is_required THEN 3 ELSE 1 END) AS quality_weight,
               pl.name AS pick_list,
               coalesce((SELECT array_agg(v.value ORDER BY v.sort_order) FROM core.pick_list_values v
                          WHERE v.pick_list_id = at.pick_list_id AND NOT v.is_deleted),
                        ARRAY[]::text[]) AS pick_list_values
          FROM core.item_attributes ia
          JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_types dt ON dt.code = at.data_type_code
          LEFT JOIN core.pick_lists pl ON pl.id = at.pick_list_id
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted
         ORDER BY ia.sort_order, at.name""", t=tid)
    et["rules"] = _rows(conn, """
        SELECT vr.guid AS id, coalesce(at.name, initcap(vr.field_name)) AS field, rt.name AS rule,
               vr.rule_type_code, at.guid AS attribute_id, vr.field_name,
               (vr.entity_type_id IS NULL) AS all_types,
               vr.param1, vr.param2, vr.severity, vr.message
          FROM core.validation_rules vr
          JOIN core.rule_types rt ON rt.code = vr.rule_type_code
          LEFT JOIN core.attribute_types at ON at.id = vr.attribute_type_id
         WHERE vr.model_id = :m AND NOT vr.is_deleted
           AND (vr.entity_type_id IS NULL OR vr.entity_type_id = :t)
           AND (vr.field_name IS NOT NULL OR vr.attribute_type_id IN (
                SELECT attribute_type_id FROM core.item_attributes
                 WHERE entity_type_id = :t AND NOT is_deleted))
         ORDER BY vr.sort_order""", m=mid, t=tid)
    et["outgoing"] = _rows(conn, _ALLOWED_SQL.format(this="source_type_id", other="target_type_id"), t=tid)
    et["incoming"] = _rows(conn, _ALLOWED_SQL.format(this="target_type_id", other="source_type_id"), t=tid)
    return et


def allowed_relationships(conn, model: Any, source_type: Any, target_type: Any) -> list[dict]:
    """The relationship types the metamodel allows from one entity type to another."""
    mid = get_model(conn, model)["_id"]
    src = _find_type(conn, mid, source_type)
    tgt = _find_type(conn, mid, target_type)
    return _rows(conn, """
        SELECT rt.name AS relationship_type, rt.verb, rt.category, rt.description, ar.note,
               ar.source_multiplicity, ar.target_multiplicity
          FROM core.allowed_relationships ar
          JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
         WHERE ar.source_type_id = :s AND ar.target_type_id = :t AND NOT ar.is_deleted
         ORDER BY rt.sort_order""", s=src["_id"], t=tgt["_id"])


def get_metamodel_diagram(conn, model: Any) -> dict:
    """Everything an ER diagram of the metamodel needs, in one call: domains, entity types with their
    attributes, relationship types, and the allowed relationships combined per (source, target) pair."""
    m = get_model(conn, model)
    mid = m["_id"]
    domains = _rows(conn, """
        SELECT guid AS id, code, name, colour FROM core.layers
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    types = _rows(conn, """
        SELECT et.id AS _id, et.guid AS id, et.code, et.name, et.table_name, et.id_prefix,
               l.guid AS domain_id, l.name AS domain, l.colour,
               (SELECT count(*) FROM core.entities e
                 WHERE e.entity_type_id = et.id AND NOT e.is_deleted) AS entity_count
          FROM core.entity_types et JOIN core.layers l ON l.id = et.layer_id
         WHERE et.model_id = :m AND NOT et.is_deleted
         ORDER BY l.sort_order, et.sort_order, et.name""", m=mid)
    attributes = _rows(conn, """
        SELECT ia.entity_type_id AS _type, at.name, at.column_name, at.data_type_code AS data_type,
               dt.name AS data_type_name, at.unit, ia.is_required, pl.name AS pick_list
          FROM core.item_attributes ia
          JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_types dt ON dt.code = at.data_type_code
          LEFT JOIN core.pick_lists pl ON pl.id = at.pick_list_id
         WHERE ia.model_id = :m AND ia.entity_type_id IS NOT NULL AND NOT ia.is_deleted
         ORDER BY ia.sort_order, at.name""", m=mid)
    by_type: dict[int, list] = {}
    for a in attributes:
        by_type.setdefault(a.pop("_type"), []).append(a)
    for t in types:
        t["attributes"] = by_type.get(t["_id"], [])
    rel_types = _rows(conn, """
        SELECT guid AS id, code, name, verb, category, is_directed FROM core.relationship_types
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    links = _rows(conn, """
        SELECT s.guid AS source, t.guid AS target,
               array_agg(rt.code ORDER BY rt.sort_order) AS relationship_types,
               array_agg(ar.source_multiplicity ORDER BY rt.sort_order) AS source_multiplicities,
               array_agg(ar.target_multiplicity ORDER BY rt.sort_order) AS target_multiplicities
          FROM core.allowed_relationships ar
          JOIN core.entity_types s ON s.id = ar.source_type_id
          JOIN core.entity_types t ON t.id = ar.target_type_id
          JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
         WHERE ar.model_id = :m AND NOT ar.is_deleted
         GROUP BY s.guid, t.guid, s.sort_order, t.sort_order
         ORDER BY s.sort_order, t.sort_order""", m=mid)
    return {"model": m, "domains": domains, "entity_types": types,
            "relationship_types": rel_types, "links": links}


def metamodel_mermaid(conn, model: Any, **scope) -> dict:
    """The metamodel (or part of it) as a Mermaid ER diagram. See eax.diagram.scope for the options."""
    from . import diagram
    data = get_metamodel_diagram(conn, model)
    try:
        part = diagram.scope(data, **scope)
    except LookupError as exc:
        raise NotFound(str(exc)) from exc
    return {"model": data["model"]["name"], "entity_types": len(part["entity_types"]),
            "links": len(part["links"]), "relationship_types": part["relationship_types"],
            "mermaid": diagram.to_mermaid(part, with_attributes=scope.get("with_attributes", True))}


# ---------------------------------------------------------------- content

def temp_table_name() -> str:
    """A fresh name for eax.get_entity's temporary tables: two calls never collide."""
    return f"e_{uuid.uuid4().hex}"


def get_entities(conn, model: Any, entity_type: str, name: str | None = None, limit: int = 500,
                 actor: str = "unknown") -> dict:
    """Entities of one type through eax.get_entity (or get_entity_by_name), with relationships.

    Uses temporary tables under a fresh guid-based name, dropped again before returning (they would
    otherwise live as long as the pooled connection). Needs a transaction (engine.begin()).
    """
    m = get_model(conn, model)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})
    table = temp_table_name()
    try:
        try:
            if name:
                tables = conn.execute(text("SELECT eax.get_entity_by_name(:t, :n, :tbl, CAST(:m AS uuid))"),
                                      {"t": entity_type, "n": name, "tbl": table, "m": str(m["id"])}).scalar_one()
            else:
                tables = conn.execute(text("SELECT eax.get_entity(:t, :tbl, CAST(:m AS uuid))"),
                                      {"t": entity_type, "tbl": table, "m": str(m["id"])}).scalar_one()
        except DBAPIError as exc:
            diag = getattr(exc.orig, "diag", None)
            raise NotFound(getattr(diag, "message_primary", None) or str(exc.orig)) from exc
        entity_table, rel_table = tables[0], tables[1]
        result = conn.execute(text(f'SELECT * FROM pg_temp."{entity_table}" LIMIT :n'), {"n": limit})
        columns = list(result.keys())
        rows = [dict(r) for r in result.mappings().all()]
        ids = [r["id"] for r in rows]
        rels = _rows(conn, f'SELECT * FROM pg_temp."{rel_table}" WHERE entity_id = ANY (:ids)', ids=ids)
    finally:
        try:  # after an error the transaction is rolled back, which removes the tables anyway
            conn.execute(text("SELECT eax.drop_entity(:tbl)"), {"tbl": table})
        except DBAPIError:
            pass
    return {"model": m["name"], "entity_table": entity_table, "relationship_table": rel_table,
            "columns": columns, "rows": rows, "relationships": rels}


def search_entities(conn, text_query: str, model: Any = None, limit: int = 50) -> list[dict]:
    """Entities whose name, display ID or description contains the text, in one or every readable model; an entity merged
    away as a duplicate (D361) is found by its old display ID or name as the one kept."""
    mid = get_model(conn, model)["_id"] if model else None
    found = _search_entities(conn, text_query, mid, limit)
    have = {str(r["id"]) for r in found}
    for r in _rows(conn, """
        SELECT e.guid AS id, e.display_id, e.name, et.name AS entity_type, m.name AS model, m.guid AS model_id,
               'Merged in: ' || a.old_display_id || ' ' || a.old_name AS description
          FROM core.entity_aliases a JOIN core.entities e ON e.guid = a.survivor_guid AND e.model_id = a.model_id AND NOT e.is_deleted
          JOIN core.entity_types et ON et.id = e.entity_type_id JOIN core.models m ON m.id = e.model_id
         WHERE NOT m.is_deleted AND core.can_read_model(m.id) AND (CAST(:m AS bigint) IS NULL OR a.model_id = :m)
           AND (a.old_display_id ILIKE :q OR a.old_name ILIKE :q)
           AND NOT EXISTS (SELECT 1 FROM core.entities o WHERE o.guid = a.old_guid AND NOT o.is_deleted)
         LIMIT 20""", m=mid, q=f"%{text_query}%"):
        if str(r["id"]) not in have and len(found) < limit:
            found.append(r)
            have.add(str(r["id"]))
    return found


def _search_entities(conn, text_query: str, mid: int | None, limit: int) -> list[dict]:
    return _rows(conn, """
        SELECT e.guid AS id, e.display_id, e.name, et.name AS entity_type, m.name AS model,
               m.guid AS model_id, left(e.description, 200) AS description
          FROM core.entities e
          JOIN core.entity_types et ON et.id = e.entity_type_id
          JOIN core.models m ON m.id = e.model_id
         WHERE NOT e.is_deleted AND NOT m.is_deleted AND core.can_read_model(m.id)
           AND (CAST(:m AS bigint) IS NULL OR e.model_id = :m)
           AND (e.name ILIKE :q OR e.display_id ILIKE :q OR e.description ILIKE :q)
         ORDER BY (lower(e.name) = lower(:exact)) DESC, e.name
         LIMIT :n""", m=mid, q=f"%{text_query}%", exact=text_query, n=limit)


def list_entities(conn, model: Any, entity_type: Any = None, limit: int = 2000) -> list[dict]:
    """Every entity of a model (or of one type), with its type, domain and relationship count."""
    m = get_model(conn, model)
    tid = _find_type(conn, m["_id"], entity_type)["_id"] if entity_type else None
    return _rows(conn, """
        SELECT e.guid AS id, e.display_id, e.name, left(e.description, 300) AS description,
               et.name AS entity_type, et.guid AS entity_type_id, l.name AS domain, l.colour,
               pe.name AS parent_name, e.status_code AS status,
               (SELECT count(*) FROM core.relationships r
                 WHERE (r.source_entity_id = e.id OR r.target_entity_id = e.id) AND NOT r.is_deleted) AS relationship_count,
               e.modified_at, e.modified_by
          FROM core.entities e
          JOIN core.entity_types et ON et.id = e.entity_type_id
          JOIN core.layers l ON l.id = et.layer_id
          LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
         WHERE e.model_id = :m AND NOT e.is_deleted
           AND (CAST(:t AS bigint) IS NULL OR e.entity_type_id = :t)
         ORDER BY l.sort_order, et.sort_order, e.name
         LIMIT :n""", m=m["_id"], t=tid, n=limit)


_ALLOWED_EXISTS = """EXISTS (SELECT 1 FROM core.allowed_relationships ar
                      WHERE ar.source_type_id = s.entity_type_id AND ar.target_type_id = t.entity_type_id
                        AND ar.relationship_type_id = r.relationship_type_id AND NOT ar.is_deleted)"""


def _find_relationship_type(conn, model_id: int, rel_type: Any) -> dict:
    guid = _as_guid(rel_type)
    where = "guid = :r" if guid else "lower(:r) IN (lower(code), lower(name), lower(verb))"
    rows = _rows(conn, f"""SELECT id AS _id, guid AS id, code, name, verb FROM core.relationship_types
                            WHERE {where} AND model_id = :m AND NOT is_deleted""", r=guid or str(rel_type), m=model_id)
    if not rows:
        raise NotFound(f"No relationship type {rel_type!r} in this model.")
    return rows[0]


def list_relationships(conn, model: Any, relationship_type: Any = None, limit: int = 5000) -> list[dict]:
    """Every relationship of a model (or of one relationship type): source, type, target, and
    whether the metamodel allows it (allowed is false for a relationship added outside the rules)."""
    m = get_model(conn, model)
    rid = _find_relationship_type(conn, m["_id"], relationship_type)["_id"] if relationship_type else None
    return _rows(conn, f"""
        SELECT r.guid AS id, rt.name AS relationship_type, rt.code AS relationship_type_code, rt.verb,
               s.guid AS source_id, s.display_id AS source_display_id, s.name AS source_name,
               st.name AS source_type, sl.colour AS source_colour,
               t.guid AS target_id, t.display_id AS target_display_id, t.name AS target_name,
               tt.name AS target_type, tl.colour AS target_colour, r.name, r.status_code AS status,
               {_ALLOWED_EXISTS} AS allowed
          FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id
          JOIN core.entity_types st ON st.id = s.entity_type_id
          JOIN core.layers sl ON sl.id = st.layer_id
          JOIN core.entities t ON t.id = r.target_entity_id
          JOIN core.entity_types tt ON tt.id = t.entity_type_id
          JOIN core.layers tl ON tl.id = tt.layer_id
         WHERE r.model_id = :m AND NOT r.is_deleted AND NOT s.is_deleted AND NOT t.is_deleted
           AND (CAST(:r AS bigint) IS NULL OR r.relationship_type_id = :r)
         ORDER BY rt.sort_order, s.name, t.name
         LIMIT :n""", m=m["_id"], r=rid, n=limit)


def relationship_type_summary(conn, model: Any) -> list[dict]:
    """Every relationship type of the model with how often it is used, how many (source type,
    target type) pairs the metamodel allows for it, and how many of its relationships are outside
    those rules."""
    m = get_model(conn, model)
    return _rows(conn, f"""
        SELECT rt.guid AS id, rt.code, rt.name, rt.verb, rt.category, rt.is_directed, rt.description,
               (SELECT count(*) FROM core.allowed_relationships ar
                 WHERE ar.relationship_type_id = rt.id AND NOT ar.is_deleted) AS allowed_pairs,
               count(r.id) AS relationship_count,
               count(r.id) FILTER (WHERE NOT {_ALLOWED_EXISTS}) AS outside_rules
          FROM core.relationship_types rt
          LEFT JOIN core.relationships r ON r.relationship_type_id = rt.id AND NOT r.is_deleted
          LEFT JOIN core.entities s ON s.id = r.source_entity_id
          LEFT JOIN core.entities t ON t.id = r.target_entity_id
         WHERE rt.model_id = :m AND NOT rt.is_deleted
         GROUP BY rt.id ORDER BY rt.sort_order, rt.name""", m=m["_id"])


# ---------------------------------------------------------------- values and validation rules

_VALUES_SQL = """
    SELECT e.id AS _entity, at.id AS _attr, at.code, at.name, ia.section, at.data_type_code AS data_type,
           dt.name AS data_type_name, at.unit, ia.is_required, at.pick_list_id AS _pick_list,
           av.value_text, av.value_number, av.value_date, av.value_bool, av.rule_override,
           re.guid AS ref_id, re.name AS ref_name, ret.code AS ref_type
      FROM core.entities e
      JOIN core.item_attributes ia ON ia.entity_type_id = e.entity_type_id AND NOT ia.is_deleted
      JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
      JOIN core.data_types dt ON dt.code = at.data_type_code
      LEFT JOIN core.attribute_values av
             ON av.entity_id = e.id AND av.attribute_type_id = at.id AND NOT av.is_deleted
      LEFT JOIN core.entities re ON re.id = av.value_ref
      LEFT JOIN core.entity_types ret ON ret.id = re.entity_type_id
     WHERE {where}
     ORDER BY e.id, ia.sort_order, at.name"""


def _display(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if hasattr(value, "normalize"):  # Decimal: 5.00 -> 5
        return format(value.normalize(), "f")
    return str(value)


def _load_values(conn, where: str, **params) -> dict[int, list[dict]]:
    """Every attribute of each entity's type with the entity's value (typed, and for display)."""
    rows = _rows(conn, _VALUES_SQL.format(where=where), **params)
    pick_ids = {r["_pick_list"] for r in rows if r["_pick_list"]}
    picks: dict[int, list[str]] = {}
    if pick_ids:
        for p in _rows(conn, """SELECT pick_list_id, array_agg(value ORDER BY sort_order) AS v
                                  FROM core.pick_list_values WHERE pick_list_id = ANY (:ids) AND NOT is_deleted
                                 GROUP BY pick_list_id""", ids=list(pick_ids)):
            picks[p["pick_list_id"]] = list(p["v"])
    out: dict[int, list[dict]] = {}
    for r in rows:
        typed = next((v for v in (r["value_text"], r["value_number"], r["value_date"], r["value_bool"])
                      if v is not None), None)
        if typed is None and r["ref_name"] is not None:
            typed = r["ref_name"]
        out.setdefault(r["_entity"], []).append({
            "code": r["code"], "name": r["name"], "section": r["section"], "data_type": r["data_type"],
            "data_type_name": r["data_type_name"],
            "unit": r["unit"], "is_required": r["is_required"], "value": _display(typed), "typed": typed,
            "ref_id": r["ref_id"], "ref_type": r["ref_type"], "override": r["rule_override"],
            "pick_list_values": picks.get(r["_pick_list"], []), "_attr": r["_attr"],
            **({"links": links.parse(r["value_text"])} if r["data_type"] == "url" else {}),
        })
    return out


def _rules_for_type(conn, model_id: int, type_id: int) -> list[dict]:
    return _rows(conn, """
        SELECT vr.rule_type_code, vr.field_name, at.code AS attribute_code, vr.param1, vr.param2,
               vr.severity, vr.message
          FROM core.validation_rules vr
          LEFT JOIN core.attribute_types at ON at.id = vr.attribute_type_id
         WHERE vr.model_id = :m AND NOT vr.is_deleted
           AND (vr.entity_type_id IS NULL OR vr.entity_type_id = :t)
         ORDER BY vr.sort_order""", m=model_id, t=type_id)


def _duplicate_names(conn, model_id: int, type_id: int) -> set[str]:
    return {r["n"] for r in _rows(conn, """
        SELECT lower(name) AS n FROM core.entities
         WHERE model_id = :m AND entity_type_id = :t AND NOT is_deleted
         GROUP BY lower(name) HAVING count(*) > 1""", m=model_id, t=type_id)}


def _relationships_by_entity(conn, entity_ids: list[int]) -> dict[int, list[dict]]:
    """Each entity's live relationships, for rules about relationships (D113): type, the entity type at
    the other end, which way, and whether the metamodel allows it."""
    if not entity_ids:
        return {}
    out: dict[int, list[dict]] = {}
    for r in _rows(conn, f"""
        SELECT x.e AS _entity, r.guid AS id, rt.name AS type, rt.code AS type_code, rt.verb,
               CASE WHEN r.source_entity_id = x.e THEN 'outgoing' ELSE 'incoming' END AS direction,
               o.guid AS other_id, o.name AS other_name, o.display_id AS other_display_id,
               ot.name AS other_type, ot.code AS other_type_code, {_ALLOWED_EXISTS} AS allowed
          FROM unnest(CAST(:ids AS bigint[])) AS x(e)
          JOIN core.relationships r ON (r.source_entity_id = x.e OR r.target_entity_id = x.e) AND NOT r.is_deleted
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id
          JOIN core.entities t ON t.id = r.target_entity_id
          JOIN core.entities o ON o.id = CASE WHEN r.source_entity_id = x.e THEN r.target_entity_id ELSE r.source_entity_id END
          JOIN core.entity_types ot ON ot.id = o.entity_type_id
         WHERE NOT o.is_deleted
         ORDER BY rt.sort_order, o.name""", ids=list(entity_ids)):
        out.setdefault(r.pop("_entity"), []).append(r)
    return out


def _warnings(entity: dict, attrs: list[dict], rules: list[dict], duplicates: set[str]) -> list[dict]:
    from . import rules as rule_check
    for_rules = [{**a, "value": a["typed"]} for a in attrs]
    return rule_check.evaluate(entity, for_rules, rules,
                               duplicate_name=(entity.get("name") or "").lower() in duplicates)


def type_table(conn, model: Any, entity_type: Any, limit: int = 10000) -> dict:
    """The entities of one type as a table: one column per attribute, each row with its values,
    relationship count and rule results (errors and warnings)."""
    m = get_model(conn, model)
    et = _find_type(conn, m["_id"], entity_type)
    tid = et.pop("_id")
    columns = _rows(conn, """
        SELECT at.code, at.name, at.data_type_code AS data_type, at.unit, ia.is_required, ia.section
          FROM core.item_attributes ia JOIN core.attribute_types at ON at.id = ia.attribute_type_id
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted AND NOT at.is_deleted
         ORDER BY ia.sort_order, at.name""", t=tid)
    rows = _rows(conn, """
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, e.description, e.status_code AS status,
               pe.guid AS parent_id, pe.name AS parent_name, e.modified_at, e.modified_by, e.row_version,
               e.created_mm_version, e.modified_mm_version,
               (SELECT count(*) FROM core.relationships r
                 WHERE (r.source_entity_id = e.id OR r.target_entity_id = e.id) AND NOT r.is_deleted) AS relationship_count
          FROM core.entities e LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
         WHERE e.model_id = :m AND e.entity_type_id = :t AND NOT e.is_deleted
         ORDER BY e.display_id LIMIT :n""", m=m["_id"], t=tid, n=limit)
    values = _load_values(conn, "e.model_id = :m AND e.entity_type_id = :t AND NOT e.is_deleted", m=m["_id"], t=tid)
    rules = _rules_for_type(conn, m["_id"], tid)
    duplicates = _duplicate_names(conn, m["_id"], tid)
    rels = _relationships_by_entity(conn, [r["_id"] for r in rows]) \
        if any(x["rule_type_code"] == "has_relationship" for x in rules) else {}
    for r in rows:
        attrs = values.get(r["_id"], [])
        r["values"] = {a["code"]: a["value"] for a in attrs if a["value"] is not None}
        found = _warnings({**r, "relationships": rels.get(r["_id"], [])}, attrs, rules, duplicates)
        r["errors"] = sum(1 for w in found if w["severity"] == "error")
        r["warnings"] = len(found) - r["errors"]
        r["messages"] = [w["message"] for w in found]
        r["checks"] = [{"rule": w["rule"], "field": w["field"], "code": w["code"], "severity": w["severity"],
                        "message": w["message"]} for w in found]
        del r["_id"]
    return {"entity_type": et, "columns": columns, "rows": rows, "rules": len(rules)}


def _find_entity(conn, m: dict, entity: Any, _alias: bool = True) -> dict:
    try:
        return _find_entity_now(conn, m, entity)
    except NotFound:
        if not _alias:
            raise
        # merged away as a duplicate (D361): its old guid or display ID finds the one kept
        from .dedupe import alias
        hit = alias(conn, m, str(entity))
        if not hit:
            raise
        e = _find_entity_now(conn, m, hit["survivor"])
        e["merged_from"] = f"{hit['old_name']} ({hit['old_display_id']})" if hit["old_display_id"] else hit["old_name"]
        return e


def _find_entity_now(conn, m: dict, entity: Any) -> dict:
    guid = _as_guid(entity)
    where = "e.guid = :e" if guid else "(lower(e.name) = lower(:e) OR lower(e.display_id) = lower(:e))"
    found = _rows(conn, f"""
        SELECT e.id AS _id, e.entity_type_id AS _type, e.guid AS id, e.display_id, e.name, e.description,
               e.status_code AS status, e.tags, e.content_area, et.content_area AS _type_area, et.repository_area AS _type_repo, et.name AS entity_type, et.code AS entity_type_code,
               et.guid AS entity_type_id, l.name AS domain, l.colour, et.status_code AS entity_type_status,
               pe.guid AS parent_id, pe.name AS parent_name,
               e.created_at, e.created_by, e.modified_at, e.modified_by, e.row_version,
               e.created_mm_version, e.modified_mm_version,
               e.origin_guid AS _origin, et.origin_guid AS _type_origin
          FROM core.entities e
          JOIN core.entity_types et ON et.id = e.entity_type_id
          JOIN core.layers l ON l.id = et.layer_id
          LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
         WHERE {where} AND e.model_id = :m AND NOT e.is_deleted
         ORDER BY e.display_id LIMIT 1""", e=guid or str(entity), m=m["_id"])
    if not found:
        raise NotFound(f"No entity {entity!r} in model {m['name']!r}.")
    e = found[0]
    from .content_framework import (  # where it sits in the content framework (D317)
        area_of_type,
        areas_of,
    )
    e["content_areas"] = areas_of(e.pop("content_area", ""))
    e["type_areas"] = area_of_type(e["entity_type_code"], e["entity_type"], e.pop("_type_area", ""))[0]
    from .content_framework import repo_of_type
    e["repository_area"] = repo_of_type(e["entity_type_code"], e["entity_type"], e.pop("_type_repo", ""), e["type_areas"])[0]
    e["model"] = {k: m[k] for k in ("id", "name", "kind", "kind_name", "version_label", "is_locked",
                                     "source_model_id", "source_model_name", "parent_model_id", "parent_model_name")}
    return e


def _lineage(conn, e: dict) -> dict:
    """Where an entity came from and where it went: the entity it was copied from (and its model),
    the template entity type its type came from, and the copies made of it in other models."""
    origin = _rows(conn, """
        SELECT x.guid AS id, x.display_id, x.name, m.guid AS model_id, m.name AS model_name,
               m.version_label AS model_version, m.kind_code AS model_kind
          FROM core.entities x JOIN core.models m ON m.id = x.model_id
         WHERE x.guid = :g AND core.can_read_model(m.id)""", g=e["_origin"]) if e.get("_origin") else []
    type_origin = _rows(conn, """
        SELECT x.guid AS id, x.name, m.guid AS model_id, m.name AS model_name, m.kind_code AS model_kind
          FROM core.entity_types x JOIN core.models m ON m.id = x.model_id
         WHERE x.guid = :g AND core.can_read_model(m.id)""", g=e["_type_origin"]) if e.get("_type_origin") else []
    copies = _rows(conn, """
        SELECT x.guid AS id, x.display_id, x.name, m.guid AS model_id, m.name AS model_name,
               m.version_label AS model_version, m.kind_code AS model_kind
          FROM core.entities x JOIN core.models m ON m.id = x.model_id
         WHERE x.origin_guid = :g AND NOT x.is_deleted AND NOT m.is_deleted AND core.can_read_model(m.id)
         ORDER BY m.name, x.name""", g=e["id"])
    return {"copied_from": origin[0] if origin else None, "copied_from_guid": e.get("_origin"),
            "type_from": type_origin[0] if type_origin else None, "copies": copies}


def get_entity_detail(conn, model: Any, entity: Any) -> dict:
    """One entity (by guid, display ID or name): every attribute of its type with its value and
    rule results, the warnings (errors and warnings from the validation rules), its relationships
    (each marked allowed or outside the metamodel's rules), parent and children."""
    m = get_model(conn, model)
    e = _find_entity(conn, m, entity)
    e["lineage"] = _lineage(conn, e)
    eid, tid = e.pop("_id"), e.pop("_type")
    e.pop("_origin"), e.pop("_type_origin")
    attrs = _load_values(conn, "e.id = :e", e=eid).get(eid, [])
    warnings = _warnings({**e, "relationships": _relationships_by_entity(conn, [eid]).get(eid, [])}, attrs,
                         _rules_for_type(conn, m["_id"], tid), _duplicate_names(conn, m["_id"], tid))
    for a in attrs:
        a.pop("typed")
        a["warnings"] = [w for w in warnings if w["code"].lower() == a["code"].lower()]
    e["attributes"] = attrs
    e["warnings"] = warnings
    e["relationships"] = _rows(conn, f"""
        SELECT r.guid AS id, rt.guid AS relationship_type_id, rt.name AS relationship_type,
               rt.code AS relationship_type_code, rt.verb, rt.category,
               CASE WHEN r.source_entity_id = :e THEN 'outgoing' ELSE 'incoming' END AS direction,
               o.guid AS other_id, o.display_id AS other_display_id, o.name AS other_name,
               ot.name AS other_type, ot.guid AS other_type_id, ol.colour AS other_colour,
               r.name, r.status_code AS status, r.modified_at, r.modified_by,
               {_ALLOWED_EXISTS} AS allowed
          FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id
          JOIN core.entities t ON t.id = r.target_entity_id
          JOIN core.entities o ON o.id = CASE WHEN r.source_entity_id = :e THEN r.target_entity_id
                                            ELSE r.source_entity_id END
          JOIN core.entity_types ot ON ot.id = o.entity_type_id
          JOIN core.layers ol ON ol.id = ot.layer_id
         WHERE (r.source_entity_id = :e OR r.target_entity_id = :e) AND NOT r.is_deleted AND NOT o.is_deleted
         ORDER BY 7 DESC, rt.sort_order, o.name""", e=eid)
    e["children"] = _rows(conn, """
        SELECT c.guid AS id, c.display_id, c.name FROM core.entities c
         WHERE c.parent_entity_id = :e AND NOT c.is_deleted ORDER BY c.name""", e=eid)
    # what the metamodel allows this entity to be linked to (for adding relationships, phase 6)
    e["allowed"] = _rows(conn, """
        SELECT 'outgoing' AS direction, rt.name AS relationship_type, rt.verb, o.guid AS other_type_id, o.name AS other_type
          FROM core.allowed_relationships ar
          JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
          JOIN core.entity_types o ON o.id = ar.target_type_id
         WHERE ar.source_type_id = :t AND NOT ar.is_deleted
        UNION ALL
        SELECT 'incoming', rt.name, rt.verb, o.guid, o.name
          FROM core.allowed_relationships ar
          JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
          JOIN core.entity_types o ON o.id = ar.source_type_id
         WHERE ar.target_type_id = :t AND NOT ar.is_deleted
         ORDER BY 1 DESC, 2, 5""", t=tid)
    return e


def check_draft(conn, model: Any, entity_type: Any, data: dict, entity: Any = None) -> dict:
    """The rules an entity would fail with the values on the form, before it is saved (owner, 5 Nov 2026, D194): the
    same checks as after a save (required flags, pick lists, the type's validation rules, duplicate names, relationships
    it must have), on a draft. data: name, description, values {attribute code: value as typed}. Nothing is written."""
    from . import rules as rule_check
    m = get_model(conn, model)
    et = _find_type(conn, m["_id"], entity_type)
    tid = et["_id"]
    attrs = _rows(conn, """
        SELECT at.code, at.name, at.data_type_code AS data_type, ia.is_required,
               coalesce((SELECT array_agg(v.value ORDER BY v.sort_order) FROM core.pick_list_values v
                          WHERE v.pick_list_id = at.pick_list_id AND NOT v.is_deleted), ARRAY[]::text[]) AS pick_list_values
          FROM core.item_attributes ia JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted ORDER BY ia.sort_order, at.name""", t=tid)
    base: dict[str, Any] = {}
    rels: list[dict] = []
    name_now = None
    if entity:
        e = _find_entity(conn, m, entity)
        base = {a["code"].lower(): a["typed"] for a in _load_values(conn, "e.id = :e", e=e["_id"]).get(e["_id"], [])}
        rels = _relationships_by_entity(conn, [e["_id"]]).get(e["_id"], [])
        name_now = (e.get("name") or "").lower()
        entity_base = {k: e.get(k) for k in ("name", "description", "display_id")}
    else:
        entity_base = {"name": "", "description": "", "display_id": None}
    draft = {str(k).lower(): v for k, v in ((data or {}).get("values") or {}).items()}
    for_rules = []
    for a in attrs:
        k = a["code"].lower()
        v = draft[k] if k in draft else base.get(k)
        if isinstance(v, str) and not v.strip():
            v = None
        for_rules.append({**a, "pick_list_values": list(a["pick_list_values"] or []), "value": v})
    ent = {**entity_base, **{k: data[k] for k in ("name", "description") if k in (data or {})}, "relationships": rels}
    name = (ent.get("name") or "").strip().lower()
    others = _rows(conn, """SELECT count(*) AS n FROM core.entities WHERE model_id = :m AND entity_type_id = :t AND NOT is_deleted
                             AND lower(name) = :n""", m=m["_id"], t=tid, n=name)[0] if name else {"n": 0}
    duplicate = others["n"] > (1 if name and name == name_now else 0)
    warnings = rule_check.evaluate(ent, for_rules, _rules_for_type(conn, m["_id"], tid), duplicate_name=duplicate)
    return {"warnings": warnings, "summary": rule_check.summary(warnings)}


def get_entity_rules(conn, model: Any, entity: Any) -> dict:
    """Every rule applied to one entity and whether it passed, failed or did not apply (D113): the
    metamodel's required flags and pick lists, the validation rules of its type (values, patterns,
    dates, duplicates, relationships it must have), and for each of its relationships whether the
    metamodel allows it. Failed first. Checks warn, they never block (D48)."""
    from . import rules as rule_check
    m = get_model(conn, model)
    e = _find_entity(conn, m, entity)
    eid, tid = e["_id"], e["_type"]
    attrs = _load_values(conn, "e.id = :e", e=eid).get(eid, [])
    rels = _relationships_by_entity(conn, [eid]).get(eid, [])
    rules = _rules_for_type(conn, m["_id"], tid)
    results = rule_check.results({**e, "relationships": rels}, [{**a, "value": a["typed"]} for a in attrs], rules,
                                 duplicate_name=(e.get("name") or "").lower() in _duplicate_names(conn, m["_id"], tid))
    rel_checks = [{
        "id": r["id"], "relationship_type": r["type"], "verb": r["verb"], "direction": r["direction"],
        "other_id": r["other_id"], "other_name": r["other_name"], "other_display_id": r["other_display_id"],
        "other_type": r["other_type"], "status": "passed" if r["allowed"] else "failed", "severity": "warning",
        "message": None if r["allowed"] else (f"No mapping in the metamodel allows {r['type']} "
                                              f"{'from' if r['direction'] == 'outgoing' else 'to'} {e['entity_type']} "
                                              f"{'to' if r['direction'] == 'outgoing' else 'from'} {r['other_type']}"),
    } for r in rels]
    every = results + rel_checks
    count = lambda st, sev=None: sum(1 for x in every if x["status"] == st and (sev is None or x["severity"] == sev))
    return {
        "entity": {k: e[k] for k in ("id", "display_id", "name", "entity_type")},
        "metamodel_version": m["metamodel_version"],
        "summary": {"checks": len(every), "passed": count("passed"), "failed": count("failed"),
                    "errors": count("failed", "error"), "warnings": count("failed", "warning"),
                    "not_applicable": count("not_applicable")},
        "rules": results, "relationships": rel_checks,
    }


# ---------------------------------------------------------------- history

_NOISE = {"id", "guid", "model_id", "origin_guid", "row_version", "created_at", "created_by",
          "modified_at", "modified_by"}


def _history_rows(conn, m: dict, eid: int):
    """The history rows of an entity, its attribute values and its relationships (oldest first),
    with names for the ids they hold and a function giving an attribute row's value for display."""
    rows = _rows(conn, """
        SELECT id, tx, table_name, row_id, row_version, operation, data, label, changed_at, changed_by
          FROM history.row_versions
         WHERE model_id = :m AND (
               (table_name = 'entities' AND row_id = :e)
            OR (table_name = 'attribute_values' AND data->>'entity_id' = :es)
            OR (table_name = 'relationships' AND (data->>'source_entity_id' = :es OR data->>'target_entity_id' = :es)))
         ORDER BY table_name, row_id, changed_at, id""", m=m["_id"], e=eid, es=str(eid))   # by time: a deep copy's
    # earlier versions (copied from its source, D132) come before the copy's own
    entity_ids, attr_ids, rel_type_ids = set(), set(), set()
    for r in rows:
        d = r["data"]
        for k in ("parent_entity_id", "source_entity_id", "target_entity_id", "value_ref"):
            if d.get(k):
                entity_ids.add(int(d[k]))
        if d.get("attribute_type_id"):
            attr_ids.add(int(d["attribute_type_id"]))
        if d.get("relationship_type_id"):
            rel_type_ids.add(int(d["relationship_type_id"]))
    names = {r["id"]: r["name"] for r in _rows(conn, "SELECT id, name FROM core.entities WHERE id = ANY (:i)",
                                               i=list(entity_ids))} if entity_ids else {}
    attrs = {r["id"]: r["name"] for r in _rows(conn, "SELECT id, name FROM core.attribute_types WHERE id = ANY (:i)",
                                               i=list(attr_ids))} if attr_ids else {}
    verbs = {r["id"]: r for r in _rows(conn, "SELECT id, guid, code, name, verb FROM core.relationship_types WHERE id = ANY (:i)",
                                       i=list(rel_type_ids))} if rel_type_ids else {}

    def attr_value(d: dict):
        for k in ("value_text", "value_number", "value_date", "value_bool"):
            v = d.get(k)
            if v is not None:
                if isinstance(v, bool):
                    return _display(v)
                if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
                    return str(int(v))
                if isinstance(v, float):
                    return f"{v:.10f}".rstrip("0").rstrip(".")
                return _display(v)
        return names.get(int(d["value_ref"])) if d.get("value_ref") else None

    return rows, names, attrs, verbs, attr_value


def get_entity_as_of(conn, model: Any, entity: Any, event: int | None = None, at: Any = None) -> dict:
    """An entity as it was at one point in its history: just after history event `event` (an id from
    get_entity_history), or at time `at`. Every field, attribute value and relationship then, beside
    its value now, so the screen can show what changed since. Reading only: rolling back to that point
    arrives with editing (build phase 6)."""
    m = get_model(conn, model)
    e = _find_entity(conn, m, entity)
    eid = e["_id"]
    rows, names, attr_names, verbs, attr_value = _history_rows(conn, m, eid)
    if not rows:
        raise NotFound("This entity has no recorded history.")
    chrono = sorted(rows, key=lambda r: (r["changed_at"], r["id"]))
    if event is not None:
        point = next((r for r in chrono if r["id"] == int(event)), None)
        if point is None:
            raise NotFound(f"History event {event} does not belong to this entity.")
        cut = [r for r in chrono if (r["changed_at"], r["id"]) <= (point["changed_at"], point["id"])]
    else:
        import datetime as _dt
        when = at if isinstance(at, _dt.datetime) else _dt.datetime.fromisoformat(str(at)) if at else None
        if when is None:
            raise NotFound("Give a history event or a time.")
        cut = [r for r in chrono if _as_datetime(r["changed_at"]) <= _aware(when)]
        if not cut:
            raise NotFound("The entity did not exist yet at that time.")
        point = cut[-1]
    state: dict[tuple, dict] = {}
    for r in cut:
        state[(r["table_name"], r["row_id"])] = r
    # what changed at this moment (the same person within the same second, as the timeline groups it):
    # the state just before it, to highlight what this moment changed and show the old value on hover
    sec = lambda r: (int(_as_datetime(r["changed_at"]).timestamp()), r["changed_by"])
    moment = {r["id"] for r in cut if sec(r) == sec(point)}
    before: dict[tuple, dict] = {}
    for r in cut:
        if r["id"] not in moment:
            before[(r["table_name"], r["row_id"])] = r
    alive = lambda r: r is not None and not r["data"].get("is_deleted") and r["operation"] != "delete"
    row = state.get(("entities", eid))
    then = row["data"] if row else {}
    prev_row = before.get(("entities", eid))
    prev = prev_row["data"] if alive(prev_row) else {}
    created_here = not alive(prev_row) and alive(row)
    now_detail = get_entity_detail(conn, model, e["id"])
    fields = []
    for label, key, now in (("Name", "name", e["name"]), ("Description", "description", e["description"]),
                            ("Parent", "parent_entity_id", e["parent_name"]), ("Status", "status_code", e["status"])):
        value, old = then.get(key), prev.get(key)
        if key == "parent_entity_id":
            value = names.get(int(value)) if value else None
            old = names.get(int(old)) if old else None
        value = None if value in (None, "") else str(value)
        old = None if old in (None, "") else str(old)
        fields.append({"field": label, "then": value, "now": None if now in (None, "") else str(now),
                       "before": old, "changed_here": value != old})

    def values_of(st):
        out = {}
        for (table, _), r in st.items():
            if table == "attribute_values" and alive(r):
                out[int(r["data"]["attribute_type_id"])] = attr_value(r["data"])
        return out
    then_values, before_values = values_of(state), values_of(before)
    attributes = []
    for a in _load_values(conn, "e.id = :e", e=eid).get(eid, []):
        t, n, b = then_values.get(a["_attr"]), a["value"], before_values.get(a["_attr"])
        attributes.append({"code": a["code"], "name": a["name"], "section": a["section"], "then": t, "now": n,
                           "changed": (t or None) != (n or None), "before": b, "changed_here": (t or None) != (b or None)})
    for f in fields:
        f["changed"] = f["then"] != f["now"]
    then_rels = []
    for (table, rel_row), r in state.items():
        d = r["data"]
        if table != "relationships" or d.get("is_deleted") or r["operation"] == "delete":
            continue
        rt = verbs.get(int(d.get("relationship_type_id") or 0), {"name": "?", "verb": "relates to"})
        outgoing = str(d.get("source_entity_id")) == str(eid)
        other = int(d["target_entity_id" if outgoing else "source_entity_id"])
        then_rels.append({"id": d.get("guid"), "relationship_type": rt["name"], "verb": rt["verb"],
                          "direction": "outgoing" if outgoing else "incoming", "other_name": names.get(other, "?"),
                          "_other": other, "added_here": not alive(before.get(("relationships", rel_row))) and r["id"] in moment})
    # relationships this moment removed: there just before it, gone at it
    removed_here = []
    for (table, rid), r in state.items():
        b = before.get((table, rid))
        if table != "relationships" or r["id"] not in moment or alive(r) or not alive(b):
            continue
        d = b["data"]
        rt = verbs.get(int(d.get("relationship_type_id") or 0), {"name": "?", "verb": "relates to"})
        outgoing = str(d.get("source_entity_id")) == str(eid)
        other = int(d["target_entity_id" if outgoing else "source_entity_id"])
        removed_here.append({"id": d.get("guid"), "relationship_type": rt["name"], "verb": rt["verb"],
                             "direction": "outgoing" if outgoing else "incoming", "other_name": names.get(other, "?")})
    others = {r["id"]: r for r in _rows(conn, """
        SELECT e.id, e.guid, e.display_id, et.name AS entity_type, l.colour
          FROM core.entities e JOIN core.entity_types et ON et.id = e.entity_type_id JOIN core.layers l ON l.id = et.layer_id
         WHERE e.id = ANY (:i)""", i=[r["_other"] for r in then_rels])} if then_rels else {}
    for r in then_rels:
        o = others.get(r.pop("_other"), {})
        r["other_id"], r["other_display_id"] = o.get("guid"), o.get("display_id")
        r["other_type"], r["other_colour"] = o.get("entity_type"), o.get("colour")
        r["relationship_type_code"] = next((v.get("code") for v in verbs.values() if v["name"] == r["relationship_type"]), None)
    then_ids = {str(r["id"]) for r in then_rels}
    now_ids = {str(r["id"]) for r in now_detail["relationships"]}
    for r in then_rels:
        r["still_there"] = str(r["id"]) in now_ids
    added_since = [{k: r[k] for k in ("id", "relationship_type", "relationship_type_code", "verb", "direction", "other_name",
                                      "other_id", "other_display_id", "other_type", "other_colour")}
                   for r in now_detail["relationships"] if str(r["id"]) not in then_ids]
    versions = sorted({(r["changed_at"], r["id"]) for r in chrono})
    return {
        "entity": {k: e[k] for k in ("id", "display_id", "name", "entity_type", "model")},
        "as_of": {"event_id": point["id"], "at": point["changed_at"], "by": point["changed_by"],
                  "position": versions.index((point["changed_at"], point["id"])) + 1, "of": len(versions),
                  "is_current": point["id"] == chrono[-1]["id"]},
        "fields": fields, "attributes": attributes, "relationships": then_rels, "added_since": added_since,
        "moment": {"created": created_here, "changes": len(moment), "removed_relationships": removed_here},
    }


def _aware(d):
    import datetime as _dt
    return d if d.tzinfo else d.replace(tzinfo=_dt.UTC)


def _as_datetime(v):
    import datetime as _dt
    return _aware(v if isinstance(v, _dt.datetime) else _dt.datetime.fromisoformat(str(v)))


def get_entity_history(conn, model: Any, entity: Any, limit: int = 500) -> dict:
    """Every recorded change to an entity: the entity row itself, its attribute values and its
    relationships (from history.row_versions), newest first, each with what changed."""
    m = get_model(conn, model)
    e = _find_entity(conn, m, entity)
    eid = e["_id"]
    rows, names, attrs, verbs, attr_value = _history_rows(conn, m, eid)

    def entity_fields(d: dict) -> dict:
        out = {k: v for k, v in d.items() if k not in _NOISE and k != "entity_type_id"}
        if "parent_entity_id" in out:
            out["parent"] = names.get(int(out.pop("parent_entity_id") or 0))
        if "status_code" in out:
            out["status"] = out.pop("status_code")
        if "is_deleted" in out:
            out["deleted"] = "Yes" if out.pop("is_deleted") else None
        return out

    # the commit each change came in with (same transaction, D195): its number and message
    txs = list({r["tx"] for r in rows if r.get("tx") is not None})
    commits = {c["tx"]: c for c in _rows(conn, """SELECT k.tx, k.number, k.message, k.committed_by,
                                                            (SELECT array_agg(DISTINCT p.source) FROM core.pending_changes p
                                                              WHERE p.commit_id = k.id AND p.source IS NOT NULL) AS sources
                                                     FROM core.commits k
                                                     WHERE k.model_id = :m AND k.tx = ANY (CAST(:t AS bigint[]))""",
                                         m=m["_id"], t=txs)} if txs else {}
    events, previous = [], {}
    for r in rows:
        d, key = r["data"], (r["table_name"], r["row_id"])
        before = previous.get(key)
        previous[key] = d
        ev = {"id": r["id"], "at": r["changed_at"], "by": r["changed_by"], "operation": r["operation"],
              "version": r["row_version"], "label": r["label"], "changes": []}
        c = commits.get(r.get("tx"))
        if c:
            src = c.get("sources") or []
            if isinstance(src, str):   # a driver that answers arrays as text
                src = [x.strip('"') for x in src.strip("{}").split(",") if x]
            ev["commit"] = {"number": c["number"], "message": c["message"], "by": c["committed_by"], "sources": src}
        if r["table_name"] == "entities":
            ev["kind"], ev["item"] = "entity", d.get("name")
            new, old = entity_fields(d), entity_fields(before) if before else {}
            for field in new.keys() | old.keys():
                if new.get(field) != old.get(field) and not (new.get(field) in (None, "") and old.get(field) in (None, "")):
                    ev["changes"].append({"field": field.replace("_", " ").capitalize(),
                                          "old": None if old.get(field) is None else str(old.get(field)),
                                          "new": None if new.get(field) is None else str(new.get(field))})
        elif r["table_name"] == "attribute_values":
            ev["kind"] = "attribute"
            ev["item"] = attrs.get(int(d.get("attribute_type_id") or 0), "attribute")
            old_v = attr_value(before) if before and not before.get("is_deleted") else None
            new_v = None if d.get("is_deleted") or r["operation"] == "delete" else attr_value(d)
            if old_v != new_v:
                ev["changes"].append({"field": ev["item"], "old": old_v, "new": new_v})
        else:
            ev["kind"] = "relationship"
            rt = verbs.get(int(d.get("relationship_type_id") or 0), {"name": "?", "verb": "relates to"})
            outgoing = str(d.get("source_entity_id")) == str(eid)
            other = names.get(int(d["target_entity_id" if outgoing else "source_entity_id"]), "?")
            ev["item"] = f"{rt['verb']} {other}" if outgoing else f"{other} {rt['verb']} this"
            gone = d.get("is_deleted") or r["operation"] == "delete"
            was_gone = bool(before and before.get("is_deleted"))
            if before is None or was_gone != gone:
                ev["changes"].append({"field": rt["name"], "old": None if not before or was_gone else ev["item"],
                                      "new": None if gone else ev["item"]})
            elif before.get("status_code") != d.get("status_code"):
                ev["changes"].append({"field": "Status", "old": before.get("status_code"), "new": d.get("status_code")})
        # what kind of change each is, so the timeline can say it plainly (D110): a value set for the
        # first time is not a change of an old value
        for c in ev["changes"]:
            rel = ev["kind"] == "relationship" and c["field"] != "Status"
            if c["old"] in (None, "") and c["new"] not in (None, ""):
                c["action"] = "added" if rel else "set"
            elif c["new"] in (None, "") and c["old"] not in (None, ""):
                c["action"] = "removed" if rel else "cleared"
            else:
                c["action"] = "changed"
        if ev["kind"] == "entity" and r["operation"] == "insert":
            ev["action"] = "copied" if before is not None else "created"   # a deep copy's own first version
        if not ev["changes"] and ev["kind"] != "entity":
            continue      # a value or relationship written again unchanged (for example by a deep copy)
        events.append(ev)
    events.sort(key=lambda x: (x["at"], x["id"]), reverse=True)
    for k in ("_id", "_type", "_origin", "_type_origin"):
        e.pop(k)
    return {"entity": e, "events": events[:limit], "total": len(events)}


# ---------------------------------------------------------------- entity graph

def entity_graph(conn, model: Any, focus: Any = None, entity_types: list | None = None,
                 depth: int = 1, limit: int = 300, direction: str = "both",
                 relationship_types: list | None = None) -> dict:
    """Entities and the relationships between them, for drawing.

    focus:        an entity (guid, display ID or name): it and everything within `depth` steps (1-3)
    entity_types: or every entity of these types (guid, code or name) and the relationships among them
    neither:      the whole model
    Lines are the relationships plus the parent hierarchy (relationship_type_code "Parent").
    direction (with focus): both, out (follow lines from source to target: what this one leads to,
    uses or contains) or in (follow them backwards: what leads to, uses or contains this one), for
    impact and dependency chains; split: in and out together (in has negative distances); tree: the
    parent hierarchy only, every ancestor (negative distances) and parts down `depth` levels. relationship_types: only these (code, name or verb; "Parent" for
    the hierarchy). Each node carries its distance (steps) from the focus.
    At most `limit` entities; truncated is true when more would have been shown.
    """
    m = get_model(conn, model)
    mid = m["_id"]
    if direction == "tree":
        depth = max(1, min(int(depth or 4), 10))
    else:
        depth = max(1, min(int(depth or 1), 6 if direction in ("out", "in", "split") else 3))
    truncated = False
    wanted = [str(x) for x in (relationship_types or []) if str(x).strip()]
    with_parent = not wanted or any(x.lower() == "parent" for x in wanted)
    rel_ids = [_find_relationship_type(conn, mid, x)["_id"] for x in wanted if x.lower() != "parent"]
    rel_filter = "AND r.relationship_type_id = ANY (:rt)" if wanted else ""
    only_parent = False
    distance: dict[int, int] = {}

    def step_sql(way: str) -> str:
        if way == "out":
            sql = f"""SELECT r.target_entity_id AS o FROM core.relationships r
                       WHERE r.source_entity_id = ANY (:f) AND NOT r.is_deleted AND r.model_id = :m {rel_filter}"""
            if with_parent:
                sql += " UNION SELECT id FROM core.entities WHERE parent_entity_id = ANY (:f) AND NOT is_deleted"
        elif way == "in":
            sql = f"""SELECT r.source_entity_id AS o FROM core.relationships r
                       WHERE r.target_entity_id = ANY (:f) AND NOT r.is_deleted AND r.model_id = :m {rel_filter}"""
            if with_parent:
                sql += """ UNION SELECT parent_entity_id FROM core.entities
                           WHERE id = ANY (:f) AND parent_entity_id IS NOT NULL AND NOT is_deleted"""
        else:
            sql = f"""SELECT CASE WHEN r.source_entity_id = ANY (:f) THEN r.target_entity_id ELSE r.source_entity_id END AS o
                        FROM core.relationships r
                       WHERE (r.source_entity_id = ANY (:f) OR r.target_entity_id = ANY (:f)) AND NOT r.is_deleted
                         AND r.model_id = :m {rel_filter}"""
            if with_parent:
                sql += """ UNION SELECT parent_entity_id FROM core.entities
                            WHERE id = ANY (:f) AND parent_entity_id IS NOT NULL AND NOT is_deleted
                           UNION SELECT id FROM core.entities WHERE parent_entity_id = ANY (:f) AND NOT is_deleted"""
        return sql

    def walk(way: str, sign: int, ids: set) -> bool:
        """Breadth first from the focus; records each new entity's signed distance."""
        cut, frontier = False, {start}
        for d in range(1, depth + 1):
            nxt = {r["o"] for r in _rows(conn, step_sql(way), f=list(frontier), m=mid, rt=rel_ids)} - ids
            if len(ids) + len(nxt) > limit:
                nxt = set(sorted(nxt)[: max(0, limit - len(ids))])
                cut = True
            for i in nxt:
                distance[i] = sign * d
            ids |= nxt
            frontier = nxt
            if not frontier:
                break
        return cut

    if focus:
        start = _find_entity(conn, m, focus)["_id"]
        ids = {start}
        distance[start] = 0
        if direction == "split":       # what leads here on the left (negative), what it leads to on the right
            truncated = walk("out", 1, ids)
            truncated = walk("in", -1, ids) or truncated
        elif direction == "tree":      # every ancestor up to the top, parts down `depth` levels
            only_parent = True
            for r in _rows(conn, """
                WITH RECURSIVE up(id, lvl) AS (
                    SELECT parent_entity_id, -1 FROM core.entities WHERE id = :s AND parent_entity_id IS NOT NULL
                    UNION ALL
                    SELECT e.parent_entity_id, up.lvl - 1 FROM core.entities e JOIN up ON e.id = up.id
                     WHERE e.parent_entity_id IS NOT NULL AND up.lvl > -50)
                SELECT id, lvl FROM up""", s=start):
                distance[r["id"]] = r["lvl"]
            for r in _rows(conn, """
                WITH RECURSIVE down(id, lvl) AS (
                    SELECT id, 1 FROM core.entities WHERE parent_entity_id = :s AND NOT is_deleted
                    UNION ALL
                    SELECT e.id, down.lvl + 1 FROM core.entities e JOIN down ON e.parent_entity_id = down.id
                     WHERE NOT e.is_deleted AND down.lvl < :d)
                SELECT id, lvl FROM down ORDER BY lvl, id""", s=start, d=depth):
                if len(distance) >= limit:
                    truncated = True
                    break
                distance[r["id"]] = r["lvl"]
            ids = set(distance)
        else:
            truncated = walk(direction if direction in ("out", "in") else "both", 1, ids)
        where, params = "e.id = ANY (:ids)", {"ids": list(ids)}
    else:
        tids = [_find_type(conn, mid, t)["_id"] for t in (entity_types or [])]
        where, params = ("e.entity_type_id = ANY (:t)", {"t": tids}) if tids else ("TRUE", {})
        start = None
    nodes = _rows(conn, f"""
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, et.name AS entity_type, et.guid AS entity_type_id,
               l.name AS domain, l.colour, l.sort_order AS domain_order
          FROM core.entities e
          JOIN core.entity_types et ON et.id = e.entity_type_id
          JOIN core.layers l ON l.id = et.layer_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND {where}
         ORDER BY l.sort_order, et.sort_order, e.display_id
         LIMIT :n""", m=mid, n=limit + 1, **params)
    if len(nodes) > limit:
        nodes, truncated = nodes[:limit], True
    by_id = {n["_id"]: n for n in nodes}
    edges = _rows(conn, f"""
        SELECT r.guid AS id, s.guid AS source, t.guid AS target, rt.code AS relationship_type_code,
               rt.name AS relationship_type, rt.verb, {_ALLOWED_EXISTS} AS allowed
          FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id
          JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted {rel_filter} {"AND FALSE" if only_parent else ""}
           AND r.source_entity_id = ANY (:ids) AND r.target_entity_id = ANY (:ids)
        """ + ("""
        UNION ALL  -- the parent hierarchy (a capability and its sub-capabilities) as "part of" lines
        SELECT c.guid, p.guid, c.guid, 'Parent', 'Parent', 'contains', TRUE
          FROM core.entities c JOIN core.entities p ON p.id = c.parent_entity_id
         WHERE c.id = ANY (:ids) AND p.id = ANY (:ids) AND NOT c.is_deleted""" if with_parent else ""),
                  m=mid, ids=list(by_id), rt=rel_ids)
    for n in nodes:
        i = n.pop("_id")
        n["focus"] = i == start
        n["distance"] = distance.get(i)
    return {"model": m["name"], "nodes": nodes, "edges": edges, "truncated": truncated, "limit": limit,
            "direction": direction if focus else "both"}


def entity_paths(conn, model: Any, source: Any, target: Any, max_steps: int = 6, max_paths: int = 10,
                 relationship_types: list | None = None) -> dict:
    """The shortest chains connecting two entities, through relationships (either direction) and the
    parent hierarchy: at most `max_paths` chains, each of the fewest steps found (up to `max_steps`).
    Returns the entities and lines on those chains (graph form, distance = steps from the source) and
    the chains themselves as lists of entity guids."""
    m = get_model(conn, model)
    mid = m["_id"]
    s, t = _find_entity(conn, m, source), _find_entity(conn, m, target)
    sid, tid = s["_id"], t["_id"]
    max_steps = max(1, min(int(max_steps or 6), 8))
    wanted = [str(x) for x in (relationship_types or []) if str(x).strip()]
    with_parent = not wanted or any(x.lower() == "parent" for x in wanted)
    rel_ids = [_find_relationship_type(conn, mid, x)["_id"] for x in wanted if x.lower() != "parent"]
    rel_filter = "AND r.relationship_type_id = ANY (:rt)" if wanted else ""
    step = f"""SELECT r.source_entity_id AS a, r.target_entity_id AS b FROM core.relationships r
                WHERE (r.source_entity_id = ANY (:f) OR r.target_entity_id = ANY (:f)) AND NOT r.is_deleted
                  AND r.model_id = :m {rel_filter}"""
    if with_parent:
        step += """ UNION SELECT id, parent_entity_id FROM core.entities
                     WHERE (id = ANY (:f) OR parent_entity_id = ANY (:f)) AND parent_entity_id IS NOT NULL AND NOT is_deleted"""
    preds: dict[int, set] = {sid: set()}
    level, frontier, found = {sid: 0}, {sid}, sid == tid
    for d in range(1, max_steps + 1):
        if found or not frontier:
            break
        nxt: set[int] = set()
        for r in _rows(conn, step, f=list(frontier), m=mid, rt=rel_ids):
            for here, there in ((r["a"], r["b"]), (r["b"], r["a"])):
                if here in frontier and (level.get(there) is None or level[there] == d):
                    level[there] = d
                    preds.setdefault(there, set()).add(here)
                    nxt.add(there)
        frontier = nxt
        found = tid in level
        if len(level) > 20000:
            break
    paths: list[list[int]] = []
    if found:
        def back(node, tail):
            if len(paths) >= max_paths:
                return
            if node == sid:
                paths.append([sid] + tail)
                return
            for p in sorted(preds.get(node, ())):
                back(p, [node] + tail)
        back(tid, []) if tid != sid else paths.append([sid])
    on_path = {i for p in paths for i in p}
    nodes = _rows(conn, """
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, et.name AS entity_type, et.guid AS entity_type_id,
               l.name AS domain, l.colour, l.sort_order AS domain_order
          FROM core.entities e JOIN core.entity_types et ON et.id = e.entity_type_id JOIN core.layers l ON l.id = et.layer_id
         WHERE e.id = ANY (:ids)""", ids=list(on_path or {sid, tid}))
    guid = {n["_id"]: n["id"] for n in nodes}
    for n in nodes:
        n["distance"] = level.get(n["_id"])
        n["focus"] = n["_id"] == sid
        n["target"] = n["_id"] == tid
    pairs = {frozenset((p[i], p[i + 1])) for p in paths for i in range(len(p) - 1)}
    edges = [e for e in _rows(conn, f"""
        SELECT r.guid AS id, r.source_entity_id AS _s, r.target_entity_id AS _t, s.guid AS source, t.guid AS target,
               rt.code AS relationship_type_code, rt.name AS relationship_type, rt.verb, {_ALLOWED_EXISTS} AS allowed
          FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id
          JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted {rel_filter}
           AND r.source_entity_id = ANY (:ids) AND r.target_entity_id = ANY (:ids)""",
        m=mid, ids=list(on_path), rt=rel_ids) if frozenset((e["_s"], e["_t"])) in pairs]
    if with_parent:
        edges += [e for e in _rows(conn, """
            SELECT c.guid AS id, c.parent_entity_id AS _s, c.id AS _t, p.guid AS source, c.guid AS target,
                   'Parent' AS relationship_type_code, 'Parent' AS relationship_type, 'contains' AS verb, TRUE AS allowed
              FROM core.entities c JOIN core.entities p ON p.id = c.parent_entity_id
             WHERE c.id = ANY (:ids) AND p.id = ANY (:ids) AND NOT c.is_deleted""", ids=list(on_path))
            if frozenset((e["_s"], e["_t"])) in pairs]
    for e in edges:
        e.pop("_s"), e.pop("_t")
    for n in nodes:
        n.pop("_id")
    return {"model": m["name"], "nodes": nodes, "edges": edges, "truncated": len(paths) >= max_paths,
            "limit": max_paths, "direction": "path", "found": found,
            "steps": (len(paths[0]) - 1) if paths else None,
            "paths": [[guid[i] for i in p] for p in paths],
            "source": {"id": s["id"], "name": s["name"]}, "target": {"id": t["id"], "name": t["name"]}}


# ---------------------------------------------------------------- metamodel versions and history (phase 3)

MM_TABLES = ["layers", "entity_types", "relationship_types", "pick_lists", "pick_list_values", "attribute_types",
             "item_attributes", "validation_rules", "allowed_relationships"]
MM_KIND = {"layers": "domain", "entity_types": "entity type", "relationship_types": "relationship type",
           "pick_lists": "pick list", "pick_list_values": "pick-list value", "attribute_types": "attribute definition",
           "item_attributes": "attribute", "validation_rules": "rule", "allowed_relationships": "mapping"}
_MM_NOISE = _NOISE | {"sort_order", "table_name", "column_name"}
_VERSION_OF_ROW = """coalesce(substring(h.label from '^metamodel v([0-9]+)')::int,
                               core.metamodel_version_at(h.model_id, h.changed_at))"""


def metamodel_versions(conn, model: Any) -> list[dict]:
    """The published versions of a model's metamodel, newest first, with how many changes each made."""
    m = get_model(conn, model)
    return _rows(conn, f"""
        SELECT v.version, v.note, v.changed_at, v.changed_by, v.guid AS id,
               (SELECT count(*) FROM history.row_versions h
                 WHERE h.model_id = v.model_id AND h.table_name = ANY (:t) AND {_VERSION_OF_ROW} = v.version) AS changes
          FROM core.metamodel_versions v WHERE v.model_id = :m ORDER BY v.version DESC""", m=m["_id"], t=MM_TABLES)


def _mm_names(conn, model_id: int) -> dict:
    """Names for the ids that appear in metamodel history rows (including retired and removed rows)."""
    def pairs(sql):
        return {r["id"]: r for r in _rows(conn, sql, m=model_id)}
    return {
        "layers": pairs("SELECT id, name FROM core.layers WHERE model_id = :m"),
        "entity_types": pairs("SELECT id, name FROM core.entity_types WHERE model_id = :m"),
        "relationship_types": pairs("SELECT id, name, verb FROM core.relationship_types WHERE model_id = :m"),
        "attribute_types": pairs("SELECT id, name FROM core.attribute_types WHERE model_id = :m"),
        "pick_lists": pairs("SELECT id, name FROM core.pick_lists WHERE model_id = :m"),
    }


def _mm_item(table: str, d: dict, names: dict) -> str:
    n = lambda kind, i: (names[kind].get(int(i)) or {}).get("name", "?") if i else ""
    if table == "item_attributes":
        owner = n("entity_types", d.get("entity_type_id")) or n("relationship_types", d.get("relationship_type_id"))
        return f"{n('attribute_types', d.get('attribute_type_id'))} on {owner}"
    if table == "allowed_relationships":
        rt = names["relationship_types"].get(int(d.get("relationship_type_id") or 0)) or {}
        return f"{n('entity_types', d.get('source_type_id'))} {rt.get('verb', '?')} {n('entity_types', d.get('target_type_id'))}"
    if table == "validation_rules":
        return d.get("message") or d.get("rule_type_code") or "rule"
    if table == "pick_list_values":
        return f"{d.get('value')} in {n('pick_lists', d.get('pick_list_id'))}"
    return d.get("name") or d.get("code") or "?"


def _mm_fields(table: str, d: dict, names: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k in _MM_NOISE or k in ("model_id",):
            continue
        if k.endswith("_id") and v is not None and k != "id":
            kind = {"layer_id": "layers", "entity_type_id": "entity_types", "relationship_type_id": "relationship_types",
                    "attribute_type_id": "attribute_types", "pick_list_id": "pick_lists", "source_type_id": "entity_types",
                    "target_type_id": "entity_types"}.get(k)
            if kind:
                v = (names[kind].get(int(v)) or {}).get("name", v)
            k = "domain" if k == "layer_id" else k[:-3]
        if k == "status_code":
            k = "status"
        if k == "is_deleted":
            k, v = "removed", ("yes" if v else None)
        out[k] = v
    return out


def _mm_change(table: str, op: str, before: dict | None, d: dict, names: dict) -> dict:
    new, old = _mm_fields(table, d, names), (_mm_fields(table, before, names) if before else {})
    if before is None or op == "insert":
        what = "added"
    elif new.get("removed") and not old.get("removed"):
        what = "removed"
    elif new.get("status") == "retired" and old.get("status") != "retired":
        what = "retired"
    elif old.get("removed") and not new.get("removed"):
        what = "restored"
    else:
        what = "changed"
    fields = []
    if what == "changed" or what == "added":
        for k in new.keys() | old.keys():
            if k in ("removed",):
                continue
            a, b = old.get(k), new.get(k)
            if what == "added":
                if b not in (None, "", False):
                    fields.append({"field": k.replace("_", " "), "old": None, "new": str(b)})
            elif a != b and not (a in (None, "") and b in (None, "")):
                fields.append({"field": k.replace("_", " "), "old": None if a is None else str(a), "new": None if b is None else str(b)})
    return {"kind": MM_KIND[table], "table": table, "item": _mm_item(table, d, names), "change": what,
            "fields": sorted(fields, key=lambda f: f["field"])}


def metamodel_history(conn, model: Any, per_version: int = 300) -> dict:
    """Every change to a model's metamodel, grouped by the version it was published in (newest first):
    what changed (kind, item, added/changed/retired/removed, old and new values), who and when. The
    first version (the metamodel the model started with) is summarised by counts."""
    m = get_model(conn, model)
    mid = m["_id"]
    versions = {v["version"]: {**v, "items": [], "counts": {}} for v in metamodel_versions(conn, m["id"])}
    rows = _rows(conn, f"""
        SELECT h.id, h.table_name, h.row_id, h.row_version, h.operation, h.data, h.changed_at, h.changed_by,
               {_VERSION_OF_ROW} AS version
          FROM history.row_versions h
         WHERE h.model_id = :m AND h.table_name = ANY (:t)
         ORDER BY h.table_name, h.row_id, h.row_version, h.id""", m=mid, t=MM_TABLES)
    names = _mm_names(conn, mid)
    previous: dict[tuple, dict] = {}
    for r in rows:
        key = (r["table_name"], r["row_id"])
        before = previous.get(key)
        previous[key] = r["data"]
        v = versions.setdefault(r["version"], {"version": r["version"], "note": "", "changed_at": r["changed_at"],
                                               "changed_by": r["changed_by"], "items": [], "counts": {}})
        kind = MM_KIND[r["table_name"]]
        v["counts"][kind] = v["counts"].get(kind, 0) + 1
        if r["version"] == 1 or len(v["items"]) >= per_version:
            continue
        ch = _mm_change(r["table_name"], r["operation"], before, r["data"], names)
        ch.update({"at": r["changed_at"], "by": r["changed_by"], "history_id": r["id"]})
        v["items"].append(ch)
    out = sorted(versions.values(), key=lambda v: v["version"], reverse=True)
    for v in out:
        v["counts"] = [{"kind": k, "count": n} for k, n in sorted(v["counts"].items())]
    return {"model": m["name"], "current_version": m["metamodel_version"], "versions": out}


def _mm_state(conn, model_id: int, version: int) -> dict[tuple, dict]:
    """Every metamodel row as it was at the end of a version: (table, row id) -> data."""
    return {(r["table_name"], r["row_id"]): r["data"] for r in _rows(conn, f"""
        SELECT DISTINCT ON (h.table_name, h.row_id) h.table_name, h.row_id, h.data
          FROM history.row_versions h
         WHERE h.model_id = :m AND h.table_name = ANY (:t) AND {_VERSION_OF_ROW} <= :v
         ORDER BY h.table_name, h.row_id, h.row_version DESC, h.id DESC""", m=model_id, t=MM_TABLES, v=version)}


def metamodel_compare(conn, model: Any, from_version: int, to_version: int | None = None) -> dict:
    """What differs between two versions of a model's metamodel (to_version: the current one when
    left out): items added, removed, retired and changed, with their old and new values."""
    m = get_model(conn, model)
    mid = m["_id"]
    to_version = int(to_version or m["metamodel_version"])
    from_version = int(from_version)
    for v in (from_version, to_version):
        if not 1 <= v <= m["metamodel_version"]:
            raise NotFound(f"Version {v} does not exist (the metamodel is at version {m['metamodel_version']}).")
    a, b = _mm_state(conn, mid, from_version), _mm_state(conn, mid, to_version)
    names = _mm_names(conn, mid)
    gone = lambda d: d is None or d.get("is_deleted")
    items = []
    for key in set(a) | set(b):
        da, db = a.get(key), b.get(key)
        table = key[0]
        if gone(da) and gone(db):
            continue
        if gone(da):
            ch = {"kind": MM_KIND[table], "table": table, "item": _mm_item(table, db, names), "change": "added",
                  "fields": _mm_change(table, "insert", None, db, names)["fields"]}
        elif gone(db):
            ch = {"kind": MM_KIND[table], "table": table, "item": _mm_item(table, da, names), "change": "removed", "fields": []}
        else:
            ch = _mm_change(table, "update", da, db, names)
            if ch["change"] == "changed" and not ch["fields"]:
                continue
        items.append(ch)
    order = list(MM_KIND.values())
    items.sort(key=lambda c: (order.index(c["kind"]), c["item"], c["change"]))
    summary = {}
    for c in items:
        summary.setdefault(c["kind"], {}).setdefault(c["change"], 0)
        summary[c["kind"]][c["change"]] += 1
    return {"model": m["name"], "from_version": from_version, "to_version": to_version, "items": items,
            "summary": [{"kind": k, **v} for k, v in summary.items()]}


def list_pick_lists(conn, model: Any) -> list[dict]:
    """The model's pick lists with their values (retired values marked)."""
    m = get_model(conn, model)
    lists = _rows(conn, """SELECT id AS _id, guid AS id, code, name, description FROM core.pick_lists
                            WHERE model_id = :m AND NOT is_deleted ORDER BY name""", m=m["_id"])
    values = _rows(conn, """SELECT pick_list_id AS _p, guid AS id, value, status_code AS status FROM core.pick_list_values
                             WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, value""", m=m["_id"])
    for pl in lists:
        pl["values"] = [{k: v for k, v in x.items() if k != "_p"} for x in values if x["_p"] == pl["_id"]]
        del pl["_id"]
    return lists


def failing_checks(conn, model: Any, entity_type: Any = None) -> dict:
    """Every entity of a model that fails a check: rule results (missing mandatory values, values out
    of range, patterns, duplicates...) and relationships outside the metamodel, one row per failure,
    with the entity's metamodel versions, plus counts by type, rule and severity."""
    m = get_model(conn, model)
    types = [_find_type(conn, m["_id"], entity_type)["id"]] if entity_type else [
        r["guid"] for r in _rows(conn, """SELECT DISTINCT et.guid, et.sort_order FROM core.entities e
             JOIN core.entity_types et ON et.id = e.entity_type_id
            WHERE e.model_id = :m AND NOT e.is_deleted ORDER BY et.sort_order""", m=m["_id"])]
    rows = []
    for t in types:
        table = type_table(conn, m["id"], t)
        et = table["entity_type"]
        for r in table["rows"]:
            for c in r["checks"]:
                rows.append({"entity_id": r["id"], "display_id": r["display_id"], "name": r["name"],
                             "entity_type": et["name"], "entity_type_id": et["id"], "colour": et["colour"],
                             "rule": c["rule"], "field": c["field"], "code": c.get("code"), "severity": c["severity"],
                             "message": c["message"], "created_mm_version": r["created_mm_version"], "modified_mm_version": r["modified_mm_version"]})
    for r in list_relationships(conn, m["id"]):
        if r["allowed"]:
            continue
        rows.append({"entity_id": r["source_id"], "display_id": r["source_display_id"], "name": r["source_name"],
                     "entity_type": r["source_type"], "entity_type_id": None, "colour": r["source_colour"],
                     "rule": "outside_metamodel", "field": "Relationship", "severity": "warning",
                     "message": f"{r['source_name']} {r['verb']} {r['target_name']}: no mapping allows {r['relationship_type']} "
                                f"from {r['source_type']} to {r['target_type']}",
                     "created_mm_version": None, "modified_mm_version": None})
    count = lambda key: [{"name": k, "count": v} for k, v in sorted(
        {x[key]: sum(1 for y in rows if y[key] == x[key]) for x in rows}.items(), key=lambda kv: -kv[1])]
    return {"model": m["name"], "metamodel_version": m["metamodel_version"], "rows": rows,
            "entities": len({r["entity_id"] for r in rows}), "failures": len(rows),
            "by_type": count("entity_type"), "by_rule": count("rule"), "by_severity": count("severity")}
