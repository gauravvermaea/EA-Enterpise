"""The Command centre and the Console (D554): eax commands from a web page, for IT and Super Admins.

The operations helper runs each command in a short-lived container of its own (its own image, the installation folder
and the Docker socket, like the updater of D417), outside Compose, so a command that stops or empties the stack still
finishes. Inside, eaxcli/cmdrun.py checks the command again and runs it through eaxpy, writing work/commands/<run>/
status.json and output.log; the page reads those. The Console is a terminal (the WebSocket of the container terminals,
D214) in which eaxcli/webconsole.py takes eax commands only.

  GET  /commands                 the catalogue (from eaxcli/help.txt) and the installation's name
  GET  /commands/runs            the history: runs and console sessions, newest first
  GET  /commands/runs/<id>?from= a run's record and its output from byte `from`
  POST /commands/run             {argv, by, roles, confirm: {typed, understood}}: start one (202)
  POST /commands/runs/<id>/stop  stop a run that may be stopped (logs, debug, status, test...)
  POST /commands/console         {by, roles, cols, rows}: a one-time ticket for the Console's WebSocket
  POST /commands/ack             {ids}: ended runs recorded in the audit trail
  GET  /commands/schedules       scheduled commands (D559; eaxcli/schedules.py, kept in persist/schedules.json)
  POST /commands/schedules       {name, argv | command+values, cron | preset, backup_first, keep, banner, confirm,
                                  demo: true for the one-click demo reset, by, roles}: a new schedule
  POST /commands/schedules/<id>/on|off|remove|run   {by, roles}
  GET  /persist                  what persist/ holds (R2.26)   POST /persist/delete {item | all, by}: delete it for good
  GET  /banner?admin=1           the banner a person sees now, or null (D558; eaxcli/banner.py, persist/banner.json)
  GET  /banner/all               the banner, its history and any warning (System admin > Banner)
  POST /banner                   {banner: {...}, by}: set it          POST /banner/clear {by}: clear it

Settings that survive resets (D558) live in persist/ (EAX_PERSIST_DIR, mounted at /eax-persist): the schedules and
the banner as JSON files written atomically, and the safety backups. The scheduler looks every 30 seconds.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

WORK = os.environ.get("EAX_WORK_MOUNT", "/eax-work")
REPO = os.environ.get("EAX_REPO_MOUNT", "/eax-repo")
RUNS = os.path.join(WORK, "commands")
sys.path.insert(0, REPO)
try:
    from eaxcli import banner as B
    from eaxcli import commands as C
    from eaxcli import schedules as S
except Exception:  # noqa: BLE001 - an older compose file without the eaxcli mount
    B = C = S = None

hooks: dict = {}       # set by ops.py: docker, me (the helper's project, image and installation folder), read_config,
                       # tickets, tlock, idle_minutes


def _need() -> None:
    if C is None:
        raise RuntimeError("The Command centre needs eaxcli mounted into the operations helper (docker-compose.yml).")


def _config_values() -> dict:
    out = {}
    for line in hooks["read_config"]():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def installation_name() -> str:
    v = _config_values()
    if v.get("EAX_INSTALLATION_NAME") or v.get("EAX_HOSTNAME"):
        return v.get("EAX_INSTALLATION_NAME") or v.get("EAX_HOSTNAME")
    try:
        return os.path.basename(hooks["me"]()["install"].rstrip("/")) or "eaexplorer"
    except Exception:  # noqa: BLE001
        return "eaexplorer"


def catalogue() -> dict:
    _need()
    return {**C.catalogue(), "installation": installation_name()}


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def history(limit: int = 200) -> list[dict]:
    out = []
    if os.path.isdir(RUNS):
        for d in os.listdir(RUNS):
            rec = _read(os.path.join(RUNS, d, "status.json"))
            if rec:
                if rec.get("state") == "running" and not d.startswith("console-") and not _container(d):
                    rec["state"] = "stopped"            # its container is gone without writing the end
                out.append(rec)
    out.sort(key=lambda r: r.get("started") or "", reverse=True)
    return out[:limit]


def _safe_id(run_id: str) -> str:
    if not re.match(r"^[A-Za-z0-9_-]{4,80}$", run_id or ""):
        raise FileNotFoundError("No such run.")
    return run_id


def last_words(run_id: str, lines: int = 15) -> str:
    """What a run's container said when it wrote no record (it stopped before eaxcli.cmdrun could start: the
    installation folder not mounted, no Python module, a Docker error): its last lines, else its state."""
    try:
        cid = hooks["docker"]("ps", "-aq", "--filter", f"label=eax.command.run={run_id}").strip().splitlines()
        if not cid:
            return "its container is gone"
        out = hooks["docker"]("logs", "--tail", str(lines), cid[0]).strip()
        state = hooks["docker"]("inspect", "--format", "{{.State.Status}} (exit {{.State.ExitCode}}) {{.State.Error}}", cid[0]).strip()
        return (" | ".join(x.strip() for x in out.splitlines() if x.strip())[-800:] or "no output") + f"; container {state}"
    except Exception as exc:  # noqa: BLE001
        return f"its container could not be read ({exc})"


def detail(run_id: str, start: int = 0) -> dict:
    folder = os.path.join(RUNS, _safe_id(run_id))
    rec = _read(os.path.join(folder, "status.json"))
    if not rec:
        if _container(run_id):                 # still starting: no record yet
            return {"status": {"state": "running", "id": run_id}, "text": "", "next": start, "commands": [], "running": True}
        # R2.49 (owner, 12 Nov 2026): the build for Run the failed ones again said only "No such run."
        raise FileNotFoundError(f"The command wrote no record: {last_words(run_id)}")
    text, nxt = "", start
    for name in ("output.log", "transcript.log"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                f.seek(max(0, start))
                data = f.read(400_000)
            text, nxt = data.decode("utf-8", "replace"), max(0, start) + len(data)
            break
    cmds = []
    p = os.path.join(folder, "commands.jsonl")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            cmds = [json.loads(x) for x in f if x.strip()]
    return {"status": rec, "text": text, "next": nxt, "commands": cmds, "running": bool(_container(run_id))}


def _container(run_id: str) -> str:
    try:
        me = hooks["me"]()
        out = hooks["docker"]("ps", "-q", "--filter", f"label=eax.command.run={run_id}",
                              "--filter", f"label=eax.command={me['project']}")
        return out.strip()
    except Exception:  # noqa: BLE001
        return ""


def _new_id(name: str) -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + re.sub(r"[^a-z0-9]", "", name)[:16] + "-" + secrets.token_hex(2)


def start(body: dict) -> dict:
    """Check the command, the person's right and (for the wipe commands) the strong confirm; then start it."""
    _need()
    by = str(body.get("by") or "?")
    roles = [str(r) for r in (body.get("roles") or [])]
    argv = body.get("argv")
    if not argv and body.get("name"):
        argv = C.build_argv(str(body["name"]), dict(body.get("values") or {}))
    if not isinstance(argv, list) or not argv:
        raise C.Refused("No command.")
    argv = C.check_argv([str(a) for a in argv])
    C.allowed_argv(argv, roles)
    kind = C.kind_of_argv(argv)
    if kind == "host":
        raise C.Refused(f"{argv[0]} runs on the machine itself: {C.HOST_WHY.get(argv[0], '')} Type there: eax {' '.join(argv)}")
    if kind == "interactive":
        raise C.Refused(f"eax {argv[0]} asks questions as it goes: run it in the Console tab.")
    if kind in ("offline", "wipe") and hooks["me"]().get("windows"):     # R2.49: compose in a container, Windows folders
        raise C.Refused(f"On Windows this runs from PowerShell in the installation folder, not from the web: .\\eax {' '.join(argv)}")
    conf = body.get("confirm") or {}
    C.check_confirm(argv, str(conf.get("typed") or ""), installation_name(), bool(conf.get("understood")))
    run_id = _launch(argv, by, _new_id(argv[0]))
    kind = C.kind_of_argv(argv)
    return {"id": run_id, "argv": argv, "kind": kind, "command": " ".join(["eax", *argv]),
            "goes_offline": kind in ("offline", "wipe") and not (argv[0] == "update" and "--status" in argv)}


