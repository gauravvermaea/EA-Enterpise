"""The self-test runner's steps (phase 36.1, D367, D522 to D529). Run inside the test runner container (the operations
helper starts it for System admin > Self-test and `eax test`; CI runs `eax test`):

  python -m eax.testing run [--level smoke|detailed] [--suites api,ui,db,security] [--role R] [--area A] [--watch]
                            [--run-id N] [--trigger web|eax|ci] [--by NAME] [--folder F]
        makes the run's fixtures (self_test_<id>_1, _2, _3 and its test accounts), runs the checks against the live API
        and the front door inside them, and writes the report. Prints RUN_ID=<n> first. With the security suite the run
        stays open ("waiting for the ZAP and Trivy scans") until `collect`.
  python -m eax.testing run --repeat N [--warnings] [--run-id N] ...
        a repeat (R2.36, D605): only the checks that failed in run N (0: the newest finished run), and those with
        warnings with --warnings; fresh fixtures as always. Prints "nothing to repeat" and makes no run when none failed.
  python -m eax.testing collect --run-id N [--error TEXT | --stopped BY]
        reads the ZAP and Trivy reports the operations helper left in the run's folder and closes the run.

Results go to the installation's database as they come (tests.test_runs, tests.test_results, tests.test_fixtures); files to
/results/<folder> (work/tests/<folder> on the host): run.log, videos of failed journeys, the scan reports, report.html and
report.xlsx. The run's fixtures are removed when it ends, however it ends (R2.11, D637; EAX_TEST_KEEP_DATA=1 keeps them
for the next run to remove)."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from . import (
    api_matrix,
    api_writes,
    db_checks,
    fixtures,
    repeat,
    report,
    security,
    store,
    ui_journeys,
)

RESULTS = Path(os.environ.get("EAX_TEST_RESULTS", "/results"))
API = os.environ.get("EAX_TEST_API_URL", "http://api:8000")


def _version() -> str:
    from .. import __version__
    return __version__


class Stopped(Exception):
    pass


class Run:
    """One run: its row, its folder and log, and a way to record results as they come."""

    def __init__(self, engine, run_id: int, folder: str, repo=None):
        self.engine, self.id, self.folder = engine, run_id, folder   # engine: the tests database's (R2.28)
        self.repo = repo if repo is not None else engine             # the repository's: the fixtures and database checks
        self.dir = RESULTS / folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.counts: dict[str, int] = {}
        self.only: set[tuple[str, str]] | None = None    # a repeat (R2.36): the checks to record, by suite and canon name
        self.ids: dict[str, str] = {}                     # this run's fixture ids (for the canon names)
        self.left_out = 0

    def where(self) -> str:
        """How far the run is, for the command line (R2.40): "[120 of about 900, 780 left]"."""
        with self.engine.connect() as conn:
            run = store.run_row(conn, self.id)
            done = conn.execute(text("SELECT count(*) FROM tests.test_results WHERE run_id = :id"), {"id": self.id}).scalar() or 0
            p = store.progress(conn, run, int(done)) if run else {"total": None, "done": done}
        return f"[{p['done']} of about {p['total']}, {p['left']} left]" if p.get("total") else f"[{p['done']} so far]"

    def log(self, msg: str) -> None:
        try:
            msg = f"{msg}  {self.where()}"
        except Exception:  # noqa: BLE001 - only a hint
            pass
        line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(self.dir / "run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with self.engine.begin() as conn:
            store.set_state(conn, self.id, step=msg[:300])
            asked = conn.execute(text("SELECT stop_asked FROM tests.test_runs WHERE id = :id"), {"id": self.id}).scalar()
        if asked:
            raise Stopped(asked)

    def recorder(self, suite: str):
        def record(name: str, outcome: str, detail: str = "", ms: int = 0, screenshot: bytes | None = None, video: str = "",
                   request: str = "", response: str = "", browser: str = "") -> None:
            if self.only is not None and (suite, repeat.canon(name, self.ids)) not in self.only:
                self.left_out += 1                # run because a repeated check needs it, not itself repeated
                return
            with self.engine.begin() as conn:
                store.add_result(conn, self.id, suite, name, outcome, detail, ms, screenshot, video, request, response, browser)
            print(f"  {outcome.upper():<8}{suite:<9}{name}" + (f": {detail[:160]}" if outcome in ("failed", "warning") else ""),
                  flush=True)
        return record


def smoke(r: Run, spec: dict, tokens: dict[str, str], ids: dict[str, str], ticket: str, rp: dict | None = None) -> None:
    """A few minutes: every test role can sign in, every main area answers, the key journeys work once. rp: a repeat's
    plan (R2.36): the API checks run again (seconds; only the failed ones are recorded), and only the failed pages and
    journeys open."""
    rec = r.recorder("smoke")
    for role, token in tokens.items():
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/me", token)
        rec(f"sign in as {role}", "passed" if s == 200 else "failed", f"{s}", int((time.time() - t0) * 1000),
            request="" if s == 200 else f"GET /api/v1/me  as {role}", response="" if s == 200 else f"{s}\n{body}")
    admin = tokens.get("super-admin") or next(iter(tokens.values()), None)
    from ..machine_access import AREA_CODES
    for area in [a for a in AREA_CODES if a != "mcp"]:
        eps = [e for e in api_matrix.endpoints(spec) if e["method"] == "get" and api_matrix.in_area(e["path"], area)]
        picked = [(e, p) for e, p in ((e, api_matrix.fill(e["path"], ids)) for e in eps)
                  if p and not api_matrix.HEAVY.search(e["path"])][:2]
        if not picked:
            rec(f"area {area} answers", "skipped", "no endpoint the run can fill", 0)
            continue
        for e, p in picked:
            t0 = time.time()
            s, body = api_matrix.call(API, "get", p, admin)
            outcome = "passed" if s < 400 else "warning" if s in (502, 503, 504) else "failed"
            rec(f"area {area} answers: GET {e['path']}", outcome, f"{s}", int((time.time() - t0) * 1000),
                request="" if outcome != "failed" else f"GET {p}  as super-admin",
                response="" if outcome != "failed" else f"{s}\n{body}")
    documentation(rec, tokens)
    deploy_page(rec, tokens)
    command_centre(rec, tokens)
    banner_and_schedules(rec, tokens)
    iterations(rec, tokens, ids)
    if rp is not None:
        routes = [x for x in (repeat.fill(rt, ids) for rt in rp["routes"]) if x]
        if routes or rp["journeys"]:
            r.log("the failed pages and journeys again, in a headless browser")
            r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), smoke=True, routes=routes,
                                                names=set(rp["journeys"])))
        return
    r.log("every page opens (as Super Admin) and the key journeys, in a headless browser")
    r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), smoke=True))


def _admin_journey(journeys: list[str] | None, role: str, pages_only: bool, names: set[str] | None = None) -> bool:
    """Whether this run's journeys change the installation's banner and schedules (the admin journey). names: a
    repeat's journeys (R2.36)."""
    from . import ui_flows
    if pages_only:
        return False
    if names is not None:
        return any(j.get("guard") == "admin" and any(n.startswith(f"journey: {j['name']}") for n in names)
                   for j in ui_flows.JOURNEYS)
    for j in ui_flows.JOURNEYS:
        if j.get("guard") == "admin" and (not journeys or any(o.lower() in j["name"].lower() for o in journeys)) \
                and ui_flows.role_plan(j, role):
            return True
    return False


