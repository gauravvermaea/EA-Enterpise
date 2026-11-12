"""TOGAF gap analysis (build phase 8.3, D172).

A gap analysis compares a baseline and a target (each a model as it is now or a tag of one) with a TOGAF
template (which architecture domain it is about) and keeps the result in the model: one gap per element,
kept (TOGAF: included), changed, new (to build or buy) or eliminated (to retire, replace, or an accidental
omission to add back). Each gap carries a note, a resolution and the work packages that close it. Compared
again later, the gaps refresh and keep their notes; gaps that went away are kept, marked gone.

Gaps can also be added to the model as Gap entities (Model Admins; committed at once, D170): each with the
gap analysis, baseline and target (models, tags, commits and metamodel versions), when it was compared, its
status and resolution, and associated with its baseline and target elements and work packages. A model
without a Gap entity type gets one (with its attributes) as a new metamodel version.

Views: the summary, the TOGAF gap matrix, the gap list; reports GR-01 to GR-05 (Superset); downloads as an
Excel workbook and a Word document.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import commits as cm
from . import compare as cp
from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError, _db_message

# TOGAF gap analysis templates (TOGAF Standard, Gap Analysis technique): what each domain's analysis compares
TEMPLATES = [
    {"code": "all", "name": "Whole architecture", "phase": "B, C, D, E",
     "types": None, "purpose": "Every element of every domain: the overall gap between baseline and target."},
    {"code": "business", "name": "Business Architecture gap analysis", "phase": "B",
     "types": ["BusinessActor", "Role", "Collaboration", "BusinessInterface", "BusinessObject", "Product", "Process", "Function",
               "Service", "Event", "Capability", "ValueStream", "Location"],
     "purpose": "Organisation, actors, roles, business services, processes and functions, products and capabilities."},
    {"code": "data", "name": "Data Architecture gap analysis", "phase": "C (data)",
     "types": ["BusinessObject", "DataObject", "Artifact"],
     "purpose": "Business and data objects, and how they are realised: the data entities to add, change or retire."},
    {"code": "application", "name": "Application Architecture gap analysis", "phase": "C (application)",
     "types": ["ApplicationComponent", "ApplicationInterface", "Service", "Process", "Function", "DataObject"],
     "purpose": "Application components, their interfaces and services: applications to build, buy, retire or replace."},
    {"code": "technology", "name": "Technology Architecture gap analysis", "phase": "D",
     "types": ["Node", "Device", "SystemSoftware", "TechnologyInterface", "CommunicationNetwork", "Path", "DistributionNetwork",
               "Equipment", "Facility", "Artifact", "Material", "Service"],
     "purpose": "Platforms, system software, devices and networks: technology to introduce, upgrade or decommission."},
    {"code": "capability", "name": "Capability gap analysis", "phase": "A, B, E",
     "types": ["Capability", "ValueStream", "Resource", "CourseOfAction"],
     "purpose": "Capabilities, value streams and resources: capability-based planning of what the target needs."},
    {"code": "motivation", "name": "Requirements and motivation gap analysis", "phase": "Requirements management",
     "types": ["Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle", "Requirement"],
     "purpose": "Drivers, goals, outcomes, principles and requirements the target adds or drops."},
]
TOGAF_CELLS = {"kept": "Included", "changed": "Changed", "new": "New: to be developed or procured",
               "eliminated": "Eliminated: intentionally retired, or an accidental omission to add back"}
RESOLUTIONS = ["Retain", "Enhance", "Build", "Buy", "Replace", "Migrate", "Retire", "Accidental omission: add back",
               "Not a gap"]
GAP_ATTRS = [  # code, name, data type, pick list, description
    ("GapStatus", "Gap Status", "list", "GapStatus", "Kept, changed, new or eliminated"),
    ("GapResolution", "Gap Resolution", "list", "GapResolution", "How the gap is closed"),
    ("GapAnalysis", "Gap Analysis", "text", None, "The gap analysis it comes from"),
    ("GapBaseline", "Baseline", "text", None, "The baseline compared: model or tag, commit and metamodel version"),
    ("GapTarget", "Target", "text", None, "The target compared: model or tag, commit and metamodel version"),
    ("GapComparedAt", "Compared On", "date", None, "When the baseline and target were compared"),
]


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _exec(conn, sql: str, **p):
    return conn.execute(text(sql), p)


def templates() -> dict:
    return {"templates": TEMPLATES, "resolutions": RESOLUTIONS, "cells": TOGAF_CELLS}


def _template(code: str) -> dict:
    t = next((x for x in TEMPLATES if x["code"] == (code or "all")), None)
    if not t:
        raise EditError(f"No gap template {code!r}: one of {', '.join(x['code'] for x in TEMPLATES)}.")
    return t


def settings_for(template: str, info: dict, settings: dict | None) -> dict:
    """The comparison settings of a gap analysis: the template's entity types (those either side has), with
    the default fields; or the person's own choice."""
    if settings and settings.get("types"):
        return settings
    t = _template(template)
    base = cp.defaults(info)
    types = {c: f for c, f in base["types"].items() if t["types"] is None or c in t["types"]}
    if not types:   # a metamodel without the template's types: every type
        types = base["types"]
    return {**base, "types": types, "metamodel": False}


def _may(conn, user, m: dict) -> None:
    roles = set(perms.model_roles(conn, user.username, m["id"]))
    if not (perms.SUPER_ADMIN in user.roles or roles & set(perms.MODEL_PERMISSIONS["model.content"])):
        raise EditError(f"Gap analyses on {m['name']} need a role that changes its content (Architect, Committer, Model Sub Admin "
                        "or Model Admin).", 403)


def _may_store(m: dict) -> None:
    if m["kind"] != "project" or m.get("is_locked"):
        raise EditError(f"Gaps are stored in a project model that is not locked; {m['name']} is "
                        f"{'locked' if m.get('is_locked') else 'a ' + str(m['kind']) + ' model'}.", 409)


def _side_label(side: dict) -> dict:
    return {**cp._label(side), "created_at": str(side.get("created_at") or "")}


# ---------------------------------------------------------------- analyses
def create(conn, model: Any, user, name: str, baseline: dict, target: dict, template: str = "all", settings: dict | None = None,
           description: str = "") -> dict:
    """A new gap analysis stored in the model given (any project model that is not locked, and may be the baseline's
    or the target's): the two sides (any models you may read, as they are now or a tag of each) compared with the
    template, the gaps stored. The storage model's roles decide who sees and works on it (D177)."""
    m = repo.get_model(conn, model)
    _may_store(m)
    _may(conn, user, m)
    if not (name or "").strip():
        raise EditError("Give the gap analysis a name, for example Application baseline 2026 to target 2028.")
    _template(template)
    left, right = cp.load_side(conn, baseline), cp.load_side(conn, target)
    st = settings_for(template, cp.fields_for(left, right), settings)
    result = cp.compare(left, right, st)
    try:
        row = _one(conn, """INSERT INTO core.gap_analyses (model_id, name, description, template, baseline, target, settings, summary,
                                                           compared_by, created_by)
                            VALUES (:m, :n, :d, :t, CAST(:b AS jsonb), CAST(:g AS jsonb), CAST(:s AS jsonb), CAST(:sum AS jsonb), :u, :u)
                            RETURNING id, guid""",
                   m=m["_id"], n=name.strip(), d=(description or "").strip(), t=template or "all",
                   b=json.dumps({**_side_label(left), "request": baseline}, default=str),
                   g=json.dumps({**_side_label(right), "request": target}, default=str),
                   s=json.dumps(st), sum=json.dumps({"totals": result["totals"], "summary": result["summary"]}), u=user.username.lower())
    except DBAPIError as exc:
        raise EditError(f"{m['name']} already has a gap analysis called '{name.strip()}'." if "gap_analyses_name_idx" in str(exc.orig)
                        else _db_message(exc), 409) from exc
    _store_items(conn, row["id"], result, user)
    _new_run(conn, row["id"], user)
    return get(conn, str(m["id"]), str(row["guid"]))


