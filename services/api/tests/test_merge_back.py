"""Merging a child into its parent (phases 19 and 20, D359, D422 to D425), dedupe (phase 21, D361, D426 to D428) and the
sample documents (D415, D429). No database needed: the three-way rules, the grouping, the files, the migration, the wiring."""

import io
import zipfile
from pathlib import Path

import pytest

from eax import dedupe as dd
from eax import merge_back as mb
from eax import sample_documents as sd
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"

P1, P2, P3 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002", "aaaaaaaa-0000-4000-8000-000000000003"
C1, C2, C3, C4 = ("cccccccc-0000-4000-8000-000000000001", "cccccccc-0000-4000-8000-000000000002",
                  "cccccccc-0000-4000-8000-000000000003", "cccccccc-0000-4000-8000-000000000004")


def ent(g, name, desc="", origin=None, values=None, parent=None, t="BusinessObject"):
    return {"guid": g, "name": name, "description": desc, "origin": origin, "values": values or {}, "parent": parent,
            "type_code": t, "entity_type": "Business Object", "relationships": []}


def rel(s, t, sn="", tn="", typ="Association"):
    return {"type_code": typ, "relationship_type": typ, "verb": "associated with", "source": s, "target": t, "source_name": sn,
            "target_name": tn, "name": ""}


SPEC = {"attributes": [{"code": "Owner", "name": "Owner", "data_type": "text"}], "entity_types": [{"code": "BusinessObject", "name": "Business Object",
                                                                                                    "attributes": [{"attribute": "Owner"}]}],
        "relationship_types": [{"code": "Association", "name": "Association"}]}


def _plan(monkeypatch, base, child, parent, cspec=SPEC, pspec=SPEC):
    """plan() with the three snapshots given (base None: no starting point)."""
    from eax import model_ops as mo
    from eax import tags as tg
    snaps = {"child": child, "parent": parent}
    monkeypatch.setattr(mb, "_bypass", lambda conn, on: None)
    monkeypatch.setattr(mb, "_start_tag", lambda conn, mid: None if base is None else
                        {"guid": "t", "name": "Starting point", "created_at": "2026-11-10", "snapshot": base})
    monkeypatch.setattr(tg, "snapshot", lambda conn, m: snaps[m["name"]])
    monkeypatch.setattr(mo, "metamodel_spec", lambda conn, mid: cspec if mid == "child" else pspec)
    return mb.plan(None, {"_id": 1, "id": "child", "name": "child"}, {"_id": 2, "id": "parent", "name": "parent"})


def snap(*entities, rels=()):
    return {"entities": {e["guid"]: e for e in entities}, "relationships": {f"r{i}": r for i, r in enumerate(rels)}}


def test_only_the_child_changed_it_is_pre_accepted(monkeypatch):
    base = snap(ent(C1, "Claim", "old", P1))
    p = _plan(monkeypatch, base, snap(ent(C1, "Claim", "new", P1)), snap(ent(P1, "Claim", "old")))
    [c] = p["changes"]
    assert (c["kind"], c["code"], c["conflict"], c["child"], c["parent"], c["base"]) == ("update", "description", False, "new", "old", "old")


def test_only_the_parent_changed_it_is_left_alone(monkeypatch):
    base = snap(ent(C1, "Claim", "old", P1))
    p = _plan(monkeypatch, base, snap(ent(C1, "Claim", "old", P1)), snap(ent(P1, "Claim", "parent's")))
    assert p["changes"] == []


def test_both_changed_it_is_a_conflict(monkeypatch):
    base = snap(ent(C1, "Claim", "old", P1, {"Owner": "A"}))
    p = _plan(monkeypatch, base, snap(ent(C1, "Claim", "child's", P1, {"Owner": "A"})),
              snap(ent(P1, "Claim", "parent's", values={"Owner": "B"})))
    [c] = p["changes"]                       # the owner changed in the parent only: the parent's stands
    assert c["conflict"] and c["code"] == "description"
    assert p["counts"]["conflicts"] == 1


