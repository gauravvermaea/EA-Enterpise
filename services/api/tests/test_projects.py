"""Phase 13 (D258 to D264): architecture projects, the project library and the repository in Mayan (no database needed)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eax import mayan
from eax import permissions as perms
from eax import projects as pj
from eax.metamodel_edit import EditError
from eax.seed import project_library as pl

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def _user(name="someone", roles=()):
    return SimpleNamespace(username=name, roles=set(roles))


def test_migration_and_version():
    sql = (ROOT / "migrations" / "sql" / "0022_projects.sql").read_text()
    assert "'0.14.0'" in sql and "CREATE SCHEMA IF NOT EXISTS proj" in sql
    for table in ("lib_purposes", "lib_phases", "lib_steps", "lib_items", "lib_item_sources", "lib_folders", "lib_templates",
                  "lib_principles", "projects", "members", "signoff", "project_models", "project_viewpoints", "principles",
                  "steps", "items", "folders", "documents", "document_events", "template_libraries", "template_library_uploads",
                  "project_libraries", "template_setup"):
        assert f"CREATE TABLE proj.{table}" in sql, table
    assert "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()       # no logic in the database (D248)
    assert "REFERENCES core" not in sql                                         # proj can move to its own database (D266)
    ver = (ROOT / "migrations" / "versions" / "0022_projects.py").read_text()
    assert 'down_revision = "0021_startup"' in ver
    assert __import__("re").search(r'version = "(0\.1\d|[1-9]\d*)\.', (ROOT / "version.toml").read_text())


def test_the_library_holds_the_reviewed_master_list():
    d = pl.data()
    assert len(d["phases"]) == 13 and len(d["steps"]) == 116
    assert len(d["items"]) == 171 and len(d["folders"]) == 51
    assert len([t for t in d["templates"] if t["source"] == "TOGAF 10"]) == 23
    ids = [i["id"] for i in d["items"]]
    assert len(ids) == len(set(ids))
    phases = {p["code"] for p in d["phases"]}
    for i in d["items"]:
        assert i["kind"] in ("Deliverable", "Artifact") and i["phase"] in phases and i["work"], i["id"]
        assert i["sources"], i["id"]                                  # every item says where it came from
    for s in d["steps"]:
        assert s["phase"] in phases and s["name"]
    assert {(s["phase"], s["name"]) for s in d["steps"]}.__len__() == len(d["steps"])


def test_the_library_seed_only_adds_what_is_missing():
    sql = pl.library_sql()
    assert "DO UPDATE" not in sql                                              # a Super Admin's changes are kept
    assert "WHERE NOT EXISTS (SELECT 1 FROM proj.lib_item_sources" in sql
    assert sql.count("ON CONFLICT (library_id, path) DO NOTHING") == 2        # TOGAF's by name, EA Explorer's own files
    assert "'EA Explorer', 'ea-explorer'" in sql and "'TOGAF 10', 'togaf'" in sql
    assert "Meridian" in pl.sample_principles_sql()
    principles = json.loads((ROOT / "eax" / "seed" / "sample_principles.json").read_text(encoding="utf-8"))["principles"]
    assert len(principles) == 48 and len({p["code"] for p in principles}) == 48


def test_no_togaf_template_file_is_in_the_repository():
    folder = REPO / "library" / "templates" / "togaf"
    ignore = [ln.strip() for ln in (folder / ".gitignore").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert ignore[0] == "*" and set(ignore[1:]) == {"!.gitignore", "!README.md"}     # the licensed files never go to git
    assert "publications.opengroup.org/i094" in (folder / "README.md").read_text()


def test_seeds_and_start_up():
    main = (ROOT / "eax" / "seed" / "__main__.py").read_text()
    assert "library_sql" in main and "sample_principles_sql" in main and "EAX_SEED_SAMPLE" in main
    later = (ROOT / "eax" / "seed" / "later.py").read_text()
    assert "sample_project" in later and "user_project_admin" in later
    compose = (REPO / "docker-compose.yml").read_text()
    assert "${EAX_LIBRARY_DIR:-./library}:/data/library:ro" in compose
    laptop = (REPO / "deploy" / "compose" / "docker-compose.laptop.yml").read_text()
    assert "MAYAN_GUNICORN_WORKERS" in laptop and "3g" in laptop             # Mayan's memory (D263)
    for script in ("eax.ps1", "eax.sh"):
        assert "publications.opengroup.org/i094" in (REPO / script).read_text(encoding="utf-8"), script


def test_routes_are_declared_registered_and_signed_in():
    src = (ROOT / "eax" / "api" / "projects.py").read_text(encoding="utf-8")
    for path in ("/projects", "/projects/library", "/projects/<string:project>", "/projects/<string:project>/people",
                 "/projects/<string:project>/items/<string:item>/choose", "/projects/<string:project>/repository",
                 "/projects/<string:project>/items/<string:item>/documents", "/projects/<string:project>/documents/<string:doc>",
                 "/projects/<string:project>/documents/<string:doc>/checkout", "/projects/<string:project>/documents/<string:doc>/checkin",
                 "/projects/<string:project>/documents/<string:doc>/undo-checkout", "/projects/library/templates/load"):
        assert f'@blp.route("{path}")' in src, path
    for block in src.split("    @blp.doc(security=SECURITY)")[1:]:
        assert "@require_auth(" in block.split("def ")[0], block[:120]
    assert "projects_blp" in (ROOT / "eax" / "app.py").read_text(encoding="utf-8")


def test_projects_need_sign_in(client):
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 401


def test_roles_and_test_users():
    assert set(pj.ROLES) == {"project-admin", "lead-architect", "architect", "model-admin", "model-sub-admin", "stakeholder"}
    assert "stakeholder" not in pj.CONTRIBUTORS and pj.ADMINS <= pj.CONTRIBUTORS
    assert pj.UNDO_CHECKOUT == {"project-admin", "lead-architect", "model-admin"}
    assert set(pj.MODEL_ROLE_FOR) == set(pj.ROLES)
    assert pj.MODEL_ROLE_FOR["stakeholder"] == perms.REPORT_VIEWER                # stakeholders read the models
    assert perms.allowed({perms.SUPER_ADMIN}, "projects.library")
    assert not perms.allowed({perms.USER, perms.MODEL_CREATOR, perms.LIBRARY_ADMIN}, "projects.library")
    assert pj.may_create(_user(roles={perms.USER}))
    users = {u for u, *_ in perms.TEST_USERS}
    assert {"user_project_admin", "user_lead_architect", "user_stakeholder"} <= users
    assert {r for _u, r in perms.PROJECT_TEST_ROLES} == set(pj.ROLES)


@pytest.mark.parametrize(("roles", "what", "ok"), [
    ({"stakeholder"}, "read", True), ({"stakeholder"}, "contribute", False), ({"architect"}, "contribute", True),
    ({"architect"}, "admin", False), ({"lead-architect"}, "admin", True), ({"model-sub-admin"}, "undo", False),
    ({"model-admin"}, "undo", True), (set(), "read", False),
])
def test_project_rules(monkeypatch, roles, what, ok):
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: set(roles))
    p = {"id": 1, "name": "P"}
    if ok:
        assert pj._need(None, p, _user(), what) == roles
    else:
        with pytest.raises(EditError) as exc:
            pj._need(None, p, _user(), what)
        assert exc.value.status == 403


def test_a_super_admin_may_do_everything(monkeypatch):
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: set())
    for what in ("read", "contribute", "admin", "undo"):
        assert "super-admin" in pj._need(None, {"id": 1, "name": "P"}, _user(roles={perms.SUPER_ADMIN}), what)


def test_mayan_multipart_and_switch(monkeypatch):
    body, ctype = mayan._multipart({"label": "A"}, 'x"y.docx', b"DATA")
    boundary = ctype.split("boundary=")[1]
    assert body.startswith(f"--{boundary}".encode()) and body.endswith(f"--{boundary}--\r\n".encode())
    assert b'filename="x\'y.docx"' in body and b"DATA" in body
    monkeypatch.setattr(mayan, "enabled", lambda: False)
    with pytest.raises(mayan.MayanError) as exc:
        mayan.cabinet("x")
    assert exc.value.status == 409
    assert mayan.ping() is False


def test_the_wizard_and_the_library_screen():
    web = REPO / "services" / "web" / "src"
    src = (web / "Projects.jsx").read_text(encoding="utf-8")
    for step in ("Basics", "Template libraries", "Models", "Views", "Principles", "Phase by phase", "People and sign-off", "Review"):
        assert step in src, step
    assert "ProjectLibraryAdmin" in src and "not_for_use" in src
    assert "Project templates</a>" in (web / "Projects.jsx").read_text(encoding="utf-8")   # moved to Project admin (D285)
    assert "#/projects" in (web / "App.jsx").read_text(encoding="utf-8")


def test_ea_explorer_templates_ship_for_every_item():
    """D264: our own library has a file for every deliverable and artifact, none with the sample's name in its text."""
    import re
    import zipfile
    items = {i["id"] for i in pl.data()["items"]}
    ours = pl.ea_explorer_templates()
    assert {t["item"] for t in ours} == items and len(ours) == len(items)
    folder = REPO / "library" / "templates" / "ea-explorer"
    for t in ours:
        f = folder / t["path"]
        assert f.is_file(), t["path"]
        assert t["origin"] in ("Sample, rebranded", "Starter")
        with zipfile.ZipFile(f) as z:
            for part in z.namelist():
                if part.endswith(".xml"):
                    plain = re.sub(r"<[^>]+>", "", z.read(part).decode("utf-8", "ignore"))
                    assert "Meridian" not in plain, (t["path"], part)
    assert "./library/templates/ea-explorer:/data/ea-explorer-templates:ro" in (REPO / "docker-compose.yml").read_text()


