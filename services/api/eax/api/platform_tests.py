"""The self-test (phase 36.1, D367, D522 to D529) and the scaling rules (phase 36.3, D526): System admin > Self-test and
System admin > Scaling. Super Admins and IT Admins (system.operate) only; nobody else sees self-test results.

  GET  /api/v1/admin/tests                              runs (newest first), the runner, the choices and how long each takes
  POST /api/v1/admin/tests                              {level, suites, role, area, watch, build_first}: start a run now
                                                        (build_first, default true: the runner is prepared first, then the run; D570, D584)
  POST /api/v1/admin/tests/build                        build the test runner (eax test --build, in the operations helper)
  GET  /api/v1/admin/tests/build/<id>?from=             the build: its record, its log from byte `from`, its steps
  PUT  /api/v1/admin/tests/settings                     {auto_build, keep_days}: build it automatically after each start or
                                                        update; keep test results N days (R2.43)
  POST /api/v1/admin/tests/delete                       {runs | "all", older_than_days}: delete test results for good (R2.43)
  GET  /api/v1/admin/tests/<run>                        a run, its results (?outcome=, ?suite=), files and fixtures; while it
                                                        waits for a watching browser also its ticket and journeys
  POST /api/v1/admin/tests/<run>/repeat                 {warnings}: run its failed checks again (R2.36)
  POST /api/v1/admin/tests/<run>/stop                   stop it
  POST /api/v1/admin/tests/<run>/browser                {results: [...], done}: journeys watched in this browser
  GET  /api/v1/admin/tests/<run>/report?format=html|xlsx  its report
  GET  /api/v1/admin/tests/<run>/screenshot/<id>        a failed journey's screenshot (PNG)
  GET  /api/v1/admin/tests/<run>/files/<path>           a file of the run (run.log, a video, zap.json, trivy-*.json)
  GET  /api/v1/admin/tests/fixtures                     every self-test fixture of every run (?run=)
  POST /api/v1/admin/tests/fixtures/purge               {runs: [ids] | "all", fixtures: [ids], confirm: "DELETE"}: purge
  GET  /api/v1/admin/scaling   PUT /api/v1/admin/scaling   the scaling rules;  GET /api/v1/admin/scaling/load (ops only)"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
from pathlib import Path

from flask import Response, g, request, send_file
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy import text

from .. import audit
from ..auth import require_auth
from ..db import get_engine
from ..testing import SUITES, report, store
from .admin import _ops, _ops_raw
from .models import Free, FreeIn

blp = Blueprint("platform_tests", __name__, url_prefix="/api/v1/admin",
                description="The self-test (phase 36.1) and the scaling rules (phase 36.3)")
SECURITY = [{"bearerAuth": []}]
WORK_TESTS = Path(os.environ.get("EAX_WORK_DIR", "/eax-work")) / "tests"


def _ops_message(exc: Exception) -> str:
    msg = getattr(exc, "reason", None) or str(exc)
    try:
        msg = json.load(exc).get("message", msg)          # an HTTP error from the helper: its own words
    except Exception:  # noqa: BLE001
        pass
    return str(msg)


def _tidy() -> list[int]:
    """Closes the runs no one is running any more (R2.64) before a page shows them or a run starts; never fails a call."""
    try:
        with store.engine().begin() as conn:
            return store.close_orphans(conn)
    except Exception:  # noqa: BLE001 - only tidying
        return []


@blp.route("/tests")
class Tests(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Self-test runs, newest first; the test runner (built, a run going on); the choices (levels, suites, roles,
        areas) and how long each kind of run takes"""
        from ..machine_access import AREAS
        _tidy()
        with store.engine().connect() as conn:
            runs = store.runs(conn, int(request.args.get("limit", 30)))
        try:
            runner = _ops_raw("GET", "/tests", timeout=10)
        except Exception as exc:  # noqa: BLE001 - the history still shows when the helper is down
            runner = {"image_present": None, "message": f"The operations helper is not reachable ({exc})."}
        from ..testing import ui_flows
        return {"runs": runs, "runner": runner, "suites": list(store.SUITES),
                "journeys": [{"name": j["name"], "key": ui_flows.key(j), "smoke": j["smoke"], "roles": j["roles"],
                              "headless_only": bool(j.get("headless_only"))} for j in ui_flows.JOURNEYS],
                "commands": _test_commands(),
                "roles": store.TEST_ROLES, "areas": [{"code": c, "label": lbl} for c, lbl, _ in AREAS],
                "estimates": {"smoke": store.estimate_minutes("smoke", []),
                              **{s: store.estimate_minutes("detailed", [s]) for s in SUITES},
                              "detailed_all": store.estimate_minutes("detailed", list(SUITES))}}

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Starts a self-test now (never scheduled) {level: smoke|detailed, suites: [api, ui, db, security] (detailed),
        role, area, watch}: it makes its own fixtures (self_test_<id>_<n>) and tests in them; follow it here"""
        data = data or {}
        try:
            level, role, area = store.clean_options(data.get("level"), data.get("role"), data.get("area"))
            suites = store.clean_suites(data.get("suites"))
            journeys = store.clean_journeys(data.get("journeys"))
            pages_only = bool(data.get("pages_only"))
            if journeys or pages_only:                  # a journey or the page sweep: the browser suite (D577)
                level, suites = "detailed", ["ui"]
        except ValueError as exc:
            abort(400, message=str(exc))
        watch = bool(data.get("watch")) and level == "detailed" and "ui" in suites
        # always prepare the runner first (owner, 11 Nov 2026, D584): `docker compose build` is near-instant when the image is
        # current (layer cache) and rebuilds it when the code or version changed, so no one builds it by hand
        build_first = data.get("build_first", True) is not False
        _tidy()                                       # a run left "running" by a runner that is gone does not block (R2.64)
        with get_engine().begin() as conn, store.tests(conn) as tc:
            busy = tc.execute(text("SELECT id FROM tests.test_runs WHERE state IN ('queued', 'running') "
                                   "AND queued_at > now() - interval '3 hours' ORDER BY id DESC LIMIT 1")).scalar()
            if busy:
                abort(409, message=f"Self-test {busy} is going on: stop it or wait for it to finish.")
            run_id = store.create_run(tc, g.user.username, "web", suites, level=level, role=role, area=area, watch=watch,
                                      journeys=journeys, pages_only=pages_only)
            audit.record(conn, actor=g.user.username, action="selftest.started", object_type="test_run", object_id=str(run_id),
                         details={"level": level, "suites": suites, "role": role, "area": area, "watch": watch,
                                  "journeys": journeys, "pages_only": pages_only})
        body = {"run_id": run_id, "level": level, "suites": suites, "role": role, "area": area, "watch": watch,
                "journeys": journeys, "pages_only": pages_only, "by": g.user.username}
        from ..testing import waiter
        if waiter.platform_managed():          # no Docker socket (R2.44, D635): the always-on runner service takes it
            with store.engine().begin() as conn:
                store.set_state(conn, run_id, step=f"{waiter.WAITING} (the platform runs it; the security scanners need "
                                                   "the Docker socket and are left out)")
            lo, hi = store.estimate_minutes(level, suites, watch)
            return {"run_id": run_id, "message": f"Queued for the test runner service: about {lo} to {hi} minutes."}
        try:
            if build_first:                     # the helper prepares (builds) the runner, then starts this run
                _ops_raw("POST", "/tests/build", {"by": g.user.username, "then": body}, timeout=60)
                with store.engine().begin() as conn:
                    store.set_state(conn, run_id, step="Preparing the test runner (seconds when it is current; the first time 5 to 15 minutes), then the run")
            else:
                _ops_raw("POST", "/tests", body, timeout=30)
        except Exception as exc:  # noqa: BLE001 - the run is closed with the reason
            msg = _ops_message(exc)
            with store.engine().begin() as conn:
                store.set_state(conn, run_id, state="error", message=f"Could not start: {msg}")
            abort(503, message=f"The self-test could not start: {msg}")
        lo, hi = store.estimate_minutes(level, suites, watch)
        if build_first:
            return {"run_id": run_id, "message": f"Preparing the test runner (the first time 5 to 15 minutes), then the run: about {lo} to {hi} minutes."}
        return {"run_id": run_id, "message": f"Started: about {lo} to {hi} minutes."}


@blp.route("/tests/build")
class TestRunnerBuild(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self):
        """Builds the test runner image (about 1.5 GB, 5 to 15 minutes): `eax test --build` in the operations helper's
        short-lived command container; follow it with GET /tests/build/<id>"""
        try:
            out = _ops_raw("POST", "/tests/build", {"by": g.user.username}, timeout=60)
        except Exception as exc:  # noqa: BLE001
            abort(503, message=f"The build could not start: {_ops_message(exc)}")
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="selftest.runner_build", object_type="test_runner",
                         object_id=str(out.get("run_id") or ""))
        return out


@blp.route("/tests/build/<string:build_id>")
class TestRunnerBuildRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, build_id):
        """A test-runner build: its record, its log from byte ?from=, its steps (base image, Python packages, Chromium,
        scanners, the code), whether it ended and, if it failed, why"""
        from urllib.parse import quote
        try:
            return _ops_raw("GET", f"/tests/build/{quote(build_id)}?from={int(request.args.get('from', 0) or 0)}", timeout=20)
        except ValueError:
            abort(400, message="from must be a number.")
        except Exception as exc:  # noqa: BLE001
            abort(404, message=f"No such build: {_ops_message(exc)}")


@blp.route("/tests/settings")
class TestRunnerSettings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data):
        """{auto_build: true|false, keep_days: N}: build the test runner automatically after each start or update when
        its image is missing; keep test results N days, 0 always (R2.43) (both in persist/settings.json)"""
        data = data or {}
        body = {"by": g.user.username}
        if "auto_build" in data:
            body["auto_build"] = bool(data.get("auto_build"))
        if "keep_days" in data:
            try:
                body["keep_days"] = int(data.get("keep_days"))
            except (TypeError, ValueError):
                abort(400, message="keep_days is a number of days (0 keeps test results always).")
        try:
            out = _ops_raw("POST", "/tests/settings", body, timeout=20)
        except Exception as exc:  # noqa: BLE001
            abort(503, message=f"The setting could not be saved: {_ops_message(exc)}")
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="selftest.settings", object_type="test_runner",
                         object_id="settings", details={k: v for k, v in body.items() if k != "by"})
        return out


@blp.route("/tests/delete")
class TestDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Delete test results for good (R2.43) {runs: [ids] | "all", older_than_days}: each run's test data, its results
        and screenshots, its reports, logs and videos in work/tests. A run still going is left"""
        from ..testing import cleanup
        data = data or {}
        runs = data.get("runs")
        try:
            with store.engine().connect() as conn:
                if runs == "all" or data.get("older_than_days"):
                    ids = [r["id"] for r in cleanup.pick(conn, "all" if runs == "all" else "",
                                                         int(data["older_than_days"]) if data.get("older_than_days") else None)]
                else:
                    ids = [int(x) for x in (runs or [])]
        except (TypeError, ValueError) as exc:
            abort(400, message=str(exc))
        if not ids:
            return {"runs": 0, "message": "No finished test runs to delete for that."}
        from .. import filestore

        def drop_folders(folders):
            if filestore.in_database():              # no local file system: the runs' files are in the store (R2.44)
                return {"removed": [f for f in folders if filestore.delete("tests", f) >= 0], "left": []}
            return _ops_raw("POST", "/tests/results/delete", {"folders": folders}, timeout=120)
        out = cleanup.delete(get_engine(), ids, g.user.username, drop_folders)
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="selftest.delete", object_type="test_run",
                         object_id=",".join(map(str, ids))[:200], details={k: v for k, v in out.items() if k != "notes"})
        return {**out, "message": cleanup.message(out)}


