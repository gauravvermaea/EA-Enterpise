"""`eax test --status | --last | --report | --fixtures | --clean` (phase 36.1, D367, D529): read from the one results store
in the api container (starting a run goes through the operations helper: services/ops/testruns.py).

  python -m eax.testing.cli status                  the run going on: its step and counts so far
  python -m eax.testing.cli last                    the last run: its result and every failure
  python -m eax.testing.cli report [run] [--xlsx]   where its report is (work/tests/<folder>/report.html, or .xlsx)
  python -m eax.testing.cli fixtures [run]          every self-test fixture still there, by run
  python -m eax.testing.cli clean <run|all> [--yes] [--dry-run]
                                                    purge them, for good (asks to type DELETE without --yes); --dry-run
                                                    lists what would go and deletes nothing (R2.11)
  python -m eax.testing.cli delete <run|all> [--older-than DAYS] [--yes]
                                                    delete test runs for good: their data, results, reports, logs and
                                                    videos (R2.43)
  python -m eax.testing.cli watch [run] [--log]    follow a run as it happens: the step, each check as it is recorded,
                                                    each failure with its reason (and the log with --log) (R3.2)
  python -m eax.testing.cli stop [run]             stop the run going on (or the one named), as the Self-test page's Stop
  python -m eax.testing.cli api <method> <path> [--as role] [--body JSON]
                                                    one call through the API test harness (R3.16), in a harness
                                                    session's own test data
Exit code 1 when the run asked about failed (for CI)."""

from __future__ import annotations

import sys

from sqlalchemy import text

from . import fixtures as fx
from . import store


def _engine():
    """The repository's engine (the fixtures; the runs are in the tests database, store.engine(), R2.28)."""
    from ..db import get_engine
    return get_engine()


def _line(r: dict) -> str:
    what = r["level"] + ("" if r["level"] == "smoke" else f" ({', '.join(r['suites'])})")
    extra = (f", role {r['role']}" if r["role"] else "") + (f", area {r['area']}" if r["area"] else "")
    return (f"Self-test {r['id']} ({store.short(r['run_guid'])}): {r['state'].upper()}  {what}{extra}  by {r['started_by']} "
            f"({r['trigger']})  passed {r['passed']}, failed {r['failed']}, skipped or warnings {r['skipped']}"
            + ("  [fixtures removed]" if r.get("purged_at") else f"  [{r['fixtures']} fixture(s)]")
            + (f"  repeats run {r['repeat_of']}" if r.get("repeat_of") else "")
            + (f"  followed up by run {r['followed_up_by']}" if r.get("followed_up_by") else
               (f"  (run its failed checks again: eax test failed {r['id']})" if r.get("failed") and r["state"] not in store.OPEN else "")))


def api_call(args: list[str], out=print) -> int:
    """`eax test api <method> <path> [--as role] [--body JSON]` (R3.16): one call in a harness session's test data (the
    newest of the last 20 hours, else a new one with every test role). Exit code 0 for a 2xx answer."""
    import json as _json

    from .. import api_harness as ah
    usage = "Usage: eax test api <GET|POST|PUT|PATCH|DELETE> </api/v1/...> [--as role] [--body '{...}']"
    plain = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--as", "--body"))]
    if len(plain) < 2 or plain[0].lower() not in ("get", "post", "put", "patch", "delete"):
        out(usage)
        return 2
    as_who = args[args.index("--as") + 1] if "--as" in args and args.index("--as") + 1 < len(args) else "super-admin"
    body = None
    if "--body" in args and args.index("--body") + 1 < len(args):
        try:
            body = _json.loads(args[args.index("--body") + 1])
        except ValueError as exc:
            out(f"--body is not JSON: {exc}")
            return 2
    sid = ah.latest_session()
    if not sid:
        out("Starting an API harness session: test accounts for every test role and its own test data (about a minute)...")
        sid = ah.session(_engine(), "eax test", list(store.TEST_ROLES), out)["session"]
    sess = ah.session_row(sid)
    if as_who not in sess["tokens"]:
        out(f"The session has no {as_who} account; it has: {', '.join(sorted(sess['tokens']))}.")
        return 2
    with _engine().begin() as conn:
        test_ids = ah.test_data_ids(conn)
    from ..metamodel_edit import EditError
    try:
        r = ah.call(plain[0], ah.fill(plain[1], sess["ids"]), sess["tokens"][as_who], body, {}, test_ids, as_who)
    except EditError as exc:
        out(f"Refused: {exc}")
        return 2
    out(f"{plain[0].upper()} {ah.fill(plain[1], sess['ids'])} as {as_who} (session {sid}): {r['status']} in {r['ms']} ms")
    out(_json.dumps(r["json"], indent=2)[:20000] if r["json"] is not None else r["body"][:20000])
    out(f"\nThe same call: {r['curl']}")
    return 0 if 200 <= r["status"] < 300 else 1


