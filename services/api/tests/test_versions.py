"""Phase 8.3: model tags, comparison and gap analysis (no database needed). The whole flow (tag, compare, make a
tag the latest and back, gap analyses, Gap entities) is in docs/phase-8.3.md."""

import pathlib
import zipfile
from io import BytesIO

from eax import compare as cp
from eax import gaps as gp
from eax.report_defs import REPORTS
from eax.setup import superset_reports as sr

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def _side(label, entities, rels=(), spec=None):
    ents = {e["guid"]: {"kind": "entity", "deleted": False, "description": "", "display_id": "", "status": "published", "tags": [],
                        "parent": None, "origin": None, "values": {}, "layer": "Application", "entity_type": "Application Component",
                        "type_code": "ApplicationComponent", **e} for e in entities}
    rel = {r["guid"]: {"kind": "relationship", "name": "", "type_code": "Flow", "relationship_type": "Flow", "verb": "flows to",
                       "origin": None, **r} for r in rels}
    spec = spec or {"layers": [{"code": "App", "name": "Application"}], "attributes": [{"code": "Owner", "name": "Owner"}],
                    "entity_types": [{"code": "ApplicationComponent", "name": "Application Component", "layer": "App",
                                      "attributes": [{"attribute": "Owner"}]}],
                    "relationship_types": [{"code": "Flow", "name": "Flow"}], "pick_lists": [], "allowed": [], "rules": []}
    return {"kind": "model", "model_id": "m", "model": label, "label": label, "commit": 1, "metamodel_version": 1, "spec": spec,
            "snapshot": {"entities": ents, "relationships": rel}}


def test_matching_and_statuses():
    left = _side("L", [{"guid": "a", "name": "CRM", "display_id": "APP-1", "values": {"Owner": "Sales"}},
                       {"guid": "b", "name": "Old billing"}, {"guid": "c", "name": "Portal", "display_id": "APP-3"}])
    right = _side("R", [{"guid": "x", "name": "CRM", "origin": "a", "values": {"Owner": "Service"}},   # copied from a
                        {"guid": "y", "name": "Customer Portal", "display_id": "APP-3"},                # same display ID, renamed
                        {"guid": "z", "name": "New billing"}])
    assert cp.match(left, right) == {"a": "x", "c": "y"}
    res = cp.compare(left, right)
    by = {i["name"]: i for i in res["items"]}
    assert by["CRM"]["status"] == "changed" and by["CRM"]["changes"][0]["label"] == "Owner"
    assert by["Customer Portal"]["renamed"] and by["Old billing"]["status"] == "eliminated" and by["New billing"]["status"] == "new"
    assert res["totals"] == {"kept": 0, "changed": 2, "new": 1, "eliminated": 1}
    assert cp.match(left, right, {"b": "z"})["b"] == "z"   # a match made by hand wins
    wb = cp.to_xlsx(res)
    assert zipfile.ZipFile(BytesIO(wb)).namelist()   # a workbook


def test_defaults_leave_out_status_tags_and_display_id():
    left = _side("L", [{"guid": "a", "name": "CRM", "status": "retired", "tags": ["x"]}])
    right = _side("R", [{"guid": "a", "name": "CRM", "status": "published"}])
    info = cp.fields_for(left, right)
    d = cp.defaults(info)["types"]["ApplicationComponent"]
    assert "name" in d and "value:Owner" in d and "status" not in d and "tags" not in d and "display_id" not in d
    assert cp.compare(left, right)["totals"]["kept"] == 1
    st = {"types": {"ApplicationComponent": ["name", "status"]}}
    assert cp.compare(left, right, st)["totals"]["changed"] == 1   # status counts once chosen


def test_relationships_follow_the_matched_ends():
    left = _side("L", [{"guid": "a", "name": "A"}, {"guid": "b", "name": "B"}],
                 [{"guid": "r1", "source": "a", "target": "b", "source_name": "A", "target_name": "B"}])
    right = _side("R", [{"guid": "a2", "name": "A", "origin": "a"}, {"guid": "b2", "name": "B", "origin": "b"}],
                  [{"guid": "r2", "source": "a2", "target": "b2", "source_name": "A", "target_name": "B"}])
    res = cp.compare(left, right)
    assert res["relationship_totals"]["kept"] == 1 and res["totals"]["kept"] == 2
    # a relationship added: its ends show it as a change (chosen per entity type: Flow to, Flow from)
    right["snapshot"]["entities"]["c2"] = {**right["snapshot"]["entities"]["b2"], "guid": "c2", "name": "C", "origin": None}
    right["snapshot"]["relationships"]["r3"] = {**right["snapshot"]["relationships"]["r2"], "guid": "r3", "target": "c2", "target_name": "C"}
    res = cp.compare(left, right)
    a = next(i for i in res["items"] if i["name"] == "A")
    assert a["status"] == "changed" and a["changes"][0]["label"] == "Flow to" and a["changes"][0]["right"] == "C"
    info = cp.fields_for(left, right)
    rels = [f for f in info["types"][0]["fields"] if f["code"].startswith("rel:")]
    assert {f["code"] for f in rels} == {"rel:Flow:out", "rel:Flow:in"}
    only_out = {"types": {"ApplicationComponent": ["name", "rel:Flow:in"]}}   # outgoing flows not chosen
    assert next(i for i in cp.compare(left, right, only_out)["items"] if i["name"] == "A")["status"] == "kept"


