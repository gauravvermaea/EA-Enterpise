"""Owner, 7 Nov 2026: sample projects for every project template; what kind of model a model is; a new model from a tag
(never a child); the model filters; the wizard holds you on a step until its required fields are filled; the old menus."""

import json
from pathlib import Path

from eax.seed import sample_projects as sp

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_a_sample_for_every_template_and_every_way_a_model_joins():
    codes = {t["code"] for t in json.loads((ROOT / "eax" / "seed" / "project_templates.json").read_text())["templates"]}
    assert {s[0] for s in sp.SAMPLES} == codes
    hows = {m[0] for s in sp.SAMPLES for m in s[4]}
    assert hows == {"refer", "add", "child", "copy", "tag", "empty"}
    assert all(s[1].endswith("(sample)") for s in sp.SAMPLES)
    assert len({s[1] for s in sp.SAMPLES}) == len(sp.SAMPLES)
    # the tag a sample copies from is made by the seed
    tagged = {(m[1], m[3]["tag"]) for s in sp.SAMPLES for m in s[4] if m[0] == "tag"}
    assert tagged <= {(m, t) for m, t, _n in sp.TAGS}
    assert "sample_projects" in (ROOT / "eax" / "seed" / "later.py").read_text()


def test_from_a_tag_is_never_a_child():
    mo = (ROOT / "eax" / "model_ops.py").read_text()
    assert "def _from_tag" in mo and "cannot be a child of (merge back into)" in mo
    pj = (ROOT / "eax" / "projects.py").read_text()
    assert 'spec["tag"] = m["tag"]' in pj and "cannot keep a parent-child link" in pj
    sql = (ROOT / "migrations" / "sql" / "0028_repository_table.sql").read_text()
    assert "source_tag_name" in sql and "sponsor_notes_html" in sql and "goals_notes_html" in sql
    assert "source_tag_name" in (ROOT / "eax" / "repository.py").read_text()


def test_screens():
    origin = (WEB / "modelOrigin.js").read_text()
    for s in ("Root metamodel", "Library model", "Child (merges back)", "Copy of a model at a tag", "New (from a metamodel)"):
        assert s in origin
    js = (WEB / "Projects.jsx").read_text()
    for s in ("pick-filters", "Kind of model", "at a tag", "tag: m.tag || undefined", "blockedAt", "Fill in what is missing first",
              "<AdmWheel choosing", "More about the sponsor", "More about the goals", "For the goal", "edit?step=Models",
              "follows the project's name"):
        assert s in js
    assert "OriginChip" in (WEB / "Metamodel.jsx").read_text()
    assert "choosing" in (WEB / "AdmWheel.jsx").read_text()


def test_mayan_top_cabinet_has_a_null_parent():
    src = (ROOT / "eax" / "mayan.py").read_text()
    assert '"parent": parent or None' in src
    js = (WEB / "Projects.jsx").read_text()
    assert "!/HTTP 4" in js     # Documents refusing (an HTTP 4xx) is not Documents starting
