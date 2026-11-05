"""Import and export sheets (build phase 10.1, D197).

POST   /models/<m>/sheets                 build sheets for the chosen types {types, format: xlsx|xlsm|zip}: a task (?wait=true: the file)
GET    /tasks/<t>/file                    the file a task made
GET    /models/<m>/loads                  the loads of a model
POST   /models/<m>/loads                  upload a sheet (multipart "file"): a load, previewed in the background
GET    /loads/<l>                         a load with its preview rows (?action=new|changed|unchanged|delete|problem)
POST   /loads/<l>/mapping                 map the columns of unknown sheets {mapping, save_as} or {saved, sheet}: previewed again
PATCH  /loads/<l>/rows/<n>                correct one row {values}
POST   /loads/<l>/add                     the rows become your uncommitted changes (a task)
POST   /loads/<l>/undo                    discard or roll back what the load did {force}
DELETE /loads/<l>                         forget a load not added
GET|POST /models/<m>/column-mappings      saved column mappings; DELETE /models/<m>/column-mappings/<c>
"""

from __future__ import annotations

import logging

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import audit
from .. import loads as ld
from .. import repository as repo
from .. import sheets as sh
from .. import tasks as tk
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

blp = Blueprint("sheets", __name__, url_prefix="/api/v1", description="Import and export sheets (phase 10.1)")
SECURITY = [{"bearerAuth": []}]
log = logging.getLogger(__name__)


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str | None = None, model_id=None, details=None):
    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            try:
                out = fn(conn)
                if action:
                    audit.record(conn, actor=g.user.username, action=action, object_type="model" if model_id else "load",
                                 object_id=str(model_id or ""), details=details or {}, request_id=getattr(g, "request_id", None))
            except Exception:
                trans.rollback()
                raise
            trans.commit()
            return out
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _file(data: bytes, name: str, ctype: str) -> Response:
    safe = name.replace('"', "'")
    return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def _task(kind: str, model_id, label: str, params: dict, user=None) -> dict:
    """Queues long work for the job runner (D192); without a job runner it is done in the request."""
    user = user or g.user
    with get_engine().connect() as conn, conn.begin():
        task = tk.create(conn, kind, model_id, user, label, params)
    try:
        from ..jobs import app as jobs_app
        from ..jobs import run_task
        with jobs_app.open():
            job = run_task.defer(task_id=task["id"], actor=user.username, roles=list(user.roles))
        with get_engine().connect() as conn, conn.begin():
            tk.set_job(conn, task["id"], job)
    except Exception:  # noqa: BLE001
        log.warning("job runner not reachable; %s done in the request", kind)
        tk.run(task["id"], user.username, list(user.roles))
    with get_engine().connect() as conn:
        return tk.get(conn, user, task["id"])


def _model_of_load(load_id) -> str:
    return _read(lambda c: str(ld._load(c, load_id)["model_guid"]))


def _upload():
    f = request.files.get("file")
    if not f or not f.filename:
        abort(400, message="Choose a file to upload (Excel .xlsx or .xlsm, CSV, or a CSV set .zip).")
    data = f.read()
    if not data:
        abort(400, message="The file is empty.")
    return f.filename, data


