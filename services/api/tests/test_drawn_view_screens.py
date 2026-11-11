"""Drawn views on the screens (phases 28 and 29): the web app's wiring to the API and to the draw.io plugin."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _src(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_the_editor_speaks_the_plugin_protocol():
    s = _src("DrawnView.jsx")
    # draw.io's own embed protocol, with a fresh page every time and autosave for the current file
    for x in ("/drawio/index.html?embed=1&proto=json&configure=1&eax=1", "eaxv=", 'action: "configure"', "autosave: 1",
              'action: "export"'):
        assert x in s, x
    # every plugin event the host must answer or show
    for ev in ("eax-ready", "eax-setup-done", "eax-relationship", "eax-add-relationship", "eax-junction-new", "eax-nest",
               "eax-choose", "eax-open", "eax-selected", "eax-changed", "eax-refused", "eax-hidden-list", "eax-placeholders",
               "eax-resynced"):
        assert f'"{ev}"' in s, ev
    # and every message it sends
    for m in ('eax: "rel"', 'eax: "rel-cancel"', 'eax: "rel-create"', 'eax: "junction-bound"', 'eax: "nest-ok"',
              'eax: "nest-refused"', 'eax: "bind"', 'eax: "place"', 'eax: "place-at-pointer"', 'eax: "resync"',
              'eax: "heat"', 'eax: "heat-off"', 'eax: "hidden"', 'eax: "placeholders"'):
        assert m in s, m


def test_the_editor_uses_the_api():
    s = _src("DrawnView.jsx")
    for x in ("/api/views/v1/models/", "/drawn-views", "/setup?view=", "/resync", "/relationships-of", "/allowed?source=", "/heat-map?attribute=",
              "/drawn-views/change", "/view-evidence", "/icon", "base_version", "force",
              "errors?.conflict", "model_changed_since", "entity-list"):
        assert x in s, x


def test_the_screens_are_wired_in():
    assert "DrawnViewPage" in _src("Metamodel.jsx") and '"drawn-views"' in _src("Metamodel.jsx")
    assert "<DrawnViewsSection" in _src("Views.jsx")
    for f in ("EntityGraph.jsx", "HierarchyMap.jsx", "RelationMatrix.jsx", "Maps.jsx", "Views.jsx", "MetamodelDiagram.jsx"):
        assert "<PictureActions model={model}" in _src(f), f                 # Save as a drawn view on every picture (D407)
    for f in ("ModelTree.jsx", "ProjectTree.jsx"):
        assert "<PictureActions picture=" in _src(f), f                     # not one model's: downloads only
    # D585 (amends D408): "Open in draw.io" opens our own draw.io as a scratch view, only through drawioScratch.js, and
    # that view is read only: nothing on it can change the model; Save as a drawn view keeps it
    for f in ("DrawnView.jsx", "Canvas.jsx"):
        assert "openInDrawio(" in _src(f), f
    sc = _src("ScratchDrawio.jsx")
    assert "readOnly: true" in sc and "keepLook: true" in sc and "<NewDrawnView" in sc and "sameTab" in sc
    assert "Leave without saving? This picture isn't kept." in sc and "noSaveBtn=1" in sc
    assert "ScratchDrawioFullScreen" in _src("App.jsx") and "#\\/drawio\\/open\\/" in _src("App.jsx")
    sk = _src("drawioScratch.js")
    assert "localStorage" in sk and "sessionStorage" in sk and "window.opener" in sk
    assert "?xml=" not in sk and "encodeURIComponent(xml" not in sk          # never the picture in the address
    assert "/api/views/v1/models/${model}/own-views" in _src("Views.jsx") and "views/render" in _src("Views.jsx")
    assert 'eax: "palettes"' in _src("DrawnView.jsx")                       # D409
    assert "<EntityIcon" in _src("ModelViews.jsx")
    assert "<ViewEvidenceList" in _src("Projects.jsx")
    ed = _src("MetamodelEditor.jsx")
    assert '"notation"' in ed and '"fill_colour"' in ed and "NOTATIONS" in ed


def test_views_sub_tabs_names_commit_and_stencil_size():
    """D412: the Views tab's sub-tabs, names on lines, Commit next to Save, the stencil size; type drop-downs searchable (D540)."""
    v = _src("Views.jsx")
    for x in ('["custom", "Custom views"]', '["standard", "Standard views"]', 'OLD_TABS = { drawn: "custom", own: "custom" }',
              'customCount ? "custom" : "standard"', 'views/${vp.own ? "custom" : "standard"}', "DrawnViewsSection model={model} m={m} generated="):
        assert x in v, x
    s = _src("DrawnView.jsx")
    for x in ("views/custom", "<th>Kind</th>", ">Drawn</span>", ">Generated</span>", "typeGroups(setup)", "typeOptions(setup)", "<SearchSelect",
              'eax: "stencil-size"', "eax.drawn.stencilSize.", "name: x.name", "name: out.name"):
        assert x in s, x
    assert s.index('"Save"}') < s.index("uncommittedLabel(pend)}")          # Uncommitted changes sits next to Save (D413)
    p = (WEB.parents[2] / "deploy" / "drawio" / "eax-plugin.js").read_text(encoding="utf-8")
    assert "THUMBS" in p and 'm.eax === "stencil-size"' in p and "eax-stencil-size" in p


