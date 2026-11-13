"""The Docker engine, the mounts, a file explorer in each container, and alerts when a container is not working
(Release 2: R2.16 to R2.19, D638 to D641; owner, 11 Nov 2026). Read through this helper, which reaches the Docker engine.

  GET  /hosts                          the engine EA Explorer runs on: OS, kernel, Docker and Compose versions, CPUs and
                                       their use, memory, disks, Docker's own disk, containers, uptime, levels, history
  GET  /mounts                         every volume and bind mount the containers use, who uses it where, warnings
  GET  /mounts/<id>[?path=]            one mount: size, free space, files, largest, newest and oldest; or a folder in it
  GET  /mounts/<id>/search?name=&min_mb=&days=   files in it by name, size or age
  GET  /containers/<s>/files?path=     a folder in a container (name, size, date, owner, permissions; mounts marked)
  GET  /containers/<s>/files/content?path=       a text file (with its sha256, for a safe edit)
  GET  /containers/<s>/files/download?path=      a file, or a folder as a zip (base64 in JSON)
  POST /containers/<s>/files           {op: write|upload|mkdir|rename|move|copy|delete, path, to, content, sha256,
                                        files, confirm}: every write is checked here and audited by the API
  GET  /alerts                         the open alerts and their history
  POST /alerts/test                    {service}: an alert as if that container had stopped (the self-test), then its
                                       recovery notice on the next look

Mounts are looked into with this helper's own image, the mount attached read only (nothing in it can change); a
container's files through docker exec and docker cp, as the terminal does (D214), switched off with
EAX_CONTAINER_CONSOLE=off. Alerts: a watcher every minute (it works while the API is down); each problem told once (again
after EAX_ALERT_REPEAT_MINUTES while it lasts) and its recovery once, to the API, which makes the notification for the IT
Admins and Super Admins and sends the webhooks. Alerts that cannot be delivered wait in work/ops/alerts.json.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tarfile
import threading
import time
import zipfile

hooks: dict = {}   # set by ops.py: docker, containers, stats, filesystems, host_cpus, console_on, values, me_image,
                   # maintenance, restarting, restart_service, token

WORK = os.environ.get("EAX_WORK_MOUNT", "/eax-work")
STATE_FILE = os.path.join(WORK, "ops", "alerts.json")
HISTORY_FILE = os.path.join(WORK, "ops", "host-history.jsonl")
HISTORY_POINTS = 1440                     # a day of one-minute samples
_lock = threading.Lock()


def _cfg(name: str, default: str) -> str:
    try:
        v = hooks["values"]().get(name, "")
    except Exception:  # noqa: BLE001 - no config file yet
        v = ""
    return (v or os.environ.get(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_cfg(name, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------- R2.16 the Docker engine
def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


_cpu_last: dict = {"busy": None, "total": None, "pct": None}


def cpu_percent(stat_text: str | None = None) -> float | None:
    """The whole machine's CPU use since the last look (/proc/stat is the host's, also inside a container)."""
    line = (stat_text if stat_text is not None else _read("/proc/stat")).splitlines()[:1]
    if not line or not line[0].startswith("cpu "):
        return None
    v = [int(x) for x in line[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    total = sum(v[:8])
    busy = total - idle
    if _cpu_last["total"] is not None and total > _cpu_last["total"]:
        _cpu_last["pct"] = round((busy - _cpu_last["busy"]) / (total - _cpu_last["total"]) * 100, 1)
    _cpu_last.update(busy=busy, total=total)
    return _cpu_last["pct"]


def meminfo(text_: str | None = None) -> dict:
    out = {}
    for line in (text_ if text_ is not None else _read("/proc/meminfo")).splitlines():
        k, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[k] = int(parts[0]) * 1024
    return out


def level(value: float | None, warn: int, alert: int) -> str:
    if value is None:
        return "unknown"
    return "red" if value >= alert else "amber" if value >= warn else "green"


def thresholds() -> dict:
    return {k: {"warn": _int(f"EAX_HOST_WARN_{k.upper()}", w), "alert": _int(f"EAX_HOST_ALERT_{k.upper()}", a)}
            for k, w, a in (("cpu", 80, 90), ("memory", 85, 95), ("disk", 80, 90))}


def _history() -> list[dict]:
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines()[-HISTORY_POINTS:] if x.strip()]
    except (OSError, ValueError):
        return []


def _keep_sample(h: dict) -> None:
    point = {"at": int(time.time()), "cpu": h.get("cpu_percent"), "memory": h.get("memory_percent"),
             "disk": h.get("disk_percent"), "eax_cpu": h.get("eax_cpu_percent"), "eax_memory": h.get("eax_memory_bytes")}
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        lines = _history()[-(HISTORY_POINTS - 1):] + [point]
        with open(HISTORY_FILE + ".tmp", "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        os.replace(HISTORY_FILE + ".tmp", HISTORY_FILE)
    except OSError:
        pass


def host(sample: bool = False) -> dict:
    """The engine this installation runs on, now."""
    d = hooks["docker"]
    try:
        info = json.loads(d("info", "--format", "{{json .}}", timeout=30) or "{}")
    except Exception as exc:  # noqa: BLE001
        info = {"error": str(exc)}
    try:
        compose = d("compose", "version", "--short", timeout=30).strip()
    except Exception:  # noqa: BLE001 - no compose plugin in this helper's image
        compose = ""
    st = hooks["stats"]()
    rows = st.get("containers") or []
    mem = meminfo()
    total_mem = mem.get("MemTotal") or info.get("MemTotal")
    avail = mem.get("MemAvailable")
    used_mem = (total_mem - avail) if total_mem and avail is not None else None
    eax_mem = sum(r.get("memory_bytes") or 0 for r in rows)
    eax_cpu = round(sum(r.get("cpu_percent") or 0 for r in rows), 1)
    cpu = cpu_percent()
    if cpu is None or not sample:        # a page asking: a fresh short sample rather than since the last minute
        time.sleep(0.5)
        cpu = cpu_percent()
    load = (_read("/proc/loadavg").split() + ["", "", ""])[:3]
    up = _read("/proc/uptime").split()
    disks = st.get("filesystems") or hooks["filesystems"]()
    root = next((x for x in disks if x.get("path") == "/" and "used_percent" in x), None)
    t = thresholds()
    h = {"name": info.get("Name"), "os": info.get("OperatingSystem"), "os_type": info.get("OSType"),
         "kernel": info.get("KernelVersion"), "architecture": info.get("Architecture"),
         "docker_version": info.get("ServerVersion"), "compose_version": compose, "docker_root": info.get("DockerRootDir"),
         "cpus": info.get("NCPU") or hooks["host_cpus"](), "cpu_percent": cpu, "load": load,
         "memory_total_bytes": total_mem, "memory_used_bytes": used_mem, "memory_free_bytes": avail,
         "memory_percent": round(used_mem / total_mem * 100, 1) if used_mem is not None and total_mem else None,
         "eax_memory_bytes": eax_mem, "other_memory_bytes": (used_mem - eax_mem) if used_mem is not None else None,
         "eax_cpu_percent": eax_cpu, "containers_running": info.get("ContainersRunning"),
         "containers_total": info.get("Containers"), "eax_containers": len(rows),
         "eax_running": sum(1 for r in rows if r.get("state") == "running"), "images": info.get("Images"),
         "uptime_seconds": int(float(up[0])) if up else None, "disks": disks, "docker_disk": st.get("docker_disk") or [],
         "disk_percent": root.get("used_percent") if root else None, "error": info.get("error")}
    h["levels"] = {"cpu": level(h["cpu_percent"], **t["cpu"]), "memory": level(h["memory_percent"], **t["memory"]),
                   "disk": level(h["disk_percent"], **t["disk"])}
    h["shares"] = sorted(({"service": r.get("key") or r.get("service"), "cpu_percent": r.get("cpu_percent"),
                           "memory_bytes": r.get("memory_bytes")} for r in rows), key=lambda x: -(x["memory_bytes"] or 0))
    if sample:
        _keep_sample(h)
    return h


def hosts() -> dict:
    """Every engine (one today: a laptop or a single server; more with Farm Admin, R2.1), the thresholds and the day's
    history (one sample a minute, kept in work/ops/host-history.jsonl)."""
    return {"hosts": [host()], "thresholds": thresholds(), "history": _history()}


# ---------------------------------------------------------------- R2.17 the mounts
# where a container must be able to write: read only there is a fault (R2.3, R2.8: "installation folder is not known")
WRITABLE = ("/eax-work", "/backups", "/eax-logs", "/eax-persist", "/var/lib/postgresql/data", "/results", "/data")


def _mid(source: str) -> str:
    return hashlib.sha1(source.encode()).hexdigest()[:12]


def mounts() -> dict:
    d = hooks["docker"]
    rows = hooks["containers"]()
    try:
        inspected = json.loads(d("inspect", *[r["id"] for r in rows], timeout=60) or "[]") if rows else []
    except Exception as exc:  # noqa: BLE001
        return {"mounts": [], "error": str(exc)}
    sizes = hooks["volume_sizes"]() or {}
    by: dict[str, dict] = {}
    svc = {r["id"][:12]: r.get("key") or r["service"] for r in rows}
    for c in inspected:
        name = svc.get((c.get("Id") or "")[:12], c.get("Name", "").lstrip("/"))
        err = ((c.get("State") or {}).get("Error") or "")
        for m in c.get("Mounts") or []:
            source = m.get("Name") or m.get("Source") or ""
            if not source or source.endswith("docker.sock"):
                continue
            x = by.setdefault(source, {"id": _mid(source), "type": m.get("Type"), "source": source,
                                       "host_path": m.get("Source"), "used_by": [], "warnings": [],
                                       "bytes": sizes.get(source)})
            ro = not m.get("RW", True)
            x["used_by"].append({"service": name, "path": m.get("Destination"), "read_only": ro,
                                 "running": (c.get("State") or {}).get("Running")})
            if ro and any(str(m.get("Destination", "")).startswith(w) for w in WRITABLE):
                x["warnings"].append(f"read only in {name} at {m.get('Destination')}, where it must be writable")
            if err and ("mount" in err.lower() or "no such file" in err.lower()):
                x["warnings"].append(f"{name} could not start with it: {err[:200]}")
    out = sorted(by.values(), key=lambda x: (x["type"] != "volume", x["source"]))
    return {"mounts": out, "at": time.time()}


PROBE = r'''
import json, os, sys, time
mode, root, arg = sys.argv[1], "/m", json.loads(sys.argv[2])
def walk(top):
    for d, dirs, files in os.walk(top):
        for f in files:
            p = os.path.join(d, f)
            try:
                s = os.lstat(p)
            except OSError:
                continue
            yield p, s
def rel(p):
    return "/" + os.path.relpath(p, root) if p != root else "/"
if mode == "summary":
    st = os.statvfs(root)
    n, size, files = 0, 0, []
    for p, s in walk(root):
        n += 1; size += s.st_size; files.append((s.st_size, s.st_mtime, rel(p)))
        if len(files) > 200000: break
    big = sorted(files, reverse=True)[:15]
    new = sorted(files, key=lambda x: -x[1])[:10]
    old = sorted(files, key=lambda x: x[1])[:10]
    folders = {}
    for sz, _, p in files:
        top = "/" + p.strip("/").split("/")[0] if p.count("/") > 1 else "/"
        folders[top] = folders.get(top, 0) + sz
    f = lambda xs: [{"path": p, "bytes": sz, "modified": m} for sz, m, p in xs]
    print(json.dumps({"files": n, "bytes": size, "disk_total": st.f_blocks * st.f_frsize, "disk_free": st.f_bavail * st.f_frsize,
                      "largest": f(big), "newest": f(new), "oldest": f(old),
                      "folders": sorted(({"path": k, "bytes": v} for k, v in folders.items()), key=lambda x: -x["bytes"])[:15]}))
elif mode == "list":
    p = os.path.normpath(os.path.join(root, arg.get("path", "/").lstrip("/")))
    if not p.startswith(root):
        print(json.dumps({"error": "Outside the mount."})); sys.exit()
    out = []
    for e in sorted(os.scandir(p), key=lambda e: e.name)[:2000]:
        s = e.stat(follow_symlinks=False)
        out.append({"name": e.name, "dir": e.is_dir(follow_symlinks=False), "bytes": s.st_size, "modified": s.st_mtime})
    print(json.dumps({"path": rel(p), "entries": out}))
else:
    name, mb, days = arg.get("name", "").lower(), float(arg.get("min_mb") or 0), float(arg.get("days") or 0)
    since = time.time() - days * 86400 if days else 0
    out = []
    for p, s in walk(root):
        if name and name not in os.path.basename(p).lower(): continue
        if s.st_size < mb * 1e6 or s.st_mtime < since: continue
        out.append({"path": rel(p), "bytes": s.st_size, "modified": s.st_mtime})
        if len(out) >= 500: break
    print(json.dumps({"found": out}))
'''


def _mount(mid: str) -> dict:
    for m in mounts().get("mounts") or []:
        if m["id"] == mid:
            return m
    raise FileNotFoundError(f"No mount {mid}.")


def probe(mid: str, mode: str, arg: dict | None = None) -> dict:
    """Looks into a mount with this helper's own image, the mount attached read only at /m (nothing can change)."""
    m = _mount(mid)
    out = hooks["docker"]("run", "--rm", "--network", "none", "--entrypoint", "python3", "-v", f"{m['source']}:/m:ro",
                          hooks["me_image"](), "-c", PROBE, mode, json.dumps(arg or {}), timeout=180)
    data = json.loads(out.strip().splitlines()[-1] or "{}")
    if data.get("error"):
        raise ValueError(data["error"])
    if mode == "summary":
        data["warnings"] = list(m["warnings"])
        if data.get("disk_total"):
            free = data["disk_free"] / data["disk_total"] * 100
            if free < 10:
                data["warnings"].append(f"nearly full: {free:.0f}% free on the disk under it")
        data["mount"] = m
    return data


