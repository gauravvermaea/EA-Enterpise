"""The Users page shows each person's projects with their roles as well as their models (R3.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _access():
    flask = pytest.importorskip("flask")
    if not hasattr(flask, "Flask"):
        pytest.skip("needs the real Flask")
    from eax.api import access
    return access


def test_project_roles_grouped_by_person_and_project_highest_first():
    access = _access()
    rows = [{"username": "Ann", "guid": "p2", "name": "Zeta", "role": "stakeholder"},
            {"username": "ann", "guid": "p2", "name": "Zeta", "role": "project-admin"},
            {"username": "ann", "guid": "p1", "name": "alpha", "role": "architect"},
            {"username": "ann", "guid": "p1", "name": "alpha", "role": "architect"},
            {"username": "bob", "guid": "p1", "name": "alpha", "role": "odd-role"}]
    out = access.project_roles(rows)
    assert [x["name"] for x in out["ann"]] == ["alpha", "Zeta"]                 # by name, case ignored
    assert out["ann"][1] == {"id": "p2", "name": "Zeta", "roles": ["project-admin", "stakeholder"], "role": "project-admin"}
    assert out["ann"][0]["roles"] == ["architect"]                             # a role once
    assert out["bob"][0]["role"] == "odd-role" and access.project_roles([]) == {}


def test_people_carry_their_projects_and_tolerate_no_projects_database(monkeypatch):
    access = _access()
    from eax import projects as pj

    def broken(write=True):
        raise RuntimeError("no projects database")
    monkeypatch.setattr(pj, "connections", broken)
    assert access._project_rows() == []
    src = (REPO / "services/api/eax/api/access.py").read_text()
    assert '"projects": on_projects.get(str(p["username"]).lower(), [])' in src
    assert "projects = fields.List(fields.Dict()" in src


def test_the_page_shows_two_lists_in_columns_and_the_csv_has_projects():
    page = (REPO / "services/web/src/Users.jsx").read_text()
    assert "<th>Projects and roles</th><th>Models and roles</th>" in page
    assert "<RoleList items={p.projects}" in page and "<RoleList items={p.models}" in page
    assert '"Keycloak roles", "Projects", "Models"]' in page
    for role in ("Project Admin", "Lead Architect", "Model Sub Admin", "Stakeholder"):
        assert role in page
    assert "<details" not in page and "Tree" not in page   # no tree: plain lists