@blp.route("/tests/<int:run_id>")
class TestRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self, run_id):
        """A run: its results (failures first; ?outcome=passed|failed|skipped|warning, ?suite=), its files, its fixtures;
        while it waits for a watching browser also its ticket and the journeys to drive"""
        _tidy()
        with store.engine().connect() as conn:
            d = store.run_detail(conn, run_id, request.args.get("outcome", ""), request.args.get("suite", ""))
            if not d:
                abort(404, message=f"No self-test run {run_id}.")
            row = store.run_row(conn, run_id) or {}
        with get_engine().connect() as conn:          # the fixtures' sizes are in the repository
            d["fixtures"] = store.fixtures(conn, run_id, include_purged=True)
        b = row.get("browser") or {}
        if row.get("watch") and row.get("state") in store.OPEN and b.get("ticket") and not b.get("done"):
            d["browser"] = {"ticket": b["ticket"], "journeys": b.get("journeys") or [], "roles": sorted((b.get("tokens") or {}).keys()),
                            # the page sweep in this browser (D575): where it starts, what it skips, the run's own ids
                            "pages": b.get("pages") or [], "pages_skip": b.get("pages_skip") or {}, "scope": b.get("scope") or []}
        from .. import filestore
        if filestore.in_database() and d["run"]["folder"]:       # its files are in the store (R2.44, D635)
            pre = f"{d['run']['folder']}/"
            d["files"] = [x["name"][len(pre):] for x in filestore.listing("tests", pre)]
            return d
        folder = WORK_TESTS / d["run"]["folder"] if d["run"]["folder"] else None
        d["files"] = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()) if folder and folder.is_dir() else []
        return d