# ---------------------------------------------------------------- R2.18 a file explorer in each container
HIDDEN = re.compile(r"(^|/)(credentials[^/]*|\.ssh|id_rsa[^/]*|id_ed25519[^/]*|secrets?)(/|$)|^/run/secrets(/|$)|docker\.sock$")
NEVER_WRITE = ("/proc", "/sys", "/dev", "/run/secrets", "/var/run/docker.sock", "/etc/passwd", "/etc/shadow")
DATABASE = ("/var/lib/postgresql/data",)
TEXT_LIMIT = 2_000_000
DIRS_MARK = "@@eax-folders@@"


def _cid(service: str) -> str:
    for r in hooks["containers"]():
        if r.get("key") == service or r["service"] == service:
            return r["id"]
    raise FileNotFoundError(f"No container {service}.")


def _clean(path: str) -> str:
    p = os.path.normpath("/" + (path or "/").lstrip("/"))
    if "\x00" in p:
        raise ValueError("Not a path.")
    return p


def _need_console() -> None:
    if not hooks["console_on"]():
        raise PermissionError("The file explorer is switched off on this installation (EAX_CONTAINER_CONSOLE=off).")


def hidden(path: str) -> bool:
    return bool(HIDDEN.search(path))


def write_check(service: str, path: str, confirm: str = "") -> str:
    """Why a write here is refused ("" when it may go ahead). The helper's own files are read only; secrets, Docker's
    socket and the kernel's folders are never written; a database's data folder needs confirm="database"."""
    p = _clean(path)
    if service.startswith("ops"):
        return "The operations helper's own files are read only."
    if hidden(p) or any(p == x or p.startswith(x + "/") for x in NEVER_WRITE):
        return f"{p} is never changed here."
    if any(p == x or p.startswith(x + "/") for x in DATABASE) and confirm != "database":
        return ("This is a database's data folder: changing files here can break the database for good. Use the SQL "
                "window or a backup and restore instead. To go on anyway, confirm with 'database'.")
    return ""


