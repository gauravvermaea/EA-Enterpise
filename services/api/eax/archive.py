"""Four states for models and projects, and the archive (R2.41, D626; owner, 12 Nov 2026: "archived or deleted models
and projects move to another physical DB so that they dont slow things down ... the work happens in background. Archive
is not freeze"; answers 21:20).

  Active     worked on
  Frozen     kept where it is, readable, no more changes (model_wizards.freeze; a project: frozen status)
  Archived   taken out of the working database whole, into the archive database (EAX_ARCHIVE_DB_URL; R2.50), as its
             backup file: the deep package with its history (a project: with its documents and the models only it uses).
             Listed and looked at from the archive; brought back to Active by its admins
  Deleted    the same, hidden from everyone but Super Admins; kept until a Super Admin purges it (no automatic removal)

Who: a model's Model Admin (a project's Project Admin) freezes, archives and brings back from the archive; only a Super
Admin deletes, restores a deleted one, or purges. Before a model moves, what refers to it is listed and the move is
refused while another model derives from it or a project uses it (archive the project, which takes its own models).
The work runs as background tasks (D273): backup file, archive row, removal from the working database, all in one go.
Bringing back makes the model again from its file (backups._restore_new: new ids, its name kept when free)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .databases import beside
from .metamodel_edit import EditError

STATES = ("active", "frozen", "archived", "deleted")


def _is_super(user) -> bool:
    return perms.SUPER_ADMIN in (user.roles or ())


def _admins(conn, model_id: int) -> list[str]:
    return [r[0] for r in conn.execute(text("SELECT username FROM core.model_users WHERE model_id = :m AND role = 'model-admin'"),
                                       {"m": model_id}).all()]


def references(conn, model: Any) -> dict:
    """What refers to a model: models derived from it or copied from it, projects that use it, open merge requests.
    blocking: those that stop it moving (children and projects)."""
    m = repo.get_model(conn, model)
    conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
    children = [r[0] for r in conn.execute(text("SELECT name FROM core.models WHERE parent_model_id = :i AND NOT is_deleted"),
                                           {"i": m["_id"]}).all()]
    copies = [r[0] for r in conn.execute(text("SELECT name FROM core.models WHERE source_model_id = :i AND NOT is_deleted"),
                                         {"i": m["_id"]}).all()]
    merges = int(conn.execute(text("""SELECT count(*) FROM core.merge_requests WHERE (child_id = :i OR parent_id = :i)
                                        AND status NOT IN ('merged', 'closed', 'withdrawn', 'rejected')"""), {"i": m["_id"]}).scalar() or 0)
    conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
    projects: list[str] = []
    try:
        from . import projects as pj
        with pj.connections() as pc:
            projects = [r[0] for r in pc.execute(text("""SELECT p.name FROM proj.project_models x JOIN proj.projects p ON p.id = x.project_id
                                                          WHERE x.model_guid = CAST(:g AS uuid)"""), {"g": str(m["id"])}).all()]
    except Exception:  # noqa: BLE001 - projects switched off: none use it
        projects = []
    blocking = [f"model {c} derives from it" for c in children] + [f"project {p} uses it" for p in projects]
    return {"model": str(m["id"]), "name": m["name"], "children": children, "copies": copies, "projects": projects,
            "open_merge_requests": merges, "blocking": blocking}


def _may_move(conn, user, m: dict, state: str) -> None:
    if state == "deleted" and not _is_super(user):
        raise EditError("Only a Super Admin deletes a model (it can then be restored or purged by a Super Admin).", 403)
    if not _is_super(user) and perms.MODEL_ADMIN not in perms.model_roles(conn, user.username, m["id"]):
        raise EditError(f"Archiving {m['name']} needs the Model Admin role on it.", 403)
    if m["kind"] != "project":
        raise EditError("Only a working model is archived or deleted (root and library models stay).", 409)


def move_model(conn, user, model: Any, state: str, note: str = "", progress=lambda _p, _n: None) -> dict:
    """Archives (or deletes) a model: its backup file into the archive database, then the model out of the working one."""
    from . import backups as bk
    from .testing.fixtures import _purge_models
    if state not in ("archived", "deleted"):
        raise EditError("Move a model to archived or deleted.")
    m = repo.get_model(conn, model)
    _may_move(conn, user, m, state)
    refs = references(conn, model)
    if refs["blocking"]:
        raise EditError(f"{m['name']} cannot move while " + "; ".join(refs["blocking"]) + ".", 409)
    progress(10, "Making its backup file (the model with its history)")
    data, info = bk.model_file(conn, model, user.username, f"{state} (R2.41)")
    admins = _admins(conn, m["_id"])
    summary = {"description": m.get("description") or "", "counts": info.get("counts"), "kind": m["kind"],
               "version": info.get("version"), "copies": refs["copies"], "frozen": bool(m.get("frozen_at"))}
    progress(50, "Putting it in the archive")
    with beside("archive", conn) as ac:
        ac.execute(text("""INSERT INTO archive.archive_store (kind, state, guid, name, summary, admins, file, file_bytes, note, moved_by,
                                                             contents)
                           VALUES ('model', :s, CAST(:g AS uuid), :n, CAST(:sum AS jsonb), :a, :f, :b, :note, :by, :c)
                           ON CONFLICT (kind, guid) DO UPDATE SET state = EXCLUDED.state, file = EXCLUDED.file,
                                 file_bytes = EXCLUDED.file_bytes, summary = EXCLUDED.summary, moved_at = now(), moved_by = EXCLUDED.moved_by,
                                 contents = EXCLUDED.contents"""),
                   {"s": state, "g": str(m["id"]), "n": m["name"], "sum": json.dumps(summary, default=str), "a": admins,
                    "f": data, "b": len(data), "note": (note or "")[:2000], "by": user.username,
                    "c": _contents_where_it_is(conn, m["_id"])})
    progress(70, "Taking it out of the working database")
    try:
        from . import views_client as vc
        vc.delete_model(str(m["id"]), user.username)
    except Exception:  # noqa: BLE001 - no drawn views, or the views service is off: they are in the file anyway
        pass
    history = _purge_models(conn, [int(m["_id"])], user.username)
    from . import audit
    audit.record(conn, actor=user.username, action=f"model.{state}", object_type="model", object_id=str(m["id"]),
                 details={"name": m["name"], "bytes": len(data), "history_versions": history, "note": note[:500]})
    return {"model": str(m["id"]), "name": m["name"], "state": state, "bytes": len(data),
            "message": f"{m['name']} is {state}: out of the working database, kept in the archive"
                       + (" until a Super Admin purges it." if state == "deleted" else "; its admins can bring it back.")}


def listing(conn, user, kind: str = "model", include_deleted: bool = False) -> list[dict]:
    """The archive: archived ones for everyone who may see them (their admins and Super Admins); deleted ones for Super
    Admins only (and only when asked)."""
    show_deleted = include_deleted and _is_super(user)
    with beside("archive", conn) as ac:
        rows = [dict(r) for r in ac.execute(text("""SELECT id, kind, state, guid::text AS guid, name, summary, admins, file_bytes,
                                                         note, moved_at, moved_by FROM archive.archive_store
                                                    WHERE kind = :k AND (state = 'archived' OR :d) ORDER BY moved_at DESC"""),
                                            {"k": kind, "d": show_deleted}).mappings()]
    if not _is_super(user):
        rows = [r for r in rows if user.username.lower() in [a.lower() for a in r["admins"] or []]
                or perms.allowed(user.roles, "models.all")]
    return rows


def contents_of(conn, model_ids: list[int], most: int = 20000) -> str:
    """What models hold, as text for Find (R2.41, D647): one line per element, "Type: Name", read before they move."""
    rows = conn.execute(text("""SELECT t.name, e.name FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                                 WHERE e.model_id = ANY(:m) AND NOT e.is_deleted ORDER BY t.name, e.name LIMIT :n"""),
                        {"m": list(model_ids), "n": most}).all()
    return "\n".join(f"{t}: {n}" for t, n in rows)


def _contents_where_it_is(conn, model_id: int) -> str:
    """contents_of, read where the model's content is (a library model's in the library schema, D633)."""
    from . import library_models as lm
    try:
        with lm.reading(conn, model_id) as rc:
            return contents_of(rc, [model_id])
    except Exception:  # noqa: BLE001 - Find then matches its name and description only
        return ""


def search(conn, user, q: str, limit: int = 50) -> list[dict]:
    """Find with Include archived (R2.41, D647): the archived models and projects this person may see (as the archive's
    list: their admins, and those who read every model; deleted ones stay out of Find, for Super Admins too) whose name,
    description or contents have the words; for each, the lines that matched. Read from the archive database."""
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    with beside("archive", conn) as ac:
        rows = [dict(r) for r in ac.execute(text("""
            SELECT id, kind, guid::text AS guid, name, summary, admins, moved_at, contents FROM archive.archive_store
             WHERE state = 'archived' AND (name ILIKE :l OR summary->>'description' ILIKE :l OR contents ILIKE :l)
             ORDER BY (name ILIKE :l) DESC, moved_at DESC LIMIT :n"""), {"l": like, "n": max(1, min(int(limit), 200))}).mappings()]
    if not _is_super(user):
        rows = [r for r in rows if user.username.lower() in [a.lower() for a in r["admins"] or []]
                or perms.allowed(user.roles, "models.all")]
    low = q.lower()
    out = []
    for r in rows:
        hits = [x for x in (r.pop("contents") or "").splitlines() if low in x.lower()][:5]
        out.append({"archive_id": r["id"], "kind": r["kind"], "guid": r["guid"], "name": r["name"], "moved_at": r["moved_at"],
                    "description": (r.get("summary") or {}).get("description") or "", "matches": hits,
                    "link": "#/archive" if r["kind"] == "model" else "#/archive?kind=project"})
    return out


def _row(conn, ident: int) -> dict:
    with beside("archive", conn) as ac:
        r = ac.execute(text("SELECT * FROM archive.archive_store WHERE id = :i"), {"i": int(ident)}).mappings().first()
    if not r:
        raise EditError(f"Nothing in the archive with id {ident}.", 404)
    return dict(r)


def bring_back(conn, user, ident: int) -> dict:
    """Makes the model again from its file (Active): archived ones by their admins or a Super Admin, deleted ones by a
    Super Admin only. The archive row goes once the model is back."""
    import io
    import zipfile

    from . import backups as bk
    r = _row(conn, ident)
    if r["kind"] != "model":
        raise EditError("That is a project: bring it back from the projects' archive.", 409)
    if r["state"] == "deleted" and not _is_super(user):
        raise EditError("Only a Super Admin restores a deleted model.", 403)
    if r["state"] == "archived" and not _is_super(user) and user.username.lower() not in [a.lower() for a in r["admins"] or []]:
        raise EditError(f"Bringing {r['name']} back needs to be one of its Model Admins (or a Super Admin).", 403)
    z = zipfile.ZipFile(io.BytesIO(bytes(r["file"])))
    info = json.loads(z.read("backup.json"))
    conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
    taken = conn.execute(text("SELECT 1 FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted"), {"n": r["name"]}).first()
    conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))

    class Admin:                                     # restored as a Super Admin would: the person may not hold Model Creator
        username, roles = user.username, list(user.roles or ()) + [perms.SUPER_ADMIN]
    message, out = bk._restore_new(conn, Admin, info, z, "" if taken else r["name"])
    out = {**out, "model": str(out["model"])}
    for a in r["admins"] or []:                      # its admins look after it again
        conn.execute(text("""INSERT INTO core.model_users (model_id, username, role)
                             SELECT id, lower(:u), 'model-admin' FROM core.models WHERE guid = CAST(:g AS uuid) ON CONFLICT DO NOTHING"""),
                     {"u": a, "g": out["model"]})
    with beside("archive", conn) as ac:
        ac.execute(text("DELETE FROM archive.archive_store WHERE id = :i"), {"i": int(ident)})
    from . import audit
    audit.record(conn, actor=user.username, action="model.unarchived", object_type="model", object_id=out["model"],
                 details={"name": r["name"], "was": r["state"], "archived_guid": str(r["guid"])})
    return {**out, "message": f"{r['name']} is back in the working database as '{out['name']}' (it was {r['state']})."}


def purge(conn, user, ident: int) -> dict:
    """Removes a deleted (or archived) one from the archive for good: Super Admins only."""
    if not _is_super(user):
        raise EditError("Only a Super Admin purges from the archive.", 403)
    r = _row(conn, ident)
    with beside("archive", conn) as ac:
        ac.execute(text("DELETE FROM archive.archive_store WHERE id = :i"), {"i": int(ident)})
    from . import audit
    audit.record(conn, actor=user.username, action="archive.purged", object_type=r["kind"], object_id=str(r["guid"]),
                 details={"name": r["name"], "state": r["state"], "bytes": r["file_bytes"]})
    return {"purged": r["name"], "message": f"{r['name']} is gone for good."}


def download(conn, user, ident: int) -> tuple[bytes, str]:
    """Its backup file, to look at it or restore it elsewhere (who may bring it back may download it)."""
    r = _row(conn, ident)
    if not _is_super(user) and (r["state"] == "deleted" or user.username.lower() not in [a.lower() for a in r["admins"] or []]):
        raise EditError("Only its admins (or a Super Admin) may download it.", 403)
    return bytes(r["file"]), f"{r['name']}.eaxbackup.zip"


def state_of(m: dict) -> str:
    """A working model's state: frozen or active (archived and deleted ones are not in the working database)."""
    return "frozen" if m.get("frozen_at") else "active"


