"""Data entry (build phase 6): forms, entities, values, relationships, retire and restore, delete, roll back,
and the data entry page by entity type (D79).

Writes go through eax.content in one transaction as the signed-in person; the database decides who may
change what (Architects, Model Sub Admins and Model Admins on the model). Every write is audited.
Validation rules warn, never block (D48); relationships outside the metamodel need allow_outside (D49).
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import INCLUDE, Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import content as ct
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free

blp = Blueprint("content", __name__, url_prefix="/api/v1/models",
                description="Data entry: create and change entities, their values and relationships (phase 6)")
SECURITY = [{"bearerAuth": []}]


class EntityIn(Schema):
    class Meta:
        unknown = INCLUDE
    entity_type = fields.String(metadata={"description": "The entity type (guid, code or name); new entities only"})
    name = fields.String()
    description = fields.String(allow_none=True)
    parent = fields.String(allow_none=True, metadata={"description": "The entity this one is part of (guid, display ID or name); empty: none"})
    tags = fields.Raw(allow_none=True, metadata={"description": "A list of tags, or one text with commas"})
    display_id = fields.String(allow_none=True, metadata={"description": "Leave empty for the next number"})
    values = fields.Dict(keys=fields.String(), allow_none=True, metadata={"description": "Attribute code: value; empty clears it"})
    row_version = fields.Integer(allow_none=True, metadata={"description": "The version you opened; refused if someone saved since"})


class RelationshipIn(Schema):
    source = fields.String(required=True)
    target = fields.String(required=True)
    relationship_type = fields.String(required=True)
    name = fields.String(load_default="")
    allow_outside = fields.Boolean(load_default=False, metadata={"description": "Add it although the metamodel does not "
                                                                               "allow it: the metamodel gets the mapping, flagged (D49)"})


class RollBackIn(Schema):
    event = fields.Integer(required=True, metadata={"description": "A history event id (GET .../history)"})


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, model_id, details=None, status: int = 200):
    try:
        with get_engine().begin() as conn:
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(model_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
        return out
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


@blp.route("/<uuid:model_id>/forms/<string:entity_type>")
class Form(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_type):
        """The form for one entity type: built-in fields, attributes by section (data type, unit, required,
        pick-list values) and the type's rules"""
        return _read(lambda c: ct.form(c, model_id, entity_type))


@blp.route("/<uuid:model_id>/entry/<string:entity_type>")
class Entry(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_type):
        """The data entry page for one type (D79): its columns and every entity with values, tags and warnings"""
        return _read(lambda c: ct.entry_table(c, model_id, entity_type))


@blp.route("/<uuid:model_id>/entity-picker")
class Picker(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Existing entities to relate to or pick as a parent: ?q=text&type=<entity type>&type=..."""
        return _read(lambda c: ct.find_entities(c, model_id, request.args.get("q", ""), request.args.getlist("type"),
                                                 int(request.args.get("limit", 50))))


@blp.route("/<uuid:model_id>/content/entities")
class Entities(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(EntityIn)
    @blp.response(201, Free)
    @require_auth("model.content")
    def post(self, data, model_id):
        """Create an entity: entity_type, name, description, parent, tags, values. The answer is the saved
        entity with saved_warnings (rules it fails; it is saved anyway, D48)"""
        return _write(lambda c: ct.create_entity(c, model_id, data, g.user.username), "entity.create", model_id,
                      {"name": data.get("name"), "type": data.get("entity_type")})


@blp.route("/<uuid:model_id>/content/entities/<string:entity_id>")
class Entity(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(EntityIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def patch(self, data, model_id, entity_id):
        """Change an entity's fields, tags and values (only those given)"""
        return _write(lambda c: ct.update_entity(c, model_id, entity_id, data, g.user.username), "entity.update", model_id,
                      {"entity": entity_id, "fields": sorted(k for k in data if k != "values"),
                       "values": sorted((data.get("values") or {}).keys())})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.content")
    def delete(self, model_id, entity_id):
        """Delete an entity with its values and relationships (kept in its history)"""
        return _write(lambda c: ct.delete_entity(c, model_id, entity_id), "entity.delete", model_id, {"entity": entity_id})


@blp.route("/<uuid:model_id>/content/entities/<string:entity_id>/<any(retire,restore):action>")
class Status(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, model_id, entity_id, action):
        """Retire an entity (kept, marked retired) or restore it"""
        return _write(lambda c: ct.set_status(c, model_id, entity_id, "retired" if action == "retire" else "published"),
                      f"entity.{action}", model_id, {"entity": entity_id})


@blp.route("/<uuid:model_id>/content/entities/<string:entity_id>/roll-back")
class RollBack(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(RollBackIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, data, model_id, entity_id):
        """Set an entity back to a point in its history (a new version; the history keeps everything)"""
        return _write(lambda c: ct.roll_back(c, model_id, entity_id, data["event"], g.user.username), "entity.roll_back",
                      model_id, {"entity": entity_id, "event": data["event"]})


@blp.route("/<uuid:model_id>/content/entities/<string:entity_id>/relationship-options")
class Options(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_id):
        """What this entity may be related to (allowed by the metamodel), and every relationship and entity type"""
        return _read(lambda c: ct.relationship_options(c, model_id, entity_id))


@blp.route("/<uuid:model_id>/content/relationships")
class Relationships(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(RelationshipIn)
    @blp.response(201, Free)
    @require_auth("model.content")
    def post(self, data, model_id):
        """Relate two existing entities. Outside the metamodel: 409 unless allow_outside (D49)"""
        return _write(lambda c: ct.add_relationship(c, model_id, data, g.user.username), "relationship.create", model_id,
                      {k: data.get(k) for k in ("source", "target", "relationship_type", "allow_outside")})


@blp.route("/<uuid:model_id>/content/relationships/<string:relationship_id>")
class Relationship(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.content")
    def delete(self, model_id, relationship_id):
        """Remove a relationship (kept in history)"""
        return _write(lambda c: ct.delete_relationship(c, model_id, relationship_id), "relationship.delete", model_id,
                      {"relationship": relationship_id})
