"""Drawn views on the demo estate (owner, 10 Nov 2026, phases 28 and 29, D354, D397): laptop only, made once (a demo estate
with drawn views already is left alone). Every name is invented.

Between them they show every state a drawn view can be in:

* a tidy view of the claims applications, saved twice (two versions), the second hiding one relationship;
* a sketch with a placeholder (an object drawn before it is in the model), a relationship drawn but not committed
  (the architect's uncommitted change from before D413, shown dashed) and an uncommitted change to an entity on it (the
  architect's, in the editor's Uncommitted changes panel, D413);
* the online claim channels through an Or junction;
* a view saved before the model changed (the model changed since it was saved);
* an entity with its own icon (the Mobile App, on several views);
* a copy of a drawn view (a new drawn view, D407);
* the model's own generated views (D406): one copied from a standard view as it is, one copied and changed;
* views as evidence in a sample project, links only (D408): the live view for a key question, version 2 for a deliverable.

The views live in the views service (D405): this waits for it like the sample libraries, and the next start makes them
when it is not up yet.
"""

from __future__ import annotations

from sqlalchemy import text

from ..metamodel_edit import EditError
from .demo_estate import DEMO_NAME

# a phone: an invented icon, plain shapes only (it passes the icon checks)
PHONE_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
             b'<rect x="6" y="2" width="12" height="20" rx="2" fill="none" stroke="#1F3A5F" stroke-width="2"/>'
             b'<circle cx="12" cy="18" r="1.2" fill="#1F3A5F"/></svg>')

LANDSCAPE = ["Claims Platform", "Customer Portal", "Mobile App", "Fraud Analytics", "Payments Hub", "Customer Master Data Hub",
             "Integration Platform", "Claims Department"]
CHANNELS = ["Customer Portal", "Mobile App", "Online claim channels (Or)", "Customers can lodge claims online"]
EARLIER = ["Customer Portal", "Mobile App", "Claims Platform"]
SKETCH = ["Claims Platform", "Payments Hub", "Mobile App", "Claims Department"]
PROJECT = "Protea Claims Transformation 2028 (sample)"
DELIVERABLE = "Application communication diagram"
QUESTION = "What is the impact of removing the legacy claims application?"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _wait_for_service(m: str) -> tuple[dict | None, str]:
    """The model's drawn views as the views service has them; it may still be starting (about two and a half minutes)."""
    import time

    from .. import views_client as vc
    why = ""
    for _ in range(30):
        try:
            return vc.list_views(m), ""
        except vc.ViewsDown as exc:
            why = str(exc)
            if "not answering" not in why:
                break
            time.sleep(5)
    return None, why


def _own_views(m: str) -> int:
    """The model's own generated views (D406): copies of a standard view's definition, kept with the model."""
    from .. import views as vp
    from .. import views_client as vc
    from ..db import get_engine
    with get_engine().connect() as conn:
        std = next((v for v in vp.list_views(conn) if v["is_builtin"] and "ApplicationComponent" in (v["element_types"] or [])), None)
    if not std:
        return 0
    base = {k: std[k] for k in ("category", "purpose", "concerns", "stakeholders", "element_types", "relationship_types",
                                "heat_attribute")}
    own = [{**base, "name": f"{std['name']} (our copy)", "category": "Model", "copied_from": std["code"]},
           {**base, "name": "Claims applications and their data", "category": "Model", "copied_from": std["code"],
            "purpose": "The claims team's own cut: the applications and the data they hold, without the technology.",
            "element_types": [t for t in base["element_types"] if not t.startswith(("Node", "Device", "System"))]
                             + [t for t in ("DataObject",) if t not in base["element_types"]]}]
    got = vc.import_model(m, {"own_views": own}, "user_architect", source="package")
    return got.get("own_views", 0)


