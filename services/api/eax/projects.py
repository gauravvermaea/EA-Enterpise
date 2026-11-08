"""Architecture projects and their repository (phase 13, D258 to D262).

A project has a purpose (Strategy, Portfolio, Project, Solution or the user's own), its models (added, derived as a
child, or created), its viewpoints, principles (from the library or its own; a child inherits its parent's), the ADM
steps (TOGAF's and the library's, accepted or removed with the reason; its own added), the deliverables and artifacts
(chosen, or placed as not_for_use in the same folders), its people and who signs off. It is set up in one pass by the
wizard (create); its repository is then built in Mayan in the background (build_repository).

Project roles (D259): Project Admin and Lead Architect run the setup and the people; Architects, Model Admin and Model
Sub Admin contribute too; Stakeholders read, and comment on, approve or reject documents (13.1) but do not contribute.
A Super Admin sees and may do everything. Rules are kept here, never in the database (D248).

Documents (D260): stored in Mayan (versions, check-out); edited outside in Office: check out, download, edit, check in
with the new file. The person who checked out, the Lead Architect, a Model Admin, the Project Admin or a Super Admin may
undo a check-out.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from .metamodel_edit import EditError

log = logging.getLogger(__name__)

ROLES = ("project-admin", "lead-architect", "architect", "model-admin", "model-sub-admin", "stakeholder")
ROLE_NAMES = {"project-admin": "Project Admin", "lead-architect": "Lead Architect", "architect": "Architect",
              "model-admin": "Model Admin", "model-sub-admin": "Model Sub Admin", "stakeholder": "Stakeholder"}
CONTRIBUTORS = {"project-admin", "lead-architect", "architect", "model-admin", "model-sub-admin"}
ADMINS = {"project-admin", "lead-architect"}
UNDO_CHECKOUT = {"project-admin", "lead-architect", "model-admin"}
# the model role a member gets on the models the project creates or derives (D261); added models keep their own people
MODEL_ROLE_FOR = {"project-admin": perms.MODEL_ADMIN, "lead-architect": perms.MODEL_ADMIN, "model-admin": perms.MODEL_ADMIN,
                  "model-sub-admin": perms.MODEL_SUB_ADMIN, "architect": perms.ARCHITECT, "stakeholder": perms.REPORT_VIEWER}
LIBRARY_DIR = Path(os.environ.get("EAX_LIBRARY_MOUNT", "/data/library"))   # EAX_LIBRARY_DIR is the host folder
EA_TEMPLATES_DIR = Path(os.environ.get("EAX_EA_TEMPLATES_MOUNT", "/data/ea-explorer-templates"))   # EA Explorer's own (D264)
NOT_FOR_USE = "not_for_use"


@contextmanager
def connections(write: bool = True):
    """The projects' connection with the repository's beside it (conn.info["core"]); one connection, one transaction,
    while proj is in the repository's database (D266)."""
    from .db import get_engine, get_projects_engine
    eng, peng = get_engine(), get_projects_engine()
    with (eng.begin() if write else eng.connect()) as cconn:
        if peng is eng:
            yield cconn
        else:
            with (peng.begin() if write else peng.connect()) as pconn:
                pconn.info["core"] = cconn
                yield pconn


def core(conn):
    """The repository's connection beside the projects' one (D266): the same connection when proj is in the
    repository's database; otherwise the one the caller put in conn.info["core"]."""
    info = getattr(conn, "info", None)
    return (info or {}).get("core", conn)


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _super(user) -> bool:
    return perms.SUPER_ADMIN in (user.roles or ())


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80] or "item"


# ---------------------------------------------------------------- the library (what the wizard offers)
def library(conn) -> dict:
    from . import content_framework as cf
    items = _rows(conn, """SELECT id, phase, name, kind, type, default_pick, work_folder, approved_folder, templates, content_area
                             FROM proj.lib_items WHERE NOT retired ORDER BY id""")
    src = {}
    for s in _rows(conn, "SELECT item_id, source, phase, name, files, location, note FROM proj.lib_item_sources ORDER BY id"):
        src.setdefault(s["item_id"], []).append({k: s[k] for k in ("source", "phase", "name", "files", "location", "note")})
    for i in items:
        i["sources"] = src.get(i["id"], [])
        # where it sits in the content framework by default (one area or several, D309), and a line on what it is
        i["areas"] = cf.area_of_item(i["name"], "", i["content_area"])[0]
        srcs = ", ".join(sorted({x["source"] for x in i["sources"]}))
        i["description"] = next((x["note"].strip() for x in i["sources"] if (x["note"] or "").strip()), "") or (
            f"{i['type']} ({srcs})" if i["type"] and srcs else i["type"] or (f"From {srcs}" if srcs else ""))
    return {
        "purposes": _rows(conn, "SELECT code, name, standard FROM proj.lib_purposes WHERE NOT retired ORDER BY sort_order, name"),
        "phases": _rows(conn, "SELECT code, name, workspace, objectives, inputs FROM proj.lib_phases ORDER BY sort_order"),
        "steps": _rows(conn, """SELECT id, phase, seq, name, source, marking, note FROM proj.lib_steps
                                 WHERE NOT retired ORDER BY phase, seq"""),
        "items": items,
        "folders": _rows(conn, "SELECT path, holds, togaf_class, origin FROM proj.lib_folders WHERE NOT retired ORDER BY path"),
        # TOGAF's templates by name, each loaded once by a Super Admin (the other libraries are listed by libraries())
        "templates": _rows(conn, """SELECT t.id, t.source, t.code, t.name, t.phase, t.purpose, t.folder, t.file_name, t.uploaded_by,
                                           t.uploaded_at, t.mayan_document_id IS NOT NULL AS has_file
                                      FROM proj.lib_templates t JOIN proj.template_libraries l ON l.id = t.library_id
                                     WHERE l.kind = 'togaf' ORDER BY t.folder, t.name"""),
        "principles": _rows(conn, """SELECT id, code, set_name, category, name, statement, rationale, implications, tier
                                      FROM proj.lib_principles WHERE NOT retired ORDER BY set_name, code"""),
        "viewpoints": _rows(core(conn), """SELECT code, name, category, purpose, element_types, source FROM core.viewpoints
                                            WHERE code NOT LIKE 'PV-%' ORDER BY code"""),
        "item_templates": item_templates_all(conn),
        "template_index": template_index(conn),
        "project_templates": __import__("eax.project_templates", fromlist=["x"]).listing(conn),
        "model_roles": __import__("eax.project_templates", fromlist=["x"]).ROLES,
        "roles": [{"code": r, "name": ROLE_NAMES[r]} for r in ROLES],
        "org_base": __import__("eax.project_bases", fromlist=["x"]).ORG_GUID,     # its charter: the wizard starts from it
    }


def item_templates_all(conn) -> dict[str, list[dict]]:
    """Every library template with a file, by library item: what the wizard offers per deliverable and artifact (D278:
    the templates of an item are chosen from several libraries)."""
    libs = _rows(conn, "SELECT id, guid::text AS guid, name, kind FROM proj.template_libraries WHERE state = 'ready' ORDER BY id")
    items = _rows(conn, "SELECT id, templates FROM proj.lib_items WHERE NOT retired")
    out: dict[str, list[dict]] = {}
    for lib in libs:
        for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=lib["id"]):
            if not _has_file(t, lib["kind"]):
                continue
            row = {"id": t["id"], "library": lib["guid"], "library_name": lib["name"], "name": t["file_name"] or t["name"]}
            if t["item_id"]:
                out.setdefault(t["item_id"], []).append(row)
            elif lib["kind"] == "togaf":
                for i in items:
                    if t["name"] and t["name"] in (i["templates"] or ""):
                        out.setdefault(i["id"], []).append(row)
    return out


def template_index(conn) -> dict[str, dict]:
    """Every template with a file in a ready library, by id: what the wizard shows for a template picked by browsing a
    library (it may belong to another document type, or to none)."""
    out: dict[str, dict] = {}
    for lib in _rows(conn, "SELECT id, guid::text AS guid, name, kind FROM proj.template_libraries WHERE state = 'ready' ORDER BY id"):
        for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=lib["id"]):
            if _has_file(t, lib["kind"]):
                out[str(t["id"])] = {"id": t["id"], "library": lib["guid"], "library_name": lib["name"], "name": t["file_name"] or t["name"]}
    return out


# ---------------------------------------------------------------- who may do what
def project_row(conn, project: Any) -> dict:
    key = str(project)
    p = _one(conn, f"""SELECT p.*, pp.guid::text AS parent_guid, pp.name AS parent_name FROM proj.projects p
                        LEFT JOIN proj.projects pp ON pp.id = p.parent_id
                       WHERE {'p.guid = CAST(:k AS uuid)' if re.fullmatch(r'[0-9a-fA-F-]{36}', key) else 'p.name = :k'}""", k=key)
    if not p:
        raise EditError(f"No project {key}.", 404)
    return p


def my_roles(conn, p: dict, user) -> set[str]:
    return {r["role"] for r in _rows(conn, "SELECT role FROM proj.members WHERE project_id = :p AND lower(username) = lower(:u)",
                                     p=p["id"], u=user.username)}


def _need(conn, p: dict, user, what: str) -> set[str]:
    roles = my_roles(conn, p, user)
    if p.get("base_kind"):          # a project base (phase 13.1, D303): anyone with a role reads it; changes as its rules say
        if what == "read":
            if _super(user) or (user.roles or ()):
                return roles | {"reader"}
        else:
            from . import project_bases as pb
            pb.check_change(p, user)
            return roles | {"super-admin"}
    if _super(user):
        if what != "read" and p.get("status") in ("finishing", "frozen", "merged", "closed"):
            raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
        return roles | {"super-admin"}
    ok = {"read": bool(roles), "contribute": bool(roles & CONTRIBUTORS), "admin": bool(roles & ADMINS),
          "undo": bool(roles & UNDO_CHECKOUT)}[what]
    if ok and what != "read" and p.get("status") in ("finishing", "frozen", "merged", "closed"):
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    if not ok:
        need = {"read": "a role on this project", "contribute": "a contributing role (not Stakeholder)",
                "admin": "Project Admin or Lead Architect", "undo": "Lead Architect, Model Admin or Project Admin"}[what]
        raise EditError(f"Not allowed on {p['name']}: needs {need}.", 403)
    return roles


def completion(conn, ids: list[int]) -> dict[int, dict]:
    """How complete each project is (owner, 8 Nov 2026): its phases marked complete, out of the phases it has (those with
    steps in its cycle). Documents and steps do not count; a phase is marked complete by someone who contributes, and
    may be reopened at any time (which lowers it again)."""
    if not ids:
        return {}
    rows = _rows(conn, """
        SELECT p.id, p.completed_at, p.completed_by,
               (SELECT count(DISTINCT s.phase) FROM proj.steps s WHERE s.project_id = p.id AND s.cycle = p.cycle AND NOT s.removed) AS phases,
               (SELECT count(*) FROM proj.phase_states ps WHERE ps.project_id = p.id AND ps.cycle = p.cycle
                   AND ps.phase IN (SELECT DISTINCT s.phase FROM proj.steps s WHERE s.project_id = p.id AND s.cycle = p.cycle AND NOT s.removed))
                   AS phases_done,
               (SELECT count(*) FROM proj.steps s WHERE s.project_id = p.id AND s.cycle = p.cycle AND NOT s.removed
                   AND s.parent_step_id IS NULL) AS steps,
               (SELECT count(*) FROM proj.steps s WHERE s.project_id = p.id AND s.cycle = p.cycle AND NOT s.removed
                   AND s.parent_step_id IS NULL AND s.done_at IS NOT NULL) AS steps_done
          FROM proj.projects p WHERE p.id = ANY (CAST(:ids AS bigint[]))""", ids=list(ids))
    out = {}
    for r in rows:
        total, done = int(r["phases"]), int(r["phases_done"])
        pct = 100 if r["completed_at"] else (round(100 * done / total) if total else 0)     # a project marked complete: 100
        out[r["id"]] = {"percent": pct, "done": done, "total": total, "completed_at": r["completed_at"], "completed_by": r["completed_by"],
                        "phases": total, "phases_done": done, "steps": int(r["steps"]), "steps_done": int(r["steps_done"])}
    return out


def mark_project(conn, project: Any, user, complete: bool) -> dict:
    """The project marked complete, or open again, at any time (owner, 8 Nov 2026): a Project Admin or Lead Architect.
    Not finishing it (freezing or merging stays in Finish the project)."""
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    conn.execute(text("UPDATE proj.projects SET completed_at = CASE WHEN :c THEN now() END, completed_by = CASE WHEN :c THEN :u END WHERE id = :p"),
                 {"c": complete, "u": user.username, "p": p["id"]})
    return {"message": f"{p['name']} is {'complete' if complete else 'open again'}."}


def phases_done(conn, p: dict) -> dict[str, dict]:
    return {r["phase"]: {"by": r["completed_by"], "at": r["completed_at"], "note": r["note"]}
            for r in _rows(conn, "SELECT * FROM proj.phase_states WHERE project_id = :p AND cycle = :c", p=p["id"], c=p.get("cycle") or 1)}