def _admin_guard(tokens: dict[str, str], before, log, sid: str = ""):
    """before="before": reads the real banner and schedules; else puts them back as they were (D583)."""
    from . import ui_flows

    def call(method: str, path: str, body: dict | None = None):
        return api_writes.call(API, method, path, tokens.get("super-admin"), body)
    try:
        if before == "before":
            return ui_flows.admin_snapshot(call)
        done = ui_flows.admin_restore(call, before or {}, sid)
        log("admin journey: " + (", ".join(done) if done else "the banner and schedules were already as before"))
    except Exception as exc:  # noqa: BLE001 - said in the log; the run goes on
        log(f"admin journey: could not read or put back the banner and schedules: {exc}")
    return None


def _wait_for_browser(engine, run_id: int, r) -> None:
    r.log("waiting for the journeys in your browser (Self-test page): keep it open")
    for i in range(1800):
        with engine.connect() as conn:
            done = conn.execute(text("SELECT browser->>'done' FROM tests.test_runs WHERE id = :id"), {"id": run_id}).scalar()
        if done == "true":
            return
        if i and i % 30 == 0:
            r.log("waiting for the journeys in your browser (Self-test page)")
        time.sleep(2)
    r.recorder("ui")("journeys in the browser", "skipped", "the browser did not finish within an hour", 0)


def _post_json(path: str, token: str | None, body: dict) -> tuple[int, str]:
    import json as _json
    import urllib.error
    import urllib.request

    from ..service_split import route
    req = urllib.request.Request(route(API, path) + path, data=_json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4000).decode("utf-8", "replace")
    except OSError as exc:
        return 0, str(exc)


def iterations(rec, tokens: dict[str, str], ids: dict[str, str]) -> None:
    """D571-D574: in the run's own project, the iteration answers, a Transition Planning iteration freezes phase B (a
    change there is refused with 409), and a Full cycle opens it again. Only the run's project is touched."""
    project = ids.get("project")
    admin = tokens.get("super-admin") or next(iter(tokens.values()), None)
    if not project or not admin:
        rec("iterations: a project's ADM iteration", "skipped", "the run has no project", 0)
        return
    base = f"/api/v1/projects/{project}"
    steps = [("the iteration answers", lambda: api_matrix.call(API, "get", base + "/iteration", admin), {200}),
             ("Transition Planning (E, F) is chosen", lambda: _post_json(base + "/iteration", admin,
                                                                        {"iteration": "transition", "note": "self-test"}), {200}),
             ("phase B is frozen: marking it is refused", lambda: _post_json(base + "/phases/B", admin, {"complete": True}), {409}),
             ("a Full cycle opens it again", lambda: _post_json(base + "/iteration", admin, {"iteration": "full"}), {200})]
    for what, fn, ok_codes in steps:
        t0 = time.time()
        s, body = fn()
        ok = s in ok_codes
        rec(f"iterations: {what}", "passed" if ok else "failed", f"{s}", int((time.time() - t0) * 1000),
            request="" if ok else what, response="" if ok else f"{s}\n{body}")


