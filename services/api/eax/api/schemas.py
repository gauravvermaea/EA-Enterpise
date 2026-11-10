"""Request and response shapes, which also drive the OpenAPI (Swagger) description."""

from marshmallow import Schema, fields


class DatabaseStatus(Schema):
    reachable = fields.Boolean(required=True)
    latency_ms = fields.Float(allow_none=True)
    schema_version = fields.String(allow_none=True, metadata={"description": "Alembic revision"})
    version = fields.String(allow_none=True, metadata={"description": "Database version (core.schema_versions)"})
    error = fields.String(allow_none=True)


class JobQueueStatus(Schema):
    waiting = fields.Integer(allow_none=True)
    failed = fields.Integer(allow_none=True)


class Heartbeat(Schema):
    status = fields.String(required=True, metadata={
        "description": "ok; warning when the API and database versions differ; degraded when the database cannot be reached"})
    service = fields.String(required=True)
    version = fields.String(required=True, metadata={"description": "API version (version.toml)"})
    versions_match = fields.Boolean(allow_none=True, metadata={"description": "API version equals database version"})
    warning = fields.String(allow_none=True)
    deployment = fields.String(required=True)
    time = fields.DateTime(required=True)
    database = fields.Nested(DatabaseStatus, required=True)
    jobs = fields.Nested(JobQueueStatus, required=True)
    maintenance = fields.Dict(allow_none=True, metadata={
        "description": "Set while a backup is restored (phase 8.4): what, since when, by whom; the installation is read only"})


class HeartbeatRecordIn(Schema):
    note = fields.String(load_default="", metadata={"description": "Free text kept with the record"})


class HeartbeatRecordOut(Schema):
    id = fields.Integer()
    at = fields.DateTime()
    source = fields.String()
    note = fields.String()
    requested_by = fields.String()


class AssignedModelOut(Schema):
    id = fields.UUID()
    name = fields.String()
    kind = fields.String()
    roles = fields.List(fields.String(), metadata={"description": "Your roles on the model"})
    role = fields.String(metadata={"description": "The highest of them"})
    permissions = fields.List(fields.String(), metadata={"description": "What they allow there (model.*)"})


class Me(Schema):
    username = fields.String()
    email = fields.String(allow_none=True)
    name = fields.String(allow_none=True)
    roles = fields.List(fields.String(), metadata={"description": "Global EA Explorer roles, mapped from the Keycloak roles"})
    keycloak_roles = fields.List(fields.String(), metadata={"description": "The realm roles Keycloak gave"})
    permissions = fields.Dict(keys=fields.String(), values=fields.Boolean())
    sees_every_model = fields.Boolean()
    models = fields.List(fields.Nested(AssignedModelOut), metadata={"description": "Models where you have a role, with the role"})
    break_glass = fields.Boolean()
    parts = fields.Dict(keys=fields.String(), values=fields.Boolean(),
                        metadata={"description": "Which parts are on: projects, repository, references (D329)"})
    library = fields.Dict(metadata={"description": "The enterprise library (D350): mode (ours, link, off), link, search_link "
                                                   "(with {q}), service (whether the library service is on)"})


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
    source_model_kind = fields.String(allow_none=True, metadata={"description": "template (made from a metamodel), reference or project (a copy)"})
    source_tag_name = fields.String(allow_none=True, metadata={"description": "Made from the source model as it was at this tag"})
    metamodel_name = fields.String()
    metamodel_version = fields.Integer()
    is_locked = fields.Boolean(metadata={"description": "read-only (templates and reference models)"})
    status = fields.String()
    owner = fields.String()
    lifecycle = fields.String(metadata={"description": "active or archived"})
    industry = fields.String(metadata={"description": "Reference models: the industry"})
    version_label = fields.String(metadata={"description": "Reference models: their version"})
    lock_level = fields.String(metadata={"description": "none, metamodel, content or maintenance (set by a Model Admin)"})
    frozen_at = fields.DateTime(allow_none=True, metadata={"description": "when the model was frozen: read only for good (D283)"})
    frozen_by = fields.String(allow_none=True)
    frozen_note = fields.String()
    lock_reason = fields.String()
    locked_at = fields.DateTime(allow_none=True)
    locked_by = fields.String(allow_none=True)
    created_at = fields.DateTime()
    created_by = fields.String()
    modified_at = fields.DateTime()
    modified_by = fields.String()
    library_state = fields.String(metadata={"description": "Roots and reference models: building, published or withdrawn (D118)"})
    copy_state = fields.String(metadata={"description": "copying while a copy runs in the background, failed if it failed"})
    copy_note = fields.String()
    history_from_source = fields.Boolean(metadata={"description": "A deep copy: its entities carry their full history from the source (D132)"})
    is_draft = fields.Boolean(metadata={"description": "Not yet published: only its Model Admins use it or create models from it (D131)"})
    approval_state = fields.String(metadata={"description": "A draft's publishing: editing, requested (waiting for approval) or returned (sent back), D134"})
    published_at = fields.DateTime(allow_none=True)
    published_by = fields.String(allow_none=True)
    entity_type_count = fields.Integer()
    entity_count = fields.Integer()
    relationship_count = fields.Integer()