def test_library_zip_paths_are_checked():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Org/09_ADM_Phase_Workspaces/A_Vision/Deliverables/x/Vision.docx", b"v")
        z.writestr("Org/__MACOSX/._Vision.docx", b"j")
        z.writestr("Org/.DS_Store", b"j")
        z.writestr("Org/Read me.txt", b"r")
    assert [n for n, _s in pj._zip_entries(buf.getvalue())] == ["Org/09_ADM_Phase_Workspaces/A_Vision/Deliverables/x/Vision.docx"]
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.docx", b"x")
    with pytest.raises(EditError):
        pj._zip_entries(bad.getvalue())
    with pytest.raises(EditError):
        pj._zip_entries(b"not a zip")


def test_template_library_routes_and_rules():
    src = (ROOT / "eax" / "api" / "projects.py").read_text(encoding="utf-8")
    for path in ("/projects/library/setup", "/projects/library/libraries", "/projects/library/libraries/<string:library>/zip",
                 "/projects/library/libraries/<string:library>/share"):
        assert f'@blp.route("{path}")' in src, path
    code = (ROOT / "eax" / "projects.py").read_text(encoding="utf-8")
    assert 'raise EditError("No template library is offered to projects' in code      # the gate before projects
    assert "WHERE shared AND state = 'ready'" in code    # EA Explorer's own, offered from the start, is enough (owner, 7 Nov 2026)
    assert 'f"{t[\'library\']}-{t[\'file_name\'] or t[\'name\']}"' in code                     # library-document names
    jobs = (ROOT / "eax" / "jobs.py").read_text(encoding="utf-8")
    assert "template_library_load" in jobs and "pending_library_loads" in jobs