def mark_phase(conn, project: Any, user, phase: str, complete: bool, note: str = "") -> dict:
    """A phase marked complete (or reopened) by anyone who contributes (owner, 8 Nov 2026); completion counts phases."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    name = (_one(conn, "SELECT name FROM proj.lib_phases WHERE code = :c", c=phase) or {}).get("name")
    if not name:
        raise EditError(f"No phase {phase}.", 404)
    if complete:
        conn.execute(text("""INSERT INTO proj.phase_states (project_id, cycle, phase, completed_by, note) VALUES (:p, :c, :ph, :u, :n)
                             ON CONFLICT (project_id, cycle, phase) DO UPDATE SET completed_by = :u, completed_at = now(), note = :n"""),
                     {"p": p["id"], "c": p["cycle"], "ph": phase, "u": user.username, "n": (note or "").strip()[:1000]})
        return {"message": f"{name} is complete."}
    conn.execute(text("DELETE FROM proj.phase_states WHERE project_id = :p AND cycle = :c AND phase = :ph"),
                 {"p": p["id"], "c": p["cycle"], "ph": phase})
    return {"message": f"{name} is open again."}


def may_create(user) -> bool:
    return perms.allowed(user.roles, "projects.create")


# ---------------------------------------------------------------- list and read
def listing(conn, user) -> list[dict]:
    rows = _rows(conn, """SELECT p.id AS pk, p.guid::text AS id, p.name, p.purpose, p.description, p.cycle, p.status, p.repo_state, p.created_by,
                                 p.is_library, (SELECT count(*) FROM proj.documents d WHERE d.project_id = p.id AND d.folder LIKE '05_Reference_Library%'
                                     AND d.deleted_at IS NULL AND d.archived_at IS NULL) AS reference_items,
                                 p.created_at, pp.name AS parent_name, pp.guid::text AS parent_id,
                                 (SELECT b.guid::text FROM proj.projects b WHERE b.id = p.base_id) AS base_id,
                                 (SELECT array_agg(DISTINCT m.role) FROM proj.members m
                                   WHERE m.project_id = p.id AND lower(m.username) = lower(:u)) AS my_roles,
                                 (SELECT count(*) FROM proj.members m WHERE m.project_id = p.id) AS people,
                                 (SELECT count(*) FROM proj.project_models pm WHERE pm.project_id = p.id) AS models,
                                 (SELECT count(*) FROM proj.items i WHERE i.project_id = p.id AND i.chosen) AS items,
                                 (SELECT count(*) FROM proj.documents d WHERE d.project_id = p.id
                                     AND d.archived_at IS NULL AND d.deleted_at IS NULL) AS documents
                            FROM proj.projects p LEFT JOIN proj.projects pp ON pp.id = p.parent_id
                           WHERE p.base_kind = '' ORDER BY p.name""", u=user.username)
    if not _super(user):
        rows = [r for r in rows if r["my_roles"]]
    done = completion(conn, [r["pk"] for r in rows])
    for r in rows:
        r["my_roles"] = sorted(r["my_roles"] or [])
        r["completion"] = done.get(r.pop("pk"))
    return rows


def detail(conn, project: Any, user) -> dict:
    p = project_row(conn, project)
    roles = _need(conn, p, user, "read")
    if p.get("base_kind"):
        # a base: whoever may change it (a Super Admin in the Organisation base) sees the screens to change it; the Empty
        # and TOGAF 10 projects stay read-only for everyone
        from . import project_bases as pbm
        try:
            pbm.check_change(p, user)
            roles = roles | {"super-admin"}
        except EditError:
            pass
    out = {k: p[k] for k in ("name", "purpose", "description", "cycle", "status", "repo_state", "repo_note", "created_by", "created_at")}
    out.update(id=str(p["guid"]), me=user.username, parent_id=p["parent_guid"], parent_name=p["parent_name"], my_roles=sorted(roles),
               may_admin=bool(roles & (ADMINS | {"super-admin"})), may_contribute=bool(roles & (CONTRIBUTORS | {"super-admin"})),
               may_undo=bool(roles & (UNDO_CHECKOUT | {"super-admin"})))
    out["members"] = _rows(conn, "SELECT username, role, added_by, added_at FROM proj.members WHERE project_id = :p ORDER BY role, username",
                           p=p["id"])
    out["signoff"] = _rows(conn, "SELECT phase, username FROM proj.signoff WHERE project_id = :p ORDER BY phase, username", p=p["id"])
    pmods = {r["guid"]: r for r in _rows(conn, "SELECT model_guid::text AS guid, how, role, role_seq FROM proj.project_models WHERE project_id = :p",
                                         p=p["id"])}
    how = {g: r["how"] for g, r in pmods.items()}
    out["models"] = [{**m, "how": how[m["id"]], "role": pmods[m["id"]]["role"], "role_seq": pmods[m["id"]]["role_seq"],
                      "home": bool(p.get("home_model")) and m["id"] == str(p["home_model"])} for m in _rows(core(conn), """SELECT m.guid::text AS id, m.name, m.kind_code AS kind, m.copy_state, m.parent_model_id IS NOT NULL AS has_parent,
                              pm.guid::text AS parent_model_id, pm.name AS parent_name, pm.name AS parent_model_name,
                              sm.name AS source_model_name, sm.kind_code AS source_model_kind, m.source_tag_name, m.metamodel_name
                         FROM core.models m LEFT JOIN core.models pm ON pm.id = m.parent_model_id
                         LEFT JOIN core.models sm ON sm.id = m.source_model_id
                        WHERE m.guid::text = ANY (CAST(:g AS text[])) ORDER BY m.name""", g=list(how))] if how else []
    names = {r["code"]: r["name"] for r in _rows(core(conn), "SELECT code, name FROM core.viewpoints")}
    out["viewpoints"] = [{"code": v["code"], "name": names.get(v["code"], v["code"])} for v in
                         _rows(conn, "SELECT viewpoint AS code FROM proj.project_viewpoints WHERE project_id = :p ORDER BY viewpoint", p=p["id"])]
    out["principles"] = _rows(conn, """SELECT pr.id, pr.code, pr.name, pr.statement, pr.rationale, pr.implications, pr.library_id,
                                              pr.area, pr.created_by, pp.name AS inherited_from, pr.mandatory,
                                              pr.origin_guid IS NOT NULL AS from_base, pr.guid::text AS guid, pr.origin_guid::text AS origin_guid,
                                              pr.refines::text AS refines FROM proj.principles pr
                                         LEFT JOIN proj.projects pp ON pp.id = pr.inherited_from
                                        WHERE pr.project_id = :p ORDER BY pr.area, pr.sort_order, pr.code, pr.name""", p=p["id"])
    # the project hierarchy (phase 13.1, D303): its base and what the base offers that it has not taken
    from . import project_bases as pbm
    out["phases_done"] = phases_done(conn, p)
    out["base_kind"] = p.get("base_kind") or ""
    out["base_chain"] = pbm.chain(conn, p)[1:]
    out["base_offers"] = len(pbm.offers(conn, p)) if not p.get("base_kind") or p.get("base_kind") == "org" else 0
    # the areas (D327): the project's own list (added before they have principles), its base's, and those in use
    own_areas = [r["name"] for r in _rows(conn, "SELECT name FROM proj.principle_areas WHERE project_id = :p ORDER BY sort_order, name", p=p["id"])]
    base_areas = [r["name"] for r in _rows(conn, """SELECT a.name FROM proj.principle_areas a JOIN proj.projects x ON x.id = a.project_id
                                                    WHERE x.id = :b ORDER BY a.sort_order, a.name""", b=p.get("base_id") or 0)]
    out["principle_area_list"] = list(dict.fromkeys(own_areas + base_areas))
    out["principle_areas"] = sorted({r["category"] for r in _rows(conn, "SELECT DISTINCT category FROM proj.lib_principles WHERE category <> ''")}
                                    | {r["area"] for r in out["principles"] if r["area"]} | set(own_areas) | set(base_areas))
    out["is_super"] = _super(user)
    out["phases"] = _rows(conn, "SELECT code, name, workspace FROM proj.lib_phases ORDER BY sort_order")
    out["steps"] = _rows(conn, """SELECT id, phase, seq, name, library_id, library_id IS NULL AS own, removed, removed_reason, done_at, done_by,
                                         done_note, parent_step_id AS parent, added_by, added_at, due_date,
                                         (SELECT coalesce(json_agg(json_build_object('at', e.at, 'by', e.by_user, 'action', e.action, 'note', e.note)
                                                                   ORDER BY e.at, e.id), '[]') FROM proj.step_events e WHERE e.step_id = proj.steps.id) AS events
                                    FROM proj.steps WHERE project_id = :p AND cycle = :c
                                   ORDER BY phase, coalesce(parent_step_id, id), parent_step_id NULLS FIRST, seq, id""", p=p["id"], c=p["cycle"])
    out["items"] = _rows(conn, """SELECT i.guid::text AS id, i.phase, i.name, i.kind, i.type, i.library_id, i.chosen, i.folder,
                                         i.approved_folder, i.placeholder, i.templates, i.note, i.not_needed_reason, i.not_needed_by, i.content_area,
                                         i.not_needed_at, i.added_by, i.mayan_cabinet_id IS NOT NULL AS stored,
                                         (SELECT count(*) FROM proj.documents d WHERE d.item_id = i.id AND d.archived_at IS NULL AND d.deleted_at IS NULL) AS documents
                                    FROM proj.items i WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.phase, i.folder""",
                              p=p["id"], c=p["cycle"])
    out["libraries"] = _rows(conn, """SELECT l.guid::text AS id, l.name, l.kind, l.state, l.shared FROM proj.project_libraries pl
                                        JOIN proj.template_libraries l ON l.id = pl.library_id
                                       WHERE pl.project_id = :p ORDER BY pl.sort_order""", p=p["id"])
    by_item, _f, _l = _project_templates(conn, p["id"])
    out["templates"] = {k: [{"id": t["id"], "library": t["library"], "name": t["file_name"] or t["name"]} for t in v] for k, v in by_item.items()}
    out["class_templates"] = class_templates(conn, p)
    out["documents"] = documents(conn, p)
    out["hidden_documents"] = _one(conn, """SELECT count(*) FILTER (WHERE archived_at IS NOT NULL AND deleted_at IS NULL) AS archived,
                                                  count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted
                                             FROM proj.documents WHERE project_id = :p""", p=p["id"])
    out["signoff_quorum"] = p.get("signoff_quorum")
    out["document_tags"] = sorted({t for d in out["documents"] for t in (d.get("tags") or [])}, key=str.lower)
    out["folders"] = [r["path"] for r in _rows(conn, "SELECT path FROM proj.folders WHERE project_id = :p ORDER BY path", p=p["id"])]
    # phase 13.0.1 (D274 to D279)
    from . import project_work as pw
    out.update(pw.fields_out(p))
    out["frozen"] = p["status"] in pw.FROZEN
    out["merged_into"] = None
    if p.get("merged_into"):
        t = _one(conn, "SELECT guid::text AS id, name FROM proj.projects WHERE id = :i", i=p["merged_into"])
        out["merged_into"] = t
    out["template"] = None
    if p.get("template_code"):
        out["template"] = _one(conn, "SELECT code, name, icon, spec->>'finish' AS finish FROM proj.project_templates WHERE code = :c", c=p["template_code"])
    out["children"] = _rows(conn, "SELECT guid::text AS id, name, status FROM proj.projects WHERE parent_id = :p ORDER BY name", p=p["id"])
    out["goals"] = pw.goals(conn, p)
    pend = p.get("pending_goals")
    out["pending_goals"] = pend if isinstance(pend, list) else __import__("json").loads(pend or "[]")
    out["viewpoints"] = pw.viewpoint_status(conn, p)
    out["model_types"] = pw.model_types(conn, p)
    out["signoffs"] = pw.signoffs(conn, p, user)
    open_by_doc = {r["document"]: r for r in out["signoffs"] if r["state"] == "open"}
    kind_of = {i["id"]: i["kind"] for i in out["items"]}
    for d in out["documents"]:
        d["kind"] = d.get("kind") or kind_of.get(d["item_id"]) or "Artifact"
        d["signoff"] = open_by_doc.get(d["id"])
    out["project_files"] = [d for d in out["documents"] if d["folder"] == pw.PROJECT_FILES]
    from . import stakeholders as sh
    out["stakeholders"] = sh.listing(conn, p["guid"], user)["stakeholders"]      # the matrix (D294): a derived project copies it
    from . import references as rf
    rf.targets(conn, user, out["documents"])      # links to other projects' documents, as they are there now (D296)
    out["is_library"] = bool(p.get("is_library"))
    out["completion"] = completion(conn, [p["id"]]).get(p["id"])
    out["may_finish"] = out["may_admin"] and not out["frozen"]
    if out["frozen"]:
        out["may_admin"] = out["may_contribute"] = out["may_undo"] = False
    return out


def documents(conn, p: dict, show: tuple | list = ()) -> list[dict]:
    """The project's documents. Archived and deleted ones are left out (and not loaded) unless asked for (D290)."""
    return _rows(conn, """SELECT d.guid::text AS id, i.guid::text AS item_id, d.folder, d.file_name, d.versions, d.origin, d.state,
                                 d.kind, d.signed_version, d.user_version, d.out_version, d.tags, d.content_area,
                                 d.accepted_by, d.accepted_at, d.accepted_note, d.accepted_evidence,
                                 d.archived_by, d.archived_at, d.deleted_by, d.deleted_at,
                                 (SELECT e.at FROM proj.document_events e WHERE e.document_id = d.id AND e.action = 'checked in'
                                   ORDER BY e.at DESC LIMIT 1) AS checked_in_at,
                                 (SELECT e.by_user FROM proj.document_events e WHERE e.document_id = d.id AND e.action = 'checked in'
                                   ORDER BY e.at DESC LIMIT 1) AS checked_in_by,
                                 d.checked_out_by, d.checked_out_at, d.created_by, d.created_at, d.modified_by, d.modified_at,
                                 d.mayan_document_id IS NOT NULL AS stored, d.link_url, d.link_project, d.link_document, d.link_item,
                                 d.description, (d.link_url <> '' OR d.link_project IS NOT NULL) AS is_link, d.title,
                                 (d.mayan_document_id IS NULL AND d.link_url = '' AND d.link_project IS NULL) AS no_file
                            FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                           WHERE d.project_id = :p AND (d.archived_at IS NULL OR :arc) AND (d.deleted_at IS NULL OR :del)
                           ORDER BY d.folder, d.file_name""", p=p["id"], arc="archived" in show, **{"del": "deleted" in show})


# ---------------------------------------------------------------- the wizard: create a project in one pass
def _check_payload(conn, d: dict) -> None:
    name = (d.get("name") or "").strip()
    if not name:
        raise EditError("Give the project a name.")
    if len(name) > 120:
        raise EditError("The name is too long (120 characters at most).")
    if _one(conn, "SELECT 1 AS x FROM proj.projects WHERE lower(name) = lower(:n)", n=name):
        raise EditError(f"A project called {name} exists already.", 409)
    if not (d.get("purpose") or "").strip():
        raise EditError("Choose the purpose: Strategy, Portfolio, Project, Solution or your own.")
    for m in d.get("members") or []:
        if m.get("role") not in ROLES:
            raise EditError(f"Unknown project role {m.get('role')}: one of {', '.join(ROLES)}.")


def create(conn, user, d: dict, sample: bool = False) -> dict:
    """Creates the project from the wizard's choices. Returns {project, copies}: copies are the model content copies to
    run in the background (as for a new model). The repository is built afterwards (build_repository)."""
    if not may_create(user):
        raise EditError("Creating a project needs a global role (User, Model Creator or Super Admin).", 403)
    if not sample and not setup_state(conn)["done"]:    # the laptop sample project is made before the setup
        raise EditError("No template library is offered to projects: a Super Admin offers one first (Project admin > Project library).", 409)
    _check_payload(conn, d)
    libs = _chosen_libraries(conn, user, d.get("libraries"))
    parent = project_row(conn, d["parent"]) if d.get("parent") else None
    if parent:
        _need(conn, parent, user, "read")
    from . import project_work as pw
    fields = pw.scope_fields(d)
    pw.check_goal_model(conn, d)
    pid = _one(conn, """INSERT INTO proj.projects (name, purpose, description, parent_id, created_by)
                        VALUES (:n, :pu, :de, :pa, :u) RETURNING id, guid::text AS guid""",
               n=d["name"].strip(), pu=d["purpose"].strip(), de=(d.get("description") or "").strip(),
               pa=parent["id"] if parent else None, u=user.username)
    p = {"id": pid["id"], "guid": pid["guid"], "name": d["name"].strip()}
    pw.save_fields(conn, p["id"], fields)
    set_quorum(conn, p, d.get("signoff_quorum"))
    if d.get("template"):
        conn.execute(text("UPDATE proj.projects SET template_code = :t WHERE id = :p"), {"t": d["template"], "p": p["id"]})
    # people: the person creating it is its Project Admin
    members = {(user.username.lower(), "project-admin")}
    for m in d.get("members") or []:
        if (m.get("username") or "").strip():
            members.add((m["username"].strip().lower(), m["role"]))
    for u, r in sorted(members):
        conn.execute(text("INSERT INTO proj.members (project_id, username, role, added_by) VALUES (:p, :u, :r, :b) ON CONFLICT DO NOTHING"),
                     {"p": p["id"], "u": u, "r": r, "b": user.username})
    people = {u for u, _r in members}
    for phase, users in (d.get("signoff") or {}).items():
        for u in users or []:
            if u.lower() not in people:
                raise EditError(f"{u} signs off but is not one of the project's people.")
            conn.execute(text("INSERT INTO proj.signoff (project_id, phase, username) VALUES (:p, :ph, :u) ON CONFLICT DO NOTHING"),
                         {"p": p["id"], "ph": phase or "", "u": u.lower()})
    # models: refer to, add, derive (a child) or create; one is the project's own model (its goals live there, D274)
    copies, made, home = [], [], None
    for m in d.get("models") or []:
        mm, cp = link_model(conn, p, user, m)
        if cp:
            copies.append(cp)
        if m.get("how") in ("derived", "created"):
            made.append(mm)
        if m.get("home"):
            home = str(mm["id"])
    model_roles(conn, made, members, user)
    conn.execute(text("UPDATE proj.projects SET home_model = CAST(:h AS uuid) WHERE id = :p"), {"h": home, "p": p["id"]})
    for v in d.get("viewpoints") or []:
        conn.execute(text("INSERT INTO proj.project_viewpoints (project_id, viewpoint) VALUES (:p, :v) ON CONFLICT DO NOTHING"),
                     {"p": p["id"], "v": v})
    for n, lib in enumerate(libs):
        conn.execute(text("INSERT INTO proj.project_libraries (project_id, library_id, sort_order) VALUES (:p, :l, :s)"),
                     {"p": p["id"], "l": lib["id"], "s": n})
        if not lib["shared"] and not lib["project_id"]:      # a library added in this wizard now belongs to the project
            conn.execute(text("UPDATE proj.template_libraries SET project_id = :p WHERE id = :l"), {"p": p["id"], "l": lib["id"]})
    _principles(conn, p, user, d, parent)
    _steps(conn, p, d)
    # the base it derives from (phase 13.1, D303): the Organisation base unless a library project or base is chosen;
    # it takes the base's principles, standards (mandatory) and steps, and its charter, at once
    from . import project_bases as pbm
    base = None
    if d.get("base"):
        base = project_row(conn, d["base"])
        if not (base.get("base_kind") or base.get("is_library")):
            raise EditError("A project derives from a project base or a library project.", 409)
        if not pbm.under_org(conn, base):        # every project comes from the Organisation base (owner, 8 Nov 2026)
            raise EditError("Every project comes from the Organisation base: choose it, or a library project below it.", 409)
    else:
        base = _one(conn, "SELECT * FROM proj.projects WHERE guid = CAST(:g AS uuid)", g=pbm.ORG_GUID)
    if base:
        conn.execute(text("UPDATE proj.projects SET base_id = :b WHERE id = :p"), {"b": base["id"], "p": p["id"]})
        pbm.take_all_new(conn, {**p, "base_id": base["id"]}, user, steps=True)
    _items(conn, p, d)
    item_templates(conn, p, d)
    reader_roles(conn, p, user)
    from . import governance as gov
    gov.charter_from_wizard(conn, p, user, d.get("charter"))      # the wizard's Charter step (owner, 8 Nov 2026)
    for v in d.get("own_viewpoints") or []:
        if (v.get("name") or "").strip():
            pw.add_viewpoint(conn, p["guid"], user, v)
    note = pw.write_goals(conn, project_row(conn, p["guid"]), user, d.get("goals"))
    from . import stakeholders as sh
    sh.from_wizard(conn, p, user, d.get("stakeholders"))     # the template's suggestions, or the parent's (D294)
    from . import references as rf
    rf.copy_into(conn, {**p, "parent_id": parent["id"] if parent else None}, user, d.get("reference"), d.get("template"))  # D296
    from . import notify
    notify.create(core(conn), kind="project.created", category="model", actor=user.username,
                  title=f"You are on the architecture project {p['name']}",
                  body=f"{user.username} set up {p['name']} ({d['purpose']}). Its repository is being built in Documents.",
                  link=f"#/projects/{p['guid']}", recipients=sorted(people))
    return {"project": {"id": p["guid"], "name": p["name"]}, "copies": copies, "note": note}