def persist_host() -> str:
    """persist/ on the host: EAX_PERSIST_DIR from the config file (absolute, or relative to the installation), else
    <installation>/persist."""
    me = hooks["me"]()
    given = _config_values().get("EAX_PERSIST_DIR", "")
    if given and given.startswith("/"):
        return given
    return os.path.join(me["install"], given or "persist").replace("\\", "/")


def _persist_inside(me: dict, host: str) -> str:
    """persist/ as the short-lived container sees it: under the installation's inside path, or mounted on its own."""
    root = me["install"].rstrip("/")
    if host.startswith(root + "/"):
        return me.get("inside", root) + host[len(root):]
    return host if host.startswith("/") else "/eax-persist"


def _launch(argv: list[str], by: str, run_id: str, env: dict | None = None) -> str:
    """The short-lived runner container (outside Compose): eaxcli.cmdrun runs the command through eaxpy."""
    me = hooks["me"]()
    name = f"{me['project']}-cmd-{run_id}"[:63]
    me.setdefault("inside", me["install"])
    extra: list[str] = []
    host = persist_host()
    seen = _persist_inside(me, host)
    if not host.startswith(me["install"].rstrip("/") + "/"):
        extra += ["-v", f"{host}:{seen}"]
    for k, v in {"EAX_PERSIST_DIR": seen, **(env or {})}.items():
        extra += ["-e", f"{k}={v}"]
    hooks["docker"]("create", "--name", name, "--label", f"eax.command={me['project']}", "--label", f"eax.command.run={run_id}",
                    "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{me['install']}:{me['inside']}", *extra,
                    "-w", me["inside"], "-e", f"COMPOSE_PROJECT_NAME={me['project']}",
                    "--entrypoint", "python3", me["image"], "-m", "eaxcli.cmdrun", run_id, by, "--", *argv)
    hooks["docker"]("start", name)
    return run_id


