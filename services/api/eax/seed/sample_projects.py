"""Sample architecture projects, one for each project template (owner, 7 Nov 2026). Laptop only, with the sample data.

Between them they show every way a model joins a project, so each can be tried and told apart:
  * referred to (read only): the model itself, the project only reads it
  * added (worked on): the model itself, the project changes it
  * a separate copy of a model, as it is now or as it was at one of its tags (no link back)
  * a child of a project model (a copy that keeps the link and can merge back)
  * a new model, empty, from a root metamodel
The template's decisions (purpose, depth, domains, phases, viewpoints, steps left out) are applied as the wizard does.
Each project is made once (skipped when one of that name exists); model copies run here, one after another.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# (template, project name, description, quorum, models, goals)
# a model: (how, model, role, extra)
#   how: refer | add | child | copy | tag | empty; model: an existing model's name (for empty: the root metamodel)
#   extra: {"name": the new model's name, "tag": the tag's name, "home": True for the primary working model}
SAMPLES: list[tuple[str, str, str, int | None, list[tuple], list[dict]]] = [
    ("transformation", "Protea Claims Transformation 2028 (sample)",
     "Protea's claims from today's platform to a straight-through target, through one transition state.", 2,
     [("add", "Protea Insurance (demo estate)", "current", {}),
      ("child", "Protea Insurance (demo estate)", "target", {"name": "Protea claims target 2028", "home": True}),
      ("child", "Protea Insurance (demo estate)", "transition", {"name": "Protea claims transition 2027"}),
      ("refer", "Insurance reference model", "reference", {})],
     [{"name": "Pay claims faster", "outcomes": [{"name": "Median claim cycle under 5 days", "measure": "median days", "target_date": "2028-06-30"}]}]),
    ("document-as-is", "Karoo Re as-is documentation (sample)",
     "Write down Karoo Re's architecture as it is, read against the principles model.", None,
     [("add", "Karoo Re (independent)", "current", {}), ("refer", "root-principle-model", "reference", {})], []),
    ("new-product", "Fynbos Pet Insurance launch (sample)",
     "A new pet insurance product for Fynbos, designed from the reference model on an empty model.", None,
     [("refer", "Insurance reference model", "reference", {}),
      ("empty", "ArchiMate 4", "target", {"name": "Fynbos pet insurance target", "home": True})],
     [{"name": "Launch pet insurance in 2027", "outcomes": [{"name": "10 000 policies in the first year", "measure": "policies", "target_date": "2027-12-31"}]}]),
    ("copy-for-reports", "Fynbos Board reporting pack (sample)",
     "A separate copy of Fynbos Commercial, shaped for the board's reports without touching the original.", None,
     [("copy", "Fynbos Commercial", "working-copy", {"name": "Fynbos Commercial for the board pack"})], []),
    ("update-and-merge", "Karoo Digital refresh (sample)",
     "Update Karoo Digital in a child copy and merge the changes back when they are agreed.", 1,
     [("child", "Karoo Digital (lean)", "working-copy", {"name": "Karoo Digital refresh 2027"})], []),
    ("scenario-planning", "Protea build or buy (sample)",
     "Two scenarios for Protea's policy administration: build in house, or buy a package.", None,
     [("add", "Protea Insurance (demo estate)", "current", {}),
      ("copy", "Protea Insurance (demo estate)", "scenario", {"name": "Protea scenario A: build", "home": True}),
      ("copy", "Protea Insurance (demo estate)", "scenario", {"name": "Protea scenario B: buy"}),
      ("refer", "Insurance reference model", "reference", {})],
     [{"name": "Choose the policy platform", "outcomes": [{"name": "Decision taken by the board", "measure": "board resolution", "target_date": "2027-03-31"}]}]),
    ("regulatory-change", "Fynbos Life conduct standard (sample)",
     "Bring Fynbos Life in line with the new conduct standard.", 2,
     [("add", "Fynbos Life", "current", {}), ("child", "Fynbos Life", "target", {"name": "Fynbos Life compliant target", "home": True}),
      ("refer", "Insurance reference model", "reference", {})],
     [{"name": "Comply with the conduct standard", "outcomes": [{"name": "No findings at the next review", "measure": "findings", "target_date": "2027-09-30"}]}]),
    ("cloud-migration", "Karoo Re cloud migration (sample)",
     "Karoo Re's applications to the cloud, from its 2026 baseline tag, through one transition.", None,
     [("add", "Karoo Re (independent)", "current", {}),
      ("tag", "Karoo Re (independent)", "target", {"name": "Karoo Re cloud target", "tag": "Baseline 2026", "home": True}),
      ("child", "Karoo Re (independent)", "transition", {"name": "Karoo Re cloud transition"}),
      ("refer", "root-principle-model", "reference", {})],
     [{"name": "Leave the data centre", "outcomes": [{"name": "All workloads in the cloud", "measure": "% of workloads", "target_date": "2028-12-31"}]}]),
    ("app-rationalisation", "Sample insurer application rationalisation (sample)",
     "Fewer applications for the sample insurer: retire, replace or keep each one.", None,
     [("add", "Sample insurance model", "current", {}),
      ("child", "Sample insurance model", "target", {"name": "Sample insurer rationalised", "home": True})],
     [{"name": "Lower the cost of running applications", "outcomes": [{"name": "A third fewer applications", "measure": "applications", "target_date": "2028-06-30"}]}]),
    ("operating-model", "Fynbos group operating model (sample)",
     "A shared operating model for the Fynbos group: what is shared and what each business keeps.", None,
     [("add", "Fynbos Mutual (group)", "current", {}),
      ("child", "Fynbos Mutual (group)", "target", {"name": "Fynbos group operating model target", "home": True}),
      ("empty", "ArchiMate 4", "transition", {"name": "Fynbos group operating model transition"})],
     [{"name": "Share services across the group", "outcomes": [{"name": "Shared services for finance and HR", "measure": "services shared", "target_date": "2028-03-31"}]}]),
    ("capability-planning", "Protea capability-based planning 2027 (sample)",
     "Protea's capabilities, the gaps to close, and the investments to close them.", None,
     [("add", "Protea part", "current", {}),
      ("child", "Protea part", "target", {"name": "Protea capability target 2027", "home": True})],
     [{"name": "Invest where capabilities are weakest", "outcomes": [{"name": "Every critical capability at maturity 3", "measure": "maturity level", "target_date": "2027-12-31"}]}]),
    ("health-check", "Karoo Operations architecture health check (sample)",
     "An assessment of Karoo Operations against the reference model: read only, nothing is changed.", None,
     [("refer", "Karoo Operations (maintenance)", "reference", {}), ("refer", "Insurance reference model", "reference", {})], []),
    ("solution-architecture", "Protea broker portal (sample)",
     "The solution architecture for Protea's new broker portal, worked on in a child of the estate.", 1,
     [("refer", "Protea Insurance (demo estate)", "reference", {}),
      ("child", "Protea Insurance (demo estate)", "working-copy", {"name": "Protea broker portal solution", "home": True})],
     [{"name": "Brokers quote and bind online", "outcomes": [{"name": "Half of new business through the portal", "measure": "% of new business", "target_date": "2027-12-31"}]}]),
    ("due-diligence", "Fynbos acquires Karoo Re (sample)",
     "Due diligence on Karoo Re for Fynbos: its architecture as found, and a separate copy to plan the merged estate.", None,
     [("add", "Karoo Re (independent)", "current", {}), ("refer", "Fynbos Mutual (group)", "reference", {}),
      ("copy", "Karoo Re (independent)", "target", {"name": "Karoo Re in the Fynbos group", "home": True})],
     [{"name": "Decide whether to buy", "outcomes": [{"name": "Recommendation to the board", "measure": "report delivered", "target_date": "2027-02-28"}]}]),
]

TAGS = [("Karoo Re (independent)", "Baseline 2026", "Karoo Re as it was at the start of 2026 (sample tag).")]


def _model_id(core, name: str) -> str | None:
    return core.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted ORDER BY id LIMIT 1"), {"n": name}).scalar()


def _model_link(core, how: str, model: str, role: str, extra: dict) -> dict | None:
    src = _model_id(core, model)
    if not src:
        return None
    out: dict[str, Any] = {"role": role, "home": bool(extra.get("home"))}
    if how in ("refer", "add"):
        out.update(how="referred" if how == "refer" else "added", model=src)
    elif how == "child":
        out.update(how="derived", start="child", **{"from": src}, copy="content", name=extra["name"])
    elif how in ("copy", "tag"):
        out.update(how="created", start="copy", **{"from": src}, copy="content", name=extra["name"])
        if how == "tag":
            tag = core.execute(text("""SELECT t.guid::text FROM core.model_tags t JOIN core.models m ON m.id = t.model_id
                                         WHERE m.guid = CAST(:m AS uuid) AND t.name = :n"""), {"m": src, "n": extra["tag"]}).scalar()
            if not tag:
                return None
            out["tag"] = tag
    elif how == "empty":
        out.update(how="created", start="empty", **{"from": src}, copy="metamodel", name=extra["name"])
    return out


def payload(conn, tpl: dict, name: str, description: str, quorum, models: list[dict], goals: list[dict]) -> dict:
    """The wizard's choices for a project made from a template (as the wizard's applyTemplate does)."""
    from .. import permissions
    s = tpl["spec"]
    phases = s.get("phases")
    from .. import projects as pj
    items = [r["id"] for r in pj._rows(conn, """SELECT id FROM proj.lib_items WHERE NOT retired AND default_pick
                                                  AND (CAST(:ph AS text[]) IS NULL OR phase = ANY (CAST(:ph AS text[])))""",
                                       ph=phases)] if not s.get("items") else list(s["items"])
    home = next((m for m in models if m.get("home")), None)
    return {
        "name": name, "purpose": s.get("purpose") or "project", "description": description, "template": tpl["code"],
        "scope": {"breadth": "", "depth": s.get("depth") or "", "domains": s.get("domains") or [], "start": "2027-01-01",
                  "end": "2027-12-31", "horizon": "2030", "notes": ""},
        "sponsor": {"name": "Jane Mokoena", "role": "Chief Operating Officer", "contact": "", "asks": [],
                    "notes_html": "<p>Sample sponsor: wants a monthly one-page update.</p>"},
        "models": models, "viewpoints": s.get("viewpoints") or [], "items": items,
        "removed_steps": [{"library_id": int(k), "reason": v or "Not needed in this kind of project"} for k, v in (s.get("removed_steps") or {}).items()],
        "goals": goals if (home and s.get("goals", True)) else [],
        "members": [{"username": u, "role": r} for u, r in permissions.PROJECT_TEST_ROLES],
        "signoff": {"": ["user_lead_architect", "user_stakeholder", "user_model_admin"]}, "signoff_quorum": quorum,
        "libraries": ["EA Explorer"],
        "stakeholders": _sample_stakeholders(s),
        **_several_templates(conn, items),
    }


def _several_templates(conn, items: list[str]) -> dict:
    """Document classes with several documents from templates (owner, 8 Nov 2026), so they can be seen in every sample
    project: the first three chosen classes with templates get their own template plus up to two more of the same
    phase from the EA Explorer library; and a class of the project's own, made from three templates of its phase."""
    from .. import projects as pj
    rows = pj._rows(conn, """SELECT t.id, t.item_id, li.phase FROM proj.lib_templates t
                               JOIN proj.template_libraries l ON l.id = t.library_id JOIN proj.lib_items li ON li.id = t.item_id
                              WHERE l.name = 'EA Explorer' AND t.item_id IS NOT NULL ORDER BY li.phase, t.id""")
    by_phase: dict[str, list[dict]] = {}
    for r in rows:
        by_phase.setdefault(r["phase"], []).append(r)
    templates: dict[str, list[int]] = {}
    for item in items:
        mine = [r for r in rows if r["item_id"] == item]
        if not mine:
            continue
        others = [r["id"] for r in by_phase.get(mine[0]["phase"], []) if r["item_id"] != item][:2]
        if not others:
            continue
        templates[item] = [r["id"] for r in mine] + others
        if len(templates) == 3:
            break
    out: dict = {"templates": templates, "placeholders": {k: False for k in templates}}
    phase_a = [r["id"] for r in by_phase.get("A", [])][:3]
    if phase_a:
        out["own_items"] = [{"phase": "A", "name": "Vision briefing pack (sample)", "kind": "Artifact", "templates": phase_a,
                             "note": "Three documents made from templates for the opening briefing: a class with several documents.",
                             "areas": ["vision.architecture_vision", "vision.stakeholders"]}]
    return out


