"""Sample content (laptop, D346; AGENTS.md: every feature comes with sample data), sent by the main API once the sample
projects exist (it knows the models, projects, documents and canvases; the library never reads its database). Made once:
nothing is added to a library that has entries already. Every name is invented."""

from __future__ import annotations

from types import SimpleNamespace

from . import library as L
from .db import one


def _who(name: str):
    return SimpleNamespace(username=name, roles=["user"], permissions={}, library_admin=False)


def _has_entries(conn, lib) -> bool:
    return bool(one(conn, "SELECT 1 AS x FROM lib.entries WHERE library_id = %(l)s", l=lib["id"]))


def _row(*cells):
    return list(cells)


def sample(conn, data: dict) -> dict:
    said = []
    ana, lead, arch = _who("user_architect"), _who("user_lead_architect"), _who("user_project_admin")
    models = data.get("models") or []
    projects = data.get("projects") or []
    refs = data.get("reference") or []
    org = L.org_library(conn)
    if not _has_entries(conn, org):
        f = {n: L.add_folder(conn, lead, org, {"name": n})["id"] for n in
             ("Architecture standards", "Reference models", "How we work", "Useful links")}
        sub = L.add_folder(conn, lead, org, {"name": "Templates and checklists", "parent": f["How we work"]})["id"]
        L.add_entry(conn, lead, org, {"kind": "page", "title": "Start here", "tags": "welcome, overview", "blocks": [
            {"type": "text", "text": "The enterprise library: where to find our standards, reference models, ways of working and useful links. "
                                     "Anyone can add to it; every change is kept and can be undone."},
            {"type": "heading", "text": "Our models"},
            {"type": "table", "header": True, "rows": [_row("Model", "What it is")] +
             [_row(f"[{m['name']}](ea:model:{m['id']})", m.get("about") or "") for m in models[:8]]},
            {"type": "heading", "text": "Architecture projects"},
            {"type": "list", "items": [f"[{p['name']}](ea:project:{p['id']})" for p in projects[:8]]},
            {"type": "links", "items": [{"label": "The TOGAF Standard (The Open Group)", "href": "https://www.opengroup.org/togaf"},
                                        {"label": "ArchiMate (The Open Group)", "href": "https://www.opengroup.org/archimate-forum/archimate-overview"}]},
        ]})
        L.add_entry(conn, lead, org, {"kind": "page", "title": "Architecture principles in brief", "folder": f["Architecture standards"],
                                      "tags": "principles, standards", "blocks": [
            {"type": "table", "header": True, "rows": [
                _row("Principle", "What it means for a project"),
                _row("Reuse before buy, buy before build", "Look in the models for what we have before choosing a product"),
                _row("Cloud first", "New solutions are hosted in the cloud unless there is a reason not to"),
                _row("One customer record", "Customer data is held once and shared through the integration layer"),
                _row("Secure by design", "Every design names its data classification and controls")]},
            {"type": "text", "text": "The full set is in the Organisation base's Principles tab."}]})
        for r in refs[:4]:
            L.add_entry(conn, ana, org, {"kind": "link", "title": r["title"], "folder": f["Architecture standards"], "href": f"ea:reference:{r['id']}",
                                         "description": "From the reference library"})
        L.add_entry(conn, lead, org, {"kind": "page", "title": "Reference models we use", "folder": f["Reference models"], "tags": "reference, models",
                                      "blocks": [{"type": "table", "header": True, "rows": [_row("Model", "Use it for")] +
                                                 [_row(f"[{m['name']}](ea:model:{m['id']})", "A starting point for new models")
                                                  for m in models if "reference" in (m.get("kind") or "")][:6]
                                                 or [_row("(none yet)", "")]}]})
        L.add_entry(conn, ana, org, {"kind": "page", "title": "Architecture review checklist", "folder": sub, "tags": "review, checklist, governance",
                                     "blocks": [{"type": "list", "items": [
                                         "The key questions are answered and accepted by their stakeholders",
                                         "Every new application has an owner, a lifecycle and a TIME decision",
                                         "The target names the capabilities it changes, with their maturity",
                                         "Gaps between baseline and target have work packages",
                                         "Principles that do not apply have a dispensation in the governance log"]}]})
        L.add_entry(conn, ana, org, {"kind": "file", "title": "Glossary", "folder": f["How we work"], "tags": "glossary"},
                    "Glossary.md", b"# Glossary (sample)\n\nCapability: what the business can do.\nValue stream: the stages that "
                                   b"create value for a stakeholder.\nWork package: a set of actions that delivers a change.\n")
        for title, href in (("Architecture Board calendar", "https://intranet.example.org/ea/board-calendar"),
                            ("Request architecture help", "https://intranet.example.org/ea/request"),
                            ("Cloud landing zone pattern (sample)", "https://intranet.example.org/ea/patterns/cloud-landing-zone")):
            L.add_entry(conn, ana, org, {"kind": "link", "title": title, "folder": f["Useful links"], "href": href})
        # a few changes in the history: a page edited, a link added and removed (undo shows them back)
        start = one(conn, "SELECT guid::text AS g FROM lib.entries WHERE library_id = %(l)s AND title = 'Start here'", l=org["id"])["g"]
        L.change_entry(conn, arch, org, start, {"description": "Begin here: what is in the library and where"})
        tmp = L.add_entry(conn, arch, org, {"kind": "link", "title": "Old intranet page (sample)", "folder": f["Useful links"],
                                            "href": "https://intranet.example.org/old"})["id"]
        L.remove_entry(conn, arch, org, tmp)
        said.append("enterprise library")
    for i, p in enumerate(projects[:3]):
        lib = one(conn, "SELECT * FROM lib.libraries WHERE project_guid::text = %(g)s", g=p["id"])
        if not lib:
            lib = one(conn, """INSERT INTO lib.libraries (scope, project_guid, project_name, created_by) VALUES ('project', %(g)s::uuid, %(n)s, 'system')
                               RETURNING *""", g=p["id"], n=p["name"])
        if _has_entries(conn, lib):
            continue
        work = L.add_folder(conn, lead, lib, {"name": "Working links"})["id"]
        L.add_folder(conn, lead, lib, {"name": "Meeting notes"})
        L.add_entry(conn, lead, lib, {"kind": "page", "title": f"{p['name']}: where everything is", "tags": "overview", "blocks": [
            {"type": "text", "text": "The project's models, its main documents and its canvases, in one place."},
            {"type": "table", "header": True, "rows": [_row("Model", "Role")] +
             [_row(f"[{m['name']}](ea:model:{m['id']})", m.get("role") or "") for m in p.get("models") or []]},
            {"type": "heading", "text": "Documents"},
            {"type": "list", "items": [f"[{d['title']}](ea:document:{p['id']}:{d['id']})" for d in (p.get("documents") or [])[:6]]
             or ["The repository's documents appear here once they are linked."]},
            {"type": "links", "items": [{"label": c["name"], "href": f"ea:canvas:{p['id']}:{c['id']}"} for c in (p.get("canvases") or [])[:5]]
             or [{"label": "The project in EA Explorer", "href": f"ea:project:{p['id']}"}]},
        ]})
        L.add_entry(conn, ana, lib, {"kind": "link", "title": "Steering committee pack (sample link)", "folder": work,
                                     "href": "https://intranet.example.org/projects/steering-pack"})
        if i == 0:
            conn.execute("UPDATE lib.libraries SET in_enterprise = true WHERE id = %(i)s", {"i": lib["id"]})
        said.append(p["name"])
    for p in data.get("external") or []:          # a project whose library is somewhere else
        conn.execute("""INSERT INTO lib.libraries (scope, project_guid, project_name, external_link, created_by)
                        VALUES ('project', %(g)s::uuid, %(n)s, %(x)s, 'system') ON CONFLICT (project_guid) DO NOTHING""",
                     {"g": p["id"], "n": p["name"], "x": p["link"]})
    return {"made": said}
