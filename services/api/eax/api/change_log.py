"""Phase 9: the change log (D180), kept in its own database (EAX_CHANGELOG_DB_URL). Everyone sees their own changes,
a Model Admin every change in the models they administer, a Super Admin every change; only a Super Admin exports or
deletes rows (eax/change_log.py)."""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from .. import change_log as cl
from ..auth import require_auth
from ..db import get_changelog_engine, get_engine
from ..metamodel_edit import EditError
from .models import Free

blp = Blueprint("change_log", __name__, url_prefix="/api/v1/change-log", description="The change log (phase 9)")
SECURITY = [{"bearerAuth": []}]
FILTERS = ("q", "model", "user", "kind", "action", "item_type", "from", "to", "mine")
QUERY_DOC = [{"in": "query", "name": k, "schema": {"type": "string"}} for k in FILTERS]


class DeleteIn(Schema):
    q = fields.String(load_default=None)
    model = fields.String(load_default=None)
    user = fields.String(load_default=None)
    kind = fields.String(load_default=None)
    action = fields.String(load_default=None)
    item_type = fields.String(load_default=None)
    to = fields.String(load_default=None, metadata={"description": "Up to and including this date (YYYY-MM-DD)"})
    mine = fields.Boolean(load_default=False)
    confirm = fields.String(required=True, metadata={"description": "The word DELETE"})

    class Meta:
        include = {"from": fields.String(load_default=None, data_key="from")}


def _filters() -> dict:
    f = {k: request.args.get(k) for k in FILTERS if request.args.get(k)}
    f["mine"] = request.args.get("mine") in ("1", "true", "yes")
    return f


def _run(fn, write: bool = False):
    """fn(conn, cl): the repository (who administers which model) and the change log's own database (D180).
    New changes are shipped first, so the screen is up to date even between the shipper's rounds."""
    try:
        cl.ship_now(limit=20_000)
    except Exception:  # noqa: BLE001 - the background shipper tries again; the screen shows what is there
        pass
    try:
        with get_engine().connect() as conn, get_changelog_engine().connect() as log:
            if not write:
                return fn(conn, log)
            with log.begin():
                return fn(conn, log)
    except EditError as exc:
        abort(exc.status, message=str(exc))


@blp.route("")
class ChangeLog(MethodView):
    @blp.doc(security=SECURITY, parameters=[*QUERY_DOC, {"in": "query", "name": "limit", "schema": {"type": "integer"}},
                                            {"in": "query", "name": "offset", "schema": {"type": "integer"}}])
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The change log as you may see it (your own; every change of models you administer; Super Admin: all), newest first"""
        return _run(lambda c, log: cl.entries(c, g.user, _filters(), request.args.get("limit", type=int) or cl.LIMIT,
                                              request.args.get("offset", type=int) or 0, cl=log))


@blp.route("/export")
class ChangeLogExport(MethodView):
    @blp.doc(security=SECURITY, parameters=[*QUERY_DOC, {"in": "query", "name": "format", "schema": {"type": "string", "enum": ["csv", "xlsx"]}}])
    @require_auth()
    def get(self):
        """Every change log row the filters select, as CSV or Excel (Super Admin). ?background=true: made in the
        background (D273), downloaded from the task"""
        if request.args.get("background") == "true":
            from . import tasks as api_tasks
            fmt = "xlsx" if request.args.get("format") == "xlsx" else "csv"
            return api_tasks.start("changelog.export", None, f"Export the change log ({fmt})",
                                   {"filters": _filters(), "format": fmt}, "#/change-log")
        data, name, ctype = _run(lambda c, log: cl.export(c, g.user, _filters(), request.args.get("format", "csv"), cl=log))
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@blp.route("/delete")
class ChangeLogDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DeleteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Deletes the change log rows the filters select, or every row (Super Admin; confirm = DELETE). The history,
        roll back and the audit trail are kept; the deletion is logged"""
        if data.pop("confirm", "") != "DELETE":
            abort(400, message="Type DELETE to confirm.")
        return _run(lambda c, log: cl.delete(c, g.user, data, cl=log), write=True)
