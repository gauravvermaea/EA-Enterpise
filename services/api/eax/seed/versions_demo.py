"""Laptop only (phase 8.3, D176): the demo estate Protea Insurance comes with tags, comparisons and gap analyses,
so the Tags and Compare tabs and the gap reports GR-01 to GR-05 have something to show from the first start.

Made once (when Protea has no tags yet), through the same functions the API uses, as the laptop test users. It runs
in the background after the API has started (entrypoint.sh: `python -m eax.seed.versions_demo &`), so a slow machine
never keeps the API from becoming healthy; each step is logged with its time, and waits on locks are cut short:
  1. user_architect tags the estate as loaded: *Baseline 2026*.
  2. user_model_admin moves it on to a target: merges the Merge test file (new entities, changed values, two new
     attributes), retires two applications (deleted with their relationships), renames one and changes a few values;
     then tags it *Target 2028*, locked.
  3. user_architect saves the comparison profile *Applications and data* and makes two gap analyses:
     *Whole architecture 2026 to 2028* (Baseline 2026 against Target 2028), with resolutions, notes and a work
     package, compared again after more decisions (results #1 and #2); and *Application Architecture since baseline*
     (Baseline 2026 against the model as it is now).
  4. user_model_admin adds the gaps of the whole-architecture analysis as Gap entities (tagged with the analysis and
     its result #2).
"""

from __future__ import annotations

import os
import sys
import time

from sqlalchemy import text

from .. import commits as cm
from .. import compare as cp
from .. import gaps as gp
from .. import merge as mg
from .. import permissions
from .. import tags as tg
from ..db import get_engine

MODEL = "Protea Insurance (demo estate)"
RETIRED = ["Billing Engine", "Regulatory Reporting Tool"]
RENAMED = ("Claims Platform", "Claims Platform (cloud)")
CHANGED = {"Customer Portal": {"Lifecycle": "Phase Out"}, "Data Warehouse": {"Hosting": "Cloud"}}


class _User:
    def __init__(self, name: str):
        self.username = name
        self.roles = ["user"]


def _as(name: str) -> _User:
    u = _User(name)
    permissions.current.set(permissions.Principal(u.username, tuple(u.roles)))
    return u


def _say(msg: str) -> None:
    print(f"EA Explorer demo estate: {msg}", flush=True)


def _step(fn, label: str = ""):
    """One transaction as the current test user (the identity is set when the connection is checked out), logged
    with its time; a lock held elsewhere for more than 60 seconds stops the step instead of waiting for ever."""
    t = time.monotonic()
    with get_engine().connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL lock_timeout = '60s'"))
            conn.execute(text("SET LOCAL statement_timeout = '600s'"))
            out = fn(conn)
    if label:
        _say(f"{label} ({time.monotonic() - t:.1f} s)")
    return out


def _guid(conn, m: str, name: str) -> str | None:
    return conn.execute(text("""SELECT e.guid FROM core.entities e JOIN core.models m ON m.id = e.model_id
                                 WHERE m.guid = CAST(:m AS uuid) AND e.name = :n AND NOT e.is_deleted"""), {"m": m, "n": name}).scalar()


