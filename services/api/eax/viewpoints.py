"""Viewpoints, business maps and report audiences (build phase 8.2, D161).

* Viewpoints as data (D147): the 25 ArchiMate 4 example viewpoints (VP-01 to VP-26, built in, loaded by the
  seed from eax/report_defs.py) and an organisation's own (Library Admins). A model is shown through a
  viewpoint as a diagram, a catalog, a matrix, a heat map coloured by any attribute, or its relationships.
* Business maps: the value stream map (stages and the capabilities that enable each, coloured by an
  attribute) and the roadmap (work packages, deliverables and plateaus on a timeline).
* Report audiences (D153): who a report interests; not roles.

Row security on the tables decides which models a person sees; the functions here only shape the answer.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from . import repository as repo
from .metamodel_edit import EditError

CODE_RE = re.compile(r"^[A-Z]{2,4}-[0-9A-Za-z-]{1,20}$")
FIELDS = ("code", "name", "category", "purpose", "concerns", "stakeholders", "element_types", "relationship_types",
          "heat_attribute", "audiences")


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


# ---------------------------------------------------------------- viewpoints
def list_viewpoints(conn, model: Any = None) -> list[dict]:
    """Every viewpoint; with a model, how many of its entities each viewpoint shows there."""
    vps = _rows(conn, """SELECT guid AS id, code, name, category, purpose, concerns, stakeholders, element_types,
                                relationship_types, heat_attribute, audiences, is_builtin, source, default_view, togaf_artifact, created_by, modified_at
                           FROM core.viewpoints ORDER BY is_builtin DESC, sort_order, code""")
    if model is not None:
        m = repo.get_model(conn, model)
        counts = {r["code"]: r["n"] for r in _rows(conn, """
            SELECT t.code, count(e.id) AS n FROM core.entity_types t
              JOIN core.entities e ON e.entity_type_id = t.id AND NOT e.is_deleted
             WHERE t.model_id = :m AND NOT t.is_deleted GROUP BY t.code""", m=m["_id"])}
        defined = {r["code"] for r in _rows(conn, "SELECT code FROM core.entity_types WHERE model_id = :m AND NOT is_deleted", m=m["_id"])}
        for v in vps:
            v["entities"] = sum(counts.get(c, 0) for c in v["element_types"])
            v["types_present"] = [c for c in v["element_types"] if counts.get(c)]
            v["types_defined"] = [c for c in v["element_types"] if c in defined]     # in the model's metamodel (D345)
    return vps


def get_viewpoint(conn, code: str) -> dict:
    rows = _rows(conn, """SELECT guid AS id, code, name, category, purpose, concerns, stakeholders, element_types,
                                 relationship_types, heat_attribute, audiences, is_builtin, source, default_view, togaf_artifact, created_by, modified_at
                            FROM core.viewpoints WHERE code = :c OR guid::text = :c""", c=str(code))
    if not rows:
        raise EditError(f"No viewpoint {code}.", 404)
    return rows[0]


def _clean(data: dict) -> dict:
    out = {k: data.get(k) for k in FIELDS}
    out["code"] = (out["code"] or "").strip().upper()
    if not CODE_RE.match(out["code"]):
        raise EditError("Give the viewpoint a code of 2 to 4 capital letters, a dash and a number or name, for example OVP-01.")
    if re.match(r"^VP-[0-9]+$", out["code"]):
        raise EditError("Codes VP-<number> belong to the built-in viewpoints; use another code, for example OVP-01.")
    out["name"] = (out["name"] or "").strip()
    if not out["name"]:
        raise EditError("Give the viewpoint a name.")
    for k in ("element_types", "relationship_types", "audiences"):
        out[k] = [str(x).strip() for x in (out[k] or []) if str(x).strip()]
    if not out["element_types"]:
        raise EditError("Choose at least one element type.")
    for k in ("category", "purpose", "concerns", "stakeholders"):
        out[k] = (out[k] or "").strip()
    out["category"] = out["category"] or "Organisation"
    out["heat_attribute"] = (out["heat_attribute"] or "Lifecycle").strip()
    return out


def save_viewpoint(conn, data: dict, actor: str, code: str | None = None) -> dict:
    """Adds an organisation's own viewpoint, or changes one (code given). Built-in ones cannot be changed."""
    v = _clean(data)
    params = {**v, "by": actor}
    if code:
        cur = get_viewpoint(conn, code)
        if cur["is_builtin"]:
            raise EditError(f"{cur['code']} is a built-in viewpoint and cannot be changed; copy it to make your own.", 403)
        conn.execute(text("""UPDATE core.viewpoints SET code = :code, name = :name, category = :category, purpose = :purpose,
                                    concerns = :concerns, stakeholders = :stakeholders, element_types = :element_types,
                                    relationship_types = :relationship_types, heat_attribute = :heat_attribute,
                                    audiences = :audiences, modified_by = :by, modified_at = now()
                              WHERE guid = :g"""), {**params, "g": cur["id"]})
    else:
        if _rows(conn, "SELECT 1 FROM core.viewpoints WHERE code = :c", c=v["code"]):
            raise EditError(f"There is already a viewpoint {v['code']}.", 409)
        conn.execute(text("""INSERT INTO core.viewpoints (code, name, category, purpose, concerns, stakeholders, element_types,
                                     relationship_types, heat_attribute, audiences, created_by, modified_by)
                             VALUES (:code, :name, :category, :purpose, :concerns, :stakeholders, :element_types,
                                     :relationship_types, :heat_attribute, :audiences, :by, :by)"""), params)
    return get_viewpoint(conn, v["code"])


