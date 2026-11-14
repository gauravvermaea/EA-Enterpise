"""The API test harness (R3.16, D662): pick an endpoint, call it as yourself or a test role, see the answer; saved cases.

GET    /api/v1/admin/api-harness/endpoints              every endpoint, with its area, summary, parameters, example body
POST   /api/v1/admin/api-harness/sessions {roles}       a session: test accounts for the roles, its own test data
POST   /api/v1/admin/api-harness/sessions/<id>/end      its test data, accounts and tokens removed
POST   /api/v1/admin/api-harness/call {session, method, path, query, body, as}
                                                        one call (reads anywhere; writes into test data only)
GET    /api/v1/admin/api-harness/cases                  the saved cases
POST   /api/v1/admin/api-harness/cases {name, method, path, query, body, as, expect_status, expect_fields}
DELETE /api/v1/admin/api-harness/cases/<id>
POST   /api/v1/admin/api-harness/cases/run {session, ids?}  run them (all, or those named) in the session's test data

IT and Super Admins (system.operate), as the Self-test page. Every call and run is in the audit trail."""

from __future__ import annotations

import time

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import api_harness as ah
from .. import audit
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

blp = Blueprint("api_harness", __name__, url_prefix="/api/v1/admin/api-harness",
                description="The API test harness: call any endpoint as yourself or a test role (R3.16)")
SECURITY = [{"bearerAuth": []}]
_SPEC: dict = {"at": 0.0, "spec": None}


def _spec() -> dict:
    if not _SPEC["spec"] or time.time() - _SPEC["at"] > 600:
        from ..testing.api_matrix import fetch_spec
        _SPEC.update(spec=fetch_spec(ah.SELF), at=time.time())
    return _SPEC["spec"]


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except EditError as exc:
        abort(exc.status, message=str(exc))


def _own_token() -> str:
    auth = request.headers.get("Authorization", "")
    return auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else ""


def _audit(action: str, ident: str, details: dict) -> None:
    with get_engine().begin() as conn:
        audit.record(conn, actor=g.user.username, action=action, object_type="api", object_id=ident[:200], details=details,
                     request_id=getattr(g, "request_id", None))


@blp.route("/endpoints")
class Endpoints(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every endpoint of the API's own description: method, path, area, summary, parameters, an example body"""
        return {"endpoints": ah.endpoints(_spec())}


@blp.route("/sessions")
class Sessions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth("system.operate")
    def post(self, data):
        """A harness session: test accounts for the roles asked for (one-day tokens) and its own test data"""
        roles = [str(r) for r in (data or {}).get("roles") or []][:12]
        out = _guard(ah.session, get_engine(), g.user.username, roles)
        _audit("api.harness.session", str(out["session"]), {"roles": out["roles"]})
        return out


@blp.route("/sessions/<int:session_id>/end")
class SessionEnd(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, session_id):
        """Ends a session: its test data, accounts and tokens removed"""
        out = _guard(ah.end, get_engine(), session_id, g.user.username)
        _audit("api.harness.end", str(session_id), {})
        return out


def _token_for(sess: dict | None, as_who: str) -> str:
    if as_who in ("", "me", "you"):
        return _own_token()
    if not sess or as_who not in sess["tokens"]:
        abort(400, message=f"The session has no {as_who} account: start a session with that role.")
    return sess["tokens"][as_who]


@blp.route("/call")
class Call(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """One call through the API, as yourself or a session's role: reads anywhere; writes into test data only"""
        d = data or {}
        as_who = str(d.get("as") or "me")
        sess = _guard(ah.session_row, int(d["session"])) if d.get("session") else None
        path = ah.fill(str(d.get("path") or ""), (sess or {}).get("ids") or {})
        with get_engine().begin() as conn:
            test_ids = ah.test_data_ids(conn)
        out = _guard(ah.call, str(d.get("method") or "get"), path, _token_for(sess, as_who), d.get("body"),
                     d.get("query") or {}, test_ids, as_who)
        _audit("api.harness.call", f"{str(d.get('method') or 'get').upper()} {path}",
               {"as": as_who, "status": out["status"], "ms": out["ms"]})
        return out


@blp.route("/cases")
class Cases(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The saved cases"""
        from ..testing import store
        with store.engine().connect() as tc:
            return {"cases": ah.cases(tc)}

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Saves a call as a case with the answer expected (a case of the same name is replaced)"""
        from ..testing import store
        with store.engine().begin() as tc:
            out = _guard(ah.save_case, tc, g.user.username, data or {})
        _audit("api.harness.case", out["name"], {"path": (data or {}).get("path")})
        return out


@blp.route("/cases/<int:case_id>")
class Case(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def delete(self, case_id):
        """Deletes a saved case"""
        from ..testing import store
        with store.engine().begin() as tc:
            if not ah.delete_case(tc, case_id):
                abort(404, message=f"No case {case_id}.")
        _audit("api.harness.case.delete", str(case_id), {})
        return {"deleted": case_id}


@blp.route("/cases/run")
class CasesRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Runs the saved cases (all, or the ids given) in the session's test data, each as its role"""
        from ..testing import store
        d = data or {}
        if not d.get("session"):
            abort(400, message="Start a session first: the cases run in its test data.")
        sess = _guard(ah.session_row, int(d["session"]))
        with store.engine().connect() as tc:
            rows = ah.cases(tc)
        wanted = {int(i) for i in d.get("ids") or []}
        rows = [r for r in rows if not wanted or r["id"] in wanted]
        with get_engine().begin() as conn:
            test_ids = ah.test_data_ids(conn)
        out = ah.run_cases(rows, sess["tokens"], sess["ids"], test_ids)
        _audit("api.harness.cases.run", str(sess["id"]), {"cases": len(out), "failed": sum(1 for r in out if not r["passed"])})
        return {"results": out, "passed": sum(1 for r in out if r["passed"]), "failed": sum(1 for r in out if not r["passed"])}
