"""Phase 13.0.4 (D283, D284, D285): model wizards, admin by wizards and architecture on screens, the five areas."""

from pathlib import Path

from eax import background as bg
from eax import merge as mg

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def _plan():
    return {
        "metamodel_gaps": {"entity_types": [{"code": "Goal"}, {"code": "Outcome"}], "relationship_types": [{"code": "realisation"}],
                           "note": "x"},
        "entities": [{"key": "a", "entity_type": "Goal", "action": "create"}, {"key": "b", "entity_type": "Outcome", "action": "create"},
                     {"key": "c", "entity_type": "Goal", "action": "update"}],
        "conflicts": [{"id": "c|name"}, {"id": "b|description"}],
        "relationships": [{"type": "realisation", "source": "b", "target": "a"}, {"type": "association", "source": "a", "target": "c"}],
    }


def _ex(**k):
    base = {"entity_types": set(), "relationship_types": set(), "entities": set(), "relationships": set(), "metamodel": set()}
    base.update({x: set(v) for x, v in k.items()})
    return base


def test_select_by_type_then_item():
    p = mg._select(_plan(), _ex(entity_types=["outcome"]))
    assert [e["key"] for e in p["entities"]] == ["a", "c"]
    assert [c["id"] for c in p["conflicts"]] == ["c|name"]
    # the relationship to the Outcome left out is left out too
    assert [r["type"] for r in p["relationships"]] == ["association"]
    assert [g["code"] for g in p["metamodel_gaps"]["entity_types"]] == ["Goal"]
    p = mg._select(_plan(), _ex(entities=["c"], relationships=["r0"]))
    assert [e["key"] for e in p["entities"]] == ["a", "b"] and p["relationships"] == []
    p = mg._select(_plan(), _ex(relationship_types=["realisation"], metamodel=["goal"]))
    assert len(p["relationships"]) == 1 and p["metamodel_gaps"]["relationship_types"] == []
    assert [g["code"] for g in p["metamodel_gaps"]["entity_types"]] == ["Outcome"]
    assert len(mg._select(_plan(), _ex())["entities"]) == 3


def test_migration_and_lock_rules():
    sql = (ROOT / "migrations" / "sql" / "0026_model_wizards.sql").read_text()
    assert "frozen_at" in sql and "frozen_by" in sql and "frozen_note" in sql and "'0.14.4'" in sql
    me = (ROOT / "eax" / "metamodel_edit.py").read_text()
    assert me.count('m.get("frozen_at")') >= 2     # a frozen model is neither locked again nor unlocked (only unfrozen)
    assert 'version = "0.1' in (ROOT / "version.toml").read_text()


def test_routes_and_background():
    src = (ROOT / "eax" / "api" / "model_wizards.py").read_text()
    for r in ("/wizards/family", "/wizards/tag-first", "/wizards/merge", "/freeze", "/unfreeze", "/detach", "/reparent", "/split",
              "/extend-preview", "/extend", "/duplicates", "/duplicates/merge", "/hand-over"):
        assert r in src
    assert "model_wizards_blp" in (ROOT / "eax" / "app.py").read_text()
    for k in ("wizard.merge", "wizard.split", "wizard.extend"):
        assert k in bg.WORK and k in bg.KINDS
    pw = (ROOT / "eax" / "project_work.py").read_text()
    assert '"merge-freeze"' in pw and "mw.tag_first" in pw and "mw.freeze" in pw


def test_five_areas_and_screens():
    areas = (WEB / "Areas.jsx").read_text()
    for a in ("System admin", "Model admin", "Project admin", "Architecture work", "Everything else"):
        assert a in areas
    app = (WEB / "App.jsx").read_text()
    for r in ('"#/work"', '"#/more"', '"#/model-admin"', '"#/project-admin"', "<AreaMenu"):
        assert r in app
    # every menu there was before the areas stays (owner, 7 Nov 2026, D289)
    for r in ('"#/metamodel"', '"#/library"', '"#/compare"', '"#/compare/gaps"', '"#/change-log"', '"#/mcp"', '"#/admin"', '"/api/docs"', 'className="subnav"'):
        assert r in app
    mm = (WEB / "Metamodel.jsx").read_text()
    # the model page keeps every tab and the Actions menu (owner: power users keep what they had); a link to its wizards
    assert "Model wizards" in mm and "<ModelActions" in mm and "ADMIN_VIEWS" in mm and '["people", "People", null]' in mm
    ma = (WEB / "ModelAdmin.jsx").read_text()
    for s in ("function WizardsHome", "function PickModel", "function MergeWizard", "function SplitWizard", "function ExtendWizard", "function FreezeDialog", "function HandOverWizard",
              "function ReparentWizard", "By type", "By item", "Merge into the parent and freeze", "Propagate changes from the parent"):
        assert s in ma
    pj = (WEB / "Projects.jsx").read_text()
    assert "export function ProjectAdmin" in pj and "Project wizards" in pj and "Copy from the library" in pj
    assert "function ProjectWizards" in pj and "function PickProject" in pj and "export function RepoHelp" in pj
    assert "function Duplicates" in (WEB / "Quality.jsx").read_text()
    sw = (WEB / "SystemWizards.jsx").read_text()
    for s in ("Give a person access", "Take a person's access away", "Back up now", "function RestoreWizard"):
        assert s in sw