class ModelListQuery(Schema):
    search = fields.String(load_default=None, metadata={"description": "Text in the name, description, owner or industry"})
    kind = fields.String(load_default=None, metadata={"description": "template, reference or project"})
    archived = fields.Boolean(load_default=True, metadata={"description": "Include archived models"})


class TypeCountOut(Schema):
    entity_type = fields.String()
    domain = fields.String()
    colour = fields.String()
    count = fields.Integer()


class RelationshipCountOut(Schema):
    relationship_type = fields.String()
    count = fields.Integer()


class DomainCountOut(Schema):
    name = fields.String()
    colour = fields.String()
    types = fields.Integer()


class LibraryModelOut(ModelOut):
    is_top = fields.Boolean(metadata={"description": "The Root model at the top of the hierarchy"})
    built_on = fields.String(allow_none=True, metadata={"description": "The root metamodel it is built on (ArchiMate 4, ...)"})
    counts_by_type = fields.List(fields.Nested(TypeCountOut))
    relationship_counts = fields.List(fields.Nested(RelationshipCountOut))
    domains = fields.List(fields.Nested(DomainCountOut))
    relationship_type_count = fields.Integer()


class EntityTypeSummary(Schema):
    id = fields.UUID()
    domain_id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    aspect = fields.String()
    id_prefix = fields.String()
    table_name = fields.String(metadata={"description": "snake_case name of the type, accepted by eax.get_entity"})
    status = fields.String()
    attribute_count = fields.Integer()
    entity_count = fields.Integer()
    content_area = fields.String(metadata={"description": "Its content framework areas, codes with commas (D309); empty: built in"})
    content_default = fields.String(metadata={"description": "Its built-in content framework areas"})
    repository_area = fields.String(metadata={"description": "The part of the Architecture Repository it is filed in (D318); empty: built in"})
    repository_default = fields.String(metadata={"description": "Its built-in Repository Area"})
    notation = fields.String(metadata={"description": "The ArchiMate 4 element whose shape and icon it shows on drawn views; empty: a plain box (D354)"})
    fill_colour = fields.String(metadata={"description": "Its own fill colour (RRGGBB); empty: its domain's"})
    is_connector = fields.Boolean(metadata={"description": "A junction: not an element (D397)"})
    drawio = fields.Dict(metadata={"description": "draw.io styles: box, shape (forms) and colour (phase 28)"})


class DomainOut(Schema):
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
    status = fields.String(metadata={"description": "published or retired"})


class Metamodel(Schema):
    model = fields.Nested(ModelOut)
    domains = fields.List(fields.Nested(DomainOut))
    relationship_types = fields.List(fields.Nested(RelationshipTypeOut))


