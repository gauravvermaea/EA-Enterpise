"""The test bench's door into a self-test run (D580, D581): the outside test bench (testbench/, `eax testbench`) runs the
self-test's own tests from another machine; this is how it gets the run's fixtures and gives back what it found.

  GET  /api/v1/admin/testbench/runs/<run>/session   the run's fixtures (ids), its sign-in ticket and its test tokens: only
                                                     for a run started for a browser (watch) by the caller, while it is open
  POST /api/v1/admin/testbench/runs/<run>/results   {suite, results: [...], done}: results into the run, marked
                                                     "external testbench"; done closes the browser part (the run ends)
  POST /api/v1/admin/testbench/runs                 {level, suites, target, version, trigger}: a run in this
                                                     installation's history for results the bench found elsewhere (or
                                                     with no fixtures); then .../results and .../finish
  POST /api/v1/admin/testbench/runs/<run>/finish    counts the results and closes such a run
  GET  /api/v1/admin/testbench/state                version, database migration and row counts (the upgrade test)
  POST /api/v1/admin/testbench/db-checks            the self-test's fixed, named, read-only database checks
                                                     (eax/testing/db_checks.py); nothing from the caller reaches SQL

Super Admins and IT Admins (system.operate) only, as the Self-test page. The tokens are the run's own one-day tokens of
its svc-self-test accounts (roles on the run's fixtures only), revoked when the run ends."""

from __future__ import annotations

import base64
import binascii
import os
import time

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .. import audit
from ..auth import require_auth
from ..db import get_engine
from ..testbench_state import count_rows
from ..testing import db_checks, store
from .models import Free, FreeIn

blp = Blueprint("testbench", __name__, url_prefix="/api/v1/admin/testbench",
                description="The outside test bench's door into a self-test run (D580, D581)")
SECURITY = [{"bearerAuth": []}]
SUITES = ("smoke", *store.SUITES)


def _open_run_of_caller(conn, run_id: int) -> dict:
    row = store.run_row(conn, run_id)
    if not row:
        abort(404, message=f"No self-test run {run_id}.")
    if not (row.get("watch") or _external(conn, run_id)) or row.get("state") not in store.OPEN:
        abort(409, message=f"Self-test {run_id} is not waiting for a browser (start it for the test bench: watch).")
    if (row.get("started_by") or "") not in (g.user.username, f"{g.user.username} (external testbench)"):
        abort(403, message="Only the person who started this run can take part in it.")
    return row


def _external(conn, run_id: int) -> bool:
    return conn.execute(text("SELECT browser->>'external' FROM tests.test_runs WHERE id = :id"), {"id": run_id}).scalar() == "true"


@blp.route("/runs")
class NewRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """{level, suites, target, version, trigger (eax|ci)}: a run in the Self-test history for the outside test bench's
        results (published with --publish), marked "external testbench"; no fixtures are made"""
        data = data or {}
        level = data.get("level") if data.get("level") in ("smoke", "detailed") else "smoke"
        suites = [x for x in (data.get("suites") or []) if x in store.SUITES] or ["api"]
        trigger = "ci" if data.get("trigger") == "ci" else "eax"
        target = str(data.get("target") or "")[:200]
        with get_engine().begin() as conn, store.tests(conn) as tc:   # the run in the tests database (R2.28)
            run_id = store.create_run(tc, f"{g.user.username} (external testbench)", trigger, suites, "",
                                      str(data.get("version") or "")[:40], level)
            store.set_state(tc, run_id, state="running", step=f"external testbench: {target}"[:200])
            store.set_browser(tc, run_id, {"external": True, "target": target, "done": False})
            audit.record(conn, actor=g.user.username, action="selftest.testbench.publish", object_type="test_run",
                         object_id=str(run_id), details={"target": target, "level": level})
        return {"run_id": run_id}


@blp.route("/runs/<int:run_id>/finish")
class Finish(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, run_id):
        """Counts the results of an external testbench run and closes it (passed, or failed when any check failed)"""
        with store.engine().begin() as conn:
            row = store.run_row(conn, run_id)
            if not row or not _external(conn, run_id):
                abort(404, message=f"No external testbench run {run_id}.")
            if (row.get("started_by") or "") != f"{g.user.username} (external testbench)":
                abort(403, message="Only the person who published this run can close it.")
            state = store.finish(conn, run_id)
        return {"run_id": run_id, "state": state}


