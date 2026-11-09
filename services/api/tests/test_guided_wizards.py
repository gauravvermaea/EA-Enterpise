"""Phase 16.3, the guided wizards (D339): what the server parts promise, without a database."""
import re
from pathlib import Path

import pytest

from eax import collect, first_run, gaps
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


class _User:
    def __init__(self, name, roles):
        self.username, self.roles = name, roles


def test_first_run_steps_and_links():
    keys = [k for k, *_ in first_run.STEPS]
    assert keys == ["settings", "people", "parts", "templates", "charter", "principles", "backups"]
    for _k, label, why, link in first_run.STEPS:
        assert label and why and (link.startswith("#/") or link == "")


def test_first_run_is_for_super_admins():
    with pytest.raises(EditError):
        first_run.mark(None, _User("ann", ["user"]), {"finished": True})


def test_collect_needs_a_model_admin(monkeypatch):
    monkeypatch.setattr(collect.repo, "get_model", lambda c, m: {"id": "m1", "_id": 1, "name": "Model One"})
    monkeypatch.setattr(collect.perms, "model_roles", lambda c, u, m: ["architect"])
    with pytest.raises(EditError) as e:
        collect.ask(None, "m1", _User("ann", ["user"]), {"types": ["X"], "people": ["bob"]})
    assert "Model Admin" in str(e.value)


def test_migration_plan_resolutions_and_columns():
    assert "Build" in gaps.RESOLUTIONS and "Retire" in gaps.RESOLUTIONS
    assert gaps.ROADMAP_COLUMNS[:4] == ["Wave", "Work package", "Start", "End"]


def test_routes_are_there():
    src = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "eax" / "api").glob("*.py")}
    assert '"/gaps/<string:analysis_id>/migration-plan"' in src["versions.py"]
    assert '"/models/<uuid:model_id>/collect"' in src["sheets.py"]
    assert '"/admin/first-run"' in src["admin.py"]
    assert 'request.args.get("fresh")' in src["quality.py"]


def test_the_screens_use_the_wizards():
    gw = (WEB / "GuidedWizards.jsx").read_text(encoding="utf-8")
    for name in ("QualityWizard", "ComplianceWizard", "MigrationWizard", "CollectWizard", "LoadDataWizard", "FirstRunPanel"):
        assert re.search(rf"export function {name}\b", gw), name
    assert "QualityWizard" in (WEB / "ModelAdmin.jsx").read_text(encoding="utf-8")
    assert "ComplianceWizard" in (WEB / "Projects.jsx").read_text(encoding="utf-8")
    assert "FirstRunPanel" in (WEB / "StartPage.jsx").read_text(encoding="utf-8")
    assert "export function Download" in (WEB / "Sheets.jsx").read_text(encoding="utf-8")