def test_added_and_removed_in_the_child(monkeypatch):
    base = snap(ent(C1, "Claim", "", P1), ent(C2, "Policy", "", P2))
    child = snap(ent(C1, "Claim", "", P1), ent(C3, "Quote", "new one"), rels=[rel(C3, C1, "Quote", "Claim")])
    parent = snap(ent(P1, "Claim"), ent(P2, "Policy"))
    p = _plan(monkeypatch, base, child, parent)
    kinds = {(c["kind"], c["name"], c["conflict"]) for c in p["changes"]}
    assert ("add", "Quote", False) in kinds and ("delete", "Policy", False) in kinds
    assert any(c["kind"] == "relate" and c["source"] == C3 and not c["conflict"] for c in p["changes"])


def test_removed_in_the_child_but_changed_in_the_parent_is_a_conflict(monkeypatch):
    base = snap(ent(C2, "Policy", "old", P2))
    p = _plan(monkeypatch, base, snap(), snap(ent(P2, "Policy", "changed since")))
    [c] = p["changes"]
    assert c["kind"] == "delete" and c["conflict"]


def test_removed_in_the_parent_and_changed_in_the_child_is_a_conflict(monkeypatch):
    base = snap(ent(C2, "Policy", "old", P2))
    p = _plan(monkeypatch, base, snap(ent(C2, "Policy", "child's", P2)), snap())
    [c] = p["changes"]
    assert c["kind"] == "add" and c["conflict"]
    p = _plan(monkeypatch, base, snap(ent(C2, "Policy", "old", P2)), snap())       # unchanged in the child: removal stands
    assert p["changes"] == []


def test_without_a_starting_point_every_difference_is_a_conflict(monkeypatch):
    p = _plan(monkeypatch, None, snap(ent(C1, "Claim", "child's", P1), ent(C3, "Quote")), snap(ent(P1, "Claim", "parent's")))
    assert p["base"] is None and all(c["conflict"] for c in p["changes"]) and len(p["changes"]) == 2


def test_references_are_compared_in_the_parents_terms(monkeypatch):
    """A child's parent (part of) is its own copy: compared as the parent's entity, so a copy is not a change."""
    base = snap(ent(C1, "Claim", "", P1), ent(C2, "Claim item", "", P2, parent=C1))
    child = snap(ent(C1, "Claim", "", P1), ent(C2, "Claim item", "", P2, parent=C1))
    parent = snap(ent(P1, "Claim"), ent(P2, "Claim item", parent=P1))
    assert _plan(monkeypatch, base, child, parent)["changes"] == []


def test_metamodel_additions_are_listed(monkeypatch):
    cspec = {**SPEC, "entity_types": SPEC["entity_types"] + [{"code": "Quote", "name": "Quote", "attributes": []}],
             "relationship_types": SPEC["relationship_types"] + [{"code": "Flow", "name": "Flow"}]}
    p = _plan(monkeypatch, snap(), snap(), snap(), cspec=cspec)
    assert {(c["section"], c["code"]) for c in p["changes"]} == {("entity_types", "Quote"), ("relationship_types", "Flow")}
    assert all(c["kind"] == "metamodel" and not c["conflict"] for c in p["changes"])


def test_a_new_entity_of_the_same_type_and_name_is_matched_not_added(monkeypatch):
    base = snap()
    p = _plan(monkeypatch, base, snap(ent(C4, "Quote", "child's")), snap(ent(P3, "Quote", "")))
    [c] = p["changes"]
    assert c["kind"] == "update" and c["parent_entity"] == P3


def test_accepted_rules():
    assert mb._accepted({"id": "x", "conflict": False}, {}) is True                       # pre-accepted
    assert mb._accepted({"id": "x", "conflict": True}, {}) is False                       # a conflict waits for a decision
    assert mb._accepted({"id": "x", "conflict": False}, {"x": {"accept": False}}) is False
    assert mb._accepted({"id": "x", "conflict": True}, {"x": {"accept": True}}) is True


def test_a_rejection_needs_a_reason(monkeypatch):
    r = {"id": 1, "guid": "g", "status": "sent", "parent_id": 2, "child_id": 1, "decisions": {},
         "plan": {"changes": [{"id": "set:x:description", "kind": "update", "name": "Claim", "field": "Description"}]}}
    monkeypatch.setattr(mb, "_request", lambda conn, rid: r)
    monkeypatch.setattr(mb, "_model_row", lambda conn, mid: {"id": f"m{mid}", "name": "parent", "_id": mid})
    monkeypatch.setattr(mb, "is_reviewer", lambda *a: True)
    monkeypatch.setattr(mb, "is_parent_admin", lambda *a: False)
    with pytest.raises(EditError, match="Say why"):
        mb.decide(None, "g", type("U", (), {"username": "anna", "roles": ()})(), {"set:x:description": {"accept": False}})
    r["plan"]["changes"].append({"id": "mm:type:Quote", "kind": "metamodel", "name": "Quote"})
    with pytest.raises(EditError, match="Model Admin"):
        mb.decide(None, "g", type("U", (), {"username": "anna", "roles": ()})(), {"mm:type:Quote": {"accept": True}})


