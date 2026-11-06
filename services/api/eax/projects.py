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
    items = _rows(conn, """SELECT id, phase, name, kind, type, default_pick, work_folder, approved_folder, templates
                             FROM proj.lib_items WHERE NOT retired ORDER BY id""")
    src = {}
    for s in _rows(conn, "SELECT item_id, source, phase, name, files, location FROM proj.lib_item_sources ORDER BY id"):
        src.setdefault(s["item_id"], []).append({k: s[k] for k in ("source", "phase", "name", "files", "location")})
    for i in items:
        i["sources"] = src.get(i["id"], [])
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
        "viewpoints": _rows(core(conn), "SELECT code, name, category, purpose FROM core.viewpoints ORDER BY code"),
        "roles": [{"code": r, "name": ROLE_NAMES[r]} for r in ROLES],
    }


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
    if _super(user):
        return roles | {"super-admin"}
    ok = {"read": bool(roles), "contribute": bool(roles & CONTRIBUTORS), "admin": bool(roles & ADMINS),
          "undo": bool(roles & UNDO_CHECKOUT)}[what]
    if not ok:
        need = {"read": "a role on this project", "contribute": "a contributing role (not Stakeholder)",
                "admin": "Project Admin or Lead Architect", "undo": "Lead Architect, Model Admin or Project Admin"}[what]
        raise EditError(f"Not allowed on {p['name']}: needs {need}.", 403)
    return roles


def may_create(user) -> bool:
    return perms.allowed(user.roles, "projects.create")


# ---------------------------------------------------------------- list and read
def listing(conn, user) -> list[dict]:
    rows = _rows(conn, """SELECT p.guid::text AS id, p.name, p.purpose, p.description, p.cycle, p.status, p.repo_state, p.created_by,
                                 p.created_at, pp.name AS parent_name, pp.guid::text AS parent_id,
                                 (SELECT array_agg(DISTINCT m.role) FROM proj.members m
                                   WHERE m.project_id = p.id AND lower(m.username) = lower(:u)) AS my_roles,
                                 (SELECT count(*) FROM proj.members m WHERE m.project_id = p.id) AS people,
                                 (SELECT count(*) FROM proj.project_models pm WHERE pm.project_id = p.id) AS models,
                                 (SELECT count(*) FROM proj.items i WHERE i.project_id = p.id AND i.chosen) AS items,
                                 (SELECT count(*) FROM proj.documents d WHERE d.project_id = p.id) AS documents
                            FROM proj.projects p LEFT JOIN proj.projects pp ON pp.id = p.parent_id ORDER BY p.name""", u=user.username)
    if not _super(user):
        rows = [r for r in rows if r["my_roles"]]
    for r in rows:
        r["my_roles"] = sorted(r["my_roles"] or [])
    return rows


