"""Sample content for the sample projects (owner, 8 Nov 2026, phase 13.8, D326): seed data only, laptop only, made
once. Every name, figure and link is invented (the companies are the fictitious Meridian, Karoo, Fynbos and Protea).

* Karoo Re cloud migration (sample), mid-way: governance records in every approval state, people with skills, calendar
  events, phases and steps done, its charter approved, a deliverable placed in the content framework, two tracking
  sheets (an application portfolio and migration costs).
* The test users' own skills (D353), as each would add them on My profile; a few have none yet.
* Protea build or buy (sample): marked complete, every phase complete.
* Fynbos Pet Insurance launch (sample): left as just set up.
* The organisation: the Architecture Board's members, organisation calendar events, links in the reference library's
  four folders, a vendor contracts sheet.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

KAROO = "Karoo Re cloud migration (sample)"
PROTEA_DONE = "Protea build or buy (sample)"
MARK = "Host core platforms on a managed cloud"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def run() -> list[str]:
    from .. import calendars as cl
    from .. import content_framework as cf
    from .. import governance as gv
    from .. import notify
    from .. import org_repository as orp
    from .. import permissions as perms
    from .. import project_org as po
    from .. import projects as pj
    from .. import reference_library as rl
    from .. import tracking_sheets as ts

    said: list[str] = []
    sa = _p("user_super_admin", ("super-admin",))
    pa, la, ma, ar = _p("user_project_admin"), _p("user_lead_architect"), _p("user_model_admin"), _p("user_architect")
    real_notify = notify.create
    notify.create = lambda *a, **k: None          # no notifications for seed data
    token = perms.current.set(sa)
    today = date.today()
    try:
        with pj.connections(True) as conn:
            user_skills(conn)
            karoo = conn.execute(text("SELECT guid::text FROM proj.projects WHERE name = :n"), {"n": KAROO}).scalar()
            if karoo and not conn.execute(text("SELECT 1 FROM proj.gov_records WHERE title = :t"), {"t": MARK}).first():
                _karoo(conn, karoo, sa, pa, la, ma, ar, today, gv, po, cl, cf, ts, pj)
                said.append(f"{KAROO}: governance, people, calendar, phases, sheets")
            protea = conn.execute(text("SELECT guid::text FROM proj.projects WHERE name = :n AND completed_at IS NULL"), {"n": PROTEA_DONE}).scalar()
            if protea:
                p = pj.project_row(conn, protea)
                for ph in [r["phase"] for r in conn.execute(text("SELECT DISTINCT phase FROM proj.steps WHERE project_id = :p AND NOT removed"), {"p": p["id"]}).mappings()]:
                    pj.mark_phase(conn, protea, sa, ph, True, "Sample: the project is complete.")
                pj.mark_project(conn, protea, sa, True)
                said.append(f"{PROTEA_DONE}: complete")
            if not conn.execute(text("SELECT 1 FROM proj.board_members")).first():
                for u, role in (("user_lead_architect", "Chair"), ("user_architect", "Member: application architecture"),
                                ("user_model_admin", "Member: data architecture"), ("user_project_admin", "Secretary")):
                    orp.board_set(conn, sa, u, role)
                for ev in ({"topic": "Architecture Board", "starts_on": str(today + timedelta(days=(3 - today.weekday()) % 7 + 7)), "at_time": "14:00",
                            "minutes": 90, "repeat": "monthly", "times": 12, "notes": "Decisions, dispensations and compliance reviews from the projects."},
                           {"topic": "Quarterly architecture strategy review", "starts_on": str(today + timedelta(days=30)), "at_time": "10:00",
                            "minutes": 120, "repeat": "monthly", "times": 4, "notes": "Every three months in practice: skip the months between."},
                           {"topic": "Enterprise architecture community day", "starts_on": str(today + timedelta(days=45)), "repeat": "none"}):
                    cl.add(conn, "org", sa, ev)
                said.append("Organisation: board members and calendar")
            if not conn.execute(text("SELECT 1 FROM proj.org_ref_entries WHERE kind = 'link' AND folder LIKE '% architectures'")).first():
                for folder, title, url, desc in (
                        ("Foundation architectures", "Architecture description standard (ISO/IEC/IEEE 42010)", "https://www.iso.org/standard/74393.html",
                         "How an architecture description is structured: stakeholders, concerns, viewpoints and views."),
                        ("Common systems architectures", "Cybersecurity framework", "https://www.nist.gov/cyberframework",
                         "A common reference for security architecture across the organisation."),
                        ("Industry architectures", "Insurance data standards", "https://www.acord.org/standards-architecture",
                         "Industry data standards and models for insurance."),
                        ("Organisation's own architectures", "Cloud landing zone pattern (sample)", "https://intranet.example.org/ea/patterns/cloud-landing-zone",
                         "Meridian's own reference pattern for a cloud landing zone (sample link).")):
                    rl.add_link(conn, sa, {"folder": folder, "title": title, "url": url, "description": desc, "source": "sample", "tags": ["sample"]})
                said.append("Organisation: reference library links")
            if not conn.execute(text("SELECT 1 FROM proj.sheets WHERE project_id IS NULL")).first():
                s = ts.create(conn, "org", sa, {"name": "Vendor contracts", "description": "Sample: the organisation's main technology contracts (all names invented).",
                                                "columns": ["Vendor", "Product or service", "Contract", "Start", "End", "Notice (days)", "Annual value (ZAR)", "Owner"]})
                rows = [("Atlas Cloud Services", "Cloud hosting", "C-2024-011", "2024-04-01", "2027-03-31", "90", "6 400 000", "CIO office"),
                        ("Kestrel Software", "Policy administration", "C-2021-004", "2021-07-01", "2026-06-30", "180", "4 100 000", "Life operations"),
                        ("Baobab Data", "Data warehouse", "C-2023-019", "2023-01-01", "2025-12-31", "90", "1 950 000", "Data office"),
                        ("Springbok Networks", "Wide area network", "C-2022-007", "2022-10-01", "2027-09-30", "120", "2 300 000", "Infrastructure"),
                        ("Umoya Security", "Security operations centre", "C-2025-002", "2025-02-01", "2028-01-31", "90", "3 200 000", "CISO"),
                        ("Fynbos Analytics", "Actuarial modelling", "C-2020-015", "2020-05-01", "2026-04-30", "180", "1 400 000", "Actuarial"),
                        ("Karoo Print", "Policy documents", "C-2019-030", "2019-09-01", "2026-08-31", "60", "650 000", "Operations"),
                        ("Protea Contact", "Contact centre platform", "C-2024-021", "2024-08-01", "2027-07-31", "90", "2 750 000", "Customer service"),
                        ("Meerkat Identity", "Identity and access", "C-2023-008", "2023-06-01", "2026-05-31", "90", "980 000", "CISO"),
                        ("Aloe Payments", "Payments gateway", "C-2022-013", "2022-03-01", "2027-02-28", "120", "1 200 000", "Finance")]
                cols = ["Vendor", "Product or service", "Contract", "Start", "End", "Notice (days)", "Annual value (ZAR)", "Owner"]
                ts.update(conn, "org", sa, s["id"], {"add": [dict(zip(cols, r, strict=True)) for r in rows]})
                said.append("Organisation: vendor contracts sheet")
    finally:
        perms.current.reset(token)
        notify.create = real_notify
    return said


def _karoo(conn, karoo, sa, pa, la, ma, ar, today, gv, po, cl, cf, ts, pj) -> None:
    from sqlalchemy import text as t
    p = pj.project_row(conn, karoo)
    signers = gv._signers(conn, p)
    if not signers:
        for u in ("user_lead_architect", "user_model_admin", "user_stakeholder"):
            conn.execute(t("INSERT INTO proj.signoff (project_id, phase, username) VALUES (:p, '', :u) ON CONFLICT DO NOTHING"), {"p": p["id"], "u": u})
        signers = gv._signers(conn, p)
    approvers = [_p(u) for u in signers]

    def rec(kind, title, status, html, **kw):
        r = gv.add(conn, karoo, pa, {"kind": kind, "title": title, "status": status, "html": f"<p>{html}</p>", "owner": kw.get("owner", "Lead architect"),
                                     "expires_on": kw.get("expires_on"), "related": kw.get("related", "")})
        return r["id"]
    # every approval state: approved by the sign-off people, approved with a reason, waiting, rejected, a draft
    d1 = rec("Decision", MARK, "Accepted", "Policy administration, claims and billing move to a managed cloud platform in the target state; the "
             "data centre lease is not renewed.", related="Target state model; Statement of Architecture Work")
    gv.send_for_approval(conn, karoo, pa, d1, "For the Architecture Board of this month.")
    for u in approvers[:max(1, (len(approvers) // 2) + 1)]:
        gv.decide(conn, karoo, u, d1, "approved", "Agreed.")
    d2 = rec("Decision", "Retire the legacy claims spreadsheet", "Accepted", "Claims tracking moves into the claims platform; the spreadsheet is archived.")
    gv.approve_with_evidence(conn, karoo, pa, d2, "Approved at the Architecture Board of 3 November (minutes in Sign-off evidence).")
    rec_d = rec("Dispensation", "Keep the actuarial engine on-premises until 2027", "Requested",
                "The actuarial engine stays on-premises for one more year-end; it does not follow the cloud-first principle until then.",
                expires_on=str(today + timedelta(days=20)), related="Principle: cloud first")
    gv.send_for_approval(conn, karoo, pa, rec_d, "Needed before the year-end freeze.")
    rec("Risk", "Lock-in to one cloud provider", "Open", "Moving three core platforms to one provider makes leaving it costly; exit plan to be written.")
    cmp = rec("Compliance assessment", "Claims platform design review", "Compliant with conditions",
              "The design follows the standards except for logging retention, to be fixed before go-live.")
    gv.approve_with_evidence(conn, karoo, pa, cmp, "Reviewed by the lead architect and the security architect.")
    iss = rec("Issue", "Data residency for policyholder records", "Open", "Policyholder records must stay in the country; the chosen region is to be confirmed.")
    gv.send_for_approval(conn, karoo, pa, iss)
    gv.decide(conn, karoo, approvers[0], iss, "rejected", "Log this as a risk with the region decision, not an issue.")
    cap = rec("Capability assessment", "Architecture capability maturity 2026", "Done", "Maturity level 2 of 5 overall; governance and repository use are the gaps.")
    gv.approve_with_evidence(conn, karoo, pa, cap, "Assessment workshop with the architecture team.")
    # its charter approved
    gv.save_charter(conn, karoo, sa, {"approve": True})
    # the project's people (names invented); a linked user's skills come from their own profile (D353)
    for name, role, user in (("Thandi Nkosi", "Lead architect", "user_lead_architect"),
                             ("Pieter van Wyk", "Project admin", "user_project_admin"),
                             ("Aisha Patel", "Application architect", "user_architect"),
                             ("Sipho Dlamini", "Data architect", "user_model_admin"),
                             ("Lerato Mokoena", "Security architect (vendor, not a user)", ""),
                             ("Johan Botha", "Business sponsor's delegate", "user_stakeholder")):
        po.add(conn, karoo, sa, {"name": name, "role": role, "username": user})
    # its calendar
    nxt = today + timedelta(days=(0 - today.weekday()) % 7)
    for ev in ({"topic": "Weekly architecture sync", "starts_on": str(nxt), "at_time": "09:30", "minutes": 45, "repeat": "weekly", "weekdays": [0],
                "times": 12},
               {"topic": "Phase gate review: Business Architecture", "starts_on": str(today + timedelta(days=14)), "at_time": "13:00", "minutes": 120},
               {"topic": "Target architecture walkthrough with the sponsor", "starts_on": str(today + timedelta(days=21)), "at_time": "11:00", "minutes": 60},
               {"topic": "Cloud cut-over rehearsal", "starts_on": str(today + timedelta(days=60))}):
        cl.add(conn, karoo, pa, ev)
    # phases and steps done
    for ph in ("P", "A"):
        if conn.execute(t("SELECT 1 FROM proj.steps WHERE project_id = :p AND phase = :ph AND NOT removed"), {"p": p["id"], "ph": ph}).first():
            for sid in [r["id"] for r in conn.execute(t("""SELECT id FROM proj.steps WHERE project_id = :p AND phase = :ph AND NOT removed
                                                         AND parent_step_id IS NULL AND done_at IS NULL ORDER BY seq"""), {"p": p["id"], "ph": ph}).mappings()]:
                pj.mark_step(conn, karoo, pa, sid, True, "Sample")
            pj.mark_phase(conn, karoo, pa, ph, True, "Sample: done.")
    for sid in [r["id"] for r in conn.execute(t("""SELECT id FROM proj.steps WHERE project_id = :p AND phase = 'B' AND NOT removed
                                                 AND parent_step_id IS NULL AND done_at IS NULL ORDER BY seq LIMIT 3"""), {"p": p["id"]}).mappings()]:
        pj.mark_step(conn, karoo, pa, sid, True, "Sample")
    # a deliverable placed in a second content framework area
    cls = cf.tag_list(conn, karoo, sa, "classes", q="Architecture Vision")["rows"]
    if cls:
        cf.place(conn, karoo, pa, "classes", [cls[0]["id"]], "add", ["vision.stakeholders"])
    # two tracking sheets
    cols = ["Application", "Business owner", "Hosting today", "Target hosting", "Annual cost (ZAR)", "TIME", "Wave", "Notes"]
    apps = [("Policy Administration System", "Life operations", "Data centre", "Managed cloud", "4 100 000", "Migrate", "2", "Largest move"),
            ("Claims Platform", "Claims", "Data centre", "Managed cloud", "2 600 000", "Invest", "1", "First to move"),
            ("Broker Portal", "Distribution", "Data centre", "Managed cloud", "900 000", "Migrate", "1", ""),
            ("Customer Portal", "Distribution", "Hosted", "Managed cloud", "750 000", "Invest", "1", ""),
            ("Legacy Claims Spreadsheet", "Claims", "Desktop", "Retired", "0", "Eliminate", "1", "Decision DEC-002"),
            ("Actuarial Engine", "Actuarial", "Data centre", "Data centre", "1 400 000", "Tolerate", "3", "Dispensation until 2027"),
            ("Billing Engine", "Finance", "Data centre", "Managed cloud", "1 100 000", "Migrate", "2", ""),
            ("Reinsurance Ledger", "Finance", "Data centre", "Managed cloud", "600 000", "Migrate", "2", ""),
            ("Document Generation", "Operations", "Hosted", "Managed cloud", "650 000", "Migrate", "2", ""),
            ("Data Warehouse", "Data office", "Data centre", "Managed cloud", "1 950 000", "Invest", "3", "Rebuilt as a lakehouse"),
            ("Identity Service", "Security", "Hosted", "Managed cloud", "980 000", "Invest", "1", "Needed by every wave"),
            ("Contact Centre", "Customer service", "Hosted", "Hosted", "2 750 000", "Tolerate", "-", "Out of scope"),
            ("Payments Gateway", "Finance", "Hosted", "Hosted", "1 200 000", "Tolerate", "-", "Out of scope"),
            ("Underwriting Rules", "Underwriting", "Data centre", "Managed cloud", "500 000", "Migrate", "3", ""),
            ("Reporting Server", "Finance", "Data centre", "Retired", "300 000", "Eliminate", "3", "Replaced by the lakehouse")]
    s1 = ts.create(conn, karoo, pa, {"name": "Application portfolio (working list)", "columns": cols,
                                     "description": "Sample: the applications in scope, before they are all in the model."})
    ts.update(conn, karoo, pa, s1["id"], {"add": [dict(zip(cols, a, strict=True)) for a in apps]})
    cc = ["Quarter", "Work package", "Budget (ZAR)", "Actual (ZAR)", "Variance (ZAR)", "Status"]
    costs = [("2026 Q3", "Landing zone", "1 500 000", "1 620 000", "-120 000", "Done"),
             ("2026 Q4", "Wave 1: claims and portals", "3 200 000", "2 950 000", "250 000", "In progress"),
             ("2027 Q1", "Wave 2: policy administration and billing", "4 800 000", "", "", "Planned"),
             ("2027 Q2", "Wave 3: data and actuarial", "2 600 000", "", "", "Planned"),
             ("2027 Q3", "Data centre exit", "900 000", "", "", "Planned")]
    s2 = ts.create(conn, karoo, pa, {"name": "Migration costs", "columns": cc, "description": "Sample: budget against actual by quarter."})
    ts.update(conn, karoo, pa, s2["id"], {"add": [dict(zip(cc, c, strict=True)) for c in costs]})


# the test users' own skills, as each would add them on My profile (D353); a few have none yet, to show that state
USER_SKILLS = {
    "user_lead_architect": ["TOGAF", "ArchiMate", "Enterprise architecture", "Cloud", "Insurance", "Architecture governance"],
    "user_architect": ["Application architecture", "Integration", "APIs", "Cloud", "ArchiMate"],
    "user_model_admin": ["Data modelling", "Data governance", "Data architecture", "ArchiMate"],
    "user_project_admin": ["Project management", "Planning", "Architecture governance"],
    "user_stakeholder": ["Claims", "Insurance", "Business process"],
    "user_global_architect": ["Enterprise architecture", "Business architecture", "Capability mapping", "TOGAF"],
    "user_model_creator": ["Metamodel design", "ArchiMate", "TOGAF"],
    "user_library_admin": ["Reference models", "Knowledge management"],
    "user_super_admin": ["Platform administration", "Security", "Identity"],
    "user_report_viewer": ["Reporting", "Portfolio management"],
}


def user_skills(conn) -> None:
    """Made once per user: a user who already has skills keeps them."""
    for user, tags in USER_SKILLS.items():
        conn.execute(text("""INSERT INTO proj.user_skills (username, skills, modified_by) VALUES (:u, CAST(:s AS text[]), :u)
                              ON CONFLICT (username) DO NOTHING"""), {"u": user, "s": tags})