def link_model(conn, p: dict, user, m: dict) -> tuple[dict, dict | None]:
    """Links a model to the project as the wizard says: referred to (read only, D274), added (worked on), derived as a
    child of a project model, or created from a root metamodel or a library model. Returns (model, copy to run)."""
    from . import model_ops as mo
    from . import repository as repo
    how, cp = m.get("how"), None
    if how in ("added", "referred"):
        if not m.get("model"):
            raise EditError("Choose the model to add or refer to.")
        mm = repo.get_model(core(conn), m["model"])
    elif how in ("derived", "created"):
        # the new-model wizard (owner, 7 Nov 2026): create empty (a metamodel only), derive from an existing model (a
        # separate copy), or derive and keep the parent-child link (it merges back later: how = derived)
        spec = {"kind": "project", "name": (m.get("name") or "").strip(), "source": m.get("from"),
                "copy": "metamodel" if m.get("start") == "empty" else (m.get("copy") or ("content" if how == "derived" else "metamodel")),
                "description": (m.get("description") or "").strip() or f"Created for the architecture project {p['name']}."}
        if not spec["source"]:
            raise EditError("Choose the metamodel or model each new model starts from.")
        if m.get("tag"):
            if how == "derived":
                raise EditError("A model made from a tag is a separate copy: it cannot keep a parent-child link.")
            spec["tag"] = m["tag"]
        if how == "derived":
            spec["parent"] = m["from"]
        if not spec["name"]:
            raise EditError("Give each new model a name.")
        res = mo.create_model(core(conn), user.username, spec)
        mm = res["model"]
        cp = res.get("_copy")
    else:
        raise EditError("A model is referred to, added, derived or created.")
    role = m.get("role") or None
    from .project_templates import ROLES
    if role and role not in ROLES:
        raise EditError(f"Unknown model role {role}: one of {', '.join(ROLES)}.")
    conn.execute(text("""INSERT INTO proj.project_models (project_id, model_guid, how, added_by, role, role_seq)
                         VALUES (:p, CAST(:m AS uuid), :h, :u, :r, :q) ON CONFLICT DO NOTHING"""),
                 {"p": p["id"], "m": str(mm["id"]), "h": how, "u": user.username, "r": role, "q": m.get("seq")})
    return mm, cp


def reader_roles(conn, p: dict, user) -> dict:
    """Owner, 7 Nov 2026: a model brought into a project (referred to or added) can be read by everyone on the project;
    whoever has no role on it yet gets Report Viewer (read only); roles they already have are kept. Giving a role on a
    model needs its Model Admin (the database checks it): where the person saving is not, the model's Model Admins are
    asked in the application instead. Returns {granted, asked: [model names]}."""
    from . import notify
    guids = [r["g"] for r in _rows(conn, "SELECT model_guid::text AS g FROM proj.project_models WHERE project_id = :p", p=p["id"])]
    people = sorted({r["u"] for r in _rows(conn, "SELECT DISTINCT lower(username) AS u FROM proj.members WHERE project_id = :p", p=p["id"])})
    out = {"granted": 0, "asked": []}
    if not guids or not people:
        return out
    c = core(conn)
    for m in _rows(c, "SELECT id, guid::text AS g, name FROM core.models WHERE guid::text = ANY (CAST(:g AS text[])) ORDER BY name", g=guids):
        have = {r["u"] for r in _rows(c, "SELECT DISTINCT lower(username) AS u FROM core.model_users WHERE model_id = :m", m=m["id"])}
        missing = [u for u in people if u not in have]
        if not missing:
            continue
        admins = sorted({r["u"] for r in _rows(c, "SELECT DISTINCT lower(username) AS u FROM core.model_users WHERE model_id = :m AND role = :r",
                                               m=m["id"], r=perms.MODEL_ADMIN)})
        if _super(user) or user.username.lower() in admins:
            for u in missing:
                c.execute(text("""INSERT INTO core.model_users (model_id, username, role, created_by) VALUES (:m, :u, :r, :b)
                                  ON CONFLICT (model_id, username, role) DO NOTHING"""),
                          {"m": m["id"], "u": u, "r": perms.REPORT_VIEWER, "b": user.username})
            out["granted"] += len(missing)
        elif admins:
            notify.create(c, kind="project.read_access", category="request", actor=user.username,
                          title=f"Read access to {m['name']} for the project {p['name']}",
                          body=(f"{user.username} brought {m['name']} into the architecture project {p['name']}. These people cannot "
                                f"read it yet: {', '.join(missing)}. Give them Report Viewer (or another role) on its People tab."),
                          link=f"#/metamodel/{m['g']}/people", recipients=admins)
            out["asked"].append(m["name"])
    return out


def model_roles(conn, made: list[dict], members: set[tuple[str, str]], user) -> None:
    """The people get roles on the models the project made (D261)."""
    for mm in made:
        for u, r in members:
            core(conn).execute(text("""INSERT INTO core.model_users (model_id, username, role, created_by) VALUES (:m, :u, :r, :b)
                                 ON CONFLICT (model_id, username, role) DO NOTHING"""),
                         {"m": mm["_id"], "u": u, "r": MODEL_ROLE_FOR[r], "b": user.username})


def item_templates(conn, p: dict, d: dict) -> None:
    """Per library item: the templates chosen for it (from several libraries; none chosen = a placeholder, D278)."""
    for lib_id, ids in (d.get("templates") or {}).items():
        conn.execute(text("UPDATE proj.items SET templates = CAST(:t AS bigint[]) WHERE project_id = :p AND library_id = :l"),
                     {"t": None if ids is None else [int(x) for x in ids], "p": p["id"], "l": lib_id})
    for lib_id, on in (d.get("placeholders") or {}).items():
        conn.execute(text("UPDATE proj.items SET placeholder = :o WHERE project_id = :p AND library_id = :l"),
                     {"o": bool(on), "p": p["id"], "l": lib_id})
    # the wizard's documents table (owner, 8 Nov 2026): a description per document type (a blank template's text) and
    # where it sits in the content framework (one area or several, D309; none = its default)
    from . import content_framework as cf
    for lib_id, note in (d.get("notes") or {}).items():
        conn.execute(text("UPDATE proj.items SET note = :n WHERE project_id = :p AND library_id = :l"),
                     {"n": str(note or "").strip()[:4000], "p": p["id"], "l": lib_id})
    for lib_id, areas in (d.get("areas") or {}).items():
        conn.execute(text("UPDATE proj.items SET content_area = :a WHERE project_id = :p AND library_id = :l"),
                     {"a": cf.clean_area(areas), "p": p["id"], "l": lib_id})


def own_item_fields(it: dict) -> dict:
    """A document type of the project's own, from the wizard: its templates (picked by browsing the libraries; none = a
    blank one, its document made later), description and content framework areas."""
    from . import content_framework as cf
    out = {"note": (it.get("note") or "").strip()[:4000], "content_area": cf.clean_area(it.get("areas") or "")}
    if "templates" in it:
        ids = [int(x) for x in it.get("templates") or []]
        out["templates"] = ids or None
        out["placeholder"] = not ids
    else:
        out["templates"] = None
        out["placeholder"] = bool(it.get("placeholder", True))
    return out


def _chosen_libraries(conn, user, chosen: list | None) -> list[dict]:
    """The template libraries the project copies its templates from (D264): those picked in the wizard, in order, or
    every library offered to projects."""
    if chosen is None:
        return _rows(conn, "SELECT * FROM proj.template_libraries WHERE shared AND state <> 'failed' ORDER BY id")
    out = []
    for key in chosen:
        lib = _library_row(conn, key)
        if not _sees_library(conn, lib, user):
            raise EditError(f"The template library {lib['name']} is not offered to you.", 403)
        if lib["state"] == "failed":
            raise EditError(f"The template library {lib['name']} failed to load: {lib['note']}")
        out.append(lib)
    return out


def _principles(conn, p: dict, user, d: dict, parent: dict | None) -> None:
    if parent:   # a child inherits its parent's principles
        conn.execute(text("""INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, library_id,
                                                          inherited_from, area, created_by)
                             SELECT :p, code, name, statement, rationale, implications, library_id, :pa, area, :u
                               FROM proj.principles WHERE project_id = :pa"""), {"p": p["id"], "pa": parent["id"], "u": user.username})
    for pr in d.get("principles") or []:
        if pr.get("library_id"):
            conn.execute(text("""INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, library_id, area, created_by)
                                 SELECT :p, code, name, statement, rationale, implications, id, category, :u FROM proj.lib_principles WHERE id = :l"""),
                         {"p": p["id"], "l": int(pr["library_id"]), "u": user.username})
        elif (pr.get("name") or "").strip():
            conn.execute(text("""INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, area, created_by)
                                 VALUES (:p, :c, :n, :s, :r, :i, :a, :u)"""),
                         {"p": p["id"], "c": pr.get("code") or "", "n": pr["name"].strip(), "s": pr.get("statement") or "",
                          "r": pr.get("rationale") or "", "i": pr.get("implications") or "", "a": (pr.get("area") or "").strip()[:80],
                          "u": user.username})


def _steps(conn, p: dict, d: dict) -> None:
    """Every library step comes in; the removed ones stay, crossed out, with the reason (D258). The project's own steps
    follow each phase's."""
    removed = {int(r["library_id"]): (r.get("reason") or "").strip() for r in d.get("removed_steps") or []}
    for why in removed.values():
        if not why:
            raise EditError("Say why a standard step is removed: it stays in the project, crossed out, with the reason.")
    conn.execute(text("""INSERT INTO proj.steps (project_id, phase, seq, name, library_id, removed, removed_reason)
                         SELECT :p, s.phase, s.seq, s.name, s.id, s.id = ANY (CAST(:ids AS bigint[])),
                                coalesce((CAST(:why AS jsonb) ->> s.id::text), '')
                           FROM proj.lib_steps s WHERE NOT s.retired"""),
                 {"p": p["id"], "ids": list(removed), "why": __import__("json").dumps({str(k): v for k, v in removed.items()})})
    _steps_own(conn, p, d.get("own_steps") or [])


def _steps_own(conn, p: dict, own: list[dict]) -> None:
    for s in own:
        if not (s.get("name") or "").strip():
            continue
        conn.execute(text("""INSERT INTO proj.steps (project_id, phase, seq, name)
                             SELECT :p, :ph, coalesce(max(seq), 0) + 1, :n FROM proj.steps WHERE project_id = :p AND phase = :ph"""),
                     {"p": p["id"], "ph": s["phase"], "n": s["name"].strip()})


def _items(conn, p: dict, d: dict) -> None:
    """Every library deliverable and artifact comes in: the chosen ones, and the others as not_for_use in the same
    folders (D258). Each is marked deliverable or artifact (the wizard may change the library's suggestion)."""
    import json
    chosen = d.get("items")
    kinds = {k: v for k, v in (d.get("kinds") or {}).items() if v in ("Deliverable", "Artifact")}
    conn.execute(text("""INSERT INTO proj.items (project_id, phase, name, kind, type, library_id, chosen, folder, approved_folder)
                         SELECT :p, i.phase, i.name, coalesce(CAST(:k AS jsonb) ->> i.id, i.kind), i.type, i.id,
                                CASE WHEN CAST(:all AS boolean) THEN i.default_pick ELSE i.id = ANY (CAST(:ids AS text[])) END,
                                i.work_folder, i.approved_folder
                           FROM proj.lib_items i WHERE NOT i.retired"""),
                 {"p": p["id"], "k": json.dumps(kinds), "all": chosen is None, "ids": list(chosen or [])})
    _items_own(conn, p, d.get("own_items") or [])


class _Who:
    """Who a planned document made by the wizard is recorded as: the project's maker."""
    def __init__(self, p: dict):
        self.username = p.get("created_by") or "system"


def _items_own(conn, p: dict, own: list[dict]) -> None:
    """The project's own deliverables and artifacts: placeholders unless said otherwise (to deliver, no template yet:
    the document is made later, D278)."""
    n = 900 + (_one(conn, "SELECT count(*) AS n FROM proj.items WHERE project_id = :p AND library_id IS NULL", p=p["id"]) or {"n": 0})["n"]
    for it in own:
        if not (it.get("name") or "").strip():
            continue
        n += 1
        ph = it.get("phase") or "X"
        kind = it.get("kind") if it.get("kind") in ("Deliverable", "Artifact") else "Deliverable"
        ws = _one(conn, "SELECT workspace FROM proj.lib_phases WHERE code = :c", c=ph)
        if not ws:
            raise EditError(f"Unknown phase {ph}.")
        folder = f"{ws['workspace']}/{kind}s/{n}_{_slug(it['name'])}"
        fx = own_item_fields(it)
        new_id = conn.execute(text("""INSERT INTO proj.items (project_id, phase, name, kind, type, chosen, folder, placeholder, note,
                                                              templates, content_area)
                                      VALUES (:p, :ph, :n, :k, :t, true, :f, :pl, :no, CAST(:tp AS bigint[]), :ca) RETURNING id"""),
                              {"p": p["id"], "ph": ph, "n": it["name"].strip(), "k": kind, "t": it.get("type") or "", "f": folder,
                               "pl": fx["placeholder"], "no": fx["note"], "tp": fx["templates"], "ca": fx["content_area"]}).scalar()
        # documents planned in it now, their files added later (owner, 8 Nov 2026)
        docs = it.get("documents") or []
        if isinstance(docs, str):
            docs = docs.split(",")
        for t in docs:
            if str(t).strip():
                add_planned(conn, p, _Who(p), {"id": new_id, "folder": folder, "name": it["name"]}, str(t))


