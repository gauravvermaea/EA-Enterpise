"""Grids, search, saved views and favourites (build phase 7).

Content grids (entities of a type, relationships) are read and saved in bulk through eax.content: each row
saved on its own, the answer lists every row's outcome. Metamodel grids (entity types, relationship types,
attributes, mappings, pick-list values, rules) are saved through eax.metamodel_edit.apply_many as one
metamodel version, all or nothing (Model Admins, D89). Search, saved views and favourites are per person.
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import INCLUDE, Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit, grids, workspace
from .. import commits as cm
from .. import content as ct
from .. import metamodel_edit as ed
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free

blp = Blueprint("grids", __name__, url_prefix="/api/v1",
                description="Grids for content and metamodel, search, saved views and favourites (phase 7)")
SECURITY = [{"bearerAuth": []}]


class RowsIn(Schema):
    rows = fields.List(fields.Dict(), required=True, metadata={"description": "Changed rows only; a row with id and delete: true is deleted"})


class ChangesIn(Schema):
    changes = fields.List(fields.Dict(), required=True, metadata={"description": "Metamodel changes {op, ...} in order, saved as one version"})
    dry_run = fields.Boolean(load_default=False)


class ViewIn(Schema):
    class Meta:
        unknown = INCLUDE
    id = fields.String(load_default=None)
    name = fields.String(required=True)
    view_kind = fields.String(required=True)
    model = fields.String(load_default=None)
    target = fields.String(load_default="")
    config = fields.Dict(load_default=dict)
    shared = fields.Boolean(load_default=False)


class FavouriteIn(Schema):
    kind = fields.String(required=True)
    id = fields.String(required=True)
    favourite = fields.Boolean(load_default=True)
    label = fields.String(load_default="")


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, object_id="", details=None, dry_run: bool = False):
    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            out = fn(conn)
            if dry_run:
                trans.rollback()
                return out
            audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(object_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
            trans.commit()
            return out
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


# ---------------------------------------------------------------- content grids
@blp.route("/models/<uuid:model_id>/grids/entities/<string:entity_type>")
class EntityGrid(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_type):
        """The entities of one type as grid rows, with the type's columns (same as the data entry page)"""
        return _read(lambda c: cm.overlay(c, model_id, g.user.username, lambda cc: ct.entry_table(cc, model_id, entity_type)))

    @blp.doc(security=SECURITY)
    @blp.arguments(RowsIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, body, model_id, entity_type):
        """Save the changed rows: new, changed and deleted entities. Each row on its own; every row's outcome"""
        def run(c):   # phase 8 (D165): kept as uncommitted changes in a working model
            if cm.uses_commits(repo.get_model(c, model_id)):
                return cm.record_entity_rows(c, model_id, entity_type, body["rows"], g.user.username)
            return ct.bulk_entities(c, model_id, entity_type, body["rows"], g.user.username)
        return _write(run, "grid.entities", model_id, {"entity_type": entity_type, "rows": len(body["rows"])})


@blp.route("/models/<uuid:model_id>/grids/relationships")
class RelationshipGrid(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Every relationship of the model (?type= one relationship type) as grid rows"""
        return _read(lambda c: cm.overlay(c, model_id, g.user.username,
                                          lambda cc: ct.relationship_grid(cc, model_id, request.args.get("type") or None)))

    @blp.doc(security=SECURITY)
    @blp.arguments(RowsIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, body, model_id):
        """Save the changed rows: new (type, source, target by guid, display ID or name), changed and deleted"""
        def run(c):
            if cm.uses_commits(repo.get_model(c, model_id)):
                return cm.record_relationship_rows(c, model_id, body["rows"], g.user.username)
            return ct.bulk_relationships(c, model_id, body["rows"], g.user.username)
        return _write(run, "grid.relationships", model_id, {"rows": len(body["rows"])})


# ---------------------------------------------------------------- metamodel grids
@blp.route("/models/<uuid:model_id>/grids/metamodel/<any(entity_types,relationship_types,attributes,mappings,pick_list_values,rules):kind>")
class MetamodelGrid(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, kind):
        """One part of the metamodel as grid rows, with the choices its drop-down cells offer"""
        return _read(lambda c: grids.metamodel_grid(c, model_id, kind))


@blp.route("/models/<uuid:model_id>/metamodel/batch")
class MetamodelBatch(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(ChangesIn)
    @blp.response(200, Free)
    @require_auth("model.metamodel")
    def post(self, body, model_id):
        """Save several metamodel changes as one new metamodel version, all or nothing (dry_run: the impact only)"""
        return _write(lambda c: ed.apply_many(c, model_id, body["changes"], g.user.username, body["dry_run"]),
                      "metamodel.batch", model_id, {"changes": len(body["changes"])}, dry_run=body["dry_run"])


# ---------------------------------------------------------------- search
@blp.route("/search")
class Search(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Search every model you may read: ?q=text&model=&type=&attribute=&tag=&status=&limit="""
        a = request.args
        return _read(lambda c: workspace.search(c, a.get("q", ""), a.get("model") or None, a.get("type", ""),
                                                a.get("attribute", ""), a.get("tag", ""), a.get("status", ""),
                                                int(a.get("limit", 100))))


# ---------------------------------------------------------------- saved views and favourites
@blp.route("/views")
class Views(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Your saved views and those shared with you: ?model=&kind=&target="""
        a = request.args
        return _read(lambda c: workspace.list_views(c, g.user.username, a.get("model") or None, a.get("kind", ""), a.get("target", "")))

    @blp.doc(security=SECURITY)
    @blp.arguments(ViewIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, body):
        """Save a view (with id: change your own view)"""
        return _write(lambda c: workspace.save_view(c, g.user.username, body), "view.save", body.get("model") or "", {"name": body["name"]})


@blp.route("/views/<string:view_id>")
class View(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, view_id):
        """Delete one of your views"""
        return _write(lambda c: workspace.delete_view(c, g.user.username, view_id), "view.delete", "", {"view": view_id})


@blp.route("/favourites")
class Favourites(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Your favourites: entities, models and views"""
        return _read(lambda c: workspace.list_favourites(c, g.user.username))

    @blp.doc(security=SECURITY)
    @blp.arguments(FavouriteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, body):
        """Mark (favourite: true) or unmark something as a favourite"""
        return _write(lambda c: workspace.set_favourite(c, g.user.username, body["kind"], body["id"], body["favourite"], body["label"]),
                      "favourite.set", "", {"kind": body["kind"], "id": body["id"]})
