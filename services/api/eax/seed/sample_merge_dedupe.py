"""Merge requests and duplicates (batch 1, phases 19, 20 and 21; owner, 10 Nov 2026, D359, D361): laptop only, made once.
Every name is invented.

Merge requests, one in each state:

* **sent, waiting for review** (with a conflict): Fynbos Commercial into Fynbos Mutual (group): a description changed in
  both, an attribute changed in the child, a new business object, one removed;
* **merged, waiting for the child's choice** (freeze or refresh): Fynbos Life into the group: two changes accepted (one
  of them a conflict decided for the child), a new business object, and a relationship rejected with its reason; the
  merge report kept;
* **closed, child refreshed**: Karoo Digital refresh 2027 into Karoo Digital (lean), refreshed after the merge (a new
  starting point);
* **closed, child frozen**: Fynbos group operating model target into the group, frozen after the merge;
* **withdrawn**: Protea claims transition 2027, sent and taken back.
Children of the sample projects are used when they are there (the next start makes the rest).

Duplicates in Protea Insurance (demo estate):

* found by name: "Claims Platfrom" (a typo of Claims Platform) and "Quote-Engine" (Quote Engine);
* found only by attributes (the same vendor and version): "Payments Gateway" beside the Payments Hub;
* merged and committed: "Mobile Claims App" into the Mobile App by a committer; its old display ID still finds the app;
* merged and waiting for a commit: "Document Store" into Document Management by an architect (their own changes).
"""

from __future__ import annotations

from sqlalchemy import text

from .demo_estate import DEMO_NAME

GROUP, LIFE, COMMERCIAL = "Fynbos Mutual (group)", "Fynbos Life", "Fynbos Commercial"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _model(conn, name: str) -> dict | None:
    from .. import repository as repo
    g = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": name}).scalar()
    return repo.get_model(conn, g) if g else None


def _ents(conn, m: dict, type_code: str) -> list[dict]:
    return [dict(r) for r in conn.execute(text("""
        SELECT e.guid::text AS g, e.name, e.origin_guid::text AS o FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND t.code = :t ORDER BY e.name"""), {"m": m["_id"], "t": type_code}).mappings()]


def _commit(conn, m: dict, who, items: list, message: str) -> list[dict]:
    from .. import commits as cm
    res = cm.record_many(conn, m["id"], who.username, items)
    ids = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
    if ids:
        cm.commit(conn, m["id"], who, None, ids, None, message)
    return res


def _guid_of(conn, m: dict, name: str) -> str | None:
    return conn.execute(text("SELECT guid::text FROM core.entities WHERE model_id = :m AND name = :n AND NOT is_deleted LIMIT 1"),
                        {"m": m["_id"], "n": name}).scalar()


def run() -> list[str]:
    from .. import permissions as perms
    from ..db import get_engine
    said: list[str] = []
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    try:
        with get_engine().begin() as conn:
            if conn.execute(text("SELECT 1 FROM core.merge_requests LIMIT 1")).first() or \
               conn.execute(text("SELECT 1 FROM core.entity_aliases LIMIT 1")).first():
                return []
        for step in (_requests, _project_requests, _duplicates):
            try:
                said += step()
            except Exception as exc:  # noqa: BLE001 - one part never stops the other
                said.append(f"{step.__name__.strip('_')} not made: {exc}")
    finally:
        perms.current.reset(token)
    return said


