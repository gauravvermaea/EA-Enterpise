"""The logs on disk, for the web (R2.30, R2.31, R2.32): the operations helper writes every container's new log lines to
its file of the day every minute, and lists, reads, backs up and cleans them for System Admin. The work is in
eaxcli/logkeep.py, shared with `eax logs backup | clean`.

  GET  /logs/files?service=       the daily files kept
  GET  /logs/own?name=|backup=&member=&q=&page=   eax's own logs (work/logs) and the log backups: listed, or one read
  GET  /logs/read?services=a,b&day=YYYY-MM-DD&level=&q=&since=HH:MM&until=HH:MM&page=N   their lines, merged by time
  POST /logs/backup {tag, by}     one zip of them and eax's own logs in work/backups/logs
  POST /logs/clean {days, by}     delete them and the log backups older than `days`
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = os.environ.get("EAX_REPO_MOUNT", "/eax-repo")
WORK = Path(os.environ.get("EAX_WORK_MOUNT", "/eax-work"))
LOGS = Path(os.environ.get("EAX_LOGS_MOUNT", "/eax-logs"))
BACKUPS = Path(os.environ.get("EAX_BACKUPS_MOUNT", "/backups"))
sys.path.insert(0, REPO)
try:
    from eaxcli import logkeep as K
except Exception:  # noqa: BLE001 - an older compose file without the eaxcli mount
    K = None

hooks: dict = {}       # set by ops.py: containers


def _need() -> None:
    if K is None:
        raise RuntimeError("The logs need eaxcli mounted into the operations helper (docker-compose.yml).")


def read_since(cid: str, since: str) -> list[str]:
    r = subprocess.run(["docker", "logs", "--timestamps", "--since", since, cid], capture_output=True, text=True,
                       errors="replace", timeout=60)
    return (r.stdout + r.stderr).splitlines()


def ship_once() -> dict:
    _need()
    if not LOGS.is_dir():
        return {}
    running = [c for c in hooks["containers"]() if c.get("state") == "running"]
    return K.ship(LOGS, [{"id": c["id"], "service": c["key"]} for c in running], read_since)


def shipper(pause: float = 60) -> None:
    """Every minute, for as long as the helper runs: the new lines of every running container to its file of the day."""
    while True:
        try:
            ship_once()
        except Exception as exc:  # noqa: BLE001 - a disk full or Docker busy: logged, tried again next minute
            print(f"logs: could not write the containers' logs to {LOGS}: {exc}", flush=True)
        time.sleep(pause)


def start() -> None:
    threading.Thread(target=shipper, daemon=True).start()


def files(service: str = "") -> dict:
    _need()
    return {"files": K.files(LOGS, service), "folder": os.environ.get("EAX_LOGS_DIR_HOST", "logs/")}


def read(args: dict) -> dict:
    _need()
    services = [s for s in str(args.get("services") or "").split(",") if s]
    if not services:
        raise ValueError("Choose one or more containers.")
    return K.read(LOGS, services, str(args.get("day") or ""), str(args.get("level") or ""), str(args.get("q") or ""),
                  str(args.get("since") or ""), str(args.get("until") or ""), int(args.get("page") or 0))


def own(args: dict) -> dict:
    """eax's own logs and the log backups: the list, or one of them read (R2.31)."""
    _need()
    if args.get("backup"):
        name = str(args["backup"])
        where = K.kept_backups(LOGS) if (K.kept_backups(LOGS) / name).is_file() else BACKUPS / "logs"
        return K.read_backup(where, name, str(args.get("member") or ""), str(args.get("q") or ""), int(args.get("page") or 0))
    if args.get("name"):
        return K.read_own(WORK / "logs", str(args["name"]), str(args.get("q") or ""), int(args.get("page") or 0))
    got = K.own_files(WORK / "logs", BACKUPS / "logs")
    got["backups"] += K.own_files(WORK / "logs", K.kept_backups(LOGS))["backups"]   # those taken before a reset
    return got


def backup(body: dict) -> dict:
    _need()
    return K.backup(LOGS, WORK / "logs", BACKUPS / "logs", str(body.get("tag") or ""))


def clean(body: dict) -> dict:
    _need()
    out = K.clean(LOGS, WORK / "logs", BACKUPS / "logs", int(body.get("days") or 0))
    out["deleted"] += K.clean(LOGS, WORK / "logs", K.kept_backups(LOGS), int(body.get("days") or 0))["deleted"]
    return out
