"""Published import formats and deliveries (build phase 34 and 34.1, D370, D378, D385, D462 to D467).

EA Explorer publishes its formats (docs/import-formats.md) and other systems write to them; it is not an ETL tool. A
**source** is one such system delivering to one model. A **delivery** is a load (eax/loads.py) that came from a source:

    list_sources(conn, user, model)               the model's sources, with deliveries waiting for review
    save_source(conn, user, model, data, source)  add or change a source (Model Admins)
    deliver(conn, user, source, name, content)    a file sent to the API (a service account) or uploaded in the screens
    collect(conn, user, source)                   take what was dropped in the source's folder: one delivery per file,
                                                  or one for a CSV set with its master file (D378)
    accept(conn, user, load)                      a person with the right accepts it as their committed load
    decline(conn, user, load, note)               or declines it

Formats: the **Excel format** (the import and export sheets of phase 10.1, .xlsx or .xlsm), the **CSV format** (the Excel
format as separate files, one CSV per sheet, plus master.csv saying which file holds what, D378), and the **ArchiMate 4
exchange format** only once it is published (D385: refused with that reason until then).

Folders: <import folder>/deliveries/<model guid>/<source folder>/incoming, done/<when>/ and failed/<when>/. The import
folder is the API's (/data/imports, the eax-imports volume, or EAX_IMPORT_DIR, which IT may map or mount to SFTP or a
share). Files are taken only when someone calls for them (the API, the screens or `eax import`), never by watching.

A delivery is matched by **type and name**, previewed (new, changed, kept, problems), and waits until a person who may
commit accepts it: the rows become their changes and are committed at once, as their load (undo as for any load). A
delivery only adds and changes (D370). Unless its source's values win, values already in EA Explorer stay (D464).
"""

from __future__ import annotations

import datetime as dt
import io
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import commits as cm
from . import loads as ld
from . import permissions as perms
from . import repository as repo
from . import sheets as sh
from .metamodel_edit import EditError

FORMATS = {".xlsx", ".xlsm", ".zip", ".csv"}
MAX_BYTES = 50 * 1024 * 1024


def root() -> Path:
    return Path(os.environ.get("EAX_DELIVERIES_DIR") or "/data/imports/deliveries")


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60]
    return s if s and s[0].isalnum() else ("source-" + s)[:60].strip("-") or "source"


def folder_of(model_guid: str, folder: str) -> Path:
    return root() / str(model_guid) / folder


def _make_folders(model_guid: str, folder: str) -> Path | None:
    base = folder_of(model_guid, folder)
    try:
        for sub in ("incoming", "done", "failed"):
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base
    except OSError:
        return None              # no import folder here (tests, a laptop without the volume): made when first needed


# ---------------------------------------------------------------- rights
def _is_admin(conn, user, m: dict) -> bool:
    return perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])


def may_accept(conn, user, m: dict) -> bool:
    """Accepting a delivery commits it: the Committer, Model Sub Admin or Model Admin role (D465)."""
    if perms.SUPER_ADMIN in user.roles:
        return True
    if cm.uses_commits(m):
        return cm.may_commit(conn, user, m)
    return _is_admin(conn, user, m)


def _may_send(conn, user, src: dict, m: dict) -> None:
    """The source's own service account, or anyone who may load content into the model (D462)."""
    if src.get("sender") and user.username.lower() == src["sender"]:
        return
    ld._may_load(conn, user, m)


# ---------------------------------------------------------------- sources
def _source(conn, source: Any) -> dict:
    g = repo._as_guid(source)
    s = _one(conn, """SELECT s.*, m.guid AS model_guid, m.name AS model_name FROM core.import_sources s
                       JOIN core.models m ON m.id = s.model_id WHERE s.guid = CAST(:g AS uuid)""", g=str(g)) if g else None
    if not s:
        raise EditError("No such import source.", 404)
    return s


def _source_out(conn, s: dict) -> dict:
    counts = _one(conn, """SELECT count(*) FILTER (WHERE status IN ('uploaded', 'mapping', 'previewed')) AS waiting,
                                  count(*) FILTER (WHERE status = 'added') AS accepted,
                                  count(*) FILTER (WHERE status = 'declined') AS declined,
                                  count(*) FILTER (WHERE status = 'undone') AS undone, count(*) AS total
                             FROM core.loads WHERE source_id = :i""", i=s["id"])
    base = folder_of(str(s["model_guid"]), s["folder"])
    try:
        incoming = sorted(p.name for p in (base / "incoming").iterdir() if p.is_file())
    except OSError:
        incoming = []
    return {"id": str(s["guid"]), "name": s["name"], "description": s["description"], "folder": s["folder"],
            "path": f"deliveries/{s['model_guid']}/{s['folder']}/incoming", "values_win": s["values_win"],
            "contact": s["contact"], "sender": s["sender"], "active": s["active"], "created_by": s["created_by"],
            "created_at": s["created_at"], "last_delivery_at": s["last_delivery_at"],
            "deliveries": {k: int(v or 0) for k, v in (counts or {}).items()}, "incoming": incoming,
            "model": {"id": str(s["model_guid"]), "name": s["model_name"]},
            # the Release 3 epic (D670): what kind of source it is, its schedule and its last run
            "kind": s.get("kind") or "folder", "schedule": s.get("schedule") or "off", "last_run": s.get("last_run") or {}}