def set_quorum(conn, p: dict, q: Any) -> None:
    """The project's quorum (D290): how many of a phase's sign-off people must approve; empty is a majority."""
    if q in (None, "", 0, "0"):
        q = None
    else:
        try:
            q = int(q)
        except (TypeError, ValueError):
            raise EditError("The quorum is a number of people (or empty for a majority).") from None
        if not 1 <= q <= 50:
            raise EditError("The quorum is between 1 and 50 people.")
    conn.execute(text("UPDATE proj.projects SET signoff_quorum = :q WHERE id = :p"), {"q": q, "p": p["id"]})


def set_people(conn, project: Any, user, members: list[dict], signoff: dict, quorum: Any = "keep") -> dict:
    """The people and who signs off, changed after setup (Project Admin, Lead Architect)."""
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    rows = {((m.get("username") or "").strip().lower(), m.get("role")) for m in members if (m.get("username") or "").strip()}
    if any(r not in ROLES for _u, r in rows):
        raise EditError(f"Each person has one of the roles {', '.join(ROLES)}.")
    if not any(r == "project-admin" for _u, r in rows):
        raise EditError("A project keeps at least one Project Admin.")
    conn.execute(text("DELETE FROM proj.members WHERE project_id = :p"), {"p": p["id"]})
    for u, r in sorted(rows):
        conn.execute(text("INSERT INTO proj.members (project_id, username, role, added_by) VALUES (:p, :u, :r, :b)"),
                     {"p": p["id"], "u": u, "r": r, "b": user.username})
    people = {u for u, _r in rows}
    conn.execute(text("DELETE FROM proj.signoff WHERE project_id = :p"), {"p": p["id"]})
    for phase, users in (signoff or {}).items():
        for u in users or []:
            if u.lower() not in people:
                raise EditError(f"{u} signs off but is not one of the project's people.")
            conn.execute(text("INSERT INTO proj.signoff (project_id, phase, username) VALUES (:p, :ph, :u) ON CONFLICT DO NOTHING"),
                         {"p": p["id"], "ph": phase or "", "u": u.lower()})
    if quorum != "keep":
        set_quorum(conn, p, quorum)
    conn.execute(text("UPDATE proj.projects SET modified_at = now() WHERE id = :p"), {"p": p["id"]})
    reader_roles(conn, p, user)
    return detail(conn, project, user)


def choose_item(conn, project: Any, user, item: str, chosen: bool) -> dict:
    """Bring a not_for_use item into use, or put one out of use (its folder and documents stay)."""
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    r = conn.execute(text("UPDATE proj.items SET chosen = :c WHERE project_id = :p AND guid = CAST(:i AS uuid) RETURNING id, mayan_cabinet_id"),
                     {"c": chosen, "p": p["id"], "i": item}).mappings().first()
    if not r:
        raise EditError("No such item in this project.", 404)
    queue_rebuild(conn, p["id"])        # its folder's name follows, and its templates are copied when it comes into use
    return {"item": item, "chosen": chosen, "message": "Brought into use." if chosen else f"Marked {NOT_FOR_USE}."}


def not_needed(conn, project: Any, user, item: str, reason: str = "", undo: bool = False) -> dict:
    """A document class (an item) marked "won't need this", with the reason; anyone on the project, logged (D290). Undo
    brings it back (whoever marked it, the Project Admin or the Lead Architect)."""
    p = project_row(conn, project)
    roles = _need(conn, p, user, "contribute")
    it = _one(conn, "SELECT * FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
    if not it:
        raise EditError("No such document class in this project.", 404)
    if undo:
        # a class left out when the project was set up is added by anyone who contributes (owner, 8 Nov 2026: Not added);
        # one marked "won't need" is brought back by whoever marked it, the Project Admin or the Lead Architect
        if it["not_needed_by"] and it["not_needed_by"].lower() != user.username.lower() and not roles & (ADMINS | {"super-admin"}):
            raise EditError(f"{it['not_needed_by']} marked it; they, the Project Admin or the Lead Architect bring it back.", 403)
        conn.execute(text("""UPDATE proj.items SET chosen = true, not_needed_reason = '', not_needed_by = NULL, not_needed_at = NULL
                             WHERE id = :i"""), {"i": it["id"]})
        queue_rebuild(conn, p["id"])
        return {"item": item, "message": f"{it['name']} is {'needed again' if it['not_needed_by'] else 'in the project now'}."}
    reason = (reason or "").strip()
    if not reason:
        raise EditError("Say why it is not needed (for example: covered by the capability assessment).")
    out = _rows(conn, """SELECT coalesce(nullif(title, ''), file_name) AS n, checked_out_by AS b FROM proj.documents
                          WHERE item_id = :i AND checked_out_by IS NOT NULL AND deleted_at IS NULL""", i=it["id"])
    if out:
        raise EditError("Checked out now: " + ", ".join(f"{r['n']} ({r['b']})" for r in out) + ". Check them in first.", 409)
    conn.execute(text("""UPDATE proj.items SET chosen = false, not_needed_reason = :r, not_needed_by = :u, not_needed_at = now()
                         WHERE id = :i"""), {"r": reason[:500], "u": user.username, "i": it["id"]})
    queue_rebuild(conn, p["id"])
    return {"item": item, "message": f"{it['name']}: won't need it ({reason[:80]}). Its documents stay."}


def add_item(conn, project: Any, user, d: dict) -> dict:
    """A new document class in a phase, made from the repository by anyone on the project (D290): its folder is made in
    Documents with the repository (within a minute); documents can be added to it then."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    name = (d.get("name") or "").strip()
    if not name:
        raise EditError("Name the document class, for example Capability Heat Map.")
    if len(name) > 120:
        raise EditError("The name is 120 characters at most.")
    phase = d.get("phase") or "X"
    if _one(conn, "SELECT 1 AS x FROM proj.items WHERE project_id = :p AND cycle = :c AND phase = :ph AND lower(name) = lower(:n)",
            p=p["id"], c=p["cycle"], ph=phase, n=name):
        raise EditError(f"Phase {phase} has a document class called {name} already: add your document to it.", 409)
    _items_own(conn, p, [{"name": name, "phase": phase, "kind": d.get("kind") or "Artifact", "type": d.get("type") or "",
                          "placeholder": True, "note": (d.get("note") or "").strip()}])
    it = _one(conn, """SELECT guid::text AS id, folder FROM proj.items WHERE project_id = :p AND cycle = :c AND phase = :ph
                       AND lower(name) = lower(:n) ORDER BY id DESC LIMIT 1""", p=p["id"], c=p["cycle"], ph=phase, n=name)
    conn.execute(text("UPDATE proj.items SET added_by = :u WHERE guid = CAST(:g AS uuid)"), {"u": user.username, "g": it["id"]})
    queue_rebuild(conn, p["id"])
    return {"item": it["id"], "message": f"{name} added to phase {phase}: its folder is made in Documents within a minute, then add documents to it."}


# ---------------------------------------------------------------- the repository in Mayan (background)
STALE_BUILD = "15 minutes"     # a build still "building" after this was cut off (a restart): it is taken up again
MAX_TRIES = 30


def pending_repositories(conn) -> list[int]:
    return [r["id"] for r in _rows(conn, f"""SELECT id FROM proj.projects
                                             WHERE (repo_state IN ('pending', 'failed') AND repo_tries < {MAX_TRIES})
                                                OR (repo_state = 'building' AND coalesce(repo_started_at, '-infinity') < now() - interval '{STALE_BUILD}')
                                             ORDER BY id""")]


def _project_templates(conn, project_id: int) -> tuple[dict, list[dict], list[str]]:
    """Every template of the project's libraries, by library item (and those that sit in other folders), plus the names of
    libraries still loading. All of them are copied: two libraries with a template for the same item give two files,
    named <library>-<file> (D264)."""
    libs = _rows(conn, """SELECT l.id, l.name, l.kind, l.state FROM proj.project_libraries pl JOIN proj.template_libraries l
                            ON l.id = pl.library_id WHERE pl.project_id = :p ORDER BY pl.sort_order""", p=project_id)
    items = _rows(conn, "SELECT id, templates FROM proj.lib_items WHERE NOT retired")
    by_item: dict[str, list[dict]] = {}
    in_folders: list[dict] = []
    for lib in libs:
        for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=lib["id"]):
            if not _has_file(t, lib["kind"]):
                continue
            t = {**t, "library": lib["name"], "kind": lib["kind"]}
            if t["item_id"]:
                by_item.setdefault(t["item_id"], []).append(t)
            elif lib["kind"] == "togaf":          # TOGAF's are named by the items that use them
                for i in items:
                    if t["name"] and t["name"] in (i["templates"] or ""):
                        by_item.setdefault(i["id"], []).append(t)
            elif t["folder"]:
                in_folders.append(t)
    return by_item, in_folders, [lib["name"] for lib in libs if lib["state"] == "loading"]


def _project_templates_by_id(conn, project_id: int) -> dict[int, dict]:
    """Every template with a file in the project's libraries, by id."""
    out: dict[int, dict] = {}
    for lib in _rows(conn, """SELECT l.id, l.name, l.kind FROM proj.project_libraries pl JOIN proj.template_libraries l
                                ON l.id = pl.library_id WHERE pl.project_id = :p ORDER BY pl.sort_order""", p=project_id):
        for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l", l=lib["id"]):
            if _has_file(t, lib["kind"]):
                out[t["id"]] = {**t, "library": lib["name"], "kind": lib["kind"]}
    return out


def _copy_template(conn_factory, project_id: int, t: dict, cabinet: int, item_id: int | None, folder: str) -> None:
    from . import mayan
    content, ctype = _template_bytes(t, t["kind"])
    name = f"{t['library']}-{t['file_name'] or t['name']}"
    doc = mayan.upload(name, content, ctype)
    mayan.add_to_cabinet(cabinet, doc["id"])
    with conn_factory() as conn:
        conn.execute(text("""INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin,
                                                         template_id, created_by, modified_by)
                             VALUES (:p, :i, :f, :m, :n, 'template', :t, 'system', 'system')"""),
                     {"p": project_id, "i": item_id, "f": folder, "m": doc["id"], "n": name, "t": t["id"]})


def build_repository(conn_factory, project_id: int) -> str:
    """Builds the project's repository in Mayan: a cabinet for the project, one for every master folder and every item
    (not_for_use items get the suffix in their name), and a copy of every template the project's libraries have for each
    chosen item (and for its folders). Safe to run again: what exists is reused, templates already copied are not copied
    again. Waits while one of its libraries is still loading. conn_factory() gives a transaction."""
    from . import mayan
    with conn_factory() as conn:
        _by, _f, loading = _project_templates(conn, project_id)
        if loading:
            note = f"Waiting for the template library {', '.join(loading)} to finish loading."
            conn.execute(text("UPDATE proj.projects SET repo_state = 'pending', repo_note = :n WHERE id = :i AND repo_state <> 'building'"),
                         {"n": note, "i": project_id})
            return note
        # claim it: one runner at a time (the queued job and the minute sweep may both try), and only when it is waiting,
        # failed, or a build cut off by a restart
        p = _one(conn, f"""UPDATE proj.projects SET repo_state = 'building', repo_tries = repo_tries + 1, repo_started_at = now(),
                                   repo_again = false
                            WHERE id = :i AND (repo_state IN ('pending', 'failed')
                                  OR (repo_state = 'building' AND coalesce(repo_started_at, '-infinity') < now() - interval '{STALE_BUILD}'))
                            RETURNING *""", i=project_id)
    if not p:
        return "already being built, or ready"
    try:
        root = mayan.cabinet("EA Explorer projects")
        if p["mayan_cabinet_id"]:        # its own folder, found by id: a renamed project keeps it (and the folder follows the name)
            pc = p["mayan_cabinet_id"]
            mayan.rename_cabinet(pc, p["name"])
        else:
            pc = mayan.cabinet(p["name"], root)
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.projects SET mayan_cabinet_id = :c WHERE id = :i"), {"c": pc, "i": project_id})
            folders = [r["path"] for r in _rows(conn, "SELECT path FROM proj.lib_folders WHERE NOT retired ORDER BY path")]
            items = _rows(conn, """SELECT i.id, i.name, i.folder, i.chosen, i.library_id, i.mayan_cabinet_id, i.mayan_cabinet_chosen,
                                          i.placeholder, i.templates FROM proj.items i
                                    WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.folder""", p=project_id, c=p["cycle"])
            by_item, in_folders, _l = _project_templates(conn, project_id)
            by_id = _project_templates_by_id(conn, project_id)
            # what was copied already, by the template it came from (its file may have been renamed by a check-in since,
            # review 8 Nov 2026), and by name for copies made before the template was recorded
            done = _rows(conn, """SELECT item_id, folder, file_name, template_id FROM proj.documents
                                   WHERE project_id = :p AND origin = 'template'""", p=project_id)
            copied = {(r["item_id"], r["folder"], r["file_name"]) for r in done}
            copied_t = {(r["item_id"], r["template_id"]) for r in done if r["template_id"]}
        cabinets = {}
        for f in sorted(set(folders) | {t["folder"] for t in in_folders}):
            cid = mayan.cabinet_path(f, pc)
            cabinets[f] = cid
            with conn_factory() as conn:
                conn.execute(text("""INSERT INTO proj.folders (project_id, path, mayan_cabinet_id) VALUES (:p, :f, :c)
                                     ON CONFLICT (project_id, path) DO UPDATE SET mayan_cabinet_id = EXCLUDED.mayan_cabinet_id"""),
                             {"p": project_id, "f": f, "c": cid})
        made = 0
        for t in in_folders:
            if (None, t["id"]) not in copied_t and (None, t["folder"], f"{t['library']}-{t['file_name'] or t['name']}") not in copied:
                _copy_template(conn_factory, project_id, t, cabinets[t["folder"]], None, t["folder"])
                made += 1
        for it in items:
            path = it["folder"] if it["chosen"] else f"{it['folder']} ({NOT_FOR_USE})"
            cid = it["mayan_cabinet_id"] or mayan.cabinet_path(path, pc)
            if it["mayan_cabinet_id"] and it["mayan_cabinet_chosen"] is not None and it["mayan_cabinet_chosen"] != it["chosen"]:
                mayan.rename_cabinet(cid, path.split("/")[-1])      # brought back into use, or put out of use: the suffix follows
            with conn_factory() as conn:
                conn.execute(text("UPDATE proj.items SET mayan_cabinet_id = :c, mayan_cabinet_chosen = :ch WHERE id = :i"),
                             {"c": cid, "ch": it["chosen"], "i": it["id"]})
                conn.execute(text("UPDATE proj.projects SET repo_started_at = now() WHERE id = :i"), {"i": project_id})  # still at it
            if not it["chosen"] or it["placeholder"]:     # a placeholder has no template: its document is made later
                continue
            cand = list(by_item.get(it["library_id"], [])) if it["library_id"] else []
            have = {t["id"] for t in cand}
            # templates picked by browsing a library (another document type's, or none's): copied too (owner, 8 Nov 2026)
            cand += [by_id[x] for x in (it["templates"] or []) if x in by_id and x not in have]
            for t in cand:
                if it["templates"] is not None and t["id"] not in it["templates"]:
                    continue
                if (it["id"], t["id"]) in copied_t or (it["id"], it["folder"], f"{t['library']}-{t['file_name'] or t['name']}") in copied:
                    continue
                _copy_template(conn_factory, project_id, t, cid, it["id"], it["folder"])
                made += 1
        note = f"Ready: {len(cabinets)} folders, {len(items)} item folders, {made} templates copied."
        with conn_factory() as conn:
            again = conn.execute(text("""UPDATE proj.projects SET repo_state = CASE WHEN repo_again THEN 'pending' ELSE 'ready' END,
                                                repo_note = :n, repo_again = false WHERE id = :i RETURNING repo_state = 'pending'"""),
                                 {"n": note, "i": project_id}).scalar()
        if again:
            note += " Something changed meanwhile: it is built again within a minute."
    except Exception as exc:
        with conn_factory() as conn:
            left = MAX_TRIES - p["repo_tries"]
            conn.execute(text("UPDATE proj.projects SET repo_state = 'failed', repo_note = :n WHERE id = :i"),
                         {"n": f"Not built yet: {str(exc)[:400]}. " + (f"It is tried again every minute ({left} more tries)." if left > 0
                               else "It is not tried again by itself: use Build the repository now."), "i": project_id})
        raise
    # documents a restore left to put back (a project backup, or an application restore): now that the folders are there
    try:
        from . import project_backup as pb
        back = pb.refill_pending(conn_factory, project_id)
    except Exception as exc:  # noqa: BLE001 - the files wait for the next build
        back = f"The restored documents are not back yet ({str(exc)[:120]}): they are tried again on the next build."
    return f"{note} {back}".strip()


def queue_rebuild(conn, project_id: int) -> None:
    """Something changed that the repository must follow (a class added, brought back into use or put out of use): it is
    built again within a minute, whatever state it is in (a running build finishes first)."""
    conn.execute(text("""UPDATE proj.projects SET repo_state = CASE WHEN repo_state = 'building' THEN repo_state ELSE 'pending' END,
                                repo_again = (repo_state = 'building'), repo_tries = 0 WHERE id = :i"""), {"i": project_id})


def retry_repository(conn, project: Any, user) -> dict:
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    conn.execute(text("UPDATE proj.projects SET repo_state = 'pending', repo_tries = 0, repo_note = 'Asked again' WHERE id = :i"), {"i": p["id"]})
    return {"id": str(p["guid"]), "project_id": p["id"]}


# ---------------------------------------------------------------- documents: upload, download, check out, check in
def _dname(d: dict) -> str:
    """A document as people know it in messages: its name, else its file's name."""
    return d.get("title") or d.get("file_name") or "The document"


def _when(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M") if hasattr(v, "strftime") else str(v or "")[:16]


def _doc(conn, p: dict, doc: str) -> dict:
    d = _one(conn, "SELECT * FROM proj.documents WHERE project_id = :p AND guid = CAST(:d AS uuid)", p=p["id"], d=doc)
    if not d:
        raise EditError("No such document in this project.", 404)
    return d


def _event(conn, doc_id: int, user, action: str, version: int | None = None, note: str = "", user_version: str = "") -> None:
    conn.execute(text("""INSERT INTO proj.document_events (document_id, by_user, action, version, note, user_version)
                         VALUES (:d, :u, :a, :v, :n, :uv)"""),
                 {"d": doc_id, "u": user.username, "a": action, "v": version, "n": note[:500], "uv": user_version or ""})


def next_version(v: str | None) -> str:
    """The version put in when none is given at check-in: the first number in the last one, its last part up by one
    (0.3 draft -> 0.4, 1.0 -> 1.1, v2 -> v3); nothing yet (or no number) -> 0.1."""
    m = re.search(r"\d+(?:\.\d+)*", v or "")
    if not m:
        return "0.1"
    parts = m.group(0).split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return (v or "")[:m.start()].lstrip() + ".".join(parts)


TAG_MAX = 40


def set_tags(conn, project: Any, user, doc: str, tags: list | None) -> dict:
    """A document's tags (D290): free text, any number; anyone who contributes to the project. Case-insensitive
    duplicates are dropped, the first spelling kept."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    out, seen = [], set()
    for t in tags or []:
        t = " ".join(str(t).split())
        if not t:
            continue
        if len(t) > TAG_MAX:
            raise EditError(f"A tag is {TAG_MAX} characters at most: {t[:20]}...")
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if len(out) > 30:
        raise EditError("30 tags at most on a document.")
    conn.execute(text("UPDATE proj.documents SET tags = :t WHERE id = :i"), {"t": out, "i": d["id"]})
    _event(conn, d["id"], user, "tagged", d["versions"], ", ".join(out) or "no tags")
    return {"id": doc, "tags": out, "message": f"{_dname(d)}: " + (", ".join(out) if out else "no tags") + "."}


def _version_label(v: str | None, required: bool, what: str) -> str:
    """Your version (D290): free text, given at every check-out and check-in (0.3 draft, 1.0 for approval)."""
    v = (v or "").strip()
    if required and not v:
        raise EditError(f"Give your version for this {what} (for example 0.2 draft or 1.0 for approval).")
    if len(v) > 40:
        raise EditError("Your version is 40 characters at most.")
    return v


DOC_KINDS = ("Deliverable", "Artifact", "None")


def _doc_kind(kind: Any) -> str | None:
    """A document's own kind (owner, 8 Nov 2026): deliverable, artifact, or neither; None: its class's."""
    if kind in (None, ""):
        return None
    if kind not in DOC_KINDS:
        raise EditError("A document is a Deliverable, an Artifact, or neither (None).")
    return kind


def from_templates(conn, project: Any, user, item: str, docs: list[dict], kind: Any = None) -> dict:
    """Documents of a class made from templates (owner, 8 Nov 2026): any number, from any library the person may use,
    the same template more than once if wanted ([{template: id, title: name}]). Each is a copy of the template's file,
    named <library>-<file>, with its own name when given. A library not yet in the project joins it."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    it = _one(conn, "SELECT * FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
    if not it:
        raise EditError("No such item in this project.", 404)
    kind = _doc_kind(kind)                   # checked before anything goes to Documents
    try:
        docs = [{**d, "template": int(d["template"])} for d in docs or [] if str(d.get("template") or "").strip()]
    except (TypeError, ValueError):
        raise EditError("A template is chosen by its number.") from None
    if not docs:
        raise EditError("Choose at least one template.")
    if len(docs) > 50:
        raise EditError("50 documents at most at once.")
    if not it["mayan_cabinet_id"]:
        raise EditError("The project's repository is not built yet in Documents: try again in a minute.", 409)
    libs: dict[int, dict] = {}
    temps = []
    for d in docs:
        t = _one(conn, "SELECT * FROM proj.lib_templates WHERE id = :i", i=int(d["template"]))
        if not t:
            raise EditError("No such template.", 404)
        lib = libs.get(t["library_id"]) or _one(conn, "SELECT * FROM proj.template_libraries WHERE id = :l", l=t["library_id"])
        libs[lib["id"]] = lib
        if not _sees_library(conn, lib, user):
            raise EditError(f"The template library {lib['name']} is not offered to you.", 403)
        if not _has_file(t, lib["kind"]):
            raise EditError(f"{t['file_name'] or t['name']} in {lib['name']} has no file yet.", 409)
        temps.append((t, lib, " ".join(str(d.get("title") or "").split())[:300]))
    if not it["chosen"]:     # a document in a class not in use brings the class back into use
        conn.execute(text("UPDATE proj.items SET chosen = true, not_needed_reason = '', not_needed_by = NULL, not_needed_at = NULL WHERE id = :i"),
                     {"i": it["id"]})
        queue_rebuild(conn, p["id"])
    have = {r["l"] for r in _rows(conn, "SELECT library_id AS l FROM proj.project_libraries WHERE project_id = :p", p=p["id"])}
    for lib in libs.values():
        if lib["id"] not in have:
            conn.execute(text("""INSERT INTO proj.project_libraries (project_id, library_id, sort_order)
                                 SELECT :p, :l, coalesce(max(sort_order), -1) + 1 FROM proj.project_libraries WHERE project_id = :p"""),
                         {"p": p["id"], "l": lib["id"]})
    made = []
    for t, lib, title in temps:
        content, ctype = _template_bytes(t, lib["kind"])
        name = f"{lib['name']}-{t['file_name'] or t['name']}"
        doc = mayan.upload(name, content, ctype)
        mayan.add_to_cabinet(it["mayan_cabinet_id"], doc["id"])
        row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, title, origin, kind,
                                                        template_id, user_version, created_by, modified_by)
                            VALUES (:p, :i, :f, :m, :n, :t, 'template', :k, :tid, '0.1', :u, :u) RETURNING id, guid::text AS guid""",
                   p=p["id"], i=it["id"], f=it["folder"], m=doc["id"], n=name, t=title, k=kind, tid=t["id"], u=user.username)
        _event(conn, row["id"], user, "made from a template", 1, f"{lib['name']}: {t['file_name'] or t['name']}", "0.1")
        made.append(row["guid"])
    return {"ids": made, "message": f"{len(made)} document{'' if len(made) == 1 else 's'} made from templates in {it['name']}."}


def add_planned(conn, p: dict, user, it: dict, title: str, kind: Any = None) -> dict:
    """A document with no file yet (owner, 8 Nov 2026): its name now, its file later (Add the file)."""
    title = " ".join((title or "").split())[:300]
    if not title:
        raise EditError("Name the document, for example Business Model Canvas.")
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, file_name, title, versions, origin, kind, created_by, modified_by)
                        VALUES (:p, :i, :f, '', :t, 0, 'planned', :k, :u, :u) RETURNING id, guid::text AS guid""",
               p=p["id"], i=it["id"], f=it["folder"], t=title, k=_doc_kind(kind), u=getattr(user, "username", "system"))
    _event(conn, row["id"], user, "planned (no file yet)", 0, title)
    return {"id": row["guid"], "message": f"{title} is in {it['name']}, with no file yet: add its file when you have it."}


