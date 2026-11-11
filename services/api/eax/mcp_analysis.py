"""Analysis and clean-up through MCP (phases 26/27, D459, D485): the data an assistant needs to answer "what is affected
if we retire X?", "where do applications overlap?", "what does each capability cost?", "what runs on technology past its
end of life?", "where are the single points of failure?", "what changed since the last tag?", "why did the quality score
drop?", and to clean a model up (orphans, untidy names, bulk fixes).

The server ships no language model (D2): these tools compute from the model as it is (eax.tags.snapshot) and give the
facts with links; the assistant reasons about them and explains. The pure functions (impact, rationalise, cost_rollup,
technology_risk, single_points, heat_map, tidy_suggestions, orphans) take a snapshot and need no database.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from . import commits as cm
from . import kpis, mcp_ops
from . import repository as repo
from .mcp_server import _run, mcp, permissions
from .metamodel_edit import EditError

# who depends on whom, by relationship type (ArchiMate 4): for these the TARGET depends on the source (it is served,
# realised, assigned, reached or triggered by it); for the structural ones the WHOLE (source) depends on its parts.
TARGET_DEPENDS = {"serving", "realization", "assignment", "access", "flow", "triggering"}
SOURCE_DEPENDS = {"composition", "aggregation"}
APPS = kpis.APPLICATION_TYPES
TECH = kpis.TECHNOLOGY_TYPES
BEHAVIOUR = {"applicationfunction", "applicationservice", "applicationprocess", "applicationinterface", "businessprocess",
             "businessfunction", "businessservice", "process", "function", "service"}
CAPABILITIES = {"capability"}
FIT = ("functionalfit", "technicalfit")


# ---------------------------------------------------------------- helpers on a snapshot
def _low(s: Any) -> str:
    return str(s or "").lower()


def _val(e: dict, codes) -> Any:
    vals = {k.lower(): v for k, v in (e.get("values") or {}).items()}
    for c in codes:
        if vals.get(c) not in (None, ""):
            return vals[c]
    return None


def _num(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", "").replace(" ", "").lstrip("R$€£"))
    except (InvalidOperation, ValueError):
        return None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _brief(e: dict, link_model: str | None = None) -> dict:
    out = {"id": e["guid"], "name": e["name"], "type": e["entity_type"], "display_id": e.get("display_id")}
    if link_model:
        out["link"] = f"/#/metamodel/{link_model}/entity/{e['guid']}"
    return out


def edges(snap: dict) -> list[dict]:
    return list(snap["relationships"].values())


def dependents_of(snap: dict) -> dict[str, list[tuple[str, dict]]]:
    """For each entity, the entities that depend on it, with the relationship."""
    dep: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for r in edges(snap):
        t = _low(r["type_code"])
        if t in TARGET_DEPENDS:
            dep[r["source"]].append((r["target"], r))
        elif t in SOURCE_DEPENDS:
            dep[r["target"]].append((r["source"], r))
    return dep


# ---------------------------------------------------------------- impact
def impact(snap: dict, start: str, depth: int = 6, model: str | None = None) -> dict:
    """What is affected if `start` goes: everything depending on it, step by step, with the path; and what it is only
    associated with (shown, not followed)."""
    ents = snap["entities"]
    if start not in ents:
        raise EditError("That entity is not in the model.", 404)
    dep = dependents_of(snap)
    seen = {start: None}
    q = deque([(start, 0)])
    rows = []
    while q:
        cur, d = q.popleft()
        if d >= depth:
            continue
        for nxt, r in dep.get(cur, []):
            if nxt in seen or nxt not in ents:
                continue
            seen[nxt] = cur
            q.append((nxt, d + 1))
            path, x = [], nxt
            while x is not None:
                path.append(ents[x]["name"])
                x = seen[x]
            rows.append({**_brief(ents[nxt], model), "step": d + 1, "because": f"{ents[cur]['name']} {r.get('verb') or r['relationship_type']} it"
                         if _low(r["type_code"]) in TARGET_DEPENDS else f"it is made of {ents[cur]['name']}", "path": " ← ".join(path)})
    related = []
    for r in edges(snap):
        if _low(r["type_code"]) in TARGET_DEPENDS | SOURCE_DEPENDS or start not in (r["source"], r["target"]):
            continue
        other = r["target"] if r["source"] == start else r["source"]
        if other in ents:
            related.append({**_brief(ents[other], model), "relationship": r["relationship_type"]})
    by_type: dict[str, int] = defaultdict(int)
    for x in rows:
        by_type[x["type"]] += 1
    return {"entity": _brief(ents[start], model), "affected": rows, "affected_by_type": dict(sorted(by_type.items())),
            "also_related": related[:100], "depth": depth,
            "how": "Followed what depends on it: serving, realization, assignment, access, flow and triggering point from the "
                   "provider to what depends on it; composition and aggregation from a part to its whole."}


# ---------------------------------------------------------------- application rationalisation
def _supporting_apps(snap: dict) -> dict[str, set[str]]:
    """For each capability, the applications supporting it: related directly, or through one behaviour element
    (an application function or service, a process) that realises or serves it."""
    ents = snap["entities"]
    adj: dict[str, set[str]] = defaultdict(set)
    for r in edges(snap):
        adj[r["source"]].add(r["target"])
        adj[r["target"]].add(r["source"])
    out: dict[str, set[str]] = defaultdict(set)
    for g, e in ents.items():
        if _low(e["type_code"]) not in CAPABILITIES:
            continue
        for n in adj[g]:
            t = _low(ents.get(n, {}).get("type_code"))
            if t in APPS:
                out[g].add(n)
            elif t in BEHAVIOUR:
                out[g] |= {a for a in adj[n] if _low(ents.get(a, {}).get("type_code")) in APPS}
    return out


def time_suggestion(e: dict) -> tuple[str, str] | None:
    """A TIME suggestion from functional and technical fit (1 to 5): both good invest; good function, poor technology
    migrate; poor function, good technology tolerate; both poor eliminate."""
    f, t = (_num(_val(e, [c])) for c in FIT)
    if f is None or t is None:
        return None
    good_f, good_t = f >= 3, t >= 3
    s = {(True, True): "Invest", (True, False): "Migrate", (False, True): "Tolerate", (False, False): "Eliminate"}[(good_f, good_t)]
    return s, f"functional fit {f}, technical fit {t}"


def rationalise(snap: dict, model: str | None = None) -> dict:
    ents = snap["entities"]
    sup = _supporting_apps(snap)
    caps = []
    for g, apps in sup.items():
        rows = []
        for a in sorted(apps, key=lambda x: ents[x]["name"]):
            e = ents[a]
            sug = time_suggestion(e)
            rows.append({**_brief(e, model), "time": _val(e, kpis.TIME_ATTRS), "lifecycle": _val(e, kpis.LIFECYCLE_ATTRS),
                         "annual_cost": _val(e, kpis.COST_ATTRS), "suggested_time": sug[0] if sug else None,
                         "suggested_because": sug[1] if sug else None})
        caps.append({**_brief(ents[g], model), "applications": rows, "overlap": len(rows) > 1})
    caps.sort(key=lambda c: (-len(c["applications"]), c["name"]))
    apps_all = [e for e in ents.values() if _low(e["type_code"]) in APPS]
    supported = set().union(*sup.values()) if sup else set()
    differs = []
    for e in apps_all:
        sug = time_suggestion(e)
        now = _val(e, kpis.TIME_ATTRS)
        if sug and now and str(now).strip().lower() != sug[0].lower():
            differs.append({**_brief(e, model), "time": now, "suggested_time": sug[0], "because": sug[1]})
    return {"capabilities_with_overlap": [c for c in caps if c["overlap"]], "capabilities": caps[:300],
            "applications_supporting_no_capability": [_brief(e, model) for e in apps_all if e["guid"] not in supported][:200],
            "time_differs_from_fit": differs[:200],
            "how": "Applications support a capability when related to it directly, or through one application function or "
                   "service or a process. TIME suggestions come from functional and technical fit (3 or more is good)."}


# ---------------------------------------------------------------- cost
def cost_rollup(snap: dict, group_type: str = "Capability", depth: int = 2, model: str | None = None) -> dict:
    """The annual cost of what supports each entity of group_type (within `depth` relationships), counted in full for
    every group it supports and also shared equally between them; plus cost supporting no group."""
    ents = snap["entities"]
    adj: dict[str, set[str]] = defaultdict(set)
    for r in edges(snap):
        adj[r["source"]].add(r["target"])
        adj[r["target"]].add(r["source"])
    groups = [g for g, e in ents.items() if _low(e["type_code"]) == _low(group_type) or _low(e["entity_type"]) == _low(group_type)]
    costed = {g: _num(_val(e, kpis.COST_ATTRS)) for g, e in ents.items()}
    costed = {g: c for g, c in costed.items() if c}
    reach: dict[str, set[str]] = {}
    for g in groups:
        seen, frontier = {g}, {g}
        for _ in range(max(1, min(depth, 4))):
            frontier = {n for f in frontier for n in adj[f] if n not in seen and _low(ents.get(n, {}).get("type_code")) not in CAPABILITIES}
            seen |= frontier
        reach[g] = {x for x in seen if x in costed}
    share: dict[str, int] = defaultdict(int)
    for items in reach.values():
        for x in items:
            share[x] += 1
    rows = []
    for g in groups:
        full = sum((costed[x] for x in reach[g]), Decimal(0))
        shared = sum((costed[x] / share[x] for x in reach[g]), Decimal(0))
        rows.append({**_brief(ents[g], model), "cost_full": round(full, 2), "cost_shared": round(shared, 2),
                     "items": [{"name": ents[x]["name"], "type": ents[x]["entity_type"], "annual_cost": costed[x],
                                "groups_sharing": share[x]} for x in sorted(reach[g], key=lambda x: -costed[x])][:30]})
    rows.sort(key=lambda r: -r["cost_full"])
    unallocated = [x for x in costed if x not in share]
    return {"group_type": group_type, "groups": rows, "total_cost": round(sum(costed.values(), Decimal(0)), 2),
            "unallocated_cost": round(sum((costed[x] for x in unallocated), Decimal(0)), 2),
            "unallocated": [{**_brief(ents[x], model), "annual_cost": costed[x]} for x in unallocated][:100],
            "how": f"Cost is the annual cost attribute. An item counts for every {group_type} it supports within {depth} "
                   "relationships (cost_full) and is also shared equally between them (cost_shared)."}


# ---------------------------------------------------------------- technology risk
def technology_risk(snap: dict, today: date | None = None, months: int = 12, model: str | None = None) -> dict:
    """Technology past or reaching its end of life (end of life, end of support or retirement date), and what depends on
    it up to the capabilities at risk."""
    today = today or datetime.now(UTC).date()
    limit = date(today.year + (today.month - 1 + months) // 12, (today.month - 1 + months) % 12 + 1, min(today.day, 28))
    ents = snap["entities"]
    rows, caps_at_risk = [], {}
    for g, e in ents.items():
        if _low(e["type_code"]) not in TECH:
            continue
        d = _date(_val(e, kpis.EOL_ATTRS))
        if d is None or d >= limit:
            continue
        hit = impact(snap, g, 6, model)["affected"]
        for x in hit:
            if _low(ents[x["id"]]["type_code"]) in CAPABILITIES:
                caps_at_risk.setdefault(x["id"], {**_brief(ents[x["id"]], model), "because_of": []})["because_of"].append(e["name"])
        rows.append({**_brief(e, model), "end_of_life": d.isoformat(), "past": d < today,
                     "applications_affected": [x["name"] for x in hit if _low(ents[x["id"]]["type_code"]) in APPS][:30],
                     "affected": len(hit)})
    rows.sort(key=lambda r: r["end_of_life"])
    return {"today": today.isoformat(), "within_months": months, "technology": rows,
            "capabilities_at_risk": sorted(caps_at_risk.values(), key=lambda c: c["name"]),
            "how": "End of life is the first of end of life, end of support or retirement date on technology elements."}


# ---------------------------------------------------------------- single points of failure
def single_points(snap: dict, model: str | None = None) -> dict:
    """Entities whose loss splits the landscape (articulation points of the relationship graph), and only providers:
    capabilities supported by one application, applications on one technology element."""
    ents = snap["entities"]
    adj: dict[str, set[str]] = defaultdict(set)
    for r in edges(snap):
        if r["source"] in ents and r["target"] in ents and r["source"] != r["target"]:
            adj[r["source"]].add(r["target"])
            adj[r["target"]].add(r["source"])
    disc, low, cut = {}, {}, set()
    timer = [0]
    for root in list(adj):
        if root in disc:
            continue
        disc[root] = low[root] = timer[0]
        timer[0] += 1
        stack = [(root, None, iter(adj[root]))]
        children = defaultdict(int)
        while stack:
            v, parent, it = stack[-1]
            advanced = False
            for w in it:
                if w not in disc:
                    disc[w] = low[w] = timer[0]
                    timer[0] += 1
                    children[v] += 1
                    stack.append((w, v, iter(adj[w])))
                    advanced = True
                    break
                if w != parent:
                    low[v] = min(low[v], disc[w])
            if advanced:
                continue
            stack.pop()
            if parent is not None:
                low[parent] = min(low[parent], low[v])
                if stack[-1][1] is not None and low[v] >= disc[parent]:
                    cut.add(parent)
        if children[root] > 1:
            cut.add(root)
    points = sorted(({**_brief(ents[g], model), "connections": len(adj[g])} for g in cut), key=lambda x: -x["connections"])
    sup = _supporting_apps(snap)
    only_app = [{**_brief(ents[c], model), "only_application": ents[next(iter(a))]["name"]} for c, a in sup.items() if len(a) == 1]
    on_tech: dict[str, set[str]] = defaultdict(set)
    for r in edges(snap):
        s, t = ents.get(r["source"]), ents.get(r["target"])
        if not s or not t:
            continue
        if _low(s["type_code"]) in TECH and _low(t["type_code"]) in APPS:
            on_tech[t["guid"]].add(s["guid"])
        elif _low(t["type_code"]) in TECH and _low(s["type_code"]) in APPS:
            on_tech[s["guid"]].add(t["guid"])
    only_tech = [{**_brief(ents[a], model), "only_technology": ents[next(iter(ts))]["name"]} for a, ts in on_tech.items() if len(ts) == 1]
    return {"split_the_landscape": points[:100], "capabilities_with_one_application": only_app[:200],
            "applications_on_one_technology_element": only_tech[:200],
            "how": "An entity splits the landscape when removing it leaves parts no longer connected (any relationship)."}


# ---------------------------------------------------------------- heat map
def heat_map(snap: dict, entity_type: str, attribute: str, model: str | None = None) -> dict:
    """Entities of a type by an attribute: each entity's value and band (numbers in three bands by thirds of the range,
    other values as they are), with counts; for a heat map or a coloured view."""
    ents = [e for e in snap["entities"].values() if _low(e["type_code"]) == _low(entity_type) or _low(e["entity_type"]) == _low(entity_type)]
    vals = {e["guid"]: _val(e, [attribute.lower()]) for e in ents}
    nums = {g: _num(v) for g, v in vals.items() if _num(v) is not None}
    numeric = bool(nums) and len(nums) >= 0.6 * max(1, sum(1 for v in vals.values() if v not in (None, "")))
    bands: dict[str, str] = {}
    if numeric:
        lo, hi = min(nums.values()), max(nums.values())
        step = (hi - lo) / 3 if hi > lo else Decimal(1)
        for g, n in nums.items():
            bands[g] = "low" if n < lo + step else ("medium" if n < lo + 2 * step else "high")
    rows = []
    counts: dict[str, int] = defaultdict(int)
    for e in sorted(ents, key=lambda x: x["name"]):
        v = vals[e["guid"]]
        band = bands.get(e["guid"]) if numeric else (str(v) if v not in (None, "") else "Not set")
        band = band or "Not set"
        counts[band] += 1
        rows.append({**_brief(e, model), "value": v, "band": band})
    return {"entity_type": entity_type, "attribute": attribute, "numeric": numeric, "counts": dict(counts), "entities": rows[:1000],
            "next": "To show it as a picture, create_drawn_view with these entities (one per band if wanted)."}


# ---------------------------------------------------------------- clean-up
ABBREVIATIONS = {"app": "Application", "apps": "Applications", "mgmt": "Management", "mgt": "Management", "svc": "Service",
                 "sys": "System", "info": "Information", "dept": "Department", "admin": "Administration", "ops": "Operations",
                 "acct": "Account", "cust": "Customer", "mgr": "Manager", "env": "Environment"}


def tidy_suggestions(snap: dict, model: str | None = None) -> list[dict]:
    """Names to tidy: spaces, inconsistent capitals, trailing punctuation, common abbreviations; with why."""
    out = []
    for e in snap["entities"].values():
        n = e["name"] or ""
        new, why = " ".join(n.split()), []
        if new != n:
            why.append("extra spaces")
        if re.search(r"[.,;:]+$", new):
            new = re.sub(r"[.,;:]+$", "", new)
            why.append("trailing punctuation")
        words = new.split(" ")
        fixed = []
        for w in words:
            k = re.sub(r"[^A-Za-z]", "", w).lower()
            if k in ABBREVIATIONS and w.lower() == k:
                fixed.append(ABBREVIATIONS[k])
                why.append(f"'{w}' written out")
            else:
                fixed.append(w)
        new = " ".join(fixed)
        if new and new[0].islower():
            new = new[0].upper() + new[1:]
            why.append("starts with a small letter")
        if new and len(new) > 4 and new == new.upper() and " " in new:
            new = new.title()
            why.append("all capitals")
        if new != n and new:
            out.append({**_brief(e, model), "suggested": new, "why": ", ".join(dict.fromkeys(why))})
    return sorted(out, key=lambda x: (x["type"], x["name"]))


def orphans(snap: dict, model: str | None = None) -> list[dict]:
    """Entities with no relationship, no parent and no parts, each with likely partners: entities whose names share a
    word with it, or that its description names."""
    ents = snap["entities"]
    linked = {r["source"] for r in edges(snap)} | {r["target"] for r in edges(snap)}
    parents = {e["parent"] for e in ents.values() if e.get("parent")}
    words = {g: {w for w in re.findall(r"[a-z]{4,}", _low(e["name"]))} for g, e in ents.items()}
    out = []
    for g, e in ents.items():
        if g in linked or e.get("parent") or g in parents:
            continue
        desc = _low(e.get("description"))
        cands = []
        for h, f in ents.items():
            if h == g:
                continue
            shared = words[g] & words[h]
            named = len(f["name"]) > 3 and _low(f["name"]) in desc
            if shared or named:
                cands.append({**_brief(f, model), "why": "its name is in the description" if named else f"shares '{sorted(shared)[0]}'"})
        cands.sort(key=lambda c: (not c["why"].startswith("its name"), c["name"]))
        out.append({**_brief(e, model), "likely_partners": cands[:5]})
    return sorted(out, key=lambda x: (x["type"], x["name"]))


# ================================================================ tools
def _snap(conn, model: str) -> tuple[dict, str]:
    from . import tags as tg
    m = repo.get_model(conn, model)
    return tg.snapshot(conn, m), str(m["id"])


def _entity(conn, model: str, entity: str) -> str:
    m = repo.get_model(conn, model)
    return str(repo.get_entity_detail(conn, str(m["id"]), entity)["id"])


@mcp.tool()
async def impact_analysis(model: str, entity: str, depth: int = 6) -> Any:
    """What is affected if an entity goes (retired, replaced, fails): everything depending on it, step by step with the
    path and why, counts by type, and what it is only associated with. entity by name, display ID or guid."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return impact(snap, _entity(conn, model, entity), max(1, min(depth, 10)), mg)
    return await _run(run)