# ---------------------------------------------------------------- scheduled commands (D559)
def _tz_env() -> None:
    tz = _config_values().get("EAX_TIMEZONE")
    if tz:
        os.environ["EAX_TIMEZONE"] = tz


def busy() -> bool:
    """Another command (not a console session) is running now."""
    try:
        me = hooks["me"]()
        out = hooks["docker"]("ps", "--filter", f"label=eax.command={me['project']}", "--format", '{{.Label "eax.command.run"}}')
        return any(x.strip() and not x.strip().startswith("console-") for x in out.splitlines())
    except Exception:  # noqa: BLE001
        return False


def start_scheduled(s: dict) -> str:
    """A schedule's run: checked again, then the runner as for a run from the page; who is 'schedule: <name>'."""
    _need()
    argv = C.check_argv([str(a) for a in s.get("argv") or []])
    env = {"EAX_SCHEDULE": s["id"], "EAX_SAFETY_BACKUP": "1" if s.get("backup_first") else "0",
           "EAX_SAFETY_KEEP": str(int(s.get("keep") or 3))}
    return _launch(argv, f"schedule: {s.get('name')} (made by {s.get('created_by')})", _new_id(f"sched{s['id']}"), env)


def schedules_list() -> dict:
    _need()
    _tz_env()
    out = S.listing()
    runs = {r.get("id"): r for r in history(400)}
    for s in out["schedules"]:
        run = runs.get((s.get("last") or {}).get("run"))
        if run:                                    # the run's own end: done, failed, stopped
            s["last"] = {**s["last"], "state": run.get("state"), "exit_code": run.get("exit_code"), "ended": run.get("ended")}
    return {**out, "installation": installation_name()}


def schedule_add(body: dict) -> dict:
    _need()
    _tz_env()
    by = str(body.get("by") or "?")
    roles = [str(r) for r in (body.get("roles") or [])]
    conf = body.get("confirm") or {}
    if body.get("demo"):
        s = S.demo_reset(by, roles, installation_name(), str(conf.get("typed") or ""), bool(conf.get("understood")),
                         at=str(body.get("at") or "02:00"))
    else:
        s = S.make(body, by, roles, installation_name())
    if s.get("banner"):
        B.set_banner({"text": S.banner_text(s), "level": "info", "audience": "everyone", "dismissible": True}, by,
                     source=f"schedule:{s['id']}")
    return s


