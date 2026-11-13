"""Archive (R2.41, D626): models moved out of the working database into the archive database, and back.

GET  /models/<m>/archive/references       what refers to the model, and what stops it moving
POST /models/<m>/archive {state, note}    archived (its Model Admin) or deleted (a Super Admin): a background task
GET  /archive?kind=model&deleted=1         the archive (deleted ones for Super Admins only)
POST /archive/<id>/restore                 back to Active (its admins; a deleted one: a Super Admin): a background task
POST /archive/<id>/purge {confirm}         gone for good (a Super Admin)
GET  /archive/<id>/download                its backup file
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import archive as ar
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn
from .tasks import start

blp = Blueprint("archive", __name__, url_prefix="/api/v1", description="Archive: archived and deleted models (R2.41)")
SECURITY = [{"bearerAuth": []}]


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except EditError as exc:
        abort(exc.status, message=str(exc))


@blp.route("/models/<model_id>/archive/references")
class References(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """What refers to the model (derived models, copies, projects, open merge requests) and what stops it moving"""
        with get_engine().connect() as conn:
            return _guard(ar.references, conn, model_id)


@blp.route("/models/<model_id>/archive")
class Move(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, model_id):
        """Archive {state: archived} (its Model Admin) or delete {state: deleted} (a Super Admin) the model: it leaves the
        working database for the archive, in the background (D273)"""
        data = data or {}
        state = data.get("state") if data.get("state") in ("archived", "deleted") else "archived"
        with get_engine().connect() as conn:                 # checked now, so the task is not even started when refused
            m = _guard(repo.get_model, conn, model_id)
            _guard(ar._may_move, conn, g.user, m, state)
            refs = ar.references(conn, model_id)
        if refs["blocking"]:
            abort(409, message=f"{m['name']} cannot move while " + "; ".join(refs["blocking"]) + ".")
        return start("archive.move", None, f"{'Archive' if state == 'archived' else 'Delete'} {m['name']}",
                     {"model": str(m["id"]), "state": state, "note": str(data.get("note") or "")[:2000]}, "#/archive")


@blp.route("/projects/<project_id>/archive/references")
class ProjectReferences(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project_id):
        """A project's models: those that move with it (only it uses them) and those that stay"""
        from .. import projects as pj
        with pj.connections(write=False) as pc:
            return _guard(ar.project_references, pc, project_id)


@blp.route("/projects/<project_id>/archive")
class ProjectMove(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, project_id):
        """Archive {state: archived} (its Project Admin) or delete {state: deleted} (a Super Admin) the project with its
        documents and the models only it uses, in the background"""
        from .. import project_backup as pb
        from .. import projects as pj
        data = data or {}
        state = data.get("state") if data.get("state") in ("archived", "deleted") else "archived"
        with pj.connections(write=False) as pc:
            p = _guard(pj.project_row, pc, project_id)
            if state == "deleted" and not ar._is_super(g.user):
                abort(403, message="Only a Super Admin deletes a project.")
            _guard(pb.need_manage, pc, p, g.user)
        return start("archive.project_move", None, f"{'Archive' if state == 'archived' else 'Delete'} {p['name']}",
                     {"project": str(p["guid"]), "state": state, "note": str(data.get("note") or "")[:2000]}, "#/archive")


@blp.route("/archive")
class Listing(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The archive: archived models (their admins and Super Admins); ?deleted=1 adds the deleted ones (Super Admins)"""
        with get_engine().connect() as conn:
            kind = "project" if request.args.get("kind") == "project" else "model"
            rows = ar.listing(conn, g.user, kind, request.args.get("deleted") == "1")
        return {"items": rows, "super_admin": ar._is_super(g.user)}


@blp.route("/archive/<int:ident>/restore")
class Restore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth()
    def post(self, ident):
        """Back to Active: the model made again from its file (its admins; a deleted one: a Super Admin), in the background"""
        with get_engine().connect() as conn:
            r = _guard(ar._row, conn, ident)
        return start("archive.restore", None, f"Bring back {r['name']}", {"id": ident, "kind": r["kind"]}, "#/archive")


@blp.route("/archive/<int:ident>/purge")
class Purge(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, ident):
        """Gone for good {confirm: "DELETE"}: a Super Admin"""
        if (data or {}).get("confirm") != "DELETE":
            abort(400, message="Type DELETE to confirm: a purged model cannot be brought back.")
        with get_engine().begin() as conn:
            return _guard(ar.purge, conn, g.user, ident)


@blp.route("/archive/<int:ident>/download")
class Download(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, ident):
        """Its backup file (.eaxbackup.zip): restore it elsewhere, or read its workbook"""
        with get_engine().connect() as conn:
            data, name = _guard(ar.download, conn, g.user, ident)
        return Response(data, mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
