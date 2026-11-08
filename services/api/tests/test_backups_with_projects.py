"""Owner, 7 Nov 2026: the application backup holds every project with its documents and its restore (web and command line)
puts them back over themselves; a project backup on Administration › Backups; the infrastructure backup's Documents."""

import inspect
import json
from pathlib import Path

from eax import backups as bk
from eax import backups_cli as cli
from eax import project_backup as pb

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"
OPS = ROOT.parent / "ops" / "ops.py"


def test_application_backup_has_projects():
    src = inspect.getsource(bk.application_backup)
    assert '"projects": []' in src and "_backup_projects(" in src
    assert "with_models=False" in inspect.getsource(bk._backup_projects)
    assert "_restore_projects(" in inspect.getsource(bk.restore_application)
    assert "over=True" in inspect.getsource(bk._restore_projects)
    assert 'f"projects/{f.name}"' in inspect.getsource(bk.application_zip)
    assert "pfiles" in inspect.getsource(bk.store_application_upload)


def test_project_file_in_application_run(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "app_dir", lambda: tmp_path)
    (tmp_path / "run1" / "projects").mkdir(parents=True)
    (tmp_path / "run1" / "projects" / "p-12345678.eaxproject.zip").write_bytes(b"x")
    assert bk.path_of("application", "run1", "p-12345678.eaxproject.zip").parent.name == "projects"
    for where in ("model", "uploaded"):
        try:
            bk.path_of(where, "run1", "p-12345678.eaxproject.zip", "00000000-0000-0000-0000-000000000000")
            raise AssertionError("refused")
        except Exception as exc:  # noqa: BLE001
            assert "No such backup" in str(exc)


def test_restore_over_and_pending_refill(tmp_path, monkeypatch):
    sig = inspect.signature(pb.restore)
    for k in ("over", "models_over", "model_guids", "uploaded"):
        assert k in sig.parameters
    src = inspect.getsource(pb.restore)
    assert "_delete_rows(pc, live[\"id\"])" in src and "_update(pc, \"projects\"" in src    # its id kept: links with other projects stay
    assert "bk._restore_over(" in src and "current.get(str(r[\"guid\"]))" in src             # the same document, by guid
    assert "hashlib.sha256" in inspect.getsource(pb.refill_documents)       # unchanged files are not sent again
    assert '"http", None) != 404' in inspect.getsource(pb.refill_documents)  # only a 404 means gone
    assert "pb.refill_pending(" in (ROOT / "eax" / "projects.py").read_text()  # every build puts restored documents back
    monkeypatch.setattr(pb, "folder", lambda: tmp_path)

    class C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **k):
            class R:
                def scalar(self):
                    return "g-1"
            return R()
    (tmp_path / "_restoring").mkdir()
    keep = tmp_path / "_restoring" / "g-1-d-1-a.docx"
    keep.write_bytes(b"a")
    (tmp_path / "_restoring" / "g-1.json").write_text(json.dumps({"files": {"d-1": str(keep)}, "trash": [], "evidence": {}}))
    monkeypatch.setattr(pb, "refill_documents", lambda f, p, files: [Path(v).unlink() for v in files.values()] and "1 put back")
    assert pb.refill_pending(lambda: C(), 7) == "1 put back"
    assert not (tmp_path / "_restoring" / "g-1.json").exists()


def test_links_kept_between_installations():
    src = inspect.getsource(pb._links)
    for k in ('"projects"', '"libraries"', '"templates"', '"steps"', '"items"', '"principles"'):
        assert k in src
    assert "_local_libraries" in inspect.getsource(pb.restore) and "_local_projects" in inspect.getsource(pb.restore)
    lib_of = {"libraries": {"1": 10}, "templates": {"5": 50}, "steps": {"3": None}, "items": {}, "principles": {}}
    v = {"library_id": 1}
    assert pb._library_links("project_libraries", v, {"library_id": 1}, lib_of) is False and v["library_id"] == 10
    v = {"library_id": 2}
    assert pb._library_links("project_libraries", v, {"library_id": 2}, lib_of) is True       # not here: the row goes
    v = {"library_id": 3, "templates": [5, 6]}
    pb._library_links("items", v, {"library_id": "X1", "templates": [5, 6]}, lib_of)
    assert v["templates"] == [50] and v["library_id"] is None


def test_command_line_and_screens():
    assert "project_ids" in inspect.getsource(cli.restore_all) and "build_repository" in inspect.getsource(cli.restore_all)
    assert "every project with its documents" in cli.__doc__
    js = (WEB / "Backups.jsx").read_text()
    for s in ("function ProjectSection", "/api/v1/admin/backups/projects", "Put back over itself", "✓ Documents",
              "Back up every model and project now", "r.projects"):
        assert s in js
    api = (ROOT / "eax" / "api" / "backups.py").read_text()
    assert '"/admin/backups/projects"' in api and "pb.list_all(pc)" in api
    ops = OPS.read_text()
    assert '"full": {"config": True, "dbs": None, "files": ["documents", "tls"]' in ops
    assert '"app+data": {"config": True, "dbs": ["mayan"], "files": ["documents"]' in ops
