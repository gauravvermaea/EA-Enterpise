"""The self-test's journeys that click, type and save (D576, D583): each a list of plain steps, run the same way headless
(here, Playwright) and watched in the admin's own browser (TestRuns.jsx with selfTestDriver.js runs the same steps in
JavaScript), only inside the run's own fixtures (self_test_<id>_n).

A journey: {name, smoke, roles: [allowed roles], refused: {role, ...} | None, why_no_refusal, headless_only, why_headless,
steps}. Each journey runs as every allowed role (smoke: the first only) and is refused to one role that may not (D583).
Steps (one key says what to do; texts may hold {sid} {m} {p} {other} {other_name} {view} {view_name} {entity} {role},
filled from the run's ids, and {$name}, filled from a "remember" step of the same journey):
  {"open": "#/route", "expect": "text"}     open a page, wait for a text (optional)
  {"click": "text"}                          a button, link, tab or label whose text starts with this (first visible);
                                             "exact": true for the whole text, "optional_alt": another text to try
                                             "opens": css of the pop-up it opens (clicked once more if none came)
  {"click_re": "regex"}                      the same, by a regular expression ("^Merge \\d+ accepted")
  {"choose": "text"}                         a radio or checkbox by its label text
  {"fill": "label", "value": "…"}            the field with this label (or placeholder or aria-label)
  {"select": "label", "option": "…"}         a drop-down with this label: the first option starting with the text
                                             ("*": the first real choice, not "(not set)")
  {"press": "F1"}                            a key
  {"expect": "text"} / {"expect_not": "text"} / {"expect_sel": "css"}   ("timeout": ms to wait longer)
  {"open": "#/…", "expect": "text", "reload": true}   opened again every few seconds until it shows (a background task)
  {"upload": "css of the file input", "data": "deliveries/good.xlsx", "name": "good.xlsx"}
                                             a test data file by its manifest key (testbench/data; EAX_TEST_DATA in the
                                             test runner), or "text": inline contents
  {"download": "text"}                       click it; a file must come (headless) or no error show (in a browser)
  {"as": "role"}                             the next pages open as another test role (sending, then reviewing)
  {"remember": "name", "url": "regex"}       wait until the page's address matches; keep its first group as {$name}
  {"popup": "text", "expect": "text"}       click it and carry on in the tab it opens (headless only; D585), until the
                                             next "open", which closes that tab and goes back
  {"drawio_ready": ms} / {"drawio_drop": "TypeCode"} / {"drawio": "js body", "poll": true}
                                             inside the draw.io frame of a drawn view or a picture opened in draw.io
                                             (headless only): wait until the
                                             plugin has set up, drop a placeholder of a type (as the stencil does), or run
                                             a check returning true or why not (ui, g, m, a, cells, txt as in
                                             deploy/drawio/tests/tests.cjs)
  any step may carry "optional": true (skipped if the control is not there), "wait": ms, "within": "css" (inside the
  last visible match, e.g. the pop-up) or "row": "text" (inside the table row, list item or fieldset holding the text).
A refused check (the role that may not): {"open": route, "disabled_or_absent": "button text"}: the button is missing or
disabled, so the save can never be made from the screen (the API matrix checks the same write is refused)."""

from __future__ import annotations

import base64
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

Record = Callable[..., None]

STEP_KINDS = ["open", "click", "click_re", "choose", "fill", "select", "press", "expect", "expect_not", "expect_sel",
              "upload", "download", "as", "remember", "drawio_ready", "drawio_drop", "drawio", "popup"]
DIALOG = "[role=dialog]"

# the drawn-view journey's checks inside draw.io (D583): a shape bound to an entity, found by the name it shows
_SHAPE = "cells().find(c => c.vertex && a(c, 'ea_id') && txt(c).indexOf({n}) >= 0)"
_LINE = "cells().find(c => c.edge && a(c, 'ea_rel_id') && txt(c).indexOf({n}) >= 0)"


def _shape(name: str) -> str:
    return _SHAPE.replace("{n}", repr(name))


def _line(name: str) -> str:
    return _LINE.replace("{n}", repr(name))


