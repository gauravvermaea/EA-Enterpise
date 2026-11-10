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
import mimetypes
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


# A class or template the map does not know sits by its ADM phase (owner, 8 Nov 2026: everything has a default)
PHASE_AREA = {"P": "prelim.principles", "A": "vision.architecture_vision", "B": "business.capabilities", "C": "data.logical_components",
              "C-D": "data.logical_components", "C-A": "app.logical_components", "D": "tech.logical_components", "E": "real.capabilities",
              "F": "real.work_packages", "G": "real.contracts", "H": "req.gaps", "R": "req.requirements", "X": "gov.guidelines"}


def area_of_item(name: str, chosen: str = "", library: str = "", phase: str = "") -> tuple[list[str], bool]:
    if areas_of(chosen):
        return areas_of(chosen), True
    if areas_of(library):
        return areas_of(library), False
    found = areas_of(_map()["document_types"].get(_norm(name), ""))
    if not found and phase:
        found = areas_of(PHASE_AREA.get(phase.upper(), "gov.guidelines"))
    return found, False


def template_default(path: str, name: str) -> list[str]:
    """A template with no deliverable or artifact: by its name (\"TOGAF Template - Architecture Vision\" -> Architecture
    Vision), else by the phase of its folder (\"Phase B - ...\"), else a guideline."""
    stem = re.sub(r"\.[a-z0-9]+$", "", (name or path.rsplit("/", 1)[-1]), flags=re.I)
    stem = re.sub(r"^.*template\s*-\s*", "", stem, flags=re.I).strip()
    found = area_of_item(stem)[0]
    if found:
        return found
    m = re.search(r"phase\s+([a-h])\b", path, re.I) or re.search(r"/([A-H])[_ -]", "/" + path)
    if re.search(r"preliminary", path, re.I):
        return ["prelim.principles"]
    if re.search(r"requirements", path, re.I):
        return ["req.requirements"]
    return [PHASE_AREA[m.group(1).upper()]] if m else ["gov.guidelines"]


# ---------------------------------------------------------------- the Repository Area (owner, 8 Nov 2026, D318)
# The part of the TOGAF Architecture Repository a document class or an entity type is filed in: one value, set on the
# class or the type (never on each document or entity). Built in: the map in seed/repository_area_map.json, else from
# its first content framework area; an admin changes it (Template setup; the metamodel editor).
REPO_AREAS = ["Architecture Metamodel", "Architecture Capability", "Architecture Landscape", "Standards Information Base",
              "Reference Library", "Governance Log", "Architecture Requirements Repository", "Solutions Landscape"]
AREA_TO_REPO = {"prelim": "Architecture Capability", "req.requirements": "Architecture Requirements Repository",
                "req.constraints": "Architecture Requirements Repository", "req.assumptions": "Architecture Requirements Repository",
                "req.gaps": "Architecture Requirements Repository", "req.locations": "Architecture Landscape",
                "data.physical_components": "Solutions Landscape", "app.physical_components": "Solutions Landscape",
                "tech.physical_components": "Solutions Landscape", "real.contracts": "Governance Log",
                "gov.standards": "Standards Information Base", "gov.guidelines": "Reference Library"}


@lru_cache(maxsize=1)
def _repo_map() -> dict:
    d = json.loads((Path(__file__).resolve().parent / "seed" / "repository_area_map.json").read_text(encoding="utf-8"))
    return {"entity_types": {_norm(k): v for k, v in d["entity_types"].items()},
            "document_types": {_norm(k): v for k, v in d["document_types"].items()}}


def clean_repo(v: Any) -> str:
    v = (str(v or "")).strip()
    if v and v not in REPO_AREAS:
        raise EditError(f"The repository area is one of: {', '.join(REPO_AREAS)}.")
    return v


def _from_areas(areas: list[str]) -> str:
    for a in areas:
        if a in AREA_TO_REPO:
            return AREA_TO_REPO[a]
        if a.split(".")[0] in AREA_TO_REPO:
            return AREA_TO_REPO[a.split(".")[0]]
    return "Architecture Landscape"


def repo_of_type(code: str, name: str, chosen: str = "", areas: list[str] | None = None) -> tuple[str, bool]:
    """An entity type's repository area and whether an admin chose it."""
    if (chosen or "").strip():
        return chosen.strip(), True
    m = _repo_map()["entity_types"]
    return m.get(_norm(code)) or m.get(_norm(name)) or _from_areas(areas if areas is not None else area_of_type(code, name)[0]), False