# ---------------------------------------------------------------- dedupe
def test_closeness():
    assert dd.closeness("Claims Platform", "claims-platform") == 1.0
    assert dd.closeness("Claims Platform", "Claims Platfrom") > 0.88
    assert dd.closeness("Windows 2016", "Windows 2022") == 0.0           # versions, not duplicates
    assert dd.closeness("Billing Engine", "Payments Hub") < 0.6
    assert dd.closeness("Claims Platform", "Platform Claims") >= 0.95   # word order (D454)
    assert dd.closeness("Platform Claims 2", "Claims Platform 3") == 0.0  # numbers still decide


def test_similar_names_across_types():
    """D454: all types, the asked type first, each with its type and same_type; short names give nothing."""
    from types import SimpleNamespace

    class C:
        def __init__(self):
            self.sql = []

    rows = [{"id": "a", "name": "Claims Platform", "display_id": "AC-1", "type_code": "ApplicationComponent", "type": "Application Component", "same_type": True},
            {"id": "b", "name": "Claims Platfrom", "display_id": "AC-2", "type_code": "ApplicationComponent", "type": "Application Component", "same_type": True},
            {"id": "c", "name": "Claims Platform", "display_id": "CAP-9", "type_code": "Capability", "type": "Capability", "same_type": False},
            {"id": "d", "name": "Payments Hub", "display_id": "AC-3", "type_code": "ApplicationComponent", "type": "Application Component", "same_type": True}]
    seen = {}
    orig = (dd.repo.get_model, dd.repo._find_type, dd._rows)
    try:
        dd.repo.get_model = lambda c, m: {"_id": 1, "id": "m"}
        dd.repo._find_type = lambda c, m, t: {"_id": 7}
        def fake_rows(c, sql, **kw):
            seen.update(kw)
            return [dict(r) for r in rows]
        dd._rows = fake_rows
        out = dd.similar_names(SimpleNamespace(), "m", "ApplicationComponent", "claims platform", all_types=True, limit=10)["similar"]
        assert [h["id"] for h in out] == ["a", "b", "c"] and out[0]["same"] and out[2]["same_type"] is False
        assert seen["alltypes"] is True and seen["t"] == 7
        assert dd.similar_names(SimpleNamespace(), "m", "ApplicationComponent", "ab")["similar"] == []
    finally:
        dd.repo.get_model, dd.repo._find_type, dd._rows = orig


def test_groups_join_and_say_why():
    g = dd._Groups(["a", "b", "c", "d"])
    g.join({"id": "a"}, {"id": "b"}, "same name", 1.0)
    g.join({"id": "b"}, {"id": "c"}, "same Vendor", 1.0)
    assert g.find("a") == g.find("c") != g.find("d")
    assert set(g.why) == {("a", "b"), ("b", "c")}


def test_moves_drop_repeats_and_links_between_the_merged():
    KEEP, OTHER = "k", "o"
    ents = {KEEP: {"name": "Keep", "relationships": [{"type": "Serving", "s": KEEP, "t": "x", "s_name": "Keep", "t_name": "X"}]},
            OTHER: {"name": "Other", "relationships": [
                {"type": "Serving", "s": OTHER, "t": "x", "s_name": "Other", "t_name": "X", "type_name": "Serving", "name": ""},   # repeat
                {"type": "Serving", "s": OTHER, "t": "y", "s_name": "Other", "t_name": "Y", "type_name": "Serving", "name": ""},   # moves
                {"type": "Flow", "s": OTHER, "t": KEEP, "s_name": "Other", "t_name": "Keep", "type_name": "Flow", "name": ""}]}}     # between
    moves, dropped = dd._moves(ents, KEEP, [OTHER])
    assert [(m["source"], m["target"]) for m in moves] == [(KEEP, "y")] and dropped == 2


