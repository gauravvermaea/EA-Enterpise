"""Creating, copying and sharing models (build phase 4): new models and roots, copies (in the background),
archive and delete, the library (publish, withdraw, promote), packages (download, analyse, upload),
moving to a new framework version, and metamodel drafts (D115, D116-D121).

Writes go through eax.model_ops; the database decides who may do what (0006, 0008) and the checks here
give a clear message first. Every write is audited.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from decimal import Decimal

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import INCLUDE, Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit, permissions, reports
from .. import model_ops as mo
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .schemas import ModelOut

log = logging.getLogger(__name__)
blp = Blueprint("models", __name__, url_prefix="/api/v1",
                description="Create, copy and share models: roots, copies, the library, packages, framework versions, metamodel drafts")
SECURITY = [{"bearerAuth": []}]
EXPORT_DIR = "/data/exports"


def _plain(v):
    """JSON-ready: dates as ISO text, UUIDs and decimals as text, nested dicts and lists followed."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, (uuid.UUID, Decimal)):
        return str(v)
    return v


# api/tasks.py imports Free from here, so the task helpers are looked up when called, not at import (a cycle)
def start(*a, **k):
    from .tasks import start as _start
    return _start(*a, **k)


def upload(*a, **k):
    from .tasks import upload as _upload
    return _upload(*a, **k)


def waiting(*a, **k):
    from .tasks import waiting as _waiting
    return _waiting(*a, **k)


class Free(Schema):
    """A response whose shape varies (counts, findings, drafts): passed through as JSON. flask-smorest
    needs a Schema here; a bare marshmallow field has no dump() and every call would end in a 500."""

    def dump(self, obj, *, many=None):  # noqa: ARG002
        return _plain(obj)


class FreeIn(Schema):
    """A request body whose shape varies ({key: value} settings, a list of types...): every field passed through as
    sent. (Free is for answers: as a body it has no fields and refuses everything with 422.)"""

    class Meta:
        unknown = INCLUDE


class CreateIn(Schema):
    kind = fields.String(load_default="project", metadata={"description": "root, project or library (Library Admins)"})
    name = fields.String(required=True)
    source = fields.String(load_default=None, metadata={"description": "The model to start from (guid or name): a root "
                                                                          "metamodel, a library model or a model you may read"})
    parent = fields.String(load_default=None, metadata={"description": "Derive from (merge back into) this project model"})
    copy = fields.String(load_default=None, metadata={"description": "metamodel (no data) | content (with the data) | history "
                                                                     "(a deep copy: the data and its full history, D132). Default content; roots: metamodel"})
    version_label = fields.String(load_default="")
    industry = fields.String(load_default="")
    description = fields.String(load_default="")
    owner = fields.String(load_default="")
    framework = fields.String(load_default="", metadata={"description": "Roots: the framework's name (for example ArchiMate)"})
    wait = fields.Boolean(load_default=False, metadata={"description": "Copy the content in this request instead of in the background"})


class CreateOut(Schema):
    model = fields.Nested(ModelOut)
    copied = fields.Dict(metadata={"description": "Rows copied now, by kind"})
    job = fields.Integer(allow_none=True, metadata={"description": "The background job copying the content (GET /api/v1/jobs/<id>)"})


class PromoteIn(Schema):
    name = fields.String(load_default=None)
    copy = fields.String(load_default=None, metadata={"description": "metamodel, content (default) or history (deep copy)"})
    version_label = fields.String(load_default="1.0")
    industry = fields.String(load_default="")
    description = fields.String(load_default=None)
    owner = fields.String(load_default="")


class DeleteQuery(Schema):
    confirm = fields.String(required=True, metadata={"description": "The model's name, typed"})


class PackageQuery(Schema):
    format = fields.String(load_default="zip", metadata={"description": "zip (manifest, metamodel JSON, CSV) or xlsx (one workbook)"})
    content = fields.String(load_default="content", metadata={"description": "metamodel (no data), content (with the data) or history "
                                                                             "(deep: the data, its change history and the metamodel's history, D132)"})


