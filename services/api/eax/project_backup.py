"""Back up and restore an architecture project, with its models and documents (owner, 7 Nov 2026).

A project backup is one zip file (eax-project-backup/1):
  backup.json                what it is: the project, when, by whom, what it holds
  project/<table>.json       the project's rows: the project, its people and sign-off, models, viewpoints, libraries,
                             principles, folders, document classes (items), steps and sub steps, documents and their history,
                             approval requests and decisions
  models/<guid>.eaxbackup.zip  a model backup (as Model admin makes) of each model the project works on (added, derived
                             or created); a model it only refers to is named, not copied
  documents/<guid>/<file>    the latest version of each document, from Documents (Mayan)

Restoring makes a NEW project ("<name> (restored <date>)"), never over the old one:
  * the models it works on: a model added (the organisation's own, worked on in place) is linked again when it is still
    here, otherwise made again from its backup; a model the project made (derived or created) is always made again from
    its backup, as a new model; a model referred to is linked again when it is still here
  * every row comes back with new ids, links between them kept; open approval requests are kept as they were
  * the repository is built again in Documents, and each document's latest version is put back in its folder.
    Earlier versions are counted but their files are only in the infrastructure backup (which holds all of Documents).
Both run in the background (tasks), so they show in the task drawer.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import backups as bk
from . import mayan
from . import projects as pj
from .metamodel_edit import EditError

FORMAT = "eax-project-backup/1"
SUFFIX = ".eaxproject.zip"

# the project's tables, in the order they are put back; for each: how it hangs on the project, and its links to remap
TABLES = [
    ("members", "project_id = :p", {}),
    ("signoff", "project_id = :p", {}),
    ("project_models", "project_id = :p", {}),
    ("project_viewpoints", "project_id = :p", {}),
    ("project_libraries", "project_id = :p", {}),
    ("principles", "project_id = :p", {"inherited_from": None}),
    ("folders", "project_id = :p", {"mayan_cabinet_id": None}),
    ("items", "project_id = :p", {"mayan_cabinet_id": None, "mayan_cabinet_chosen": None}),
    ("steps", "project_id = :p", {"parent_step_id": "steps"}),
    ("step_events", "step_id IN (SELECT id FROM proj.steps WHERE project_id = :p)", {"step_id": "steps"}),
    ("documents", "project_id = :p", {"item_id": "items", "mayan_document_id": None}),
    ("document_events", "document_id IN (SELECT id FROM proj.documents WHERE project_id = :p)", {"document_id": "documents"}),
    ("signoff_requests", "document_id IN (SELECT id FROM proj.documents WHERE project_id = :p)", {"document_id": "documents"}),
    ("stakeholders", "project_id = :p", {}),
    ("stakeholder_notes", "stakeholder_id IN (SELECT id FROM proj.stakeholders WHERE project_id = :p)", {"stakeholder_id": "stakeholders"}),
    ("standards", "project_id = :p", {}),
    ("base_skips", "project_id = :p", {}),
    ("gov_kinds", "project_id = :p", {}),
    ("gov_records", "project_id = :p", {"evidence_mayan_id": None}),
    ("gov_approvals", "record_id IN (SELECT id FROM proj.gov_records WHERE project_id = :p)", {"record_id": "gov_records"}),
    ("gov_decisions", """approval_id IN (SELECT a.id FROM proj.gov_approvals a JOIN proj.gov_records r ON r.id = a.record_id
                                          WHERE r.project_id = :p)""", {"approval_id": "gov_approvals"}),
    ("gov_history", "record_id IN (SELECT id FROM proj.gov_records WHERE project_id = :p)", {"record_id": "gov_records"}),
    ("charters", "project_id = :p", {}),
    ("phase_states", "project_id = :p", {}),
    ("task_statuses", "project_id = :p", {}),
    ("org_people", "project_id = :p", {"stakeholder_id": "stakeholders"}),
    ("tasks", "project_id = :p", {"step_id": "steps"}),
    ("repo_tags", "project_id = :p", {}),
    ("cf_type_areas", "project_id = :p", {}),
    ("cf_entity_areas", "project_id = :p", {}),
    ("repo_tag_docs", "tag_id IN (SELECT id FROM proj.repo_tags WHERE project_id = :p)", {"tag_id": "repo_tags", "document_id": "documents"}),
    ("signoff_decisions", """request_id IN (SELECT r.id FROM proj.signoff_requests r JOIN proj.documents d ON d.id = r.document_id
                                             WHERE d.project_id = :p)""", {"request_id": "signoff_requests"}),
]
NEW_GUID = {"projects", "items", "documents", "signoff_requests", "steps", "stakeholders", "stakeholder_notes", "tasks", "org_people", "standards", "gov_records", "gov_approvals", "repo_tags"}   # tables whose guid is made new (when they have one)


def folder() -> Path:
    return bk.app_dir() / "projects"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _cols(conn, table: str) -> list[str]:
    return [r["c"] for r in pj._rows(conn, """SELECT column_name AS c FROM information_schema.columns
                                               WHERE table_schema = 'proj' AND table_name = :t ORDER BY ordinal_position""", t=table)]


# ---------------------------------------------------------------- back up
def may_manage(pc, p: dict, user) -> bool:
    """Who backs a project up, downloads, deletes and restores its backups: its Project Admin or Lead Architect, a Super
    Admin, or IT (system.operate, owner 7 Nov 2026); a frozen or finished project too (backing up changes nothing)."""
    from . import permissions as perms
    return (perms.SUPER_ADMIN in user.roles or perms.allowed(user.roles, "system.operate")
            or bool(pj.my_roles(pc, p, user) & pj.ADMINS))


def need_manage(pc, p: dict, user) -> None:
    if not may_manage(pc, p, user):
        raise EditError(f"Not allowed on {p['name']}: backing it up needs its Project Admin or Lead Architect, IT or a Super Admin.", 403)


def may_restore_new(user) -> bool:
    from . import permissions as perms
    return pj.may_create(user) or perms.allowed(user.roles, "system.operate")


def backup(core, pc, user, project: Any, why: str = "") -> tuple[str, dict]:
    """Writes the backup file under <backups>/projects/<project guid>/; returns a message and what it holds."""
    p = pj.project_row(pc, project)
    need_manage(pc, p, user)
    data, info = project_file(core, pc, user, p, why)
    out_dir = folder() / str(p["guid"])
    out_dir.mkdir(parents=True, exist_ok=True)
    file = f"{info['created']}-{bk._slug(why, 40) or 'backup'}{SUFFIX}"
    (out_dir / file).write_bytes(data)
    (out_dir / file.replace(SUFFIX, ".json")).write_text(json.dumps(info, indent=2, ensure_ascii=False))
    n_models = len([m for m in info["models"] if not m.get("error")])
    msg = (f"{p['name']} backed up: {info['counts'].get('documents', 0)} documents, {n_models} models, "
           f"{info['counts'].get('steps', 0)} steps ({len(data) // 1024 + 1} KB).")
    if info["documents_missing"]:
        msg += f" {len(info['documents_missing'])} document files could not be read from Documents and are not in it."
    cleanup_project(out_dir)
    return msg, {"file": file, "project": str(p["guid"]), "info": info}


def cleanup_project(out_dir: Path) -> list[str]:
    """The newest of a project's own backups, as many as the application backups keep (D222)."""
    n, gone = bk.keep(), []
    for f in sorted(out_dir.glob(f"*{SUFFIX}"), reverse=True)[n:]:
        f.unlink(missing_ok=True)
        f.with_name(f.name.replace(SUFFIX, ".json")).unlink(missing_ok=True)
        gone.append(f.name)
    return gone