# ---------------------------------------------------------------- projects (R2.41, second part)
def project_references(pc, project: Any) -> dict:
    """A project's models: those only it uses (made by it, used by no other project, nothing derived from them) move
    with it; the rest stay where they are and are listed."""
    from . import projects as pj
    p = pj.project_row(pc, project)
    core = pj.core(pc)
    rows = pj._rows(pc, "SELECT model_guid::text AS guid, how FROM proj.project_models WHERE project_id = :p", p=p["id"])
    moving, staying = [], []
    for r in rows:
        others = pc.execute(text("""SELECT count(*) FROM proj.project_models WHERE model_guid = CAST(:g AS uuid)
                                     AND project_id <> :p"""), {"g": r["guid"], "p": p["id"]}).scalar() or 0
        core.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        m = core.execute(text("""SELECT m.id, m.name, m.kind_code, (SELECT count(*) FROM core.models c WHERE c.parent_model_id = m.id
                                        AND NOT c.is_deleted) AS children
                                   FROM core.models m WHERE m.guid = CAST(:g AS uuid) AND NOT m.is_deleted"""), {"g": r["guid"]}).mappings().first()
        core.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
        if not m:
            continue
        own = r["how"] in ("created", "derived") and not others and not m["children"] and m["kind_code"] == "project"
        (moving if own else staying).append({"guid": r["guid"], "name": m["name"], "id": int(m["id"]), "how": r["how"],
                                             "why": "" if own else "used by another project" if others else
                                             "another model derives from it" if m["children"] else "referred to, not made by it"})
    return {"project": str(p["guid"]), "name": p["name"], "moving": moving, "staying": staying}