def upload(conn, project: Any, user, item: str, file_name: str, content: bytes, user_version: str = "", title: str = "",
           kind: Any = None) -> dict:
    """A new document in an item's folder (stored in Mayan): any number of documents per item (D290). Its name may differ
    from its file's name; with no file it is planned, its file added later (owner, 8 Nov 2026)."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")      # any contributor; a class not in use comes back (owner, 7 Nov 2026)
    it = _one(conn, "SELECT * FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
    if not it:
        raise EditError("No such item in this project.", 404)
    if not content and (title or "").strip():
        return add_planned(conn, p, user, it, title, kind)
    if not file_name or not content:
        raise EditError("Choose a file to upload, or name the document to add its file later.")
    if not it["mayan_cabinet_id"]:
        raise EditError("The project's repository is not built yet in Documents: try again in a minute.", 409)
    uv = _version_label(user_version, False, "upload") or "0.1"     # checked before the file goes to Documents
    kind = _doc_kind(kind)
    ctype = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    doc = mayan.upload(file_name, content, ctype)
    mayan.add_to_cabinet(it["mayan_cabinet_id"], doc["id"])
    if not it["chosen"]:     # a document in a class marked "won't need this" brings the class back into use
        conn.execute(text("""UPDATE proj.items SET chosen = true, not_needed_reason = '', not_needed_by = NULL, not_needed_at = NULL
                             WHERE id = :i"""), {"i": it["id"]})
        queue_rebuild(conn, p["id"])
    title = " ".join((title or "").split())[:300]
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin, created_by, modified_by,
                                                    user_version, title, kind)
                        VALUES (:p, :i, :f, :m, :n, 'upload', :u, :u, :uv, :t, :k) RETURNING id, guid::text AS guid""",
               p=p["id"], i=it["id"], f=it["folder"], m=doc["id"], n=file_name, u=user.username, uv=uv, t=title, k=_doc_kind(kind))
    _event(conn, row["id"], user, "uploaded", 1, file_name, uv)
    return {"id": row["guid"], "message": f"{title or file_name} is in {it['name']}" + (f" (file {file_name})." if title else ".")}


def add_file(conn, project: Any, user, doc: str, file_name: str, content: bytes, user_version: str = "") -> dict:
    """The first file of a planned document (owner, 8 Nov 2026): it becomes version 1."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    _live(d)
    _not_link(d)
    if d["mayan_document_id"]:
        raise EditError(f"{d['title'] or d['file_name']} has its file already: check it out and check in a new version.", 409)
    if not file_name or not content:
        raise EditError("Choose the file.")
    it = _one(conn, "SELECT * FROM proj.items WHERE id = :i", i=d["item_id"]) if d["item_id"] else None
    cabinet = (it or {}).get("mayan_cabinet_id")
    if it is None:
        from . import project_work as pw
        cabinet = pw._cabinet(conn, p, d["folder"])
    if not cabinet:
        raise EditError("The project's repository is not built yet in Documents: try again in a minute.", 409)
    up = mayan.upload(file_name, content, mimetypes.guess_type(file_name)[0] or "application/octet-stream")
    mayan.add_to_cabinet(cabinet, up["id"])
    uv = _version_label(user_version, False, "upload") or "0.1"
    conn.execute(text("""UPDATE proj.documents SET mayan_document_id = :m, file_name = :n, versions = 1, user_version = :uv,
                                modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {"m": up["id"], "n": file_name, "uv": uv, "u": user.username, "i": d["id"]})
    _event(conn, d["id"], user, "file added", 1, file_name, uv)
    return {"id": doc, "message": f"{d['title'] or file_name} has its file now: {file_name} (version 1)."}