def _key(i: dict) -> str:
    return f"{(i['left'] or {}).get('guid') or ''}|{(i['right'] or {}).get('guid') or ''}"


def _store_items(conn, analysis_id: int, result: dict, user) -> None:
    keys = []
    for i in result["items"]:
        k = _key(i)
        keys.append(k)
        _exec(conn, """INSERT INTO core.gap_items (analysis_id, match_key, entity_type, entity_type_name, layer, name, status,
                                                   baseline_guid, baseline_name, target_guid, target_name, changes, gone)
                       VALUES (:a, :k, :t, :tn, :l, :n, :s, CAST(:bg AS uuid), :bn, CAST(:tg AS uuid), :tgn, CAST(:c AS jsonb), false)
                       ON CONFLICT (analysis_id, match_key) DO UPDATE SET entity_type = EXCLUDED.entity_type,
                           entity_type_name = EXCLUDED.entity_type_name, layer = EXCLUDED.layer, name = EXCLUDED.name,
                           status = EXCLUDED.status, baseline_name = EXCLUDED.baseline_name, target_name = EXCLUDED.target_name,
                           changes = EXCLUDED.changes, gone = false""",
              a=analysis_id, k=k, t=i["entity_type"], tn=i["entity_type_name"], l=i["domain"] or "", n=i["name"], s=i["status"],
              bg=(i["left"] or {}).get("guid"), bn=(i["left"] or {}).get("name"), tg=(i["right"] or {}).get("guid"),
              tgn=(i["right"] or {}).get("name"), c=json.dumps(i["changes"], default=str))
    _exec(conn, "UPDATE core.gap_items SET gone = true WHERE analysis_id = :a AND NOT (match_key = ANY (CAST(:k AS text[])))",
          a=analysis_id, k=keys or [""])


def _new_run(conn, analysis_id: int, user) -> int:
    """Keeps this result of the analysis as its next numbered run."""
    a = _one(conn, "SELECT baseline, target FROM core.gap_analyses WHERE id = :i", i=analysis_id)
    items = _rows(conn, """SELECT match_key AS key, entity_type, entity_type_name, layer AS domain, name, status, resolution, note, changes
                             FROM core.gap_items WHERE analysis_id = :a AND NOT gone ORDER BY id""", a=analysis_id)
    for i in items:
        i["changes"] = cm._json(i["changes"])
    totals = {s: sum(1 for i in items if i["status"] == s) for s in ("kept", "changed", "new", "eliminated")}
    n = _one(conn, """UPDATE core.gap_analyses SET runs_made = greatest(runs_made,
                          (SELECT coalesce(max(number), 0) FROM core.gap_runs WHERE analysis_id = :a)) + 1
                      WHERE id = :a RETURNING runs_made AS n""", a=analysis_id)["n"]
    _exec(conn, """INSERT INTO core.gap_runs (analysis_id, number, compared_by, baseline, target, totals, items)
                   VALUES (:a, :n, :u, CAST(:b AS jsonb), CAST(:t AS jsonb), CAST(:tot AS jsonb), CAST(:i AS jsonb))""",
          a=analysis_id, n=n, u=user.username.lower(), b=json.dumps(cm._json(a["baseline"]), default=str),
          t=json.dumps(cm._json(a["target"]), default=str), tot=json.dumps(totals), i=json.dumps(items, default=str))
    return n


