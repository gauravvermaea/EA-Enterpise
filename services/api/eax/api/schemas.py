"""Request and response shapes, which also drive the OpenAPI (Swagger) description."""

from marshmallow import Schema, fields


class DatabaseStatus(Schema):
    reachable = fields.Boolean(required=True)
    latency_ms = fields.Float(allow_none=True)
    schema_version = fields.String(allow_none=True, metadata={"description": "Alembic revision"})
    error = fields.String(allow_none=True)


class JobQueueStatus(Schema):
    waiting = fields.Integer(allow_none=True)
    failed = fields.Integer(allow_none=True)


class Heartbeat(Schema):
    status = fields.String(required=True, metadata={"description": "ok or degraded"})
    service = fields.String(required=True)
    version = fields.String(required=True)
    deployment = fields.String(required=True)
    time = fields.DateTime(required=True)
    database = fields.Nested(DatabaseStatus, required=True)
    jobs = fields.Nested(JobQueueStatus, required=True)


class HeartbeatRecordIn(Schema):
    note = fields.String(load_default="", metadata={"description": "Free text kept with the record"})


class HeartbeatRecordOut(Schema):
    id = fields.Integer()
    at = fields.DateTime()
    source = fields.String()
    note = fields.String()
    requested_by = fields.String()


class Me(Schema):
    username = fields.String()
    email = fields.String(allow_none=True)
    name = fields.String(allow_none=True)
    roles = fields.List(fields.String())


class JobRequestIn(Schema):
    note = fields.String(load_default="")


class JobOut(Schema):
    job_id = fields.Integer()
    status = fields.String()
    task = fields.String(allow_none=True)


class AuditEvent(Schema):
    id = fields.Integer()
    at = fields.DateTime()
    actor = fields.String()
    action = fields.String()
    object_type = fields.String(allow_none=True)
    object_id = fields.String(allow_none=True)
    source = fields.String()
    details = fields.Dict()


class AuditQuery(Schema):
    limit = fields.Integer(load_default=50, validate=lambda n: 1 <= n <= 500)


# ---- Phase 1: models and the metamodel (read only)

class ModelOut(Schema):
    id = fields.UUID()
    name = fields.String()
    description = fields.String()
    kind = fields.String(metadata={"description": "template, reference or project"})
    kind_name = fields.String()
    parent_model_id = fields.UUID(allow_none=True, metadata={"description": "The model this one merges back into"})
    parent_model_name = fields.String(allow_none=True)
    source_model_id = fields.UUID(allow_none=True, metadata={"description": "The model it was created or copied from"})
    source_model_name = fields.String(allow_none=True)
    metamodel_name = fields.String()
    metamodel_version = fields.Integer()
    is_locked = fields.Boolean(metadata={"description": "read-only (templates and reference models)"})
    status = fields.String()
    entity_type_count = fields.Integer()
    entity_count = fields.Integer()
    relationship_count = fields.Integer()


class EntityTypeSummary(Schema):
    id = fields.UUID()
    layer_id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    aspect = fields.String()
    id_prefix = fields.String()
    table_name = fields.String(metadata={"description": "snake_case name of the type, accepted by eax.get_entity"})
    status = fields.String()
    attribute_count = fields.Integer()
    entity_count = fields.Integer()


class LayerOut(Schema):
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    colour = fields.String()
    entity_types = fields.List(fields.Nested(EntityTypeSummary))


class RelationshipTypeOut(Schema):
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    verb = fields.String()
    category = fields.String()
    is_directed = fields.Boolean()
    description = fields.String()


class Metamodel(Schema):
    model = fields.Nested(ModelOut)
    layers = fields.List(fields.Nested(LayerOut))
    relationship_types = fields.List(fields.Nested(RelationshipTypeOut))


class AttributeOut(Schema):
    code = fields.String()
    name = fields.String()
    description = fields.String()
    column_name = fields.String()
    data_type = fields.String()
    data_type_name = fields.String()
    unit = fields.String()
    is_required = fields.Boolean()
    section = fields.String()
    pick_list = fields.String(allow_none=True)
    pick_list_values = fields.List(fields.String())


class RuleOut(Schema):
    field = fields.String()
    rule = fields.String()
    param1 = fields.String()
    param2 = fields.String()
    severity = fields.String()
    message = fields.String()


class AllowedOut(Schema):
    relationship_type = fields.String()
    verb = fields.String()
    other_type_id = fields.UUID()
    other_type = fields.String()
    note = fields.String()


class EntityTypeDetail(Schema):
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    aspect = fields.String()
    id_prefix = fields.String()
    table_name = fields.String()
    layer = fields.String()
    colour = fields.String()
    attributes = fields.List(fields.Nested(AttributeOut))
    rules = fields.List(fields.Nested(RuleOut))
    outgoing = fields.List(fields.Nested(AllowedOut), metadata={"description": "this type -> other type"})
    incoming = fields.List(fields.Nested(AllowedOut), metadata={"description": "other type -> this type"})


class EntitiesQuery(Schema):
    type = fields.String(required=True, metadata={"description": "Entity type name, code or table name"})
    name = fields.String(load_default=None, metadata={"description": "One entity by name (case-insensitive)"})
    limit = fields.Integer(load_default=500, validate=lambda n: 1 <= n <= 5000)


class EntitiesOut(Schema):
    entity_table = fields.String()
    relationship_table = fields.String()
    columns = fields.List(fields.String(), metadata={"description": "Column order of the entity table"})
    rows = fields.List(fields.Dict(), metadata={"description": "One object per entity, keyed by column (id is the internal key, guid the global id)"})
    relationships = fields.List(fields.Dict())


class EntityListQuery(Schema):
    type = fields.String(load_default=None, metadata={"description": "Only this entity type (name, code or table name)"})
    limit = fields.Integer(load_default=2000, validate=lambda n: 1 <= n <= 10000)


class EntitySummaryOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    description = fields.String()
    entity_type = fields.String()
    entity_type_id = fields.UUID()
    layer = fields.String()
    colour = fields.String()
    parent_name = fields.String(allow_none=True)
    status = fields.String()
    relationship_count = fields.Integer()
    modified_at = fields.DateTime()
    modified_by = fields.String()


class RelationshipOut(Schema):
    id = fields.UUID()
    relationship_type = fields.String()
    verb = fields.String()
    source_id = fields.UUID()
    source_display_id = fields.String()
    source_name = fields.String()
    source_type = fields.String()
    target_id = fields.UUID()
    target_display_id = fields.String()
    target_name = fields.String()
    target_type = fields.String()
    name = fields.String()
    status = fields.String()


class EntityAttributeValueOut(Schema):
    code = fields.String()
    name = fields.String()
    section = fields.String()
    data_type = fields.String()
    unit = fields.String()
    is_required = fields.Boolean()
    value = fields.String(allow_none=True)


class EntityRelationshipOut(Schema):
    id = fields.UUID()
    relationship_type = fields.String()
    verb = fields.String()
    direction = fields.String(metadata={"description": "outgoing (this -> other) or incoming (other -> this)"})
    other_id = fields.UUID()
    other_display_id = fields.String()
    other_name = fields.String()
    other_type = fields.String()
    other_colour = fields.String()


class EntityRefOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()


class EntityDetailOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    description = fields.String()
    status = fields.String()
    entity_type = fields.String()
    entity_type_id = fields.UUID()
    layer = fields.String()
    colour = fields.String()
    parent_id = fields.UUID(allow_none=True)
    parent_name = fields.String(allow_none=True)
    created_at = fields.DateTime()
    created_by = fields.String()
    modified_at = fields.DateTime()
    modified_by = fields.String()
    row_version = fields.Integer()
    attributes = fields.List(fields.Nested(EntityAttributeValueOut))
    relationships = fields.List(fields.Nested(EntityRelationshipOut))
    children = fields.List(fields.Nested(EntityRefOut))


class DiagramAttributeOut(Schema):
    name = fields.String()
    column_name = fields.String()
    data_type = fields.String()
    data_type_name = fields.String()
    unit = fields.String()
    is_required = fields.Boolean()
    pick_list = fields.String(allow_none=True)


class DiagramTypeOut(Schema):
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    table_name = fields.String()
    id_prefix = fields.String()
    layer_id = fields.UUID()
    layer = fields.String()
    colour = fields.String()
    entity_count = fields.Integer()
    attributes = fields.List(fields.Nested(DiagramAttributeOut))


class DiagramLinkOut(Schema):
    source = fields.UUID()
    target = fields.UUID()
    relationship_types = fields.List(fields.String(), metadata={"description": "Codes of the allowed relationship types"})


class MetamodelDiagram(Schema):
    model = fields.Nested(ModelOut)
    layers = fields.List(fields.Nested(LayerOut))
    entity_types = fields.List(fields.Nested(DiagramTypeOut))
    relationship_types = fields.List(fields.Nested(RelationshipTypeOut))
    links = fields.List(fields.Nested(DiagramLinkOut))


class MermaidQuery(Schema):
    layer = fields.List(fields.String(), load_default=None,
                        metadata={"description": "Layers to show (name or code); repeat for several. All when left out"})
    type = fields.String(load_default=None, metadata={"description": "Focus on this entity type and the types it may connect to"})
    rel = fields.List(fields.String(), load_default=None,
                      metadata={"description": "Relationship types to show; repeat for several. Default: all but Association and Specialization"})
    generic = fields.Boolean(load_default=False, metadata={"description": "Include Association and Specialization"})
    connected = fields.Boolean(load_default=False, metadata={"description": "Also show types in other layers that the chosen layers connect to"})
    attributes = fields.Boolean(load_default=True, metadata={"description": "List each type's attributes"})


class MermaidOut(Schema):
    model = fields.String()
    entity_types = fields.Integer()
    links = fields.Integer()
    relationship_types = fields.List(fields.String())
    mermaid = fields.String()


class SqlQueryIn(Schema):
    database = fields.String(load_default="eaexplorer", metadata={"description": "Database on this installation's server"})
    username = fields.String(required=True, metadata={"description": "PostgreSQL user, for example eax_app or postgres"})
    password = fields.String(required=True, load_only=True)
    sql = fields.String(required=True, metadata={"description": "One or more SQL statements"})
    allow_changes = fields.Boolean(load_default=False, metadata={"description": "Commit the run; otherwise it is rolled back at the end"})


class SqlResultSet(Schema):
    columns = fields.List(fields.String())
    rows = fields.List(fields.List(fields.Raw()))
    row_count = fields.Integer(allow_none=True)
    truncated = fields.Boolean()
    status = fields.String()


class SqlQueryOut(Schema):
    results = fields.List(fields.Nested(SqlResultSet))
    notices = fields.List(fields.String())
    committed = fields.Boolean()
    duration_ms = fields.Integer()


class ServiceHealth(Schema):
    name = fields.String()
    kind = fields.String(metadata={"description": "The product behind the service"})
    status = fields.String(metadata={"description": "up, warning, down or off"})
    detail = fields.String()
    target = fields.String(metadata={"description": "What was checked, inside the Docker network"})
    response_ms = fields.Integer()


class ServicesHealth(Schema):
    status = fields.String(metadata={"description": "ok, degraded, or down when the database is down"})
    time = fields.DateTime()
    duration_ms = fields.Integer()
    counts = fields.Dict(keys=fields.String(), values=fields.Integer())
    services = fields.List(fields.Nested(ServiceHealth))
