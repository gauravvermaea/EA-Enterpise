"""The logs kept on disk, their backups and their cleaning (owner, 12 Nov 2026: R2.30 "backup and clean logs", R2.32
"logs to be written to a mounted disk", R2.31 "see on web per container").

  logs/containers/<service>/<YYYY-MM-DD>.log   every container's log, one file per day, secrets masked; written by the
                                               operations helper every minute (ship), so a container made again (a
                                               clean-restart, an update) loses nothing
  work/backups/logs/<when>-logs.zip            a log backup: the containers' daily files and eax's own logs (work/logs)

The logs folder is EAX_LOGS_DIR (in the config file: a mounted disk on a server), else logs/ beside work/; like
persist/, no cleanup, clean-run or clean-restart empties it. Used by eax (eax logs backup | clean) and by the operations
helper (the web), so both do exactly the same. Plain files, nothing in a database (D248).
"""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import persist

ROOT = Path(__file__).resolve().parent.parent
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}\.log$")
ZIP = re.compile(r"^\d{8}T\d{6}Z-logs(-[a-z0-9-]+)?\.zip$")
LEVELS = ("debug", "info", "warning", "error")
_MASKS = [(re.compile(r"((?:PASSWORD|SECRET|TOKEN|_KEY|URLENC)[A-Za-z_]*\s*[:=]\s*)\S+", re.I), r"\1****"),
          (re.compile(r"(postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:)[^@\s]+@"), r"\1****@"),
          (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1****"),
          (re.compile(r'("(?:password|secret|token)"\s*:\s*")[^"]*"', re.I), r'\1****"')]


def mask(line: str) -> str:
    """A log line with what looks like a secret hidden (passwords, tokens, keys, a connection string's password)."""
    for rx, rep in _MASKS:
        line = rx.sub(rep, line)
    return line


def folder(root: Path | str | None = None) -> Path:
    """The logs folder: EAX_LOGS_DIR from the environment or the config file, else logs/ beside work/."""
    root = Path(root) if root else ROOT
    given = os.environ.get("EAX_LOGS_DIR") or persist._config_value(root, "EAX_LOGS_DIR")
    p = Path(given) if given else root / "logs"
    return p if p.is_absolute() else root / p


def level_of(line: str) -> str:
    """debug, info, warning or error, from the words a line carries (info when it says none)."""
    low = line.lower()
    if re.search(r"\b(error|exception|traceback|critical|fatal|failed)\b", low):
        return "error"
    if re.search(r"\b(warn|warning)\b", low):
        return "warning"
    if re.search(r"\bdebug\b", low):
        return "debug"
    return "info"


# ---------------------------------------------------------------- written every minute (the operations helper)
def ship(base: Path, containers: list[dict], read_since, now: float | None = None) -> dict[str, int]:
    """Appends each container's new log lines to its file of the day. containers: {id, service}; read_since(id, since)
    gives its lines with their timestamps ("2026-11-13T05:00:01.123456789Z text") since an RFC 3339 time. Where each
    container got to is kept in .shipped.json, so nothing is written twice."""
    state_file = base / ".shipped.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    now = now or time.time()
    out: dict[str, int] = {}
    for c in containers:
        last = state.get(c["id"]) or datetime.fromtimestamp(now - 600, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        lines = [ln for ln in read_since(c["id"], last) if ln[:30] > last]
        n = 0
        for ln in sorted(lines):
            day = ln[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T", ln) else datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
            f = base / "containers" / c["service"] / f"{day}.log"
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(mask(ln.rstrip("\n")) + "\n")
            n += 1
            state[c["id"]] = ln.split(" ", 1)[0][:30]
        out[c["service"]] = out.get(c["service"], 0) + n
    base.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_name(".shipped.json.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, state_file)
    return out


# ---------------------------------------------------------------- reading (the web, R2.31)
def files(base: Path, service: str = "") -> list[dict]:
    """The daily files kept: service, day, size; the newest first."""
    out = []
    root = base / "containers"
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or (service and d.name != service):
            continue
        for f in d.iterdir():
            if DAY.match(f.name):
                out.append({"service": d.name, "day": f.name[:10], "size": f.stat().st_size})
    return sorted(out, key=lambda x: (x["day"], x["service"]), reverse=True)


def read(base: Path, services: list[str], day: str, level: str = "", q: str = "", since: str = "", until: str = "",
         page: int = 0, size: int = 1000) -> dict:
    """The lines of one day of one or several containers, merged by time, filtered by level (that level and worse),
    words and time (HH:MM), a page at a time (never the whole file at once in the answer)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day or ""):
        raise ValueError("Give the day as YYYY-MM-DD.")
    worse = LEVELS[LEVELS.index(level):] if level in LEVELS else LEVELS
    rows = []
    for s in services:
        if not re.match(r"^[a-z0-9_-]+$", s):
            raise ValueError(f"No container {s!r}.")
        f = base / "containers" / s / f"{day}.log"
        if not f.is_file():
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.rstrip("\n")
                t = ln[11:16]
                if (since and t < since) or (until and t > until):
                    continue
                lv = level_of(ln)
                if lv not in worse or (q and q.lower() not in ln.lower()):
                    continue
                rows.append({"service": s, "line": ln, "level": lv})
    rows.sort(key=lambda r: r["line"][:30])
    total = len(rows)
    start = max(0, int(page)) * size
    return {"day": day, "services": services, "total": total, "page": int(page), "pages": (total + size - 1) // size,
            "lines": rows[start:start + size]}


# ---------------------------------------------------------------- backing up and cleaning (R2.30)
def backup(base: Path, own_logs: Path, dest: Path, tag: str = "") -> dict:
    """One zip of every container's daily files and eax's own logs, in dest (work/backups/logs)."""
    dest.mkdir(parents=True, exist_ok=True)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-logs" + (f"-{re.sub(r'[^a-z0-9-]', '', tag.lower())}" if tag else "") + ".zip"
    n = 0
    with zipfile.ZipFile(dest / name, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in ((base / "containers", "containers"), (own_logs, "eax")):
            if not src.is_dir():
                continue
            for f in sorted(src.rglob("*")):
                if f.is_file() and not f.name.startswith("."):
                    z.write(f, f"{arc}/{f.relative_to(src)}")
                    n += 1
    return {"file": name, "files": n, "size": (dest / name).stat().st_size}


def clean(base: Path, own_logs: Path, zips: Path, days: int, now: float | None = None) -> dict:
    """Deletes the daily files, eax's own logs and the log backups older than `days` (0 keeps them); returns what went."""
    if int(days) <= 0:
        return {"deleted": [], "kept_days": 0}
    cut = (now or time.time()) - int(days) * 86400
    cut_day = datetime.fromtimestamp(cut, UTC).strftime("%Y-%m-%d")
    gone: list[str] = []
    for f in (base / "containers").rglob("*.log") if (base / "containers").is_dir() else []:
        if DAY.match(f.name) and f.name[:10] < cut_day:
            f.unlink()
            gone.append(f"containers/{f.parent.name}/{f.name}")
    for d, label in ((own_logs, "work/logs"), (zips, "backups/logs")):
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.stat().st_mtime < cut and (d is not zips or ZIP.match(f.name)):
                f.unlink()
                gone.append(f"{label}/{f.name}")
    return {"deleted": sorted(gone), "kept_days": int(days)}


def kept_backups(base: Path) -> Path:
    """Where the log backups taken before a reset go: inside the logs folder, which no reset empties (R2.30)."""
    return base / "backups"


def default_keep_days(deployment: str) -> int:
    """14 days on a laptop, 90 on a server or in the cloud (R2.30)."""
    return 14 if (deployment or "laptop").lower() == "laptop" else 90


def older_than(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- eax's own logs and the log backups, read (R2.31)
SAFE = re.compile(r"^[A-Za-z0-9._ -]{1,120}$")


def own_files(own_logs: Path, zips: Path) -> dict:
    """eax's own logs (work/logs: up, start-later, test, ...) and the log backups (work/backups/logs), newest first."""
    def listing(d: Path, pat: str) -> list[dict]:
        if not d.is_dir():
            return []
        return sorted(({"name": f.name, "size": f.stat().st_size, "changed": f.stat().st_mtime}
                       for f in d.glob(pat) if f.is_file()), key=lambda x: x["changed"], reverse=True)
    return {"own": listing(own_logs, "*.log"), "backups": listing(zips, "*-logs*.zip")}


def _page(lines: list[str], q: str, page: int, size: int) -> dict:
    rows = [{"line": mask(ln), "level": level_of(ln)} for ln in lines if not q or q.lower() in ln.lower()]
    start = max(0, int(page)) * size
    return {"total": len(rows), "page": int(page), "pages": (len(rows) + size - 1) // size, "lines": rows[start:start + size]}


def read_own(own_logs: Path, name: str, q: str = "", page: int = 0, size: int = 1000) -> dict:
    """One of eax's own logs, a page at a time, secrets masked."""
    if not SAFE.match(name or "") or not name.endswith(".log"):
        raise ValueError("Choose one of eax's logs.")
    f = own_logs / name
    if not f.is_file():
        raise ValueError(f"No log {name}.")
    return {"name": name, **_page(f.read_text(encoding="utf-8", errors="replace").splitlines(), q, page, size)}


def read_backup(zips: Path, name: str, member: str = "", q: str = "", page: int = 0, size: int = 1000) -> dict:
    """A log backup: its files, or one of them read a page at a time."""
    if not ZIP.match(name or ""):
        raise ValueError("Choose one of the log backups.")
    f = zips / name
    if not f.is_file():
        raise ValueError(f"No log backup {name}.")
    with zipfile.ZipFile(f) as z:
        members = [i.filename for i in z.infolist() if not i.is_dir()]
        if not member:
            return {"name": name, "members": members}
        if member not in members:
            raise ValueError(f"{name} has no {member}.")
        text = z.read(member).decode("utf-8", errors="replace")
    return {"name": name, "member": member, "members": members, **_page(text.splitlines(), q, page, size)}
