"""Scenario planning (phase 27.1, D364, D495): laptop only, made once, on the sample project "Protea build or buy (sample)"
(baseline Protea Insurance (demo estate), scenario models A: build and B: buy). Every name is invented.

* **Scenario A: build** has its what-ifs **committed** (by the Lead Architect): the Policy Administration System is
  replaced by "Protea Policy Platform (in-house build)", which takes its relationships.
* **Scenario B: buy** has its what-ifs **applied and pending**, the Architect's own uncommitted changes: the Policy
  Administration System replaced by "Policy Suite (bought package)" and the Underwriting Rules Engine retired (the suite
  has its own rules). Only user_architect sees them until they are committed.
* **SCN-001 Policy platform: build or buy** is recorded by the Architect (who sees B with the what-ifs): both scored,
  B recommended, logged as a governance **decision waiting for approval** by the project's sign-off people.
"""

from __future__ import annotations

from sqlalchemy import text

PROJECT = "Protea build or buy (sample)"
A, B = "Protea scenario A: build", "Protea scenario B: buy"
PAS, URE = "Policy Administration System", "Underwriting Rules Engine"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def run() -> list[str]:
    from .. import permissions as perms
    from .. import projects as pj
    said: list[str] = []
    try:
        with pj.connections(True) as pc:
            pg = pc.execute(text("SELECT guid::text FROM proj.projects WHERE name = :n"), {"n": PROJECT}).scalar()
            if not pg:
                return [f"scenario samples skipped: {PROJECT} is not there"]
            if pc.execute(text("""SELECT 1 FROM proj.scenario_assessments a JOIN proj.projects p ON p.id = a.project_id
                                   WHERE p.name = :n LIMIT 1"""), {"n": PROJECT}).first():
                return []
    except Exception as exc:  # noqa: BLE001 - the table not there yet (an older database): nothing to do
        return [f"scenario samples skipped: {exc}"]
    for step in (_build, _buy, _assessment):
        token = perms.current.set(_p("user_super_admin", ("super-admin",)))
        try:
            said += step(pg)
        except Exception as exc:  # noqa: BLE001 - one part never stops the others
            said.append(f"{step.__name__.strip('_')} not made: {exc}")
        finally:
            perms.current.reset(token)
    return said


def _build(pg: str) -> list[str]:
    """Scenario A: the in-house build, committed by the Lead Architect."""
    from .. import commits as cm
    from .. import projects as pj
    from .. import scenarios as sc
    la = _p("user_lead_architect")
    with pj.connections(True) as pc:
        core = pj.core(pc)
        core.execute(text("SELECT set_config('eax.actor', 'user_lead_architect', true)"))
        _p_, models = sc.project_models(pc, pg, _p("user_super_admin", ("super-admin",)))
        scen = sc._pick(models, A, "scenario")
        m = scen["_m"]
        if not core.execute(text("""SELECT 1 FROM core.entities WHERE model_id = :m AND name = :n AND NOT is_deleted"""),
                            {"m": m["_id"], "n": PAS}).first():
            return []                              # made already
        items, _said = sc._plan_what_ifs(core, m, la, [
            {"retire": PAS, "replace_with": "Protea Policy Platform (in-house build)",
             "description": "Policy administration built in house on the cloud data platform (scenario A).",
             "values": {"AnnualCost": 1900000, "Lifecycle": "Plan", "TimeClassification": "Invest", "Hosting": "IaaS"}}])
        res = cm.record_many(core, str(m["id"]), la.username, items)
        ids = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
        if ids:
            cm.commit(core, str(m["id"]), la, None, ids, None, "Scenario A: build the policy platform in house (sample)")
        return [f"{A}: {len(ids)} what-if changes committed"]


def _buy(pg: str) -> list[str]:
    """Scenario B: the bought package, the Architect's own uncommitted what-ifs."""
    from .. import projects as pj
    from .. import scenarios as sc
    ar = _p("user_architect")
    with pj.connections(True) as pc:
        pj.core(pc).execute(text("SELECT set_config('eax.actor', 'user_architect', true)"))
        out = sc.apply_what_ifs(pc, pg, ar, B, [
            {"retire": PAS, "replace_with": "Policy Suite (bought package)",
             "description": "A bought policy administration package with its own rules engine (scenario B).",
             "values": {"AnnualCost": 1500000, "Lifecycle": "Plan", "TimeClassification": "Invest", "Hosting": "SaaS",
                        "Vendor": "Marula Software"}},
            {"retire": URE}], confirm=True)
        return [f"{B}: {out['kept']} what-if changes pending for user_architect"]


def _assessment(pg: str) -> list[str]:
    from .. import projects as pj
    from .. import scenarios as sc
    ar = _p("user_architect")
    with pj.connections(True) as pc:
        pj.core(pc).execute(text("SELECT set_config('eax.actor', 'user_architect', true)"))
        out = sc.record_assessment(
            pc, pg, ar, "Policy platform: build or buy",
            [{"model": A, "score": 6, "notes": "Fits our own products best, but the build takes two years and the cost stays high."},
             {"model": B, "score": 7.5, "notes": "Lower running cost and one platform fewer (the rules engine goes); "
                                                 "we change some products to fit the package."}],
            recommendation="Buy the policy suite (scenario B).\n\nIt costs less to run, retires the Underwriting Rules Engine "
                           "and reaches the same capabilities sooner. Keep the product rules we need in its own rules engine.",
            recommended=B, governance="approval", via="mcp", confirm=True)
        return [f"{out['ref']} recorded: {out['message']}"]
