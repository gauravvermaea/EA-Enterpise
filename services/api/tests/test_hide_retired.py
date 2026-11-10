"""Frozen and archived models and projects are out of the way (owner, 9 Nov 2026, D360): the screens' wiring."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def test_lists_hide_and_offer_the_checkbox():
    marks = (WEB / "ModelMarks.jsx").read_text(encoding="utf-8")
    for x in ("export const isRetiredModel", "export const isRetiredProject", "export function useShowRetired",
              "Show frozen and archived (", "eax.showRetired."):
        assert x in marks, x
    for f in ("Metamodel.jsx", "Areas.jsx", "Projects.jsx"):
        s = (WEB / f).read_text(encoding="utf-8")
        assert "<ShowRetired" in s and "useShowRetired()" in s, f


def test_switchers_and_pickers_never_offer_them():
    sw = (WEB / "ModelSwitcher.jsx").read_text(encoding="utf-8")
    assert "!isRetiredModel(x) || x.id === current" in sw and "!isRetiredProject(x) || x.id === current" in sw
    for f in ("GridPages.jsx", "Libraries.jsx", "Merge.jsx", "ModelAdmin.jsx", "ModelOps.jsx", "SystemWizards.jsx",
              "Canvas.jsx", "References.jsx", "GuidedWizards.jsx"):
        s = (WEB / f).read_text(encoding="utf-8")
        assert "liveModels(" in s or "liveProjects(" in s, f