def _exec(cid: str, *cmd: str, timeout: int = 60) -> str:
    return hooks["docker"]("exec", cid, *cmd, timeout=timeout)


def files_list(service: str, path: str = "/") -> dict:
    """One folder's entries. The folder is given to find with a trailing slash, so a folder that is a link (/bin, /lib
    and /sbin on most images link to /usr/...) is followed and its contents listed; a link to a folder is a folder (R2.60,
    owner 13 Nov 2026: "double click on a folder at root level, there is no folders inside it")."""
    _need_console()
    cid, p = _cid(service), _clean(path)
    q = shlex.quote(p.rstrip("/") + "/")
    out = _exec(cid, "sh", "-c", f"find {q} -mindepth 1 -maxdepth 1 -exec stat -c '%n|%s|%Y|%U|%A|%F' {{}} + "
                                 f"2>/dev/null | head -n 3000; echo {DIRS_MARK}; "
                                 f"find -L {q} -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -n 3000; true")
    d = json.loads(hooks["docker"]("inspect", cid, timeout=30))[0]
    mpoints = {m.get("Destination"): {"source": m.get("Name") or m.get("Source"), "read_only": not m.get("RW", True)}
               for m in d.get("Mounts") or []}
    listing, _, dirs_out = out.partition(DIRS_MARK)
    folders = {os.path.normpath(x.strip()) for x in dirs_out.splitlines() if x.strip()}
    rows = []
    for line in listing.splitlines():
        parts = line.rsplit("|", 5)
        if len(parts) != 6:
            continue
        full, size, mtime, owner, perms, kind = parts
        full = os.path.normpath(full)
        if hidden(full):
            continue
        link = "link" in kind
        rows.append({"name": os.path.basename(full), "path": full, "bytes": int(size) if size.isdigit() else 0,
                     "modified": int(mtime) if mtime.isdigit() else 0, "owner": owner, "permissions": perms,
                     "dir": "directory" in kind or (link and full in folders), "link": link, "mount": mpoints.get(full)})
    rows.sort(key=lambda r: (not r["dir"], r["name"].lower()))
    return {"service": service, "path": p, "entries": rows, "mount": mpoints.get(p),
            "read_only_reason": write_check(service, p + "/x")}


