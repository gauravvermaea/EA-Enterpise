"""The self-test's browser sign-in (phase 36.1, D529).

  GET /api/v1/selftest/session?ticket=&role=   the run's token for one of its roles, while the run is going on

The screens opened with ?eaxselftest=<ticket>&eaxrole=<role> (the headless journeys, and the journeys watched in the
admin's own browser) ask here for the run's own token for that role and use it instead of Keycloak. The ticket is the
run's one secret: made by the runner, kept in core.test_runs while the run is open (given only to Super Admins and IT
Admins by System admin > Self-test), and forgotten, with every token of the run revoked, when its checks end. The
token only ever reaches what the run's account for that role may: the run's own fixtures and the standard screens."""

from __future__ import annotations

import hmac

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .models import Free

blp = Blueprint("selftest_session", __name__, url_prefix="/api/v1/selftest", description="The self-test's browser sign-in")


@blp.route("/session")
class Session(MethodView):
    @blp.doc(security=[])
    @blp.response(200, Free)
    def get(self):
        """The running self-test's token for one role (its ticket needed; nothing without it)"""
        ticket, role = request.args.get("ticket", ""), request.args.get("role", "")
        if len(ticket) < 20:
            abort(401, message="Not a self-test ticket.")
        from ..testing import store
        with store.engine().connect() as conn:       # the tests database (R2.28)
            rows = conn.execute(text("""SELECT id, run_guid::text AS g, browser FROM core.test_runs
                                         WHERE state IN ('queued', 'running') AND browser ? 'ticket'""")).mappings().all()
        run = next((r for r in rows if hmac.compare_digest(str(r["browser"].get("ticket", "")), ticket)), None)
        if not run:
            abort(401, message="Not a self-test ticket, or its run has ended.")
        token = (run["browser"].get("tokens") or {}).get(role)
        if not token:
            abort(400, message=f"The run has no account for the role {role!r}.")
        sid = run["g"].replace("-", "")[:12]
        return {"run": run["id"], "role": role, "username": f"svc-self-test-{sid}-{role}", "token": token}
