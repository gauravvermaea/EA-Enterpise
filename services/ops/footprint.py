"""How much each container takes (R2.22; owner, 13 Nov 2026: "measure only for now"): image size, the container's own
disk, its volumes, memory and CPU now (at rest, or under the self-test's load when measured during a run), and how long
it took to start (from started to healthy). Each measurement is kept in work/footprint/<when>.json and .md, so a later
one is shown beside the one before (before and after a change). Read only.

  GET  /footprint            the newest measurement and the one before, and the newest memory watch
  POST /footprint {label}    measure now (eax footprint [label])

Memory over time (Release 3.5, R3.5-M1; owner, 14 Nov 2026: "Lets measure first", "In an ideal world I want laptop to
run at around 10 GB", "No functionality loss or paging should happen"): a **watch** samples every container's memory
(one `docker stats` call, nothing heavier) every few seconds and keeps, per container, the lowest, the average and the
peak, the whole installation's peak beside the guide (EAX_MEMORY_TARGET_MB, 10 GB unless set; a guide, not a limit:
"10 GB is not a hard limit, I am open to it being more"), and **paging**: the
memory the Docker host has, how little was left at worst and the swap in use (from the host's /proc/meminfo, which in
the operations helper is the Docker host's, Docker Desktop's VM on a laptop). `eax footprint --watch [minutes] [label]`
watches for a while; every self-test run is watched on its own from start to end (testruns.py), its table kept in the
run's folder (memory.md) and in work/footprint.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

WORK = Path(os.environ.get("EAX_WORK_MOUNT", "/eax-work"))
hooks: dict = {}       # set by ops.py: stats, docker, project
EVERY = 15             # seconds between memory samples in a watch
MEMINFO = "/proc/meminfo"


def target_mb() -> float:
    """The memory the whole installation should be near (owner: "In an ideal world I want laptop to run at around 10 GB";
    "10 GB is not a hard limit, I am open to it being more"): a guide to compare with, never a limit."""
    try:
        return float(os.environ.get("EAX_MEMORY_TARGET_MB") or 10240)
    except ValueError:
        return 10240.0


def _mb(b) -> float | None:
    return None if b is None else round(float(b) / 1e6, 1)


def _start_seconds(d: dict) -> float | None:
    """Seconds from started to its first healthy check (None without a health check or before it is healthy)."""
    st = d.get("State") or {}
    log = (st.get("Health") or {}).get("Log") or []
    started = st.get("StartedAt") or ""
    ok = [h.get("End") for h in log if h.get("ExitCode") == 0 and h.get("End")]
    if not started or not ok:
        return None
    try:
        t0 = datetime.fromisoformat(re.sub(r"\.(\d{6})\d*", r".\1", started).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(re.sub(r"\.(\d{6})\d*", r".\1", min(ok)).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((t1 - t0).total_seconds(), 1) if t1 >= t0 else None


def measure(label: str = "") -> dict:
    """One measurement of every container of the installation; kept in work/footprint."""
    s = hooks["stats"](fresh=True)
    images: dict[str, int] = {}
    starts: dict[str, float | None] = {}
    ids = [c["id"] for c in s["containers"]]
    try:
        for d in json.loads(hooks["docker"]("inspect", *ids, timeout=60) or "[]") if ids else []:
            starts[d["Id"][:12]] = _start_seconds(d)
            img = d.get("Image") or ""
            if img and img not in images:
                images[img] = int(json.loads(hooks["docker"]("image", "inspect", img, timeout=30) or "[{}]")[0].get("Size") or 0)
            starts[d["Id"][:12] + ":image"] = images.get(img)
    except Exception as exc:  # noqa: BLE001 - measured as far as Docker answered
        s.setdefault("problems", []).append(f"docker inspect: {exc}")
    rows = []
    for c in s["containers"]:
        k = c["id"][:12]
        rows.append({"container": c.get("key") or c["service"], "state": c["state"], "image": c.get("image"),
                     "image_mb": _mb(starts.get(k + ":image")), "own_disk_mb": _mb(c.get("layer_bytes")),
                     "volumes_mb": _mb(c.get("volume_bytes")), "memory_mb": _mb(c.get("memory_bytes")),
                     "memory_limit_mb": _mb(c.get("memory_limit_bytes")), "cpu_percent": c.get("cpu_percent"),
                     "start_seconds": starts.get(k), "restarts": c.get("restarts")})
    m = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "label": str(label or "")[:60], "containers": rows,
         "totals": {k: round(sum(r[k] or 0 for r in rows), 1) for k in ("image_mb", "own_disk_mb", "volumes_mb", "memory_mb")},
         "problems": s.get("problems", [])}
    d = WORK / "footprint"
    d.mkdir(parents=True, exist_ok=True)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (d / f"{name}.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    (d / f"{name}.md").write_text(to_markdown(m, previous(name)), encoding="utf-8")
    (d / "latest.md").write_text(to_markdown(m, previous(name)), encoding="utf-8")
    return m


# ---------------------------------------------------------------- memory over time (R3.5-M1)
def service_of(name: str, project: str) -> str:
    """A container's name as its service: eaexplorer-api-1 -> api, eaexplorer-testrunner -> testrunner."""
    n = name[len(project) + 1:] if project and name.startswith(project + "-") else name
    return re.sub(r"-\d+$", "", n) or name