@mcp.tool()
async def application_rationalisation(model: str) -> Any:
    """Applications per capability (directly or through application functions, services and processes): overlaps
    (several applications for one capability), applications supporting no capability, and TIME suggestions from
    functional and technical fit beside the TIME recorded, each with its reason."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return rationalise(snap, mg)
    return await _run(run)


@mcp.tool()
async def cost_rollup_analysis(model: str, group_type: str = "Capability", depth: int = 2) -> Any:
    """Annual cost rolled up to capabilities (or value streams, business units: group_type is an entity type), through the
    relationships within `depth` steps: counted in full and shared equally, plus cost that supports nothing."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return cost_rollup(snap, group_type, max(1, min(depth, 4)), mg)
    return await _run(run)


@mcp.tool()
async def technology_risk_analysis(model: str, within_months: int = 12) -> Any:
    """Technology past its end of life or reaching it within the months given, what depends on each, and which
    capabilities that puts at risk."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return technology_risk(snap, None, max(1, min(within_months, 60)), mg)
    return await _run(run)


@mcp.tool()
async def single_points_of_failure(model: str) -> Any:
    """Entities whose loss would split the landscape, capabilities supported by only one application, and applications
    running on only one technology element."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return single_points(snap, mg)
    return await _run(run)


@mcp.tool()
async def heat_map_data(model: str, entity_type: str, attribute: str) -> Any:
    """Entities of a type by an attribute (cost, quality, maturity, investment...): each value and band with counts, for a
    heat map; draw it with create_drawn_view."""
    def run(conn):
        snap, mg = _snap(conn, model)
        return heat_map(snap, entity_type, attribute, mg)
    return await _run(run)


