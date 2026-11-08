"""Common analysis (build phase 13.0.5, D286): what two or more models have in common.

The counterpart of gap analysis (eax/gaps.py). Two or more sides, each a model as it is now or a tag of one, are
matched element by element the way a comparison matches two sides (hand-made matches, guid, origin, type and name;
the display ID only when the person asks, as models made apart reuse the same IDs for different things), side by side in order, so one element of the result holds the matching entity
of each side that has it. Close names that did not match are **suggested**; the person confirms (a hand-made match,
kept for the next run) or rejects each.

Everything is the person's choice (owner, 7 Nov 2026): the sides, the **threshold** (common means in all of them, or in
at least N), the entity types and, per type, the fields and relationships to compare, whether to compare **values**
(which fields agree or differ across the sides) and **relationships** (the same link between matched elements).

It is stored in a project model the person chooses, whose roles decide who sees and works on it (as for gap analyses,
D177), with numbered runs; each element carries a note and a decision. From the result: tag the common elements in
each side's model (`common: <name>`), or make a new model holding them; Excel and Word downloads.
"""

from __future__ import annotations

import difflib
import io
import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import commits as cm
from . import compare as cp
from . import gaps as gp
from . import repository as repo
from .metamodel_edit import EditError, _db_message

DECISIONS = ["Standardise", "Share (one for all)", "Keep separate", "Merge into one", "Investigate", "Not the same thing"]
SUGGEST_AT = 0.8     # name similarity for a suggestion
SUGGEST_MAX_TYPE = 800


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def tag_name(name: str) -> str:
    return f"common: {name.strip()}"[:100]


# ---------------------------------------------------------------- the set-up screen
def load_sides(conn, sides: list[dict]) -> list[dict]:
    if not isinstance(sides, list) or len(sides) < 2:
        raise EditError("Choose two or more models (or tags) to find what they have in common.")
    if len(sides) > 12:
        raise EditError("At most 12 sides in one common analysis.")
    return [cp.load_side(conn, s) for s in sides]


def fields_for(loaded: list[dict]) -> dict:
    """The set-up screen: every entity type of any side with its fields and relationships (and the defaults), how
    many entities each side has of it, and the relationship types."""
    types: dict[str, dict] = {}
    rels: dict[str, dict] = {}
    for i in range(1, len(loaded)):
        info = cp.fields_for(loaded[0], loaded[i])
        for t in info["types"]:
            x = types.setdefault(t["code"], {**{k: t[k] for k in ("code", "name", "layer")}, "fields": [], "counts": [0] * len(loaded),
                                             "default": False})
            have = {f["code"] for f in x["fields"]}
            x["fields"] += [f for f in t["fields"] if f["code"] not in have]
            x["counts"][0] = t["left"]
            x["counts"][i] = t["right"]
        for r in info["relationship_types"]:
            rels[r["code"]] = r
    for x in types.values():
        x["default"] = sum(1 for c in x["counts"] if c) >= 2     # only a type two sides have can have something in common
        x["in"] = sum(1 for c in x["counts"] if c)
    return {"sides": [cp._label(s) for s in loaded], "types": sorted(types.values(), key=lambda t: (t["layer"] or "", t["name"])),
            "relationship_types": sorted(rels.values(), key=lambda r: r["name"])}


def defaults(info: dict, n: int) -> dict:
    return {"threshold": n, "values": True, "relationships": True, "by_display_id": False,
            "types": {t["code"]: [f["code"] for f in t["fields"] if f["default"] and not f["code"].startswith("rel:")]
                      for t in info["types"] if t["default"]},
            "relationship_types": [r["code"] for r in info["relationship_types"]], "matches": [], "rejected": []}


def clean_settings(st: dict | None, info: dict, n: int) -> dict:
    base = defaults(info, n)
    st = dict(st or {})
    out = {**base, **{k: v for k, v in st.items() if k in base}}
    try:
        out["threshold"] = max(2, min(n, int(out["threshold"])))
    except (TypeError, ValueError):
        out["threshold"] = n
    out["values"], out["relationships"], out["by_display_id"] = bool(out["values"]), bool(out["relationships"]), bool(out["by_display_id"])
    if not out["types"]:
        raise EditError("Choose at least one entity type to compare.")
    for k in ("matches", "rejected"):
        out[k] = [p for p in (out.get(k) or []) if isinstance(p, list) and len(p) == 2 and all(isinstance(x, list) and len(x) == 2 for x in p)]
    return out