def project_file(core, pc, user, p: dict, why: str = "", with_models: bool = True) -> tuple[bytes, dict]:
    """One project as a backup file (bytes) and what it holds. In an application backup the models are backed up beside
    it already: with_models=False leaves them out (they are named, by guid and name, either way)."""
    rows = {"projects": [p]}
    for table, where, _m in TABLES:
        rows[table] = pj._rows(pc, f"SELECT * FROM proj.{table} WHERE {where} ORDER BY id" if "id" in _cols(pc, table)
                               else f"SELECT * FROM proj.{table} WHERE {where}", p=p["id"])
    models = rows["project_models"]
    buf = io.BytesIO()
    skipped_docs, model_files = [], []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for table, data in rows.items():
            z.writestr(f"project/{table}.json", json.dumps(data, default=str, ensure_ascii=False))
        names = {str(r["guid"]): r["name"] for r in pj._rows(core, "SELECT guid, name FROM core.models WHERE guid::text = ANY (CAST(:g AS text[]))",
                                                                g=[str(m["model_guid"]) for m in models])}
        for m in models:
            if m["how"] == "referred" or not with_models:
                model_files.append({"guid": str(m["model_guid"]), "name": names.get(str(m["model_guid"])), "how": m["how"], "in_file": False})
                continue
            try:
                data, info = bk.model_file(core, str(m["model_guid"]), user.username, f"with the project {p['name']}")
                z.writestr(f"models/{m['model_guid']}{bk.SUFFIX}", data)
                model_files.append({"guid": str(m["model_guid"]), "name": info["model"]["name"], "how": m["how"], "in_file": True})
            except Exception as exc:  # noqa: BLE001 - a model gone or unreadable: said in the result
                model_files.append({"guid": str(m["model_guid"]), "error": str(exc)[:200], "how": m["how"]})
        up = _documents_up() if rows["documents"] else True
        for d in rows["documents"]:
            if not d.get("mayan_document_id"):
                continue
            if not up:
                skipped_docs.append(f"{d['file_name']}: Documents is not answering")
                continue
            try:
                content, _ct, _name = mayan.download(d["mayan_document_id"])
                z.writestr(f"documents/{d['guid']}/{d['file_name']}", content)
            except Exception as exc:  # noqa: BLE001 - Documents down or the file gone: the row is kept, the file said missing
                skipped_docs.append(f"{d['file_name']}: {str(exc)[:120]}")
        info = {"format": FORMAT, "created": _stamp(), "by": user.username, "why": why,
                "project": {"id": str(p["guid"]), "name": p["name"]},
                "counts": {t: len(v) for t, v in rows.items()}, "models": model_files,
                "documents_missing": skipped_docs, "links": _links(pc, rows)}
        z.writestr("backup.json", json.dumps(info, indent=2, ensure_ascii=False))
        z.writestr("README.txt", "EA Explorer project backup (eax-project-backup/1): the project's rows, the models it works on "
                                 "(model backups) and the latest version of each document. Restore it on the project page "
                                 "(Admin › Back up and restore) or in Project admin; it comes back as a new project.\n")
    return buf.getvalue(), info


