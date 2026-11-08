"""Phase 13.0.7 (D299): the content framework on each project."""

import json
import re
from pathlib import Path

import pytest

from eax import content_framework as cf
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_the_screen_and_the_server_have_the_same_areas():
    js = (WEB / "cfAreas.js").read_text()
    rows = re.findall(r'\["([a-z_.]+)", "([^"]+)", "([^"]+)", "([^"]+)"\]', js)
    assert rows == [tuple(a) for a in cf.AREAS]
    assert len(cf.AREAS) == 37 and len(set(cf.LABEL)) == 37


def test_no_objective_in_the_labels():
    assert not any("objective" in label.lower() for _c, label, _s, _g in cf.AREAS)


def test_the_default_map_only_uses_known_areas():
    m = json.loads((ROOT / "eax" / "seed" / "content_framework_map.json").read_text(encoding="utf-8"))
    for section in ("entity_types", "document_types"):
        assert all(v in cf.LABEL for v in m[section].values()), section
    lib = json.loads((ROOT / "eax" / "seed" / "project_library.json").read_text(encoding="utf-8"))
    names = {i["name"] for i in lib["items"]}
    assert set(m["document_types"]) <= names                     # no stale names
    assert len(m["document_types"]) >= 150


def test_shipped_entity_types_are_placed():
    for code in ("ApplicationComponent", "Capability", "ValueStream", "DataObject", "Node", "WorkPackage", "Goal", "Outcome",
                 "Driver", "Principle", "Requirement", "Stakeholder", "BusinessActor", "Process", "Application", "DataEntity", "Platform"):
        assert cf.area_of_type(code, "")[0], code
    assert cf.area_of_type("ApplicationComponent", "Application Component") == (["app.logical_components"], False)
    assert cf.area_of_type("x", "Application Component") == (["app.logical_components"], False)      # by name too
    assert cf.area_of_type("ApplicationComponent", "", "tech.services") == (["tech.services"], True)  # its own choice wins
    assert cf.area_of_type("Grouping", "Grouping") == ([], False)


def test_document_types_by_choice_library_or_default():
    assert cf.area_of_item("Architecture Contract") == (["real.contracts"], False)
    assert cf.area_of_item("Architecture Contract", library="gov.standards") == (["gov.standards"], False)
    assert cf.area_of_item("Architecture Contract", "req.gaps", "gov.standards") == (["req.gaps"], True)


def test_areas_are_checked():
    assert cf.clean_area("") == ""
    assert cf.clean_area(" gov.guidelines ") == "gov.guidelines"
    with pytest.raises(EditError):
        cf.clean_area("nope")


def test_migration_and_wiring():
    sql = (ROOT / "migrations" / "sql" / "0029_content_framework.sql").read_text()
    for t in ("core.entity_types", "proj.lib_items", "proj.items", "proj.documents"):
        assert f"ALTER TABLE {t} ADD COLUMN content_area" in sql
    assert "'0.14.7'" in sql
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/<string:project>/content-framework/<string:area>"' in api
    assert "content_area" in (ROOT / "eax" / "metamodel_edit.py").read_text()
    assert "content_area" in (ROOT / "eax" / "model_ops.py").read_text()
    s = (WEB / "Projects.jsx").read_text()
    assert '["content", "Content framework"]' in s and "<ContentFrameworkTab p={p} />" in s and "repo-hl" in s
    assert "Content framework area" in (WEB / "MetamodelEditor.jsx").read_text()


def test_no_two_web_files_differ_only_by_case():
    stems = [f.stem.lower() for f in WEB.iterdir() if f.is_file()]
    assert len(stems) == len(set(stems)), "two files differ only by case or extension: imports break on Windows"


