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