def _analysis(conn, m: dict, analysis: Any) -> dict:
    g = repo._as_guid(analysis)
    a = _one(conn, "SELECT * FROM core.gap_analyses WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not a:
        raise EditError("No such gap analysis in this model.", 404)
    return a


def refresh(conn, model: Any, user, analysis: Any) -> dict:
    """Compares the two sides again (a model side as it is now; a tag never changes): gaps refresh, notes,
    resolutions, work packages and Gap entities are kept; gaps that went away are kept, marked gone."""
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    b, t = cm._json(a["baseline"]), cm._json(a["target"])
    left, right = cp.load_side(conn, b["request"]), cp.load_side(conn, t["request"])
    result = cp.compare(left, right, cm._json(a["settings"]))
    _exec(conn, """UPDATE core.gap_analyses SET baseline = CAST(:b AS jsonb), target = CAST(:t AS jsonb), summary = CAST(:s AS jsonb),
                   compared_at = now(), compared_by = :u WHERE id = :i""",
          b=json.dumps({**_side_label(left), "request": b["request"]}, default=str),
          t=json.dumps({**_side_label(right), "request": t["request"]}, default=str),
          s=json.dumps({"totals": result["totals"], "summary": result["summary"]}), u=user.username.lower(), i=a["id"])
    _store_items(conn, a["id"], result, user)
    _new_run(conn, a["id"], user)
    return get(conn, str(m["id"]), str(a["guid"]))


def list_analyses(conn, model: Any = None) -> dict:
    """The gap analyses you may see (those stored in models you may read), or those stored in one model."""
    m = repo.get_model(conn, model) if model else None
    rows = _rows(conn, """SELECT a.guid AS id, a.name, a.description, a.template, a.baseline ->> 'label' AS baseline,
                                 a.target ->> 'label' AS target, a.compared_at, a.compared_by, a.created_by,
                                 x.guid AS model_id, x.name AS model_name,
                                 a.baseline ->> 'model_id' AS baseline_model, a.target ->> 'model_id' AS target_model,
                                 (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status <> 'kept') AS gaps,
                                 (SELECT count(*) FROM core.gap_items i WHERE i.analysis_id = a.id AND NOT i.gone AND i.status <> 'kept'
                                     AND i.resolution = '') AS undecided
                            FROM core.gap_analyses a JOIN core.models x ON x.id = a.model_id AND NOT x.is_deleted
                           WHERE (CAST(:m AS bigint) IS NULL OR a.model_id = :m) ORDER BY a.compared_at DESC""", m=m["_id"] if m else None)
    for r in rows:
        r["id"], r["model_id"] = str(r["id"]), str(r["model_id"])
        r["template_name"] = _template(r["template"])["name"] if any(x["code"] == r["template"] for x in TEMPLATES) else r["template"]
    return {"analyses": rows, **templates()}


def model_of(conn, analysis: Any) -> str:
    """The model a gap analysis is stored in (when you may read it)."""
    g = repo._as_guid(analysis)
    r = _one(conn, """SELECT x.guid FROM core.gap_analyses a JOIN core.models x ON x.id = a.model_id WHERE a.guid = :g""",
             g=str(g)) if g else None
    if not r:
        raise EditError("No such gap analysis, or you may not read the model it is stored in.", 404)
    return str(r["guid"])


def get(conn, model: Any, analysis: Any) -> dict:
    m = repo.get_model(conn, model)
    a = _analysis(conn, m, analysis)
    items = _rows(conn, """SELECT i.guid AS id, i.entity_type, i.entity_type_name, i.layer AS domain, i.name, i.status, i.baseline_guid,
                                  i.baseline_name, i.target_guid, i.target_name, i.changes, i.note, i.resolution, i.work_packages,
                                  i.gap_entity, i.gone, i.modified_by, i.modified_at
                             FROM core.gap_items i WHERE i.analysis_id = :a
                            ORDER BY i.gone, CASE i.status WHEN 'new' THEN 1 WHEN 'eliminated' THEN 2 WHEN 'changed' THEN 3 ELSE 4 END,
                                     i.layer, i.entity_type_name, lower(i.name)""", a=a["id"])
    here = {str(r["guid"]): r for r in _rows(conn, """SELECT guid, name, is_deleted FROM core.entities WHERE model_id = :m
                                                       AND (guid = ANY (CAST(:g AS uuid[])))""",
                                              m=m["_id"], g=list({str(x) for i in items for x in [i["baseline_guid"], i["target_guid"],
                                                                                                  i["gap_entity"], *(i["work_packages"] or [])]
                                                                  if x}) or ["00000000-0000-0000-0000-000000000000"])}
    for i in items:
        i["id"] = str(i["id"])
        i["changes"] = cm._json(i["changes"])
        for k in ("baseline_guid", "target_guid", "gap_entity"):
            i[k] = cm._s(i[k])
        i["baseline_here"] = bool(i["baseline_guid"] and i["baseline_guid"] in here and not here[i["baseline_guid"]]["is_deleted"])
        i["target_here"] = bool(i["target_guid"] and i["target_guid"] in here and not here[i["target_guid"]]["is_deleted"])
        i["work_packages"] = [{"id": str(w), "name": (here.get(str(w)) or {}).get("name") or "(gone)"} for w in (i["work_packages"] or [])]
        i["togaf_cell"] = TOGAF_CELLS[i["status"]]
    t = _template(a["template"]) if any(x["code"] == a["template"] for x in TEMPLATES) else {"code": a["template"], "name": a["template"]}
    live = [i for i in items if not i["gone"]]
    runs = _rows(conn, """SELECT guid AS id, number, compared_at, compared_by, totals FROM core.gap_runs WHERE analysis_id = :a
                           ORDER BY number DESC""", a=a["id"])
    for r in runs:
        r["id"] = str(r["id"])
        r["totals"] = cm._json(r["totals"])
        r["tag"] = run_tag(a["name"], r["number"])
    return {"id": str(a["guid"]), "name": a["name"], "description": a["description"], "template": t,
            "model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"], "is_locked": bool(m.get("is_locked"))},
            "baseline": cm._json(a["baseline"]), "target": cm._json(a["target"]), "settings": cm._json(a["settings"]),
            "compared_at": a["compared_at"], "compared_by": a["compared_by"], "created_by": a["created_by"],
            "totals": {s: sum(1 for i in live if i["status"] == s) for s in ("kept", "changed", "new", "eliminated")},
            "undecided": sum(1 for i in live if i["status"] != "kept" and not i["resolution"]),
            "items": items, "resolutions": RESOLUTIONS, "cells": TOGAF_CELLS, "runs": runs,
            "run": runs[0]["number"] if runs else None, "tags": [analysis_tag(a["name"]), run_tag(a["name"], runs[0]["number"])] if runs else []}


def item_detail(conn, model: Any, analysis: Any, item: Any) -> dict:
    """One gap side by side: the element in the baseline and in the target (every field, value and relationship),
    the differences marked. A model side is shown as it is now; a tag as frozen."""
    m = repo.get_model(conn, model)
    a = _analysis(conn, m, analysis)
    g = repo._as_guid(item)
    i = _one(conn, "SELECT * FROM core.gap_items WHERE guid = :g AND analysis_id = :a", g=str(g), a=a["id"]) if g else None
    if not i:
        raise EditError("No such gap in this analysis.", 404)
    b, t = cm._json(a["baseline"]), cm._json(a["target"])
    left, right = cp.load_side(conn, b["request"]), cp.load_side(conn, t["request"])
    out = cp.entity_detail(left, right, str(i["baseline_guid"]) if i["baseline_guid"] else None,
                           str(i["target_guid"]) if i["target_guid"] else None)
    out["gap"] = {"id": str(i["guid"]), "name": i["name"], "status": i["status"], "togaf_cell": TOGAF_CELLS[i["status"]],
                  "resolution": i["resolution"], "note": i["note"]}
    return out


def update_item(conn, model: Any, user, analysis: Any, item: Any, note: str | None = None, resolution: str | None = None,
                work_packages: list | None = None) -> dict:
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    g = repo._as_guid(item)
    i = _one(conn, "SELECT id FROM core.gap_items WHERE guid = :g AND analysis_id = :a", g=str(g), a=a["id"]) if g else None
    if not i:
        raise EditError("No such gap in this analysis.", 404)
    sets, p = ["modified_by = :u", "modified_at = now()"], {"u": user.username.lower(), "i": i["id"]}
    if note is not None:
        sets.append("note = :note")
        p["note"] = note.strip()
    if resolution is not None:
        sets.append("resolution = :res")
        p["res"] = resolution.strip()
    if work_packages is not None:
        wps = []
        for w in work_packages:
            wg = repo._as_guid(w)
            e = _one(conn, """SELECT e.guid FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                               WHERE e.guid = :g AND e.model_id = :m AND NOT e.is_deleted""", g=str(wg), m=m["_id"]) if wg else None
            if not e:
                raise EditError("A work package must be an entity of this model.", 409)
            wps.append(str(e["guid"]))
        sets.append("work_packages = CAST(:w AS uuid[])")
        p["w"] = wps
    _exec(conn, f"UPDATE core.gap_items SET {', '.join(sets)} WHERE id = :i", **p)
    return {"updated": str(g)}


def update_items(conn, model: Any, user, analysis: Any, items: list, resolution: str | None = None, note: str | None = None) -> dict:
    """The same resolution (or note) for many gaps at once."""
    for i in items:
        update_item(conn, model, user, analysis, i, note=note, resolution=resolution)
    return {"updated": len(items)}


def delete(conn, model: Any, user, analysis: Any) -> dict:
    """Deletes a gap analysis with its results, notes and decisions, and the Gap entities made from it in the model,
    at once (D189, D193: no draft or approval; needs the Model Admin role when there are any). Like any delete, the
    entities leave the model, its reports and search; the history keeps them."""
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    deleted, done = _delete_gap_entities(conn, m, user, analysis_tag(a["name"]), None, f"the gap analysis {a['name']}")
    _exec(conn, "DELETE FROM core.gap_analyses WHERE id = :i", i=a["id"])
    return {"deleted": str(a["guid"]), "name": a["name"], "gap_entities_deleted": deleted,
            "commit_number": done["number"] if done else None,
            "note": f"Deleted the gap analysis {a['name']}" + (f" and its {deleted} Gap entities" if deleted else "") + "."}


