"""Scenario planning with AI (phase 27.1, D364, D490 to D495): the rules that need no database.

The end-to-end session (figures, comparison, what-ifs as uncommitted changes, making a scenario, an assessment with a
governance decision sent for approval) was run against a test database; see docs/phase-27.1.md."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from eax import project_backup as pb
from eax import scenarios as sc
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "migrations" / "sql" / "0041_scenarios.sql").read_text(encoding="utf-8")


def test_the_migration_holds_rows_only():
    assert "CREATE TABLE IF NOT EXISTS proj.scenario_assessments" in SQL
    assert "'0.18.0', '0041_scenarios'" in SQL and "ON CONFLICT (version) DO NOTHING" in SQL
    for word in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "CREATE POLICY"):
        assert word not in SQL.upper(), word          # D248: no logic in the database
    v = (ROOT / "migrations" / "versions" / "0041_scenarios.py").read_text(encoding="utf-8")
    assert 'revision = "0041_scenarios"' in v and "0041_scenarios.sql" in v


def test_a_project_backup_carries_the_assessments():
    t = next(x for x in pb.TABLES if x[0] == "scenario_assessments")
    assert t[2] == {"document_id": "documents", "gov_record_id": "gov_records"}
    names = [x[0] for x in pb.TABLES]
    assert names.index("scenario_assessments") > names.index("gov_records") > names.index("documents")
    assert "scenario_assessments" in pb.NEW_GUID


def test_the_suggested_score():
    base = {"total_cost": 1000.0, "risks": 4, "capabilities_covered": 10, "applications": 20}
    assert sc.suggested_score(base, dict(base)) == {"score": 5.0, "reasons": ["no difference in the figures"]}
    better = sc.suggested_score(base, {"total_cost": 800.0, "risks": 2, "capabilities_covered": 11, "applications": 18})
    assert better["score"] > 5 and any("cost down 20%" in r for r in better["reasons"])
    worse = sc.suggested_score(base, {"total_cost": 3000.0, "risks": 10, "capabilities_covered": 6, "applications": 30})
    assert 0 <= worse["score"] < 5
    assert sc.suggested_score({}, {})["score"] == 5.0


def test_the_difference_is_scenario_minus_baseline():
    d = sc._delta({"applications": 30, "total_cost": 100.0, "risks": 3}, {"applications": 28, "total_cost": 90.5, "risks": 4})
    assert d == {"applications": -2, "total_cost": -9.5, "risks": 1}


def _models():
    return [{"id": "11111111-1111-1111-1111-111111111111", "name": "Estate", "role": "current"},
            {"id": "22222222-2222-2222-2222-222222222222", "name": "Scenario A", "role": "scenario"}]


def test_the_baseline_and_picking_a_model():
    ms = _models()
    assert sc.baseline_of(ms)["name"] == "Estate"
    assert sc.baseline_of(ms, "scenario a")["name"] == "Scenario A"
    assert sc._pick(ms, "22222222-2222-2222-2222-222222222222", "x")["name"] == "Scenario A"
    with pytest.raises(EditError, match="not a model of this project"):
        sc._pick(ms, "Elsewhere", "scenario")
    with pytest.raises(EditError, match="no Current state model"):
        sc.baseline_of([ms[1]])


def test_what_ifs_must_be_a_list():
    for bad in ([], None, "retire X", [{}] * 51):
        with pytest.raises(EditError):
            sc._plan_what_ifs(None, {"id": "m", "name": "M"}, None, bad)


def test_the_assessment_as_a_word_document():
    a = {"ref": "SCN-001", "title": "Build or buy", "baseline": "Estate", "created_by": "user_architect", "created_at": "2026-11-10T10:00",
         "recommended": "Scenario B", "recommendation": "Buy it.\n\nIt costs less.",
         "scenarios": [{"name": "Scenario B", "score": 7.5, "notes": "cheaper",
                        "figures": {"total_cost": 900.0, "applications": 28, "capabilities": 10, "capabilities_covered": 9, "risks": 2},
                        "baseline_figures": {"total_cost": 1000.0, "applications": 30, "capabilities": 10, "capabilities_covered": 10,
                                             "risks": 1},
                        "comparison": {"totals": {"added": 1, "changed": 3, "retired": 2},
                                       "added": [{"name": "Policy Suite", "type": "Application Component"}],
                                       "retired": [{"name": "Old System", "type": "Application Component"}], "changed": [],
                                       "capabilities_touched": ["Underwriting"]}}]}
    data = sc.assessment_docx(a, "Build or buy project")
    doc = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
    for want in ("Build or buy", "Recommended: Scenario B", "It costs less.", "Policy Suite (Application Component)",
                 "Capabilities touched: Underwriting", "Estate (baseline)", "7.5"):
        assert want in doc, want


def test_the_mcp_tools_and_prompt():
    src = (ROOT / "eax" / "mcp_scenarios.py").read_text(encoding="utf-8")
    tools = set(re.findall(r"@mcp\.tool\(\)\nasync def (\w+)", src))
    assert tools == {"how_to_plan_scenarios", "scenario_overview", "compare_scenario", "list_scenario_assessments", "make_scenario",
                     "apply_what_ifs", "record_scenario_assessment"}
    assert "def plan_scenarios(" in src
    server = (ROOT / "eax" / "mcp_server.py").read_text(encoding="utf-8")
    assert re.search(r"from \. import (\(.*?)?\bmcp_scenarios\b", server, re.S), "the server imports mcp_scenarios"
    # every changing tool previews first (a confirm token) and checks a read-only credential
    for t in ("make_scenario", "apply_what_ifs", "record_scenario_assessment"):
        body = src.split(f"async def {t}(")[1].split("@mcp.tool()")[0]
        assert "write=True" in body and "confirm=confirm" in body, t
    assert "_may_write()" in src and "mcp_ops._use_preview" in src and "mcp_ops._keep_preview" in src


def test_the_preview_token_is_bound_to_the_arguments():
    a = sc.preview_hash("apply_what_ifs", {"project": "P", "actions": [{"retire": "X"}], "confirm": "pv_1", "why": "because"})
    b = sc.preview_hash("apply_what_ifs", {"project": "P", "actions": [{"retire": "X"}]})
    c = sc.preview_hash("apply_what_ifs", {"project": "P", "actions": [{"retire": "Y"}]})
    d = sc.preview_hash("make_scenario", {"project": "P", "actions": [{"retire": "X"}]})
    assert a == b and b != c and b != d


def test_the_rest_api_and_the_seed():
    api = (ROOT / "eax" / "api" / "scenarios.py").read_text(encoding="utf-8")
    for route in ("/projects/<string:project>/scenarios", "/scenarios/<string:model>/compare", "/scenario-assessments/<string:aid>",
                  "/scenario-assessments/<string:aid>/docx"):
        assert route in api, route
    assert "scenarios_blp" in (ROOT / "eax" / "app.py").read_text(encoding="utf-8")
    later = (ROOT / "eax" / "seed" / "later.py").read_text(encoding="utf-8")
    assert "sample_scenarios" in later
    seed = (ROOT / "eax" / "seed" / "sample_scenarios.py").read_text(encoding="utf-8")
    assert "confirm=True" in seed and 'governance="approval"' in seed and "cm.commit(" in seed
    assert "objective" not in seed.lower()
