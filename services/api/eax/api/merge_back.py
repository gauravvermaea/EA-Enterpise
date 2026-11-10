"""Merge requests, dedupe and sample documents (batch 1, D421: phases 19 and 20, 21 and the Other views and documents tab).

Merging a child into its parent (D359, D422 to D425):
GET  /models/<m>/merge-requests                 the model's requests: sent (as a child) and received (as a parent)
GET  /models/<m>/merge-requests/preview         what sending the child would ask the parent's reviewers (nothing kept)
POST /models/<m>/merge-requests                 {note}: the child's Model Admin sends it (a background task, ?wait=true)
GET  /merge-requests/waiting                    requests waiting for me: to review, or to freeze or refresh the child
GET  /merge-requests/<r>                        one request: its changes, decisions and report
POST /merge-requests/<r>/decisions              {decisions: {change id: {accept, reason}}}: the parent's reviewers
POST /merge-requests/<r>/merge                  everything accepted into the parent (a background task, ?wait=true)
POST /merge-requests/<r>/withdraw               {note}: the sender takes it back while it waits for review
POST /merge-requests/<r>/finish                 {choice: freeze | refresh, note}: the child's Model Admin, after the merge
GET  /merge-requests/<r>/report                 the merge report as a Word document

Dedupe (D361, D426 to D428; the find and merge routes are in model_wizards):
POST /models/<m>/duplicates/compare             {ids, keep}: a pair or group side by side
GET  /models/<m>/content/similar?entity_type=&name=&entity=&all_types=&limit=   names that look like this one (data entry, drawn views)

Other views and documents (D415, D429):
GET  /sample-documents                          the sample templates
GET  /sample-documents/<code>                   one, made as it is downloaded
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import dedupe as dd
from .. import merge_back as mb
from .. import repository as repo
from .. import sample_documents as sd
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn
from .tasks import start, waiting

blp = Blueprint("merge_back", __name__, url_prefix="/api/v1",
                description="Merge a child into its parent, dedupe, sample documents (batch 1, D421)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, object_id, details=None, object_type: str = "model"):
    try:
        with get_engine().connect() as conn, conn.begin():
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type=object_type, object_id=str(object_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
            return out
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


def _request_models(rid) -> tuple[str, str, int]:
    """The child's and the parent's guids and the request's number (to start a task on the right model)."""
    def go(conn):
        r = mb._request(conn, rid)
        return str(mb._model_row(conn, r["child_id"])["id"]), str(mb._model_row(conn, r["parent_id"])["id"]), r["number"]
    return _read(go)


# ---------------------------------------------------------------- merge requests
@blp.route("/models/<uuid:model_id>/merge-requests")
class MergeRequests(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's merge requests: those it sent as a child and those sent to it as a parent"""
        return _read(lambda c: mb.listing(c, model_id, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Send the child for merge into its parent (its Model Admin): the changes are worked out three-way and the parent's
        reviewers are told"""
        note = (data or {}).get("note", "")
        if not waiting():
            return start("mergeback.send", model_id, "Send for merge into the parent", {"note": note}, f"#/model-admin/{model_id}/merge-requests")
        return _write(lambda c: mb.send(c, model_id, g.user, note), "merge_request.sent", model_id)


@blp.route("/models/<uuid:model_id>/merge-requests/preview")
class MergePreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """What sending the child would ask its parent's reviewers: the changes found, three-way; nothing is kept"""
        return _read(lambda c: mb.preview(c, model_id, g.user))


@blp.route("/merge-requests/waiting")
class MergeWaiting(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Merge requests waiting for me: to review, or to freeze or refresh the child after the merge"""
        return _read(lambda c: {"requests": mb.waiting_for(c, g.user)})


@blp.route("/merge-requests/<uuid:request_id>")
class MergeRequest(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, request_id):
        """One merge request: the changes found, each decision and the report"""
        return _read(lambda c: mb.get(c, request_id, g.user))


@blp.route("/merge-requests/<uuid:request_id>/decisions")
class MergeDecisions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, request_id):
        """The parent's reviewers accept or reject changes ({change id: {accept, reason}}; a rejection needs a reason;
        accept null takes a decision back)"""
        d = (data or {}).get("decisions") or {}
        return _write(lambda c: mb.decide(c, request_id, g.user, d), "merge_request.decided", request_id,
                      {"changes": len(d)}, "merge_request")


@blp.route("/merge-requests/<uuid:request_id>/merge")
class MergeDo(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, request_id):  # noqa: ARG002
        """Merge everything accepted into the parent: tagged first, one commit, the report kept"""
        child, parent, number = _request_models(request_id)
        if not waiting():
            return start("mergeback.merge", parent, f"Merge request {number} into the parent", {"request": str(request_id)},
                         f"#/merge-requests/{request_id}")
        return _write(lambda c: mb.merge(c, request_id, g.user), "merge_request.merged", request_id, {}, "merge_request")


@blp.route("/merge-requests/<uuid:request_id>/withdraw")
class MergeWithdraw(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, request_id):
        """The sender takes the request back while it waits for review"""
        return _write(lambda c: mb.withdraw(c, request_id, g.user, (data or {}).get("note", "")), "merge_request.withdrawn",
                      request_id, {}, "merge_request")


@blp.route("/merge-requests/<uuid:request_id>/finish")
class MergeFinish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, request_id):
        """After the merge, the child's Model Admin: freeze the child, or refresh it from the parent and carry on"""
        d = data or {}
        child, _parent, number = _request_models(request_id)
        if not waiting():
            return start("mergeback.finish", child, f"{'Freeze' if d.get('choice') == 'freeze' else 'Refresh'} the child of merge request {number}",
                         {"request": str(request_id), "choice": d.get("choice", ""), "note": d.get("note", "")}, f"#/merge-requests/{request_id}")
        return _write(lambda c: mb.finish(c, request_id, g.user, d.get("choice", ""), d.get("note", "")), "merge_request.closed",
                      request_id, {"choice": d.get("choice")}, "merge_request")


@blp.route("/merge-requests/<uuid:request_id>/report")
class MergeReport(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, request_id):
        """The merge report as a Word document: accepted, rejected with the reasons, anything not applied"""
        data, name = _read(lambda c: mb.report_docx(c, request_id, g.user))
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- dedupe
@blp.route("/models/<uuid:model_id>/duplicates/compare")
class DuplicatesCompare(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """A pair or group of likely duplicates side by side, and what merging them into one would move"""
        d = data or {}
        return _read(lambda c: dd.compare(c, model_id, d.get("ids") or [], d.get("keep")))


@blp.route("/models/<uuid:model_id>/content/similar")
class SimilarNames(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Entities of a type whose names look like this one (data entry warns before a duplicate is made)"""
        a = request.args
        return _read(lambda c: dd.similar_names(c, model_id, a.get("entity_type", ""), a.get("name", ""), a.get("entity") or None,
                                                limit=int(a.get("limit") or 5) if str(a.get("limit") or "5").isdigit() else 5,
                                                all_types=a.get("all_types") in ("1", "true", "yes")))


# ---------------------------------------------------------------- other views and documents
@blp.route("/sample-documents")
class SampleDocuments(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Sample document templates for views and documents outside TOGAF and ArchiMate"""
        return sd.listing()


@blp.route("/sample-documents/<string:code>")
class SampleDocument(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, code):
        """One sample template, made as it is downloaded"""
        try:
            data, name, ctype = sd.make(code)
        except EditError as exc:
            abort(exc.status, message=str(exc))
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{name}"'})
