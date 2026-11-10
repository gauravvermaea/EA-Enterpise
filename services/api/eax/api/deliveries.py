"""Published import formats, deliveries and a model from a metamodel workbook (build phase 34 and 34.1, D370, D419, D462 to D468).

GET    /models/<m>/import-sources           the model's sources, the deliveries waiting for review, what you may do
POST   /models/<m>/import-sources           add a source {name, description, folder, values_win, contact, sender} (Model Admins)
PATCH  /import-sources/<s>                  change it {name, description, values_win, contact, sender, active}
POST   /import-sources/<s>/deliveries       deliver a file (multipart "file"; ?how=upload from the screens): previewed, waits
POST   /import-sources/<s>/collect          take what was dropped in the source's folder: one delivery each, previewed
POST   /loads/<l>/accept                    accept a delivery as your committed load (a task; Committers)
POST   /loads/<l>/decline                   decline it {note}
GET    /metamodel-workbooks/template        the metamodel workbook: empty, or ?model=<id> that model's metamodel (round trip)
POST   /metamodel-workbooks/preview         what a workbook would make (multipart "file", base): added, changed, errors
POST   /metamodel-workbooks                 make the model (multipart "file", name, base, description)

The empty templates of the Excel and CSV formats: POST /models/<m>/sheets {types, format, blank: true} (api/sheets.py).
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import deliveries as dv
from .. import loads as ld
from .. import metamodel_workbook as mw
from ..auth import require_auth
from ..metamodel_edit import EditError
from .models import Free, FreeIn
from .sheets import _model_of_load, _read, _task, _upload, _write

blp = Blueprint("deliveries", __name__, url_prefix="/api/v1", description="Import formats and deliveries (phase 34)")
SECURITY = [{"bearerAuth": []}]


def _preview(load: dict, model_id) -> dict:
    task = _task("load.preview", model_id, f"Preview of the delivery {load['file_name']}",
                 {"load": load["id"], "file": load["file_name"]})
    return task


@blp.route("/models/<uuid:model_id>/import-sources")
class Sources(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's import sources, with the deliveries waiting for review"""
        return _read(lambda c: dv.list_sources(c, g.user, model_id))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, model_id):
        """Adds an import source {name, description, folder, values_win, contact, sender} (Model Admins)"""
        return _write(lambda c: dv.save_source(c, g.user, model_id, data or {}), "import_source.added", model_id,
                      {"name": (data or {}).get("name")})


@blp.route("/import-sources/<source_id>")
class Source(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, source_id):
        """Changes an import source {name, description, values_win, contact, sender, active} (Model Admins)"""
        model = _read(lambda c: str(dv._source(c, source_id)["model_guid"]))
        return _write(lambda c: dv.save_source(c, g.user, model, data or {}, source_id), "import_source.changed", model,
                      {"source": source_id})


@blp.route("/import-sources/<source_id>/deliveries")
class Deliveries(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "how", "schema": {"type": "string"}}])
    @blp.response(202, Free)
    @require_auth()
    def post(self, source_id):
        """Delivers a file (multipart field file) in a published format: kept, previewed in the background, waiting for a
        person to accept it. A service account named as the source's sender, or anyone who may load into the model."""
        name, data = _upload()
        how = "upload" if request.args.get("how") == "upload" else "api"
        model = _read(lambda c: str(dv._source(c, source_id)["model_guid"]))
        load = _write(lambda c: dv.deliver(c, g.user, source_id, name, data, how), "delivery.received", model, {"name": name})
        return {"load": load, "task": _preview(load, model)}


@blp.route("/import-sources/<source_id>/collect")
class Collect(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, source_id):
        """Takes the files dropped in the source's folder: one delivery a workbook or file, one for a CSV set with
        master.csv; each previewed in the background"""
        model = _read(lambda c: str(dv._source(c, source_id)["model_guid"]))
        out = _write(lambda c: dv.collect(c, g.user, source_id), "delivery.collected", model, {"source": source_id})
        out["tasks"] = [_preview(x, model) for x in out["loads"]]
        return out


@blp.route("/loads/<load_id>/accept")
class Accept(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, load_id):
        """Accepts a delivery: its rows become your changes, committed at once as your load (a task; Committers)"""
        from .. import repository as repo
        model_id = _model_of_load(load_id)

        def check(c):
            r = ld._load(c, load_id)
            m = repo.get_model(c, model_id)
            if not r.get("source_id"):
                raise EditError("This load is not a delivery: add it as your own changes on the load page.", 409)
            if not dv.may_accept(c, g.user, m):
                raise EditError("Accepting a delivery commits it: it needs the Committer, Model Sub Admin or Model Admin role.", 403)
            if r["status"] != "previewed":
                raise EditError("This delivery was already accepted or declined, or its preview is not ready.", 409)
            return r
        r = _read(check)
        return {"task": _task("delivery.accept", model_id, f"Accept the delivery {r['file_name']}", {"load": load_id})}


@blp.route("/loads/<load_id>/decline")
class Decline(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, load_id):
        """Declines a delivery {note}: nothing in the model changes"""
        model_id = _model_of_load(load_id)
        return _write(lambda c: dv.decline(c, g.user, load_id, (data or {}).get("note") or ""), "delivery.declined", model_id,
                      {"load": load_id})


# ---------------------------------------------------------------- a model from a metamodel workbook (D419)
def _file(data: bytes, name: str) -> Response:
    safe = name.replace('"', "'")
    return Response(data, mimetype=mw.XLSX, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@blp.route("/metamodel-workbooks/template")
class WorkbookTemplate(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "model", "schema": {"type": "string"}}])
    @require_auth()
    def get(self):
        """The metamodel workbook: empty with its drop-downs, or ?model=<id> that model's metamodel in the same layout"""
        model = request.args.get("model") or None
        data, name = _read(lambda c: mw.template(c, model))
        return _file(data, name)


def _workbook_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        abort(400, message="Choose the metamodel workbook (.xlsx) to upload.")
    if not f.filename.lower().endswith((".xlsx", ".xlsm")):
        abort(400, message="A metamodel workbook is an Excel file (.xlsx): download the template to start from.")
    data = f.read()
    if not data:
        abort(400, message="The file is empty.")
    return data


@blp.route("/metamodel-workbooks/preview")
class WorkbookPreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self):
        """What a metamodel workbook would make (multipart file, base): counts, added, changed, errors and warnings"""
        data = _workbook_upload()
        base = request.form.get("base") or None
        return _read(lambda c: mw.preview(c, g.user, data, base))


@blp.route("/metamodel-workbooks")
class Workbooks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self):
        """Makes a project model from a metamodel workbook (multipart file, name, base, description): blank (on Root) or
        added to the base model's metamodel; you become its Model Admin"""
        data = _workbook_upload()
        form = request.form
        out = _write(lambda c: mw.create(c, g.user, data, form.get("name") or "", form.get("base") or None,
                                         form.get("description") or "", form.get("icon") or None),
                     "model.created", None, {"from": "metamodel workbook", "name": form.get("name"), "base": form.get("base")})
        m = out["model"]
        out["model"] = {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]}
        return out
