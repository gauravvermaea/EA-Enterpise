"""Backups and restores (build phase 8.4, D216).

Administration > Backups (IT and Super Admins):
GET    /admin/backups                                  infrastructure and application backups, schedules, the one running
PUT    /admin/backups/schedules/<kind>                 {enabled, cron, tag, keep, warn_after_hours}: when and how many (D222)
POST   /admin/backups/infrastructure                   {tag}: an infrastructure backup now (a task)
POST   /admin/backups/infrastructure/<name>/pin        {pinned}
POST   /admin/backups/infrastructure/<name>/restore    {what: full|app|app+data|db|files, confirm: "RESTORE"}: in maintenance
GET    /admin/backups/restore                          the restore running or last finished (followed by the screen)
GET    /admin/restores                                 every restore (infrastructure and application), the one running
GET    /admin/restores/<id>                            one restore with its whole log; POST .../delete forgets a finished one
POST   /admin/backups/infrastructure/<name>/delete     delete an infrastructure backup by hand (not pinned)
POST   /admin/backups/application/<name>/delete        delete an application backup by hand (not pinned)
POST   /admin/backups/uploaded/<file>/delete           delete an uploaded file
POST   /admin/backups/application                      {tag, models}: every model (or the chosen ones) backed up (a task)
POST   /admin/backups/application/<name>/pin           {pinned}
GET    /admin/backups/application/<name>/<file>        download one model's file
POST   /admin/backups/upload                           a model backup file (.eaxbackup.zip) or a whole application
                                                    backup (.eaxapp.zip) from another installation (multipart "file")
GET    /admin/backups/application/<name>/download      every model of an application backup in one file (D233)
POST   /admin/backups/application/<name>/restore-all   {confirm: "RESTORE"}: every model over itself (Super Admins; a task)
POST   /admin/backups/stop                             stop the backups running (D231)
POST   /admin/backups/restore-model                    {where, name, file, model, mode: new|over, new_name, target}: a task
GET    /admin/backups/uploaded/<file>                  download an uploaded file
For the operations helper only (its token, D229):
POST   /internal/restore-started                       {restore}: an infrastructure restore starts: everyone is told now
On the model page (its Model Admins):
GET    /models/<m>/backups                             its backups (its own and those in application backups)
POST   /models/<m>/backups                             {note}: back it up now (a task)
GET    /models/<m>/backups/<file>                      download one of its own
POST   /models/<m>/backups/<file>/pin                  {pinned}
"""

from __future__ import annotations

import hmac
import os

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .. import __version__, audit, restore_notice
from .. import backup_schedule as bs
from .. import backups as bk
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .admin import _ops
from .models import Free, FreeIn
from .sheets import _task as _start_task


def _task(kind, *a, **kw):
    """A backup task, once the backups have a folder (R2.44, D635: on a server or platform, a mounted one)."""
    from .. import backup_folder
    ok, why = backup_folder.ready()
    if not ok and kind.startswith("backup."):
        abort(409, message=why)
    return _start_task(kind, *a, **kw)

blp = Blueprint("backups", __name__, url_prefix="/api/v1", description="Backups and restores (phase 8.4)")
SECURITY = [{"bearerAuth": []}]


def _err(exc) -> None:
    abort(getattr(exc, "status", 404), message=str(exc))


def _audit(action: str, object_type: str, object_id: str, details: dict) -> None:
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=action, object_type=object_type, object_id=object_id, details=details,
                     request_id=getattr(g, "request_id", None))