class AttributeOut(Schema):
    item_id = fields.UUID(metadata={"description": "This attribute on this type (for changing it)"})
    attribute_id = fields.UUID(metadata={"description": "The attribute definition, shared by the types that use it"})
    default_value = fields.String(allow_none=True)
    help_text = fields.String()
    pick_list_id = fields.UUID(allow_none=True)
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
    id = fields.UUID()
    rule_type_code = fields.String()
    attribute_id = fields.UUID(allow_none=True)
    field_name = fields.String(allow_none=True)
    all_types = fields.Boolean(metadata={"description": "The rule applies to every entity type"})
    field = fields.String()
    rule = fields.String()
    param1 = fields.String()
    param2 = fields.String()
    severity = fields.String()
    message = fields.String()


class AllowedOut(Schema):
    id = fields.UUID(metadata={"description": "The mapping (for removing it)"})
    relationship_type_id = fields.UUID()
    relationship_type = fields.String()
    verb = fields.String()
    other_type_id = fields.UUID()
    other_type = fields.String()
    note = fields.String()
    source_multiplicity = fields.String(metadata={"description": "How many sources one target may have: n, * or n..m; empty: any (D395)"})
    target_multiplicity = fields.String(metadata={"description": "How many targets one source may have: n, * or n..m; empty: any (D395)"})


class EntityTypeDetail(Schema):
    status = fields.String()
    domain_id = fields.UUID()
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    aspect = fields.String()
    id_prefix = fields.String()
    table_name = fields.String()
    domain = fields.String()
    colour = fields.String()
    content_area = fields.String(metadata={"description": "Its content framework areas, codes with commas (D309); empty: built in"})
    content_default = fields.String(metadata={"description": "Its built-in content framework areas"})
    repository_area = fields.String(metadata={"description": "The part of the Architecture Repository it is filed in (D318); empty: built in"})
    repository_default = fields.String(metadata={"description": "Its built-in Repository Area"})
    notation = fields.String(metadata={"description": "The ArchiMate 4 element whose shape and icon it shows on drawn views; empty: a plain box (D354)"})
    fill_colour = fields.String(metadata={"description": "Its own fill colour (RRGGBB); empty: its domain's"})
    is_connector = fields.Boolean(metadata={"description": "A junction: not an element (D397)"})
    drawio = fields.Dict(metadata={"description": "draw.io styles: box, shape (forms) and colour (phase 28)"})
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
    domain = fields.String()
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
    name = fields.String(allow_none=True)
    status = fields.String()
    relationship_type_code = fields.String()
    source_colour = fields.String()
    target_colour = fields.String()
    allowed = fields.Boolean(metadata={"description": "false: the metamodel has no rule allowing it"})


class RelationshipListQuery(Schema):
    type = fields.String(load_default=None, metadata={"description": "Only this relationship type (guid, code, name or verb)"})
    limit = fields.Integer(load_default=5000, validate=lambda n: 1 <= n <= 20000)


class RelationshipTypeSummaryOut(RelationshipTypeOut):
    allowed_pairs = fields.Integer(metadata={"description": "(source type, target type) pairs the metamodel allows"})
    relationship_count = fields.Integer(metadata={"description": "Relationships of this type in the model"})
    outside_rules = fields.Integer(metadata={"description": "Of those, how many the metamodel does not allow"})


class RuleResultOut(Schema):
    field = fields.String(metadata={"description": "Attribute or field name"})
    code = fields.String(metadata={"description": "Attribute code, or the built-in field (name, description)"})
    rule = fields.String(metadata={"description": "Rule type code; required = the attribute's required flag"})
    severity = fields.String(metadata={"description": "error or warning; neither blocks a save"})
    message = fields.String()


class EntityAttributeValueOut(Schema):
    code = fields.String()
    name = fields.String()
    section = fields.String()
    data_type = fields.String()
    data_type_name = fields.String()
    unit = fields.String()
    is_required = fields.Boolean()
    value = fields.String(allow_none=True)
    ref_id = fields.UUID(allow_none=True, metadata={"description": "The linked entity, for entity-link attributes"})
    ref_type = fields.String(allow_none=True)
    pick_list_values = fields.List(fields.String())
    warnings = fields.List(fields.Nested(RuleResultOut))


