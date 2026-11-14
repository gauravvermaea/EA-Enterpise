"""Diagrams of EA Explorer's own estate (R2.33; owner, 12 Nov 2026: "Logical and physical diagram with softwares,
components physical network etc of estate"; 13 Nov: build it):

  logical   the components and what each does, and how they call each other (LOGICAL, FLOWS: kept here, beside the code)
  physical  the containers with their images, the Docker networks they are on, the ports published, the volumes and
            folders mounted: from docker-compose.yml (the repository's docs/estate.md and .drawio files, made by
            tools/build_estate_diagrams.py) or from the running containers (System Admin > Estate, through the
            operations helper), so the pictures stay true

Both come as nodes and edges (the screens draw them; exporting.js shape) and as draw.io files (to_drawio).
"""

from __future__ import annotations

import html
import itertools
import re

# ---------------------------------------------------------------- logical: the components and how they call each other
LOGICAL = [  # id, name, what it does, group
    ("people", "People (browser)", "architects, admins and readers in a web browser", "Users"),
    ("assistant", "AI assistant", "a person's own language model, through MCP", "Users"),
    ("eax", "eax command", "starts, stops, backs up, updates and tests the installation", "Users"),
    ("proxy", "Front door (nginx)", "https for everything; the only published ports", "Edge"),
    ("web", "Screens (React)", "the pages people use", "Application"),
    ("api", "API and job runner", "REST API, background jobs, the rules", "Application"),
    ("mcp", "MCP server", "the tools an assistant may use, with the person's own rights", "Application"),
    ("library", "Library service", "reference and enterprise libraries, documentation", "Application"),
    ("views", "Views service", "drawn views and their versions", "Application"),
    ("operations", "Operations service", "housekeeping, retention, usage, deployments, updates (R2.27)", "Application"),
    ("personal", "Personal data service", "each person's notifications, requests, favourites, views, skills (R2.53)", "Application"),
    ("drawio", "draw.io", "the diagram editor", "Application"),
    ("keycloak", "Keycloak", "sign-in and the global roles", "Platform"),
    ("reports", "Reports (Superset)", "dashboards and charts on the report views", "Platform"),
    ("dms", "Documents (Mayan)", "project documents and files", "Platform"),
    ("ops", "Operations helper", "backups, restores, updates, logs, the Command centre, the self-test", "Operations"),
    ("backup", "Backup service", "dumps and restores every database and file set", "Operations"),
    ("testrunner", "Test runner", "the self-test: API, browser, database, security, backups", "Operations"),
    ("db", "PostgreSQL", "one database: the repository and its schemas (tests, operations, archive, personal, library_models, D630)", "Data"),
    ("files", "Files and folders", "documents, imports, exports, backups, logs, persist/", "Data"),
]
FLOWS = [  # from, to, what
    ("people", "proxy", "https"), ("assistant", "proxy", "MCP over https"), ("eax", "ops", "commands"),
    ("proxy", "web", "pages"), ("proxy", "api", "/api"), ("proxy", "mcp", "/mcp"), ("proxy", "keycloak", "/auth"),
    ("proxy", "reports", "/reports"), ("proxy", "dms", "/documents"), ("proxy", "drawio", "/drawio"),
    ("web", "api", "REST"), ("api", "db", "SQL"), ("api", "library", "REST"), ("api", "views", "REST"),
    ("api", "keycloak", "tokens"), ("api", "dms", "REST"), ("api", "ops", "operations"), ("mcp", "db", "SQL"),
    ("reports", "db", "report views"), ("dms", "db", "SQL"), ("keycloak", "db", "SQL"), ("library", "db", "SQL"),
    ("views", "db", "SQL"), ("ops", "backup", "backups"), ("backup", "db", "dump, restore"), ("backup", "files", "archive"),
    ("proxy", "operations", "/api/v1/operations"), ("proxy", "personal", "/api/v1/me/"), ("operations", "db", "SQL"),
    ("personal", "db", "SQL"), ("operations", "ops", "updates, deployments"),
    ("ops", "testrunner", "runs"), ("testrunner", "proxy", "tests as people do"), ("dms", "files", "documents"),
]
GROUP_ORDER = ["Users", "Edge", "Application", "Platform", "Operations", "Data"]
FILL = {"Users": "#fff4e5", "Edge": "#fde2e4", "Application": "#e3f0ff", "Platform": "#e8f5e9", "Operations": "#f3e8ff",
        "Data": "#fff9c4", "frontend": "#e3f0ff", "backend": "#e8f5e9", "terminal": "#f3e8ff", "published": "#fde2e4",
        "volumes": "#fff9c4", "folders": "#fff4e5"}


