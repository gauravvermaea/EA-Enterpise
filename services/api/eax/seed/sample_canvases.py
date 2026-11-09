"""Business Model Canvases for the sample projects (owner, 9 Nov 2026, D344): laptop only, made once per project (a
project with a canvas already is left alone). Every name is invented.

Between them they show every kind and state: a current state (agreed), a working copy with changes marked by hand
(added, changed, crossed out), the target made clean from it (draft), a scenario, a working copy of the changes
between two canvases, and the documents behind a canvas (when Documents is up).
"""

from __future__ import annotations

from sqlalchemy import text

B = {"kp": "key_partners", "ka": "key_activities", "kr": "key_resources", "vp": "value_propositions", "cr": "customer_relationships",
     "ch": "channels", "cs": "customer_segments", "co": "cost_structure", "rs": "revenue_streams"}

PROTEA_TODAY = [
    ("cs", "Retail policyholders (motor and home)"), ("cs", "Small businesses"), ("cs", "Brokers' clients"),
    ("vp", "Claims settled in about 20 working days"), ("vp", "Cover through a broker you trust"), ("vp", "Wide panel of repairers"),
    ("ch", "Brokers"), ("ch", "Call centre"), ("ch", "Branch walk-ins"), ("ch", "Paper claim forms by post"),
    ("cr", "Personal service through the broker"), ("cr", "Call-centre agents for claims"),
    ("rs", "Premiums, monthly and annual"), ("rs", "Excess on claims"), ("rs", "Broker administration fees"),
    ("kr", "Claims handlers (240)"), ("kr", "Legacy claims system"), ("kr", "Repairer and assessor panel"),
    ("ka", "Assess and settle claims"), ("ka", "Detect fraud"), ("ka", "Manage repairers"),
    ("kp", "Brokers"), ("kp", "Repairers and assessors"), ("kp", "Reinsurers"),
    ("co", "Claims paid"), ("co", "Claims handling staff"), ("co", "Legacy system licences and support"), ("co", "Broker commission"),
]
FYNBOS_PET = [
    ("cs", "Dog and cat owners, 25 to 45"), ("cs", "Vets' practices (as a channel and partner)"),
    ("vp", "Vet bills paid straight to the vet"), ("vp", "Cover in five minutes, online"), ("vp", "Two simple cover levels"),
    ("ch", "Fynbos app and website"), ("ch", "Vets' practices"), ("ch", "Pet shops (leaflets and QR codes)"),
    ("cr", "Self-service, with a chat line"), ("cr", "Reminders for vaccinations"),
    ("rs", "Monthly premiums"), ("rs", "Wellness add-on"),
    ("kr", "The group's underwriting and billing"), ("kr", "Vet network"), ("kr", "Pet claims rules"),
    ("ka", "Sign up and pay vets"), ("ka", "Grow the vet network"), ("ka", "Price by breed and age"),
    ("kp", "Vets' practices"), ("kp", "Fynbos Commercial (shared services)"), ("kp", "Pet food brand (marketing)"),
    ("co", "Claims paid to vets"), ("co", "Vet network fees"), ("co", "Marketing"), ("co", "Shared services charge"),
]


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _fill(cv, conn, pg, who, cid, items):
    for b, t in items:
        cv.add_item(conn, pg, who, cid, {"block": B[b], "text": t})


def _find(cv, conn, pg, who, cid, words):
    return next(i["id"] for rows in cv.get(conn, pg, who, cid)["blocks"].values() for i in rows if i["text"].startswith(words))


