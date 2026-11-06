"""Tree views (owner, 6 Nov 2026, D250): key and value only, each level read when it is opened.

* The metamodel: model > entity type > its attributes (name: data type, required, weight) and the relations the
  metamodel allows, outgoing and incoming; a relation names the entity type at its other end so the screen can jump
  to it.
* The entities: model > entity type (its count and data quality) > its entities (a page at a time, with the data
  quality last calculated, D245) > one entity: its attribute values that are filled (key: value; how many are empty)
  and its relationships, outgoing and incoming, naming the entity (and its type) at the other end.
* A search that finds entity types, entities and values, for the filter box; and an Excel outline of any of them.
Reads only; the database does no work beyond the queries (D248).
"""

from __future__ import annotations

import io
from collections import defaultdict
from typing import Any

from . import repository as repo

PAGE = 200


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _quality(conn, m: dict) -> tuple[dict, dict]:
    """Each entity's last calculated data quality score (by entity id) and the model's colours."""
    from . import quality
    scores = {r["e"]: float(r["s"]) for r in _rows(conn, """SELECT entity_id AS e, (row ->> 'score') AS s
                                                              FROM core.quality_entities WHERE model_id = :m""", m=m["_id"])
              if r["s"] is not None}
    try:
        bands = quality.bands_for(conn, m)
    except Exception:  # noqa: BLE001 - colours are a help
        bands = dict(quality.BANDS)
    return scores, bands


# ---------------------------------------------------------------- the metamodel
def metamodel_tree(conn, model: Any) -> dict:
    m = repo.get_model(conn, model)
    types = _rows(conn, """SELECT et.id AS _id, et.guid::text AS id, et.code, et.name, l.name AS layer, l.colour,
                                  et.status_code AS status,
                                  (SELECT count(*) FROM core.entities e WHERE e.entity_type_id = et.id AND NOT e.is_deleted) AS entities
                             FROM core.entity_types et JOIN core.layers l ON l.id = et.layer_id
                            WHERE et.model_id = :m AND NOT et.is_deleted ORDER BY l.sort_order, et.sort_order, et.name""",
                  m=m["_id"])
    attrs = defaultdict(list)
    for a in _rows(conn, """SELECT ia.entity_type_id AS t, at.name, at.code, dt.name AS data_type, at.unit, ia.is_required,
                                   coalesce(ia.quality_weight, at.quality_weight, CASE WHEN ia.is_required THEN 3 ELSE 1 END) AS weight
                              FROM core.item_attributes ia
                              JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
                              JOIN core.data_types dt ON dt.code = at.data_type_code
                             WHERE ia.model_id = :m AND ia.entity_type_id IS NOT NULL AND NOT ia.is_deleted
                             ORDER BY ia.sort_order, at.name""", m=m["_id"]):
        value = a["data_type"] + (f" ({a['unit']})" if a["unit"] else "") + (", required" if a["is_required"] else "") + \
            (f", data quality weight {a['weight']}" if a["weight"] else ", left out of data quality")
        attrs[a["t"]].append({"key": a["name"], "value": value, "code": a["code"]})
    rels = defaultdict(lambda: {"out": [], "in": []})
    for r in _rows(conn, """SELECT ar.source_type_id AS s, ar.target_type_id AS t, rt.name AS rel, rt.verb,
                                   st.guid::text AS s_id, st.name AS s_name, tt.guid::text AS t_id, tt.name AS t_name
                              FROM core.allowed_relationships ar
                              JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id AND NOT rt.is_deleted
                              JOIN core.entity_types st ON st.id = ar.source_type_id AND NOT st.is_deleted
                              JOIN core.entity_types tt ON tt.id = ar.target_type_id AND NOT tt.is_deleted
                             WHERE ar.model_id = :m AND NOT ar.is_deleted ORDER BY rt.sort_order, tt.name""", m=m["_id"]):
        rels[r["s"]]["out"].append({"relationship": r["rel"], "verb": r["verb"], "other_type_id": r["t_id"], "other_type": r["t_name"]})
        rels[r["t"]]["in"].append({"relationship": r["rel"], "verb": r["verb"], "other_type_id": r["s_id"], "other_type": r["s_name"]})
    return {"model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]},
            "types": [{**{k: v for k, v in t.items() if not k.startswith("_")}, "attributes": attrs.get(t["_id"], []),
                       "relations": rels[t["_id"]] if t["_id"] in rels else {"out": [], "in": []}} for t in types]}


