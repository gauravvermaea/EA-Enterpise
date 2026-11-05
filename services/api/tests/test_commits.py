"""Phase 8: commits of content, conflicts, roll back and merges (D165). The parts that need no database;
the whole flow (record, overlay, request, commit, conflict, roll back, merge) is in docs/phase-8.md."""

import pathlib

from eax import commits as cm
from eax import permissions as p

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_who_commits_and_who_sees_history():
    assert p.MODEL_ROLES == [p.MODEL_ADMIN, p.MODEL_SUB_ADMIN, p.COMMITTER, p.ARCHITECT, p.HISTORY_VIEWER, p.REPORT_VIEWER]
    assert p.MODEL_PERMISSIONS["model.commit"] == {p.MODEL_ADMIN, p.MODEL_SUB_ADMIN, p.COMMITTER}
    assert p.MODEL_PERMISSIONS["model.history"] == {p.MODEL_ADMIN, p.HISTORY_VIEWER}
    assert p.COMMITTER in p.MODEL_PERMISSIONS["model.content"]
    assert p.ARCHITECT not in p.MODEL_PERMISSIONS["model.commit"]   # architects ask for a commit
    assert {p.COMMITTER, p.HISTORY_VIEWER} <= p.MODEL_PERMISSIONS["model.read"]
    users = {u: m for u, _kc, m in p.TEST_USERS}
    assert p.COMMITTER in users["user_committer"]["Protea Insurance (demo estate)"]


def test_only_project_models_use_commits():
    assert cm.uses_commits({"kind": "project"})
    assert not cm.uses_commits({"kind": "template"})
    assert not cm.uses_commits({"kind": "reference"})


def test_fields_a_change_touches():
    after = {"values": {"Owner": "x", "AnnualCost": "1"}}
    t = cm._touched("entity.update", {"data": {"name": "n", "values": {"owner": "y", "Lifecycle": "Plan"}}}, after)
    assert t == ["name", "value:Owner", "value:Lifecycle"]   # codes as the model spells them
    assert cm._touched("entity.status", {}, None) == ["status"]
    assert cm._touched("relationship.rename", {}, None) == ["name"]


def test_differences_ignore_internal_ids():
    a = {"name": "A", "values": {"Owner": "x"}, "_value_ids": [1]}
    b = {"name": "A", "values": {"Owner": "y", "Lifecycle": "Plan"}, "_value_ids": [2]}
    assert cm._differences(a, b) == [("value:Lifecycle", None, "Plan"), ("value:Owner", "x", "y")]
    assert cm._differences(a, {**a, "_value_ids": [9]}) == []


def test_resolutions_keep_theirs_or_another_value():
    ch = {"op": "entity.update", "args": {"entity": "e", "data": {"description": "mine", "values": {"Owner": "me", "Lifecycle": "Plan"}}}}
    out = cm._resolved_args(ch, {"fields": {"value:owner": "theirs", "description": {"value": "agreed"}}})
    assert out["data"] == {"description": "agreed", "values": {"Lifecycle": "Plan"}}
    out = cm._resolved_args(ch, {"fields": {"value:Lifecycle": {"value": "Live"}}})
    assert out["data"]["values"] == {"Owner": "me", "Lifecycle": "Live"}
    assert cm._resolved_args(ch, "mine") == ch["args"]


def test_new_entities_get_their_guid_before_recording():
    a = cm._prepare("entity.create", {"data": {"name": "x", "row_version": 3}})
    assert a["data"]["guid"] and "row_version" not in a["data"]
    keep = cm._prepare("relationship.create", {"data": {"guid": "11111111-1111-1111-1111-111111111111"}})
    assert keep["data"]["guid"] == "11111111-1111-1111-1111-111111111111"   # a diagram shape's own id is kept


def test_every_content_write_goes_through_commits():
    """Content writes of the API call eax.commits for project models: data entry, the entity page, grids, and
    the batch endpoint that diagram editors (draw.io, phases 28-29) and tools use."""
    content = (ROOT / "eax" / "api" / "content.py").read_text(encoding="utf-8")
    grids = (ROOT / "eax" / "api" / "grids.py").read_text(encoding="utf-8")
    batch = (ROOT / "eax" / "api" / "commits.py").read_text(encoding="utf-8")
    for op in ("entity.create", "entity.update", "entity.delete", "relationship.create", "relationship.delete"):
        assert f'"{op}"' in content, op
    assert "record_entity_rows" in grids and "record_relationship_rows" in grids
    assert "/changes/batch" in batch and "record_many" in batch
    migration = (ROOT / "migrations" / "sql" / "0013_commits.sql").read_text(encoding="utf-8")
    assert "0.8.3" in migration and "core.pending_changes" in migration


def test_web_has_the_changes_tab():
    src = (WEB / "Changes.jsx").read_text(encoding="utf-8")
    for bit in ("/changes/commit", "/changes/request", "discard", "/roll-back", "/commits/latest", "EntityLink",
                "errors?.conflicts", "All mine", "All theirs"):
        assert bit in src, bit
    assert "ChangesTab" in (WEB / "Metamodel.jsx").read_text(encoding="utf-8")
    merge = (WEB / "Merge.jsx").read_text(encoding="utf-8")   # the merge has a screen of its own, not on the commit screen
    assert "/merge-test-file?format=xlsx" in merge and "/merge-test-file?format=zip" in merge   # files to try it with
    assert 'form.append("with_data"' in merge and "content=${content}" in merge   # with or without data
    assert "Use this value" in merge and "bulk-bar" in merge   # conflicts decided in bulk
    assert "source_model: source" in merge   # straight from another model, no file
    assert "/merges" in merge and "/merges" not in src and "MergeTab" in (WEB / "Metamodel.jsx").read_text(encoding="utf-8")
    ops = (WEB / "ModelOps.jsx").read_text(encoding="utf-8")
    assert "reject-publish" in ops and "reopen" in ops


def test_merge_or_not():
    """D169: a Model Admin merges into a project model that is not read-only or locked; otherwise no merge at all."""
    from types import SimpleNamespace

    from eax import merge as mg
    admin = SimpleNamespace(username="someone", roles=["super-admin"])
    base = {"id": "x", "name": "M", "kind": "project", "is_locked": False, "lock_level": "none", "locked_by": None, "lock_reason": ""}
    assert mg.blocked(None, base, admin) is None
    assert mg.blocked(None, {**base, "is_locked": True, "kind": "reference"}, admin)
    assert mg.blocked(None, {**base, "kind": "template"}, admin)
    for level in ("metamodel", "content", "maintenance"):   # any lock: no merge
        assert "locked" in mg.blocked(None, {**base, "lock_level": level, "locked_by": "someone"}, admin)
    src = (ROOT.parent / "web" / "src" / "Merge.jsx").read_text(encoding="utf-8")
    assert "may_add_metamodel" not in src and "addMeta" not in src   # no partial merges
    merge_py = (ROOT / "eax" / "merge.py").read_text(encoding="utf-8")
    assert "cm.commit(conn" in merge_py   # a merge is committed at once, no commit step (D170)