def run() -> list[str]:
    from .. import commits as cm
    from .. import drawn_views as dv
    from .. import notify
    from .. import permissions as perms
    from .. import projects as pj
    from .. import views_client as vc
    from ..db import get_engine

    if not vc.service_on():
        return ["the views service is switched off: no sample drawn views"]
    with get_engine().connect() as conn:
        m = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": DEMO_NAME}).scalar()
    if not m:
        return []
    have, why = _wait_for_service(m)
    if have is None:
        return [f"sample drawn views not made yet ({why}); the next start makes them"]
    if have.get("views"):
        return []
    said: list[str] = []
    ar, la = _p("user_architect"), _p("user_lead_architect")
    real_notify = notify.create
    notify.create = lambda *a, **k: None
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    made: dict[str, tuple[str, int]] = {}
    try:
        with get_engine().begin() as conn:
            conn.execute(text("SELECT set_config('eax.actor', 'user_architect', true)"))
            ids = {r["name"]: r["g"] for r in conn.execute(text("""
                SELECT e.name, e.guid::text AS g FROM core.entities e JOIN core.models x ON x.id = e.model_id
                 WHERE x.guid::text = :m AND NOT e.is_deleted"""), {"m": m}).mappings()}
            want = set(LANDSCAPE + CHANNELS + SKETCH)
            if not want <= set(ids):
                return [f"drawn views skipped: the demo estate lacks {', '.join(sorted(want - set(ids)))}"]
            dv.set_icon(conn, m, ar, ids["Mobile App"], PHONE_SVG, "phone.svg", "image/svg+xml")
            m_row = dv.repo.get_model(conn, m)

            def mk():
                return dv.marker(conn, m_row["_id"])

            # saved before the model changed: then a committed change to one of its entities
            # the view still shows the app's old name ("Protea Go"): Resync renames it to the model's "Mobile App"
            xml = dv.generate(conn, m, ar, [ids[n] for n in EARLIER]).replace('label="Mobile App"', 'label="Protea Go"', 1)
            v = vc.create(m, {"name": "Customer channels (before the app was renamed)", "source": "generated",
                              "description": "Saved before a later change to the model: it shows the model changed "
                                             "since; Resync brings the app's new name.", "xml": xml}, ar.username, mk())
            made["earlier"] = (v["id"], 1)
            conn.execute(text("""UPDATE core.entities SET description = description || ' (renamed in the app stores in 2026)',
                                        modified_at = clock_timestamp(), modified_by = 'user_architect'
                                  WHERE guid = CAST(:g AS uuid)"""), {"g": ids["Mobile App"]})

            # tidy, two versions; the second hides one relationship
            v = vc.create(m, {"name": "Claims application landscape", "source": "generated",
                              "description": "The applications behind claims, laid out by domain.",
                              "xml": dv.generate(conn, m, ar, [ids[n] for n in LANDSCAPE])}, ar.username, mk())
            ents = dv._entities(conn, m_row, [ids[n] for n in LANDSCAPE])
            rels = dv._relationships(conn, m_row, list(ents))
            gone = next((r for r in rels if r["source"] == ids["Integration Platform"] and r["target"] == ids["Claims Platform"]),
                        rels[0] if rels else None)
            hidden = [{"rel": gone["type"], "id": gone["id"], "source": gone["source"], "target": gone["target"]}] if gone else []
            vc.save(m, v["id"], {"xml": dv.build_xml(list(ents.values()), rels, hidden=hidden), "base_version": 1,
                                 "note": "Hid the integration platform's serving line: it crossed everything"}, la.username, mk())
            made["landscape"] = (v["id"], 2)

            # a copy of a drawn view (D407): a new drawn view from the landscape's first version
            vc.create(m, {"name": "Claims application landscape (working copy)", "copy_from": v["id"], "copy_version": 1,
                          "description": "A copy to try another arrangement without touching the agreed one."},
                      la.username, mk())

            # the junction
            v = vc.create(m, {"name": "Online claim channels", "source": "generated",
                              "description": "Either channel realises online claims: an Or junction (D397).",
                              "xml": dv.generate(conn, m, ar, [ids[n] for n in CHANNELS])}, ar.username, mk())
            made["channels"] = (v["id"], 1)

            # a sketch: a placeholder and an uncommitted relationship (the architect's own change)
            try:
                pend = cm.record(conn, m, "user_architect", "relationship.create",
                                 {"data": {"source": ids["Mobile App"], "target": ids["Claims Department"],
                                           "relationship_type": "Serving", "name": "", "allow_outside": False}})
            except EditError:                # already there (an earlier start): the sketch shows it as it is
                pend = {}
            try:                             # an uncommitted entity change on the sketch (D413): the Uncommitted changes panel
                cm.record(conn, m, "user_architect", "entity.update",
                          {"entity": ids["Payments Hub"],
                           "data": {"description": "Takes claim payments and refunds; to move onto the new rails in 2028."}})
            except EditError:
                pass
            ents = dv._entities(conn, m_row, [ids[n] for n in SKETCH])
            rels = [dict(r, committed=True) for r in dv._relationships(conn, m_row, list(ents))]
            if pend.get("id"):
                rels.append({"id": str(pend["id"]), "type": "Serving", "source": ids["Mobile App"],
                             "target": ids["Claims Department"], "committed": False})
            from .. import notation
            ph = [{"type": "ApplicationComponent", "name": "Claims rules engine (not in the model yet)",
                   "look": notation.look("ApplicationComponent", "")}]
            v = vc.create(m, {"name": "Claims target sketch", "source": "new",
                              "description": "A sketch: one object not in the model yet, one relationship not committed yet.",
                              "xml": dv.build_xml(list(ents.values()), rels, placeholders=ph)}, ar.username, mk())
            made["sketch"] = (v["id"], 1)
        said.append(f"{DEMO_NAME}: 5 drawn views (one in two versions, one a copy), an icon, a junction view, "
                    "an uncommitted relationship and an uncommitted entity change")
        n = _own_views(m)
        if n:
            said.append(f"{DEMO_NAME}: {n} of the model's own generated views (copies of a standard view)")

        # evidence in a sample project (when the sample projects are there): links only (D408)
        with pj.connections(True) as conn:
            p = conn.execute(text("SELECT guid::text FROM proj.projects WHERE name = :n"), {"n": PROJECT}).scalar()
            if p and not conn.execute(text("""SELECT 1 FROM proj.view_evidence ev JOIN proj.projects x ON x.id = ev.project_id
                                               WHERE x.guid::text = :p"""), {"p": p}).first():
                item = conn.execute(text("""SELECT i.guid::text FROM proj.items i JOIN proj.projects x ON x.id = i.project_id
                                             WHERE x.guid::text = :p AND i.name = :n LIMIT 1"""), {"p": p, "n": DELIVERABLE}).scalar()
                q = conn.execute(text("""SELECT q.guid::text FROM proj.key_questions q JOIN proj.projects x ON x.id = q.project_id
                                          WHERE x.guid::text = :p AND q.question = :q LIMIT 1"""), {"p": p, "q": QUESTION}).scalar()
                n = 0
                if item:
                    dv.add_evidence(conn, p, la, {"model": m, "view": made["landscape"][0], "version": 2, "item": item,
                                                  "note": "The landscape as agreed at the architecture board"})
                    n += 1
                if q:
                    dv.add_evidence(conn, p, la, {"model": m, "view": made["sketch"][0], "question": q,
                                                  "note": "Where the legacy claims application's work goes (the live view)"})
                    n += 1
                if n:
                    said.append(f"{PROJECT}: {n} drawn views as evidence (links)")
    except vc.ViewsDown as exc:
        said.append(f"sample drawn views stopped part way ({exc})")
    finally:
        perms.current.reset(token)
        notify.create = real_notify
    return said
