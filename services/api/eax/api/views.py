"""Views, business maps and report audiences (build phase 8.2, D161).

GET  /views                                  every view (built in VP-01 to VP-26, and the organisation's own)
POST /views                                  add your own (Library Admins)
PUT/DELETE /views/<code>                     change or delete your own (built-in ones are fixed)
GET  /models/<m>/views                       every view with how many of the model's entities it shows
GET  /models/<m>/views/<code>                the model through one view: elements, relationships, attributes
POST /models/<m>/views/render                the model through a view definition: the model's own views (D406), kept by the
                                             views service, are sent as they were opened (the picture is never stored)
GET  /models/<m>/maps/value-streams               the value stream map
GET  /models/<m>/maps/roadmap                     the roadmap of work packages, deliverables and plateaus
GET  /report-audiences                            who each report is for (D153)
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import repository as repo
from .. import views as vp
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn

blp = Blueprint("views", __name__, url_prefix="/api/v1",
                description="Views (VP-01 to VP-26 and your own), business maps and report audiences (phase 8.2)")
SECURITY = [{"bearerAuth": []}]


class ViewIn(Schema):
    code = fields.String(required=True, metadata={"description": "For example OVP-01; VP-<number> is kept for the built-in ones"})
    name = fields.String(required=True)
    category = fields.String(load_default="Organisation")
    purpose = fields.String(load_default="")
    concerns = fields.String(load_default="")
    stakeholders = fields.String(load_default="")
    element_types = fields.List(fields.String(), required=True, metadata={"description": "Entity type codes"})
    relationship_types = fields.List(fields.String(), load_default=list, metadata={"description": "Empty: every type"})
    heat_attribute = fields.String(load_default="Lifecycle")
    audiences = fields.List(fields.String(), load_default=list)


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, details: dict):
    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type="viewpoint", object_id=details.get("code", ""),
                         details=details, request_id=getattr(g, "request_id", None))
            trans.commit()
            return out
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


@blp.route("/views")
class Views(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every view: the 25 built in (ArchiMate 4, Appendix C) and the organisation's own"""
        return _read(lambda c: vp.list_views(c))

    @blp.doc(security=SECURITY)
    @blp.arguments(ViewIn)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def post(self, body):
        """Add one of the organisation's own views (Library Admins)"""
        return _write(lambda c: vp.save_view(c, body, g.user.username), "viewpoint.add", {"code": body["code"]})


@blp.route("/views/<string:code>")
class View(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, code):
        """One view"""
        return _read(lambda c: vp.get_view(c, code))

    @blp.doc(security=SECURITY)
    @blp.arguments(ViewIn)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def put(self, body, code):
        """Change one of the organisation's own views (built-in ones cannot be changed)"""
        return _write(lambda c: vp.save_view(c, body, g.user.username, code), "viewpoint.change", {"code": code})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def delete(self, code):
        """Delete one of the organisation's own views"""
        return _write(lambda c: vp.delete_view(c, code), "viewpoint.delete", {"code": code})


@blp.route("/models/<uuid:model_id>/views")
class ModelViews(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Every view with how many of this model's entities it shows"""
        return _read(lambda c: vp.list_views(c, model_id))


@blp.route("/models/<uuid:model_id>/views/render")
class RenderView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """The model through a view definition (the model's own view, D406): {name, element_types, relationship_types,
        heat_attribute, ...}; the same answer as a standard view's"""
        return _read(lambda c: vp.render(c, model_id, data))


@blp.route("/models/<uuid:model_id>/views/<string:code>")
class ModelView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, code):
        """The model through one view: elements with their values, relationships and the attributes to colour by"""
        return _read(lambda c: vp.model_view(c, model_id, code))


@blp.route("/models/<uuid:model_id>/maps/value-streams")
class ValueStreamMap(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Value streams, their stages in order and the capabilities that enable each stage"""
        return _read(lambda c: vp.value_stream_map(c, model_id))


@blp.route("/models/<uuid:model_id>/maps/roadmap")
class Roadmap(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Work packages, deliverables and plateaus with their dates and what they deliver"""
        return _read(lambda c: vp.roadmap(c, model_id))


@blp.route("/report-audiences")
class Audiences(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Who reports are for (CEO, CFO, architects...) and which reports each has (D153)"""
        return _read(lambda c: vp.audiences(c))