def test_two_way_sync_and_decoration():
    """D413, D414: relationships committed at once, entities from the drawing for committers, the Uncommitted changes panel,
    deleting a line asks, the view brought up to date on opening and watched while open; draw.io's decoration palettes."""
    s = _src("DrawnView.jsx")
    for x in ("/drawn-views/change", "/drawn-views/commit", "function changeNow(", '"relationship.create"', '"relationship.delete"',
              "pending: false", "UncommittedPanel", "Commit selected", "Commit all", "/changes/discard", "/changes`",
              "LineDeleteDialog", '"eax-line-deleted"', 'eax: "line-hide"', 'eax: "line-restore"', 'eax: "line-removed"',
              "Hide in this view", "Delete from the model", 'eax: "placeholder-type"', "typeFamily(", "Create a new {typeName}",
              "commit={{ view: info.name }}", "resync(true)", "Updated since last saved", "/access`", "30000", '"focus"',
              "General, Misc and Basic"):
        assert x in s, x
    assert "/content/relationships" not in s and "/pending`" not in s and "CommitDialog" not in s
    d = _src("DataEntry.jsx")
    for x in ("commit = null", "Save and commit", "/drawn-views/change", "Commit message", '"entity.update"', '"entity.create"'):
        assert x in d, x
    p = (WEB.parents[2] / "deploy" / "drawio" / "eax-plugin.js").read_text(encoding="utf-8")
    for x in ('"eax-line-deleted"', 'm.eax === "line-hide"', '"placeholder-type"', 'ea_decor: "1"', "addGeneralPalette", "addMiscPalette",
              "addBasicPalette", "function isDecor(", "committed: solid", "auto: !!m.auto"):
        assert x in p, x
    assert "ArchiMate" not in p.split("var DECOR")[1].split("];")[0]                # never draw.io's ArchiMate libraries (D396)


