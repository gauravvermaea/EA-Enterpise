"""Phase 13.0.1 (D274 to D279): setting up and running an architecture project. The rules against a database are checked
by hand (docs/phase-13.0.1.md); here what needs none."""

from pathlib import Path

import pytest

from eax import background as bg
from eax import project_work as pw
from eax import tasks as tk
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_migration():
    sql = (ROOT / "migrations" / "sql" / "0024_project_setup.sql").read_text()
    assert "'0.14.2'" in sql and "'0024_project_setup'" in sql
    for col in ("scope_depth", "scope_domains", "sponsor_asks", "notes_html", "home_model", "pending_goals", "merged_into",
                "placeholder", "templates", "signed_version"):
        assert col in sql
    assert "'referred'" in sql and "'frozen'" in sql and "'merged'" in sql
    assert "proj.signoff_requests" in sql and "proj.signoff_decisions" in sql
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()
    assert 'down_revision = "0023_background"' in (ROOT / "migrations" / "versions" / "0024_project_setup.py").read_text()
    assert 'version = "0.1' in (ROOT / "version.toml").read_text()


def test_rich_text_is_cleaned():
    out = pw.clean_html('<p onclick="x()">Hi <b>there</b><script>alert(1)</script><img src=x onerror=1>'
                        '<a href="javascript:evil()">bad</a><a href="https://example.org">ok</a><style>p{}</style></p>')
    assert out == ('<p>Hi <b>there</b><a>bad</a><a href="https://example.org" rel="noreferrer" target="_blank">ok</a></p>')
    assert pw.clean_html(None) == ""


def test_scope_and_sponsor():
    f = pw.scope_fields({"scope": {"depth": "Segment", "domains": ["business", "nonsense", "data"], "start": "2027-01-01",
                                   "end": "2027-12-31", "breadth": " Claims "},
                         "sponsor": {"name": "Jane", "asks": [{"ask": "A roadmap", "by": "2027-06-30"}, {"ask": "  "}]}})
    assert f["scope_depth"] == "segment" and f["scope_domains"] == ["business", "data"] and f["scope_breadth"] == "Claims"
    assert '"A roadmap"' in f["sponsor_asks"] and f["sponsor_asks"].count("ask") == 1
    with pytest.raises(EditError):
        pw.scope_fields({"scope": {"start": "2027-05-01", "end": "2027-01-01"}})
    with pytest.raises(EditError):
        pw.scope_fields({"scope": {"depth": "galactic"}})


def test_outcome_text_round_trip():
    o = {"description": "Faster", "measure": "median days", "target_date": "2027-12-31"}
    assert pw._split_outcome(pw._outcome_text(o)) == ("Faster", "median days", "2027-12-31")


def test_background_kinds_and_routes():
    for k in ("project.updated", "project.finished"):
        assert k in bg.WORK and tk.KINDS[k]
    src = (ROOT / "eax" / "api" / "projects.py").read_text()
    for route in ('"/projects/<string:project>/files"', '"/projects/<string:project>/documents/<string:doc>/kind"',
                  '"/projects/<string:project>/documents/<string:doc>/signoff"', '"/projects/<string:project>/signoffs/<string:request_id>/decide"',
                  '"/projects/<string:project>/signoffs/<string:request_id>/record"', '"/projects/<string:project>/viewpoints"',
                  '"/projects/<string:project>/finish"'):
        assert route in src
    assert 'start("project.updated"' in src and 'start("project.finished"' in src


def test_frozen_projects_are_read_only(monkeypatch):
    from eax import projects as pj
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: {"project-admin"})
    p = {"id": 1, "name": "P", "status": "frozen"}

    class U:
        username, roles = "a", ("user",)
    assert pj._need(None, p, U(), "read")
    with pytest.raises(EditError):
        pj._need(None, p, U(), "contribute")


def test_web():
    src = (WEB / "Projects.jsx").read_text()
    assert src.index('"Models"') < src.index('"Basics"')     # the wizard starts with the models (owner, 7 Nov 2026)
    for s in ('"Scope"', '"Goals and outcomes"', '"Sponsor"', '"Notes and files"', "function FinishDialog", "function SignoffTab",
              "✎ Edit", "<AdmWheel", "placeholder", "Objective"[:0] + "Outcome"):
        assert s in src
    assert "objective" not in src.lower().replace("objectives", "")   # outcome, not objective (owner, 7 Nov 2026)
    for s in ("function NewModel", "Create empty", "Derive from an existing model", "Derive and keep the parent-child link",
              "function PickModels", "function PrimaryModel", '"Primary working model"'):
        assert s in src                                       # model selection first, the new-model wizard (owner, 7 Nov 2026)
    assert (WEB / "AdmWheel.jsx").exists() and (WEB / "RichText.jsx").exists()


def test_reader_roles_rule():
    src = (ROOT / "eax" / "projects.py").read_text()
    assert "def reader_roles" in src and "project.read_access" in src and "REPORT_VIEWER" in src
