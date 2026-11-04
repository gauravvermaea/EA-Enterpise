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

from .. import audit, permissions
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


class Free(Schema):
    """A response whose shape varies (counts, findings, drafts): passed through as JSON. flask-smorest
    needs a Schema here; a bare marshmallow field has no dump() and every call would end in a 500."""

    def dump(self, obj, *, many=None):  # noqa: ARG002
        return _plain(obj)


class CreateIn(Schema):
    kind = fields.String(load_default="project", metadata={"description": "root, project or library (Library Admins)"})
    name = fields.String(required=True)
    source = fields.String(load_default=None, metadata={"description": "The model to start from (guid or name): a root "
                                                                          "metamodel, a library model or a model you may read"})
    parent = fields.String(load_default=None, metadata={"description": "Derive from (merge back into) this project model"})
    copy = fields.String(load_default=None, metadata={"description": "metadata | content | history (default content; roots: metamodel)"})
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
    version_label = fields.String(load_default="1.0")
    industry = fields.String(load_default="")
    description = fields.String(load_default=None)
    owner = fields.String(load_default="")


class DeleteQuery(Schema):
    confirm = fields.String(required=True, metadata={"description": "The model's name, typed"})


class PackageQuery(Schema):
    format = fields.String(load_default="zip", metadata={"description": "zip (manifest, metamodel JSON, CSV) or xlsx (one workbook)"})


class MoveIn(Schema):
    target = fields.String(required=True, metadata={"description": "The root metamodel to move to"})
    mode = fields.String(load_default="copy", metadata={"description": "copy (a new model) or in_place"})
    map = fields.Dict(load_default=None, metadata={"description": "Entity type code -> target type code (null: leave out)"})
    name = fields.String(load_default=None, metadata={"description": "copy: the new model's name"})


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


@blp.route("/models/<uuid:model_id>/publish")
class Publish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth("library.curate")
    def post(self, model_id):
        """Publish a root or library model into the library: it is locked (Library Admins, D118)"""
        return _write(lambda conn: mo.publish(conn, model_id, g.user.username), "library.published", model_id)


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
    @blp.response(201, CreateOut)
    @require_auth("library.curate")
    def post(self, data, model_id):
        """Promote a model into the library (Library Admins, D118)

        A copy of it (metamodel and content) becomes a published library model; a root makes a root.
        The model itself carries on as it is.
        """
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
        try:
            with get_engine().connect() as conn:
                data, filename, ctype = mo.export_package(conn, model_id, fmt, g.user.username)
        except repo.NotFound as exc:
            abort(404, message=str(exc))
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="model.downloaded", object_type="model", object_id=str(model_id),
                         details={"format": fmt}, request_id=getattr(g, "request_id", None))
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
        as a root of its own"""
        pkg = _uploaded()
        with get_engine().connect() as conn:
            return mo.analyse_package(conn, pkg)


@blp.route("/packages/import")
class Import(MethodView):
    @blp.doc(security=SECURITY, requestBody={"content": {"multipart/form-data": {"schema": {
        "type": "object", "properties": {"file": {"type": "string", "format": "binary"},
                                         "placement": {"type": "string", "enum": ["root", "own_root"]},
                                         "root": {"type": "string", "description": "placement root: the root metamodel (id)"},
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
        out = _write(lambda conn: mo.import_package(conn, pkg, placement, g.user.username, request.form.get("name") or None,
                                                    as_kind, request.form.get("root") or None), "package.uploaded", None,
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
        in_place (the model takes the new metamodel as one version; its Model Admin)"""
        out = _write(lambda conn: mo.framework_move(conn, model_id, data["target"], data["mode"], g.user.username, data.get("map"),
                                                    data.get("name")), "model.framework_moved", model_id, data)
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
        metamodel version of the model it changes"""
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
        """Reject a draft; it is kept for the record"""
        return _write(lambda conn: mo.draft_reject(conn, g.user, draft_id, g.user.username, data["reason"]), "draft.rejected",
                      draft_id, data)
