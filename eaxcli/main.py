"""The eax commands (phase 13.9, D331): help, the dispatch, starting again, the console."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import help as help_
from . import info, stack
from .core import (
    EAX,
    ENV_FILE,
    ENV_REL,
    ROOT,
    WINDOWS,
    WORK,
    Failure,
    assert_docker,
    attached,
    capture,
    compose,
    compose_args,
    diagnostics,
    docker_ok,
    kind,
    log_path,
    say,
    setting,
    start_log,
    stop_log,
    version,
)

DOCKER_COMMANDS = {"check", "up", "start-later", "debug", "status", "logs", "down", "backup", "backups", "restore", "restores", "databases", "footprint",
                   "restore-log", "delete-backup", "delete-restore", "app-backup", "restore-model", "restore-app",
                   "stop-backup", "services", "service", "import", "update", "rollback", "test", "standby"}
KEEP = ("tls",)                       # in work/data: the local certificate, kept by cleanup (D107)
KEEP_WORK = ("data", "tools")         # in work: data (its tls kept) and tools (uv and its Python, D331)


def _packs_auto() -> None:
    """Every full start copies what is new or changed in the pack sources first (owner, 11 Nov 2026, D584)."""
    try:
        from . import packs
        packs.auto()
    except Exception as exc:  # noqa: BLE001 - a start never fails because of the packs
        say(f"Industry packs: not copied ({exc}); the packs already in library/industry-packs are used.", "yellow")


def help_text(name: str = "") -> str:
    """The help from eaxcli/help.txt (the one source for every form, D331): the overview, one command, or --all."""
    return help_.render("py", EAX, WINDOWS, name)[0]


def show_help(name: str = "", arg: str = "") -> int:
    text, code = help_.render("py", EAX, WINDOWS, name, arg)
    print(text)
    return code


def document(options: list[str]) -> None:
    """eax document: every command in full, in the console (a menu, page by page) or as a web page (asks which)."""
    mode = "console" if "--console" in options else "web" if "--web" in options else ""
    if not mode:
        answer = input("Show the commands (1) here in the console or (2) as a web page in your browser? [1/2] ").strip()
        mode = "web" if answer in ("2", "w", "web") else "console"
    if mode == "web":
        import os
        import webbrowser
        out = WORK / "docs" / "eax-commands.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(help_.document_html("py", EAX, WINDOWS).encode("utf-8"))
        say(f"The commands as a web page: {out}")
        if not os.environ.get("EAX_NO_BROWSER"):
            webbrowser.open(out.resolve().as_uri())
        return
    while True:
        say("")
        say(f"EA Explorer commands ({EAX} document)", "cyan")
        print(help_.render("py", EAX, WINDOWS, "--groups")[0])
        try:
            answer = input("Number, s to search, q to quit: ").strip()
        except EOFError:
            return
        if answer in ("q", "Q"):
            return
        if answer in ("s", "S"):
            try:
                word = input("Search for: ").strip()
            except EOFError:
                return
            _paged(help_.render("py", EAX, WINDOWS, "--search", word)[0])
        elif answer.isdigit():
            _paged(help_.render("py", EAX, WINDOWS, "--group", answer)[0])
        elif answer:
            say("Choose a number, s or q.")


def _paged(text: str) -> None:
    rows = max(10, shutil.get_terminal_size((80, 24)).lines - 2)
    for i, line in enumerate(text.splitlines(), 1):
        print(line)
        if i % rows == 0 and sys.stdout.isatty():      # pages only on a terminal (piped or tested: all of it)
            try:
                if input("-- Enter for more, q to stop -- ").strip() == "q":
                    return
            except EOFError:
                return


# ---------------------------------------------------------------- starting again (no log: the logs folder goes)
def cleanup(options: list[str]) -> None:
    all_, yes, cert = "--all" in options, "--yes" in options or "-y" in options, "--certificate" in options
    unknown = [o for o in options if o not in ("--all", "--yes", "-y", "--certificate")]
    if unknown:
        raise Failure(f"Unknown option {unknown[0]}")
    say(f"This deletes everything in {WORK}: the config file, all logs, the laptop data folders, and every backup and "
        "restore log (work/backups).", "yellow")
    if all_:
        say("With --all it also deletes the Docker volumes: the databases and documents start empty.", "yellow")
    if not yes and input("Type yes to continue: ").strip() != "yes":
        say("Nothing deleted.")
        return
    try:                                   # the logs first, where no reset deletes them (R2.30)
        from . import logkeep
        base = logkeep.folder(WORK.parent)
        out = logkeep.backup(base, WORK / "logs", logkeep.kept_backups(base), "before-cleanup")
        say(f"Logs backed up first: {logkeep.kept_backups(base) / out['file']}")
    except Exception as exc:  # noqa: BLE001 - a log backup never stops the cleanup
        say(f"The logs could not be backed up first: {exc}", "yellow")
    if ENV_FILE.exists():
        attached(compose_args(["down", "-v", "--remove-orphans"] if all_ else ["down", "--remove-orphans"]))
    elif all_:
        say(f"No {ENV_REL}, so the Docker volumes cannot be found by name; list them with: docker volume ls")
    if WORK.exists():
        for p in WORK.iterdir():
            if p.name in KEEP_WORK and not (cert and p.name == "data"):
                if p.name == "data":
                    for q in p.iterdir():
                        if q.name not in KEEP:
                            _remove(q)
                continue
            _remove(p)
    for b in (WORK / "backups", WORK / "data" / "backups"):
        _remove(b)
    if not WINDOWS and ((WORK / "backups").exists() or (WORK / "data" / "backups").exists()) and docker_ok():
        # the backups are written by containers as root: removed by a container too (as eax.sh does)
        attached(["docker", "run", "--rm", "-v", f"{WORK}:/w", "--entrypoint", "sh",
                  setting("EAX_IMAGE_POSTGRES", "postgres:17-alpine"), "-c", "rm -rf /w/backups /w/data/backups"])
    if (WORK / "backups").exists():
        say("WARNING: work/backups could not be deleted completely (a file is in use?): delete it by hand.", "yellow")
    else:
        say("Every backup and restore log is deleted.")
    kept = "uv and its Python (work/tools)" + ("" if cert else " and the local certificate (work/data/tls)")
    say(f"The work folder is empty apart from {kept}. Run {EAX} init laptop to start again.")


def _remove(p: Path) -> None:
    try:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()
    except OSError:
        pass


def clean(command: str, rest: list[str], wait_all: bool) -> int:
    """clean-run, clean-debug, clean-restart: cleanup --all --yes, init, then up or debug, each a run of its own."""
    kind_ = rest[0] if rest else "laptop"
    last = ["debug" if command == "clean-debug" else "up", *(["--wait-all"] if wait_all else [])]
    steps = [["cleanup", "--all", "--yes"], ["init", kind_], last]
    if command == "clean-restart":
        if ENV_FILE.exists():
            steps.insert(0, ["down"])
        else:
            say(f"No {ENV_REL} yet: nothing running to bring down; going straight to clean-run.", "yellow")
    os.environ["EAX_BUILD_PULL"] = "1"         # the last step builds on fresh base images (R3.12, D673)
    for step in steps:
        say("")
        say(f"=== {EAX} {' '.join(step)}", "cyan")
        code = run_self(step)
        if code != 0:
            say(f"ERROR: {EAX} {' '.join(step)} failed (exit {code}); {command} stopped there.", "red")
            return code
    return 0


def restart(wait_all: bool) -> int:
    """restart: down, then up, each a run of its own (its own log). The data is kept."""
    for step in (["down"], ["up", *(["--wait-all"] if wait_all else [])]):
        say("")
        say(f"=== {EAX} {' '.join(step)}", "cyan")
        code = run_self(step)
        if code != 0:
            say(f"ERROR: {EAX} {' '.join(step)} failed (exit {code}); restart stopped there.", "red")
            return code
    return 0


def run_self(args: list[str]) -> int:
    """This program again, as its own run (its own log), like typing the command."""
    import subprocess
    return subprocess.run([sys.executable, str(ROOT / "eaxpy.py"), *args], cwd=ROOT, check=False).returncode


# ---------------------------------------------------------------- the console (phase 13.5, D330)
def console(options: list[str]) -> None:
    """A numbered menu for getting a system that is down back up. It runs in the operations helper; what needs this
    machine (start, stop, diagnostics, any eax command) it hands back here by its exit code. No sign-in on the machine.
    With --server: another installation, through its API."""
    if "--server" in options:
        assert_docker()
        attached(compose_args(["run", "--rm", "--no-deps", "api", "python", "-m", "eax.console_cli", "remote", *options]))
        return
    stopped = False                   # after Stop everything, nothing is started again until asked
    while True:
        ok = docker_ok()
        code = 99
        if ok and ENV_FILE.exists() and not stopped:
            # built first: an ops image from before the console has no console.py (seconds when nothing changed)
            print("Starting the console (the operations helper; the first time it is built, a minute)...", flush=True)
            if capture(compose_args(["up", "-d", "--build", "--no-deps", "ops"]))[0] == 0:
                code = attached(compose_args(["exec", "ops", "python3", "/app/console.py", "--version", version()]))
                if code not in (0, 20, 21, 23, 25):      # it failed: the basic menu, not the same failure again
                    say(f"The console stopped with an error (exit {code}); the basic menu follows. Its log: work/logs/console-*.log", "yellow")
                    code = 99
        if code == 99:                # the helper could not start: only what this machine can do
            say("")
            say(f"EA Explorer console (basic: {'everything is stopped' if stopped else 'the operations helper is not running'})", "cyan")
            if not ok:
                say("Docker is not running: start it, wait for 'Engine running', then choose 1.", "yellow")
            elif not ENV_FILE.exists():
                say(f"Not set up yet: there is no {ENV_REL}. Run {EAX} init laptop first.", "yellow")
            print("  1  Start everything\n  2  Save a diagnostics file for support\n  c  Command prompt (every eax command)\n  q  Quit")
            try:
                a = input("Choose: ").strip().lower()
            except EOFError:
                a = "q"
            code = {"1": 20, "2": 23, "c": 25, "q": 0}.get(a, 98)
        if code == 0:
            return
        if code == 20:
            stopped = False
            run_self(["up"])
        elif code == 21:
            run_self(["down"])
            stopped = True
        elif code == 23:
            run_self(["diag"])
        elif code == 25:
            print("Type an eax command (for example: logs api, services, backups). Empty or back: the menu.")
            while True:
                try:
                    line = input("eax> ").strip()
                except EOFError:
                    break
                if line in ("", "back", "b", "menu"):
                    break
                words = line.split()
                if words[0] == "console":
                    print("You are in the console already.")
                    continue
                run_self(words)


# ---------------------------------------------------------------- init, check, the dispatch
def init(rest: list[str]) -> None:
    kind_ = rest[0] if rest else "laptop"
    template = ROOT / "deploy" / "templates" / f"eaexplorer.{kind_}.env"
    if ENV_FILE.exists():
        raise Failure(f"{ENV_REL} already exists; not overwriting. Use {EAX} cleanup to start again.")
    if not template.exists():
        raise Failure(f"Unknown deployment kind: {kind_}")
    for d in ("logs", "backups", "proxy", "data/imports", "data/exports", "data/tls"):
        (WORK / d).mkdir(parents=True, exist_ok=True)
    # a plain copy, UTF-8 without BOM and LF endings (Docker Compose reads it cleanly); no passwords are generated
    text = template.read_text(encoding="utf-8")
    ENV_FILE.write_text("\n".join(text.splitlines()) + "\n", encoding="utf-8", newline="\n")
    say(f"Created {ENV_REL} ({kind_}) from deploy/templates/eaexplorer.{kind_}.env.")
    if kind_ == "laptop":
        info.show_logins()
    else:
        _ask_backup_folder()
        say(f"Now replace every change-me value in {ENV_REL} with your own passwords before {EAX} up.")


def _ask_backup_folder() -> None:
    """A server or platform keeps its backups in a mounted folder (R2.44, D635): asked here, kept as EAX_BACKUP_DIR;
    no backups are taken until it is set."""
    import sys
    if not sys.stdin.isatty():
        say(f"Set EAX_BACKUP_DIR in {ENV_REL} to the mounted folder for backups: no backups are taken until it is set.")
        return
    folder = input("Folder for backups: a mounted network share or volume (empty: set EAX_BACKUP_DIR later): ").strip()
    if not folder:
        say(f"No backups are taken until EAX_BACKUP_DIR is set in {ENV_REL}.")
        return
    text_ = ENV_FILE.read_text(encoding="utf-8").replace("\nEAX_BACKUP_DIR=\n", f"\nEAX_BACKUP_DIR={folder}\n", 1)
    ENV_FILE.write_text(text_, encoding="utf-8", newline="\n")
    say(f"Backups go to {folder} (EAX_BACKUP_DIR).")


def check() -> None:
    if attached(["docker", "version", "--format", "Docker {{.Server.Version}}"]) != 0:
        raise Failure("Docker is not running.")
    attached(["docker", "compose", "version"])
    if not ENV_FILE.exists():
        raise Failure(f"No {ENV_REL} yet: run {EAX} init")
    say(f"Config: {ENV_REL} ({kind()})")
    compose(["config", "--quiet"])
    say("Compose configuration is valid.")


def need_backups() -> None:
    if not stack.service_on("backups"):
        raise Failure(f"Backups are switched off: {EAX} service backups on")


def dispatch(command: str, rest: list[str], wait_all: bool) -> None:
    ops = ["ops", "python3", "/app/ops.py"]
    api = ["api", "python", "-m", "eax.backups_cli"]
    if command in DOCKER_COMMANDS:
        assert_docker()
    if command == "init":
        init(rest)
    elif command == "check":
        check()
    elif command == "up":
        if not rest:                               # the industry packs first (D584); never fatal
            _packs_auto()
        page = stack.upgrade_page(not rest)        # an upgrade (D230): the maintenance page while it rebuilds
        try:
            stack.up(rest, wait_all)
        finally:
            if page:
                _remove(WORK / "proxy" / "maintenance")
        if rest:
            info.show_part_urls(rest)
        else:
            info.show_urls()
            info.show_logins()
    elif command == "start-later":
        stack.later()
    elif command == "debug":
        if not rest:
            _packs_auto()
        code = stack.up(rest, wait_all, no_throw=True)
        if code != 0:
            say(f"docker compose up failed (exit {code}); recording what is running anyway.", "red")
        diagnostics()
        if rest:
            info.show_part_urls(rest)
        else:
            info.show_urls()
            info.show_logins()
        info.watch_containers(rest)
    elif command == "diag":
        diagnostics()
    elif command == "status":
        from . import core as _core
        _core.heading(f"EA Explorer {_core.release()}, build {_core.build_id()}")
        _core.say_status_lines(_core.compose_out(["ps", "-a"]))    # each container in its state's colour (R2.10)
        stack.show_filesystems()
    elif command == "logs" and rest[:1] in (["backup"], ["clean"]):   # back up and clean the logs (R2.30)
        from . import logs_cli
        return logs_cli.main(rest)
    elif command == "logs":
        attached(compose_args(["logs", "-f", "--tail=100", *rest]))
    elif command == "down":
        compose(["down"])
    elif command == "backup":
        need_backups()
        stack.backup_helpers()
        stack.interactive([*ops, "backup"], rest)
    elif command == "backups":
        stack.backup_helpers()
        stack.interactive([*ops, "list"], rest)
    elif command == "footprint":        # how much each container takes (R2.22): kept in work/footprint
        stack.interactive([*ops, "footprint"], rest)
    elif command == "stop-backup":
        stack.backup_helpers()
        stack.interactive([*ops, "stop-backup"], [])
    elif command == "restore-app":
        stack.interactive([*api, "restore-all"], rest)
    elif command == "maintenance":
        stack.maintenance(rest[0] if rest else "")
    elif command == "restore":
        need_backups()
        stack.backup_helpers()
        stack.interactive([*ops, "restore"], [*rest, "--version", version()])
    elif command == "restores":
        stack.backup_helpers()
        stack.interactive([*ops, "restores"], [])
    elif command == "databases":       # where each database lives and whether it answers (R2.50)
        stack.interactive(["api", "python", "-m", "eax.databases"], rest)
    elif command in ("restore-log", "delete-backup", "delete-restore"):
        stack.backup_helpers()
        stack.interactive([*ops, command], rest)
    elif command == "app-backup":
        stack.interactive([*api, "backup"], rest)
    elif command == "import":           # deliveries dropped in the import folder (phase 34, D466)
        stack.interactive(["api", "python", "-m", "eax.deliveries_cli"], rest)
    elif command in ("update", "rollback"):   # updating to a new release from git (phase 36, D417)
        stack.backup_helpers()
        stack.interactive([*ops, command], rest)
    elif command == "restore-model":
        stack.interactive([*api, "restore"], rest)
    elif command == "test" and "--build" in rest:   # only build the test runner image (D570; the Self-test page's button)
        say("Building the test runner (about 1.5 GB, 5 to 15 minutes the first time): base image, Python packages, "
            "Chromium, scanners.")
        compose(["--profile", "test", "build", "testrunner"])
        say("The test runner is built.")
    elif command == "test" and rest[:1] == ["clean"]:   # delete every test run's data, for good (R2.0.1, D593)
        stack.interactive(["api", "python", "-m", "eax.testing.cli", "clean", "all"], rest[1:])
    elif command == "test" and rest[:1] == ["delete"]:  # delete test results for good (R2.43)
        stack.interactive(["api", "python", "-m", "eax.testing.cli", "delete"], rest[1:])
    elif command == "test" and rest[:1] == ["api"]:     # the API test harness: one call (R3.16)
        stack.interactive(["api", "python", "-m", "eax.testing.cli", "api"], rest[1:])
    elif command == "test" and rest[:1] in (["watch"], ["stop"]):   # follow a run live, or stop it (R3.2)
        stack.interactive(["api", "python", "-m", "eax.testing.cli", rest[0]], rest[1:])
    elif command == "test":             # the self-test (phase 36.1, D367, D529): results read in the api container, a
        read = [a for a in rest if a in ("--status", "--last", "--report", "--fixtures", "--clean")]   # run through ops
        if read:
            stack.interactive(["api", "python", "-m", "eax.testing.cli", read[0].removeprefix("--")],
                              [a for a in rest if a != read[0]])
        else:
            # always prepare the runner first (D584): seconds when it is current, rebuilt when the code or version changed
            say("Preparing the test runner... (the first time about 5 to 15 minutes; seconds when it is current)")
            compose(["--profile", "test", "build", "testrunner"])
            stack.backup_helpers()
            stack.interactive([*ops, "test"], [*rest, "--version", version()])
    elif command == "standby":          # the database standby (phase 36.3, D527; EAX_COMPOSE_EXTRA=standby)
        what = rest[0] if rest else "status"
        if what == "status":
            stack.interactive(["db", "psql", "-U", "postgres", "-c"],
                              ["SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication"])
            stack.interactive(["db-standby", "psql", "-U", "postgres", "-c"],
                              ["SELECT pg_is_in_recovery() AS following_the_primary, now() - pg_last_xact_replay_timestamp() AS behind_by"])
        elif what == "promote":
            say("The standby becomes the primary: it stops following and accepts changes. Then set EAX_DB_HOST=db-standby "
                f"(or the standby's host) and run {EAX} up.")
            if input("Type PROMOTE to go on: ").strip() != "PROMOTE":
                say("Nothing changed.")
                return
            stack.interactive(["-u", "postgres", "db-standby", "pg_ctl", "promote", "-D"], ["/var/lib/postgresql/data"])
        else:
            raise Failure(f"Usage: {EAX} standby status|promote")
    elif command == "services":
        stack.show_services()
    elif command == "servers":
        stack.servers(rest)
    elif command == "service":
        if len(rest) < 2:
            raise Failure(f"Usage: {EAX} service <name> on|off   (names: {', '.join(stack.SERVICES)})")
        stack.set_service(rest[0], rest[1].lower())
    elif command == "url":
        info.show_urls()
        info.show_logins()
    elif command == "logins":
        if not ENV_FILE.exists():
            raise Failure(f"No {ENV_REL} yet: run {EAX} init first.")
        info.show_logins()
    elif command == "trust":
        if not ENV_FILE.exists():
            raise Failure(f"No {ENV_REL} yet: run {EAX} init first.")
        info.trust(rest)
    else:
        raise Failure(help_.unknown(command, EAX))


def main(argv: list[str]) -> int:
    if "--no-color" in argv:                  # plain text, wherever it is typed (R2.10)
        from . import core as _core
        _core.no_colour()
        argv = [a for a in argv if a != "--no-color"]
    command = argv[0] if argv else ""
    if command == "screen" or (not command and sys.stdin.isatty()):   # the full screen (R3.1); the numbered menu without it
        from . import screen
        return screen.main(argv[1:])
    if command == "menu":                     # the numbered menu (R2.29), kept as it is (owner: "keep both kinds of menus")
        from . import menu
        return menu.main(argv[1:])
    command = command or "help"
    rest = [a for a in argv[1:] if a]
    if command in ("help", "-h", "--help", "/?"):
        return show_help(rest[0] if rest else "", rest[1] if len(rest) > 1 else "")
    if any(a in ("--help", "-h", "/?") for a in rest):
        return show_help(command)     # <command> --help: the help of that command
    if command == "run":
        command = "up"                # run: the everyday start, the same as up
    elif command == "stop":
        command = "down"              # stop: the same as down (the data is kept)
    wait_all = "--wait-all" in rest
    rest = [a for a in rest if a != "--wait-all"]
    try:
        if command in ("clean-run", "clean-debug", "clean-restart"):
            return clean(command, rest, wait_all)
        if command == "restart":
            return restart(wait_all)
        if command == "cleanup":
            cleanup(rest)
            return 0
        if command == "console":
            console(rest)
            return 0
        if command == "document":
            document(rest)
            return 0
        if command == "persist":                # what persist/ holds, and deleting it (R2.26): every form
            from . import persist_cli
            return persist_cli.main(rest)
        if command == "schedule":               # scheduled eax commands (D559): persist/schedules.json, every form
            from . import schedule_cli
            return schedule_cli.main(rest)
        if command == "test" and "--reset-survival" in rest:   # settings outlive a real reset (D561): runs here
            from . import reset_survival
            return reset_survival.main(ROOT, rest)
        if command == "packs":                  # the industry packs (phase 39, D546): one Python program for every form
            from . import packs
            return packs.main(rest)
        if command in ("deploy", "secrets"):    # phase 36 (D498, D504): one Python program for every form (D500)
            if command == "deploy":
                from . import deploy
                return deploy.main(rest)
            from . import secrets as vault
            return vault.main(rest)
    except (Failure, KeyboardInterrupt) as exc:
        say(f"ERROR: {exc}" if isinstance(exc, Failure) else "Stopped.", "red")
        return 1
    start_log(command, rest)
    if Path(ROOT / "eaexplorer.env").exists() and not ENV_FILE.exists():
        say(f"Found eaexplorer.env in the main folder: it is no longer used. The config now lives in {ENV_REL}.", "yellow")
        say(f"Delete the old file and run {EAX} init laptop (or copy your changes into {ENV_REL}).", "yellow")
    failed = False
    try:
        dispatch(command, rest, wait_all)
    except Failure as exc:
        failed = True
        say(f"ERROR: {exc}", "red")
    except KeyboardInterrupt:
        failed = True
        say("Stopped (Ctrl+C).", "yellow")
    finally:
        if log_path():
            print(f"Log: {log_path()}")
        stop_log()
    return 1 if failed else 0