def command_centre(rec, tokens: dict[str, str]) -> None:
    """D554: System admin > Command centre lists every eax command for admins (nothing is run) and refuses other
    people; a run with no known command is refused."""
    admin = tokens.get("super-admin") or tokens.get("it-admin")
    other = next((t for k, t in tokens.items() if k not in ("super-admin", "it-admin")), None)
    if admin:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands", admin, size=None)   # the whole list
        ok = s == 200 and '"status"' in body and '"cleanup"' in body
        rec("command centre: every eax command is listed", "passed" if ok else "warning" if s in (502, 503, 504) else "failed",
            f"{s}", int((time.time() - t0) * 1000), request="" if ok else "GET /api/v1/admin/commands",
            response="" if ok else f"{s}\n{body}")
        t0 = time.time()
        s, body = api_matrix.call(API, "post", "/api/v1/admin/commands/run", admin)   # no command: nothing runs
        rec("command centre: a run without a known command is refused", "passed" if s == 400 else "warning" if s in (502, 503, 504) else "failed",
            f"{s}", int((time.time() - t0) * 1000), request="" if s == 400 else "POST /api/v1/admin/commands/run {}",
            response="" if s == 400 else f"{s}\n{body}")
    if other:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands", other)
        rec("command centre: refused to people who are not IT or Super Admins", "passed" if s == 403 else "failed", f"{s}",
            int((time.time() - t0) * 1000), request="" if s == 403 else "GET /api/v1/admin/commands", response="" if s == 403 else body)


def banner_and_schedules(rec, tokens: dict[str, str]) -> None:
    """D558, D559: the banner answers every signed-in person (null when none is set: nothing shown); the schedules
    list for admins (kept in persist/, read without warnings) and is refused to others."""
    admin = tokens.get("super-admin") or tokens.get("it-admin")
    other = next((t for k, t in tokens.items() if k not in ("super-admin", "it-admin")), None)
    for who, tok in (("an admin", admin), ("a user", other)):
        if tok:
            t0 = time.time()
            s, body = api_matrix.call(API, "get", "/api/v1/banner", tok)
            ok = s == 200 and '"banner"' in body
            rec(f"banner: answers {who} (a banner or nothing)", "passed" if ok else "failed", f"{s}", int((time.time() - t0) * 1000),
                request="" if ok else "GET /api/v1/banner", response="" if ok else f"{s}\n{body}")
    if admin:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands/schedules", admin, size=None)
        ok = s == 200 and '"schedules"' in body
        warn = ok and '"warning": ""' not in body and '"warning":""' not in body
        rec("schedules: listed from persist/schedules.json", "warning" if warn or s in (502, 503, 504) else "passed" if ok else "failed",
            f"{s}", int((time.time() - t0) * 1000), request="" if ok and not warn else "GET /api/v1/admin/commands/schedules",
            response="" if ok and not warn else f"{s}\n{body[:2000]}")
    if other:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands/schedules", other)
        rec("schedules: refused to people who are not IT or Super Admins", "passed" if s == 403 else "failed", f"{s}",
            int((time.time() - t0) * 1000), request="" if s == 403 else "GET /api/v1/admin/commands/schedules", response="" if s == 403 else body)


def deploy_page(rec, tokens: dict[str, str]) -> None:
    """D555: System admin > Deploy answers its questions for admins (the operations helper behind it) and refuses others."""
    admin = tokens.get("super-admin") or tokens.get("it-admin")
    other = next((t for k, t in tokens.items() if k not in ("super-admin", "it-admin")), None)
    if admin:
        t0 = time.time()
        s, body = api_matrix.call(API, "post", "/api/v1/operations/deploys/questions", admin)
        ok = s == 200 and "hostname" in body
        rec("deploy: the questions answer (no laptop)", "passed" if ok and '"laptop"' not in body else
            "warning" if s in (502, 503, 504) else "failed", f"{s}", int((time.time() - t0) * 1000),
            request="" if ok else "POST /api/v1/operations/deploys/questions", response="" if ok else f"{s}\n{body}")
    if other:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/operations/deploys", other)
        rec("deploy: refused to people who are not IT or Super Admins", "passed" if s == 403 else "failed", f"{s}",
            int((time.time() - t0) * 1000), request="" if s == 403 else "GET /api/v1/operations/deploys", response="" if s == 403 else body)


def documentation(rec, tokens: dict[str, str]) -> None:
    """D550: every user reads the documents of the running version, and they are in the Enterprise library's folder."""
    user = next((t for k, t in tokens.items() if k not in ("super-admin", "it-admin")), None) or next(iter(tokens.values()), None)
    for what, path in (("the Documentation list answers", "/api/v1/documentation"),
                       ("a document opens (capabilities)", "/api/v1/documentation/capabilities"),
                       ("the documentation search answers", "/api/v1/documentation/search?q=backup")):
        t0 = time.time()
        s, body = api_matrix.call(API, "get", path, user, size=None)
        ok = s == 200 and any(k in body for k in ('"documents"', '"results"', '"html"', '"key"', '"version"'))
        rec(f"documentation: {what}", "passed" if ok else "failed", f"{s}", int((time.time() - t0) * 1000),
            request="" if ok else f"GET {path}", response="" if ok else f"{s}\n{body}")
    lib = os.environ.get("EAX_TEST_LIBRARY_URL", "http://library:8100")
    t0 = time.time()
    import urllib.error
    import urllib.request
    try:                                             # the whole answer: the folder list can be long
        req = urllib.request.Request(lib + "/api/library/v1/libraries/org",
                                     headers={"Accept": "application/json", **({"Authorization": f"Bearer {user}"} if user else {})})
        with urllib.request.urlopen(req, timeout=30) as resp:
            s, body = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        s, body = exc.code, ""
    except OSError:
        s, body = 0, ""
    if s in (502, 503, 504) or s == 0:
        rec("documentation: the Enterprise library folder", "skipped", "the library service is off or not reachable", 0)
        return
    ok = s == 200 and "EA Explorer documentation" in body
    rec("documentation: the Enterprise library has the EA Explorer documentation folder", "passed" if ok else "failed", f"{s}",
        int((time.time() - t0) * 1000), request="" if ok else "GET /api/library/v1/libraries/org", response="" if ok else f"{s}\n{body}")


