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
import re

# ---------------------------------------------------------------- logical: the components and how they call each other
LOGICAL = [  # id, name, what it does, group
    ("people", "People (browser)", "architects, admins and readers in a web browser", "Users"),
    ("assistant", "AI assistant", "a person's own language model, through MCP", "Users"),
    ("eax", "eax command", "starts, stops, backs up, updates and tests the installation", "Users"),
    ("proxy", "Front door (nginx)", "https for everything; the only published ports", "Edge"),
    ("web", "Screens (React)", "the pages people use", "Application"),
    ("api", "API and job runner", "REST API, background jobs, the rules; the MCP server beside it", "Application"),
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
    """The logical diagram: a column per group (users, edge, application, platform, operations, data)."""
    nodes, W, H, GAP = [], 190, 58, 22
    for gi, g in enumerate(GROUP_ORDER):
        members = [c for c in LOGICAL if c[3] == g]
        x = 20 + gi * (W + 70)
        nodes.append({"id": f"g_{g}", "label": g, "x": x - 10, "y": 10, "w": W + 20, "h": 50 + len(members) * (H + GAP),
                      "fill": FILL[g], "container": True, "bold": True})
        for i, (cid, name, what, _g) in enumerate(members):
            nodes.append({"id": cid, "label": name, "sub": what, "x": x, "y": 45 + i * (H + GAP), "w": W, "h": H,
                          "fill": "#ffffff", "parent": f"g_{g}"})
    edges = [{"source": a, "target": b, "label": w} for a, b, w in FLOWS]
    return nodes, edges


# ---------------------------------------------------------------- physical: containers, networks, ports, mounts
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::?-([^}]*))?\}")


def plain(text: str) -> str:
    """${NAME:-default} as its default (what a fresh installation uses)."""
    return _VAR.sub(lambda m: m.group(2) or "", str(text or ""))


def _mount(spec) -> dict:
    if isinstance(spec, dict):
        src, dst = str(spec.get("source") or ""), str(spec.get("target") or "")
    else:
        bits = plain(spec).split(":")
        if len(bits) >= 2 and len(bits[0]) == 1:          # a Windows drive letter
            bits = [bits[0] + ":" + bits[1], *bits[2:]]
        src, dst = bits[0], (bits[1] if len(bits) > 1 else "")
    kind = "socket" if src.endswith(".sock") else "folder" if src.startswith((".", "/", "~")) or re.match(r"^[A-Za-z]:", src) else "volume"
    return {"source": src, "target": dst, "kind": kind}


def from_compose(compose: dict) -> list[dict]:
    """Each service of docker-compose.yml: image, networks, published ports, mounts, profile (e.g. test: on demand)."""
    out = []
    for name, s in (compose.get("services") or {}).items():
        nets = s.get("networks") or (["none"] if s.get("network_mode") == "none" else ["default"])
        out.append({"service": name, "image": plain(s.get("image") or ""), "networks": list(nets) if not isinstance(nets, dict) else list(nets),
                    "ports": [plain(p) for p in s.get("ports") or []], "mounts": [_mount(v) for v in s.get("volumes") or []],
                    "profiles": list(s.get("profiles") or []), "state": ""})
    return out


def from_inspect(inspected: list[dict]) -> list[dict]:
    """The running installation (docker inspect of its containers): the same shape, with each container's state."""
    out = []
    for d in inspected:
        labels = ((d.get("Config") or {}).get("Labels")) or {}
        svc = labels.get("com.docker.compose.service") or (d.get("Name") or "").strip("/")
        nets = sorted(((d.get("NetworkSettings") or {}).get("Networks") or {}).keys())
        nets = [re.sub(r"^.*?_", "", n) if "_" in n else n for n in nets]
        ports = []
        for cport, binds in ((d.get("NetworkSettings") or {}).get("Ports") or {}).items():
            for b in binds or []:
                ports.append(f"{b.get('HostIp') or '0.0.0.0'}:{b.get('HostPort')}:{cport.split('/')[0]}")
        mounts = [{"source": m.get("Name") or m.get("Source") or "", "target": m.get("Destination") or "",
                   "kind": "volume" if m.get("Type") == "volume" else "socket" if str(m.get("Source", "")).endswith(".sock") else "folder"}
                  for m in d.get("Mounts") or []]
        out.append({"service": svc, "image": (d.get("Config") or {}).get("Image") or "", "networks": nets, "ports": sorted(set(ports)),
                    "mounts": mounts, "profiles": [], "state": ((d.get("State") or {}).get("Status")) or ""})
    return sorted(out, key=lambda x: x["service"])


