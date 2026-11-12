"""`eax test --status | --last | --report | --fixtures | --clean` (phase 36.1, D367, D529): read from the one results store
in the api container (starting a run goes through the operations helper: services/ops/testruns.py).

  python -m eax.testing.cli status                  the run going on: its step and counts so far
  python -m eax.testing.cli last                    the last run: its result and every failure
  python -m eax.testing.cli report [run] [--xlsx]   where its report is (work/tests/<folder>/report.html, or .xlsx)
  python -m eax.testing.cli fixtures [run]          every self-test fixture still there, by run
  python -m eax.testing.cli clean <run|all> [--yes] purge them, for good (asks to type DELETE without --yes)
  python -m eax.testing.cli delete <run|all> [--older-than DAYS] [--yes]
                                                    delete test runs for good: their data, results, reports, logs and
                                                    videos (R2.43)
Exit code 1 when the run asked about failed (for CI)."""

from __future__ import annotations

import sys

from sqlalchemy import text

from . import fixtures as fx
from . import store


def _engine():
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


def main(argv: list[str]) -> int:
    cmd, args = (argv[0] if argv else "last"), argv[1:]
    eng = _engine()
    with eng.connect() as conn:
        runs = store.runs(conn, 50)
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
        with eng.connect() as conn:
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
        with eng.connect() as conn:
            if args[0] == "all":
                ids = [r[0] for r in conn.execute(text("SELECT DISTINCT run_id FROM core.test_fixtures WHERE purged_at IS NULL "
                                                        "ORDER BY run_id")).all()]
            elif args[0].isdigit():
                ids = [int(args[0])]
            else:
                print("Usage: eax test --clean <run|all> [--yes]")
                return 2
            n = conn.execute(text("SELECT count(*) FROM core.test_fixtures WHERE purged_at IS NULL AND run_id = ANY(:r)"),
                             {"r": ids}).scalar()
        if not ids or not n:
            print("No self-test fixtures to remove for that.")
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
        return _delete(eng, args)
    print(__doc__)
    return 2


def _delete(eng, args: list[str]) -> int:
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
        with eng.connect() as conn:
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
