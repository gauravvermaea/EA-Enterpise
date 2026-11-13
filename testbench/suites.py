"""Everything the inside self-test runs, run from outside (D580): the same levels, suites and filters as `eax test`, the
same code (services/api/eax/testing/, imported through shared.py).

How a run goes:
  1. the target's API description (openapi.json): public, so it answers even when nothing else works;
  2. a self-test run started on the target for the test bench (POST /api/v1/admin/tests, watch): the target makes its
     own fixtures (self_test_<id>_<n>) and test accounts; the bench takes the ids, ticket and tokens
     (GET /api/v1/admin/testbench/runs/<run>/session). Without a token, or when the target cannot start one, only the
     checks that need no fixtures run (anonymous refusals, the front door), and the report says so;
  3. smoke: the self-test's own smoke (eax/testing/run.smoke, every check it has), its browser part in every browser;
     detailed: db, api (matrix and writes), ui (every page and journey, every browser), security, as chosen;
  4. the results go back to the target's run (marked "external testbench"; all of them with --publish), which closes it.

COVERED lists the self-test calls the bench makes; tests/test_testbench.py checks every call the inside run makes is in
it, so a check can never be only inside."""

from __future__ import annotations

import base64
import time
import types

from . import SUITES, security_out, shared, ui
from .target import Client, message

# the self-test's calls this bench makes (or stands in for: ui_journeys.run_all -> ui.run, in every browser)
COVERED = {
    "smoke",                                                   # the whole smoke, with every check it holds
    "api_matrix.fetch_spec", "api_matrix.run", "api_writes.run",
    "db_checks.run", "db_checks.run_outside",
    "security.front_door", "security.python_dependencies", "security.read_zap", "security.read_trivy",
    "ui_journeys.run_all", "ui_flows.journeys", "ui_flows.run", "ui_pages.sweep", "ui_flows.skipped_in_browser",
}
# what the inside run calls that is the platform's own bookkeeping, not a test (made by the target for the bench)
BOOKKEEPING = {"fixtures.accounts", "fixtures.models_and_project", "fixtures.clean_leftovers", "report.write", "report.html", "report.xlsx",
               "store.create_run", "store.set_state", "store.set_browser", "store.clean_options", "store.clean_suites",
               "store.clean_journeys", "store.add_result", "store.short", "ui_pages.seeds",
               "store.repeat_options", "store.set_fixture_ids",   # a repeat's options and the ids it matches by (R2.36)
               "store.engine"}                                    # where the runs are kept (the tests database, R2.28)


class Session:
    """The target's self-test run the bench takes part in: ids, ticket, tokens."""
    def __init__(self, run_id=None, ids=None, ticket="", tokens=None, why=""):
        self.run_id, self.ids, self.ticket, self.tokens, self.why = run_id, ids or {}, ticket, tokens or {}, why

    @property
    def ok(self) -> bool:
        return bool(self.run_id and self.ticket)


def start_session(client: Client, role: str, run, wait_s: int = 900) -> Session:
    if not client.token:
        return Session(why="no token given (--token or EAX_TESTBENCH_TOKEN): only the checks that need no fixtures run")
    s, a = client.post("/api/v1/admin/tests", {"level": "detailed", "suites": ["ui"], "watch": True, "role": role})
    if s not in (200, 202):
        return Session(why=f"the target could not start a self-test run ({s}: {message(a)})")
    run_id = a.get("run_id")
    run.log(f"self-test run {run_id} started on the target for the test bench: making its fixtures")
    t0 = time.time()
    while time.time() - t0 < wait_s:
        s, a = client.get(f"/api/v1/admin/testbench/runs/{run_id}/session")
        if s == 200 and a.get("ready"):
            return Session(run_id, a.get("ids") or {}, a.get("ticket", ""), a.get("tokens") or {})
        if s not in (200, 599, 502, 503, 504):
            return Session(run_id, why=f"the run's fixtures could not be taken ({s}: {message(a)})")
        time.sleep(5)
    return Session(run_id, why=f"the target's run {run_id} did not make its fixtures within {wait_s // 60} minutes")


