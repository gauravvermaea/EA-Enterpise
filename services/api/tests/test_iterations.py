"""ADM iteration types on projects (D571-D574): TOGAF's mapping, custom phases, freezing in the API and the screens."""

from pathlib import Path

import pytest

from eax import iterations as it
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_togaf_mapping_and_requirements_management_always_on():
    assert it.clean("full") == ("full", ["P", "A", "B", "C", "D", "E", "F", "G", "H"])
    assert it.clean("capability") == ("capability", ["P", "A"])
    assert it.clean("development") == ("development", ["B", "C", "D"])
    assert it.clean("transition") == ("transition", ["E", "F"])
    assert it.clean("governance") == ("governance", ["G", "H"])
    for code in ("full", "capability", "development", "transition", "governance"):
        cur = {"phases": it.clean(code)[1]}
        assert it.enabled(cur, "RM") and it.enabled(cur, "X") and it.enabled(cur, "")


def test_every_iteration_enables_exactly_its_phases_and_c_parts_follow_c():
    expected = {"capability": {"P", "A"}, "development": {"B", "C", "D"}, "transition": {"E", "F"}, "governance": {"G", "H"}}
    for code, on in expected.items():
        cur = {"phases": it.clean(code)[1]}
        for ph in it.PHASES:
            assert it.enabled(cur, ph) == (ph in on), (code, ph)
        assert it.enabled(cur, "C-D") == ("C" in on) and it.enabled(cur, "C-A") == ("C" in on)


def test_built_in_phases_are_fixed_and_custom_is_checked():
    assert it.clean("transition", ["A", "B"]) == ("transition", ["E", "F"])        # built-in: phases given are ignored
    assert it.clean("custom", ["E", "a", "Preliminary", "B"]) == ("custom", ["P", "A", "B", "E"])
    assert it.clean("custom", "A, C-D") == ("custom", ["A", "C"])
    assert it.clean("CUSTOM", ["p"]) == ("custom", ["P"])
    with pytest.raises(EditError, match="at least one phase"):
        it.clean("custom", [])
    with pytest.raises(EditError, match="Not ADM phases: Z"):
        it.clean("custom", ["A", "Z"])
    with pytest.raises(EditError, match="No iteration"):
        it.clean("waterfall")


def test_labels_name_the_phases():
    assert it.label("transition", ["E", "F"]) == "Transition Planning iteration (E, F)"
    assert it.label("capability", ["P", "A"]) == "Architecture Capability iteration (Preliminary, A)"


def test_guard_refuses_a_frozen_phase_with_409(monkeypatch):
    monkeypatch.setattr(it, "current", lambda conn, p: {"code": "transition", "name": "Transition Planning iteration",
                                                         "phases": ["E", "F"], "chosen": True})
    p = {"id": 1, "name": "P"}
    it.guard(None, p, "E")
    it.guard(None, p, "RM")
    with pytest.raises(EditError) as e:
        it.guard(None, p, "C-D")
    assert e.value.status == 409 and "Phase C isn't part of this Transition Planning iteration" in str(e.value)
    with pytest.raises(EditError, match="The Preliminary phase isn't part"):
        it.guard(None, p, "P")
    it.guard(None, {**p, "base_kind": "org"}, "B")                 # bases have no iteration


def test_the_api_guards_every_phase_edit():
    src = (ROOT / "eax" / "projects.py").read_text(encoding="utf-8")
    for fn in ("mark_phase", "mark_step", "add_step", "add_substep", "delete_substep", "choose_item", "not_needed", "add_item",
               "offer_template", "from_templates", "upload", "add_file", "set_title", "accept", "set_hidden", "check_out", "check_in"):
        body = src.split(f"\ndef {fn}(", 1)[1].split("\ndef ", 1)[0]
        assert "_iter.guard" in body, fn
    work = (ROOT / "eax" / "project_work.py").read_text(encoding="utf-8")
    for fn in ("raise_signoff", "decide_signoff", "set_document_kind"):
        assert "_iter.guard" in work.split(f"\ndef {fn}(", 1)[1].split("\ndef ", 1)[0], fn


def test_migration_is_rows_only_and_chained():
    sql = (ROOT / "migrations" / "sql" / "0048_project_iterations.sql").read_text(encoding="utf-8")
    assert "proj.iteration_changes" in sql and "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()
    v = (ROOT / "migrations" / "versions" / "0048_project_iterations.py").read_text(encoding="utf-8")
    assert 'down_revision = "0047_relationship_attributes"' in v


def test_web_twin_matches_and_screens_freeze():
    js = (WEB / "iterations.js").read_text(encoding="utf-8")
    assert 'PHASES = ["P", "A", "B", "C", "D", "E", "F", "G", "H"]' in js and '"C-D": "C"' in js
    projects = (WEB / "Projects.jsx").read_text(encoding="utf-8")
    assert "<IterationControl p={p} />" in projects and "readOnlyIn(outer, sel)" in projects
    assert "enabled={(c) => projectPhaseEnabled(p, c)}" in projects
    assert "off={off(" in (WEB / "AdmWheel.jsx").read_text(encoding="utf-8")


def test_backups_seed_and_mcp_carry_it():
    assert '("iteration_changes", "project_id = :p", {})' in (ROOT / "eax" / "project_backup.py").read_text(encoding="utf-8")
    assert "sample_iterations" in (ROOT / "eax" / "seed" / "later.py").read_text(encoding="utf-8")
    assert "mcp_iterations" in (ROOT / "eax" / "mcp_server.py").read_text(encoding="utf-8")
    from eax.seed import sample_iterations as si
    states = {c for _n, changes in si.PLAN for c, *_ in changes}
    assert {"full", "development", "transition", "governance", "custom"} <= states