def repo_of_item(name: str, chosen: str = "", areas: list[str] | None = None) -> tuple[str, bool]:
    """A document class's repository area and whether an admin chose it."""
    if (chosen or "").strip():
        return chosen.strip(), True
    return _repo_map()["document_types"].get(_norm(name)) or _from_areas(areas if areas is not None else area_of_item(name)[0]), False


# ---------------------------------------------------------------- reading
def _models(conn, p: dict) -> list[dict]:
    guids = [str(r["g"]) for r in _rows(conn, "SELECT model_guid AS g FROM proj.project_models WHERE project_id = :p", p=p["id"])]
    if not guids:
        return []
    return _rows(pj.core(conn), """SELECT m.id AS _id, m.guid::text AS id, m.name, m.kind_code AS kind
                                     FROM core.models m WHERE m.guid = ANY (CAST(:g AS uuid[])) AND NOT m.is_deleted ORDER BY m.name""", g=guids)


def _bases(conn, p: dict) -> list[dict]:
    """The projects this one is based on, nearest first (D317: a project inherits their placements)."""
    from . import project_bases as pb
    out, seen, cur = [], {p["id"]}, pb.base_row(conn, p)
    while cur and cur["id"] not in seen and len(out) < 10:
        seen.add(cur["id"])
        out.append(cur)
        cur = pb.base_row(conn, cur)
    return out


def _type_parent(conn, p: dict) -> dict[str, tuple[list[str], str]]:
    """Entity types placed by the projects above (by the type's code, nearest wins): code -> (areas, project name)."""
    out: dict[str, tuple[list[str], str]] = {}
    for b in _bases(conn, p):
        for r in _rows(conn, "SELECT lower(type_code) AS c, areas AS a FROM proj.cf_type_areas WHERE project_id = :p AND type_code <> ''", p=b["id"]):
            out.setdefault(r["c"], (areas_of(r["a"]), b["name"]))
    return out


def _ent_parent(conn, p: dict) -> dict[str, tuple[list[str], str]]:
    """Entities placed by the projects above: entity guid -> (areas, project name); matched on guid or origin."""
    out: dict[str, tuple[list[str], str]] = {}
    for b in _bases(conn, p):
        for r in _rows(conn, "SELECT entity_guid::text AS g, areas AS a FROM proj.cf_entity_areas WHERE project_id = :p", p=b["id"]):
            out.setdefault(r["g"], (areas_of(r["a"]), b["name"]))
    return out


def _type_over(conn, p: dict) -> dict[str, list[str]]:
    """The project's own placement of its models' entity types (owner, 8 Nov 2026): type guid -> areas."""
    return {str(r["g"]): areas_of(r["a"]) for r in _rows(conn, "SELECT type_guid::text AS g, areas AS a FROM proj.cf_type_areas WHERE project_id = :p",
                                                         p=p["id"])}


def _ent_over(conn, p: dict) -> dict[str, list[str]]:
    """The project's own placement of single entities: entity guid -> areas (over their type's)."""
    return {str(r["g"]): areas_of(r["a"]) for r in _rows(conn, "SELECT entity_guid::text AS g, areas AS a FROM proj.cf_entity_areas WHERE project_id = :p",
                                                         p=p["id"])}


def _types(conn, models: list[dict], p: dict | None = None) -> list[dict]:
    if not models:
        return []
    rows = _rows(pj.core(conn), """
        SELECT t.id AS _id, t.guid::text AS id, t.model_id AS _m, t.code, t.name, t.content_area, t.repository_area, l.name AS domain, l.colour,
               (SELECT count(*) FROM core.entities e WHERE e.entity_type_id = t.id AND NOT e.is_deleted) AS entities
          FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
         WHERE t.model_id = ANY (CAST(:m AS bigint[])) AND NOT t.is_deleted
         ORDER BY l.sort_order, t.sort_order, t.name""", m=[x["_id"] for x in models])
    over = _type_over(conn, p) if p else {}
    parent = _type_parent(conn, p) if p else {}
    for r in rows:
        r["default_area"], r["chosen"] = area_of_type(r["code"], r["name"], r["content_area"])
        r["repository"] = repo_of_type(r["code"], r["name"], r["repository_area"], r["default_area"])[0]
        r["source"] = "admin" if r["chosen"] else "built-in"
        if (r["code"] or "").lower() in parent:          # placed by a project above (D317)
            r["default_area"], r["source"] = parent[r["code"].lower()][0], f"parent: {parent[r['code'].lower()][1]}"
            r["chosen"] = "parent"
        r["area"] = r["default_area"]
        if r["id"] in over:                 # placed by the project itself
            r["area"], r["chosen"] = over[r["id"]], "project"
    return rows


