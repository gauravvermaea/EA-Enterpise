"""eax schedule: scheduled eax commands from the command line (D559), the same file as System admin > Command
centre > Schedules (persist/schedules.json; the operations helper starts what is due).

  eax schedule list
  eax schedule add "<name>" --at 02:00 [--weekly <0-6>|--hourly <minute>|--once YYYY-MM-DDTHH:MM|--cron "<expr>"]
                   [--off] [--no-backup] [--keep N] [--banner] [--confirm <installation name>] -- <command> [options]
  eax schedule demo-reset [--at 02:00] --confirm <installation name>
  eax schedule on|off|remove|run <id or name>
"""

from __future__ import annotations

from datetime import datetime

from . import banner as B
from . import commands as C
from . import schedules as S
from .core import ROOT, Failure, say

ROLES = ["super-admin"]    # on the machine itself: whoever runs eax may do anything eax does


def _who() -> str:
    import getpass
    try:
        return f"{getpass.getuser()} (command line)"
    except Exception:  # noqa: BLE001
        return "command line"


def _list() -> int:
    out = S.listing(ROOT)
    if out["warning"]:
        say(f"WARNING: {out['warning']}", "yellow")
    say(f"Schedules ({out['time_zone']}; kept in {out['file']}):")
    if not out["schedules"]:
        say("  none. Add one: eax schedule add \"Nightly backup\" --at 01:30 -- backup nightly")
    for s in out["schedules"]:
        last = s.get("last") or {}
        state = "on " if s.get("enabled") else "off"
        say(f"  {s['id']}  {state}  {s['name']:<28} {s['command']:<34} {s['when']:<24} next: {s.get('next') or '-'}"
            + (f"   last: {last.get('state')} {last.get('at', '')}" if last else ""))
    return 0


def _add(args: list[str]) -> int:
    if "--" not in args:
        raise Failure("Put the command after --, e.g. eax schedule add \"Nightly backup\" --at 01:30 -- backup nightly")
    i = args.index("--")
    opts, argv = args[:i], args[i + 1:]
    if not opts or opts[0].startswith("--"):
        raise Failure("Give the schedule a name first, e.g. eax schedule add \"Nightly backup\" --at 01:30 -- backup nightly")
    name, opts = opts[0], opts[1:]
    val = {}
    flags = set()
    k = 0
    while k < len(opts):
        o = opts[k]
        if o in ("--at", "--weekly", "--hourly", "--once", "--cron", "--keep", "--confirm"):
            if k + 1 >= len(opts):
                raise Failure(f"{o} needs a value.")
            val[o] = opts[k + 1]
            k += 2
        elif o in ("--off", "--no-backup", "--banner"):
            flags.add(o)
            k += 1
        else:
            raise Failure(f"Unknown option {o}")
    if "--cron" in val:
        when = {"cron": val["--cron"]}
    elif "--once" in val:
        when = {"preset": {"kind": "once", "at": val["--once"]}}
    elif "--hourly" in val:
        when = {"preset": {"kind": "hourly", "minute": int(val["--hourly"])}}
    elif "--weekly" in val:
        when = {"preset": {"kind": "weekly", "day": int(val["--weekly"]), "time_": val.get("--at", "02:00")}}
    else:
        when = {"preset": {"kind": "nightly", "time_": val.get("--at", "02:00")}}
    if C.kind_of_argv(argv) == "wipe" and not val.get("--confirm"):
        raise Failure(f"eax {argv[0]} deletes everything every time it runs: add --confirm {C.installation_name(ROOT)}")
    body = {"name": name, "argv": argv, **when, "enabled": "--off" not in flags, "backup_first": "--no-backup" not in flags,
            "keep": int(val.get("--keep", 3)), "banner": "--banner" in flags,
            "confirm": {"typed": val.get("--confirm", ""), "understood": True}}
    s = S.make(body, _who(), ROLES, C.installation_name(ROOT), ROOT)
    if s.get("banner"):
        B.set_banner({"text": S.banner_text(s), "level": "info"}, _who(), source=f"schedule:{s['id']}", root=ROOT)
    say(f"Schedule {s['id']} made: {s['name']}: eax {' '.join(s['argv'])}, {s['when']}" + ("" if s["enabled"] else " (off)"), "green")
    if s.get("wipe"):
        say("It deletes everything every time it runs." + (" A safety backup is taken first." if s["backup_first"] else ""), "yellow")
    return 0


def main(args: list[str]) -> int:
    what = args[0] if args else "list"
    rest = args[1:]
    try:
        if what == "list":
            return _list()
        if what == "add":
            return _add(rest)
        if what == "demo-reset":
            at = rest[rest.index("--at") + 1] if "--at" in rest else "02:00"
            typed = rest[rest.index("--confirm") + 1] if "--confirm" in rest and rest.index("--confirm") + 1 < len(rest) else ""
            s = S.demo_reset(_who(), ROLES, C.installation_name(ROOT), typed, True, at=at, root=ROOT)
            B.set_banner({"text": S.banner_text(s), "level": "info"}, _who(), source=f"schedule:{s['id']}", root=ROOT)
            say(f"Schedule {s['id']} made: the demo resets {s['when']} (eax clean-restart laptop); the banner says so.", "green")
            return 0
        if what in ("on", "off", "remove"):
            if not rest:
                raise Failure(f"Which schedule? eax schedule {what} <id or name>")
            s = S.find(rest[0], ROOT)
            S.change(s["id"], what, _who(), ROLES, ROOT)
            if what == "remove":
                B.clear(_who(), ROOT, source=f"schedule:{s['id']}")
            say(f"Schedule {s['id']} ({s['name']}): {what}.", "green")
            return 0
        if what == "run":
            if not rest:
                raise Failure("Which schedule? eax schedule run <id or name>")
            s = S.find(rest[0], ROOT)
            import subprocess
            import sys
            say(f"Running {s['name']} now: eax {' '.join(s['argv'])}")
            code = subprocess.call([sys.executable, str(ROOT / "eaxpy.py"), *C.with_yes(s["argv"])], cwd=ROOT)
            S.record(s["id"], {"at": datetime.now(S.zone(ROOT)).isoformat(timespec="seconds"),
                               "state": "done" if code == 0 else "failed", "exit_code": code, "note": "run now (command line)"}, ROOT)
            return code
        raise Failure("eax schedule list | add | demo-reset | on | off | remove | run")
    except (S.ScheduleError, C.Refused, FileNotFoundError) as exc:
        raise Failure(str(exc)) from exc
