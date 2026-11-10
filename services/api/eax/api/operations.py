"""Operations insight and housekeeping (phases 35 and 35.1, D371): usage, database health, retention rules, housekeeping
runs and the archive, for IT Admins and Super Admins. The Prometheus metrics are at /api/metrics (app.py)."""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import operations as ops
from ..auth import require_auth
from ..db import get_engine
from .models import Free, FreeIn

blp = Blueprint("operations", __name__, url_prefix="/api/v1/operations",
                description="Operations insight and housekeeping (phases 35 and 35.1)")
SECURITY = [{"bearerAuth": []}]


def _do(fn, write: bool = False):
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except ops.NotConfirmed as exc:
        abort(409, message=str(exc))
    except PermissionError as exc:
        abort(403, message=str(exc))
    except LookupError as exc:
        abort(404, message=str(exc))
    except ValueError as exc:
        abort(422, message=str(exc))


@blp.route("/usage")
class Usage(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Who uses what and how often; models' use and size; idle models (a report only); stale work and old loads"""
        ops.flush()
        return _do(lambda c: ops.insight(c, int(request.args.get("days") or 30)))


@blp.route("/database")
class Database(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Database health: the largest tables, the slowest queries, when tables were last tidied"""
        return _do(ops.db_health)


@blp.route("/retention")
class Retention(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The retention rules, whether housekeeping may act, and the runs"""
        return _do(lambda c: {"rules": ops.rules(c), "state": ops.state(c), "runs": ops.runs(c)})


@blp.route("/retention/<code>")
class RetentionRule(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data, code):
        """Set a rule: {action: keep | archive | delete, after_days}. Housekeeping then waits for a new dry run."""
        return _do(lambda c: ops.set_rule(c, g.user.username, code, (data or {}).get("action", ""),
                                          (data or {}).get("after_days") or 0, g.user.roles), write=True)


@blp.route("/housekeeping/run")
class HousekeepingRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Run housekeeping now: {dry_run: true} (always allowed) or a real run (only once a dry run is confirmed)"""
        dry = (data or {}).get("dry_run", True) is not False
        return _do(lambda c: ops.run(c, g.user.username, dry_run=dry), write=True)


@blp.route("/housekeeping/runs/<run_id>/confirm")
class HousekeepingConfirm(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, run_id):
        """Confirm a dry run: from now on the nightly run acts on these rules"""
        return _do(lambda c: ops.confirm(c, g.user.username, run_id), write=True)


@blp.route("/archive")
class Archive(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Search the archive: ?q=words&rule=loads"""
        a = request.args
        return _do(lambda c: ops.archive_search(c, a.get("q", ""), a.get("rule", ""), int(a.get("limit") or 100)))


@blp.route("/archive/<int:item>")
class ArchivedItem(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, item):
        """One archived item as it was"""
        return _do(lambda c: ops.archived_item(c, item))


@blp.route("/archive/<int:item>/file")
class ArchivedFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, item):
        """An archived item's file (a load's sheet, a task's file)"""
        data, name, ctype = _do(lambda c: ops.archived_file(c, item))
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")[:120] or "archived"
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{safe}"'})