def _delete_gap_entities(conn, m: dict, user, tag: str, keep_if_other_run: str | None, what: str) -> tuple[int, dict | None]:
    """Deletes the model's Gap entities carrying tag, in one commit at once. With keep_if_other_run (a result's tag), an
    entity that another result also brought up to date only loses that tag. Returns (deleted, commit)."""
    found = _rows(conn, """SELECT e.guid, e.name, e.tags FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                            WHERE e.model_id = :m AND NOT e.is_deleted AND t.code = 'Gap' AND CAST(:tag AS text) = ANY (e.tags)""",
                  m=m["_id"], tag=tag)
    ops = []
    for e in found:
        others = [t for t in _tag_list(e["tags"]) if t.startswith("gap-run: ") and t != keep_if_other_run] if keep_if_other_run else []
        if others:
            ops.append(("entity.update", {"entity": str(e["guid"]), "data": {"tags": [t for t in _tag_list(e["tags"]) if t != tag]}}))
        else:
            ops.append(("entity.delete", {"entity": str(e["guid"])}))
    if not ops:
        return 0, None
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"{what[0].upper()}{what[1:]} has {len(ops)} Gap entities in {m['name']}; deleting them with it needs the "
                        "Model Admin role there (they are removed at once, as they were added).", 403)
    if (m.get("lock_level") or "none") != "none" or m.get("is_locked") or not cm.uses_commits(m):
        raise EditError(f"{m['name']} is read-only or locked: unlock it to delete {what} and its Gap entities.", 409)
    results = cm.record_many(conn, str(m["id"]), user.username, ops)
    bad = [x["error"] for x in results if not x["ok"]]
    if bad:
        raise EditError(f"Could not delete the Gap entities of {what}: {bad[0]}", 409)
    ids = [x["kept"]["change"] for x in results if x.get("kept")]
    done = cm.commit(conn, str(m["id"]), user, None, ids, None, f"Deleted {what} and its Gap entities") if ids else None
    gone = [str(e["guid"]) for (op, _), e in zip(ops, found, strict=True) if op == "entity.delete"]
    if gone:
        _exec(conn, "UPDATE core.gap_items SET gap_entity = NULL WHERE gap_entity = ANY (CAST(:g AS uuid[]))", g=gone)
    return len(gone), done


# ---------------------------------------------------------------- tags on Gap entities, and comparing two results
def _tag_text(name: str) -> str:
    return " ".join(str(name).replace(",", " ").split())[:80].lower()   # entity tags are kept in lower case


def analysis_tag(name: str) -> str:
    """The tag every Gap entity of an analysis carries (find, filter and report its gaps)."""
    return f"gap-analysis: {_tag_text(name)}"


def run_tag(name: str, number: int) -> str:
    """The tag of one result (run) of an analysis: the Gap entities made or brought up to date from it."""
    return f"gap-run: {_tag_text(name)} #{number}"


def list_runs(conn, model: Any = None, q: str | None = None, analysis: Any = None) -> dict:
    """Every result (run) of every gap analysis you may see (or of those stored in one model, or of one analysis), newest
    first; q filters on the analysis name, the result number and the baseline and target."""
    m = repo.get_model(conn, model) if model else None
    ag = repo._as_guid(analysis) if analysis else None
    rows = _rows(conn, """SELECT r.guid AS id, r.number, r.compared_at, r.compared_by, r.totals, a.guid AS analysis_id,
                                 a.name AS analysis, a.template, r.baseline ->> 'label' AS baseline, r.target ->> 'label' AS target,
                                 x.name AS model_name, x.guid AS model_id,
                                 (SELECT max(number) FROM core.gap_runs z WHERE z.analysis_id = a.id) AS latest
                            FROM core.gap_runs r JOIN core.gap_analyses a ON a.id = r.analysis_id
                            JOIN core.models x ON x.id = a.model_id AND NOT x.is_deleted
                           WHERE (CAST(:m AS bigint) IS NULL OR a.model_id = :m)
                             AND (CAST(:ag AS uuid) IS NULL OR a.guid = CAST(:ag AS uuid))
                             AND (CAST(:q AS text) IS NULL
                                  OR concat_ws(' ', a.name, '#' || r.number, r.baseline ->> 'label', r.target ->> 'label', x.name)
                                     ILIKE '%' || CAST(:q AS text) || '%')
                           ORDER BY r.compared_at DESC, r.number DESC""",
                 m=m["_id"] if m else None, ag=str(ag) if ag else None, q=(q or "").strip() or None)
    for r in rows:
        r["id"], r["analysis_id"], r["model_id"], r["totals"] = str(r["id"]), str(r["analysis_id"]), str(r["model_id"]), cm._json(r["totals"])
        r["label"] = f"{r['analysis']} #{r['number']} ({str(r['compared_at'])[:16].replace('T', ' ')})"
        r["is_latest"] = r.pop("latest") == r["number"]
    return {"runs": rows}


def run_info(conn, run: Any) -> dict:
    """The model a result is stored in (the model of its analysis: its roles decide who may delete it) and its name."""
    r = _run(conn, run)
    m = _one(conn, "SELECT m.guid FROM core.gap_analyses a JOIN core.models m ON m.id = a.model_id WHERE a.id = :i", i=r["analysis_id"])
    return {"model": str(m["guid"]), "name": f"{r['analysis']} #{r['number']}"}


def _tag_list(tags) -> list[str]:
    if isinstance(tags, str):
        return [t for t in tags.strip("{}").replace('"', "").split(",") if t]
    return list(tags or [])


def delete_run(conn, model: Any, user, run: Any) -> dict:
    """Deletes one result of a gap analysis, and the Gap entities made from it, at once (D189: Gap entities are the
    one kind of content deleted without a draft or approval, as they are added). A Gap entity that a later result
    brought up to date (it carries another result's tag too) only loses this result's tag. The analysis keeps its gaps,
    notes, resolutions and other results; a deleted result's number is never used again."""
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    r = _run(conn, run)
    label = f"{r['analysis']} #{r['number']}"
    tag = run_tag(r["analysis"], r["number"])
    before = len(_rows(conn, """SELECT 1 AS x FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                                 WHERE e.model_id = :m AND NOT e.is_deleted AND t.code = 'Gap' AND CAST(:tag AS text) = ANY (e.tags)""",
                         m=m["_id"], tag=tag))
    deleted, done = _delete_gap_entities(conn, m, user, tag, tag, f"the result {label}")
    _exec(conn, "DELETE FROM core.gap_runs WHERE id = :i", i=r["id"])
    untagged = before - deleted
    return {"deleted": str(r["guid"]), "name": label, "gap_entities_deleted": deleted, "gap_entities_untagged": untagged,
            "commit_number": done["number"] if done else None,
            "note": f"Deleted {label}" + (f" and {deleted} Gap entities" if deleted else "")
                    + (f"; {untagged} Gap entities kept for a later result lost its tag" if untagged else "") + "."}