def logical() -> tuple[list[dict], list[dict]]:
    """The logical diagram: a column per group (users, edge, application, platform, operations, data), a group of more
    than ROWS components in two columns so the columns stay level (R3.4); lines routed by route()."""
    cols: list[tuple[str, list]] = []
    for g in GROUP_ORDER:
        members = [c for c in LOGICAL if c[3] == g]
        for i in range(0, len(members), ROWS):
            cols.append((g, members[i:i + ROWS]))
    depth = max(len(m) for _g, m in cols)
    rows: list[dict] = [{"h": 24, "cells": []}] + [{"h": 62, "cells": []} for _ in range(depth)]
    for ci, (_g, members) in enumerate(cols):
        for ri, (cid, name, what, _gg) in enumerate(members):
            rows[ri + 1]["cells"].append((box(cid, name, what), ci, 1))
    edges = [{"source": a, "target": b, "label": w} for a, b, w in FLOWS]
    nodes, edges = route(rows, len(cols), W_BOX, edges)
    groups = []
    bottom = max(n["y"] + n["h"] for n in nodes)              # every group as tall as the grid: level columns
    for g in GROUP_ORDER:
        idx = [i for i, (gg, _m) in enumerate(cols) if gg == g]
        if not idx:
            continue
        kids = [n for n in nodes if n["id"] in {c[0] for c in LOGICAL if c[3] == g}]
        x0 = min(n["x"] for n in kids) - 10
        x1 = max(n["x"] + n["w"] for n in kids) + 10
        groups.append({"id": f"g_{g}", "label": g, "x": x0, "y": nodes[0]["_row_y"][0], "w": x1 - x0,
                       "h": bottom + 10 - nodes[0]["_row_y"][0], "fill": FILL[g], "container": True,
                       "bold": True, "keepSize": True})
        for n in kids:
            n["parent"] = f"g_{g}"
    for n in nodes:
        n.pop("_row_y", None)
    return groups + nodes, edges


# ---------------------------------------------------------------- the layout: boxes on a grid, lines between them (R3.4)
# Owner, 13 Nov 2026: "estate diagrams are not clean"; his diagrams had lines from box centre to box centre over other
# boxes and their text, no arrowheads, text out of its boxes. Here every box sits in a cell of a grid; between the rows are
# gaps and between the columns channels, and a line only ever runs in those: down (or up) from a port on its box's edge
# into the gap beside it, along the gap to a channel, along the channel to the gap beside its target, along that gap and
# into a port on the target's edge, with an arrowhead. Each line has its own lane in every gap and channel it uses (the
# gaps and channels grow to fit), and each box spreads its lines' ports along its edge, so no two lines lie on one another
# and no line crosses a box it does not join.
ROWS = 4               # components per column in the logical diagram
W_BOX = 200
LANE, PAD, GAP_MIN, CHANNEL_MIN = 7, 9, 20, 26
CHAR = {12: 6.9, 11: 6.3, 10: 5.8, 9: 5.2}      # about how wide a character is at each font size (bold 12 the widest)


def text_width(text: str, size: int = 10) -> float:
    return len(str(text)) * CHAR.get(size, size * 0.58)