class EntityRelationshipOut(Schema):
    id = fields.UUID()
    relationship_type_id = fields.UUID()
    relationship_type = fields.String()
    relationship_type_code = fields.String()
    verb = fields.String()
    category = fields.String()
    direction = fields.String(metadata={"description": "outgoing (this -> other) or incoming (other -> this)"})
    other_id = fields.UUID()
    other_display_id = fields.String()
    other_name = fields.String()
    other_type = fields.String()
    other_type_id = fields.UUID()
    other_colour = fields.String()
    name = fields.String(allow_none=True)
    status = fields.String()
    modified_at = fields.DateTime()
    modified_by = fields.String()
    allowed = fields.Boolean(metadata={"description": "false: the metamodel has no rule allowing it"})


class EntityAllowedOut(Schema):
    direction = fields.String()
    relationship_type = fields.String()
    verb = fields.String()
    other_type_id = fields.UUID()
    other_type = fields.String()


class EntityRefOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()


class LineageModelOut(Schema):
    id = fields.UUID()
    name = fields.String()
    kind = fields.String()
    kind_name = fields.String()
    version_label = fields.String()
    is_locked = fields.Boolean()
    source_model_id = fields.UUID(allow_none=True, metadata={"description": "The model this model was created or copied from"})
    source_model_name = fields.String(allow_none=True)
    parent_model_id = fields.UUID(allow_none=True, metadata={"description": "The model this model merges back into"})
    parent_model_name = fields.String(allow_none=True)


class LineageItemOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    model_id = fields.UUID()
    model_name = fields.String()
    model_version = fields.String()
    model_kind = fields.String()


class LineageOut(Schema):
    copied_from = fields.Nested(LineageItemOut, allow_none=True, metadata={"description": "The entity this one was copied from"})
    copied_from_guid = fields.UUID(allow_none=True, metadata={"description": "Its guid, also when you may not read that model"})
    type_from = fields.Nested(LineageItemOut, allow_none=True, metadata={"description": "The template entity type its type came from"})
    copies = fields.List(fields.Nested(LineageItemOut), metadata={"description": "Copies of this entity in other models"})


class EntityDetailOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    description = fields.String()
    status = fields.String()
    entity_type = fields.String()
    entity_type_id = fields.UUID()
    domain = fields.String()
    colour = fields.String()
    parent_id = fields.UUID(allow_none=True)
    parent_name = fields.String(allow_none=True)
    created_at = fields.DateTime()
    created_by = fields.String()
    modified_at = fields.DateTime()
    modified_by = fields.String()
    row_version = fields.Integer()
    entity_type_code = fields.String()
    created_mm_version = fields.Integer(allow_none=True)
    modified_mm_version = fields.Integer(allow_none=True)
    tags = fields.List(fields.String())
    content_areas = fields.List(fields.String(), metadata={"description": "Its own content framework areas (D317); empty: its type's"})
    type_areas = fields.List(fields.String(), metadata={"description": "Its type's content framework areas"})
    repository_area = fields.String(metadata={"description": "Its type's Repository Area (D318)"})
    model = fields.Nested(LineageModelOut, metadata={"description": "The model the entity is part of"})
    lineage = fields.Nested(LineageOut)
    attributes = fields.List(fields.Nested(EntityAttributeValueOut))
    warnings = fields.List(fields.Nested(RuleResultOut), metadata={"description": "Failed validation rules, errors first"})
    relationships = fields.List(fields.Nested(EntityRelationshipOut))
    children = fields.List(fields.Nested(EntityRefOut))
    allowed = fields.List(fields.Nested(EntityAllowedOut), metadata={"description": "Relationships the metamodel allows for this entity's type"})


class TypeTableColumnOut(Schema):
    code = fields.String()
    name = fields.String()
    data_type = fields.String()
    unit = fields.String()
    is_required = fields.Boolean()
    section = fields.String()


class TypeTableRowOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    description = fields.String()
    status = fields.String()
    parent_id = fields.UUID(allow_none=True)
    parent_name = fields.String(allow_none=True)
    modified_at = fields.DateTime()
    modified_by = fields.String()
    row_version = fields.Integer()
    relationship_count = fields.Integer()
    values = fields.Dict(keys=fields.String(), values=fields.String(), metadata={"description": "Attribute code -> value"})
    errors = fields.Integer()
    warnings = fields.Integer()
    messages = fields.List(fields.String())
    checks = fields.List(fields.Dict(), metadata={"description": "Each failed check: rule, field, code, severity, message"})
    created_mm_version = fields.Integer(allow_none=True, metadata={"description": "Metamodel version it was created in"})
    modified_mm_version = fields.Integer(allow_none=True, metadata={"description": "Metamodel version it was last changed in"})


class TypeTableTypeOut(Schema):
    status = fields.String()
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    aspect = fields.String()
    id_prefix = fields.String()
    table_name = fields.String()
    domain = fields.String()
    colour = fields.String()


class TypeTableOut(Schema):
    entity_type = fields.Nested(TypeTableTypeOut)
    columns = fields.List(fields.Nested(TypeTableColumnOut))
    rows = fields.List(fields.Nested(TypeTableRowOut))
    rules = fields.Integer(metadata={"description": "Validation rules that apply to this type"})


class HistoryChangeOut(Schema):
    field = fields.String()
    old = fields.String(allow_none=True)
    new = fields.String(allow_none=True)
    action = fields.String(metadata={"description": "set (first value), changed, cleared, added or removed (relationships)"})


class HistoryEventOut(Schema):
    id = fields.Integer()
    at = fields.DateTime()
    by = fields.String()
    operation = fields.String(metadata={"description": "insert, update or delete"})
    version = fields.Integer()
    label = fields.String(allow_none=True)
    kind = fields.String(metadata={"description": "entity, attribute or relationship"})
    item = fields.String(allow_none=True)
    changes = fields.List(fields.Nested(HistoryChangeOut))
    action = fields.String(allow_none=True, metadata={"description": "created, when this event created the entity"})
    commit = fields.Dict(allow_none=True, metadata={"description": "The commit it came in with: number, message, by (D195)"})


class RuleResultOut(Schema):
    field = fields.String(metadata={"description": "The field, attribute or Relationships"})
    code = fields.String()
    rule = fields.String(metadata={"description": "Rule type code (required, mandatory, regex, has_relationship...)"})
    rule_name = fields.String()
    checks = fields.String(metadata={"description": "What the rule asks, in words"})
    severity = fields.String(metadata={"description": "error or warning"})
    status = fields.String(metadata={"description": "passed, failed or not_applicable"})
    message = fields.String(allow_none=True, metadata={"description": "Why it failed or did not apply"})
    value = fields.String(allow_none=True, metadata={"description": "The value checked (for a relationship rule: the matching relationships)"})


class RelationshipCheckOut(Schema):
    id = fields.UUID()
    relationship_type = fields.String()
    verb = fields.String()
    direction = fields.String()
    other_id = fields.UUID()
    other_name = fields.String()
    other_display_id = fields.String(allow_none=True)
    other_type = fields.String()
    status = fields.String(metadata={"description": "passed (the metamodel allows it) or failed"})
    severity = fields.String()
    message = fields.String(allow_none=True)


class RuleSummaryOut(Schema):
    checks = fields.Integer()
    passed = fields.Integer()
    failed = fields.Integer()
    errors = fields.Integer()
    warnings = fields.Integer()
    not_applicable = fields.Integer()


class EntityRulesOut(Schema):
    entity = fields.Dict()
    metamodel_version = fields.Integer()
    summary = fields.Nested(RuleSummaryOut)
    rules = fields.List(fields.Nested(RuleResultOut), metadata={"description": "Every rule applied, failed first"})
    relationships = fields.List(fields.Nested(RelationshipCheckOut), metadata={"description": "Each relationship: allowed by the metamodel or not"})


class EntityHistoryOut(Schema):
    entity = fields.Nested(EntityRefOut)
    events = fields.List(fields.Nested(HistoryEventOut))
    total = fields.Integer()


class HistoryQuery(Schema):
    limit = fields.Integer(load_default=500, validate=lambda n: 1 <= n <= 5000)


