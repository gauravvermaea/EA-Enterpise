"""Key questions for the sample projects (owner, 9 Nov 2026, D341): laptop only, with the sample data, made once per
project (a project that has key questions already is left alone). Every name is invented.

Each sample project gets the questions its kind of work answers, in every state, so the Key questions tab can be tried
at once: open; answered (a summary pointing to the viewpoints, a page of the project, a document when there is one),
waiting for the stakeholder; accepted by user_stakeholder in the application; accepted as recorded by a contributor
for a stakeholder outside the application; rejected and opened again. Some answers use a placeholder viewpoint (a
text, or an empty file made in the project's files when Documents is up).
"""

from __future__ import annotations

from sqlalchemy import text

# a question: (question, asked by, expected answer or approach, viewpoints, what happens, answer, placeholder)
#   what happens: open | answered | accepted (user_stakeholder, in the application) | recorded (accepted, recorded for
#   the one who asks) | rejected (rejected with a reason, open again) | reopened (accepted, then opened again)
#   placeholder: None or {name, kind: text | file, file_type, description}
#   answer: rich text (HTML, cleaned on the way in) or plain text (one paragraph)
Q = tuple
GENERIC: list[Q] = [
    ("Which stakeholders does this work affect, and what does each need from it?", "Project sponsor",
     "A stakeholder map with each one's concerns, and the views that answer them.", ["VP-14"], "accepted",
     "The stakeholder map lists every group with its power, interest and concerns; each concern is mapped to the viewpoint "
     "that answers it. See the Stakeholders tab and the Stakeholder viewpoint.", None),
]
BY_TEMPLATE: dict[str, list[Q]] = {
    "transformation": [
        ("What is the impact of removing the legacy claims application?", "Chief Information Officer",
         "Show what integrates with it and which processes use it: an application cooperation view and a process-to-application map.",
         ["VP-11", "VP-08"], "accepted",
         "<p><b>Eleven interfaces and four claims processes use it.</b></p><ul><li>Seven interfaces move to the claims hub in "
         "the transition state; the other four retire with it.</li><li>First notice of loss and assessment are the processes "
         "to re-point first; payments and recoveries follow.</li></ul><p>See the application cooperation and usage views.</p>", None),
        ("What does the target look like, layer by layer?", "Head of Claims",
         "One layered view of the target: business, application and technology.", ["VP-05"], "recorded",
         "The layered view of the 2028 target: straight-through claims on the claims hub, with the document service and "
         "payments shared with policy administration.", None),
        ("In which order do we move, and what does each transition deliver?", "Chief Operating Officer",
         "A migration view through the transition state, and the work packages that deliver it.", ["VP-24", "VP-25"], "answered",
         "One transition state in 2027: the claims hub and digital first notice of loss go live; assessment and payments "
         "follow in 2028. The work packages are on the migration view.", None),
        ("What will it cost to run the claims estate after 2028?", "Chief Financial Officer",
         "A run-cost comparison of today against the target, from the application portfolio.", [], "rejected",
         "Run cost falls by a fifth once the legacy claims application is retired.",
         {"name": "Claims run-cost comparison", "kind": "file", "file_type": "xlsx",
          "description": "Today's and the target's run cost per application, from the portfolio."}),
        ("Which capabilities are weakest today?", "Head of Claims", "A capability map with today's maturity as a heat map.", ["VP-19"], "open", "", None),
    ],
    "document-as-is": [
        ("Which applications do we run, and who owns each?", "Chief Information Officer",
         "The application structure and the organisation that owns each application.", ["VP-02", "VP-01"], "accepted",
         "Forty-two applications, each with its business owner and support team; nine have no named owner and are flagged.", None),
        ("Where is our data held?", "Data protection officer", "The information structure and the applications that hold each data object.",
         ["VP-03"], "answered", "Policy and claims data sit in two systems; customer data is copied into five. The copies are listed with their owners.", None),
        ("What runs on which infrastructure?", "Head of Infrastructure", "A technology view of the data centre and the cloud tenancy.",
         ["VP-04"], "open", "", None),
    ],
    "new-product": [
        ("What will the pet insurance product offer, and through which channels?", "Head of Product",
         "A product view: the product, its services and the channels that sell it.", ["VP-07"], "accepted",
         "Two cover levels sold online and through vets' practices; claims are paid to the vet directly.", None),
        ("Which capabilities must we build, and which can we reuse from the group?", "Chief Operating Officer",
         "The capability map of the target, marking the capabilities the group already has.", ["VP-19"], "answered",
         "Underwriting, billing and claims payment are reused from Fynbos Commercial; vet network management is new.", None),
        ("How does the launch serve the group's strategy?", "Chief Executive", "Goal and outcome realisation for the launch.",
         ["VP-15", "VP-21"], "open", "", None),
    ],
    "copy-for-reports": [
        ("What should the board see each quarter?", "Company secretary", "One layered summary and three measures, the same every quarter.",
         ["VP-05"], "recorded", "The board pack's layered summary and the three measures were agreed with the company secretary.", None),
    ],
    "update-and-merge": [
        ("What changed in Karoo Digital since the last refresh?", "Head of Digital", "The changes in the child copy, before they merge back.",
         ["VP-05"], "answered", "Two new channels and the retirement of the old quote engine; see the layered view and the change log.", None),
    ],
    "scenario-planning": [
        ("Build or buy: which scenario serves the policy platform goal better?", "Board",
         "Goal realisation for each scenario, and the gaps each leaves.", ["VP-15", "VP-26"], "accepted",
         "Buying closes the gaps sooner and at lower risk; building keeps the pricing engine in house. The board chose to buy.", None),
        ("Which capabilities change in each scenario?", "Chief Operating Officer", "A capability map per scenario.", ["VP-19"], "accepted",
         "Policy administration and product configuration change in both; only building changes pricing.", None),
    ],
    "regulatory-change": [
        ("Which requirements does the conduct standard put on us?", "Head of Compliance",
         "The requirements, traced to the parts of the architecture that meet them.", ["VP-16"], "accepted",
         "Twenty-three requirements; nineteen are met today, four need changes to the advice and complaints processes.", None),
        ("Where are we not compliant today?", "Chief Risk Officer", "A gap view of today against the compliant target.", ["VP-26"], "answered",
         "The four gaps are in advice records, complaints turnaround and disclosure at sale.",
         None),
        ("How will we show the regulator we comply?", "Head of Compliance", "An evidence pack per requirement.", [], "open", "",
         {"name": "Regulator evidence pack outline", "kind": "file", "file_type": "docx",
          "description": "The evidence for each requirement, to fill in as the changes land."}),
    ],
    "cloud-migration": [
        ("What is the impact of moving the core platforms to the cloud?", "Chief Information Officer",
         "What runs where today and in the target, and what depends on it.", ["VP-04", "VP-13"], "accepted",
         "The core platforms move in three waves; the two batch interfaces to the reinsurance bureau need re-hosting first.", None),
        ("Which applications move in each wave?", "Head of Infrastructure", "The migration view and its work packages.", ["VP-24"], "recorded",
         "Wave 1: the eight stateless services; wave 2: policy and claims; wave 3: the data warehouse.", None),
        ("What is left in the data centre after the last wave?", "Chief Financial Officer", "A gap view of the data centre against the target.",
         ["VP-26"], "reopened", "Nothing but the archive server, which retires in 2029.", None),
    ],
    "app-rationalisation": [
        ("Which applications can we retire without hurting the business?", "Chief Information Officer",
         "Application usage by process, and the gaps retiring each one would leave.", ["VP-08", "VP-26"], "accepted",
         "<p>Fourteen applications can go without leaving a gap:</p><ul><li>nine are used by no process today;</li>"
         "<li>five serve only processes another application already serves.</li></ul><p>The gap view lists each one.</p>", None),
        ("What is the impact of removing an application?", "Head of Operations",
         "For any application: what integrates with it and which processes use it.", ["VP-11", "VP-08"], "answered",
         "The application cooperation view shows each application's interfaces; the usage view shows the processes. "
         "Together they are the impact check run before any retirement.", None),
        ("Which applications overlap?", "Enterprise architect", "The application structure grouped by the capability each serves.",
         ["VP-02"], "open", "", None),
    ],
    "operating-model": [
        ("Which services should the group share?", "Group Chief Executive", "The organisation and the processes each business runs, side by side.",
         ["VP-01", "VP-10"], "accepted", "Finance, HR and procurement are shared; each business keeps sales and claims.", None),
        ("What resources does the shared service centre need?", "Group Chief Financial Officer", "A resource map of the shared services.",
         ["VP-22"], "open", "", None),
    ],
    "capability-planning": [
        ("Which capabilities should we invest in first?", "Executive Committee",
         "The capability map with maturity and importance, and the value streams each serves.", ["VP-19", "VP-20"], "accepted",
         "Claims assessment and customer data management: both critical and at maturity 1.", None),
        ("What outcomes will the investments deliver?", "Chief Financial Officer", "Outcome realisation for each investment.", ["VP-21"], "answered",
         "Shorter claim cycles and fewer data errors, each with a measure and a date.", None),
    ],
    "health-check": [
        ("How healthy is Karoo Operations' architecture against the reference model?", "Chief Information Officer",
         "A layered view read against the reference model, and the principles it breaks.", ["VP-05", "VP-17"], "recorded",
         "Sound in the business layer; three principles broken in the application layer (duplicate customer data, no "
         "single sign-on, point-to-point interfaces).", None),
    ],
    "solution-architecture": [
        ("How does the broker portal fit with what we already run?", "Head of Broker Distribution",
         "The application cooperation view of the portal with the estate.", ["VP-11"], "accepted",
         "The portal calls policy administration and rating through the integration layer; nothing new is built in the core.", None),
        ("Which services must the portal realise?", "Product owner", "Service realisation from the broker's point of view.", ["VP-12"], "answered",
         "Quote, bind and endorse; claims notification follows in the second release.", None),
        ("Where will it be deployed?", "Head of Infrastructure", "Implementation and deployment of the portal.", ["VP-13"], "open", "",
         {"name": "Broker portal deployment notes", "kind": "text", "description": "To be replaced by the deployment view once the hosting choice is made."}),
    ],
    "due-diligence": [
        ("What would we take on if Fynbos buys Karoo Re?", "Group Chief Executive",
         "Karoo Re's applications and capabilities, and the gaps against the Fynbos group.", ["VP-02", "VP-19", "VP-26"], "accepted",
         "Karoo Re brings a sound reinsurance capability and nine applications, three of which duplicate the group's.", None),
        ("What would integration cost?", "Group Chief Financial Officer", "The gap view priced per gap.", ["VP-26"], "rejected",
         "About a year of work for one team.", None),
    ],
}
SAMPLE_PROJECT = [   # Protea Target Architecture 2028 (sample project): no template
    ("Which teams change in the 2028 target?", "Chief Operating Officer", "The organisation view, today against the target.",
     ["VP-01"], "answered", "Claims and policy servicing merge into one operations team; the broker desk moves to distribution.", None),
    ("How do our applications work together in 2028?", "Chief Information Officer", "The application cooperation view of the target.",
     ["VP-11"], "accepted", "Through the integration layer only: the twelve point-to-point interfaces are gone.", None),
]


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def run() -> list[str]:
    from .. import key_questions as kq
    from .. import notify
    from .. import permissions as perms
    from .. import projects as pj

    said: list[str] = []
    la, ar, pa, st = _p("user_lead_architect"), _p("user_architect"), _p("user_project_admin"), _p("user_stakeholder")
    real_notify = notify.create
    notify.create = lambda *a, **k: None          # no notifications for seed data
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    try:
        with pj.connections(True) as conn:
            rows = conn.execute(text("""SELECT guid::text AS g, name, template_code FROM proj.projects
                                         WHERE (name LIKE '%(sample)' OR name LIKE '%(sample project)')
                                           AND status = 'active' AND coalesce(base_kind, '') = ''
                                           AND NOT EXISTS (SELECT 1 FROM proj.key_questions q WHERE q.project_id = projects.id)
                                         ORDER BY name""")).mappings().all()
            for r in rows:
                qs = (BY_TEMPLATE.get(r["template_code"] or "") or SAMPLE_PROJECT) + GENERIC
                n = _one_project(conn, kq, pj, r["g"], qs, la, ar, pa, st)
                said.append(f"{r['name']}: {n} key questions")
    finally:
        perms.current.reset(token)
        notify.create = real_notify
    return said


