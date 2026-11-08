"""D329: Projects, Repository and References switched on or off; Projects off takes the other two with it."""
import pytest

from eax import settings as st
from eax.metamodel_edit import EditError


def test_bool_settings_parse():
    assert st.check("part_projects", "off") is False and st.check("part_projects", True) is True
    with pytest.raises(EditError):
        st.check("part_references", "maybe")


def test_projects_off_switches_the_others_off(monkeypatch):
    monkeypatch.setattr(st, "values", lambda conn=None: {"part_projects": False, "part_repository": True, "part_references": True})
    assert st.parts() == {"projects": False, "repository": False, "references": False}
    monkeypatch.setattr(st, "values", lambda conn=None: {"part_projects": True, "part_repository": False, "part_references": True})
    assert st.parts() == {"projects": True, "repository": False, "references": True}


@pytest.mark.parametrize(("path", "on", "want"), [
    ("/api/v1/projects/abc/principles", {"projects": False}, "projects"),
    ("/api/v1/calendars/org", {"projects": False}, "projects"),
    ("/api/v1/repository/governance/DEC", {"repository": False}, "repository"),
    ("/api/v1/repository/summary", {"repository": False}, None),          # the Organisation base's id, for Principles
    ("/api/v1/projects/abc/repo-tags", {"repository": False}, "repository"),
    ("/api/v1/projects/abc/repository", {"repository": False}, None),       # the project's own document store
    ("/api/v1/reference-library/pick", {"references": False}, "references"),
    ("/api/v1/projects/abc/reference/folders", {"references": False}, "references"),
    ("/api/v1/models", {"projects": False, "repository": False, "references": False}, None),
])
def test_paths_of_parts(path, on, want):
    full = {"projects": True, "repository": True, "references": True, **on}
    assert st.part_of_path(path, full) == want