JOURNEYS: list[dict] = [
    {"name": "model content: create, edit, history", "smoke": True,
     "roles": ["model-admin", "committer", "architect"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/entry", "select": ("Entity type", "Application Component"),
                 "disabled_or_absent": "+ In a form"},
     "steps": [
         {"open": "#/metamodel/{m}/entry", "expect": "Entity type"},
         {"select": "Entity type", "option": "Application Component"},
         {"click": "+ In a form", "opens": DIALOG},
         {"fill": "Name", "value": "Journey app {sid} {role}"},
         {"fill": "Commit message", "value": "self-test journey", "optional": True},
         {"click": "Save", "exact": True, "optional_alt": "Save and commit"},
         {"fill": "Filter", "value": "Journey app {sid} {role}", "wait": 800},
         {"expect": "Journey app {sid} {role}"},
         {"open": "#/metamodel/{m}/changes", "expect": "Journey app {sid}", "optional": True},
         {"open": "#/metamodel/{m}/history", "optional": True},
     ]},
    {"name": "quality and duplicates: find and merge", "smoke": True, "roles": ["model-admin"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/duplicates", "click_first": "Find duplicates",
                 "disabled_or_absent": "Compare and merge"},
     "steps": [
         {"open": "#/metamodel/{m}/quality", "expect": "Quality"},
         {"open": "#/metamodel/{m}/duplicates", "expect": "Find duplicates"},
         {"click": "Find duplicates", "wait": 1500},
         {"expect": "{dup}"},
         {"click": "Compare and merge"},
         {"click": "Merge 1 into the one kept", "wait": 1500},
         {"expect_not": "Merging…", "timeout": 60000},                 # done (the merge is slower on a laptop)
     ]},
    {"name": "project: iteration, frozen phase, back", "smoke": True, "roles": ["super-admin", "architect"],
     "refused": {"role": "no-role", "open": "#/projects/{p}", "disabled_or_absent": "Change…"},
     "steps": [
         {"open": "#/projects/{p}", "expect": "{project_name}"},
         {"click": "Choose…", "optional_alt": "Change…"},
         {"choose": "Transition Planning"},
         {"fill": "Note (optional)", "value": "self-test {sid} {role}"},
         {"click": "Save", "exact": True},
         {"expect": "Now a Transition Planning"},          # what saving said, in the dialog (it closes after)
         {"expect_not": "Note (optional)", "timeout": 5000},   # the dialog closed: the iteration was saved
         {"expect": "Transition Planning"},
         {"open": "#/projects/{p}/phases/B", "expect": "isn't part of this", "optional": True},
         {"open": "#/projects/{p}", "expect": "{project_name}"},
         {"click": "Change…"},
         {"choose": "Full cycle"},
         {"click": "Save", "exact": True, "wait": 1500},
         {"expect_not": "Note (optional)"},
         {"click": "Iteration history", "optional": True},
         {"expect": "Full cycle"},
     ]},
    # the menu bar (R2.0, D586 to D591): its areas open, a Wizards item goes to the wizards page, / finds a function; the
    # admin areas are not there for a role that may not use them (D588)
    {"name": "the menu bar: areas, wizards and Find", "smoke": True, "roles": ["super-admin"],
     "refused": {"role": "report-viewer", "open": "#/", "disabled_or_absent": "System Admin"},
     "steps": [
         {"open": "#/", "expect": "Architecture Work"},
         {"click": "Architecture Work", "exact": True}, {"expect": "My models"}, {"press": "Escape"},
         {"click": "Model Admin", "exact": True}, {"click": "Wizards", "within": ".tm-area.open"}, {"expect": "Model admin"},
         {"click": "Project Admin", "exact": True}, {"click": "Wizards", "within": ".tm-area.open"}, {"expect": "Project admin"},
         {"click": "System Admin", "exact": True}, {"click": "Wizards", "within": ".tm-area.open"}, {"expect": "Wizards"},
         {"click": "Repository & Content Framework", "exact": True}, {"expect": "Content framework"}, {"press": "Escape"},
         {"press": "/"}, {"expect_sel": ".qj"},
         {"fill": "Find", "value": "backups", "wait": 600}, {"expect": "System Admin"}, {"press": "Escape"},
     ]},
    {"name": "the libraries for everyone: Model library and Project library", "smoke": True,
     "roles": ["architect", "report-viewer"], "refused": None,
     "why_no_refusal": "everyone signed in may open the Model library and the Project library (owner, 12 Nov 2026)",
     "steps": [
         {"open": "#/", "expect": "Architecture Work"},
         {"click": "Architecture Work", "exact": True}, {"click": "Model library", "within": ".tm-area.open"},
         {"expect": "Library"},
         {"click": "Architecture Work", "exact": True}, {"click": "Project library", "within": ".tm-area.open"},
         {"expect": "Project library"},
     ]},
    {"name": "help and documentation", "smoke": False, "roles": ["architect", "report-viewer"], "refused": None,
     "why_no_refusal": "everyone signed in may read the help and the documentation",
     "steps": [
         {"open": "#/metamodel/{m}", "expect": "{model_name}"},
         {"press": "F1"}, {"expect_sel": ".help-panel"}, {"press": "Escape"},
         {"open": "#/projects/{p}", "expect": "{project_name}", "optional": True},
         {"press": "F1"}, {"expect_sel": ".help-panel"}, {"press": "Escape"},
         {"open": "#/documentation", "expect": "Documentation for"},
         {"fill": "Search", "value": "backup", "wait": 800},
         {"expect": "ackup"},
     ]},
    # the real banner and schedules are read first and always put back (admin_guard, run.py), D583
    {"name": "admin: banner and a schedule, put back", "smoke": False, "roles": ["super-admin", "it-admin"],
     "refused": {"role": "architect", "open": "#/admin/banner", "disabled_or_absent": "Save the banner"},
     "guard": "admin",
     "steps": [
         {"open": "#/admin/banner", "expect": "Who sees it"},
         {"fill": "Message", "value": "self_test_{sid} banner ({role}): a self-test, please ignore"},
         {"select": "Who sees it", "option": "IT Admins and Super Admins only"},
         {"click": "Save the banner", "wait": 1500},
         {"expect": "The banner is set."},
         {"expect": "self_test_{sid} banner", "optional": True},          # shown at the top, to admins only
         {"click": "Clear the banner", "wait": 1500},
         {"expect": "The banner is cleared"},
         {"open": "#/admin/commands/schedules", "expect": "New schedule"},
         {"click": "+ New schedule"},
         {"fill": "Name", "value": "self_test_{sid} schedule {role}"},
         {"click": "Make the schedule", "wait": 2000},
         {"expect": "Schedule made"},
         {"click": "Turn off", "row": "self_test_{sid} schedule {role}", "wait": 1500},   # off: it never runs
         {"expect": "Turn on", "row": "self_test_{sid} schedule {role}"},
         {"click": "Remove", "exact": True, "row": "self_test_{sid} schedule {role}", "wait": 1500},   # the confirm is accepted
         # the page says so ("<name>: removed.", which holds the name, so the name alone is no test that it went)
         {"expect": "self_test_{sid} schedule {role}: removed."},
     ]},
    {"name": "drawn view: drop, bind, create, line, undo, save", "smoke": False, "roles": ["model-admin", "committer"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/drawn-views/{view}", "disabled_or_absent": "Save",
                 "exact": True},
     "headless_only": True,
     "why_headless": "the draw.io canvas is a separate site: a page in the admin's browser cannot reach into it",
     "steps": [
         {"open": "#/metamodel/{m}/drawn-views/{view}", "expect": "{view_name}"},
         {"select": "Layout", "option": "Editing", "optional": True},
         {"drawio_ready": 60000},
         # a capability dropped from the stencil, bound to an existing one found with a misspelling (fuzzy, D454)
         {"drawio_drop": "Capability", "x": 640, "y": 380},
         {"expect": "What is this Capability?"},
         {"fill": "Find a Capability", "value": "Self-test capabilty 2", "within": DIALOG, "wait": 1000},
         {"expect": "Self-test capability 2", "within": DIALOG},
         {"click": "Self-test capability 2", "exact": True, "within": DIALOG, "wait": 1500},
         {"drawio": "return !!" + _shape("Self-test capability 2") + " || 'the dropped shape is not bound';", "poll": True},
         # an application created through the pop-up: a near name shows what is already in the model first
         {"drawio_drop": "ApplicationComponent", "x": 380, "y": 560},
         {"expect": "What is this Application Component?"},
         {"click": "Create a new Application Component", "within": DIALOG, "wait": 1200},
         {"fill": "Name", "value": "Self-test application 2x", "within": DIALOG, "wait": 1800},
         {"expect": "Already in the model", "within": DIALOG},
         {"fill": "Name", "value": "Drawn app {sid} {role}", "within": DIALOG, "wait": 800},
         {"fill": "Owner", "value": "Self-test team", "within": DIALOG, "optional": True},     # required in some metamodels
         {"select": "Lifecycle", "option": "*", "within": DIALOG, "optional": True},
         {"click": "Save and commit", "within": DIALOG, "wait": 2500},
         {"drawio": "return !!" + _shape("Drawn app {sid} {role}") + " || 'the new entity is not on the view';", "poll": True},
         # a line drawn between them: the allowed relationship asked for, then named, with a key:value
         {"drawio": "const s = " + _shape("Drawn app {sid} {role}") + ", t = " + _shape("Self-test capability 1") + ";"
                    " if (!s || !t) return 'the two shapes are not on the view';"
                    " g.insertEdge(g.getDefaultParent(), null, '', s, t); return true;"},
         {"expect": "A new relationship"},
         {"fill": "Relationship type", "value": "Association", "within": DIALOG},
         {"press": "Enter"},
         {"fill": "Name (optional)", "value": "feeds {sid} {role}", "within": DIALOG},
         {"click": "Add the relationship", "within": DIALOG, "wait": 2500},
         {"drawio": "return !!" + _line("feeds {sid} {role}") + " || 'the line is not bound to the relationship';", "poll": True},
         {"drawio": "const e = " + _line("feeds {sid} {role}") + "; if (!e) return 'no line'; g.setSelectionCell(e); return true;",
          "wait": 1200},
         {"click": "Properties", "optional": True},
         {"fill": "Relationship name", "value": "serves {sid} {role}"},
         {"fill": "Protocol", "value": "https"},
         {"click": "Save and commit", "wait": 2500},
         {"drawio": "const e = " + _line("serves {sid} {role}") + "; const t = e ? txt(e) : '';"
                    " return t === 'serves {sid} {role} (Association) [Protocol:https]' || ('the line shows ' + JSON.stringify(t));",
          "poll": True},
         # undo and redo of a move
         {"drawio": "const v = " + _shape("Drawn app {sid} {role}") + "; const x = v.geometry.x; g.moveCells([v], 40, 0);"
                    " if (v.geometry.x !== x + 40) return 'it did not move';"
                    " ui.actions.get('undo').funct(); if (v.geometry.x !== x) return 'undo did not put it back';"
                    " ui.actions.get('redo').funct(); return v.geometry.x === x + 40 || 'redo did not move it again';"},
         {"click": "Save", "exact": True, "wait": 3000},
         # opened again: what was saved comes back, the line's label with it
         {"open": "#/metamodel/{m}/views", "optional": True},
         {"open": "#/metamodel/{m}/drawn-views/{view}", "expect": "{view_name}"},
         {"drawio_ready": 60000},
         {"drawio": "const e = " + _line("serves {sid} {role}") + "; const t = e ? txt(e) : '';"
                    " return t === 'serves {sid} {role} (Association) [Protocol:https]' || ('after reopening the line shows ' + JSON.stringify(t));",
          "poll": True},
     ]},
    {"name": "a model's picture in draw.io: its objects and their properties, read only", "smoke": False,
     "roles": ["model-admin"], "refused": None,
     "why_no_refusal": "anyone who may read the model may open its pictures in draw.io; nothing there changes the model",
     "headless_only": True,
     "why_headless": "the picture opens in a new tab with the draw.io canvas, a separate site: a watched run cannot follow it",
     "steps": [                                                         # R2.7 (owner, 11 Nov 2026; read-only panels, 12 Nov)
         {"open": "#/metamodel/{m}/graph", "expect": "Open in draw.io"},
         {"popup": "Open in draw.io", "expect": "not saved", "wait": 1500},
         {"drawio_ready": 60000},
         {"expect": "Objects on this picture"},
         {"click": "Show", "exact": True, "within": ".picture-panels", "wait": 1000},
         {"expect": "Attributes", "within": ".picture-panels"},
         {"drawio": "return !!g.getSelectionCell() || 'Show did not select it on the picture';"},
     ]},
    {"name": "open in draw.io: a picture read only, exported, saved as a drawn view", "smoke": False, "roles": ["model-admin"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/diagram", "disabled_or_absent": "Save as a drawn view"},
     "headless_only": True,
     "why_headless": "the picture opens in a new tab with the draw.io canvas, a separate site: a watched run cannot follow it",
     "steps": [
         {"open": "#/metamodel/{m}/diagram", "expect": "Open in draw.io"},
         {"popup": "Open in draw.io", "expect": "not saved", "wait": 1500},          # D585: our draw.io, a tab of its own
         {"drawio_ready": 60000},
         {"drawio": "return (!g.isCellsMovable() && !g.isConnectable()) || 'the picture is not read only';"},
         {"drawio": "return !!ui.actions.get('eaxExportDrawio') || 'File > Export as has no .drawio file';"},
         {"download": "Download .drawio"},
         {"click": "Save as a drawn view", "exact": True},
         {"fill": "Name", "value": "self_test_{sid} opened {role}", "within": DIALOG},
         {"click": "Save and open", "within": DIALOG, "wait": 3000},
         {"remember": "opened", "url": r"drawn-views/([^/?]+)"},                      # the tab became the drawn view
         {"drawio_ready": 60000},
     ]},
    {"name": "import: upload a delivery, accept, undo", "smoke": False, "roles": ["model-admin"],
     "refused": {"role": "report-viewer", "open": "#/metamodel/{m}/import/deliveries", "disabled_or_absent": "+ Add a source"},
     "steps": [
         {"open": "#/metamodel/{m}/import/deliveries", "expect": "Sources"},
         {"click": "+ Add a source"},
         {"fill": "Name", "value": "self_test_{sid} source {role}", "within": DIALOG},
         {"click": "Save", "exact": True, "within": DIALOG, "wait": 1500},
         {"expect": "self_test_{sid} source {role}"},
         {"upload": "input[type=file]", "row": "self_test_{sid} source {role}", "data": "deliveries/good.xlsx",
          "name": "good.xlsx", "wait": 3000},
         {"expect": "Accept and commit", "timeout": 240000},            # previewed in the background (a busy job queue)
         {"click": "Accept and commit", "wait": 3000},
         {"expect": "Undo the load", "timeout": 90000},                 # accepted: committed as the load
         {"click": "Undo the load", "wait": 3000},                      # the confirm is accepted
         {"expect_not": "Undo the load", "timeout": 30000},
     ]},
    {"name": "survey: make, send, answer, Excel", "smoke": False, "roles": ["super-admin", "model-creator"],
     "refused": {"role": "architect", "open": "#/surveys", "disabled_or_absent": "＋ New survey"},
     "steps": [
         {"open": "#/surveys", "expect": "Surveys"},
         {"fill": "New survey title", "value": "self_test_{sid} survey {role}"},
         {"click": "＋ New survey", "wait": 1500},
         {"remember": "survey", "url": r"#/surveys/([^/?#]+)"},
         {"expect": "Who it is for"},
         {"click": "＋ Section"},
         {"click": "＋ Question"},
         {"fill": "What do you want to ask?", "value": "Is the self-test working?"},
         {"fill": "Option 1", "value": "Yes"},
         {"fill": "Option 2", "value": "No"},
         {"click": "Save questions", "wait": 1500},
         {"fill": "Person", "value": "svc-self-test-{sid}-architect"},
         {"click": "Add", "exact": True, "wait": 1500},
         {"click": "Send", "exact": True, "wait": 2000},                # the confirm is accepted
         {"expect": "Sent:"},
         {"as": "architect"},                                           # the person asked answers it
         {"open": "#/surveys/{$survey}/answer", "expect": "Is the self-test working?"},
         {"choose": "Yes"},
         {"click": "Send my answers", "wait": 2000},
         {"as": "{role}"},
         {"open": "#/surveys/{$survey}/results", "expect": "Results:"},
         {"download": "⬇ Excel"},
         {"open": "#/surveys/{$survey}", "expect": "self_test_{sid} survey"},
         {"click": "Close", "exact": True, "wait": 1500},               # closed: nobody else is asked
     ]},
    {"name": "child merge: send, accept, refresh", "smoke": False, "roles": ["super-admin"],
     "refused": {"role": "architect", "open": "#/model-admin/{other}/send", "disabled_or_absent": "Preview and send…"},
     "steps": [
         {"open": "#/metamodel/{other}/entry", "expect": "Entity type"},
         {"select": "Entity type", "option": "Application Component"},
         {"click": "+ In a form", "opens": DIALOG},
         {"fill": "Name", "value": "Merged app {sid} {role}"},
         {"click": "Save", "exact": True, "optional_alt": "Save and commit", "wait": 1500},
         {"open": "#/metamodel/{other}/changes", "optional": True},
         {"click": "Commit all", "optional": True, "wait": 2500},
         {"open": "#/model-admin/{other}/send", "expect": "for merge into"},
         {"click": "Preview and send…", "wait": 2000},
         {"click": "Send for merge", "within": DIALOG, "wait": 4000},
         {"click": "Open the request", "within": DIALOG, "wait": 2000, "timeout": 90000},   # once the send is done
         {"remember": "mr", "url": r"#/merge-requests/([^/?#]+)"},
         {"as": "model-admin"},                                         # the parent's Model Admin reviews and merges
         {"open": "#/merge-requests/{$mr}", "expect": "Merge request"},
         {"click_re": r"^Merge \d+ accepted", "wait": 4000},
         {"expect": "Merged", "timeout": 90000},
         {"as": "{role}"},                                              # the child's admin refreshes the child
         # the merge finishes in the background: opened again until it shows (the laptop's full run, 12 Nov 2026)
         {"open": "#/merge-requests/{$mr}", "expect": "What happens to", "reload": True, "timeout": 180000},
         {"click": "Refresh {other_name}", "wait": 4000},
         {"expect": "now holds what", "timeout": 90000},             # the refresh's own message (the task's result)
     ]},
]

# what a journey needs from the run's fixtures, by the placeholders its steps use: left out when the run has none
NEEDS = {"project": ("{p}", "{project_name}"), "view": ("{view}", "{view_name}"), "other_model": ("{other}", "{other_name}")}


def data_folder() -> Path:
    """The test data (testbench/data, D580): EAX_TEST_DATA in the test runner (/testdata), else this checkout's."""
    env = os.environ.get("EAX_TEST_DATA", "").strip()
    if env:
        return Path(env)
    if Path("/testdata/manifest.json").is_file():
        return Path("/testdata")
    here = Path(__file__).resolve().parents
    return here[4] / "testbench" / "data" if len(here) > 4 else Path("/testdata")   # in a container: /app/eax/testing


def data_bytes(name: str) -> bytes:
    """A test data file by its manifest key ("deliveries/good.xlsx")."""
    p = (data_folder() / name).resolve()
    if data_folder().resolve() not in p.parents:
        raise ValueError(f"{name}: not in the test data folder")
    return p.read_bytes()


def fill_text(s: str, ids: dict[str, str], role: str) -> str:
    vals = {"sid": ids.get("sid", ""), "m": ids.get("model", ""), "p": ids.get("project", ""), "other": ids.get("other_model", ""),
            "other_name": ids.get("other_name", ""), "view": ids.get("view", ""), "view_name": ids.get("view_name", ""),
            "entity": ids.get("entity", ""), "model_name": ids.get("model_name", ""), "project_name": ids.get("project_name", ""),
            "role": role, "dup": ids.get("dup", "Self-test duplicate")}
    for k, v in vals.items():
        s = s.replace("{" + k + "}", v)
    return s


def key(j: dict) -> str:
    """What --journey takes for a journey: its name up to the colon ("model content", "drawn view"). Unique (unit tested)."""
    return j["name"].split(":")[0].strip()


def missing(j: dict, ids: dict[str, str]) -> list[str]:
    """The fixtures a journey needs that this run has not got (a project, a drawn view, the child model)."""
    text = str(j["steps"]) + str(j.get("refused") or "")
    return [k for k, marks in NEEDS.items() if any(x in text for x in marks) and not ids.get(k)]


def role_plan(j: dict, role: str = "", smoke: bool = False) -> list[tuple[str, bool]]:
    """Who a journey runs as (D583): [(role, refused)]. Every allowed role and then the one refused; smoke the first
    allowed role only; with --role, that role (refused when it may not, skipped when the journey refuses nobody)."""
    if role:
        if role in j["roles"] or (role == "super-admin" and not j.get("refused")):
            return [(role, False)]
        ref = j.get("refused")
        return [(role, True)] if ref else []
    if smoke:
        return [(j["roles"][0], False)]
    out = [(r, False) for r in j["roles"]]
    if j.get("refused"):
        out.append((j["refused"]["role"], True))
    return out


def journeys(ids: dict[str, str], role: str = "", only: list[str] | None = None, smoke: bool = False,
             watch: bool = False) -> list[dict]:
    """The journeys to run: [{name, role, steps, refused, headless_only, …}], one per role of role_plan, filled.
    Journeys needing a fixture the run has not got are left out. watch=True leaves out the headless ones and puts the
    data files in (base64), as the admin's browser cannot read them."""
    out = []
    for j in JOURNEYS:
        if smoke and not j["smoke"]:
            continue
        if only and not any(o.lower() in j["name"].lower() for o in only):
            continue
        if watch and j.get("headless_only"):
            continue
        if missing(j, ids):
            continue
        plan = role_plan(j, role, smoke)
        allowed = [r for r, refused in plan if not refused]
        for r, refused in plan:
            if refused:
                ref = dict(j["refused"], role=r)
                name = f"{j['name']} (refused)" if role else f"{j['name']}: refused to {r}"
                out.append({"name": name, "role": r, "refusal": _fill_obj(ref, ids, r), "steps": []})
                continue
            steps = [_fill_obj(s, ids, r) for s in j["steps"]]
            if watch:
                steps = [_with_data(s) for s in steps]
            out.append({"name": j["name"] + ("" if len(allowed) == 1 else f" as {r}"), "role": r, "steps": steps,
                        "headless_only": j.get("headless_only", False), "guard": j.get("guard", "")})
    return out


def _with_data(s: dict) -> dict:
    if "upload" in s and s.get("data"):
        try:
            return {**s, "b64": base64.b64encode(data_bytes(s["data"])).decode()}
        except (OSError, ValueError, IndexError):      # no test data folder: the step then says the file is missing
            return s
    return s


def _fill_obj(o, ids, role):
    if isinstance(o, str):
        return fill_text(o, ids, role)
    if isinstance(o, dict):
        return {k: _fill_obj(v, ids, role) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_fill_obj(v, ids, role) for v in o]
    return o


def skipped_in_browser() -> list[str]:
    """The journeys the watched-in-your-browser mode leaves out, with why (shown on the report)."""
    return [f"{j['name']}: {j['why_headless']}" for j in JOURNEYS if j.get("headless_only")]


# ---------------------------------------------------------------- the real settings an admin journey changes (D583)
def admin_snapshot(call: Callable[..., tuple]) -> dict:
    """The banner and the schedules as they are, before the admin journey changes them. call(method, path, body=None)
    gives (status, answer) as a Super Admin."""
    _st, b = call("GET", "/api/v1/admin/banner")
    _st2, sc = call("GET", "/api/v1/admin/commands/schedules")
    return {"banner": (b or {}).get("banner") if isinstance(b, dict) else None,
            "schedules": [x.get("id") for x in ((sc or {}).get("schedules") or [])] if isinstance(sc, dict) else []}


BANNER_FIELDS = ("text", "link", "link_text", "level", "audience", "dismissible", "starts", "ends")


def admin_restore(call: Callable[..., tuple], before: dict, sid: str) -> list[str]:
    """Puts the banner back as it was and removes any schedule the journey made (named self_test_<id>). Returns what
    it did, for the log. Never touches a schedule that was there before."""
    done: list[str] = []
    _st, b = call("GET", "/api/v1/admin/banner")
    now = (b or {}).get("banner") if isinstance(b, dict) else None
    was = before.get("banner")
    if was and (not now or {k: now.get(k) for k in BANNER_FIELDS} != {k: was.get(k) for k in BANNER_FIELDS}):
        call("PUT", "/api/v1/admin/banner", {k: was.get(k) for k in BANNER_FIELDS if was.get(k) is not None})
        done.append("banner put back")
    elif not was and now and str(now.get("text", "")).startswith(f"self_test_{sid}"):
        call("DELETE", "/api/v1/admin/banner")
        done.append("the self-test banner cleared")
    _st2, sc = call("GET", "/api/v1/admin/commands/schedules")
    for x in ((sc or {}).get("schedules") or []) if isinstance(sc, dict) else []:
        if x.get("id") not in before.get("schedules", []) and str(x.get("name", "")).startswith(f"self_test_{sid}"):
            call("POST", f"/api/v1/admin/commands/schedules/{x['id']}/remove", {})
            done.append(f"schedule {x.get('name')} removed")
    return done


# ---------------------------------------------------------------- running a journey with Playwright (headless)

_CLICKABLE = "button, a, [role=tab], [role=button], [role=option], summary, label"
_ROWS = "tr, li, fieldset, .chip"
_DRAWIO = ("const ui = window.eaxEditorUi, g = ui.editor.graph, m = g.getModel();"
           " const a = (c, n) => c && c.value && c.value.getAttribute ? c.value.getAttribute(n) : null;"
           " const F = (id) => ui.eax.findEntity(id), R = (id) => ui.eax.findRelationship(id);"
           " const cells = () => Object.values(m.cells);"
           " const txt = (c) => String(g.convertValueToString(c) || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();")


def _visible(loc):
    try:
        return loc.is_visible()
    except Exception:  # noqa: BLE001
        return False


def _root(page, s: dict):
    """Where a step looks: the page, the last visible pop-up ("within"), or the row holding a text ("row")."""
    if s.get("within"):
        loc = page.locator(s["within"])
        for i in reversed(range(min(loc.count(), 10))):
            if _visible(loc.nth(i)):
                return loc.nth(i)
        return None
    if s.get("row"):
        loc = page.locator(_ROWS).filter(has_text=s["row"])
        for i in range(min(loc.count(), 20)):
            if _visible(loc.nth(i)):
                return loc.nth(i)
        return None
    return page


def _modal(page):
    """The open pop-up dialog (EA Explorer's Modal, drawn last on the page), or None. While one is open the page behind
    it cannot be clicked, so a step's button, choice or field is looked for in it first (the laptop's full run, 12 Nov
    2026: a project page's own Save or a label with the same words came before the iteration dialog's)."""
    try:
        loc = page.locator(".ed-dialog[role=dialog]")
        for i in reversed(range(min(loc.count(), 5))):
            if _visible(loc.nth(i)):
                return loc.nth(i)
    except Exception:  # noqa: BLE001 - a page still loading has none
        return None
    return None


def _in_modal_first(page, root, s: dict, find):
    """find(where) in the open dialog when the step names no "within" or "row", else (and when not there) in root."""
    if root is page and not s.get("within") and not s.get("row"):
        m = _modal(page)
        if m is not None:
            got = find(m)
            if got is not None:
                return got
    return find(root)


def _clickable(page, text: str, exact: bool = False, pattern: str = ""):
    pat = re.compile(pattern) if pattern else re.compile(rf"^\s*{re.escape(text)}\s*$" if exact else rf"^\s*{re.escape(text)}", re.I)
    loc = page.locator(_CLICKABLE).filter(has_text=pat)
    for i in range(min(loc.count(), 20)):
        el = loc.nth(i)
        if _visible(el):
            return el
    return None


def _enabled(el, wait_ms: int = 30000) -> bool:
    """True once the control is enabled, waiting up to wait_ms: some are enabled only when their page has loaded or laid
    out what they act on (Open in draw.io on a picture, R2.0.1)."""
    end = time.time() + wait_ms / 1000
    while True:
        try:
            if not el.is_disabled():
                return True
        except Exception:  # noqa: BLE001 - gone from the page: let the step say so
            return False
        if time.time() > end:
            return False
        time.sleep(0.25)


def _field(page, label: str):
    """The first visible field to type into with this label or placeholder: an exact label first, and never a checkbox,
    radio or button whose label merely starts the same ("Person" is not "Personal details", R2.0.1)."""
    def fillable(el) -> bool:
        try:
            return el.evaluate("e => e.isContentEditable || e.tagName === 'TEXTAREA' || e.tagName === 'SELECT' || "
                               "(e.tagName === 'INPUT' && !/^(checkbox|radio|button|submit|hidden|file)$/i.test(e.type))")
        except Exception:  # noqa: BLE001
            return False
    for loc in (page.get_by_label(label, exact=True), page.get_by_label(label, exact=False),
                page.get_by_placeholder(label, exact=False)):
        for i in range(min(loc.count(), 10)):
            if _visible(loc.nth(i)) and fillable(loc.nth(i)):
                return loc.nth(i)
    return None


def _shows(root, text: str, timeout: int) -> None:
    """Waits for the text to show somewhere visible (the same words in a hidden menu option do not count)."""
    root.locator(f"text={text} >> visible=true").first.wait_for(state="visible", timeout=timeout)


def _drawio_frame(page):
    for fr in page.frames:
        if fr is page.main_frame:
            continue
        try:
            if fr.evaluate("() => !!window.eaxEditorUi"):
                return fr
        except Exception:  # noqa: BLE001 - a frame still loading
            continue
    return None


def _drawio(page, body: str, poll: bool, timeout: int):
    """Runs a check inside draw.io: true when done, else why not (retried until the time is up when poll)."""
    end = time.time() + timeout / 1000
    why = "the draw.io frame is not there"
    while True:
        fr = _drawio_frame(page)
        if fr is not None:
            try:
                out = fr.evaluate("() => { " + _DRAWIO + " " + body + " }")
                if out is True:
                    return ""
                why = str(out) if out else "false"
            except Exception as exc:  # noqa: BLE001 - not set up yet
                why = str(exc).splitlines()[0][:200]
        if not poll or time.time() >= end:
            return why
        page.wait_for_timeout(400)


def drop_script(type_code: str, x: int = 600, y: int = 400) -> str:
    """A placeholder of a type put on the canvas the way the stencil drops one (the plugin then asks what it is)."""
    t = repr(type_code)
    return ("const o = mxUtils.createXmlDocument().createElement('object');"
            f" o.setAttribute('label', {t}); o.setAttribute('ea_type', {t}); o.setAttribute('ea_placeholder', '1');"
            f" const v = new mxCell(o, new mxGeometry({int(x)}, {int(y)}, 120, 60), 'dashed=1;'); v.vertex = true;"
            " g.importCells([v], 0, 0, g.getDefaultParent()); return true;")


def with_vars(o, vars_: dict[str, str]):
    """{$name} filled from what a "remember" step kept."""
    if isinstance(o, str):
        for k, v in vars_.items():
            o = o.replace("{$" + k + "}", v)
        return o
    if isinstance(o, dict):
        return {k: with_vars(v, vars_) for k, v in o.items()}
    if isinstance(o, list):
        return [with_vars(v, vars_) for v in o]
    return o


def step(page, s: dict, open_route: Callable[..., None], state: dict | None = None) -> str:
    """Runs one step; returns "" when done, or why it could not be done (an optional step is then skipped). state keeps
    the role pages open as ("as") and what was remembered."""
    state = state if state is not None else {}
    s = with_vars(s, state.setdefault("vars", {}))
    if re.search(r"\{\$[a-z_]+\}", str(s)):
        return "a {$name} no earlier step remembered"
    timeout = int(s.get("timeout", 20000))
    if state.get("tab") is not None and "open" in s:   # back from a tab a "popup" step opened
        _close_tab(state)
    page = state.get("tab") or page
    root = _root(page, s)
    if root is None:
        return f"nothing shows {s.get('within') or s.get('row')}"
    if "as" in s:
        state["role"] = s["as"]
    elif "open" in s:
        if state.get("role"):
            open_route(s["open"], state["role"])
        else:
            open_route(s["open"])
        if s.get("expect") and s.get("reload"):        # what a background task changes: opened again until it shows
            end = time.time() + max(timeout, 60000) / 1000
            while True:
                try:
                    _shows(page, s["expect"], 8000)
                    break
                except Exception:  # noqa: BLE001
                    if time.time() > end:
                        raise
                    # a real reload: opening the same address again only moves to its #fragment in the same page, which
                    # fetches nothing, so the page never saw the background task finish (the full self-test, 13 Nov
                    # 2026: child merge, step 18, 180 seconds on the request as it was before the merge)
                    page.reload(wait_until="domcontentloaded", timeout=60000)
        elif s.get("expect"):                          # a full-page screen (a drawn view) has no EA Explorer header
            _shows(page, s["expect"], max(timeout, 60000))
        else:
            page.wait_for_selector("text=EA Explorer", timeout=60000)
    elif "popup" in s:                                # before "expect": it carries one too
        el = _clickable(root, s["popup"])
        if el is None:
            return f"no button or link \"{s['popup']}\""
        if not _enabled(el):
            return f"\"{s['popup']}\" is disabled"
        with page.context.expect_page(timeout=timeout) as pg:
            el.click()
        tab = pg.value
        tab.wait_for_load_state()
        state["tab"] = tab
        if s.get("expect"):
            _shows(tab, s["expect"], max(timeout, 60000))
    elif "click" in s or "click_re" in s:
        what = s.get("click") or s.get("click_re")
        # wait for it to appear: a button that comes with what a step loads (+ In a form once the entity type's rows
        # are in) is later on a slower machine (R2.0.1, the laptop's smoke run); an optional step waits less
        end = time.time() + (3 if s.get("optional") else timeout / 1000)
        while True:
            el = _in_modal_first(page, root, s, lambda w: _clickable(w, s.get("click", ""), s.get("exact", False), s.get("click_re", "")))
            if el is None and s.get("optional_alt"):
                el = _in_modal_first(page, root, s, lambda w: _clickable(w, s["optional_alt"]))
            if el is not None or time.time() > end:
                break
            page.wait_for_timeout(300)
        if el is None:
            return f"no button or link \"{what}\""
        if not _enabled(el):
            return f"\"{what}\" is disabled"
        el.click()
        if s.get("opens"):                             # a click that opens a pop-up: once more if the page was still
            try:                                       # settling and the first click was lost (the laptop's full run)
                page.wait_for_selector(s["opens"], timeout=5000)
            except Exception:  # noqa: BLE001
                el = _clickable(root, s.get("click", ""), s.get("exact", False), s.get("click_re", ""))
                if el is None or not _enabled(el):
                    return f"\"{what}\" opened nothing"
                el.click()
                page.wait_for_selector(s["opens"], timeout=timeout)
    elif "choose" in s:
        def label(w):
            lab = w.locator("label").filter(has_text=s["choose"])
            for i in range(min(lab.count(), 10)):
                if _visible(lab.nth(i)):
                    return lab.nth(i)
            return None
        loc = _in_modal_first(page, root, s, label)
        if loc is None:
            return f"no choice \"{s['choose']}\""
        loc.click()
        box = loc.locator("input[type=radio], input[type=checkbox]")
        if box.count() and box.first.get_attribute("type") == "radio" and not box.first.is_checked():
            box.first.check()                          # the click landed on the label's text but not its radio
        if box.count() and box.first.get_attribute("type") == "radio" and not box.first.is_checked():
            return f"\"{s['choose']}\" was not chosen"
    elif "fill" in s:
        end = time.time() + (3 if s.get("optional") else timeout / 1000)
        el = _in_modal_first(page, root, s, lambda w: _field(w, s["fill"]))
        while el is None and time.time() < end:        # a field that comes with a pop-up or the page's data
            page.wait_for_timeout(300)
            el = _in_modal_first(page, root, s, lambda w: _field(w, s["fill"]))
        if el is None:
            return f"no field \"{s['fill']}\""
        el.fill(s["value"])
    elif "select" in s:
        # wait for the drop-down and its choices: they come with what the page loads (the entity types of the model's
        # metamodel), later on a slower machine (R2.0.1, the laptop's smoke run)
        end = time.time() + timeout / 1000
        while True:
            el = _field(root, s["select"])
            pick = None
            if el is not None:
                opts = el.locator("option").all_inner_texts()
                if s["option"] == "*":                 # any real choice: the first that is not "(not set)"
                    pick = next((o for o in opts if o.strip() and not o.strip().startswith(("(", "Choose"))), None)
                else:
                    pick = next((o for o in opts if o.strip().lower().startswith(s["option"].lower())), None)
            if pick is not None or time.time() > end:
                break
            page.wait_for_timeout(300)
        if el is None:
            return f"no drop-down \"{s['select']}\""
        if pick is None:
            return f"\"{s['select']}\" has no option \"{s['option']}\""
        el.select_option(label=pick)
    elif "press" in s:
        page.keyboard.press(s["press"])
    elif "expect" in s:
        _shows(root, s["expect"], timeout)
    elif "expect_not" in s:
        end = time.time() + int(s.get("timeout", 500)) / 1000
        while True:
            page.wait_for_timeout(500)
            if not page.locator(f"text={s['expect_not']} >> visible=true").count():
                break
            if time.time() >= end:
                return f"\"{s['expect_not']}\" still shows"
    elif "expect_sel" in s:
        page.wait_for_selector(s["expect_sel"], timeout=timeout)
    elif "upload" in s:
        try:
            content = data_bytes(s["data"]) if s.get("data") else str(s.get("text", "")).encode()
        except OSError as exc:
            return f"no test data file {s.get('data')}: {exc}"
        root.locator(s["upload"]).first.set_input_files(files=[{"name": s.get("name") or Path(s.get("data", "file")).name,
                                                                "mimeType": "application/octet-stream", "buffer": content}])
    elif "download" in s:
        el = _clickable(root, s["download"])
        if el is None:
            return f"no button or link \"{s['download']}\""
        with page.expect_download(timeout=timeout) as d:
            el.click()
        path = d.value.path()
        if not path or Path(path).stat().st_size == 0:
            return f"\"{s['download']}\" gave an empty file"
    elif "remember" in s:
        end = time.time() + timeout / 1000
        while True:
            hit = re.search(s["url"], page.url)
            if hit:
                state["vars"][s["remember"]] = hit.group(1)
                break
            if time.time() >= end:
                return f"the address never matched {s['url']} (it is {page.url})"
            page.wait_for_timeout(300)
    elif "drawio_ready" in s:
        why = _drawio(page, "return !!(ui.eax && cells().some(c => a(c, 'ea_id'))) || 'not set up yet';", True,
                      int(s["drawio_ready"]) or 60000)
        if why:
            return f"draw.io did not set up: {why}"
        page.wait_for_timeout(1000)
    elif "drawio_drop" in s:
        why = _drawio(page, drop_script(s["drawio_drop"], s.get("x", 600), s.get("y", 400)), False, timeout)
        if why:
            return f"could not drop a {s['drawio_drop']}: {why}"
    elif "drawio" in s:
        why = _drawio(page, s["drawio"], bool(s.get("poll")), timeout)
        if why:
            return why
    page.wait_for_timeout(s.get("wait", 400))
    return ""


def refusal(page, r: dict, open_route: Callable[..., None]) -> tuple[str, str]:
    """The role that may not: the button that would save is missing or disabled."""
    open_route(r["open"])
    try:                                             # a page that fills the window (a drawn view) has no header to wait for
        page.wait_for_selector("text=EA Explorer", timeout=30000)
    except Exception:  # noqa: BLE001
        page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    if r.get("select"):                              # its choices come with the page's data: wait for them (20 s)
        end, pick, el = time.time() + 20, None, None
        while pick is None and time.time() < end:
            el = _field(page, r["select"][0])
            if el is not None:
                opts = el.locator("option").all_inner_texts()
                pick = next((o for o in opts if o.strip().lower().startswith(r["select"][1].lower())), None)
            if pick is None:
                page.wait_for_timeout(300)
        if el is not None and pick:
            el.select_option(label=pick)
            page.wait_for_timeout(3000)
    if r.get("click_first"):
        el = _clickable(page, r["click_first"])
        if el is not None and not el.is_disabled():
            el.click()
            page.wait_for_timeout(1500)
    el = _clickable(page, r["disabled_or_absent"], bool(r.get("exact")))
    if el is None:
        return "passed", f"\"{r['disabled_or_absent']}\" not offered to {r.get('role', 'this role')}"
    if el.is_disabled():
        return "passed", f"\"{r['disabled_or_absent']}\" disabled for {r.get('role', 'this role')}"
    return "failed", f"\"{r['disabled_or_absent']}\" is offered to {r.get('role', 'this role')}, who may not do it"


def _close_tab(state: dict) -> None:
    tab = state.pop("tab", None)
    try:
        if tab is not None and not tab.is_closed():
            tab.close()
    except Exception:  # noqa: BLE001 - already gone
        pass


_LAST_SHOT: dict = {}


def run_one(page, j: dict, open_route: Callable[..., None]) -> tuple[str, str]:
    """Runs one journey on a page; returns (outcome, detail)."""
    if j.get("refusal"):
        return refusal(page, j["refusal"], open_route)
    done, skipped = 0, []
    state: dict = {"vars": {}}
    try:
        for s in j["steps"]:
            try:
                why = step(page, s, open_route, state)
            except Exception as exc:  # noqa: BLE001 - a step that times out is a failed step
                why = str(exc).splitlines()[0][:200]
            if why:
                if s.get("optional"):
                    skipped.append(why)
                    continue
                try:   # the tab the step failed in, before it is closed (a "popup" step's tab), for the report
                    _LAST_SHOT["png"] = (state.get("tab") or page).screenshot(full_page=False)
                except Exception:  # noqa: BLE001
                    _LAST_SHOT["png"] = None
                return "failed", f"step {done + len(skipped) + 1} ({_say(s)}): {why}{_page_says(state.get('tab') or page)}"
            done += 1
    finally:
        _close_tab(state)                              # a tab a "popup" step opened
    return "passed", f"{done} steps as {j['role']}" + (f"; {len(skipped)} optional skipped" if skipped else "")


def _page_says(page) -> str:
    """What the page showed when a step failed (its address, heading, and status lines), so the report says what was
    there instead of only what was missing."""
    try:
        said = page.evaluate("""() => {
            const t = (sel) => [...document.querySelectorAll(sel)].map((e) => (e.innerText || "").trim()).filter(Boolean);
            return { at: location.hash || location.pathname, h1: t("h1").slice(0, 1),
                     status: t(".status, .rag, .error, [role=alert]").slice(0, 3) };
        }""")
        parts = [f"at {said['at']}"] + [f"heading \"{x[:80]}\"" for x in said["h1"]] + [f"\"{x[:100]}\"" for x in said["status"]]
        return " · the page showed: " + ", ".join(parts)
    except Exception:  # noqa: BLE001 - the page is gone
        return ""


def _say(s: dict) -> str:
    k = next(iter(s))
    v = str(s[k])
    return f"{k} {v[:80]}{'…' if len(v) > 80 else ''}"


def run(page_factory: Callable[[str], tuple], js: list[dict], record: Record) -> dict[str, int]:
    """Runs the journeys; page_factory(role) gives (page, open_route, close) for that role's browser context;
    open_route(route, role=None) opens a route, as another test role when given."""
    counts = {"journeys": 0, "passed": 0, "failed": 0}
    for j in js:
        t0 = time.time()
        _LAST_SHOT.clear()
        page, open_route, close = page_factory(j["role"])
        errors: list[str] = []
        page.on("pageerror", lambda e, errs=errors: errs.append(f"script error: {str(e)[:200]}"))
        page.on("response", lambda r, errs=errors: errs.append(f"{r.request.method} {r.url.split('?')[0]}: {r.status}")
                if "/api/" in r.url and r.status >= 500 else None)
        try:
            outcome, detail = run_one(page, j, open_route)
        except Exception as exc:  # noqa: BLE001
            outcome, detail = "failed", str(exc).splitlines()[0][:300]
        if outcome == "passed" and errors:
            outcome, detail = "failed", "; ".join(errors[:5])
        shot = _LAST_SHOT.pop("png", None) if outcome == "failed" else None   # the tab the failing step was in
        if outcome == "failed" and shot is None:
            try:
                shot = page.screenshot(full_page=False)
            except Exception:  # noqa: BLE001
                shot = None
        video = close(outcome)
        counts["journeys"] += 1
        counts[outcome] = counts.get(outcome, 0) + 1
        record(f"journey: {j['name']}", outcome, detail, int((time.time() - t0) * 1000), screenshot=shot, video=video or "")
    return counts