def physical(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """The physical diagram: the host; inside it a band per Docker network (a container on several networks sits in the
    first, with the others named); the published ports at the top; the volumes and folders mounted at the bottom."""
    nodes, edges = [], []
    W, H, GAP = 200, 62, 18
    order = ["frontend", "backend", "terminal", "none", "default"]
    home = {}
    for it in items:
        nets = it["networks"] or ["default"]
        home[it["service"]] = sorted(nets, key=lambda n: order.index(n) if n in order else 9)[0]
    bands = [n for n in order if n in home.values()] + sorted({v for v in home.values() if v not in order})
    per_row = 4
    y = 120
    nodes.append({"id": "published", "label": "Published on the host", "sub": ", ".join(sorted({p for it in items for p in it["ports"]})) or "nothing",
                  "x": 20, "y": 20, "w": per_row * (W + GAP) + 20, "h": 60, "fill": FILL["published"], "bold": True})
    for band in bands:
        members = [it for it in items if home[it["service"]] == band]
        rows = (len(members) + per_row - 1) // per_row
        bh = 40 + rows * (H + GAP)
        nodes.append({"id": f"net_{band}", "label": f"Network: {band}" + (" (internal)" if band in ("backend", "terminal") else ""),
                      "x": 20, "y": y, "w": per_row * (W + GAP) + 20, "h": bh, "fill": FILL.get(band, "#f5f5f5"),
                      "container": True, "bold": True})
        for i, it in enumerate(members):
            others = [n for n in it["networks"] if n != band]
            sub = it["image"] + (f" · also on {', '.join(others)}" if others else "") + (f" · {it['state']}" if it["state"] else "") \
                + (" · on demand" if it["profiles"] else "")
            nodes.append({"id": f"c_{it['service']}", "label": it["service"], "sub": sub, "parent": f"net_{band}",
                          "x": 30 + (i % per_row) * (W + GAP), "y": y + 34 + (i // per_row) * (H + GAP), "w": W, "h": H,
                          "fill": "#ffffff", "dashed": bool(it["profiles"])})
            if it["ports"]:
                edges.append({"source": "published", "target": f"c_{it['service']}", "label": ", ".join(it["ports"])})
        y += bh + 30
    stores: dict[str, str] = {}
    for it in items:
        for m in it["mounts"]:
            if m["kind"] == "socket":
                continue
            key = m["source"] if m["kind"] == "volume" else re.sub(r"/[^/]*\.[a-z]+$", "", m["source"])   # a file: its folder
            stores.setdefault(key, m["kind"])
    vols = sorted(k for k, v in stores.items() if v == "volume")
    folders = sorted(k for k, v in stores.items() if v == "folder")
    for title, group, keys in (("Docker volumes", "volumes", vols), ("Folders on the host", "folders", folders)):
        if not keys:
            continue
        rows = (len(keys) + per_row - 1) // per_row
        nodes.append({"id": f"g_{group}", "label": title, "x": 20, "y": y, "w": per_row * (W + GAP) + 20,
                      "h": 40 + rows * 46, "fill": FILL[group], "container": True, "bold": True})
        for i, k in enumerate(keys):
            nodes.append({"id": f"s_{k}", "label": k, "parent": f"g_{group}", "x": 30 + (i % per_row) * (W + GAP),
                          "y": y + 34 + (i // per_row) * 46, "w": W, "h": 34, "fill": "#ffffff", "fontSize": 11})
        y += 40 + rows * 46 + 30
    for it in items:
        for m in it["mounts"]:
            if m["kind"] == "socket":
                continue
            key = m["source"] if m["kind"] == "volume" else re.sub(r"/[^/]*\.[a-z]+$", "", m["source"])
            edges.append({"source": f"c_{it['service']}", "target": f"s_{key}", "label": m["target"], "dashed": True, "arrow": False})
    return nodes, edges


# ---------------------------------------------------------------- draw.io files and the document
def to_drawio(title: str, nodes: list[dict], edges: list[dict]) -> str:
    """A .drawio file of the nodes and edges (absolute places; a node in a container is placed inside it)."""
    by = {n["id"]: n for n in nodes}
    cid = lambda i: "n_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(i))  # noqa: E731
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for n in nodes:
        p = by.get(n.get("parent"))
        x, y = n["x"] - (p["x"] if p else 0), n["y"] - (p["y"] if p else 0)
        label = f"<b>{html.escape(n['label'])}</b>" + (f"<br><font style='font-size:10px' color='#5b6775'>{html.escape(n['sub'])}</font>" if n.get("sub") else "")
        style = ("rounded=1;arcSize=6;whiteSpace=wrap;html=1;align=left;spacingLeft=6;"
                 f"verticalAlign={'top' if n.get('container') else 'middle'};fillColor={n.get('fill', '#ffffff')};strokeColor=#8a96a3;"
                 f"fontSize={n.get('fontSize', 12)};" + ("container=1;collapsible=0;" if n.get("container") else "")
                 + ("dashed=1;" if n.get("dashed") else ""))
        cells.append(f'<mxCell id="{cid(n["id"])}" value="{html.escape(label)}" style="{style}" vertex="1" '
                     f'parent="{cid(p["id"]) if p else "1"}"><mxGeometry x="{x}" y="{y}" width="{n["w"]}" height="{n["h"]}" as="geometry"/></mxCell>')
    for i, e in enumerate(edges):
        if e["source"] in by and e["target"] in by:
            cells.append(f'<mxCell id="e_{i}" value="{html.escape(e.get("label", ""))}" style="html=1;endArrow={"none" if e.get("arrow") is False else "block"};'
                         f'fontSize=10;labelBackgroundColor=#ffffff;{"dashed=1;" if e.get("dashed") else ""}" edge="1" parent="1" '
                         f'source="{cid(e["source"])}" target="{cid(e["target"])}"><mxGeometry relative="1" as="geometry"/></mxCell>')
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
        lines.append(f"| {it['service']}{' (on demand)' if it['profiles'] else ''} | `{it['image']}` | {', '.join(it['networks'])} | "
                     f"{', '.join(it['ports']) or '-'} | {mounts} |")
    lines += ["", "The backend and terminal networks are internal: nothing on them is reachable from outside but through the",
              "front door. Each database can live on a server of its own (docs/databases.md).", ""]
    return "\n".join(lines)