def detail(conn, project: Any, user) -> dict:
    p = project_row(conn, project)
    roles = _need(conn, p, user, "read")
    out = {k: p[k] for k in ("name", "purpose", "description", "cycle", "status", "repo_state", "repo_note", "created_by", "created_at")}
    out.update(id=str(p["guid"]), me=user.username, parent_id=p["parent_guid"], parent_name=p["parent_name"], my_roles=sorted(roles),
               may_admin=bool(roles & (ADMINS | {"super-admin"})), may_contribute=bool(roles & (CONTRIBUTORS | {"super-admin"})),
               may_undo=bool(roles & (UNDO_CHECKOUT | {"super-admin"})))
    out["members"] = _rows(conn, "SELECT username, role, added_by, added_at FROM proj.members WHERE project_id = :p ORDER BY role, username",
                           p=p["id"])
    out["signoff"] = _rows(conn, "SELECT phase, username FROM proj.signoff WHERE project_id = :p ORDER BY phase, username", p=p["id"])
    how = {r["guid"]: r["how"] for r in _rows(conn, "SELECT model_guid::text AS guid, how FROM proj.project_models WHERE project_id = :p",
                                              p=p["id"])}
    out["models"] = [{**m, "how": how[m["id"]]} for m in _rows(core(conn), """SELECT guid::text AS id, name, kind_code AS kind, copy_state
                       FROM core.models WHERE guid::text = ANY (CAST(:g AS text[])) ORDER BY name""", g=list(how))] if how else []
    names = {r["code"]: r["name"] for r in _rows(core(conn), "SELECT code, name FROM core.viewpoints")}
    out["viewpoints"] = [{"code": v["code"], "name": names.get(v["code"], v["code"])} for v in
                         _rows(conn, "SELECT viewpoint AS code FROM proj.project_viewpoints WHERE project_id = :p ORDER BY viewpoint", p=p["id"])]
    out["principles"] = _rows(conn, """SELECT pr.id, pr.code, pr.name, pr.statement, pr.rationale, pr.implications,
                                              pp.name AS inherited_from FROM proj.principles pr
                                         LEFT JOIN proj.projects pp ON pp.id = pr.inherited_from
                                        WHERE pr.project_id = :p ORDER BY pr.code, pr.name""", p=p["id"])
    out["phases"] = _rows(conn, "SELECT code, name, workspace FROM proj.lib_phases ORDER BY sort_order")
    out["steps"] = _rows(conn, """SELECT id, phase, seq, name, library_id IS NULL AS own, removed, removed_reason, done_at, done_by
                                    FROM proj.steps WHERE project_id = :p AND cycle = :c ORDER BY phase, seq""", p=p["id"], c=p["cycle"])
    out["items"] = _rows(conn, """SELECT i.guid::text AS id, i.phase, i.name, i.kind, i.type, i.library_id, i.chosen, i.folder,
                                         i.approved_folder, (SELECT count(*) FROM proj.documents d WHERE d.item_id = i.id) AS documents
                                    FROM proj.items i WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.phase, i.folder""",
                              p=p["id"], c=p["cycle"])
    out["libraries"] = _rows(conn, """SELECT l.guid::text AS id, l.name, l.kind, l.state, l.shared FROM proj.project_libraries pl
                                        JOIN proj.template_libraries l ON l.id = pl.library_id
                                       WHERE pl.project_id = :p ORDER BY pl.sort_order""", p=p["id"])
    by_item, _f, _l = _project_templates(conn, p["id"])
    out["templates"] = {k: [{"id": t["id"], "library": t["library"], "name": t["file_name"] or t["name"]} for t in v] for k, v in by_item.items()}
    out["documents"] = documents(conn, p)
    out["folders"] = [r["path"] for r in _rows(conn, "SELECT path FROM proj.folders WHERE project_id = :p ORDER BY path", p=p["id"])]
    return out