def ids_of(conn, run_id: int, run_guid: str) -> dict[str, str]:
    """The run's ids as the self-test's journeys and API matrix use them (fixtures.models_and_project). conn: the
    repository's; the fixtures' record is in the tests database."""
    with store.tests(conn) as tc:
        rows = tc.execute(text("SELECT kind, ident, name FROM tests.test_fixtures WHERE run_id = :r AND purged_at IS NULL "
                               "ORDER BY id"), {"r": run_id}).mappings().all()
    models = [r for r in rows if r["kind"] == "model"]
    first = next((r for r in models if str(r["name"]).endswith("_1")), models[0] if models else None)
    second = next((r for r in models if str(r["name"]).endswith("_2")), None)
    ids = {"sid": store.short(run_guid)}
    if first:
        ids.update(model=first["ident"], model_id=first["ident"], model_name=first["name"])
        ent = conn.execute(text("SELECT e.guid::text FROM core.entities e JOIN core.models m ON m.id = e.model_id "
                                "WHERE m.guid = CAST(:g AS uuid) AND NOT e.is_deleted ORDER BY e.id LIMIT 1"),
                           {"g": first["ident"]}).scalar()
        if ent:
            ids.update(entity=ent, entity_id=ent)
        names = [n for (n,) in conn.execute(text(
            "SELECT e.name FROM core.entities e JOIN core.models m ON m.id = e.model_id WHERE m.guid = CAST(:g AS uuid) "
            "AND NOT e.is_deleted AND e.name LIKE 'Self-test duplicate%' ORDER BY e.name"), {"g": first["ident"]}).all()]
        if names:
            ids["dup"] = os.path.commonprefix(names) or names[0]
    if second:
        ids["other_model"] = second["ident"]
    project = next((r for r in rows if r["kind"] == "project"), None)
    if project:
        ids.update(project=project["ident"], project_id=project["ident"], project_name=project["name"])
    return ids


@blp.route("/runs/<int:run_id>/session")
class Session(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, run_id):
        """The run's fixtures, sign-in ticket and test tokens, for the test bench that started it (D580)"""
        with get_engine().begin() as conn:
            with store.tests(conn) as tc:
                row = _open_run_of_caller(tc, run_id)
                guid = tc.execute(text("SELECT run_guid::text FROM tests.test_runs WHERE id = :id"), {"id": run_id}).scalar()
            b = row.get("browser") or {}
            if not b.get("ticket"):
                return {"ready": False, "step": row.get("step") or "making the run's fixtures"}
            ids = ids_of(conn, run_id, guid)
            audit.record(conn, actor=g.user.username, action="selftest.testbench.session", object_type="test_run",
                         object_id=str(run_id), details={"roles": sorted((b.get("tokens") or {}).keys())})
        return {"ready": True, "run_id": run_id, "run_guid": guid, "ticket": b["ticket"], "tokens": b.get("tokens") or {},
                "ids": ids, "level": row.get("level"), "role": row.get("role") or "", "area": row.get("area") or ""}


@blp.route("/runs/<int:run_id>/results")
class Results(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, run_id):
        """{suite, results: [{name, outcome, detail, ms, browser, screenshot (PNG base64), request, response}], done}:
        results into the run, marked "external testbench"; done ends the run's wait"""
        data = data or {}
        suite = data.get("suite") if data.get("suite") in SUITES else "ui"
        n = 0
        with store.engine().begin() as conn:
            _open_run_of_caller(conn, run_id)
            for r in (data.get("results") or [])[:200]:
                shot = None
                if r.get("screenshot"):
                    try:
                        shot = base64.b64decode(str(r["screenshot"]).split(",")[-1], validate=True)[:3_000_000]
                    except (binascii.Error, ValueError):
                        shot = None
                outcome = r.get("outcome") if r.get("outcome") in store.OUTCOMES else "failed"
                where = str(r.get("browser") or "").strip()
                store.add_result(conn, run_id, suite if suite != "smoke" else "smoke", str(r.get("name") or "")[:300], outcome,
                                 str(r.get("detail") or "")[:4000], int(r.get("ms") or 0), shot, "",
                                 str(r.get("request") or "")[:4000], str(r.get("response") or "")[:8000],
                                 ("external testbench" + (f" · {where}" if where else ""))[:200])
                n += 1
            if data.get("done"):
                store.set_browser(conn, run_id, {"done": True, "bench": True})
        return {"ok": True, "recorded": n}


@blp.route("/db-checks")
class DbChecks(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self):
        """The self-test's read-only database checks, by name, with their results (for the outside test bench, D581)"""
        from .. import __version__
        out: list[dict] = []

        def record(name, outcome, detail="", ms=0, **_kw):
            out.append({"name": name, "outcome": outcome, "detail": detail, "ms": ms})
        t0 = time.time()
        with get_engine().connect() as conn:
            db_checks.run(conn, __version__, record)
            if hasattr(db_checks, "run_outside"):
                db_checks.run_outside(conn, record)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="selftest.testbench.db_checks", object_type="system",
                         object_id="db", details={"checks": len(out)})
        return {"version": __version__, "results": out, "ms": int((time.time() - t0) * 1000)}


@blp.route("/state")
class State(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The installation's version, its database migration (alembic) and a few row counts: what an upgrade must keep
        (the outside test bench compares them before and after an upgrade, D582); within 30 seconds, what was not
        counted in time said in problems"""
        from .. import __version__
        with get_engine().begin() as conn:
            conn.execute(text("SET LOCAL statement_timeout = 5000"))
            migration = conn.execute(text("SELECT version_num FROM public.alembic_version LIMIT 1")).scalar()
        counts, problems = count_rows(get_engine())
        return {"version": __version__, "migration": migration, "counts": counts, "problems": problems}