@mcp.tool()
async def what_changed(model: str, since_tag: str = "", since_date: str = "") -> Any:
    """What changed in a model since a tag (name or id), or since a date (the last tag on or before it): totals and
    the differences. Write the narrative from it."""
    from . import model_operations as mops
    from . import tags as tg

    def run(conn):
        m = repo.get_model(conn, model)
        tl = tg.list_tags(conn, str(m["id"])).get("tags", [])
        pick = None
        if since_tag:
            pick = next((t for t in tl if since_tag in (str(t.get("id")), t.get("name"))), None)
        elif since_date:
            d = since_date[:10]
            older = [t for t in tl if str(t.get("created_at") or t.get("tagged_at") or "")[:10] <= d]
            pick = max(older, key=lambda t: str(t.get("created_at") or t.get("tagged_at") or ""), default=None)
        else:
            pick = max(tl, key=lambda t: str(t.get("created_at") or t.get("tagged_at") or ""), default=None)
        if not pick:
            raise EditError(f"{m['name']} has no tag to compare with" + (f" on or before {since_date}" if since_date else "") + ".")
        out = mops.compare_now(conn, model, model, left_tag=str(pick["id"]))
        out["since"] = {"tag": pick.get("name"), "id": str(pick.get("id")), "at": pick.get("created_at") or pick.get("tagged_at")}
        return out
    return await _run(run)


