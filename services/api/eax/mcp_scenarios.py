"""Scenario planning through MCP (phase 27.1, D364, D490 to D495): the guided prompt *plan scenarios* and its tools.

Registered on the same MCP server (eax.mcp_server imports this module). Every tool runs as the signed-in person in a
project they are on (eax.scenarios has the rules). Tools that change something follow D458: called without `confirm`
they answer with a **preview** and a confirm token; called again with the same arguments and `confirm=<token>` (by the
same person, within 30 minutes) they do it. Making a scenario tags its source first. What-ifs are the person's
uncommitted changes. Everything is in the change log as done through MCP and in the AI activity log.
"""

from __future__ import annotations

from typing import Any

import anyio

from . import audit, permissions
from . import repository as repo
from . import scenarios as sc
from .mcp_server import _clean, mcp
from .metamodel_edit import EditError

GUIDE = """Plan scenarios with EA Explorer (phase 27.1). Work in this order, as the person, and ask before changing anything:

1. scenario_overview(project): the baseline (the Current state model) and every scenario model with its figures (cost,
   applications, capabilities covered, end-of-life technology, risks), what it adds, changes and retires against the
   baseline, the capabilities it touches, and a suggested score. compare_scenario(project, scenario) gives one in full.
2. No scenario yet, or another is wanted? make_scenario(project, name, start="copy" | "child"): preview first, then the
   person's yes, then call again with confirm=<token>. The baseline is tagged first.
3. What-ifs: apply_what_ifs(project, scenario, actions), e.g.
   [{"retire": "Policy Administration System", "replace_with": "Policy Suite"}, {"retire": "Underwriting Rules Engine"},
    {"add": "Claims Triage Bot", "type": "ApplicationComponent", "relationships": [{"type": "Serving", "to": "Claims Handling"}]},
    {"change": "Billing Engine", "values": {"AnnualCost": 450000}}]
   They are the person's own uncommitted changes in that scenario: only they see them until they commit them. Preview,
   yes, confirm. Then scenario_overview again to see the effect.
4. Compare and explain: for each scenario say what it adds, changes and retires, cost, applications, capabilities
   covered, risks and impact (the capabilities touched). Propose a score (0 to 10, 5 = like the baseline) with reasons;
   the suggested score is a starting point, the person decides.
5. Record it: record_scenario_assessment(project, title, scenarios=[{model, score, notes}], recommendation, recommended,
   governance="none" | "draft" | "approval"): kept with the project (Scenarios tab), as a Word document (filed in the
   repository when an item fits), and optionally as a governance log decision sent for approval. Preview, yes, confirm.

Never commit what-ifs or send anything for approval without the person's yes. Give links (/#/projects/<id>/scenarios,
/#/metamodel/<id>) to what you made."""


def _who() -> permissions.Principal:
    return permissions.current.get()


def _note(**what) -> None:
    try:
        from .mcp_server import note_call
        note_call(**what)
    except ImportError:          # an older server without the activity log
        pass


def _may_write() -> str | None:
    try:
        from .mcp_server import may_write
        return may_write()
    except ImportError:
        return None


def _hash(tool: str, args: dict) -> str:
    return sc.preview_hash(tool, args)        # the same as eax.mcp_ops.args_hash (D458)


def _token_new(core, user, tool: str, args: dict, summary: dict) -> str:
    """A preview kept in core.mcp_previews, as every changing MCP tool does (eax.mcp_ops, D458)."""
    from . import mcp_ops
    return mcp_ops._keep_preview(core, user, tool, _hash(tool, args), summary)


def _token_use(core, user, tool: str, args: dict, token: str) -> None:
    """The confirm must be this person's, for this tool and these arguments, unused and not expired (eax.mcp_ops)."""
    from . import mcp_ops
    mcp_ops._use_preview(core, user, tool, _hash(tool, args), token)


async def _proj(fn, *, write: bool = False, tool: str = "", args: dict | None = None, confirm: str = "") -> Any:
    """A scenarios function on the projects' connection as the signed-in person. A changing tool previews (and returns a
    confirm token) unless confirm is a valid token for the same arguments; then it does the change."""
    from . import projects as pj
    from . import settings as app_settings
    if permissions.current.get() is None:
        return {"error": "Sign in required."}
    if not app_settings.parts().get("projects", True):
        return {"error": "Projects are switched off in this installation (System admin > System settings)."}
    if write:
        why = _may_write()
        if why:
            return {"error": why}
    who = _who()
    args = args or {}

    def work():
        with pj.connections(write) as pc:
            core = pj.core(pc)
            if write and confirm:
                _token_use(core, who, tool, args, confirm)
                out = fn(pc, who, True)
                audit.record(core, actor=who.username, action=f"mcp.scenarios.{tool}", object_type="project",
                             object_id=str(args.get("project") or ""), source="mcp")
                return out, True
            out = fn(pc, who, False) if write else fn(pc, who)
            if write and isinstance(out, dict) and "preview" in out:
                out["confirm"] = _token_new(core, who, tool, args, out["preview"])
                out["next"] = f"Show the person this preview; after their yes call {tool} again with the same arguments and confirm=\"{out['confirm']}\"."
            return out, False
    try:
        result, did = await anyio.to_thread.run_sync(work)
    except (repo.NotFound, EditError) as exc:
        return {"error": str(exc)}
    result = _clean(result)
    if write:
        _note(**({"wrote": True} if did else {"previewed": True}))
    return {"count": len(result), "items": result} if isinstance(result, list) else result