def pick_watch(runs: list[dict], args: list[str]) -> dict | None:
    """The run named, else the one running, else the last one."""
    named = next((a for a in args if a.isdigit()), None)
    if named:
        return next((r for r in runs if str(r["id"]) == named), None) or {"id": int(named)}
    return next((r for r in runs if r["state"] in store.OPEN), None) or (runs[0] if runs else None)


def watch(teng, runs: list[dict], args: list[str], out=print, every: float = 2.0) -> int:
    from . import live
    from .run import RESULTS
    pick = pick_watch(runs, args)
    if not pick:
        out("No self-test to watch: start one with eax test.")
        return 0
    out(f"Watching self-test {pick['id']} (Ctrl+C stops watching; the run goes on; eax test stop {pick['id']} stops the run)")
    reader = live.file_log_reader(_results_root(RESULTS))

    def get(after: int, log_at: int):
        with teng.connect() as conn:
            return live.snapshot(conn, int(pick["id"]), after, log_at, reader)
    try:
        state = live.follow(get, out=out, every=every, show_log="--log" in args)
    except KeyboardInterrupt:
        out("Stopped watching; the run goes on.")
        return 0
    return 0 if state in ("passed", "") else 1


def stop(eng, runs: list[dict], args: list[str], out=print) -> int:
    import getpass

    from .. import audit
    named = next((a for a in args if a.isdigit()), None)
    live_runs = [r for r in runs if r["state"] in store.OPEN]
    pick = next((r for r in runs if str(r["id"]) == named), None) if named else (live_runs[0] if live_runs else None)
    if not pick or pick["state"] not in store.OPEN:
        out("No self-test is running" + (f" as {named}" if named else "") + ": nothing to stop.")
        return 0
    by = f"{getpass.getuser()} (eax test stop)"
    with eng.begin() as conn, store.tests(conn) as tc:
        if not store.ask_stop(tc, int(pick["id"]), by):
            out(f"Self-test {pick['id']} is not running.")
            return 0
        audit.record(conn, actor=by, action="selftest.stopped", object_type="test_run", object_id=str(pick["id"]))
    out(f"Self-test {pick['id']} is asked to stop: it stops at its next step and removes its test data.")
    return 0


def _results_root(default):
    """Where the runs' folders are seen from here: /eax-work/tests in the api container, else the runner's own."""
    import os
    from pathlib import Path
    work = Path(os.environ.get("EAX_WORK_DIR", "/eax-work")) / "tests"
    return work if work.is_dir() else default


