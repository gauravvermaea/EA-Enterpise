"""The TOGAF business architecture artifacts (D345): extension types, views, sample data and the tabs."""
from pathlib import Path

from eax.report_defs import VIEWS
from eax.seed import archimate4 as A
from eax.seed import demo_estate as D
from eax.seed import togaf10

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def test_extensions_in_both_metamodels():
    ext = {t[0] for t in A.EXTENSIONS}
    assert ext == {"ValueStreamStage", "ProductLifecycleStage", "BusinessScenario", "Control", "Contract", "Measure"}
    assert not ext & set(A.SPEC_TYPES)
    togaf = {t[0] for t in togaf10.TYPES}
    assert {"ValueStreamStage", "ProductLifecycleStage", "BusinessScenario", "Control", "Contract", "Measure"} <= togaf
    assert ("Importance", "N", "Assessment") in A.MAP["Capability"] and ("Investment", "N", "Assessment") in A.MAP["Capability"]


def test_demo_estate_has_every_extension_type():
    present = {t for t, *_ in D.E}
    assert {t[0] for t in A.EXTENSIONS} <= present
    caps = [a for t, _n, _d, _p, a in D.E if t == "Capability"]
    assert all("Importance" in a and "Investment" in a for a in caps)


def test_togaf_views_cover_the_artifacts():
    names = {v["togaf_artifact"] for v in VIEWS if v["togaf_artifact"]}
    for a in ("Business Capability Map", "Value Stream Map", "Organization Map", "Business Interaction matrix", "Information Map",
              "Value Stream Stages catalog", "Product Lifecycle diagram", "Business Scenario", "Contract/Measure catalog"):
        assert a in names, a
    assert not any("bjective" in v["togaf_artifact"] for v in VIEWS)        # Outcome, never the other word


def test_tabs_on_the_model_and_project_pages():
    assert '["business", "Business views", null]' in (WEB / "Metamodel.jsx").read_text()          # D352
    assert '["business", "Business artifacts"]' in (WEB / "Projects.jsx").read_text()
    ba = (WEB / "BusinessArchitecture.jsx").read_text()
    assert "types_defined" in ba and "view_reports" in ba
    model_tab = ba.split("export function ModelBusinessArtifacts")[1].split("\n}\n")[0]
    assert "canvas" not in model_tab.lower()                              # the model's tab: only what comes from the model
    project_tab = ba.split("export function ProjectBusinessArtifacts")[1]
    assert "/canvases" in project_tab and 'phase === "B"' in project_tab


def test_every_business_view_has_its_reports():
    from eax.report_defs import REPORTS, VIEW_REPORTS, VIEWS
    codes = {r["code"] for r in REPORTS}
    togaf = {v["code"] for v in VIEWS if v.get("togaf_artifact")}
    assert set(VIEW_REPORTS) == togaf                                   # every one, and only those (D352)
    assert all(c in codes for cs in VIEW_REPORTS.values() for c in cs)
    assert all(v in codes for v in togaf)                                    # each is also a dashboard of its own
