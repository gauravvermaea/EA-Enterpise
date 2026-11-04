"""Changing a model's metamodel, its versions and history, failing checks and model locks (build phase 3).

Writes go through eax.metamodel_edit (one change = one new metamodel version, D72); reads through
eax.repository. Every write is audited. Only Model Admins and Super Admins change a metamodel or
lock a model (D89, phase 3.1), checked here and again by the database. Templates and reference
models are refused by the database whoever asks.
"""

from __future__ import annotations

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import INCLUDE, Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import metamodel_edit as ed
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine

blp = Blueprint("metamodel-edit", __name__, url_prefix="/api/v1/models",
                description="Change a model's metamodel; its versions, history and failing checks; model locks")
SECURITY = [{"bearerAuth": []}]


class ChangeIn(Schema):
    class Meta:
        unknown = INCLUDE   # the change's own fields (see eax/metamodel_edit.py)
    op = fields.String(required=True, metadata={"description": "entity_type.create, attribute.create, attribute.update, "
                                                               "mapping.add, rule.create ... (see the module docs)"})
    dry_run = fields.Boolean(load_default=False, metadata={"description": "Show what the change would do, without saving it"})


class ImpactRowOut(Schema):
    entity_id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    rule = fields.String()
    field = fields.String()
    severity = fields.String()


class ImpactOut(Schema):
    summary = fields.List(fields.String())
    newly_failing = fields.List(fields.Nested(ImpactRowOut))
    now_passing = fields.List(fields.Nested(ImpactRowOut))
    newly_failing_count = fields.Integer()
    now_passing_count = fields.Integer()


class ChangeOut(Schema):
    model = fields.String()
    op = fields.String()
    version = fields.Integer(metadata={"description": "The metamodel version this change publishes (not kept when dry_run)"})
    note = fields.String()
    dry_run = fields.Boolean()
    result = fields.Dict()
    impact = fields.Nested(ImpactOut)


class VersionOut(Schema):
    id = fields.UUID()
    version = fields.Integer()
    note = fields.String()
    changed_at = fields.DateTime()
    changed_by = fields.String()
    changes = fields.Integer()


class FieldChangeOut(Schema):
    field = fields.String()
    old = fields.String(allow_none=True)
    new = fields.String(allow_none=True)


class MmChangeOut(Schema):
    kind = fields.String()
    table = fields.String()
    item = fields.String()
    change = fields.String(metadata={"description": "added, changed, retired, restored or removed"})
    fields_ = fields.List(fields.Nested(FieldChangeOut), data_key="fields", attribute="fields")
    at = fields.DateTime()
    by = fields.String()
    history_id = fields.Integer()


class CountOut(Schema):
    kind = fields.String()
    count = fields.Integer()


class HistoryVersionOut(VersionOut):
    items = fields.List(fields.Nested(MmChangeOut))
    counts = fields.List(fields.Nested(CountOut))


class MmHistoryOut(Schema):
    model = fields.String()
    current_version = fields.Integer()
    versions = fields.List(fields.Nested(HistoryVersionOut))


class CompareQuery(Schema):
    from_ = fields.Integer(required=True, data_key="from", metadata={"description": "The earlier version"})
    to = fields.Integer(load_default=None, metadata={"description": "The later version (default: the current one)"})


class CompareOut(Schema):
    model = fields.String()
    from_version = fields.Integer()
    to_version = fields.Integer()
    items = fields.List(fields.Nested(MmChangeOut))
    summary = fields.List(fields.Dict())


class PickValueOut(Schema):
    id = fields.UUID()
    value = fields.String()
    status = fields.String()


class PickListOut(Schema):
    id = fields.UUID()
    code = fields.String()
    name = fields.String()
    description = fields.String()
    values = fields.List(fields.Nested(PickValueOut))


class FailingRowOut(Schema):
    entity_id = fields.UUID()
    display_id = fields.String()
    name = fields.String()
    entity_type = fields.String()
    entity_type_id = fields.UUID(allow_none=True)
    colour = fields.String()
    rule = fields.String()
    field = fields.String()
    severity = fields.String()
    message = fields.String()
    created_mm_version = fields.Integer(allow_none=True)
    modified_mm_version = fields.Integer(allow_none=True)


class NameCountOut(Schema):
    name = fields.String()
    count = fields.Integer()


class FailingOut(Schema):
    model = fields.String()
    metamodel_version = fields.Integer()
    rows = fields.List(fields.Nested(FailingRowOut))
    entities = fields.Integer()
    failures = fields.Integer()
    by_type = fields.List(fields.Nested(NameCountOut))
    by_rule = fields.List(fields.Nested(NameCountOut))
    by_severity = fields.List(fields.Nested(NameCountOut))


class FailingQuery(Schema):
    type = fields.String(load_default=None, metadata={"description": "Only this entity type (guid, code or name)"})


