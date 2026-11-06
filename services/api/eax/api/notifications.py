"""Notifications, requests, webhooks, metamodel push-down and change documents (build phase 8.1, D84, D209).

GET    /notifications                          mine: ?show=open|actions|resolved|all&category=&model=&q=&limit=&offset=
GET    /notifications/counts                   unread, open actions, open requests sent to me (the bell)
POST   /notifications/read                     mark read {ids} (none: all)
POST   /notifications/<n>/dismiss              put an information notification away
POST   /notifications/<n>/resolve              resolve one that needs action {note}
GET    /requests                               ?box=received|sent&status=active|closed|all|<status>&q=
POST   /requests                               send one {to, subject, body}
GET    /requests/people                        who a request can go to ?q=
GET    /requests/<r>                           one request with its comments (sender and receiver only)
POST   /requests/<r>/comments                  {body}
POST   /requests/<r>/status                    {status: in_progress|done|declined|open, note}
GET    /models/<m>/pushdown                    what this model can push down, to whom; pushes made; packages arrived
POST   /models/<m>/pushdown                    push {mode: forced|offered, fill_defaults, note} (Model Admin)
POST   /models/<m>/pushdown/<t>/decide         accept or reject an offered package {accept, note} (Model Admin)
GET    /models/<m>/change-documents            the model's change documents
GET    /change-documents/<d>                   one change document (anyone who may read the model)
GET|POST /admin/webhooks; PATCH|DELETE /admin/webhooks/<w>; GET /admin/webhooks/<w>/deliveries;
POST   /admin/webhooks/<w>/test                installation-wide webhooks (IT and Super Admins)
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import audit, change_docs, notify, pushdown, tickets, webhooks
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn

blp = Blueprint("notifications", __name__, url_prefix="/api/v1",
                description="Notifications, requests, webhooks, metamodel push-down and change documents (phase 8.1)")
SECURITY = [{"bearerAuth": []}]
ERRORS = (notify.NotFound, tickets.RequestError, webhooks.HookError, pushdown.PushError, EditError, repo.NotFound,
          ValueError, LookupError)


def _status(exc) -> int:
    if isinstance(exc, (notify.NotFound, repo.NotFound, LookupError)) and not isinstance(exc, ValueError):
        return 404
    return getattr(exc, "status", 400)


def _join(conn) -> None:
    """Super Admins get every model's notifications (D209: everyone with a role on the model)."""
    from .. import permissions
    if permissions.sees_every_model(getattr(g.user, "roles", ())):
        notify.join_super_admin(conn, g.user.username)


def _read(fn, join: bool = False):
    try:
        if join:
            with get_engine().begin() as conn:
                _join(conn)
                return fn(conn)
        with get_engine().connect() as conn:
            return fn(conn)
    except ERRORS as exc:
        abort(_status(exc), message=str(exc))


