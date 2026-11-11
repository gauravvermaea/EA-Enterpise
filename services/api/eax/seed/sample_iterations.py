"""Laptop sample (owner, 11 Nov 2026; D571-D574): ADM iteration types on the sample projects, one of each state, made once.

* Protea Target Architecture 2028: a Full cycle, chosen.
* Protea Claims Transformation 2028: Full cycle, then Architecture Development (B, C, D), then Transition Planning (E, F)
  -- two changes in its history; its work in B to D is frozen (read only), not deleted.
* Karoo Operations architecture health check: an Architecture Governance iteration (G, H).
* Protea broker portal: a Custom iteration (A, B, E).
* Karoo Re as-is documentation: none chosen yet, so its page asks "Which iteration is this?".
Rows only, in proj.iteration_changes; a project that has any is left as it is.
"""

from __future__ import annotations

from sqlalchemy import text

PLAN = [
    ("Protea Target Architecture 2028 (sample project)", [("full", None, "user_lead_architect", "The whole cycle this year.")]),
    ("Protea Claims Transformation 2028 (sample)", [
        ("development", None, "user_lead_architect", "Business to Technology first; the vision is agreed."),
        ("transition", None, "user_architect", "B to D signed off: now the work packages and the roadmap."),
    ]),
    ("Karoo Operations architecture health check (sample)", [("governance", None, "user_architect", "Checking delivery against the architecture.")]),
    ("Protea broker portal (sample)", [("custom", ["A", "B", "E"], "user_stakeholder", "A light pass: vision, business and options.")]),
]


def run() -> list[str]:
    from .. import iterations as it
    from .. import projects as pj
    out = []
    with pj.connections(True) as pc:
        for name, changes in PLAN:
            p = pc.execute(text("SELECT id, cycle FROM proj.projects WHERE name = :n"), {"n": name}).mappings().first()
            if not p:
                continue
            if pc.execute(text("SELECT 1 FROM proj.iteration_changes WHERE project_id = :p LIMIT 1"), {"p": p["id"]}).first():
                continue
            prev = None
            for n, (code, phases, who, note) in enumerate(changes):
                code, enabled = it.clean(code, phases)
                pc.execute(text("""INSERT INTO proj.iteration_changes (project_id, cycle, iteration, phases, previous_iteration,
                                                                     previous_phases, by_user, at, note)
                                   VALUES (:p, :c, :i, :ph, :pi, :pp, :u, now() - make_interval(days => :d), :n)"""),
                           {"p": p["id"], "c": p["cycle"] or 1, "i": code, "ph": enabled, "pi": prev[0] if prev else None,
                            "pp": prev[1] if prev else None, "u": who, "d": 20 - 10 * n, "n": note})
                prev = (code, enabled)
            out.append(f"{name}: {it.label(*prev)}")
    return out