def test_gap_templates_and_settings():
    codes = [t["code"] for t in gp.TEMPLATES]
    assert codes[0] == "all" and {"business", "data", "application", "technology"} <= set(codes)
    left = _side("L", [{"guid": "a", "name": "CRM"}])
    info = cp.fields_for(left, left)
    assert list(gp.settings_for("application", info, None)["types"]) == ["ApplicationComponent"]
    assert gp.settings_for("technology", info, None)["types"]   # no technology types: every type rather than nothing
    assert set(gp.TOGAF_CELLS) == {"kept", "changed", "new", "eliminated"}


def test_gap_downloads():
    data = {"name": "Apps 2026 to 2028", "description": "", "template": gp.TEMPLATES[3], "compared_at": "2026-11-05T10:00:00",
            "compared_by": "someone", "baseline": {"label": "Baseline", "commit": 1, "metamodel_version": 1},
            "target": {"label": "Target", "commit": 2, "metamodel_version": 1},
            "totals": {"kept": 1, "changed": 0, "new": 1, "eliminated": 1}, "undecided": 1,
            "items": [{"status": s, "togaf_cell": gp.TOGAF_CELLS[s], "layer": "Application", "entity_type": "ApplicationComponent",
                       "entity_type_name": "Application Component", "name": n, "baseline_name": b, "target_name": t, "changes": [],
                       "resolution": r, "note": "", "work_packages": [], "gap_entity": None, "gone": False}
                      for s, n, b, t, r in (("kept", "CRM", "CRM", "CRM", ""), ("new", "Portal", None, "Portal", "Build"),
                                            ("eliminated", "Mainframe", "Mainframe", None, ""))]}
    names = zipfile.ZipFile(BytesIO(gp.to_docx(data))).namelist()
    assert "word/document.xml" in names
    assert b"Gap matrix" in zipfile.ZipFile(BytesIO(gp.to_xlsx(data))).read("xl/workbook.xml")


def test_gap_reports():
    gr = [r for r in REPORTS if r["family"] == "Gap analysis"]
    assert [r["code"] for r in gr] == [f"GR-0{i}" for i in range(1, 6)]
    for r in gr:
        charts = sr.charts_for(r)
        assert charts
        for c in charts:
            view = c["dataset_uuid"]
            assert view
    assert {"gap_analyses", "gap_items", "gap_matrix"} <= set(sr.VIEWS)


def test_web_has_tags_and_compare():
    src = (WEB / "Versions.jsx").read_text(encoding="utf-8")
    for bit in ("/tags", "/restore", "/compare/fields", "/compare/download", "/compare-profiles", "/gaps", "/gap-entities",
                "format=docx", "TOGAF gap matrix"):
        assert bit in src, bit
    page = (WEB / "Metamodel.jsx").read_text(encoding="utf-8")
    assert "TagsTab" in page and "CompareTab" not in page   # Compare and gap analyses are first-class (D177)
    app = (WEB / "App.jsx").read_text(encoding="utf-8")
    assert "CompareScreen" in app and "#/compare" in app
    assert "store_in" in src and "Store the gaps in" in src


def test_gap_results_compared_and_tags():
    assert gp.run_tag("Apps, 2026  to 2028", 3) == "gap-run: apps 2026 to 2028 #3"
    assert gp.analysis_tag("Apps") == "gap-analysis: apps"
    i = lambda k, n, s, r="": {"key": k, "entity_type": "AC", "entity_type_name": "Application Component", "layer": "Application",  # noqa: E731
                               "name": n, "status": s, "resolution": r, "note": "", "changes": []}
    pairs = [gp._pair(i("a", "CRM", "new"), i("a", "CRM", "kept")), gp._pair(None, i("b", "Portal", "new")),
             gp._pair(i("c", "Billing", "eliminated", "Retire"), i("c", "Billing", "eliminated", "Replace")),
             gp._pair(i("d", "HR", "changed"), i("d", "HR", "new")), gp._pair(i("e", "X", "kept"), i("e", "X", "kept"))]
    assert [p["change"] for p in pairs] == ["Gap closed", "New gap", "Resolution changed", "Status changed", "Not a gap in either"]
    res = {"a": {"label": "A #1", "baseline": "B", "target": "T", "totals": {"new": 1}},
           "b": {"label": "A #2", "baseline": "B", "target": "T", "totals": {"new": 1}},
           "counts": {"New gap": 1}, "rows": pairs}
    assert b"Comparison" in zipfile.ZipFile(BytesIO(gp.runs_to_xlsx(res))).read("xl/workbook.xml")
    src = (WEB / "Versions.jsx").read_text(encoding="utf-8")
    assert "/gap-runs/compare" in src and "Two gap results compared" in src and "format=csv" in src
    assert "Filter results by name" in src and "/api/v1/gap-runs/${r.id}" in src   # filter and delete (D189)
    csv = gp.runs_to_csv(res).decode("utf-8-sig").splitlines()
    assert csv[1].startswith("What happened,Layer") and csv[2].startswith("Gap closed")