def host_memory(path: str = MEMINFO) -> dict:
    """The Docker host's memory in MB: total, available, swap total and swap in use (paging when it grows)."""
    vals: dict[str, float] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition(":")
            if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                vals[k] = float(v.split()[0]) / 1024           # kB -> MB
    except (OSError, ValueError, IndexError):
        return {}
    if "MemTotal" not in vals:
        return {}
    return {"total_mb": round(vals["MemTotal"], 1), "available_mb": round(vals.get("MemAvailable", 0), 1),
            "swap_total_mb": round(vals.get("SwapTotal", 0), 1),
            "swap_used_mb": round(vals.get("SwapTotal", 0) - vals.get("SwapFree", 0), 1)}


def sample(project: str | None = None) -> dict:
    """One reading: {at, containers: {service: MB}, host: {...}}; only this installation's containers (its name prefix,
    the test runner included)."""
    from_ops = hooks.get("_size")
    project = project if project is not None else (hooks["project"]() if hooks.get("project") else "")
    out = hooks["docker"]("stats", "--no-stream", "--format", "{{json .}}", timeout=60)
    mem: dict[str, float] = {}
    for line in (out or "").splitlines():
        try:
            st = json.loads(line)
        except ValueError:
            continue
        name = st.get("Name") or ""
        if project and not name.startswith(project + "-"):
            continue
        used = (st.get("MemUsage") or "").partition("/")[0]
        b = from_ops(used) if from_ops else 0
        key = service_of(name, project)
        mem[key] = round(mem.get(key, 0) + b / 1e6, 1)
    return {"at": time.time(), "containers": mem, "host": host_memory()}


class Recorder:
    """The samples of one watch, summed up as they come: per container lowest, average and peak; the installation's
    total peak and when; the host's least available memory and most swap in use."""

    def __init__(self, label: str = ""):
        self.label, self.started, self.samples = label, time.time(), 0
        self.rows: dict[str, dict] = {}
        self.total_peak, self.total_peak_at, self.total_sum = 0.0, 0.0, 0.0
        self.host: dict = {}

    def add(self, s: dict) -> None:
        self.samples += 1
        total = 0.0
        for k, mb in s["containers"].items():
            r = self.rows.setdefault(k, {"min": mb, "max": mb, "sum": 0.0, "n": 0, "max_at": s["at"]})
            r["min"], r["sum"], r["n"] = min(r["min"], mb), r["sum"] + mb, r["n"] + 1
            if mb >= r["max"]:
                r["max"], r["max_at"] = mb, s["at"]
            total += mb
        self.total_sum += total
        if total >= self.total_peak:
            self.total_peak, self.total_peak_at = round(total, 1), s["at"]
        h = s.get("host") or {}
        if h:
            m = self.host
            m["total_mb"] = h["total_mb"]
            m["least_available_mb"] = min(m.get("least_available_mb", h["available_mb"]), h["available_mb"])
            m["swap_total_mb"] = h["swap_total_mb"]
            m["swap_used_at_start_mb"] = m.get("swap_used_at_start_mb", h["swap_used_mb"])
            m["most_swap_used_mb"] = max(m.get("most_swap_used_mb", h["swap_used_mb"]), h["swap_used_mb"])

    def result(self) -> dict:
        when = lambda t: datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds")  # noqa: E731
        rows = [{"container": k, "lowest_mb": round(r["min"], 1), "average_mb": round(r["sum"] / r["n"], 1),
                 "peak_mb": round(r["max"], 1), "peak_at": when(r["max_at"])}
                for k, r in sorted(self.rows.items(), key=lambda kv: -kv[1]["max"])]
        t = target_mb()
        h = dict(self.host)
        if h:
            h["paged"] = h.get("most_swap_used_mb", 0) > h.get("swap_used_at_start_mb", 0) + 64
        return {"kind": "memory", "label": self.label[:80], "at": when(self.started), "until": when(time.time()),
                "minutes": round((time.time() - self.started) / 60, 1), "samples": self.samples, "containers": rows,
                "total_peak_mb": self.total_peak, "total_peak_at": when(self.total_peak_at) if self.samples else None,
                "total_average_mb": round(self.total_sum / self.samples, 1) if self.samples else 0,
                "target_mb": t, "within_target": self.total_peak <= t, "host": h}