class LockIn(Schema):
    level = fields.String(required=True, metadata={"description": "metamodel, content (metamodel and content) or maintenance"})
    reason = fields.String(load_default="")


class LockOut(Schema):
    id = fields.UUID()
    name = fields.String()
    lock_level = fields.String()
    lock_reason = fields.String()
    locked_at = fields.DateTime(allow_none=True)
    locked_by = fields.String(allow_none=True)


def _read(fn, *args, **kwargs):
    with get_engine().connect() as conn:
        try:
            return fn(conn, *args, **kwargs)
        except repo.NotFound as exc:
            abort(404, message=str(exc))


def _write(model_id, action: str, details: dict, fn, *args, dry_run: bool = False, **kwargs):
    """Runs a change in one transaction: rolled back for a dry run, otherwise committed with an audit event."""
    engine = get_engine()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            result = fn(conn, *args, **kwargs)
        except ed.EditError as exc:
            trans.rollback()
            abort(exc.status, message=str(exc))
        except repo.NotFound as exc:
            trans.rollback()
            abort(404, message=str(exc))
        except DBAPIError as exc:
            trans.rollback()
            # insufficient_privilege: the database's own permission check (phase 3.1)
            abort(403 if getattr(getattr(exc, "orig", None), "sqlstate", None) == "42501" else 409,
                  message=ed._db_message(exc))
        if dry_run:
            trans.rollback()
            return result
        audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(model_id),
                     source="api", request_id=getattr(g, "request_id", None),
                     details={**details, **({"version": result.get("version"), "note": result.get("note")}
                                            if isinstance(result, dict) and "version" in result else {})})
        trans.commit()
        return result


@blp.route("/<uuid:model_id>/metamodel/changes")
class MetamodelChange(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(ChangeIn)
    @blp.response(200, ChangeOut)
    @require_auth("model.metamodel")
    def post(self, body, model_id):
        """Make one change to a project model's metamodel (or, with dry_run, see what it would do)

        Each change publishes a new metamodel version at once with a note saying what it was. The
        impact lists the entities that will fail (or pass) checks because of it: it never blocks the
        change (D64). Adding a mandatory attribute takes a default value (empty allowed) and
        `apply_default_to_existing` puts it on the entities that have none.
        """
        body = dict(body)
        op, dry = body.pop("op"), body.pop("dry_run", False)
        return _write(model_id, "metamodel.change", {"op": op, "fields": body},
                      ed.apply, model_id, op, body, g.user.username, dry, dry_run=dry)


@blp.route("/<uuid:model_id>/metamodel/versions")
class MetamodelVersions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, VersionOut(many=True))
    @require_auth()
    def get(self, model_id):
        """The published versions of the model's metamodel, newest first"""
        return _read(repo.metamodel_versions, model_id)


@blp.route("/<uuid:model_id>/metamodel/history")
class MetamodelHistory(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, MmHistoryOut)
    @require_auth()
    def get(self, model_id):
        """Every change to the metamodel, grouped by version: what, old and new values, who and when"""
        return _read(repo.metamodel_history, model_id)


@blp.route("/<uuid:model_id>/metamodel/compare")
class MetamodelCompare(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(CompareQuery, location="query")
    @blp.response(200, CompareOut)
    @require_auth()
    def get(self, query, model_id):
        """What differs between two versions of the metamodel (`to` defaults to the current version)"""
        return _read(repo.metamodel_compare, model_id, query["from_"], query["to"])


@blp.route("/<uuid:model_id>/metamodel/pick-lists")
class PickLists(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, PickListOut(many=True))
    @require_auth()
    def get(self, model_id):
        """The model's pick lists and their values"""
        return _read(repo.list_pick_lists, model_id)


@blp.route("/<uuid:model_id>/checks")
class FailingChecks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FailingQuery, location="query")
    @blp.response(200, FailingOut)
    @require_auth()
    def get(self, query, model_id):
        """Every entity failing a check (rules, mandatory values, relationships outside the metamodel)"""
        return _read(repo.failing_checks, model_id, query["type"])


@blp.route("/<uuid:model_id>/lock")
class ModelLock(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(LockIn)
    @blp.response(200, LockOut)
    @require_auth("model.lock")
    def put(self, body, model_id):
        """Lock the model: metamodel (metamodel read-only), content (metamodel and content read-only) or
        maintenance (only you may change it until you lift the lock)"""
        return _write(model_id, "model.lock", body, ed.set_lock, model_id, body["level"], body["reason"], g.user.username)

    @blp.doc(security=SECURITY)
    @blp.response(200, LockOut)
    @require_auth("model.lock")
    def delete(self, model_id):
        """Lift the model's lock"""
        return _write(model_id, "model.unlock", {}, ed.clear_lock, model_id, g.user.username)