class MoveIn(Schema):
    target = fields.String(required=True, metadata={"description": "The root metamodel to move to"})
    mode = fields.String(load_default="copy", metadata={"description": "copy (a new model) or in_place"})
    map = fields.Dict(load_default=None, metadata={"description": "Entity type code -> target type code (null: leave out)"})
    name = fields.String(load_default=None, metadata={"description": "copy: the new model's name"})
    with_data = fields.Boolean(load_default=True, metadata={"description": "copy: bring the content across (false: the target's metamodel only)"})


class MovePreviewQuery(Schema):
    target = fields.String(required=True)
    map = fields.String(load_default=None, metadata={"description": "JSON object: entity type code -> target type code"})


class DraftIn(Schema):
    class Meta:
        unknown = INCLUDE
    kind = fields.String(load_default="root", metadata={"description": "root (a new root metamodel) or changes (to target)"})
    name = fields.String(load_default=None)
    base = fields.String(load_default=None, metadata={"description": "root: start from a copy of this root"})
    target = fields.String(load_default=None, metadata={"description": "changes: the model they are for"})
    version = fields.String(load_default="")
    framework = fields.String(load_default="")
    note = fields.String(load_default="", metadata={"description": "What was asked for"})
    spec = fields.Dict(load_default=None, metadata={"description": "A whole metamodel document (eax-metamodel/1)"})


class DraftEditIn(Schema):
    action = fields.String(required=True, metadata={"description": "set, remove or replace"})
    section = fields.String(load_default=None, metadata={"description": "layers, pick_lists, attributes, entity_types, "
                                                                        "relationship_types, allowed or rules"})
    item = fields.Dict(load_default=None)
    code = fields.String(load_default=None, metadata={"description": "remove: the item's code (allowed and rules: its position)"})
    spec = fields.Dict(load_default=None, metadata={"description": "replace: the whole metamodel document"})


class DraftApplyIn(Schema):
    name = fields.String(load_default=None, metadata={"description": "root drafts: the new root's name"})
    version_label = fields.String(load_default=None)
    description = fields.String(load_default=None)
    create_model = fields.String(load_default=None, metadata={"description": "root drafts: also create a project model of this name"})
    remove_missing = fields.Boolean(load_default=False, metadata={"description": "changes drafts: retire what the draft leaves out"})


class RejectIn(Schema):
    reason = fields.String(load_default="")


class NoteIn(Schema):
    note = fields.String(load_default="", metadata={"description": "Shown to everyone on the draft as a comment"})


class CommentIn(Schema):
    body = fields.String(required=True)
    section = fields.String(load_default=None, metadata={"description": "On one item: its section (entity_types, ...)"})
    code = fields.String(load_default=None, metadata={"description": "On one item: its code"})


class ResolveIn(Schema):
    resolved = fields.Boolean(load_default=True)


class DraftQuery(Schema):
    status = fields.String(load_default=None, metadata={"description": "draft, applied or rejected"})


def _write(fn, action: str, object_id=None, details=None, status: int = 200):
    """Runs fn(conn) in one transaction as the signed-in person, audits it, and turns refusals into 4xx."""
    try:
        with get_engine().begin() as conn:
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(object_id or ""),
                         details=details or {}, request_id=getattr(g, "request_id", None))
        return out
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


def _start_copy(out: dict, wait: bool) -> dict:
    """Starts the background copy a create or promote asked for (or runs it now)."""
    c = out.pop("_copy", None)
    if not c:
        return out
    roles = list(g.user.roles)
    if not wait:
        try:
            from ..jobs import app as jobs_app
            from ..jobs import copy_model
            with jobs_app.open():
                out["job"] = copy_model.defer(source=c["source"], target=c["target"], actor=g.user.username, roles=roles,
                                              publish=bool(c.get("publish")))
            return out
        except Exception:  # no job runner reachable: copy in this request instead
            log.warning("job runner not reachable; copying in the request")
    out["copied"] = _write(lambda conn: mo.run_copy(conn, c["source"], c["target"], g.user.username, bool(c.get("publish"))),
                           "model.copied", c["target"], {"source": c["source"]})
    with get_engine().connect() as conn:
        out["model"] = repo.get_model(conn, c["target"])
    return out


def _user_can(permission: str) -> bool:
    return permissions.allowed(g.user.roles, permission)


