"""Deliveries and a model from a metamodel workbook (batch 2, phase 34 and 34.1, D419, D462 to D468; AGENTS.md: every
state): laptop only, made once. Every name is invented.

On Protea Insurance (demo estate):

* source **Configuration database** (EA Explorer's values stay; sent by the service account svc-cmdb-sync) with
  - a delivery **waiting for review**: a CSV set with master.csv holding a new application, one changed (an empty field
    filled), one whose vendor differs (kept as it is in EA Explorer), a row asking to delete (a problem: deliveries never
    delete), a row with no name (a problem), and relationships by name (one new, one whose end is not found);
  - a delivery **accepted** by user_committer (committed as their load) and one **accepted, then undone**;
  - a file **dropped in its folder and not taken yet** (when the import folder is there);
* source **Finance system** (its values win) with a delivery **declined** by user_model_admin and one waiting whose
  changed costs win over EA Explorer's;
* source **Old spreadsheet feed**, switched off.

And a model **Reinsurance programme (from a workbook)**, made from a metamodel workbook on Root (blank), with its
own types (Treaty, Cedent, Work package), a Link attribute and an allowed relationship with multiplicities.
"""

from __future__ import annotations

import csv
import io
import zipfile

from sqlalchemy import text

from .demo_estate import DEMO_NAME

MARK = "Configuration database"
WORKBOOK_MODEL = "Reinsurance programme (from a workbook)"


def _p(name, roles=("user",)):
    from .. import permissions as perms
    return perms.Principal(name, tuple(roles))


def _csv(rows: list[list[str]]) -> str:
    s = io.StringIO()
    w = csv.writer(s)
    for r in rows:
        w.writerow(r)
    return s.getvalue()


def csv_set(apps: list[list[str]], rels: list[list[str]] | None = None) -> bytes:
    """A delivery in the CSV format: master.csv, applications.csv and (if given) relationships.csv."""
    from .. import sheets as sh
    entries = [("applications.csv", "entities", "ApplicationComponent", "Application Component")]
    if rels:
        entries.append(("relationships.csv", "relationships", "", ""))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("master.csv", sh.master_csv(entries))
        z.writestr("applications.csv", _csv(apps))
        if rels:
            z.writestr("relationships.csv", _csv(rels))
    return buf.getvalue()


def run() -> list[str]:
    from .. import permissions as perms
    from ..db import get_engine
    said: list[str] = []
    token = perms.current.set(_p("user_super_admin", ("super-admin",)))
    try:
        with get_engine().begin() as conn:
            done = conn.execute(text("SELECT 1 FROM core.import_sources WHERE name = :n"), {"n": MARK}).first()
            made = conn.execute(text("SELECT 1 FROM core.models WHERE name = :n"), {"n": WORKBOOK_MODEL}).first()
        for step, skip in ((_deliveries, done), (_workbook_model, made)):
            if skip:
                continue
            try:
                said += step()
            except Exception as exc:  # noqa: BLE001 - one part never stops the other
                said.append(f"{step.__name__.strip('_')} not made: {exc}")
    finally:
        perms.current.reset(token)
    return said


def _deliveries() -> list[str]:
    from .. import deliveries as dv
    from .. import loads as ld
    from ..db import get_engine
    sa = _p("user_super_admin", ("super-admin",))
    committer, admin = _p("user_committer"), _p("user_model_admin")
    with get_engine().begin() as conn:
        demo = conn.execute(text("SELECT guid::text FROM core.models WHERE name = :n AND NOT is_deleted"), {"n": DEMO_NAME}).scalar()
        if not demo:
            return []
        sender = conn.execute(text("SELECT username FROM core.service_accounts WHERE username = 'svc-cmdb-sync'")).scalar() \
            if conn.execute(text("SELECT to_regclass('core.service_accounts')")).scalar() else None
        cmdb = dv.save_source(conn, sa, demo, {"name": MARK, "folder": "configuration-database", "values_win": False,
                                               "contact": "user_committer", "sender": sender,
                                               "description": "Applications, vendors, versions and hosting from the configuration "
                                                              "database, every night."})
        fin = dv.save_source(conn, sa, demo, {"name": "Finance system", "folder": "finance", "values_win": True,
                                              "contact": "user_model_admin",
                                              "description": "Annual cost and the owning budget holder of each application."})
        old = dv.save_source(conn, sa, demo, {"name": "Old spreadsheet feed", "folder": "old-spreadsheet",
                                              "description": "Replaced by the configuration database."})
        dv.save_source(conn, sa, demo, {"active": False}, old["id"])

        def deliver(src, name, content, how, by=sa):
            load = dv.deliver(conn, by, src["id"], name, content, how)
            ld.preview(conn, load["id"], sa)
            return load["id"]

        # accepted (committed by the committer as their load)
        a = deliver(cmdb, "cmdb-2026-11-03.zip", csv_set(
            [["name", "Vendor", "Version", "Hosting", "Owner"],
             ["Reinsurance Ledger", "Kestrel Labs", "3.2", "SaaS", "Head of Reinsurance"],
             ["Billing Engine", "", "", "", ""]]), "folder")
        dv.accept(conn, committer, a)
        # accepted, then undone
        u = deliver(cmdb, "cmdb-2026-11-05.zip", csv_set(
            [["name", "Vendor", "Version"], ["Broker Commission Tool", "Marula Soft", "1.0"]]), "api")
        dv.accept(conn, committer, u)
        ld.undo(conn, committer, u)
        # waiting for review: new, changed (an empty field filled), kept, problems; relationships by name
        deliver(cmdb, "cmdb-2026-11-10.zip", csv_set(
            [["name", "Vendor", "Version", "Hosting", "Url", "delete"],
             ["Quote Optimiser", "Kestrel Labs", "1.4", "SaaS", "https://quote.example.org | product page", ""],
             ["Broker Portal", "", "", "", "https://portal.example.org/help | broker help", ""],
             ["CRM", "Lourie CRM Cloud", "", "", "", ""],
             ["Actuarial Modelling", "", "", "", "", "Yes"],
             ["", "Nameless Systems", "", "", "", ""]],
            [["source", "relationship_type", "target", "name"],
             ["Container Platform", "Serving", "Quote Optimiser", "hosts"],
             ["Old Mainframe Box", "Serving", "CRM", ""]]), "api", _p(sender, ("user",)) if sender else sa)
        # the finance system: its values win; one declined, one waiting with changed costs
        fin_file = csv_set([["name", "AnnualCost", "Owner"], ["Billing Engine", "1450000", "Chief Financial Officer"],
                            ["CRM", "980000", ""]])
        d = deliver(fin, "finance-2026-10.zip", fin_file, "upload")
        dv.decline(conn, admin, d, "The October file still had the old cost centres; waiting for the corrected one.")
        deliver(fin, "finance-2026-11.zip", fin_file, "upload")
        # a file dropped in the folder and not taken yet (only where the import folder is there)
        base = dv._make_folders(demo, cmdb["folder"])
        dropped = ""
        if base is not None:
            try:
                (base / "incoming" / "cmdb-2026-11-11.xlsx").write_bytes(_workbook_delivery(conn, demo))
                dropped = " and a file dropped in its folder"
            except OSError:
                pass
    return [f"Import sources on {DEMO_NAME}: Configuration database (a delivery waiting, one accepted, one undone{dropped}), "
            "Finance system (its values win: one declined, one waiting), Old spreadsheet feed (off)"]