def _batches(run, everything: bool) -> list[tuple[str, list[dict]]]:
    t = run.tally()
    summary = {"name": "external testbench: summary", "outcome": "failed" if run.failed else "passed",
               "detail": f"{t['passed']} passed, {t['failed']} failed, {t['warning']} warnings, {t['skipped']} skipped; "
                         f"target {run.target}; browsers: {', '.join(run.browsers) or 'none'}; "
                         f"report on the test bench machine: {run.folder}"}
    out: list[tuple[str, list[dict]]] = [("smoke", [summary])]
    if everything:
        by: dict[str, list[dict]] = {}
        for r in run.results:
            by.setdefault(r.suite if r.suite in ("smoke", *SUITES) else "smoke", []).append({
                "name": r.name if r.suite in ("smoke", *SUITES) else f"{r.suite}: {r.name}", "outcome": r.outcome,
                "detail": r.detail, "ms": r.ms, "browser": r.browser, "request": r.request, "response": r.response,
                "screenshot": base64.b64encode(r.screenshot).decode() if r.screenshot else ""})
        for suite, rs in by.items():
            for i in range(0, len(rs), 100):
                out.append((suite, rs[i:i + 100]))
    return out


def _post(client: Client, run_id, batches, run, finish_with_done: bool) -> bool:
    for i, (suite, rs) in enumerate(batches):
        s, a = client.post(f"/api/v1/admin/testbench/runs/{run_id}/results",
                           {"suite": suite, "results": rs, "done": finish_with_done and i == len(batches) - 1})
        if s != 200:
            run.log(f"could not give the results to run {run_id} on {client.target}: {s} {message(a)}")
            return False
    return True


def publish(client: Client, sess: Session, run, everything: bool, to: Client | None = None) -> None:
    """Results into the self-test history (D581), marked "external testbench".

    The target's own run (the one that made the fixtures) always gets the summary and is closed (done); with --publish
    it gets every result. --publish <another address> puts every result into a new run in that installation's history."""
    elsewhere = to is not None and to.target != client.target
    if sess.run_id and client.token:
        if _post(client, sess.run_id, _batches(run, everything and not elsewhere), run, True):
            run.log(f"results given to the target's self-test run {sess.run_id}"
                    + (" (every result)" if everything and not elsewhere else " (the summary)"))
    if to is None or not to.token or (not elsewhere and sess.run_id):
        return
    s, a = to.post("/api/v1/admin/testbench/runs", {"level": run.level, "suites": [x for x in run.suites if x in SUITES],
                                                    "target": run.target, "version": run.version})
    if s != 200:
        run.log(f"could not publish to {to.target}: {s} {message(a)}")
        return
    rid = a.get("run_id")
    if _post(to, rid, _batches(run, True), run, False):
        s, a = to.post(f"/api/v1/admin/testbench/runs/{rid}/finish")
        run.log(f"published to {to.target}: self-test run {rid} ({a.get('state', s) if isinstance(a, dict) else s}), "
                "marked external testbench")


