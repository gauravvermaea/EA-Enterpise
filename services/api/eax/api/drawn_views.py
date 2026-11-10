"""Drawn views in draw.io (phases 28 and 29; D354, D387 to D402).

The drawn views themselves (list, open, save, versions, rename, remove) and a model's own view definitions are the views
service's (/api/views/v1, its own database, D405). Here, what needs the model's data:

GET    /models/<m>/drawn-views/access                       for the views service: may this person draw, and the model's last change
POST   /models/<m>/drawn-views/check                        for the views service: a view's objects are the model's own {entities, relationships}
GET    /models/<m>/tags/<t>/drawn-views/<v>                 a view as a tag keeps it (read only)
GET    /models/<m>/drawn-views/setup[?view=]                  the plugin's setup message: types, allowed, lines, read only, icons
POST   /models/<m>/drawn-views/resync                       what is current for the objects on a view {view? | xml?}
POST   /models/<m>/drawn-views/change                       a change made on the view, in the model at once and committed (D413)
                                                            {op, args, view_name?, message?}
POST   /models/<m>/drawn-views/commit                       commit the person's uncommitted changes {changes?, message?} (D413)
POST   /models/<m>/drawn-views/relationships-of             an entity's relationships with objects on the view {entity, others}
GET    /models/<m>/drawn-views/allowed?source=&target=      the relationship types allowed between two entities (or types)
POST   /models/<m>/drawn-views/generate                     the xml of a view of chosen entities {entities, include_relationships?}
GET    /models/<m>/heat-map?attribute=&ranges=              each entity's colour by one attribute, with the legend
GET    /models/<m>/entities/<e>/icon                        the entity's own icon
POST   /models/<m>/entities/<e>/icon                        set it (multipart file "file", SVG or PNG, at most 64 KB)
DELETE /models/<m>/entities/<e>/icon                        remove it
GET    /projects/<p>/view-evidence                          the drawn views the project uses as evidence
POST   /projects/<p>/view-evidence                          one more, a link only (D408) {model, view, version?, item | question, note?}
DELETE /projects/<p>/view-evidence/<id>                     no longer evidence
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import drawn_views as dv
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn

blp = Blueprint("drawn_views", __name__, url_prefix="/api/v1",
                description="Drawn views in draw.io: files, versions, resync, icons, heat maps, evidence (phases 28 and 29)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except EditError as exc:
        abort(exc.status, message=str(exc))


def _write(fn, action: str, object_id: str, details: dict | None = None):
    try:
        with get_engine().begin() as conn:
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type="drawn_view", object_id=str(object_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
        return out
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


def _project(fn, action: str | None = None, obj: str = "", details: dict | None = None):
    """A project's evidence: the projects' connection, the repository's beside it (D266)."""
    from .. import projects as pj
    try:
        with pj.connections(bool(action)) as conn:
            out = fn(conn)
            if action:
                audit.record(pj.core(conn), actor=g.user.username, action=action, object_type="project", object_id=str(obj),
                             details=details or {}, request_id=getattr(g, "request_id", None))
            return out
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except EditError as exc:
        abort(exc.status, message=str(exc))