def _backup_suite(r: Run, tokens: dict[str, str], ids: dict[str, str], run_id: int) -> None:
    """The backup checks (backups_check.py, R2.45), as the run's Super Admin; the restored model is the run's fixture."""
    from . import backups_check

    def add_fixture(kind: str, ident: str, name: str) -> None:
        with r.engine.begin() as conn:
            store.add_fixture(conn, run_id, kind, ident, name)
    r.log("backups: an infrastructure and an application backup, a trial restore of each (nothing live is touched)")
    backups_check.run(API, tokens.get("super-admin", ""), ids, r.recorder("backup"), r.log, r.repo, run_id, add_fixture)


def coverage_html(c: dict) -> str:
    import html as _h
    rows = "".join(f"<tr><td>{_h.escape(a['area'])}</td><td>{a['run']}</td><td>{a['lines']}</td><td>{a['percent']}%</td></tr>"
                   for a in c.get("areas") or [])
    files = "".join(f"<tr><td>{_h.escape(f['file'])}</td><td>{f['run']}</td><td>{f['lines']}</td><td>{f['percent']}%</td></tr>"
                    for f in c.get("files") or [])
    return ("<!doctype html><meta charset='utf-8'><title>Code coverage</title><style>body{font-family:sans-serif}"
            "td,th{padding:2px 8px;text-align:left}</style>"
            f"<h1>Code coverage of the API: {c.get('percent')}%</h1><p>{c.get('run')} of {c.get('lines')} lines of EA Explorer's "
            "code ran while the API was up (since it started; D642).</p>"
            f"<h2>By area</h2><table><tr><th>Area</th><th>Lines run</th><th>Lines</th><th>Covered</th></tr>{rows}</table>"
            f"<h2>By file, the least covered first</h2><table><tr><th>File</th><th>Lines run</th><th>Lines</th><th>Covered</th></tr>"
            f"{files}</table>")


def coverage_result(r: Run, token: str) -> dict | None:
    """The API's code coverage at the run's end (EAX_COVERAGE=on, D642): kept as coverage.json and coverage.html in the
    run's folder and as one result line (a measurement, never a failure)."""
    import json as _json
    t0 = time.time()
    s, body = api_matrix.call(API, "get", "/api/v1/admin/coverage", token, timeout=180, size=None)
    rec = r.recorder("api")
    try:
        c = _json.loads(body) if s == 200 else {}
    except ValueError:
        c = {}
    ms = int((time.time() - t0) * 1000)
    if not c.get("on") or c.get("percent") is None:
        rec("coverage: the API's code run by this test", "skipped", c.get("why") or f"HTTP {s}", ms)
        return None
    try:
        (r.dir / "coverage.json").write_text(_json.dumps(c, indent=1), encoding="utf-8")
        (r.dir / "coverage.html").write_text(coverage_html(c), encoding="utf-8")
    except OSError as exc:
        r.log(f"coverage files not written: {exc}")
    low = ", ".join(f"{a['area']} {a['percent']}%" for a in (c.get("areas") or [])[:4])
    rec("coverage: the API's code run by this test", "passed",
        f"{c['percent']}% of lines ({c['run']} of {c['lines']}); least covered areas: {low}; coverage.html in the run's folder",
        ms)
    r.counts["coverage %"] = c["percent"]
    return c


# the containers a run tests (owner, 13 Nov 2026: no waiting for everything to start; "Why is sample data and industry pack
# needed for testing?" They are not): the core and the second-tier services the checks use. The sample data, the
# industry packs and the demo estate are never waited for.
UNDER_TEST = {"api": "the API", "web": "the screens", "proxy": "the front door", "keycloak": "sign-in", "db": "the database",
              "operations": "the operations service", "personal": "the personal data service", "library": "the libraries",
              "views": "the drawn views", "reports": "Reports", "dms": "Documents", "drawio": "draw.io"}


def readiness(containers: list[dict]) -> dict[str, str]:
    """Each container under test: up, starting, failed, or off (switched off: not there, or stopped on purpose)."""
    out: dict[str, str] = {}
    for svc in UNDER_TEST:
        rows = [c for c in containers if c.get("service") == svc]
        if not rows:
            out[svc] = "off"
            continue
        states = []
        for c in rows:
            state, health = str(c.get("state") or "").lower(), str(c.get("health") or "").lower()
            if state == "running":
                states.append("starting" if health == "starting" else "failed" if health == "unhealthy" else "up")
            elif state in ("created", "restarting"):
                states.append("starting")
            elif state == "exited" and int(c.get("exit_code") or 0) == 0:
                states.append("off")
            else:
                states.append("failed")
        out[svc] = "up" if "up" in states else "starting" if "starting" in states else states[0]
    return out


