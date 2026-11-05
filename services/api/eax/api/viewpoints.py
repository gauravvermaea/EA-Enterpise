"""Viewpoints, business maps and report audiences (build phase 8.2, D161).

GET  /viewpoints                                  every viewpoint (built in VP-01 to VP-26, and the organisation's own)
POST /viewpoints                                  add your own (Library Admins)
PUT/DELETE /viewpoints/<code>                     change or delete your own (built-in ones are fixed)
GET  /models/<m>/viewpoints                       every viewpoint with how many of the model's entities it shows
GET  /models/<m>/viewpoints/<code>                the model through one viewpoint: elements, relationships, attributes
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
from .. import viewpoints as vp
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free

blp = Blueprint("viewpoints", __name__, url_prefix="/api/v1",
                description="Viewpoints (VP-01 to VP-26 and your own), business maps and report audiences (phase 8.2)")
SECURITY = [{"bearerAuth": []}]


class ViewpointIn(Schema):
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


@blp.route("/viewpoints")
class Viewpoints(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every viewpoint: the 25 built in (ArchiMate 4, Appendix C) and the organisation's own"""
        return _read(lambda c: vp.list_viewpoints(c))

    @blp.doc(security=SECURITY)
    @blp.arguments(ViewpointIn)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def post(self, body):
        """Add one of the organisation's own viewpoints (Library Admins)"""
        return _write(lambda c: vp.save_viewpoint(c, body, g.user.username), "viewpoint.add", {"code": body["code"]})


@blp.route("/viewpoints/<string:code>")
class Viewpoint(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, code):
        """One viewpoint"""
        return _read(lambda c: vp.get_viewpoint(c, code))

    @blp.doc(security=SECURITY)
    @blp.arguments(ViewpointIn)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def put(self, body, code):
        """Change one of the organisation's own viewpoints (built-in ones cannot be changed)"""
        return _write(lambda c: vp.save_viewpoint(c, body, g.user.username, code), "viewpoint.change", {"code": code})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def delete(self, code):
        """Delete one of the organisation's own viewpoints"""
        return _write(lambda c: vp.delete_viewpoint(c, code), "viewpoint.delete", {"code": code})


@blp.route("/models/<uuid:model_id>/viewpoints")
class ModelViewpoints(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Every viewpoint with how many of this model's entities it shows"""
        return _read(lambda c: vp.list_viewpoints(c, model_id))


@blp.route("/models/<uuid:model_id>/viewpoints/<string:code>")
class ModelViewpoint(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, code):
        """The model through one viewpoint: elements with their values, relationships and the attributes to colour by"""
        return _read(lambda c: vp.model_viewpoint(c, model_id, code))


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
