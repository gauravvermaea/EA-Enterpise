"""The self-test runner's steps (phase 36.1, D367, D522 to D529). Run inside the test runner container (the operations
helper starts it for System admin > Self-test and `eax test`; CI runs `eax test`):

  python -m eax.testing run [--level smoke|detailed] [--suites api,ui,db,security] [--role R] [--area A] [--watch]
                            [--run-id N] [--trigger web|eax|ci] [--by NAME] [--folder F]
        makes the run's fixtures (self_test_<id>_1, _2, _3 and its test accounts), runs the checks against the live API
        and the front door inside them, and writes the report. Prints RUN_ID=<n> first. With the security suite the run
        stays open ("waiting for the ZAP and Trivy scans") until `collect`.
  python -m eax.testing collect --run-id N [--error TEXT | --stopped BY]
        reads the ZAP and Trivy reports the operations helper left in the run's folder and closes the run.

Results go to the installation's database as they come (core.test_runs, core.test_results, core.test_fixtures); files to
/results/<folder> (work/tests/<folder> on the host): run.log, videos of failed journeys, the scan reports, report.html and
report.xlsx. Nothing is ever purged here: the fixtures stay until someone removes them (D529)."""

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

from . import api_matrix, api_writes, db_checks, fixtures, report, security, store, ui_journeys

RESULTS = Path(os.environ.get("EAX_TEST_RESULTS", "/results"))
API = os.environ.get("EAX_TEST_API_URL", "http://api:8000")


def _version() -> str:
    from .. import __version__
    return __version__


class Stopped(Exception):
    pass


class Run:
    """One run: its row, its folder and log, and a way to record results as they come."""

    def __init__(self, engine, run_id: int, folder: str):
        self.engine, self.id, self.folder = engine, run_id, folder
        self.dir = RESULTS / folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.counts: dict[str, int] = {}

    def log(self, msg: str) -> None:
        line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(self.dir / "run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with self.engine.begin() as conn:
            store.set_state(conn, self.id, step=msg[:300])
            asked = conn.execute(text("SELECT stop_asked FROM core.test_runs WHERE id = :id"), {"id": self.id}).scalar()
        if asked:
            raise Stopped(asked)

    def recorder(self, suite: str):
        def record(name: str, outcome: str, detail: str = "", ms: int = 0, screenshot: bytes | None = None, video: str = "",
                   request: str = "", response: str = "", browser: str = "") -> None:
            with self.engine.begin() as conn:
                store.add_result(conn, self.id, suite, name, outcome, detail, ms, screenshot, video, request, response, browser)
            print(f"  {outcome.upper():<8}{suite:<9}{name}" + (f": {detail[:160]}" if outcome in ("failed", "warning") else ""),
                  flush=True)
        return record


def smoke(r: Run, spec: dict, tokens: dict[str, str], ids: dict[str, str], ticket: str) -> None:
    """A few minutes: every test role can sign in, every main area answers, the key journeys work once."""
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
    r.log("every page opens (as Super Admin) and the key journeys, in a headless browser")
    r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), smoke=True))