def _cp_out(cid: str, path: str) -> bytes:
    r = subprocess.run(["docker", "cp", "-L", f"{cid}:{path}", "-"], capture_output=True, timeout=300)
    if r.returncode:
        raise FileNotFoundError((r.stderr or b"").decode(errors="replace").strip()[:300] or f"No {path}.")
    return r.stdout


def _cp_in(cid: str, folder: str, files: dict[str, bytes]) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            t.addfile(info, io.BytesIO(data))
    r = subprocess.run(["docker", "cp", "-", f"{cid}:{folder}"], input=buf.getvalue(), capture_output=True, timeout=300)
    if r.returncode:
        raise RuntimeError((r.stderr or b"").decode(errors="replace").strip()[:300])


def _one_file(tar_bytes: bytes) -> tuple[str, bytes] | None:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        members = [m for m in t.getmembers() if m.isfile()]
        if len(members) == 1 and len(t.getmembers()) == 1:
            return members[0].name, t.extractfile(members[0]).read()
    return None


def files_content(service: str, path: str) -> dict:
    _need_console()
    p = _clean(path)
    if hidden(p):
        raise PermissionError("Not shown here.")
    one = _one_file(_cp_out(_cid(service), p))
    if not one:
        raise ValueError(f"{p} is a folder: download it as a zip.")
    data = one[1]
    if len(data) > TEXT_LIMIT or b"\x00" in data[:8000]:
        return {"path": p, "bytes": len(data), "binary": True, "sha256": hashlib.sha256(data).hexdigest()}
    return {"path": p, "bytes": len(data), "binary": False, "sha256": hashlib.sha256(data).hexdigest(),
            "text": data.decode("utf-8", errors="replace"), "read_only_reason": write_check(service, p)}


