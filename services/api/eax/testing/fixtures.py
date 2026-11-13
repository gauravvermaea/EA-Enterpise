"""A self-test run's fixtures: made at its start, removed at its end (phase 36.1, D529; R2.11, D637).

The self-test runs on the live installation but only in what it makes itself, named after the run's short id (the first
12 characters of its guid) so runs never clash and can be repeated:

  self_test_<id>_1          a model (empty from ArchiMate 4, with a few applications, capabilities and relationships)
  self_test_<id>_2          a child of it (where the person with no role is refused: cross-user)
  self_test_<id>_3          an architecture project on the first model
  svc-self-test-<id>-<role> one service account per role tested, each with a one-day token (machine access, D366): the
                            global roles, the model roles on self_test_<id>_1, and someone with no role at all

Each is recorded in tests.test_fixtures with its run. Purging (System admin > Self-test > Test fixtures, or
`eax test --clean <run|all>`) is a **hard delete**: the models and everything in them (entities, relationships, values,
history versions, tags, KPI snapshots, quality runs, uncommitted changes, drawn views), the projects (and their folder
in Documents), the service accounts and credentials. Only what tests.test_fixtures lists for the run is touched, never
anything else even if its name looks like a fixture; it is idempotent (what is gone is skipped) and safe to run again
after a partial failure. History stays append-only for everything else: the guard is lifted only inside the purge's own
transaction and checked back on before it commits, as housekeeping does (D445, D248). The change log keeps the run and
the purge (who, when, how many); the run's report stays downloadable, marked "fixtures removed".

Since R2.11 (D637) the models and projects are marked is_test_data, so the model and project lists leave them out
(except for the self-test's own accounts, or with ?test_data=1), and every run removes its own fixtures when it ends,
passed, failed or stopped (remove_at_end; EAX_TEST_KEEP_DATA=1 keeps them for the next run to remove). preview() is the
dry run: what a purge would delete, nothing deleted."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text

from .. import permissions as perms
from . import store

DESCRIPTION = "Made by the EA Explorer self-test, run {run} ({guid}). Removed from System admin > Self-test > Test fixtures."

# what the run's project members are, per test role (D583): the architect works on it, the report viewer only reads it
PROJECT_TEST_ROLES = {"architect": "architect", "report-viewer": "stakeholder"}
# the key of the key:value the drawn-view journey sets on a line (a text attribute on Association in self_test_<id>_1)
LINE_ATTRIBUTE = "Protocol"


def _principal(username: str, roles: tuple[str, ...]):
    return perms.Principal(username, roles)


def _as(principal, coro):
    """Runs one of the MCP build tools in-process as the run's own account (the same code as the screens and MCP)."""
    token = perms.current.set(principal)
    try:
        out = asyncio.run(coro)
    finally:
        perms.current.reset(token)
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(str(out["error"]))
    return out


def accounts(conn, run: dict, by: str, roles: list[str], log) -> dict[str, str]:
    """One service account and a one-day token per role; returns {role: token}. The super-admin one is always made (it
    makes the other fixtures) and so is the no-role one when any cross-user check runs."""
    from .. import machine_access as ma
    sid = store.short(run["run_guid"])
    tokens: dict[str, str] = {}
    scopes = {a: "read-write" for a in ma.AREA_CODES}
    for role in roles:
        global_role = role if role in store.GLOBAL_TEST_ROLES else perms.USER
        name = f"self-test-{sid}-{role}"
        sa = ma.create_service_account(conn, by, [perms.SUPER_ADMIN], {
            "username": name, "name": f"Self-test {sid} {role}", "roles": [global_role],
            "description": DESCRIPTION.format(run=run["id"], guid=run["run_guid"])})
        with store.tests(conn) as tc:
            store.add_fixture(tc, run["id"], "service_account", sa["username"], sa["username"])
        cred = ma.create(conn, by, [perms.SUPER_ADMIN], {"kind": "token", "owner": sa["username"], "days": 1,
                                                        "name": f"self_test_{sid} {role}", "scopes": scopes})
        with store.tests(conn) as tc:
            store.add_fixture(tc, run["id"], "credential", cred["guid"], f"self_test_{sid}_token_{role}")
        tokens[role] = cred["secret"]
    log(f"{len(tokens)} test account(s) with one-day tokens: {', '.join(tokens)}")
    return tokens