# ---------------------------------------------------------------- sample documents
def test_every_sample_document_is_made_and_opens():
    lst = sd.listing()["templates"]
    assert len(lst) >= 8 and {t["type"] for t in lst} == {"docx", "pptx", "xlsx"}
    for t in lst:
        data, name, ctype = sd.make(t["code"])
        assert name.endswith("." + t["type"]) and ctype
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert ("word/document.xml" in names) or ("ppt/slides/slide1.xml" in names) or ("xl/workbook.xml" in names)
        text = data.decode("latin-1").lower()
        for word in ("objective", "meridian", "strategyzer", "lean canvas", "togaf template"):
            assert word not in text, (t["code"], word)
    with pytest.raises(EditError):
        sd.make("nope")


def test_no_template_files_are_kept_in_the_repository():
    assert not list((ROOT / "eax").glob("**/*.pptx")) and not list((ROOT / "eax").glob("**/*.docx"))


# ---------------------------------------------------------------- the migration, the wiring, the screens
def test_migration_0034():
    sql = (ROOT / "migrations" / "sql" / "0034_merge_dedupe.sql").read_text()
    assert "'0.17.0'" in sql and "ON CONFLICT (version) DO NOTHING" in sql
    for word in ("CREATE TRIGGER", "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", "LANGUAGE plpgsql"):
        assert word not in sql.upper().replace("DO $$", ""), word                                 # D248
    for t in ("core.merge_requests", "core.entity_aliases"):
        assert f"CREATE TABLE {t}" in sql
    assert "'start'" in sql
    py = (ROOT / "migrations" / "versions" / "0034_merge_dedupe.py").read_text()
    assert 'down_revision = "0033_drawn_views"' in py and 'revision = "0034_merge_dedupe"' in py


def test_a_child_gets_a_starting_point_when_made():
    src = (ROOT / "eax" / "model_ops.py").read_text()
    assert src.count("merge_back.mark_start") == 2           # made with content (run_copy) and without


def test_routes_and_background_work_are_wired():
    api = (ROOT / "eax" / "api" / "merge_back.py").read_text()
    for route in ("/models/<uuid:model_id>/merge-requests", "/merge-requests/waiting", "/merge-requests/<uuid:request_id>/decisions",
                  "/merge-requests/<uuid:request_id>/merge", "/merge-requests/<uuid:request_id>/finish", "/merge-requests/<uuid:request_id>/report",
                  "/models/<uuid:model_id>/duplicates/compare", "/models/<uuid:model_id>/content/similar", "/sample-documents"):
        assert route in api, route
    assert api.count("@require_auth()") >= 13
    assert "merge_back_blp" in (ROOT / "eax" / "app.py").read_text()
    from eax import background, tasks
    assert background and {"mergeback.send", "mergeback.merge", "mergeback.finish"} <= set(tasks.WORK)


def test_screens():
    mbx = (WEB / "MergeBack.jsx").read_text()
    for s in ("SendForMergeWizard", "MergeRequestsTab", "Freeze it", "Refresh it from", "Download the report"):
        assert s in mbx
    ma = (WEB / "ModelAdmin.jsx").read_text()
    assert '"up-freeze"' not in ma and 'k: "send"' in ma and "merge-requests" in ma      # partial merges dropped (D359)
    assert "#/merge-requests" in (WEB / "App.jsx").read_text()
    q = (WEB / "Quality.jsx").read_text()
    assert "DedupeDialog" in q and "duplicates/compare" in q
    assert "content/similar" in (WEB / "DataEntry.jsx").read_text()
    assert '"otherdocs", "Other views and documents"' in (WEB / "Projects.jsx").read_text()
    for f in ("MergeBack.jsx", "OtherDocs.jsx", "Quality.jsx"):
        assert "objective" not in (WEB / f).read_text().lower()


def test_seed_shows_every_state():
    src = (ROOT / "eax" / "seed" / "sample_merge_dedupe.py").read_text()
    for s in ("mb.send", "mb.merge", "mb.withdraw", '"refresh"', '"freeze"', "dd.merge", "Payments Gateway", "Claims Platfrom"):
        assert s in src
    assert "sample_merge_dedupe" in (ROOT / "eax" / "seed" / "later.py").read_text()
