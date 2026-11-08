"""A project's stakeholder matrix (owner, 8 Nov 2026, D294): TOGAF's stakeholder management.

Each stakeholder is typed in (a person or a group; not linked to users or model entities). It has:
- its TOGAF category (corporate functions, end-user organisation, systems operations, project organisation, outside
  services), organisation, role and contact details;
- power (influence) and interest, High/Medium/Low; the class (key players, keep satisfied, keep informed, minimal
  effort) is worked out from them on a 3x3 grid (CLASS_OF) and may be set by hand;
- its position: ability to disrupt, understanding now and needed, commitment now and needed, support needed;
- its concerns, and the project's viewpoints and document classes that answer them;
- how it is engaged (approach, how often, channel, who looks after it), the next contact, notes (rich text);
- any number of dated discussion notes (rich text); the last contact is the latest of them.

Everyone on the project sees the matrix; contributors change it. A new project starts with its template's suggested
stakeholders; a derived project copies its parent's (without the discussions). The sponsor stays on its own step.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError
from .project_work import clean_html

_rows, _one = pj._rows, pj._one

CATEGORIES = {"corporate": "Corporate functions", "end-user": "End-user organisation", "operations": "Systems operations",
              "project": "Project organisation", "outside": "Outside services"}
LEVELS = {"H": "High", "M": "Medium", "L": "Low"}
CLASSES = {"key": "Key players", "satisfied": "Keep satisfied", "informed": "Keep informed", "minimal": "Minimal effort"}
APPROACH = {"key": "Engage closely", "satisfied": "Consult", "informed": "Inform", "minimal": "Monitor"}
# power -> interest -> class (owner, 8 Nov 2026)
CLASS_OF = {"H": {"H": "key", "M": "key", "L": "satisfied"},
            "M": {"H": "key", "M": "informed", "L": "satisfied"},
            "L": {"H": "informed", "M": "informed", "L": "minimal"}}
POSITION = ("disrupt", "understanding_now", "understanding_needed", "commitment_now", "commitment_needed", "support_needed")
TEXT = ("organisation", "role_title", "email", "phone", "concerns", "approach", "frequency", "channel", "owner")
RANK = {"": 0, "L": 1, "M": 2, "H": 3}


def auto_class(power: str, interest: str) -> str:
    """The class from power and interest; '' until both are given."""
    return CLASS_OF.get(power or "", {}).get(interest or "", "")


def _level(v: Any, what: str) -> str:
    v = (str(v or "").strip()[:1]).upper()
    if v not in ("", "H", "M", "L"):
        raise EditError(f"{what} is High, Medium or Low.")
    return v


def _date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as exc:
        raise EditError("The next contact is a date (YYYY-MM-DD).") from exc


def clean(d: dict, item_ids: dict[str, int] | None = None) -> dict:
    """A stakeholder's fields, checked (item_ids: the project's document classes, guid -> id)."""
    name = (d.get("name") or "").strip()
    if not name:
        raise EditError("Give the stakeholder a name (a person or a group).")
    cat = (d.get("category") or "").strip()
    if cat and cat not in CATEGORIES:
        raise EditError(f"The category is one of: {', '.join(CATEGORIES.values())}.")
    cls = (d.get("class") or "").strip()
    if cls and cls not in CLASSES:
        raise EditError(f"The class is one of: {', '.join(CLASSES.values())}.")
    out = {"name": name[:200], "category": cat, "power": _level(d.get("power"), "Power"),
           "interest": _level(d.get("interest"), "Interest"), "class": cls,
           "next_contact": _date(d.get("next_contact")), "notes_html": clean_html(d.get("notes_html")),
           "viewpoints": [str(v)[:20] for v in d.get("viewpoints") or [] if v]}
    for k in POSITION:
        out[k] = _level(d.get(k), k.replace("_", " ").capitalize())
    for k in TEXT:
        out[k] = (d.get(k) or "").strip()[:2000 if k == "concerns" else 300]
    if item_ids is not None:
        out["items"] = [item_ids[g] for g in d.get("items") or [] if g in item_ids]
    return out


def _items(conn, p: dict) -> tuple[dict[str, int], dict[int, dict]]:
    rows = _rows(conn, "SELECT id, guid::text AS guid, name, phase FROM proj.items WHERE project_id = :p", p=p["id"])
    return {r["guid"]: r["id"] for r in rows}, {r["id"]: r for r in rows}


def _out(r: dict, items_by_id: dict[int, dict], last: dict[int, Any]) -> dict:
    auto = auto_class(r["power"], r["interest"])
    cls = r["class"] or auto
    gaps = [k.split("_")[0] for k in ("understanding", "commitment")
            if r[f"{k}_needed"] and RANK[r[f"{k}_now"]] < RANK[r[f"{k}_needed"]]]
    nxt = r.get("next_contact")
    lc = last.get(r["id"])
    return {"id": str(r["guid"]), "name": r["name"], "organisation": r["organisation"], "role_title": r["role_title"],
            "category": r["category"], "email": r["email"], "phone": r["phone"], "concerns": r["concerns"],
            "power": r["power"], "interest": r["interest"], "class": cls, "class_auto": auto, "class_set": bool(r["class"]),
            **{k: r[k] for k in POSITION}, "gaps": gaps,
            "approach": r["approach"] or (APPROACH.get(cls, "")), "approach_set": bool(r["approach"]),
            "frequency": r["frequency"], "channel": r["channel"], "owner": r["owner"],
            "next_contact": str(nxt)[:10] if nxt else "", "last_contact": str(lc)[:10] if lc else "",
            "overdue": bool(nxt and str(nxt)[:10] < date.today().isoformat()),
            "notes_html": r["notes_html"], "viewpoints": list(r["viewpoints"] or []),
            "items": [{"id": str(items_by_id[i]["guid"]), "name": items_by_id[i]["name"], "phase": items_by_id[i]["phase"]}
                      for i in (r["items"] or []) if i in items_by_id],
            "uncovered": not (r["viewpoints"] or r["items"]),
            "entity": ({"id": str(r["entity_guid"]), "model": str(r["entity_model"])} if r.get("entity_guid") else None),
            "modified_by": r.get("modified_by") or r["created_by"], "modified_at": r.get("modified_at") or r["created_at"]}


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    _ids, by_id = _items(conn, p)
    rows = _rows(conn, "SELECT * FROM proj.stakeholders WHERE project_id = :p ORDER BY sort_order, id", p=p["id"])
    last = {r["s"]: r["d"] for r in _rows(conn, """SELECT n.stakeholder_id AS s, max(n.held_on) AS d FROM proj.stakeholder_notes n
                                                     JOIN proj.stakeholders s ON s.id = n.stakeholder_id
                                                    WHERE s.project_id = :p GROUP BY n.stakeholder_id""", p=p["id"])}
    out = [_out(r, by_id, last) for r in rows]
    counts = {c: sum(1 for s in out if s["class"] == c) for c in CLASSES}
    return {"stakeholders": out, "categories": CATEGORIES, "levels": LEVELS, "classes": CLASSES, "approaches": APPROACH,
            "counts": counts, "may_edit": _may_edit(conn, p, user)}


def _may_edit(conn, p: dict, user) -> bool:
    try:
        pj._need(conn, p, user, "contribute")
        return True
    except EditError:
        return False


def _row(conn, p: dict, sid: str) -> dict:
    r = _one(conn, "SELECT * FROM proj.stakeholders WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=sid)
    if not r:
        raise EditError("No such stakeholder in this project.", 404)
    return r


_COLS = ("name", "organisation", "role_title", "category", "email", "phone", "concerns", "power", "interest", "class",
         *POSITION, "approach", "frequency", "channel", "owner", "next_contact", "notes_html", "viewpoints", "items")


def _write(conn, p: dict, user, vals: dict, sid: int | None = None) -> int:
    params = {**vals, "viewpoints": list(vals.get("viewpoints") or []), "items": list(vals.get("items") or []),
              "p": p["id"], "u": user.username}
    cast = {"viewpoints": "CAST(:viewpoints AS text[])", "items": "CAST(:items AS bigint[])"}
    cols = [c for c in _COLS if c in vals]
    if sid is None:
        params["o"] = (conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM proj.stakeholders WHERE project_id = :p"),
                                    {"p": p["id"]}).scalar() or 1)
        sql = (f"INSERT INTO proj.stakeholders (project_id, sort_order, created_by, {', '.join(cols)}) "
               f"VALUES (:p, :o, :u, {', '.join(cast.get(c, f':{c}') for c in cols)}) RETURNING id")
        return conn.execute(text(sql), params).scalar()
    sets = ", ".join(f"{c} = {cast.get(c, f':{c}')}" for c in cols)
    conn.execute(text(f"UPDATE proj.stakeholders SET {sets}, modified_by = :u, modified_at = now() WHERE id = :i"), {**params, "i": sid})
    return sid


def add(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    ids, _ = _items(conn, p)
    new = _write(conn, p, user, clean(d, ids))
    g = conn.execute(text("SELECT guid::text FROM proj.stakeholders WHERE id = :i"), {"i": new}).scalar()
    return {"id": g, "message": f"{d.get('name', '').strip()} added to the stakeholders."}


def update(conn, project: Any, user, sid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, sid)
    ids, _ = _items(conn, p)
    merged = {**{k: r[k] for k in _COLS if k != "items"}, **d}       # fields left out stay as they are
    if "items" not in d:
        by_id = {v: k for k, v in ids.items()}
        merged["items"] = [by_id[i] for i in r["items"] or [] if i in by_id]
    _write(conn, p, user, clean(merged, ids), r["id"])
    return {"id": sid, "message": f"{merged['name']} saved."}


def delete(conn, project: Any, user, sid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, sid)
    conn.execute(text("DELETE FROM proj.stakeholders WHERE id = :i"), {"i": r["id"]})
    return {"message": f"{r['name']} taken out of the stakeholders (with its discussion notes)."}


def reorder(conn, project: Any, user, order: list[str]) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    for n, g in enumerate(order or []):
        conn.execute(text("UPDATE proj.stakeholders SET sort_order = :n WHERE project_id = :p AND guid = CAST(:g AS uuid)"),
                     {"n": n, "p": p["id"], "g": g})
    return {"message": "Order saved."}


# ---------------------------------------------------------------- discussion notes
def notes(conn, project: Any, user, sid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    r = _row(conn, p, sid)
    rows = _rows(conn, "SELECT * FROM proj.stakeholder_notes WHERE stakeholder_id = :s ORDER BY held_on DESC, id DESC", s=r["id"])
    return {"stakeholder": r["name"], "notes": [{"id": str(n["guid"]), "held_on": str(n["held_on"])[:10], "title": n["title"],
                                                 "html": n["html"], "by": n["by_user"], "modified_at": n["modified_at"] or n["created_at"]}
                                                for n in rows]}


def _note_vals(d: dict) -> dict:
    html = clean_html(d.get("html"))
    if not (html or "").strip() and not (d.get("title") or "").strip():
        raise EditError("Write what was discussed.")
    held = d.get("held_on") or date.today().isoformat()
    try:
        held = date.fromisoformat(str(held)[:10])
    except ValueError as exc:
        raise EditError("When it was held is a date (YYYY-MM-DD).") from exc
    return {"h": held, "t": (d.get("title") or "").strip()[:200], "x": html}


def add_note(conn, project: Any, user, sid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, sid)
    v = _note_vals(d)
    g = conn.execute(text("""INSERT INTO proj.stakeholder_notes (stakeholder_id, held_on, title, html, by_user)
                             VALUES (:s, :h, :t, :x, :u) RETURNING guid::text"""), {**v, "s": r["id"], "u": user.username}).scalar()
    return {"id": g, "message": f"Discussion with {r['name']} on {v['h']} noted."}


def _note(conn, p: dict, nid: str) -> dict:
    n = _one(conn, """SELECT n.* FROM proj.stakeholder_notes n JOIN proj.stakeholders s ON s.id = n.stakeholder_id
                       WHERE s.project_id = :p AND n.guid = CAST(:g AS uuid)""", p=p["id"], g=nid)
    if not n:
        raise EditError("No such discussion note in this project.", 404)
    return n


def update_note(conn, project: Any, user, nid: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    n = _note(conn, p, nid)
    v = _note_vals({"held_on": str(n["held_on"]), "title": n["title"], "html": n["html"], **d})
    conn.execute(text("UPDATE proj.stakeholder_notes SET held_on = :h, title = :t, html = :x, modified_at = now() WHERE id = :i"),
                 {**v, "i": n["id"]})
    return {"id": nid, "message": "Discussion note saved."}


def delete_note(conn, project: Any, user, nid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    n = _note(conn, p, nid)
    conn.execute(text("DELETE FROM proj.stakeholder_notes WHERE id = :i"), {"i": n["id"]})
    return {"message": "Discussion note deleted."}


# ---------------------------------------------------------------- at creation: the template's suggestions, a parent's
def from_wizard(conn, p: dict, user, rows: list[dict]) -> int:
    """The stakeholders the wizard ends with (a template's suggestions, kept, changed or added to; or a parent's)."""
    ids, _ = _items(conn, p)
    n = 0
    for d in rows or []:
        if not (d.get("name") or "").strip():
            continue
        _write(conn, p, user, clean(d, ids))
        n += 1
    return n


def suggestions(spec: dict | None) -> list[dict]:
    """A template's suggested stakeholders, checked (the template keeps names, category, power, interest, concerns)."""
    out = []
    for s in (spec or {}).get("stakeholders") or []:
        try:
            c = clean(s)
        except EditError:
            continue
        out.append({k: c[k] for k in ("name", "category", "power", "interest", "concerns", "role_title") if c.get(k)})
    return out


