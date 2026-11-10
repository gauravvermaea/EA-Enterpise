"""Published import formats, deliveries and a model from a metamodel workbook (phase 34, D370, D378, D385, D419, D462 to D468).
No database needed: the formats, the master file, the workbook and the rules that need no rows."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from eax import deliveries as dv
from eax import loads as ld
from eax import machine_access as ma
from eax import metamodel_workbook as mw
from eax import sheets as sh
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "sql" / "0042_import_formats.sql").read_text()


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, t in files.items():
            z.writestr(n, t)
    return buf.getvalue()


def test_the_migration_holds_rows_only_and_moves_to_0_18_0():
    assert "'0.18.0'" in SQL and "ON CONFLICT (version) DO NOTHING" in SQL
    assert "CREATE TABLE core.import_sources" in SQL and "'declined'" in SQL
    for word in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"):     # rows only (D248)
        assert word not in SQL.upper(), word
    v = (ROOT / "migrations" / "versions" / "0042_import_formats.py").read_text()
    assert 'revision = "0042_import_formats"' in v and 'down_revision = "0041_scenarios"' in v
    assert 'version = "0.' in (ROOT / "version.toml").read_text()       # 0.18.0 or later (0.19.0: the last set)


def test_a_csv_set_carries_its_master_file_and_reads_back_by_it():
    master = sh.master_csv([("apps.csv", "entities", "ApplicationComponent", "Application Component"),
                            ("links.csv", "relationships", "", "")])
    data = _zip({"master.csv": master, "apps.csv": "name,Vendor\nQuote Optimiser,Kestrel Labs\n",
                 "links.csv": "source,relationship_type,target\nA,Serving,B\n", "notes.csv": "ignored,file\n1,2\n"})
    got = sh.read(data, "delivery.zip")
    assert got["master"] is True
    assert [(s["name"], s["kind"], s["entity_type"]) for s in got["sheets"]] == [
        ("apps", "entities", "ApplicationComponent"), ("links", "relationships", None)]     # notes.csv is not named: not read
    types = [{"code": "ApplicationComponent", "name": "Application Component"}, {"code": "Node", "name": "Node"}]
    assert ld._type_for(got["sheets"][0], types, {})["code"] == "ApplicationComponent"
    assert ld._is_relationships(got["sheets"][1]) and not ld._is_relationships(got["sheets"][0])


def test_a_master_file_naming_a_missing_file_or_a_bad_kind_is_refused():
    with pytest.raises(EditError, match="not in the .zip"):
        sh.read(_zip({"master.csv": sh.master_csv([("gone.csv", "entities", "Node", "")])}), "d.zip")
    with pytest.raises(EditError, match="kind is entities or relationships"):
        sh.read_master(b"file,kind,entity_type\napps.csv,people,Node\n")
    with pytest.raises(EditError, match="give its entity_type"):
        sh.read_master(b"file,kind,entity_type\napps.csv,entities,\n")


def test_a_csv_set_without_a_master_file_reads_as_before():
    got = sh.read(_zip({"Node.csv": "name\nCluster\n", "relationships.csv": "source,target\n"}), "old.zip")
    assert {s["name"] for s in got["sheets"]} == {"Node", "relationships"} and not got["master"]


def test_the_archimate_exchange_format_waits_for_its_publication():
    with pytest.raises(EditError, match="Open Group publishes"):
        sh.read(b"<model/>", "estate.xml")
    with pytest.raises(EditError, match="Open Group publishes"):
        dv._check_file("estate.xml", b"<model/>")
    with pytest.raises(EditError, match="deliver the Excel format"):
        dv._check_file("estate.json", b"{}")


def test_source_folders_are_safe_names():
    assert dv.slug("Configuration database") == "configuration-database"
    assert dv.slug("../../etc") == "etc"
    assert dv.slug("  ") == "source"
    assert all(c.isalnum() or c in "-_" for c in dv.slug("Finance: system (SAP-like) 2026"))


def test_metamodel_workbooks_are_in_the_metamodel_area():
    assert ma.area_of("/api/v1/metamodel-workbooks/preview") == "metamodel"
    assert ma.area_of("/api/v1/import-sources/x/deliveries") == "models"
    assert ma.area_of("/api/v1/models/0b0e6a1e-0000-0000-0000-000000000000/import-sources") == "models"


def test_a_filled_workbook_reads_as_a_metamodel_document():
    from eax.seed.sample_imports import WORKBOOK_MODEL, workbook_bytes
    spec = mw.read(workbook_bytes())
    assert spec["name"] == WORKBOOK_MODEL and spec["framework"] == "Reinsurance EA"
    assert [t["code"] for t in spec["entity_types"]] == ["Treaty", "Cedent", "WorkPackage"]
    treaty = spec["entity_types"][0]
    assert [(a["attribute"], a["required"]) for a in treaty["attributes"]] == [("Owner", True), ("Status", False), ("Capacity", False)]
    assert spec["pick_lists"][0]["values"] == ["Planned", "In force", "Expired"]
    assert {a["code"]: a["data_type"] for a in spec["attributes"]}["Documents"] == "url"       # a Link (D418)
    assert spec["allowed"][0] == {"source": "Treaty", "relationship": "Covers", "target": "Cedent", "source_multiplicity": "0..*",
                                  "target_multiplicity": "1..*", "note": ""}
    assert spec["relationship_types"][0]["directed"] is True


def test_a_workbook_without_types_is_not_a_metamodel_workbook():
    from openpyxl import Workbook
    wb = Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(EditError, match="no Types sheet"):
        mw.read(buf.getvalue())


def _spec(**kw):
    base = {"format": "eax-metamodel/1", "name": "", "framework": "", "version": "", "domains": [], "pick_lists": [],
            "attributes": [], "entity_types": [], "relationship_types": [], "allowed": [], "rules": []}
    base.update(kw)
    return base


def test_adding_to_a_base_adds_and_updates_never_takes_away():
    base = _spec(domains=[{"code": "Business", "name": "Business"}],
                 pick_lists=[{"code": "Status", "name": "Status", "values": ["Active", "Retired"]}],
                 attributes=[{"code": "Owner", "name": "Owner", "data_type": "text"}],
                 entity_types=[{"code": "Actor", "name": "Actor", "domain": "Business", "attributes": [{"attribute": "Owner", "required": False}]},
                               {"code": "Role", "name": "Role", "domain": "Business", "attributes": []}],
                 relationship_types=[{"code": "Assignment", "name": "Assignment", "attributes": []}],
                 allowed=[{"source": "Actor", "relationship": "Assignment", "target": "Role"}],
                 rules=[{"entity_type": "Actor", "attribute": "Owner", "rule_type": "required"}])
    wb = _spec(name="Extended", pick_lists=[{"code": "status", "name": "Status", "values": ["Planned"]}],
               entity_types=[{"code": "Actor", "name": "Business actor", "domain": "", "attributes": [{"attribute": "Owner", "required": True}]},
                             {"code": "Team", "name": "Team", "domain": "Business", "attributes": []}],
               allowed=[{"source": "Team", "relationship": "Assignment", "target": "Role", "target_multiplicity": "1"},
                        {"source": "Actor", "relationship": "Assignment", "target": "Role", "note": "people only"}])
    out, what = mw.merge_specs(base, wb)
    assert [t["code"] for t in out["entity_types"]] == ["Actor", "Role", "Team"]             # Role stays: nothing taken away
    actor = out["entity_types"][0]
    assert actor["name"] == "Business actor" and actor["domain"] == "Business"               # an empty cell keeps the base's value
    assert actor["attributes"][0]["required"] is True
    assert out["pick_lists"][0]["values"] == ["Active", "Retired", "Planned"]
    assert len(out["allowed"]) == 2 and out["allowed"][0]["note"] == "people only"
    assert len(out["rules"]) == 1 and out["name"] == "Extended"
    assert what["entity_types"] == {"added": ["Team"], "changed": ["Actor"]}
    assert what["allowed"]["added"] == ["Team Assignment Role"] and what["allowed"]["changed"] == ["Actor Assignment Role"]
    assert what["pick_lists"]["changed"] == ["status"]


def test_type_attributes_for_a_type_only_the_base_has_join_it():
    base = _spec(attributes=[{"code": "Docs", "name": "Documents", "data_type": "url"}],
                 entity_types=[{"code": "WorkPackage", "name": "Work package", "domain": "I", "attributes": []}])
    wb = _spec(_pending_items=[("workpackage", {"attribute": "Docs", "required": False})])
    out, what = mw.merge_specs(base, wb)
    assert out["entity_types"][0]["attributes"] == [{"attribute": "Docs", "required": False}]
    assert what["entity_types"]["changed"] == ["WorkPackage"] and not out["_orphans"]
    out, _ = mw.merge_specs(_spec(), _spec(_pending_items=[("nowhere", {"attribute": "Docs"})]))
    assert out["_orphans"] and "nowhere" in out["_orphans"][0]


def test_whoever_creates_models_may_make_one_from_a_workbook():
    from eax import permissions as perms
    assert mw.may_create(perms.Principal("a", ("model-creator",)))
    assert mw.may_create(perms.Principal("b", ("library-admin",)))
    assert mw.may_create(perms.Principal("c", ("super-admin",)))
    assert not mw.may_create(perms.Principal("d", ("user",)))


def test_delivery_rules_are_in_the_preview():
    import inspect
    src = inspect.getsource(ld.preview)
    for s in ("A delivery never deletes (D370)", "blank_clears = False", 'row["kept"]', "never removes relationships",
              "a delivery is matched by type"):
        assert s in src, s
    acc = inspect.getsource(dv.accept)
    assert "may_accept" in acc and "cm.commit(" in acc


def test_eax_import_is_in_every_form_and_the_help():
    repo = ROOT.parents[1]
    assert "### import [source|--all] [--as user]" in (repo / "eaxcli" / "help.txt").read_text()
    assert "eax.deliveries_cli" in (repo / "eax.sh").read_text()
    assert "eax.deliveries_cli" in (repo / "eax.ps1").read_text()
    assert "eax.deliveries_cli" in (repo / "eaxcli" / "main.py").read_text()
    assert "`eax import" in (repo / "docs" / "command-line-and-console.md").read_text()