def set_title(conn, project: Any, user, doc: str, title: str) -> dict:
    """A document's name, apart from its file's name ('' : shown by its file's name)."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    title = " ".join((title or "").split())[:300]
    if not title and not d["mayan_document_id"] and not (d.get("link_url") or d.get("link_project")):
        raise EditError("A document with no file yet needs a name.")
    conn.execute(text("UPDATE proj.documents SET title = :t, modified_by = :u, modified_at = now() WHERE id = :i"),
                 {"t": title, "u": user.username, "i": d["id"]})
    _event(conn, d["id"], user, "renamed", d["versions"], title or d["file_name"])
    return {"id": doc, "message": f"Named {title or d['file_name']}."}


def download(conn, project: Any, user, doc: str) -> tuple[bytes, str, str]:
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    _not_link(d)
    if not d["mayan_document_id"]:
        raise EditError("This document has no file yet: add its file first.", 404)
    content, ctype, _n = mayan.download(d["mayan_document_id"])
    return content, ctype, d["file_name"]


def _not_link(d: dict) -> None:
    """A link (D296) has no file: nothing to download, check out or check in."""
    if d.get("link_url") or d.get("link_project"):
        raise EditError(f"{_dname(d)} is a link: open it (it has no file, check-out or versions here).", 409)


def _live(d: dict) -> None:
    if d.get("deleted_at"):
        raise EditError(f"{_dname(d)} is deleted: restore it first.", 409)
    if d.get("archived_at"):
        raise EditError(f"{_dname(d)} is archived: restore it first.", 409)


def accept(conn, project: Any, user, doc: str, note: str, evidence_name: str = "", evidence: bytes = b"") -> dict:
    """Accepted directly (D290): anyone who contributes, with the evidence: a note (required) and a file (optional, kept
    in 00_Project/Sign-off evidence). An open request to the sign-off people is withdrawn."""
    from . import project_work as pw
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    _live(d)
    if d["checked_out_by"]:
        raise EditError(f"{_dname(d)} is checked out by {d['checked_out_by']}: check it in first.", 409)
    if d["state"] in ("Approved", "Accepted"):
        raise EditError(f"{_dname(d)} is {d['state'].lower()} already.", 409)
    if d.get("kind") == "None":
        raise EditError(f"{d.get('title') or d['file_name']} is neither a deliverable nor an artifact: it needs no approval.", 409)
    note = (note or "").strip()
    if not note:
        raise EditError("Give the evidence: why it is accepted (and attach the email or minutes if you have them).")
    kept = ""
    if evidence:
        kept = f"{d['file_name']} v{d['versions']} - accepted - {evidence_name or 'evidence'}"
        pw._store(conn, p, user, pw.EVIDENCE, kept, evidence, origin="evidence", kind="Artifact")
    pw.withdraw_request(conn, d["id"], user, "accepted directly")
    conn.execute(text("""UPDATE proj.documents SET state = 'Accepted', signed_version = versions, accepted_by = :u, accepted_at = now(),
                                accepted_note = :n, accepted_evidence = :e WHERE id = :i"""),
                 {"u": user.username, "n": note[:2000], "e": kept, "i": d["id"]})
    _event(conn, d["id"], user, "accepted", d["versions"], note + (f" (evidence: {evidence_name})" if evidence else ""), d["user_version"])
    return {"id": doc, "message": f"{_dname(d)} v{d['versions']} is accepted."}


def set_hidden(conn, project: Any, user, doc: str, how: str, undo: bool = False) -> dict:
    """Archive or delete a document with all its versions, or restore it (D290): anyone who contributes. Neither is shown
    or loaded unless asked for; nothing is removed from Documents, so both can be undone."""
    from . import project_work as pw
    if how not in ("archive", "delete"):
        raise EditError("Archive or delete.")
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    col = "archived" if how == "archive" else "deleted"
    if undo:
        if not d[f"{col}_at"]:
            raise EditError(f"{_dname(d)} is not {col}.", 409)
        conn.execute(text(f"UPDATE proj.documents SET {col}_at = NULL, {col}_by = NULL WHERE id = :i"), {"i": d["id"]})
        _event(conn, d["id"], user, f"restored ({col})", d["versions"])
        return {"id": doc, "message": f"{_dname(d)} is back."}
    if d[f"{col}_at"]:
        raise EditError(f"{_dname(d)} is {col} already.", 409)
    if d["checked_out_by"]:
        raise EditError(f"{_dname(d)} is checked out by {d['checked_out_by']}: check it in or undo the check-out first.", 409)
    pw.withdraw_request(conn, d["id"], user, col)
    conn.execute(text(f"UPDATE proj.documents SET {col}_at = now(), {col}_by = :u WHERE id = :i"), {"u": user.username, "i": d["id"]})
    _event(conn, d["id"], user, col, d["versions"])
    return {"id": doc, "message": f"{_dname(d)} is {col} with all its versions. "
            + ("Tick Show archived to see it again." if col == "archived" else "Tick Show deleted to see it or restore it.")}


def check_out(conn, project: Any, user, doc: str, user_version: str = "") -> dict:
    """Checked out to you: nobody else can check in a new version until you check in or it is undone. No version is asked
    for (owner, D290); one may be given as a note of what is being worked on."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    if d["checked_out_by"]:
        raise EditError(f"Checked out by {d['checked_out_by']} since {_when(d['checked_out_at'])}.", 409)
    _live(d)
    _not_link(d)
    if not d["mayan_document_id"]:
        raise EditError(f"{d['title'] or d['file_name']} has no file yet: add its file first.", 409)
    uv = _version_label(user_version, False, "check-out")
    taken = conn.execute(text("""UPDATE proj.documents SET checked_out_by = :u, checked_out_at = now(), out_version = :uv
                                  WHERE id = :i AND checked_out_by IS NULL RETURNING id"""),
                         {"u": user.username, "i": d["id"], "uv": uv}).scalar()
    if not taken:          # someone else took it a moment ago
        raise EditError("Someone checked it out a moment ago: refresh the page.", 409)
    try:
        mayan.check_out(d["mayan_document_id"])
    except Exception:  # noqa: BLE001 - left checked out in Documents by an earlier try that never reached here: start again
        mayan.check_in(d["mayan_document_id"])
        mayan.check_out(d["mayan_document_id"])
    _event(conn, d["id"], user, "checked out", d["versions"], "", uv)
    return {"id": doc, "message": "Checked out to you: download it, edit it in Office, then check in the new file."}


def check_in(conn, project: Any, user, doc: str, file_name: str, content: bytes, comment: str = "", user_version: str = "") -> dict:
    """The new file becomes the next version; the check-out ends. Your version is asked for; left empty, the next one is
    put in for you (0.3 draft becomes 0.4; nothing yet becomes 0.1) (D290)."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    _not_link(d)
    if (d["checked_out_by"] or "").lower() != user.username.lower():
        raise EditError("Check the document out first: only the person who checked it out checks it in." if not d["checked_out_by"]
                        else f"Checked out by {d['checked_out_by']}: only they check it in (or have it undone).", 409)
    if not content:
        raise EditError("Choose the new file.")
    if not (comment or "").strip():
        raise EditError("Say what changed in this version.")
    uv = _version_label(user_version, False, "check-in") or next_version(d.get("user_version") or d.get("out_version"))
    note = f"{user.username}: {comment}".strip(": ")
    import hashlib
    # Documents' files and our version count stay in step (review, 8 Nov 2026): a check-in whose save failed after
    # Documents took the file is tried again without adding it twice (Documents has one file more than we count); the
    # same file as the current version is refused (nothing changed: undo the check-out instead)
    try:
        held = len(mayan.files(d["mayan_document_id"]))
    except Exception:  # noqa: BLE001
        held = None
    retry = held is not None and held > d["versions"]
    if not retry:
        try:
            same = mayan.latest(d["mayan_document_id"]).get("checksum") == hashlib.sha256(content).hexdigest()
        except Exception:  # noqa: BLE001
            same = False
        if same:
            raise EditError(f"This file is the same as version {d['versions']}: nothing changed. Choose the changed file, "
                            "or undo the check-out.", 409)
    mayan.check_in(d["mayan_document_id"])
    if not retry:
        mayan.new_version(d["mayan_document_id"], file_name or d["file_name"], content, note,
                          mimetypes.guess_type(file_name or d["file_name"])[0] or "application/octet-stream")
    conn.execute(text("""UPDATE proj.documents SET versions = versions + 1, checked_out_by = NULL, checked_out_at = NULL,
                                file_name = :n, modified_by = :u, modified_at = now(), user_version = :uv, out_version = '',
                                state = CASE WHEN state IN ('Approved', 'Accepted', 'Rejected') THEN 'Draft' ELSE state END
                          WHERE id = :i"""),
                 {"n": file_name or d["file_name"], "u": user.username, "i": d["id"], "uv": uv})
    _event(conn, d["id"], user, "checked in", d["versions"] + 1, comment, uv)
    from . import project_work as pw
    pw.withdraw_open(conn, d["id"], user)
    return {"id": doc, "message": f"Version {d['versions'] + 1} ({uv}) checked in."}


def undo_check_out(conn, project: Any, user, doc: str) -> dict:
    """Ends a check-out without a new version: the person who checked out, or the Lead Architect, a Model Admin, the
    Project Admin or a Super Admin."""
    from . import mayan
    p = project_row(conn, project)
    d = _doc(conn, p, doc)
    if not d["checked_out_by"]:
        _need(conn, p, user, "contribute")
        try:
            mayan.check_in(d["mayan_document_id"])     # left checked out in Documents only: freed there
        except Exception:  # noqa: BLE001
            pass
        raise EditError("It is not checked out.", 409)
    _need(conn, p, user, "contribute" if d["checked_out_by"].lower() == user.username.lower() else "undo")
    mayan.check_in(d["mayan_document_id"])
    conn.execute(text("UPDATE proj.documents SET checked_out_by = NULL, checked_out_at = NULL WHERE id = :i"), {"i": d["id"]})
    _event(conn, d["id"], user, "check-out undone", d["versions"], f"was checked out by {d['checked_out_by']}")
    if d["checked_out_by"].lower() != user.username.lower():
        from . import notify
        notify.create(core(conn), kind="project.checkout_undone", category="model", actor=user.username,
                      title=f"{user.username} undid your check-out of {d['file_name']}",
                      body=f"Project {p['name']}: your changes were not checked in. Check it out again to carry on.",
                      link=f"#/projects/{p['guid']}/repository", recipients=[d["checked_out_by"]])
    return {"id": doc, "message": "Check-out undone."}


def template_download(conn, project: Any, user, template_id: int) -> tuple[bytes, str, str]:
    """A template of one of the project's libraries, straight from the library (anyone on the project)."""
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    t = _one(conn, """SELECT t.*, l.name AS library, l.kind FROM proj.lib_templates t
                        JOIN proj.template_libraries l ON l.id = t.library_id
                        JOIN proj.project_libraries pl ON pl.library_id = l.id AND pl.project_id = :p
                       WHERE t.id = :t""", p=p["id"], t=template_id)
    if not t or not _has_file(t, t["kind"]):
        raise EditError("That template is not in this project's libraries, or has no file yet.", 404)
    data, ctype = _template_bytes(t, t["kind"])
    return data, ctype, f"{t['library']}-{t['file_name'] or t['name']}"


def _step(conn, p: dict, step_id: int) -> dict:
    s = _one(conn, "SELECT * FROM proj.steps WHERE project_id = :p AND id = :s", p=p["id"], s=step_id)
    if not s:
        raise EditError("No such step in this project.", 404)
    if s["removed"]:
        raise EditError("This step was removed from the project.")
    return s


def _step_event(conn, step_id: int, user, action: str, note: str = "", at: Any = None) -> None:
    """A step's history (owner, 8 Nov 2026): when it was opened, closed and reopened, and by whom."""
    conn.execute(text("""INSERT INTO proj.step_events (step_id, by_user, action, note, at)
                         VALUES (:s, :u, :a, :n, coalesce(CAST(:at AS timestamptz), now()))"""),
                 {"s": step_id, "u": getattr(user, "username", "system"), "a": action, "n": (note or "")[:1000], "at": at})


def mark_step(conn, project: Any, user, step_id: int, done: bool, note: str = "") -> dict:
    """A step is marked done, or not done again, by anyone who contributes (D275). Marking a step done records who did it
    and when as a sub step of the same name under it (owner, 7 Nov 2026). A sub step ("+ sub step", work to do again) is
    completed on its own: completing it never completes the step; someone marks the step done (owner, 8 Nov 2026).
    Not done again: the step's completion record made by marking it is taken back."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    s = _step(conn, p, step_id)
    note = (note or "").strip()[:1000]
    if s.get("parent_step_id"):                     # a sub step: complete it, or open it again (its step is not touched)
        conn.execute(text("""UPDATE proj.steps SET done_at = CASE WHEN :d THEN now() END, done_by = CASE WHEN :d THEN :u END,
                                    done_note = CASE WHEN :d AND :n <> '' THEN :n ELSE done_note END WHERE id = :s"""),
                     {"d": done, "u": user.username, "s": step_id, "n": note})
        if bool(s["done_at"]) != done:
            _step_event(conn, step_id, user, "closed" if done else "reopened", note)
        return {"step": step_id, "done": done, "message": f"{'Done' if done else 'Open again'}: {s['name']} (sub step; the step itself is marked done on its own)"}
    if done:
        if s["done_at"]:                        # ticked twice (two people, a double click): nothing more to record
            return {"step": step_id, "done": True, "message": f"{s['name']} is done already."}
        n = (_one(conn, "SELECT count(*) AS n FROM proj.steps WHERE parent_step_id = :s", s=step_id) or {"n": 0})["n"]
        conn.execute(text("""INSERT INTO proj.steps (project_id, cycle, phase, seq, name, parent_step_id, done_at, done_by, done_note,
                                                     added_by, added_at)
                             VALUES (:p, :c, :ph, :q, :nm, :s, now(), :u, :n, :u, now())"""),
                     {"p": p["id"], "c": s["cycle"], "ph": s["phase"], "q": n + 1, "nm": s["name"], "s": step_id, "u": user.username, "n": note})
    else:                       # not done again: the completion record made by marking it is taken back
        last = _one(conn, """SELECT id FROM proj.steps WHERE parent_step_id = :s AND done_at IS NOT NULL AND added_at = done_at
                              ORDER BY done_at DESC, id DESC LIMIT 1""", s=step_id)
        if last:
            conn.execute(text("DELETE FROM proj.steps WHERE id = :i"), {"i": last["id"]})
    conn.execute(text("""UPDATE proj.steps SET done_at = CASE WHEN :d THEN now() END, done_by = CASE WHEN :d THEN :u END,
                                done_note = CASE WHEN :d AND :n <> '' THEN :n ELSE done_note END WHERE id = :s"""),
                 {"d": done, "u": user.username, "s": step_id, "n": note})
    if bool(s["done_at"]) != done:
        _step_event(conn, step_id, user, "closed" if done else "reopened", note)
    still = (_one(conn, "SELECT count(*) AS n FROM proj.steps WHERE parent_step_id = :s AND done_at IS NULL", s=step_id) or {"n": 0})["n"]
    return {"step": step_id, "done": done, "message": f"{'Done' if done else 'Reopened'}: {s['name']}"
            + (f" ({still} sub step{'s' if still != 1 else ''} still open)" if done and still else "")}


def add_step(conn, project: Any, user, d: dict) -> dict:
    """A step of the project's own, added at any time to a phase (anyone who contributes; owner, 7 Nov 2026)."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    name = (d.get("name") or "").strip()
    if not name:
        raise EditError("Give the step a name.")
    if len(name) > 300:
        raise EditError("The step's name is 300 characters at most.")
    phase = d.get("phase") or ""
    if not _one(conn, "SELECT 1 AS x FROM proj.lib_phases WHERE code = :c", c=phase):
        raise EditError("Choose the phase the step belongs to.")
    seq = (_one(conn, """SELECT coalesce(max(seq), 0) AS n FROM proj.steps WHERE project_id = :p AND cycle = :c AND phase = :ph
                          AND parent_step_id IS NULL""", p=p["id"], c=p["cycle"], ph=phase) or {"n": 0})["n"] + 1
    r = _one(conn, """INSERT INTO proj.steps (project_id, cycle, phase, seq, name, added_by, added_at, due_date)
                      VALUES (:p, :c, :ph, :q, :n, :u, now(), :due) RETURNING id""",
             p=p["id"], c=p["cycle"], ph=phase, q=seq, n=name, u=user.username, due=d.get("due_date") or None)
    _step_event(conn, r["id"], user, "opened")
    return {"step": r["id"], "message": f"Step added to phase {phase}: {name}."}


def add_substep(conn, project: Any, user, step_id: int, d: dict) -> dict:
    """"+ sub step": the step is to be done again; the sub step is opened now and completed later, and the step is open
    until someone marks it done again (owner, 7 and 8 Nov 2026)."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    s = _step(conn, p, step_id)
    if s["parent_step_id"]:
        raise EditError("Add the sub step to the step itself.")
    n = (_one(conn, "SELECT count(*) AS n FROM proj.steps WHERE parent_step_id = :s", s=step_id) or {"n": 0})["n"]
    if not n and s["done_at"]:      # done before sub steps existed: that completion becomes the first sub step
        conn.execute(text("""INSERT INTO proj.steps (project_id, cycle, phase, seq, name, parent_step_id, done_at, done_by, done_note,
                                                     added_by, added_at)
                             VALUES (:p, :c, :ph, 1, :nm, :s, :a, :b, :n, :b, :a)"""),
                     {"p": p["id"], "c": s["cycle"], "ph": s["phase"], "nm": s["name"], "s": step_id, "a": s["done_at"],
                      "b": s["done_by"], "n": s["done_note"] or ""})
        n = 1
    name = (d.get("name") or "").strip() or s["name"]
    # its open date (owner, 8 Nov 2026): today unless given; not after the date it is due by
    opened = str(d.get("open_date") or "").strip() or None
    if opened and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", opened):
        raise EditError("The open date is a date, for example 2026-11-08.")
    if opened and d.get("due_date") and str(d["due_date"]) < opened:
        raise EditError("It is due before it opens: choose a due date on or after the open date.")
    r = _one(conn, """INSERT INTO proj.steps (project_id, cycle, phase, seq, name, parent_step_id, added_by, added_at, due_date, done_note)
                      VALUES (:p, :c, :ph, :q, :n, :s, :u, coalesce(CAST(:op AS date)::timestamptz, now()), :due, :note) RETURNING id""",
             p=p["id"], c=s["cycle"], ph=s["phase"], q=n + 1, n=name[:300], s=step_id, u=user.username, op=opened,
             due=d.get("due_date") or None, note=(d.get("note") or "").strip()[:1000])
    _step_event(conn, r["id"], user, "opened", "", opened)
    # to be done again: the step is open until someone marks it done (completing the sub step does not)
    conn.execute(text("UPDATE proj.steps SET done_at = NULL, done_by = NULL WHERE id = :s"), {"s": step_id})
    if s["done_at"]:
        _step_event(conn, step_id, user, "reopened", "a sub step was opened")
    return {"step": r["id"], "message": f"{s['name']}: opened again, to complete{(' by ' + str(d['due_date'])) if d.get('due_date') else ''}."}


def delete_substep(conn, project: Any, user, step_id: int) -> dict:
    """An open sub step taken away again (a completed one is reopened with Not done instead)."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    s = _step(conn, p, step_id)
    if not s["parent_step_id"]:
        raise EditError("Only a sub step is taken away; a step of the library is removed in the wizard (with the reason).")
    if s["done_at"]:
        raise EditError("This sub step is done: mark it not done first.")
    conn.execute(text("DELETE FROM proj.steps WHERE id = :i"), {"i": step_id})
    return {"step": step_id, "message": "Sub step taken away."}