def test_project_organisation_and_stakeholders_into_the_architecture():
    sql = (ROOT / "migrations" / "sql" / "0029_content_framework.sql").read_text()
    assert "CREATE TABLE proj.org_people" in sql and "stakeholder_id bigint REFERENCES proj.stakeholders" in sql
    assert "ADD COLUMN entity_guid uuid, ADD COLUMN entity_model uuid" in sql
    from eax import project_backup as pb
    from eax import project_org as po
    assert ("org_people", "project_id = :p", {"stakeholder_id": "stakeholders"}) in pb.TABLES
    assert "Lead Architect" in po.ROLES
    sh = (ROOT / "eax" / "stakeholders.py").read_text()
    assert "def to_model" in sh and '"Stakeholder"' in sh
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/<string:project>/organisation"' in api and '"/projects/<string:project>/stakeholders/to-model"' in api
    s = (WEB / "Projects.jsx").read_text()
    assert '["organisation", "Organisation"]' in s and '["archrepo", "Enterprise Repository (Project Scope)"]' in s


def test_architecture_repository_top_level():
    app = (WEB / "App.jsx").read_text()
    assert '"#/repository"' in app and "<ArchitectureRepositoryPage />" in app
    assert 'key: "repository"' in (WEB / "Areas.jsx").read_text()


def test_several_areas_per_thing():
    """One entity type, document type or document may sit in several areas (D309): stored joined by commas, in the
    order of the framework, without repeats; unknown codes refused."""
    assert cf.clean_area(["app.services", "data.entities", "app.services"]) == "data.entities,app.services"
    assert cf.clean_area("app.services, data.entities") == "data.entities,app.services"
    assert cf.clean_area([]) == "" and cf.clean_area("") == ""
    assert cf.areas_of("data.entities,app.services") == ["data.entities", "app.services"]
    assert cf.area_of_type("x", "y", "data.entities,app.services") == (["data.entities", "app.services"], True)
    try:
        cf.clean_area(["data.entities", "nope"])
        raise AssertionError("an unknown area is refused")
    except cf.EditError:
        pass
    js = (ROOT.parent / "web/src/CfAreaPicker.jsx").read_text(encoding="utf-8")
    assert "export function AreaPicker" in js and "export function AreaChecks" in js


def test_wizard_documents_table():
    """The wizard's documents per phase (owner, 8 Nov 2026): Steps and Documents as tabs; a table of the document types
    added (D/A, description, templates with their library, content framework areas); Not added below; templates added
    by browsing the libraries, copied when the repository is built."""
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    for x in ("function PhaseDocuments", "function TemplatesCell", "Templates/documents not in use", "Browse the libraries", "setPart(\"docs\")",
              "notes: d.notes, areas: d.areas", "<WzAreas"):
        assert x in js, x
    src = (ROOT / "eax/projects.py").read_text(encoding="utf-8")
    for x in ("def own_item_fields", "def template_index", "_project_templates_by_id", "cand += [by_id[x]"):
        assert x in src, x
    from eax import projects as pj
    assert pj.own_item_fields({"templates": [3, "4"], "areas": ["gov.standards"], "note": " x "}) == {
        "note": "x", "content_area": "gov.standards", "templates": [3, 4], "placeholder": False}
    assert pj.own_item_fields({"templates": []})["placeholder"] is True


def test_documents_from_templates():
    """A class's documents made from templates (owner, 8 Nov 2026): several at once, the same template more than once;
    the sample projects have classes with several templates and a class of their own made from three."""
    src = (ROOT / "eax/projects.py").read_text(encoding="utf-8")
    assert "def from_templates" in src and "'made from a template'" not in src.replace('"made from a template"', "")
    api = (ROOT / "eax/api/projects.py").read_text(encoding="utf-8")
    assert "/documents/from-templates" in api
    js = (ROOT.parent / "web/src/Projects.jsx").read_text(encoding="utf-8")
    assert "From templates (one or several)" in js and "＋ again" in js and "/documents/from-templates" in js
    seed = (ROOT / "eax/seed/sample_projects.py").read_text(encoding="utf-8")
    assert "def _several_templates" in seed and "**_several_templates(conn, items)" in seed