def services_ready(r, token: str, wait: int = 600, pause: int = 10, call=None, sleep=time.sleep, clock=time.time) -> dict:
    """Waits only for the containers this run tests to finish starting (up to `wait` seconds), saying which on the run's
    step, so a test can start right after `eax clean-restart`. A switched-off one: its checks are skipped. One still not
    up at the end: a failed check with the reason; the run goes on."""
    import json as _json
    call = call or api_matrix.call
    t0, last = clock(), {}
    while True:
        s, body = call(API, "get", "/api/v1/admin/services/health", token, timeout=90, size=None)
        try:
            last = readiness(_json.loads(body).get("containers") or []) if s == 200 else last
        except ValueError:
            pass
        waiting = [k for k, v in last.items() if v == "starting"]
        if s == 200 and not waiting:
            break
        if clock() - t0 >= wait:
            break
        names = ", ".join(UNDER_TEST[k] for k in waiting) or "the services' state"
        r.log(f"waiting for {names} to finish starting")
        with r.engine.begin() as conn:
            store.set_state(conn, r.id, step=f"Waiting for {names} to finish starting")
        sleep(pause)
    rec, ms = r.recorder("smoke"), int((clock() - t0) * 1000)
    up = sorted(k for k, v in last.items() if v == "up")
    rec("start-up: the services under test are up", "passed" if up and not any(v in ("starting", "failed") for v in last.values())
        else "failed", "; ".join(f"{UNDER_TEST[k]} {v}" for k, v in sorted(last.items()) if v != "up") or "all up", ms)
    for k, v in sorted(last.items()):
        if v == "off":
            rec(f"start-up: {UNDER_TEST[k]}", "skipped", "switched off: its checks are skipped", 0)
        elif v in ("starting", "failed"):
            rec(f"start-up: {UNDER_TEST[k]}", "failed",
                "still starting after the wait" if v == "starting" else "stopped or unhealthy", ms)
    return last


def alert_check(api: str, token: str, rec, log, wait: int = 150, pause: int = 10) -> None:
    """R2.19, as the owner asked: a container "stopped on purpose" (a test alert: the watcher tells it as if api had
    stopped; nothing is stopped), then the alert and its recovery notice, within the watcher's next looks."""
    import json as _json
    t0 = time.time()
    s, _ = api_matrix.call(api, "post", "/api/v1/admin/alerts/test", token)
    if s != 200:
        rec("alerts: a test alert is raised", "failed", f"HTTP {s}", int((time.time() - t0) * 1000))
        return
    log(f"alerts: waiting up to {wait} s for the watcher's alert and recovery notice")
    seen: set[str] = set()
    while time.time() - t0 < wait:
        s, body = api_matrix.call(api, "get", "/api/v1/admin/alerts", token, size=None)
        try:
            hist = _json.loads(body).get("history") or []
        except ValueError:
            hist = []
        seen |= {h.get("event") for h in hist if h.get("at") and h["at"] >= t0 - 5 and "test alert" in str(h.get("detail") or "")
                 or (h.get("at") and h["at"] >= t0 - 5 and h.get("event") == "recovered" and h.get("kind") == "stopped")}
        if {"alert", "recovered"} <= seen:
            break
        time.sleep(pause)
    ms = int((time.time() - t0) * 1000)
    rec("alerts: a container that stops raises an alert", "passed" if "alert" in seen else "failed",
        "" if "alert" in seen else "no alert from the watcher in time", ms)
    rec("alerts: its recovery is told", "passed" if "recovered" in seen else "failed",
        "" if "recovered" in seen else "no recovery notice in time", ms)


def _repeat_detailed(r: Run, p: dict, spec: dict, tokens: dict[str, str], test_tokens: dict[str, str], ids: dict[str, str],
                     ticket: str, role: str, area: str) -> bool:
    """A detailed repeat (R2.36): each suite only as far as its failed checks need. Returns whether ZAP or Trivy run
    next (scans.json in the run's folder says which)."""
    import json as _json
    if p["db"]:
        r.log("database checks again (read only)")
        with r.repo.connect() as conn:
            db_checks.run(conn, _version(), r.recorder("db"))
    if p["api"]:
        r.log(f"API: the {len(p['api'])} failed endpoint check(s) again")
        api_matrix.run(API, spec, test_tokens, ids, ids.get("other_model"), r.recorder("api"), area=area, only=set(p["api"]))
    if p["writes"]:
        r.log(f"API writes: up to the last failed one ({len(p['writes'])} to repeat)")
        api_writes.run(API, test_tokens, ids, r.recorder("api"), area=area, only=set(p["writes"]))
    routes = [x for x in (repeat.fill(rt, ids) for rt in p["routes"]) if x]
    if routes or p["journeys"]:
        names = set(p["journeys"])
        guarded = _admin_journey(None, role, False, names)
        before = _admin_guard(tokens, "before", r.log) if guarded else None
        try:
            r.log(f"browser: {len(routes)} page(s) and {len(names)} journey(s) again (Chromium, headless)")
            r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), role=role, routes=routes, names=names))
        finally:
            if guarded:
                _admin_guard(tokens, before, r.log, sid=ids.get("sid", ""))
    if p["front_door"]:
        r.log("security: headers and cookies at the front door, Python dependencies")
        rec = r.recorder("security")
        security.front_door(rec)
        security.python_dependencies(rec)
    if "backup" in p["suites"]:                     # the backup checks run as one (each needs the one before)
        _backup_suite(r, tokens, ids, r.id)
    sc = repeat.scans(p)
    if sc["zap"] or sc["images"]:
        (r.dir / repeat.SCANS).write_text(_json.dumps(sc), encoding="utf-8")
        return True
    return False