@mcp.tool()
async def kpi_trend(model: str, kpi: str = "") -> Any:
    """A model's KPIs month by month and at every tag (phase 24), or one KPI (code or name): with the biggest changes
    between snapshots, to explain a trend ("why did the quality score drop in September?")."""
    def run(conn):
        t = kpis.trends(conn, model, permissions.current.get())
        if not kpi:
            return t
        rows = [k for k in t.get("kpis") or [] if kpi.lower() in (str(k.get("code", "")).lower(), str(k.get("name", "")).lower())]
        if not rows:
            raise EditError(f"No KPI {kpi!r}: one of " + ", ".join(str(k.get("code")) for k in t.get("kpis") or []))
        return {"kpi": rows[0], "model": t.get("model")}
    return await _run(run)


@mcp.tool()
async def find_orphans(model: str) -> Any:
    """Entities with no relationships, no parent and no parts, each with likely partners (shared words, named in the
    description). Check allowed_relationships before suggesting one; add them with add_relationships."""
    def run(conn):
        snap, mg = _snap(conn, model)
        rows = orphans(snap, mg)
        return {"orphans": rows[:300], "count": len(rows)}
    return await _run(run)


@mcp.tool()
async def tidy_names(model: str) -> Any:
    """Names worth tidying (extra spaces, small first letters, all capitals, trailing punctuation, abbreviations such as
    Mgmt or App written out), with the suggested name and why. Apply the ones the person agrees with change_entities."""
    def run(conn):
        snap, mg = _snap(conn, model)
        rows = tidy_suggestions(snap, mg)
        return {"suggestions": rows[:500], "count": len(rows)}
    return await _run(run)