def delete_viewpoint(conn, code: str) -> dict:
    cur = get_viewpoint(conn, code)
    if cur["is_builtin"]:
        raise EditError(f"{cur['code']} is a built-in viewpoint and cannot be deleted.", 403)
    conn.execute(text("DELETE FROM core.viewpoints WHERE guid = :g"), {"g": cur["id"]})
    return {"deleted": cur["code"]}


def _values(conn, model_id: int, entity_ids: list[int]) -> dict[int, dict[str, str]]:
    """Every attribute value of these entities, by attribute name, as shown."""
    if not entity_ids:
        return {}
    out: dict[int, dict[str, str]] = {}
    for r in _rows(conn, """
        SELECT v.entity_id, a.name AS attribute,
               coalesce(v.value_text, trim_scale(v.value_number)::text, v.value_date::text,
                        CASE WHEN v.value_bool THEN 'Yes' WHEN NOT v.value_bool THEN 'No' END, re.name) AS value
          FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
          LEFT JOIN core.entities re ON re.id = v.value_ref
         WHERE v.model_id = :m AND NOT v.is_deleted AND v.entity_id = ANY (:ids)""", m=model_id, ids=entity_ids):
        if r["value"] not in (None, ""):
            out.setdefault(r["entity_id"], {})[r["attribute"]] = r["value"]
    return out


def model_viewpoint(conn, model: Any, code: str) -> dict:
    """The model through one viewpoint: its elements (with every attribute value), the relationships between
    them that the viewpoint shows, and the attributes to colour a heat map by."""
    m = repo.get_model(conn, model)
    vp = get_viewpoint(conn, code)
    ents = _rows(conn, """
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, e.description, t.code AS type_code, t.name AS entity_type,
               t.guid AS entity_type_id, l.name AS layer, l.colour, l.sort_order AS layer_order, pe.name AS parent
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id JOIN core.layers l ON l.id = t.layer_id
          LEFT JOIN core.entities pe ON pe.id = e.parent_entity_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND t.code = ANY (:types)
         ORDER BY l.sort_order, t.name, e.name""", m=m["_id"], types=list(vp["element_types"]))
    vals = _values(conn, m["_id"], [e["_id"] for e in ents])
    ids = [e["_id"] for e in ents]
    rels = _rows(conn, """
        SELECT r.guid AS id, rt.code AS relationship_type_code, rt.name AS relationship_type, rt.verb, r.name,
               s.guid AS source, t.guid AS target
          FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted AND r.source_entity_id = ANY (:ids) AND r.target_entity_id = ANY (:ids)
           AND (cardinality(CAST(:rels AS text[])) = 0 OR rt.code = ANY (CAST(:rels AS text[])))""",
                 m=m["_id"], ids=ids, rels=list(vp["relationship_types"]))
    attributes: dict[str, int] = {}
    for e in ents:
        e["values"] = vals.get(e.pop("_id"), {})
        for k in e["values"]:
            attributes[k] = attributes.get(k, 0) + 1
    types = []
    for e in ents:
        if not types or types[-1]["code"] != e["type_code"]:
            if not any(t["code"] == e["type_code"] for t in types):
                types.append({"code": e["type_code"], "name": e["entity_type"], "id": e["entity_type_id"], "layer": e["layer"],
                              "colour": e["colour"], "count": 0})
        next(t for t in types if t["code"] == e["type_code"])["count"] += 1
    heat = next((a for a in attributes if a.replace(" ", "").lower() == vp["heat_attribute"].lower()), None)
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "viewpoint": vp, "entities": ents, "relationships": rels,
            "types": types, "attributes": sorted(attributes, key=lambda a: (-attributes[a], a)), "heat_attribute": heat}


