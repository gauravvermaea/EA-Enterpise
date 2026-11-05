"""Long work in the background, followed until done (D192): GET /tasks (yours), GET /tasks/<id>."""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import tasks as tk
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free

blp = Blueprint("tasks", __name__, url_prefix="/api/v1", description="Background tasks (D192)")
SECURITY = [{"bearerAuth": []}]


@blp.route("/tasks")
class Tasks(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "active", "schema": {"type": "boolean"},
                                             "description": "only running ones and those finished in the last ten minutes"}])
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Your background tasks, newest first: what, status (queued, running, done, failed) and the outcome in words"""
        with get_engine().connect() as conn:
            return tk.mine(conn, g.user, request.args.get("active") == "true")


@blp.route("/tasks/<task_id>")
class Task(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, task_id):
        """One background task: follow it until done is true; message says what happened"""
        try:
            with get_engine().connect() as conn:
                return tk.get(conn, g.user, task_id)
        except EditError as exc:
            abort(exc.status, message=str(exc))