def _requests() -> list[str]:
    from .. import merge_back as mb
    from ..db import get_engine
    said = []
    sa, ma = _p("user_super_admin", ("super-admin",)), _p("user_model_admin")
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_model_admin', true)"))
        group, life, com = _model(conn, GROUP), _model(conn, LIFE), _model(conn, COMMERCIAL)
        if not (group and life and com):
            return ["merge requests skipped: the Fynbos models are not there"]
        for child in (life, com):
            mb.mark_start(conn, str(child["id"]), "user_model_admin")

        # Fynbos Life: merged, waiting for the child's choice
        bo = _ents(conn, life, "BusinessObject")
        a, b = bo[0], bo[1]
        _commit(conn, life, ma, [
            ("entity.update", {"entity": a["g"], "data": {"description": f"{a['name']}: kept for every life policy, including funeral cover."}}),
            ("entity.update", {"entity": b["g"], "data": {"description": f"{b['name']}: as the life business records it."}}),
            ("entity.create", {"data": {"entity_type": "BusinessObject", "name": "Funeral Cover Quote",
                                        "description": "A quote for funeral cover, given before the policy is taken up."}})],
            "Life products: funeral cover")
        quote = _guid_of(conn, life, "Funeral Cover Quote")
        _commit(conn, life, ma, [("relationship.create", {"data": {"relationship_type": "Association", "source": quote, "target": a["g"],
                                                                   "allow_outside": True}})], "Quote linked")
        _commit(conn, group, sa, [("entity.update", {"entity": b["o"], "data": {"description": f"{b['name']}: the group's own wording."}})],
                "Group wording")
        r = mb.send(conn, str(life["id"]), ma, "Funeral cover is agreed for the life business: please take it into the group model.")
        full = mb.get(conn, r["id"], sa)
        dec = {}
        for c in full["changes"]:
            if c["conflict"]:
                dec[c["id"]] = {"accept": True, "reason": "The life business's wording is the agreed one."}
            elif c["kind"] == "relate":
                dec[c["id"]] = {"accept": False, "reason": "Quotes are linked to products at group level, not to records."}
        mb.decide(conn, r["id"], ma, dec)
        mb.merge(conn, r["id"], ma)
        said.append(f"merge request {r['number']}: {LIFE} merged into {GROUP}, waiting for the child's choice")

        # Fynbos Commercial: sent, waiting for review (a conflict among the changes)
        bo = _ents(conn, com, "BusinessObject")
        a, b, d = bo[2], bo[3], bo[-1]
        _commit(conn, com, sa, [
            ("entity.update", {"entity": a["g"], "data": {"description": f"{a['name']}: for short-term and commercial lines."}}),
            ("entity.update", {"entity": b["g"], "data": {"description": f"{b['name']}: commercial wording."}}),
            ("entity.create", {"data": {"entity_type": "BusinessObject", "name": "Fleet Schedule",
                                        "description": "The vehicles covered by a commercial fleet policy."}}),
            ("entity.delete", {"entity": d["g"]})], "Commercial lines")
        _commit(conn, group, sa, [("entity.update", {"entity": b["o"], "data": {"description": f"{b['name']}: group wording, agreed in March."}})],
                "Group wording")
        r = mb.send(conn, str(com["id"]), sa, "Commercial lines changes for the group model; one description differs from the group's.")
        said.append(f"merge request {r['number']}: {COMMERCIAL} sent to {GROUP}, waiting for review")

    return said


def _project_requests() -> list[str]:
    """The sample projects' children: refreshed, frozen, withdrawn (when the sample projects are there)."""
    from .. import merge_back as mb
    from ..db import get_engine
    said = []
    sa = _p("user_super_admin", ("super-admin",))
    for child_name, end in (("Karoo Digital refresh 2027", "refresh"), ("Fynbos group operating model target", "freeze"),
                            ("Protea claims transition 2027", "withdraw")):
        try:
            with get_engine().begin() as conn:
                conn.execute(text("SELECT set_config('eax.actor', 'user_super_admin', true)"))
                child = _model(conn, child_name)
                if not child or not child.get("parent_model_id"):
                    said.append(f"{child_name} is not there yet: its merge request is made on a later start")
                    continue
                if not mb._start_tag(conn, child["_id"]):
                    mb.mark_start(conn, str(child["id"]), "user_super_admin")
                types = [r["code"] for r in conn.execute(text("""SELECT t.code FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                                                                  WHERE e.model_id = :m AND NOT e.is_deleted GROUP BY t.code
                                                                  ORDER BY count(*) DESC LIMIT 1"""), {"m": child["_id"]}).mappings()]
                if not types:
                    continue
                e = _ents(conn, child, types[0])[0]
                _commit(conn, child, sa, [("entity.update", {"entity": e["g"], "data": {"description": f"{e['name']}: as changed in {child_name}."}})],
                        f"Work in {child_name}")
                r = mb.send(conn, str(child["id"]), sa, f"{child_name}: ready to merge.")
                if end == "withdraw":
                    mb.withdraw(conn, r["id"], sa, "Sent too early: the transition is not agreed yet.")
                    said.append(f"merge request {r['number']}: {child_name} withdrawn")
                    continue
                mb.merge(conn, r["id"], sa)
                mb.finish(conn, r["id"], sa, end, f"{child_name} merged into its parent.")
                said.append(f"merge request {r['number']}: {child_name} merged and {'refreshed' if end == 'refresh' else 'frozen'}")
        except Exception as exc:  # noqa: BLE001 - one sample never stops the others
            said.append(f"merge request of {child_name} not made: {exc}")
    return said


