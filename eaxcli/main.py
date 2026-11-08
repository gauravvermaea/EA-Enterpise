"""The eax commands (phase 13.9, D331): help, the dispatch, starting again, the console."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

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

HELP = """EA Explorer helper. Usage: {eax} <command> [options]
(the launcher fetches uv into work/tools the first time and runs this Python program with it; phase 13.9, D331)

Getting started
  init [laptop|server]  Creates work/eaexplorer.env from the template for the deployment kind
                        (laptop if not given) and the work folders. Nothing is generated: on a
                        laptop every password is P^55w0rd1234&; on a server, replace every change-me
                        value before starting. Refuses to overwrite an existing config file.
  check                 Checks that Docker Desktop is running and that the config file and compose
                        files are valid. Starts nothing.
  run                   The everyday start, after the first clean-run: the same as up. Keeps the
                        databases, documents and settings from last time.
  up [service...] [--wait-all]
                        Starts in two tiers (D255): the core first (sign-in, the API, the screens; you can sign
                        in when it says ready), then Reports, Documents, draw.io and the sample data in the
                        background. --wait-all starts everything and waits until all of it is up (also on
                        run, debug and the clean-* commands).
                        Builds our images, pulls the others, and starts every container in the
                        background. Then prints the addresses and (laptop) the logins.
                        Name services to start only those and what they depend on, for example
                        "up api proxy" starts the API, PostgreSQL and nginx only (about 1 GB);
                        the API is then at https://localhost/api/docs (laptop also http://).

Finding problems
  debug [service...] [--wait-all]
                        Same as up, but does not stop on failure: it saves a diagnostics report and
                        then keeps recording the containers' output to
                        work/logs/containers-<date-time>.log until you press Ctrl+C.
                        The containers keep running after Ctrl+C. "debug api" starts and records
                        the API (and PostgreSQL) only.
  diag                  Saves a diagnostics report into this run's log: Docker versions, memory and
                        disk, image settings, every container's state, the last 300 log lines of
                        each container, and the compose configuration (passwords masked).
  status                Lists every container with its state and health, including stopped ones, then the file
                        systems: Docker's disk, the work and backups folders, and this computer's drive (size, used, free).
  logs [service]        Follows the logs of every container, or of one (for example: logs api).
                        Ctrl+C to stop.

Everyday use
  url                   Prints the addresses to open (and the logins on a laptop).
  trust [--remove]      Adds EA Explorer's local certificate (work/data/tls/ca.crt) to your Windows
                        trusted root certificates, so the browser stops warning about https://localhost.
                        Run it once after the first start: clean-run keeps the certificate. --remove
                        takes EA Explorer's certificates out again.
  logins                Prints every user name and password (laptop only).
  down                  Stops and removes the containers. Data in Docker volumes and in work/ is kept.
  backup [tag]          Takes an infrastructure backup now (every database, the document files, the
                        certificate, the config file, the release and image versions) into
                        work/backups/infrastructure, tagged (D216, D226).
  backups [words]       Lists every backup: infrastructure (numbered, to restore) and application;
                        with words, only those whose tag, name or maker has them (search by tag).
  restore [name|tag|latest] [--what full|app|app+data|db|files] [--yes]
                        Restores an infrastructure backup: by name, by tag (the newest with it) or
                        latest (the newest good one). Without one it lists them to choose
                        from, then asks what to restore and for RESTORE to confirm. full = everything;
                        app = the config file; app+data = the config file, the repository and
                        document databases and the document files; db = every database; files =
                        the document files and the certificate. A backup of the current state is
                        taken first; nothing live changes until all is restored cleanly; it can be
                        run again. Works when the console is down (starts db, backup and ops).
  restores              Lists every restore (infrastructure and model) with its status.
  restore-log <id>      Shows a restore's whole log (also in work/backups/restores/<id>).
  delete-backup <name>  Deletes an infrastructure backup (unpin it first if it is pinned).
  delete-restore <id>   Forgets a finished restore and its log.
  stop-backup           Stops the backups running (infrastructure: at once; application: after the
                        model it is on); the partial backup is deleted. A restore cannot be stopped.
  restore-app [run|tag|latest] [--yes]
                        Restores every model of an application backup, each over itself (each backed
                        up first); models no longer there are made again; newer models stay as they
                        are. Needs the api container running.
  maintenance on|off    Shows (or stops showing) the maintenance page to everyone, served by the
                        proxy. Restores and up (an upgrade) switch it on and off themselves.
  app-backup [tag]      Backs up every model now (an application backup), into work/backups/application.
  restore-model         Lists the application backups and the models in them to choose from, then
                        restores one as a new model or over itself (needs the api container running).
  services              Lists the optional services (reports, documents, drawio, mcp, change_log,
                        backups), whether each is on in the config file and its containers' state.
  servers [n]           How many API and job servers run (D249): without n, shows them; with n (1 to 16), writes
                        EAX_API_SERVERS (a dated copy of the config file first) and adds or removes servers now,
                        without a restart (nginx spreads API calls across them). Also on Administration > Containers.
  service <name> on|off Switches one optional service on or off: keeps a dated copy of the config file
                        in work/config-history, writes the switch, then starts or stops its containers.
                        Everything is on unless switched off (D191). Also in Administration > System
                        settings > Services.

