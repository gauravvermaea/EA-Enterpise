"""The project's own uploads on Other views and documents (owner, 10 Nov 2026, D461): laptop only, made once per project
(a project with an upload already is left alone), when Documents is up. Every name is invented.

Between them they show every state: files uploaded by different people on the project (the Lead Architect, an architect
and a stakeholder), one with a title and description and one without, and one replaced by a newer file (two versions,
the first downloadable as an earlier version).
"""

from __future__ import annotations

import io

from sqlalchemy import text

PROJECTS = ("Protea Target Architecture 2028 (sample project)", "Protea Claims Transformation 2028 (sample)")


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _xlsx(rows: list[tuple]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Volumes"
    for r in rows:
        ws.append(list(r))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _members(conn, project: str) -> set[str]:
    return {r["username"] for r in conn.execute(text("""SELECT m.username FROM proj.members m JOIN proj.projects p ON p.id = m.project_id
                                                        WHERE p.guid = CAST(:p AS uuid)"""), {"p": project}).mappings().all()}


def run() -> list[str]:
    from .. import other_uploads as ou
    from .. import projects as pj

    said: list[str] = []
    for name in PROJECTS:
        try:                         # only when Documents is up: otherwise made at the next start
            with pj.connections(True) as conn:
                line = _one_project(conn, ou, name)
        except Exception as exc:  # noqa: BLE001 - Documents not up yet (nothing was kept): tried again at the next start
            said.append(f"{name}: uploads left for the next start ({exc})")
            break
        if line:
            said.append(line)
    return said


def _one_project(conn, ou, name: str) -> str:
    pg = conn.execute(text("""SELECT guid::text FROM proj.projects p WHERE name = :n
                               AND NOT EXISTS (SELECT 1 FROM proj.documents d WHERE d.project_id = p.id AND d.origin = 'other')"""),
                      {"n": name}).scalar()
    if not pg:
        return ""
    people = _members(conn, pg)
    la = _p("user_lead_architect" if "user_lead_architect" in people else "user_super_admin",
            () if "user_lead_architect" in people else ("super-admin",))
    ar = _p("user_architect" if "user_architect" in people else la.username, la.roles)
    st = _p("user_stakeholder" if "user_stakeholder" in people else la.username, la.roles)
    ou.upload(conn, pg, la, [("Claims workshop notes 3 November.md",
                              b"# Claims workshop, 3 November (sample)\n\nWho came, what hurts today, what good looks like in 2028.\n"
                              b"\n- Paper claim forms still 30% of claims\n- Repairers wait 9 days for approval\n")],
              "Claims workshop notes", "Notes from the workshop with the claims managers; shared with the team.")
    ou.upload(conn, pg, st, [("Broker feedback summary.txt",
                              b"Broker feedback (sample)\n\nBrokers want live claim tracking and one number to call.\n")])
    first = ou.upload(conn, pg, ar, [("Claims volumes by channel.xlsx",
                                      _xlsx([("Channel", "Claims a month"), ("Call centre", 4200), ("Paper", 2600), ("Broker", 1900)]))],
                      "Claims volumes by channel", "Monthly claims by channel, from the claims system's reports.")
    ou.replace(conn, pg, ar, first["uploads"][0]["id"], "Claims volumes by channel.xlsx",
               _xlsx([("Channel", "Claims a month"), ("Call centre", 4100), ("Paper", 2450), ("Broker", 1950), ("App (pilot)", 300)]),
               "October figures added, with the app pilot")
    return f"{name}: 3 uploads on Other views and documents, one replaced (two versions)"
