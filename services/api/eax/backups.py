"""Application backups and model backups (build phase 8.4, D216).

An application backup is every model (or chosen ones) as model backup files in one tagged folder, and (when it is of
every model) every project with its documents (owner, 7 Nov 2026):
    work/backups/application/<UTC time>-<tag>/manifest.json, models/<model>.eaxbackup.zip and
    projects/<project>.eaxproject.zip (a project backup without its models: they are beside it)
A model backup is one model's file, made by its Model Admin on the model page:
    work/backups/application/models/<model guid>/<UTC time>-<note>.eaxbackup.zip (+ .json beside it)
A file brought from another installation is kept in application/uploaded/.

Each .eaxbackup.zip holds:
    backup.json        what it is: the model, when, who, why, the version, the counts
    package.zip        the deep model package (eax-package/1: metamodel, content, history), restored as a new model
    workbook.xlsx      the model in one Excel workbook, for people to read
    restore/side.json  the metamodel and the snapshot of the content, to put the model back over itself
(Documents and diagrams are added when the document management of phase 13 is built.)

Restoring makes a new model from package.zip, or puts the model back as it was over itself (the tag mechanism of
D172: the current state is kept as a tag and as a model backup first). Every backup and restore runs as a task in the
job runner. How many are kept is set on Administration > Backups (D222); pinned ones always.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import __version__
from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

FORMAT = "eax-model-backup/1"
SUFFIX = ".eaxbackup.zip"


def root() -> Path:
    return Path(os.environ.get("EAX_BACKUP_MOUNT", "/data/backups"))


def app_dir() -> Path:
    return root() / "application"


def keep(conn=None) -> int:
    """How many application backups (and of each model's own) are kept: Administration > Backups (D222)."""
    from . import backup_schedule as bs
    if conn is not None:
        return bs.keep(conn, "application")
    try:
        from .db import get_engine
        with get_engine().connect() as c:
            return bs.keep(c, "application")
    except Exception:  # noqa: BLE001
        return 7


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def human(stamp: str) -> str:
    """20261106T072704Z -> 2026-11-06 07:27 UTC"""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})", stamp or "")
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]} UTC" if m else (stamp or "")


def _slug(s: str, n: int = 50) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (s or "").strip()).strip("-.")[:n]


def _bypass(conn, on: bool) -> None:
    """IT Admins back up every model although they have no role on them: the rows are read past row-level security
    for that moment only (as in push-down, D84)."""
    conn.execute(text("SELECT set_config('eax.rls_bypass', :v, true)"), {"v": "on" if on else ""})


# ---------------------------------------------------------------- one model's backup file
def model_file(conn, model: Any, by: str, why: str) -> tuple[bytes, dict]:
    """One model as a backup file (bytes) and what it holds."""
    from . import tags as tg
    m = repo.get_model(conn, model)
    package, _, _ = mo.export_package(conn, model, "zip", actor=by, content_level="history")
    workbook = b""
    if m["kind"] != "template":
        workbook, _, _ = mo.export_package(conn, model, "xlsx", actor=by, content_level="content")
    side = tg.side_of_model(conn, model) if m["kind"] != "template" else None
    info = {"format": FORMAT, "created": _stamp(), "by": by, "why": why, "version": __version__,
            "model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"], "version": m["version_label"]},
            "counts": {"entities": len(side["snapshot"]["entities"]) if side else 0,
                       "relationships": len(side["snapshot"]["relationships"]) if side else 0},
            "contains": ["package.zip"] + (["workbook.xlsx", "restore/side.json"] if side else []),
            "later": "Documents and diagrams are added with the document management of phase 13."}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", json.dumps(info, indent=2, ensure_ascii=False))
        z.writestr("package.zip", package)
        if side:
            z.writestr("workbook.xlsx", workbook)
            z.writestr("restore/side.json", json.dumps({k: side[k] for k in ("commit", "metamodel_version", "spec", "snapshot")},
                                                       default=str, ensure_ascii=False))
        z.writestr("README.txt", "EA Explorer model backup (eax-model-backup/1). backup.json says what it is; package.zip is the "
                                 "model package (upload it on Models > Upload a package, or restore this file on Administration > "
                                 "Backups); workbook.xlsx is the model to read in Excel; restore/side.json puts the model back "
                                 "over itself on the installation it came from.\n")
    return buf.getvalue(), info


