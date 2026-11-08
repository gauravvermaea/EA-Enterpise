"""The content framework on each project (owner, 8 Nov 2026, D299).

The structure is fixed (AREAS, in the shape of TOGAF's content framework): principles, vision and requirements;
architecture definition (motivation, business, information systems, technology); architecture realisation. Each area
holds:
- the entity types of the project's models placed there, and their entities;
- the document types of the project placed there, and their documents (every state, the latest version).

Where a type sits: the type's own choice (core.entity_types.content_area, chosen when the metamodel is defined;
proj.items.content_area and proj.lib_items.content_area for document types) or, when none is chosen, the default map
(eax/seed/content_framework_map.json) by the type's code or name. A document may also be placed on its own
(proj.documents.content_area); it then shows there as well as under its type. '' is "not placed".

One entity type, document type or document may sit in several areas (owner, 8 Nov 2026, D309): the column holds the
area codes joined by commas ("data.entities,app.services"), in the order of AREAS.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one

# (code, label, section, group); the order is the diagram's. "Outcomes" where TOGAF says objectives (house style).
AREAS: list[tuple[str, str, str, str]] = [
    ("prelim.principles", "Architecture Principles", "Principles, vision and requirements", "Preliminary"),
    ("req.requirements", "Requirements", "Principles, vision and requirements", "Architecture Requirements"),
    ("req.constraints", "Constraints", "Principles, vision and requirements", "Architecture Requirements"),
    ("req.assumptions", "Assumptions", "Principles, vision and requirements", "Architecture Requirements"),
    ("req.gaps", "Gaps", "Principles, vision and requirements", "Architecture Requirements"),
    ("req.locations", "Locations", "Principles, vision and requirements", "Architecture Requirements"),
    ("vision.business_strategy", "Business Strategy", "Principles, vision and requirements", "Architecture Vision"),
    ("vision.technology_strategy", "Technology Strategy", "Principles, vision and requirements", "Architecture Vision"),
    ("vision.principles_drivers", "Business Principles, Outcomes and Drivers", "Principles, vision and requirements", "Architecture Vision"),
    ("vision.architecture_vision", "Architecture Vision", "Principles, vision and requirements", "Architecture Vision"),
    ("vision.stakeholders", "Stakeholders", "Principles, vision and requirements", "Architecture Vision"),
    ("motivation.drivers", "Drivers", "Architecture definition", "Motivation"),
    ("motivation.goals", "Goals", "Architecture definition", "Motivation"),
    ("motivation.outcomes", "Outcomes", "Architecture definition", "Motivation"),
    ("motivation.measures", "Measures", "Architecture definition", "Motivation"),
    ("business.value_streams", "Value Streams", "Architecture definition", "Business: strategy"),
    ("business.capabilities", "Business Capabilities", "Architecture definition", "Business: strategy"),
    ("business.courses_of_action", "Courses of Action", "Architecture definition", "Business: strategy"),
    ("business.services_contracts", "Business Services, Contracts", "Architecture definition", "Business: operational"),
    ("business.processes_events", "Processes, Events", "Architecture definition", "Business: operational"),
    ("business.functions_org_units", "Functions, Organisation Units", "Architecture definition", "Business: operational"),
    ("business.roles_actors", "Roles, Actors", "Architecture definition", "Business: operational"),
    ("data.entities", "Data Entities", "Architecture definition", "Data"),
    ("data.logical_components", "Logical Data Components", "Architecture definition", "Data"),
    ("data.physical_components", "Physical Data Components", "Architecture definition", "Data"),
    ("app.services", "Application Services", "Architecture definition", "Application"),
    ("app.logical_components", "Logical Application Components", "Architecture definition", "Application"),
    ("app.physical_components", "Physical Application Components", "Architecture definition", "Application"),
    ("tech.services", "Technology Services", "Architecture definition", "Technology"),
    ("tech.logical_components", "Logical Technology Components", "Architecture definition", "Technology"),
    ("tech.physical_components", "Physical Technology Components", "Architecture definition", "Technology"),
    ("real.capabilities", "Capabilities", "Architecture realisation", "Opportunities, solutions and migration planning"),
    ("real.work_packages", "Work Packages", "Architecture realisation", "Opportunities, solutions and migration planning"),
    ("real.contracts", "Architecture Contracts", "Architecture realisation", "Opportunities, solutions and migration planning"),
    ("gov.standards", "Standards", "Architecture realisation", "Implementation governance"),
    ("gov.guidelines", "Guidelines", "Architecture realisation", "Implementation governance"),
    ("gov.specifications", "Specifications", "Architecture realisation", "Implementation governance"),
]
LABEL = {c: label for c, label, _s, _g in AREAS}
MAX_ENTITIES = 500          # per entity type in one area's list


def clean_area(v: Any) -> str:
    """One area code or several (a list, or codes joined by commas) as the stored text: known codes, no repeats, in the
    order of AREAS; '' for none."""
    if isinstance(v, (list, tuple, set)):
        codes = [str(x or "").strip() for x in v]
    else:
        codes = [x.strip() for x in str(v or "").split(",")]
    codes = [c for c in codes if c]
    for c in codes:
        if c not in LABEL:
            raise EditError(f"{c} is not an area of the content framework.")
    return ",".join(c for c in LABEL if c in codes)


def areas_of(v: Any) -> list[str]:
    """The stored text as a list of area codes."""
    return [c for c in (x.strip() for x in str(v or "").split(",")) if c]


def labels(v: Any) -> str:
    return ", ".join(LABEL.get(c, c) for c in areas_of(v))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


@lru_cache(maxsize=1)
def _map() -> dict:
    d = json.loads((Path(__file__).resolve().parent / "seed" / "content_framework_map.json").read_text(encoding="utf-8"))
    return {"entity_types": {_norm(k): v for k, v in d["entity_types"].items()},
            "document_types": {_norm(k): v for k, v in d["document_types"].items()}}


def area_of_type(code: str, name: str, chosen: str = "") -> tuple[list[str], bool]:
    """An entity type's areas and whether they were chosen (True) or come from the default map (False)."""
    if areas_of(chosen):
        return areas_of(chosen), True
    m = _map()["entity_types"]
    return areas_of(m.get(_norm(code)) or m.get(_norm(name)) or ""), False


