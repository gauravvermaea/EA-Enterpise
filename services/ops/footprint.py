"""How much each container takes (R2.22; owner, 13 Nov 2026: "measure only for now"): image size, the container's own
disk, its volumes, memory and CPU now (at rest, or under the self-test's load when measured during a run), and how long
it took to start (from started to healthy). Each measurement is kept in work/footprint/<when>.json and .md, so a later
one is shown beside the one before (before and after a change). Read only.

  GET  /footprint            the newest measurement and the one before
  POST /footprint {label}    measure now (eax footprint [label])
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

WORK = Path(os.environ.get("EAX_WORK_MOUNT", "/eax-work"))
hooks: dict = {}       # set by ops.py: stats, docker


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


def history() -> list[dict]:
    d = WORK / "footprint"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
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
    return {"latest": h[-1] if h else None, "before": h[-2] if len(h) > 1 else None, "count": len(h)}


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
    m = measure(" ".join(a for a in args if not a.startswith("--")))
    print(to_markdown(m, previous(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "~")))
    print(f"Kept in work/footprint ({time.strftime('%H:%M')}): latest.md, and each measurement by its time.")
    return 0
