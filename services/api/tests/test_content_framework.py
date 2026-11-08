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
    sample_own = {"Capability Heat Map", "Sponsor brief"}            # classes of the sample projects' own (D318: all placed)
    assert set(m["document_types"]) <= names | sample_own        # no stale names
    assert len(m["document_types"]) >= 150


def test_shipped_entity_types_are_placed():
    for code in ("ApplicationComponent", "Capability", "ValueStream", "DataObject", "Node", "WorkPackage", "Goal", "Outcome",
                 "Driver", "Principle", "Requirement", "Stakeholder", "BusinessActor", "Process", "Application", "DataEntity", "Platform"):
        assert cf.area_of_type(code, "")[0], code
    assert cf.area_of_type("ApplicationComponent", "Application Component") == (["app.logical_components"], False)
    assert cf.area_of_type("x", "Application Component") == (["app.logical_components"], False)      # by name too
    assert cf.area_of_type("ApplicationComponent", "", "tech.services") == (["tech.services"], True)  # its own choice wins
    assert cf.area_of_type("Grouping", "Grouping") == (["gov.specifications"], False)      # defaults for every type (D317)
    assert cf.area_of_type("NoSuchType", "No such type") == ([], False)


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


def test_tag_items_wiring():
    """D317: Tag items lists the project's classes, documents, entity types and entities; places many at once, per project."""
    assert cf.KINDS == ("classes", "documents", "types", "entities")
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for t in ("proj.cf_type_areas", "proj.cf_entity_areas"):
        assert f"CREATE TABLE {t}" in sql
    assert '"cf_type_areas"' in (ROOT / "eax" / "project_backup.py").read_text()
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/<string:project>/cf-tags"' in api and "cf.place(" in api and "cf.tag_list(" in api
    s = (WEB / "ContentFramework.jsx").read_text()
    for w in ("🏷 Tag items", "＋ Add area to ticked…", "− Take area off ticked…", "＋ Tag more items here", "own_entities", "/cf-tags"):
        assert w in s


def test_place_checks_before_touching_anything():
    class P(dict):
        pass
    import eax.projects as pj
    calls = []
    orig = pj.project_row, pj._need
    pj.project_row = lambda c, p: {"id": 1, "name": "x"}
    pj._need = lambda c, p, u, w: calls.append(w)
    try:
        for kind, ids, how, areas, msg in (("nope", ["a"], "add", ["prelim.principles"], "Tag deliverables"),
                                            ("classes", ["a"], "swap", [], "Set, add"),
                                            ("classes", [], "add", ["prelim.principles"], "Tick at least"),
                                            ("classes", ["a"], "add", [], "Choose the area")):
            with pytest.raises(EditError, match=msg):
                cf.place(None, "p", None, kind, ids, how, areas)
        with pytest.raises(EditError, match="1000"):
            cf.place(None, "p", None, "classes", [str(i) for i in range(1001)], "reset")
    finally:
        pj.project_row, pj._need = orig
    assert calls and set(calls) == {"contribute"}


def test_defaults_set_by_admins_and_inherited():
    """D317: built-in, then the admin's (library item, template, entity type, entity), then a parent project's, then the project's."""
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for x in ("ALTER TABLE proj.lib_templates ADD COLUMN content_area", "ALTER TABLE core.entities ADD COLUMN content_area",
              "ALTER TABLE proj.cf_type_areas ADD COLUMN type_code"):
        assert x in sql
    src = (ROOT / "eax" / "content_framework.py").read_text()
    for x in ("def _bases(", "def _type_parent(", "def _ent_parent(", "def _entities_off_type(", "def _tpl(", "def template_setup(",
              "def place_library_template(", "def add_template("):
        assert x in src
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for x in ('"/projects/library/template-setup"', '"/projects/library/templates/<int:template_id>/content-area"',
              '"/projects/library/libraries/<string:library>/templates"'):
        assert x in api
    assert '"content_areas" in data' in (ROOT / "eax" / "content.py").read_text()
    assert "SET content_area = s.content_area" in (ROOT / "eax" / "model_ops.py").read_text()
    web = (WEB / "TemplateSetup.jsx").read_text()
    assert "⬆ Upload a template…" in web and "class_areas" in web
    assert "<TemplateSetup />" in (WEB / "Projects.jsx").read_text()
    assert "content_areas" in (WEB / "DataEntry.jsx").read_text()
    assert "cf-plus" in (WEB / "ContentFramework.jsx").read_text()


def test_repository_area_is_on_the_type_and_the_class():
    """D318: the Repository Area is set on the entity type and the document class, with built-in defaults; not on each entity."""
    src = (ROOT / "eax" / "seed" / "build.py").read_text()
    assert '("RepositoryArea", "N", "Repository")' not in src and "'attr:RepositoryArea'" not in src
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    assert "ALTER TABLE core.entity_types ADD COLUMN repository_area" in sql and "ALTER TABLE proj.lib_items ADD COLUMN repository_area" in sql
    assert cf.repo_of_type("Principle", "Principle") == ("Architecture Capability", False)
    assert cf.repo_of_type("Requirement", "Requirement")[0] == "Architecture Requirements Repository"
    assert cf.repo_of_type("ApplicationComponent", "Application Component")[0] == "Architecture Landscape"
    assert cf.repo_of_type("ApplicationComponent", "Application Component", "Solutions Landscape") == ("Solutions Landscape", True)
    assert cf.repo_of_item("Architecture Contract")[0] == "Governance Log"
    assert cf.repo_of_item("Standards Library")[0] == "Standards Information Base"
    assert cf.repo_of_item("Requirements catalog")[0] == "Architecture Requirements Repository"
    assert cf.repo_of_item("Architecture Principles")[0] == "Architecture Capability"
    with pytest.raises(EditError):
        cf.clean_repo("Somewhere")
    m = json.loads((ROOT / "eax" / "seed" / "repository_area_map.json").read_text())
    assert set(m["document_types"].values()) | set(m["entity_types"].values()) <= set(cf.REPO_AREAS)


def test_org_repository_views():
    """D318: the organisation's map opens existing screens; decisions, assessments and people are read only across the
    projects a person is on."""
    from eax import governance
    from eax import org_repository as orp
    assert "Capability assessment" in governance.KINDS
    assert set(orp.GOV_KINDS) == {"decisions", "compliance", "capability"}
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for x in ('"/repository/governance/<string:kind>"', '"/repository/people"', '"/repository/model-levels"', '"/repository/summary"'):
        assert x in api
    web = (WEB / "ArchitectureRepository.jsx").read_text()
    for x in ("#/repository/decisions", "#/library?kind=reference", "#/admin/users", "view=tiles&level=strategic", "choose:"):
        assert x in web
    assert "ModelsByLevel" in (WEB / "Areas.jsx").read_text()


def test_org_charter_seeded():
    """D319: the organisation-wide charter in the Organisation base, filled in by the seed; the TOGAF 10 project keeps the guidance."""
    b = json.loads((ROOT / "eax" / "seed" / "project_bases.json").read_text(encoding="utf-8"))
    assert [c["key"] for c in b["org_charter"]] == [c["key"] for c in b["charter"]]
    assert all(len(c["html"]) > 200 for c in b["org_charter"])
    assert '(ORG_GUID, "org_charter")' in (ROOT / "eax" / "project_bases.py").read_text()
    assert "OrgCharterCard" in (WEB / "Projects.jsx").read_text()


def test_admins_see_everything_outside_a_project():
    """D320: outside a project admins see every project and every user; inside a project, the project."""
    from eax import org_repository as orp

    class U:
        def __init__(self, roles):
            self.roles, self.username = roles, "x"
    assert orp.may_see_all_users(U(["super-admin"])) and orp.may_see_all_users(U(["user-admin"]))
    assert not orp.may_see_all_users(U(["user"]))
    web = (WEB / "ArchitectureRepository.jsx").read_text()
    assert "function AllUsers" in web and "/api/v1/people" in web and "archrepo" in web


def test_calendars_and_repository_parts():
    """D324: calendars (repeats, skips, iCalendar), the board, measures, the reference library's parts."""
    from datetime import date

    from eax import calendars as cl
    from eax import org_repository as orp
    ev = {"starts_on": date(2026, 11, 2), "repeat": "weekly", "weekdays": [0, 3], "times": 4, "until_on": None, "skipped": [date(2026, 11, 5)]}
    assert cl.occurrences(ev, date(2026, 11, 1), date(2026, 12, 31)) == [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 12)]
    m = {"starts_on": date(2026, 1, 31), "repeat": "monthly", "until_on": date(2026, 6, 30), "times": None, "skipped": []}
    assert cl.occurrences(m, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]
    once = {"starts_on": date(2026, 11, 9), "repeat": "none", "until_on": None, "times": None, "skipped": []}
    assert cl.occurrences(once, date(2026, 11, 1), date(2026, 11, 30)) == [date(2026, 11, 9)]
    with pytest.raises(EditError):
        cl._vals({"topic": "", "starts_on": "2026-11-09"})
    body = cl.ics(None, "org", "Org", [{"id": "x", "topic": "Board, monthly", "starts_on": date(2026, 11, 12), "at_time": None, "minutes": 60, "notes": "",
                                        "repeat": "weekly", "weekdays": [0], "until_on": None, "times": 3, "skipped": []}])
    assert "BEGIN:VCALENDAR" in body and "SUMMARY:Board\\, monthly" in body and "RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=3" in body
    assert set(orp.REF_PARTS) == {"foundation", "common", "industry", "own"}
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for x in ("CREATE TABLE proj.cal_events", "CREATE TABLE proj.cal_feeds", "CREATE TABLE proj.board_members", "'Foundation architectures'"):
        assert x in sql
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for x in ('"/calendars/<string:cal>"', '"/calendar-feed/<string:token>.ics"', '"/repository/board"', '"/repository/measures/<string:what>"'):
        assert x in api
    web = (WEB / "ArchitectureRepository.jsx").read_text()
    for x in ("#/repository/calendar", "#/repository/board", "#/repository/measures", "#/repository/reference/foundation", "standards?group=Business"):
        assert x in web
    assert "<CalendarView cal={p.id} />" in (WEB / "Projects.jsx").read_text()


def test_tracking_sheets_and_sample_content():
    """D325, D326."""
    from eax import tracking_sheets as ts
    cols, rows = ts.read_file("x.csv", b"Application,Cost\nClaims,10\n,\nBilling,5\n")
    assert cols == ["Application", "Cost"] and rows == [{"Application": "Claims", "Cost": "10"}, {"Application": "Billing", "Cost": "5"}]
    assert ts._cols(["A", "A", "", None]) == ["A", "A (2)", "Column 3", "Column 4"]
    assert ts._cell(1200.0) == "1200" and ts._cell(None) == ""
    with pytest.raises(EditError):
        ts.read_file("x.txt", b"a")
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    assert "CREATE TABLE proj.sheets" in sql and "CREATE TABLE proj.sheet_rows" in sql
    assert (ROOT / "eax" / "sheets.py").read_text().startswith('"""Import and export sheets')      # phase 10.1 untouched
    later = (ROOT / "eax" / "seed" / "later.py").read_text()
    assert "sample_content" in later
    sc = (ROOT / "eax" / "seed" / "sample_content.py").read_text()
    for x in ("send_for_approval", "approve_with_evidence", '"rejected"', "board_set", "cl.add", "ts.create", "add_link"):
        assert x in sc
    assert "<TrackingSheets scope={p.id} />" in (WEB / "Projects.jsx").read_text()
