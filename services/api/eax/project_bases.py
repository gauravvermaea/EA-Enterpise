"""Project bases (owner, 8 Nov 2026, phase 13.1, D303, D304): a hierarchy of projects like the models'.

    Empty project          read-only for everyone; nothing in it
      TOGAF 10 project     read-only for everyone; every ADM step, the TOGAF 10 content metamodel, TOGAF's principles
                           (with security ones), the BDAT and security standards, a charter
        Organisation base  Super Admins change it: its steps, principles, standards and charter are the organisation's
          every project    derives from the Organisation base (a library project may derive from the Empty project)

What a base holds is offered down (owner: "offer it down"): a new project takes everything at once; a running project
sees what is new or changed in its base and a Project Admin or Lead Architect takes it or skips it. Principles and
standards are mandatory below the base (a project cannot change or remove them; it may add its own, and ask for a
dispensation in its governance log).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one

NS = uuid.UUID("2a8d9a0e-6f1b-4f7e-9c3a-13b1b0a5e001")
EMPTY_GUID = str(uuid.uuid5(NS, "empty"))
TOGAF_GUID = str(uuid.uuid5(NS, "togaf10"))
ORG_GUID = str(uuid.uuid5(NS, "organisation"))
BASES = [  # (kind, guid, name, description)
    ("empty", EMPTY_GUID, "Empty project", "The top of the project hierarchy: nothing in it. Read-only."),
    ("togaf", TOGAF_GUID, "TOGAF 10 project", "Every step of the TOGAF 10 ADM, the TOGAF 10 content metamodel, TOGAF's principles with "
     "security ones, business, data, application, technology and security standards, and an architecture charter. Read-only."),
    ("org", ORG_GUID, "Organisation base", "The organisation's own base, made from the TOGAF 10 project: its steps, principles, "
     "standards and charter apply to every project. Changed by Super Admins only."),
]
READ_ONLY = {"empty", "togaf"}
KINDS = ("principle", "standard", "step")
P_FIELDS = ("name", "area", "statement", "rationale", "implications")
S_FIELDS = ("name", "area", "description", "status", "source")


def seed() -> dict:
    return json.loads((Path(__file__).resolve().parent / "seed" / "project_bases.json").read_text(encoding="utf-8"))


def _lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def bases_sql(togaf_model_guid: str) -> str:
    """The three bases, idempotent (only what is missing; a Super Admin's changes to the Organisation base are kept),
    and every project that has no base yet put under the Organisation base."""
    s = seed()
    out = ["-- project bases (phase 13.1, D303)\n"]
    for kind, g, name, desc in BASES:
        out.append(f"""INSERT INTO proj.projects (guid, name, purpose, description, base_kind, status, repo_state, repo_note, created_by)
VALUES ({_lit(g)}::uuid, {_lit(name)}, 'base', {_lit(desc)}, {_lit(kind)}, 'active', 'ready',
        'A project base has no repository of its own.', 'system')
ON CONFLICT (guid) DO NOTHING;\n""")
    pid = lambda g: f"(SELECT id FROM proj.projects WHERE guid = {_lit(g)}::uuid)"  # noqa: E731
    out.append(f"UPDATE proj.projects SET base_id = {pid(EMPTY_GUID)} WHERE guid = {_lit(TOGAF_GUID)}::uuid AND base_id IS NULL;\n")
    out.append(f"UPDATE proj.projects SET base_id = {pid(TOGAF_GUID)} WHERE guid = {_lit(ORG_GUID)}::uuid AND base_id IS NULL;\n")
    for g in (TOGAF_GUID, ORG_GUID):          # both point at the TOGAF 10 content metamodel
        out.append(f"""INSERT INTO proj.project_models (project_id, model_guid, how, added_by)
SELECT {pid(g)}, {_lit(togaf_model_guid)}::uuid, 'added', 'system' ON CONFLICT DO NOTHING;\n""")
    # TOGAF 10: every step of the library, once
    out.append(f"""INSERT INTO proj.steps (project_id, cycle, phase, seq, name, library_id, guid)
SELECT {pid(TOGAF_GUID)}, 1, s.phase, s.seq, s.name, s.id, md5('togaf-step-' || s.id)::uuid
  FROM proj.lib_steps s WHERE NOT s.retired
   AND NOT EXISTS (SELECT 1 FROM proj.steps x WHERE x.guid = md5('togaf-step-' || s.id)::uuid);\n""")
    # every document type of the library (the ones picked by default in use), once; the Organisation base copies them
    for g in (TOGAF_GUID, ORG_GUID):
        out.append(f"""INSERT INTO proj.items (project_id, phase, name, kind, type, library_id, chosen, folder, approved_folder)
SELECT {pid(g)}, i.phase, i.name, i.kind, i.type, i.id, i.default_pick, i.work_folder, i.approved_folder
  FROM proj.lib_items i WHERE NOT i.retired AND NOT EXISTS (SELECT 1 FROM proj.items x WHERE x.project_id = {pid(g)});\n""")
    # the shared template libraries (so each document type shows its templates)
    for g in (TOGAF_GUID, ORG_GUID):
        out.append(f"""INSERT INTO proj.project_libraries (project_id, library_id, sort_order)
SELECT {pid(g)}, l.id, row_number() OVER (ORDER BY l.id) FROM proj.template_libraries l
 WHERE l.shared AND NOT EXISTS (SELECT 1 FROM proj.project_libraries x WHERE x.project_id = {pid(g)});\n""")
    # its principles and standards (mandatory below it) and its charter
    for n, p in enumerate(s["principles"], 1):
        out.append(f"""INSERT INTO proj.principles (project_id, name, area, statement, rationale, implications, mandatory, sort_order, guid, created_by)
SELECT {pid(TOGAF_GUID)}, {_lit(p['name'])}, {_lit(p['area'])}, {_lit(p['statement'])}, {_lit(p['rationale'])}, {_lit(p['implications'])},
       true, {n}, md5('togaf-principle-' || {_lit(p['name'])})::uuid, 'system'
 WHERE NOT EXISTS (SELECT 1 FROM proj.principles x WHERE x.guid = md5('togaf-principle-' || {_lit(p['name'])})::uuid);\n""")
    for n, x in enumerate(s["standards"], 1):
        out.append(f"""INSERT INTO proj.standards (project_id, area, name, description, status, source, mandatory, sort_order, guid, created_by)
SELECT {pid(TOGAF_GUID)}, {_lit(x['area'])}, {_lit(x['name'])}, {_lit(x['description'])}, {_lit(x['status'])}, {_lit(x['source'])},
       true, {n}, md5('togaf-standard-' || {_lit(x['name'])})::uuid, 'system'
 WHERE NOT EXISTS (SELECT 1 FROM proj.standards y WHERE y.guid = md5('togaf-standard-' || {_lit(x['name'])})::uuid);\n""")
    sections = json.dumps({c["key"]: c["html"] for c in s["charter"]})
    for g in (TOGAF_GUID, ORG_GUID):
        out.append(f"""INSERT INTO proj.charters (project_id, sections, modified_by) SELECT {pid(g)}, {_lit(sections)}::jsonb, 'system'
ON CONFLICT (project_id) DO NOTHING;\n""")
    # the Organisation base takes the TOGAF 10 project's steps, principles and standards once (then Super Admins own it)
    out.append(f"""INSERT INTO proj.steps (project_id, cycle, phase, seq, name, library_id, guid, origin_guid)
SELECT {pid(ORG_GUID)}, 1, s.phase, s.seq, s.name, s.library_id, md5('org-' || s.guid::text)::uuid, s.guid
  FROM proj.steps s WHERE s.project_id = {pid(TOGAF_GUID)} AND s.parent_step_id IS NULL
   AND NOT EXISTS (SELECT 1 FROM proj.steps x WHERE x.project_id = {pid(ORG_GUID)});\n""")
    out.append(f"""INSERT INTO proj.principles (project_id, name, area, statement, rationale, implications, mandatory, sort_order, guid, origin_guid, created_by)
SELECT {pid(ORG_GUID)}, p.name, p.area, p.statement, p.rationale, p.implications, true, p.sort_order, md5('org-' || p.guid::text)::uuid, p.guid, 'system'
  FROM proj.principles p WHERE p.project_id = {pid(TOGAF_GUID)}
   AND NOT EXISTS (SELECT 1 FROM proj.principles x WHERE x.project_id = {pid(ORG_GUID)});\n""")
    out.append(f"""INSERT INTO proj.standards (project_id, area, name, description, status, source, mandatory, sort_order, guid, origin_guid, created_by)
SELECT {pid(ORG_GUID)}, x.area, x.name, x.description, x.status, x.source, true, x.sort_order, md5('org-' || x.guid::text)::uuid, x.guid, 'system'
  FROM proj.standards x WHERE x.project_id = {pid(TOGAF_GUID)}
   AND NOT EXISTS (SELECT 1 FROM proj.standards y WHERE y.project_id = {pid(ORG_GUID)});\n""")
    # every other project derives from the Organisation base (owner: "all projects derive from this organisation one")
    out.append(f"UPDATE proj.projects SET base_id = {pid(ORG_GUID)} WHERE base_kind = '' AND base_id IS NULL;\n")
    return "".join(out)


# ---------------------------------------------------------------- the rules
def check_change(p: dict, user) -> None:
    """A base is read-only (the Empty and TOGAF 10 projects), or Super Admins only (the Organisation base)."""
    kind = p.get("base_kind") or ""
    if kind in READ_ONLY:
        raise EditError(f"{p['name']} is a project base: read-only for everyone.", 409)
    if kind == "org" and not pj._super(user):
        raise EditError(f"{p['name']} is the organisation's base: only Super Admins change it.", 403)


def base_row(conn, p: dict) -> dict | None:
    return _one(conn, "SELECT * FROM proj.projects WHERE id = :b", b=p["base_id"]) if p.get("base_id") else None


def chain(conn, p: dict) -> list[dict]:
    """The project and the bases above it, nearest first."""
    out, seen, cur = [], set(), p
    while cur and cur["id"] not in seen and len(out) < 10:
        seen.add(cur["id"])
        out.append({"id": str(cur["guid"]), "name": cur["name"], "base_kind": cur.get("base_kind") or "", "is_library": cur.get("is_library")})
        cur = base_row(conn, cur)
    return out


def _skips(conn, p: dict) -> set[tuple[str, str]]:
    return {(r["kind"], str(r["origin_guid"])) for r in _rows(conn, "SELECT kind, origin_guid FROM proj.base_skips WHERE project_id = :p", p=p["id"])}


def offers(conn, p: dict) -> list[dict]:
    """What the project's base holds that the project has not taken (or has taken in an older form) and not skipped."""
    b = base_row(conn, p)
    if not b:
        return []
    skipped = _skips(conn, p)
    out: list[dict] = []
    for kind, table, fields in (("principle", "principles", P_FIELDS), ("standard", "standards", S_FIELDS)):
        cols = ", ".join(fields)
        mine = {str(r["origin_guid"]): r for r in _rows(conn, f"SELECT id, origin_guid, mandatory, {cols} FROM proj.{table} "
                                                              "WHERE project_id = :p AND origin_guid IS NOT NULL", p=p["id"])}
        for r in _rows(conn, f"SELECT guid, mandatory, {cols} FROM proj.{table} WHERE project_id = :b ORDER BY area, sort_order, name", b=b["id"]):
            g = str(r["guid"])
            have = mine.get(g)
            if have is None:
                if (kind, g) not in skipped:
                    out.append({"kind": kind, "action": "add", "id": g, "name": r["name"], "area": r["area"], "mandatory": r["mandatory"]})
            elif any((have[f] or "") != (r[f] or "") for f in fields) or have["mandatory"] != r["mandatory"]:
                out.append({"kind": kind, "action": "update", "id": g, "name": r["name"], "area": r["area"], "mandatory": r["mandatory"],
                            "changed": [f for f in fields if (have[f] or "") != (r[f] or "")]})
    have_steps = _rows(conn, "SELECT origin_guid, library_id, phase, lower(name) AS n FROM proj.steps WHERE project_id = :p AND cycle = :c",
                       p=p["id"], c=p.get("cycle") or 1)
    by_origin = {str(s["origin_guid"]) for s in have_steps if s["origin_guid"]}
    by_lib = {s["library_id"] for s in have_steps if s["library_id"]}
    by_name = {(s["phase"], s["n"]) for s in have_steps}
    for s in _rows(conn, """SELECT guid, phase, seq, name, library_id FROM proj.steps WHERE project_id = :b AND NOT removed
                             AND parent_step_id IS NULL ORDER BY phase, seq""", b=b["id"]):
        g = str(s["guid"])
        if g in by_origin or (s["library_id"] and s["library_id"] in by_lib) or (s["phase"], s["name"].lower()) in by_name:
            continue
        if ("step", g) not in skipped:
            out.append({"kind": "step", "action": "add", "id": g, "name": s["name"], "area": s["phase"], "mandatory": False})
    return out


def _take(conn, p: dict, b: dict, o: dict, user) -> None:
    by = getattr(user, "username", "system")
    if o["kind"] in ("principle", "standard"):
        table, fields = ("principles", P_FIELDS) if o["kind"] == "principle" else ("standards", S_FIELDS)
        r = _one(conn, f"SELECT * FROM proj.{table} WHERE project_id = :b AND guid = CAST(:g AS uuid)", b=b["id"], g=o["id"])
        if not r:
            raise EditError(f"That {o['kind']} is no longer in the base.", 404)
        vals = {f: r[f] for f in fields}
        mine = _one(conn, f"SELECT id FROM proj.{table} WHERE project_id = :p AND origin_guid = CAST(:g AS uuid)", p=p["id"], g=o["id"])
        if mine:
            sets = ", ".join(f"{f} = :{f}" for f in fields)
            conn.execute(text(f"UPDATE proj.{table} SET {sets}, mandatory = :m WHERE id = :i"), {**vals, "m": r["mandatory"], "i": mine["id"]})
        else:
            cols = ", ".join(fields)
            conn.execute(text(f"""INSERT INTO proj.{table} (project_id, {cols}, mandatory, sort_order, origin_guid, created_by)
                                  VALUES (:p, {', '.join(':' + f for f in fields)}, :m, :o, CAST(:g AS uuid), :u)"""),
                         {**vals, "p": p["id"], "m": r["mandatory"], "o": r["sort_order"], "g": o["id"], "u": by})
    else:
        s = _one(conn, "SELECT * FROM proj.steps WHERE project_id = :b AND guid = CAST(:g AS uuid)", b=b["id"], g=o["id"])
        if not s:
            raise EditError("That step is no longer in the base.", 404)
        seq = (_one(conn, "SELECT coalesce(max(seq), 0) AS n FROM proj.steps WHERE project_id = :p AND phase = :ph AND parent_step_id IS NULL",
                    p=p["id"], ph=s["phase"]) or {"n": 0})["n"]
        conn.execute(text("""INSERT INTO proj.steps (project_id, cycle, phase, seq, name, library_id, origin_guid, added_by, added_at)
                             VALUES (:p, :c, :ph, :q, :n, :l, CAST(:g AS uuid), :u, now())"""),
                     {"p": p["id"], "c": p.get("cycle") or 1, "ph": s["phase"], "q": max(seq + 1, s["seq"]), "n": s["name"],
                      "l": s["library_id"], "g": o["id"], "u": by})


def take_all_new(conn, p: dict, user, steps: bool = False) -> int:
    """A new project takes its base's principles and standards (and, when asked, its steps) at once."""
    b = base_row(conn, p)
    if not b:
        return 0
    n = 0
    for o in offers(conn, p):
        if o["kind"] != "step" or steps:
            _take(conn, p, b, o, user)
            n += 1
    _copy_charter(conn, p, b)
    return n


def _copy_charter(conn, p: dict, b: dict) -> None:
    conn.execute(text("""INSERT INTO proj.charters (project_id, sections, modified_by)
                         SELECT :p, sections, 'system' FROM proj.charters WHERE project_id = :b
                         ON CONFLICT (project_id) DO NOTHING"""), {"p": p["id"], "b": b["id"]})


# ---------------------------------------------------------------- what the screens call
def view(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    b = base_row(conn, p)
    may = False
    try:
        pj._need(conn, p, user, "admin")
        may = not p.get("base_kind") or p.get("base_kind") == "org"
    except EditError:
        may = False
    # what a project may derive from: the Organisation base, or a library project below it (owner, 8 Nov 2026)
    bases = [{k: r[k] for k in ("id", "name", "base_kind", "is_library")} for r in _rows(conn, """
                SELECT *, guid::text AS id FROM proj.projects WHERE base_kind = 'org' OR (is_library AND base_kind = '')
                 ORDER BY base_kind = '', name""") if r["base_kind"] == "org" or under_org(conn, r)]
    return {"chain": chain(conn, p), "base": {"id": str(b["guid"]), "name": b["name"]} if b else None,
            "offers": offers(conn, p) if not p.get("base_kind") or p.get("base_kind") == "org" else [], "may_take": may,
            "may_rebase": pj._super(user) and not p.get("base_kind"), "bases": bases}


def decide(conn, project: Any, user, kind: str, guid: str, take: bool) -> dict:
    """Take or skip one offer from the base ('*' as guid: every offer)."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "admin")
    if p.get("base_kind") in READ_ONLY:
        raise EditError(f"{p['name']} is a project base: read-only for everyone.", 409)
    b = base_row(conn, p)
    if not b:
        raise EditError("This project has no base.", 409)
    todo = [o for o in offers(conn, p) if (guid == "*" or o["id"] == guid) and (kind == "*" or o["kind"] == kind)]
    if not todo:
        raise EditError("Nothing like that is offered from the base.", 404)
    for o in todo:
        if take:
            _take(conn, p, b, o, user)
        else:
            if o["mandatory"]:
                raise EditError(f"{o['name']} is mandatory: it cannot be skipped (ask for a dispensation in the governance log).", 409)
            conn.execute(text("""INSERT INTO proj.base_skips (project_id, kind, origin_guid, skipped_by) VALUES (:p, :k, CAST(:g AS uuid), :u)
                                 ON CONFLICT DO NOTHING"""), {"p": p["id"], "k": o["kind"], "g": o["id"], "u": user.username})
    n = len(todo)
    return {"message": f"{'Took' if take else 'Skipped'} {n} item{'s' if n != 1 else ''} from {b['name']}."}


def under_org(conn, b: dict) -> bool:
    """Every project comes from the Organisation base (owner, 8 Nov 2026): a project's base is the Organisation base
    itself, or a library project that sits below it."""
    cur, hops = b, 0
    while cur and hops < 30:
        if str(cur["guid"]) == ORG_GUID:
            return True
        cur, hops = base_row(conn, cur), hops + 1
    return False


def rebase(conn, project: Any, user, base: str) -> dict:
    """A Super Admin puts a project (a library project, say) under another base: a base or a library project."""
    if not pj._super(user):
        raise EditError("Only a Super Admin changes what a project derives from.", 403)
    p = pj.project_row(conn, project)
    if p.get("base_kind"):
        raise EditError("The project bases keep their place in the hierarchy.", 409)
    b = pj.project_row(conn, base)
    if not (b.get("base_kind") or b.get("is_library")) or b["id"] == p["id"]:
        raise EditError("A project derives from a project base or a library project.", 409)
    if not under_org(conn, b):
        raise EditError("Every project comes from the Organisation base: choose it, or a library project below it.", 409)
    cur, hops = b, 0
    while cur and hops < 30:                    # the new base must not sit below the project itself
        if cur["id"] == p["id"]:
            raise EditError("That would make the hierarchy go round in a circle.", 409)
        cur, hops = base_row(conn, cur), hops + 1
    conn.execute(text("UPDATE proj.projects SET base_id = :b WHERE id = :p"), {"b": b["id"], "p": p["id"]})
    return {"message": f"{p['name']} now derives from {b['name']}: what {b['name']} holds is offered on its Base tab."}


def tree(conn, user) -> dict:
    """Project admin's hierarchy: the bases and library projects as nodes, each with the projects right below it."""
    rows = _rows(conn, """SELECT p.id, p.guid::text AS gid, p.name, p.base_kind, p.is_library, p.base_id, p.status, p.description
                            FROM proj.projects p ORDER BY p.name""")
    by_id = {r["id"]: r for r in rows}
    nodes = []
    for r in rows:
        if not (r["base_kind"] or r["is_library"]):
            continue
        under = [x for x in rows if x["base_id"] == r["id"]]
        nodes.append({"id": r["gid"], "name": r["name"], "base_kind": r["base_kind"], "is_library": r["is_library"],
                      "parent": by_id[r["base_id"]]["gid"] if r["base_id"] in by_id else None, "description": r["description"],
                      "projects": [{"id": x["gid"], "name": x["name"], "status": x["status"]} for x in under
                                   if not (x["base_kind"] or x["is_library"])]})
    order = {"empty": 0, "togaf": 1, "org": 2, "": 3}
    nodes.sort(key=lambda n: (order.get(n["base_kind"], 3), n["name"]))
    return {"nodes": nodes, "super_admin": pj._super(user)}