def to_csv(conn, project: Any, user) -> tuple[str, bytes]:
    data = listing(conn, project, user)
    p = pj.project_row(conn, project)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Stakeholder", "Organisation", "Role", "Category", "Power", "Interest", "Class", "Ability to disrupt",
                "Understanding now", "Understanding needed", "Commitment now", "Commitment needed", "Support needed",
                "Concerns", "Viewpoints", "Document classes", "Approach", "How often", "Channel", "Looked after by",
                "Email", "Phone", "Last contact", "Next contact"])
    lv = lambda v: LEVELS.get(v, "")  # noqa: E731
    for s in data["stakeholders"]:
        w.writerow([s["name"], s["organisation"], s["role_title"], CATEGORIES.get(s["category"], ""), lv(s["power"]),
                    lv(s["interest"]), CLASSES.get(s["class"], ""), *[lv(s[k]) for k in POSITION], s["concerns"],
                    ", ".join(s["viewpoints"]), ", ".join(i["name"] for i in s["items"]), s["approach"], s["frequency"],
                    s["channel"], s["owner"], s["email"], s["phone"], s["last_contact"], s["next_contact"]])
    name = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in p["name"]).strip() or "project"
    return f"{name} - stakeholders.csv", ("﻿" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- into the architecture (owner, 8 Nov 2026, D302)
def _entity_text(r: dict) -> str:
    parts = [f"Role: {r['role_title']}" if r["role_title"] else "", f"Organisation: {r['organisation']}" if r["organisation"] else "",
             f"Concerns: {r['concerns']}" if r["concerns"] else ""]
    return "\n".join(x for x in parts if x)


def to_model(conn, project: Any, user, model: str | None = None, ids: list[str] | None = None) -> dict:
    """The stakeholders as Stakeholder entities in one of the project's models (the project's own model unless another
    is given): new ones are made, ones made before are brought up to date (name, role, organisation, concerns)."""
    from . import content
    from . import content_framework as cf
    from . import repository as repo
    from .project_work import _tag
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    mine = {str(r["g"]) for r in _rows(conn, "SELECT model_guid AS g FROM proj.project_models WHERE project_id = :p", p=p["id"])}
    model = str(model or p.get("home_model") or "")
    if not model or model not in mine:
        raise EditError("Choose one of the project's models for the stakeholders.")
    c = pj.core(conn)
    m = repo.get_model(c, model)
    try:
        et = repo._find_type(c, m["_id"], "Stakeholder")
    except repo.NotFound:
        types = _rows(c, "SELECT code, name, content_area FROM core.entity_types WHERE model_id = :m AND NOT is_deleted", m=m["_id"])
        found = [t for t in types if "vision.stakeholders" in cf.area_of_type(t["code"], t["name"], t["content_area"])[0]]
        if not found:
            raise EditError(f"{m['name']}'s metamodel has no Stakeholder type (nor one placed under Stakeholders in the content "
                            "framework).", 409) from None
        et = found[0]
    rows = _rows(conn, "SELECT * FROM proj.stakeholders WHERE project_id = :p ORDER BY sort_order, id", p=p["id"])
    if ids:
        rows = [r for r in rows if str(r["guid"]) in set(ids)]
    made = changed = 0
    for r in rows:
        desc = _entity_text(r)
        done = False
        if r.get("entity_guid") and str(r.get("entity_model")) == model:
            try:
                content.update_entity(c, model, str(r["entity_guid"]), {"name": r["name"], "description": desc}, user.username)
                changed += 1
                done = True
            except (repo.NotFound, EditError):
                done = False                   # the entity is gone: made again
        if not done:
            e = content.create_entity(c, model, {"entity_type": et["code"], "name": r["name"], "description": desc,
                                                 "tags": [_tag(p)]}, user.username, light=True)
            conn.execute(text("UPDATE proj.stakeholders SET entity_guid = CAST(:e AS uuid), entity_model = CAST(:m AS uuid) WHERE id = :i"),
                         {"e": str(e["id"]), "m": model, "i": r["id"]})
            made += 1
    return {"message": f"Stakeholders in {m['name']}: {made} new, {changed} brought up to date."}
