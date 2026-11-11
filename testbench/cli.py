"""`eax testbench` / `python -m testbench` (D579 to D582): the outside test bench's commands.

  run (the default)  everything the self-test runs, from this machine, with the same names and filters as `eax test`
  install            eax deploy with an answers file, wait for health, then the suites
  upgrade            install --from, note the state, eax update --to, check the state, then the suites
  load               k6: --users N --minutes M, against testbench/thresholds.json
  suites             the suites, checks and journeys the bench runs (the same lists as the self-test)
  data build|check|list   the test data (testbench/data)
  setup              what to install on this machine, and the command for each (nothing is installed by the bench)

Every command that touches an installation needs --target <address> --i-own-this (or EAX_TESTBENCH_I_OWN_THIS=<host>)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import LEVELS, SUITES, shared
from .results import Run
from .target import Client, GuardError, check_owned, clean, credentials, message, password_token

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2
REPORTS = shared.ROOT / "testbench" / "reports"            # one folder a run: report.html, report.json, junit.xml


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eax testbench", description="EA Explorer's test bench, run from outside the "
                                "installation (docs/testbench.md).")
    sub = p.add_subparsers(dest="command")

    def target_opts(sp, needs_target: bool = True):
        g = sp.add_argument_group("target and sign-in")
        g.add_argument("--target", required=needs_target, help="the installation's address, e.g. https://ea.example.org")
        g.add_argument("--i-own-this", action="store_true", help="say the installation is yours (required every time)")
        g.add_argument("--token", default=os.environ.get("EAX_TESTBENCH_TOKEN", ""),
                       help="a Super Admin's or IT Admin's machine-access token (or EAX_TESTBENCH_TOKEN)")
        g.add_argument("--user", default=os.environ.get("EAX_TESTBENCH_USER", ""), help="a Keycloak user instead of a token")
        g.add_argument("--password", default=os.environ.get("EAX_TESTBENCH_PASSWORD", ""))
        g.add_argument("--realm", default="eaexplorer")
        g.add_argument("--client", default="eax-odata", help="the Keycloak client allowing a password sign-in (D433)")
        g.add_argument("--credentials", help="a JSON file as testbench/data/credentials.template.json")
        g.add_argument("--insecure", action="store_true", help="do not check the certificate (a laptop's own)")
        g.add_argument("--out", help="the report's folder (default testbench/reports/<time>)")
        g.add_argument("--quiet", action="store_true")

    def suite_opts(sp):
        g = sp.add_argument_group("what to run (as eax test)")
        lv = g.add_mutually_exclusive_group()
        lv.add_argument("--smoke", action="store_true", help="(the default) the self-test's smoke")
        lv.add_argument("--detailed", action="store_true", help="the suites chosen (all if none)")
        g.add_argument("--suite", action="append", default=[], help="api, ui, db, security or all (again for more)")
        g.add_argument("--role", default="", help="one test role only")
        g.add_argument("--area", default="", help="one API area only")
        g.add_argument("--journey", action="append", default=[], help="one browser journey, by part of its name")
        g.add_argument("--pages-only", action="store_true", help="only the page sweep")
        g.add_argument("--browsers", default="chromium", help="chromium,firefox,webkit,msedge or all (default chromium)")
        g.add_argument("--db", default="", help="run the database checks on this database (a SQLAlchemy address) "
                       "instead of through the target's API")
        g.add_argument("--no-zap", action="store_true", help="leave out the OWASP ZAP scan")
        g.add_argument("--no-trivy", action="store_true", help="leave out the Trivy image scans")
        g.add_argument("--no-fixtures", action="store_true", help="only what needs no fixtures (refusals, front door)")
        g.add_argument("--publish", nargs="?", const="TARGET", default="",
                       help="every result into the self-test history: of the target, or of the address given")
        g.add_argument("--publish-token", default="", help="a token for --publish <another address>")

    r = sub.add_parser("run", help="the self-test's checks from outside (the default)")
    target_opts(r, needs_target=False)
    suite_opts(r)
    a = r.add_argument_group("as eax test")
    a.add_argument("--status", action="store_true", help="the target's self-test runs going on")
    a.add_argument("--last", action="store_true", help="the last test bench run here: its result and every failure")
    a.add_argument("--report", nargs="?", const="last", help="where a test bench report is")
    a.add_argument("--fixtures", nargs="?", const="", help="every self-test fixture still on the target")
    a.add_argument("--clean", help="purge the target's fixtures of a run, or all, FOR GOOD")
    a.add_argument("--yes", action="store_true")
    a.add_argument("--reset-survival", action="store_true", help="the platform's reset-survival test (deletes all data)")
    a.add_argument("--confirm", default="", help="the installation's name, for --reset-survival")
    a.add_argument("--token-after", default="", help="a token made after the reset, to read its result")

    i = sub.add_parser("install", help="eax deploy with an answers file, then the suites")
    target_opts(i)
    suite_opts(i)
    i.add_argument("--answers", required=True, help="the deploy wizard's answers (eax deploy --answers)")
    i.add_argument("--folder", default="", help="the installation folder (default this checkout)")
    i.add_argument("--ref", default="", help="a tag or version to install into --folder (fetched from --url)")
    i.add_argument("--url", default=os.environ.get("EAX_UPDATE_GIT_URL", ""), help="the git repository")

    u = sub.add_parser("upgrade", help="install --from, eax update --to, check nothing was lost")
    target_opts(u)
    suite_opts(u)
    u.add_argument("--from", dest="from_ref", required=True, help="the tag or version to start from")
    u.add_argument("--to", required=True, help="the tag or version to move to, or a code folder")
    u.add_argument("--answers", required=True)
    u.add_argument("--folder", default="", help="a new folder for the --from installation")
    u.add_argument("--url", default=os.environ.get("EAX_UPDATE_GIT_URL", ""))

    lo = sub.add_parser("load", help="the load test with k6")
    target_opts(lo)
    lo.add_argument("--users", type=int, default=200)
    lo.add_argument("--minutes", type=float, default=10)

    sub.add_parser("suites", help="the suites, checks and journeys the bench runs")
    d = sub.add_parser("data", help="the test data: build, check or list")
    d.add_argument("action", nargs="?", default="list", choices=("build", "check", "list"))
    s = sub.add_parser("setup", help="what this machine needs, and how to get it")
    s.add_argument("--browsers", default="chromium")
    return p


def level_and_suites(args, store) -> tuple[str, list[str]]:
    """As eax test: --suite, --journey or --pages-only mean detailed; detailed with no suite means all four."""
    asked = [x for s in args.suite for x in s.split(",") if x.strip()]
    if args.journey or args.pages_only:
        asked = asked or ["ui"]
    level = "detailed" if (args.detailed or asked) else "smoke"
    suites = store.clean_suites(asked or None) if level == "detailed" else list(SUITES)
    return level, suites


def sign_in(args, target: str) -> str:
    c = credentials(args.credentials) if args.credentials else {}
    token = args.token or c.get("token", "")
    user, password = args.user or c.get("user", ""), args.password or c.get("password", "")
    if not token and user:
        token = password_token(target, user, password, c.get("realm") or args.realm, c.get("client") or args.client)
    if c.get("token_after_reset") and not getattr(args, "token_after", ""):
        args.token_after = c["token_after_reset"]
    return token


def folder_for(args) -> Path:
    if args.out:
        return Path(args.out)
    return REPORTS / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def finish(run: Run, extra: dict | None = None) -> int:
    from . import report  # noqa: PLC0415
    out = report.write(run, extra)
    t = run.tally()
    print(f"\nTest bench {'FAILED' if run.failed else 'passed'}: {t['passed']} passed, {t['failed']} failed, "
          f"{t['warning']} warnings, {t['skipped']} skipped.")
    for row in run.coverage():
        print(f"  {row[0]}: {row[1]}")
    print(f"Report: {out['html']}  (also {out['json'].name} and {out['junit'].name})")
    return EXIT_FAILED if run.failed else EXIT_OK


def latest_report(base: Path | None = None) -> Path | None:
    base = base or REPORTS
    reports = sorted(base.glob("*/report.json")) if base.is_dir() else []
    return reports[-1] if reports else None


def cmd_suites() -> int:
    from . import suites  # noqa: PLC0415
    flows, matrix = shared.module("ui_flows"), shared.module("api_matrix")
    store = shared.module("store")
    print("Levels: " + ", ".join(LEVELS) + "    Suites: " + ", ".join(SUITES) + " (the self-test's: "
          + ", ".join(store.SUITES) + ")")
    print("Roles: " + ", ".join(store.TEST_ROLES))
    print("The self-test calls the bench makes: " + ", ".join(sorted(suites.COVERED)))
    print(f"Browser journeys ({len(flows.JOURNEYS)}):")
    for j in flows.JOURNEYS:
        print(f"  {j['name']}  (roles: {', '.join(j['roles'])})")
    print(f"API matrix: every endpoint in the target's API description; heavy ones held back: {matrix.HEAVY.pattern}")
    return EXIT_OK


def cmd_setup(args) -> int:
    from .ui import clean_browsers  # noqa: PLC0415
    names = clean_browsers(args.browsers)
    have = []
    for mod in ("playwright", "sqlalchemy", "openpyxl", "pip_audit"):
        try:
            __import__(mod)
            have.append(f"{mod}: here")
        except ImportError:
            have.append(f"{mod}: MISSING")
    import shutil  # noqa: PLC0415
    print("The test bench needs (it installs nothing itself):")
    print("  Python packages: pip install -r testbench/requirements.txt   (" + "; ".join(have) + ")")
    print("  Browsers:        python -m playwright install " + " ".join(n for n in names if n != "msedge")
          + ("   and Microsoft Edge itself for msedge (python -m playwright install msedge)" if "msedge" in names else ""))
    print(f"  k6 (load test):  {'here' if shutil.which('k6') else 'MISSING: https://grafana.com/docs/k6/latest/set-up/install-k6/'}")
    print(f"  Docker (ZAP):    {'here' if shutil.which('docker') else 'missing: the ZAP scan is skipped'}")
    print(f"  Trivy:           {'here' if shutil.which('trivy') else 'missing: the image scans are skipped (https://trivy.dev)'}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["run", *argv]
    args = parser().parse_args(argv)
    if args.command == "suites":
        return cmd_suites()
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "data":
        from .data import manifest  # noqa: PLC0415
        from .data.build import build, check  # noqa: PLC0415
        if args.action == "build":
            print("Written: " + (", ".join(build()) or "nothing (as built)"))
            return EXIT_OK
        if args.action == "check":
            bad = check()
            print("Every file is as built." if not bad else "Not as built: " + ", ".join(bad))
            return EXIT_FAILED if bad else EXIT_OK
        for name, f in manifest()["files"].items():
            print(f"{name:<32}{f['what']}")
        return EXIT_OK
    if args.command == "run" and (args.last or args.report) and not args.target:
        rep = latest_report() if args.report in (None, "last") else Path(args.report) / "report.json"
        if not rep or not rep.exists():
            print("No test bench report here yet (testbench/reports/).")
            return EXIT_FAILED
        data = json.loads(rep.read_text(encoding="utf-8"))
        print(f"{rep.parent / 'report.html'}: {data['result']} ({data['totals']}) against {data['target']}")
        if args.last:
            for r in data["results"]:
                if r["outcome"] == "failed":
                    print(f"  FAILED {r['suite']}: {r['name']}: {r['detail'][:300]}")
        return EXIT_FAILED if data["result"] == "failed" else EXIT_OK
    try:
        if not args.target:
            raise GuardError("Give --target https://<host> (the EA Explorer address you sign in on) and --i-own-this.")
        target = clean(args.target)
        check_owned(target, args.i_own_this)
        if args.insecure:
            shared.insecure()
        token = sign_in(args, target)
    except (GuardError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return EXIT_USAGE
    client = Client(target, token)
    store = shared.module("store")
    if args.command == "run":
        if args.status or args.fixtures is not None or args.clean:
            return cmd_platform(args, client)
        if args.reset_survival:
            return cmd_reset(args, client, target)
    if args.command == "load":
        return cmd_load(args, client, target)
    try:
        level, suites_ = level_and_suites(args, store)
        role, area = store.clean_options(level, args.role, args.area)[1:]
        journeys = store.clean_journeys(args.journey)
        from .ui import clean_browsers  # noqa: PLC0415
        browsers = clean_browsers(args.browsers)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return EXIT_USAGE
    run = Run(target, folder_for(args), level=level, suites=suites_, quiet=args.quiet)
    notes: list[str] = []
    if args.command in ("install", "upgrade"):
        from . import lifecycle  # noqa: PLC0415
        folder = Path(args.folder or ("." if args.command == "install" else f"testbench-install-{args.from_ref}")).resolve()
        if args.command == "install":
            if args.ref:
                lifecycle.export(args.ref, folder, args.url)
            ok = lifecycle.install(run, folder, Path(args.answers), target)
        else:
            def login() -> Client:
                return Client(target, sign_in(args, target))
            ok = lifecycle.upgrade(run, args.from_ref, args.to, folder, Path(args.answers), target, login, url=args.url)
            client = login() if ok else client
        if not ok:
            return finish(run, {"notes": [f"the {args.command} failed: the suites were not run"]})
    from . import suites  # noqa: PLC0415
    publish_to = None
    if args.publish:
        to = target if args.publish == "TARGET" else clean(args.publish)
        publish_to = Client(to, args.publish_token or client.token)
    run.log(f"test bench: {level} against {target}" + ("" if level == "smoke" else f", {', '.join(suites_)}")
            + f", browsers {', '.join(browsers)}")
    sess = suites.run_all(run, client, target, level, suites_, role=role, area=area, journeys=journeys,
                          pages_only=args.pages_only, browsers=browsers, db_dsn=args.db,
                          publish_all=bool(args.publish), zap=not args.no_zap, trivy=not args.no_trivy,
                          fixtures=not args.no_fixtures, publish_to=publish_to)
    if sess.why:
        notes.append(sess.why)
    if sess.run_id:
        notes.append(f"fixtures: the target's self-test run {sess.run_id} (self_test_{sess.ids.get('sid', '?')}_n); "
                     f"they stay until removed: eax testbench --target {target} --i-own-this --clean {sess.run_id}")
    return finish(run, {"notes": notes})


def cmd_platform(args, client: Client) -> int:
    from . import suites  # noqa: PLC0415
    if args.status:
        s, a = client.get("/api/v1/admin/tests")
        if s != 200:
            print(f"ERROR: {s} {message(a)}")
            return EXIT_FAILED
        for r in (a.get("runs") if isinstance(a, dict) else a) or []:
            print(f"  {r.get('id')}: {r.get('state')} {r.get('level')} by {r.get('started_by')} {r.get('step') or ''}")
        return EXIT_OK
    if args.clean:
        if not args.yes and input(f"Purge the fixtures of {args.clean} on {client.target} FOR GOOD? Type DELETE: ") != "DELETE":
            print("Nothing purged.")
            return EXIT_FAILED
        s, a = suites.clean(client, args.clean)
        print(f"{'Purged' if s == 200 else 'ERROR'}: {json.dumps(a)[:500] if isinstance(a, dict) else a}")
        return EXIT_OK if s == 200 else EXIT_FAILED
    s, a = suites.fixtures_list(client, args.fixtures or "")
    if s != 200:
        print(f"ERROR: {s} {message(a)}")
        return EXIT_FAILED
    items = (a.get("fixtures") if isinstance(a, dict) else a) or []
    print(f"{len(items)} self-test fixture(s) on {client.target}:")
    for f in items:
        print(f"  run {f.get('run_id')}: {f.get('kind')} {f.get('name')}")
    return EXIT_OK


def cmd_reset(args, client: Client, target: str) -> int:
    from . import reset  # noqa: PLC0415
    s, a = client.get("/api/v1/admin/commands")
    name = a.get("installation", "") if isinstance(a, dict) else ""
    if s != 200 or not name:
        print(f"ERROR: could not read the installation's name ({s}: {message(a)}); a Super Admin's token is needed.")
        return EXIT_FAILED
    if args.confirm != name:
        print(f"This runs a REAL clean-restart on {target}: it DELETES every database and the work folder there. "
              f"Add --confirm {name}")
        return EXIT_USAGE
    run = Run(target, folder_for(args), level="reset-survival", suites=["reset-survival"], quiet=args.quiet)
    reset.run(run, client, name, args.confirm, token_after=args.token_after)
    return finish(run)


def cmd_load(args, client: Client, target: str) -> int:
    from . import load, suites  # noqa: PLC0415
    run = Run(target, folder_for(args), level="load", suites=["load"], quiet=args.quiet)
    sess = suites.start_session(client, "", run) if client.token else suites.Session(why="no token")
    tokens = list(sess.tokens.values()) if sess.ok else ([client.token] if client.token else [])
    if not tokens:
        print("ERROR: the load test signs in: give --token (or a user).")
        return EXIT_USAGE
    try:
        load.run(run, target, tokens, sess.ids.get("model", ""), args.users, args.minutes, insecure=args.insecure)
    finally:
        suites.publish(client, sess, run, False)
    return finish(run)
