"""The stakeholder matrix (owner, 8 Nov 2026, D294), project completion and steps (owner, 8 Nov 2026)."""

import inspect
import json
from pathlib import Path

import pytest

from eax import project_backup as pb
from eax import projects as pj
from eax import stakeholders as sh
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_class_from_power_and_interest():
    grid = {("H", "H"): "key", ("H", "M"): "key", ("H", "L"): "satisfied", ("M", "H"): "key", ("M", "M"): "informed",
            ("M", "L"): "satisfied", ("L", "H"): "informed", ("L", "M"): "informed", ("L", "L"): "minimal"}
    for (p, i), c in grid.items():
        assert sh.auto_class(p, i) == c
    assert sh.auto_class("", "H") == ""
    js = (WEB / "Stakeholders.jsx").read_text()
    assert 'H: { H: "key", M: "key", L: "satisfied" }, M: { H: "key", M: "informed", L: "satisfied" }, L: { H: "informed", M: "informed", L: "minimal" }' in js


def test_clean():
    c = sh.clean({"name": " CIO ", "power": "high", "interest": "l", "category": "corporate", "views": ["VP-05"],
                  "next_contact": "2026-12-01", "notes_html": "<p>x</p><script>y</script>"}, {"g1": 7})
    assert c["name"] == "CIO" and c["power"] == "H" and c["interest"] == "L" and "script" not in c["notes_html"]
    for bad in ({"name": ""}, {"name": "X", "power": "Z"}, {"name": "X", "category": "nope"}, {"name": "X", "class": "boss"},
                {"name": "X", "next_contact": "soon"}):
        with pytest.raises(EditError):
            sh.clean(bad)
    assert sh.clean({"name": "X", "items": ["g1", "gone"]}, {"g1": 7})["items"] == [7]


def test_templates_suggest_stakeholders():
    d = json.loads((ROOT / "eax" / "seed" / "project_templates.json").read_text(encoding="utf-8"))["templates"]
    assert len(d) == 14 and all(t.get("stakeholders") for t in d)
    for t in d:
        for s in t["stakeholders"]:
            assert s["category"] in sh.CATEGORIES and s["power"] in "HML" and s["interest"] in "HML"
    assert sh.suggestions({"stakeholders": [{"name": "A", "power": "H"}, {"name": ""}]}) == [{"name": "A", "power": "H"}]
    from eax import project_templates as pt
    assert "Stakeholders" in pt.STEPS and "sh.suggestions(s)" in inspect.getsource(pt.clean_spec)


def test_wired_in():
    assert "sh.from_wizard(" in inspect.getsource(pj.create)
    assert 'out["stakeholders"]' in inspect.getsource(pj.detail) and 'out["completion"]' in inspect.getsource(pj.detail)
    assert [t for t, _w, _m in pb.TABLES].index("stakeholder_notes") > [t for t, _w, _m in pb.TABLES].index("stakeholders")
    assert {"stakeholders", "stakeholder_notes"} <= pb.NEW_GUID
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for r in ('"/projects/<string:project>/stakeholders"', '"/projects/<string:project>/stakeholders/<string:sid>"',
              '"/projects/<string:project>/stakeholders/<string:sid>/notes"', '"/projects/<string:project>/stakeholder-notes/<string:nid>"'):
        assert r in api
    sql = (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()
    assert "CREATE TABLE proj.stakeholders" in sql and "CREATE TABLE proj.stakeholder_notes" in sql
    js = (WEB / "Projects.jsx").read_text()
    assert '"Sponsor", "Stakeholders"' in js and "<StakeholderMatrix p={p} />" in js and "stakeholders: (s.stakeholders || [])" in js
    mcp = (ROOT / "eax" / "mcp_build.py").read_text()
    for t in ("def list_stakeholders", "def save_stakeholder", "def note_stakeholder_discussion"):
        assert t in mcp


def test_completion_and_steps():
    src = inspect.getsource(pj.completion)
    # phases marked complete only (owner, 8 Nov 2026): documents do not count
    assert "proj.phase_states" in src and "proj.documents" not in src and "completed_at" in src
    ms = inspect.getsource(pj.mark_step)
    assert "_settle_step" not in ms and "the step itself is marked done on its own" in ms
    assert "SET done_at = NULL, done_by = NULL WHERE id = :s" in inspect.getsource(pj.add_substep)
    js = (WEB / "Projects.jsx").read_text()
    assert "export function Completion" in js and "useWhileBuilding" in js
    assert 'setPart("steps")' in js and 'setPart("documents")' in js and 'setPart("views")' in js