def _run(conn, run: Any) -> dict:
    g = repo._as_guid(run)
    r = _one(conn, """SELECT r.*, a.name AS analysis FROM core.gap_runs r JOIN core.gap_analyses a ON a.id = r.analysis_id
                        JOIN core.models x ON x.id = a.model_id WHERE r.guid = :g""", g=str(g)) if g else None
    if not r:
        raise EditError("No such gap analysis result, or you may not read the model it is stored in.", 404)
    return r


def compare_runs(conn, run_a: Any, run_b: Any) -> dict:
    """Two gap results side by side (two runs of one analysis, or of two analyses): each element's status and
    resolution in each, and what happened: a gap closed, a new gap, a status or resolution changed, unchanged."""
    a, b = _run(conn, run_a), _run(conn, run_b)
    ia, ib = cm._json(a["items"]), cm._json(b["items"])

    def keys(i):
        return [i["key"], f"{i['entity_type']}|{i['name'].strip().lower()}"]
    index_b: dict[str, dict] = {}
    for i in ib:
        for k in keys(i):
            index_b.setdefault(k, i)
    used, rows = set(), []
    for i in ia:
        j = next((index_b[k] for k in keys(i) if k in index_b and id(index_b[k]) not in used), None)
        if j is not None:
            used.add(id(j))
        rows.append(_pair(i, j))
    for j in ib:
        if id(j) not in used:
            rows.append(_pair(None, j))
    order = ("New gap", "Gap closed", "Status changed", "Resolution changed", "Unchanged gap", "Not a gap in either")
    rows.sort(key=lambda r: (order.index(r["change"]), r["domain"], r["entity_type_name"], r["name"].lower()))
    counts = {c: sum(1 for r in rows if r["change"] == c) for c in order}
    label = lambda r: f"{r['analysis']} #{r['number']} ({str(r['compared_at'])[:16].replace('T', ' ')})"  # noqa: E731
    return {"a": {"label": label(a), "baseline": cm._json(a["baseline"]).get("label"), "target": cm._json(a["target"]).get("label"),
                  "totals": cm._json(a["totals"])},
            "b": {"label": label(b), "baseline": cm._json(b["baseline"]).get("label"), "target": cm._json(b["target"]).get("label"),
                  "totals": cm._json(b["totals"])},
            "counts": counts, "rows": rows}


def _pair(i: dict | None, j: dict | None) -> dict:
    gap_a = bool(i and i["status"] != "kept")
    gap_b = bool(j and j["status"] != "kept")
    if gap_a and not gap_b:
        change = "Gap closed"
    elif gap_b and not gap_a:
        change = "New gap"
    elif not gap_a and not gap_b:
        change = "Not a gap in either"
    elif i["status"] != j["status"]:
        change = "Status changed"
    elif (i.get("resolution") or "") != (j.get("resolution") or ""):
        change = "Resolution changed"
    else:
        change = "Unchanged gap"
    x = j or i
    return {"entity_type_name": x["entity_type_name"], "domain": x.get("domain") or "", "name": x["name"],
            "status_a": (i or {}).get("status") or "", "status_b": (j or {}).get("status") or "",
            "resolution_a": (i or {}).get("resolution") or "", "resolution_b": (j or {}).get("resolution") or "",
            "note_a": (i or {}).get("note") or "", "note_b": (j or {}).get("note") or "",
            "fields_a": ", ".join(c["label"] for c in (i or {}).get("changes") or []),
            "fields_b": ", ".join(c["label"] for c in (j or {}).get("changes") or []), "change": change}


RUN_COLUMNS = [("What happened", "change"), ("Domain", "domain"), ("Entity type", "entity_type_name"), ("Element", "name"),
               ("Status A", "status_a"), ("Status B", "status_b"), ("Resolution A", "resolution_a"),
               ("Resolution B", "resolution_b"), ("Fields changed A", "fields_a"), ("Fields changed B", "fields_b"),
               ("Note A", "note_a"), ("Note B", "note_b")]


def runs_to_csv(res: dict) -> bytes:
    """The comparison of two gap results as CSV (UTF-8 with a byte order mark, so spreadsheets read accents)."""
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"A: {res['a']['label']}", f"B: {res['b']['label']}"])
    w.writerow([h for h, _ in RUN_COLUMNS])
    for r in res["rows"]:
        w.writerow([r[k] for _, k in RUN_COLUMNS])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def runs_to_xlsx(res: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")
    fills = {"New gap": "E3F4E6", "Gap closed": "DDEBF7", "Status changed": "FFF4D6", "Resolution changed": "FFF4D6"}
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Comparing two gap analysis results"])
    ws["A1"].font = Font(bold=True, size=14)
    for k in ("a", "b"):
        r = res[k]
        ws.append([f"Result {k.upper()}", r["label"], f"baseline {r['baseline']}", f"target {r['target']}",
                   ", ".join(f"{s} {n}" for s, n in (r["totals"] or {}).items())])
    ws.append([])
    ws.append(["What happened", "Elements"])
    for c in ws[ws.max_row]:
        c.font, c.fill = bold, head
    for k, v in res["counts"].items():
        ws.append([k, v])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 26, 60
    cs = wb.create_sheet("Comparison")
    cols = ["What happened", "Domain", "Entity type", "Element", "Status A", "Status B", "Resolution A", "Resolution B",
            "Fields changed A", "Fields changed B", "Note A", "Note B"]
    cs.append(cols)
    for c in cs[1]:
        c.font, c.fill = bold, head
    for r in res["rows"]:
        cs.append([r["change"], r["domain"], r["entity_type_name"], r["name"], r["status_a"], r["status_b"], r["resolution_a"],
                   r["resolution_b"], r["fields_a"], r["fields_b"], r["note_a"], r["note_b"]])
        if r["change"] in fills:
            for c in cs[cs.max_row]:
                c.fill = PatternFill("solid", fgColor=fills[r["change"]])
    cs.freeze_panes = "A2"
    for col in cs.columns:
        cs.column_dimensions[col[0].column_letter].width = min(50, max(10, *(len(str(c.value or "")) for c in col[:200])))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- gaps as Gap entities
def _ensure_gap_type(conn, m: dict, user) -> int | None:
    """Adds a Gap entity type (with its attributes, pick lists and associations) to a metamodel without one."""
    spec = mo.metamodel_spec(conn, str(m["id"]))
    types = {t["code"].lower(): t for t in spec["entity_types"]}
    attrs = {a["code"].lower() for a in spec["attributes"]}
    want_attrs = [a for a in GAP_ATTRS if a[0].lower() not in attrs]
    gap = types.get("gap")
    if gap and not want_attrs and {a[0].lower() for a in GAP_ATTRS} <= {i["attribute"].lower() for i in gap.get("attributes") or []}:
        return None
    lists = {p["code"].lower() for p in spec["pick_lists"]}
    if "gapstatus" not in lists:
        spec["pick_lists"].append({"code": "GapStatus", "name": "Gap Status", "description": "TOGAF gap analysis status",
                                   "values": ["Changed", "New", "Eliminated", "Kept"]})
    if "gapresolution" not in lists:
        spec["pick_lists"].append({"code": "GapResolution", "name": "Gap Resolution", "description": "How a gap is closed",
                                   "values": RESOLUTIONS})
    for code, name, dt, pl, desc in want_attrs:
        spec["attributes"].append({"code": code, "name": name, "data_type": dt, "pick_list": pl, "unit": "", "description": desc})
    domain = (types.get("workpackage") or {}).get("domain") or (spec["domains"][0]["code"] if spec["domains"] else None)
    if not domain:
        raise EditError("The metamodel has no domain to put a Gap entity type in.", 409)
    items = [{"attribute": c, "required": False, "section": "Gap", "default": None, "help": d} for c, _n, _t, _p, d in GAP_ATTRS]
    if gap:
        have = {i["attribute"].lower() for i in gap.get("attributes") or []}
        gap.setdefault("attributes", []).extend(i for i in items if i["attribute"].lower() not in have)
    else:
        spec["entity_types"].append({"code": "Gap", "name": "Gap", "domain": domain, "id_prefix": "GAP", "aspect": "",
                                     "description": "A difference between a baseline and a target architecture (TOGAF gap analysis)",
                                     "status": "published", "attributes": items})
    rel = next((r for r in spec["relationship_types"] if r["code"].lower() == "association"), None)
    if rel:
        have_allowed = {(a["source"].lower(), a["relationship"].lower(), a["target"].lower()) for a in spec["allowed"]}
        for t in spec["entity_types"]:
            for s, tg in (("Gap", t["code"]), (t["code"], "Gap")):
                if (s.lower(), "association", tg.lower()) not in have_allowed:
                    spec["allowed"].append({"source": s, "relationship": rel["code"], "target": tg, "note": "Gap analysis"})
    version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                           {"m": m["_id"], "n": f"Gap entity type for gap analyses ({user.username})"}).scalar_one()
    mo.apply_spec(conn, m["_id"], spec, "merge")
    return version