def schedule_change(sid: str, what: str, body: dict) -> dict:
    _need()
    _tz_env()
    by = str(body.get("by") or "?")
    roles = [str(r) for r in (body.get("roles") or [])]
    if what == "run":
        s = S.find(sid)
        C.allowed_argv(s["argv"], roles)
        run_id = start_scheduled(s)
        S.record(s["id"], {"run": run_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "state": "started", "note": f"run now by {by}"})
        return {"id": run_id, "schedule": s["id"], "command": " ".join(["eax", *s["argv"]])}
    s = S.change(sid, what, by, roles)
    if what == "remove":
        B.clear(by, source=f"schedule:{sid}")
    return s


def scheduler_tick() -> list[dict]:
    if S is None:
        return []
    _tz_env()
    return S.tick(start_scheduled, busy)


def scheduler() -> None:
    """Every 30 seconds: start what is due (a missed run within the hour after a restart runs once, D559)."""
    while True:
        try:
            for x in scheduler_tick():
                print(f"ops: schedule {x['id']}: {x['what']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - never stops the helper
            print(f"ops: command scheduler: {exc}", flush=True)
        time.sleep(30)


# ---------------------------------------------------------------- persist/ (R2.26)
def persist_list() -> dict:
    """What persist/ holds (eaxcli/persist.py items), for System Admin > Persist."""
    _need()
    from eaxcli import persist as P
    return {"items": P.items(), "folder": str(P.folder())}


def persist_delete(body: dict) -> dict:
    """{item | all: true, by}: deletes one item of persist/ (a settings file with its .bak, or a safety backup), or all."""
    _need()
    from eaxcli import persist as P
    gone = P.delete_all() if body.get("all") else P.delete(str(body.get("item") or ""))
    return {"deleted": gone, "items": P.items()}


# ---------------------------------------------------------------- the banner (D558)
def reset_survival_runs() -> dict:
    """The reset-survival test's results (D561), kept in persist/test-results so the reset they test cannot delete them."""
    _need()
    from eaxcli import reset_survival as RS
    return {"runs": RS.history(Path(REPO)), "installation": installation_name()}


def banner_now(admin: bool) -> dict:
    _need()
    _tz_env()
    return {"banner": B.current(admin=admin)}


def banner_all() -> dict:
    _need()
    _tz_env()
    data, warn = B.load()
    sched_warn = S.load()[1]
    return {"banner": data.get("banner"), "history": list(reversed(data.get("history") or [])), "warning": warn,
            "schedules_warning": sched_warn, "file": str(B.path()), "showing": B.current(admin=True)}


def banner_set(body: dict) -> dict:
    _need()
    _tz_env()
    return {"banner": B.set_banner(dict(body.get("banner") or {}), str(body.get("by") or "?"))}


def banner_clear(body: dict) -> dict:
    _need()
    return {"cleared": B.clear(str(body.get("by") or "?"))}


def stop(run_id: str, by: str) -> dict:
    _need()
    rec = _read(os.path.join(RUNS, _safe_id(run_id), "status.json"))
    if not rec:
        raise FileNotFoundError("No such run.")
    if not rec.get("argv") or rec["argv"][0] not in C.STOPPABLE:
        raise C.Refused("This command cannot be stopped halfway; wait for it to finish.")
    cid = _container(run_id)
    if cid:
        hooks["docker"]("stop", "-t", "5", cid)
    rec.update(state="stopped", ended=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), stopped_by=by)
    with open(os.path.join(RUNS, run_id, "status.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    return rec


def ack(ids: list[str]) -> int:
    """Runs whose end is now in the audit trail: marked, so the job records each end once."""
    n = 0
    for run_id in ids:
        try:
            p = os.path.join(RUNS, _safe_id(str(run_id)), "status.json")
        except FileNotFoundError:
            continue
        rec = _read(p)
        if rec and rec.get("ended") and not rec.get("logged"):
            rec["logged"] = True
            with open(p, "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=2)
            n += 1
    return n


def console_ticket(body: dict) -> dict:
    """A one-time ticket for the Console: a terminal running eaxcli/webconsole.py in a container of its own."""
    _need()
    by = str(body.get("by") or "?")
    roles = [str(r) for r in (body.get("roles") or []) if re.match(r"^[a-z-]+$", str(r))]
    C.allowed("status", roles)
    me = hooks["me"]()
    sid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    argv = ["docker", "run", "--rm", "-it", "--name", f"{me['project']}-console-{sid}"[:63],
            "--label", f"eax.command={me['project']}", "--label", f"eax.command.run=console-{sid}",
            "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{me['install']}:{me.get('inside', me['install'])}",
            "-w", me.get("inside", me["install"]), "-e", f"COMPOSE_PROJECT_NAME={me['project']}", "-e", "TERM=xterm-256color",
            "-e", f"EAX_CONSOLE_USER={by}", "-e", f"EAX_CONSOLE_ROLES={','.join(roles)}", "-e", f"EAX_CONSOLE_SESSION={sid}",
            "--entrypoint", "python3", me["image"], "-m", "eaxcli.webconsole"]
    ticket = secrets.token_urlsafe(32)
    now = time.time()
    with hooks["tlock"]:
        hooks["tickets"][ticket] = {"session": f"console-{sid}", "service": "eax console", "cid": "", "argv": argv,
                                    "user": by, "cols": max(20, min(int(body.get("cols") or 120), 500)),
                                    "rows": max(5, min(int(body.get("rows") or 32), 200)), "until": now + 30}
    return {"ticket": ticket, "session": f"console-{sid}", "idle_minutes": hooks["idle_minutes"]()}


def seed_samples(deployment: str) -> int:
    """Laptop sample data (AGENTS.md): when no command has ever been run, a few past runs in each state (done, failed,
    stopped, a wipe kept with its backup note) and a console session with a refused line, so the History shows them."""
    if deployment != "laptop" or (os.path.isdir(RUNS) and os.listdir(RUNS)):
        return 0
    samples = [
        ("20261109T0805Z-status-sa01", "user_it_admin", ["status"], "done", 0, "command centre",
         ("$ eax status    (user_it_admin)\nNAME            STATE     HEALTH\napi-1           running   healthy\n"
          "db-1            running   healthy\n[finished: exit code 0]\n")),
        ("20261109T0810Z-backup-sa02", "user_it_admin", ["backup", "before-upgrade"], "done", 0, "command centre",
         "$ eax backup before-upgrade    (user_it_admin)\nInfrastructure backup 20261109T0810Z-before-upgrade taken.\n[finished: exit code 0]\n"),
        ("20261109T0900Z-restorelog-sa03", "user_super_admin", ["restore-log", "r-missing"], "failed", 1, "command centre",
         "$ eax restore-log r-missing    (user_super_admin)\nNo restore r-missing.\n[finished: exit code 1]\n"),
        ("20261109T0930Z-logs-sa04", "user_it_admin", ["logs", "api"], "stopped", None, "command centre",
         "$ eax logs api    (user_it_admin)\napi-1  | GET /api/health 200\napi-1  | GET /api/v1/models 200\n"),
    ]
    for rid, by, argv, state, code, source, text in samples:
        folder = os.path.join(RUNS, rid)
        os.makedirs(folder, exist_ok=True)
        stamp = f"{rid[:4]}-{rid[4:6]}-{rid[6:8]}T{rid[9:11]}:{rid[11:13]}:00Z"
        with open(os.path.join(folder, "status.json"), "w", encoding="utf-8") as f:
            json.dump({"id": rid, "by": by, "argv": argv, "command": "eax " + " ".join(argv), "kind": C.kind_of(argv[0]) if C else "run",
                       "source": source, "started": stamp, "ended": stamp, "exit_code": code, "state": state,
                       "logged": True, "sample": True}, f, indent=2)
        with open(os.path.join(folder, "output.log"), "w", encoding="utf-8") as f:
            f.write(text)
    folder = os.path.join(RUNS, "console-20261109T1000Z-sa05")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "status.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "console-20261109T1000Z-sa05", "by": "user_super_admin", "kind": "console", "command": "Console session",
                   "source": "console", "started": "2026-11-09T10:00:00Z", "ended": "2026-11-09T10:06:00Z", "state": "done",
                   "exit_code": 0, "argv": [], "logged": True, "sample": True}, f, indent=2)
    lines = [{"at": "2026-11-09T10:01:00Z", "by": "user_super_admin", "command": "eax services", "exit_code": 0, "refused": ""},
             {"at": "2026-11-09T10:02:00Z", "by": "user_super_admin", "command": "", "exit_code": None,
              "refused": "ls -la: 'ls' is not an eax command. Type help for the list."},
             {"at": "2026-11-09T10:04:00Z", "by": "user_super_admin", "command": "eax help restore", "exit_code": 0, "refused": ""}]
    with open(os.path.join(folder, "commands.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(x) + "\n" for x in lines))
    with open(os.path.join(folder, "transcript.log"), "w", encoding="utf-8") as f:
        f.write("EA Explorer console: type eax commands as on the machine itself.\neax> services\nreports  on\ndocuments on\n"
                "eax> ls -la\n'ls' is not an eax command. Type help for the list.\neax> help restore\n...\neax> exit\nConsole ended.\n")
    return len(samples) + 1


def seed_persist(deployment: str) -> int:
    """Laptop sample data (AGENTS.md): when persist/ has no schedules yet, four schedules in each state (a nightly
    backup on, a weekly smoke self-test on, the demo reset off, one whose last run failed), and a banner that was set
    and has ended (in the banner's history only: a banner shows only when an admin sets one, D558)."""
    if deployment != "laptop" or S is None or S.path().exists():
        return 0
    _tz_env()
    who = "user_super_admin"
    items = [
        {"id": "a1b2c3", "name": "Nightly backup", "argv": ["backup", "nightly"], "cron": "30 1 * * *", "enabled": True,
         "created_by": "user_it_admin", "created_at": "2026-11-01T09:00:00", "checked": "2026-11-10T01:30:00",
         "wipe": False, "backup_first": False, "keep": 3, "banner": False, "confirmed": None,
         "last": {"run": "", "at": "2026-11-10T01:30:00", "state": "done", "note": "sample"}, "sample": True},
        {"id": "d4e5f6", "name": "Weekly smoke self-test", "argv": ["test", "--smoke"], "cron": "0 6 * * 1", "enabled": True,
         "created_by": who, "created_at": "2026-11-01T09:05:00", "checked": "2026-11-09T06:00:00",
         "wipe": False, "backup_first": False, "keep": 3, "banner": False, "confirmed": None,
         "last": {"run": "", "at": "2026-11-09T06:00:00", "state": "done", "note": "sample"}, "sample": True},
        {"id": "0d3m01", "name": "Demo reset every night", "argv": ["clean-restart", "laptop"], "cron": "0 2 * * *",
         "enabled": False, "created_by": who, "created_at": "2026-11-02T18:00:00", "checked": "2026-11-02T18:00:00",
         "wipe": True, "backup_first": False, "keep": 3, "banner": True,
         "confirmed": {"by": who, "at": "2026-11-02T18:00:00", "installation": installation_name()},
         "last": {}, "sample": True},
        {"id": "f41l3d", "name": "Weekly model backups", "argv": ["app-backup", "weekly"], "cron": "0 3 * * 0", "enabled": True,
         "created_by": "user_it_admin", "created_at": "2026-11-01T09:10:00", "checked": "2026-11-08T03:00:00",
         "wipe": False, "backup_first": False, "keep": 3, "banner": False, "confirmed": None,
         "last": {"run": "", "at": "2026-11-08T03:00:00", "state": "failed", "exit_code": 1,
                  "note": "sample: the api container was not running"}, "sample": True},
    ]
    S.save(items)
    if not B.path().exists():
        from eaxcli import persist
        persist.write_json(B.path(), {"version": persist.VERSION, "_comment": B.COMMENT, "banner": None, "history": [
            {"text": "EA Explorer is being upgraded on Saturday 7 November from 08:00 to 10:00.", "link": "#/documentation",
             "link_text": "What's new", "level": "notice", "audience": "everyone", "dismissible": True,
             "starts": "2026-11-05T08:00", "ends": "2026-11-07T10:00", "by": "user_it_admin", "at": "2026-11-05T07:55:00",
             "source": "admin", "what": "set", "sample": True}]})
    return len(items)