def test_the_working_space():
    """D420: the stencil on the left and a bottom panel of tabs, each pinned or unpinned, three preset layouts remembered for
    the person; the drop pop-up; the Relationships and Allowed relationships tabs; draw.io's Format panel gone."""
    s = _src("DrawnView.jsx")
    for x in ('drawing: { stencil: true, bottom: false }', 'editing: { stencil: true, bottom: true }', 'canvas: { stencil: false, bottom: false }',
              '"Canvas only"', "eax.drawn.layout.", "localStorage", '["find", "Find in the model"]', '["props", "Properties"]',
              '["rels", "Relationships"]', '["allowed", "Allowed relationships"]', '["unc", "Uncommitted changes"]', "drawn-resizer",
              "setPointerCapture", 'eax: "stencil-panel"', '"eax-canvas-click"', '"eax-dropped"', "function DropDialog(", "Leave as a placeholder",
              "Bind it to an existing", "function RelatedTab(", 'eax: "add-related"', "function AllowedTab(", 'eax: "add-allowed"',
              '"eax-waiting-line"', 'eax: "waiting-cancel"', "drawn-strip"):
        assert x in s, x
    assert "UncommittedDialog" not in s and "drawn-search" not in s and "drawn-props\"" not in s
    p = (WEB.parents[2] / "deploy" / "drawio" / "eax-plugin.js").read_text(encoding="utf-8")
    for x in ("function noFormatPanel(", "toggleFormatElement", 'get("format")', "a.visible = false", 'm.eax === "stencil-panel"',
              "eax-stencil-width", "function freeSpot(", "function addRelated(", "function addAllowed(", 'ea_waiting: "1"',
              "eax-waiting-line", "eax-dropped", 'm.eax === "waiting-cancel"'):
        assert x in p, x
    from eax import drawn_views
    assert "a.source_multiplicity AS sm, a.target_multiplicity AS tm" in Path(drawn_views.__file__).read_text(encoding="utf-8")


def test_similar_names_while_creating_from_a_drawn_view():
    """D454: creating from a drawn view shows names already in the model (all types, the shape's type first) with Use
    this one, asks before making a second of the same name and type, and the Bind searches find near spellings."""
    d = _src("DataEntry.jsx")
    for x in ("onUseExisting", 'all_types: "1"', "Already in the model", "Use this one", "already exists as {aOrAn(",
              "Use the existing one", "Create another", "another type, so the shape"):
        assert x in d, x
    v = _src("DrawnView.jsx")
    assert 'import { fuzzyFilter } from "./names"' in v and v.count("fuzzyFilter(") >= 3
    assert "onUseExisting={(x) => { realise(dlg.cell" in v
    n = _src("names.js")
    for x in ("export function closeness", "export function searchScore", "export function fuzzyFilter", "numbers(na) !== numbers(nb)"):
        assert x in n, x


def test_type_dropdowns_search_and_duplicates_tab():
    """D540: every type drop-down of the drawn view is a SearchSelect (typed, fuzzy); D541/D542: Duplicates is its own tab,
    run with a button, says when nothing is found, downloads Excel; Report designer, OData and Merge requests are tabs."""
    d = _src("DrawnView.jsx")
    assert "<select value={panel.type}" not in d and "<select value={msg.type}" not in d and "<select value={sel.type}" not in d
    assert d.count("<SearchSelect") >= 6 and "paletteMatches(groups, setup, palQ)" in d
    # still grouped by domain in the stencil's (ArchiMate) order: the options come from typeGroups, each with its domain,
    # and the picker shows a heading per domain when nothing is typed
    assert "typeGroups(setup).flatMap(([d, ts]) => ts.map(([c, t]) => ({ value: c," in d and "group: d }))" in d
    ss = _src("SearchSelect.jsx")
    for x in ("fuzzyFilter", 'role="combobox"', "search-select-group", "o.group !== lastGroup", 'role="listbox"', "ArrowDown", "Escape", "nativeEvent.stopPropagation"):
        assert x in ss, x
    q = _src("Quality.jsx")
    for x in ("export function Duplicates", "Find duplicates", "No likely duplicates found.", "/duplicates/xlsx?"):
        assert x in q, x
    m = _src("Metamodel.jsx")
    for x in ('["duplicates", "Duplicates", null]', '["designer", "Report designer", null]', '["odata", "Power BI and Excel", null]',
              '["merge-requests", "Merge requests", null]', 'v === "quality" && itemId === "duplicates" ? "duplicates"',
              'v === "reports" && itemId === "designer" ? "designer"'):
        assert x in m, x
    assert '["send", "Send for merge"' in _src("ModelAdmin.jsx")