def add_gap_entities(conn, model: Any, user, analysis: Any, items: list | None = None, include_kept: bool = False) -> dict:
    """Adds the chosen gaps (all but the kept ones when none is chosen) to the model as Gap entities, each with
    its analysis, baseline and target, when compared, status and resolution, associated with its baseline and
    target elements and work packages; a gap that already has one is brought up to date. Model Admins; one
    commit straight away (D170)."""
    m = repo.get_model(conn, model)
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"Adding gaps as Gap entities needs the Model Admin role on {m['name']} (they are committed at once, and the "
                        "metamodel may get a Gap entity type).", 403)
    if (m.get("lock_level") or "none") != "none" or m.get("is_locked") or not cm.uses_commits(m):
        raise EditError(f"{m['name']} is read-only or locked: unlock it to add Gap entities.", 409)
    a = _analysis(conn, m, analysis)
    data = get(conn, str(m["id"]), str(a["guid"]))
    chosen = [i for i in data["items"] if not i["gone"] and (str(i["id"]) in {str(x) for x in items} if items
                                                             else include_kept or i["status"] != "kept")]
    if not chosen:
        raise EditError("Choose the gaps to add.", 409)
    version = _ensure_gap_type(conn, m, user)
    b, t = data["baseline"], data["target"]

    def side_text(s):
        return f"{s.get('label')} (commit {s.get('commit')}, metamodel v{s.get('metamodel_version')})"
    when = str(data["compared_at"])[:10]
    ops, owners = [], []
    for i in chosen:
        label = {"kept": "Kept", "changed": "Changed", "new": "New", "eliminated": "Eliminated"}[i["status"]]
        changes = "; ".join(f"{c['label']}: {c.get('left')} -> {c.get('right')}" for c in i["changes"][:20])
        desc = (f"{TOGAF_CELLS[i['status']]}. {i['entity_type_name']} '{i['name']}' in the gap analysis '{data['name']}' "
                f"(result #{data['run']}, tagged '{data['tags'][-1] if data['tags'] else ''}') "
                f"({data['template']['name']}): baseline {side_text(b)}, target {side_text(t)}, compared on {when} by "
                f"{data['compared_by']}." + (f" Changes: {changes}." if changes else "") + (f" Note: {i['note']}" if i["note"] else ""))
        values = {"GapStatus": label, "GapAnalysis": data["name"], "GapBaseline": side_text(b), "GapTarget": side_text(t),
                  "GapComparedAt": when, "GapResolution": i["resolution"] if i["resolution"] in RESOLUTIONS else ""}
        name = f"Gap: {i['name']} ({label.lower()})"
        exists = i["gap_entity"] and _one(conn, """SELECT tags FROM core.entities WHERE guid = CAST(:g AS uuid) AND NOT is_deleted""",
                                          g=i["gap_entity"])
        if exists:
            old = exists["tags"] or []
            if isinstance(old, str):
                old = [t for t in old.strip("{}").replace('"', "").split(",") if t]
            tags = list(dict.fromkeys([*old, *data["tags"]]))   # earlier runs' tags stay: each result can still be found
            ops.append(("entity.update", {"entity": i["gap_entity"], "data": {"name": name, "description": desc, "values": values,
                                                                              "tags": tags}}))
            owners.append((i, i["gap_entity"], False))
        else:
            g = str(uuid.uuid4())
            ops.append(("entity.create", {"data": {"guid": g, "entity_type": "Gap", "name": name, "description": desc, "values": values,
                                                   "tags": data["tags"]}}))
            owners.append((i, g, True))
    for i, g, new in owners:
        if not new:
            continue
        ends = [x for x, here in ((i["baseline_guid"], i["baseline_here"]), (i["target_guid"], i["target_here"])) if x and here]
        ends += [w["id"] for w in i["work_packages"]]
        for e in dict.fromkeys(ends):
            ops.append(("relationship.create", {"data": {"relationship_type": "Association", "source": g, "target": e,
                                                         "allow_outside": True}}))
    results = cm.record_many(conn, str(m["id"]), user.username, ops)
    failed = [{"what": (a_.get("data") or {}).get("name") or op, "error": r["error"]} for (op, a_), r in zip(ops, results, strict=True)
              if not r["ok"]]
    ids = [r["kept"]["change"] for r in results if r.get("ok") and r.get("kept")]
    done = cm.commit(conn, str(m["id"]), user, None, ids, None, f"Gaps of '{data['name']}' as Gap entities") if ids else None
    made = 0
    for (i, g, _new), r in zip(owners, results[:len(owners)], strict=True):
        if r["ok"]:
            _exec(conn, "UPDATE core.gap_items SET gap_entity = CAST(:g AS uuid) WHERE guid = CAST(:i AS uuid)", g=g, i=i["id"])
            made += 1
    return {"gap_entities": made, "failed": failed[:50], "tags": data["tags"], "commit": done["commit"] if done else None,
            "commit_number": done["number"] if done else None, "metamodel_version": version,
            "note": f"{made} gaps are Gap entities now, tagged '{data['tags'][-1] if data['tags'] else ''}' "
                    f"(commit {done['number'] if done else '-'})"
                    + (f"; the metamodel got a Gap entity type (version {version})" if version else "") + "."}


# ---------------------------------------------------------------- a migration plan from the gaps (WIZ-017, phase 16.3, D339)
ROADMAP_COLUMNS = ["Wave", "Work package", "Start", "End", "Resolution", "Gaps", "New", "Changed", "Eliminated"]


