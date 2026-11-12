"""R2.48 (D607; owner, 12 Nov 2026: "architecture principles and how show them current UI is not great"; the owner's four
answers: TOGAF cards, grouped by area, an organisation page and each project's tab, edited on the card)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "services" / "web" / "src"


def test_principles_are_cards_by_area_edited_on_the_card():
    src = (WEB / "Principles.jsx").read_text(encoding="utf-8")
    for part in ("principle-card", "principle-area", "<h5>Statement</h5>", '"Rationale"', '"Implications"', "Expand all",
                 "PrincipleEditor", "＋ From the library", "＋ Refine it", "dispensation"):
        assert part in src, part
    assert "<table" not in src                                         # no more table of principles
    projects = (WEB / "Projects.jsx").read_text(encoding="utf-8")
    assert 'import { PrinciplesTab } from "./Principles";' in projects and "function PrinciplesTab" not in projects


def test_the_organisation_page_is_in_the_menu_for_everyone():
    assert 'route.startsWith("#/principles") ? <PrinciplesPage />' in (WEB / "App.jsx").read_text(encoding="utf-8")
    menu = (WEB / "menu.js").read_text(encoding="utf-8")
    assert '{ label: "Architecture principles", href: "#/principles" }' in menu
    assert '"page:#/principles"' in (WEB / "help" / "catalogue.json").read_text(encoding="utf-8")


def test_a_principle_can_be_added_from_the_library_in_its_own_words():
    src = (REPO / "services" / "api" / "eax" / "project_work.py").read_text(encoding="utf-8")
    assert 'if d.get("library_id"):' in src and "FROM proj.lib_principles WHERE id = :l AND NOT retired" in src
