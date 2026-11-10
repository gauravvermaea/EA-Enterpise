"""Scenario planning with AI (phase 27.1, D364; built 10 Nov 2026, D490 to D495).

In an architecture project, an assistant (through MCP, the guided prompt *plan scenarios*) or a person (the project's
Scenarios tab) works with the project's **scenario models** beside its **baseline**:

* **overview**: the baseline (the project model whose role is Current state, or one chosen) and every scenario model
  (role Scenario; Target state models too, marked as such), each with its figures (entities, applications,
  capabilities and how many are covered, total annual cost, technology past or near end of life, applications marked
  Eliminate, orphans) and its comparison with the baseline: what it adds, changes and retires, by entity type, and the
  capabilities those changes touch (the impact). Each figure is worked out as the person sees the model: its committed
  content **with the person's own uncommitted changes on top** (their what-ifs), so a what-if shows at once.
* **make a scenario** (preview, then confirm): a separate copy, or a child that can merge back, of the baseline (or any
  project model), joined to the project with the role Scenario; the baseline is **tagged first** ("Before scenario
  <name>") so the comparison can always be made again from the same starting point. The project's people get their
  roles on it, as when the project made its models (D261).
* **what-ifs** (preview, then confirm): "retire X", "retire X and replace it with Y" (Y new, of X's type unless said, or
  an existing entity; X's relationships move to Y where the metamodel allows; X goes), "add X", "change X". All are kept
  as **the person's uncommitted changes** in the scenario model (D165): only they see them until they commit them, and
  they can be thrown away from the Changes tab.
* **assessment** (preview, then confirm): the comparison as it is now, a score and notes per scenario, a recommendation
  and the scenario recommended, kept with the project (Scenarios tab, SCN-001...), as a **Word document** (downloadable,
  and filed in the project's repository when an item is given or one fits), and optionally as a **governance log
  decision** (a draft, or sent for approval to the project's sign-off people).

Everything runs as the person, within their permissions: reading needs a role on the project and the right to read the
models; making scenarios, what-ifs and assessments need a contributing role (not Stakeholder). Nothing here is logic in
the database (D248).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from . import commits as cm
from . import compare as cmp
from . import kpis as kp
from . import permissions as perms
from . import projects as pj
from . import repository as repo
from . import tags as tg
from .metamodel_edit import EditError

SCENARIO_ROLES = ("scenario", "target")
BASELINE_ROLE = "current"
WHAT_IFS = ("retire", "replace", "add", "change")
DOMAINS_THAT_COVER = ("Business", "Application", "Technology", "Data")
CAPABILITY_TYPES = ("capability",)
MAX_LIST = 60


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    return float(v) if isinstance(v, (int, float, Decimal)) else v


def preview_hash(tool: str, args: dict) -> str:
    """What a preview's confirm token is bound to (D458): the tool and its arguments, confirm and why left out."""
    keep = {k: v for k, v in args.items() if k not in ("confirm", "why")}
    return hashlib.sha256(json.dumps([tool, keep], sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- the project's models
def project_models(pc, project: Any, user) -> tuple[dict, list[dict]]:
    """The project and its models with their roles (guid, name, role, how)."""
    p = pj.project_row(pc, project)
    pj._need(pc, p, user, "read")
    links = _rows(pc, "SELECT model_guid::text AS id, how, role, role_seq FROM proj.project_models WHERE project_id = :p", p=p["id"])
    core = pj.core(pc)
    out = []
    for link in links:
        try:
            m = repo.get_model(core, link["id"])
        except repo.NotFound:
            continue                         # a model the person may not read, or gone
        out.append({"id": str(m["id"]), "name": m["name"], "role": link["role"] or "", "how": link["how"], "_m": m})
    out.sort(key=lambda x: ({"current": 0, "scenario": 1, "target": 2}.get(x["role"], 3), x["name"].lower()))
    return p, out


def _pick(models: list[dict], ref: Any, what: str) -> dict:
    key = str(ref or "").strip().lower()
    for m in models:
        if key in (m["id"].lower(), m["name"].lower()):
            return m
    names = ", ".join(m["name"] for m in models) or "none"
    raise EditError(f"{ref} is not a model of this project ({what}); its models: {names}.", 404)


def baseline_of(models: list[dict], baseline: Any = None) -> dict:
    if baseline:
        return _pick(models, baseline, "baseline")
    cur = [m for m in models if m["role"] == BASELINE_ROLE]
    if not cur:
        raise EditError("This project has no Current state model: say which model is the baseline.", 409)
    return cur[0]


# ---------------------------------------------------------------- figures of one model, as the person sees it
def _coverage(conn, model_id: int) -> tuple[int, int, list[str]]:
    """Capabilities, how many are covered (related to anything in the business, application, technology or data
    domains), and the names of those not covered."""
    caps = _rows(conn, """SELECT e.id, e.name FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                           WHERE e.model_id = :m AND NOT e.is_deleted AND lower(t.code) = ANY (CAST(:c AS text[]))""",
                 m=model_id, c=list(CAPABILITY_TYPES))
    if not caps:
        return 0, 0, []
    covered = {r["id"] for r in _rows(conn, """
        SELECT c.id FROM core.entities c
          JOIN core.relationships r ON (r.source_entity_id = c.id OR r.target_entity_id = c.id) AND NOT r.is_deleted
          JOIN core.entities o ON o.id = CASE WHEN r.source_entity_id = c.id THEN r.target_entity_id ELSE r.source_entity_id END
                              AND NOT o.is_deleted
          JOIN core.entity_types ot ON ot.id = o.entity_type_id JOIN core.layers l ON l.id = ot.layer_id
         WHERE c.model_id = :m AND c.id = ANY (CAST(:ids AS bigint[])) AND l.name = ANY (CAST(:d AS text[]))""",
                                        m=model_id, ids=[c["id"] for c in caps], d=list(DOMAINS_THAT_COVER))}
    return len(caps), len(covered), sorted(c["name"] for c in caps if c["id"] not in covered)


def figures_now(conn, m: dict) -> dict:
    """A model's figures as stored now (on the connection as it is: inside an overlay, with the person's changes)."""
    data = kp.load(conn, m["_id"])
    std = {(c, d): v for c, d, v in kp.standard_values(data)}
    apps = sum(int(v or 0) for (c, _d), v in std.items() if c == "applications_by_lifecycle")
    eliminate = int(std.get(("applications_by_time", "Eliminate")) or 0)
    caps, covered, uncovered = _coverage(conn, m["_id"])
    past, soon = int(std.get(("eol_technology", "")) or 0), int(std.get(("eol_technology_soon", "")) or 0)
    return {"entities": int(std.get(("entities", "")) or 0), "applications": apps, "capabilities": caps,
            "capabilities_covered": covered, "capabilities_not_covered": uncovered[:MAX_LIST],
            "total_cost": _num(std.get(("total_cost", ""))), "technology_past_end_of_life": past,
            "technology_end_of_life_within_12_months": soon, "applications_to_eliminate": eliminate,
            "orphans": int(std.get(("orphans", "")) or 0),
            "risks": past + soon + (caps - covered)}


def figures(core, m: dict, user) -> dict:
    """A model's figures as the person sees it (their uncommitted changes on top)."""
    pending = cm.has_pending(core, str(m["id"]), user.username) if cm.uses_commits(m) else False
    out = cm.overlay(core, str(m["id"]), user.username, lambda c: figures_now(c, m))
    out = {k: v for k, v in out.items() if k not in ("pending_changes",)}
    out["with_my_changes"] = bool(pending)
    return out


def _side(core, m: dict, user) -> dict:
    """A model ready to compare, as the person sees it. Display IDs are left out of the matching: a scenario is a copy of
    the baseline, so its entities are matched by id, by origin (the entity it was copied from) and by type and name;
    two entities made separately in each model that happen to get the same display ID are not the same entity."""
    side = cm.overlay(core, str(m["id"]), user.username, lambda c: tg.side_of_model(c, str(m["id"])))
    ents = side["snapshot"]["entities"]
    side["snapshot"] = {**side["snapshot"], "entities": {g: {**e, "display_id": None} for g, e in ents.items()}}
    return side


# ---------------------------------------------------------------- comparison with the baseline
def comparison(core, base: dict, scen: dict, user, detail: bool = False) -> dict:
    """What the scenario adds, changes and retires against the baseline, and the capabilities that touches."""
    left, right = _side(core, base["_m"], user), _side(core, scen["_m"], user)
    res = cmp.compare(left, right, None)
    items = res["items"]
    changed = [i for i in items if i["status"] != "kept"]
    by_type = [{"entity_type": s["name"], "domain": s["domain"], "new": s["new"], "changed": s["changed"], "retired": s["eliminated"]}
               for s in res["summary"] if s["new"] or s["changed"] or s["eliminated"]]
    # the impact: capabilities related (on either side) to anything added, changed or retired, or changed themselves
    lents, rents = left["snapshot"]["entities"], right["snapshot"]["entities"]
    touched_l = {i["left"]["guid"] for i in changed if i.get("left")}
    touched_r = {i["right"]["guid"] for i in changed if i.get("right")}

    def caps_near(snap: dict, ents: dict, touched: set) -> set[str]:
        out = set()
        for r in snap["relationships"].values():
            for a, b in ((r["source"], r["target"]), (r["target"], r["source"])):
                if a in touched and (ents.get(b) or {}).get("type_code", "").lower() in CAPABILITY_TYPES:
                    out.add(ents[b]["name"])
        for g in touched:
            if (ents.get(g) or {}).get("type_code", "").lower() in CAPABILITY_TYPES:
                out.add(ents[g]["name"])
        return out
    impact = sorted(caps_near(left["snapshot"], lents, touched_l) | caps_near(right["snapshot"], rents, touched_r))

    def names(status: str) -> list[dict]:
        return [{"name": i["name"], "type": i["entity_type_name"],
                 **({"changes": [c["label"] for c in i["changes"]][:8]} if status == "changed" else {})}
                for i in changed if i["status"] == status][:MAX_LIST if not detail else 2000]
    out = {"baseline": base["name"], "scenario": scen["name"],
           "totals": {"added": res["totals"]["new"], "changed": res["totals"]["changed"], "retired": res["totals"]["eliminated"],
                      "kept": res["totals"]["kept"]},
           "relationships": {"added": res["relationship_totals"]["new"], "retired": res["relationship_totals"]["eliminated"],
                             "renamed": res["relationship_totals"]["changed"]},
           "by_type": by_type, "added": names("new"), "changed": names("changed"), "retired": names("eliminated"),
           "capabilities_touched": impact[:MAX_LIST], "capabilities_touched_count": len(impact)}
    if detail:
        out["relationship_changes"] = [r for r in res["relationships"] if r["status"] != "kept"][:2000]
    return out


def _delta(a: dict, b: dict) -> dict:
    keys = ("entities", "applications", "capabilities", "capabilities_covered", "total_cost", "technology_past_end_of_life",
            "technology_end_of_life_within_12_months", "applications_to_eliminate", "orphans", "risks")
    out = {}
    for k in keys:
        x, y = a.get(k), b.get(k)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            out[k] = round(y - x, 2)
    return out


def suggested_score(base_fig: dict, fig: dict) -> dict:
    """A starting score out of 10 (5 = no better, no worse than the baseline) with its reasons; the person (or the
    assistant, with the person) gives the score that is kept."""
    s, why = 5.0, []
    bc, sc = base_fig.get("total_cost") or 0, fig.get("total_cost") or 0
    if bc:
        pct = (sc - bc) / bc * 100
        step = max(-2.0, min(2.0, -pct / 10))
        if abs(pct) >= 1:
            s += step
            why.append(f"annual cost {'down' if pct < 0 else 'up'} {abs(pct):.0f}%")
    dr = (fig.get("risks") or 0) - (base_fig.get("risks") or 0)
    if dr:
        s += max(-2.0, min(2.0, -dr * 0.5))
        why.append(f"{abs(dr)} {'fewer' if dr < 0 else 'more'} risks (end of life, capabilities not covered)")
    dc = (fig.get("capabilities_covered") or 0) - (base_fig.get("capabilities_covered") or 0)
    if dc:
        s += max(-1.5, min(1.5, dc * 0.5))
        why.append(f"{abs(dc)} {'more' if dc > 0 else 'fewer'} capabilities covered")
    da = (fig.get("applications") or 0) - (base_fig.get("applications") or 0)
    if da:
        s += max(-1.0, min(1.0, -da * 0.25))
        why.append(f"{abs(da)} {'fewer' if da < 0 else 'more'} applications")
    return {"score": round(max(0.0, min(10.0, s)), 1), "reasons": why or ["no difference in the figures"]}


def overview(pc, project: Any, user, baseline: Any = None) -> dict:
    """The baseline and every scenario with figures, comparison, impact and a suggested score; the assessments kept."""
    p, models = project_models(pc, project, user)
    core = pj.core(pc)
    out: dict[str, Any] = {"project": {"id": str(p["guid"]), "name": p["name"]},
                           "models": [{k: m[k] for k in ("id", "name", "role", "how")} for m in models]}
    try:
        base = baseline_of(models, baseline)
    except EditError as exc:
        out.update(baseline=None, scenarios=[], message=str(exc), assessments=assessments(pc, p, user))
        return out
    bfig = figures(core, base["_m"], user)
    out["baseline"] = {"id": base["id"], "name": base["name"], "role": base["role"], "figures": bfig}
    scen = []
    for m in models:
        if m["id"] == base["id"] or m["role"] not in SCENARIO_ROLES:
            continue
        try:
            fig = figures(core, m["_m"], user)
            comp = comparison(core, base, m, user)
        except EditError as exc:
            scen.append({"id": m["id"], "name": m["name"], "role": m["role"], "error": str(exc)})
            continue
        scen.append({"id": m["id"], "name": m["name"], "role": m["role"], "how": m["how"], "figures": fig,
                     "difference": _delta(bfig, fig), "comparison": comp, "suggested": suggested_score(bfig, fig),
                     "link": f"/#/metamodel/{m['id']}"})
    out["scenarios"] = scen
    out["assessments"] = assessments(pc, p, user)
    pj_roles = pj._need(pc, p, user, "read")
    out["may_contribute"] = bool(pj_roles & (pj.CONTRIBUTORS | {"super-admin"}))
    if not scen:
        out["message"] = "No scenario models yet: make one (a copy or a child of the baseline) to compare."
    return out


def compare_one(pc, project: Any, user, scenario: Any, baseline: Any = None) -> dict:
    """One scenario against the baseline in full: every element added, changed and retired, and relationship changes."""
    p, models = project_models(pc, project, user)
    base = baseline_of(models, baseline)
    scen = _pick(models, scenario, "scenario")
    core = pj.core(pc)
    bfig, fig = figures(core, base["_m"], user), figures(core, scen["_m"], user)
    return {"baseline": {"name": base["name"], "figures": bfig}, "scenario": {"name": scen["name"], "figures": fig},
            "difference": _delta(bfig, fig), "suggested": suggested_score(bfig, fig),
            "comparison": comparison(core, base, scen, user, detail=True)}


# ---------------------------------------------------------------- making a scenario model
def make_scenario(pc, project: Any, user, name: str, start: str = "copy", source: Any = None, confirm: bool = False) -> dict:
    """A scenario model: a separate copy (start copy) or a child that merges back (start child) of the baseline or of
    `source` (a project model). Preview unless confirm; the source is tagged first."""
    from . import model_ops as mo
    p, models = project_models(pc, project, user)
    pj._need(pc, p, user, "contribute")
    name = " ".join((name or "").split())
    if not name:
        raise EditError("Give the scenario model a name.")
    if start not in ("copy", "child"):
        raise EditError('start is "copy" (a separate copy) or "child" (a copy that can merge back into its source).')
    src = _pick(models, source, "source") if source else baseline_of(models)
    core = pj.core(pc)
    if _one(core, "SELECT 1 AS x FROM core.models WHERE lower(name) = lower(:n) AND NOT is_deleted", n=name):
        raise EditError(f"A model called {name} exists already: choose another name.", 409)
    if start == "child" and src["_m"]["kind"] != "project":
        raise EditError("Only a project model can have a child: use start=\"copy\".")
    tag_name = f"Before scenario {name}"[:120]
    plan = {"will": [f"tag {src['name']} as it is now ('{tag_name}'), so the comparison can be made again from the same point",
                     f"make '{name}', a {'separate copy' if start == 'copy' else 'child (it can merge back)'} of {src['name']} "
                     "with its metamodel and content",
                     f"join it to {p['name']} with the role Scenario; the project's people get their roles on it"],
            "source": src["name"], "name": name, "start": start}
    if not confirm:
        return {"preview": plan, "confirm": "Call again with confirm=true to make it (after the person says yes)."}
    tag = tg.create_tag(core, src["id"], user, tag_name, f"Taken before the scenario model {name} was made (project {p['name']}).")
    m = {"how": "derived" if start == "child" else "created", "start": "copy", "from": src["id"], "copy": "content", "name": name,
         "role": "scenario", "description": f"A scenario of {src['name']} for the project {p['name']}."}
    mm, cp = pj.link_model(pc, p, user, m)
    if cp:
        mo.run_copy(core, cp["source"], cp["target"], user.username)
    members = {(r["username"], r["role"]) for r in _rows(pc, "SELECT username, role FROM proj.members WHERE project_id = :p", p=p["id"])}
    pj.model_roles(pc, [mm], members, user)
    made = repo.get_model(core, str(mm["id"]))
    return {"model": str(made["id"]), "name": made["name"], "entities": made.get("entity_count"), "tag": tag.get("name") or tag_name,
            "link": f"/#/metamodel/{made['id']}",
            "message": f"{made['name']} is ready as a scenario of {p['name']}; {src['name']} was tagged '{tag_name}' first."}


# ---------------------------------------------------------------- what-ifs, as the person's uncommitted changes
def _entity(core, m: dict, ref: Any, what: str) -> dict:
    try:
        eid = repo._as_guid(ref)
        row = None
        if eid:
            row = _one(core, """SELECT e.id, e.guid::text AS guid, e.name, t.code AS type_code FROM core.entities e
                                 JOIN core.entity_types t ON t.id = e.entity_type_id
                                WHERE e.model_id = :m AND e.guid = CAST(:g AS uuid) AND NOT e.is_deleted""", m=m["_id"], g=str(eid))
        if not row:
            rows = _rows(core, """SELECT e.id, e.guid::text AS guid, e.name, t.code AS type_code FROM core.entities e
                                   JOIN core.entity_types t ON t.id = e.entity_type_id
                                  WHERE e.model_id = :m AND NOT e.is_deleted AND (lower(e.name) = lower(:n) OR e.display_id = :n)
                                  ORDER BY e.id""", m=m["_id"], n=str(ref or "").strip())
            if len(rows) > 1:
                raise EditError(f"More than one entity is called {ref} in {m['name']}: give its display ID or id.", 409)
            row = rows[0] if rows else None
    except repo.NotFound:
        row = None
    if not row:
        raise EditError(f"No {what} '{ref}' in {m['name']} (as you see it, with your uncommitted changes).", 404)
    return row


def _relationships_of(core, m: dict, eid: int) -> list[dict]:
    return _rows(core, """SELECT r.guid::text AS guid, rt.code AS type, r.name, s.guid::text AS source, t.guid::text AS target,
                                 s.id = :e AS outgoing, CASE WHEN s.id = :e THEN t.name ELSE s.name END AS other
                            FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                            JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted
                            JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted
                           WHERE r.model_id = :m AND NOT r.is_deleted AND (r.source_entity_id = :e OR r.target_entity_id = :e)
                           ORDER BY rt.code, other""", m=m["_id"], e=eid)


def _plan_what_ifs(core, m: dict, user, actions: list[dict]) -> tuple[list[tuple[str, dict]], list[str]]:
    """The changes for the what-ifs (worked out on the scenario as the person sees it) and what they mean in words."""
    if not isinstance(actions, list) or not actions:
        raise EditError("Give the what-ifs as a list, e.g. [{\"retire\": \"Policy Administration System\", \"replace_with\": "
                        "\"Policy Suite\"}, {\"retire\": \"Underwriting Rules Engine\"}].")
    if len(actions) > 50:
        raise EditError("At most 50 what-ifs at a time.")

    def plan(conn):
        items: list[tuple[str, dict]] = []
        said: list[str] = []
        made: dict[str, str] = {}
        for a in actions:
            if not isinstance(a, dict):
                raise EditError("Each what-if is an object such as {\"retire\": \"X\"}.")
            if a.get("retire"):
                x = _entity(conn, m, a["retire"], "entity to retire")
                rels = _relationships_of(conn, m, x["id"])
                new = a.get("replace_with")
                if new:
                    try:
                        y = _entity(conn, m, new, "replacement")
                        yg, yname, ynew = y["guid"], y["name"], False
                    except EditError:
                        yname = " ".join(str(new).split())
                        yg = made.get(yname.lower()) or str(uuid.uuid4())
                        ynew = yname.lower() not in made
                        if ynew:
                            made[yname.lower()] = yg
                            data = {"guid": yg, "entity_type": a.get("type") or x["type_code"], "name": yname,
                                    "description": a.get("description") or f"Replaces {x['name']} (what-if).",
                                    "values": a.get("values") or {}}
                            items.append(("entity.create", {"data": data}))
                    moved = 0
                    for r in rels:
                        src, tgt = (yg, r["target"]) if r["outgoing"] else (r["source"], yg)
                        if src == tgt:
                            continue
                        items.append(("relationship.create", {"data": {"relationship_type": r["type"], "source": src, "target": tgt,
                                                                       "name": r["name"] or ""}}))
                        moved += 1
                    said.append(f"replace {x['name']} with {yname}{' (new, ' + (a.get('type') or x['type_code']) + ')' if ynew else ''}: "
                                f"{moved} relationships move to it where the metamodel allows; {x['name']} is retired")
                else:
                    said.append(f"retire {x['name']} ({len(rels)} relationships go with it)")
                items.append(("entity.delete", {"entity": x["guid"]}))
            elif a.get("add"):
                nm = " ".join(str(a["add"]).split())
                if not a.get("type"):
                    raise EditError(f"Say the entity type of {nm} (type).")
                g = str(uuid.uuid4())
                made[nm.lower()] = g
                items.append(("entity.create", {"data": {"guid": g, "entity_type": a["type"], "name": nm,
                                                         "description": a.get("description") or "", "values": a.get("values") or {}}}))
                for rel in a.get("relationships") or []:
                    other = _entity(conn, m, rel.get("to") or rel.get("from"), "related entity")
                    src, tgt = (g, other["guid"]) if rel.get("to") else (other["guid"], g)
                    items.append(("relationship.create", {"data": {"relationship_type": rel.get("type"), "source": src, "target": tgt,
                                                                   "name": rel.get("name") or ""}}))
                said.append(f"add {nm} ({a['type']}) with {len(a.get('relationships') or [])} relationships")
            elif a.get("change"):
                x = _entity(conn, m, a["change"], "entity to change")
                data = {k: a[k] for k in ("name", "description", "values") if a.get(k) is not None}
                if not data:
                    raise EditError(f"Say what changes in {x['name']} (name, description or values).")
                items.append(("entity.update", {"entity": x["guid"], "data": data}))
                said.append(f"change {x['name']}: {', '.join(data if 'values' not in data else [*(k for k in data if k != 'values'), *data['values']])}")
            else:
                raise EditError("A what-if is one of: {retire, replace_with?, type?}, {add, type, relationships?}, {change, name?, "
                                "description?, values?}.")
        return items, said
    return cm.overlay(core, str(m["id"]), user.username, plan)


def apply_what_ifs(pc, project: Any, user, scenario: Any, actions: list[dict], confirm: bool = False) -> dict:
    """What-ifs in a scenario model, as the person's uncommitted changes. Preview unless confirm."""
    p, models = project_models(pc, project, user)
    pj._need(pc, p, user, "contribute")
    scen = _pick(models, scenario, "scenario")
    if scen["role"] not in SCENARIO_ROLES:
        raise EditError(f"{scen['name']} is the project's {scen['role'] or 'model'}, not a scenario: what-ifs go in a scenario model "
                        "(make one first).", 409)
    core = pj.core(pc)
    m = scen["_m"]
    if not cm.uses_commits(m):
        raise EditError(f"{m['name']} does not keep uncommitted changes: what-ifs need a working model.", 409)
    roles = set(perms.model_roles(core, user.username, m["id"]))
    if not (perms.SUPER_ADMIN in user.roles or roles & set(perms.MODEL_PERMISSIONS["model.content"])):
        raise EditError(f"Changing {m['name']} needs a role that changes its content (Architect, Committer, Model Sub Admin or "
                        "Model Admin).", 403)
    items, said = _plan_what_ifs(core, m, user, actions)
    if not confirm:
        return {"scenario": m["name"], "preview": said, "changes": len(items),
                "confirm": "Call again with confirm=true to keep them as your uncommitted changes (after the person says yes)."}
    res = cm.record_many(core, str(m["id"]), user.username, items)
    failed = [{"change": op, "error": r["error"]} for (op, _a), r in zip(items, res, strict=True) if not r.get("ok")]
    kept = sum(1 for r in res if r.get("ok"))
    return {"scenario": m["name"], "done": said, "kept": kept, "not_kept": failed[:50],
            "message": f"{kept} change{'s' if kept != 1 else ''} kept as your uncommitted changes in {m['name']} (only you see them until "
                       "you commit them; throw them away from its Changes tab)." +
                       (f" {len(failed)} could not be made (for example a relationship the metamodel does not allow)." if failed else "")}


# ---------------------------------------------------------------- assessments
def _out(r: dict) -> dict:
    sc = r["scenarios"] if isinstance(r["scenarios"], list) else json.loads(r["scenarios"] or "[]")
    return {"id": str(r["guid"]), "ref": r["ref"], "title": r["title"], "baseline": r["baseline_name"], "scenarios": sc,
            "recommendation": r["recommendation"], "recommended": r["recommended_name"] or "", "created_by": r["created_by"],
            "created_at": r["created_at"], "via": r["via"], "document": r.get("doc_guid"), "document_name": r.get("doc_name") or "",
            "decision": r.get("gov_ref") and {"ref": r["gov_ref"], "title": r.get("gov_title"), "approval": r.get("gov_approval"),
                                               "id": r.get("gov_guid")}}


_ASSESS_SQL = """SELECT a.*, d.guid::text AS doc_guid, coalesce(nullif(d.title, ''), d.file_name) AS doc_name, g.ref AS gov_ref,
                        g.title AS gov_title, g.approval AS gov_approval, g.guid::text AS gov_guid
                   FROM proj.scenario_assessments a LEFT JOIN proj.documents d ON d.id = a.document_id
                   LEFT JOIN proj.gov_records g ON g.id = a.gov_record_id WHERE a.project_id = :p"""


def assessments(pc, p: dict, user) -> list[dict]:
    pj._need(pc, p, user, "read")
    return [_out(r) for r in _rows(pc, _ASSESS_SQL + " ORDER BY a.created_at DESC, a.id DESC", p=p["id"])]


def get_assessment(pc, project: Any, user, aid: str) -> dict:
    p = pj.project_row(pc, project)
    pj._need(pc, p, user, "read")
    r = _one(pc, _ASSESS_SQL + " AND a.guid = CAST(:g AS uuid)", p=p["id"], g=aid) if repo._as_guid(aid) else None
    if not r:
        r = _one(pc, _ASSESS_SQL + " AND a.ref = :g", p=p["id"], g=str(aid))
    if not r:
        raise EditError("No such assessment in this project.", 404)
    return _out(r)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"
    return "" if v is None else str(v)


def assessment_docx(a: dict, project_name: str) -> bytes:
    from .gaps import _p, _table, docx_from
    body = [_p(a["title"], "Title"), _p(f"{a['ref']} · project {project_name} · baseline {a['baseline']} · by {a['created_by']} · "
                                        f"{str(a['created_at'])[:16]}")]
    body.append(_p("Recommendation", "Heading1"))
    if a.get("recommended"):
        body.append(_p(f"Recommended: {a['recommended']}", bold=True))
    for para in re.split(r"\n\s*\n", a.get("recommendation") or "") or [""]:
        body.append(_p(para.strip()))
    rows = [["Scenario", "Score (0-10)", "Added", "Changed", "Retired", "Annual cost", "Applications", "Capabilities covered", "Risks"]]
    for s in a["scenarios"]:
        f, c = s.get("figures") or {}, (s.get("comparison") or {}).get("totals") or {}
        rows.append([s["name"], _fmt(s.get("score")), _fmt(c.get("added")), _fmt(c.get("changed")), _fmt(c.get("retired")),
                     _fmt(f.get("total_cost")), _fmt(f.get("applications")),
                     f"{_fmt(f.get('capabilities_covered'))} of {_fmt(f.get('capabilities'))}", _fmt(f.get("risks"))])
    base = a.get("baseline_figures") or (a["scenarios"][0].get("baseline_figures") if a["scenarios"] else None) or {}
    if base:
        rows.append([f"{a['baseline']} (baseline)", "", "", "", "", _fmt(base.get("total_cost")), _fmt(base.get("applications")),
                     f"{_fmt(base.get('capabilities_covered'))} of {_fmt(base.get('capabilities'))}", _fmt(base.get("risks"))])
    body.append(_p("The scenarios compared", "Heading1"))
    body.append(_table(rows))
    for s in a["scenarios"]:
        body.append(_p(s["name"], "Heading2"))
        if s.get("notes"):
            body.append(_p(s["notes"]))
        comp = s.get("comparison") or {}
        for key, label in (("added", "Added"), ("retired", "Retired"), ("changed", "Changed")):
            lst = comp.get(key) or []
            if lst:
                body.append(_p(f"{label}: " + ", ".join(f"{x['name']} ({x['type']})" for x in lst[:40]) +
                               (" and more" if len(lst) > 40 else "")))
        if comp.get("capabilities_touched"):
            body.append(_p("Capabilities touched: " + ", ".join(comp["capabilities_touched"][:40])))
    body.append(_p("Figures are worked out as the author saw each model when the assessment was recorded, with their own "
                   "uncommitted changes (what-ifs) included."))
    return docx_from(body)


def _repository_item(pc, p: dict, item: str | None) -> dict | None:
    if item:
        it = _one(pc, """SELECT * FROM proj.items WHERE project_id = :p AND (guid::text = :i OR lower(name) = lower(:i)) LIMIT 1""",
                  p=p["id"], i=item)
        if not it:
            raise EditError(f"No document class '{item}' in this project.", 404)
        return it
    for pat in ("%architecture definition%", "%option%", "%scenario%", "%assessment%"):
        it = _one(pc, """SELECT * FROM proj.items WHERE project_id = :p AND lower(name) LIKE :n AND chosen
                         ORDER BY id LIMIT 1""", p=p["id"], n=pat)
        if it:
            return it
    return None


def record_assessment(pc, project: Any, user, title: str, scenarios: list[dict], recommendation: str = "", recommended: Any = None,
                      baseline: Any = None, governance: str = "none", item: str | None = None, confirm: bool = False,
                      via: str = "mcp") -> dict:
    """Keeps an assessment: the comparison as it is now, each scenario's score and notes, the recommendation. Preview unless
    confirm. governance: none | draft (a Decision in the governance log) | approval (sent to the sign-off people)."""
    from . import governance as gv
    p, models = project_models(pc, project, user)
    pj._need(pc, p, user, "contribute")
    title = " ".join((title or "").split())[:300]
    if not title:
        raise EditError("Give the assessment a title.")
    if governance not in ("none", "draft", "approval"):
        raise EditError('governance is "none", "draft" (a decision in the governance log) or "approval" (sent for approval).')
    if not isinstance(scenarios, list) or not scenarios:
        raise EditError("Give the scenarios assessed: [{model, score (0 to 10), notes}].")
    base = baseline_of(models, baseline)
    core = pj.core(pc)
    bfig = figures(core, base["_m"], user)
    rows = []
    for s in scenarios:
        if not isinstance(s, dict) or not s.get("model"):
            raise EditError("Each scenario is {model, score, notes}.")
        m = _pick(models, s["model"], "scenario")
        score = s.get("score")
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError) as exc:
                raise EditError("A score is a number from 0 to 10.") from exc
            if not 0 <= score <= 10:
                raise EditError("A score is a number from 0 to 10.")
        fig = figures(core, m["_m"], user)
        rows.append({"model": m["id"], "name": m["name"], "role": m["role"], "score": score, "notes": (s.get("notes") or "").strip()[:4000],
                     "figures": fig, "difference": _delta(bfig, fig), "suggested": suggested_score(bfig, fig),
                     "comparison": comparison(core, base, m, user)})
    rec = _pick(models, recommended, "recommended scenario") if recommended else None
    it = _repository_item(pc, p, item)
    plan = {"title": title, "baseline": base["name"],
            "scenarios": [{"name": r["name"], "score": r["score"], "suggested": r["suggested"]["score"],
                           "added": r["comparison"]["totals"]["added"], "changed": r["comparison"]["totals"]["changed"],
                           "retired": r["comparison"]["totals"]["retired"], "difference": r["difference"]} for r in rows],
            "recommended": rec["name"] if rec else "", "governance": governance,
            "document": f"a Word document filed in '{it['name']}'" if it else "a Word document kept with the assessment (download)"}
    if not confirm:
        return {"preview": plan, "confirm": "Call again with confirm=true to record it (after the person says yes)."}
    n = (_one(pc, "SELECT count(*) AS n FROM proj.scenario_assessments WHERE project_id = :p", p=p["id"]) or {"n": 0})["n"]
    ref = f"SCN-{int(n) + 1:03d}"
    for r in rows:
        r["baseline_figures"] = bfig
    row = _one(pc, """INSERT INTO proj.scenario_assessments (project_id, ref, title, baseline_guid, baseline_name, scenarios, recommendation,
                                                            recommended_guid, recommended_name, created_by, via)
                      VALUES (:p, :ref, :t, CAST(:bg AS uuid), :bn, CAST(:sc AS jsonb), :rec, CAST(:rg AS uuid), :rn, :u, :via)
                      RETURNING id, guid::text AS guid, created_at""",
               p=p["id"], ref=ref, t=title, bg=base["id"], bn=base["name"], sc=json.dumps(rows, default=str), rec=(recommendation or "").strip(),
               rg=rec["id"] if rec else None, rn=rec["name"] if rec else "", u=user.username, via=via)
    said = [f"{ref} {title} is kept with the project (Scenarios tab)."]
    # the Word document, filed in the project's repository when it can be
    a = get_assessment(pc, p["guid"], user, row["guid"])
    if it:
        try:
            data = assessment_docx(a, p["name"])
            fname = re.sub(r"[^\w .()-]+", "-", f"{ref} {title}")[:120] + ".docx"
            up = pj.upload(pc, p["guid"], user, str(it["guid"]), fname, data, title=f"{ref} {title}")
            doc = _one(pc, "SELECT id FROM proj.documents WHERE guid = CAST(:g AS uuid)", g=up["id"])
            if doc:
                pc.execute(text("UPDATE proj.scenario_assessments SET document_id = :d WHERE id = :i"), {"d": doc["id"], "i": row["id"]})
            said.append(f"Filed as a Word document in '{it['name']}'.")
        except Exception as exc:  # noqa: BLE001 - Documents down or the repository not built: the assessment is kept anyway
            said.append(f"Not filed in the repository ({exc}); download it from the Scenarios tab.")
    # a decision in the governance log
    if governance != "none":
        lines = [f"<p><strong>{ref}</strong>: {title}.</p>"]
        if rec:
            lines.append(f"<p>Recommended scenario: <strong>{rec['name']}</strong>.</p>")
        lines += [f"<p>{x}</p>" for x in re.split(r"\n\s*\n", (recommendation or "").strip()) if x.strip()]
        lines.append("<ul>" + "".join(f"<li>{r['name']}: score {r['score'] if r['score'] is not None else '-'}</li>" for r in rows) + "</ul>")
        rec_out = gv.add(pc, p["guid"], user, {"kind": "Decision", "title": f"Choose a scenario: {title}"[:300], "html": "".join(lines),
                                               "owner": user.username, "related": "; ".join(r["name"] for r in rows)[:1000]})
        g = _one(pc, "SELECT id FROM proj.gov_records WHERE guid = CAST(:g AS uuid)", g=rec_out["id"])
        pc.execute(text("UPDATE proj.scenario_assessments SET gov_record_id = :g WHERE id = :i"), {"g": g["id"], "i": row["id"]})
        said.append(f"Logged as decision {rec_out['ref']} (a draft).")
        if governance == "approval":
            try:
                said.append(gv.send_for_approval(pc, p["guid"], user, rec_out["id"], f"Scenario assessment {ref}.")["message"])
            except EditError as exc:
                said.append(f"Not sent for approval: {exc}")
    out = get_assessment(pc, p["guid"], user, row["guid"])
    out["message"] = " ".join(said)
    return out


def assessment_file(pc, project: Any, user, aid: str) -> tuple[bytes, str]:
    p = pj.project_row(pc, project)
    a = get_assessment(pc, project, user, aid)
    return assessment_docx(a, p["name"]), re.sub(r"[^\w .()-]+", "-", f"{a['ref']} {a['title']}")[:120] + ".docx"