def migration_plan(conn, model: Any, user, analysis: Any, packages: list[dict]) -> dict:
    """The gaps of an analysis grouped into work packages: each package a Work Package entity in the model (one commit,
    Model Admins), associated with the elements its gaps are about, its gaps pointing at it (their work packages), and
    its resolution given to its gaps that have none. Returns the roadmap rows (a wave, dates, the gaps of each package)
    for a tracking sheet. A gap may be in one package only."""
    m = repo.get_model(conn, model)
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"Making a migration plan needs the Model Admin role on {m['name']} (the work packages are committed at once).", 403)
    if (m.get("lock_level") or "none") != "none" or m.get("is_locked") or not cm.uses_commits(m):
        raise EditError(f"{m['name']} is read-only or locked: unlock it to add work packages.", 409)
    a = _analysis(conn, m, analysis)
    data = get(conn, str(m["id"]), str(a["guid"]))
    items = {i["id"]: i for i in data["items"] if not i["gone"]}
    spec = mo.metamodel_spec(conn, str(m["id"]))
    wp = next((t for t in spec["entity_types"] if t["code"].lower() == "workpackage"), None)
    if not wp:
        raise EditError(f"{m['name']}'s metamodel has no Work Package entity type: extend it first (Model admin > Extend from "
                        "another model, from ArchiMate 4).", 409)
    seen: set[str] = set()
    plan = []
    for n, p in enumerate(packages or [], 1):
        name = " ".join(str(p.get("name") or "").split())[:200]
        gaps = [str(x) for x in p.get("gaps") or [] if str(x) in items]
        if not name or not gaps:
            continue
        twice = [items[g]["name"] for g in gaps if g in seen]
        if twice:
            raise EditError(f"{twice[0]} is in two work packages: a gap goes into one.")
        seen.update(gaps)
        res = p.get("resolution") or ""
        if res and res not in RESOLUTIONS:
            raise EditError(f"The resolution is one of: {', '.join(RESOLUTIONS)}.")
        plan.append({"n": n, "name": name, "gaps": gaps, "wave": str(p.get("wave") or "").strip()[:40],
                     "start": str(p.get("start") or "")[:10], "end": str(p.get("end") or "")[:10], "resolution": res,
                     "description": str(p.get("description") or "").strip()[:2000]})
    if not plan:
        raise EditError("Put the gaps into at least one work package (each with a name).")
    ops, made = [], []
    for p in plan:
        g = str(uuid.uuid4())
        gl = [items[x] for x in p["gaps"]]
        when = " to ".join(x for x in (p["start"], p["end"]) if x)
        desc = (p["description"] + "\n\n" if p["description"] else "") + (
            f"From the gap analysis '{data['name']}'"
            + (f", wave {p['wave']}" if p["wave"] else "") + (f", {when}" if when else "")
            + (f", resolution {p['resolution']}" if p["resolution"] else "") + ". Gaps: "
            + "; ".join(f"{i['name']} ({i['status']})" for i in gl[:60]) + ".")
        ops.append(("entity.create", {"data": {"guid": g, "entity_type": wp["code"], "name": p["name"], "description": desc,
                                               "tags": [*data["tags"], "migration-plan"]}}))
        made.append((p, g))
    for p, g in made:
        ends = []
        for x in p["gaps"]:
            i = items[x]
            if i["status"] == "eliminated":
                ends += [i["baseline_guid"]] if i["baseline_here"] else []
            else:
                ends += [i["target_guid"]] if i["target_here"] else []
        for e in dict.fromkeys(e for e in ends if e):
            ops.append(("relationship.create", {"data": {"relationship_type": "Association", "source": g, "target": e,
                                                         "allow_outside": True}}))
    results = cm.record_many(conn, str(m["id"]), user.username, ops)
    failed = [{"what": (a_.get("data") or {}).get("name") or op, "error": r["error"]}
              for (op, a_), r in zip(ops, results, strict=True) if not r["ok"]]
    ids = [r["kept"]["change"] for r in results if r.get("ok") and r.get("kept")]
    done = cm.commit(conn, str(m["id"]), user, None, ids, None, f"Migration plan from '{data['name']}'") if ids else None
    rows = []
    for (p, g), r in zip(made, results[:len(made)], strict=True):
        if not r["ok"]:
            continue
        for x in p["gaps"]:
            _exec(conn, """UPDATE core.gap_items SET work_packages = array_append(coalesce(work_packages, '{}'), CAST(:w AS uuid)),
                                  resolution = CASE WHEN coalesce(resolution, '') = '' AND :r <> '' THEN :r ELSE resolution END,
                                  modified_by = :u, modified_at = now()
                            WHERE guid = CAST(:i AS uuid) AND NOT (CAST(:w AS uuid) = ANY (coalesce(work_packages, '{}')))""",
                  w=g, r=p["resolution"], u=user.username, i=x)
        gl = [items[x] for x in p["gaps"]]
        rows.append({"Wave": p["wave"], "Work package": p["name"], "Start": p["start"], "End": p["end"], "Resolution": p["resolution"],
                     "Gaps": "; ".join(i["name"] for i in gl), "New": str(sum(1 for i in gl if i["status"] == "new")),
                     "Changed": str(sum(1 for i in gl if i["status"] == "changed")),
                     "Eliminated": str(sum(1 for i in gl if i["status"] == "eliminated"))})
    rows.sort(key=lambda r: (r["Wave"] or "~", r["Start"] or "~", r["Work package"]))
    left = [i["name"] for i in items.values() if i["status"] != "kept" and i["id"] not in seen]
    return {"work_packages": len(rows), "failed": failed[:50], "rows": rows, "columns": ROADMAP_COLUMNS, "analysis": data["name"],
            "model": {"id": str(m["id"]), "name": m["name"]}, "commit_number": done["number"] if done else None,
            "not_planned": left[:200],
            "note": f"{len(rows)} work packages made in {m['name']} (commit {done['number'] if done else '-'}), each linked to its "
                    f"gaps and the elements they are about." + (f" {len(left)} gaps are in no work package yet." if left else "")}


def suggest_packages(conn, model: Any, analysis: Any, by: str = "domain") -> dict:
    """A first grouping of the gaps that are not kept, for the wizard to start from: by domain, by entity type, by
    resolution, or one package per gap; gaps already in a work package are left out."""
    m = repo.get_model(conn, model)
    a = _analysis(conn, m, analysis)
    data = get(conn, str(m["id"]), str(a["guid"]))
    todo = [i for i in data["items"] if not i["gone"] and i["status"] != "kept" and not i["work_packages"]]
    groups: dict[str, list[dict]] = {}
    for i in todo:
        k = {"domain": i["domain"] or "Other", "type": i["entity_type_name"], "resolution": i["resolution"] or "Not decided",
             "each": i["name"]}.get(by, i["domain"] or "Other")
        groups.setdefault(k, []).append(i)
    status = lambda i: {"new": "New", "changed": "Changed", "eliminated": "Eliminated"}.get(i["status"], i["status"])  # noqa: E731
    return {"analysis": {"id": str(a["guid"]), "name": data["name"]}, "by": by, "resolutions": RESOLUTIONS,
            "packages": [{"name": (f"{k}: {data['name']}" if by != "each" else f"Work on {k}")[:200], "wave": "", "start": "", "end": "",
                          "resolution": "", "gaps": [i["id"] for i in v]} for k, v in sorted(groups.items())],
            "gaps": [{"id": i["id"], "name": i["name"], "type": i["entity_type_name"], "domain": i["domain"], "status": status(i),
                      "resolution": i["resolution"] or ""} for i in todo],
            "already": sum(1 for i in data["items"] if not i["gone"] and i["work_packages"])}