VERSION_ACTIONS = ("uploaded", "checked in", "file added", "made from a template", "back to a tag")


def versions(conn, project: Any, user, doc: str) -> list[dict]:
    """A document's versions only, newest first (owner, 8 Nov 2026): each with its number, your version, who, when and
    what changed; not every other thing that happened to it. A copy from a template made by the repository build has
    no event: its first version is made up from the document."""
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    rows = _rows(conn, """SELECT DISTINCT ON (version) version, at, by_user, action, user_version, note FROM proj.document_events
                           WHERE document_id = :d AND action = ANY (CAST(:a AS text[])) AND version IS NOT NULL
                           ORDER BY version, at DESC""", d=d["id"], a=list(VERSION_ACTIONS))
    have = {r["version"] for r in rows}
    if d["versions"] >= 1 and 1 not in have:
        rows.append({"version": 1, "at": d["created_at"], "by_user": d["created_by"],
                     "action": "made from a template" if d["origin"] == "template" else "uploaded", "user_version": "",
                     "note": "copied from its template when the repository was built" if d["origin"] == "template" else ""})
    rows = [r for r in rows if 1 <= r["version"] <= d["versions"]]
    return sorted(rows, key=lambda r: -r["version"])


def download_version(conn, project: Any, user, doc: str, version: int) -> tuple[bytes, str, str]:
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    _not_link(d)
    if not d["mayan_document_id"]:
        raise EditError("This document has no file yet.", 404)
    if not 1 <= int(version) <= d["versions"]:
        raise EditError(f"{_dname(d)} has versions 1 to {d['versions']}.", 404)
    content, ctype, name = mayan.download_version(d["mayan_document_id"], int(version))
    base, dot, ext = (name or d["file_name"]).rpartition(".")
    return content, ctype, f"{base} (v{version}).{ext}" if dot else f"{name} (v{version})"


def class_templates(conn, p: dict) -> dict[str, list[dict]]:
    """Per document class (item guid): the templates to download (owner, 8 Nov 2026): those it was set up with (its
    library item's templates in the project's libraries, or those chosen for it) and those added to it since."""
    by_item, _f, _l = _project_templates(conn, p["id"])
    by_id = _project_templates_by_id(conn, p["id"])
    out: dict[str, list[dict]] = {}
    items = _rows(conn, """SELECT guid::text AS g, library_id, templates, offered_templates FROM proj.items
                            WHERE project_id = :p AND cycle = :c""", p=p["id"], c=p.get("cycle") or 1)
    for it in items:
        rows, seen = [], set()
        base = list(by_item.get(it["library_id"], [])) if it["library_id"] else []
        chosen = it["templates"]
        for t in base + [by_id[x] for x in chosen or [] if x in by_id]:
            if t["id"] in seen or (chosen is not None and t["id"] not in chosen):
                continue
            seen.add(t["id"])
            rows.append({"id": t["id"], "library": t["library"], "name": t["file_name"] or t["name"], "added": False})
        for x in it["offered_templates"] or []:
            if x in by_id and x not in seen:
                seen.add(x)
                t = by_id[x]
                rows.append({"id": x, "library": t["library"], "name": t["file_name"] or t["name"], "added": True})
        if rows:
            out[it["g"]] = rows
    return out


def offer_template(conn, project: Any, user, item: str, template_id: int, remove: bool = False) -> dict:
    """A template added to a document class to download (or taken off again). Its library joins the project."""
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    it = _one(conn, "SELECT * FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
    if not it:
        raise EditError("No such document class in this project.", 404)
    t = _one(conn, "SELECT * FROM proj.lib_templates WHERE id = :i", i=int(template_id))
    if not t:
        raise EditError("No such template.", 404)
    name = t["file_name"] or t["name"]
    if remove:
        conn.execute(text("UPDATE proj.items SET offered_templates = array_remove(offered_templates, CAST(:t AS bigint)) WHERE id = :i"),
                     {"t": t["id"], "i": it["id"]})
        return {"message": f"{name} is no longer offered in {it['name']}."}
    lib = _one(conn, "SELECT * FROM proj.template_libraries WHERE id = :l", l=t["library_id"])
    if not _sees_library(conn, lib, user):
        raise EditError(f"The template library {lib['name']} is not offered to you.", 403)
    if not _has_file(t, lib["kind"]):
        raise EditError(f"{name} has no file yet.", 409)
    conn.execute(text("""INSERT INTO proj.project_libraries (project_id, library_id, sort_order)
                         SELECT :p, :l, coalesce(max(sort_order), -1) + 1 FROM proj.project_libraries WHERE project_id = :p
                         ON CONFLICT DO NOTHING"""), {"p": p["id"], "l": lib["id"]})
    conn.execute(text("""UPDATE proj.items SET offered_templates = array_append(offered_templates, CAST(:t AS bigint))
                          WHERE id = :i AND NOT (CAST(:t AS bigint) = ANY (offered_templates))"""), {"t": t["id"], "i": it["id"]})
    return {"message": f"{lib['name']} › {name} is offered in {it['name']}: download it, or make a document from it."}


def history(conn, project: Any, user, doc: str) -> list[dict]:
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    return _rows(conn, """SELECT at, by_user, action, version, user_version, note FROM proj.document_events WHERE document_id = :d
                           ORDER BY at DESC, id DESC""", d=d["id"])


# ---------------------------------------------------------------- template libraries (D264)
def _super_or_library(user) -> bool:
    return perms.allowed(user.roles, "projects.library")


def setup_state(conn) -> dict:
    """Projects can start once a template library is offered to them. EA Explorer's own is offered from the start, so
    nothing has to be done first (owner, 7 Nov 2026): TOGAF 10 and an organisation's own library are optional extras."""
    r = _one(conn, "SELECT done_by, done_at FROM proj.template_setup WHERE id = 1")
    offered = _one(conn, "SELECT count(*) AS n FROM proj.template_libraries WHERE shared AND state = 'ready'")["n"]
    return {"done": bool(r) or offered > 0, "confirmed": bool(r), "offered": offered,
            "done_by": r["done_by"] if r else None, "done_at": r["done_at"] if r else None}


def _library_row(conn, lib: Any) -> dict:
    key = str(lib)
    r = _one(conn, f"""SELECT * FROM proj.template_libraries
                       WHERE {'guid = CAST(:k AS uuid)' if re.fullmatch(r'[0-9a-fA-F-]{36}', key) else 'name = :k'}""", k=key)
    if not r:
        raise EditError(f"No template library {key}.", 404)
    return r


def _sees_library(conn, lib: dict, user) -> bool:
    if lib["shared"] or _super_or_library(user) or lib["created_by"].lower() == user.username.lower():
        return True
    return bool(lib["project_id"] and my_roles(conn, {"id": lib["project_id"]}, user))


def _has_file(t: dict, kind: str) -> bool:
    if kind == "ea-explorer":
        return (EA_TEMPLATES_DIR / t["path"]).is_file() or bool(t["mayan_document_id"])
    return bool(t["mayan_document_id"])


def libraries(conn, user) -> list[dict]:
    """The template libraries this person may use: the shared ones, their own private ones (and a Super Admin's: all)."""
    rows = _rows(conn, """SELECT l.*, l.guid::text AS gid, p.name AS project_name, p.guid::text AS project_guid
                            FROM proj.template_libraries l LEFT JOIN proj.projects p ON p.id = l.project_id
                           ORDER BY CASE l.kind WHEN 'ea-explorer' THEN 0 WHEN 'togaf' THEN 1 ELSE 2 END, l.name""")
    out = []
    for lib in rows:
        if not _sees_library(conn, lib, user):
            continue
        temps = _rows(conn, "SELECT path, mayan_document_id FROM proj.lib_templates WHERE library_id = :l", l=lib["id"])
        files = sum(1 for t in temps if _has_file(t, lib["kind"]))
        out.append({"id": lib["gid"], "name": lib["name"], "kind": lib["kind"], "description": lib["description"],
                    "shared": lib["shared"], "state": lib["state"], "note": lib["note"], "templates": len(temps), "files": files,
                    "usable": lib["state"] == "ready" and files > 0, "created_by": lib["created_by"], "created_at": lib["created_at"],
                    "project": lib["project_name"], "project_id": lib["project_guid"],
                    "may_share": _super_or_library(user), "may_download": files > 0})
    return out


def finish_setup(conn, user, shared: list[str]) -> dict:
    """The Super Admin's template library setup (before the first project): which libraries are offered to projects."""
    _need_library(user)
    ids = set(shared or [])
    if not ids:
        raise EditError("Offer at least one template library to projects (EA Explorer's own can be used as it is).")
    for lib in _rows(conn, "SELECT id, guid::text AS gid, name, state FROM proj.template_libraries"):
        on = lib["gid"] in ids
        if on and lib["state"] != "ready":
            raise EditError(f"{lib['name']} is still {lib['state']}: wait for it, or leave it out.")
        conn.execute(text("""UPDATE proj.template_libraries SET shared = :s,
                                    shared_by = CASE WHEN :s AND NOT shared THEN :u ELSE shared_by END,
                                    shared_at = CASE WHEN :s AND NOT shared THEN now() ELSE shared_at END WHERE id = :i"""),
                     {"s": on, "u": user.username, "i": lib["id"]})
    conn.execute(text("""INSERT INTO proj.template_setup (id, done_by) VALUES (1, :u)
                         ON CONFLICT (id) DO UPDATE SET done_by = EXCLUDED.done_by, done_at = now()"""), {"u": user.username})
    return {"message": "Template library setup finished: projects can be created.", "setup": setup_state(conn)}


def share_library(conn, user, lib: str, shared: bool) -> dict:
    """A Super Admin offers a library to every project, or stops offering it (projects keep the copies they made)."""
    _need_library(user)
    row = _library_row(conn, lib)
    if shared and row["state"] != "ready":
        raise EditError(f"{row['name']} is still {row['state']}.")
    conn.execute(text("""UPDATE proj.template_libraries SET shared = :s, shared_by = CASE WHEN :s THEN :u ELSE shared_by END,
                                shared_at = CASE WHEN :s THEN now() ELSE shared_at END WHERE id = :i"""),
                 {"s": shared, "u": user.username, "i": row["id"]})
    if row["project_id"] or row["created_by"] != "system":
        from . import notify
        notify.create(core(conn), kind="project.library", category="model", actor=user.username,
                      title=f"Template library {row['name']} is {'now offered to every project' if shared else 'no longer offered'}",
                      body="", link="#/project-admin", recipients=[row["created_by"]])
    return {"message": f"{row['name']} is {'offered to every project' if shared else 'no longer offered to new projects'}."}


ZIP_SKIP = ("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")
MAX_LIBRARY_ZIP = 500 * 1024 * 1024


def _zip_entries(content: bytes) -> list[tuple[str, int]]:
    import io
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise EditError("The template library is uploaded as one .zip file in the library's folder layout.") from exc
    out = []
    for info in z.infolist():
        name = info.filename.replace("\\", "/")
        base = name.rsplit("/", 1)[-1]
        if info.is_dir() or any(s in name for s in ZIP_SKIP) or base.startswith((".", "~$")) or base.lower() in ("manifest.json", "read me.txt"):
            continue
        if ".." in name.split("/") or name.startswith("/"):
            raise EditError(f"The zip holds an unsafe path: {name}.")
        out.append((name, info.file_size))
    if not out:
        raise EditError("The zip holds no files.")
    return out


def add_library(conn, user, name: str, content: bytes, description: str = "") -> dict:
    """A new template library from a zip in the library's folder layout (download EA Explorer's to start from). It is
    private to whoever adds it until a Super Admin shares it; the files are stored in Documents in the background."""
    if not (may_create(user) or _super_or_library(user)):
        raise EditError("Adding a template library needs a global role.", 403)
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise EditError("Give the template library a name (up to 80 characters).")
    if _one(conn, "SELECT 1 AS x FROM proj.template_libraries WHERE lower(name) = lower(:n)", n=name):
        raise EditError(f"There is already a template library called {name}.", 409)
    if len(content) > MAX_LIBRARY_ZIP:
        raise EditError("The zip is larger than 500 MB.", 413)
    entries = _zip_entries(content)
    lib = _one(conn, """INSERT INTO proj.template_libraries (name, kind, description, shared, state, note, created_by)
                        VALUES (:n, 'own', :d, false, 'loading', :note, :u) RETURNING id, guid::text AS gid""",
               n=name, d=(description or "").strip(), note=f"{len(entries)} files waiting to be stored in Documents.", u=user.username)
    conn.execute(text("INSERT INTO proj.template_library_uploads (library_id, content, uploaded_by) VALUES (:l, :c, :u)"),
                 {"l": lib["id"], "c": content, "u": user.username})
    return {"id": lib["gid"], "library_id": lib["id"], "name": name, "files": len(entries),
            "message": f"{name}: {len(entries)} files are being stored in Documents. It is yours (and your project's) until "
                       "a Super Admin offers it to every project."}


def pending_library_loads(conn) -> list[int]:
    return [r["library_id"] for r in _rows(conn, "SELECT library_id FROM proj.template_library_uploads ORDER BY uploaded_at")]


def _place(conn, path: str) -> tuple[str | None, str]:
    """Which library item (deliverable or artifact) a file in the library layout belongs to, and its folder."""
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    items = _rows(conn, "SELECT id, work_folder FROM proj.lib_items WHERE NOT retired")
    best = max((i for i in items if folder == i["work_folder"] or folder.startswith(i["work_folder"] + "/")),
               key=lambda i: len(i["work_folder"]), default=None)
    return (best["id"] if best else None), folder


def load_library_upload(conn_factory, library_id: int) -> str:
    """Stores an uploaded library zip's files in Mayan, one template per file (background job)."""
    import io
    import zipfile

    from . import mayan
    with conn_factory() as conn:
        up = _one(conn, "SELECT content, uploaded_by FROM proj.template_library_uploads WHERE library_id = :l", l=library_id)
        lib = _one(conn, "SELECT * FROM proj.template_libraries WHERE id = :l", l=library_id)
    if not up or not lib:
        return "nothing to load"
    raw = up["content"]
    content = bytes.fromhex(raw[2:]) if isinstance(raw, str) and raw.startswith("\\x") else bytes(raw)
    if lib["kind"] == "togaf":
        return _load_togaf_zip(conn_factory, lib, up["uploaded_by"], content)
    try:
        entries = _zip_entries(content)
        z = zipfile.ZipFile(io.BytesIO(content))
        tops = {n.split("/", 1)[0] for n, _s in entries}
        with conn_factory() as conn:
            known = {r["work_folder"].split("/", 1)[0] for r in _rows(conn, "SELECT work_folder FROM proj.lib_items")}
            known |= {r["path"].split("/", 1)[0] for r in _rows(conn, "SELECT path FROM proj.lib_folders")}
            have = {r["path"] for r in _rows(conn, "SELECT path FROM proj.lib_templates WHERE library_id = :l", l=library_id)}
        strip = len(tops) == 1 and not (tops & known) and all("/" in n for n, _s in entries)   # a zip of the whole folder
        root = mayan.cabinet("EA Explorer library templates")
        lc = mayan.cabinet(lib["name"], root)
        stored = 0
        for name, _size in entries:
            path = name.split("/", 1)[1] if strip else name
            if path in have:
                continue
            with conn_factory() as conn:
                item, folder = _place(conn, path)
            fname = path.rsplit("/", 1)[-1]
            doc = mayan.upload(fname, z.read(name), mimetypes.guess_type(fname)[0] or "application/octet-stream",
                               label=f"{lib['name']}-{fname}")
            mayan.add_to_cabinet(mayan.cabinet_path(folder, lc) if folder else lc, doc["id"])
            with conn_factory() as conn:
                conn.execute(text("""INSERT INTO proj.lib_templates (library_id, path, item_id, source, name, folder, origin,
                                                                     mayan_document_id, file_name, uploaded_by, uploaded_at)
                                     VALUES (:l, :p, :i, :s, :n, :f, 'Uploaded', :m, :n, :u, now())
                                     ON CONFLICT (library_id, path) DO NOTHING"""),
                             {"l": library_id, "p": path, "i": item, "s": lib["name"], "n": fname, "f": folder, "m": doc["id"],
                              "u": up["uploaded_by"]})
            stored += 1
        with conn_factory() as conn:
            n = _one(conn, "SELECT count(*) AS n, count(item_id) AS items FROM proj.lib_templates WHERE library_id = :l", l=library_id)
            conn.execute(text("DELETE FROM proj.template_library_uploads WHERE library_id = :l"), {"l": library_id})
            note = f"Ready: {n['n']} templates ({n['items']} for deliverables and artifacts, {n['n'] - n['items']} in other folders)."
            conn.execute(text("UPDATE proj.template_libraries SET state = 'ready', note = :n WHERE id = :l"), {"n": note, "l": library_id})
        _notify_from_job(kind="project.library", category="model", actor="system", title=f"Template library {lib['name']} is ready",
                         body=note, link="#/project-admin", recipients=[lib["created_by"]], conn_factory=conn_factory)
        return note
    except Exception as exc:
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.template_libraries SET state = 'failed', note = :n WHERE id = :l"),
                         {"n": f"Not stored yet: {str(exc)[:300]}. Tried again every minute.", "l": library_id})
        raise


