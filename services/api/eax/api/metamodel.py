"""Models, their metamodel and their content, read only (build phase 1).

Identifiers in URLs and responses are guids; the bigint keys stay inside the database. The work
is done by eax.repository, which the MCP server uses too. Every call needs a signed-in user.
Editing the metamodel arrives in build phase 3; entering content in phase 6.
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from .schemas import (
    EntitiesOut, EntitiesQuery, EntityDetailOut, EntityListQuery, EntitySummaryOut, EntityTypeDetail,
    MermaidOut, MermaidQuery, Metamodel, MetamodelDiagram, ModelOut, RelationshipOut,
)

blp = Blueprint(
    "metamodel", __name__, url_prefix="/api/v1/models",
    description="Models, their metamodel and their content (read only)",
)
SECURITY = [{"bearerAuth": []}]


def _call(fn, *args, begin: bool = False, **kwargs):
    """Runs a repository function on a fresh connection; NotFound becomes a 404."""
    engine = get_engine()
    with (engine.begin() if begin else engine.connect()) as conn:
        try:
            return fn(conn, *args, **kwargs)
        except repo.NotFound as exc:
            abort(404, message=str(exc))


@blp.route("")
class ModelList(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut(many=True))
    @require_auth()
    def get(self):
        """Every model you may read: templates, reference models and project models (with parent and source)"""
        return _call(repo.list_models)


@blp.route("/<uuid:model_id>")
class ModelView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, ModelOut)
    @require_auth()
    def get(self, model_id):
        """One model and its counts"""
        return _call(repo.get_model, model_id)


@blp.route("/<uuid:model_id>/metamodel")
class ModelMetamodel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Metamodel)
    @require_auth()
    def get(self, model_id):
        """The model's metamodel: layers with their entity types, and the relationship types"""
        return _call(repo.get_metamodel, model_id)


@blp.route("/<uuid:model_id>/metamodel/diagram")
class ModelMetamodelDiagram(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, MetamodelDiagram)
    @require_auth()
    def get(self, model_id):
        """Data for the metamodel ER diagram: entity types with their attributes, and the allowed
        relationships combined per source and target type"""
        return _call(repo.get_metamodel_diagram, model_id)


@blp.route("/<uuid:model_id>/metamodel/mermaid")
class ModelMetamodelMermaid(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(MermaidQuery, location="query")
    @blp.response(200, MermaidOut)
    @require_auth()
    def get(self, query, model_id):
        """The metamodel, or part of it, as a Mermaid ER diagram (paste into any Mermaid editor)"""
        return _call(repo.metamodel_mermaid, model_id, layers=query["layer"], entity_type=query["type"],
                     relationship_types=query["rel"], include_generic=query["generic"],
                     include_connected=query["connected"], with_attributes=query["attributes"])


@blp.route("/<uuid:model_id>/entity-types/<uuid:type_id>")
class EntityTypeView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, EntityTypeDetail)
    @require_auth()
    def get(self, model_id, type_id):
        """One entity type: its attributes, validation rules and allowed relationships"""
        return _call(repo.get_entity_type, model_id, type_id)


@blp.route("/<uuid:model_id>/entity-list")
class EntityListView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(EntityListQuery, location="query")
    @blp.response(200, EntitySummaryOut(many=True))
    @require_auth()
    def get(self, query, model_id):
        """Every entity of the model (or of one type): display ID, name, type, layer, relationship count"""
        return _call(repo.list_entities, model_id, query.get("type"), query["limit"])


@blp.route("/<uuid:model_id>/entities/<uuid:entity_id>")
class EntityDetailView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, EntityDetailOut)
    @require_auth()
    def get(self, model_id, entity_id):
        """One entity: every attribute of its type with its value, its relationships, parent and children"""
        return _call(repo.get_entity_detail, model_id, entity_id)


@blp.route("/<uuid:model_id>/relationships")
class RelationshipListView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, RelationshipOut(many=True))
    @require_auth()
    def get(self, model_id):
        """Every relationship of the model: source, relationship type, target"""
        return _call(repo.list_relationships, model_id)


@blp.route("/<uuid:model_id>/entities")
class EntitiesView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(EntitiesQuery, location="query")
    @blp.response(200, EntitiesOut)
    @require_auth()
    def get(self, query, model_id):
        """Entities of one type in the model, one column per attribute (built by eax.get_entity)

        Give `type` as the type's name, code or table name. Add `name` for one entity
        (eax.get_entity_by_name). The relationships of the returned entities come with them.
        """
        return _call(repo.get_entities, model_id, query["type"], query.get("name"), query["limit"],
                     actor=g.user.username, begin=True)
