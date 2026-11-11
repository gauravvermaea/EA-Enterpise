"""Starting and stopping: the optional services (D191), the two-tier start (D255), the API servers (D249), disks."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from .core import (
    EAX,
    ROOT,
    WINDOWS,
    WORK,
    Failure,
    capture,
    compose,
    compose_args,
    compose_out,
    copy_config,
    say,
    setting,
    write_setting,
)

# name: setting, compose services in start order (mcp and change_log run inside the api container)
SERVICES = {
    "reports": ("EAX_SERVICE_REPORTS", ["reports-init", "reports"]),
    "documents": ("EAX_SERVICE_DOCUMENTS", ["dms-broker", "dms"]),
    "drawio": ("EAX_SERVICE_DRAWIO", ["drawio"]),
    "mcp": ("EAX_SERVICE_MCP", ["api"]),
    "change_log": ("EAX_SERVICE_CHANGE_LOG", ["api"]),
    "backups": ("EAX_SERVICE_BACKUPS", ["backup"]),
    "library": ("EAX_SERVICE_LIBRARY", ["library"]),
    "views": ("EAX_SERVICE_VIEWS", ["views"]),
}
CORE = ["db", "setup", "proxy", "web", "keycloak", "api"]
STARTUP_PY = ("import json,urllib.request as u; d=json.load(u.urlopen('http://localhost:8000/api/startup',timeout=20)); "
              "print(d['overall']+'|'+', '.join(p['key']+': '+p['status'] for p in d['parts']))")


def service_on(name: str) -> bool:
    default = setting("EAX_MCP_ENABLED", "on") if name == "mcp" else "on"
    return setting(SERVICES[name][0], default).lower() not in ("off", "false", "0", "no", "disabled")


def write_services_file() -> None:
    """work/services.env: the switches only (no secrets), read by the api container."""
    lines = ["# Written by EA Explorer from eaexplorer.env: the service switches only (D191). Do not edit; change eaexplorer.env."]
    lines += [f"{SERVICES[n][0]}={'on' if service_on(n) else 'off'}" for n in SERVICES]
    (WORK / "services.env").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def off_containers() -> list[str]:
    return [c for n, (_s, cs) in SERVICES.items() if not service_on(n) and cs[0] != "api" for c in cs]


def api_servers() -> int:
    try:
        n = int(setting("EAX_API_SERVERS", "1"))
    except ValueError:
        n = 1
    return max(1, min(16, n))


def tiers() -> dict[str, list[str]]:
    off = off_containers()
    on = [s for s in compose_out(["config", "--services"]) if s not in off]
    return {"first": [s for s in on if s in CORE], "later": [s for s in on if s not in CORE], "off": off}


def wait_core(minutes: int = 15) -> bool:
    """Until the API (every copy) and Keycloak say healthy; each change shown; False when one stopped or too long."""
    until, last = time.time() + minutes * 60, ""
    while time.time() < until:
        rows = [r for r in compose_out(["ps", "-a", "--format", "{{.Name}}|{{.State}}|{{.Health}}", "api", "keycloak"]) if "|" in r]
        parts = [r.split("|") for r in rows]
        now = ", ".join(f"{p[0]}: {p[2] or p[1]}" for p in parts)
        if now and now != last:
            say(f"  {now}")
            last = now
        if len(parts) >= 2 and all(p[2] == "healthy" for p in parts):
            return True
        if any(p[1] in ("exited", "dead") for p in parts):
            say(f"A core container stopped; see {EAX} logs api (or keycloak).", "red")
            return False
        time.sleep(5)
    say(f"The API or sign-in was not ready after {minutes} minutes; see {EAX} logs api (or keycloak).", "yellow")
    return False


def wait_all(minutes: int = 30) -> None:
    """--wait-all: until every part is up (the API's start-up status, D255): Reports, Documents, Diagrams, sample data."""
    until, t0, last = time.time() + minutes * 60, time.time(), ""
    say(f"Waiting for everything: Reports, Documents, Diagrams and the sample data (up to {minutes} minutes)...")
    while time.time() < until:
        rows = [r for r in compose_out(["exec", "-T", "api", "python", "-c", STARTUP_PY]) if "|" in r]
        now = rows[-1] if rows else ""
        if now and now != last:
            say(f"  {now.split('|', 1)[1]}")
            last = now
        if now.startswith("up|"):
            say(f"Everything is up after {int(time.time() - t0)} s.", "green")
            return
        if now.startswith("down|") and "starting" not in now:
            say(f"Started, but not everything is up (see above): {EAX} logs <service>.", "yellow")
            return
        time.sleep(10)
    say(f"Not everything was up after {minutes} minutes (see above); EA Explorer is usable, the rest may still come.", "yellow")


def start_later() -> None:
    """The second tier in a process of its own, with its own log, so this window is free at once."""
    args = [sys.executable, str(ROOT / "eaxpy.py"), "start-later"]
    kw: dict = {"cwd": ROOT, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if WINDOWS:
        kw["creationflags"] = 0x00000008 | 0x08000000      # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    say("Reports, documents, draw.io, backups and the operations helper start now in the background "
        "(log: work/logs/eax-*-start-later.log).")


def up(names: list[str], wait_everything: bool, no_throw: bool = False) -> int:
    write_services_file()
    scale = ["--scale", f"api={api_servers()}"]
    if names:
        return compose(["up", "-d", "--build", *(scale if "api" in names else []), *names], no_throw=no_throw)
    t = tiers()
    if t["off"]:
        say(f"Switched off (D191): {', '.join(t['off'])}: created, not started.")
    say(f"Starting the core first (D255): {', '.join(t['first'])}", "cyan")
    code = compose(["up", "-d", "--build", *scale, *t["first"]], no_throw=no_throw)
    if code != 0:
        return code
    say("Waiting for the API and sign-in to be ready (the database upgrade and the built-in models come first)...")
    started = time.time()
    ready = wait_core()
    if wait_everything:
        later()
        wait_all()
        return 0
    start_later()
    say(f"(To wait for everything instead: {EAX} up --wait-all.)")
    if ready:
        say(f"EA Explorer is ready after {int(time.time() - started)} s: you can sign in.", "green")
        say("Still starting in the background: Reports, Documents, Diagrams and the sample data; the screens show each in "
            "red, amber or green (down, starting, up).", "green")
        hint = WORK / ".check-hint-shown"
        if not hint.exists():            # the first start: how to check it (D582)
            say("Check your installation: System admin > Self-test > Build the test runner, then Smoke test > Start;")
            say(f"  or {EAX} test --smoke; or from another machine {EAX} testbench --target https://<address> --i-own-this --smoke.")
            say("  Results: Self-test > History and the report. Steps: docs/deployment.md, \"Check your installation\".")
            try:
                hint.touch()
            except OSError:
                pass
    return 0


def later() -> None:
    """start-later: the rest without touching the core, then the switched-off ones created (not started)."""
    t = tiers()
    if t["later"]:
        say(f"Starting after the core (D255): {', '.join(t['later'])}")
        compose(["up", "-d", "--build", "--no-deps", *t["later"]], no_throw=True)
    if t["off"]:
        compose(["create", "--build", *t["off"]], no_throw=True)
        compose(["stop", *t["off"]], no_throw=True, quiet=True)
    say("Everything is started.")


def show_filesystems() -> None:
    """The disks after the containers: Docker's and the work and backups folders (read by the operations helper), and
    this computer's disk the project sits on (read here, so it shows with the helper down too)."""
    say("")
    if compose_out(["ps", "--status", "running", "-q", "ops"]):
        for ln in compose_out(["exec", "-T", "ops", "python3", "/app/ops.py", "filesystems"]):
            say(ln)
    else:
        say("File systems: the operations helper is not running, so Docker's disk is not read (docker system df below).", "yellow")
        for ln in capture(["docker", "system", "df"])[1].splitlines():
            say(f"  {ln}")
    try:
        u = shutil.disk_usage(ROOT)
        pct = round(u.used / u.total * 100, 1)
        colour = "red" if pct >= 90 else "yellow" if pct >= 80 else ""
        say(f"  This computer's disk for the project folder: {u.total / 1e9:,.1f} GB, {u.used / 1e9:,.1f} GB used, "
            f"{u.free / 1e9:,.1f} GB free ({pct}% used)", colour)
    except OSError:
        pass


def show_services() -> None:
    for n, (s, cs) in SERVICES.items():
        say(f"{n:<11} {'on ' if service_on(n) else 'off'}   {s} = {setting(s, 'on')}   containers: {', '.join(cs)}")
    compose(["ps", "-a"])


def set_service(name: str, value: str) -> None:
    if name not in SERVICES:
        raise Failure(f"Unknown service '{name}'. One of: {', '.join(SERVICES)}")
    if value not in ("on", "off"):
        raise Failure(f"Say on or off: {EAX} service {name} on")
    copy = copy_config(f"{name}-{value}")
    write_setting(SERVICES[name][0], value, drop="EAX_MCP_ENABLED" if name == "mcp" else "")
    write_services_file()
    say(f"{SERVICES[name][0]}={value} written (the config file before is kept as work/config-history/{copy}).")
    names = SERVICES[name][1]
    if names[0] == "api":
        compose(["restart", "api"])
    elif value == "on":
        compose(["up", "-d", *names])
    else:
        compose(["stop", *names])


def servers(args: list[str]) -> None:
    if not args:
        say(f"API and job servers wanted: {api_servers()} (EAX_API_SERVERS). Running:")
        compose(["ps", "api"])
        return
    try:
        n = int(args[0])
    except ValueError:
        n = 0
    if not 1 <= n <= 16:
        raise Failure(f"Usage: {EAX} servers <1 to 16>")
    copy_config(f"servers-{n}")
    write_setting("EAX_API_SERVERS", str(n), section="# ---- API and job servers (D249)")
    say(f"Running {n} API and job server(s); stopping a server lets the jobs it runs finish first.")
    compose(["up", "-d", "--no-deps", "--no-recreate", "--scale", f"api={n}", "api"])


def maintenance(arg: str) -> None:
    flag = WORK / "proxy" / "maintenance"
    if arg not in ("on", "off"):
        raise Failure(f"Usage: {EAX} maintenance on|off")
    if arg == "on":
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("maintenance\n", encoding="utf-8", newline="\n")
        say(f"The maintenance page is shown to everyone until: {EAX} maintenance off")
    else:
        if flag.exists():
            flag.unlink()
        say("The maintenance page is off.")


def upgrade_page(all_services: bool) -> bool:
    """While up rebuilds a running installation (D230) the proxy shows the maintenance page; True when switched on here."""
    flag = WORK / "proxy" / "maintenance"
    if not all_services or flag.exists() or not compose_out(["ps", "--status", "running", "-q", "proxy"]):
        return False
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("upgrade\n", encoding="utf-8", newline="\n")
    say("Everyone sees the maintenance page until this has finished.")
    return True


def backup_helpers() -> None:
    """Backups and restores talk to the operations helper and the backup container: started first (with the database)."""
    compose(["up", "-d", "db", "backup", "ops"], quiet=True)


def compose_attached(args: list[str]) -> int:
    from .core import attached
    return attached(compose_args(args))


def interactive(target: list[str], args: list[str]) -> None:
    """A command in a container with this console attached, so it can ask and show progress."""
    code = compose_attached(["exec", *target, *[a for a in args if a]])
    if code != 0:
        raise Failure(f"{target[0]} {' '.join(target[2:])} ended with exit {code}")