@mcp.tool()
async def change_entities(model: str, changes: list[dict], commit_message: str = "", confirm: str = "", why: str = "") -> Any:
    """Change many entities at once as YOUR changes (bulk quality fixes, tidied names, attributes filled from their
    descriptions): changes = [{entity: name, display ID or guid, name?, description?, values: {attribute code: value}?,
    parent?}]. They stay your uncommitted changes, unless commit_message is given and you may commit. The model is
    tagged first. First call: a preview (each entity's current and new values) and a confirm token; call again with
    confirm=<token>. Never guess values you cannot justify from the model or the person."""
    if not changes:
        return {"error": "Give the changes: [{entity, name?, description?, values?, parent?}]."}
    if len(changes) > 2000:
        return {"error": "At most 2,000 entities at a time."}
    args = {"model": model, "changes": changes, "commit_message": commit_message}

    def resolved(conn):
        rows = []
        mid = str(repo.get_model(conn, model)["id"])
        for c in changes:
            e = repo.get_entity_detail(conn, mid, c.get("entity"))
            data = {k: c[k] for k in ("name", "description", "parent") if k in c}
            if c.get("values"):
                data["values"] = c["values"]
            rows.append((e, data))
        return rows

    def preview(conn, user):
        m = repo.get_model(conn, model)
        rows = resolved(conn)
        shown = []
        for e, data in rows[:200]:
            now = {a.get("code"): a.get("value") for a in e.get("attributes") or [] if isinstance(a, dict)}
            shown.append({"entity": e["name"], "type": e.get("entity_type"), "changes": {
                k: {"now": (e.get(k) if k != "values" else {a: now.get(a) for a in v}), "new": v} for k, v in data.items()}})
        commits = cm.uses_commits(m)
        return {"model": m["name"], "entities": len(rows), "first": shown,
                "will": f"Change {len(rows)} entities in {m['name']} as your changes"
                        + (", then commit them" if commit_message and commits and cm.may_commit(conn, user, m) else
                           " (uncommitted until a committer commits them)" if commits else "") + ", after tagging it."}

    def apply(conn, user):
        m = repo.get_model(conn, model)
        items = [("entity.update", {"entity": str(e["id"]), "data": data}) for e, data in resolved(conn)]
        res = cm.record_many(conn, m["id"], user.username, items)
        ok = [r for r in res if r.get("ok")]
        failed = [r["error"] for r in res if not r.get("ok")]
        out = {"changed": len(ok), "failed": failed[:30], "pending": cm.uses_commits(m)}
        ids = [r["kept"]["change"] for r in ok if r.get("kept")]
        if commit_message and ids and cm.uses_commits(m) and cm.may_commit(conn, user, m):
            done = cm.commit(conn, m["id"], user, None, ids, None, f"{commit_message} (through MCP)")
            out.update(pending=False, commit=done.get("number"))
        out["message"] = f"{len(ok)} entities changed" + (f", committed as commit {out['commit']}" if out.get("commit") else
                                                          ": your uncommitted changes" if out["pending"] else "") + \
                         (f"; {len(failed)} failed" if failed else "") + "."
        return out
    return await mcp_ops.operate("change_entities", args, confirm, preview, apply, tag=[model], label="changing entities")