def wrap(text: str, width: float, size: int = 10, most: int = 2) -> list[str]:
    """The text in lines that fit width (words kept whole where they can be; a path broken at its separators); the last
    line ends with an ellipsis when the text does not fit in `most` lines (the whole text is the box's tooltip)."""
    per = max(4, int(width // CHAR.get(size, size * 0.58)))
    words = re.split(r"(?<=[ /\\·,])", str(text or "").strip())
    lines, cur = [], ""
    for w in words:
        while len(w) > per:                       # a word longer than a line: cut it
            if cur:
                lines.append(cur.rstrip())
                cur = ""
            lines.append(w[:per])
            w = w[per:]
        if len(cur) + len(w) > per and cur:
            lines.append(cur.rstrip())
            cur = ""
        cur += w
    if cur.strip():
        lines.append(cur.rstrip())
    if len(lines) > most:
        lines = lines[:most]
        lines[-1] = lines[-1][:per - 1].rstrip() + "…"
    return [x.strip() for x in lines] or [""]


def box(ident: str, label: str, sub: str = "", fill: str = "#ffffff", size: int = 12, sub_lines: int = 2, **extra) -> dict:
    inner = W_BOX - 12
    return {"id": ident, "label": label, "sub": sub, "fill": fill, "fontSize": size, "keepSize": True,
            "lines": wrap(label, inner, min(12, size), 2 if not sub else 1),
            "sublines": wrap(sub, inner, 10, sub_lines) if sub else [], "title": f"{label}: {sub}" if sub else label, **extra}


def route(rows: list[dict], C: int, W: int, edges: list[dict], left: int = 20, top: int = 20):
    """Places rows of cells ({h, cells: [(node, column, span)]}) on a grid of C columns W wide and routes each edge
    (source, target) at right angles through the gaps and channels. Returns (nodes with x, y, w, h; edges with points)."""
    pos = {}
    for r, row in enumerate(rows):
        for n, c, span in row.get("cells", []):
            pos[n["id"]] = (r, c, span, n)
    R = len(rows)
    plans = []
    for e in edges:
        if e["source"] not in pos or e["target"] not in pos or e["source"] == e["target"]:
            continue
        ra, ca, sa, _ = pos[e["source"]]
        rb, cb, sb, _ = pos[e["target"]]
        if ra < rb:
            p = {"sa": "bottom", "ga": ra + 1, "sb": "top", "gb": rb}
        elif ra > rb:
            p = {"sa": "top", "ga": ra, "sb": "bottom", "gb": rb + 1}
        else:
            p = {"sa": "bottom", "ga": ra + 1, "sb": "bottom", "gb": rb + 1}
        ta, tb = ca + sa / 2, cb + sb / 2
        p["k"] = None if p["ga"] == p["gb"] else (int(tb) if ta <= tb else int(tb + 0.999))
        plans.append({**p, "e": e})
    gaps: dict[int, list] = {g: [] for g in range(R + 1)}
    chans: dict[int, list] = {k: [] for k in range(C + 1)}
    sides: dict[tuple[str, str], list] = {}
    for i, p in enumerate(plans):
        gaps[p["ga"]].append(i)
        if p["gb"] != p["ga"]:
            gaps[p["gb"]].append(i)
        if p["k"] is not None:
            chans[p["k"]].append(i)
        # the ports facing one gap in one column are spread together: the box above and the box below never put a
        # port at the same place, so their stubs never lie on one another
        for nid, side, end in ((p["e"]["source"], p["sa"], "a"), (p["e"]["target"], p["sb"], "b")):
            r, c, span, _n = pos[nid]
            sides.setdefault((r + 1 if side == "bottom" else r, c, span), []).append((i, end, nid, side))

    def size(n: int, least: int) -> int:
        return max(least, 2 * PAD + max(0, n - 1) * LANE)
    gh = {g: size(len(v), GAP_MIN) for g, v in gaps.items()}
    cw = {k: size(len(v), CHANNEL_MIN) for k, v in chans.items()}
    xs = [left + cw[0]]
    for c in range(1, C):
        xs.append(xs[-1] + W + cw[c])
    gy, ry, y = {}, {}, top
    for r in range(R):
        gy[r] = y
        y += gh[r]
        ry[r] = y
        y += rows[r]["h"]
    gy[R] = y
    nodes = []
    for r, row in enumerate(rows):
        for n, c, span in row.get("cells", []):
            n.update(x=xs[c], y=ry[r], w=xs[c + span - 1] + W - xs[c], h=row["h"], _row_y=ry)
            if span > 1 and n.get("sub"):           # a box across columns wraps its text to its own width
                n["sublines"] = wrap(n["sub"], n["w"] - 12, 10, len(n.get("sublines") or [1]))
            nodes.append(n)
    by = {n["id"]: n for n in nodes}

    def other_x(i: int, end: str) -> float:          # where the line's other end is, to order the ports along an edge
        p = plans[i]
        o = by[p["e"]["target"] if end == "a" else p["e"]["source"]]
        return o["x"] + o["w"] / 2
    ports: dict[tuple[int, str], tuple[float, float]] = {}
    for uses in sides.values():
        uses.sort(key=lambda u: other_x(u[0], u[1]))
        for j, (i, end, nid, side) in enumerate(uses):
            n = by[nid]
            ports[(i, end)] = (round(n["x"] + n["w"] * (j + 1) / (len(uses) + 1), 1), n["y"] + (n["h"] if side == "bottom" else 0))

    def lane_y(g: int, i: int) -> float:
        n = len(gaps[g])
        return round(gy[g] + (gh[g] - (n - 1) * LANE) / 2 + gaps[g].index(i) * LANE, 1)

    def lane_x(k: int, i: int) -> float:
        n = len(chans[k])
        start = (xs[k] - cw[k]) if k < C else xs[C - 1] + W
        return round(start + (cw[k] - (n - 1) * LANE) / 2 + chans[k].index(i) * LANE, 1)
    out = []
    for i, p in enumerate(plans):
        (ax, ay), (bx, by_) = ports[(i, "a")], ports[(i, "b")]
        la = lane_y(p["ga"], i)
        if p["k"] is None:
            pts = [(ax, ay), (ax, la), (bx, la), (bx, by_)]
        else:
            vx, lb = lane_x(p["k"], i), lane_y(p["gb"], i)
            pts = [(ax, ay), (ax, la), (vx, la), (vx, lb), (bx, lb), (bx, by_)]
        clean = [pts[0]]
        for q in pts[1:]:
            if q != clean[-1]:
                clean.append(q)
        e = dict(p["e"])
        e.update(points=[[x, yy] for x, yy in clean], exit=p["sa"], entry=p["sb"],
                 label_at=[ax + 3, la - 3], short=wrap(e.get("label", ""), 150, 9, 1)[0] if e.get("label") else "")
        out.append(e)
    return nodes, out


def crossings(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Each line that passes through a box it does not join, or through its own boxes (for the tests and the self-check)."""
    boxes = [n for n in nodes if not n.get("container") and n.get("shape") != "text"]
    bad = []
    for e in edges:
        pts = e.get("points") or []
        for (x1, y1), (x2, y2) in itertools.pairwise(pts):
            for n in boxes:
                lo_x, hi_x, lo_y, hi_y = n["x"] + 0.5, n["x"] + n["w"] - 0.5, n["y"] + 0.5, n["y"] + n["h"] - 0.5
                if max(x1, x2) > lo_x and min(x1, x2) < hi_x and max(y1, y2) > lo_y and min(y1, y2) < hi_y:
                    bad.append(f"{e['source']} -> {e['target']} crosses {n['id']}")
    return bad


def overflows(nodes: list[dict]) -> list[str]:
    """Each box whose text does not fit inside it."""
    bad = []
    for n in nodes:
        if n.get("container") or "lines" not in n:
            continue
        size = n.get("fontSize", 12)
        widths = [text_width(t, size) for t in n["lines"]] + [text_width(t, 10) for t in n.get("sublines", [])]
        height = 16 + 14 * (len(n["lines"]) - 1) + 13 * len(n.get("sublines", []))
        if max(widths, default=0) > n["w"] - 8 or height > n["h"]:
            bad.append(n["id"])
    return bad


# ---------------------------------------------------------------- physical: containers, networks, ports, mounts
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::?-([^}]*))?\}")


def plain(text: str) -> str:
    """${NAME:-default} as its default (what a fresh installation uses)."""
    return _VAR.sub(lambda m: m.group(2) or "", str(text or ""))


_DESKTOP = re.compile(r"^/(?:run/desktop/mnt/host|host_mnt|mnt/host)/([a-zA-Z])(?:/(.*))?$")
_ANON = re.compile(r"^[0-9a-f]{64}$")


def host_path(src: str) -> str:
    r"""A host folder in the host's own form: Docker Desktop's /host_mnt/c/Users/... (or /run/desktop/mnt/host/c/...)
    is C:\Users\... as on Windows; C:/Users/... too."""
    m = _DESKTOP.match(src)
    if m:
        return f"{m.group(1).upper()}:\\" + (m.group(2) or "").replace("/", "\\").rstrip("\\")
    if re.match(r"^[A-Za-z]:[\\/]", src):
        return src[0].upper() + ":\\" + src[3:].replace("/", "\\").rstrip("\\")
    return src.rstrip("/") or src


def is_file(src: str) -> bool:
    """A single file mounted (README.md, docker-compose.yml, help.txt, version.toml), not a folder."""
    last = re.split(r"[\\/]", src.rstrip("/\\"))[-1]
    return bool(re.fullmatch(r"[^.].*\.[A-Za-z0-9]{1,5}", last)) and not src.endswith(".sock")


def _mount(spec) -> dict:
    if isinstance(spec, dict):
        src, dst = str(spec.get("source") or ""), str(spec.get("target") or "")
    else:
        bits = plain(spec).split(":")
        if len(bits) >= 2 and len(bits[0]) == 1:          # a Windows drive letter
            bits = [bits[0] + ":" + bits[1], *bits[2:]]
        src, dst = bits[0], (bits[1] if len(bits) > 1 else "")
    kind = "socket" if src.endswith(".sock") else "folder" if src.startswith((".", "/", "~")) or re.match(r"^[A-Za-z]:", src) else "volume"
    if kind == "folder" and is_file(src):
        kind = "file"
    return {"source": host_path(src) if kind in ("folder", "file") else src, "target": dst, "kind": kind}


def port(spec: str) -> str:
    """A published port without the address it is bound to ("0.0.0.0:443:443", ":::443:443" and "443:443" are one)."""
    bits = str(spec).split(":")
    return ":".join(bits[-2:]) if len(bits) >= 2 else str(spec)


def from_compose(compose: dict) -> list[dict]:
    """Each service of docker-compose.yml: image, networks, published ports, mounts, profile (e.g. test: on demand), and
    whether it runs once and ends (no restart policy: setup, reports-init)."""
    out = []
    for name, s in (compose.get("services") or {}).items():
        nets = s.get("networks") or (["none"] if s.get("network_mode") == "none" else ["default"])
        out.append({"service": name, "image": plain(s.get("image") or ""), "networks": list(nets),
                    "ports": sorted({port(plain(p)) for p in s.get("ports") or []}),
                    "mounts": [_mount(v) for v in s.get("volumes") or []],
                    "profiles": list(s.get("profiles") or []), "state": "",
                    "one_shot": not s.get("restart") and not s.get("profiles")})
    return out


def from_inspect(inspected: list[dict]) -> list[dict]:
    """The running installation (docker inspect of its containers): the same shape, with each container's state; a
    container with no restart policy that has finished is a one-shot (setup, reports-init)."""
    out = []
    for d in inspected:
        labels = ((d.get("Config") or {}).get("Labels")) or {}
        svc = labels.get("com.docker.compose.service") or (d.get("Name") or "").strip("/")
        nets = sorted(((d.get("NetworkSettings") or {}).get("Networks") or {}).keys())
        nets = [re.sub(r"^.*?_", "", n) if "_" in n else n for n in nets]
        ports = set()
        for cport, binds in ((d.get("NetworkSettings") or {}).get("Ports") or {}).items():
            for b in binds or []:
                ports.add(f"{b.get('HostPort')}:{cport.split('/')[0]}")
        mounts = []
        for m in d.get("Mounts") or []:
            src = m.get("Name") or m.get("Source") or ""
            if m.get("Type") == "volume":
                kind = "volume"
            elif str(m.get("Source", "")).endswith(".sock"):
                kind = "socket"
            else:
                kind = "file" if is_file(src) else "folder"
            mounts.append({"source": host_path(src) if kind in ("folder", "file") else src, "target": m.get("Destination") or "",
                           "kind": kind})
        state = ((d.get("State") or {}).get("Status")) or ""
        restart = (((d.get("HostConfig") or {}).get("RestartPolicy")) or {}).get("Name") or ""
        out.append({"service": svc, "image": (d.get("Config") or {}).get("Image") or "", "networks": nets, "ports": sorted(ports),
                    "mounts": mounts, "profiles": [], "state": state,
                    "one_shot": state in ("exited", "created") and restart in ("", "no")})
    return sorted(out, key=lambda x: x["service"])


def stores(items: list[dict]) -> list[dict]:
    """Each volume, folder and file mounted, once: {key, kind, label, users: [(service, target)]}. An anonymous volume (a
    64-character id) is named by who uses it."""
    found: dict[str, dict] = {}
    for it in items:
        for m in it["mounts"]:
            if m["kind"] == "socket":
                continue
            key = m["source"].lower() if m["kind"] != "volume" else m["source"]
            s = found.setdefault(key, {"key": key, "kind": m["kind"], "label": m["source"], "users": []})
            s["users"].append((it["service"], m["target"]))
    for s in found.values():
        if s["kind"] == "volume" and _ANON.match(s["label"]):
            s["label"] = f"anonymous volume (used by {', '.join(sorted({u for u, _t in s['users']}))})"
    return sorted(found.values(), key=lambda s: (s["kind"], s["label"].lower()))


def physical(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """The physical diagram: the ports published on the host at the top; a band per Docker network (a container on
    several networks sits in the first, the others named); the volumes, folders and files mounted at the bottom, each
    once; the one-shot containers that have finished listed apart. Lines from the published ports to the containers that
    publish them and from each container to what it mounts, one per pair, routed by route()."""
    PER = 4
    running = [it for it in items if not it.get("one_shot")]
    done = [it for it in items if it.get("one_shot")]
    order = ["frontend", "backend", "terminal", "none", "default"]
    home = {}
    for it in running:
        nets = it["networks"] or ["default"]
        home[it["service"]] = min(nets, key=lambda n: order.index(n) if n in order else 9)
    bands = [n for n in order if n in home.values()] + sorted({v for v in home.values() if v not in order})
    published = sorted({f"{p} {it['service']}" for it in running for p in it["ports"]})
    rows: list[dict] = [{"h": 50, "cells": [(box("published", "Published on the host",
                                               ", ".join(published) or "nothing", FILL["published"], sub_lines=2, bold=True), 0, PER)]}]
    spans: list[tuple[str, str, int, int]] = []          # (id, label, first row, last row) of each band and group
    for band in bands:
        members = [it for it in running if home[it["service"]] == band]
        first = len(rows)
        rows.append({"h": 24, "cells": []})
        for i in range(0, len(members), PER):
            cells = []
            for j, it in enumerate(members[i:i + PER]):
                others = [n for n in it["networks"] if n != band]
                sub = " · ".join(x for x in (it["image"], f"also on {', '.join(others)}" if others else "", it["state"],
                                              "on demand" if it["profiles"] else "") if x)
                cells.append((box(f"c_{it['service']}", it["service"], sub, dashed=bool(it["profiles"])), j, 1))
            rows.append({"h": 62, "cells": cells})
        spans.append((f"net_{band}", f"Network: {band}" + (" (internal)" if band in ("backend", "terminal") else ""), first,
                      len(rows) - 1))
    st = stores(running)
    for title, kind in (("Docker volumes", "volume"), ("Folders on the host", "folder"), ("Files on the host", "file")):
        keys = [s for s in st if s["kind"] == kind]
        if not keys:
            continue
        first = len(rows)
        rows.append({"h": 24, "cells": []})
        for i in range(0, len(keys), PER):
            rows.append({"h": 48, "cells": [(box(f"s_{s['key']}", s["label"], "", "#ffffff", size=11), j, 1)
                                            for j, s in enumerate(keys[i:i + PER])]})
        spans.append((f"g_{kind}", title, first, len(rows) - 1))
    edges = [{"source": "published", "target": f"c_{it['service']}", "label": ", ".join(it["ports"])} for it in running if it["ports"]]
    pairs: dict[tuple[str, str], list[str]] = {}
    for s in st:
        for svc, target in s["users"]:
            pairs.setdefault((f"c_{svc}", f"s_{s['key']}"), []).append(target)
    edges += [{"source": a, "target": b, "label": ", ".join(t), "dashed": True} for (a, b), t in pairs.items()]
    if done:
        rows.append({"h": 48, "cells": [(box("finished", "Run once and finished",
                                             ", ".join(f"{it['service']} ({it['state'] or 'runs at start'})" for it in done),
                                             "#f5f5f5", sub_lines=2), 0, PER)]})
    nodes, edges = route(rows, PER, W_BOX, edges)
    ry = nodes[0]["_row_y"]
    left = min(n["x"] for n in nodes) - 10
    right = max(n["x"] + n["w"] for n in nodes) + 10
    bands_out = []
    for ident, label, first, last in spans:
        kind = ident.split("_", 1)[1]
        bands_out.append({"id": ident, "label": label, "x": left, "y": ry[first], "w": right - left,
                          "h": ry[last] + rows[last]["h"] + 10 - ry[first], "fill": FILL.get(kind, FILL.get(
                              {"volume": "volumes", "folder": "folders", "file": "folders"}.get(kind, ""), "#f5f5f5")),
                          "container": True, "bold": True, "keepSize": True})
        inside = {n["id"] for r in rows[first:last + 1] for n, _c, _s in r.get("cells", [])}
        for n in nodes:
            if n["id"] in inside:
                n["parent"] = ident
    for n in nodes:
        n.pop("_row_y", None)
    return bands_out + nodes, edges


# ---------------------------------------------------------------- draw.io files and the document
def to_drawio(title: str, nodes: list[dict], edges: list[dict]) -> str:
    """A .drawio file of the nodes and edges (absolute places; a node in a container is placed inside it); a routed line
    keeps its bends and leaves and enters its boxes where the picture does (R3.4)."""
    by = {n["id"]: n for n in nodes}

    def cid(i) -> str:
        return "n_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(i))
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for n in nodes:
        p = by.get(n.get("parent"))
        x, y = n["x"] - (p["x"] if p else 0), n["y"] - (p["y"] if p else 0)
        head = "<br>".join(html.escape(t) for t in n.get("lines") or [n["label"]])
        subs = n.get("sublines") or ([n["sub"]] if n.get("sub") else [])
        label = f"<b>{head}</b>" + (f"<br><font style='font-size:10px' color='#5b6775'>{'<br>'.join(html.escape(t) for t in subs)}</font>"
                                    if subs else "")
        style = ("rounded=1;arcSize=6;whiteSpace=wrap;html=1;align=left;spacingLeft=6;"
                 f"verticalAlign={'top' if n.get('container') else 'middle'};fillColor={n.get('fill', '#ffffff')};strokeColor=#8a96a3;"
                 f"fontSize={n.get('fontSize', 12)};" + ("container=1;collapsible=0;" if n.get("container") else "")
                 + ("dashed=1;" if n.get("dashed") else ""))
        tip = f' tooltip="{html.escape(n["title"])}"' if n.get("title") else ""
        cells.append(f'<UserObject id="{cid(n["id"])}" label="{html.escape(label)}"{tip}><mxCell style="{style}" vertex="1" '
                     f'parent="{cid(p["id"]) if p else "1"}"><mxGeometry x="{x}" y="{y}" width="{n["w"]}" height="{n["h"]}" '
                     'as="geometry"/></mxCell></UserObject>')
    for i, e in enumerate(edges):
        if e["source"] not in by or e["target"] not in by:
            continue
        a, b, pts = by[e["source"]], by[e["target"]], e.get("points") or []
        style = (f"html=1;endArrow={'none' if e.get('arrow') is False else 'block'};endFill=1;fontSize=10;labelBackgroundColor=#ffffff;"
                 + ("dashed=1;" if e.get("dashed") else ""))
        inner = ""
        if len(pts) > 1:
            fx = lambda n, x: f"{max(0.0, min(1.0, (x - n['x']) / n['w'])):.3f}"  # noqa: E731
            style += (f"edgeStyle=none;exitX={fx(a, pts[0][0])};exitY={0 if e.get('exit') == 'top' else 1};exitPerimeter=0;"
                      f"entryX={fx(b, pts[-1][0])};entryY={0 if e.get('entry') == 'top' else 1};entryPerimeter=0;")
            mids = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
            inner = f'<Array as="points">{mids}</Array>' if mids else ""
        cells.append(f'<mxCell id="e_{i}" value="{html.escape(e.get("short") or e.get("label", ""))}" style="{style}" edge="1" '
                     f'parent="1" source="{cid(e["source"])}" target="{cid(e["target"])}"><mxGeometry relative="1" as="geometry">'
                     f'{inner}</mxGeometry></mxCell>')
    return (f'<mxfile host="EA Explorer" type="device"><diagram id="estate" name="{html.escape(title)}"><mxGraphModel grid="1" '
            f'gridSize="10" page="0"><root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>\n')


def markdown(items: list[dict]) -> str:
    """docs/estate.md: both diagrams in words (tables), beside their .drawio files."""
    lines = ["# EA Explorer's own estate (R2.33)", "",
             "Made by `python tools/build_estate_diagrams.py` from docker-compose.yml: do not edit by hand. The pictures are",
             "[estate/logical.drawio](estate/logical.drawio) and [estate/physical.drawio](estate/physical.drawio) (open them",
             "in draw.io); System Admin › Estate draws them for the running installation.", "",
             "## Logical: the components", "", "| Component | What it does | Group |", "|---|---|---|"]
    lines += [f"| {n} | {w} | {g} |" for _i, n, w, g in LOGICAL]
    names = {i: n for i, n, _w, _g in LOGICAL}
    lines += ["", "## Logical: who calls whom", "", "| From | To | What |", "|---|---|---|"]
    lines += [f"| {names[a]} | {names[b]} | {w} |" for a, b, w in FLOWS]
    lines += ["", "## Physical: the containers", "", "| Container | Image | Networks | Published | Mounted |", "|---|---|---|---|---|"]
    for it in items:
        mounts = ", ".join(f"{m['source']} → {m['target']}" for m in it["mounts"]) or "-"
        lines.append(f"| {it['service']}{' (on demand)' if it['profiles'] else ''}{' (runs once at start)' if it.get('one_shot') else ''} | `{it['image']}` | {', '.join(it['networks'])} | "
                     f"{', '.join(it['ports']) or '-'} | {mounts} |")
    lines += ["", "The backend and terminal networks are internal: nothing on them is reachable from outside but through the",
              "front door. Each database can live on a server of its own (docs/databases.md).", ""]
    return "\n".join(lines)