def read_file(path: Path) -> tuple[dict, zipfile.ZipFile]:
    try:
        z = zipfile.ZipFile(path)
        info = json.loads(z.read("backup.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise EditError(f"{path.name} is not an EA Explorer model backup.", 400) from exc
    if info.get("format") != FORMAT:
        raise EditError(f"{path.name} is not an EA Explorer model backup.", 400)
    return info, z


def _meta(path: Path) -> dict:
    side = path.with_suffix("").with_suffix(".json")
    try:
        meta = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            meta, _ = read_file(path)
        except EditError:
            meta = {}
    return {**meta, "file": path.name, "bytes": path.stat().st_size, "pinned": bool(meta.get("pinned"))}


# ---------------------------------------------------------------- listing
def list_application() -> dict:
    """The application backups (newest first), the model backups by model and the uploaded files."""
    base = app_dir()
    runs = []
    for d in sorted(base.glob("*/manifest.json"), reverse=True):
        try:
            m = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m["name"] = d.parent.name
        m["pinned"] = (d.parent / "PINNED").exists()
        m["bytes"] = sum(f.stat().st_size for f in d.parent.rglob("*") if f.is_file())
        runs.append(m)
    uploaded = [_meta(p) for p in sorted((base / "uploaded").glob(f"*{SUFFIX}"), reverse=True)] if (base / "uploaded").is_dir() else []
    return {"runs": runs, "uploaded": uploaded, "folder": "work/backups/application"}


def list_model(model_guid: str) -> list[dict]:
    """A model's backups: its own (made on the model page) and its files in the application backups, newest first."""
    out = []
    own = app_dir() / "models" / model_guid
    if own.is_dir():
        out += [{**_meta(p), "where": "model", "run": ""} for p in own.glob(f"*{SUFFIX}")]
    for run in list_application()["runs"]:
        for f in run.get("models") or []:
            if f.get("id") == model_guid and f.get("status") == "ok":
                p = app_dir() / run["name"] / "models" / f["file"]
                if p.exists():
                    out.append({**f, "created": run.get("created"), "by": run.get("by"), "why": run.get("tag"),
                                "bytes": p.stat().st_size, "where": "application", "run": run["name"], "pinned": run.get("pinned")})
    return sorted(out, key=lambda x: str(x.get("created") or ""), reverse=True)


def path_of(where: str, name: str, file: str, model_guid: str = "") -> Path:
    """The file of a backup, never outside the backup folder."""
    project_file_ = (file or "").endswith(".eaxproject.zip") and where == "application"   # a project in an application backup
    if not re.match(r"^[A-Za-z0-9._-]+$", file or "") or not (file.endswith(SUFFIX) or project_file_):
        raise EditError("No such backup file.", 404)
    if where == "model":
        p = app_dir() / "models" / str(repo._as_guid(model_guid) or "x") / file
    elif where == "uploaded":
        p = app_dir() / "uploaded" / file
    else:
        if not re.match(r"^[A-Za-z0-9._-]+$", name or ""):
            raise EditError("No such backup.", 404)
        p = app_dir() / name / ("projects" if project_file_ else "models") / file
    if not p.is_file():
        raise EditError("No such backup file.", 404)
    return p


# ---------------------------------------------------------------- making them (run as tasks by the job runner)
def stop_application(by: str) -> list[str]:
    """Asks the running application backups to stop after the model they are on (D231)."""
    out = []
    for r in list_application()["runs"]:
        if r.get("status") == "running":
            try:
                (app_dir() / r["name"] / "STOP").write_text(by or "someone", encoding="utf-8")
                out.append(r["name"])
            except OSError:
                pass
    return out


def application_backup(conn, user, tag: str, models: list[str] | None = None, keep_n: int | None = None) -> tuple[str, dict]:
    """Every model (or the chosen ones) into one tagged application backup; with every model, every project too, with its
    documents (the latest version of each, from Documents)."""
    name = f"{_stamp()}-{_slug(tag) or 'application'}"
    folder = app_dir() / name / "models"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"format": "eax-application-backup/1", "tag": tag or "application", "by": user.username, "created": _stamp(),
                "version": __version__, "status": "running", "models": [], "projects": []}
    _write_json(folder.parent / "manifest.json", manifest)
    _bypass(conn, True)
    try:
        rows = repo._rows(conn, """SELECT guid, name, kind_code FROM core.models WHERE NOT is_deleted AND source_model_id IS NOT NULL
                                   ORDER BY kind_code <> 'template', name""")
        wanted = {str(repo._as_guid(m)) for m in models or []}
        ok = 0
        for r in rows:
            if wanted and str(r["guid"]) not in wanted:
                continue
            if (folder.parent / "STOP").exists():          # stopped by hand (D231): the partial backup goes
                who = (folder.parent / "STOP").read_text(encoding="utf-8").strip() or "someone"
                shutil.rmtree(folder.parent, ignore_errors=True)
                return (f"Application backup '{manifest['tag']}' stopped by {who} after {ok} model{'s' if ok != 1 else ''}; "
                        "the partial backup was deleted.", {"name": name, "stopped": True, "models": ok})
            file = f"{_slug(r['name'], 40) or 'model'}-{str(r['guid'])[:8]}{SUFFIX}"
            try:
                data, info = model_file(conn, str(r["guid"]), user.username, f"application backup {tag}")
                (folder / file).write_bytes(data)
                manifest["models"].append({"id": str(r["guid"]), "name": r["name"], "kind": r["kind_code"], "file": file,
                                           "status": "ok", "counts": info["counts"]})
                ok += 1
            except Exception as exc:  # noqa: BLE001 - one model does not stop the others; it is listed with why
                manifest["models"].append({"id": str(r["guid"]), "name": r["name"], "kind": r["kind_code"], "file": "",
                                           "status": "failed", "error": str(exc)[:300]})
        if not wanted:
            _write_json(folder.parent / "manifest.json", manifest)
            _backup_projects(conn, user, folder.parent, manifest, tag)
    finally:
        _bypass(conn, False)
    p_ok = len([p for p in manifest["projects"] if p["status"] == "ok"])
    p_failed = len(manifest["projects"]) - p_ok
    docs = sum(p.get("documents", 0) for p in manifest["projects"])
    failed = len(manifest["models"]) - ok + p_failed
    missing = sum(p.get("missing", 0) for p in manifest["projects"])
    manifest.update(status="ok" if not (failed or missing) else "partial", finished=_stamp(), documents_missing=missing)
    _write_json(folder.parent / "manifest.json", manifest)
    removed = cleanup(keep_n or keep(conn))
    return (f"Application backup '{manifest['tag']}': {ok} model{'s' if ok != 1 else ''}"
            f"{f', {p_ok} project' + ('s' if p_ok != 1 else '') + f' with {docs} documents' if manifest['projects'] else ''} backed up"
            f"{f', {failed} failed' if failed else ''}."
            + (f" {missing} document files could not be read from Documents (is it running?): this backup is partial." if missing else ""),
            {"name": name, "models": ok, "projects": p_ok, "documents": docs, "failed": failed, "removed": removed})


def _backup_projects(conn, user, run_dir: Path, manifest: dict, tag: str) -> None:
    """Every project of the application backup, each to projects/<name>-<guid8>.eaxproject.zip, with its documents."""
    from . import project_backup as pb
    from . import projects as pj
    from .background import _projects_beside
    out = run_dir / "projects"
    out.mkdir(parents=True, exist_ok=True)
    with _projects_beside(conn) as pc:
        for p in pj._rows(pc, "SELECT * FROM proj.projects ORDER BY name"):
            file = f"{_slug(p['name'], 40) or 'project'}-{str(p['guid'])[:8]}{pb.SUFFIX}"
            try:
                data, info = pb.project_file(conn, pc, user, p, f"application backup {tag}", with_models=False)
                (out / file).write_bytes(data)
                manifest["projects"].append({"id": str(p["guid"]), "name": p["name"], "file": file, "status": "ok",
                                             "documents": info["counts"].get("documents", 0),
                                             "missing": len(info.get("documents_missing") or [])})
            except Exception as exc:  # noqa: BLE001 - one project does not stop the others; it is listed with why
                manifest["projects"].append({"id": str(p["guid"]), "name": p["name"], "file": "", "status": "failed",
                                             "error": str(exc)[:300]})


def model_backup(conn, user, model: Any, why: str = "") -> tuple[str, dict]:
    """A Model Admin's backup of their model (or one taken before a restore over it)."""
    m = repo.get_model(conn, model)
    data, info = model_file(conn, model, user.username, why or "backed up on the model page")
    folder = app_dir() / "models" / str(m["id"])
    folder.mkdir(parents=True, exist_ok=True)
    file = f"{_stamp()}-{_slug(why, 40) or 'backup'}{SUFFIX}"
    (folder / file).write_bytes(data)
    _write_json(folder / file.replace(SUFFIX, ".json"), {**info, "pinned": False})
    cleanup(keep(conn))
    return f"{m['name']} backed up ({len(data) // 1024 + 1} KB).", {"file": file, "model": str(m["id"]), "counts": info["counts"]}


def may_back_up(conn, user, model: Any) -> dict:
    m = repo.get_model(conn, model)
    if perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"]):
        return m
    raise EditError(f"Backing up {m['name']} needs the Model Admin role on it.", 403)


# ---------------------------------------------------------------- restore records (D227)
# Every restore, of a model as of the installation, has a record in work/backups/restores/<id>: status.json and
# restore.log, listed on Administration > Restores and by the eax command, kept until deleted by hand.
def restores_dir() -> Path:
    return root() / "restores"


def new_record(kind: str, backup: str, what: str, by: str, model: str = "") -> dict:
    rid = f"{_stamp()}-{kind[:5]}-{_slug(backup, 40) or 'restore'}"
    rec = {"id": rid, "kind": kind, "backup": backup, "what": what, "by": by, "model": model,
           "started": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "finished": None, "status": "running", "error": "",
           "warnings": [], "step": "starting"}
    (restores_dir() / rid).mkdir(parents=True, exist_ok=True)
    _write_json(restores_dir() / rid / "status.json", rec)
    return rec


def record_log(rec: dict, msg: str, step: str = "") -> None:
    try:
        with open(restores_dir() / rec["id"] / "restore.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")
        if step:
            rec["step"] = step
            _write_json(restores_dir() / rec["id"] / "status.json", rec)
    except OSError:
        pass


def record_end(rec: dict, status: str, error: str = "") -> None:
    rec.update(status=status, error=error[:1000], step="done" if status == "ok" else "failed",
               finished=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        _write_json(restores_dir() / rec["id"] / "status.json", rec)
    except OSError:
        pass


def list_records(model: str = "") -> list[dict]:
    out = []
    for f in restores_dir().glob("*/status.json") if restores_dir().is_dir() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        r.pop("token_sha", None)
        if not model or r.get("model") == model:
            out.append(r)
    return sorted(out, key=lambda r: r.get("started") or "", reverse=True)


def record_detail(rid: str, tail: int = 5000) -> dict:
    if not re.match(r"^[A-Za-z0-9._-]+$", rid or ""):
        raise EditError("No such restore.", 404)
    d = restores_dir() / rid
    try:
        rec = json.loads((d / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EditError("No such restore.", 404) from exc
    rec.pop("token_sha", None)
    try:
        lines = (d / "restore.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    return {**rec, "log": lines[-tail:], "lines": len(lines)}


def delete_record(rid: str) -> dict:
    rec = record_detail(rid, 0)
    if rec["status"] == "running":
        raise EditError("This restore is still running: it can be deleted when it has finished.", 409)
    shutil.rmtree(restores_dir() / rid, ignore_errors=True)
    return {"deleted": rid}


def delete_application(name: str) -> dict:
    """Delete an application backup by hand (not pinned)."""
    folder = app_dir() / name
    if not re.match(r"^[A-Za-z0-9._-]+$", name or "") or not (folder / "manifest.json").exists() or name in ("models", "uploaded", "projects"):
        raise EditError("No such backup.", 404)
    if (folder / "PINNED").exists():
        raise EditError(f"{name} is pinned: unpin it first.", 409)
    shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": name}


def delete_file(where: str, file: str, model_guid: str = "") -> dict:
    """Delete one model backup file or an uploaded file by hand (not pinned)."""
    if where not in ("model", "uploaded"):
        raise EditError("Delete the whole application backup instead.", 409)
    p = path_of(where, "", file, model_guid)
    if _meta(p)["pinned"]:
        raise EditError(f"{file} is pinned: unpin it first.", 409)
    p.unlink(missing_ok=True)
    p.with_suffix("").with_suffix(".json").unlink(missing_ok=True)
    return {"deleted": file}


# ---------------------------------------------------------------- restoring (run as tasks)
RESTORE_LOCK = "Being restored from a backup (restore {rid}) by {by}"   # the lock's reason (D236); the job runner
#                                                                       lifts one whose restore is no longer running


def lock_for_restore(model: Any, user, rid: str) -> bool:
    """Locks a model while a backup is put back over it (D236): a maintenance lock for the person restoring, in a
    transaction of its own so that everyone else sees it at once and cannot change the model meanwhile. Returns
    whether this restore set it (False: they hold such a lock already). A model locked by anyone else is refused."""
    from . import metamodel_edit as me
    from .db import get_engine
    with get_engine().begin() as c:
        m = repo.get_model(c, model)
        level = m.get("lock_level") or "none"
        if level != "none":
            if level == "maintenance" and (m.get("locked_by") or "").lower() == user.username.lower():
                return False
            raise EditError(f"{m['name']} is locked ({level}) by {m.get('locked_by') or '?'}: it cannot be restored until "
                            "the lock is lifted.", 409)
        me.set_lock(c, model, "maintenance", RESTORE_LOCK.format(rid=rid, by=user.username), user.username)
    return True


def unlock_after_restore(conn, model: Any, user) -> None:
    """Lifts the restore's lock (D236). With conn: in the restore's own transaction (it then holds the model's row);
    without: in a transaction of its own (after the restore's work was rolled back)."""
    from . import metamodel_edit as me
    try:
        if conn is not None:
            me.clear_lock(conn, model, user.username)
        else:
            from .db import get_engine
            with get_engine().begin() as c:
                me.clear_lock(c, model, user.username)
    except EditError:
        pass


def lift_stale_restore_locks(conn) -> int:
    """Every minute (the job runner): a model still locked by a restore that is no longer running is unlocked (D236)."""
    running = {r["id"] for r in list_records() if r.get("status") == "running"}
    n = 0
    for r in repo._rows(conn, """SELECT id, lock_reason FROM core.models
                                  WHERE lock_level = 'maintenance' AND lock_reason LIKE 'Being restored from a backup (restore %'"""):
        rid = re.match(r"^Being restored from a backup \(restore ([^)]+)\)", r["lock_reason"])
        if rid and rid.group(1) not in running:
            conn.execute(text("UPDATE core.models SET lock_level = 'none' WHERE id = :i"), {"i": r["id"]})
            n += 1
    return n


def _announce(what: str, rec: dict) -> None:
    """Everyone is told (D229), in a transaction of its own (the restore's own rolls back when it fails)."""
    from . import restore_notice
    from .db import get_engine
    try:
        with get_engine().begin() as c:
            getattr(restore_notice, what)(c, rec)
    except Exception as exc:  # noqa: BLE001 - a notification never stops a restore
        record_log(rec, f"(could not tell everyone: {exc})")


def restore(conn, user, p: dict) -> tuple[str, dict]:
    """p: where (model, application, uploaded), name (the application backup), file, model (for a model backup), mode
    (new or over), new_name, target (the model to put back, mode over). Recorded with its log (D227)."""
    path = path_of(p.get("where") or "application", p.get("name") or "", p.get("file") or "", p.get("model") or "")
    info, z = read_file(path)
    mode = "over" if p.get("mode") == "over" else "new"
    rec = new_record("application", f"{info['model']['name']} ({human(info['created'])})", mode, user.username,
                     info["model"]["id"])
    record_log(rec, f"restore of {path.name} ({info['model']['name']}, backed up {human(info['created'])} by {info.get('by')}) "
                    f"{'over the model' if mode == 'over' else 'as a new model'}, by {user.username}", "restoring")
    _announce("started", rec)
    target = p.get("target") or info["model"]["id"]
    locked = False
    try:
        if mode == "over":
            locked = lock_for_restore(target, user, rec["id"])
            record_log(rec, f"{info['model']['name']} is locked while it is restored: nobody else can change it meanwhile")
        conn.execute(text("SAVEPOINT restore_model"))
        with z:
            if mode == "over":
                record_log(rec, "the model as it is now is backed up first; then the backup becomes one commit of kind restore")
                msg, out = _restore_over(conn, user, info, z, target)
            else:
                record_log(rec, "making a new model from the package (a draft)")
                msg, out = _restore_new(conn, user, info, z, (p.get("new_name") or "").strip())
        if locked:
            unlock_after_restore(conn, target, user)       # lifted with the restore itself
        conn.execute(text("RELEASE SAVEPOINT restore_model"))
    except Exception as exc:
        if locked:
            try:
                conn.execute(text("ROLLBACK TO SAVEPOINT restore_model"))
            except Exception:  # noqa: BLE001 - the savepoint was not made yet
                pass
            unlock_after_restore(None, target, user)
        record_log(rec, f"failed: {exc} (nothing was changed: the restore runs in one transaction)")
        record_end(rec, "failed", str(exc))
        _announce("ended", rec)
        raise
    record_log(rec, msg)
    record_end(rec, "ok")
    _announce("ended", rec)
    return msg, {**out, "restore": rec["id"]}


def _restore_new(conn, user, info: dict, z: zipfile.ZipFile, new_name: str) -> tuple[str, dict]:
    kind = info["model"].get("kind")
    if kind == "template" and perms.SUPER_ADMIN not in user.roles:
        raise EditError("Restoring a root metamodel needs the Super Admin role.", 403)
    if not (perms.SUPER_ADMIN in user.roles or perms.allowed(user.roles, "models.create")):
        raise EditError("Restoring a backup as a new model needs the Model Creator role (or Super Admin).", 403)
    pkg = mo.read_package(z.read("package.zip"), "package.zip")
    as_kind = "library" if kind == "reference" and (perms.SUPER_ADMIN in user.roles or perms.allowed(user.roles, "library.curate")) \
        else None if kind == "template" else "project"
    name = new_name or f"{info['model']['name']} (restored from {human(info['created'])[:10]})"
    if not new_name:   # restoring the same backup again makes another copy, never a clash (D227: restores can be repeated)
        base, n = name, 1
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))   # every name counts
        while conn.execute(text("SELECT 1 FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted"), {"n": name}).first():
            n += 1
            name = f"{base} {n}"
        conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
    where = "as a root metamodel" if kind == "template" else "under its root metamodel"
    conn.execute(text("SAVEPOINT restore_root"))
    try:
        out = mo.import_package(conn, pkg, "root", user.username, name=name, as_kind=as_kind)
        conn.execute(text("RELEASE SAVEPOINT restore_root"))
    except EditError as exc:
        if exc.status != 409:
            raise
        conn.execute(text("ROLLBACK TO SAVEPOINT restore_root"))
        out = mo.import_package(conn, pkg, "own_root", user.username, name=name, as_kind=as_kind)
        where = "as a root of its own (its metamodel does not match one here)"
    new = out["model"]
    if perms.SUPER_ADMIN not in user.roles:   # the person who restored it looks after it
        conn.execute(text("""INSERT INTO core.model_users (model_id, username, role) VALUES (:m, :u, 'model-admin')
                             ON CONFLICT DO NOTHING"""), {"m": new["_id"], "u": user.username.lower()})
    return (f"Restored {info['model']['name']} as the new model '{new['name']}' {where}; it starts as a draft.",
            {"model": str(new["id"]), "name": new["name"], "counts": out.get("counts")})


def _restore_over(conn, user, info: dict, z: zipfile.ZipFile, target: Any) -> tuple[str, dict]:
    from . import tags as tg
    m = repo.get_model(conn, target)
    if str(m["id"]) != info["model"]["id"]:
        raise EditError(f"This backup is of {info['model']['name']}, not of {m['name']}: restore it as a new model instead.", 409)
    if "restore/side.json" not in z.namelist():
        raise EditError("This backup cannot be put back over a model (a root metamodel): restore it as a new model.", 409)
    side = json.loads(z.read("restore/side.json"))
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"Restoring {m['name']} over itself needs the Model Admin role on it.", 403)
    # the state now is kept first: a model backup file (and, by the tag mechanism, a before-restore tag)
    model_backup(conn, user, str(m["id"]), f"before restoring the backup of {human(info['created'])}")
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    row = repo._rows(conn, """INSERT INTO core.model_tags (model_id, name, description, kind, commit_number, metamodel_version, spec,
                                                           snapshot, entity_count, relationship_count, created_by)
                              VALUES (:m, :n, :d, 'backup', :c, :v, CAST(:spec AS jsonb), CAST(:snap AS jsonb), :ec, :rc, :by)
                              RETURNING guid""",
                     m=m["_id"], n=f"Backup of {human(info['created'])} restored {when} UTC",
                     d=f"The backup made by {info.get('by')} ({info.get('why') or 'no note'}), put back by {user.username}.",
                     c=side.get("commit") or 0, v=side.get("metamodel_version") or 0, spec=json.dumps(side["spec"], default=str),
                     snap=json.dumps(side["snapshot"], default=str), ec=len(side["snapshot"]["entities"]),
                     rc=len(side["snapshot"]["relationships"]), by=user.username.lower())[0]
    out = tg.restore_tag(conn, str(m["id"]), user, str(row["guid"]),
                         f"Restored the backup of {human(info['created'])} ({info.get('why') or 'no note'})")
    return (f"{m['name']} is back as it was in the backup of {human(info['created'])} (commit {out['commit_number']}). "
            f"What it was just before is kept as a model backup and as the tag '{out['before_tag']['name']}'.",
            {"model": str(m["id"]), "commit": out["commit"], "items": out["items"], "before_tag": out["before_tag"]})


# ---------------------------------------------------------------- a whole application backup at once (D233)
APP_FORMAT = "eax-application-backup/1"
APP_SUFFIX = ".eaxapp.zip"


def _run(name: str) -> tuple[Path, dict]:
    if not re.match(r"^[A-Za-z0-9._-]+$", name or ""):
        raise EditError("No such application backup.", 404)
    d = app_dir() / name
    try:
        return d, json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EditError("No such application backup.", 404) from exc


def application_zip(name: str) -> Path:
    """Every model of an application backup in one file (<name>.eaxapp.zip, made in a temporary folder) to download
    and upload to another installation."""
    import tempfile
    d, manifest = _run(name)
    if manifest.get("status") == "running":
        raise EditError("This application backup is still running.", 409)
    out = Path(tempfile.mkdtemp(prefix="eaxapp-")) / f"{name}{APP_SUFFIX}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:    # the model files are zips already
        z.write(d / "manifest.json", "manifest.json")
        for m in manifest.get("models") or []:
            f = d / "models" / (m.get("file") or "")
            if m.get("status") == "ok" and f.is_file():
                z.write(f, f"models/{f.name}")
        for p in manifest.get("projects") or []:
            f = d / "projects" / (p.get("file") or "")
            if p.get("status") == "ok" and f.is_file():
                z.write(f, f"projects/{f.name}")
    return out


def store_application_upload(path: Path, filename: str) -> dict:
    """A whole application backup from another installation (.eaxapp.zip): listed with the others, marked uploaded."""
    try:
        z = zipfile.ZipFile(path)
        manifest = json.loads(z.read("manifest.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise EditError(f"{filename} is not an EA Explorer application backup.", 400) from exc
    if manifest.get("format") != APP_FORMAT:
        raise EditError(f"{filename} is not an EA Explorer application backup.", 400)
    with z:
        files = [n for n in z.namelist() if re.match(r"^models/[A-Za-z0-9._-]+" + re.escape(SUFFIX) + "$", n)]
        pfiles = [n for n in z.namelist() if re.match(r"^projects/[A-Za-z0-9._-]+\.eaxproject\.zip$", n)]
        name = f"{_stamp()}-uploaded-{_slug(manifest.get('tag') or 'application', 30) or 'application'}"
        d = app_dir() / name
        (d / "models").mkdir(parents=True, exist_ok=True)
        (d / "projects").mkdir(parents=True, exist_ok=True)
        for n in files + pfiles:
            (d / n).write_bytes(z.read(n))
    have = {Path(n).name for n in files + pfiles}
    manifest["models"] = [m for m in manifest.get("models") or [] if m.get("file") in have]
    manifest["projects"] = [p for p in manifest.get("projects") or [] if p.get("file") in have]
    manifest.update(uploaded=True, uploaded_from=filename, status=manifest.get("status") or "ok")
    _write_json(d / "manifest.json", manifest)
    return {"run": name, "tag": manifest.get("tag"), "models": len(manifest["models"]), "projects": len(manifest["projects"])}


def restore_application(conn, user, name: str) -> tuple[str, dict]:
    """Every model of an application backup put back over itself; one that no longer exists is made again with its
    name (D233). Models made after the backup are left as they are. Each model in a savepoint of its own: one that
    fails is listed with why and the others go on. Recorded with its log and told to everyone."""
    if perms.SUPER_ADMIN not in user.roles:
        raise EditError("Restoring a whole application backup needs the Super Admin role.", 403)
    d, manifest = _run(name)
    models = [m for m in manifest.get("models") or [] if m.get("status") == "ok"]
    projects = [p for p in manifest.get("projects") or [] if p.get("status") == "ok"]
    if not models and not projects:
        raise EditError("This application backup has no model to restore.", 409)
    rec = new_record("application", f"{manifest.get('tag') or name} ({human(manifest.get('created', ''))}), every model"
                     f"{' and project' if projects else ''}", "all", user.username)
    record_log(rec, f"restore of every model in {name} ({len(models)}) by {user.username}: each over itself, or made again "
                    "if it no longer exists; models made after the backup stay as they are", "restoring")
    _announce("started", rec)
    over, made, kept, failed = [], [], [], []
    remade: dict[str, str] = {}       # a model made again: its guid in the backup -> the new model (for the projects)
    # the project models put back over themselves are locked first, all at once, so nobody changes them meanwhile
    # (D236); each is unlocked as its restore is done (or fails)
    locked: dict[str, bool] = {}
    for m in models:
        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
        live = repo._rows(conn, "SELECT kind_code FROM core.models WHERE guid = CAST(:g AS uuid) AND NOT is_deleted", g=m["id"])
        conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
        if live and live[0]["kind_code"] == "project":
            try:
                locked[m["id"]] = lock_for_restore(m["id"], user, rec["id"])
            except EditError as exc:
                locked[m["id"]] = None
                failed.append(f"{m['name']}: {exc}")
    record_log(rec, f"{sum(1 for v in locked.values() if v is not None)} models locked while they are restored")
    for i, m in enumerate(models, 1):
        if locked.get(m["id"], False) is None:      # locked by someone else: not touched
            record_log(rec, f"{i}/{len(models)} {m['name']} skipped: locked by someone else")
            continue
        rec["step"] = f"model {i} of {len(models)}: {m['name']}"
        conn.execute(text("SAVEPOINT restore_all"))
        try:
            info, z = read_file(d / "models" / m["file"])
            with z:
                conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
                exists = conn.execute(text("SELECT 1 FROM core.models WHERE guid = CAST(:g AS uuid) AND NOT is_deleted"),
                                      {"g": info["model"]["id"]}).first()
                same_name = not exists and conn.execute(text(
                    "SELECT 1 FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted"), {"n": info["model"]["name"]}).first()
                conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
                if exists and info["model"].get("kind") == "project" and "restore/side.json" in z.namelist():
                    msg, _ = _restore_over(conn, user, info, z, info["model"]["id"])
                    if locked.get(m["id"]):
                        unlock_after_restore(conn, m["id"], user)
                    over.append(m["name"])
                elif exists:
                    msg = (f"{m['name']} ({'a root metamodel' if info['model'].get('kind') == 'template' else 'a library model'}) "
                           "exists: kept as it is (only project models are put back over themselves)")
                    kept.append(m["name"])
                elif same_name:   # made again by an earlier restore of this backup: a restore can be repeated (D228)
                    msg = f"{m['name']}: a model with this name exists (made again by an earlier restore?): kept as it is"
                    kept.append(m["name"])
                    if not manifest.get("uploaded"):    # this installation's own backup: that is the one made again before
                        conn.execute(text("SELECT set_config('eax.rls_bypass', 'on', true)"))
                        remade[info["model"]["id"]] = conn.execute(text(
                            "SELECT guid::text FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted"),
                            {"n": info["model"]["name"]}).scalar()
                        conn.execute(text("SELECT set_config('eax.rls_bypass', '', true)"))
                else:
                    msg, out_new = _restore_new(conn, user, info, z, info["model"]["name"])
                    made.append(m["name"])
                    remade[info["model"]["id"]] = out_new.get("model")
            conn.execute(text("RELEASE SAVEPOINT restore_all"))
            record_log(rec, f"{i}/{len(models)} {msg}", rec["step"])
        except Exception as exc:  # noqa: BLE001 - one model does not stop the others; listed with why
            conn.execute(text("ROLLBACK TO SAVEPOINT restore_all"))
            if locked.get(m["id"]):
                unlock_after_restore(conn, m["id"], user)
            failed.append(f"{m['name']}: {exc}")
            record_log(rec, f"{i}/{len(models)} {m['name']} FAILED (nothing changed for it): {exc}", rec["step"])
    p_done, p_ids, p_failed = _restore_projects(conn, user, d, projects, rec, remade, bool(manifest.get("uploaded"))) if projects else ([], [], [])
    failed += p_failed
    rec["warnings"] = [f"Not restored: {f}" for f in failed]
    msg = (f"Every model of '{manifest.get('tag') or name}': {len(over)} put back, {len(made)} made again"
           f"{f', {len(kept)} kept as they are (root metamodels, library models, models made again before)' if kept else ''}{f', {len(failed)} failed' if failed else ''}.")
    if projects:
        msg += (f" {len(p_done)} of {len(projects)} projects put back as they were; their repositories are built again in "
                "Documents and their documents put back within a few minutes.")
    record_log(rec, msg)
    record_end(rec, "failed" if failed and not (over or made) else "ok", "; ".join(failed)[:1000])
    _announce("ended", rec)
    return msg, {"restore": rec["id"], "over": over, "made": made, "kept": kept, "failed": failed, "projects": p_done, "project_ids": p_ids}


def _restore_projects(conn, user, run_dir: Path, projects: list[dict], rec: dict, remade: dict | None = None,
                      uploaded: bool = False) -> tuple[list[str], list[int], list[str]]:
    """After the models: each project of the backup over itself (or made again), each in a savepoint of its own. Its
    repository is built again by the minute job, which then puts its documents back (a document still in Documents gets
    the backed-up file as its newest version when it differs; one that is gone is uploaded again)."""
    from . import project_backup as pb
    from .background import _projects_beside
    done, ids, failed = [], [], []
    with _projects_beside(conn) as pc:
        for i, p in enumerate(projects, 1):
            rec["step"] = f"project {i} of {len(projects)}: {p['name']}"
            pc.execute(text("SAVEPOINT restore_project"))
            try:
                msg, out = pb.restore(conn, pc, user, run_dir / "projects" / p["file"], over=True, model_guids=remade or {},
                                      uploaded=uploaded)
                pc.execute(text("RELEASE SAVEPOINT restore_project"))
                done.append(p["name"])
                ids.append(out["project_id"])
                record_log(rec, f"project {i}/{len(projects)} {msg}", rec["step"])
            except Exception as exc:  # noqa: BLE001 - one project does not stop the others; listed with why
                pc.execute(text("ROLLBACK TO SAVEPOINT restore_project"))
                failed.append(f"{p['name']}: {exc}")
                record_log(rec, f"project {i}/{len(projects)} {p['name']} FAILED (nothing changed for it): {exc}", rec["step"])
    return done, ids, failed


def store_upload(data: bytes, filename: str) -> dict:
    """A backup file from another installation, kept to restore as a new model."""
    folder = app_dir() / "uploaded"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{_stamp()}-{_slug(Path(filename or 'upload').name.replace(SUFFIX, ''), 40) or 'upload'}{SUFFIX}"
    p = folder / name
    p.write_bytes(data)
    try:
        info, z = read_file(p)
        z.close()
    except EditError:
        p.unlink()
        raise
    _write_json(folder / name.replace(SUFFIX, ".json"), {**info, "pinned": False, "uploaded": True})
    return {**info, "file": name}


# ---------------------------------------------------------------- pinning and cleaning up
def pin(where: str, name: str, file: str, model_guid: str, pinned: bool) -> dict:
    if where == "application":
        folder = app_dir() / name
        if not re.match(r"^[A-Za-z0-9._-]+$", name or "") or not (folder / "manifest.json").exists():
            raise EditError("No such backup.", 404)
        flag = folder / "PINNED"
        if pinned:
            flag.write_text(_stamp(), encoding="utf-8")
        elif flag.exists():
            flag.unlink()
        return {"name": name, "pinned": pinned}
    p = path_of(where, name, file, model_guid)
    side = p.with_suffix("").with_suffix(".json")
    meta = _meta(p)
    _write_json(side, {**{k: v for k, v in meta.items() if k not in ("file", "bytes")}, "pinned": pinned})
    return {"file": file, "pinned": pinned}


def cleanup(n: int | None = None) -> list[str]:
    """Keeps the newest n application backups (Administration > Backups, D222), and of each model's own; pinned ones always."""
    n, gone = n or keep(), []
    runs = [r for r in list_application()["runs"] if not r["pinned"] and r.get("status") != "running" and not r.get("uploaded")]
    for r in runs[n:]:
        shutil.rmtree(app_dir() / r["name"], ignore_errors=True)
        gone.append(r["name"])
    from . import project_backup as pb
    gone += pb.cleanup_stash()                  # files of restores and uploads nothing waits for any more
    projects = app_dir() / "projects"          # each project's own backups (made on its page), the newest n of each
    if projects.is_dir():
        for d in projects.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                files = sorted(d.glob("*.eaxproject.zip"), reverse=True)
                for f in files[n:]:
                    f.unlink(missing_ok=True)
                    f.with_name(f.name.replace(".eaxproject.zip", ".json")).unlink(missing_ok=True)
                    gone.append(f"projects/{d.name}/{f.name}")
    models = app_dir() / "models"
    if models.is_dir():
        for d in models.iterdir():
            files = sorted((_meta(p) for p in d.glob(f"*{SUFFIX}")), key=lambda x: x["file"], reverse=True)
            for f in [x for x in files if not x["pinned"]][n:]:
                (d / f["file"]).unlink(missing_ok=True)
                (d / f["file"].replace(SUFFIX, ".json")).unlink(missing_ok=True)
                gone.append(f"{d.name}/{f['file']}")
    return gone


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)
