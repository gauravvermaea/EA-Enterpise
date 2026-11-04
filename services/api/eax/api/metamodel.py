"""Models, their metamodel and their content, read only (build phase 1).

Identifiers in URLs and responses are guids; the bigint keys stay inside the database. The work
is done by eax.repository, which the MCP server uses too. Every call needs a signed-in user.
Editing the metamodel arrives in build phase 3; entering content in phase 6. Phase 2 adds the
views behind the model screens: the entities of a type as a table with rule results, the
relationship types with their use, an entity's history and the entity graph.
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from .schemas import (
    AsOfQuery,
    EntitiesOut,
    EntitiesQuery,
    EntityAsOfOut,
    EntityDetailOut,
    EntityGraphOut,
    EntityHistoryOut,
    EntityListQuery,
    EntitySummaryOut,
    EntityTypeDetail,
    GraphQuery,
    HistoryQuery,
    LibraryModelOut,
    MermaidOut,
    MermaidQuery,
    Metamodel,
    MetamodelDiagram,
    ModelListQuery,
    ModelOut,
    PathQuery,
    RelationshipListQuery,
    RelationshipOut,
    RelationshipTypeSummaryOut,
    TypeTableOut,
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
    @blp.arguments(ModelListQuery, location="query")
    @blp.response(200, ModelOut(many=True))
    @require_auth()
    def get(self, query):
        """Every model you may read: templates, reference models and project models

        With their properties (owner, active or archived, industry and version for reference
        models), parent and source, and counts. Filter by text, kind, or leave out archived ones.
        """
        return _call(repo.list_models, query["search"], query["kind"], query["archived"])


@blp.route("/library")
class Library(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, LibraryModelOut(many=True))
    @require_auth()
    def get(self):
        """The model library: read-only reference models with their counts by type

        Reference models are locked: nobody can change them (the database refuses it), and they are
        updated only by a product release, which adds a new version beside the old one.
        """
        return _call(repo.get_library)


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
        """One entity: every attribute of its type with its value and rule results, the warnings,
        its relationships (each marked allowed or not), parent, children, and the relationships its
        type may have"""
        return _call(repo.get_entity_detail, model_id, entity_id)


@blp.route("/<uuid:model_id>/entity-types/<uuid:type_id>/table")
class TypeTableView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, TypeTableOut)
    @require_auth()
    def get(self, model_id, type_id):
        """The entities of one type as a table: a column per attribute, and per row its values,
        relationship count and validation results (errors and warnings)"""
        return _call(repo.type_table, model_id, type_id)


@blp.route("/<uuid:model_id>/entities/<uuid:entity_id>/history")
class EntityHistoryView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(HistoryQuery, location="query")
    @blp.response(200, EntityHistoryOut)
    @require_auth()
    def get(self, query, model_id, entity_id):
        """Every recorded change to an entity, its attribute values and its relationships, newest first"""
        return _call(repo.get_entity_history, model_id, entity_id, query["limit"])


@blp.route("/<uuid:model_id>/entities/<uuid:entity_id>/as-of")
class EntityAsOfView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(AsOfQuery, location="query")
    @blp.response(200, EntityAsOfOut)
    @require_auth()
    def get(self, query, model_id, entity_id):
        """An entity as it was at one point in its history, beside its values now

        Give `event` (a history event id from .../history) or `at` (a time). Read only: rolling back
        to that point arrives with editing (build phase 6).
        """
        if query["event"] is None and query["at"] is None:
            abort(400, message="Give event or at.")
        return _call(repo.get_entity_as_of, model_id, entity_id, query["event"], query["at"])


@blp.route("/<uuid:model_id>/entities/<uuid:entity_id>/paths")
class EntityPathsView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(PathQuery, location="query")
    @blp.response(200, EntityGraphOut)
    @require_auth()
    def get(self, query, model_id, entity_id):
        """The shortest chains connecting this entity to another (`to`), through relationships either way
        and the parent hierarchy, as a graph and as lists of entities"""
        return _call(repo.entity_paths, model_id, entity_id, query["to"], query["steps"], query["paths"], query["rel"])


@blp.route("/<uuid:model_id>/graph")
class EntityGraphView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(GraphQuery, location="query")
    @blp.response(200, EntityGraphOut)
    @require_auth()
    def get(self, query, model_id):
        """Entities and the lines between them (relationships and the parent hierarchy), for drawing

        Give `focus` (an entity and everything within `depth` steps) or `type` (every entity of
        those types); with neither, the whole model. With `focus`, `direction` out or in follows the
        lines one way only (impact and dependency chains) and `rel` keeps chosen relationship types.
        At most `limit` entities.
        """
        return _call(repo.entity_graph, model_id, query["focus"], query["type"], query["depth"], query["limit"],
                     query["direction"], query["rel"])


@blp.route("/<uuid:model_id>/relationship-types")
class RelationshipTypeSummaryView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, RelationshipTypeSummaryOut(many=True))
    @require_auth()
    def get(self, model_id):
        """Every relationship type with how often the model uses it and how many uses break the rules"""
        return _call(repo.relationship_type_summary, model_id)


@blp.route("/<uuid:model_id>/relationships")
class RelationshipListView(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(RelationshipListQuery, location="query")
    @blp.response(200, RelationshipOut(many=True))
    @require_auth()
    def get(self, query, model_id):
        """Every relationship of the model (or of one type): source, relationship type, target, and
        whether the metamodel allows it"""
        return _call(repo.list_relationships, model_id, query["type"], query["limit"])


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