# ---------------------------------------------------------------- the engine
def match(left: dict, right: dict, manual: dict | None = None, by_display_id: bool = False) -> dict[str, str]:
    """Left entity guid -> right entity guid, as a comparison matches (eax/compare.py: hand-made matches, the same guid, a
    copy of the same element, type and name) but the display ID counts only when asked: in models made apart (two
    companies, two business units) the same display ID is often a different thing."""
    le, re_ = left["snapshot"]["entities"], right["snapshot"]["entities"]
    out: dict[str, str] = {}
    used: set[str] = set()

    def pair(lg, rg):
        if lg in le and rg in re_ and lg not in out and rg not in used:
            out[lg] = rg
            used.add(rg)
    for lg, rg in (manual or {}).items():
        pair(str(lg), str(rg))
    for g in le:
        if g in re_:
            pair(g, g)
    by_origin: dict[str, str] = {}
    for g, e in re_.items():
        by_origin.setdefault(g, g)
        if e.get("origin"):
            by_origin.setdefault(e["origin"], g)
    for g, e in le.items():
        for k in (g, e.get("origin")):
            if k and k in by_origin:
                pair(g, by_origin[k])
                break
    if by_display_id:
        by_id = {(e["type_code"], e["display_id"]): g for g, e in re_.items() if e.get("display_id")}
        for g, e in le.items():
            if e.get("display_id") and (e["type_code"], e["display_id"]) in by_id:
                pair(g, by_id[(e["type_code"], e["display_id"])])
    by_name: dict[tuple, str] = {}
    for g, e in re_.items():
        by_name.setdefault((e["type_code"], _norm(e["name"])), g)
    for g, e in le.items():
        k = (e["type_code"], _norm(e["name"]))
        if k in by_name:
            pair(g, by_name[k])
    return out