def move_project(pc, user, project: Any, state: str, note: str = "", progress=lambda _p, _n: None) -> dict:
    """Archives (or deletes) a project with its documents and the models only it uses; the models others use stay."""
    from . import audit
    from . import project_backup as pb
    from . import projects as pj
    from .testing.fixtures import _purge_models
    if state not in ("archived", "deleted"):
        raise EditError("Move a project to archived or deleted.")
    p = pj.project_row(pc, project)
    if state == "deleted" and not _is_super(user):
        raise EditError("Only a Super Admin deletes a project (it can then be restored or purged by a Super Admin).", 403)
    pb.need_manage(pc, p, user)
    core = pj.core(pc)
    refs = project_references(pc, project)
    progress(10, "Making its backup file (the project, its documents and its own models)")
    data, info = pb.project_file(core, pc, user, p, f"{state} (R2.41)")
    admins = [r[0] for r in pc.execute(text("SELECT username FROM proj.members WHERE project_id = :p AND role = 'project-admin'"),
                                       {"p": p["id"]}).all()]
    summary = {"description": p.get("description") or "", "counts": info.get("counts"), "models": refs["moving"],
               "models_kept": refs["staying"], "documents_missing": info.get("documents_missing")}
    progress(50, "Putting it in the archive")
    with beside("archive", core) as ac:
        ac.execute(text("""INSERT INTO archive.archive_store (kind, state, guid, name, summary, admins, file, file_bytes, note, moved_by,
                                                             contents)
                           VALUES ('project', :s, CAST(:g AS uuid), :n, CAST(:sum AS jsonb), :a, :f, :b, :note, :by, :c)
                           ON CONFLICT (kind, guid) DO UPDATE SET state = EXCLUDED.state, file = EXCLUDED.file,
                                 file_bytes = EXCLUDED.file_bytes, summary = EXCLUDED.summary, moved_at = now(), moved_by = EXCLUDED.moved_by,
                                 contents = EXCLUDED.contents"""),
                   {"s": state, "g": str(p["guid"]), "n": p["name"], "sum": json.dumps(summary, default=str), "a": admins,
                    "f": data, "b": len(data), "note": (note or "")[:2000], "by": user.username,
                    "c": "\n".join([p.get("description") or "", *[f"Model: {x}" for x in refs.get("moving") or [] if isinstance(x, str)]])})
    progress(70, "Taking it out of the working databases")
    if p.get("mayan_cabinet_id"):
        try:
            from . import mayan
            if hasattr(mayan, "delete_cabinet"):
                mayan.delete_cabinet(p["mayan_cabinet_id"])
        except Exception:  # noqa: BLE001 - Documents off: its files are in the backup file anyway
            pass
    pc.execute(text("DELETE FROM proj.projects WHERE id = :i"), {"i": p["id"]})
    if refs["moving"]:
        _purge_models(core, [m["id"] for m in refs["moving"]], user.username)
    audit.record(core, actor=user.username, action=f"project.{state}", object_type="project", object_id=str(p["guid"]),
                 details={"name": p["name"], "bytes": len(data), "models": [m["name"] for m in refs["moving"]]})
    kept = f" Kept where they are: {', '.join(m['name'] for m in refs['staying'])}." if refs["staying"] else ""
    return {"project": str(p["guid"]), "name": p["name"], "state": state, "bytes": len(data),
            "message": f"{p['name']} is {state} with {len(refs['moving'])} model(s) of its own." + kept}