def _entities_off_type(conn, p: dict, models: list[dict], tarea: dict[int, list[str]]) -> dict[str, dict]:
    """The entities that do not simply sit where their type does: placed in their model (by an admin), by a project
    above, or by this project. guid -> {areas, default, chosen, source, _t, _m}."""
    if not models:
        return {}
    own, parent = _ent_over(conn, p), _ent_parent(conn, p)
    keys = list(set(own) | set(parent))
    out = {}
    by_key = " OR guid = ANY (CAST(:k AS uuid[])) OR origin_guid = ANY (CAST(:k AS uuid[]))" if keys else ""
    for e in _rows(pj.core(conn), f"""SELECT guid::text AS g, origin_guid::text AS o, entity_type_id AS _t, model_id AS _m, content_area AS a
                                        FROM core.entities WHERE model_id = ANY (CAST(:m AS bigint[])) AND NOT is_deleted
                                         AND (content_area <> ''{by_key})""",
                   m=[x["_id"] for x in models], k=keys):
        dflt, src = tarea.get(e["_t"], []), "its type"
        if areas_of(e["a"]):
            dflt, src = areas_of(e["a"]), "admin"
        par = parent.get(e["g"]) or (parent.get(e["o"]) if e["o"] else None)
        if par:
            dflt, src = par[0], f"parent: {par[1]}"
        out[e["g"]] = {"areas": own.get(e["g"], dflt), "default": dflt, "chosen": e["g"] in own, "source": src, "_t": e["_t"], "_m": e["_m"]}
    return out


def _items(conn, p: dict) -> list[dict]:
    rows = _rows(conn, """SELECT i.id AS _id, i.guid::text AS id, i.phase, i.name, i.kind, i.chosen, i.content_area,
                                 coalesce(li.content_area, '') AS library_area, coalesce(li.repository_area, '') AS library_repo
                            FROM proj.items i LEFT JOIN proj.lib_items li ON li.id = i.library_id
                           WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.phase, i.name""", p=p["id"], c=p.get("cycle") or 1)
    parent: dict = {}
    for b in _bases(conn, p):                            # placed by a project above (D317), by library item or name
        for x in _rows(conn, "SELECT library_id AS l, lower(name) AS n, content_area AS a FROM proj.items WHERE project_id = :p AND content_area <> ''",
                       p=b["id"]):
            for k in ((("l", x["l"]),) if x["l"] else ()) + (("n", x["n"]),):
                parent.setdefault(k, (areas_of(x["a"]), b["name"]))
    lib_of = {r["_id"]: r for r in _rows(conn, "SELECT id AS _id, library_id FROM proj.items WHERE project_id = :p", p=p["id"])}
    for r in rows:
        par = parent.get(("l", (lib_of.get(r["_id"]) or {}).get("library_id"))) or parent.get(("n", r["name"].lower()))
        r["default"], _c = area_of_item(r["name"], "", r["library_area"], r["phase"])
        r["source"] = "admin" if areas_of(r["library_area"]) else "built-in"
        if par:
            r["default"], r["source"] = par[0], f"parent: {par[1]}"
        r["chosen_area"] = bool(areas_of(r["content_area"]))
        r["repository"] = repo_of_item(r["name"], r["library_repo"], r["default"])[0]
        r["area"] = areas_of(r["content_area"]) or r["default"]
    return rows


def _tpl(conn, p: dict) -> dict[str, list[str]]:
    """Documents made from a template with areas of its own (D317): document guid -> the template's areas."""
    return {r["g"]: areas_of(r["a"]) for r in _rows(conn, """SELECT d.guid::text AS g, t.content_area AS a FROM proj.documents d
                                                              JOIN proj.lib_templates t ON t.id = d.template_id
                                                             WHERE d.project_id = :p AND t.content_area <> ''""", p=p["id"])}


def _own(conn, p: dict) -> dict[str, list[str]]:
    """The documents placed on their own: guid -> areas."""
    return {r["g"]: areas_of(r["a"]) for r in _rows(conn, """SELECT guid::text AS g, content_area AS a FROM proj.documents
                                                              WHERE project_id = :p AND content_area <> ''""", p=p["id"])}


