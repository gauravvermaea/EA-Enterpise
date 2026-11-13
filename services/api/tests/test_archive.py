"""R2.41 (D626; owner, 12 Nov 2026, answers 21:20): models move out of the working database into the archive database
whole (their backup file), and back. Checked on PostgreSQL on 13 Nov 2026, with the archive in the same database and in
a database of its own: a model with 1,700 entities archived (gone from the working database, its row in the archive),
brought back with its entities, deleted, refused to someone else, purged; and the laptop sample data made once."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


class _User:
    def __init__(self, name, roles):
        self.username, self.roles = name, roles


def test_who_may_move_what(monkeypatch):
    from eax import archive as ar
    from eax import permissions as perms
    from eax.metamodel_edit import EditError
    m = {"id": "g", "name": "M", "kind": "project"}
    monkeypatch.setattr(perms, "model_roles", lambda conn, u, mid: ["model-admin"] if u == "admin" else [])
    ar._may_move(None, _User("admin", ["user"]), m, "archived")                         # its Model Admin archives
    for user, state in ((_User("admin", ["user"]), "deleted"), (_User("other", ["user"]), "archived")):
        with pytest.raises(EditError):
            ar._may_move(None, user, m, state)                                          # only a Super Admin deletes
    ar._may_move(None, _User("su", ["super-admin"]), m, "deleted")
    with pytest.raises(EditError):
        ar._may_move(None, _User("su", ["super-admin"]), {**m, "kind": "reference"}, "archived")   # library models stay


def test_the_move_is_whole_and_refused_while_referred_to():
    from eax import archive as ar
    src = inspect.getsource(ar.move_model)
    assert 'refs["blocking"]' in src and "bk.model_file(" in src and "_purge_models(" in src
    assert src.index("bk.model_file(") < src.index("INSERT INTO archive.archive_store") < src.index("_purge_models(")
    back = inspect.getsource(ar.bring_back)
    assert 'r["state"] == "deleted" and not _is_super(user)' in back and "DELETE FROM archive.archive_store" in back
    assert "Only a Super Admin purges" in inspect.getsource(ar.purge)
    listing = inspect.getsource(ar.listing)
    assert "include_deleted and _is_super(user)" in listing                             # deleted: Super Admins only


def test_the_archive_database_and_the_wiring():
    from eax import databases as dbs
    assert dbs.TABLES["archive"] == ("archive.archive_store",)
    assert (REPO / "services/api/migrations/sql/0053_archive_store.sql").is_file()
    bg = (REPO / "services/api/eax/background.py").read_text()
    assert '"archive.move": archive_move' in bg and '"archive.restore": archive_restore' in bg
    api = (REPO / "services/api/eax/api/archive.py").read_text()
    for r in ("/models/<model_id>/archive/references", "/models/<model_id>/archive", "/archive", "/archive/<int:ident>/restore",
              "/archive/<int:ident>/purge", "/archive/<int:ident>/download"):
        assert f'@blp.route("{r}")' in api, r
    assert "archive_blp" in (REPO / "services/api/eax/app.py").read_text()
    web = (REPO / "services/web/src/ModelAdmin.jsx").read_text()
    assert 'k: "archive-db", title: "Move to the archive"' in web and "<MoveToArchiveDialog" in web
    assert '"#/archive"' in (REPO / "services/web/src/menu.js").read_text()
    assert '("Sample archive: a model archived and one deleted, a project archived", sample_archive)' in (REPO / "services/api/eax/seed/later.py").read_text()


def test_a_project_moves_with_only_its_own_models():
    """R2.41 part 2 (D628): checked on PostgreSQL on 13 Nov 2026: a project with a model it created archived (both gone
    from the working databases, one archive row holding both), brought back as a project with its model and its Project
    Admin, archived again."""
    from eax import archive as ar
    refs = inspect.getsource(ar.project_references)
    assert '"created", "derived"' in refs and "not others" in refs and 'm["children"]' in refs and '"project"' in refs
    src = inspect.getsource(ar.move_project)
    assert src.index("pb.project_file(") < src.index("INSERT INTO archive.archive_store") < src.index("DELETE FROM proj.projects") \
        < src.index("_purge_models(")
    assert "need_manage" in src and "Only a Super Admin deletes a project" in src
    back = inspect.getsource(ar.bring_back_project)
    assert "pb.restore(" in back and "project-admin" in back and "DELETE FROM archive.archive_store" in back
    assert 'r["kind"] != "model"' in inspect.getsource(ar.bring_back)        # a project is not brought back as a model


def test_project_routes_tasks_page_and_sample():
    from eax import background
    assert {"archive.project_move", "archive.restore"} <= set(background.WORK) & set(background.KINDS)
    api = (REPO / "services/api/eax/api/archive.py").read_text()
    assert "/projects/<project_id>/archive/references" in api and '"archive.project_move"' in api and '"kind": r["kind"]' in api
    rest = inspect.getsource(background.archive_restore)
    assert 'get("kind") == "project"' in rest and "bring_back_project" in rest
    web = (REPO / "services/web/src/Archive.jsx").read_text()
    assert "MoveProjectToArchiveDialog" in web and "kind=${kind}" in web
    assert "MoveProjectToArchiveDialog" in (REPO / "services/web/src/ProjectTabs.jsx").read_text()
    sample = (REPO / "services/api/eax/seed/sample_archive.py").read_text()
    assert "sample archived project" in sample and "move_project(" in sample


def test_a_model_you_may_not_read_is_404_not_a_server_error():
    """Full self-test, 13 Nov 2026: GET /models/{id}/archive/references answered 500 "NotFound" to IT Admin, Model
    Creator, Library Admin and a person with no role on the model. A model they may not read is a 404, here and, as a
    safety net, anywhere repository.NotFound is raised."""
    api = (REPO / "services/api/eax/api/archive.py").read_text()
    guard = api[api.index("def _guard("):api.index("@blp.route", api.index("def _guard("))]
    assert "except repo.NotFound as exc:" in guard and "abort(404, message=str(exc))" in guard
    app = (REPO / "services/api/eax/app.py").read_text()
    assert "@app.errorhandler(_NotFound)" in app and '"code": 404' in app
    assert app.index("@app.errorhandler(_NotFound)") < app.index("@app.errorhandler(Exception)")
    try:
        from werkzeug.exceptions import HTTPException

        from eax import repository as repo
        from eax.api import archive as A
    except ImportError as exc:                       # only where Flask is a stub; the test runner has the real one
        pytest.skip(f"needs Flask: {exc}")

    def unreadable(*_a):
        raise repo.NotFound("No model 'x', or you may not read it.")
    with pytest.raises(HTTPException) as got:
        A._guard(unreadable)
    assert got.value.code == 404