def _write(fn, action: str | None = None, object_type: str = "", object_id: str = "", details=None):
    try:
        with get_engine().begin() as conn:
            out = fn(conn)
            if action:
                audit.record(conn, actor=g.user.username, action=action, object_type=object_type, object_id=object_id,
                             details=details(out) if callable(details) else (details or {}),
                             request_id=getattr(g, "request_id", None))
            return out
    except ERRORS as exc:
        abort(_status(exc), message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


# ---------------------------------------------------------------- notifications
@blp.route("/notifications")
class Notifications(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """My notifications: open (action ones not resolved, information ones not dismissed), actions, resolved or all"""
        a = request.args
        return _read(lambda c: notify.listing(c, g.user.username, show=a.get("show", "open"), category=a.get("category", ""),
                                              model=a.get("model", ""), q=a.get("q", ""), limit=int(a.get("limit", 100)),
                                              offset=int(a.get("offset", 0))), join=True)


@blp.route("/notifications/counts")
class NotificationCounts(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The bell: unread notifications, open actions and open requests sent to me"""
        return _read(lambda c: notify.counts(c, g.user.username), join=True)


@blp.route("/notifications/read")
class NotificationsRead(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Mark some ({ids}) or all of my notifications read"""
        return _write(lambda c: {"marked": notify.mark_read(c, g.user.username, (data or {}).get("ids"))})


@blp.route("/notifications/<uuid:nid>/dismiss")
class NotificationDismiss(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, nid):
        """Put away an information notification (only for me)"""
        return _write(lambda c: notify.dismiss(c, g.user.username, nid))


@blp.route("/notifications/<uuid:nid>/resolve")
class NotificationResolve(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, nid):
        """Resolve a notification that needs action, with a note of what was done: resolved for everyone who got it"""
        return _write(lambda c: notify.resolve(c, g.user.username, nid, (data or {}).get("note", "")),
                      "notification.resolve", "notification", str(nid), {"note": (data or {}).get("note", "")})


# ---------------------------------------------------------------- requests
@blp.route("/requests")
class Requests(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Requests sent to me (box=received) or by me (box=sent): status active, closed, all or one status"""
        a = request.args
        return _read(lambda c: tickets.listing(c, g.user.username, a.get("box", "received"), a.get("status", "active"),
                                               a.get("q", "")))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Send a request to another person {to, subject, body}: private to the two of you"""
        d = data or {}
        return _write(lambda c: tickets.send(c, g.user.username, d.get("to", ""), d.get("subject", ""), d.get("body", ""),
                                             d.get("via", "screen")),
                      "request.send", "request", "", lambda out: {"number": out["number"], "to": out["receiver"]})


@blp.route("/requests/people")
class RequestPeople(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """People a request can be sent to (?q= part of a username)"""
        return _read(lambda c: {"people": [r["username"] for r in tickets.people(c, request.args.get("q", ""))
                                           if r["username"] != g.user.username.lower()]})


@blp.route("/requests/<rid>")
class RequestOne(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, rid):
        """One request (by number or id) with its comments: its sender and receiver only"""
        return _read(lambda c: tickets.get(c, g.user.username, rid))


@blp.route("/requests/<rid>/comments")
class RequestComment(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, rid):
        """Comment on a request {body}"""
        return _write(lambda c: tickets.comment(c, g.user.username, rid, (data or {}).get("body", "")))


@blp.route("/requests/<rid>/status")
class RequestStatus(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, rid):
        """Move a request along {status, note}: the receiver to in progress, done or declined (a note for the last two);
        the sender may open a closed one again"""
        d = data or {}
        return _write(lambda c: tickets.set_status(c, g.user.username, rid, d.get("status", ""), d.get("note", "")),
                      "request.status", "request", str(rid), {"status": d.get("status"), "note": d.get("note", "")})


# ---------------------------------------------------------------- metamodel push-down
@blp.route("/models/<uuid:model_id>/pushdown")
class PushDown(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.read")
    def get(self, model_id):
        """What this model can push down and to whom, the pushes it made, and the packages that arrived from above"""
        return _read(lambda c: pushdown.overview(c, model_id))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("model.metamodel")
    def post(self, data, model_id):
        """Push the metamodel versions made since the last push to the models directly below {mode: forced|offered,
        fill_defaults, note}: forced makes them at once, offered asks each model's Model Admin (D84)"""
        d = data or {}
        fn = pushdown.pass_on if d.get("pass_on") else pushdown.push
        return _write(lambda c: fn(c, model_id, g.user.username, d.get("mode", ""), d.get("fill_defaults", True), d.get("note", "")),
                      "pushdown.push", "model", str(model_id),
                      lambda out: {"versions": out["versions"], "mode": out["mode"], "note": d.get("note", "")})


@blp.route("/models/<uuid:model_id>/pushdown/<int:target_id>/decide")
class PushDecide(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("model.metamodel")
    def post(self, data, model_id, target_id):
        """Accept (made at once) or reject (the model diverges from its parent; a note is needed) an offered package"""
        d = data or {}
        return _write(lambda c: pushdown.decide(c, model_id, target_id, g.user.username, bool(d.get("accept")), d.get("note", "")),
                      "pushdown.accepted" if d.get("accept") else "pushdown.rejected", "model", str(model_id),
                      {"note": d.get("note", ""), "package": target_id})


# ---------------------------------------------------------------- change documents
@blp.route("/models/<uuid:model_id>/change-documents")
class ChangeDocuments(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("model.read")
    def get(self, model_id):
        """The model's change documents, newest first"""
        return _read(lambda c: {"documents": change_docs.for_model(c, repo.get_model(c, model_id)["_id"])})


@blp.route("/change-documents/<ref>")
class ChangeDocument(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, ref):
        """One change document (by number or id): for anyone who may read its model"""
        def run(c):
            def may(guid):
                try:
                    repo.get_model(c, guid)
                    return True
                except repo.NotFound:
                    return False
            return change_docs.get(c, ref, g.user.username, may)
        return _read(run)


# ---------------------------------------------------------------- webhooks (IT and Super Admins)
@blp.route("/admin/webhooks")
class Webhooks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The installation's webhooks with their delivery counts"""
        return _read(lambda c: {"webhooks": webhooks.listing(c), "kinds": list(notify.CATEGORIES)})

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Add a webhook {name, url, kinds}: a secret is made to sign its messages"""
        return _write(lambda c: webhooks.create(c, data or {}, g.user.username), "webhook.add", "webhook", "",
                      lambda out: {"name": out["name"], "url": out["url"], "kinds": out["kinds"]})


@blp.route("/admin/webhooks/<uuid:hook_id>")
class Webhook(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def patch(self, data, hook_id):
        """Change a webhook {name, url, kinds, enabled, new_secret}"""
        return _write(lambda c: webhooks.update(c, hook_id, data or {}), "webhook.change", "webhook", str(hook_id),
                      {k: v for k, v in (data or {}).items() if k != "secret"})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def delete(self, hook_id):
        """Delete a webhook and its delivery log"""
        return _write(lambda c: webhooks.delete(c, hook_id), "webhook.delete", "webhook", str(hook_id))


@blp.route("/admin/webhooks/<uuid:hook_id>/deliveries")
class WebhookDeliveries(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, hook_id):
        """The last deliveries of a webhook"""
        return _read(lambda c: {"deliveries": webhooks.deliveries(c, hook_id)})


@blp.route("/admin/webhooks/<uuid:hook_id>/test")
class WebhookTest(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, hook_id):
        """Send a test message now and say what the receiver answered"""
        return _read(lambda c: webhooks.test(c, hook_id, g.user.username))
