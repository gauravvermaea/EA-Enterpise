"""Phase 13.0.3 (D281, D282): model roles in a project and project templates as wizards."""

import json
from pathlib import Path

import pytest

from eax import project_templates as pt
from eax.metamodel_edit import EditError
from eax.seed import project_library as pl

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_migration():
    sql = (ROOT / "migrations" / "sql" / "0025_project_templates.sql").read_text()
    assert "'0.14.3'" in sql and "proj.project_templates" in sql and "role_seq" in sql and "template_code" in sql
    for r in ("'current'", "'target'", "'transition'", "'scenario'", "'reference'", "'working-copy'"):
        assert r in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA proj TO eax_migrator" in \
        (ROOT / "migrations" / "sql" / "0024_project_setup.sql").read_text()
    assert __import__("re").search(r'version = "(0\.1\d|[1-9]\d*)\.', (ROOT / "version.toml").read_text())


def test_fourteen_templates_ship_and_are_valid():
    ts = json.loads((ROOT / "eax" / "seed" / "project_templates.json").read_text(encoding="utf-8"))["templates"]
    codes = [t["code"] for t in ts]
    assert len(ts) == 14 and len(set(codes)) == 14
    for c in ("transformation", "document-as-is", "new-product", "copy-for-reports", "update-and-merge", "scenario-planning",
              "regulatory-change", "cloud-migration", "app-rationalisation", "operating-model", "capability-planning",
              "health-check", "solution-architecture", "due-diligence"):
        assert c in codes
    for t in ts:
        spec = pt.clean_spec({k: v for k, v in t.items() if k not in ("code", "name", "icon", "description", "sort")})
        assert spec["slots"], t["code"]
        if spec["primary"]:
            assert spec["primary"] in [x["role"] for x in spec["slots"]], t["code"]
        assert not spec["goals"] or spec["primary"], t["code"]
    assert "INSERT INTO proj.project_templates" in pl.library_sql() and "ON CONFLICT (code) DO NOTHING" in pl.library_sql()


def test_spec_is_checked():
    with pytest.raises(EditError):
        pt.clean_spec({"slots": [{"role": "future"}]})
    with pytest.raises(EditError):
        pt.clean_spec({"primary": "dream", "slots": []})
    s = pt.clean_spec({"slots": [{"role": "reference", "starts": ["existing", "bogus"]}], "skip": ["Sponsor", "Nope"]})
    assert s["slots"][0]["how"] == "referred" and s["slots"][0]["starts"] == ["existing"] and s["skip"] == ["Sponsor"]


def test_routes_and_web():
    src = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/templates"' in src and '"/projects/templates/<string:code>"' in src and '"/projects/<string:project>/as-template"' in src
    js = (WEB / "Projects.jsx").read_text()
    for s in ("function Gallery", "function RoleSlots", "function applyTemplate", "Kind of project", "Blank project",
              "function ProjectTemplatesAdmin", "Save as a project template", "Gap analysis"):
        assert s in js