@blp.route("/tests/<int:run_id>/repeat")
class TestRepeat(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data, run_id):
        """Runs the failed ones again (R2.36, D605) {warnings: false}: a new run of only the checks that failed in this
        run (and its warnings, if asked), as the same roles, in fresh fixtures; its report shows each check then and now"""
        data = data or {}
        warnings = bool(data.get("warnings"))
        with get_engine().begin() as conn, store.tests(conn) as tc:
            busy = tc.execute(text("SELECT id FROM tests.test_runs WHERE state IN ('queued', 'running') "
                                   "AND queued_at > now() - interval '3 hours' ORDER BY id DESC LIMIT 1")).scalar()
            if busy:
                abort(409, message=f"Self-test {busy} is going on: stop it or wait for it to finish.")
            try:
                o = store.repeat_options(tc, run_id, warnings)
            except ValueError as exc:
                abort(404 if "No self-test" in str(exc) else 409, message=str(exc))
            new_id = store.create_run(tc, g.user.username, "web", o["suites"], level=o["level"], role=o["role"],
                                      area=o["area"], repeat_of=run_id, repeat_warnings=warnings)
            audit.record(conn, actor=g.user.username, action="selftest.started", object_type="test_run", object_id=str(new_id),
                         details={"repeat_of": run_id, "warnings": warnings, "checks": o["checks"]})
        body = {"run_id": new_id, "level": o["level"], "suites": o["suites"], "role": o["role"], "area": o["area"],
                "repeat": run_id, "warnings": warnings, "by": g.user.username}
        from ..testing import waiter
        if waiter.platform_managed():          # no Docker socket (R2.44): the always-on runner service takes it
            with store.engine().begin() as conn:
                store.set_state(conn, new_id, step=f"{waiter.WAITING} (the failed checks again)")
            return {"run_id": new_id, "checks": o["checks"],
                    "message": f"Queued: the {o['checks']} failed check(s) of self-test {run_id} again, by the test runner service."}
        try:
            _ops_raw("POST", "/tests/build", {"by": g.user.username, "then": body}, timeout=60)
            with store.engine().begin() as conn:
                store.set_state(conn, new_id, step="Preparing the test runner (seconds when it is current), then the failed checks again")
        except Exception as exc:  # noqa: BLE001 - the run is closed with the reason
            msg = _ops_message(exc)
            with store.engine().begin() as conn:
                store.set_state(conn, new_id, state="error", message=f"Could not start: {msg}")
            abort(503, message=f"The self-test could not start: {msg}")
        return {"run_id": new_id, "checks": o["checks"],
                "message": f"Running the {o['checks']} failed check(s) of self-test {run_id} again."}