Starting again
  cleanup [--all] [--yes] [--certificate]
                        Stops the containers and deletes everything in the work folder: the config
                        file, logs and laptop data folders (including backups). With --all it also
                        deletes the Docker volumes, so the databases and documents start empty.
                        The local certificate (work/data/tls) is kept, so you need not trust it
                        again; --certificate deletes it too. Asks you to type yes unless --yes is given.
  clean-run [laptop|server] [--wait-all]
                        Starts again from scratch in one step: cleanup --all --yes, then init
                        (laptop if not given), then up. Deletes the databases and everything in
                        the work folder without asking.
  clean-debug [laptop|server] [--wait-all]
                        The same, but ends with debug instead of up (keeps recording the
                        containers' output until Ctrl+C).
  clean-restart [laptop|server] [--wait-all]
                        For testing a new version: down (stops and removes the running containers),
                        then clean-run (cleanup --all --yes, init, up). Rebuilds our images and
                        starts with empty databases; the trusted certificate is kept.

When something is wrong
  console [--server https://host] [--insecure]
                        A numbered menu for getting EA Explorer back up, for anyone (D330): status, start,
                        restart, stop, problems and logs, back up, restore (guided), reset a password (a
                        person, Keycloak's administrator, break-glass, the database logins), users and roles,
                        settings and switches, background tasks, health and data quality, the maintenance
                        page, a diagnostics file, and a prompt for every eax command. On this machine nobody
                        signs in; anything that changes or replaces data asks you to type YES. With --server
                        it works on another installation through its API (sign in with Keycloak, your roles).
                        Every command and the console in detail: docs/command-line-and-console.md.

  help [command]        This text, or the part about one command.

Logs: every command except help and cleanup writes its full output to
work/logs/eax-<date-time>-<command>.log. When a Docker step fails, a diagnostics report is added to
that log automatically, so the log file is all you need to send when something goes wrong."""

DOCKER_COMMANDS = {"check", "up", "start-later", "debug", "status", "logs", "down", "backup", "backups", "restore", "restores",
                   "restore-log", "delete-backup", "delete-restore", "app-backup", "restore-model", "restore-app",
                   "stop-backup", "services", "service"}
KEEP = ("tls",)                       # in work/data: the local certificate, kept by cleanup (D107)
KEEP_WORK = ("data", "tools")         # in work: data (its tls kept) and tools (uv and its Python, D331)


def help_text() -> str:
    return HELP.format(eax=EAX)


def show_help(name: str = "") -> None:
    if not name:
        print(help_text())
        return
    show = False
    for line in help_text().splitlines():
        if line.startswith("  ") and not line.startswith(" " * 24) and line[2:3].isalpha():
            show = line.split()[0] == name
        elif not line.startswith(" " * 24):
            show = False
        if show:
            print(line)


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
    for step in steps:
        say("")
        say(f"=== {EAX} {' '.join(step)}", "cyan")
        code = run_self(step)
        if code != 0:
            say(f"ERROR: {EAX} {' '.join(step)} failed (exit {code}); {command} stopped there.", "red")
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
        say(f"Now replace every change-me value in {ENV_REL} with your own passwords before {EAX} up.")


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
        compose(["ps", "-a"])
        stack.show_filesystems()
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
    elif command in ("restore-log", "delete-backup", "delete-restore"):
        stack.backup_helpers()
        stack.interactive([*ops, command], rest)
    elif command == "app-backup":
        stack.interactive([*api, "backup"], rest)
    elif command == "restore-model":
        stack.interactive([*api, "restore"], rest)
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
        raise Failure(f"Unknown command '{command}'. Run {EAX} help")


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "help"
    if command == "run":
        command = "up"                # run: the everyday start, the same as up
    rest = [a for a in argv[1:] if a]
    wait_all = "--wait-all" in rest
    rest = [a for a in rest if a != "--wait-all"]
    if command in ("help", "-h", "--help", "/?"):
        show_help(rest[0] if rest else "")
        return 0
    try:
        if command in ("clean-run", "clean-debug", "clean-restart"):
            return clean(command, rest, wait_all)
        if command == "cleanup":
            cleanup(rest)
            return 0
        if command == "console":
            console(rest)
            return 0
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