def cmd_run(args) -> int:
    from ..db import get_engine
    engine, repo = store.engine(), get_engine()      # the run's record, and the architecture its fixtures live in
    level, role, area = store.clean_options(args.level, args.role, args.area)
    suites = store.clean_suites(args.suites)
    folder = args.folder or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rep_of, rep_warn = None, bool(args.warnings)
    with engine.begin() as conn:
        if args.run_id:                             # recorded by the Self-test page: a repeat says so in its row
            got = conn.execute(text("SELECT repeat_of, repeat_warnings FROM tests.test_runs WHERE id = :id"),
                               {"id": args.run_id}).first()
            if got and got[0]:
                rep_of, rep_warn = int(got[0]), bool(got[1])
        if args.repeat is not None and not rep_of:  # `eax test failed [N]`: what it repeats, before any run is made
            try:
                o = store.repeat_options(conn, args.repeat or None, rep_warn)
            except ValueError as exc:
                print(str(exc), flush=True)
                if args.run_id:
                    store.set_state(conn, args.run_id, state="error", message=str(exc))
                return 0 if "nothing to repeat" in str(exc) else 2
            rep_of, level, role, area, suites = o["of"], o["level"], o["role"], o["area"], o["suites"]
            print(f"Repeating the {o['checks']} failed check(s) of self-test {rep_of}"
                  + (" (and its warnings)" if rep_warn else "") + ".", flush=True)
        run_id = args.run_id or store.create_run(conn, args.by or "eax test", args.trigger, suites, folder, _version(), level,
                                                 role, area, args.watch, repeat_of=rep_of, repeat_warnings=rep_warn)
        store.set_state(conn, run_id, state="running", folder=folder, version=_version())
        run = dict(conn.execute(text("SELECT id, run_guid::text AS run_guid, started_by FROM tests.test_runs WHERE id = :id"),
                                {"id": run_id}).mappings().first())
    print(f"RUN_ID={run_id}", flush=True)
    r = Run(engine, run_id, folder, repo)
    by = run["started_by"]
    error, stopped, keep_open = "", "", False
    try:
        r.log(f"self-test {run_id} ({store.short(run['run_guid'])}): {level}"
              + (f", the failed checks of run {rep_of} again" + (" (and its warnings)" if rep_warn else "") if rep_of else "")
              + ("" if level == "smoke" else f", {', '.join(suites)}") + (f", role {role}" if role else "")
              + (f", area {area}" if area else "") + (", watched in a browser" if args.watch else ""))
        roles = ["super-admin"] + ([role] if role and role != "super-admin" else [] if role else store.TEST_ROLES[1:])
        fixtures.clean_leftovers(repo, run_id, by, r.log)   # earlier runs' test data goes first (D593)
        with repo.begin() as conn:
            tokens = fixtures.accounts(conn, run, by, roles, r.log)
        services_ready(r, tokens.get("super-admin", ""))   # only what this run tests, never the sample data or packs
        ids = fixtures.models_and_project(repo, run, by, roles, r.log)
        with engine.begin() as conn:
            store.set_fixture_ids(conn, run_id, ids)
        p = None
        if rep_of:                                   # only the failed checks are recorded from here (R2.36)
            with engine.connect() as conn:
                p = repeat.plan(repeat.wanted(conn, rep_of, rep_warn), repeat.fixture_ids(conn, rep_of))
            r.only, r.ids = p["keys"], ids
            r.log(f"repeating {len(p['keys'])} check(s) of run {rep_of}: {', '.join(p['suites'])}")
        test_tokens = {k: v for k, v in tokens.items() if not role or k == role}
        ticket = secrets.token_urlsafe(24)
        from . import ui_flows, ui_pages
        journeys = store.clean_journeys(args.journey)
        with engine.begin() as conn:
            store.set_browser(conn, run_id, {
                "ticket": ticket, "tokens": tokens, "done": False,
                # what the admin's own browser runs (TestRuns.jsx): the same page sweep and journeys (D575, D576)
                "pages": [] if journeys else ui_pages.seeds(ids), "pages_skip": ui_pages.SKIP_ROUTES,
                "scope": [v for k, v in ids.items() if k in ("model", "other_model", "project", "entity") and v],
                "journeys": [] if args.pages_only else ui_flows.journeys(ids, role=role, only=journeys, watch=True)})
        spec = api_matrix.fetch_spec(API)
        if level == "smoke":
            r.log("smoke test: sign-in, every area, the key journeys" if not p else "smoke test: the failed checks again")
            smoke(r, spec, test_tokens, ids, ticket, p)
        elif p is not None:
            keep_open = _repeat_detailed(r, p, spec, tokens, test_tokens, ids, ticket, role, area)
        else:
            if "db" in suites:
                r.log("database checks (read only)")
                with repo.connect() as conn:
                    db_checks.run(conn, _version(), r.recorder("db"))
            if "api" in suites:
                r.log(f"API: every endpoint{f' of {area}' if area else ''}, as {', '.join(test_tokens)}")
                api_matrix.run(API, spec, test_tokens, ids, ids.get("other_model"), r.recorder("api"), area=area)
                r.log("API writes, area by area, inside the run's own fixtures (and the same writes refused)")
                r.counts.update({f"writes {k}": v for k, v in api_writes.run(API, test_tokens, ids, r.recorder("api"),
                                                                              area=area).items()})
            guarded = "ui" in suites and not getattr(args, "ui_review", False) and _admin_journey(journeys, role, args.pages_only)
            if guarded:                                  # the real banner and schedules, put back however the run ends (D583)
                admin_before = _admin_guard(tokens, "before", r.log)
            try:
                if "ui" in suites and getattr(args, "ui_review", False):   # the UI review only (R2.12)
                    from . import ui_review
                    r.log("UI review: every main page as each role at three widths (screenshots and notes, nothing changed)")
                    r.counts.update(ui_review.run(ids, ticket, r.dir, r.recorder("ui"), roles=[role] if role else None))
                elif "ui" in suites and not args.watch:
                    r.log("browser: every page, then the journeys (Chromium, headless)" if not (journeys or args.pages_only)
                          else "browser: the page sweep" if args.pages_only else f"browser: journey {', '.join(journeys)}")
                    r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), role=role, journeys=journeys,
                                                        pages_only=args.pages_only))
                if "ui" in suites and args.watch:
                    _wait_for_browser(engine, run_id, r)
            finally:
                if guarded:
                    _admin_guard(tokens, admin_before, r.log, sid=ids.get("sid", ""))
            if "ui" in suites and args.watch:
                for why in ui_flows.skipped_in_browser():
                    name, _, reason = why.partition(": ")
                    r.recorder("ui")(f"journey: {name}", "skipped", f"headless only: {reason}", 0)
            if "security" in suites:
                rec = r.recorder("security")
                r.log("security: headers and cookies at the front door, Python dependencies")
                security.front_door(rec)
                security.python_dependencies(rec)
                keep_open = True
            if "api" in suites and not area:          # container alerts and their recovery (R2.19)
                alert_check(API, tokens.get("super-admin", ""), r.recorder("api"), r.log)
            if "backup" in suites:                    # the last: backups and trial restores (R2.45)
                _backup_suite(r, tokens, ids, run_id)
        coverage_result(r, tokens.get("super-admin", ""))   # what of the API's code this run made it run (D642)
    except Stopped as exc:
        stopped = str(exc)
    except Exception as exc:  # noqa: BLE001 - the run itself broke: kept as an error with the reason
        error = f"{exc}"
        print(f"ERROR: {exc}", flush=True)
        with open(r.dir / "run.log", "a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    _close_access(engine, run_id, by, repo)
    if keep_open and not (error or stopped):
        with engine.begin() as conn:
            store.set_state(conn, run_id, step="waiting for the ZAP baseline scan and the Trivy image scans")
        print("SCANS_NEXT", flush=True)  # the operations helper runs ZAP and Trivy (scans.json), then `collect` closes the run
        return 0
    return _close(engine, r, error, stopped)


def _close_access(engine, run_id: int, by: str, repo=None) -> None:
    """When its checks end the run's tokens are revoked and its browser ticket forgotten: the accounts and models stay
    (fixtures, until someone purges them), but nobody can sign in with them any more. engine: the tests database's;
    repo: the repository's, where the credentials are."""
    from .. import machine_access as ma
    from .. import permissions as perms
    with engine.connect() as conn:
        creds = [g for (g,) in conn.execute(text("SELECT ident FROM tests.test_fixtures WHERE run_id = :r AND kind = 'credential' "
                                                 "AND purged_at IS NULL"), {"r": run_id}).all()]
    with (repo if repo is not None else engine).begin() as conn:
        for guid in creds:
            try:
                ma.revoke(conn, by, [perms.SUPER_ADMIN], guid, "the self-test run ended")
            except Exception:  # noqa: BLE001
                pass
    with engine.begin() as conn:
        conn.execute(text("UPDATE tests.test_runs SET browser = jsonb_build_object('done', true) WHERE id = :id"), {"id": run_id})


SUITE_NAMES = {"smoke": "Smoke", "api": "API", "ui": "Pages and journeys", "db": "Database", "security": "Security"}


def summary_text(d: dict) -> str:
    """What a run found, for the command line (owner, 12 Nov 2026: "when test have executed from command line, they
    should give a summary of what passed what failed"): the counts per suite, the functional health and why, and every
    failure by name (critical first), each with its reason."""
    from . import health
    hs, results = d["health"], d["results"]
    lines = ["", "=" * 78, f"Self-test {d['run']['id']}: summary", "-" * 78,
             f"{'Suite':<22}{'passed':>8}{'failed':>8}{'warnings':>10}{'skipped':>9}"]
    for suite, n in hs["suites"].items():
        lines.append(f"{SUITE_NAMES.get(suite, suite):<22}{n['passed']:>8}{n['failed']:>8}{n['warning']:>10}{n['skipped']:>9}")
    t = d["tally"]
    lines += [f"{'All':<22}{t['passed']:>8}{t['failed']:>8}{t['warning']:>10}{t['skipped']:>9}", "-" * 78,
              f"Functional health: {hs['health']}: {hs['reason']}",
              f"  critical {hs['critical']['failed']} failed of {sum(hs['critical'].values())}, non-critical "
              f"{hs['non_critical']['failed']} failed of {sum(hs['non_critical'].values())}; security "
              f"{hs['security']['failed']} failed, {hs['security']['warning']} warnings (not counted in the health)"]
    failed = [x for x in results if x["outcome"] == "failed"]
    if failed:
        failed.sort(key=lambda x: health.importance(x["suite"], x["name"]) != "critical")
        lines += ["-" * 78, f"Failed ({len(failed)}):"]
        for x in failed:
            imp = "CRITICAL" if health.importance(x["suite"], x["name"]) == "critical" else "        "
            lines.append(f"  {imp} {x['suite']:<9} {x['name'][:90]}")
            if x.get("detail"):
                lines.append(f"           {' ' * 9} {str(x['detail']).splitlines()[0][:110]}")
    warned = [x for x in results if x["outcome"] == "warning"]
    if warned:
        lines += [f"Warnings ({len(warned)}): " + "; ".join(x["name"][:60] for x in warned[:8]) + ("…" if len(warned) > 8 else "")]
    rp = d.get("repeat")
    if rp:                                           # a repeat: each check then and now (R2.36)
        lines += ["-" * 78, f"Repeat of self-test {rp['of']}: {rp['fixed']} of {len(rp['checks'])} now pass"
                  + (" (the earlier run is followed up)" if rp["all_passed"] else ""),
                  f"  {'then':<9}{'now':<14}check"]
        for c in rp["checks"]:
            lines.append(f"  {c['then']:<9}{c['now']:<14}{c['suite']:<9} {c['name'][:80]}")
    lines.append("=" * 78)
    return "\n".join(lines)


def _close(engine, r: Run, error: str = "", stopped: str = "") -> int:
    with engine.begin() as conn:
        state = store.finish(conn, r.id, error, stopped)
        if not (error or stopped) and repeat.mark_followed_up(conn, r.id):
            print("Every repeated check passes now: the earlier run is marked as followed up.", flush=True)
    if getattr(r, "repo", None) is not None:          # the run's test data goes now, however it ended (R2.11)
        fixtures.remove_at_end(r.repo, r.id, lambda m: print(m, flush=True))
    try:
        with engine.connect() as conn:
            (r.dir / "report.html").write_text(report.to_html(conn, r.id), encoding="utf-8")
            (r.dir / "report.xlsx").write_bytes(report.to_xlsx(conn, r.id))
    except Exception as exc:  # noqa: BLE001 - the results are in the database whatever happens to the files
        print(f"the report files could not be written: {exc}", flush=True)
    from .. import filestore
    if filestore.in_database():                      # no local file system (R2.44, D635): the run's folder into the store
        try:
            print(f"{filestore.put_folder('tests', r.dir, r.folder)} file(s) of the run kept in the file store", flush=True)
        except Exception as exc:  # noqa: BLE001 - the results are in the database whatever happens to the files
            print(f"the run's files could not be put in the file store: {exc}", flush=True)
    try:                                             # the summary at the end (owner, 12 Nov 2026: R2.35, D604)
        with engine.connect() as conn:
            print(summary_text(store.run_detail(conn, r.id)), flush=True)
    except Exception:  # noqa: BLE001 - the report files and the page have it all
        pass
    print(f"self-test {r.id} {state}: work/tests/{r.folder}/report.html", flush=True)
    return 0 if state == "passed" else 1


def cmd_collect(args) -> int:
    from ..db import get_engine
    engine, repo = store.engine(), get_engine()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT folder, state, started_by FROM tests.test_runs WHERE id = :id"), {"id": args.run_id}).first()
    if not row:
        print(f"No self-test run {args.run_id}.")
        return 2
    if row[1] not in store.OPEN:
        print(f"Self-test run {args.run_id} is closed already ({row[1]}).")
        return 0 if row[1] == "passed" else 1
    r = Run.__new__(Run)
    r.engine, r.repo, r.id, r.folder, r.dir = engine, repo, args.run_id, row[0], RESULTS / row[0]
    r.dir.mkdir(parents=True, exist_ok=True)
    r.only, r.ids, r.left_out, r.counts = None, {}, 0, {}
    with engine.connect() as conn:                   # a repeat records only the scans that failed before (R2.36)
        rp = conn.execute(text("SELECT repeat_of, repeat_warnings FROM tests.test_runs WHERE id = :id"), {"id": args.run_id}).first()
        if rp and rp[0]:
            r.only = repeat.plan(repeat.wanted(conn, int(rp[0]), bool(rp[1])), repeat.fixture_ids(conn, int(rp[0])))["keys"]
            r.ids = repeat.fixture_ids(conn, args.run_id)
    if not (args.error or args.stopped):
        rec = r.recorder("security")
        security.read_zap(r.dir / "zap.json", rec)
        security.read_trivy(r.dir, rec)
    _close_access(engine, args.run_id, row[2], repo)
    return _close(engine, r, args.error or "", args.stopped or "")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m eax.testing")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("--level", default="smoke", choices=["smoke", "detailed"])
    a.add_argument("--suites", default="all")
    a.add_argument("--role", default="")
    a.add_argument("--area", default="")
    a.add_argument("--watch", action="store_true")
    a.add_argument("--journey", action="append", default=[])
    a.add_argument("--pages-only", action="store_true")
    a.add_argument("--ui-review", action="store_true", help="screenshots of every main page, each role, three widths (R2.12)")
    a.add_argument("--run-id", type=int, default=0)
    a.add_argument("--trigger", default="eax", choices=["web", "eax", "ci"])
    a.add_argument("--by", default="")
    a.add_argument("--folder", default="")
    a.add_argument("--repeat", type=int, default=None, help="repeat run N's failed checks (0: the newest finished run)")
    a.add_argument("--warnings", action="store_true", help="with --repeat: its warnings too")
    c = sub.add_parser("collect")
    c.add_argument("--run-id", type=int, required=True)
    c.add_argument("--error", default="")
    c.add_argument("--stopped", default="")
    args = p.parse_args(argv)
    t0 = time.time()
    code = cmd_run(args) if args.cmd == "run" else cmd_collect(args)
    print(f"({time.time() - t0:.0f} s)", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