def _download(path) -> Response:
    data = path.read_bytes()
    return Response(data, mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{path.name}"'})


def services_on() -> bool:
    from .. import services
    try:
        return services.enabled("backups")
    except Exception:  # noqa: BLE001
        return True


# ---------------------------------------------------------------- Administration > Backups
def web_proven(conn) -> dict:
    """Whether backups and restores from the web are proven (R2.46; owner, 12 Nov 2026: "If we can not do reliable backups
    and restores from web, then we should just show the command to run"): the newest self-test run with backup checks
    (R2.45) passed all of them. Until one has, the Backups page shows the commands instead of its buttons."""
    from ..testing import store
    with store.tests(conn) as tc:                    # the self-test's results, in the tests database (R2.28)
        row = tc.execute(text("""SELECT r.id, r.finished_at,
                                        count(*) FILTER (WHERE x.outcome = 'failed') AS failed, count(*) AS checks
                                   FROM tests.test_runs r JOIN tests.test_results x ON x.run_id = r.id AND x.suite = 'backup'
                                  WHERE r.state IN ('passed', 'failed')
                                  GROUP BY r.id ORDER BY r.id DESC LIMIT 1""")).mappings().first()
    if not row:
        return {"proven": False, "why": "No self-test has checked the backups yet: run eax test backup (or the full test)."}
    if row["failed"]:
        return {"proven": False, "run": row["id"],
                "why": f"Self-test {row['id']}: {row['failed']} of {row['checks']} backup checks failed."}
    return {"proven": True, "run": row["id"], "at": row["finished_at"]}


@blp.route("/admin/backups")
class Backups(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every backup: infrastructure (from the operations helper) and application, what is running, maintenance"""
        try:
            infra = _ops("GET", "/backups", timeout=20)
        except Exception as exc:  # noqa: BLE001 - shown on the page; application backups still listed
            infra = {"infrastructure": [], "state": {}, "error": getattr(exc, "description", str(exc)), "keep": bk.keep()}
        with get_engine().connect() as conn:
            schedules = bs.get_all(conn)
            tz = str(bs.zone(conn))
            proven = web_proven(conn)
        return {"infrastructure": infra, "application": bk.list_application(), "on": services_on(), "schedules": schedules,
                "time_zone": tz, "folder": "work/backups", "version": __version__, "web": proven}


@blp.route("/admin/backups/projects")
class ProjectBackupsAll(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every project with its own backups (made on its page or here), newest first; each holds the project, its models
        and the latest version of each document"""
        from .. import project_backup as pb
        from ..db import get_projects_engine
        with get_projects_engine().connect() as pc:
            return {"projects": pb.list_all(pc)}


@blp.route("/admin/backups/schedules/<kind>")
class Schedule(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data, kind):
        """When a kind of backup runs and how many are kept ({enabled, cron, tag, keep, warn_after_hours}); IT and Super
        Admins. Kept in the database, never in the config file (D222)"""
        try:
            with get_engine().begin() as conn:
                before = bs.get(conn, kind)
                out = bs.update(conn, kind, data or {}, g.user.username)
                audit.record(conn, actor=g.user.username, action="backup.schedule", object_type="backup", object_id=kind,
                             details={k: {"from": before.get(k), "to": out.get(k)} for k in ("enabled", "cron", "tag", "keep",
                                                                                              "warn_after_hours")
                                      if before.get(k) != out.get(k)}, request_id=getattr(g, "request_id", None))
        except EditError as exc:
            _err(exc)
        return out


@blp.route("/admin/backups/infrastructure")
class InfraBackup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """An infrastructure backup now, tagged ({tag}): every database, the files, the config file, the release and
        image versions. Runs as a task; people keep working (no lock)"""
        if not services_on():
            abort(409, message="Backups are switched off (Administration > Services > Backups).")
        tag = str((data or {}).get("tag") or "").strip()[:60] or "on-demand"
        with get_engine().connect() as conn:
            keep = bs.keep(conn, "infrastructure")
        return _task("backup.infrastructure", None, f"Infrastructure backup '{tag}'", {"tag": tag, "version": __version__,
                                                                                       "keep": keep})


@blp.route("/admin/backups/infrastructure/<name>/verify")
class InfraVerify(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, name):
        """Checks an infrastructure backup can be restored, touching nothing live (R2.45): its checksums, every file set
        readable, every database restored into a scratch copy, counted and dropped. A task; its result lists the checks"""
        return _task("backup.verify", None, f"Trial restore of {name}", {"name": name})


@blp.route("/admin/backups/infrastructure/<name>/pin")
class InfraPin(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, name):
        """Pin a backup so the clean-up never removes it ({pinned: true}), or unpin it"""
        pinned = bool((data or {}).get("pinned"))
        out = _ops("POST", f"/backups/{name}/pin", {"pinned": pinned})
        _audit("backup.pin", "backup", name, {"pinned": pinned, "kind": "infrastructure"})
        return out


@blp.route("/admin/backups/infrastructure/<name>/restore")
class InfraRestore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data, name):
        """Restore an infrastructure backup, whole or in part ({what, confirm: "RESTORE"}). The installation is read-only
        while it runs, a backup of the current state is taken first, and everyone signs in again afterwards"""
        data = data or {}
        if str(data.get("confirm") or "") != "RESTORE":
            abort(400, message="Type RESTORE to confirm.")
        what = str(data.get("what") or "")
        _audit("backup.restore.start", "backup", name, {"what": what})
        return _ops("POST", "/backups/restore", {"name": name, "what": what, "by": g.user.username, "version": __version__},
                    timeout=20)


@blp.route("/internal/restore-started")
class RestoreStarted(MethodView):
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    def post(self, data):
        """For the operations helper only (X-Ops-Token): an infrastructure restore is starting, so everyone is told now and
        the webhooks are sent at once, before the database is replaced (D229)"""
        token = os.environ.get("EAX_OPS_TOKEN", "")
        if not token or not hmac.compare_digest(request.headers.get("X-Ops-Token", ""), token):
            abort(403, message="Not allowed.")
        try:
            rec = bk.record_detail(str((data or {}).get("restore") or ""), tail=1)
        except EditError as exc:
            _err(exc)
        with get_engine().begin() as conn:
            nid = restore_notice.started(conn, rec, send_now=True)
        return {"notified": bool(nid)}


@blp.route("/admin/backups/restore")
class RestoreState(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The backup or restore running in the operations helper, or the last one finished, with its log"""
        return _ops("GET", "/backups", timeout=20).get("state", {})


@blp.route("/admin/backups/application")
class AppBackup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """An application backup now ({tag, models}): every model (or the chosen ones) as a model backup file. A task"""
        data = data or {}
        tag = str(data.get("tag") or "").strip()[:60] or "application"
        return _task("backup.application", None, f"Application backup '{tag}'", {"tag": tag, "models": data.get("models") or []})


@blp.route("/admin/backups/application/<name>/download")
class AppDownload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, name):
        """Every model of an application backup in one file (<name>.eaxapp.zip), to keep or to upload elsewhere (D233)"""
        try:
            path = bk.application_zip(name)
        except EditError as exc:
            _err(exc)

        def stream():
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        yield chunk
            finally:
                import shutil
                shutil.rmtree(path.parent, ignore_errors=True)
        return Response(stream(), mimetype="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{path.name}"',
                                 "Content-Length": str(path.stat().st_size)})


@blp.route("/admin/backups/application/<name>/restore-all")
class AppRestoreAll(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data, name):
        """Every model of an application backup put back over itself; models no longer there are made again; models
        made since stay as they are ({confirm: "RESTORE"}; Super Admins; a task, D233)"""
        from .. import permissions as perms
        if perms.SUPER_ADMIN not in g.user.roles:
            abort(403, message="Restoring a whole application backup needs the Super Admin role.")
        if str((data or {}).get("confirm") or "") != "RESTORE":
            abort(400, message="Type RESTORE to confirm.")
        try:
            _, manifest = bk._run(name)
        except EditError as exc:
            _err(exc)
        _audit("backup.restore.start", "backup", name, {"what": "every model"})
        return _task("backup.restore_all", None, f"Restore every model of '{manifest.get('tag') or name}'", {"name": name})


@blp.route("/admin/backups/stop")
class StopBackups(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self):
        """Stop the backups running (D231): an infrastructure backup is killed and its partial folder deleted; an
        application backup stops after the model it is on and is deleted. A restore cannot be stopped"""
        stopping = [f"{n} (application: stops after the model it is on)" for n in bk.stop_application(g.user.username)]
        message = ""
        try:
            stopping += [x for x in _ops("POST", "/backups/stop", {"by": g.user.username}, timeout=60).get("stopping", [])
                         if "(application" not in x]
        except Exception as exc:  # noqa: BLE001 - abort() from _ops, or the helper is down
            message = getattr(exc, "data", {}).get("message", "") if hasattr(exc, "data") else str(exc)
        if not stopping:
            abort(409, message=message or "No backup is running.")
        _audit("backup.stop", "backup", ", ".join(stopping)[:200], {})
        return {"stopping": stopping}


@blp.route("/admin/backups/application/<name>/pin")
class AppPin(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, name):
        pinned = bool((data or {}).get("pinned"))
        try:
            out = bk.pin("application", name, "", "", pinned)
        except EditError as exc:
            _err(exc)
        _audit("backup.pin", "backup", name, {"pinned": pinned, "kind": "application"})
        return out


@blp.route("/admin/backups/application/<name>/<file>")
class AppFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, name, file):
        """Download one model's backup file from an application backup"""
        try:
            return _download(bk.path_of("application", name, file))
        except EditError as exc:
            _err(exc)


@blp.route("/admin/backups/uploaded/<file>")
class UploadedFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, file):
        try:
            return _download(bk.path_of("uploaded", "", file))
        except EditError as exc:
            _err(exc)


@blp.route("/admin/backups/upload")
class Upload(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth("system.operate")
    def post(self):
        """A model backup file from another installation (multipart "file"), kept to restore as a new model"""
        f = request.files.get("file")
        if not f or not f.filename:
            abort(400, message="Choose a model backup file (.eaxbackup.zip).")
        if f.filename.lower().endswith(bk.APP_SUFFIX):     # a whole application backup (D233)
            import tempfile
            from pathlib import Path
            tmp = Path(tempfile.mkdtemp(prefix="eaxup-")) / "upload.zip"
            try:
                f.save(tmp)
                out = bk.store_application_upload(tmp, f.filename)
            except EditError as exc:
                _err(exc)
            finally:
                import shutil
                shutil.rmtree(tmp.parent, ignore_errors=True)
            _audit("backup.upload", "backup", out["run"], {"models": out["models"]})
            return out
        try:
            out = bk.store_upload(f.read(), f.filename)
        except EditError as exc:
            _err(exc)
        _audit("backup.upload", "backup", out["file"], {"model": out["model"]["name"]})
        return out


@blp.route("/admin/backups/restore-model")
class RestoreModel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data):
        """Restore a model backup file ({where, name, file, model, mode: new|over, new_name, target}) as a new model
        (Model Creators, Super Admins) or over the model it came from (its Model Admin, after typing its name). A task"""
        data = dict(data or {})
        try:
            path = bk.path_of(data.get("where") or "application", data.get("name") or "", data.get("file") or "",
                              data.get("model") or "")
            info, z = bk.read_file(path)
            z.close()
        except EditError as exc:
            _err(exc)
        from .. import permissions as perms
        with get_engine().connect() as conn:   # whose backup files may be restored: their own model's, or IT and Super Admins
            may = perms.SUPER_ADMIN in g.user.roles or (data.get("where") != "model" and perms.allowed(g.user.roles, "system.operate"))
            if not may:
                try:
                    bk.may_back_up(conn, g.user, info["model"]["id"])
                except (repo.NotFound, EditError):
                    abort(403, message=f"Restoring a backup of {info['model']['name']} needs the Model Admin role on it, "
                                       "or IT Admin or Super Admin.")
        if data.get("mode") == "over":
            with get_engine().connect() as conn:
                try:
                    m = repo.get_model(conn, data.get("target") or info["model"]["id"])
                except (repo.NotFound, EditError) as exc:
                    _err(exc)
            if str(data.get("confirm") or "").strip() != m["name"]:
                abort(400, message=f"Type the model's name ({m['name']}) to put it back over itself.")
        return _task("backup.restore", None if data.get("mode") != "over" else info["model"]["id"],
                     f"Restore {info['model']['name']} ({'over itself' if data.get('mode') == 'over' else 'as a new model'})", data)


# ---------------------------------------------------------------- restores and deleting by hand (D227)
@blp.route("/admin/restores")
class Restores(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every restore, infrastructure and application, newest first, with the one running"""
        try:
            return _ops("GET", "/restores", timeout=20)
        except Exception:  # noqa: BLE001 - the helper is down: the records are files the API reads too
            return {"restores": bk.list_records(), "active": {"active": False}, "helper": "The operations helper is not reachable."}


@blp.route("/admin/restores/<rid>")
class RestoreDetail(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, rid):
        """One restore with its whole log (the newest 5,000 lines)"""
        try:
            return bk.record_detail(rid)
        except EditError as exc:
            _err(exc)


@blp.route("/admin/restores/<rid>/delete")
class RestoreDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, rid):
        """Forget a finished restore and its log"""
        try:
            out = bk.delete_record(rid)
        except EditError as exc:
            _err(exc)
        _audit("backup.delete", "restore", rid, {})
        return out


@blp.route("/admin/backups/infrastructure/<name>/delete")
class InfraDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, name):
        """Delete an infrastructure backup by hand (unpin it first if it is pinned)"""
        out = _ops("POST", f"/backups/{name}/delete", {})
        _audit("backup.delete", "backup", name, {"kind": "infrastructure"})
        return out


@blp.route("/admin/backups/application/<name>/delete")
class AppDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, name):
        """Delete an application backup by hand (unpin it first if it is pinned)"""
        try:
            out = bk.delete_application(name)
        except EditError as exc:
            _err(exc)
        _audit("backup.delete", "backup", name, {"kind": "application"})
        return out


@blp.route("/admin/backups/uploaded/<file>/delete")
class UploadedDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, file):
        try:
            out = bk.delete_file("uploaded", file)
        except EditError as exc:
            _err(exc)
        _audit("backup.delete", "backup", file, {"kind": "uploaded"})
        return out


# ---------------------------------------------------------------- on the model page
@blp.route("/models/<model>/backups")
class ModelBackups(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model):
        """The model's backups (its Model Admins): its own and its files in the application backups"""
        with get_engine().connect() as conn:
            try:
                m = bk.may_back_up(conn, g.user, model)
            except (repo.NotFound, EditError) as exc:
                _err(exc)
            keep = bk.keep(conn)
        return {"model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]}, "backups": bk.list_model(str(m["id"])),
                "keep": keep, "restores": bk.list_records(str(m["id"]))[:20]}

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, model):
        """Back the model up now ({note}); kept with the application backups and downloadable. A task"""
        with get_engine().connect() as conn:
            try:
                m = bk.may_back_up(conn, g.user, model)
            except (repo.NotFound, EditError) as exc:
                _err(exc)
        note = str((data or {}).get("note") or "").strip()[:80]
        return _task("backup.model", str(m["id"]), f"Back up {m['name']}", {"note": note})


@blp.route("/models/<model>/backups/<file>")
class ModelBackupFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model, file):
        with get_engine().connect() as conn:
            try:
                m = bk.may_back_up(conn, g.user, model)
                return _download(bk.path_of("model", "", file, str(m["id"])))
            except (repo.NotFound, EditError) as exc:
                _err(exc)


@blp.route("/models/<model>/backups/<file>/delete")
class ModelBackupDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model, file):
        """Delete one of the model's own backups (its Model Admins; unpin it first)"""
        with get_engine().connect() as conn:
            try:
                m = bk.may_back_up(conn, g.user, model)
                out = bk.delete_file("model", file, str(m["id"]))
            except (repo.NotFound, EditError) as exc:
                _err(exc)
        _audit("backup.delete", "model", str(m["id"]), {"file": file})
        return out


@blp.route("/models/<model>/backups/<file>/pin")
class ModelBackupPin(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model, file):
        pinned = bool((data or {}).get("pinned"))
        with get_engine().connect() as conn:
            try:
                m = bk.may_back_up(conn, g.user, model)
                out = bk.pin("model", "", file, str(m["id"]), pinned)
            except (repo.NotFound, EditError) as exc:
                _err(exc)
        _audit("backup.pin", "model", str(m["id"]), {"pinned": pinned, "file": file})
        return out
