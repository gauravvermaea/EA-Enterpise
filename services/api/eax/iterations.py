"""ADM iteration types on a project (owner, 11 Nov 2026; D571-D574).

A project's current ADM cycle runs as one of TOGAF's iteration cycles, which decides which phases are **enabled**. The
others are frozen: read only, never hidden and never deleted; choosing another iteration unfreezes them exactly as they
were. Requirements Management (RM) and "across the cycle" (X) are always enabled. The owner first proposed Development =
A-F and Capability = Preliminary only, and accepted TOGAF's mapping instead (D571).

Any user who can open the project may change the iteration at any time (not while the project is read only); every
change is kept, per cycle, in proj.iteration_changes. A cycle with no change recorded runs as a Full cycle, and the
project page asks which iteration it is. The rules live here, in Python (D248); web/src/iterations.js is the twin.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .metamodel_edit import EditError

# the phases, in ADM order; C-D and C-A follow C; RM and X are always enabled
PHASES = ["P", "A", "B", "C", "D", "E", "F", "G", "H"]
FOLLOWS = {"C-D": "C", "C-A": "C"}
ALWAYS = {"RM", "X", ""}
PHASE_NAMES = {"P": "Preliminary", "A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "G": "G", "H": "H"}

ITERATIONS: dict[str, dict] = {
    "full": {"name": "Full cycle", "phases": PHASES,
             "about": "Every phase, Preliminary to H."},
    "capability": {"name": "Architecture Capability iteration", "phases": ["P", "A"],
                   "about": "Establishes or changes the architecture capability: Preliminary and Architecture Vision."},
    "development": {"name": "Architecture Development iteration", "phases": ["B", "C", "D"],
                    "about": "Creates architecture content: Business, Information Systems and Technology Architecture."},
    "transition": {"name": "Transition Planning iteration", "phases": ["E", "F"],
                   "about": "Plans the change: Opportunities and Solutions, and Migration Planning."},
    "governance": {"name": "Architecture Governance iteration", "phases": ["G", "H"],
                   "about": "Governs implementation and change: Implementation Governance and Change Management."},
    "custom": {"name": "Custom iteration", "phases": None,
               "about": "The phases you tick."},
}
DEFAULT = "full"


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)


def _arr(v: Any) -> list[str]:
    """A text[] as a list (drivers give a list; some give the literal "{E,F}")."""
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip().strip('"') for x in v.strip("{}").split(",") if x.strip()]
    return list(v)


def base_phase(phase: str | None) -> str:
    ph = (phase or "").strip()
    return FOLLOWS.get(ph, ph)


def clean(iteration: Any, phases: Any = None) -> tuple[str, list[str]]:
    """Checks an iteration and returns (code, enabled phases in ADM order). Built-in iterations' phases are fixed;
    a custom one needs at least one phase, each a real one."""
    code = str(iteration or "").strip().lower()
    if code not in ITERATIONS:
        raise EditError(f"No iteration {iteration!r}: choose one of " + ", ".join(i["name"] for i in ITERATIONS.values()) + ".")
    if code != "custom":
        return code, list(ITERATIONS[code]["phases"])
    if isinstance(phases, str):
        phases = phases.replace(";", ",").split(",")
    picked = set()
    for x in phases or []:
        s = str(x).strip()
        if s:
            picked.add("P" if s.lower() in ("p", "preliminary") else base_phase(s.upper()))
    bad = sorted(x for x in picked if x not in PHASES)
    if bad:
        raise EditError("Not ADM phases: " + ", ".join(bad) + ". Choose from Preliminary and A to H.")
    if not picked:
        raise EditError("A custom iteration needs at least one phase ticked.")
    return code, [x for x in PHASES if x in picked]


def label(code: str, phases: list[str]) -> str:
    names = ["Preliminary" if x == "P" else x for x in phases]
    return f"{ITERATIONS.get(code, ITERATIONS[DEFAULT])['name']} ({', '.join(names)})"


def current(conn, p: dict) -> dict:
    """The project's iteration in its current cycle: {code, name, phases, label, chosen, by, at}."""
    r = conn.execute(text("""SELECT iteration, phases, by_user, at FROM proj.iteration_changes
                              WHERE project_id = :p AND cycle = :c ORDER BY id DESC LIMIT 1"""),
                     {"p": p["id"], "c": p.get("cycle") or 1}).mappings().first()
    if not r:
        code, phases = DEFAULT, list(PHASES)
        return {"code": code, "name": ITERATIONS[code]["name"], "phases": phases, "label": label(code, phases),
                "chosen": False, "by": None, "at": None}
    code = r["iteration"] if r["iteration"] in ITERATIONS else DEFAULT
    phases = [x for x in PHASES if x in _arr(r["phases"])] or list(PHASES)
    return {"code": code, "name": ITERATIONS[code]["name"], "phases": phases, "label": label(code, phases),
            "chosen": True, "by": r["by_user"], "at": _iso(r["at"])}