def files_download(service: str, path: str) -> dict:
    _need_console()
    p = _clean(path)
    if hidden(p):
        raise PermissionError("Not shown here.")
    raw = _cp_out(_cid(service), p)
    one = _one_file(raw)
    if one:
        return {"name": os.path.basename(p) or "file", "content": base64.b64encode(one[1]).decode()}
    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw)) as t, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for m in t.getmembers():
            if m.isfile() and not hidden("/" + m.name):
                z.writestr(m.name, t.extractfile(m).read())
    return {"name": (os.path.basename(p) or "root") + ".zip", "content": base64.b64encode(buf.getvalue()).decode()}


def files_change(service: str, b: dict) -> dict:
    """One write, checked: write (an edit, refused when the file changed meanwhile), upload, mkdir, rename, move, copy,
    delete. Returns what was done (the API puts it in the audit trail, an edit with its before and after)."""
    _need_console()
    op, p = str(b.get("op") or ""), _clean(str(b.get("path") or ""))
    to = _clean(str(b.get("to"))) if b.get("to") else ""
    for target in [p] + ([to] if to else []):
        why = write_check(service, target, str(b.get("confirm") or ""))
        if why:
            raise PermissionError(why)
    if p == "/" or (to == "/"):
        raise PermissionError("Not the whole file system.")
    cid = _cid(service)
    done: dict = {"op": op, "path": p, "to": to}
    if op == "write":
        new = str(b.get("content") or "").encode()
        before = b""
        try:
            got = _one_file(_cp_out(cid, p))
            before = got[1] if got else b""
        except FileNotFoundError:
            pass
        if b.get("sha256") and hashlib.sha256(before).hexdigest() != b["sha256"]:
            raise ValueError("The file changed since you opened it: open it again, then make your change.")
        _cp_in(cid, os.path.dirname(p), {os.path.basename(p): new})
        done.update(before=before[:20000].decode("utf-8", errors="replace"), after=new[:20000].decode("utf-8", errors="replace"),
                    bytes=len(new))
    elif op == "upload":
        files = {str(f["name"]).replace("/", "_"): base64.b64decode(f.get("content") or "") for f in b.get("files") or []}
        if not files:
            raise ValueError("Choose files to upload.")
        if not b.get("overwrite"):
            have = {e["name"] for e in files_list(service, p)["entries"]}
            clash = sorted(set(files) & have)
            if clash:
                raise FileExistsError(f"Already there (tick overwrite to replace): {', '.join(clash)}")
        _cp_in(cid, p, files)
        done.update(files=sorted(files), bytes=sum(len(v) for v in files.values()))
    elif op == "mkdir":
        _exec(cid, "mkdir", "-p", p)
    elif op in ("rename", "move"):
        if not to:
            raise ValueError("Say where it goes.")
        _exec(cid, "mv", "-n", p, to)
    elif op == "copy":
        if not to:
            raise ValueError("Say where the copy goes.")
        _exec(cid, "cp", "-a", p, to, timeout=300)
    elif op == "delete":
        if str(b.get("confirm_path") or "") != p:
            raise ValueError(f"To delete, confirm with the full path: {p}")
        _exec(cid, "rm", "-rf", "--", p, timeout=300)
    else:
        raise ValueError(f"Unknown change {op!r}.")
    return done