# ---------------------------------------------------------------- the entities, a level at a time
def types_tree(conn, model: Any) -> dict:
    """The model's entity types with how many entities each has and its data quality as last calculated."""
    m = repo.get_model(conn, model)
    scores, bands = _quality(conn, m)
    types = _rows(conn, """SELECT et.id AS _id, et.guid::text AS id, et.code, et.name, l.name AS layer, l.colour
                             FROM core.entity_types et JOIN core.layers l ON l.id = et.layer_id
                            WHERE et.model_id = :m AND NOT et.is_deleted ORDER BY l.sort_order, et.sort_order, et.name""",
                  m=m["_id"])
    ents = defaultdict(list)
    for r in _rows(conn, "SELECT id, entity_type_id AS t FROM core.entities WHERE model_id = :m AND NOT is_deleted", m=m["_id"]):
        ents[r["t"]].append(r["id"])
    out = []
    for t in types:
        ids = ents.get(t["_id"], [])
        s = [scores[i] for i in ids if i in scores]
        out.append({**{k: v for k, v in t.items() if not k.startswith("_")}, "entities": len(ids),
                    "score": round(sum(s) / len(s), 2) if s else None})
    return {"model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]}, "types": out, "bands": bands}


def type_entities(conn, model: Any, entity_type: Any, offset: int = 0, limit: int = PAGE, q: str = "") -> dict:
    """One page of an entity type's entities, by name, each with its data quality as last calculated."""
    m = repo.get_model(conn, model)
    t = repo._find_type(conn, m["_id"], entity_type)
    scores, bands = _quality(conn, m)
    limit = max(1, min(int(limit or PAGE), 1000))
    where = "e.model_id = :m AND e.entity_type_id = :t AND NOT e.is_deleted"
    params = {"m": m["_id"], "t": t["_id"]}
    if q:
        where += " AND (e.name ILIKE :q OR e.display_id ILIKE :q)"
        params["q"] = f"%{q}%"
    total = _rows(conn, f"SELECT count(*) AS n FROM core.entities e WHERE {where}", **params)[0]["n"]
    rows = _rows(conn, f"""SELECT e.id AS _id, e.guid::text AS id, e.display_id, e.name, e.status_code AS status
                             FROM core.entities e WHERE {where} ORDER BY lower(e.name), e.display_id
                            OFFSET :o LIMIT :l""", o=max(0, int(offset or 0)), l=limit, **params)
    return {"type": {"id": str(t["id"]), "name": t["name"], "code": t["code"], "colour": t["colour"]}, "total": total,
            "offset": int(offset or 0), "bands": bands,
            "entities": [{**{k: v for k, v in r.items() if not k.startswith("_")}, "score": scores.get(r["_id"])} for r in rows]}


def _nodes(conn, m: dict, where: str, **p) -> list[dict]:
    """Entities with their filled values, empty count and relationships both ways, in a few queries for any number."""
    ents = _rows(conn, f"""SELECT e.id AS _id, e.guid::text AS id, e.display_id, e.name, e.description, e.status_code AS status,
                                  et.guid::text AS type_id, et.name AS type, p.guid::text AS parent_id, p.name AS parent
                             FROM core.entities e JOIN core.entity_types et ON et.id = e.entity_type_id
                             LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                            WHERE e.model_id = :m AND NOT e.is_deleted AND {where}
                            ORDER BY lower(e.name), e.display_id""", m=m["_id"], **p)
    if not ents:
        return []
    ids = [e["_id"] for e in ents]
    vals = repo._load_values(conn, "e.id = ANY (CAST(:ids AS bigint[]))", ids=ids)
    rels = defaultdict(lambda: {"out": [], "in": []})
    for r in _rows(conn, """SELECT x.e AS _e, rt.name AS relationship, rt.verb,
                                   CASE WHEN r.source_entity_id = x.e THEN 'out' ELSE 'in' END AS dir,
                                   o.guid::text AS other_id, o.name AS other, o.display_id AS other_display_id,
                                   ot.guid::text AS other_type_id, ot.name AS other_type
                              FROM unnest(CAST(:ids AS bigint[])) AS x(e)
                              JOIN core.relationships r ON (r.source_entity_id = x.e OR r.target_entity_id = x.e) AND NOT r.is_deleted
                              JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                              JOIN core.entities o ON o.id = CASE WHEN r.source_entity_id = x.e THEN r.target_entity_id
                                                                  ELSE r.source_entity_id END AND NOT o.is_deleted
                              JOIN core.entity_types ot ON ot.id = o.entity_type_id
                             ORDER BY rt.sort_order, o.name""", ids=ids):
        rels[r.pop("_e")][r.pop("dir")].append(r)
    scores, bands = _quality(conn, m)
    out = []
    for e in ents:
        values, empty = [], 0
        if e["description"]:
            values.append({"key": "Description", "value": e["description"]})
        if e["parent"]:
            values.append({"key": "Part of", "value": e["parent"], "ref_id": e["parent_id"]})
        for a in vals.get(e["_id"], []):
            if a["value"] in (None, ""):
                empty += 1
                continue
            values.append({"key": a["name"], "value": a["value"] + (f" {a['unit']}" if a.get("unit") else ""),
                           "ref_id": str(a["ref_id"]) if a.get("ref_id") else None})
        out.append({**{k: v for k, v in e.items() if not k.startswith("_") and k != "description"}, "values": values,
                    "empty": empty, "relations": rels[e["_id"]] if e["_id"] in rels else {"out": [], "in": []},
                    "score": scores.get(e["_id"]), "bands": bands})
    return out


def entity_node(conn, model: Any, entity: Any) -> dict:
    """One entity: its filled attribute values (key: value), how many are empty, and its relationships both ways."""
    m = repo.get_model(conn, model)
    n = _nodes(conn, m, "(e.guid::text = :x OR e.display_id = :x)", x=str(entity))
    if not n:
        raise repo.NotFound(f"No entity {entity!r} in {m['name']}.")
    return n[0]


# ---------------------------------------------------------------- the filter box
def search(conn, model: Any, q: str, limit: int = 50) -> dict:
    """What matches the filter: entity types (by name or code), entities (by name or ID) and attribute values, each
    with the path to open in the tree."""
    m = repo.get_model(conn, model)
    q = (q or "").strip()
    if len(q) < 2:
        return {"q": q, "types": [], "entities": [], "values": []}
    like = f"%{q}%"
    types = _rows(conn, """SELECT guid::text AS id, name FROM core.entity_types
                            WHERE model_id = :m AND NOT is_deleted AND (name ILIKE :q OR code ILIKE :q) ORDER BY name LIMIT :l""",
                  m=m["_id"], q=like, l=limit)
    ents = _rows(conn, """SELECT e.guid::text AS id, e.name, e.display_id, et.guid::text AS type_id, et.name AS type
                            FROM core.entities e JOIN core.entity_types et ON et.id = e.entity_type_id
                           WHERE e.model_id = :m AND NOT e.is_deleted AND (e.name ILIKE :q OR e.display_id ILIKE :q)
                           ORDER BY lower(e.name) LIMIT :l""", m=m["_id"], q=like, l=limit)
    vals = _rows(conn, """SELECT e.guid::text AS id, e.name, et.guid::text AS type_id, et.name AS type, at.name AS attribute,
                                 coalesce(v.value_text, CAST(v.value_number AS text), CAST(v.value_date AS text)) AS value
                            FROM core.attribute_values v
                            JOIN core.attribute_types at ON at.id = v.attribute_type_id
                            JOIN core.entities e ON e.id = v.entity_id AND NOT e.is_deleted
                            JOIN core.entity_types et ON et.id = e.entity_type_id
                           WHERE v.model_id = :m AND NOT v.is_deleted
                             AND (v.value_text ILIKE :q OR CAST(v.value_number AS text) ILIKE :q OR CAST(v.value_date AS text) ILIKE :q)
                           ORDER BY lower(e.name) LIMIT :l""", m=m["_id"], q=like, l=limit)
    return {"q": q, "types": types, "entities": ents, "values": vals}


# ---------------------------------------------------------------- Excel outlines
def tree_xlsx(conn, model: Any, scope: str, entity_type: Any = None, entity: Any = None) -> bytes:
    """The tree as an Excel outline (the + opens a level): scope metamodel, entities (the whole model, or one entity
    type), or entity (one entity)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    m = repo.get_model(conn, model)
    wb = Workbook()
    ws = wb.active
    ws.title = "Tree"
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.append(["Item", "Key", "Value"])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 60
    tones = {"good": "D3F9D8", "fair": "FFF3BF", "poor": "FFE3E3"}

    def row(level: int, item: str, key: str = "", value: str = "", bold: bool = False, fill: str | None = None):
        ws.append(["    " * level + item, key, value])
        r = ws.max_row
        if level:
            ws.row_dimensions[r].outlineLevel = min(level, 7)
            ws.row_dimensions[r].hidden = level > 1
        if bold:
            ws.cell(r, 1).font = Font(bold=True)
        if fill:
            ws.cell(r, 1).fill = PatternFill("solid", fgColor=fill)

    def tone(score, bands):
        from .quality import tone as qt
        return tones.get(qt(score, bands)) if score is not None else None

    def entity_rows(level: int, n: dict):
        row(level, f"{n['name']} ({n['display_id']})", "Data quality", f"{n['score']:.2f}%" if n["score"] is not None else "-",
            bold=True, fill=tone(n["score"], n["bands"]))
        if n["values"] or n["empty"]:
            row(level + 1, "Attributes", "", f"{n['empty']} empty" if n["empty"] else "")
            for v in n["values"]:
                row(level + 2, "", v["key"], v["value"])
        if n["relations"]["out"] or n["relations"]["in"]:
            row(level + 1, "Relations")
            for r in n["relations"]["out"]:
                row(level + 2, "", f"{r['relationship']} →", f"{r['other']} ({r['other_type']})")
            for r in n["relations"]["in"]:
                row(level + 2, "", f"← {r['relationship']}", f"{r['other']} ({r['other_type']})")

    row(0, m["name"], "", "Model", bold=True)
    if scope == "metamodel":
        for t in metamodel_tree(conn, m["id"])["types"]:
            row(1, t["name"], "Entity type", f"{t['layer']} layer, {t['entities']} entities", bold=True)
            row(2, "Attributes")
            for a in t["attributes"]:
                row(3, "", a["key"], a["value"])
            row(2, "Relations")
            for r in t["relations"]["out"]:
                row(3, "", f"{r['relationship']} →", r["other_type"])
            for r in t["relations"]["in"]:
                row(3, "", f"← {r['relationship']}", r["other_type"])
    elif scope == "entity":
        entity_rows(1, entity_node(conn, m["id"], entity))
    else:
        tt = types_tree(conn, m["id"])
        for t in tt["types"]:
            if entity_type and str(entity_type) not in (t["id"], t["code"], t["name"]):
                continue
            if not t["entities"]:
                continue
            row(1, t["name"], "Entity type", f"{t['entities']} entities" + (f", data quality {t['score']:.2f}%" if t["score"] is not None else ""),
                bold=True, fill=tone(t["score"], tt["bands"]))
            for n in _nodes(conn, m, "et.guid::text = :t", t=t["id"]):
                entity_rows(2, n)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
