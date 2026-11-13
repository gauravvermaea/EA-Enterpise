"""Phase 13.0.6 (D296, D297): links and the reference area, the project page layout, sign-off requests sent,
dismiss all, the SQL diagram and Architecture work."""

from pathlib import Path

import pytest

from eax import references as rf
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_a_link_is_a_link():
    assert rf.is_link({"link_url": "https://example.org"})
    assert rf.is_link({"link_project": "x"})
    assert not rf.is_link({"name": "a.docx"})


def test_link_addresses_must_be_web_or_in_app():
    assert rf._url(" https://example.org/a ") == "https://example.org/a"
    assert rf._url("#/projects/1") == "#/projects/1"
    with pytest.raises(EditError):
        rf._url("file:///etc/passwd")
    with pytest.raises(EditError):
        rf._url("javascript:alert(1)")


def test_reference_paths_stay_in_the_reference_area():
    assert rf.clean_path("Papers/2026").startswith(rf.REFERENCE + "/")
    assert rf.clean_path(f"{rf.REFERENCE}/a/../b") == f"{rf.REFERENCE}/a/b"
    assert ".." not in rf.clean_path("../../x")


def test_routes_exist():
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for r in ("/links", "/reference", "/reference/folders", "/library", "/projects/reference-sources", "/templates/<", "/principles"):
        assert r in api
    assert '"/notifications/dismiss-all"' in (ROOT / "eax" / "api" / "notifications.py").read_text()
    assert '"/schema"' in (ROOT / "eax" / "api" / "sql.py").read_text()


def test_architecture_work_has_tabs_views_filters_and_pins():
    s = (WEB / "Areas.jsx").read_text()
    assert "Projects <span" in s and "Models <span" in s
    assert "eax-work-view" in s and "work-tiles" in s and "grid-table" in s
    assert "pinned only" in s and "/api/v1/me/favourites" in s


def test_project_page_layout():
    s = (WEB / "Projects.jsx").read_text()
    assert '["models", "Models"]' in s and '["signoff",' in s
    assert "SignoffLink" in s and "NotSignedOff" in s
    assert "SchemaDiagram" in (WEB / "Sql.jsx").read_text()
    assert "Dismiss all" in (WEB / "Notifications.jsx").read_text()


def test_tasks_are_a_scratchpad():
    from eax import project_backup as pb
    from eax import project_tasks as pt
    assert pt.STANDARD == ("Created", "Open", "To do", "Done", "Not done", "Rejected")
    assert set(pt.FINISHED) <= set(pt.STANDARD)
    assert [t for t, _w, _m in pb.TABLES if "task" in t] == ["task_statuses", "tasks"]
    src = (ROOT / "eax" / "project_tasks.py").read_text()
    assert "UPDATE proj.steps" not in src   # finishing a task never finishes its step
    assert '"/projects/<string:project>/tasks"' in (ROOT / "eax" / "api" / "projects.py").read_text()
    s = (WEB / "Projects.jsx").read_text()
    assert '["tasks", "Tasks"]' in s and "<TasksTab p={p} />" in s