class GraphQuery(Schema):
    focus = fields.String(load_default=None, metadata={"description": "An entity (guid, display ID or name): it and its neighbours"})
    depth = fields.Integer(load_default=1, validate=lambda n: 1 <= n <= 10, metadata={"description": "Steps from the focus: 1 to 3; up to 6 with out, in or split; levels down (up to 10) with tree"})
    direction = fields.String(load_default="both", validate=lambda d: d in ("both", "out", "in", "split", "tree"),
                              metadata={"description": "With focus: both, out (impact), in (dependencies), split (in and out together) or tree (parents and parts)"})
    rel = fields.List(fields.String(), load_default=None, metadata={"description": "Only these relationship types (code, name or verb; Parent for the hierarchy); repeat for several"})
    type = fields.List(fields.String(), load_default=None, metadata={"description": "Or: every entity of these types; repeat for several"})
    limit = fields.Integer(load_default=300, validate=lambda n: 1 <= n <= 2000)


class GraphNodeOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    entity_type = fields.String()
    entity_type_id = fields.UUID()
    domain = fields.String()
    colour = fields.String()
    domain_order = fields.Integer()
    focus = fields.Boolean()
    distance = fields.Integer(allow_none=True, metadata={"description": "Steps from the focus (negative: before it, for split and tree)"})
    target = fields.Boolean(metadata={"description": "Paths: the entity the paths lead to"})


class GraphEdgeOut(Schema):
    id = fields.UUID()
    source = fields.UUID()
    target = fields.UUID()
    relationship_type_code = fields.String(metadata={"description": "Parent for the parent hierarchy"})
    relationship_type = fields.String()
    verb = fields.String()
    allowed = fields.Boolean()


class EntityGraphOut(Schema):
    model = fields.String()
    nodes = fields.List(fields.Nested(GraphNodeOut))
    edges = fields.List(fields.Nested(GraphEdgeOut))
    truncated = fields.Boolean(metadata={"description": "More entities would have been shown than the limit"})
    limit = fields.Integer()
    direction = fields.String()
    found = fields.Boolean(metadata={"description": "Paths: whether any path was found"})
    steps = fields.Integer(allow_none=True, metadata={"description": "Paths: steps on the shortest path"})
    paths = fields.List(fields.List(fields.UUID()), metadata={"description": "Paths: each as the guids of its entities, source first"})
    source = fields.Nested(EntityRefOut, allow_none=True)
    target = fields.Nested(EntityRefOut, allow_none=True)


class PathQuery(Schema):
    to = fields.String(required=True, metadata={"description": "The other entity (guid, display ID or name)"})
    steps = fields.Integer(load_default=6, validate=lambda n: 1 <= n <= 8, metadata={"description": "At most this many steps"})
    paths = fields.Integer(load_default=10, validate=lambda n: 1 <= n <= 50, metadata={"description": "At most this many paths"})
    rel = fields.List(fields.String(), load_default=None, metadata={"description": "Only these relationship types (Parent for the hierarchy)"})


class AsOfQuery(Schema):
    event = fields.Integer(load_default=None, metadata={"description": "A history event id (from .../history): the entity just after it"})
    at = fields.DateTime(load_default=None, metadata={"description": "Or a time: the entity as it was then"})


class AsOfPointOut(Schema):
    event_id = fields.Integer()
    at = fields.DateTime()
    by = fields.String()
    position = fields.Integer(metadata={"description": "Which recorded change this is, from the first"})
    of = fields.Integer()
    is_current = fields.Boolean()


class AsOfValueOut(Schema):
    code = fields.String()
    field = fields.String()
    name = fields.String()
    section = fields.String()
    then = fields.String(allow_none=True)
    now = fields.String(allow_none=True)
    changed = fields.Boolean(metadata={"description": "Then differs from now"})
    before = fields.String(allow_none=True, metadata={"description": "The old value: just before this moment"})
    changed_here = fields.Boolean(metadata={"description": "This moment changed it (from before to then)"})