def _documents_up() -> bool:
    try:
        return mayan.ping()
    except Exception:  # noqa: BLE001
        return False


def _links(pc, rows: dict) -> dict:
    """The rows' links outside the project, by what stays the same between installations: other projects by guid, the
    template libraries by guid, their templates by library and path, library steps and classes by phase and name,
    principles by code."""
    def ids(col, tables):
        return sorted({r[col] for t in tables for r in rows.get(t, []) if r.get(col) is not None})

    def q(sql, xs):
        return pj._rows(pc, sql, x=list(xs)) if xs else []
    projects = (ids("parent_id", ["projects"]) + ids("merged_into", ["projects"]) + ids("inherited_from", ["principles"])
                + ids("base_id", ["projects"]))
    tpl = sorted({t for r in rows.get("items", []) for t in (r.get("templates") or [])})
    return {
        "projects": {str(r["id"]): str(r["guid"]) for r in q("SELECT id, guid FROM proj.projects WHERE id = ANY (CAST(:x AS bigint[]))", projects)},
        "libraries": {str(r["id"]): str(r["guid"]) for r in q("SELECT id, guid FROM proj.template_libraries WHERE id = ANY (CAST(:x AS bigint[]))",
                                                                ids("library_id", ["project_libraries"]))},
        "templates": {str(r["id"]): [str(r["lib"]), r["path"]] for r in q(
            """SELECT t.id, l.guid AS lib, t.path FROM proj.lib_templates t JOIN proj.template_libraries l ON l.id = t.library_id
                WHERE t.id = ANY (CAST(:x AS bigint[]))""", tpl)},
        "steps": {str(r["id"]): r["name"] for r in q("SELECT id, phase || '|' || name AS name FROM proj.lib_steps WHERE id = ANY (CAST(:x AS bigint[]))",
                                                     ids("library_id", ["steps"]))},
        "items": {str(r["id"]): r["name"] for r in q("SELECT id, phase || '|' || name AS name FROM proj.lib_items WHERE id = ANY (CAST(:x AS text[]))",
                                                     [str(x) for x in ids("library_id", ["items"])])},
        "principles": {str(r["id"]): r["code"] for r in q("SELECT id, code FROM proj.lib_principles WHERE id = ANY (CAST(:x AS bigint[]))",
                                                          ids("library_id", ["principles"]))},
    }

def list_backups(pc, user, project: Any) -> dict:
    p = pj.project_row(pc, project)
    pj._need(pc, p, user, "read")
    d = folder() / str(p["guid"])
    out = []
    for f in sorted(d.glob(f"*{SUFFIX}"), reverse=True) if d.exists() else []:
        try:
            info = json.loads(f.with_name(f.name.replace(SUFFIX, ".json")).read_text())
        except (OSError, ValueError):
            info = {}
        out.append({"file": f.name, "size": f.stat().st_size, "created": info.get("created"), "by": info.get("by"),
                    "why": info.get("why"), "counts": info.get("counts") or {}, "models": info.get("models") or [],
                    "documents_missing": info.get("documents_missing") or []})
    return {"backups": out, "may_manage": may_manage(pc, p, user), "may_restore": may_restore_new(user)}


def list_all(pc) -> list[dict]:
    """Every project, with its backups (Administration › Backups, for IT and Super Admins)."""
    out = []
    for p in pj._rows(pc, "SELECT guid, name, status FROM proj.projects ORDER BY lower(name)"):
        d = folder() / str(p["guid"])
        files = []
        for f in sorted(d.glob(f"*{SUFFIX}"), reverse=True) if d.exists() else []:
            try:
                info = json.loads(f.with_name(f.name.replace(SUFFIX, ".json")).read_text())
            except (OSError, ValueError):
                info = {}
            files.append({"file": f.name, "size": f.stat().st_size, "created": info.get("created"), "by": info.get("by"),
                          "why": info.get("why"), "counts": info.get("counts") or {},
                          "models": len([m for m in info.get("models") or [] if not m.get("error")]),
                          "documents_missing": len(info.get("documents_missing") or [])})
        out.append({"id": str(p["guid"]), "name": p["name"], "status": p["status"], "backups": files})
    return out