@blp.route("/tests/<int:run_id>/stop")
class TestStop(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, run_id):
        """Stops a running self-test: it ends at its next step, keeps what it found, and its tokens are revoked; one no one is
        running any more (its test runner was restarted or removed) is closed as stopped at once (R2.64)"""
        if run_id in _tidy():
            return {"message": f"Self-test {run_id} is closed as stopped: its test runner was no longer running."}
        with get_engine().begin() as conn, store.tests(conn) as tc:
            if not store.ask_stop(tc, run_id, g.user.username):
                abort(409, message=f"Self-test {run_id} is not running.")
            audit.record(conn, actor=g.user.username, action="selftest.stopped", object_type="test_run", object_id=str(run_id))
        try:
            _ops_raw("POST", "/tests/stop", {"run_id": run_id, "by": g.user.username}, timeout=30)
        except Exception:  # noqa: BLE001 - the runner also sees the request at its next step
            pass
        return {"message": "Stopping: it ends at its next step."}


@blp.route("/tests/<int:run_id>/browser")
class TestBrowser(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def post(self, data, run_id):
        """Journeys watched in this browser {results: [{name, outcome, detail, ms, browser, screenshot: PNG base64}], done}"""
        data = data or {}
        with store.engine().begin() as conn:
            row = store.run_row(conn, run_id)
            if not row or not row["watch"] or row["state"] not in store.OPEN:
                abort(409, message=f"Self-test {run_id} is not waiting for a browser.")
            for r in (data.get("results") or [])[:50]:
                shot = None
                if r.get("screenshot"):
                    try:
                        shot = base64.b64decode(str(r["screenshot"]).split(",")[-1], validate=True)[:3_000_000]
                    except (binascii.Error, ValueError):
                        shot = None
                outcome = r.get("outcome") if r.get("outcome") in store.OUTCOMES else "failed"
                nm = str(r.get("name") or "")[:300]
                nm = nm if nm.startswith(("page: ", "page sweep")) else f"journey: {nm}"   # the sweep names its own (D575)
                store.add_result(conn, run_id, "ui", nm, outcome,
                                 str(r.get("detail") or ""), int(r.get("ms") or 0), shot, "", "", "", str(r.get("browser") or "")[:200])
            if data.get("done"):
                store.set_browser(conn, run_id, {"done": True})
        return {"ok": True}


@blp.route("/tests/<int:run_id>/report")
class TestReport(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, run_id):
        """The run's report: ?format=html (default; one page, screenshots inside) or xlsx (Excel)"""
        fmt = request.args.get("format", "html")
        with store.engine().connect() as conn:
            try:
                if fmt == "xlsx":
                    return send_file(io.BytesIO(report.to_xlsx(conn, run_id)), as_attachment=True,
                                     download_name=f"self-test-{run_id}.xlsx",
                                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                body = report.to_html(conn, run_id)
            except KeyError:
                abort(404, message=f"No self-test run {run_id}.")
        return Response(body, mimetype="text/html", headers={"Content-Disposition": f'attachment; filename="self-test-{run_id}.html"'})


@blp.route("/tests/<int:run_id>/screenshot/<int:result_id>")
class TestScreenshot(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, run_id, result_id):
        """A failed browser journey's screenshot (PNG)"""
        with store.engine().connect() as conn:
            ok = conn.execute(text("SELECT 1 FROM tests.test_results WHERE id = :r AND run_id = :run"),
                              {"r": result_id, "run": run_id}).first()
            png = store.screenshot(conn, result_id) if ok else None
        if not png:
            abort(404, message="No screenshot.")
        return send_file(io.BytesIO(png), mimetype="image/png", download_name=f"self-test-{run_id}-{result_id}.png")


@blp.route("/tests/<int:run_id>/files/<path:name>")
class TestFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth("system.operate")
    def get(self, run_id, name):
        """A file of the run from work/tests/<folder>: run.log, a failed journey's video, the ZAP and Trivy reports"""
        with store.engine().connect() as conn:
            folder = conn.execute(text("SELECT folder FROM tests.test_runs WHERE id = :id"), {"id": run_id}).scalar()
        if not folder:
            abort(404, message=f"No files for self-test run {run_id}.")
        from .. import filestore
        if filestore.in_database():                  # no local file system: the run's files are in the store (R2.44)
            try:
                data = filestore.get("tests", f"{folder}/{name}")
            except ValueError:
                data = None
            if data is None:
                abort(404, message="No such file in this run.")
            return send_file(io.BytesIO(data), mimetype=filestore.kind_of(name), as_attachment=True,
                             download_name=name.rsplit("/", 1)[-1])
        base = (WORK_TESTS / folder).resolve()
        path = (base / name).resolve()
        if base not in path.parents or not path.is_file():
            abort(404, message="No such file in this run.")
        return send_file(path, as_attachment=True)


@blp.route("/tests/fixtures")
class Fixtures(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """Every self-test fixture still there (models, projects, service accounts, credentials), with its run, kind,
        name, when it was made and its size (?run=<id> for one run; ?purged=1 for those already purged too)"""
        run = request.args.get("run")
        with get_engine().connect() as conn:
            return {"fixtures": store.fixtures(conn, int(run) if run else None, request.args.get("purged") == "1")}


@blp.route("/tests/fixtures/purge")
class FixturesPurge(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth("system.operate")
    def post(self, data):
        """Purges self-test fixtures, for good (cannot be undone) {runs: [ids] or "all", fixtures: [fixture ids] (or every
        fixture of those runs), confirm: "DELETE"}: a background task, run by run; only what each run recorded.
        {dry_run: true}: what would be removed (each fixture, its run, and a model's entities, relationships and history
        versions), at once; nothing is deleted and no confirm is needed (R2.11)"""
        data = data or {}
        if data.get("dry_run"):
            with store.engine().connect() as conn:
                if data.get("runs") == "all":
                    runs = [r[0] for r in conn.execute(text("SELECT DISTINCT run_id FROM tests.test_fixtures "
                                                            "WHERE purged_at IS NULL ORDER BY run_id")).all()]
                else:
                    runs = sorted({int(x) for x in data.get("runs") or []})
                picked = {int(x) for x in data.get("fixtures") or []}
                if picked:
                    runs = sorted(set(runs) | {r[0] for r in conn.execute(text(
                        "SELECT DISTINCT run_id FROM tests.test_fixtures WHERE id = ANY(:i)"), {"i": list(picked)}).all()})
            from ..testing import fixtures as fx
            with get_engine().connect() as conn:
                p = fx.preview(conn, runs)
            if picked:
                p["fixtures"] = [f for f in p["fixtures"] if f["id"] in picked]
            return {"dry_run": True, **p, "text": fx.preview_text(p)}
        if data.get("confirm") != "DELETE":
            abort(400, message='Type DELETE to confirm: the fixtures are removed for good and cannot be brought back.')
        with store.engine().connect() as conn:
            if data.get("runs") == "all":
                runs = [r[0] for r in conn.execute(text(
                    "SELECT DISTINCT run_id FROM tests.test_fixtures WHERE purged_at IS NULL ORDER BY run_id")).all()]
            else:
                runs = sorted({int(x) for x in data.get("runs") or []})
            picked = [int(x) for x in data.get("fixtures") or []]
            if picked:
                runs = sorted(set(runs) | {r[0] for r in conn.execute(text(
                    "SELECT DISTINCT run_id FROM tests.test_fixtures WHERE id = ANY(:i)"), {"i": picked}).all()})
            busy = conn.execute(text("SELECT id FROM tests.test_runs WHERE id = ANY(:r) AND state IN ('queued', 'running')"),
                                {"r": runs}).scalar()
        if not runs:
            abort(400, message="Choose fixtures or runs to purge.")
        if busy:
            abort(409, message=f"Self-test {busy} is still running: stop it or let it finish first.")
        from .sheets import _task
        return {"task": _task("selftest.purge", None, f"Purge the fixtures of self-test run(s) {', '.join(map(str, runs))}",
                              {"runs": runs, "fixtures": picked})}


@blp.route("/scaling")
class Scaling(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def get(self):
        """The scaling rules of the API and job servers (fixed or by rules: fewest and most servers, people per server,
        CPU up and down, minutes, cool-down), the load seen and the decisions taken (D526)"""
        return _ops("GET", "/scaling", timeout=30)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("system.operate")
    def put(self, data):
        """Saves the scaling rules {settings: {EAX_SCALE_MODE: fixed|auto, EAX_SCALE_MIN, ...}} in the config file (a dated
        copy first); in auto mode the operations helper applies them every minute"""
        settings = (data or {}).get("settings") or {}
        if not isinstance(settings, dict):
            abort(400, message="settings is an object of EAX_SCALE_* values.")
        with get_engine().begin() as conn:
            audit.record(conn, actor=g.user.username, action="system.scaling", object_type="system", object_id="api",
                         details={"settings": settings})
        return _ops("POST", "/scaling", {"settings": settings, "by": g.user.username}, timeout=30)


@blp.route("/scaling/load")
class ScalingLoad(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    def get(self):
        """For the operations helper only (its X-Ops-Token): how many people the API has seen in the last 15 minutes"""
        import hmac
        token = os.environ.get("EAX_OPS_TOKEN", "")
        if not token or not hmac.compare_digest(request.headers.get("X-Ops-Token", ""), token):
            abort(401, message="For the operations helper only.")
        with get_engine().connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM core.known_users WHERE seen_at > now() - interval '15 minutes'")).scalar()
        return {"people": int(n or 0), "window_minutes": 15}


def _test_commands() -> dict:
    """The `eax test` entry of the shared command-line help (eaxcli/help.txt, mounted read-only like the documents), for
    the Self-test page's "From the command line" section: generated from the help, so it never drifts from it (D578)."""
    from .. import shipped_docs
    base = shipped_docs.root()
    for f in (base / "eaxcli" / "help.txt", base / "help.txt"):
        if f.is_file():
            return store.test_entry(f.read_text(encoding="utf-8"))
    return {"syntax": "", "summary": "", "options": [], "examples": []}