def list_sources(conn, user, model: Any) -> dict:
    m = repo.get_model(conn, model)
    rows = _rows(conn, """SELECT s.*, m.guid AS model_guid, m.name AS model_name FROM core.import_sources s
                           JOIN core.models m ON m.id = s.model_id WHERE s.model_id = :m ORDER BY lower(s.name)""", m=m["_id"])
    waiting = _rows(conn, """SELECT l.guid FROM core.loads l WHERE l.model_id = :m AND l.source_id IS NOT NULL
                              AND l.status IN ('uploaded', 'mapping', 'previewed') ORDER BY l.created_at DESC LIMIT 100""",
                    m=m["_id"])
    return {"sources": [_source_out(conn, s) for s in rows],
            "waiting": [ld.get(conn, user, str(w["guid"]), with_rows=False) for w in waiting] if _sees_deliveries(conn, user, m) else [],
            "may_manage": _is_admin(conn, user, m), "may_accept": may_accept(conn, user, m)}


def _sees_deliveries(conn, user, m: dict) -> bool:
    if perms.SUPER_ADMIN in user.roles:
        return True
    return bool(set(perms.model_roles(conn, user.username, m["id"])) & {perms.MODEL_ADMIN, perms.MODEL_SUB_ADMIN, perms.COMMITTER})


def save_source(conn, user, model: Any, data: dict, source: Any = None) -> dict:
    """Adds or changes a source {name, description, folder, values_win, contact, sender, active} (Model Admins, D462)."""
    m = repo.get_model(conn, model)
    if not _is_admin(conn, user, m):
        raise EditError(f"Import sources of {m['name']} are set up by its Model Admins.", 403)
    name = (data.get("name") or "").strip()
    old = _source(conn, source) if source else None
    if old and str(old["model_guid"]) != str(m["id"]):
        raise EditError("That source belongs to another model.", 404)
    if not name and not old:
        raise EditError("Give the source a name: the system that delivers, for example Configuration database.")
    contact = (data.get("contact") or (old or {}).get("contact") or user.username).strip().lower()
    sender = data.get("sender", (old or {}).get("sender"))
    sender = (sender or "").strip().lower() or None
    vals = {"name": name or old["name"], "description": (data.get("description") if data.get("description") is not None
                                                         else (old or {}).get("description", "")) or "",
            "values_win": bool(data.get("values_win", (old or {}).get("values_win", False))), "contact": contact,
            "sender": sender, "active": bool(data.get("active", (old or {}).get("active", True)))}
    try:
        if old:
            conn.execute(text("""UPDATE core.import_sources SET name = :name, description = :description, values_win = :values_win,
                                        contact = :contact, sender = :sender, active = :active, updated_at = now()
                                  WHERE id = :i"""), {**vals, "i": old["id"]})
            g = str(old["guid"])
        else:
            folder = slug(data.get("folder") or name)
            taken = {r["folder"] for r in _rows(conn, "SELECT folder FROM core.import_sources WHERE model_id = :m", m=m["_id"])}
            base, n = folder, 2
            while folder in taken:
                folder, n = f"{base[:56]}-{n}", n + 1
            g = str(conn.execute(text("""INSERT INTO core.import_sources (model_id, name, description, folder, values_win, contact,
                                                                         sender, active, created_by)
                                         VALUES (:m, :name, :description, :folder, :values_win, :contact, :sender, :active, :u)
                                         RETURNING guid"""),
                                 {**vals, "m": m["_id"], "folder": folder, "u": user.username.lower()}).scalar_one())
    except Exception as exc:
        if "import_sources_name" in str(exc):
            raise EditError(f"{m['name']} already has a source called {vals['name']}.", 409) from exc
        raise
    s = _source(conn, g)
    _make_folders(str(s["model_guid"]), s["folder"])
    return _source_out(conn, s)