def documents(conn, p: dict) -> list[dict]:
    return _rows(conn, """SELECT d.guid::text AS id, i.guid::text AS item_id, d.folder, d.file_name, d.versions, d.origin, d.state,
                                 d.checked_out_by, d.checked_out_at, d.created_by, d.created_at, d.modified_by, d.modified_at,
                                 d.mayan_document_id IS NOT NULL AS stored
                            FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                           WHERE d.project_id = :p ORDER BY d.folder, d.file_name""", p=p["id"])


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
    from . import model_ops as mo
    from . import repository as repo
    if not may_create(user):
        raise EditError("Creating a project needs a global role (User, Model Creator or Super Admin).", 403)
    if not sample and not setup_state(conn)["done"]:    # the laptop sample project is made before the setup
        raise EditError("A Super Admin finishes the template library setup first (Administration > Project library).", 409)
    _check_payload(conn, d)
    libs = _chosen_libraries(conn, user, d.get("libraries"))
    parent = project_row(conn, d["parent"]) if d.get("parent") else None
    if parent:
        _need(conn, parent, user, "read")
    pid = _one(conn, """INSERT INTO proj.projects (name, purpose, description, parent_id, created_by)
                        VALUES (:n, :pu, :de, :pa, :u) RETURNING id, guid::text AS guid""",
               n=d["name"].strip(), pu=d["purpose"].strip(), de=(d.get("description") or "").strip(),
               pa=parent["id"] if parent else None, u=user.username)
    p = {"id": pid["id"], "guid": pid["guid"], "name": d["name"].strip()}
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
    # models: add, derive (a child) or create
    copies, made = [], []
    for m in d.get("models") or []:
        how = m.get("how")
        if how == "added":
            mm = repo.get_model(core(conn), m["model"])
        elif how in ("derived", "created"):
            spec = {"kind": "project", "name": (m.get("name") or "").strip(), "source": m["from"],
                    "copy": m.get("copy") or ("content" if how == "derived" else "metamodel"),
                    "description": f"Created for the architecture project {p['name']}."}
            if how == "derived":
                spec["parent"] = m["from"]
            if not spec["name"]:
                raise EditError("Give each new model a name.")
            res = mo.create_model(core(conn), user.username, spec)
            mm = res["model"]
            if res.get("_copy"):
                copies.append(res["_copy"])
            made.append(mm)
        else:
            raise EditError("A model is added, derived or created.")
        conn.execute(text("""INSERT INTO proj.project_models (project_id, model_guid, how, added_by) VALUES (:p, CAST(:m AS uuid), :h, :u)
                             ON CONFLICT DO NOTHING"""), {"p": p["id"], "m": str(mm["id"]), "h": how, "u": user.username})
    # the people get roles on the models the project made (D261)
    for mm in made:
        for u, r in members:
            core(conn).execute(text("""INSERT INTO core.model_users (model_id, username, role, created_by) VALUES (:m, :u, :r, :b)
                                 ON CONFLICT (model_id, username, role) DO NOTHING"""),
                         {"m": mm["_id"], "u": u, "r": MODEL_ROLE_FOR[r], "b": user.username})
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
    _items(conn, p, d)
    from . import notify
    notify.create(core(conn), kind="project.created", category="model", actor=user.username,
                  title=f"You are on the architecture project {p['name']}",
                  body=f"{user.username} set up {p['name']} ({d['purpose']}). Its repository is being built in Documents.",
                  link=f"#/projects/{p['guid']}", recipients=sorted(people))
    return {"project": {"id": p["guid"], "name": p["name"]}, "copies": copies}


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
                                                          inherited_from, created_by)
                             SELECT :p, code, name, statement, rationale, implications, library_id, :pa, :u
                               FROM proj.principles WHERE project_id = :pa"""), {"p": p["id"], "pa": parent["id"], "u": user.username})
    for pr in d.get("principles") or []:
        if pr.get("library_id"):
            conn.execute(text("""INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, library_id, created_by)
                                 SELECT :p, code, name, statement, rationale, implications, id, :u FROM proj.lib_principles WHERE id = :l"""),
                         {"p": p["id"], "l": int(pr["library_id"]), "u": user.username})
        elif (pr.get("name") or "").strip():
            conn.execute(text("""INSERT INTO proj.principles (project_id, code, name, statement, rationale, implications, created_by)
                                 VALUES (:p, :c, :n, :s, :r, :i, :u)"""),
                         {"p": p["id"], "c": pr.get("code") or "", "n": pr["name"].strip(), "s": pr.get("statement") or "",
                          "r": pr.get("rationale") or "", "i": pr.get("implications") or "", "u": user.username})


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
    for s in d.get("own_steps") or []:
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
    n = 900
    for it in d.get("own_items") or []:
        if not (it.get("name") or "").strip():
            continue
        n += 1
        ph = it.get("phase") or "X"
        kind = it.get("kind") if it.get("kind") in ("Deliverable", "Artifact") else "Deliverable"
        ws = _one(conn, "SELECT workspace FROM proj.lib_phases WHERE code = :c", c=ph)
        if not ws:
            raise EditError(f"Unknown phase {ph}.")
        folder = f"{ws['workspace']}/{kind}s/{n}_{_slug(it['name'])}"
        conn.execute(text("""INSERT INTO proj.items (project_id, phase, name, kind, type, chosen, folder)
                             VALUES (:p, :ph, :n, :k, :t, true, :f)"""),
                     {"p": p["id"], "ph": ph, "n": it["name"].strip(), "k": kind, "t": it.get("type") or "", "f": folder})


def set_people(conn, project: Any, user, members: list[dict], signoff: dict) -> dict:
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
    conn.execute(text("UPDATE proj.projects SET modified_at = now() WHERE id = :p"), {"p": p["id"]})
    return detail(conn, project, user)


def choose_item(conn, project: Any, user, item: str, chosen: bool) -> dict:
    """Bring a not_for_use item into use, or put one out of use (its folder and documents stay)."""
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    r = conn.execute(text("UPDATE proj.items SET chosen = :c WHERE project_id = :p AND guid = CAST(:i AS uuid) RETURNING id, mayan_cabinet_id"),
                     {"c": chosen, "p": p["id"], "i": item}).mappings().first()
    if not r:
        raise EditError("No such item in this project.", 404)
    return {"item": item, "chosen": chosen, "message": "Brought into use." if chosen else f"Marked {NOT_FOR_USE}."}


# ---------------------------------------------------------------- the repository in Mayan (background)
def pending_repositories(conn) -> list[int]:
    return [r["id"] for r in _rows(conn, """SELECT id FROM proj.projects WHERE repo_state IN ('pending', 'failed') AND repo_tries < 30
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


