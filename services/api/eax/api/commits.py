"""Commits, change sets, merges and draft decisions (build phase 8, D165, D151).

GET  /models/<m>/changes                      the Changes tab: my uncommitted changes, requests waiting for me
POST /models/<m>/changes/request              ask the model's committers to commit my changes
POST /models/<m>/changes/withdraw             take a request back
POST /models/<m>/changes/commit               commit (committers): my changes, or a requested set; 409 with the conflicts
POST /models/<m>/changes/reject               reject requested changes (committers)
POST /models/<m>/changes/send-back            send a requested set back with a note (committers)
POST /models/<m>/changes/discard              discard my own uncommitted changes
POST /models/<m>/changes/batch                several content changes at once (diagram saves, tools): recorded as my
                                              uncommitted changes in a project model, applied at once elsewhere
GET  /models/<m>/commits                      commits: mine, or everyone's with History Viewer or Model Admin (D151)
GET  /models/<m>/commits/latest               the last commit (open pages show when someone commits, E37)
GET  /models/<m>/commits/<id>                 one commit and what each item changed
POST /models/<m>/commits/<id>/roll-back       undo a commit, whole or items, as a new commit (committers)
GET  /models/<m>/merge-test-file              a package made from this model to try merging with (zip or Excel)
POST /models/<m>/merges                       upload a model to merge into this one: the plan
POST /models/<m>/merges/<id>/apply            apply it with the decisions: my uncommitted changes
POST /models/<m>/merges/<id>/cancel
POST /models/<m>/reject-publish               reject a requested draft model (its approvers)
POST /models/<m>/reopen                       open a rejected draft again (its Model Admin)
GET  /drafts/waiting                          draft models waiting for my approval
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import commits as cm
from .. import merge as mg
from .. import model_ops as mo
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free

blp = Blueprint("commits", __name__, url_prefix="/api/v1",
                description="Commits of content, change sets, merges and draft decisions (phase 8)")
SECURITY = [{"bearerAuth": []}]


class ChangesIn(Schema):
    set = fields.String(load_default=None, metadata={"description": "A change set id; empty: my own uncommitted changes"})
    changes = fields.List(fields.String(), load_default=None, metadata={"description": "Only these changes; empty: all"})
    note = fields.String(load_default="")
    message = fields.String(load_default="", metadata={"description": "The commit message"})
    resolutions = fields.Dict(load_default=None, metadata={"description": "change id: skip | mine | {fields: {field: mine | theirs | "
                                                                          "{value: ...}}}"})


class RollBackIn(Schema):
    items = fields.List(fields.Integer(), load_default=None, metadata={"description": "Only these items; empty: the whole commit"})
    force = fields.Boolean(load_default=False, metadata={"description": "Roll back although the targets changed since"})
    message = fields.String(load_default="")


class MergeApplyIn(Schema):
    decisions = fields.Dict(load_default=None, metadata={"description": "conflict id: mine | theirs | {value: ...}"})
    all_conflicts = fields.String(load_default="", metadata={"description": "mine or theirs for every conflict not decided"})
    add_metamodel = fields.Boolean(load_default=False, metadata={"description": "Add the missing types and attributes (Model Admins)"})


class BatchIn(Schema):
    changes = fields.List(fields.Dict(), required=True, metadata={"description": (
        "[{op, args}] in order. op: entity.create {data} | entity.update {entity, data} | entity.status {entity, status} | "
        "entity.delete {entity} | relationship.create {data} | relationship.delete {relationship} | relationship.rename "
        "{relationship, name}. A new entity or relationship may carry data.guid (a diagram shape's id), so later "
        "changes in the same batch refer to it")})


class NoteIn(Schema):
    note = fields.String(load_default="")


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, model_id, details=None):
    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            try:
                out = fn(conn)
            except Exception:
                trans.rollback()
                raise
            audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(model_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
            trans.commit()
            return out
    except cm.CommitConflict as exc:
        abort(409, message=str(exc), errors={"conflicts": exc.conflicts})
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


# ---------------------------------------------------------------- change sets
@blp.route("/models/<uuid:model_id>/changes")
class Changes(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """My uncommitted changes (by change set) and, if I may commit, the changes others asked to commit;
        ?entity=<id> only those to one entity and its relationships (the entity page)"""
        return _read(lambda c: cm.changes_page(c, model_id, g.user, request.args.get("entity") or None))


def _step(name: str, fn, permission: str | None = None):
    class Step(MethodView):
        @blp.doc(security=SECURITY)
        @blp.arguments(ChangesIn)
        @blp.response(200, Free)
        @require_auth(permission)
        def post(self, data, model_id):
            return _write(lambda c: fn(c, model_id, data), f"changes.{name}", model_id,
                          {k: data.get(k) for k in ("set", "changes", "note", "message") if data.get(k)})
    Step.__name__ = f"Changes{name.title().replace('-', '')}"
    Step.post.__doc__ = fn.__doc__
    return blp.route(f"/models/<uuid:model_id>/changes/{name}", endpoint=f"changes_{name.replace('-', '_')}")(Step)


def _request(c, m, d):
    """Ask the model's committers to commit my changes (my open change set, or one sent back; or only the
    chosen changes, which become a request of their own)"""
    return cm.request_commit(c, m, g.user, d.get("set"), d.get("note", ""), d.get("changes"))


def _withdraw(c, m, d):
    """Take my request back (the changes stay mine, uncommitted)"""
    return cm.withdraw_request(c, m, g.user, d.get("set"))


def _commit(c, m, d):
    """Commit (Committers, Model Sub Admins, Model Admins): my changes, or a requested change set; all or the chosen
    changes. Conflicts with content committed since come back as 409 with errors.conflicts, to resolve and send again."""
    return cm.commit(c, m, g.user, d.get("set"), d.get("changes"), d.get("resolutions"), d.get("message", ""))


def _reject(c, m, d):
    """Reject requested changes, whole set or chosen ones, with a note (committers)"""
    return cm.reject(c, m, g.user, d.get("set"), d.get("changes"), d.get("note", ""))


def _send_back(c, m, d):
    """Send a requested change set back to its author with a note (committers)"""
    return cm.send_back(c, m, g.user, d.get("set"), d.get("note", ""))


def _discard(c, m, d):
    """Discard my own uncommitted changes: a whole set or the chosen ones"""
    return cm.discard(c, m, g.user, d.get("set"), d.get("changes"))


_step("request", _request)
_step("withdraw", _withdraw)
_step("commit", _commit, "model.commit")
_step("reject", _reject, "model.commit")
_step("send-back", _send_back, "model.commit")
_step("discard", _discard)


BATCH_OPS = ("entity.create", "entity.update", "entity.status", "entity.delete",
             "relationship.create", "relationship.delete", "relationship.rename")


@blp.route("/models/<uuid:model_id>/changes/batch")
class Batch(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(BatchIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, data, model_id):
        """Several content changes at once, the way a diagram editor saves (phases 28-29) or a tool sends them.
        In a project model they become my uncommitted changes, each checked on its own (D165: commits work the
        same whatever screen made the change); in other models they are applied at once, all or nothing"""
        items = []
        for i, ch in enumerate(data["changes"]):
            if not isinstance(ch, dict) or ch.get("op") not in BATCH_OPS or not isinstance(ch.get("args"), dict):
                abort(400, message=f"Change {i + 1}: give op (one of {', '.join(BATCH_OPS)}) and args.")
            items.append((ch["op"], ch["args"]))
        if len(items) > 5000:
            abort(400, message="Send at most 5000 changes at a time.")

        def run(c):
            m = cm._model(c, model_id)
            if cm.uses_commits(m):
                res = cm.record_many(c, model_id, g.user.username, items)
                return {"pending": True, "saved": sum(1 for r in res if r["ok"]), "failed": sum(1 for r in res if not r["ok"]),
                        "results": [{"ok": r["ok"], "error": r.get("error"), "label": (r.get("kept") or {}).get("label"),
                                     "change": (r.get("kept") or {}).get("change")} for r in res],
                        "note": "Saved as uncommitted changes: only you see them until they are committed (Changes tab)."}
            out = []
            for i, (op, args) in enumerate(items):
                try:
                    cm._apply(c, m, op, cm._prepare(op, args), g.user.username)
                except (EditError, repo.NotFound) as exc:
                    raise EditError(f"Change {i + 1} ({op}): {exc}", getattr(exc, "status", 409)) from exc
                out.append({"ok": True})
            return {"pending": False, "saved": len(out), "failed": 0, "results": out}
        return _write(run, "changes.batch", model_id, {"count": len(items)})


# ---------------------------------------------------------------- commits
@blp.route("/models/<uuid:model_id>/commits")
class Commits(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Commits of the model, newest first: mine (as author or committer), or everyone's with the History Viewer or
        Model Admin role (D151); ?person= one person's"""
        return _read(lambda c: cm.commits(c, model_id, g.user, request.args.get("person", ""), int(request.args.get("limit", 200))))