class AsOfRelationshipOut(Schema):
    id = fields.UUID(allow_none=True)
    relationship_type = fields.String()
    verb = fields.String()
    direction = fields.String()
    other_id = fields.UUID(allow_none=True)
    other_name = fields.String()
    other_display_id = fields.String(allow_none=True)
    other_type = fields.String(allow_none=True)
    other_colour = fields.String(allow_none=True)
    relationship_type_code = fields.String(allow_none=True)
    still_there = fields.Boolean()
    added_here = fields.Boolean(metadata={"description": "This moment created the relationship"})


class AsOfMomentRelationshipOut(Schema):
    id = fields.UUID(allow_none=True)
    relationship_type = fields.String()
    verb = fields.String()
    direction = fields.String()
    other_name = fields.String()


class AsOfMomentOut(Schema):
    created = fields.Boolean(metadata={"description": "The entity was created at this moment"})
    changes = fields.Integer(metadata={"description": "Recorded changes in this moment"})
    removed_relationships = fields.List(fields.Nested(AsOfMomentRelationshipOut),
                                        metadata={"description": "Relationships this moment removed"})


class AsOfEntityOut(Schema):
    id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    entity_type = fields.String()
    model = fields.Nested(LineageModelOut)


class EntityAsOfOut(Schema):
    entity = fields.Nested(AsOfEntityOut)
    as_of = fields.Nested(AsOfPointOut)
    moment = fields.Nested(AsOfMomentOut, metadata={"description": "What this moment (one person, one second) changed"})
    fields_ = fields.List(fields.Nested(AsOfValueOut), data_key="fields", attribute="fields")
    attributes = fields.List(fields.Nested(AsOfValueOut))
    relationships = fields.List(fields.Nested(AsOfRelationshipOut), metadata={"description": "Its relationships then"})
    added_since = fields.List(fields.Nested(AsOfRelationshipOut), metadata={"description": "Relationships it has now that it did not have then"})


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
    domain_id = fields.UUID()
    domain = fields.String()
    colour = fields.String()
    entity_count = fields.Integer()
    attributes = fields.List(fields.Nested(DiagramAttributeOut))


class DiagramLinkOut(Schema):
    source = fields.UUID()
    target = fields.UUID()
    relationship_types = fields.List(fields.String(), metadata={"description": "Codes of the allowed relationship types"})
    source_multiplicities = fields.List(fields.String(), metadata={"description": "Source end of each, in the same order (D395)"})
    target_multiplicities = fields.List(fields.String(), metadata={"description": "Target end of each, in the same order (D395)"})


class MetamodelDiagram(Schema):
    model = fields.Nested(ModelOut)
    domains = fields.List(fields.Nested(DomainOut))
    entity_types = fields.List(fields.Nested(DiagramTypeOut))
    relationship_types = fields.List(fields.Nested(RelationshipTypeOut))
    links = fields.List(fields.Nested(DiagramLinkOut))


class MermaidQuery(Schema):
    domain = fields.List(fields.String(), load_default=None,
                        metadata={"description": "Domains to show (name or code); repeat for several. All when left out"})
    type = fields.String(load_default=None, metadata={"description": "Focus on this entity type and the types it may connect to"})
    rel = fields.List(fields.String(), load_default=None,
                      metadata={"description": "Relationship types to show; repeat for several. Default: all but Association and Specialization"})
    generic = fields.Boolean(load_default=False, metadata={"description": "Include Association and Specialization"})
    connected = fields.Boolean(load_default=False, metadata={"description": "Also show types in other domains that the chosen domains connect to"})
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
    keep = fields.Boolean(load_default=False, metadata={"description": "Commit at the end (keep the changes); otherwise rolled back"})


class SqlResultSet(Schema):
    columns = fields.List(fields.String())
    rows = fields.List(fields.List(fields.Raw()))
    row_count = fields.Integer(allow_none=True)
    truncated = fields.Boolean()
    status = fields.String()


class SqlQueryOut(Schema):
    results = fields.List(fields.Nested(SqlResultSet))
    notices = fields.List(fields.String())
    committed = fields.Boolean(metadata={"description": "True when the changes were kept (keep), false when rolled back"})
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