def run() -> str:
    try:
        with get_engine().connect() as conn:
            m = conn.execute(text("SELECT guid FROM core.models WHERE name = :n"), {"n": MODEL}).scalar()
            if not m:
                return "the demo estate is not loaded"
            if conn.execute(text("SELECT count(*) FROM core.model_tags t JOIN core.models x ON x.id = t.model_id WHERE x.guid = :m"),
                            {"m": m}).scalar():
                return "already there"
        m = str(m)

        arch = _as("user_architect")
        base = _step(lambda c: tg.create_tag(c, m, arch, "Baseline 2026", "The estate as loaded: the baseline for the 2028 target"),
                     "tagged Baseline 2026")

        admin = _as("user_model_admin")

        def merge(c):
            data, name, _ = mg.sample_package(c, m, "zip", admin.username)
            plan = mg.analyse(c, m, data, name, admin)
            return mg.apply(c, m, plan["id"], admin, None, "theirs", True)
        _step(merge, "merged the Merge test file")

        def target(c):
            ops = []
            for name in RETIRED:
                g = _guid(c, m, name)
                if not g:
                    continue
                for r in cm._rows(c, """SELECT r.guid FROM core.relationships r JOIN core.entities e
                                          ON e.id IN (r.source_entity_id, r.target_entity_id)
                                         WHERE e.guid = :g AND NOT r.is_deleted""", g=str(g)):
                    ops.append(("relationship.delete", {"relationship": str(r["guid"])}))
                ops.append(("entity.delete", {"entity": str(g)}))
            g = _guid(c, m, RENAMED[0])
            if g:
                ops.append(("entity.update", {"entity": str(g), "data": {"name": RENAMED[1]}}))
            for name, values in CHANGED.items():
                g = _guid(c, m, name)
                if g:
                    ops.append(("entity.update", {"entity": str(g), "data": {"values": values}}))
            cm.record_many(c, m, admin.username, ops)
            return cm.commit(c, m, admin, None, None, None, "Target 2028: two applications retired, claims moved to the cloud")
        _step(target, "retired, renamed and changed the target elements")
        tgt = _step(lambda c: tg.create_tag(c, m, admin, "Target 2028", "The agreed target architecture for 2028", lock=True),
                    "tagged Target 2028 (locked)")

        arch = _as("user_architect")
        b, t = {"kind": "tag", "id": base["id"]}, {"kind": "tag", "id": tgt["id"]}

        def profile(c):
            info = cp.fields_for(cp.load_side(c, b), cp.load_side(c, t))
            d = cp.defaults(info)
            keep = {x["code"] for x in info["types"] if x["domain"] in ("Application", "Data", "Information")} or set(d["types"])
            d["types"] = {k: v for k, v in d["types"].items() if k in keep}
            return cp.save_profile(c, arch, "Applications and data", d)
        _step(profile, "saved the comparison profile")

        whole = _step(lambda c: gp.create(c, m, arch, "Whole architecture 2026 to 2028", b, t, "all", None,
                                          "Baseline 2026 against the locked Target 2028 tag"), "gap analysis: whole architecture")
        gaps = [i for i in whole["items"] if i["status"] != "kept"]
        by = {s: [i for i in gaps if i["status"] == s] for s in ("new", "changed", "eliminated")}

        def decide(c):
            wp = c.execute(text("""SELECT e.guid FROM core.entities e JOIN core.entity_types y ON y.id = e.entity_type_id
                                    JOIN core.models x ON x.id = e.model_id
                                   WHERE x.guid = CAST(:m AS uuid) AND y.code = 'WorkPackage' AND NOT e.is_deleted ORDER BY e.name LIMIT 1"""),
                           {"m": m}).scalar()
            for i in by["eliminated"]:
                gp.update_item(c, m, arch, whole["id"], i["id"], note="Retired by 2028; data moved first", resolution="Retire",
                               work_packages=[str(wp)] if wp else None)
            if by["new"]:
                gp.update_items(c, m, arch, whole["id"], [i["id"] for i in by["new"][:2]], resolution="Build")
            if by["changed"]:
                gp.update_items(c, m, arch, whole["id"], [i["id"] for i in by["changed"][:4]], resolution="Enhance")
        _step(decide, "decided the first gaps")
        # more decisions, then compared again: result #2 (the resolutions changed since #1)
        def more(c):
            if by["new"][2:]:
                gp.update_items(c, m, arch, whole["id"], [i["id"] for i in by["new"][2:4]], resolution="Buy")
            if by["changed"][4:]:
                gp.update_items(c, m, arch, whole["id"], [i["id"] for i in by["changed"][4:7]], resolution="Not a gap")
            return gp.refresh(c, m, arch, whole["id"])
        _step(more, "more decisions, compared again (result #2)")

        _step(lambda c: gp.create(c, m, arch, "Application Architecture since baseline", b, {"kind": "model", "id": m},
                                  "application", None, "Baseline 2026 against the model as it is now"),
              "gap analysis: application architecture")

        admin = _as("user_model_admin")
        out = _step(lambda c: gp.add_gap_entities(c, m, admin, whole["id"]), "added the Gap entities")
        return (f"tags Baseline 2026 and Target 2028, profile, 2 gap analyses (3 results), "
                f"{out['gap_entities']} Gap entities")
    finally:
        permissions.current.set(None)


def run_sheets() -> str:
    """Phase 10.1 demo (D197): a saved column mapping for the sample CMDB file (deploy/samples/cmdb-applications.csv)
    and a load previewed for the architect."""
    import io

    from openpyxl import load_workbook

    from .. import loads as ld
    from .. import sheets as sh
    with get_engine().connect() as conn:
        m = conn.execute(text("SELECT guid FROM core.models WHERE name = :n"), {"n": MODEL}).scalar()
        if not m:
            return "the demo estate is not loaded"
        if conn.execute(text("SELECT count(*) FROM core.column_mappings s JOIN core.models x ON x.id = s.model_id WHERE x.guid = :m"),
                        {"m": m}).scalar():
            return "already there"
    m = str(m)
    try:
        arch = _as("user_architect")
        _step(lambda c: ld.save_mapping(c, arch, m, "CMDB applications", "ApplicationComponent",
                                        {"Application": "name", "Business owner": "Owner", "Status": "Lifecycle", "Vendor": "Vendor"}),
              "saved mapping")

        def review(c):
            data, _n, _t = sh.build(c, m, ["ApplicationComponent", "Capability"], "xlsx", "user_architect")
            wb = load_workbook(io.BytesIO(data))
            ws = wb["Application Component"]
            codes = [x.value for x in ws[2]]
            ws.cell(3, codes.index("description") + 1, "Reviewed in the yearly application review")
            r = 3
            while ws.cell(r, 1).value:
                r += 1
            ws.cell(r, 3, "Claims Triage Assistant")
            buf = io.BytesIO()
            wb.save(buf)
            load = ld.create(c, m, arch, "Protea application review (sample).xlsx", buf.getvalue())
            ld.preview(c, load["id"], arch)
            return load
        _step(review, "a load previewed for user_architect")
        return "a saved column mapping and a previewed load"
    finally:
        permissions.current.set(None)


def main() -> int:
    """Laptop with the sample only; never fails the container (the API is already serving)."""
    from ..config import get_settings
    with_sample = os.environ.get("EAX_SEED_SAMPLE", "false").strip().lower() in ("1", "true", "yes")
    if get_settings().deployment != "laptop" or not with_sample:
        return 0
    t = time.monotonic()
    try:
        _say(f"tags and gap analyses: {run()} ({time.monotonic() - t:.0f} s)")
        _say(f"sheets: {run_sheets()}")
    except Exception as exc:  # noqa: BLE001 - demo data is a convenience
        print(f"EA Explorer demo estate WARNING: tags and gap analyses not made ({exc}); a clean restart tries again",
              file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