# ---------------------------------------------------------------- downloads
def to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")
    fills = {"changed": "FFF4D6", "new": "E3F4E6", "eliminated": "FBE3E1"}
    live = [i for i in data["items"] if not i["gone"]]

    def sheet(ws, cols, rows, status_col=None):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = bold, head
        for r in rows:
            ws.append(r)
            if status_col is not None and r[status_col] in fills:
                for c in ws[ws.max_row]:
                    c.fill = PatternFill("solid", fgColor=fills[r[status_col]])
        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(60, max(10, *(len(str(c.value or "")) for c in col[:200])))
    ws = wb.active
    ws.title = "Gap analysis"
    for row in _overview(data):
        ws.append(row)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 24, 90
    sheet(wb.create_sheet("Gaps"), ["Status", "TOGAF", "Domain", "Entity type", "Element", "Baseline", "Target", "Fields changed",
                                    "Resolution", "Note", "Work packages", "Gap entity"],
          [[i["status"], i["togaf_cell"], i["domain"], i["entity_type_name"], i["name"], i["baseline_name"], i["target_name"],
            ", ".join(c["label"] for c in i["changes"]), i["resolution"], i["note"], ", ".join(w["name"] for w in i["work_packages"]),
            "yes" if i["gap_entity"] else ""] for i in live], 0)
    # the TOGAF gap matrix, one block per entity type: baseline elements down, target elements across
    mx = wb.create_sheet("Gap matrix")
    r0 = 1
    for _code, group in _by_type(live):
        base = [i for i in group if i["baseline_name"]]
        tgt = [i for i in group if i["target_name"]]
        mx.cell(r0, 1, group[0]["entity_type_name"]).font = Font(bold=True, size=12)
        mx.cell(r0 + 1, 1, "Baseline \\ Target").font = bold
        for c, i in enumerate(tgt, 2):
            mx.cell(r0 + 1, c, i["target_name"]).font = bold
        mx.cell(r0 + 1, len(tgt) + 2, "Eliminated").font = bold
        for rr, i in enumerate(base, r0 + 2):
            mx.cell(rr, 1, i["baseline_name"]).font = bold
            for c, j in enumerate(tgt, 2):
                if j is i:
                    mx.cell(rr, c, "Included" if i["status"] == "kept" else "Changed")
            if i["status"] == "eliminated":
                mx.cell(rr, len(tgt) + 2, i["resolution"] or "Eliminated")
        new_row = r0 + 2 + len(base)
        mx.cell(new_row, 1, "New").font = bold
        for c, j in enumerate(tgt, 2):
            if j["status"] == "new":
                mx.cell(new_row, c, j["resolution"] or "New")
        r0 = new_row + 3
    mx.column_dimensions["A"].width = 40
    sheet(wb.create_sheet("Field changes"), ["Entity type", "Element", "Field", "Baseline", "Target"],
          [[i["entity_type_name"], i["name"], c["label"], str(c.get("left") or ""), str(c.get("right") or "")]
           for i in live for c in i["changes"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _by_type(items: list[dict]) -> list[tuple[str, list[dict]]]:
    out: dict[str, list[dict]] = {}
    for i in items:
        out.setdefault(i["entity_type"], []).append(i)
    return sorted(out.items(), key=lambda kv: (kv[1][0]["domain"] or "", kv[1][0]["entity_type_name"]))


def _overview(data: dict) -> list[list]:
    b, t = data["baseline"], data["target"]
    tot = data["totals"]
    return [[data["name"]], ["Template", f"{data['template']['name']} (TOGAF phase {data['template'].get('phase', '')})"],
            ["Baseline", f"{b.get('label')} - commit {b.get('commit')}, metamodel v{b.get('metamodel_version')}"],
            ["Target", f"{t.get('label')} - commit {t.get('commit')}, metamodel v{t.get('metamodel_version')}"],
            ["Compared", f"{str(data["compared_at"])[:16].replace("T", " ")} by {data['compared_by']}"], ["Description", data["description"]], [],
            ["Included (kept)", tot["kept"]], ["Changed", tot["changed"]], ["New", tot["new"]], ["Eliminated", tot["eliminated"]],
            ["Gaps without a resolution", data["undecided"]]]


def _p(txt: str, style: str | None = None, bold: bool = False) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{escape(str(txt))}</w:t></w:r></w:p>'


def _table(rows: list[list]) -> str:
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
           '<w:tblBorders><w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/>'
           '<w:right w:val="single" w:sz="4"/><w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders>'
           '</w:tblPr>']
    for n, r in enumerate(rows):
        out.append("<w:tr>")
        for c in r:
            shade = '<w:tcPr><w:shd w:val="clear" w:fill="DDE6F0"/></w:tcPr>' if n == 0 else ""
            out.append(f"<w:tc>{shade}{_p(c if c is not None else '', bold=n == 0)}</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def to_docx(data: dict) -> bytes:
    """The gap analysis as a Word document: overview, the gaps by domain with their resolutions, notes and
    work packages, and what changed."""
    live = [i for i in data["items"] if not i["gone"]]
    body = [_p(data["name"], "Title")]
    ov = _overview(data)
    body.append(_table([["", "Compared"]] + [[r[0], r[1]] for r in ov[1:6] if r]))
    body.append(_p("Summary", "Heading1"))
    body.append(_table([["Status (TOGAF)", "Elements"]] + [[TOGAF_CELLS[s], str(data["totals"][s])] for s in ("kept", "changed", "new",
                                                                                                             "eliminated")]
                       + [["Gaps without a resolution", str(data["undecided"])]]))
    for status, title in (("new", "New elements (gaps: to be developed or procured)"),
                          ("eliminated", "Eliminated elements (gaps: to retire, replace, or add back if omitted by accident)"),
                          ("changed", "Changed elements")):
        group = [i for i in live if i["status"] == status]
        if not group:
            continue
        body.append(_p(title, "Heading1"))
        for _code, items in _by_type(group):
            body.append(_p(items[0]["entity_type_name"], "Heading2"))
            body.append(_table([["Element", "Resolution", "Work packages", "Note" if status != "changed" else "What changed"]] +
                               [[i["name"], i["resolution"], ", ".join(w["name"] for w in i["work_packages"]),
                                 i["note"] if status != "changed" else "; ".join(f"{c['label']}: {c.get('left')} -> {c.get('right')}"
                                                                                 for c in i["changes"][:12])]
                                for i in items]))
    return docx_from(body)


def docx_from(body: list[str]) -> bytes:
    """A Word document from paragraphs and tables made with _p and _table (gap and common analyses)."""
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
           'w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr></w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:spacing w:before="240" w:after="80"/></w:pPr>'
              '<w:rPr><w:b/><w:color w:val="1F4E79"/><w:sz w:val="30"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:spacing w:before="160" w:after="60"/></w:pPr>'
              '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
              '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style></w:styles>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                   'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                   'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", styles)
    return buf.getvalue()