def _sample_stakeholders(spec: dict) -> list[dict]:
    """The template's suggested stakeholders, with a sample position, engagement and next contact (D294)."""
    out = []
    for n, x in enumerate(spec.get("stakeholders") or []):
        r = {**x, "disrupt": x.get("power") or "M", "understanding_now": "L" if n % 3 else "M", "understanding_needed": "H" if x.get("interest") == "H" else "M",
             "commitment_now": "M" if n % 2 else "L", "commitment_needed": "H" if x.get("power") == "H" else "M",
             "support_needed": x.get("power") or "M", "frequency": "monthly" if x.get("power") == "H" else "at each phase gate",
             "channel": "steering committee" if x.get("power") == "H" else "email update", "owner": "user_lead_architect",
             "next_contact": "2026-12-01"}
        out.append(r)
    return out


def run() -> list[str]:
    """Makes the sample projects that are not there yet; returns what it made (or skipped and why)."""
    from .. import model_ops as mo
    from .. import permissions as perms
    from .. import project_templates as pt
    from .. import projects as pj
    from .. import tags as tg

    admin = perms.Principal("user_super_admin", ("super-admin",))
    maker = perms.Principal("user_project_admin", ("user",))
    token = perms.current.set(admin)        # the database sees a Super Admin for the copies and tags
    said: list[str] = []
    try:
        with pj.connections() as conn:
            core = pj.core(conn)
            for model, tag, note in TAGS:
                mid = _model_id(core, model)
                if mid and not core.execute(text("""SELECT 1 FROM core.model_tags t JOIN core.models m ON m.id = t.model_id
                                                     WHERE m.guid = CAST(:m AS uuid) AND t.name = :n"""), {"m": mid, "n": tag}).first():
                    tg.create_tag(core, mid, admin, tag, note)
        for code, name, description, quorum, models, goals in SAMPLES:
            with pj.connections() as conn:
                if conn.execute(text("SELECT 1 FROM proj.projects WHERE name = :n"), {"n": name}).first():
                    continue
                core = pj.core(conn)
                try:
                    tpl = pt.get(conn, code)
                except Exception:  # noqa: BLE001 - the template was retired or renamed
                    said.append(f"{name}: no template {code}")
                    continue
                links = [x for x in (_model_link(core, *m) for m in models) if x]
                if not links:
                    said.append(f"{name}: none of its models is here")
                    continue
                out = pj.create(conn, maker, payload(conn, tpl, name, description, quorum, links, goals), sample=True)
                for c in out.get("copies") or []:       # model content copies, here (no job runner needed)
                    mo.run_copy(conn, c["source"], c["target"], admin.username)
                p = pj.project_row(conn, out["project"]["id"])
                from .. import project_work as pw
                pend = p.get("pending_goals")
                if pend and pend not in ("[]", []):
                    pw.write_goals(conn, pj.project_row(conn, out["project"]["id"]), maker, pend if isinstance(pend, list) else __import__("json").loads(pend))
                    conn.execute(text("UPDATE proj.projects SET pending_goals = '[]' WHERE id = :p"), {"p": p["id"]})
                said.append(f"{name}: made")
    finally:
        perms.current.reset(token)
    return said
