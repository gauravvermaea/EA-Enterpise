"""MCP sample data (batch 3, phases 26/27; owner, 10 Nov 2026, D458, D482, AGENTS.md: every state shown): laptop only,
made once. Every name is invented.

* **A model copied and deduped through MCP**: "Protea Insurance clean-up (MCP)", a child of Protea Insurance (demo
  estate) made by copy_model, with its duplicates merged by merge_duplicates ("Claims Platfrom" into Claims Platform,
  "Quote-Engine" into Quote Engine); tagged first, as every MCP change is.
* **A merge done through MCP**: "Karoo MCP sandbox" (a separate copy of Karoo Digital (lean)) and its child "Karoo MCP
  sandbox clean-up", whose changes overrode the sandbox through override_parent (every change accepted), after which
  the child was frozen.
* **The AI activity log** with a call of every kind (read, preview, change, refused, error), by several people over the
  last two weeks, the changes above among them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from .demo_estate import DEMO_NAME

COPY_NAME = "Protea Insurance clean-up (MCP)"
SANDBOX, SANDBOX_CHILD = "Karoo MCP sandbox", "Karoo MCP sandbox clean-up"
LEAN = "Karoo Digital (lean)"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _model(conn, name: str) -> dict | None:
    from .. import repository as repo
    g = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": name}).scalar()
    return repo.get_model(conn, g) if g else None


def _audit(conn, actor: str, tool: str, model: str, why: str) -> None:
    from .. import audit
    audit.record(conn, actor=actor, action=f"mcp.{tool}", object_type="model", object_id=model,
                 details={"via": "mcp", "why": why, "sample": True}, source="mcp")


def link(m: dict) -> str:
    return f"/#/metamodel/{m['id']}"


def run() -> list[str]:
    from .. import permissions as perms
    from ..db import get_engine
    said: list[str] = []
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    try:
        with get_engine().begin() as conn:
            if conn.execute(text("SELECT 1 FROM core.mcp_activity LIMIT 1")).first():
                return []
        for step in (_copy_and_dedupe, _override, _activity):
            try:
                said += step()
            except Exception as exc:  # noqa: BLE001 - one part never stops the others
                said.append(f"{step.__name__.strip('_')} not made: {exc}")
    finally:
        perms.current.reset(token)
    return said


def _copy_and_dedupe() -> list[str]:
    from .. import dedupe
    from .. import model_operations as mo
    from ..db import get_engine
    sa = _p("user_super_admin", ("super-admin",))
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
        demo = _model(conn, DEMO_NAME)
        if not demo:
            return ["MCP copy skipped: the demo estate is not there"]
        if _model(conn, COPY_NAME):
            return []
        out = mo.copy_or_child(conn, sa, str(demo["id"]), COPY_NAME, linked=True,
                               description="Made through MCP (copy_model) and cleaned up: duplicates merged (sample, D458).")
        _audit(conn, sa.username, "copy_model", out["model"], "Make a copy of the demo estate and remove all duplicates as you see fit")
    said = [f"{COPY_NAME}: a child of {DEMO_NAME} made through MCP"]
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
        mo.tag_before(conn, sa, out["model"], "merging duplicates (through MCP)")
        groups = dedupe.candidates(conn, out["model"], None, [], 0.88, True).get("groups") or []
        merged = 0
        for g in groups:
            ids = [e["id"] for e in g.get("entities") or []]
            if len(ids) < 2:
                continue
            c = dedupe.compare(conn, out["model"], ids)
            res = dedupe.merge(conn, out["model"], sa, c["keep"], [i for i in ids if i != c["keep"]])
            merged += res["merged"]
        _audit(conn, sa.username, "merge_duplicates", out["model"], "Remove all duplicates as you see fit")
    said.append(f"{COPY_NAME}: {merged} duplicates merged through MCP, tagged first")
    return said


def _override() -> list[str]:
    from .. import commits as cm
    from .. import model_operations as mo
    from ..db import get_engine
    sa = _p("user_super_admin", ("super-admin",))
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
        lean = _model(conn, LEAN)
        if not lean or _model(conn, SANDBOX):
            return [] if lean else ["MCP override skipped: Karoo Digital (lean) is not there"]
        box = mo.copy_or_child(conn, sa, str(lean["id"]), SANDBOX, linked=False,
                               description="A separate copy of Karoo Digital (lean), to show a merge done through MCP (sample).")
        kid = mo.copy_or_child(conn, sa, box["model"], SANDBOX_CHILD, linked=True,
                               description="Changed and then overrode its parent through MCP (override_parent), then frozen (sample).")
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
        m = _model(conn, SANDBOX_CHILD)
        first = conn.execute(text("""SELECT e.guid::text FROM core.entities e WHERE e.model_id = :m AND NOT e.is_deleted
                                      ORDER BY e.display_id LIMIT 1"""), {"m": m["_id"]}).scalar()
        if first:
            res = cm.record_many(conn, m["id"], sa.username, [("entity.update", {"entity": first, "data": {
                "description": "Described more fully during the clean-up through MCP (sample)."}})])
            ids = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
            if ids and cm.uses_commits(m):
                cm.commit(conn, m["id"], sa, None, ids, None, "Clean-up through MCP (sample)")
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
        mo.tag_before(conn, sa, kid["model"], "overriding the parent (through MCP)")
        out = mo.override(conn, sa, kid["model"], "Override through MCP: every change accepted (sample, D458).", "freeze")
        _audit(conn, sa.username, "override_parent", kid["model"], "Override its parent with it")
    return [f"{SANDBOX_CHILD} overrode {SANDBOX} through MCP: {out['message']}"]


def _activity() -> list[str]:
    from .. import mcp_activity as ma
    from ..db import get_engine
    now = datetime.now(UTC)
    with get_engine().begin() as conn:
        copy = _model(conn, COPY_NAME)
        kid = _model(conn, SANDBOX_CHILD)
        rows = [
            # (days ago, user, tool, arguments, result, wrote, previewed, changes)
            (13, "user_architect", "list_models", {}, {"count": 18}, False, False, []),
            (13, "user_architect", "impact_analysis", {"model": DEMO_NAME, "entity": "Claims Platform",
                                                       "why": "What is affected if we retire the Claims Platform?"},
             {"affected": 14}, False, False, []),
            (12, "user_architect", "application_rationalisation", {"model": DEMO_NAME, "why": "Where do our applications overlap?"},
             {"capabilities_with_overlap": 6}, False, False, []),
            (11, "user_history_viewer", "merge_duplicates", {"model": DEMO_NAME, "groups": [{"keep": "…", "others": ["…"]}],
                                                              "why": "Remove the duplicates"},
             {"error": "Merging duplicates in Protea Insurance (demo estate) needs a role that changes content."}, False, False, []),
            (9, "user_super_admin", "copy_model", {"model": DEMO_NAME, "name": COPY_NAME, "linked": True,
                                                   "why": "Make a copy of the demo estate and remove all duplicates as you see fit"},
             {"preview": {"will": f"Make a child of {DEMO_NAME} called {COPY_NAME}"}, "confirm": "pv_sample"}, False, True, []),
            (9, "user_super_admin", "copy_model", {"model": DEMO_NAME, "name": COPY_NAME, "linked": True,
                                                   "why": "Make a copy of the demo estate and remove all duplicates as you see fit"},
             {"done": True, "name": COPY_NAME}, True, False,
             [{"what": f"copy of {DEMO_NAME}", "model": COPY_NAME, "link": link(copy) if copy else "", "message": f"{COPY_NAME} made"}]),
            (9, "user_super_admin", "find_duplicates", {"model": COPY_NAME}, {"groups": 2}, False, False, []),
            (9, "user_super_admin", "merge_duplicates", {"model": COPY_NAME, "groups": [{"keep": "…", "others": ["…"]}],
                                                         "why": "Remove all duplicates as you see fit"},
             {"done": True, "merged": 2}, True, False,
             [{"what": "merging duplicates", "model": COPY_NAME, "link": link(copy) if copy else "", "message": "2 duplicates merged"}]),
            (6, "user_super_admin", "override_parent", {"model": SANDBOX_CHILD, "after": "freeze", "why": "Override its parent with it"},
             {"done": True}, True, False,
             [{"what": "overriding the parent", "model": SANDBOX_CHILD, "link": link(kid) if kid else "",
               "message": f"{SANDBOX_CHILD} overrode {SANDBOX}: every change merged"}]),
            (4, "user_model_admin", "technology_risk_analysis", {"model": DEMO_NAME, "why": "What runs on technology past its end of life?"},
             {"technology": 3}, False, False, []),
            (3, "user_model_admin", "what_changed", {"model": "Karoo Re (independent)", "since_tag": "Q5 baseline"},
             {"error": "Karoo Re (independent) has no tag 'Q5 baseline'."}, False, False, []),
            (1, "user_architect", "save_report_document", {"project": "Protea claims transformation", "title": "Claims landscape summary",
                                                           "why": "Write a current-state summary of the claims landscape"},
             {"preview": {"will": "Keep Claims landscape summary.docx on the project's Repository tab"}, "confirm": "pv_sample2"},
             False, True, []),
        ]
        for days, user, tool, args, result, wrote, previewed, changes in rows:
            ma.record(conn, username=user, tool=tool, arguments=args, result=result, ms=40 + days * 7, wrote=wrote,
                      previewed=previewed, changes=changes, credential="Laptop assistant token" if user == "user_model_admin" else "")
            conn.execute(text("UPDATE core.mcp_activity SET at = :at WHERE id = (SELECT max(id) FROM core.mcp_activity)"),
                         {"at": now - timedelta(days=days, minutes=len(tool))})
    return [f"AI activity log: {len(rows)} calls of every kind"]