def models_and_project(engine, run: dict, by: str, roles: list[str], log) -> dict[str, str]:
    """The run's models and project, made through the same functions as the screens and MCP, as its super-admin account.
    engine: the repository's; each fixture is recorded in the tests database (store.engine()). Returns the ids the tests
    fill paths with."""
    from .. import mcp_build as mb
    from .. import (
        mcp_server,  # noqa: F401 - loads the MCP tools in their order (mcp_build is one of them)
    )
    sid = store.short(run["run_guid"])
    me = _principal(f"svc-self-test-{sid}-super-admin", (perms.SUPER_ADMIN,))
    desc = DESCRIPTION.format(run=run["id"], guid=run["run_guid"])
    m1 = _as(me, mb.create_model(f"self_test_{sid}_1", start="empty", source="ArchiMate 4", description=desc))
    with store.engine().begin() as tc:
        store.add_fixture(tc, run["id"], "model", m1["model"], m1["name"])
    mark_model(engine, m1["model"])
    _as(me, mb.add_entities(m1["model"], "Capability", [{"name": f"Self-test capability {i}"} for i in (1, 2, 3)]))
    _as(me, mb.add_entities(m1["model"], "ApplicationComponent", [{"name": f"Self-test application {i}"} for i in (1, 2)]
                            + [{"name": "Self-test duplicate app"}, {"name": "Self-test duplicate ap"}]))   # a pair to find and merge (D576)
    _as(me, mb.add_relationships(m1["model"], [
        {"relationship_type": "Association", "source": "Self-test application 1", "target": "Self-test capability 1"},
        {"relationship_type": "Association", "source": "Self-test application 2", "target": "Self-test capability 2"}]))
    try:
        _as(me, mb.commit_my_changes(m1["model"], "Self-test fixtures"))
    except RuntimeError:
        pass                                       # nothing to commit: the model saves straight away
    # the drawn-view journey sets a key:value on a line (D564): a text attribute on Association, in this model only
    try:
        from .. import metamodel_edit as med
        with engine.begin() as conn:
            med.apply(conn, m1["model"], "attribute.create",
                      {"relationship_type": "Association", "name": LINE_ATTRIBUTE, "data_type": "text"}, me.username)
    except Exception as exc:  # noqa: BLE001 - the journey then checks the line's name and type only
        log(f"no line attribute for the drawn-view journey: {exc}")
    view_ids: dict[str, str] = {}
    try:                                           # a drawn view for the drawn-view journey (D583)
        v = _as(me, mb.create_drawn_view(m1["model"], f"self_test_{sid} view",
                                          ["Self-test application 1", "Self-test capability 1", "Self-test application 2"]))
        view_ids = {"view": str(v["id"]), "view_name": f"self_test_{sid} view"}
    except Exception as exc:  # noqa: BLE001 - no views service: the drawn-view journey is skipped, with why
        log(f"no drawn view made: {exc}")
    m2 =_as(me, mb.create_model(f"self_test_{sid}_2", start="child", source=m1["model"], description=desc))
    with store.engine().begin() as tc:
        store.add_fixture(tc, run["id"], "model", m2["model"], m2["name"])
    mark_model(engine, m2["model"])
    with engine.begin() as conn:
        model_roles = [r for r in roles if r in store.MODEL_TEST_ROLES]
        for role in model_roles:
            conn.execute(text("""INSERT INTO core.model_users (model_id, username, role, created_by)
                                 SELECT id, :u, :r, :by FROM core.models WHERE guid = CAST(:g AS uuid) ON CONFLICT DO NOTHING"""),
                         {"u": f"svc-self-test-{sid}-{role}", "r": role, "by": by, "g": m1["model"]})
        ent = conn.execute(text("SELECT e.guid::text FROM core.entities e JOIN core.models m ON m.id = e.model_id "
                                "WHERE m.guid = CAST(:g AS uuid) AND NOT e.is_deleted ORDER BY e.id LIMIT 1"),
                           {"g": m1["model"]}).scalar()
    ids = {"model": m1["model"], "model_id": m1["model"], "model_name": m1["name"], "other_model": m2["model"], "sid": sid,
           "other_name": m2["name"], "dup": "Self-test duplicate ap", **view_ids}
    if ent:
        ids.update(entity=ent, entity_id=ent)
    try:
        from .. import project_templates as pt
        from .. import projects as pj
        with pj.connections() as pc:
            tpl = (pt.listing(pc) or [{}])[0].get("code")
        if tpl:
            p = _as(me, mb.create_project(f"self_test_{sid}_3", tpl, [{"how": "referred", "model": m1["model"],
                                                                         "role": "current", "home": True}], description=desc))
            with store.engine().begin() as tc:
                store.add_fixture(tc, run["id"], "project", p["project"], f"self_test_{sid}_3")
            with pj.connections() as pc:             # test data: left out of the project list (R2.11)
                pc.execute(text("UPDATE proj.projects SET is_test_data = true WHERE guid::text = :g"), {"g": str(p["project"])})
            ids.update(project=p["project"], project_id=p["project"], project_name=f"self_test_{sid}_3")
            # the test roles the journeys' role plan runs on the project are its members (D583)
            with pj.connections() as pc:
                for role in [r for r in roles if r in PROJECT_TEST_ROLES]:
                    pc.execute(text("""INSERT INTO proj.members (project_id, username, role, added_by)
                                       SELECT id, :u, :r, :by FROM proj.projects WHERE guid::text = :g
                                       ON CONFLICT DO NOTHING"""),
                               {"u": f"svc-self-test-{sid}-{role}", "r": PROJECT_TEST_ROLES[role], "by": by,
                                "g": str(p["project"])})
    except Exception as exc:  # noqa: BLE001 - the project journeys and endpoints are then skipped, with why
        log(f"no project made: {exc}")
    log(f"fixtures made: {m1['name']}, {m2['name']}" + (f", {ids['project_name']}" if "project" in ids else ""))
    return ids