# ---------------------------------------------------------------- deliveries
def _check_file(name: str, content: bytes) -> None:
    ext = os.path.splitext(name.lower())[1]
    if ext == ".xml":
        sh.read(content, name)          # says why: the ArchiMate exchange format is not published yet (D385)
    if ext not in FORMATS:
        raise EditError(f"{name}: deliver the Excel format (.xlsx, .xlsm), the CSV format (a .zip with master.csv, or "
                        "CSV files with master.csv in the folder) or a single CSV.")
    if len(content) > MAX_BYTES:
        raise EditError(f"{name}: at most {MAX_BYTES // (1024 * 1024)} MB a delivery.")


def deliver(conn, user, source: Any, name: str, content: bytes, how: str = "api") -> dict:
    """One delivery: kept as a load from the source, previewed in the background by the caller (a task), waiting for review."""
    src = _source(conn, source)
    m = repo.get_model(conn, str(src["model_guid"]))
    if not src["active"]:
        raise EditError(f"The source {src['name']} is switched off: a Model Admin switches it on again.", 409)
    _may_send(conn, user, src, m)
    if not content:
        raise EditError("The file is empty.")
    _check_file(name, content)
    sh.read(content, name)             # readable at all: say so now, not in the background
    fmt = (name.rsplit(".", 1)[-1] if "." in name else "csv").lower()
    row = _one(conn, """INSERT INTO core.loads (model_id, file_name, format, content, owner, created_by, source_id, delivery)
                        VALUES (:m, :f, :fmt, :c, :o, :u, :s, :d) RETURNING id, guid""",
               m=m["_id"], f=name[:200], fmt=fmt, c=content, o=src["contact"], u=user.username.lower(), s=src["id"], d=how)
    conn.execute(text("UPDATE core.import_sources SET last_delivery_at = now() WHERE id = :i"), {"i": src["id"]})
    from . import notify
    reviewers = sorted({src["contact"], *[r["username"] for r in _rows(conn, """SELECT DISTINCT username FROM core.model_users
                                                        WHERE model_id = :m AND role IN ('model-admin', 'committer')""", m=m["_id"])]})
    notify.create(conn, kind="delivery.waiting", category="request", needs_action=True, model_id=m["_id"], actor=user.username,
                  recipients=reviewers, link=f"#/metamodel/{m['id']}/import/load/{row['guid']}", ref_kind="load", ref_id=row["id"],
                  title=f"A delivery from {src['name']} waits for review in {m['name']}",
                  body=f"{name}: check the preview (new, changed, kept and problems), then accept it as your committed load or "
                       "decline it.")
    return ld.get(conn, user, str(row["guid"]), with_rows=False) if _sees_deliveries(conn, user, m) or \
        user.username.lower() in (src["contact"],) else {"id": str(row["guid"]), "file_name": name, "status": "uploaded"}