def _one_project(conn, kq, pj, pg: str, qs: list[Q], la, ar, pa, st) -> int:
    p = pj.project_row(conn, pg)
    doc = conn.execute(text("""SELECT guid::text FROM proj.documents WHERE project_id = :p AND item_id IS NOT NULL AND file_name <> ''
                                ORDER BY id LIMIT 1"""),
                       {"p": p["id"]}).scalar()
    for i, (question, asked_by, approach, vps, what, answer, ph) in enumerate(qs):
        who = la if i % 2 == 0 else ar
        out = kq.add_question(conn, pg, who, {"question": question, "asked_by": asked_by, "approach": approach, "viewpoints": vps})
        qid = out["id"]
        if ph:
            kq.add_placeholder(conn, pg, who, {**ph, "questions": [qid]})
        if what == "open":
            continue
        # what the answer points to besides its viewpoints (they link by themselves): a deliverable of the project
        # when there is one, the minutes for a decision taken at the steering committee, the repository otherwise
        links = []
        if what == "recorded":
            links.append({"url": "https://intranet.example.org/ea/steering-committee/minutes", "label": "Steering committee minutes (sample link)"})
        if not vps and not ph:
            links.append({"url": f"#/projects/{pg}/repository", "label": "The project's repository"})
        body = {"answer": answer, "links": links, **({"documents": [doc]} if doc and i == 0 else {})}
        kq.answer(conn, pg, who, qid, body)
        if what == "accepted":
            kq.decide(conn, pg, st, qid, "accepted", "Agreed in the review.")
        elif what == "recorded":
            kq.record(conn, pg, pa, qid, {"by": asked_by, "decision": "accepted", "note": "Accepted by email after the steering committee."})
        elif what == "rejected":
            kq.decide(conn, pg, st, qid, "rejected", "Not enough: show the figures behind it, per application.")
        elif what == "reopened":
            kq.decide(conn, pg, st, qid, "accepted", "Agreed.")
            kq.reopen(conn, pg, la, qid, "The archive server's retirement moved to 2030: the answer needs updating.")
    try:                            # the empty files of file placeholders, when Documents is up (otherwise from the tab)
        kq.make_files(conn, pg, la)
    except Exception:  # noqa: BLE001 - Documents not up yet
        pass
    return len(qs)