def _duplicates() -> list[str]:
    from .. import dedupe as dd
    from ..db import get_engine
    co, ar = _p("user_committer"), _p("user_architect")
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_committer', true)"))
        m = _model(conn, DEMO_NAME)
        if not m:
            return []
        hub = conn.execute(text("""SELECT a.code, coalesce(v.value_text, v.value_number::text) AS v
                                     FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                                     JOIN core.entities e ON e.id = v.entity_id
                                    WHERE e.model_id = :m AND e.name = 'Payments Hub' AND NOT v.is_deleted AND a.code IN ('Vendor', 'Version')"""),
                           {"m": m["_id"]}).mappings().all()
        same = {r["code"]: r["v"] for r in hub} or {"Vendor": "Rand Payments", "Version": "4.1"}
        new = [("Claims Platfrom", {"Owner": "Head of Claims IT", "Lifecycle": "Production"}, "Typed in again by mistake: the Claims Platform."),
               ("Quote-Engine", {"Owner": "Head of Distribution IT", "Lifecycle": "Production"}, "The quote engine, loaded from a broker's sheet."),
               ("Payments Gateway", {"Owner": "Head of Finance IT", "Lifecycle": "Production", **same},
                "Loaded from the finance team's list: the same product and version as the Payments Hub."),
               ("Mobile Claims App", {"Owner": "Head of Digital", "Lifecycle": "Production"}, "The claims part of the mobile app, listed apart."),
               ("Document Store", {"Owner": "Head of Operations IT", "Lifecycle": "Production"}, "The document store, loaded twice.")]
        _commit(conn, m, co, [("entity.create", {"data": {"entity_type": "ApplicationComponent", "name": n, "description": d, "values": v}})
                              for n, v, d in new], "Applications loaded from team lists (with duplicates)")
        dept = _guid_of(conn, m, "Claims Department")
        mca = _guid_of(conn, m, "Mobile Claims App")
        if dept and mca:
            _commit(conn, m, co, [("relationship.create", {"data": {"relationship_type": "Serving", "source": mca, "target": dept,
                                                                    "allow_outside": True}})], "Mobile claims serve the claims team")
        mobile, store, docs = _guid_of(conn, m, "Mobile App"), _guid_of(conn, m, "Document Store"), _guid_of(conn, m, "Document Management")
        said = []
        if mobile and mca:
            out = dd.merge(conn, str(m["id"]), co, mobile, [mca], {"description": mobile})
            said.append(f"duplicates: {out['message']}")
    if store and docs:
        from .. import permissions as perms
        token = perms.current.set(ar)          # the architect's own changes: an architect does not commit
        try:
            with get_engine().begin() as conn:
                conn.execute(text("SELECT set_config('eax.actor', 'user_architect', true)"))
                out = dd.merge(conn, str(m["id"]), ar, docs, [store])
                said.append(f"duplicates: {out['message']}")
        finally:
            perms.current.reset(token)
    return said