@blp.route("/models")
class Models(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(CreateIn)
    @blp.response(201, CreateOut)
    @require_auth()
    def post(self, data):
        """Create a model: a root metamodel, a project model or a library model

        root: from Root (empty) or a copy of another root (Model Creators). project: from a root, a library
        model or any model you may read, with its metamodel only, its content, or its content and history;
        `parent` derives it from (merges it back into) a project model whose Model Admin you are. library: a
        reference model built from `source` (Library Admins), left editable until published. You become the
        new model's Model Admin. Copying content runs in the background (see `job`).
        """
        if data["kind"] == "library" and not _user_can("library.curate"):
            abort(403, message="Creating a library model needs the Library Admin role (D118).")
        wait = data.pop("wait")
        out = _write(lambda conn: mo.create_model(conn, g.user.username, data), "model.created", None,
                     {k: v for k, v in data.items() if v})
        return _start_copy(out, wait)


@blp.route("/models/<uuid:model_id>/archive")
class Archive(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, model_id):
        """Archive a model: read-only and hidden from lists by default (its Model Admin)"""
        return _write(lambda conn: mo.set_lifecycle(conn, model_id, True, g.user.username), "model.archived", model_id)


@blp.route("/models/<uuid:model_id>/reactivate")
class Reactivate(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, model_id):
        """Bring an archived model back (its Model Admin)"""
        return _write(lambda conn: mo.set_lifecycle(conn, model_id, False, g.user.username), "model.reactivated", model_id)


@blp.route("/models/<uuid:model_id>")
class DeleteModel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DeleteQuery, location="query")
    @blp.response(200, Free)
    @require_auth("models.delete")
    def delete(self, query, model_id):
        """Delete a model (Super Admins, D121)

        Type its name in `confirm`. A package of it is written to the exports folder first as its backup.
        Refused while other models are derived from it or built on it: archive it instead.
        """
        return _write(lambda conn: mo.delete_model(conn, model_id, query["confirm"], g.user.username, EXPORT_DIR),
                      "model.deleted", model_id)