# ---------------------------------------------------------------- business maps
def value_stream_map(conn, model: Any) -> dict:
    """Value streams with their stages (Value Stream Stages, D345, or child value streams, in flow order) and the
    capabilities that serve each stage (or the stream itself), with every attribute value of each capability."""
    m = repo.get_model(conn, model)
    vs = _rows(conn, """
        SELECT e.id AS _id, e.guid AS id, e.name, e.description, e.parent_entity_id AS _parent
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND t.code IN ('ValueStream', 'ValueStreamStage') ORDER BY e.name""", m=m["_id"])
    by_id = {v["_id"]: v for v in vs}
    flows = _rows(conn, """
        SELECT r.source_entity_id AS a, r.target_entity_id AS b FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
         WHERE r.model_id = :m AND NOT r.is_deleted AND rt.code IN ('Flow', 'Triggering')
           AND r.source_entity_id = ANY (:ids) AND r.target_entity_id = ANY (:ids)""", m=m["_id"], ids=list(by_id))
    nxt = {f["a"]: f["b"] for f in flows}
    caps = _rows(conn, """
        SELECT DISTINCT c.id AS _id, c.guid AS id, c.name, c.display_id, r.target_entity_id AS _stage
          FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities c ON c.id = r.source_entity_id AND NOT c.is_deleted
          JOIN core.entity_types ct ON ct.id = c.entity_type_id AND ct.code = 'Capability'
         WHERE r.model_id = :m AND NOT r.is_deleted AND r.target_entity_id = ANY (:ids)
         ORDER BY c.name""", m=m["_id"], ids=list(by_id))
    vals = _values(conn, m["_id"], list({c["_id"] for c in caps}))
    attributes: dict[str, int] = {}
    for c in caps:
        c["values"] = vals.get(c["_id"], {})
    for v in vals.values():
        for k in v:
            attributes[k] = attributes.get(k, 0) + 1
    streams = []
    for v in vs:
        if v["_parent"] in by_id:
            continue
        kids = [k for k in vs if k["_parent"] == v["_id"]]
        # order the stages along the flow: start where nothing flows in
        into = {nxt[k["_id"]] for k in kids if k["_id"] in nxt}
        order, seen = [], set()
        for start in [k for k in kids if k["_id"] not in into] + kids:
            cur = start["_id"]
            while cur in by_id and cur not in seen and by_id[cur]["_parent"] == v["_id"]:
                seen.add(cur)
                order.append(by_id[cur])
                cur = nxt.get(cur)
        stages = order or [v]
        streams.append({
            "id": str(v["id"]), "name": v["name"], "description": v["description"],
            "stages": [{"id": str(s["id"]), "name": s["name"].split(": ", 1)[-1] if s is not v else s["name"],
                        "capabilities": [{k: c[k] for k in ("id", "name", "display_id", "values")}
                                         for c in caps if c["_stage"] == s["_id"]]} for s in stages]})
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "value_streams": streams,
            "attributes": sorted(attributes, key=lambda a: (-attributes[a], a))}


def roadmap(conn, model: Any) -> dict:
    """Work packages, deliverables and plateaus with their start and end dates, and what each delivers."""
    m = repo.get_model(conn, model)
    items = _rows(conn, """
        SELECT e.id AS _id, e.guid AS id, e.display_id, e.name, t.code AS type_code, t.name AS entity_type,
               max(v.value_date) FILTER (WHERE a.code = 'StartDate') AS start_date,
               max(v.value_date) FILTER (WHERE a.code = 'EndDate') AS end_date,
               max(v.value_text) FILTER (WHERE a.code = 'Owner') AS owner,
               max(v.value_text) FILTER (WHERE a.code = 'Priority') AS priority,
               max(v.value_text) FILTER (WHERE a.code = 'ArchitectureState') AS architecture_state
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
          LEFT JOIN core.attribute_values v ON v.entity_id = e.id AND NOT v.is_deleted
          LEFT JOIN core.attribute_types a ON a.id = v.attribute_type_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND t.code IN ('WorkPackage', 'Deliverable', 'Plateau')
         GROUP BY e.id, e.guid, e.display_id, e.name, t.code, t.name
         ORDER BY CASE t.code WHEN 'Plateau' THEN 0 WHEN 'WorkPackage' THEN 1 ELSE 2 END, 7, e.name""", m=m["_id"])
    links = _rows(conn, """
        SELECT s.guid AS source, t.guid AS target, t.name AS target_name, rt.name AS relationship_type
          FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted AND r.source_entity_id = ANY (:ids)
           AND rt.code IN ('Realization', 'Triggering', 'Aggregation')""", m=m["_id"], ids=[i["_id"] for i in items])
    for i in items:
        i.pop("_id")
        for k in ("start_date", "end_date"):
            i[k] = (i[k].isoformat() if hasattr(i[k], "isoformat") else str(i[k])) if i[k] else None
        i["delivers"] = [{"id": str(x["target"]), "name": x["target_name"], "relationship_type": x["relationship_type"]}
                         for x in links if x["source"] == i["id"]]
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "items": items}


# ---------------------------------------------------------------- audiences
def audiences(conn) -> list[dict]:
    return _rows(conn, """SELECT a.code, a.name, a.audience_group AS "group",
                                 coalesce(array_agg(l.report_code ORDER BY l.report_code) FILTER (WHERE l.report_code IS NOT NULL),
                                          '{}') AS reports
                            FROM core.report_audiences a LEFT JOIN core.report_audience_links l ON l.audience_code = a.code
                           GROUP BY a.code, a.name, a.audience_group, a.sort_order ORDER BY a.sort_order""")
