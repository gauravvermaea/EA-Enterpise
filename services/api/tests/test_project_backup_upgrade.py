"""Upgrading an older project backup on restore: steps per format version, newer files refused."""
import pytest

from eax import backups as bk
from eax import project_backup as pb
from eax.metamodel_edit import EditError


def _old():
    return {"projects": [{"id": 7, "created_at": "2026-10-01T10:00:00+00:00", "created_by": "ann"}],
            "steps": [{"id": 1, "added_by": "ann", "added_at": None, "done_at": "2026-10-05T09:00:00+00:00", "done_by": "bob"},
                      {"id": 2, "added_by": "ann", "added_at": "2026-10-02T09:00:00+00:00", "removed": True}],
            "gov_records": [{"id": 11, "created_by": "cy", "created_at": "2026-10-03T09:00:00+00:00"}],
            "principles": [{"id": 3, "area": "Data"}, {"id": 4, "area": "Business"}, {"id": 5, "area": ""}]}


def test_format_version_read_from_the_file():
    assert pb.format_of({"format": "eax-project-backup/1"}) == 1
    assert pb.format_of({"format": pb.FORMAT}) == pb.FORMAT_VERSION
    assert pb.format_of({"format": "nonsense"}) == 0


def test_a_format_1_file_is_upgraded():
    rows = _old()
    done = pb.upgrade(rows, {"format": "eax-project-backup/1"})
    ev = rows["step_events"]
    assert [(e["step_id"], e["action"]) for e in ev] == [(1, "opened"), (1, "closed")]   # a removed step gets none
    assert rows["steps"][0]["added_at"] == "2026-10-01T10:00:00+00:00"                     # from the project's start
    assert rows["gov_records"][0]["approval"] == "Draft" and rows["gov_history"][0]["action"] == "logged"
    assert [a["name"] for a in rows["principle_areas"]] == ["Business", "Data"]
    assert len(done) == 3 and all("0.15.1" in d for d in done)


def test_a_current_file_is_left_alone():
    rows = _old()
    assert pb.upgrade(rows, {"format": pb.FORMAT}) == [] and "step_events" not in rows


def test_every_format_version_has_a_step():
    assert sorted(pb.UPGRADES) == list(range(2, pb.FORMAT_VERSION + 1))


def test_about_a_file():
    a = pb.about_file({"format": "eax-project-backup/1"})
    assert a["format_version"] == 1 and a["upgrade"] == ["0.15.1"] and a["version"] == "before 0.15.1"
    assert pb.about_file({"format": pb.FORMAT, "version": "0.15.1"})["upgrade"] == []


def test_newer_files_are_refused(tmp_path):
    import json
    import zipfile
    f = tmp_path / "x.eaxproject.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("backup.json", json.dumps({"format": f"eax-project-backup/{pb.FORMAT_VERSION + 1}", "version": "99.0.0"}))
    with pytest.raises(EditError) as e:
        pb._read(f)
    assert "newer" in str(e.value)
    assert bk.newer_than_here("99.0.0") and not bk.newer_than_here("0.1.0") and not bk.newer_than_here(None)