# ---------------------------------------------------------------- R2.19 alerts when a container is not working
ONE_SHOT = ("setup", "reports-init", "testrunner")
WORDS = {"stopped": "has stopped", "restarting": "keeps restarting", "unhealthy": "is unhealthy (its health check fails)",
         "oom": "ran out of memory", "host-cpu": "CPU has been high", "host-memory": "memory has been high", "host-disk": "disk is nearly full"}


def assess(rows: list[dict], host_levels: dict | None = None, seen_restarts: dict | None = None) -> list[dict]:
    """What is not working now: one entry per problem, keyed so it is told once."""
    out = []
    seen = seen_restarts if seen_restarts is not None else {}
    for r in rows:
        name = r.get("key") or r.get("service") or "?"
        if r.get("service") in ONE_SHOT or str(r.get("service", "")).endswith("-init"):
            if r.get("state") == "exited" and int(r.get("exit_code") or 0) != 0:
                out.append({"key": f"{name}:stopped", "service": name, "kind": "stopped",
                            "detail": f"the set-up step ended with exit code {r.get('exit_code')}"})
            continue
        state = r.get("state")
        if state in ("exited", "dead"):
            out.append({"key": f"{name}:stopped", "service": name, "kind": "stopped",
                        "detail": f"{r.get('status') or state} (exit code {r.get('exit_code')})"})
        restarts, before = int(r.get("restarts") or 0), seen.get(name)
        seen[name] = restarts
        if state == "restarting" or (before is not None and restarts - before >= 2):
            out.append({"key": f"{name}:restarting", "service": name, "kind": "restarting",
                        "detail": f"restarted {restarts} time(s) since it was made"})
        if r.get("health") == "unhealthy":
            out.append({"key": f"{name}:unhealthy", "service": name, "kind": "unhealthy", "detail": r.get("status") or ""})
        if r.get("oom_killed"):
            out.append({"key": f"{name}:oom", "service": name, "kind": "oom", "detail": "killed for using too much memory"})
    for k, lv in (host_levels or {}).items():
        if lv == "red":
            out.append({"key": f"host:{k}", "service": "host", "kind": f"host-{k}",
                        "detail": f"{k} above the alert level for {_int('EAX_ALERT_HOST_MINUTES', 10)} minutes"})
    return out


