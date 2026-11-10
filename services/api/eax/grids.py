"""Grids (build phase 7): spreadsheet-style views of a model's metamodel, read here and saved through
eax.metamodel_edit.apply_many as one metamodel version (Model Admins, D89). The content grids (entities,
relationships) are in eax.content. Every grid answers its rows and the choices its drop-down cells offer.
"""

from __future__ import annotations

from typing import Any

from . import repository as repo
from .metamodel_edit import EditError

KINDS = ("entity_types", "relationship_types", "attributes", "mappings", "pick_list_values", "rules")


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def metamodel_grid(conn, model: Any, kind: str) -> dict:
    if kind not in KINDS:
        raise EditError(f"Unknown grid {kind!r}. Known: {', '.join(KINDS)}.", 404)
    m = repo.get_model(conn, model)
    mid = m["_id"]
    choices = {
        "domains": [r["name"] for r in _rows(conn, "SELECT name FROM core.layers WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order", m=mid)],
        "entity_types": [r["name"] for r in _rows(conn, """SELECT name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted
                                                              AND NOT is_connector
                                                            ORDER BY name""", m=mid)],
        "relationship_types": [r["name"] for r in _rows(conn, """SELECT name FROM core.relationship_types WHERE model_id = :m
                                                                  AND NOT is_deleted ORDER BY sort_order, name""", m=mid)],
        "data_types": [r["code"] for r in _rows(conn, "SELECT code FROM core.data_types ORDER BY sort_order")],
        "pick_lists": [r["name"] for r in _rows(conn, "SELECT name FROM core.pick_lists WHERE model_id = :m AND NOT is_deleted ORDER BY name", m=mid)],
        "pick_list_ids": {r["name"]: str(r["guid"]) for r in _rows(conn, "SELECT name, guid FROM core.pick_lists WHERE model_id = :m AND NOT is_deleted", m=mid)},
        "rule_types": [r["code"] for r in _rows(conn, "SELECT code FROM core.rule_types ORDER BY code")],
        "severities": ["error", "warning"],
        "statuses": ["published", "retired"],
    }
    if kind == "entity_types":
        rows = _rows(conn, """
            SELECT t.guid AS id, t.name, t.code, l.name AS domain, t.id_prefix, t.aspect, t.description, t.status_code AS status,
                   (SELECT count(*) FROM core.entities e WHERE e.entity_type_id = t.id AND NOT e.is_deleted) AS entities
              FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
             WHERE t.model_id = :m AND NOT t.is_deleted ORDER BY l.sort_order, t.sort_order, t.name""", m=mid)
    elif kind == "relationship_types":
        rows = _rows(conn, """
            SELECT r.guid AS id, r.name, r.code, r.verb, r.category, r.is_directed, r.description, r.status_code AS status,
                   (SELECT count(*) FROM core.relationships x WHERE x.relationship_type_id = r.id AND NOT x.is_deleted) AS relationships
              FROM core.relationship_types r WHERE r.model_id = :m AND NOT r.is_deleted ORDER BY r.sort_order, r.name""", m=mid)
    elif kind == "attributes":
        rows = _rows(conn, """
            SELECT ia.guid AS id, coalesce(t.name, '(relationship) ' || rt.name) AS entity_type, a.name, a.code,
                   a.data_type_code AS data_type, pl.name AS pick_list, ia.is_required, ia.section, a.unit, a.description,
                   ia.default_value
              FROM core.item_attributes ia JOIN core.attribute_types a ON a.id = ia.attribute_type_id
              LEFT JOIN core.entity_types t ON t.id = ia.entity_type_id
              LEFT JOIN core.relationship_types rt ON rt.id = ia.relationship_type_id
              LEFT JOIN core.pick_lists pl ON pl.id = a.pick_list_id
             WHERE ia.model_id = :m AND NOT ia.is_deleted AND NOT a.is_deleted
             ORDER BY t.name NULLS LAST, ia.sort_order, a.name""", m=mid)
    elif kind == "mappings":
        rows = _rows(conn, """
            SELECT ar.guid AS id, rt.name AS relationship_type, s.name AS source_type, t.name AS target_type,
                   ar.source_multiplicity, ar.target_multiplicity, ar.note, ar.from_content
              FROM core.allowed_relationships ar JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
              JOIN core.entity_types s ON s.id = ar.source_type_id JOIN core.entity_types t ON t.id = ar.target_type_id
             WHERE ar.model_id = :m AND NOT ar.is_deleted ORDER BY rt.sort_order, s.name, t.name""", m=mid)
    elif kind == "pick_list_values":
        rows = _rows(conn, """
            SELECT v.guid AS id, pl.name AS pick_list, v.value, v.status_code AS status
              FROM core.pick_list_values v JOIN core.pick_lists pl ON pl.id = v.pick_list_id
             WHERE v.model_id = :m AND NOT v.is_deleted ORDER BY pl.name, v.sort_order, v.value""", m=mid)
    else:
        rows = _rows(conn, """
            SELECT vr.guid AS id, coalesce(t.name, '(every type)') AS entity_type,
                   coalesce(a.name, vr.field_name) AS field, vr.rule_type_code AS rule_type, vr.param1, vr.param2,
                   vr.severity, vr.message
              FROM core.validation_rules vr LEFT JOIN core.entity_types t ON t.id = vr.entity_type_id
              LEFT JOIN core.attribute_types a ON a.id = vr.attribute_type_id
             WHERE vr.model_id = :m AND NOT vr.is_deleted ORDER BY t.name NULLS FIRST, vr.sort_order""", m=mid)
        choices["fields"] = ["name", "description", "display_id", "relationships"] + [
            r["name"] for r in _rows(conn, "SELECT name FROM core.attribute_types WHERE model_id = :m AND NOT is_deleted ORDER BY name", m=mid)]
    return {"model": {"id": m["id"], "name": m["name"]}, "kind": kind, "rows": rows, "choices": choices}