def _post_json(path: str, token: str | None, body: dict) -> tuple[int, str]:
    import json as _json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(API + path, data=_json.dumps(body).encode(), method="POST",
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
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands", admin)
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
        s, body = api_matrix.call(API, "get", "/api/v1/admin/commands/schedules", admin)
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
        s, body = api_matrix.call(API, "post", "/api/v1/deploys/questions", admin)
        ok = s == 200 and "hostname" in body
        rec("deploy: the questions answer (no laptop)", "passed" if ok and '"laptop"' not in body else
            "warning" if s in (502, 503, 504) else "failed", f"{s}", int((time.time() - t0) * 1000),
            request="" if ok else "POST /api/v1/deploys/questions", response="" if ok else f"{s}\n{body}")
    if other:
        t0 = time.time()
        s, body = api_matrix.call(API, "get", "/api/v1/deploys", other)
        rec("deploy: refused to people who are not IT or Super Admins", "passed" if s == 403 else "failed", f"{s}",
            int((time.time() - t0) * 1000), request="" if s == 403 else "GET /api/v1/deploys", response="" if s == 403 else body)


def documentation(rec, tokens: dict[str, str]) -> None:
    """D550: every user reads the documents of the running version, and they are in the Enterprise library's folder."""
    user = next((t for k, t in tokens.items() if k not in ("super-admin", "it-admin")), None) or next(iter(tokens.values()), None)
    for what, path in (("the Documentation list answers", "/api/v1/documentation"),
                       ("a document opens (capabilities)", "/api/v1/documentation/capabilities"),
                       ("the documentation search answers", "/api/v1/documentation/search?q=backup")):
        t0 = time.time()
        s, body = api_matrix.call(API, "get", path, user)
        ok = s == 200 and ("version" in body or "results" in body)
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


def cmd_run(args) -> int:
    from ..db import get_engine
    engine = get_engine()
    level, role, area = store.clean_options(args.level, args.role, args.area)
    suites = store.clean_suites(args.suites)
    folder = args.folder or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with engine.begin() as conn:
        run_id = args.run_id or store.create_run(conn, args.by or "eax test", args.trigger, suites, folder, _version(), level,
                                                 role, area, args.watch)
        store.set_state(conn, run_id, state="running", folder=folder, version=_version())
        run = dict(conn.execute(text("SELECT id, run_guid::text AS run_guid, started_by FROM core.test_runs WHERE id = :id"),
                                {"id": run_id}).mappings().first())
    print(f"RUN_ID={run_id}", flush=True)
    r = Run(engine, run_id, folder)
    by = run["started_by"]
    error, stopped, keep_open = "", "", False
    try:
        r.log(f"self-test {run_id} ({store.short(run['run_guid'])}): {level}"
              + ("" if level == "smoke" else f", {', '.join(suites)}") + (f", role {role}" if role else "")
              + (f", area {area}" if area else "") + (", watched in a browser" if args.watch else ""))
        roles = ["super-admin"] + ([role] if role and role != "super-admin" else [] if role else store.TEST_ROLES[1:])
        with engine.begin() as conn:
            tokens = fixtures.accounts(conn, run, by, roles, r.log)
        ids = fixtures.models_and_project(engine, run, by, roles, r.log)
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
            r.log("smoke test: sign-in, every area, the key journeys")
            smoke(r, spec, test_tokens, ids, ticket)
        else:
            if "db" in suites:
                r.log("database checks (read only)")
                with engine.connect() as conn:
                    db_checks.run(conn, _version(), r.recorder("db"))
            if "api" in suites:
                r.log(f"API: every endpoint{f' of {area}' if area else ''}, as {', '.join(test_tokens)}")
                api_matrix.run(API, spec, test_tokens, ids, ids.get("other_model"), r.recorder("api"), area=area)
                r.log("API writes, area by area, inside the run's own fixtures (and the same writes refused)")
                r.counts.update({f"writes {k}": v for k, v in api_writes.run(API, test_tokens, ids, r.recorder("api"),
                                                                              area=area).items()})
            if "ui" in suites and not args.watch:
                r.log("browser: every page, then the journeys (Chromium, headless)" if not (journeys or args.pages_only)
                      else "browser: the page sweep" if args.pages_only else f"browser: journey {', '.join(journeys)}")
                r.counts.update(ui_journeys.run_all(ids, ticket, r.dir, r.recorder("ui"), role=role, journeys=journeys,
                                                    pages_only=args.pages_only))
            if "ui" in suites and args.watch:
                r.log("waiting for the journeys in your browser (Self-test page): keep it open")
                for i in range(1800):
                    with engine.connect() as conn:
                        done = conn.execute(text("SELECT browser->>'done' FROM core.test_runs WHERE id = :id"), {"id": run_id}).scalar()
                    if done == "true":
                        break
                    if i and i % 30 == 0:
                        r.log("waiting for the journeys in your browser (Self-test page)")
                    time.sleep(2)
                else:
                    r.recorder("ui")("journeys in the browser", "skipped", "the browser did not finish within an hour", 0)
                for why in ui_flows.skipped_in_browser():
                    name, _, reason = why.partition(": ")
                    r.recorder("ui")(f"journey: {name}", "skipped", f"headless only: {reason}", 0)
            if "security" in suites:
                rec = r.recorder("security")
                r.log("security: headers and cookies at the front door, Python dependencies")
                security.front_door(rec)
                security.python_dependencies(rec)
                keep_open = True
    except Stopped as exc:
        stopped = str(exc)
    except Exception as exc:  # noqa: BLE001 - the run itself broke: kept as an error with the reason
        error = f"{exc}"
        print(f"ERROR: {exc}", flush=True)
        with open(r.dir / "run.log", "a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    _close_access(engine, run_id, by)
    if keep_open and not (error or stopped):
        with engine.begin() as conn:
            store.set_state(conn, run_id, step="waiting for the ZAP baseline scan and the Trivy image scans")
        return 0                  # the operations helper runs ZAP and Trivy, then `collect` closes the run
    return _close(engine, r, error, stopped)


def _close_access(engine, run_id: int, by: str) -> None:
    """When its checks end the run's tokens are revoked and its browser ticket forgotten: the accounts and models stay
    (fixtures, until someone purges them), but nobody can sign in with them any more."""
    from .. import machine_access as ma
    from .. import permissions as perms
    with engine.begin() as conn:
        for (guid,) in conn.execute(text("SELECT ident FROM core.test_fixtures WHERE run_id = :r AND kind = 'credential' "
                                         "AND purged_at IS NULL"), {"r": run_id}).all():
            try:
                ma.revoke(conn, by, [perms.SUPER_ADMIN], guid, "the self-test run ended")
            except Exception:  # noqa: BLE001
                pass
        conn.execute(text("UPDATE core.test_runs SET browser = jsonb_build_object('done', true) WHERE id = :id"), {"id": run_id})


def _close(engine, r: Run, error: str = "", stopped: str = "") -> int:
    with engine.begin() as conn:
        state = store.finish(conn, r.id, error, stopped)
    try:
        with engine.connect() as conn:
            (r.dir / "report.html").write_text(report.to_html(conn, r.id), encoding="utf-8")
            (r.dir / "report.xlsx").write_bytes(report.to_xlsx(conn, r.id))
    except Exception as exc:  # noqa: BLE001 - the results are in the database whatever happens to the files
        print(f"the report files could not be written: {exc}", flush=True)
    print(f"self-test {r.id} {state}: work/tests/{r.folder}/report.html", flush=True)
    return 0 if state == "passed" else 1


def cmd_collect(args) -> int:
    from ..db import get_engine
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT folder, state, started_by FROM core.test_runs WHERE id = :id"), {"id": args.run_id}).first()
    if not row:
        print(f"No self-test run {args.run_id}.")
        return 2
    if row[1] not in store.OPEN:
        print(f"Self-test run {args.run_id} is closed already ({row[1]}).")
        return 0 if row[1] == "passed" else 1
    r = Run.__new__(Run)
    r.engine, r.id, r.folder, r.dir = engine, args.run_id, row[0], RESULTS / row[0]
    r.dir.mkdir(parents=True, exist_ok=True)
    if not (args.error or args.stopped):
        rec = r.recorder("security")
        security.read_zap(r.dir / "zap.json", rec)
        security.read_trivy(r.dir, rec)
    _close_access(engine, args.run_id, row[2])
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
    a.add_argument("--run-id", type=int, default=0)
    a.add_argument("--trigger", default="eax", choices=["web", "eax", "ci"])
    a.add_argument("--by", default="")
    a.add_argument("--folder", default="")
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