def enabled(it: dict, phase: str | None) -> bool:
    ph = base_phase(phase)
    return ph in ALWAYS or ph not in PHASES or ph in it["phases"]


def phase_enabled(conn, p: dict, phase: str | None) -> bool:
    return enabled(current(conn, p), phase)


def guard(conn, p: dict, phase: str | None) -> None:
    """Refuses a change in a phase the project's iteration leaves out (409); the API's guard, not only the screens'."""
    if p.get("base_kind"):
        return
    it = current(conn, p)
    if not enabled(it, phase):
        ph = base_phase(phase)
        name = "The Preliminary phase" if ph == "P" else f"Phase {ph}"
        raise EditError(f"{name} isn't part of this {it['name']}. Change the iteration to work on it.", 409)


def guard_item(conn, p: dict, item_id: Any) -> None:
    if not item_id:
        return
    r = conn.execute(text("SELECT phase FROM proj.items WHERE id = :i"), {"i": item_id}).mappings().first()
    if r:
        guard(conn, p, r["phase"])


def guard_doc(conn, p: dict, d: dict) -> None:
    guard_item(conn, p, d.get("item_id"))


def history(conn, p: dict) -> list[dict]:
    rows = conn.execute(text("""SELECT cycle, iteration, phases, previous_iteration, previous_phases, by_user, at, note
                                  FROM proj.iteration_changes WHERE project_id = :p ORDER BY id DESC"""),
                        {"p": p["id"]}).mappings().all()
    out = []
    for r in rows:
        prev = (label(r["previous_iteration"], _arr(r["previous_phases"]) or list(PHASES)) if r["previous_iteration"]
                else label(DEFAULT, list(PHASES)) + ", not chosen")
        out.append({"cycle": r["cycle"], "to": label(r["iteration"], _arr(r["phases"])), "from": prev,
                    "iteration": r["iteration"], "phases": _arr(r["phases"]), "by": r["by_user"],
                    "at": _iso(r["at"]), "note": r["note"] or ""})
    return out


def set_iteration(conn, project: Any, user, iteration: Any, phases: Any = None, note: str = "") -> dict:
    """Any user who can open the project changes its iteration, at any time; kept with who, when, from and to."""
    from . import projects as pj
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    if p.get("status") in ("finishing", "frozen", "merged", "closed"):
        raise EditError(f"{p['name']} is {p['status']}: its iteration is read only.", 409)
    code, enabled_phases = clean(iteration, phases)
    was = current(conn, p)
    if was["chosen"] and was["code"] == code and was["phases"] == enabled_phases:
        return {"iteration": was, "message": f"Already a {was['label']}."}
    conn.execute(text("""INSERT INTO proj.iteration_changes (project_id, cycle, iteration, phases, previous_iteration,
                                                             previous_phases, by_user, note)
                         VALUES (:p, :c, :i, :ph, :pi, :pp, :u, :n)"""),
                 {"p": p["id"], "c": p.get("cycle") or 1, "i": code, "ph": enabled_phases,
                  "pi": was["code"] if was["chosen"] else None, "pp": was["phases"] if was["chosen"] else None,
                  "u": getattr(user, "username", "system"), "n": (note or "").strip()[:500]})
    from . import audit
    audit.record(pj.core(conn), actor=getattr(user, "username", "system"), action="project.iteration", object_type="project",
                 object_id=str(p["guid"]), details={"name": p["name"], "cycle": p.get("cycle") or 1,
                                                    "from": was["label"], "to": label(code, enabled_phases),
                                                    "note": (note or "").strip()[:500]})
    now = current(conn, p)
    frozen = [x for x in PHASES if x not in now["phases"]]
    return {"iteration": now, "frozen": frozen,
            "message": f"Now a {now['label']}." + (f" Frozen (read only): {', '.join('Preliminary' if x == 'P' else x for x in frozen)}." if frozen else "")}


def catalogue() -> list[dict]:
    return [{"code": k, "name": v["name"], "phases": v["phases"], "about": v["about"]} for k, v in ITERATIONS.items()]