def _copy_template(conn_factory, project_id: int, t: dict, cabinet: int, item_id: int | None, folder: str) -> None:
    from . import mayan
    content, ctype = _template_bytes(t, t["kind"])
    name = f"{t['library']}-{t['file_name'] or t['name']}"
    doc = mayan.upload(name, content, ctype)
    mayan.add_to_cabinet(cabinet, doc["id"])
    with conn_factory() as conn:
        conn.execute(text("""INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin,
                                                         created_by, modified_by)
                             VALUES (:p, :i, :f, :m, :n, 'template', 'system', 'system')"""),
                     {"p": project_id, "i": item_id, "f": folder, "m": doc["id"], "n": name})


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
            conn.execute(text("UPDATE proj.projects SET repo_state = 'pending', repo_note = :n WHERE id = :i"), {"n": note, "i": project_id})
            return note
        p = _one(conn, "UPDATE proj.projects SET repo_state = 'building', repo_tries = repo_tries + 1 WHERE id = :i RETURNING *", i=project_id)
    if not p:
        return "gone"
    try:
        root = mayan.cabinet("EA Explorer projects")
        pc = mayan.cabinet(p["name"], root)
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.projects SET mayan_cabinet_id = :c WHERE id = :i"), {"c": pc, "i": project_id})
            folders = [r["path"] for r in _rows(conn, "SELECT path FROM proj.lib_folders WHERE NOT retired ORDER BY path")]
            items = _rows(conn, """SELECT i.id, i.name, i.folder, i.chosen, i.library_id, i.mayan_cabinet_id FROM proj.items i
                                    WHERE i.project_id = :p AND i.cycle = :c ORDER BY i.folder""", p=project_id, c=p["cycle"])
            by_item, in_folders, _l = _project_templates(conn, project_id)
            copied = {(r["item_id"], r["folder"], r["file_name"]) for r in
                      _rows(conn, "SELECT item_id, folder, file_name FROM proj.documents WHERE project_id = :p AND origin = 'template'",
                            p=project_id)}
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
            if (None, t["folder"], f"{t['library']}-{t['file_name'] or t['name']}") not in copied:
                _copy_template(conn_factory, project_id, t, cabinets[t["folder"]], None, t["folder"])
                made += 1
        for it in items:
            path = it["folder"] if it["chosen"] else f"{it['folder']} ({NOT_FOR_USE})"
            cid = it["mayan_cabinet_id"] or mayan.cabinet_path(path, pc)
            with conn_factory() as conn:
                conn.execute(text("UPDATE proj.items SET mayan_cabinet_id = :c WHERE id = :i"), {"c": cid, "i": it["id"]})
            if not it["chosen"]:
                continue
            for t in by_item.get(it["library_id"], []):
                if (it["id"], it["folder"], f"{t['library']}-{t['file_name'] or t['name']}") in copied:
                    continue
                _copy_template(conn_factory, project_id, t, cid, it["id"], it["folder"])
                made += 1
        note = f"Ready: {len(cabinets)} folders, {len(items)} item folders, {made} templates copied."
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.projects SET repo_state = 'ready', repo_note = :n WHERE id = :i"), {"n": note, "i": project_id})
        return note
    except Exception as exc:
        with conn_factory() as conn:
            conn.execute(text("UPDATE proj.projects SET repo_state = 'failed', repo_note = :n WHERE id = :i"),
                         {"n": f"Not built yet: {str(exc)[:400]}. It is tried again every minute.", "i": project_id})
        raise