def path_of(project_guid: str, file: str) -> Path:
    if "/" in file or "\\" in file or not file.endswith(SUFFIX):
        raise EditError("No such backup.", 404)
    f = folder() / project_guid / file
    if not f.exists():
        raise EditError("No such backup.", 404)
    return f


def delete_backup(pc, user, project: Any, file: str) -> dict:
    p = pj.project_row(pc, project)
    need_manage(pc, p, user)
    f = path_of(str(p["guid"]), file)
    f.unlink()
    f.with_name(file.replace(SUFFIX, ".json")).unlink(missing_ok=True)
    return {"message": f"Backup {file} deleted."}


# ---------------------------------------------------------------- restore (as a new project)
def _read(path: Path) -> tuple[dict, zipfile.ZipFile]:
    try:
        z = zipfile.ZipFile(path)
        info = json.loads(z.read("backup.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise EditError(f"{path.name} is not an EA Explorer project backup.", 400) from exc
    if info.get("format") != FORMAT:
        raise EditError(f"{path.name} is not an EA Explorer project backup.", 400)
    return info, z


def restore(core, pc, user, path: Path, new_name: str = "", over: bool = False, models_over: bool = False,
            model_guids: dict | None = None, uploaded: bool = False) -> tuple[str, dict]:
    """The project from the backup file: rows, models and documents (see the module's notes).

    Restored as a NEW project (the default): new ids and guids, the models it made made again as new models, the person
    restoring made its Project Admin. over=True (the application restore, or a Super Admin): the project goes back over
    itself, keeping its id (so its links with other projects stay) when it is still here, or made again with its own guid;
    its documents keep their place in Documents (the same document, found by its guid in this project) and get the
    backed-up file as a new version when it differs; documents added since go to Documents' trash. models_over=True: the
    models the project made (derived or created) are put back over themselves too. model_guids: the application restore's
    old model guid -> the model made again. uploaded: a file from elsewhere (models are linked only where the person may
    see them)."""
    from . import permissions as perms
    if not over and not may_restore_new(user):
        raise EditError("Restoring a project makes a new one: it needs the right to create projects (or IT).", 403)
    info, z = _read(path)
    links = info.get("links") or {}
    with z:
        names = set(z.namelist())
        load = lambda t: json.loads(z.read(f"project/{t}.json")) if f"project/{t}.json" in names else []  # noqa: E731
        old = load("projects")[0]
        notes: list[str] = []
        live = None
        current: dict[str, int] = {}              # over: this project's documents now, guid -> their document in Documents
        if over:
            live = pj._one(pc, "SELECT * FROM proj.projects WHERE guid = CAST(:g AS uuid)", g=str(old["guid"]))
            name = old["name"]
            taken = pc.execute(text("SELECT 1 FROM proj.projects WHERE lower(name) = lower(:n) AND guid <> CAST(:g AS uuid)"),
                               {"n": name, "g": str(old["guid"])}).first()
            if taken:
                name = f"{name} (restored)"
                notes.append(f"another project is called {old['name']} now: this one is {name}")
            if live:
                current = {str(r["guid"]): r["mayan_document_id"] for r in pj._rows(
                    pc, "SELECT guid, mayan_document_id FROM proj.documents WHERE project_id = :p AND mayan_document_id IS NOT NULL",
                    p=live["id"])}
        else:
            when = (info.get("created") or "")[:8]
            name = (new_name or "").strip() or f"{old['name']} (restored {when[:4]}-{when[4:6]}-{when[6:8]})"
            base, n = name, 1
            while pc.execute(text("SELECT 1 FROM proj.projects WHERE lower(name) = lower(:n)"), {"n": name}).first():
                n += 1
                name = f"{base} {n}"
        # 1. the models
        model_map: dict[str, str] = {}
        exists = lambda g: bool(core.execute(text("SELECT 1 FROM core.models WHERE guid = CAST(:g AS uuid) AND NOT is_deleted"),  # noqa: E731
                                             {"g": g}).first())
        sees = lambda g: perms.sees_every_model(user.roles) or bool(perms.model_roles(core, user.username, g))  # noqa: E731
        for m in load("project_models"):
            g = str(m["model_guid"])
            in_zip = f"models/{g}{bk.SUFFIX}"
            if model_guids and g in model_guids:      # made again by the application restore
                model_map[g] = model_guids[g]
                continue
            if models_over and m["how"] in ("derived", "created") and exists(g) and in_zip in names:
                mz = zipfile.ZipFile(io.BytesIO(z.read(in_zip)))
                minfo = json.loads(mz.read("backup.json"))
                if minfo["model"].get("kind") == "project" and "restore/side.json" in mz.namelist():
                    mine = bk.lock_for_restore(g, user, f"project-{old['guid']}")
                    try:
                        bk._restore_over(core, user, minfo, mz, g)
                    finally:
                        if mine:
                            bk.unlock_after_restore(core, g, user)
                    notes.append(f"its model {minfo['model']['name']} put back as it was")
                model_map[g] = g
                continue
            if (over or m["how"] in ("referred", "added")) and exists(g):
                if uploaded and not sees(g):
                    notes.append(f"a model it uses ({g[:8]}…) is one you cannot see: left out")
                    continue
                model_map[g] = g
                continue
            if in_zip not in names:
                notes.append(f"a model it {'refers to' if m['how'] == 'referred' else 'used'} ({g[:8]}…) is not here and not in the backup: left out")
                continue
            if not (perms.SUPER_ADMIN in user.roles or perms.allowed(user.roles, "models.create")):
                raise EditError("Restoring the project's models needs the Model Creator role (or Super Admin).", 403)
            mz = zipfile.ZipFile(io.BytesIO(z.read(in_zip)))
            minfo = json.loads(mz.read("backup.json"))
            _msg, out = bk._restore_new(core, user, minfo, mz, f"{minfo['model']['name']} ({name})")
            model_map[g] = out["model"]
        # 2. the project row: over itself in place (its id kept), or a new one
        cols = {t: _cols(pc, t) for t in ["projects"] + [t for t, _w, _m in TABLES]}
        project_of = _local_projects(pc, links.get("projects") or {})
        skip = {"id", "mayan_cabinet_id", "created_at", "modified_at", "repo_started_at", "repo_again"}
        vals = {c: old[c] for c in cols["projects"] if c in old and c not in skip and (over or c != "guid")}
        vals.update(name=name, repo_state="pending", repo_tries=0, repo_note="Restored: being built again",
                    modified_by=user.username, parent_id=project_of.get(str(old.get("parent_id"))),
                    merged_into=project_of.get(str(old.get("merged_into"))),
                    home_model=model_map.get(str(old.get("home_model"))) if old.get("home_model") else None,
                    base_kind="")
        if "base_id" in cols["projects"]:       # its base, matched here by guid; else the Organisation base (phase 13.1)
            from . import project_bases as pbm
            org = pj._one(pc, "SELECT id FROM proj.projects WHERE guid = CAST(:g AS uuid)", g=pbm.ORG_GUID)
            vals["base_id"] = project_of.get(str(old.get("base_id"))) or (org["id"] if org else None)
        if not over:
            vals.update(created_by=user.username, parent_id=None, merged_into=None, status="active"
                        if old.get("status") in ("finishing", "frozen", "merged", "closed") else old.get("status"))
        if live:
            _delete_rows(pc, live["id"])
            _update(pc, "projects", live["id"], vals, cols["projects"])
            new_p = live["id"]
        else:
            new_p = _insert(pc, "projects", vals, cols["projects"])
        guid = str(pc.execute(text("SELECT guid FROM proj.projects WHERE id = :i"), {"i": new_p}).scalar())
        # 3. its rows, links kept
        lib_of = _local_libraries(pc, links)
        has_file = {d["guid"] for d in load("documents") if any(nm.startswith(f"documents/{d['guid']}/") for nm in names)}
        by_mayan = {d["mayan_document_id"]: str(d["guid"]) for d in load("documents") if d.get("mayan_document_id")}
        ids: dict[str, dict] = {"projects": {old["id"]: new_p}}
        dropped = 0
        evidence: dict[str, str] = {}
        for table, _w, remap in TABLES:
            ids[table] = {}
            rows = load(table)
            if table == "steps":            # a step before its sub steps
                rows = sorted(rows, key=lambda r: (r.get("parent_step_id") is not None, r.get("id") or 0))
            for r in rows:
                if table == "project_models":
                    g = model_map.get(str(r["model_guid"]))
                    if not g:
                        continue
                    r = {**r, "model_guid": g}
                if table == "documents":
                    kept = current.get(str(r["guid"])) if over else None
                    if str(r["guid"]) not in has_file and not kept and not (r.get("link_url") or r.get("link_project")):
                        dropped += 1        # no file anywhere: left out (a template comes again with the repository)
                        continue
                    r = {**r, "mayan_document_id": kept}
                vals = {c: r[c] for c in cols[table] if c in r and c != "id" and not (c == "guid" and table in NEW_GUID and not over)}
                if "project_id" in cols[table]:
                    vals["project_id"] = new_p
                lost = False
                for col, target in remap.items():
                    if col not in vals or col == "mayan_document_id":
                        continue
                    if target is None:
                        vals[col] = None
                    elif vals[col] is not None:
                        vals[col] = ids[target].get(vals[col])
                        lost = lost or vals[col] is None
                if lost and table not in ("steps", "tasks", "org_people"):   # what it hangs on is not back (a document left out): it goes too
                    continue
                if table == "principles":
                    vals["inherited_from"] = project_of.get(str(r.get("inherited_from")))
                if table == "stakeholders" and r.get("items"):      # the document classes that answer its concerns
                    vals["items"] = [ids["items"][x] for x in r["items"] if x in ids["items"]]
                lost = _library_links(table, vals, r, lib_of)
                if lost:
                    continue
                if table == "signoff_decisions" and r.get("evidence_mayan_id"):
                    ev = by_mayan.get(r["evidence_mayan_id"])
                    vals["evidence_mayan_id"] = current.get(ev) if ev else None
                new_id = _insert(pc, table, vals, cols[table])
                if "id" in r:
                    ids[table][r["id"]] = new_id
                if table == "signoff_decisions" and r.get("evidence_mayan_id") and by_mayan.get(r["evidence_mayan_id"]):
                    evidence[str(new_id)] = by_mayan[r["evidence_mayan_id"]]      # its evidence document (by guid in the backup)
        if not over and not any((m.get("username") or "").lower() == user.username.lower() and m.get("role") == "project-admin"
                                for m in load("members")):
            pc.execute(text("""INSERT INTO proj.members (project_id, username, role, added_by) VALUES (:p, :u, 'project-admin', :u)
                                ON CONFLICT DO NOTHING"""), {"p": new_p, "u": user.username})
        if dropped:
            notes.append(f"{dropped} documents had no file in the backup and are left out")
        # 4. what Documents needs once the repository is built again (after this commits): the files, the documents
        # added since (over), the evidence links
        doc_guid = None                       # over: the documents keep their guids
        if not over:
            doc_guid = {str(r["guid"]): str(pc.execute(text("SELECT guid FROM proj.documents WHERE id = :i"), {"i": nid}).scalar())
                        for r in load("documents") for nid in [ids["documents"].get(r["id"])] if nid}
            evidence = {k: doc_guid.get(v, v) for k, v in evidence.items()}
        stash = folder() / "_restoring"
        stash.mkdir(parents=True, exist_ok=True)
        files = {}
        for d in load("documents"):
            new_g = doc_guid.get(str(d["guid"])) if doc_guid is not None else str(d["guid"])
            if not new_g or ids["documents"].get(d["id"]) is None:
                continue
            for nm in names:
                if nm.startswith(f"documents/{d['guid']}/"):
                    f = stash / f"{guid}-{new_g}-{Path(nm).name}"
                    f.write_bytes(z.read(nm))
                    files[new_g] = str(f)
                    break
        backed = {str(d["guid"]) for d in load("documents")}
        trash = [mid for g, mid in current.items() if g not in backed]
        _write_pending(guid, files, trash, evidence)
    if over:
        msg = (f"{name} put back as it was ({'over itself' if live else 'made again'}): {len(ids['documents'])} documents, "
               f"{len(ids['steps'])} steps{f'; {len(trash)} documents added since go to the trash in Documents' if trash else ''}."
               f"{(' ' + '; '.join(notes) + '.') if notes else ''}")
        return msg, {"project": guid, "project_id": new_p, "files": files}
    # the goals and outcomes are entities tagged with the project: tagged with the new one (a model made again here is the
    # project's own, its old tag is replaced; a model linked again keeps the old project's tag too)
    old_tag, new_tag = f"project:{old['guid']}", f"project:{guid}"
    for g_old, g_new in model_map.items():
        core.execute(text(f"""UPDATE core.entities SET tags = {"array_replace(tags, :o, :n)" if g_old != g_new else "array_append(tags, :n)"}
                              WHERE model_id = (SELECT id FROM core.models WHERE guid = CAST(:m AS uuid)) AND :o = ANY (tags)
                                AND NOT (:n = ANY (tags))"""), {"o": old_tag, "n": new_tag, "m": g_new})
    # a model the project derived comes back as a separate copy: its link to the parent cannot be made again
    for g_old, g_new in model_map.items():
        if g_old != g_new:
            pc.execute(text("""UPDATE proj.project_models SET how = 'created' WHERE project_id = :p AND model_guid = CAST(:g AS uuid)
                                 AND how = 'derived'"""), {"p": new_p, "g": g_new})
    msg = (f"Restored {old['name']} as the new project '{name}': {len(ids['documents'])} documents, "
           f"{len(model_map)} models, {len(ids['steps'])} steps. Its repository is being built again.")
    if notes:
        msg += " " + "; ".join(notes) + "."
    return msg, {"project": guid, "project_id": new_p, "files": files}


def _local_projects(pc, by_id: dict) -> dict[str, int]:
    """The backup's other projects (by their id there) -> the same project here (by guid), when it is here."""
    if not by_id:
        return {}
    here = {str(r["guid"]): r["id"] for r in pj._rows(pc, "SELECT id, guid FROM proj.projects WHERE guid::text = ANY (CAST(:g AS text[]))",
                                                       g=list(by_id.values()))}
    return {k: here[g] for k, g in by_id.items() if g in here}


def _local_libraries(pc, links: dict) -> dict:
    """The backup's library links -> the same thing here: template libraries by guid, templates by library and path, library
    steps and classes by phase and name, principles by code. A backup made before links were kept: ids as they are."""
    if not links:
        return {}
    libs = {str(r["guid"]): r["id"] for r in pj._rows(pc, "SELECT id, guid FROM proj.template_libraries")}
    out = {"libraries": {k: libs.get(g) for k, g in (links.get("libraries") or {}).items()}}
    tp = {(str(r["lib"]), r["path"]): r["id"] for r in pj._rows(
        pc, "SELECT t.id, l.guid AS lib, t.path FROM proj.lib_templates t JOIN proj.template_libraries l ON l.id = t.library_id")}
    out["templates"] = {k: tp.get((v[0], v[1])) for k, v in (links.get("templates") or {}).items()}
    st = {r["name"]: r["id"] for r in pj._rows(pc, "SELECT id, phase || '|' || name AS name FROM proj.lib_steps")}
    out["steps"] = {k: st.get(v) for k, v in (links.get("steps") or {}).items()}
    it = {r["name"]: r["id"] for r in pj._rows(pc, "SELECT id, phase || '|' || name AS name FROM proj.lib_items")}
    out["items"] = {k: it.get(v) for k, v in (links.get("items") or {}).items()}
    pr = {r["code"]: r["id"] for r in pj._rows(pc, "SELECT id, code FROM proj.lib_principles")}
    out["principles"] = {k: pr.get(v) for k, v in (links.get("principles") or {}).items()}
    return out


def _library_links(table: str, vals: dict, r: dict, lib_of: dict) -> bool:
    """The row's links to the libraries, as they are here; True when the row cannot come back without one."""
    if not lib_of:
        return False
    if table == "project_libraries":
        vals["library_id"] = lib_of["libraries"].get(str(r.get("library_id")))
        return vals["library_id"] is None
    kind = {"steps": "steps", "items": "items", "principles": "principles"}.get(table)
    if kind and r.get("library_id") is not None:
        vals["library_id"] = lib_of[kind].get(str(r["library_id"]))       # gone here: kept as the project's own
    if table == "items" and r.get("templates") is not None:
        vals["templates"] = [t for t in (lib_of["templates"].get(str(x)) for x in r["templates"]) if t is not None]
    return False


def _update(conn, table: str, row_id: int, vals: dict, cols: list[str]) -> None:
    """A row put back in place, each value cast to its column's type (as _insert)."""
    out, ph = _typed(conn, table, vals, cols)
    sets = ", ".join(f"{c} = {ph[c]}" for c in out)
    conn.execute(text(f"UPDATE proj.{table} SET {sets} WHERE id = :_id"), {**out, "_id": row_id})


def _delete_rows(pc, project_id: int) -> None:
    """A project's own rows in every table, the dependent ones first; the project's row stays (its id, and so its links
    with other projects, kept)."""
    for table, where, _m in reversed(TABLES):
        pc.execute(text(f"DELETE FROM proj.{table} WHERE {where}"), {"p": project_id})


def _insert(conn, table: str, vals: dict, cols: list[str]) -> int | None:
    """One row back, each value cast to its column's type (columns the backup does not have get their defaults)."""
    out, ph = _typed(conn, table, vals, cols)
    has_id = "id" in cols
    sql = (f"INSERT INTO proj.{table} ({', '.join(out)}) VALUES ({', '.join(ph[c] for c in out)})"
           + (" RETURNING id" if has_id else ""))
    r = conn.execute(text(sql), out)
    return r.scalar() if has_id else None


def _pgtype(udt: str | None) -> str:
    return {"_text": "text[]", "int4": "integer", "int8": "bigint", "int2": "smallint", "bool": "boolean", "timestamptz": "timestamptz",
            "timestamp": "timestamp", "uuid": "uuid", "jsonb": "jsonb", "json": "json", "date": "date", "numeric": "numeric",
            "_int8": "bigint[]", "_int4": "integer[]", "_uuid": "uuid[]"}.get(udt or "", "text")


def _typed(conn, table: str, vals: dict, cols: list[str]) -> tuple[dict, dict]:
    """The values cast to their columns' types: jsonb as JSON text, arrays as lists, the rest as text; and the placeholders."""
    types = {r["c"]: r["t"] for r in pj._rows(conn, """SELECT column_name AS c, udt_name AS t FROM information_schema.columns
                                                         WHERE table_schema = 'proj' AND table_name = :t""", t=table)}
    out = {}
    for k, v in vals.items():
        if k not in cols:
            continue
        t = types.get(k, "")
        if t in ("jsonb", "json"):
            v = None if v is None else (v if isinstance(v, str) else json.dumps(v))
        elif t.startswith("_") and isinstance(v, str):          # an array read back as text
            try:
                v = json.loads(v)
            except ValueError:
                v = [x for x in v.strip("{}").split(",") if x]
        out[k] = v
    return out, {c: f"CAST(:{c} AS {_pgtype(types.get(c))})" for c in out}


def _write_pending(project_guid: str, files: dict, trash: list, evidence: dict) -> None:
    """What the next build of the project's repository does in Documents once this restore has committed."""
    if not (files or trash or evidence):
        return
    stash = folder() / "_restoring"
    stash.mkdir(parents=True, exist_ok=True)
    (stash / f"{project_guid}.json").write_text(json.dumps({"files": files, "trash": trash, "evidence": evidence}))


def refill_pending(conn_factory, project_id: int) -> str:
    """After the project's repository is built: the documents a restore left to put back (the ones that fail wait for the
    next build), the documents added since a restore over it to the trash, the sign-off evidence linked again."""
    with conn_factory() as conn:
        g = conn.execute(text("SELECT guid::text FROM proj.projects WHERE id = :i"), {"i": project_id}).scalar()
    pend = folder() / "_restoring" / f"{g}.json"
    if not g or not pend.exists():
        return ""
    todo = json.loads(pend.read_text())
    if "files" not in todo:                    # the first form of this file: document id -> file
        todo = {"files": {}, "trash": [], "evidence": {}}
    msg = refill_documents(conn_factory, project_id, todo["files"]) if todo["files"] else ""
    left_copies = {}
    if todo.get("copies"):                     # reference files copied from another project (D296)
        from . import references as rf
        m2, left_copies = rf.copy_files(conn_factory, project_id, todo["copies"])
        msg = f"{msg} {m2}".strip()
    gone = 0
    for mid in todo.get("trash") or []:
        try:
            mayan.trash(mid)
            gone += 1
        except Exception:  # noqa: BLE001 - gone already
            pass
    if gone:
        msg += f" {gone} documents added since the backup moved to the trash in Documents."
    for dec, doc in (todo.get("evidence") or {}).items():
        with conn_factory() as conn:
            conn.execute(text("""UPDATE proj.signoff_decisions SET evidence_mayan_id = (SELECT mayan_document_id FROM proj.documents
                                   WHERE project_id = :p AND guid = CAST(:g AS uuid)) WHERE id = :d"""),
                         {"p": project_id, "g": doc, "d": int(dec)})
    left = {k: v for k, v in todo["files"].items() if Path(v).exists()}
    if left or left_copies:
        pend.write_text(json.dumps({"files": left, "trash": [], "evidence": todo.get("evidence") or {}, "copies": left_copies}))
    else:
        pend.unlink(missing_ok=True)
    return msg.strip()


def refill_documents(conn_factory, project_id: int, files: dict) -> str:
    """Each document's backed-up file into Documents: a document still there (and still this project's: found by its guid)
    gets it as its newest version when it differs; one that is gone is uploaded again into its folder."""
    put, failed, kept = 0, [], 0
    for doc_guid, f in files.items():
        with conn_factory() as conn:
            d = pj._one(conn, """SELECT d.id, d.file_name, d.folder, d.mayan_document_id, i.mayan_cabinet_id AS item_cab, fo.mayan_cabinet_id AS folder_cab
                                   FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                                   LEFT JOIN proj.folders fo ON fo.project_id = d.project_id AND fo.path = d.folder
                                  WHERE d.project_id = :p AND d.guid = CAST(:g AS uuid)""", p=project_id, g=doc_guid)
        if not d:
            Path(f).unlink(missing_ok=True)
            continue
        try:
            still, same = None, False
            content = Path(f).read_bytes()
            if d.get("mayan_document_id"):
                try:
                    now = mayan.latest(d["mayan_document_id"])
                    still = d["mayan_document_id"]
                    same = bool(now.get("checksum")) and now["checksum"] == hashlib.sha256(content).hexdigest()
                except mayan.MayanError as exc:
                    if getattr(exc, "http", None) != 404:
                        raise                      # Documents not answering: tried again on the next build
            if still and same:  # Documents has it as it was: nothing to do
                kept += 1
            elif still:        # the same document: the backed-up file becomes its newest version (its history kept there)
                mayan.new_version(still, d["file_name"], content, "put back from a backup")
                put += 1
            else:
                up = mayan.upload(d["file_name"], content)
                cab = d["item_cab"] or d["folder_cab"]
                if cab:
                    mayan.add_to_cabinet(cab, up["id"])
                with conn_factory() as conn:
                    conn.execute(text("UPDATE proj.documents SET mayan_document_id = :m WHERE id = :i"), {"m": up["id"], "i": d["id"]})
                put += 1
            Path(f).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{d['file_name']}: {str(exc)[:100]}")
    return (f"{put} documents put back in Documents" + (f", {kept} were there as they were" if kept else "")
            + (f"; {len(failed)} not yet ({failed[0]}): tried again on the next build" if failed else "") + ".")


def cleanup_stash(days: int = 30) -> list[str]:
    """Files of restores and uploads older than a month that nothing waits for any more."""
    import time
    gone, cut = [], time.time() - days * 86400
    waiting = set()
    for p in (folder() / "_restoring").glob("*.json") if (folder() / "_restoring").is_dir() else []:
        try:
            waiting |= set((json.loads(p.read_text()).get("files") or {}).values())
        except (OSError, ValueError):
            pass
    for sub in ("_restoring", "_uploads"):
        d = folder() / sub
        for f in d.iterdir() if d.is_dir() else []:
            if f.is_file() and f.stat().st_mtime < cut and str(f) not in waiting and not (sub == "_restoring" and f.suffix == ".json"):
                f.unlink(missing_ok=True)
                gone.append(f"{sub}/{f.name}")
    return gone