def overview(conn, project: Any, user) -> dict:
    """The diagram's numbers: per area, the entity types and entities, the document types and documents."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    models = _models(conn, p)
    types = _types(conn, models, p)
    items = _items(conn, p)
    docs = pj.documents(conn, p)
    item_area = {i["id"]: i["area"] for i in items}
    out = {c: {"types": 0, "entities": 0, "doc_types": 0, "documents": 0} for c in LABEL}
    for t in types:
        for a in t["area"]:
            if a in out:
                out[a]["types"] += 1
                out[a]["entities"] += int(t["entities"])
    tarea = {t["_id"]: t["area"] for t in types}
    for e in _entities_off_type(conn, p, models, tarea).values():   # counted where they are, not under their type's areas
        for a in tarea.get(e["_t"], []):
            if a in out:
                out[a]["entities"] -= 1
        for a in e["areas"]:
            if a in out:
                out[a]["entities"] += 1
    for i in items:
        for a in i["area"]:
            if a in out and i["chosen"]:
                out[a]["doc_types"] += 1
    own, tpl = _own(conn, p), _tpl(conn, p)
    for d in docs:
        for a in set(item_area.get(d["item_id"]) or []) | set(own.get(d["id"], [])) | set(tpl.get(d["id"], [])):
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
    all_types = _types(conn, models, p)
    types = [t for t in all_types if here(t["area"])]
    off = _entities_off_type(conn, p, models, {t["_id"]: t["area"] for t in all_types})
    ents: dict[int, list[dict]] = {}
    if types and not unplaced:
        for r in _rows(pj.core(conn), """
                SELECT * FROM (SELECT e.guid::text AS id, e.entity_type_id AS _t, e.name, e.display_id, e.status_code AS status,
                                      row_number() OVER (PARTITION BY e.entity_type_id ORDER BY e.name) AS n
                                 FROM core.entities e WHERE e.entity_type_id = ANY (CAST(:t AS bigint[])) AND NOT e.is_deleted) x
                 WHERE n <= :lim ORDER BY name""", t=[t["_id"] for t in types], lim=MAX_ENTITIES):
            if r["id"] in off and code not in off[r["id"]]["areas"]:       # placed elsewhere on its own
                continue
            ents.setdefault(r.pop("_t"), []).append({k: v for k, v in r.items() if k != "n"} | {"own": r["id"] in off})
    # entities placed here on their own (owner, 8 Nov 2026): a way to reach them from the content framework
    loose_e: dict[int, list[dict]] = {}
    shown_e = {e["id"] for xs in ents.values() for e in xs}
    want = [g for g, e in off.items() if code in e["areas"] and g not in shown_e]
    if want and not unplaced:
        for r in _rows(pj.core(conn), """SELECT e.guid::text AS id, e.model_id AS _m, e.name, e.display_id, e.status_code AS status,
                                                t.name AS type, t.guid::text AS type_id
                                           FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                                          WHERE e.guid = ANY (CAST(:g AS uuid[])) AND NOT e.is_deleted ORDER BY e.name""", g=want):
            loose_e.setdefault(r.pop("_m"), []).append(r)
    tree_models = []
    for m in models:
        mt = [t for t in types if t["_m"] == m["_id"]]
        tree_models.append({"id": m["id"], "name": m["name"], "kind": m["kind"], "own_entities": loose_e.get(m["_id"], []), "types": [
            {"id": t["id"], "name": t["name"], "code": t["code"], "domain": t["domain"], "colour": t["colour"], "chosen": t["chosen"],
             "areas": t["area"],
             "count": int(t["entities"]), "entities": ents.get(t["_id"], []), "more": max(0, int(t["entities"]) - MAX_ENTITIES)}
            for t in mt]})
    items = [i for i in _items(conn, p) if here(i["area"]) and i["chosen"]]       # the document types in the project
    docs = pj.documents(conn, p)
    own, tpl = _own(conn, p), _tpl(conn, p)
    keep = ("id", "file_name", "title", "state", "versions", "user_version", "kind", "is_link", "link_url", "modified_at", "modified_by", "folder")
    doc_types = []
    for i in items:
        doc_types.append({"id": i["id"], "name": i["name"], "phase": i["phase"], "kind": i["kind"], "placed": i["chosen_area"], "areas": i["area"],
                          "documents": [{k: d.get(k) for k in keep} | {"own_areas": _merge(own.get(d["id"], []), tpl.get(d["id"], []))}
                                                                    for d in docs if d["item_id"] == i["id"]]})
    shown = {d["id"] for t in doc_types for d in t["documents"]}
    loose = [{k: d.get(k) for k in keep} | {"type": d["item_id"], "own_areas": _merge(own.get(d["id"], []), tpl.get(d["id"], []))} for d in docs
             if not unplaced and code in own.get(d["id"], []) + tpl.get(d["id"], []) and d["id"] not in shown]
    where = next(({"section": s, "group": g} for c, _l, s, g in AREAS if c == code), {})
    return {"area": None if unplaced else {"code": code, "label": LABEL[code], **where},
            "models": tree_models, "doc_types": doc_types, "documents": loose,
            "areas": [{"code": c, "label": label, "group": g} for c, label, _s, g in AREAS],
            "may_place_documents": _may(conn, p, user, "contribute")}


def _merge(*lists: list[str]) -> list[str]:
    have = {a for xs in lists for a in xs}
    return [c for c in LABEL if c in have]


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


# ---------------------------------------------------------------- tagging (owner, 8 Nov 2026)
# The project's Content framework tab › Tag items: every deliverable and artifact (document class), document, entity type
# of the project's models and entity, with its areas; changed one by one or many at once. Document classes and documents
# are the project's own; entity types and entities are placed for this project only (the metamodel keeps its default).
KINDS = ("classes", "documents", "types", "entities")
MAX_TAG_ROWS = 300


def _chip(r: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items() if not k.startswith("_")}


def tag_list(conn, project: Any, user, kind: str, q: str = "", phase: str = "", area_code: str = "", offset: int = 0) -> dict:
    """The rows of one kind with their areas: areas (where it sits now), default (where it would sit by itself),
    chosen (placed in this project), set_by and set_at."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    if kind not in KINDS:
        raise EditError("Tag deliverables and artifacts, documents, entity types or entities.")
    ql = (q or "").strip().lower()
    rows: list[dict] = []
    if kind == "classes":
        info = {r["g"]: r for r in _rows(conn, """SELECT guid::text AS g, area_set_by, area_set_at, type,
                                                        (SELECT count(*) FROM proj.documents d WHERE d.item_id = i.id AND d.deleted_at IS NULL) AS documents
                                                   FROM proj.items i WHERE project_id = :p""", p=p["id"])}
        for i in _items(conn, p):
            if not i["chosen"]:
                continue
            dflt = i["default"]
            x = info.get(i["id"], {})
            rows.append({"id": i["id"], "name": i["name"], "kind": i["kind"], "phase": i["phase"], "type": x.get("type") or "",
                         "documents": int(x.get("documents") or 0), "areas": i["area"], "default": dflt, "chosen": bool(i["chosen_area"]), "source": i["source"],
                         "repository": i["repository"],
                         "set_by": x.get("area_set_by"), "set_at": x.get("area_set_at")})
    elif kind == "documents":
        items = {i["id"]: i for i in _items(conn, p)}
        by = {r["g"]: r for r in _rows(conn, "SELECT guid::text AS g, area_set_by, area_set_at FROM proj.documents WHERE project_id = :p", p=p["id"])}
        own, tpl = _own(conn, p), _tpl(conn, p)
        for d in pj.documents(conn, p):
            it = items.get(d["item_id"]) or {}
            dflt = _merge(it.get("area") or [], tpl.get(d["id"], []))
            mine = own.get(d["id"], [])
            rows.append({"id": d["id"], "name": d.get("title") or d["file_name"], "file_name": d["file_name"], "class": it.get("name") or "",
                         "phase": it.get("phase") or "", "kind": d.get("kind"), "areas": _merge(dflt, mine), "repository": it.get("repository") or "",
                         "source": "its class and template" if tpl.get(d["id"]) else "its class",
                         "default": dflt, "own": mine, "chosen": bool(mine), "set_by": (by.get(d["id"]) or {}).get("area_set_by"),
                         "set_at": (by.get(d["id"]) or {}).get("area_set_at")})
    elif kind == "types":
        models = _models(conn, p)
        mname = {m["_id"]: m["name"] for m in models}
        mguid = {m["_id"]: m["id"] for m in models}
        by = {str(r["g"]): r for r in _rows(conn, "SELECT type_guid::text AS g, set_by, set_at FROM proj.cf_type_areas WHERE project_id = :p", p=p["id"])}
        for t in _types(conn, models, p):
            rows.append({"id": t["id"], "name": t["name"], "code": t["code"], "model": mname.get(t["_m"], ""), "model_id": mguid.get(t["_m"]), "domain": t["domain"], "entities": int(t["entities"]),
                         "areas": t["area"], "default": t["default_area"], "chosen": t["chosen"] == "project", "source": t["source"],
                         "repository": t["repository"],
                         "set_by": (by.get(t["id"]) or {}).get("set_by"), "set_at": (by.get(t["id"]) or {}).get("set_at")})
    else:                        # entities: many, so found by name and paged
        models = _models(conn, p)
        if models:
            types = {t["_id"]: t for t in _types(conn, models, p)}
            off = _entities_off_type(conn, p, models, {k: t["area"] for k, t in types.items()})
            by = {str(r["g"]): r for r in _rows(conn, "SELECT entity_guid::text AS g, set_by, set_at FROM proj.cf_entity_areas WHERE project_id = :p",
                                                 p=p["id"])}
            mname = {m["_id"]: m["name"] for m in models}
            mguid = {m["_id"]: m["id"] for m in models}
            for e in _rows(pj.core(conn), """SELECT e.guid::text AS id, e.name, e.display_id, e.entity_type_id AS _t, e.model_id AS _m
                                              FROM core.entities e WHERE e.model_id = ANY (CAST(:m AS bigint[])) AND NOT e.is_deleted
                                               AND (:q = '' OR lower(e.name) LIKE :ql OR lower(coalesce(e.display_id, '')) LIKE :ql)
                                             ORDER BY e.name, e.id""", m=[m["_id"] for m in models], q=ql, ql=f"%{ql}%"):
                t = types.get(e["_t"]) or {}
                x = off.get(e["id"]) or {"areas": t.get("area") or [], "default": t.get("area") or [], "chosen": False, "source": "its type"}
                rows.append({"id": e["id"], "name": e["name"], "display_id": e["display_id"], "type": t.get("name") or "",
                             "model": mname.get(e["_m"], ""), "model_id": mguid.get(e["_m"]), "type_id": t.get("id"), "areas": x["areas"], "default": x["default"], "chosen": x["chosen"],
                             "source": x["source"], "repository": t.get("repository") or "",
                             "set_by": (by.get(e["id"]) or {}).get("set_by"), "set_at": (by.get(e["id"]) or {}).get("set_at")})
    phases = sorted({r["phase"] for r in rows if r.get("phase")})
    if ql and kind != "entities":
        rows = [r for r in rows if ql in f"{r['name']} {r.get('class', '')} {r.get('model', '')} {r.get('file_name', '')}".lower()]
    if phase and kind in ("classes", "documents"):
        rows = [r for r in rows if r.get("phase") == phase or (phase == "C" and r.get("phase") in ("C-D", "C-A"))]
    if area_code == "_none":
        rows = [r for r in rows if not r["areas"]]
    elif area_code == "_changed":
        rows = [r for r in rows if r["chosen"]]
    elif area_code:
        rows = [r for r in rows if area_code in r["areas"]]
    total = len(rows)
    rows = rows[offset:offset + MAX_TAG_ROWS]
    return {"kind": kind, "total": total, "offset": offset, "page": MAX_TAG_ROWS, "phases": phases, "rows": [_chip(r) for r in rows],
            "may_place": _may(conn, p, user, "contribute") and not p.get("frozen"), "areas": [{"code": c, "label": lab, "group": g} for c, lab, _s, g in AREAS]}