def test_sides_with_different_types_and_attributes():
    spec_r = {"layers": [{"code": "App", "name": "Application"}], "attributes": [{"code": "Owner", "name": "Owner"}, {"code": "Cost", "name": "Cost"}],
              "entity_types": [{"code": "ApplicationComponent", "name": "Application Component", "layer": "App",
                                "attributes": [{"attribute": "Owner"}, {"attribute": "Cost"}]},
                               {"code": "Node", "name": "Node", "layer": "App", "attributes": []}],
              "relationship_types": [{"code": "Flow", "name": "Flow"}], "pick_lists": [], "allowed": [], "rules": []}
    left = _side("L", [{"guid": "a", "name": "CRM", "values": {"Owner": "Sales"}}])
    right = _side("R", [{"guid": "a", "name": "CRM", "values": {"Owner": "Sales", "Cost": "10"}},
                        {"guid": "n", "name": "Server", "type_code": "Node", "entity_type": "Node"}], spec=spec_r)
    info = cp.fields_for(left, right)
    ac = next(t for t in info["types"] if t["code"] == "ApplicationComponent")
    cost = next(f for f in ac["fields"] if f["code"] == "value:Cost")
    assert cost["only"] == "right" and not cost["default"]
    node = next(t for t in info["types"] if t["code"] == "Node")
    assert node["in_right"] and not node["in_left"]
    res = cp.compare(left, right)   # the defaults: Cost left out, the Node new
    assert res["totals"] == {"kept": 1, "changed": 0, "new": 1, "eliminated": 0}
    st = cp.defaults(info)
    st["types"]["ApplicationComponent"].append("value:Cost")
    assert cp.compare(left, right, st)["totals"]["changed"] == 1   # counted once ticked


def test_element_side_by_side():
    left = _side("L", [{"guid": "a", "name": "CRM", "values": {"Owner": "Sales"}}, {"guid": "b", "name": "Billing"}],
                 [{"guid": "r1", "source": "a", "target": "b", "source_name": "CRM", "target_name": "Billing"}])
    right = _side("R", [{"guid": "a", "name": "CRM", "values": {"Owner": "Service"}}, {"guid": "c", "name": "Ledger"}],
                  [{"guid": "r2", "source": "a", "target": "c", "source_name": "CRM", "target_name": "Ledger"}])
    d = cp.entity_detail(left, right, "a", "a")
    owner = next(f for f in d["fields"] if f["label"] == "Owner")
    assert d["status"] == "changed" and owner["differs"] and owner["left"] == "Sales" and owner["right"] == "Service"
    assert {(r["other"], r["left"], r["right"]) for r in d["relationships"]} == {("Billing", True, False), ("Ledger", False, True)}
    assert cp.entity_detail(left, right, "b", None)["status"] == "eliminated"


def test_web_has_tag_screens_and_details():
    src = (WEB / "Versions.jsx").read_text(encoding="utf-8")
    for bit in ("export function TagPage", "/compare/detail", "/detail`", "side by side"):
        assert bit in src, bit
    assert "Tag this model now" in (WEB / "ModelOps.jsx").read_text(encoding="utf-8")


def test_history_tab_defines_what_it_uses():
    """The entity History tab went blank: it used helpers only the Details tab defined (5 Nov 2026)."""
    src = (WEB / "ModelViews.jsx").read_text(encoding="utf-8")
    body = src[src.index("function HistoryTab("):src.index("\nfunction ", src.index("function HistoryTab(") + 10)]
    for name in ("hl", "f"):
        if f"{name}(" in body:
            assert f"const {name} = " in body, name


def test_rules_as_you_type_and_commit_messages():
    """D194: the form checks the rules before saving; D195: commit messages in History and the change log."""
    form = (WEB / "DataEntry.jsx").read_text(encoding="utf-8")
    assert "/content/entities/check" in form and "checked as you type" in form
    api = (ROOT / "eax" / "api" / "content.py").read_text()
    assert '"/<uuid:model_id>/content/entities/check"' in api
    assert "commit_message" in (ROOT / "eax" / "change_log.py").read_text()
    assert 'ev["commit"]' in (ROOT / "eax" / "repository.py").read_text()
    assert "ALTER TABLE core.commits ADD COLUMN tx" in (ROOT / "migrations" / "sql" / "0015_change_log.sql").read_text()