@blp.route("/models/<uuid:model_id>/commits/latest")
class LatestCommit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The last commit: number, who and when (open pages compare it with the one they loaded, E37)"""
        return _read(lambda c: cm.latest(c, model_id))


@blp.route("/models/<uuid:model_id>/commits/<string:commit_id>")
class Commit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, commit_id):
        """One commit: its items, each with what it changed (before and after)"""
        return _read(lambda c: cm.commit_detail(c, model_id, g.user, commit_id))


@blp.route("/models/<uuid:model_id>/commits/<string:commit_id>/roll-back")
class RollBackCommit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(RollBackIn)
    @blp.response(200, Free)
    @require_auth("model.commit")
    def post(self, data, model_id, commit_id):
        """Undo a commit, whole or chosen items, as a new commit (committers). 409 lists targets changed since (force)"""
        return _write(lambda c: cm.roll_back_commit(c, model_id, g.user, commit_id, data.get("items"), data["force"],
                                                    data.get("message", "")), "commit.roll_back", model_id,
                      {"commit": commit_id, "items": data.get("items")})


# ---------------------------------------------------------------- merges
@blp.route("/models/<uuid:model_id>/merges")
class Merges(MethodView):
    @blp.doc(security=SECURITY, requestBody={"content": {"multipart/form-data": {"schema": {
        "type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}}}})
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, model_id):
        """Upload a model package (.zip or .xlsx) to merge into this model: the plan (new entities, filled fields,
        conflicts to decide, new relationships, metamodel parts missing). Form field with_data=false (or a package
        without data): only the metamodel parts this model lacks. Nothing changes until it is applied"""
        f = request.files.get("file")
        if f is None:
            abort(400, message="Send the model as the form field 'file'.")
        data, name = f.read(), f.filename or ""
        with_data = (request.form.get("with_data") or "true").lower() not in ("false", "0", "no")
        return _write(lambda c: mg.analyse(c, model_id, data, name, g.user, with_data), "merge.analyse", model_id,
                      {"file": name, "with_data": with_data})


@blp.route("/models/<uuid:model_id>/merge-test-file")
class MergeTestFile(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "format", "schema": {"type": "string", "enum": ["zip", "xlsx"]}},
                                     {"in": "query", "name": "content", "schema": {"type": "string", "enum": ["content", "metamodel"]}}])
    @require_auth()
    def get(self, model_id):
        """A package made from this model to try the Merge tab with (?format=zip|xlsx): some descriptions and values
        changed (conflicts), empty fields filled, four new entities with relationships, one attribute the metamodel lacks"""
        fmt = "xlsx" if request.args.get("format") == "xlsx" else "zip"
        with_data = request.args.get("content", "content") != "metamodel"
        try:
            with get_engine().connect() as conn:
                data, name, ctype = mg.sample_package(conn, model_id, fmt, g.user.username, with_data)
        except (repo.NotFound, EditError) as exc:
            abort(getattr(exc, "status", 404), message=str(exc))
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@blp.route("/models/<uuid:model_id>/merges/<string:merge_id>/apply")
class MergeApply(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(MergeApplyIn)
    @blp.response(200, Free)
    @require_auth("model.content")
    def post(self, data, model_id, merge_id):
        """Apply a merge with the decisions: it becomes my uncommitted changes (commit it, or ask for a commit)"""
        return _write(lambda c: mg.apply(c, model_id, merge_id, g.user, data.get("decisions"), data.get("all_conflicts", ""),
                                         data["add_metamodel"]), "merge.apply", model_id, {"merge": merge_id})


@blp.route("/models/<uuid:model_id>/merges/<string:merge_id>/cancel")
class MergeCancel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id, merge_id):
        """Cancel a merge before applying it"""
        return _write(lambda c: mg.cancel(c, model_id, merge_id, g.user), "merge.cancel", model_id, {"merge": merge_id})


# ---------------------------------------------------------------- draft models (D165)
@blp.route("/models/<uuid:model_id>/reject-publish")
class RejectPublish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Reject a draft model waiting for approval, with the reason (its approvers): not published, archived"""
        return _write(lambda c: mo.reject_publish(c, model_id, g.user.username, g.user, data.get("note", "")),
                      "model.publish_rejected", model_id, data)


@blp.route("/models/<uuid:model_id>/reopen")
class Reopen(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Open a rejected draft again to change it and ask once more (its Model Admin)"""
        return _write(lambda c: mo.reopen_draft(c, model_id, g.user.username, g.user, data.get("note", "")),
                      "model.reopened", model_id, data)


@blp.route("/drafts/waiting")
class Waiting(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Draft models waiting for my approval"""
        return _read(lambda c: mo.waiting_for_me(c, g.user))