def place(conn, project: Any, user, kind: str, ids: list[str], how: str, areas: Any = None) -> dict:
    """Areas for several rows of one kind at once: how is set (these areas), add (these areas too), remove (take these
    off) or reset (back to the default). Anyone who contributes to the project."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    if kind not in KINDS:
        raise EditError("Tag deliverables and artifacts, documents, entity types or entities.")
    if how not in ("set", "add", "remove", "reset"):
        raise EditError("Set, add, remove or reset the areas.")
    ids = [str(x) for x in ids or [] if str(x).strip()]
    if not ids:
        raise EditError("Tick at least one row.")
    if len(ids) > 1000:
        raise EditError("1000 rows at most at once.")
    want = areas_of(clean_area(areas)) if how != "reset" else []
    if how in ("set", "add", "remove") and how != "set" and not want:
        raise EditError("Choose the area.")
    cur = {r["id"]: r for r in tag_list(conn, project, user, kind)["rows"]} if kind != "entities" else None
    if kind == "entities":
        cur = {r["id"]: r for r in _entity_rows(conn, p, user, ids)}

    def result(r: dict) -> str:
        base = r.get("own", []) if kind == "documents" else r["areas"]
        if how == "set":
            new = want
        elif how == "add":
            new = list(base) + [a for a in want if a not in base]
        elif how == "remove":
            new = [a for a in base if a not in want]
        else:
            return ""
        return clean_area(new)
    n = 0
    for i in ids:
        r = cur.get(i)
        if not r:
            continue
        v = result(r)
        back = how == "reset" or (kind != "documents" and v == clean_area(r["default"]))   # the same as the default: back to it
        if back:
            v = ""
        if kind == "documents":                            # its own areas: only those its class does not give it already
            v = clean_area([a for a in areas_of(v) if a not in r["default"]])
        if kind == "classes":
            conn.execute(text("""UPDATE proj.items SET content_area = :a, area_set_by = CASE WHEN :a = '' THEN NULL ELSE :u END,
                                        area_set_at = CASE WHEN :a = '' THEN NULL ELSE now() END
                                  WHERE project_id = :p AND guid = CAST(:g AS uuid)"""), {"a": v, "u": user.username, "p": p["id"], "g": i})
        elif kind == "documents":
            conn.execute(text("""UPDATE proj.documents SET content_area = :a, area_set_by = CASE WHEN :a = '' THEN NULL ELSE :u END,
                                        area_set_at = CASE WHEN :a = '' THEN NULL ELSE now() END
                                  WHERE project_id = :p AND guid = CAST(:g AS uuid)"""), {"a": v, "u": user.username, "p": p["id"], "g": i})
        else:
            table, col = ("proj.cf_type_areas", "type_guid") if kind == "types" else ("proj.cf_entity_areas", "entity_guid")
            if back:
                conn.execute(text(f"DELETE FROM {table} WHERE project_id = :p AND {col} = CAST(:g AS uuid)"), {"p": p["id"], "g": i})
            else:
                extra = (", type_code", ", :c", ", type_code = EXCLUDED.type_code") if kind == "types" else ("", "", "")
                conn.execute(text(f"""INSERT INTO {table} (project_id, {col}, areas, set_by{extra[0]}) VALUES (:p, CAST(:g AS uuid), :a, :u{extra[1]})
                                      ON CONFLICT (project_id, {col}) DO UPDATE SET areas = EXCLUDED.areas, set_by = EXCLUDED.set_by,
                                                                                   set_at = now(){extra[2]}"""),
                             {"p": p["id"], "g": i, "a": v, "u": user.username, "c": r.get("code") or ""})
        n += 1
    what = {"reset": "back to their default", "set": f"placed in {labels(clean_area(want)) or 'no area'}",
            "add": f"also in {labels(clean_area(want))}", "remove": f"taken out of {labels(clean_area(want))}"}[how]
    return {"changed": n, "message": f"{n} {'row' if n == 1 else 'rows'} {what}."}


def _entity_rows(conn, p: dict, user, ids: list[str]) -> list[dict]:
    models = _models(conn, p)
    if not models:
        return []
    types = {t["_id"]: t for t in _types(conn, models, p)}
    off = _entities_off_type(conn, p, models, {k: t["area"] for k, t in types.items()})
    out = []
    for e in _rows(pj.core(conn), """SELECT guid::text AS id, entity_type_id AS _t FROM core.entities
                                      WHERE guid = ANY (CAST(:g AS uuid[])) AND model_id = ANY (CAST(:m AS bigint[])) AND NOT is_deleted""",
                   g=ids, m=[m["_id"] for m in models]):
        dflt = (types.get(e["_t"]) or {}).get("area") or []
        x = off.get(e["id"]) or {"areas": dflt, "default": dflt}
        out.append({"id": e["id"], "areas": x["areas"], "default": x["default"]})
    return out


# ---------------------------------------------------------------- admin: the defaults (owner, 8 Nov 2026, D317)
# Where the project library's deliverables and artifacts sit, and each template's own areas over its class's: kept by
# Super Admins and Library Admins on Project admin › Template setup, also while uploading a template. Every project
# starts from these (then its parent's choices, then its own).
def template_setup(conn, user, library: str = "") -> dict:
    pj._need_library(user)
    libs = [{"id": str(lb["guid"]), "name": lb["name"], "kind": lb["kind"], "may_add": lb["kind"] != "ea-explorer"}
            for lb in _rows(conn, "SELECT guid, name, kind FROM proj.template_libraries ORDER BY kind <> 'ea-explorer', name")]
    classes = []
    for i in _rows(conn, "SELECT id, phase, name, kind, type, content_area, repository_area FROM proj.lib_items WHERE NOT retired ORDER BY phase, name"):
        builtin = area_of_item(i["name"], phase=i["phase"])[0]
        own = areas_of(i["content_area"])
        repo, repo_chosen = repo_of_item(i["name"], i["repository_area"], own or builtin)
        classes.append({"id": i["id"], "phase": i["phase"], "name": i["name"], "kind": i["kind"], "type": i["type"] or "",
                        "areas": own or builtin, "default": builtin, "chosen": bool(own), "source": "admin" if own else "built-in",
                        "repository": repo, "repository_chosen": repo_chosen, "repository_default": repo_of_item(i["name"], "", own or builtin)[0]})
    by_id = {c["id"]: c for c in classes}
    out = {"libraries": libs, "classes": classes, "areas": [{"code": c, "label": lab, "group": g} for c, lab, _s, g in AREAS],
           "repository_areas": REPO_AREAS}
    lib = next((x for x in libs if x["id"] == library), libs[0] if libs else None)
    if lib:
        row = pj._library_row(conn, lib["id"])
        tpl = []
        for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=row["id"]):
            c = by_id.get(t["item_id"]) or {}
            tpl.append({"id": t["id"], "path": t["path"], "folder": t["path"].rsplit("/", 1)[0] if "/" in t["path"] else "",
                        "name": t["file_name"] or t["name"] or t["path"].rsplit("/", 1)[-1], "has_file": pj._has_file(t, row["kind"]),
                        "item_id": t["item_id"], "item": c.get("name") or "", "phase": c.get("phase") or t.get("phase") or "",
                        "class_areas": c.get("areas") or template_default(t["path"], t["file_name"] or t["name"] or ""),
                        "areas": areas_of(t["content_area"]),
                        "uploaded_by": t["uploaded_by"], "uploaded_at": t["uploaded_at"].isoformat() if t.get("uploaded_at") else None})
        out |= {"library": lib, "templates": tpl}
    return out


def place_library_repo(conn, user, item: int, value: Any) -> dict:
    """A deliverable's or artifact's Repository Area for every project ('' = the built-in default; Super and Library Admins)."""
    pj._need_library(user)
    v = clean_repo(value)
    it = _one(conn, "SELECT id, name FROM proj.lib_items WHERE id = :i", i=item)
    if not it:
        raise EditError("No such deliverable or artifact in the library.", 404)
    conn.execute(text("UPDATE proj.lib_items SET repository_area = :a WHERE id = :i"), {"a": v, "i": it["id"]})
    return {"message": f"{it['name']}: filed in {v or repo_of_item(it['name'])[0] + ' (built in)'}.", "repository": v}


def place_library_template(conn, user, template_id: int, code: Any) -> dict:
    """A template's own areas, over its deliverable's or artifact's (Super Admins and Library Admins)."""
    pj._need_library(user)
    code = clean_area(code)
    t = _one(conn, "SELECT id, coalesce(nullif(file_name, ''), name, path) AS n FROM proj.lib_templates WHERE id = :i", i=template_id)
    if not t:
        raise EditError("No such template.", 404)
    conn.execute(text("UPDATE proj.lib_templates SET content_area = :a WHERE id = :i"), {"a": code, "i": t["id"]})
    return {"message": f"{t['n']}: {'also in ' + labels(code) if code else 'only where its deliverable or artifact sits'}.", "areas": areas_of(code)}