@blp.route("/models/<uuid:model_id>/drawn-views/access")
class Access(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """For the views service (D405): the model as you see it, whether you may draw its views (and why not), and its last
        content change {id, name, may_draw, read_only_reason, marker}"""
        return _read(lambda c: dv.access(c, model_id, g.user))


@blp.route("/models/<uuid:model_id>/drawn-views/check")
class Check(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """For the views service: a view's objects are the model's own entities and relationships (D354) {entities,
        relationships}; 400 when not; else how many are missing or deleted"""
        return _read(lambda c: dv.check(c, model_id, data.get("entities") or [], data.get("relationships") or []))


@blp.route("/models/<uuid:model_id>/tags/<string:tag>/drawn-views/<string:view>")
class TagView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, tag, view):
        """A drawn view as a tag keeps it (read only): its file at its last version, or ?version=n"""
        from .. import tags
        return _read(lambda c: tags.tag_drawn_view(c, model_id, tag, view))


@blp.route("/models/<uuid:model_id>/drawn-views/setup")
class Setup(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The draw.io plugin's setup message for this model (and ?view=, the own icons of its entities): types with
        their looks, the allowed relationships, the relationship lines, and readOnly for someone who may not draw"""
        return _read(lambda c: dv.setup(c, model_id, g.user, request.args.get("view") or None))


@blp.route("/models/<uuid:model_id>/drawn-views/resync")
class Resync(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """What is current for the objects on a view ({view} or {xml}): entities (name, type, look, icon, deleted),
        relationships among them (committed, or yours uncommitted), new ones and gone ones"""
        return _read(lambda c: dv.resync(c, model_id, g.user, data.get("view"), data.get("xml")))


@blp.route("/models/<uuid:model_id>/drawn-views/pending")
class Pending(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Your uncommitted changes to the relationships and junctions on one view ({targets: their ids}): what the
        view's Commit button commits through /changes/commit (or asks for through /changes/request), with
        may_commit (D412)"""
        return _read(lambda c: dv.view_pending(c, model_id, g.user, data.get("targets") or []))


@blp.route("/models/<uuid:model_id>/drawn-views/change")
class ChangeNow(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, data, model_id):
        """A change made on a drawn view {op, args, view_name?, message?}: in the model at once and committed as you (D413).
        Relationships (relationship.create, .rename, .delete) and junctions: anyone who may change the model; entities
        (entity.create, entity.update): the model's committers only (403 otherwise)"""
        op = data.get("op") or ""
        return _write(lambda c: dv.change_now(c, model_id, g.user, op, data.get("args") or {}, data.get("view_name") or "",
                                              data.get("message") or ""), f"drawn_view.{op}", model_id,
                      {"op": op, "view": data.get("view_name") or ""})


@blp.route("/models/<uuid:model_id>/drawn-views/commit")
class CommitMine(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, data, model_id):
        """Commit your uncommitted changes from a drawn view's Uncommitted changes panel {changes?: ids, message?} (D413):
        relationships and junctions need no committer; anything else does"""
        return _write(lambda c: dv.commit_mine(c, model_id, g.user, data.get("changes") or None, data.get("message") or ""),
                      "drawn_view.commit", model_id, {"changes": len(data.get("changes") or [])})


@blp.route("/models/<uuid:model_id>/drawn-views/relationships-of")
class RelationshipsOf(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """When an entity is placed {entity, others}: the entity (look, icon) and its relationships with the others"""
        return _read(lambda c: dv.relationships_of(c, model_id, g.user, data.get("entity") or "", data.get("others") or []))


@blp.route("/models/<uuid:model_id>/drawn-views/allowed")
class Allowed(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The relationship types allowed from source to target (entity ids, or type codes), with multiplicity; through a
        junction, only those its rules leave (D397)"""
        return _read(lambda c: dv.allowed_between(c, model_id, request.args.get("source", ""), request.args.get("target", "")))


@blp.route("/models/<uuid:model_id>/drawn-views/generate")
class Generate(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """The draw.io file of a view of chosen entities, laid out by domain {entities, include_relationships}"""
        return _read(lambda c: {"xml": dv.generate(c, model_id, g.user, data.get("entities") or [],
                                                   data.get("include_relationships", True))})


@blp.route("/models/<uuid:model_id>/heat-map")
class HeatMap(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Each entity's colour by one attribute (?attribute=), pick-list values or number ranges (?ranges=0-10,10-20 or
        five equal bands), with the legend"""
        ranges = None
        if request.args.get("ranges"):
            try:
                ranges = [tuple(float(x) for x in r.split(":")) for r in request.args["ranges"].split(",")]
            except ValueError:
                abort(400, message="ranges: from:to pairs with commas, e.g. 0:10,10:20")
        return _read(lambda c: dv.heat_map(c, model_id, request.args.get("attribute", ""), ranges))


@blp.route("/models/<uuid:model_id>/entities/<string:entity>/icon")
class EntityIcon(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id, entity):
        """The entity's own icon (SVG or PNG); 404 when it has none"""
        got = _read(lambda c: dv.get_icon(c, model_id, entity))
        if not got:
            abort(404, message="This entity shows its type's icon.")
        ctype, content = got
        return Response(content, mimetype=ctype, headers={"Cache-Control": "private, max-age=60",
                                                          "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                                                          "X-Content-Type-Options": "nosniff"})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, model_id, entity):
        """Set the entity's own icon: a multipart file "file", SVG or PNG, at most 64 KB (an SVG with scripts, links,
        styles or embedded content is refused)"""
        f = request.files.get("file")
        content = f.read() if f else request.get_data()
        name, ctype = (f.filename, f.mimetype) if f else ("", request.mimetype or "")
        return _write(lambda c: dv.set_icon(c, model_id, g.user, entity, content, name, ctype), "entity.icon", entity)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.content")
    def delete(self, model_id, entity):
        """Remove the entity's own icon (its type's icon shows again)"""
        return _write(lambda c: dv.remove_icon(c, model_id, g.user, entity), "entity.icon_remove", entity)


@blp.route("/projects/<string:project>/view-evidence")
class Evidence(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The drawn views the project uses as evidence: for which deliverable or key question, the live view or which version"""
        return _project(lambda c: dv.evidence(c, project, g.user))

    @blp.doc(security=SECURITY)
    @blp.response(201, Free)
    @require_auth()
    def post(self, project):
        """A drawn view as evidence, a link only (D408): model, view, version (none: the live view), item (a deliverable) or
        question (a key question), note"""
        data = request.get_json(silent=True) or dict(request.form)
        return _project(lambda c: dv.add_evidence(c, project, g.user, data),
                        "drawn_view.evidence", project, {k: data.get(k) for k in ("model", "view", "version", "item", "question")})


@blp.route("/projects/<string:project>/view-evidence/<string:evidence>")
class OneEvidence(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, project, evidence):
        """No longer evidence"""
        return _project(lambda c: dv.remove_evidence(c, project, g.user, evidence), "drawn_view.evidence_remove", project)