def bring_back_project(pc, user, ident: int) -> dict:
    """The project made again from its file (a new project, its own models made again), its Project Admins again."""
    import tempfile
    from pathlib import Path

    from . import audit
    from . import project_backup as pb
    from . import projects as pj
    core = pj.core(pc)
    r = _row(core, ident)
    if r["kind"] != "project":
        raise EditError("That is a model: bring it back from the models' archive.", 409)
    if r["state"] == "deleted" and not _is_super(user):
        raise EditError("Only a Super Admin restores a deleted project.", 403)
    if r["state"] == "archived" and not _is_super(user) and user.username.lower() not in [a.lower() for a in r["admins"] or []]:
        raise EditError(f"Bringing {r['name']} back needs to be one of its Project Admins (or a Super Admin).", 403)

    class Admin:
        username, roles = user.username, list(user.roles or ()) + ["super-admin"]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"{r['guid']}{pb.SUFFIX}"
        path.write_bytes(bytes(r["file"]))
        message, out = pb.restore(core, pc, Admin, path, new_name=r["name"])
    new = str(out.get("project") or "")
    for a in r["admins"] or []:
        pc.execute(text("""INSERT INTO proj.members (project_id, username, role, added_by)
                           SELECT id, lower(:u), 'project-admin', :by FROM proj.projects WHERE guid::text = :g ON CONFLICT DO NOTHING"""),
                   {"u": a, "by": user.username, "g": new})
    with beside("archive", core) as ac:
        ac.execute(text("DELETE FROM archive.archive_store WHERE id = :i"), {"i": int(ident)})
    audit.record(core, actor=user.username, action="project.unarchived", object_type="project", object_id=new,
                 details={"name": r["name"], "was": r["state"], "archived_guid": str(r["guid"])})
    return {"project": new, "name": r["name"], "message": f"{r['name']} is back (it was {r['state']}). {message}"}