def retry_repository(conn, project: Any, user) -> dict:
    p = project_row(conn, project)
    _need(conn, p, user, "admin")
    conn.execute(text("UPDATE proj.projects SET repo_state = 'pending', repo_tries = 0, repo_note = 'Asked again' WHERE id = :i"), {"i": p["id"]})
    return {"id": str(p["guid"]), "project_id": p["id"]}


# ---------------------------------------------------------------- documents: upload, download, check out, check in
def _doc(conn, p: dict, doc: str) -> dict:
    d = _one(conn, "SELECT * FROM proj.documents WHERE project_id = :p AND guid = CAST(:d AS uuid)", p=p["id"], d=doc)
    if not d:
        raise EditError("No such document in this project.", 404)
    return d


def _event(conn, doc_id: int, user, action: str, version: int | None = None, note: str = "") -> None:
    conn.execute(text("INSERT INTO proj.document_events (document_id, by_user, action, version, note) VALUES (:d, :u, :a, :v, :n)"),
                 {"d": doc_id, "u": user.username, "a": action, "v": version, "n": note[:500]})


def upload(conn, project: Any, user, item: str, file_name: str, content: bytes) -> dict:
    """A new document in an item's folder (stored in Mayan)."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    it = _one(conn, "SELECT * FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
    if not it:
        raise EditError("No such item in this project.", 404)
    if not file_name or not content:
        raise EditError("Choose a file to upload.")
    if not it["mayan_cabinet_id"]:
        raise EditError("The project's repository is not built yet in Documents: try again in a minute.", 409)
    ctype = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    doc = mayan.upload(file_name, content, ctype)
    mayan.add_to_cabinet(it["mayan_cabinet_id"], doc["id"])
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, mayan_document_id, file_name, origin, created_by, modified_by)
                        VALUES (:p, :i, :f, :m, :n, 'upload', :u, :u) RETURNING id, guid::text AS guid""",
               p=p["id"], i=it["id"], f=it["folder"], m=doc["id"], n=file_name, u=user.username)
    _event(conn, row["id"], user, "uploaded", 1, file_name)
    return {"id": row["guid"], "message": f"{file_name} is in {it['name']}."}


def download(conn, project: Any, user, doc: str) -> tuple[bytes, str, str]:
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    if not d["mayan_document_id"]:
        raise EditError("This document has no file yet.", 404)
    content, ctype, _n = mayan.download(d["mayan_document_id"])
    return content, ctype, d["file_name"]


def check_out(conn, project: Any, user, doc: str) -> dict:
    """Checked out to you: nobody else can check in a new version until you check in or it is undone."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    if d["checked_out_by"]:
        raise EditError(f"Checked out by {d['checked_out_by']} since {d['checked_out_at']:%Y-%m-%d %H:%M}.", 409)
    mayan.check_out(d["mayan_document_id"])
    conn.execute(text("UPDATE proj.documents SET checked_out_by = :u, checked_out_at = now() WHERE id = :i"), {"u": user.username, "i": d["id"]})
    _event(conn, d["id"], user, "checked out", d["versions"])
    return {"id": doc, "message": "Checked out to you: download it, edit it in Office, then check in the new file."}


def check_in(conn, project: Any, user, doc: str, file_name: str, content: bytes, comment: str = "") -> dict:
    """The new file becomes the next version; the check-out ends."""
    from . import mayan
    p = project_row(conn, project)
    _need(conn, p, user, "contribute")
    d = _doc(conn, p, doc)
    if (d["checked_out_by"] or "").lower() != user.username.lower():
        raise EditError("Check the document out first: only the person who checked it out checks it in." if not d["checked_out_by"]
                        else f"Checked out by {d['checked_out_by']}: only they check it in (or have it undone).", 409)
    if not content:
        raise EditError("Choose the new file.")
    mayan.check_in(d["mayan_document_id"])
    note = f"{user.username}: {comment}".strip(": ")
    mayan.new_version(d["mayan_document_id"], file_name or d["file_name"], content, note,
                      mimetypes.guess_type(file_name or d["file_name"])[0] or "application/octet-stream")
    conn.execute(text("""UPDATE proj.documents SET versions = versions + 1, checked_out_by = NULL, checked_out_at = NULL,
                                file_name = :n, modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {"n": file_name or d["file_name"], "u": user.username, "i": d["id"]})
    _event(conn, d["id"], user, "checked in", d["versions"] + 1, comment)
    return {"id": doc, "message": f"Version {d['versions'] + 1} checked in."}