# ---------------------------------------------------------------- publishing a draft model (D131, D134)
@blp.route("/models/<uuid:model_id>/publishing")
class Publishing(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """A model's publishing state, its steps so far (requested, sent back, approved) and what you may do next"""
        with get_engine().connect() as conn:
            try:
                return mo.publishing(conn, model_id, g.user)
            except repo.NotFound as exc:
                abort(404, message=str(exc))


# ---------------------------------------------------------------- reports (phase 5, D71, D137)
@blp.route("/models/<uuid:model_id>/reports")
class ModelReports(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's standard reports (dashboard links) and report catalogue: every entity type and
        attribute with the report view and column it is in (rpt.t_<type>), and which types count as
        applications, capabilities, ... for the standard reports"""
        with get_engine().connect() as conn:
            try:
                return reports.model_reports(conn, model_id)
            except repo.NotFound as exc:
                abort(404, message=str(exc))


def _publish_step(action: str, fn):
    def view(data, model_id):
        return _write(lambda conn: fn(conn, model_id, g.user.username, g.user, data.get("note", "")), action, model_id, data)
    return view


@blp.route("/models/<uuid:model_id>/request-publish")
class RequestPublish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, data, model_id):
        """Ask for a draft model to be published (its Model Admin); an approver then approves or sends it back"""
        return _publish_step("model.publish_requested", mo.request_publish)(data, model_id)


@blp.route("/models/<uuid:model_id>/publish")
class Publish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, data, model_id):
        """Approve a requested draft and publish it (D134): Library Admins for roots and library models (locked
        into the library); for a project model its Model Admins or those of the model it comes from"""
        return _publish_step("model.published", mo.publish)(data, model_id)


@blp.route("/models/<uuid:model_id>/send-back-publish")
class SendBackPublish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, data, model_id):
        """Send a requested draft back to its makers with a note (approvers)"""
        return _publish_step("model.publish_sent_back", mo.send_back_publish)(data, model_id)


@blp.route("/models/<uuid:model_id>/withdraw-publish-request")
class WithdrawPublishRequest(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, ModelOut)
    @require_auth()
    def post(self, data, model_id):
        """Take back a request to publish (the model's Model Admin)"""
        return _publish_step("model.publish_request_withdrawn", mo.withdraw_publish_request)(data, model_id)


@blp.route("/models/<uuid:model_id>/withdraw")
class Withdraw(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth("library.curate")
    def post(self, model_id):
        """Withdraw a library model: gone from the library, kept for the models built on it (Library Admins)"""
        return _write(lambda conn: mo.withdraw(conn, model_id, g.user.username), "library.withdrawn", model_id)


@blp.route("/models/<uuid:model_id>/restore")
class Restore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth("library.curate")
    def post(self, model_id):
        """Put a withdrawn library model back in the library (Library Admins)"""
        return _write(lambda conn: mo.withdraw(conn, model_id, g.user.username, restore=True), "library.restored", model_id)


@blp.route("/models/<uuid:model_id>/promote")
class Promote(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(PromoteIn)
    @blp.response(201, Free)
    @require_auth("library.curate")
    def post(self, data, model_id):
        """Promote a model into the library (Library Admins, D118)

        A copy of it (metamodel and content) becomes a published library model; a root makes a root.
        The model itself carries on as it is.
        """
        if not waiting():   # D273: the promotion and its copy in the background
            return start("library.promoted", model_id, f"Promote into the library as '{data.get('name') or 'a library model'}'",
                         data, "#/library")
        out = _write(lambda conn: mo.promote(conn, model_id, data, g.user.username), "library.promoted", model_id, data)
        return _start_copy(out, False)


@blp.route("/models/<uuid:model_id>/package")
class Package(MethodView):
    @blp.doc(security=SECURITY, responses={"200": {"description": "The package file"}})
    @blp.arguments(PackageQuery, location="query")
    @require_auth()
    def get(self, query, model_id):
        """Download a model as a package (D116): a zip (manifest.json, metamodel.json, one CSV per entity type,
        relationships.csv) or one Excel workbook. Change it and upload it again, here or elsewhere."""
        fmt = "xlsx" if query["format"] == "xlsx" else "zip"
        if request.args.get("background") == "true":   # D273: made in the background, downloaded from the task
            return start("model.downloaded", model_id, f"Download the model package ({fmt}, {query['content']})",
                         {"format": fmt, "content": query["content"]}, f"#/metamodel/{model_id}")
        try:
            with get_engine().connect() as conn:
                data, filename, ctype = mo.export_package(conn, model_id, fmt, g.user.username, query["content"])
        except repo.NotFound as exc:
            abort(404, message=str(exc))
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="model.downloaded", object_type="model", object_id=str(model_id),
                         details={"format": fmt, "content": query["content"]}, request_id=getattr(g, "request_id", None))
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@blp.route("/models/<uuid:model_id>/metamodel-spec")
class Spec(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """A model's metamodel as one JSON document (eax-metamodel/1), as packages and drafts use it"""
        with get_engine().connect() as conn:
            try:
                return mo.metamodel_spec(conn, model_id)
            except repo.NotFound as exc:
                abort(404, message=str(exc))


def _uploaded() -> dict:
    f = request.files.get("file")
    if f is None:
        abort(400, message="Send the package as the form field 'file'.")
    try:
        return mo.read_package(f.read(), f.filename or "")
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except Exception as exc:  # a damaged file
        abort(400, message=f"The file could not be read as a package: {exc}")


@blp.route("/packages/analyse")
class Analyse(MethodView):
    @blp.doc(security=SECURITY, requestBody={"content": {"multipart/form-data": {"schema": {
        "type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}}}})
    @blp.response(200, Free)
    @require_auth()
    def post(self):
        """Look at a package before uploading it (D108): what it holds, its checks, and where it can go:
        under its root metamodel (found by name and version, and matching it completely) or under Root
        as a root of its own. In the background (D273): the answer is a task; ?wait=true checks it in the request"""
        if not waiting():
            f = upload()
            return start("package.analyse", None, f"Check the package {f[0]}", {}, "#/metamodel", [f])
        pkg = _uploaded()
        with get_engine().connect() as conn:
            return mo.analyse_package(conn, pkg)


@blp.route("/packages/import")
class Import(MethodView):
    @blp.doc(security=SECURITY, requestBody={"content": {"multipart/form-data": {"schema": {
        "type": "object", "properties": {"file": {"type": "string", "format": "binary"},
                                         "placement": {"type": "string", "enum": ["root", "own_root"]},
                                         "root": {"type": "string", "description": "placement root: the root metamodel (id)"},
                                         "content": {"type": "string", "enum": ["metamodel", "content", "history"],
                                                     "description": "what to load (default: everything the package has)"},
                                         "name": {"type": "string"}, "as_kind": {"type": "string", "enum": ["library", "project"]}}}}}})
    @blp.response(201, Free)
    @require_auth()
    def post(self):
        """Upload a package (D108): placement root (under the root metamodel `root`, which it must match completely) or own_root (its metamodel
        becomes a root of its own under Root). as_kind library (Library Admins) or project (Model Creators)."""
        pkg = _uploaded()
        placement = request.form.get("placement") or "root"
        as_kind = request.form.get("as_kind") or None
        kind = pkg["manifest"].get("model", {}).get("kind")
        wants_library = as_kind == "library" or (as_kind is None and kind == "reference")
        if wants_library and not _user_can("library.curate"):
            abort(403, message="Uploading into the library needs the Library Admin role (D118); upload it as a project model.")
        if not wants_library and not (_user_can("models.create") or _user_can("library.curate")):
            abort(403, message="Uploading a model needs the Model Creator role.")
        if not waiting():   # D273: loaded in the background
            f = upload()
            return start("package.uploaded", None, f"Upload the package {f[0]}",
                         {"placement": placement, "as_kind": as_kind, "name": request.form.get("name") or None,
                          "root": request.form.get("root") or None, "content": request.form.get("content") or None},
                         "#/metamodel", [f])
        out = _write(lambda conn: mo.import_package(conn, pkg, placement, g.user.username, request.form.get("name") or None,
                                                    as_kind, request.form.get("root") or None, request.form.get("content") or None),
                     "package.uploaded", None,
                     {"package": pkg["manifest"].get("model", {}).get("name"), "placement": placement})
        return {"model": repo_model_out(out["model"]), "root": repo_model_out(out.get("root")), "counts": out["counts"]}


def repo_model_out(m):
    return None if m is None else {k: v for k, v in m.items() if not k.startswith("_")}


@blp.route("/models/<uuid:model_id>/framework-preview")
class MovePreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(MovePreviewQuery, location="query")
    @blp.response(200, Free)
    @require_auth()
    def get(self, query, model_id):
        """What moving the model to another root metamodel (a new framework version) would do: each entity type
        and the type it maps to, and what would be left out"""
        tmap = json.loads(query["map"]) if query.get("map") else None
        with get_engine().connect() as conn:
            try:
                return mo.framework_preview(conn, model_id, query["target"], tmap)
            except EditError as exc:
                abort(exc.status, message=str(exc))
            except repo.NotFound as exc:
                abort(404, message=str(exc))


@blp.route("/models/<uuid:model_id>/framework-move")
class Move(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(MoveIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Move the model to another root metamodel (D121): copy (a new model, the content mapped across) or
        in_place (the model takes the new metamodel as one version; its Model Admin). In the background (D273)"""
        if not waiting():
            return start("model.framework_moved", model_id, f"Move the model to another framework ({data['mode']})", data,
                         f"#/metamodel/{model_id}")
        out = _write(lambda conn: mo.framework_move(conn, model_id, data["target"], data["mode"], g.user.username, data.get("map"),
                                                    data.get("name"), data.get("with_data", True)), "model.framework_moved", model_id, data)
        out["model"] = repo_model_out(out["model"])
        return out


# ---------------------------------------------------------------- metamodel drafts (D115, D120)

@blp.route("/metamodel-drafts")
class Drafts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DraftQuery, location="query")
    @blp.response(200, Free(many=True))
    @require_auth()
    def get(self, query):
        """Your metamodel drafts, and drafts of changes to models you are Model Admin of"""
        with get_engine().connect() as conn:
            return mo.draft_list(conn, g.user, query["status"])

    @blp.doc(security=SECURITY)
    @blp.arguments(DraftIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """Start a metamodel draft: a new root (empty, or from a copy of `base`) or changes to `target`; give
        `spec` to upload a whole metamodel document at once"""
        via = "upload" if data.get("spec") else "screen"
        return _write(lambda conn: mo.draft_create(conn, g.user, data, via), "draft.created", None,
                      {"name": data.get("name"), "kind": data.get("kind")})


@blp.route("/metamodel-drafts/<uuid:draft_id>")
class Draft(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, draft_id):
        """A draft: its metamodel, its checks, and what it changes against the model it starts from"""
        with get_engine().connect() as conn:
            try:
                return mo.draft_get(conn, g.user, draft_id)
            except EditError as exc:
                abort(exc.status, message=str(exc))


@blp.route("/metamodel-drafts/<uuid:draft_id>/edit")
class DraftEdit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DraftEditIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Change a draft: set or remove one item, or replace the whole document; it is checked again"""
        return _write(lambda conn: mo.draft_edit(conn, g.user, draft_id, data["action"], data.get("section"), data.get("item"),
                                                 data.get("code"), data.get("spec")), "draft.changed", draft_id,
                      {"action": data["action"], "section": data.get("section")})


@blp.route("/metamodel-drafts/<uuid:draft_id>/apply")
class DraftApply(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DraftApplyIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Apply a reviewed draft (D115): a new root metamodel (and optionally a model from it), or one new
        metamodel version of the model it changes. In the background (D273)"""
        if not waiting():
            return start("draft.applied", None, "Apply a metamodel draft", {"draft": str(draft_id), "data": data},
                         "#/metamodel/drafts")
        out = _write(lambda conn: mo.draft_apply(conn, g.user, draft_id, g.user.username, data), "draft.applied", draft_id, data)
        out["model"] = repo_model_out(out["model"])
        if out.get("created"):
            out["created"] = repo_model_out(out["created"])
        return out


@blp.route("/metamodel-drafts/<uuid:draft_id>/reject")
class DraftReject(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(RejectIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Reject a draft (from waiting for review or sent back); it is kept, and can be reopened as a new round"""
        return _write(lambda conn: mo.draft_reject(conn, g.user, draft_id, g.user.username, data["reason"]), "draft.rejected",
                      draft_id, data)


# Review rounds (D130): send back for changes, resubmit, reopen, and comments on the draft or its items
def _round(action: str, fn):
    def view(data, draft_id):
        return _write(lambda conn: fn(conn, g.user, draft_id, g.user.username, data.get("note", "")), action, draft_id, data)
    return view


@blp.route("/metamodel-drafts/<uuid:draft_id>/send-back")
class DraftSendBack(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Send a draft back to its maker for changes (reviewers): it becomes editable, with your note and comments"""
        return _round("draft.sent_back", mo.draft_send_back)(data, draft_id)


@blp.route("/metamodel-drafts/<uuid:draft_id>/resubmit")
class DraftResubmit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Send a fixed draft back for review: a new round"""
        return _round("draft.resubmitted", mo.draft_resubmit)(data, draft_id)


@blp.route("/metamodel-drafts/<uuid:draft_id>/reopen")
class DraftReopen(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Open a rejected draft again for changes, as a new round"""
        return _round("draft.reopened", mo.draft_reopen)(data, draft_id)


@blp.route("/metamodel-drafts/<uuid:draft_id>/comments")
class DraftComments(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(CommentIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, draft_id):
        """Comment on a draft, or on one of its items (section and code)"""
        return _write(lambda conn: mo.draft_comment(conn, g.user, draft_id, data["body"], data.get("section"), data.get("code")),
                      "draft.commented", draft_id, {"section": data.get("section"), "code": data.get("code")})


@blp.route("/metamodel-drafts/<uuid:draft_id>/comments/<uuid:comment_id>/resolve")
class DraftCommentResolve(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(ResolveIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, draft_id, comment_id):
        """Mark a comment fixed (resolved true) or open again (false)"""
        return _write(lambda conn: mo.draft_resolve_comment(conn, g.user, draft_id, comment_id, data["resolved"]),
                      "draft.comment_resolved", draft_id, {"comment": str(comment_id), "resolved": data["resolved"]})