def area_of_item(name: str, chosen: str = "", library: str = "") -> tuple[list[str], bool]:
    if areas_of(chosen):
        return areas_of(chosen), True
    if areas_of(library):
        return areas_of(library), False
    return areas_of(_map()["document_types"].get(_norm(name), "")), False


# ---------------------------------------------------------------- reading
def _models(conn, p: dict) -> list[dict]:
    guids = [str(r["g"]) for r in _rows(conn, "SELECT model_guid AS g FROM proj.project_models WHERE project_id = :p", p=p["id"])]
    if not guids:
        return []
    return _rows(pj.core(conn), """SELECT m.id AS _id, m.guid::text AS id, m.name, m.kind_code AS kind
                                     FROM core.models m WHERE m.guid = ANY (CAST(:g AS uuid[])) AND NOT m.is_deleted ORDER BY m.name""", g=guids)


def _types(conn, models: list[dict]) -> list[dict]:
    if not models:
        return []
    rows = _rows(pj.core(conn), """
        SELECT t.id AS _id, t.guid::text AS id, t.model_id AS _m, t.code, t.name, t.content_area, l.name AS layer, l.colour,
               (SELECT count(*) FROM core.entities e WHERE e.entity_type_id = t.id AND NOT e.is_deleted) AS entities
          FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
         WHERE t.model_id = ANY (CAST(:m AS bigint[])) AND NOT t.is_deleted
         ORDER BY l.sort_order, t.sort_order, t.name""", m=[x["_id"] for x in models])
    for r in rows:
        r["area"], r["chosen"] = area_of_type(r["code"], r["name"], r["content_area"])
    return rows


def _items(conn, p: dict) -> list[dict]:
    rows = _rows(conn, """SELECT i.id AS _id, i.guid::text AS id, i.phase, i.name, i.kind, i.chosen, i.content_area,
                                 coalesce(li.content_area, '') AS library_area
                            FROM proj.items i LEFT JOIN proj.lib_items li ON li.id = i.library_id
                           WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.phase, i.name""", p=p["id"], c=p.get("cycle") or 1)
    for r in rows:
        r["area"], r["chosen_area"] = area_of_item(r["name"], r["content_area"], r["library_area"])
    return rows


def _own(conn, p: dict) -> dict[str, list[str]]:
    """The documents placed on their own: guid -> areas."""
    return {r["g"]: areas_of(r["a"]) for r in _rows(conn, """SELECT guid::text AS g, content_area AS a FROM proj.documents
                                                              WHERE project_id = :p AND content_area <> ''""", p=p["id"])}