def step(problems: list[dict], open_: dict, now: float, repeat_minutes: int) -> list[dict]:
    """The events to tell: a new problem (alert), one still there after repeat_minutes (reminder), one gone
    (recovered). open_ is changed in place."""
    events, keys = [], {p["key"] for p in problems}
    for p in problems:
        o = open_.get(p["key"])
        if not o:
            open_[p["key"]] = {**p, "since": now, "told": now, "times": 1}
            events.append({**p, "event": "alert", "since": now})
        elif repeat_minutes and now - o["told"] >= repeat_minutes * 60:
            o.update(told=now, times=o["times"] + 1, detail=p["detail"])
            events.append({**p, "event": "reminder", "since": o["since"], "times": o["times"]})
    for k in [k for k in open_ if k not in keys]:
        o = open_.pop(k)
        events.append({**o, "event": "recovered", "minutes": round((now - o["since"]) / 60, 1)})
    return events


def _load() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    for k, v in (("open", {}), ("history", []), ("outbox", []), ("restarts", {}), ("seen_restarts", {}), ("tests", {})):
        s.setdefault(k, v)
    return s


def _save(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        s["history"] = s["history"][-500:]
        s["outbox"] = s["outbox"][-500:]
        with open(STATE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(s, f)
        os.replace(STATE_FILE + ".tmp", STATE_FILE)
    except OSError:
        pass


def text_of(e: dict) -> str:
    what = WORDS.get(e["kind"], e["kind"])
    who = "The host's" if e["service"] == "host" and e["kind"] != "host-disk" else "The host" if e["service"] == "host" \
        else f"Container {e['service']}"
    if e["event"] == "recovered":
        return f"{who} is working again ({what.split(' (')[0]} for {e.get('minutes', 0)} min)"
    return f"{who} {what}" + (" (still)" if e["event"] == "reminder" else "")


def _deliver(s: dict) -> int:
    """The waiting events to the API (it makes the notifications and sends the webhooks); kept while it is down."""
    if not s["outbox"]:
        return 0
    import urllib.request
    url = os.environ.get("EAX_API_URL", "http://api:8000") + "/api/v1/internal/container-alerts"
    req = urllib.request.Request(url, data=json.dumps({"events": s["outbox"]}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Ops-Token": hooks.get("token", "")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - this installation's API
            r.read()
    except Exception:  # noqa: BLE001 - the API is down (perhaps the very alert): tried again next minute
        return 0
    n, s["outbox"] = len(s["outbox"]), []
    return n


def _auto_restart(s: dict, events: list[dict], now: float) -> None:
    """A container restarted on its own when the setting names it (off by default), at most N times an hour."""
    wanted = {x.strip() for x in _cfg("EAX_ALERT_AUTO_RESTART", "").split(",") if x.strip()}
    most = _int("EAX_ALERT_AUTO_RESTART_MAX", 3)
    for e in events:
        if e["event"] == "recovered" or e["service"] not in wanted or e["kind"] not in ("stopped", "unhealthy"):
            continue
        done = [t for t in s["restarts"].get(e["service"], []) if now - t < 3600]
        if len(done) >= most:
            s["history"].append({"at": now, "event": "restart-skipped", "service": e["service"],
                                 "detail": f"restarted {len(done)} times in the last hour already"})
            continue
        try:
            hooks["restart_service"](e["service"])
            done.append(now)
            s["history"].append({"at": now, "event": "restarted", "service": e["service"], "detail": "restarted on its own"})
            s["outbox"].append({"event": "restarted", "service": e["service"], "kind": e["kind"], "key": e["key"],
                                "detail": "restarted on its own (EAX_ALERT_AUTO_RESTART)", "at": now})
        except Exception as exc:  # noqa: BLE001
            s["history"].append({"at": now, "event": "restart-failed", "service": e["service"], "detail": str(exc)[:200]})
        s["restarts"][e["service"]] = done


def sustained(history: list[dict], thresholds_: dict, minutes: int) -> dict:
    """The host is red for alerts only when a level stayed at or above its alert line for the last `minutes` samples
    (one a minute): a busy minute (a start-up, a self-test, a backup) is not an alert (owner, 13 Nov 2026: "The host CPU
    is high" while starting, "all containers are ok")."""
    out = {}
    for k in ("cpu", "memory", "disk"):
        last = [p.get(k) for p in history[-minutes:]] if minutes > 0 else []
        out[k] = "red" if len(last) >= max(1, minutes) and all(v is not None and v >= thresholds_[k]["alert"] for v in last) \
            else "green"
    return out


def starting(rows: list[dict]) -> bool:
    """EA Explorer is still starting (a container being made, restarting or with its health check starting)."""
    return any(r.get("state") in ("created", "restarting") or r.get("health") == "starting" for r in rows)


def watch_once(now: float | None = None) -> list[dict]:
    """One look: every container and the host; alerts, reminders and recoveries queued and sent."""
    now = now or time.time()
    if _cfg("EAX_ALERTS", "on").lower() in ("off", "false", "0", "no"):
        return []
    if hooks.get("restarting", lambda: False)() or hooks.get("maintenance", lambda: None)():
        return []       # a restart, update or restore stops containers on purpose
    with _lock:
        s = _load()
        rows = hooks["stats"](fresh=True).get("containers") or []
        try:
            host(sample=True)                                     # the sample of this minute, into the history
            levels = {} if starting(rows) else sustained(_history(), thresholds(), _int("EAX_ALERT_HOST_MINUTES", 10))
        except Exception:  # noqa: BLE001 - the host's numbers are a nicety; containers are still watched
            levels = {}
        problems = assess(rows, levels, s["seen_restarts"])
        for svc in list(s["tests"]):                              # the self-test's pretend stop: one look, then gone
            problems.append({"key": f"{svc}:test", "service": svc, "kind": "stopped", "detail": "a test alert (self-test)"})
            s["tests"].pop(svc)
        events = step(problems, s["open"], now, _int("EAX_ALERT_REPEAT_MINUTES", 60))
        for e in events:
            e["at"], e["text"] = now, text_of(e)
            s["history"].append({k: e.get(k) for k in ("at", "event", "service", "kind", "detail", "text")})
            s["outbox"].append(e)
        _auto_restart(s, events, now)
        _deliver(s)
        _save(s)
        return events


def alerts() -> dict:
    s = _load()
    opened = [{**o, "text": text_of({**o, "event": "alert"})} for o in s["open"].values()]
    return {"open": sorted(opened, key=lambda o: o["since"]), "history": s["history"][-200:][::-1],
            "waiting": len(s["outbox"]), "repeat_minutes": _int("EAX_ALERT_REPEAT_MINUTES", 60),
            "auto_restart": _cfg("EAX_ALERT_AUTO_RESTART", ""), "on": _cfg("EAX_ALERTS", "on")}


def test_alert(service: str) -> dict:
    with _lock:
        s = _load()
        s["tests"][service or "api"] = time.time()
        _save(s)
    return {"queued": True}


def loop(pause: int = 60) -> None:
    time.sleep(90)                       # let the stack come up first
    while True:
        try:
            watch_once()
        except Exception as exc:  # noqa: BLE001 - one look failing never stops the watcher
            print(f"ops: container watcher: {exc}", flush=True)
        time.sleep(pause)