# ---------------------------------------------------------------- the guided prompt
if hasattr(mcp, "prompt"):
    @mcp.prompt()
    def plan_scenarios(project: str = "", question: str = "") -> str:
        """Plan and compare scenarios in an architecture project with an assistant (phase 27.1)."""
        return (f"{GUIDE}\n\nProject: {project or '(ask which; list_projects shows them)'}. "
                f"The question: {question or '(ask what the scenarios should decide)'}.\nStart with scenario_overview.")


@mcp.tool()
async def how_to_plan_scenarios() -> Any:
    """READ FIRST when asked to plan, compare or assess scenarios in a project: the order of work and the tools."""
    return {"guide": GUIDE}


# ---------------------------------------------------------------- reading
@mcp.tool()
async def scenario_overview(project: str, baseline: str = "") -> Any:
    """A project's baseline (its Current state model, or `baseline`) and every scenario model (role Scenario, and Target
    state) with: figures (entities, applications, capabilities and how many are covered, total annual cost, technology past
    or near end of life, applications to eliminate, orphans, risks), the difference from the baseline, what each adds,
    changes and retires by entity type, the capabilities touched (impact), a suggested score (0-10, 5 = like the
    baseline) and the assessments recorded. Figures include YOUR uncommitted changes (your what-ifs)."""
    return await _proj(lambda pc, who: sc.overview(pc, project, who, baseline or None))


@mcp.tool()
async def compare_scenario(project: str, scenario: str, baseline: str = "") -> Any:
    """One scenario model against the baseline in full: every element added, changed (with what changed) and retired,
    the relationship changes, the capabilities touched, both models' figures, the difference and a suggested score."""
    return await _proj(lambda pc, who: sc.compare_one(pc, project, who, scenario, baseline or None))


@mcp.tool()
async def list_scenario_assessments(project: str) -> Any:
    """The scenario assessments recorded in a project (SCN-001...): title, baseline, each scenario's score, notes and
    figures at the time, the recommendation, its Word document and governance decision (and its approval state)."""
    from . import projects as pj
    return await _proj(lambda pc, who: sc.assessments(pc, pj.project_row(pc, project), who))


# ---------------------------------------------------------------- changing (preview, then confirm)
@mcp.tool()
async def make_scenario(project: str, name: str, start: str = "copy", source: str = "", confirm: str = "") -> Any:
    """Make a scenario model in a project: start "copy" (a separate copy) or "child" (a copy that can merge back) of the
    baseline, or of `source` (another model of the project). The source is tagged first ("Before scenario <name>"); the
    new model joins the project with the role Scenario and the project's people get their roles on it. Without confirm:
    a preview and a confirm token. After the person's yes: call again with the same arguments and confirm=<token>."""
    args = {"project": project, "name": name, "start": start, "source": source}
    return await _proj(lambda pc, who, ok: sc.make_scenario(pc, project, who, name, start, source or None, confirm=ok),
                       write=True, tool="make_scenario", args=args, confirm=confirm)


@mcp.tool()
async def apply_what_ifs(project: str, scenario: str, actions: list[dict], confirm: str = "") -> Any:
    """What-ifs in a scenario model, kept as YOUR uncommitted changes (only you see them until you commit them; they can be
    thrown away from the model's Changes tab). Each action is one of:
      {"retire": X}                                   X goes (with its relationships)
      {"retire": X, "replace_with": Y, "type": T?}    Y (new, of X's type unless T; or an existing entity) takes X's
                                                      relationships where the metamodel allows; X goes
      {"add": Y, "type": T, "description"?, "values"?, "relationships"?: [{"type": R, "to": Z} | {"type": R, "from": Z}]}
      {"change": X, "name"?, "description"?, "values"?: {attribute code: value}}
    Entities by name, display ID or id. Without confirm: a preview in words and a confirm token; after the person's yes call
    again with the same arguments and confirm=<token>."""
    args = {"project": project, "scenario": scenario, "actions": actions}
    return await _proj(lambda pc, who, ok: sc.apply_what_ifs(pc, project, who, scenario, actions, confirm=ok),
                       write=True, tool="apply_what_ifs", args=args, confirm=confirm)


@mcp.tool()
async def record_scenario_assessment(project: str, title: str, scenarios: list[dict], recommendation: str = "",
                                     recommended: str = "", baseline: str = "", governance: str = "none", item: str = "",
                                     confirm: str = "") -> Any:
    """Record a scenario assessment in a project: scenarios [{model, score (0-10), notes}], a recommendation (plain text,
    paragraphs split by a blank line) and the scenario recommended. The comparison and figures as they are now are kept
    with it (SCN-001...). It becomes a Word document (filed in the project's repository under `item`, a document class, or
    one that fits; otherwise downloadable from the Scenarios tab) and, with governance "draft" or "approval", a Decision
    in the governance log (approval: sent to the project's sign-off people). Without confirm: a preview and a confirm
    token; after the person's yes call again with the same arguments and confirm=<token>."""
    args = {"project": project, "title": title, "scenarios": scenarios, "recommendation": recommendation, "recommended": recommended,
            "baseline": baseline, "governance": governance, "item": item}
    return await _proj(lambda pc, who, ok: sc.record_assessment(pc, project, who, title, scenarios, recommendation, recommended or None,
                                                              baseline or None, governance, item or None, confirm=ok),
                       write=True, tool="record_scenario_assessment", args=args, confirm=confirm)