@mcp.tool()
async def get_relationship(model: str, relationship: str) -> Any:
    """One relationship (by guid): its type, name, ends, the attributes it has (its type's, and those of its allowed
    relationship: source type + type + target type) with their values and which are required, and its quality
    findings (a required value missing, a value kept that no longer belongs) (D563, D564)."""
    from . import content as ct
    return await _run(lambda conn: ct.relationship_detail(conn, str(repo.get_model(conn, model)["id"]), relationship))


@mcp.tool()
async def change_relationships(model: str, changes: list[dict], commit_message: str = "", confirm: str = "",
                               why: str = "") -> Any:
    """Name relationships and set their attribute values as YOUR changes: changes = [{relationship: guid, name?,
    values: {attribute code or name: value}?}] (an empty value clears it; the type and ends stay). Only the attributes
    of the relationship's type and its allowed relationship are accepted (get_relationship lists them). They stay your
    uncommitted changes unless commit_message is given and you may commit. The model is tagged first. First call: a
    preview (each relationship's current and new values) and a confirm token; call again with confirm=<token>."""
    from . import content as ct
    if not changes:
        return {"error": "Give the changes: [{relationship, name?, values?}]."}
    if len(changes) > 2000:
        return {"error": "At most 2,000 relationships at a time."}
    args = {"model": model, "changes": changes, "commit_message": commit_message}

    def resolved(conn):
        mid = str(repo.get_model(conn, model)["id"])
        rows = []
        for c in changes:
            r = ct.relationship_detail(conn, mid, c.get("relationship"))
            data = {k: c[k] for k in ("name", "values") if c.get(k) is not None}
            rows.append((r, data))
        return rows

    def preview(conn, user):
        m = repo.get_model(conn, model)
        rows = resolved(conn)
        shown = [{"relationship": f"{r['source_name']} {r['relationship_type']} {r['target_name']}",
                  "changes": {k: {"now": (r.get("name") if k == "name" else {a: (r.get("values") or {}).get(a) for a in v}),
                                  "new": v} for k, v in data.items()}} for r, data in rows[:200]]
        commits = cm.uses_commits(m)
        return {"model": m["name"], "relationships": len(rows), "first": shown,
                "will": f"Change {len(rows)} relationships in {m['name']} as your changes"
                        + (", then commit them" if commit_message and commits and cm.may_commit(conn, user, m) else
                           " (uncommitted until a committer commits them)" if commits else "") + ", after tagging it."}

    def apply(conn, user):
        m = repo.get_model(conn, model)
        items = [("relationship.rename", {"relationship": str(r["id"]), **data}) for r, data in resolved(conn)]
        res = cm.record_many(conn, m["id"], user.username, items)
        ok = [x for x in res if x.get("ok")]
        failed = [x["error"] for x in res if not x.get("ok")]
        out = {"changed": len(ok), "failed": failed[:30], "pending": cm.uses_commits(m)}
        ids = [x["kept"]["change"] for x in ok if x.get("kept")]
        if commit_message and ids and cm.uses_commits(m) and cm.may_commit(conn, user, m):
            done = cm.commit(conn, m["id"], user, None, ids, None, f"{commit_message} (through MCP)")
            out.update(pending=False, commit=done.get("number"))
        out["message"] = f"{len(ok)} relationships changed" + (
            f", committed as commit {out['commit']}" if out.get("commit") else
            ": your uncommitted changes" if out["pending"] else "") + (f"; {len(failed)} failed" if failed else "") + "."
        return out
    return await mcp_ops.operate("change_relationships", args, confirm, preview, apply, tag=[model],
                                 label="changing relationships")