def mark_model(engine, guid) -> None:
    """A fixture model is test data (R2.11, D637): the model lists leave it out for everyone but the self-test's own
    accounts, until the run's end removes it."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE core.models SET is_test_data = true WHERE guid = CAST(:g AS uuid)"), {"g": str(guid)})


def preview(conn, run_ids: list[int]) -> dict[str, Any]:
    """A dry run (R2.11): what purging these runs would delete, nothing deleted. conn: the repository's. Each fixture
    still there with its run, kind and name, and for models their entities, relationships and history versions."""
    with store.tests(conn) as tc:
        rows = [dict(r) for r in tc.execute(text("""SELECT f.id, f.run_id, f.kind, f.ident, f.name, r.state
                                                      FROM tests.test_fixtures f JOIN tests.test_runs r ON r.id = f.run_id
                                                     WHERE f.run_id = ANY(:r) AND f.purged_at IS NULL ORDER BY f.run_id, f.id"""),
                                            {"r": list(run_ids)}).mappings()]
    out = {"runs": sorted({r["run_id"] for r in rows}), "fixtures": [], "totals": {}, "running": []}
    for r in rows:
        item = {k: r[k] for k in ("id", "run_id", "kind", "name")}
        if r["state"] in store.OPEN:
            out["running"].append(r["run_id"])
        if r["kind"] == "model":
            c = conn.execute(text("""SELECT (SELECT count(*) FROM core.entities e WHERE e.model_id = m.id) AS entities,
                                            (SELECT count(*) FROM core.relationships x WHERE x.model_id = m.id) AS relationships,
                                            (SELECT count(*) FROM history.row_versions v WHERE v.model_id = m.id) AS history_versions
                                       FROM core.models m WHERE m.guid::text = :g"""), {"g": r["ident"]}).mappings().first()
            item.update(dict(c) if c else {"gone": True})
        out["fixtures"].append(item)
        out["totals"][r["kind"]] = out["totals"].get(r["kind"], 0) + 1
    out["running"] = sorted(set(out["running"]))
    return out


def preview_text(p: dict[str, Any]) -> str:
    if not p["fixtures"]:
        return "Dry run: no test data to remove."
    lines = [f"Dry run: nothing is deleted. Removing the test data of run(s) {', '.join(map(str, p['runs']))} would delete:"]
    for f in p["fixtures"]:
        extra = (f" ({f.get('entities', 0)} entities, {f.get('relationships', 0)} relationships, "
                 f"{f.get('history_versions', 0)} history versions)" if f["kind"] == "model" and not f.get("gone") else "")
        lines.append(f"  run {f['run_id']:<6} {f['kind']:<16} {f['name']}{extra}")
    lines.append("In all: " + ", ".join(f"{n} {k.replace('_', ' ')}(s)" for k, n in sorted(p["totals"].items())) + ".")
    if p["running"]:
        lines.append(f"Still running (left alone until they end): {', '.join(map(str, p['running']))}.")
    return "\n".join(lines)


def remove_at_end(repo, run_id: int, log=print) -> dict[str, Any] | None:
    """The end of every run, passed, failed or stopped (R2.11; owner: the harness cleans up after itself): the run's test
    data removed for good, as purge() does. EAX_TEST_KEEP_DATA=1 keeps it (to look into a failure); the next run removes
    it then (clean_leftovers). A run whose process was killed is cleaned by the next run too."""
    import os
    if os.environ.get("EAX_TEST_KEEP_DATA", "").lower() in ("1", "true", "yes", "on"):
        log("test data kept (EAX_TEST_KEEP_DATA): the next run removes it")
        return None
    try:
        with repo.begin() as conn:
            out = purge(conn, run_id, "self-test (end of run)")
        log(f"test data removed: {out['models']} model(s), {out['projects']} project(s), {out['service_accounts']} account(s), "
            f"{out['credentials']} credential(s)")
        return out
    except Exception as exc:  # noqa: BLE001 - the next run removes what is left (clean_leftovers)
        log(f"test data not removed now ({exc}); the next run removes it")
        return None


# ---------------------------------------------------------------- purging (D529; and at every run's end, R2.11)
def _plan(conn) -> list[tuple[str, str]]:
    """(table, which of its rows go) for everything that refers to core.models, directly or through other rows (up to
    four steps: change sets, then pending changes, then commit items...). Read from the catalogue, so a table added later
    is purged too."""
    fks = conn.execute(text("""
        SELECT c.conrelid::regclass::text AS child, a.attname AS col, c.confrelid::regclass::text AS parent, pa.attname AS pcol
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
          JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1]
         WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1""")).mappings().all()
    where: dict[str, list[str]] = {"core.models": ["id = ANY(:ids)"]}
    frontier = ["core.models"]
    for _depth in range(4):
        nxt = []
        for f in fks:
            if f["parent"] in frontier and f["child"] != f["parent"] and not f["child"].startswith("history."):
                cond = f"{f['col']} IN (SELECT {f['pcol']} FROM {f['parent']} WHERE {' OR '.join(where[f['parent']])})"
                if cond not in where.setdefault(f["child"], []):
                    where[f["child"]].append(cond)
                    nxt.append(f["child"])
        frontier = nxt
    return [(t, " OR ".join(f"({w})" for w in ws)) for t, ws in where.items() if t != "core.models"]


def _purge_models(conn, model_ids: list[int], by: str) -> int:
    """Deletes the models and everything that refers to them, children first; then their history versions with the
    guard lifted inside this transaction only. Returns the history versions removed."""
    if not model_ids:
        return 0
    conn.execute(text("SELECT set_config('eax.actor', :a, true), set_config('eax.user_roles', 'super-admin', true)"),
                 {"a": by})
    left = _plan(conn)
    for _round in range(16):                       # tables refer to each other: delete what can go, again until done
        still = []
        for t, cond in left:
            sp = conn.begin_nested()
            try:
                conn.execute(text(f"DELETE FROM {t} WHERE {cond}"), {"ids": model_ids})
                sp.commit()
            except Exception:  # noqa: BLE001 - something still refers to these rows: next round
                sp.rollback()
                still.append((t, cond))
        left = still
        if not left:
            break
    for mid in sorted(model_ids, reverse=True):    # children (made later) first
        conn.execute(text("UPDATE core.models SET parent_model_id = NULL, source_model_id = NULL WHERE id = :i"), {"i": mid})
    from .. import personal
    personal.forget_models(conn, model_ids)       # notifications, favourites, views about them (no FK crosses, D632)
    conn.execute(text("DELETE FROM core.models WHERE id = ANY(:ids)"), {"ids": model_ids})
    conn.execute(text("ALTER TABLE history.row_versions DISABLE TRIGGER row_versions_no_change"))
    n = conn.execute(text("DELETE FROM history.row_versions WHERE model_id = ANY(:ids)"), {"ids": model_ids})
    conn.execute(text("ALTER TABLE history.row_versions ENABLE TRIGGER row_versions_no_change"))
    on = conn.execute(text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'row_versions_no_change' "
                           "AND tgrelid = 'history.row_versions'::regclass")).scalar()
    if on != "O":
        raise RuntimeError("The history guard did not come back on: nothing is purged.")
    return max(0, int(getattr(n, "rowcount", 0) or 0))


def purge(conn, run_id: int, by: str, kinds: list[str] | None = None, fixture_ids: list[int] | None = None,
          progress=None) -> dict[str, Any]:
    """Hard-deletes a run's fixtures (all, or the kinds or fixture ids chosen): only what tests.test_fixtures lists for
    the run. Idempotent. Returns the counts; the change log keeps them."""
    say = progress or (lambda _p, _n: None)
    with store.tests(conn) as tc:                  # what to remove: the tests database's record of the run (R2.28)
        run = tc.execute(text("SELECT id, run_guid::text AS g, state FROM tests.test_runs WHERE id = :id"), {"id": run_id}).mappings().first()
        rows = [dict(r) for r in tc.execute(text("""SELECT id, kind, ident, name FROM tests.test_fixtures
                                                    WHERE run_id = :r AND purged_at IS NULL ORDER BY id"""), {"r": run_id}).mappings()]
    if not run:
        raise LookupError(f"No self-test run {run_id}.")
    if run["state"] in store.OPEN:
        raise ValueError(f"Self-test run {run_id} is still running: stop it or let it finish first.")
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]
    if fixture_ids:
        rows = [r for r in rows if r["id"] in set(fixture_ids)]
    counts = {"models": 0, "projects": 0, "service_accounts": 0, "credentials": 0, "history_versions": 0, "notes": []}
    sid = store.short(run["g"])
    say(10, f"run {run_id}: {len(rows)} fixture(s)")
    for r in [x for x in rows if x["kind"] == "credential"]:
        n = conn.execute(text("DELETE FROM core.machine_credentials WHERE guid::text = :g AND owner LIKE :o"),
                         {"g": r["ident"], "o": f"svc-self-test-{sid}-%"})
        counts["credentials"] += max(0, n.rowcount or 0)
    for r in [x for x in rows if x["kind"] == "service_account"]:
        if not r["ident"].startswith(f"svc-self-test-{sid}-"):
            counts["notes"].append(f"refused {r['ident']}: not this run's account")
            continue
        conn.execute(text("DELETE FROM core.machine_credentials WHERE owner = :u"), {"u": r["ident"]})
        conn.execute(text("DELETE FROM core.model_users WHERE username = :u"), {"u": r["ident"]})
        n = conn.execute(text("DELETE FROM core.service_accounts WHERE username = :u"), {"u": r["ident"]})
        counts["service_accounts"] += max(0, n.rowcount or 0)
    say(30, "accounts and credentials removed")
    projects = [x for x in rows if x["kind"] == "project"]
    if projects:
        from .. import projects as pj
        with pj.connections() as pc:
            for r in projects:
                p = pc.execute(text("SELECT id, name, mayan_cabinet_id FROM proj.projects WHERE guid::text = :g"),
                               {"g": r["ident"]}).mappings().first()
                if not p:
                    continue
                if not p["name"].startswith(f"self_test_{sid}_"):
                    counts["notes"].append(f"refused project {p['name']}: not this run's")
                    continue
                if p["mayan_cabinet_id"]:
                    try:
                        from .. import mayan
                        if hasattr(mayan, "delete_cabinet"):
                            mayan.delete_cabinet(p["mayan_cabinet_id"])
                    except Exception as exc:  # noqa: BLE001 - Documents may be off: noted, the project still goes
                        counts["notes"].append(f"Documents kept {p['name']}'s folder: {exc}")
                pc.execute(text("DELETE FROM proj.projects WHERE id = :i"), {"i": p["id"]})
                counts["projects"] += 1
    say(50, "projects removed")
    model_rows = [x for x in rows if x["kind"] == "model"]
    if model_rows:
        found = conn.execute(text("SELECT id, guid::text AS g, name FROM core.models WHERE guid::text = ANY(:g)"),
                             {"g": [r["ident"] for r in model_rows]}).mappings().all()
        ok = [m for m in found if m["name"].startswith(f"self_test_{sid}_")]
        counts["notes"] += [f"refused model {m['name']}: not this run's" for m in found if m not in ok]
        for m in ok:
            try:
                from .. import views_client as vc
                vc.delete_model(m["g"], by)
            except Exception:  # noqa: BLE001 - no drawn views, or the views service is off
                pass
        counts["history_versions"] = _purge_models(conn, [int(m["id"]) for m in ok], by)
        counts["models"] = len(ok)
    say(90, "models removed")
    with store.tests(conn) as tc:
        if rows:
            tc.execute(text("UPDATE tests.test_fixtures SET purged_at = now(), purged_by = :by WHERE id = ANY(:ids)"),
                       {"by": by, "ids": [r["id"] for r in rows]})
        if not tc.execute(text("SELECT 1 FROM tests.test_fixtures WHERE run_id = :r AND purged_at IS NULL"), {"r": run_id}).first():
            tc.execute(text("UPDATE tests.test_runs SET purged_at = coalesce(purged_at, now()), purged_by = coalesce(purged_by, :by) "
                            "WHERE id = :r"), {"by": by, "r": run_id})
    from .. import audit
    audit.record(conn, actor=by, action="selftest.purged", object_type="test_run", object_id=str(run_id),
                 details={k: v for k, v in counts.items() if k != "notes"} | {"run_guid": run["g"]})
    say(100, f"run {run_id} purged")
    return counts


def clean_leftovers(engine, this_run: int, by: str, log, stale_hours: int = 6) -> dict[str, int]:
    """Before a run (owner, 12 Nov 2026, R2.0.1, D593: "deleted previously created test data before next test if any
    remains"): every earlier run's fixtures still there are removed for good, from the UI and `eax test` alike. A run
    still marked queued or running for more than stale_hours (its runner stopped on an error) is closed as an error
    first, so its data can go too. Only what tests.test_fixtures lists is touched, as purge() does. engine: the
    repository's (the runs' records are in the tests database, store.engine())."""
    with store.engine().begin() as conn:
        stale = conn.execute(text("""UPDATE tests.test_runs SET state = 'error', finished_at = now(),
                                         message = 'Closed by a later self-test: it had stopped without finishing.'
                                   WHERE id <> :me AND state IN ('queued', 'running')
                                     AND COALESCE(started_at, queued_at) < now() - make_interval(hours => :h)
                               RETURNING id"""), {"me": this_run, "h": stale_hours}).scalars().all()
        runs = conn.execute(text("""SELECT DISTINCT f.run_id FROM tests.test_fixtures f JOIN tests.test_runs r ON r.id = f.run_id
                                     WHERE f.purged_at IS NULL AND f.run_id <> :me AND r.state NOT IN ('queued', 'running')
                                     ORDER BY f.run_id"""), {"me": this_run}).scalars().all()
    total = {"runs": 0, "models": 0, "projects": 0, "service_accounts": 0, "credentials": 0, "closed": len(stale)}
    if not runs:
        log("no test data left from earlier runs" + (f" (closed {len(stale)} stopped run(s))" if stale else ""))
        return total
    log(f"removing the test data left by {len(runs)} earlier run(s): {', '.join(map(str, runs))}")
    for run in runs:
        try:
            with engine.begin() as conn:
                out = purge(conn, run, by)
            total["runs"] += 1
            for k in ("models", "projects", "service_accounts", "credentials"):
                total[k] += out.get(k, 0)
        except Exception as exc:  # noqa: BLE001 - one run's leftovers never stop the new run
            log(f"  run {run}: could not remove all of its test data: {exc}")
    log(f"removed {total['models']} model(s), {total['projects']} project(s), {total['service_accounts']} account(s) and "
        f"{total['credentials']} credential(s) of earlier runs")
    return total