def run() -> list[str]:
    from .. import canvases as cv
    from .. import notify
    from .. import permissions as perms
    from .. import projects as pj

    said: list[str] = []
    la, ar = _p("user_lead_architect"), _p("user_architect")
    real_notify = notify.create
    notify.create = lambda *a, **k: None
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    try:
        with pj.connections(True) as conn:
            def project(name):
                return conn.execute(text("""SELECT guid::text FROM proj.projects p WHERE name = :n
                                             AND NOT EXISTS (SELECT 1 FROM proj.canvases c WHERE c.project_id = p.id)"""), {"n": name}).scalar()
            pg = project("Protea Claims Transformation 2028 (sample)")
            if pg:
                today = cv.create(conn, pg, la, {"name": "Protea claims business model 2026", "kind": "current",
                                                 "description": "Claims as they run today (sample)."})["id"]
                _fill(cv, conn, pg, la, today, PROTEA_TODAY)
                cv.change_item(conn, pg, la, _find(cv, conn, pg, la, today, "Detect fraud"), {"note": "Rules engine plus two investigators."})
                cv.change(conn, pg, la, today, {"status": "agreed"})
                wc = cv.copy(conn, pg, ar, today, {"name": "Protea claims 2028 (working copy)", "kind": "working"})["id"]
                for words in ("Branch walk-ins", "Paper claim forms", "Legacy claims system", "Legacy system licences"):
                    cv.remove_item(conn, pg, ar, _find(cv, conn, pg, ar, wc, words))
                cv.change_item(conn, pg, ar, _find(cv, conn, pg, ar, wc, "Claims settled"), {"text": "Simple claims settled the same day; the rest in 5 days"})
                cv.change_item(conn, pg, ar, _find(cv, conn, pg, ar, wc, "Claims handlers"), {"text": "Claims handlers (150), on complex claims"})
                for b, t in (("ch", "Mobile app: claim with photos"), ("ch", "WhatsApp claims line"), ("kr", "Claims hub (straight-through)"),
                             ("ka", "Settle simple claims automatically"), ("cr", "Live claim tracking"), ("kp", "Cloud platform provider"),
                             ("co", "Claims hub subscription")):
                    cv.add_item(conn, pg, ar, wc, {"block": B[b], "text": t})
                target = cv.clean_up(conn, pg, la, wc, {"name": "Protea claims business model 2028", "kind": "target",
                                                        "description": "The target after the transformation (sample): from the working copy."})["id"]
                sc = cv.copy(conn, pg, ar, target, {"name": "Protea claims: partner-led scenario", "kind": "scenario"})["id"]
                cv.add_item(conn, pg, ar, sc, {"block": B["kp"], "text": "Claims administration partner (outsourced first notice of loss)"})
                cv.remove_item(conn, pg, ar, _find(cv, conn, pg, ar, sc, "WhatsApp"))
                cv.from_compare(conn, pg, la, today, target, {"name": "Protea claims 2026 to 2028 changes (working copy)"})
                try:                    # the documents behind the current state, when Documents is up
                    cv.add_document(conn, pg, la, today, {"note": "Workshop with the claims managers"}, "Claims business model workshop notes.md",
                                    b"# Claims business model workshop (sample)\n\nWho our claimants are, how they reach us, what it costs.\n")
                except Exception:  # noqa: BLE001 - Documents not up yet: the canvas stands without it
                    pass
                said.append("Protea Claims Transformation 2028 (sample): 5 canvases")
            pg = project("Fynbos Pet Insurance launch (sample)")
            if pg:
                t = cv.create(conn, pg, la, {"name": "Fynbos pet insurance business model", "kind": "target",
                                             "description": "The new product's business model (sample)."})["id"]
                _fill(cv, conn, pg, la, t, FYNBOS_PET)
                cv.change(conn, pg, la, t, {"status": "agreed"})
                s = cv.copy(conn, pg, ar, t, {"name": "Fynbos pet insurance: direct only", "kind": "scenario",
                                              "description": "Without vets' practices as a channel (sample)."})["id"]
                cv.remove_item(conn, pg, ar, _find(cv, conn, pg, ar, s, "Vets' practices (as"))
                cv.remove_item(conn, pg, ar, _find(cv, conn, pg, ar, s, "Vets' practices"))
                cv.add_item(conn, pg, ar, s, {"block": B["ch"], "text": "Social media campaigns"})
                said.append("Fynbos Pet Insurance launch (sample): 2 canvases")
            pg = project("Fynbos acquires Karoo Re (sample)")
            if pg:
                k = cv.create(conn, pg, la, {"name": "Karoo Re today", "kind": "current", "description": "Karoo Re as found in the due diligence (sample)."})["id"]
                _fill(cv, conn, pg, la, k, [("cs", "Primary insurers in southern Africa"), ("vp", "Treaty and facultative reinsurance"),
                                            ("ch", "Reinsurance brokers"), ("cr", "Long-standing account managers"), ("rs", "Reinsurance premiums"),
                                            ("kr", "Underwriting team"), ("ka", "Price and place treaties"), ("kp", "Retrocessionaires"),
                                            ("co", "Claims paid"), ("co", "Underwriting staff")])
                said.append("Fynbos acquires Karoo Re (sample): 1 canvas")
    finally:
        perms.current.reset(token)
        notify.create = real_notify
    return said