def main(argv: list[str]) -> int:
    cmd, args = (argv[0] if argv else "last"), argv[1:]
    if cmd == "api":                                  # the API test harness, one call (R3.16): no run list needed
        return api_call(args)
    eng, teng = _engine(), store.engine()
    try:                                              # runs no one is running any more are closed first (R2.64)
        with teng.begin() as conn:
            for rid in store.close_orphans(conn):
                print(f"Self-test {rid} is closed as stopped: its test runner was no longer running.")
    except Exception:  # noqa: BLE001, S110 - only tidying
        pass
    with teng.connect() as conn:
        runs = store.runs(conn, 50)
    if cmd == "watch":                                # follow a run live (R3.2): Ctrl+C stops watching, not the run
        return watch(teng, runs, args)
    if cmd == "stop":                                 # stop a run, as the watch window's Stop (R3.2)
        return stop(eng, runs, args)
    if cmd == "status":
        live = [r for r in runs if r["state"] in store.OPEN]
        if not live:
            print("No self-test is running." + (f" The last: {_line(runs[0])}" if runs else ""))
            return 0
        r = live[0]
        print(_line(r))
        print(f"  now: {r['step']}")
        return 0
    if cmd in ("last", "report"):
        pick = next((x for x in runs if args and str(x["id"]) == args[0]), None) if args and args[0].isdigit() else \
            next((x for x in runs if x["state"] not in store.OPEN), None)
        if not pick:
            print("No self-test has finished yet: run eax test.")
            return 0
        if cmd == "report":
            ext = "xlsx" if "--xlsx" in args else "html"
            print(f"The report of self-test {pick['id']}: work/tests/{pick['folder']}/report.{ext}")
            print(f"(also System admin > Self-test > run {pick['id']} > Download report)")
            return 0 if pick["state"] == "passed" else 1
        print(_line(pick))
        print(f"  {pick['message']}")
        with teng.connect() as conn:
            d = store.run_detail(conn, pick["id"], "failed")
        for x in d["results"][:200]:
            print(f"  FAILED  {x['suite']:<9}{x['name']}: {x['detail'][:300]}")
            if x["request"]:
                print(f"          asked: {x['request']}")
                print(f"          answer: {x['response'][:300]}")
        print(f"Report: work/tests/{pick['folder']}/report.html")
        return 0 if pick["state"] == "passed" else 1
    if cmd == "fixtures":
        with eng.connect() as conn:
            rows = store.fixtures(conn, int(args[0]) if args and args[0].isdigit() else None)
        if not rows:
            print("No self-test fixtures: nothing to clean.")
            return 0
        for f in rows:
            size = f" ({f['entities']} entities, {f['relationships']} relationships)" if f["kind"] == "model" else ""
            print(f"  run {f['run_id']:<5} {f['kind']:<16} {f['name']:<44} made {str(f['created_at'])[:16]}{size}")
        print(f"{len(rows)} fixture(s). Remove them with: eax test --clean <run|all>")
        return 0
    if cmd == "clean":
        if not args:
            print("Usage: eax test --clean <run|all> [--yes]")
            return 2
        with teng.connect() as conn:
            if args[0] == "all":
                ids = [r[0] for r in conn.execute(text("SELECT DISTINCT run_id FROM tests.test_fixtures WHERE purged_at IS NULL "
                                                        "ORDER BY run_id")).all()]
            elif args[0].isdigit():
                ids = [int(args[0])]
            else:
                print("Usage: eax test --clean <run|all> [--yes]")
                return 2
            n = conn.execute(text("SELECT count(*) FROM tests.test_fixtures WHERE purged_at IS NULL AND run_id = ANY(:r)"),
                             {"r": ids}).scalar()
        if not ids or not n:
            print("No self-test fixtures to remove for that.")
            return 0
        if "--dry-run" in args:                       # what would go, nothing deleted (R2.11)
            with eng.connect() as conn:
                print(fx.preview_text(fx.preview(conn, ids)))
            return 0
        print(f"This removes {n} self-test fixture(s) of run(s) {', '.join(map(str, ids))} FOR GOOD: the self_test models and "
              "everything in them, the projects, the test accounts and credentials. It cannot be undone. The runs' reports stay.")
        if "--yes" not in args and input("Type DELETE to go on: ").strip() != "DELETE":
            print("Nothing removed.")
            return 1
        for run in ids:
            with eng.begin() as conn:
                out = fx.purge(conn, run, "eax test --clean", progress=lambda _p, note: print(f"  {note}", flush=True))
            print(f"  run {run}: {out['models']} model(s), {out['projects']} project(s), {out['service_accounts']} account(s), "
                  f"{out['credentials']} credential(s), {out['history_versions']} history versions" +
                  (f"; {'; '.join(out['notes'])}" if out["notes"] else ""))
        return 0
    if cmd == "delete":                               # test results, for good (R2.43)
        return _delete(eng, args, teng)
    print(__doc__)
    return 2


def _delete(eng, args: list[str], teng=None) -> int:
    """eax test delete <run|all> [--older-than DAYS] [--yes]: each run's test data, results and screenshots, and its
    reports, logs and videos in work/tests, for good (R2.43)."""
    from . import cleanup
    usage = "Usage: eax test delete <run|all> [--older-than DAYS] [--yes]"
    days = None
    if "--older-than" in args:
        i = args.index("--older-than")
        if i + 1 >= len(args) or not args[i + 1].isdigit():
            print(usage)
            return 2
        days = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    which = next((a for a in args if not a.startswith("--")), "")
    try:
        with (teng or store.engine()).connect() as conn:
            runs = cleanup.pick(conn, which, days)
    except ValueError as exc:
        print(f"{exc}\n{usage}")
        return 2
    if not runs:
        print("No finished test runs to delete for that.")
        return 0
    print(f"This deletes {len(runs)} test run(s) ({', '.join(str(r['id']) for r in runs[:20])}{'...' if len(runs) > 20 else ''}) "
          "FOR GOOD: their test data, results and screenshots, and their reports, logs and videos in work/tests. "
          "It cannot be undone.")
    if "--yes" not in args and input("Type DELETE to go on: ").strip() != "DELETE":
        print("Nothing deleted.")
        return 1
    from ..api.admin import _ops_raw
    out = cleanup.delete(eng, [r["id"] for r in runs], "eax test delete",
                         lambda folders: _ops_raw("POST", "/tests/results/delete", {"folders": folders}, timeout=120),
                         say=lambda m: print(f"  {m}", flush=True))
    print(cleanup.message(out))
    return 0 if not out["left"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
