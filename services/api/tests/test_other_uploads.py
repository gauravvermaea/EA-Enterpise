"""A project's own uploads on Other views and documents (D461). No database needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from eax import other_uploads as ou
from eax import permissions as perms
from eax import projects as pj
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations" / "sql" / "0038_other_uploads.sql").read_text()


def test_migration_adds_only_a_column_and_an_index():
    assert "ADD COLUMN IF NOT EXISTS file_size bigint" in SQL
    assert "ON CONFLICT (version) DO NOTHING" in SQL
    for word in ("TRIGGER", "FUNCTION", "CREATE TABLE"):       # D248: rows only, and nothing new to back up
        assert word not in SQL.upper()
    v = (ROOT / "migrations" / "versions" / "0038_other_uploads.py").read_text()
    assert 'revision = "0038_other_uploads"' in v and 'down_revision = "0037_surveys_maturity"' in v


def test_who_may_replace_and_delete():
    d = {"created_by": "user_architect"}
    me = perms.Principal("user_architect", ("user",))
    other = perms.Principal("user_stakeholder", ("user",))
    sup = perms.Principal("someone", ("super-admin",))
    assert ou._may_change(d, {"architect"}, me)                      # who uploaded it
    assert not ou._may_change(d, {"stakeholder"}, other)             # anyone else on the project: no
    assert ou._may_change(d, {"lead-architect"}, other)              # the Lead Architect
    assert ou._may_change(d, {"project-admin"}, other)               # the Project Admin
    assert ou._may_change(d, set(), sup)                             # a Super Admin


def test_files_are_checked_but_any_type_is_taken():
    assert ou._check_file("plan.vsdx", b"x") == "plan.vsdx"
    assert ou._check_file("a/b\\c.bin", b"x") == "a_b_c.bin"
    with pytest.raises(EditError):
        ou._check_file("empty.txt", b"")
    with pytest.raises(EditError) as e:
        ou._check_file("big.zip", b"x" * (ou.MAX_BYTES + 1))
    assert e.value.status == 413
    assert ou._type_of("Claims volumes.xlsx") == "xlsx" and ou._type_of("README") == "file"


def test_only_members_and_not_when_finished():
    class Conn:
        def execute(self, *a, **k):
            class R:
                def mappings(self):
                    return self

                def all(self):
                    return []
            return R()
    p = {"id": 1, "name": "P", "status": "active"}
    with pytest.raises(EditError) as e:
        ou._member(Conn(), p, perms.Principal("nobody", ("user",)), False)
    assert e.value.status == 403
    assert ou._member(Conn(), p, perms.Principal("boss", ("super-admin",)), True) == set()
    with pytest.raises(EditError) as e:
        ou._member(Conn(), {**p, "status": "frozen"}, perms.Principal("boss", ("super-admin",)), True)
    assert e.value.status == 409


def test_uploads_stay_out_of_the_repository_and_approvals():
    src = Path(pj.__file__).read_text(encoding="utf-8")
    assert "AND d.origin <> 'other'" in src                          # not in the repository table
    assert 'd.get("origin") == "other"' in src                       # never accepted
    import inspect
    assert "'None'" in inspect.getsource(ou.upload)                  # kind None: sign-off refuses it (project_work)


def test_routes_and_seed_are_wired():
    api = (ROOT / "eax" / "api" / "projects.py").read_text(encoding="utf-8")
    for route in ("/other-uploads\")", "/other-uploads/<string:doc>\")", "/replace\")", "/versions\")", "/download\")"):
        assert route in api
    for action in ("project.other_upload.add", "project.other_upload.replace", "project.other_upload.delete"):
        assert action in api                                         # in the change log
    later = (ROOT / "eax" / "seed" / "later.py").read_text(encoding="utf-8")
    assert "sample_other_uploads" in later