def memory_markdown(m: dict) -> str:
    """The table people read: each container's lowest, average and peak, the total against the target, and paging."""
    gb = lambda mb: f"{mb / 1024:.1f} GB"  # noqa: E731
    t, h = m["target_mb"], m.get("host") or {}
    lines = [f"# EA Explorer memory, {m['at']} to {m['until']}" + (f" ({m['label']})" if m.get("label") else ""), "",
             f"Watched {m['minutes']} minutes, {m['samples']} samples (`eax footprint --watch`, R3.5-M1).", "",
             f"**Peak of the whole installation: {gb(m['total_peak_mb'])}** at {m['total_peak_at']} "
             f"({'within' if m['within_target'] else 'above'} the guide of {gb(t)}, not a limit); average {gb(m['total_average_mb'])}.", ""]
    if h:
        lines += [f"Docker host: {gb(h['total_mb'])}; the least left at any moment {gb(h['least_available_mb'])}; swap in use "
                  f"{h['swap_used_at_start_mb']:.0f} MB at the start, at most {h['most_swap_used_mb']:.0f} MB"
                  f" of {h['swap_total_mb']:.0f} MB: " + ("**it paged**" if h.get("paged") else "no paging") + ".", ""]
    lines += ["| Container | Lowest MB | Average MB | Peak MB | Peak at |", "|---|---:|---:|---:|---|"]
    for r in m["containers"]:
        lines.append(f"| {r['container']} | {r['lowest_mb']} | {r['average_mb']} | {r['peak_mb']} | {r['peak_at'][11:19]} |")
    return "\n".join(lines + [""])