def analyse(loaded: list[dict], st: dict) -> dict:
    """Matches the sides in order and gathers each element's members; then the values, relationships and suggestions."""
    n = len(loaded)
    ents = [s["snapshot"]["entities"] for s in loaded]
    manual: dict[tuple[int, int], dict[str, str]] = {}
    for (i, gi), (j, gj) in st.get("matches") or []:
        i, j = int(i), int(j)
        if i == j:
            continue
        if i > j:
            (i, gi), (j, gj) = (j, gj), (i, gi)
        manual.setdefault((i, j), {})[str(gi)] = str(gj)
    clusters: list[dict[int, str]] = []
    where: dict[tuple[int, str], int] = {}
    for i in range(n):
        for j in range(i):
            for jg, ig in match(loaded[j], loaded[i], manual.get((j, i)), st.get("by_display_id", False)).items():
                if (i, ig) in where:
                    continue
                c = where.get((j, jg))
                if c is None or i in clusters[c]:
                    continue
                clusters[c][i] = ig
                where[(i, ig)] = c
        for g in ents[i]:
            if (i, g) not in where:
                where[(i, g)] = len(clusters)
                clusters.append({i: g})
    want = st["types"]
    thr = st["threshold"]
    names_by_side = [{g: e["name"] for g, e in side.items()} for side in ents]
    labels = {t["code"]: {f["code"]: f["label"] for f in t["fields"]} for t in fields_for(loaded)["types"]}
    tinfo: dict[str, dict] = {}
    for s in loaded:
        for t in s["spec"].get("entity_types") or []:
            tinfo.setdefault(t["code"], t)
    layer_names = {lay["code"]: lay["name"] for s in loaded for lay in s["spec"].get("layers") or []}
    items, keep_idx = [], {}
    for c, mem in enumerate(clusters):
        first = ents[min(mem)][mem[min(mem)]]
        code = first["type_code"]
        if code not in want:
            continue
        members = {str(i): {"guid": g, "name": ents[i][g]["name"], "display_id": ents[i][g].get("display_id")} for i, g in sorted(mem.items())}
        differs = []
        if st["values"] and len(mem) > 1:
            for f in want.get(code) or []:
                if f.startswith("rel:"):
                    continue
                vals = {str(i): cp._field(ents[i][g], f, names_by_side[i]) for i, g in mem.items()}
                if len({str(v) if v not in (None, "") else "" for v in vals.values()}) > 1:
                    differs.append({"field": f, "label": labels.get(code, {}).get(f, f), "values": vals})
        t = tinfo.get(code) or {}
        keep_idx[c] = len(items)
        items.append({"key": "|".join(f"{i}:{g}" for i, g in sorted(mem.items())), "entity_type": code,
                      "entity_type_name": first["entity_type"], "layer": layer_names.get(t.get("layer"), first.get("layer") or ""),
                      "name": first["name"], "members": members, "count": len(mem), "common": len(mem) >= thr, "differs": differs})
    # relationships: by type and the elements at their ends
    relationships = []
    if st["relationships"]:
        want_r = set(st.get("relationship_types") or [])
        found: dict[tuple, dict] = {}
        for i, s in enumerate(loaded):
            for r in s["snapshot"]["relationships"].values():
                if want_r and r["type_code"] not in want_r:
                    continue
                a, b = where.get((i, r["source"])), where.get((i, r["target"]))
                if a not in keep_idx or b not in keep_idx:
                    continue
                k = (r["type_code"], a, b)
                x = found.setdefault(k, {"type": r["type_code"], "relationship_type": r["relationship_type"],
                                         "source": items[keep_idx[a]]["name"], "target": items[keep_idx[b]]["name"], "sides": []})
                if i not in x["sides"]:
                    x["sides"].append(i)
        for x in found.values():
            x["count"] = len(x["sides"])
            x["common"] = x["count"] >= thr
            relationships.append(x)
        relationships.sort(key=lambda x: (-x["count"], x["relationship_type"], x["source"], x["target"]))
    # close names not matched: suggestions (only between elements no side of which overlaps)
    rejected = {tuple(sorted((f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}"))) for a, b in st.get("rejected") or []}
    suggestions = []
    by_type: dict[str, list[dict]] = {}
    for it in items:
        if it["count"] < n:
            by_type.setdefault(it["entity_type"], []).append(it)
    for code, group in by_type.items():
        if len(group) > SUGGEST_MAX_TYPE:
            continue
        normed = [(_norm(x["name"]), x) for x in group]
        for a in range(len(normed)):
            na, x = normed[a]
            for b in range(a + 1, len(normed)):
                nb, y = normed[b]
                if set(x["members"]) & set(y["members"]) or re.findall(r"\d+", na) != re.findall(r"\d+", nb):
                    continue
                score = difflib.SequenceMatcher(None, na, nb).ratio()
                if score < SUGGEST_AT:
                    continue
                i, j = min(x["members"], key=int), min(y["members"], key=int)
                pa, pb = [int(i), x["members"][i]["guid"]], [int(j), y["members"][j]["guid"]]
                if tuple(sorted((f"{pa[0]}:{pa[1]}", f"{pb[0]}:{pb[1]}"))) in rejected:
                    continue
                suggestions.append({"entity_type": code, "entity_type_name": x["entity_type_name"], "a": pa, "a_name": x["name"],
                                    "a_sides": sorted(int(k) for k in x["members"]), "b": pb, "b_name": y["name"],
                                    "b_sides": sorted(int(k) for k in y["members"]), "score": round(score, 2)})
    suggestions.sort(key=lambda s: -s["score"])
    summary: dict[str, dict] = {}
    for it in items:
        s = summary.setdefault(it["entity_type"], {"entity_type": it["entity_type"], "name": it["entity_type_name"], "layer": it["layer"],
                                                    "elements": 0, "common": 0, "differ": 0, "by_count": {}})
        s["elements"] += 1
        s["common"] += it["common"]
        s["differ"] += bool(it["common"] and it["differs"])
        s["by_count"][str(it["count"])] = s["by_count"].get(str(it["count"]), 0) + 1
    items.sort(key=lambda x: (-x["count"], x["layer"] or "", x["entity_type_name"], x["name"].lower()))
    return {"items": items, "relationships": relationships, "suggestions": suggestions[:300],
            "summary": sorted(summary.values(), key=lambda s: (s["layer"] or "", s["name"])), "totals": _totals(items, n, thr)}


def _totals(items: list[dict], n: int, thr: int) -> dict:
    return {"elements": len(items), "common": sum(1 for i in items if i["common"]), "in_all": sum(1 for i in items if i["count"] == n),
            "only_one": sum(1 for i in items if i["count"] == 1), "differ": sum(1 for i in items if i["common"] and i["differs"]),
            "threshold": thr, "sides": n}


# ---------------------------------------------------------------- stored analyses
def _may(conn, user, m: dict) -> None:
    gp._may(conn, user, m)


def _may_store(m: dict) -> None:
    if m["kind"] != "project" or m.get("is_locked"):
        raise EditError(f"A common analysis is stored in a project model that is not locked; {m['name']} is "
                        f"{'locked' if m.get('is_locked') else 'a ' + str(m['kind']) + ' model'}.", 409)


def preview(conn, sides: list[dict]) -> dict:
    loaded = load_sides(conn, sides)
    info = fields_for(loaded)
    return {**info, "defaults": defaults(info, len(loaded)), "decisions": DECISIONS}


def create(conn, model: Any, user, name: str, sides: list[dict], settings: dict | None = None, description: str = "") -> dict:
    m = repo.get_model(conn, model)
    _may_store(m)
    _may(conn, user, m)
    if not (name or "").strip():
        raise EditError("Give the common analysis a name, for example Claims across the three business units.")
    loaded = load_sides(conn, sides)
    st = clean_settings(settings, fields_for(loaded), len(loaded))
    result = analyse(loaded, st)
    labels = [{**cp._label(s), "request": r} for s, r in zip(loaded, sides, strict=True)]
    try:
        row = _one(conn, """INSERT INTO core.common_analyses (model_id, name, description, sides, settings, summary, relationships,
                                                              suggestions, compared_by, created_by)
                            VALUES (:m, :n, :d, CAST(:s AS jsonb), CAST(:st AS jsonb), CAST(:sum AS jsonb), CAST(:r AS jsonb),
                                    CAST(:sg AS jsonb), :u, :u) RETURNING id, guid""",
                   m=m["_id"], n=name.strip(), d=(description or "").strip(), s=json.dumps(labels, default=str), st=json.dumps(st),
                   sum=json.dumps({"totals": result["totals"], "summary": result["summary"]}), r=json.dumps(result["relationships"]),
                   sg=json.dumps(result["suggestions"]), u=user.username.lower())
    except DBAPIError as exc:
        raise EditError(f"{m['name']} already has a common analysis called '{name.strip()}'." if "common_analyses_name_idx" in str(exc.orig)
                        else _db_message(exc), 409) from exc
    _store_items(conn, row["id"], result)
    _new_run(conn, row["id"], user)
    return get(conn, str(m["id"]), str(row["guid"]))


def _store_items(conn, analysis_id: int, result: dict) -> None:
    """Upserts the elements by key; an element whose members changed takes over the note and decision of the earlier
    element that shares a member with it."""
    old = _rows(conn, "SELECT id, match_key, note, decision, gone FROM core.common_items WHERE analysis_id = :a", a=analysis_id)
    by_member: dict[str, dict] = {}
    for o in old:
        for mem in o["match_key"].split("|"):
            by_member.setdefault(mem, o)
    keys, taken = [], set()
    for it in result["items"]:
        keys.append(it["key"])
        carry = None
        if not any(o["match_key"] == it["key"] for o in old):
            carry = next((by_member[mem] for mem in it["key"].split("|") if mem in by_member and by_member[mem]["id"] not in taken
                          and (by_member[mem]["note"] or by_member[mem]["decision"])), None)
            if carry:
                taken.add(carry["id"])
        conn.execute(text("""INSERT INTO core.common_items (analysis_id, match_key, entity_type, entity_type_name, layer, name, members,
                                                           sides_count, is_common, differs, note, decision, gone)
                             VALUES (:a, :k, :t, :tn, :l, :n, CAST(:mem AS jsonb), :c, :ic, CAST(:d AS jsonb), :note, :dec, false)
                             ON CONFLICT (analysis_id, match_key) DO UPDATE SET entity_type = EXCLUDED.entity_type,
                                 entity_type_name = EXCLUDED.entity_type_name, layer = EXCLUDED.layer, name = EXCLUDED.name,
                                 members = EXCLUDED.members, sides_count = EXCLUDED.sides_count, is_common = EXCLUDED.is_common,
                                 differs = EXCLUDED.differs, gone = false"""),
                     {"a": analysis_id, "k": it["key"], "t": it["entity_type"], "tn": it["entity_type_name"], "l": it["layer"] or "",
                      "n": it["name"], "mem": json.dumps(it["members"]), "c": it["count"], "ic": it["common"],
                      "d": json.dumps(it["differs"], default=str), "note": (carry or {}).get("note") or "", "dec": (carry or {}).get("decision") or ""})
    conn.execute(text("UPDATE core.common_items SET gone = true WHERE analysis_id = :a AND NOT (match_key = ANY (CAST(:k AS text[])))"),
                 {"a": analysis_id, "k": keys or [""]})


def _new_run(conn, analysis_id: int, user) -> int:
    a = _one(conn, "SELECT sides, summary FROM core.common_analyses WHERE id = :i", i=analysis_id)
    items = _rows(conn, """SELECT match_key AS key, entity_type, entity_type_name, name, sides_count AS count, is_common AS common,
                                  members, decision, note FROM core.common_items WHERE analysis_id = :a AND NOT gone ORDER BY id""", a=analysis_id)
    for i in items:
        i["members"] = cm._json(i["members"])
    n = _one(conn, """UPDATE core.common_analyses SET runs_made = greatest(runs_made,
                          (SELECT coalesce(max(number), 0) FROM core.common_runs WHERE analysis_id = :a)) + 1
                      WHERE id = :a RETURNING runs_made AS n""", a=analysis_id)["n"]
    conn.execute(text("""INSERT INTO core.common_runs (analysis_id, number, compared_by, sides, totals, items)
                         VALUES (:a, :n, :u, CAST(:s AS jsonb), CAST(:t AS jsonb), CAST(:i AS jsonb))"""),
                 {"a": analysis_id, "n": n, "u": user.username.lower(), "s": json.dumps(cm._json(a["sides"]), default=str),
                  "t": json.dumps((cm._json(a["summary"]) or {}).get("totals") or {}), "i": json.dumps(items, default=str)})
    return n


def model_of(conn, analysis: Any) -> str:
    g = repo._as_guid(analysis)
    r = _one(conn, "SELECT x.guid FROM core.common_analyses a JOIN core.models x ON x.id = a.model_id WHERE a.guid = :g", g=str(g)) if g else None
    if not r:
        raise EditError("No such common analysis, or you may not read the model it is stored in.", 404)
    repo.get_model(conn, str(r["guid"]))   # only when you may read it
    return str(r["guid"])


def _analysis(conn, m: dict, analysis: Any) -> dict:
    g = repo._as_guid(analysis)
    a = _one(conn, "SELECT * FROM core.common_analyses WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not a:
        raise EditError("No such common analysis in this model.", 404)
    return a


def refresh(conn, model: Any, user, analysis: Any, settings: dict | None = None) -> dict:
    """Compares the sides again (with new settings, or the same): notes and decisions are kept."""
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    req = [s["request"] for s in cm._json(a["sides"])]
    loaded = load_sides(conn, req)
    st = clean_settings({**cm._json(a["settings"]), **(settings or {})}, fields_for(loaded), len(loaded))
    result = analyse(loaded, st)
    conn.execute(text("""UPDATE core.common_analyses SET sides = CAST(:s AS jsonb), settings = CAST(:st AS jsonb), summary = CAST(:sum AS jsonb),
                             relationships = CAST(:r AS jsonb), suggestions = CAST(:sg AS jsonb), compared_at = now(), compared_by = :u
                          WHERE id = :i"""),
                 {"s": json.dumps([{**cp._label(x), "request": r} for x, r in zip(loaded, req, strict=True)], default=str),
                  "st": json.dumps(st), "sum": json.dumps({"totals": result["totals"], "summary": result["summary"]}),
                  "r": json.dumps(result["relationships"]), "sg": json.dumps(result["suggestions"]), "u": user.username.lower(), "i": a["id"]})
    _store_items(conn, a["id"], result)
    _new_run(conn, a["id"], user)
    return get(conn, str(m["id"]), str(a["guid"]))


def decide_suggestions(conn, model: Any, user, analysis: Any, confirm: list, reject: list) -> dict:
    """Confirmed suggestions become hand-made matches, rejected ones are not suggested again; then compared again."""
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    st = cm._json(a["settings"])
    ok = [p for p in confirm or [] if isinstance(p, list) and len(p) == 2]
    no = [p for p in reject or [] if isinstance(p, list) and len(p) == 2]
    if not ok and not no:
        raise EditError("Confirm or reject at least one suggestion.")
    return refresh(conn, model, user, analysis, {"matches": (st.get("matches") or []) + ok, "rejected": (st.get("rejected") or []) + no})


def list_analyses(conn, model: Any = None) -> dict:
    m = repo.get_model(conn, model) if model else None
    rows = _rows(conn, """SELECT a.guid AS id, a.name, a.description, a.sides, a.summary, a.compared_at, a.compared_by, a.created_by,
                                 a.runs_made, x.guid AS model_id, x.name AS model_name
                            FROM core.common_analyses a JOIN core.models x ON x.id = a.model_id AND NOT x.is_deleted
                           WHERE (CAST(:m AS bigint) IS NULL OR a.model_id = :m) ORDER BY a.compared_at DESC""", m=m["_id"] if m else None)
    readable = {str(r["guid"]) for r in _rows(conn, "SELECT guid FROM core.models WHERE NOT is_deleted")}
    out = []
    for r in rows:
        if str(r["model_id"]) not in readable:
            continue
        sides = cm._json(r.pop("sides"))
        r.update(id=str(r["id"]), model_id=str(r["model_id"]), sides=[s.get("label") for s in sides],
                 totals=(cm._json(r.pop("summary")) or {}).get("totals") or {})
        out.append(r)
    return {"analyses": out, "decisions": DECISIONS}


def get(conn, model: Any, analysis: Any) -> dict:
    m = repo.get_model(conn, model)
    a = _analysis(conn, m, analysis)
    items = _rows(conn, """SELECT guid AS id, match_key, entity_type, entity_type_name, layer, name, members, sides_count, is_common,
                                  differs, note, decision, gone, modified_by, modified_at
                             FROM core.common_items WHERE analysis_id = :a
                            ORDER BY gone, sides_count DESC, layer, entity_type_name, lower(name)""", a=a["id"])
    for i in items:
        i["id"] = str(i["id"])
        i["members"], i["differs"] = cm._json(i["members"]), cm._json(i["differs"])
    runs = _rows(conn, "SELECT guid AS id, number, compared_at, compared_by, totals FROM core.common_runs WHERE analysis_id = :a ORDER BY number DESC",
                 a=a["id"])
    for r in runs:
        r["id"], r["totals"] = str(r["id"]), cm._json(r["totals"])
    summ = cm._json(a["summary"]) or {}
    return {"id": str(a["guid"]), "name": a["name"], "description": a["description"],
            "model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"], "is_locked": bool(m.get("is_locked"))},
            "sides": cm._json(a["sides"]), "settings": cm._json(a["settings"]), "totals": summ.get("totals") or {},
            "summary": summ.get("summary") or [], "relationships": cm._json(a["relationships"]), "suggestions": cm._json(a["suggestions"]),
            "compared_at": a["compared_at"], "compared_by": a["compared_by"], "created_by": a["created_by"],
            "items": items, "runs": runs, "decisions": DECISIONS, "tag": tag_name(a["name"])}


def update_items(conn, model: Any, user, analysis: Any, items: list, decision: str | None = None, note: str | None = None) -> dict:
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    if decision not in (None, "") and decision not in DECISIONS:
        raise EditError(f"A decision is one of: {', '.join(DECISIONS)}.")
    if decision is None and note is None:
        raise EditError("Give a decision or a note.")
    n = 0
    for i in items or []:
        g = repo._as_guid(i)
        if not g:
            continue
        sets = ["modified_by = :u", "modified_at = now()"]
        if decision is not None:
            sets.append("decision = :d")
        if note is not None:
            sets.append("note = :n")
        r = conn.execute(text(f"UPDATE core.common_items SET {', '.join(sets)} WHERE guid = :g AND analysis_id = :a"),
                         {"u": user.username.lower(), "d": decision or "", "n": (note or "").strip()[:4000], "g": str(g), "a": a["id"]})
        n += r.rowcount or 0
    return {"updated": n, "message": f"{n} element{'s' if n != 1 else ''} updated."}


def delete(conn, model: Any, user, analysis: Any) -> dict:
    m = repo.get_model(conn, model)
    _may(conn, user, m)
    a = _analysis(conn, m, analysis)
    conn.execute(text("DELETE FROM core.common_analyses WHERE id = :i"), {"i": a["id"]})
    return {"message": f"Common analysis '{a['name']}' deleted (tags it put on entities stay)."}


# ---------------------------------------------------------------- acting on the result
def _common_members(data: dict, only: list | None) -> dict[int, list[str]]:
    pick = {str(x) for x in only or []}
    out: dict[int, list[str]] = {}
    for i in data["items"]:
        if i["gone"] or not i["is_common"] or (pick and i["id"] not in pick):
            continue
        for side, mem in i["members"].items():
            out.setdefault(int(side), []).append(mem["guid"])
    return out


def tag_common(conn, model: Any, user, analysis: Any, items: list | None = None) -> dict:
    """Tags the common elements (all, or those chosen) in each side that is a model as it is now: `common: <name>`,
    one commit per model. A side the person may not change, or a tag side, is listed as skipped."""
    data = get(conn, model, analysis)
    tag = tag_name(data["name"])
    done, skipped = [], []
    for side, guids in _common_members(data, items).items():
        s = data["sides"][side]
        if s.get("kind") != "model":
            skipped.append(f"{s.get('label')}: a tag never changes")
            continue
        sm = repo.get_model(conn, s["model_id"])
        have = {str(r["guid"]): list(r["tags"] or []) for r in _rows(conn, """SELECT guid, tags FROM core.entities WHERE model_id = :m
                   AND NOT is_deleted AND guid = ANY (CAST(:g AS uuid[]))""", m=sm["_id"], g=guids)}
        def tags_of(t):
            return [x.strip('"') for x in (t if isinstance(t, list) else str(t).strip("{}").split(",")) if x]
        work = [("entity.update", {"entity": g, "data": {"tags": sorted(set(tags_of(t)) | {tag})}}) for g, t in have.items()
                if tag.lower() not in [x.lower() for x in tags_of(t)]]   # tags are kept in lower case
        if not work:
            done.append(f"{sm['name']}: already tagged")
            continue
        try:
            with conn.begin_nested():
                res = cm.record_many(conn, sm["id"], user.username, work)
                ids = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
                if ids:
                    cm.commit(conn, sm["id"], user, None, ids, None, f"Tagged {tag} (common analysis)")
            done.append(f"{sm['name']}: {len(ids)} tagged")
        except (EditError, DBAPIError, cm.CommitConflict) as exc:
            skipped.append(f"{sm['name']}: {getattr(exc, 'orig', exc)}".split("\n")[0][:300])
    return {"tag": tag, "done": done, "skipped": skipped,
            "message": f"Tagged '{tag}': " + ("; ".join(done) or "nothing") + (f". Skipped: {'; '.join(skipped)}" if skipped else ".")}


def make_model(conn, model: Any, user, analysis: Any, d: dict) -> dict:
    """A new model holding the common elements (all, or those chosen), copied from one side's model with the
    relationships between them (the split wizard, D283), separate from it."""
    from . import model_wizards as mw
    data = get(conn, model, analysis)
    side = int(d.get("side") or 0)
    if side >= len(data["sides"]) or data["sides"][side].get("kind") != "model":
        raise EditError("Choose a side that is a model as it is now: the new model is copied from it.")
    guids = _common_members(data, d.get("items")).get(side) or []
    if not guids:
        raise EditError(f"{data['sides'][side].get('label')} has none of the common elements chosen.")
    name = (d.get("name") or "").strip() or f"Common: {data['name']}"
    return mw.split(conn, data["sides"][side]["model_id"], user, {
        "name": name, "entities": guids, "child": False,
        "description": (d.get("description") or "").strip() or f"What {', '.join(s.get('label') or '' for s in data['sides'])} have in common "
                                                                 f"(common analysis '{data['name']}')."})


# ---------------------------------------------------------------- downloads
def to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    bold, head, green = Font(bold=True), PatternFill("solid", fgColor="DDE6F0"), PatternFill("solid", fgColor="E3F4E6")
    labels = [s.get("label") or f"Side {n + 1}" for n, s in enumerate(data["sides"])]

    def sheet(ws, cols, rows, mark=None):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = bold, head
        for r in rows:
            ws.append(r)
            if mark is not None and r[mark] == "yes":
                for c in ws[ws.max_row]:
                    c.fill = green
        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(50, max(10, *(len(str(c.value or "")) for c in col[:200])))
    ws = wb.active
    ws.title = "Summary"
    t = data["totals"]
    sheet(ws, ["Entity type", "Layer", "Elements", "Common", "Common, values differ"] + [f"In {k}" for k in range(len(labels), 0, -1)],
          [[s["name"], s["layer"], s["elements"], s["common"], s["differ"]] + [s["by_count"].get(str(k), 0) for k in range(len(labels), 0, -1)]
           for s in data["summary"]])
    ws.append([])
    ws.append([f"Common means in at least {t.get('threshold')} of {t.get('sides')}: {t.get('common')} of {t.get('elements')} elements; "
               f"{t.get('in_all')} in all; {t.get('only_one')} in only one."])
    live = [i for i in data["items"] if not i["gone"]]
    sheet(wb.create_sheet("Elements"), ["Entity type", "Element", "In how many", "Common"] + labels + ["Values that differ", "Decision", "Note"],
          [[i["entity_type_name"], i["name"], i["sides_count"], "yes" if i["is_common"] else "no"]
           + [(i["members"].get(str(k)) or {}).get("name") or "" for k in range(len(labels))]
           + ["; ".join(d["label"] for d in i["differs"]), i["decision"], i["note"]] for i in live], mark=3)
    rows = []
    for i in live:
        for d in i["differs"]:
            rows.append([i["entity_type_name"], i["name"], d["label"]] + [str(d["values"].get(str(k)) if d["values"].get(str(k)) is not None else "")
                                                                         for k in range(len(labels))])
    sheet(wb.create_sheet("Values that differ"), ["Entity type", "Element", "Field"] + labels, rows)
    sheet(wb.create_sheet("Relationships"), ["Relationship", "Source", "Target", "In how many", "Common"] + labels,
          [[r["relationship_type"], r["source"], r["target"], r["count"], "yes" if r["common"] else "no"]
           + ["yes" if k in r["sides"] else "" for k in range(len(labels))] for r in data["relationships"]], mark=4)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_docx(data: dict) -> bytes:
    t = data["totals"]
    labels = [s.get("label") or f"Side {n + 1}" for n, s in enumerate(data["sides"])]
    body = [gp._p(data["name"], "Title")]
    if data["description"]:
        body.append(gp._p(data["description"]))
    body.append(gp._p(f"Compared: {', '.join(labels)}. Common means in at least {t.get('threshold')} of {t.get('sides')}. "
                      f"{t.get('common')} of {t.get('elements')} elements are common ({t.get('in_all')} in all), and {t.get('differ')} "
                      f"of them have values that differ."))
    body.append(gp._p("Summary", "Heading1"))
    body.append(gp._table([["Entity type", "Elements", "Common", "Values differ"]] +
                          [[s["name"], str(s["elements"]), str(s["common"]), str(s["differ"])] for s in data["summary"]]))
    live = [i for i in data["items"] if not i["gone"] and i["is_common"]]
    body.append(gp._p("The common elements", "Heading1"))
    by: dict[str, list] = {}
    for i in live:
        by.setdefault(i["entity_type_name"], []).append(i)
    for name, group in by.items():
        body.append(gp._p(name, "Heading2"))
        body.append(gp._table([["Element", "In", "Values that differ", "Decision", "Note"]] +
                              [[i["name"], f"{i['sides_count']} of {len(labels)}", "; ".join(d["label"] for d in i["differs"]),
                                i["decision"], i["note"]] for i in group]))
    common_r = [r for r in data["relationships"] if r["common"]]
    if common_r:
        body.append(gp._p("Common relationships", "Heading1"))
        body.append(gp._table([["Source", "Relationship", "Target", "In"]] +
                              [[r["source"], r["relationship_type"], r["target"], f"{r['count']} of {len(labels)}"] for r in common_r[:500]]))
    return gp.docx_from(body)