def collect(conn, user, source: Any) -> dict:
    """Takes the files dropped in the source's incoming folder (D378): a CSV set with master.csv becomes one delivery (the
    CSVs it names, zipped), every Excel workbook, .zip or other CSV one delivery each. Taken files move to done/<when>/,
    files that cannot be taken to failed/<when>/ with a note of why."""
    src = _source(conn, source)
    m = repo.get_model(conn, str(src["model_guid"]))
    _may_send(conn, user, src, m)
    base = _make_folders(str(src["model_guid"]), src["folder"])
    if base is None:
        raise EditError("The import folder is not there: check the API's import folder (/data/imports, EAX_IMPORT_DIR).", 409)
    inc = base / "incoming"
    files = sorted(p for p in inc.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        return {"loads": [], "failed": [], "message": f"Nothing in {src['name']}'s folder."}
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    made, failed = [], []

    def move(paths: list[Path], where: str, why: str = "") -> None:
        dest = base / where / stamp
        dest.mkdir(parents=True, exist_ok=True)
        for p in paths:
            shutil.move(str(p), str(dest / p.name))
        if why:
            (dest / f"{paths[0].name}.why.txt").write_text(why + "\n", encoding="utf-8")

    def one(name: str, content: bytes, paths: list[Path]) -> None:
        sp = conn.begin_nested()
        try:
            made.append(deliver(conn, user, src["guid"], name, content, "folder"))
            sp.commit()
            move(paths, "done")
        except EditError as exc:
            sp.rollback()
            failed.append({"file": name, "why": str(exc)})
            move(paths, "failed", str(exc))

    master = next((p for p in files if p.name.lower() == sh.MASTER), None)
    if master:
        try:
            listed = sh.read_master(master.read_bytes())
            by_name = {p.name.lower(): p for p in files}
            missing = [e["file"] for e in listed if e["file"].lower() not in by_name]
            if missing:
                raise EditError(f"master.csv names {', '.join(missing)}, not in the folder (yet): drop every file, then collect.")
            parts = [master] + [by_name[e["file"].lower()] for e in listed]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p in parts:
                    z.writestr(p.name, p.read_bytes())
            one(f"{src['folder']}-{stamp}.zip", buf.getvalue(), parts)
            files = [p for p in files if p not in parts]
        except EditError as exc:
            failed.append({"file": master.name, "why": str(exc)})
            if "not in the folder (yet)" not in str(exc):
                move([master], "failed", str(exc))
            files = [p for p in files if p != master and p.suffix.lower() != ".csv"]   # CSVs wait for their master file
    for p in files:
        if not p.exists():
            continue
        one(p.name, p.read_bytes(), [p])
    msg = f"{len(made)} deliveries from {src['name']} taken" + (f", {len(failed)} could not be" if failed else "") + "."
    return {"loads": made, "failed": failed, "message": msg}


# ---------------------------------------------------------------- review
def _delivery(conn, load: Any) -> tuple[dict, dict]:
    r = ld._load(conn, load)
    if not r.get("source_id"):
        raise EditError("This load is not a delivery: add it on the load page as your own changes.", 409)
    return r, repo.get_model(conn, str(r["model_guid"]))


def accept(conn, user, load: Any) -> dict:
    """The delivery becomes the person's changes and is committed at once: their committed load (D465). Undone as any load.
    Run as a background task."""
    r, m = _delivery(conn, load)
    if not may_accept(conn, user, m):
        raise EditError("Accepting a delivery commits it: it needs the Committer, Model Sub Admin or Model Admin role on "
                        f"{m['name']}.", 403)
    if r["status"] != "previewed":
        raise EditError({"added": "This delivery was already accepted.", "declined": "This delivery was declined."}.get(
            r["status"], "The preview is not ready yet."), 409)
    me = user.username.lower()
    conn.execute(text("UPDATE core.loads SET owner = :o WHERE id = :i"), {"o": me, "i": r["id"]})
    if not any(x["action"] in ("new", "changed") for x in (r["preview"] or {}).get("rows", [])):
        conn.execute(text("""UPDATE core.loads SET status = 'added', added_at = now(), accepted_by = :u, accepted_at = now(),
                                    message = 'Accepted: nothing to change (every row unchanged, kept or a problem).' WHERE id = :i"""),
                     {"u": me, "i": r["id"]})
        from . import notify
        notify.resolve_ref(conn, "load", r["id"], me, "accepted")
        return {"accepted": True, "added": 0, "committed": 0, "failed": [], "message": "Accepted: nothing to change."}
    out = ld.add(conn, user, str(r["guid"]))
    committed = 0
    mm = cm._model(conn, str(m["id"]))
    if cm.uses_commits(mm):
        ids = [x["g"] for x in _rows(conn, "SELECT unnest(change_ids)::text AS g FROM core.loads WHERE id = :i", i=r["id"])]
        if ids:
            res = cm.commit(conn, str(m["id"]), user, None, ids, None,
                            f"Delivery from {r['_source']['name']}: {r['file_name']}")
            done = (res or {}).get("committed")
            committed = len(done) if isinstance(done, list) else int(done or 0)
    conn.execute(text("UPDATE core.loads SET accepted_by = :u, accepted_at = now(), message = :msg WHERE id = :i"),
                 {"u": me, "i": r["id"], "msg": f"Accepted by {me}: {out['added']} changes committed"
                  + (f" ({len(out['failed'])} could not be made)" if out["failed"] else "") + "."})
    from . import notify
    notify.resolve_ref(conn, "load", r["id"], me, "accepted")
    return {"accepted": True, "added": out["added"], "committed": committed, "failed": out["failed"],
            "message": f"Accepted: {out['added']} changes committed as your load. Undo it on the load page if needed."}


def decline(conn, user, load: Any, note: str = "") -> dict:
    r, m = _delivery(conn, load)
    if not may_accept(conn, user, m):
        raise EditError(f"Declining a delivery needs the Committer, Model Sub Admin or Model Admin role on {m['name']}.", 403)
    if r["status"] in ("added", "undone", "declined"):
        raise EditError(f"This delivery was already {'accepted' if r['status'] in ('added', 'undone') else 'declined'}.", 409)
    me = user.username.lower()
    conn.execute(text("""UPDATE core.loads SET status = 'declined', declined_by = :u, declined_at = now(), message = :msg
                          WHERE id = :i"""), {"u": me, "i": r["id"], "msg": f"Declined by {me}" + (f": {note.strip()}" if note.strip() else ".")})
    from . import notify
    notify.resolve_ref(conn, "load", r["id"], me, "declined")
    return {"declined": True, "message": "Declined: nothing in the model changed."}
