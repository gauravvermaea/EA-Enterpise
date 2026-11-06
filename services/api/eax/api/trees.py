"""Tree views (D250): key and value only, a level at a time.

GET /models/<m>/tree/metamodel               model > entity types > attributes and allowed relations (both ways)
GET /models/<m>/tree/types                   the entity types with their counts and data quality (last calculated)
GET /models/<m>/tree/types/<type>            a page of its entities (?offset=&limit=&q=), each with its data quality
GET /models/<m>/tree/entities/<entity>       one entity: its filled values, how many are empty, its relationships
GET /models/<m>/tree/search?q=               entity types, entities and values matching, for the filter box
GET /models/<m>/tree/xlsx?scope=metamodel|entities|entity&type=&entity=   the tree as an Excel outline
"""

from __future__ import annotations

from flask import Response, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import repository as repo
from .. import trees
from ..auth import require_auth
from ..db import get_engine
from .models import Free

blp = Blueprint("trees", __name__, url_prefix="/api/v1", description="Tree views of the metamodel and the entities")
SECURITY = [{"bearerAuth": []}]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except repo.NotFound as exc:
        abort(404, message=str(exc))


@blp.route("/models/<uuid:model_id>/tree/metamodel")
class MetamodelTree(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The metamodel as a tree: entity types with their attributes and the relations allowed both ways"""
        return _read(lambda c: trees.metamodel_tree(c, model_id))


@blp.route("/models/<uuid:model_id>/tree/types")
class TypesTree(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The entity types with how many entities each has and their data quality as last calculated"""
        return _read(lambda c: trees.types_tree(c, model_id))


@blp.route("/models/<uuid:model_id>/tree/types/<string:entity_type>")
class TypeEntities(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_type):
        """A page of an entity type's entities (?offset=, limit= up to 1000, q= to filter by name or ID)"""
        a = request.args
        return _read(lambda c: trees.type_entities(c, model_id, entity_type, int(a.get("offset", 0) or 0),
                                                   int(a.get("limit", trees.PAGE) or trees.PAGE), a.get("q", "")))


@blp.route("/models/<uuid:model_id>/tree/entities/<string:entity>")
class EntityTree(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity):
        """One entity in the tree: its filled values (key and value), how many are empty, and its relationships"""
        return _read(lambda c: trees.entity_node(c, model_id, entity))


@blp.route("/models/<uuid:model_id>/tree/search")
class TreeSearch(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """What matches the filter box (?q=): entity types, entities and attribute values, with their path"""
        return _read(lambda c: trees.search(c, model_id, request.args.get("q", "")))


@blp.route("/models/<uuid:model_id>/tree/xlsx")
class TreeXlsx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id):
        """The tree as an Excel outline: ?scope=metamodel, entities (&type= for one entity type) or entity (&entity=)"""
        a = request.args
        scope = a.get("scope", "entities")
        if scope not in ("metamodel", "entities", "entity"):
            abort(400, message="scope is metamodel, entities or entity.")
        data = _read(lambda c: trees.tree_xlsx(c, model_id, scope, a.get("type") or None, a.get("entity") or None))
        return Response(data, mimetype=XLSX, headers={"Content-Disposition": f'attachment; filename="EA-Explorer-tree-{scope}.xlsx"'})