def overview(conn, project: Any, user) -> dict:
    """The diagram's numbers: per area, the entity types and entities, the document types and documents."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    models = _models(conn, p)
    types = _types(conn, models)
    items = _items(conn, p)
    docs = pj.documents(conn, p)
    item_area = {i["id"]: i["area"] for i in items}
    out = {c: {"types": 0, "entities": 0, "doc_types": 0, "documents": 0} for c in LABEL}
    for t in types:
        for a in t["area"]:
            if a in out:
                out[a]["types"] += 1
                out[a]["entities"] += int(t["entities"])
    for i in items:
        for a in i["area"]:
            if a in out and i["chosen"]:
                out[a]["doc_types"] += 1
    own = _own(conn, p)
    for d in docs:
        for a in set(item_area.get(d["item_id"]) or []) | set(own.get(d["id"], [])):
            if a in out:
                out[a]["documents"] += 1
    return {"areas": [{"code": c, "label": label, "section": s, "group": g, **out[c]} for c, label, s, g in AREAS],
            "models": [{"id": m["id"], "name": m["name"]} for m in models],
            "unplaced": {"entity_types": sum(1 for t in types if not t["area"]),
                         "document_types": sum(1 for i in items if i["chosen"] and not i["area"])}}


def area(conn, project: Any, user, code: str) -> dict:
    """One area as a tree: Metamodels > each project model > its entity types here > their entities; Documents >
    the document types here > their documents (every state, latest version), and documents placed here on their own.
    code '_unplaced' lists what is not placed anywhere (to place it)."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    unplaced = code == "_unplaced"
    if not unplaced and code not in LABEL:
        raise EditError("No such area of the content framework.", 404)
    models = _models(conn, p)
    here = (lambda a: not a) if unplaced else (lambda a: code in a)
    types = [t for t in _types(conn, models) if here(t["area"])]
    ents: dict[int, list[dict]] = {}
    if types and not unplaced:
        for r in _rows(pj.core(conn), """
                SELECT * FROM (SELECT e.guid::text AS id, e.entity_type_id AS _t, e.name, e.display_id, e.status_code AS status,
                                      row_number() OVER (PARTITION BY e.entity_type_id ORDER BY e.name) AS n
                                 FROM core.entities e WHERE e.entity_type_id = ANY (CAST(:t AS bigint[])) AND NOT e.is_deleted) x
                 WHERE n <= :lim ORDER BY name""", t=[t["_id"] for t in types], lim=MAX_ENTITIES):
            ents.setdefault(r.pop("_t"), []).append({k: v for k, v in r.items() if k != "n"})
    tree_models = []
    for m in models:
        mt = [t for t in types if t["_m"] == m["_id"]]
        tree_models.append({"id": m["id"], "name": m["name"], "kind": m["kind"], "types": [
            {"id": t["id"], "name": t["name"], "code": t["code"], "layer": t["layer"], "colour": t["colour"], "chosen": t["chosen"],
             "areas": t["area"],
             "count": int(t["entities"]), "entities": ents.get(t["_id"], []), "more": max(0, int(t["entities"]) - MAX_ENTITIES)}
            for t in mt]})
    items = [i for i in _items(conn, p) if here(i["area"]) and i["chosen"]]       # the document types in the project
    docs = pj.documents(conn, p)
    own = _own(conn, p)
    keep = ("id", "file_name", "title", "state", "versions", "user_version", "kind", "is_link", "link_url", "modified_at", "modified_by", "folder")
    doc_types = []
    for i in items:
        doc_types.append({"id": i["id"], "name": i["name"], "phase": i["phase"], "kind": i["kind"], "placed": i["chosen_area"], "areas": i["area"],
                          "documents": [{k: d.get(k) for k in keep} | {"own_areas": own.get(d["id"], [])}
                                                                    for d in docs if d["item_id"] == i["id"]]})
    shown = {d["id"] for t in doc_types for d in t["documents"]}
    loose = [{k: d.get(k) for k in keep} | {"type": d["item_id"], "own_areas": own.get(d["id"], [])} for d in docs
             if not unplaced and code in own.get(d["id"], []) and d["id"] not in shown]
    where = next(({"section": s, "group": g} for c, _l, s, g in AREAS if c == code), {})
    return {"area": None if unplaced else {"code": code, "label": LABEL[code], **where},
            "models": tree_models, "doc_types": doc_types, "documents": loose,
            "areas": [{"code": c, "label": label, "group": g} for c, label, _s, g in AREAS],
            "may_place_documents": _may(conn, p, user, "contribute")}


def _may(conn, p: dict, user, what: str) -> bool:
    try:
        pj._need(conn, p, user, what)
        return True
    except EditError:
        return False


# ---------------------------------------------------------------- placing
def place_item(conn, project: Any, user, item: str, code: Any) -> dict:
    """Where a document type of the project sits: one area or several ('' = back to the default)."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    code = clean_area(code)
    it = _one(conn, "SELECT id, name FROM proj.items WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=item)
    if not it:
        raise EditError("No such document type in this project.", 404)
    conn.execute(text("UPDATE proj.items SET content_area = :a WHERE id = :i"), {"a": code, "i": it["id"]})
    return {"message": f"{it['name']}: {labels(code) if code else 'back to where it sits by default'}.", "areas": areas_of(code)}


def place_document(conn, project: Any, user, doc: str, code: Any) -> dict:
    """A document placed on its own, in one area or several ('' = only under its document type)."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    code = clean_area(code)
    d = pj._doc(conn, p, doc)
    conn.execute(text("UPDATE proj.documents SET content_area = :a WHERE id = :i"), {"a": code, "i": d["id"]})
    return {"message": f"{d.get('title') or d['file_name']}: {labels(code) if code else 'shown under its document type only'}.",
            "areas": areas_of(code)}


def place_library_item(conn, user, item: int, code: Any) -> dict:
    """Where a document type of the project library sits (Super Admins and Library Admins)."""
    pj._need_library(user)
    code = clean_area(code)
    it = _one(conn, "SELECT id, name FROM proj.lib_items WHERE id = :i", i=item)
    if not it:
        raise EditError("No such document type in the library.", 404)
    conn.execute(text("UPDATE proj.lib_items SET content_area = :a WHERE id = :i"), {"a": code, "i": it["id"]})
    return {"message": f"{it['name']}: {labels(code) if code else 'not placed'}.", "areas": areas_of(code)}