@mcp.tool()
async def why_commit_blocked(model: str) -> Any:
    """Why your changes in a model cannot be committed now, and what would fix it: the model's lock or freeze, your role,
    and the errors on your uncommitted changes (errors block a commit, warnings do not)."""
    def run(conn):
        from . import merge as mg
        user = permissions.current.get()
        m = repo.get_model(conn, model)
        reasons, fixes = [], []
        if m.get("frozen_at"):
            reasons.append(f"{m['name']} is frozen (read only for good).")
            fixes.append("A Super Admin unfreezes it, or work in a copy (copy_model).")
        why = mg.blocked(conn, m, user)
        if why and "Model Admin role" not in why:
            reasons.append(why)
        if cm.uses_commits(m) and not cm.may_commit(conn, user, m):
            reasons.append("You do not have a role that commits (Committer, Model Sub Admin or Model Admin).")
            fixes.append("Ask a committer (request_my_commit), or ask a Model Admin for the Committer role.")
        page = cm.changes_page(conn, model, user)
        errors, pending = [], page.get("pending_count", 0)
        for st in page.get("mine") or []:
            for ch in st.get("changes") or []:
                for w in ch.get("warnings") or []:
                    sev = str((w or {}).get("severity", "") if isinstance(w, dict) else "").lower()
                    if sev == "error":
                        errors.append({"change": ch.get("label"), "error": w.get("message") or w})
        if errors:
            reasons.append(f"{len(errors)} errors on your changes (errors block a commit).")
            fixes.append("Fix the values the errors name (change_entities), then commit.")
        if not pending:
            reasons.append("You have no uncommitted changes in this model.")
        return {"model": m["name"], "pending_changes": pending, "can_commit": not reasons, "reasons": reasons,
                "errors": errors[:50], "fixes": fixes}
    return await _run(run)