def save_memory(m: dict, folder: Path | None = None) -> Path:
    """Kept in work/footprint (<time>-memory.json and .md, latest-memory.md) and, for a self-test, its run's folder."""
    d = WORK / "footprint"
    d.mkdir(parents=True, exist_ok=True)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-memory"
    md = memory_markdown(m)
    (d / f"{name}.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    (d / f"{name}.md").write_text(md, encoding="utf-8")
    (d / "latest-memory.md").write_text(md, encoding="utf-8")
    if folder is not None:
        try:
            (folder / "memory.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
            (folder / "memory.md").write_text(md, encoding="utf-8")
        except OSError:
            pass
    return d / f"{name}.md"


def watch(label: str = "", seconds: float = 600, until=None, every: float = EVERY, say=None, folder: Path | None = None,
          stop=None) -> dict:
    """Samples until `seconds` have passed, or `until()` says so, or the event `stop` is set; then keeps the result."""
    rec = Recorder(label)
    end = time.time() + seconds
    last_said = 0.0
    while True:
        try:
            rec.add(sample())
        except Exception as exc:  # noqa: BLE001 - a missed sample is skipped, the watch goes on
            if say:
                say(f"(a sample was missed: {exc})")
        if say and time.time() - last_said >= 60:
            last_said = time.time()
            r = rec.result()
            say(f"{time.strftime('%H:%M')} {r['samples']} samples: peak so far {r['total_peak_mb'] / 1024:.1f} GB (guide {r['target_mb'] / 1024:.0f} GB)")
        if (until and until()) or (stop is not None and stop.is_set()) or (not until and stop is None and time.time() >= end):
            break
        if stop is not None:
            if stop.wait(every):
                break
        else:
            time.sleep(every)
    m = rec.result()
    save_memory(m, folder)
    return m


def watch_in_background(label: str, folder: Path):
    """For a self-test run (testruns.run_sequence): samples on a thread until the returned event is set."""
    import threading
    stop = threading.Event()
    threading.Thread(target=watch, kwargs={"label": label, "seconds": 0, "folder": folder, "stop": stop},
                     daemon=True, name="selftest-memory").start()
    return stop


def latest_memory() -> dict | None:
    d = WORK / "footprint"
    files = sorted(d.glob("*-memory.json")) if d.is_dir() else []
    for f in reversed(files):
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def history() -> list[dict]:
    d = WORK / "footprint"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        if f.stem.endswith("-memory"):
            continue
        try:
            out.append({"name": f.stem, **json.loads(f.read_text(encoding="utf-8"))})
        except (OSError, ValueError):
            continue
    return out


def previous(before: str) -> dict | None:
    older = [h for h in history() if h["name"] < before]
    return older[-1] if older else None


def latest() -> dict:
    h = history()
    return {"latest": h[-1] if h else None, "before": h[-2] if len(h) > 1 else None, "count": len(h),
            "memory": latest_memory(), "target_mb": target_mb()}


def to_markdown(m: dict, before: dict | None = None) -> str:
    """The table people read (work/footprint/latest.md): each container, and the change since the one before."""
    was = {r["container"]: r for r in (before or {}).get("containers", [])}

    def cell(r, k):
        v = r.get(k)
        if v is None:
            return "-"
        b = (was.get(r["container"]) or {}).get(k)
        return f"{v}" + (f" ({v - b:+.1f})" if isinstance(b, int | float) and isinstance(v, int | float) and b != v else "")
    lines = [f"# EA Explorer footprint, {m['at']}" + (f" ({m['label']})" if m.get("label") else ""), "",
             "Measured by `eax footprint` (R2.22). In brackets: the change since " +
             (f"{before['at']}" + (f" ({before['label']})" if before.get("label") else "") if before else "nothing (the first)") + ".", "",
             "| Container | Image MB | Own disk MB | Volumes MB | Memory MB | CPU % | Start s | Restarts |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in m["containers"]:
        lines.append(f"| {r['container']} | {cell(r, 'image_mb')} | {cell(r, 'own_disk_mb')} | {cell(r, 'volumes_mb')} | "
                     f"{cell(r, 'memory_mb')} | {cell(r, 'cpu_percent')} | {cell(r, 'start_seconds')} | {r.get('restarts') or 0} |")
    t = m["totals"]
    lines += [f"| **All** | {t['image_mb']} | {t['own_disk_mb']} | {t['volumes_mb']} | {t['memory_mb']} | | | |", ""]
    if m.get("problems"):
        lines += ["Not measured: " + "; ".join(m["problems"]), ""]
    return "\n".join(lines)


def cli(args: list[str]) -> int:
    if "--watch" in args:                  # eax footprint --watch [minutes] [label]
        i = args.index("--watch")
        rest = [a for a in args[:i] + args[i + 1:] if not a.startswith("--")]
        minutes = float(rest.pop(0)) if rest and re.fullmatch(r"\d+(\.\d+)?", rest[0]) else 10.0
        print(f"Watching every container's memory for {minutes:g} minutes, every {EVERY} seconds (Ctrl+C stops early)...", flush=True)
        try:
            m = watch(" ".join(rest), seconds=minutes * 60, say=lambda t: print(t, flush=True))
        except KeyboardInterrupt:
            return 130
        print(memory_markdown(m))
        print("Kept in work/footprint: latest-memory.md, and each watch by its time.")
        return 0
    m = measure(" ".join(a for a in args if not a.startswith("--")))
    print(to_markdown(m, previous(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "~")))
    print(f"Kept in work/footprint ({time.strftime('%H:%M')}): latest.md, and each measurement by its time.")
    return 0
