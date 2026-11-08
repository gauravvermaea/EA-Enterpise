"""Phase 13.1 (D303 to D307): project bases, the TOGAF 10 metamodel, standards, governance log, charter, skills."""

import json
from pathlib import Path

import pytest

from eax import content_framework as cf
from eax import governance as gv
from eax import project_bases as pb
from eax import standards as st
from eax.metamodel_edit import EditError
from eax.seed import togaf10 as t10

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def test_migration():
    sql = (ROOT / "migrations" / "sql" / "0031_project_bases.sql").read_text()
    for s in ("ADD COLUMN base_kind", "ADD COLUMN base_id", "CREATE TABLE proj.standards", "CREATE TABLE proj.base_skips",
              "CREATE TABLE proj.gov_records", "CREATE TABLE proj.gov_kinds", "CREATE TABLE proj.charters",
              "ALTER TABLE proj.org_people ADD COLUMN skills", "'0.15.0'"):
        assert s in sql
    assert 'version = "0.15.' in (ROOT / "version.toml").read_text()


def test_togaf10_metamodel():
    codes = [c for c, *_ in t10.TYPES]
    assert len(codes) == len(set(codes)) and len(codes) >= 35
    assert all(area in cf.LABEL for *_x, area, _d in t10.TYPES)
    assert "Outcome" in codes and not any("objective" in (n + d).lower() for _c, n, *_r, d in t10.TYPES)
    rels = {r for r, *_ in t10.RELS}
    assert all(s in codes and t in codes and r in rels for s, r, t in t10.ALLOWED)
    assert len({(s, r, t) for s, r, t in t10.ALLOWED}) == len(t10.ALLOWED)


def test_seed_content_is_ours_and_grouped():
    s = pb.seed()
    areas = {p["area"] for p in s["principles"]}
    assert {"Business", "Data", "Application", "Technology", "Security"} <= areas
    assert {"Business", "Data", "Application", "Technology", "Security"} <= {x["area"] for x in s["standards"]}
    assert all(p["statement"] and p["rationale"] and p["implications"] for p in s["principles"])
    assert len({p["name"] for p in s["principles"]}) == len(s["principles"])
    assert all(x["status"] in st.STATUSES for x in s["standards"])
    assert [c["key"] for c in s["charter"]][:2] == ["purpose", "scope"]
    text = json.dumps(s).lower()
    assert "objective" not in text and "meridian" not in text


def test_bases_sql_is_idempotent_and_ordered():
    sql = pb.bases_sql("00000000-0000-0000-0000-000000000001")
    assert sql.count("ON CONFLICT (guid) DO NOTHING") == 3
    assert "WHERE base_kind = '' AND base_id IS NULL" in sql
    assert sql.index("TOGAF 10 project") < sql.index("md5('org-' || s.guid::text)")
    assert len({pb.EMPTY_GUID, pb.TOGAF_GUID, pb.ORG_GUID}) == 3


def test_base_rules():
    class U:
        username = "x"
        roles = ("user",)

    class S:
        username = "sa"
        roles = ("super-admin",)
    for kind in ("empty", "togaf"):
        with pytest.raises(EditError):
            pb.check_change({"name": "b", "base_kind": kind}, S())
    with pytest.raises(EditError):
        pb.check_change({"name": "b", "base_kind": "org"}, U())
    pb.check_change({"name": "b", "base_kind": "org"}, S())
    pb.check_change({"name": "p", "base_kind": ""}, U())


def test_governance_kinds():
    assert list(gv.KINDS) == ["Decision", "Dispensation", "Compliance assessment", "Capability assessment", "Risk", "Issue"]   # D318
    assert all(len(v[0]) == 3 and v[1] for v in gv.KINDS.values())


def test_api_and_screens():
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for r in ('"/projects/bases"', '"/projects/<string:project>/base"', '"/projects/<string:project>/standards"',
              '"/projects/<string:project>/governance"', '"/projects/<string:project>/charter"'):
        assert r in api
    s = (WEB / "Projects.jsx").read_text()
    for t in ('["base", "Base"]', '["charter", "Charter"]', '["standards", "Standards"]', '["governance", "Governance log"]', "<BasesTree />", "<BaseBanner"):
        assert t in s
    a = (WEB / "Areas.jsx").read_text()
    assert "function ProjectHierarchy" in a and "function ModelHierarchy" in a and "Repository view" in a
    assert "skills" in (WEB / "ProjectOrg.jsx").read_text()
    pr = (ROOT / "eax" / "projects.py").read_text()
    assert "pbm.take_all_new" in pr and "pb.check_change(p, user)" in pr


def test_hierarchy_drawn_as_a_tree():
    t = (WEB / "ProjectTree.jsx").read_text()
    assert "export function flatten" in t and "openDrawio" in t and "usePanZoom" in t
    assert "<ProjectTree items={flatten(data.nodes)}" in (WEB / "ProjectGovernance.jsx").read_text()
    a = (WEB / "Areas.jsx").read_text()
    assert "<ModelTree models={keep} />" in a and "<ProjectTree items=" in a


def test_project_template_read_view_and_new_project():
    s = (WEB / "Projects.jsx").read_text()
    assert "function TemplateView" in s and "Make a project from it" in s and "#/projects/new?template=${t.code}" in s


def test_documents_named_planned_and_kinds_and_phase_completion():
    sql = (ROOT / "migrations" / "sql" / "0031_project_bases.sql").read_text()
    assert "ADD COLUMN title text" in sql and "'Deliverable', 'Artifact', 'None'" in sql and "CREATE TABLE proj.phase_states" in sql
    assert "ADD COLUMN completed_at timestamptz" in sql
    from eax import projects as pj
    assert pj.DOC_KINDS == ("Deliverable", "Artifact", "None")
    assert pj._doc_kind("") is None and pj._doc_kind("None") == "None"
    with pytest.raises(EditError):
        pj._doc_kind("Other")
    src = (ROOT / "eax" / "projects.py").read_text()
    assert "def add_planned" in src and "def add_file" in src and "def mark_phase" in src and "def mark_project" in src
    assert "deliverables_done" not in src.split("def completion")[1].split("def mark_project")[0]   # documents never count
    assert '"action_name": "replace"' in (ROOT / "eax" / "mayan.py").read_text()
    s = (WEB / "Projects.jsx").read_text()
    assert "neither (no approval)" in s and "function PhaseDone" in s and '["report", "Project report"]' in s and "Add the file…" in s
    m = (WEB / "Metamodel.jsx").read_text()
    assert "function EntityFinder" in m and "entities (grid)" in m


def test_governance_approval():
    """D321: an approval state beside the status; sent to the sign-off people or approved with evidence or a reason."""
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for x in ("ADD COLUMN approval text NOT NULL DEFAULT 'Draft'", "CREATE TABLE proj.gov_approvals", "CREATE TABLE proj.gov_decisions",
              "CREATE TABLE proj.gov_history"):
        assert x in sql
    assert gv.APPROVAL == ("Draft", "Waiting for approval", "Approved", "Rejected")
    for f in ("send_for_approval", "decide", "approve_with_evidence", "history"):
        assert callable(getattr(gv, f))
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    assert '"/projects/<string:project>/governance/<string:rid>/approval"' in api and '/evidence"' in api and '/history"' in api
    bk = (ROOT / "eax" / "project_backup.py").read_text()
    assert '("gov_approvals"' in bk and '("gov_history"' in bk
    web = (ROOT.parent / "web" / "src" / "ProjectGovernance.jsx").read_text()
    assert "function ApprovalBox" in web and "Approve with evidence…" in web and "Send for approval…" in web