def run_all(run, client: Client, target: str, level: str, suites: list[str], role: str = "", area: str = "",
            journeys: list[str] | None = None, pages_only: bool = False, browsers: list[str] | None = None,
            db_dsn: str = "", publish_all: bool = False, zap: bool = True, trivy: bool = True,
            fixtures: bool = True, publish_to: Client | None = None) -> Session:
    api_matrix, api_writes, db_checks = shared.module("api_matrix"), shared.module("api_writes"), shared.module("db_checks")
    run_mod = shared.module("run")
    shared.point_at(target)
    browsers = browsers or ["chromium"]
    # 1. the API description: public
    try:
        spec = api_matrix.fetch_spec(target)
        run.version = str((spec.get("info") or {}).get("version") or "")
        run.recorder("smoke")("the target answers (its API description)", "passed", f"version {run.version}", 0)
    except Exception as exc:  # noqa: BLE001 - a broken platform: say so, and run what needs nothing
        run.recorder("smoke")("the target answers (its API description)", "failed", f"{target}/api/openapi.json: {exc}", 0)
        spec = {}
    # 2. the target's run, for its fixtures
    sess = start_session(client, role, run) if (fixtures and spec) else Session(why="--no-fixtures" if not fixtures else "the target does not answer")
    run.platform_run = sess.run_id
    if not sess.ok:
        run.recorder("smoke")("fixtures on the target", "skipped" if not client.token or not fixtures else "failed", sess.why, 0)
    tokens = {k: v for k, v in sess.tokens.items() if not role or k == role}
    try:
        if not sess.ok:                                           # independent: what needs no fixtures
            run.log("independent checks: every endpoint refused without a sign-in, and the front door")
            if spec:
                api_matrix.run(target, spec, {}, {}, None, run.recorder("api"), area=area)
            if "security" in suites or level == "smoke":
                security_out.run(run, target, run.version, zap=False, trivy=False)
            return sess
        if level == "smoke":
            run.log("smoke test: sign-in, every area, the key checks, then the browser part in every browser")
            shim = types.SimpleNamespace(run_all=lambda ids, ticket, folder, record, **kw: ui.run(
                run, target, ticket, ids, browsers, smoke=True))
            real = run_mod.ui_journeys
            run_mod.ui_journeys = shim
            try:
                run_mod.smoke(run, spec, tokens, sess.ids, sess.ticket)
            finally:
                run_mod.ui_journeys = real
            return sess
        if "db" in suites:
            run.log("database checks (read only)" + (" through the target's API" if not db_dsn else " on the database given"))
            db(run, client, db_dsn, db_checks)
        if "api" in suites:
            run.log(f"API: every endpoint{f' of {area}' if area else ''}, as {', '.join(tokens) or 'nobody'}; then the writes")
            api_matrix.run(target, spec, tokens, sess.ids, sess.ids.get("other_model"), run.recorder("api"), area=area)
            run.counts.update({f"writes {k}": v for k, v in
                               api_writes.run(target, tokens, sess.ids, run.recorder("api"), area=area).items()})
        if "ui" in suites:
            run.log("browser: every page, then the journeys, in " + ", ".join(browsers))
            run.counts.update(ui.run(run, target, sess.ticket, sess.ids, browsers, role=role, journeys=journeys,
                                     pages_only=pages_only))
        if "security" in suites:
            security_out.run(run, target, run.version, zap=zap, trivy=trivy)
    finally:
        publish(client, sess, run, publish_all, publish_to)
    return sess


def db(run, client: Client, dsn: str, db_checks) -> None:
    rec = run.recorder("db")
    if dsn:
        try:
            from sqlalchemy import create_engine  # noqa: PLC0415
            eng = create_engine(dsn, pool_pre_ping=True)
            with eng.connect() as conn:
                db_checks.run(conn, run.version, rec)
        except Exception as exc:  # noqa: BLE001
            rec("database checks", "failed", f"could not reach the database given: {str(exc).splitlines()[0][:300]}", 0)
        return
    s, a = client.post("/api/v1/admin/testbench/db-checks", timeout=300)
    if s != 200:
        rec("database checks", "skipped" if s in (401, 403) else "failed",
            f"the target's API did not run them ({s}: {message(a)}); give --db <dsn> to run them directly", 0)
        return
    for r in a.get("results") or []:
        rec(r.get("name", ""), r.get("outcome", "failed"), r.get("detail", ""), int(r.get("ms") or 0))


def fixtures_list(client: Client, run_id: str = "") -> tuple[int, object]:
    return client.get("/api/v1/admin/tests/fixtures" + (f"?run={run_id}" if run_id else ""))


def clean(client: Client, which: str) -> tuple[int, object]:
    runs = "all" if which == "all" else [int(which)]
    return client.post("/api/v1/admin/tests/fixtures/purge", {"runs": runs, "confirm": "DELETE"}, timeout=600)
