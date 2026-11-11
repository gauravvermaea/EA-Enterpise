"""Runs one eax command for a web page (D554) and keeps its record: work/commands/<run>/status.json and output.log.

The same code runs it for EA Explorer's Command centre (in a short-lived container the operations helper starts, beside
the stack, so it outlives the stack stopping) and for eax deploy's Commands tab (on the machine itself, or on the server
over SSH). Usage, in the installation folder:

    python3 -m eaxcli.cmdrun <run-id> <who> -- <command> [options...]

The command and its options are checked again here (eaxcli/commands.py): nothing but a known eax command runs, through
eaxpy (the same code as typing it), never a shell. A command that deletes everything (cleanup, clean-*) first takes an
infrastructure backup and copies it to persist/safety-backups/ beside the work folder (D558); while it runs, its record
is kept in persist/safety-backups/commands/<run> (the work folder is being emptied) and copied back into work/commands
when it ends. A scheduled run (D559) says so in EAX_SCHEDULE (its id), EAX_SAFETY_BACKUP (0: no backup first) and
EAX_SAFETY_KEEP (how many of its safety backups to keep).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import commands as C

ROOT = Path(__file__).resolve().parent.parent


def runs_dir(root: Path = ROOT) -> Path:
    return root / "work" / "commands"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_status(folder: Path, rec: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "status.json.tmp"
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "status.json")


def read_status(folder: Path) -> dict:
    try:
        return json.loads((folder / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _safety_home(root: Path) -> Path:
    from . import persist
    return persist.folder(root) / "safety-backups" / "commands"


def run(run_id: str, who: str, argv: list[str], root: Path = ROOT, source: str = "command centre") -> int:
    argv = C.with_yes(C.check_argv(argv))
    wipe = C.kind_of_argv(argv) == "wipe"
    schedule = os.environ.get("EAX_SCHEDULE", "")
    if schedule:
        source = f"schedule {schedule}"
    home = (_safety_home(root) / run_id) if wipe else (runs_dir(root) / run_id)
    rec = {"id": run_id, "by": who, "argv": argv, "command": " ".join(["eax", *argv]), "kind": C.kind_of_argv(argv),
           "source": source, "schedule": schedule or None, "started": _now(), "ended": None, "exit_code": None,
           "state": "running"}
    write_status(home, rec)
    code = 0
    with open(home / "output.log", "ab", buffering=0) as out:
        def say(text: str) -> None:
            out.write((text + "\n").encode())
        say(f"$ {rec['command']}    ({who}, {rec['started']})")
        if wipe and os.environ.get("EAX_SAFETY_BACKUP", "1") != "0":
            code = C.safety_backup(root, run_id, say, keep=int(os.environ.get("EAX_SAFETY_KEEP", "0") or 0),
                                   group=f"sched{schedule}" if schedule else "")
            if code:
                say("The backup first failed, so nothing was deleted.")
        elif wipe:
            say("No backup first (this schedule was made without one).")
        if not code:
            env = {**os.environ, "EAX_COMMAND_RUN": run_id, "EAX_COMMAND_BY": who, "PYTHONUNBUFFERED": "1"}
            code = subprocess.call([sys.executable, str(root / "eaxpy.py"), *argv], cwd=root, stdout=out,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
        say(f"[finished: exit code {code}]")
    rec.update(ended=_now(), exit_code=code, state="done" if code == 0 else "failed")
    write_status(home, rec)
    if wipe:                                      # the work folder may be new: put the record back where runs are listed
        dest = runs_dir(root) / run_id
        dest.mkdir(parents=True, exist_ok=True)
        for f in ("status.json", "output.log"):
            try:
                (dest / f).write_bytes((home / f).read_bytes())
            except OSError:
                pass
    return code


def history(root: Path = ROOT, limit: int = 100) -> list[dict]:
    out = []
    base = runs_dir(root)
    if base.is_dir():
        for d in base.iterdir():
            rec = read_status(d)
            if rec:
                out.append(rec)
    out.sort(key=lambda r: r.get("started") or "", reverse=True)
    return out[:limit]


def output(run_id: str, start: int = 0, root: Path = ROOT, limit: int = 200_000) -> dict:
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("No such run.")
    for base in (runs_dir(root) / run_id, _safety_home(root) / run_id):
        f = base / "output.log"
        if f.is_file():
            data = f.read_bytes()
            chunk = data[start:start + limit]
            return {"status": read_status(base), "text": chunk.decode("utf-8", "replace"), "next": start + len(chunk)}
    raise FileNotFoundError("No such run.")


def main(args: list[str]) -> int:
    if len(args) < 4 or args[2] != "--":
        print("Usage: python3 -m eaxcli.cmdrun <run-id> <who> -- <command> [options...]")
        return 2
    try:
        return run(args[0], args[1], args[3:])
    except C.Refused as exc:
        print(f"Refused: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