def add_template(conn, user, library: str, item: Any, file_name: str, content: bytes, areas: Any = None, class_areas: Any = None) -> dict:
    """A new template uploaded into a library (not EA Explorer's own), for a deliverable or artifact, tagged as it is
    uploaded: its own areas, and (when given) its deliverable's or artifact's areas for every project."""
    from . import mayan
    pj._need_library(user)
    lib = pj._library_row(conn, library)
    if lib["kind"] == "ea-explorer":
        raise EditError("EA Explorer's own templates ship with it: download the library, change it and upload it as your own.")
    name = (file_name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    if not name or not content:
        raise EditError("Choose the file.")
    it = _one(conn, "SELECT id, name, work_folder FROM proj.lib_items WHERE id = :i AND NOT retired", i=int(item)) if str(item or "").isdigit() else None
    if item and not it:
        raise EditError("No such deliverable or artifact in the library.", 404)
    folder = it["work_folder"] if it else ""
    path = f"{folder}/{name}" if folder else name
    if _one(conn, "SELECT 1 AS x FROM proj.lib_templates WHERE library_id = :l AND path = :p", l=lib["id"], p=path):
        raise EditError(f"{lib['name']} has {path} already: replace its file instead.", 409)
    root = mayan.cabinet("EA Explorer library templates")
    lc = mayan.cabinet(lib["name"], root)
    doc = mayan.upload(name, content, mimetypes.guess_type(name)[0] or "application/octet-stream", label=f"{lib['name']}-{name}")
    mayan.add_to_cabinet(mayan.cabinet_path(folder, lc) if folder else lc, doc["id"])
    row = _one(conn, """INSERT INTO proj.lib_templates (library_id, path, item_id, source, name, folder, origin, mayan_document_id, file_name,
                                                        uploaded_by, uploaded_at, content_area)
                        VALUES (:l, :p, :i, :s, :n, :f, 'Uploaded', :m, :n, :u, now(), :a) RETURNING id""",
               l=lib["id"], p=path, i=it["id"] if it else None, s=lib["name"], n=name, f=folder, m=doc["id"], u=user.username,
               a=clean_area(areas))
    if it and class_areas is not None:
        place_library_item(conn, user, it["id"], class_areas)
    return {"id": row["id"], "message": f"{name} added to {lib['name']}{' for ' + it['name'] if it else ''}."}