def undo_check_out(conn, project: Any, user, doc: str) -> dict:
    """Ends a check-out without a new version: the person who checked out, or the Lead Architect, a Model Admin, the
    Project Admin or a Super Admin."""
    from . import mayan
    p = project_row(conn, project)
    d = _doc(conn, p, doc)
    if not d["checked_out_by"]:
        raise EditError("It is not checked out.", 409)
    if d["checked_out_by"].lower() != user.username.lower():
        _need(conn, p, user, "undo")
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


def mark_step(conn, project: Any, user, step_id: int, done: bool) -> dict:
    """A step is marked done by anyone who contributes; reopened by the Lead Architect or the Project Admin (D258)."""
    p = project_row(conn, project)
    roles = _need(conn, p, user, "contribute")
    s = _one(conn, "SELECT id, name, removed, done_at FROM proj.steps WHERE project_id = :p AND id = :s", p=p["id"], s=step_id)
    if not s:
        raise EditError("No such step in this project.", 404)
    if s["removed"]:
        raise EditError("This step was removed from the project.")
    if not done and s["done_at"] and not roles & (ADMINS | {"super-admin"}):
        raise EditError("Reopening a step needs the Lead Architect or the Project Admin.", 403)
    conn.execute(text("""UPDATE proj.steps SET done_at = CASE WHEN :d THEN now() END, done_by = CASE WHEN :d THEN :u END
                         WHERE id = :s"""), {"d": done, "u": user.username, "s": step_id})
    return {"step": step_id, "done": done, "message": f"{'Done' if done else 'Reopened'}: {s['name']}"}


def history(conn, project: Any, user, doc: str) -> list[dict]:
    p = project_row(conn, project)
    _need(conn, p, user, "read")
    d = _doc(conn, p, doc)
    return _rows(conn, "SELECT at, by_user, action, version, note FROM proj.document_events WHERE document_id = :d ORDER BY at DESC", d=d["id"])


# ---------------------------------------------------------------- template libraries (D264)
def _super_or_library(user) -> bool:
    return perms.allowed(user.roles, "projects.library")


def setup_state(conn) -> dict:
    r = _one(conn, "SELECT done_by, done_at FROM proj.template_setup WHERE id = 1")
    return {"done": bool(r), "done_by": r["done_by"] if r else None, "done_at": r["done_at"] if r else None}


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
                      body="", link="#/projects", recipients=[row["created_by"]])
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
                         body=note, link="#/projects", recipients=[lib["created_by"]], conn_factory=conn_factory)
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
                         body=note, link="#/admin/projects", recipients=[uploaded_by], conn_factory=conn_factory)
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
    from . import mayan
    _need_library(user)
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
                         WHERE id = :i"""), {"m": doc["id"], "f": file_name, "u": user.username, "i": template_id})
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
            upload_template(conn, user, t["id"], f.name, f.read_bytes())
            loaded.append(f.name)
    return {"loaded": loaded, "skipped": skipped,
            "message": f"{len(loaded)} template file(s) stored; {len(skipped)} file(s) did not match a TOGAF template."}