def test_proj_has_its_own_connection_string(monkeypatch):
    """D266: proj is reached through EAX_PROJECTS_DB_URL and never joined with another schema."""
    import re

    from eax import config
    code = (ROOT / "eax" / "projects.py").read_text(encoding="utf-8")
    for sql in re.findall(r'"""(.*?)"""', code, re.S) + re.findall(r'"(SELECT [^"]*|INSERT [^"]*|UPDATE [^"]*|DELETE [^"]*)"', code):
        assert not ("proj." in sql and re.search(r"\b(core|history|audit|reports)\.", sql)), sql[:120]
    monkeypatch.setenv("EAX_PROJECTS_DB_URL", "postgresql://u:p%5E@other:5432/projects")
    assert config.Settings().projects_sqlalchemy_url == "postgresql+psycopg://u:p%5E@other:5432/projects"
    monkeypatch.setenv("EAX_PROJECTS_DB_URL", "")
    s = config.Settings()
    assert s.projects_sqlalchemy_url == s.sqlalchemy_url
    assert "EAX_PROJECTS_DB_URL=" in (REPO / "deploy" / "templates" / "eaexplorer.server.env").read_text()


def test_togaf_zip_as_downloaded():
    """D264: the TOGAF templates are uploaded as the zip as it is (zips inside it too) and matched by name."""
    import io
    import zipfile
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("Phase A - Architecture Vision/TOGAF® Template - Architecture Vision.docx", b"v")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("I094/Preliminary Phase/TOGAF® Template - Architecture Principles.docx", b"p")
        z.writestr("I094/Phase A.zip", inner.getvalue())
        z.writestr("__MACOSX/._x", b"j")
    files = dict(pj._zip_files(outer.getvalue()))
    assert set(files) == {"I094/Preliminary Phase/TOGAF® Template - Architecture Principles.docx",
                          "I094/Phase A/Phase A - Architecture Vision/TOGAF® Template - Architecture Vision.docx"}
    temps = [{"name": "TOGAF® Template - Architecture Definition.docx", "folder": "x/Phase C - Information Systems Architecture"},
             {"name": "TOGAF® Template - Architecture Definition.docx", "folder": "x/Phase D - Technology Architecture"},
             {"name": "TOGAF® Template - Architecture Vision.docx", "folder": "x/Phase A - Architecture Vision"}]
    assert pj._togaf_match(temps, "TOGAF® Template - Architecture Vision.docx", "") == [temps[2]]
    assert pj._togaf_match(temps, "TOGAF® Template - Architecture Definition.docx", "Phase D - Technology Architecture") == [temps[1]]
    src = (ROOT / "eax" / "api" / "projects.py").read_text(encoding="utf-8")
    assert "pj.add_library_zip" in src
    web = (REPO / "services" / "web" / "src")
    assert "Upload the TOGAF zip" in (web / "Projects.jsx").read_text(encoding="utf-8")
    assert "Set up architecture projects" in (web / "StartPage.jsx").read_text(encoding="utf-8")


