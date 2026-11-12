"""Updates through the operations helper (phase 36, D417, D511): the helper's side of moving to a newer release.

The helper has no internet (it is only on the internal networks), so everything that reads the repository or changes the
installation runs in a short-lived **updater** container it starts from its own image (Docker CLI, Compose, git,
Python), on the default network (the internet) and the installation's backend network (the helper and the API), with the
Docker socket and the installation folder mounted at the same path as on the host:
  listing a channel's versions   eaxcli/releases.py list ...           (--rm, a few seconds)
  an update, a retry, a rollback eaxcli/updater.py run|retry|rollback  (detached; survives the helper being rebuilt)
The updater is not part of the Compose project, so `docker compose up --remove-orphans` never stops it.

  GET  /updates                  settings, the installed version, the update running or waiting, the history, the
                                 schedule, failed versions, whether an updater runs
  GET  /updates/versions?channel=prod|rc|latest   what that channel offers above the installed version, with notes
  POST /updates/settings         {git_url, rc, latest, by}: written to the config file (a dated copy first)
  POST /updates/start            {channel, to, at, by}: now, or at a time (work/updates/scheduled.json)
  POST /updates/retry            {by}    POST /updates/rollback {by}    POST /updates/schedule/cancel {by}
A thread starts a scheduled update when its time comes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime

WORK = os.environ.get("EAX_WORK_MOUNT", "/eax-work")
UPD = os.path.join(WORK, "updates")
REPO = os.environ.get("EAX_REPO_MOUNT", "/eax-repo")
sys.path.insert(0, REPO)                 # eaxcli (mounted read-only): the channels, versions and plan
try:
    from eaxcli import releases as R  # noqa: E402
except Exception:  # noqa: BLE001 - an older compose file without the eaxcli mount: updates say so
    R = None

SETTINGS = {"git_url": ("EAX_UPDATE_GIT_URL", "https://github.com/gauravvermaea/EA-Enterpise"), "rc": ("EAX_UPDATE_RC", "off"), "latest": ("EAX_UPDATE_LATEST", "off")}
ON = {"on", "true", "1", "yes"}
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
hooks: dict = {}                         # set by ops.py: read_config, write_config, copy_config, docker


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(name: str, default=None):
    try:
        with open(os.path.join(UPD, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    os.makedirs(os.path.dirname(os.path.join(UPD, name)), exist_ok=True)
    tmp = os.path.join(UPD, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, os.path.join(UPD, name))


# ---------------------------------------------------------------- settings (the config file)
def settings() -> dict:
    lines = hooks["read_config"]()
    vals = {}
    for line in lines:
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=(.*)$", line)
        if m:
            vals[m.group(1)] = m.group(2).strip().strip("'\"")
    out = {k: vals.get(env, d) or d for k, (env, d) in SETTINGS.items()}
    return {"git_url": out["git_url"], "rc": out["rc"].lower() in ON, "latest": out["latest"].lower() in ON}


def save_settings(body: dict, by: str) -> dict:
    url = str(body.get("git_url") or "").strip()
    if url and not re.match(r"^(https?://|ssh://|git@|git://|file://|/)", url):
        raise ValueError("The repository link must start with https:// (a public git repository).")
    hooks["copy_config"](by, "update-settings")
    lines = hooks["read_config"]()
    want = {"EAX_UPDATE_GIT_URL": url, "EAX_UPDATE_RC": "on" if body.get("rc") else "off",
            "EAX_UPDATE_LATEST": "on" if body.get("latest") else "off"}
    for key, value in want.items():
        rx = re.compile(rf"^\s*{key}\s*=")
        if any(rx.match(ln) for ln in lines):
            lines = [f"{key}={value}" if rx.match(ln) else ln for ln in lines]
        else:
            if not any(ln.startswith("# ---- Updates (D417)") for ln in lines):
                lines += ["", "# ---- Updates (D417): the repository link and the channels offered (System admin > Updates)"]
            lines.append(f"{key}={value}")
    hooks["write_config"](lines)
    _cache.clear()
    return settings()


def channels() -> dict:
    s = settings()
    return {k: {"label": v["label"], "branch": v["branch"], "about": v["about"],
                "enabled": k == "prod" or bool(s.get(k))} for k, v in (R.CHANNELS if R else {}).items()}


# ---------------------------------------------------------------- the updater container
def _own_container() -> dict:
    """This helper's own container, inspected: by HOSTNAME (its id), or else by its Compose service label (a hostname set
    in the compose file, or HOSTNAME not passed through)."""
    cid = os.environ.get("HOSTNAME", "")
    try:
        if cid:
            return json.loads(hooks["docker"]("inspect", cid))[0]
    except Exception:  # noqa: BLE001 - not a container id: look it up by its label below
        pass
    ids = hooks["docker"]("ps", "-q", "--filter", "label=com.docker.compose.service=ops").split()
    if not ids:
        raise RuntimeError("The operations helper cannot find its own container (HOSTNAME is not its id and no running "
                           "container has the label com.docker.compose.service=ops).")
    return json.loads(hooks["docker"]("inspect", ids[0]))[0]


INSIDE = "/eax-install"


def host_path(path: str) -> str:
    """A host path as Docker reported it, tidied: forward slashes, no trailing one (C:\\Users\\x -> C:/Users/x)."""
    return (path or "").replace("\\", "/").rstrip("/")


def is_windows(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:/", host_path(path)))


def inside(install: str) -> str:
    """Where the installation folder is mounted in the helper's short-lived containers (the Command centre, the updater,
    the test runner's build): the same path on Linux and macOS; /eax-install when the host is Windows, as a container's
    working directory must be a Linux path (owner, 12 Nov 2026, R2.49: "the working directory 'C:/Users/gaura/Github/
    EA-Enterpise' is invalid"; then /run/desktop/mnt/host/c/... mounted an empty folder: "No module named 'eaxcli'").
    Docker Desktop takes the Windows path itself as a mount's source."""
    return INSIDE if is_windows(install) else install


def mount_args(me: dict) -> list[str]:
    """-v <installation>:<inside> -w <inside> for a short-lived container."""
    return ["-v", f"{me['install']}:{me['inside']}", "-w", me["inside"]]


WINDOWS_REFUSED = ("On Windows this runs from PowerShell in the installation folder, not from the web: {cmd}. (Compose in a "
                   "container would give the containers Linux paths for your Windows folders, R2.49.)")


def install_folder(d: dict) -> str:
    """The installation folder on the host, from the helper's container (R2.0.1, R2.8): the folder holding the files
    docker-compose.yml mounts into it (the compose file itself, deploy/, eaxcli/, work/), else the Compose label
    project.working_dir; a Windows one as C:/Users/... (host_path; inside() says where containers see it). Empty when none
    is there."""
    mounts = {m.get("Destination", ""): m.get("Source", "") for m in d.get("Mounts") or []}
    up = {f"{REPO}/docker-compose.yml": 1, f"{REPO}/deploy": 1, f"{REPO}/eaxcli": 1, "/eax-work": 1,
          f"{REPO}/services/api/version.toml": 3}
    for dest, levels in up.items():
        src = (mounts.get(dest) or "").replace("\\", "/").rstrip("/")
        if src:
            for _ in range(levels):
                src = os.path.dirname(src)
            if src:
                return host_path(src)
    wd = ((d.get("Config") or {}).get("Labels") or {}).get("com.docker.compose.project.working_dir", "")
    return host_path(wd)


def _me() -> dict:
    """This helper's container: the Compose project, its image and the installation folder on the host."""
    d = _own_container()
    project = (d.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project", "")
    install = install_folder(d)
    if not install:
        seen = ", ".join(sorted(m.get("Destination", "") for m in d.get("Mounts") or [])) or "none"
        raise RuntimeError("The installation folder is not known: the operations helper has none of the installation's "
                           f"folders mounted (it has: {seen}). Run eax up (or eax clean-restart) so it is made again from "
                           "docker-compose.yml.")
    return {"project": project, "image": d.get("Config", {}).get("Image") or d.get("Image"), "install": install,
            "inside": inside(install), "windows": is_windows(install)}


def updater_running() -> dict | None:
    try:
        me = _me()
        out = hooks["docker"]("ps", "-a", "--filter", f"label=eax.updater={me['project']}", "--format", "{{json .}}")
    except Exception:  # noqa: BLE001
        return None
    rows = [json.loads(x) for x in out.splitlines() if x.strip()]
    run = [r for r in rows if r.get("State") == "running"]
    return run[0] if run else None


def _shell(install: str, run_id: str, script: str, args: list[str]) -> str:
    q = " ".join("'" + a.replace("'", "'\\''") + "'" for a in args)
    if script == "updater":
        return (f"git config --global --add safe.directory '*' && cd '{install}' && "
                f"mkdir -p work/updates/{run_id}/runner && rm -rf work/updates/{run_id}/runner/eaxcli && "
                f"cp -r eaxcli work/updates/{run_id}/runner/ && "
                f"exec python3 work/updates/{run_id}/runner/eaxcli/updater.py {q}")
    return f"git config --global --add safe.directory '*' && cd '{install}' && exec python3 eaxcli/releases.py {q}"


def _start_container(run_id: str, args: list[str]) -> str:
    me = _me()
    if updater_running():
        raise RuntimeError("An updater is already running.")
    if me["windows"]:
        raise RuntimeError(WINDOWS_REFUSED.format(cmd=".\\eax update"))
    name = f"{me['project']}-updater-{run_id}"[:60]
    env = ["-e", f"COMPOSE_PROJECT_NAME={me['project']}", "-e", "EAX_OPS_URL=http://ops:8090",
           "-e", f"EAX_OPS_TOKEN={os.environ.get('EAX_OPS_TOKEN', '')}", "-e", "EAX_API_URL=http://api:8000"]
    hooks["docker"]("create", "--name", name, "--label", f"eax.updater={me['project']}", "--label", f"eax.update={run_id}",
                    "-v", "/var/run/docker.sock:/var/run/docker.sock", *mount_args(me),
                    *env, "--entrypoint", "sh", me["image"], "-c", _shell(me["inside"], run_id, "updater", args))
    try:
        hooks["docker"]("network", "connect", f"{me['project']}_backend", name)
    except Exception:  # noqa: BLE001 - started anyway; it says when it cannot reach the helper
        pass
    hooks["docker"]("start", name)
    return name


def _list_in_container(channel: str, installed: dict) -> dict:
    me = _me()
    s = settings()
    args = ["list", s["git_url"], channel, installed.get("version") or "0.0.0", installed.get("commit") or "",
            "--cache", "work/updates/cache.git"]
    r = subprocess.run(["docker", "run", "--rm", *mount_args(me),
                        "--entrypoint", "sh", me["image"], "-c", _shell(me["inside"], "", "releases", args)],
                       capture_output=True, text=True, timeout=180)
    last = (r.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return {"error": (r.stderr or r.stdout).strip()[-300:] or "the version list could not be read"}


# ---------------------------------------------------------------- what the screens and eax ask
def installed() -> dict:
    got = _read("installed.json")
    if got:
        return got
    v = os.environ.get("EAX_VERSION", "")
    try:
        with open(os.path.join(REPO, "services", "api", "version.toml"), encoding="utf-8") as f:
            m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
            v = m.group(1) if m else v
    except OSError:
        pass
    return {"version": v, "channel": "prod", "commit": "", "ref": f"v{v}" if v and v != "dev" else "", "at": ""}


def _log_tail(uid: str, n: int = 200) -> list[str]:
    try:
        with open(os.path.join(UPD, uid, "update.log"), encoding="utf-8") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def status(tail: int = 200) -> dict:
    cur = _read("current.json")
    if cur:
        cur["log"] = _log_tail(cur.get("id", ""), tail)
    hist = sorted(_read("history.json", []) or [], key=lambda h: h.get("started") or "", reverse=True)
    return {"available": R is not None, "settings": settings(), "channels": channels(), "installed": installed(),
            "current": cur, "history": hist, "scheduled": _read("scheduled.json"),
            "failed_versions": _read("failed-versions.json", []) or [], "updater": updater_running()}


def versions(channel: str) -> dict:
    if R is None:
        raise RuntimeError("Updates need the eaxcli folder mounted in the operations helper: run eax clean-restart once.")
    ch = channels()
    if channel not in ch:
        raise ValueError("Choose a channel: prod, rc or latest.")
    if not ch[channel]["enabled"]:
        raise PermissionError(f"The {ch[channel]['label']} channel is off: a Super Admin or IT Admin enables it first.")
    if not settings()["git_url"]:
        raise ValueError("Set the repository link first (System admin > Updates).")
    inst = installed()
    key = f"{channel}:{inst.get('version')}:{inst.get('commit')}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    out = _list_in_container(channel, inst)
    failed = set(_read("failed-versions.json", []) or [])
    for v in out.get("versions") or []:
        v["failed_before"] = v.get("version") in failed
    out.update(channel=channel, installed=inst)
    if not out.get("error"):
        _cache[key] = (time.time(), out)
    return out


def start(body: dict) -> dict:
    """An update now, or at a time (body.at, ISO date and time)."""
    with _lock:
        by = str(body.get("by") or "")
        channel = str(body.get("channel") or "prod")
        cur = _read("current.json")
        if cur and cur.get("status") in ("running", "failed", "rolling-back"):
            raise RuntimeError(f"Update {cur['id']} is {cur['status']}: finish it first (Retry or Roll back).")
        got = versions(channel)
        if got.get("error"):
            raise RuntimeError(got["error"])
        offered = [R.Version(**{k: v for k, v in x.items() if k in R.Version.__dataclass_fields__}) for x in got["versions"]]
        pick = R.plan(offered, str(body.get("to") or ""))
        at = str(body.get("at") or "").strip()
        if at:
            when = _parse_at(at)
            sched = {"id": uuid.uuid4().hex[:12], "channel": channel, "to": pick.version, "ref": pick.ref,
                     "steps": pick.steps, "at": when, "by": by, "set": _now()}
            _write("scheduled.json", sched)
            return {"scheduled": sched}
        return _launch(channel, pick, by)


def _parse_at(at: str) -> str:
    try:
        if re.match(r"^\d{1,2}:\d{2}$", at):                    # today (or tomorrow) at this time, the helper's clock
            hh, mm = map(int, at.split(":"))
            t = datetime.now(UTC).astimezone()
            when = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if when <= t:
                when = when.fromtimestamp(when.timestamp() + 86400).astimezone()
        else:
            when = datetime.fromisoformat(at.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.astimezone()
    except ValueError as exc:
        raise ValueError("The time must be like 22:00 or 2026-11-12T22:00.") from exc
    if when.timestamp() < time.time() - 60:
        raise ValueError("That time has passed.")
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _launch(channel: str, pick, by: str, run_id: str = "") -> dict:
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:4]
    notes = pick.notes if hasattr(pick, "notes") else ""
    req = {"id": run_id, "by": by, "channel": channel, "to": pick.version, "url": settings()["git_url"],
           "steps": list(pick.steps), "notes": notes, "asked": _now()}
    _write(os.path.join(run_id, "request.json"), req)
    name = _start_container(run_id, ["run", "--id", run_id])
    return {"started": True, "id": run_id, "container": name, "to": pick.version, "steps": list(pick.steps)}


def decide(action: str, by: str) -> dict:
    cur = _read("current.json")
    if action == "retry":
        if not cur or cur.get("status") != "failed":
            raise RuntimeError("No failed update to retry.")
        return {"started": True, "id": cur["id"], "container": _start_container(cur["id"], ["retry", "--id", cur["id"], "--by", by])}
    if action == "rollback":
        uid = cur["id"] if cur else next((h["id"] for h in sorted(_read("history.json", []) or [], key=lambda h: h.get("started") or "",
                                                                    reverse=True) if h.get("kind") == "update" and h.get("status") == "ok"), "")
        if not uid:
            raise RuntimeError("Nothing to roll back.")
        return {"started": True, "id": uid, "container": _start_container(uid, ["rollback", "--id", uid, "--by", by])}
    raise ValueError("retry or rollback")


def cancel_schedule(by: str) -> dict:
    s = _read("scheduled.json")
    if not s:
        raise RuntimeError("No update is scheduled.")
    os.remove(os.path.join(UPD, "scheduled.json"))
    hist = _read("history.json", []) or []
    hist.append({"id": s["id"], "kind": "update", "status": "cancelled", "channel": s["channel"], "to": s["to"],
                 "by": by, "started": s["at"], "finished": _now(), "error": f"Scheduled by {s['by']} for {s['at']}; cancelled by {by}"})
    _write("history.json", hist)
    return {"cancelled": s}


def scheduler_tick(now: float | None = None) -> str:
    """A scheduled update whose time has come starts (D417: the organisation decides when). Returns what happened."""
    s = _read("scheduled.json")
    if not s:
        return ""
    try:
        when = datetime.fromisoformat(s["at"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError):
        return ""
    if when > (now or time.time()):
        return "waiting"
    try:
        os.remove(os.path.join(UPD, "scheduled.json"))
        pick = R.Version(channel=s["channel"], version=s["to"], ref=s["ref"], steps=s["steps"])
        _launch(s["channel"], pick, s["by"], s["id"])
        print(f"ops: the update scheduled for {s['at']} by {s['by']} has started", flush=True)
        return "started"
    except Exception as exc:  # noqa: BLE001 - recorded so the screen shows it
        hist = _read("history.json", []) or []
        hist.append({"id": s.get("id"), "kind": "update", "status": "not-started", "channel": s.get("channel"),
                     "to": s.get("to"), "by": s.get("by"), "started": s.get("at"), "finished": _now(),
                     "error": f"The scheduled update could not start: {exc}"})
        _write("history.json", hist)
        return "not-started"


def scheduler() -> None:
    """Every 30 seconds: scheduler_tick."""
    while True:
        time.sleep(30)
        try:
            scheduler_tick()
        except Exception as exc:  # noqa: BLE001 - never stops the helper
            print(f"ops: update scheduler: {exc}", flush=True)


# ---------------------------------------------------------------- eax update / eax rollback (in this helper)
def _ask(prompt: str, choices: list[str] | None = None) -> str:
    while True:
        a = input(prompt).strip()
        if not choices or a in choices:
            return a
        print(f"  Type one of: {', '.join(choices)}")


def _follow(uid: str) -> int:
    print(f"The update runs in its own container. Following its log (work/updates/{uid}/update.log); Ctrl+C stops "
          "following, not the update. EA Explorer restarts during the update, which may end this window: then check "
          "with eax update --status.", flush=True)
    seen = 0
    while True:
        lines = _log_tail(uid, 100000)
        for line in lines[seen:]:
            print(line, flush=True)
        seen = len(lines)
        cur = _read("current.json")
        if not cur or cur.get("id") != uid or cur.get("status") not in ("running", "rolling-back"):
            if not updater_running():
                h = next((x for x in reversed(_read("history.json", []) or []) if x.get("id") == uid), {})
                st = (cur or {}).get("status") or h.get("status", "")
                print(f"\nResult: {st or 'unknown'}" + (f" - {(cur or h).get('error')}" if (cur or h).get("error") else ""))
                return 0 if st in ("ok", "rolled-back") else 1
        time.sleep(2)


def print_status() -> int:
    st = status(30)
    inst = st["installed"]
    print(f"Installed: {inst.get('version') or 'unknown'} (channel {inst.get('channel')}, commit {str(inst.get('commit'))[:12] or '-'})")
    print(f"Repository: {st['settings']['git_url'] or '(not set: System admin > Updates, or eax update --url <link>)'}")
    print("Channels: " + ", ".join(f"{c['label']} {'on' if c['enabled'] else 'off'}" for c in st["channels"].values()))
    if st["scheduled"]:
        s = st["scheduled"]
        print(f"Scheduled: to {s['to']} at {s['at']} (by {s['by']})")
    if st["current"]:
        c = st["current"]
        print(f"Update {c['id']}: {c['status']} ({c.get('from', {}).get('version')} -> {c.get('to')})" + (f" - {c['error']}" if c.get("error") else ""))
        for line in c["log"][-10:]:
            print("  " + line)
        if c["status"] == "failed":
            print("Choose: eax update --retry, or eax rollback")
    print("History:" if st["history"] else "History: no updates yet")
    for h in st["history"][:15]:
        print(f"  {str(h.get('started') or '')[:16]:<17} {h.get('kind', 'update'):<8} {h.get('status', ''):<12} "
              f"{(h.get('from') or {}).get('version', '') if isinstance(h.get('from'), dict) else ''} -> {h.get('to', '')}  by {h.get('by', '')}")
    return 0


def cli(args: list[str], who: str = "eax command") -> int:
    """eax update [--status] [--retry] [--channel prod|rc|latest] [--to <version>] [--at <time>] [--url <link>] [--yes]
       eax rollback [--yes]"""
    if args and args[0] == "rollback":
        if "--yes" not in args and _ask("Roll back to the version before the last update? Work done since then is lost. Type YES: ") != "YES":
            print("Nothing done.")
            return 1
        try:
            out = decide("rollback", who)
        except RuntimeError as exc:
            print(exc)
            return 1
        return _follow(out["id"])
    opt = lambda name: args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""  # noqa: E731
    if "--status" in args:
        return print_status()
    if "--url" in args:
        s = settings()
        print("Repository link set:", save_settings({**s, "git_url": opt("--url")}, who)["git_url"])
    if "--retry" in args:
        try:
            return _follow(decide("retry", who)["id"])
        except RuntimeError as exc:
            print(exc)
            return 1
    channel, to, at = opt("--channel"), opt("--to"), opt("--at")
    guided = not channel
    if guided:
        print_status()
        ch = channels()
        on = [k for k, c in ch.items() if c["enabled"]]
        print("\nChannels: " + "; ".join(f"{k} = {c['label']}{'' if c['enabled'] else ' (off: enable it in System admin > Updates)'}"
                                         for k, c in ch.items()))
        channel = _ask(f"Channel ({'/'.join(on)}) [prod]: ", on + [""]) or "prod"
    try:
        got = versions(channel)
    except (RuntimeError, ValueError, PermissionError) as exc:
        print(exc)
        return 1
    if got.get("error"):
        print(got["error"])
        return 1
    offered = got.get("versions") or []
    if not offered:
        print(f"Nothing newer on {channel}: {got['installed'].get('version')} is the newest.")
        return 0
    if guided:
        print("\nOffered (oldest first):")
        for i, v in enumerate(offered, 1):
            label = v["version"] + (f"  {v['commit'][:8]} {v.get('title', '')}" if channel == "latest" else "")
            print(f"  {i}. {label}{'   (failed here before)' if v.get('failed_before') else ''}")
        n = _ask(f"Which (1-{len(offered)}) [{len(offered)}]: ", [str(i) for i in range(1, len(offered) + 1)] + [""]) or str(len(offered))
        to = offered[int(n) - 1]["version"] if channel != "latest" else offered[int(n) - 1]["ref"]
    try:
        pick = R.plan([R.Version(**{k: v for k, v in x.items() if k in R.Version.__dataclass_fields__}) for x in offered], to)
    except R.ReleaseError as exc:
        print(exc)
        return 1
    print(f"\nUpdate {got['installed'].get('version')} -> {pick.version} on {channel}: {len(pick.steps)} step(s): {', '.join(pick.steps)}")
    if pick.notes:
        print("\nRelease notes:\n" + "\n".join("  " + ln for ln in pick.notes.splitlines()[:60]))
    print("\nFirst a full backup (code, databases, files, config; pinned). Then the maintenance page while each release is "
          "built and checked. A failed step stops and asks: retry or roll back.")
    if guided and not at:
        at = _ask("Now, or at a time (e.g. 22:00) [now]: ") or ""
    if "--yes" not in args and _ask("Type YES to go ahead: ") != "YES":
        print("Nothing done.")
        return 1
    try:
        out = start({"channel": channel, "to": to or pick.version, "at": at, "by": who})
    except (RuntimeError, ValueError, PermissionError) as exc:
        print(exc)
        return 1
    if out.get("scheduled"):
        s = out["scheduled"]
        print(f"Scheduled: to {s['to']} at {s['at']} (UTC). Signed-in people see a banner beforehand. Cancel in System admin > Updates.")
        return 0
    return _follow(out["id"])