# ---------------------------------------------------------------- sheets
@blp.route("/models/<uuid:model_id>/sheets")
class Sheets(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The entity types to choose from, by layer, with how many entities each has"""
        def run(c):
            m, types = sh.types_of(c, model_id, [t["code"] for t in repo._rows(c, """SELECT code FROM core.entity_types
                                                                                      WHERE model_id = (SELECT id FROM core.models WHERE guid = :g)
                                                                                        AND NOT is_deleted""", g=str(model_id))])
            return {"model": {"id": str(m["id"]), "name": m["name"]},
                    "types": [{"code": t["code"], "name": t["name"], "layer": t["layer"], "entities": t["n"],
                               "attributes": len(t["attributes"])} for t in types]}
        return _read(run)

    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "wait", "schema": {"type": "boolean"}}])
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Builds the sheets for the chosen entity types {types: [codes], format: xlsx|xlsm|zip}, with their data and the
        relationships between them (built now, D197). A task to follow; its file at GET /tasks/<id>/file"""
        types, fmt = data.get("types") or [], data.get("format") or "xlsx"
        if fmt not in ("xlsx", "xlsm", "zip"):
            abort(400, message="format is xlsx, xlsm or zip (a CSV set).")
        if request.args.get("wait") == "true":
            content, name, ctype = _read(lambda c: sh.build(c, model_id, types, fmt, g.user.username))
            return _file(content, name, ctype)
        m = _read(lambda c: sh.types_of(c, model_id, types)[0])
        return {"task": _task("sheet.build", model_id, f"Sheets of {m['name']} ({len(types) or 'every'} types, .{fmt})",
                              {"types": types, "format": fmt})}


@blp.route("/models/<uuid:model_id>/sheets/fields")
class SheetFields(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "types", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The fields of entity types (comma-separated codes), for mapping a sheet's columns"""
        codes = [x for x in (request.args.get("types") or "").split(",") if x]
        return _read(lambda c: {"types": [{"code": t["code"], "name": t["name"],
                                           "attributes": [{"code": a["code"], "name": a["name"], "data_type": a["data_type"]}
                                                          for a in t["attributes"]]} for t in sh.types_of(c, model_id, codes)[1]]})


@blp.route("/tasks/<task_id>/file")
class TaskFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, task_id):
        """The file a background task made (for example built sheets)"""
        f = _read(lambda c: tk.file_of(c, g.user, task_id))
        return _file(bytes(f["content"]), f["name"], f["content_type"])


# ---------------------------------------------------------------- loads
@blp.route("/models/<uuid:model_id>/loads")
class Loads(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's loads you may see: yours, and everyone's for committers and Model Admins"""
        return _read(lambda c: ld.list_loads(c, g.user, model_id))

    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, model_id):
        """Uploads a sheet (multipart field file): kept as a load and previewed in the background"""
        name, data = _upload()
        load = _write(lambda c: ld.create(c, model_id, g.user, name, data), "load.upload", model_id, {"name": name})
        task = _task("load.preview", model_id, f"Preview of {name}", {"load": load["id"], "file": name})
        return {"load": load, "task": task}


@blp.route("/loads/<load_id>")
class Load(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "action", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth()
    def get(self, load_id):
        """A load: status, summary and its preview rows (filter by action)"""
        return _read(lambda c: ld.get(c, g.user, load_id, True, request.args.get("action") or ""))

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, load_id):
        """Forgets a load that was not added"""
        def run(c):
            r = ld._load(c, load_id)
            if r["status"] == "added":
                raise EditError("An added load is undone, not deleted.", 409)
            if g.user.username.lower() not in (r["created_by"], r["owner"]):
                raise EditError("Only the person who loaded it deletes it.", 403)
            from sqlalchemy import text
            c.execute(text("DELETE FROM core.loads WHERE id = :i"), {"i": r["id"]})
            return {"deleted": load_id}
        return _write(run, "load.delete", _model_of_load(load_id), {"name": load_id})


@blp.route("/loads/<load_id>/mapping")
class LoadMapping(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, load_id):
        """Maps the columns of sheets EA Explorer does not know {mapping: {sheet: {entity_type, columns {header: code}}},
        save_as} or uses a saved one {saved, sheet}; then previews again"""
        mapping = data.get("mapping") or {}
        if data.get("saved"):
            mapping = _read(lambda c: ld.apply_saved_mapping(c, load_id, data["saved"], data.get("sheet") or ""))
        model_id = _model_of_load(load_id)
        _write(lambda c: ld.set_mapping(c, g.user, load_id, mapping, data.get("save_as")))
        return {"task": _task("load.preview", model_id, "Preview with the mapped columns", {"load": load_id})}


@blp.route("/loads/<load_id>/rows/<int:n>")
class LoadRow(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, load_id, n):
        """Corrects one row of the preview {values: {code: value}}; the preview is worked out again"""
        return _write(lambda c: ld.edit_row(c, g.user, load_id, n, data.get("values") or {}))


@blp.route("/loads/<load_id>/add")
class LoadAdd(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, load_id):
        """The previewed rows become your uncommitted changes (a task); commit them on the Changes tab"""
        model_id = _model_of_load(load_id)
        r = _read(lambda c: ld.get(c, g.user, load_id, with_rows=False))
        if r["status"] != "previewed":
            abort(409, message="Preview the load first." if r["status"] != "added" else "This load is already added.")
        if g.user.username.lower() not in (r["owner"], r["created_by"]) and "super-admin" not in g.user.roles:
            abort(403, message=f"This load becomes {r['owner']}'s changes: they add it.")
        from .. import permissions as perms
        owner = g.user if g.user.username.lower() == r["owner"] else perms.Principal(r["owner"], ())
        return {"task": _task("load.add", model_id, f"Add {r['file_name']} to {r['owner']}'s changes", {"load": load_id}, owner)}


@blp.route("/loads/<load_id>/undo")
class LoadUndo(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, load_id):
        """Undoes an added load: uncommitted changes discarded, committed ones rolled back as a new commit {force}"""
        model_id = _model_of_load(load_id)
        return _write(lambda c: ld.undo(c, g.user, load_id, bool(data.get("force"))), "load.undo", model_id, {"name": load_id})


# ---------------------------------------------------------------- column mappings
@blp.route("/models/<uuid:model_id>/column-mappings")
class Mappings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Saved column mappings for sheets from other systems"""
        return _read(lambda c: ld.list_mappings(c, model_id))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Saves a mapping {name, entity_type, columns {header: code}}"""
        return _write(lambda c: ld.save_mapping(c, g.user, model_id, data.get("name", ""), data.get("entity_type"),
                                                data.get("columns") or {}), "mapping.save", model_id, {"name": data.get("name")})


@blp.route("/models/<uuid:model_id>/column-mappings/<mapping_id>")
class Mapping(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, model_id, mapping_id):
        """Deletes a saved mapping"""
        return _write(lambda c: ld.delete_mapping(c, g.user, model_id, mapping_id), "mapping.delete", model_id, {"name": mapping_id})
