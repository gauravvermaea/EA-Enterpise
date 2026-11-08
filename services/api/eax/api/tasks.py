"""Long work in the background, followed until done (D192, D273): GET /tasks (yours), GET /tasks/<id>.

start() is what every slow button's route calls: it records the task (with the uploaded file, if any), queues it for
the job runner and answers {"task": ...} at once; the screen follows it and the task drawer shows it. Without a job
runner the work is done in the request (the answer is the finished task). ?wait=true on such a route does the work in
the request as before (scripts and tests)."""

from __future__ import annotations

import logging

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import tasks as tk
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

log = logging.getLogger(__name__)
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
            if request.args.get("history") == "true":
                return tk.mine(conn, g.user, history=True, limit=int(request.args.get("limit") or 50),
                               offset=int(request.args.get("offset") or 0))
            return tk.mine(conn, g.user, request.args.get("active") == "true")

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, data):
        """Delete your finished tasks from your history: {ids: [...]} for some, or {all: true} for every one"""
        d = data or {}
        if not d.get("all") and not d.get("ids"):
            abort(400, message="Give ids, or all: true.")
        try:
            with get_engine().connect() as conn, conn.begin():
                return tk.delete_history(conn, g.user, None if d.get("all") else d.get("ids"))
        except EditError as exc:
            abort(exc.status, message=str(exc))


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


def waiting() -> bool:
    """?wait=true: do the work in the request (as before D273)."""
    return request.args.get("wait") == "true"


def start(kind: str, model_id, label: str, params: dict, link: str = "",
          inputs: list[tuple[str, str, bytes]] | None = None, user=None) -> dict:
    """Queues slow work for the job runner (D273) and answers {"task": ...} at once."""
    user = user or g.user
    try:
        with get_engine().connect() as conn, conn.begin():
            task = tk.create(conn, kind, model_id, user, label, params, link, inputs)
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except Exception as exc:  # noqa: BLE001 - an unknown model and the like
        abort(404 if exc.__class__.__name__ == "NotFound" else 400, message=str(exc))
    try:
        from ..jobs import app as jobs_app
        from ..jobs import run_task
        with jobs_app.open():
            job = run_task.defer(task_id=task["id"], actor=user.username, roles=list(user.roles))
        with get_engine().connect() as conn, conn.begin():
            tk.set_job(conn, task["id"], job)
    except Exception:  # noqa: BLE001
        log.warning("job runner not reachable; %s done in the request", kind)
        tk.run(task["id"], user.username, list(user.roles))
    with get_engine().connect() as conn:
        return {"task": tk.get(conn, user, task["id"])}


def upload(field: str = "file", limit: int = 200 * 1024 * 1024) -> tuple[str, str, bytes]:
    """The uploaded file of a request, as an input of a task."""
    f = request.files.get(field)
    if f is None:
        abort(400, message=f"Send the file as the form field '{field}'.")
    data = f.read(limit + 1)
    if len(data) > limit:
        abort(413, message=f"The file is larger than {limit // (1024 * 1024)} MB.")
    return (f.filename or "upload", f.mimetype or "application/octet-stream", data)
