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
           p.guid AS parent_model_id, p.name AS parent_model_name, m.metamodel_name,
           m.metamodel_version, m.is_locked, m.status_code AS status,
           (SELECT count(*) FROM core.entity_type t WHERE t.model_id = m.id AND NOT t.is_deleted) AS entity_type_count,
           (SELECT count(*) FROM core.entity e WHERE e.model_id = m.id AND NOT e.is_deleted) AS entity_count,
           (SELECT count(*) FROM core.relationship r WHERE r.model_id = m.id AND NOT r.is_deleted) AS relationship_count
      FROM core.model m
      JOIN core.model_kind k ON k.code = m.kind_code
      LEFT JOIN core.model p ON p.id = m.parent_model_id
     WHERE NOT m.is_deleted AND core.can_read_model(m.id)"""


def list_models(conn) -> list[dict]:
    """Every readable model: templates first, then reference models, projects, work copies."""
    return _rows(conn, _MODEL_SQL + """
     ORDER BY CASE m.kind_code WHEN 'template' THEN 1 WHEN 'reference' THEN 2
              WHEN 'project' THEN 3 ELSE 4 END, m.name""")


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
    """Layers with their entity types, and the relationship types."""
    m = get_model(conn, model)
    mid = m["_id"]
    layers = _rows(conn, """
        SELECT guid AS id, code, name, description, colour FROM core.layer
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    types = _rows(conn, """
        SELECT et.guid AS id, l.guid AS layer_id, et.code, et.name, et.description, et.aspect, et.id_prefix,
               et.table_name, et.status_code AS status,
               (SELECT count(*) FROM core.item_attribute ia
                 WHERE ia.entity_type_id = et.id AND NOT ia.is_deleted) AS attribute_count,
               (SELECT count(*) FROM core.entity e
                 WHERE e.entity_type_id = et.id AND NOT e.is_deleted) AS entity_count
          FROM core.entity_type et
          JOIN core.layer l ON l.id = et.layer_id
         WHERE et.model_id = :m AND NOT et.is_deleted ORDER BY et.sort_order, et.name""", m=mid)
    rel_types = _rows(conn, """
        SELECT guid AS id, code, name, verb, category, is_directed, description FROM core.relationship_type
         WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=mid)
    for layer in layers:
        layer["entity_types"] = [t for t in types if t["layer_id"] == layer["id"]]
    return {"model": m, "layers": layers, "relationship_types": rel_types}


def _find_type(conn, model_id: int, entity_type: Any) -> dict:
    """An entity type of a model by guid, or by name, code or table name (case-insensitive)."""
    guid = _as_guid(entity_type)
    where = "et.guid = :t" if guid else "lower(:t) IN (lower(et.code), lower(et.name), lower(et.table_name))"
    rows = _rows(conn, f"""
        SELECT et.id AS _id, et.guid AS id, et.code, et.name, et.description, et.aspect, et.id_prefix,
               et.table_name, l.name AS layer, l.colour
          FROM core.entity_type et JOIN core.layer l ON l.id = et.layer_id
         WHERE {where} AND et.model_id = :m AND NOT et.is_deleted""", t=guid or str(entity_type), m=model_id)
    if not rows:
        raise NotFound(f"No entity type {entity_type!r} in this model.")
    return rows[0]


_ALLOWED_SQL = """
    SELECT rt.name AS relationship_type, rt.verb, o.guid AS other_type_id, o.name AS other_type, ar.note
      FROM core.allowed_relationship ar
      JOIN core.relationship_type rt ON rt.id = ar.relationship_type_id
      JOIN core.entity_type o ON o.id = ar.{other}
     WHERE ar.{this} = :t AND NOT ar.is_deleted
     ORDER BY rt.sort_order, o.sort_order"""


def get_entity_type(conn, model: Any, entity_type: Any) -> dict:
    """One entity type with its attributes, validation rules and allowed relationships."""
    mid = get_model(conn, model)["_id"]
    et = _find_type(conn, mid, entity_type)
    tid = et["_id"]
    et["attributes"] = _rows(conn, """
        SELECT at.code, at.name, at.description, at.column_name, at.data_type_code AS data_type,
               dt.name AS data_type_name, at.unit, ia.is_required, ia.section,
               pl.name AS pick_list,
               coalesce((SELECT array_agg(v.value ORDER BY v.sort_order) FROM core.pick_list_value v
                          WHERE v.pick_list_id = at.pick_list_id AND NOT v.is_deleted),
                        ARRAY[]::text[]) AS pick_list_values
          FROM core.item_attribute ia
          JOIN core.attribute_type at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
          JOIN core.data_type dt ON dt.code = at.data_type_code
          LEFT JOIN core.pick_list pl ON pl.id = at.pick_list_id
         WHERE ia.entity_type_id = :t AND NOT ia.is_deleted
         ORDER BY ia.sort_order, at.name""", t=tid)
    et["rules"] = _rows(conn, """
        SELECT coalesce(at.name, initcap(vr.field_name)) AS field, rt.name AS rule,
               vr.param1, vr.param2, vr.severity, vr.message
          FROM core.validation_rule vr
          JOIN core.rule_type rt ON rt.code = vr.rule_type_code
          LEFT JOIN core.attribute_type at ON at.id = vr.attribute_type_id
         WHERE vr.model_id = :m AND NOT vr.is_deleted
           AND (vr.entity_type_id IS NULL OR vr.entity_type_id = :t)
           AND (vr.field_name IS NOT NULL OR vr.attribute_type_id IN (
                SELECT attribute_type_id FROM core.item_attribute
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
        SELECT rt.name AS relationship_type, rt.verb, rt.category, rt.description, ar.note
          FROM core.allowed_relationship ar
          JOIN core.relationship_type rt ON rt.id = ar.relationship_type_id
         WHERE ar.source_type_id = :s AND ar.target_type_id = :t AND NOT ar.is_deleted
         ORDER BY rt.sort_order""", s=src["_id"], t=tgt["_id"])


# ---------------------------------------------------------------- content

def get_entities(conn, model: Any, entity_type: str, name: str | None = None, limit: int = 500,
                 actor: str = "unknown") -> dict:
    """Entities of one type through eax.get_entity (or get_entity_by_name), with relationships.

    Uses temporary tables, so the connection must be inside a transaction (engine.begin()).
    """
    m = get_model(conn, model)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": actor})
    try:
        if name:
            tables = conn.execute(text("SELECT eax.get_entity_by_name(:t, :n, CAST(:m AS uuid))"),
                                  {"t": entity_type, "n": name, "m": str(m["id"])}).scalar_one()
        else:
            tables = conn.execute(text("SELECT eax.get_entity(:t, CAST(:m AS uuid))"),
                                  {"t": entity_type, "m": str(m["id"])}).scalar_one()
    except DBAPIError as exc:
        diag = getattr(exc.orig, "diag", None)
        raise NotFound(getattr(diag, "message_primary", None) or str(exc.orig)) from exc
    entity_table, rel_table = tables[0], tables[1]
    result = conn.execute(text(f'SELECT * FROM pg_temp."{entity_table}" LIMIT :n'), {"n": limit})
    columns = list(result.keys())
    rows = [dict(r) for r in result.mappings().all()]
    ids = [r["id"] for r in rows]
    rels = _rows(conn, f'SELECT * FROM pg_temp."{rel_table}" WHERE entity_id = ANY (:ids)', ids=ids)
    # temporary tables: drop them so a pooled connection stays clean
    conn.execute(text(f'DROP TABLE pg_temp."{entity_table}", pg_temp."{rel_table}"'))
    return {"model": m["name"], "entity_table": entity_table, "relationship_table": rel_table,
            "columns": columns, "rows": rows, "relationships": rels}


def search_entities(conn, text_query: str, model: Any = None, limit: int = 50) -> list[dict]:
    """Entities whose name, display ID or description contains the text, in one or every readable model."""
    mid = get_model(conn, model)["_id"] if model else None
    return _rows(conn, """
        SELECT e.guid AS id, e.display_id, e.name, et.name AS entity_type, m.name AS model,
               m.guid AS model_id, left(e.description, 200) AS description
          FROM core.entity e
          JOIN core.entity_type et ON et.id = e.entity_type_id
          JOIN core.model m ON m.id = e.model_id
         WHERE NOT e.is_deleted AND NOT m.is_deleted AND core.can_read_model(m.id)
           AND (CAST(:m AS bigint) IS NULL OR e.model_id = :m)
           AND (e.name ILIKE :q OR e.display_id ILIKE :q OR e.description ILIKE :q)
         ORDER BY (lower(e.name) = lower(:exact)) DESC, e.name
         LIMIT :n""", m=mid, q=f"%{text_query}%", exact=text_query, n=limit)


def list_entities(conn, model: Any, entity_type: Any = None, limit: int = 2000) -> list[dict]:
    """Every entity of a model (or of one type), with its type, layer and relationship count."""
    m = get_model(conn, model)
    tid = _find_type(conn, m["_id"], entity_type)["_id"] if entity_type else None
    return _rows(conn, """
        SELECT e.guid AS id, e.display_id, e.name, left(e.description, 300) AS description,
               et.name AS entity_type, et.guid AS entity_type_id, l.name AS layer, l.colour,
               pe.name AS parent_name, e.status_code AS status,
               (SELECT count(*) FROM core.relationship r
                 WHERE (r.source_entity_id = e.id OR r.target_entity_id = e.id) AND NOT r.is_deleted) AS relationship_count,
               e.modified_at, e.modified_by
          FROM core.entity e
          JOIN core.entity_type et ON et.id = e.entity_type_id
          JOIN core.layer l ON l.id = et.layer_id
          LEFT JOIN core.entity pe ON pe.id = e.parent_entity_id
         WHERE e.model_id = :m AND NOT e.is_deleted
           AND (CAST(:t AS bigint) IS NULL OR e.entity_type_id = :t)
         ORDER BY l.sort_order, et.sort_order, e.name
         LIMIT :n""", m=m["_id"], t=tid, n=limit)


def list_relationships(conn, model: Any, limit: int = 5000) -> list[dict]:
    """Every relationship of a model: source, relationship type, target."""
    m = get_model(conn, model)
    return _rows(conn, """
        SELECT r.guid AS id, rt.name AS relationship_type, rt.verb,
               s.guid AS source_id, s.display_id AS source_display_id, s.name AS source_name,
               st.name AS source_type,
               t.guid AS target_id, t.display_id AS target_display_id, t.name AS target_name,
               tt.name AS target_type, r.name, r.status_code AS status
          FROM core.relationship r
          JOIN core.relationship_type rt ON rt.id = r.relationship_type_id
          JOIN core.entity s ON s.id = r.source_entity_id
          JOIN core.entity_type st ON st.id = s.entity_type_id
          JOIN core.entity t ON t.id = r.target_entity_id
          JOIN core.entity_type tt ON tt.id = t.entity_type_id
         WHERE r.model_id = :m AND NOT r.is_deleted
         ORDER BY rt.sort_order, s.name, t.name
         LIMIT :n""", m=m["_id"], n=limit)


def get_entity_detail(conn, model: Any, entity: Any) -> dict:
    """One entity (by guid, display ID or name) with its attributes, relationships, parent and children."""
    m = get_model(conn, model)
    guid = _as_guid(entity)
    where = "e.guid = :e" if guid else "(lower(e.name) = lower(:e) OR lower(e.display_id) = lower(:e))"
    found = _rows(conn, f"""
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, e.description, e.status_code AS status,
               et.name AS entity_type, et.guid AS entity_type_id, l.name AS layer, l.colour,
               pe.guid AS parent_id, pe.name AS parent_name,
               e.created_at, e.created_by, e.modified_at, e.modified_by, e.row_version
          FROM core.entity e
          JOIN core.entity_type et ON et.id = e.entity_type_id
          JOIN core.layer l ON l.id = et.layer_id
          LEFT JOIN core.entity pe ON pe.id = e.parent_entity_id
         WHERE {where} AND e.model_id = :m AND NOT e.is_deleted
         ORDER BY e.display_id LIMIT 1""", e=guid or str(entity), m=m["_id"])
    if not found:
        raise NotFound(f"No entity {entity!r} in model {m['name']!r}.")
    e = found[0]
    eid = e["_id"]
    # every attribute of the type, with the entity's value where it has one
    e["attributes"] = _rows(conn, """
        SELECT at.code, at.name, ia.section, at.data_type_code AS data_type, at.unit, ia.is_required,
               coalesce(av.value_text, av.value_number::text, av.value_date::text,
                        av.value_bool::text, re.name) AS value
          FROM core.entity e
          JOIN core.item_attribute ia ON ia.entity_type_id = e.entity_type_id AND NOT ia.is_deleted
          JOIN core.attribute_type at ON at.id = ia.attribute_type_id
          LEFT JOIN core.attribute_value av
                 ON av.entity_id = e.id AND av.attribute_type_id = at.id AND NOT av.is_deleted
          LEFT JOIN core.entity re ON re.id = av.value_ref
         WHERE e.id = :e
         ORDER BY ia.sort_order, at.name""", e=eid)
    e["relationships"] = _rows(conn, """
        SELECT r.guid AS id, rt.name AS relationship_type, rt.verb,
               CASE WHEN r.source_entity_id = :e THEN 'outgoing' ELSE 'incoming' END AS direction,
               o.guid AS other_id, o.display_id AS other_display_id, o.name AS other_name,
               ot.name AS other_type, ol.colour AS other_colour
          FROM core.relationship r
          JOIN core.relationship_type rt ON rt.id = r.relationship_type_id
          JOIN core.entity o ON o.id = CASE WHEN r.source_entity_id = :e THEN r.target_entity_id
                                            ELSE r.source_entity_id END
          JOIN core.entity_type ot ON ot.id = o.entity_type_id
          JOIN core.layer ol ON ol.id = ot.layer_id
         WHERE (r.source_entity_id = :e OR r.target_entity_id = :e) AND NOT r.is_deleted AND NOT o.is_deleted
         ORDER BY 4 DESC, rt.sort_order, o.name""", e=eid)
    e["children"] = _rows(conn, """
        SELECT c.guid AS id, c.display_id, c.name FROM core.entity c
         WHERE c.parent_entity_id = :e AND NOT c.is_deleted ORDER BY c.name""", e=eid)
    return e