def test_steps_and_template_downloads(monkeypatch):
    """Steps are ticked done, or not done again, by any contributor (D275); templates download straight from the libraries."""
    monkeypatch.setattr(pj, "project_row", lambda conn, p: {"id": 1, "name": "P"})
    calls = []

    class Conn:
        def execute(self, sql, params=None):
            calls.append(params)

    # the step itself; it has no sub steps yet (owner, 7 Nov 2026: completions become sub steps)
    monkeypatch.setattr(pj, "_one", lambda conn, sql, **k: None if "parent_step_id = :s" in sql else
                        {"id": 5, "name": "Agree scope", "removed": False, "done_at": "x", "cycle": 1, "phase": "A", "parent_step_id": None})
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: {"architect"})
    monkeypatch.setattr(pj._iter, "guard", lambda conn, p, phase: None)      # a Full cycle (D571-D574)
    assert pj.mark_step(Conn(), "P", _user(), 5, False)["done"] is False     # an architect reopens too (D275)
    assert pj.mark_step(Conn(), "P", _user(), 5, True)["done"]
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: {"stakeholder"})
    with pytest.raises(EditError):
        pj.mark_step(Conn(), "P", _user(), 5, True)             # a stakeholder does not contribute
    monkeypatch.setattr(pj, "my_roles", lambda conn, p, user: {"lead-architect"})
    assert pj.mark_step(Conn(), "P", _user(), 5, False)["done"] is False
    src = (ROOT / "eax" / "api" / "projects.py").read_text(encoding="utf-8")
    assert '"/projects/<string:project>/steps/<int:step>/done"' in src and '"/projects/<string:project>/templates/<int:template>"' in src


def test_togaf_folder_loads_itself(monkeypatch, tmp_path):
    """The TOGAF folder on disk is loaded again by the minute job after a clean restart (no git, no hand work)."""
    folder = tmp_path / "templates" / "togaf" / "Phase A - Architecture Vision"
    folder.mkdir(parents=True)
    (folder / "TOGAF® Template - Architecture Vision.docx").write_bytes(b"v")
    monkeypatch.setattr(pj, "LIBRARY_DIR", tmp_path)
    waiting = [{"id": 1, "name": "TOGAF® Template - Architecture Vision.docx", "folder": "x/Phase A - Architecture Vision",
                "mayan_document_id": None}]
    monkeypatch.setattr(pj, "_rows", lambda conn, sql, **k: waiting)
    assert pj.togaf_files_waiting(None)
    monkeypatch.setattr(pj, "_rows", lambda conn, sql, **k: [])
    assert not pj.togaf_files_waiting(None)
    assert "togaf_files_waiting" in (ROOT / "eax" / "jobs.py").read_text(encoding="utf-8")