def _notify_from_job(conn_factory, **kw) -> None:
    """A notification from a background job: in the repository's database (D266)."""
    from . import notify
    from .db import get_engine, projects_separate
    if projects_separate():
        with get_engine().begin() as c:
            notify.create(c, **kw)
    else:
        with conn_factory() as c:
            notify.create(c, **kw)


def _zip_files(content: bytes) -> list[tuple[str, bytes]]:
    """Every file of a zip as (path, bytes), the files of zips inside it too (one level), junk left out."""
    import io
    import zipfile
    out = []
    z = zipfile.ZipFile(io.BytesIO(content))
    for name, _s in _zip_entries(content):
        data = z.read(name)
        if name.lower().endswith(".zip"):
            try:
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                continue
            for n2, _s2 in _zip_entries(data):
                out.append((f"{name[:-4]}/{n2}", inner.read(n2)))
        else:
            out.append((name, data))
    return out


def _togaf_match(temps: list[dict], name: str, parent: str) -> list[dict]:
    """The TOGAF templates a file is, by its name (the folder decides when two phases share a name)."""
    stem = name.rsplit(".", 1)[0]
    match = [t for t in temps if t["name"] == name or t["name"] == stem or t["name"].removesuffix(".docx") == stem]
    if len(match) > 1:
        match = [t for t in match if parent and parent in (t["folder"] or "")] or match[:1]
    return match


def add_library_zip(conn, user, lib: str, content: bytes) -> dict:
    """The TOGAF template deliverables as one zip (the I094 download as it is): stored in the background, each file
    against the TOGAF template of its name, unchanged (Super Admins)."""
    _need_library(user)
    row = _library_row(conn, lib)
    if row["kind"] != "togaf":
        raise EditError("Upload a changed library as a new library (Add a template library); EA Explorer's own is fixed.")
    if len(content) > MAX_LIBRARY_ZIP:
        raise EditError("The zip is larger than 500 MB.", 413)
    files = _zip_files(content)
    conn.execute(text("""INSERT INTO proj.template_library_uploads (library_id, content, uploaded_by) VALUES (:l, :c, :u)
                         ON CONFLICT (library_id) DO UPDATE SET content = EXCLUDED.content, uploaded_by = EXCLUDED.uploaded_by,
                                                               uploaded_at = now()"""),
                 {"l": row["id"], "c": content, "u": user.username})
    conn.execute(text("UPDATE proj.template_libraries SET state = 'loading', note = :n WHERE id = :l"),
                 {"n": f"{len(files)} files in the zip waiting to be stored in Documents.", "l": row["id"]})
    return {"library_id": row["id"], "files": len(files),
            "message": f"{len(files)} files received: each TOGAF template is stored in Documents in the background, unchanged."}


def _load_togaf_zip(conn_factory, lib: dict, uploaded_by: str, content: bytes) -> str:
    from . import mayan
    try:
        files = _zip_files(content)
        with conn_factory() as conn:
            temps = _rows(conn, "SELECT id, name, folder, mayan_document_id FROM proj.lib_templates WHERE library_id = :l", l=lib["id"])
        root = mayan.cabinet("EA Explorer library templates")
        lc = mayan.cabinet(lib["name"], root)
        loaded, skipped = 0, []
        for path, data in files:
            name = path.rsplit("/", 1)[-1]
            parent = path.rsplit("/", 2)[-2] if path.count("/") else ""
            match = [t for t in _togaf_match(temps, name, parent) if not t["mayan_document_id"]]
            if not match and not _togaf_match(temps, name, parent):
                skipped.append(name)
                continue
            for t in match:
                doc = mayan.upload(name, data, mimetypes.guess_type(name)[0] or "application/octet-stream", label=f"{lib['name']}-{name}")
                mayan.add_to_cabinet(mayan.cabinet_path(t["folder"], lc) if t["folder"] else lc, doc["id"])
                with conn_factory() as conn:
                    conn.execute(text("""UPDATE proj.lib_templates SET mayan_document_id = :m, file_name = :f, uploaded_by = :u,
                                                uploaded_at = now() WHERE id = :i"""),
                                 {"m": doc["id"], "f": name, "u": uploaded_by, "i": t["id"]})
                t["mayan_document_id"] = doc["id"]
                loaded += 1
        with conn_factory() as conn:
            n = _one(conn, "SELECT count(*) AS n, count(mayan_document_id) AS f FROM proj.lib_templates WHERE library_id = :l", l=lib["id"])
            note = (f"Ready: {n['f']} of {n['n']} TOGAF templates have their file ({loaded} stored now)."
                    + (f" {len(skipped)} file(s) in the zip are not TOGAF templates of the library and were left out." if skipped else ""))
            conn.execute(text("DELETE FROM proj.template_library_uploads WHERE library_id = :l"), {"l": lib["id"]})
            conn.execute(text("UPDATE proj.template_libraries SET state = 'ready', note = :n WHERE id = :l"), {"n": note, "l": lib["id"]})
        _notify_from_job(kind="project.library", category="model", actor="system", title="The TOGAF 10 templates are loaded",
                         body=note, link="#/project-admin/library", recipients=[uploaded_by], conn_factory=conn_factory)
        return note
    except Exception as exc:
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.template_libraries SET state = 'failed', note = :n WHERE id = :l"),
                         {"n": f"Not stored yet: {str(exc)[:300]}. Tried again every minute.", "l": lib["id"]})
        raise


def _template_bytes(t: dict, kind: str) -> tuple[bytes, str]:
    from . import mayan
    if kind == "ea-explorer" and (EA_TEMPLATES_DIR / t["path"]).is_file():
        f = EA_TEMPLATES_DIR / t["path"]
        return f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    content, ctype, _n = mayan.download(t["mayan_document_id"])
    return content, ctype


def library_zip(conn, user, lib: str) -> tuple[bytes, str]:
    """The whole library as one zip in its folder layout, to rebrand and upload back as a new library."""
    import io
    import zipfile
    row = _library_row(conn, lib)
    if not _sees_library(conn, row, user):
        raise EditError("Not allowed to see this template library.", 403)
    temps = [t for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=row["id"])
             if _has_file(t, row["kind"])]
    if not temps:
        raise EditError(f"{row['name']} has no files yet.", 409)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for t in temps:
            data, _c = _template_bytes(t, row["kind"])
            z.writestr(t["path"], data)
        z.writestr("Read me.txt", README_ZIP.format(name=row["name"]))
    return out.getvalue(), f"{_slug(row['name'])}_templates.zip"


README_ZIP = """{name}: template library from EA Explorer

Each deliverable and artifact has its own folder (09_ADM_Phase_Workspaces/<phase>/Deliverables or Artifacts/...).
To make your own library:
  1. Rebrand or replace the files you want (keep them in their folders; the file names may change).
  2. Add more documents to any folder: each becomes a template of that deliverable, artifact or folder.
  3. Zip the folders again and upload the zip as a new template library (Administration > Project library, or in
     the project wizard). Give it its own name.
Files in a deliverable's or artifact's folder are copied into that item's folder of every project that uses the
library, named <library name>-<file name>.
"""


# ---------------------------------------------------------------- TOGAF's files (Super Admins, once)
def _need_library(user) -> None:
    if not _super_or_library(user):
        raise EditError("The project library is kept by Super Admins.", 403)


def upload_template(conn, user, template_id: int, file_name: str, content: bytes) -> dict:
    """A template's file, stored in Mayan exactly as uploaded (TOGAF's: your licensed copy, never changed)."""
    _need_library(user)
    return _store_template(conn, user.username, template_id, file_name, content)


def _store_template(conn, actor: str, template_id: int, file_name: str, content: bytes) -> dict:
    from . import mayan
    t = _one(conn, """SELECT t.*, l.name AS library, l.kind FROM proj.lib_templates t JOIN proj.template_libraries l ON l.id = t.library_id
                       WHERE t.id = :i""", i=template_id)
    if not t:
        raise EditError("No such template.", 404)
    if t["kind"] == "ea-explorer":
        raise EditError("EA Explorer's own templates ship with it: download the library, change it and upload it as your own.")
    if not content:
        raise EditError("Choose the file.")
    root = mayan.cabinet("EA Explorer library templates")
    cid = mayan.cabinet_path(t["folder"], mayan.cabinet(t["library"], root)) if t["folder"] else mayan.cabinet(t["library"], root)
    doc = mayan.upload(file_name, content, mimetypes.guess_type(file_name)[0] or "application/octet-stream", label=f"{t['library']}-{file_name}")
    mayan.add_to_cabinet(cid, doc["id"])
    conn.execute(text("""UPDATE proj.lib_templates SET mayan_document_id = :m, file_name = :f, uploaded_by = :u, uploaded_at = now()
                         WHERE id = :i"""), {"m": doc["id"], "f": file_name, "u": actor, "i": template_id})
    return {"id": template_id, "message": f"{file_name} stored for {t['name']}."}


def templates_in_folder() -> list[Path]:
    base = LIBRARY_DIR / "templates" / "togaf"
    if not base.is_dir():
        return []
    return sorted(f for f in base.rglob("*") if f.is_file() and not f.name.startswith(".") and f.name.lower() != "readme.md")


def load_templates_from_folder(conn, user) -> dict:
    """Every file in the TOGAF folder (library/templates/togaf, mounted at /data/library) whose name matches a TOGAF
    template is stored in Mayan for it (only templates that have no file yet)."""
    _need_library(user)
    return _load_folder(conn, user.username)


def togaf_files_waiting(conn) -> bool:
    """TOGAF templates without their file while the folder has files: loaded automatically on start (after a clean
    restart Documents is empty again, the folder on disk is not), so nobody loads them by hand and they never go to git."""
    files = templates_in_folder()
    if not files:
        return False
    waiting = _rows(conn, """SELECT t.id, t.name, t.folder, t.mayan_document_id FROM proj.lib_templates t
                               JOIN proj.template_libraries l ON l.id = t.library_id
                              WHERE l.kind = 'togaf' AND t.mayan_document_id IS NULL""")
    return any(_togaf_match(waiting, f.name, f.parent.name) for f in files) if waiting else False


def auto_load_togaf(conn_factory) -> str:
    """The background job's load of the TOGAF folder (one transaction; the files are small)."""
    with conn_factory() as conn:
        out = _load_folder(conn, "system")
        if out["loaded"]:
            conn.execute(text("""UPDATE proj.template_libraries SET note = :n WHERE kind = 'togaf'"""),
                         {"n": f"Loaded automatically from library/templates/togaf: {len(out['loaded'])} file(s)."})
    return out["message"]


def _load_folder(conn, actor: str) -> dict:
    files = templates_in_folder()
    if not files:
        return {"loaded": [], "message": f"No files in {LIBRARY_DIR / 'templates' / 'togaf'} (library/templates/togaf in the EA Explorer folder)."}
    temps = _rows(conn, """SELECT t.id, t.name, t.folder, t.mayan_document_id FROM proj.lib_templates t
                             JOIN proj.template_libraries l ON l.id = t.library_id WHERE l.kind = 'togaf'""")
    loaded, skipped = [], []
    for f in files:
        match = _togaf_match(temps, f.name, f.parent.name)
        todo = [t for t in match if not t["mayan_document_id"]]
        if not match:
            skipped.append(f"{f.name}: no TOGAF template of that name")
            continue
        for t in todo:
            _store_template(conn, actor, t["id"], f.name, f.read_bytes())
            loaded.append(f.name)
    return {"loaded": loaded, "skipped": skipped,
            "message": f"{len(loaded)} template file(s) stored; {len(skipped)} file(s) did not match a TOGAF template."}


# ---------------------------------------------------------------- open a template library to look through it (owner, 8 Nov 2026)
def library_templates(conn, user, library: Any) -> dict:
    """A template library's files by folder (read only): what each is, which deliverable or artifact it is for, and
    whether its file is here yet. Anyone who may use the library looks through it and downloads its files."""
    lib = _library_row(conn, library)
    if not _sees_library(conn, lib, user):
        raise EditError(f"The template library {lib['name']} is not offered to you.", 403)
    items = {r["id"]: r for r in _rows(conn, "SELECT id, name, phase, kind FROM proj.lib_items")}
    out = []
    for t in _rows(conn, "SELECT * FROM proj.lib_templates WHERE library_id = :l ORDER BY path", l=lib["id"]):
        it = items.get(t["item_id"]) if t.get("item_id") else None
        out.append({"id": t["id"], "path": t["path"], "folder": t["path"].rsplit("/", 1)[0] if "/" in t["path"] else "",
                    "name": t["file_name"] or t["name"] or t["path"].rsplit("/", 1)[-1], "has_file": _has_file(t, lib["kind"]),
                    "item": it["name"] if it else "", "item_id": t.get("item_id"), "phase": (it or {}).get("phase") or t.get("phase") or ""})
    return {"library": {"id": str(lib["guid"]), "name": lib["name"], "kind": lib["kind"], "description": lib.get("description") or ""},
            "templates": out}


def library_template_file(conn, user, template_id: int) -> tuple[bytes, str, str]:
    t = _one(conn, """SELECT t.*, l.kind, l.name AS library, l.guid FROM proj.lib_templates t
                        JOIN proj.template_libraries l ON l.id = t.library_id WHERE t.id = :t""", t=template_id)
    if not t:
        raise EditError("No such template.", 404)
    lib = _library_row(conn, str(t["guid"]))
    if not _sees_library(conn, lib, user):
        raise EditError(f"The template library {lib['name']} is not offered to you.", 403)
    if not _has_file(t, t["kind"]):
        raise EditError("This template has no file yet.", 404)
    data, ctype = _template_bytes(t, t["kind"])
    return data, ctype, f"{t['library']}-{t['file_name'] or t['name']}"
