"""A project's ADM iteration through MCP (D571-D574): read it, and change it with a preview first (D458).

Any person who can open the project may change its iteration; the phases it leaves out are frozen (read only), never
deleted, and choosing another iteration unfreezes them. Registered on the same MCP server as the other tools.
"""

from __future__ import annotations

from typing import Any

from . import iterations as it
from .mcp_scenarios import _proj
from .mcp_server import mcp


@mcp.tool()
async def project_iteration(project: str) -> Any:
    """A project's ADM iteration in its current cycle (Full cycle, Architecture Capability (Preliminary, A), Architecture
    Development (B, C, D), Transition Planning (E, F), Architecture Governance (G, H) or Custom), the phases enabled and
    frozen, the choices, and the history of changes."""
    from . import projects as pj

    def run(pc, who):
        p = pj.project_row(pc, project)
        pj._need(pc, p, who, "read")
        cur = it.current(pc, p)
        return {"project": p["name"], "cycle": p.get("cycle") or 1, "iteration": cur,
                "frozen_phases": [x for x in it.PHASES if x not in cur["phases"]], "choices": it.catalogue(),
                "history": it.history(pc, p), "link": f"/#/projects/{p['guid']}"}
    return await _proj(run)


@mcp.tool()
async def set_project_iteration(project: str, iteration: str, phases: list[str] | None = None, note: str = "",
                                confirm: str = "") -> Any:
    """Change a project's ADM iteration: iteration is full, capability, development, transition, governance or custom
    (with phases, e.g. ["A", "B", "E"]; P is Preliminary). The phases left out become read only (frozen), never deleted.
    Without confirm: a preview and a confirm token; after the person's yes call again with the same arguments and
    confirm=<token>."""
    from . import projects as pj
    args = {"project": project, "iteration": iteration, "phases": phases or [], "note": note}

    def run(pc, who, ok):
        if ok:
            return it.set_iteration(pc, project, who, iteration, phases, note)
        p = pj.project_row(pc, project)
        pj._need(pc, p, who, "read")
        code, enabled = it.clean(iteration, phases)
        was = it.current(pc, p)
        frozen = [x for x in it.PHASES if x not in enabled]
        return {"preview": {"project": p["name"], "from": was["label"], "to": it.label(code, enabled),
                            "frozen_after": frozen, "note": "Frozen phases become read only; nothing is deleted."}}
    return await _proj(run, write=True, tool="set_project_iteration", args=args, confirm=confirm)
