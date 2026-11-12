"""On-screen help for everything (D497): every page, tab, sub-tab, pop-up, wizard step, field and button of the web
screens has an entry in the one help catalogue (services/web/src/help/catalogue.json). The screens are read from
their sources by tools/help_inventory.py, so a screen added later without help fails here."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("help_inventory", ROOT / "tools" / "help_inventory.py")
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)


def test_every_screen_part_has_help():
    missing = inv.missing()
    lines = [f"{kind}: {key}" for kind, keys in missing.items() for key in keys]
    assert not lines, ("These have no on-screen help; add them to services/web/src/help/catalogue.json "
                       "(see docs/help-catalogue.md):\n  " + "\n  ".join(lines))


def test_the_inventory_finds_the_screens():
    """The scan itself works: it finds the main routes, tabs, pop-ups, steps, fields and buttons."""
    need = inv.needed()
    assert {"page:#/metamodel", "page:#/projects", "page:#/admin", "page:#/surveys"} <= need["page"]
    assert {"tab:Grid", "tab:Views", "tab:Quality", "tab:Machine access", "tab:Scenarios"} <= need["tab"]
    assert "popup:Merge duplicates: *" in need["popup"] and "popup:Find" in need["popup"]
    assert "step:Basics" in need["step"] and "step:Conflicts" in need["step"]
    assert "field:Commit message" in need["field"]
    assert "button:Commit" in need["button"]
    assert len(need["field"]) > 300 and len(need["button"]) > 300


def test_entries_are_well_formed():
    cat = json.loads(inv.CATALOGUE.read_text(encoding="utf-8"))
    for key, entry in cat.items():
        if key.startswith("_"):
            continue
        kind = key.split(":", 1)[0]
        assert kind in {"page", "tab", "popup", "step", "field", "button"}, key
        if kind in {"page", "tab", "popup", "step"}:
            assert isinstance(entry, dict) and entry.get("what") and isinstance(entry.get("how"), list) and entry["how"], key
        else:
            assert isinstance(entry, str) and entry.strip(), key
    text = json.dumps(cat).lower()
    assert "objective" not in text                       # the owner's rule: Outcome, never that word


def test_help_is_wired_into_the_screens():
    web = ROOT / "services" / "web" / "src"
    app = (web / "App.jsx").read_text(encoding="utf-8")
    assert "<HelpPanel />" in app
    # the ? menu's Help for this page (F1): the Classic row's own ? button went with R2.25 (D606)
    assert '{ label: "Help for this page (F1)", action: "help" }' in (web / "menu.js").read_text(encoding="utf-8")
    assert "openHelp({ popup: title })" in (web / "ModelOps.jsx").read_text(encoding="utf-8")   # ? on every pop-up
    panel = (web / "help" / "HelpPanel.jsx").read_text(encoding="utf-8")
    assert '"F1"' in panel and "setAttribute(\"title\"" in panel