def _workbook_delivery(conn, demo: str) -> bytes:
    """An Excel-format delivery (the published template for applications, one row filled)."""
    from openpyxl import load_workbook

    from .. import sheets as sh
    data, _n, _t = sh.build(conn, demo, ["ApplicationComponent"], "xlsx", "svc-cmdb-sync", blank=True)
    wb = load_workbook(io.BytesIO(data))
    ws = next(s for s in wb.worksheets if s.title not in ("Read me", "Lists", "_eax", "Relationships"))
    codes = [c.value for c in ws[2]]
    row = {"name": "Claims Triage Assistant", "Vendor": "Kestrel Labs", "Version": "0.9"}
    for col, code in enumerate(codes, start=1):
        if code in row:
            ws.cell(3, col, row[code])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def workbook_bytes() -> bytes:
    """A small metamodel workbook in our layout (the D419 template, filled)."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Read me"
    sheets = {
        "Model": [["field", "value"], ["name", WORKBOOK_MODEL], ["framework", "Reinsurance EA"], ["version", "1.0"],
                  ["description", "A small metamodel for a reinsurance programme, made from a metamodel workbook."]],
        "Domains": [["code", "name", "colour", "description"], ["Business", "Business", "ECD678", ""],
                    ["Programme", "Programme", "F1BBB7", "Work packages and their documents"]],
        "Pick lists": [["code", "name", "description", "values"], ["TreatyStatus", "Treaty status", "", "Planned\nIn force\nExpired"]],
        "Attributes": [["code", "name", "data_type", "pick_list", "unit", "description", "quality_weight"],
                       ["Owner", "Owner", "text", "", "", "Who answers for it", ""],
                       ["Status", "Status", "list", "TreatyStatus", "", "", ""],
                       ["Capacity", "Capacity", "currency", "", "ZAR", "The treaty's capacity", ""],
                       ["Documents", "Documents", "url", "", "", "Links to the documents (D418)", ""]],
        "Types": [["code", "name", "domain", "id_prefix", "aspect", "description"],
                  ["Treaty", "Treaty", "Business", "TRT", "", "A reinsurance treaty"],
                  ["Cedent", "Cedent", "Business", "CED", "", "An insurer ceding risk"],
                  ["WorkPackage", "Work package", "Programme", "WP", "", "A piece of the programme's work"]],
        "Type attributes": [["type", "attribute", "required", "section", "default", "help", "quality_weight"],
                            ["Treaty", "Owner", "Yes", "", "", "", ""], ["Treaty", "Status", "No", "", "Planned", "", ""],
                            ["Treaty", "Capacity", "No", "", "", "", ""], ["WorkPackage", "Documents", "No", "", "", "", ""],
                            ["WorkPackage", "Owner", "No", "", "", "", ""]],
        "Relationship types": [["code", "name", "verb", "category", "directed", "description"],
                               ["Covers", "Covers", "covers", "", "Yes", "A treaty covers a cedent's business"],
                               ["Delivers", "Delivers", "delivers", "", "Yes", ""]],
        "Allowed relationships": [["source", "relationship", "target", "source_multiplicity", "target_multiplicity", "note"],
                                  ["Treaty", "Covers", "Cedent", "0..*", "1..*", ""],
                                  ["WorkPackage", "Delivers", "Treaty", "", "0..1", ""]],
    }
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _workbook_model() -> list[str]:
    from .. import metamodel_workbook as mw
    from ..db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("SELECT set_config('eax.actor', 'user_model_creator', true)"))
        out = mw.create(conn, _p("user_model_creator", ("model-creator",)), workbook_bytes(), WORKBOOK_MODEL, None)
    return [f"{WORKBOOK_MODEL}: made from a metamodel workbook ({out['counts']['added']} items)"]
