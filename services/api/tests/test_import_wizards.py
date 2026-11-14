"""The Import and export wizards (D676): Bring data in and Take data out. Their choices and steps are plain data
(importWizardLists.js, run here with node); the screens are checked for what each step uses. The wizards were also
rendered in Chromium on 14 Nov 2026 with the API answered from fixtures: every path clicked through (a push source made
and its Python kit shown, an upload going to its load's preview, an OData source refused without an address, the folder
source's dialog, read-only people stopped at the first step, each way out) with no error in the console."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _node(expr: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node here")
    script = f"import({json.dumps((WEB / 'importWizardLists.js').as_uri())}).then(m => console.log(JSON.stringify({expr})))"
    out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_bring_in_asks_where_the_data_is_with_every_way_in():
    got = _node("m.BRING_IN.map(c => c[0])")
    assert got == ["file", "folder", "odata", "push", "ai"]


def test_take_out_asks_what_it_is_for_with_every_way_out():
    assert _node("m.TAKE_OUT.map(c => c[0])") == ["edit", "file", "live", "package", "api"]


def test_every_choice_has_a_label_and_a_hint():
    for c in _node("[...m.BRING_IN, ...m.TAKE_OUT]"):
        assert len(c) == 3 and c[1] and len(c[2]) > 20


def test_the_steps_of_each_way_in_end_in_a_review():
    got = _node("Object.fromEntries(m.BRING_IN.map(([k]) => [k, m.bringInSteps(k)]))")
    for kind, names in got.items():
        assert names[0] == "Where is your data?" and names[-1].startswith("Review"), kind
    assert got["push"][2] == "Send it (Python kit)" and got["odata"][2] == "Check the mapping and run"
    assert _node("m.bringInSteps('nonsense')") == got["file"]


def test_the_steps_of_each_way_out():
    got = _node("Object.fromEntries(m.TAKE_OUT.map(([k]) => [k, m.takeOutSteps(k)]))")
    assert got["edit"] == ["What is it for?", "Download the workbook", "Upload it back"]
    assert all(names[0] == "What is it for?" and len(names) == 3 for names in got.values())


def test_the_wizards_use_the_screens_that_do_the_work():
    src = (WEB / "ImportWizards.jsx").read_text(encoding="utf-8")
    for part in ("<Download model={model} m={m}", "<Upload model={model} m={m} may={may} onDone={onClose}",
                 "<SourceDialog model={model} source={{}}", "<SourcePanel id={source.id} model={model}",
                 "/discovery-sources`, { ...form, kind }", "<ODataTab model={model}", "<DownloadDialog m={m}",
                 'href="/api/docs"', 'go(`/metamodel/${model}/import/${where}`)'):
        assert part in src, part
    assert "Bringing data in needs a role that changes the content" in src          # read-only people are stopped first
    assert 'disabled.folder = disabled.folder || "Folder sources are set up by the model\'s Model Admins."' in src


def test_the_wizards_start_from_import_and_export():
    sheets = (WEB / "Sheets.jsx").read_text(encoding="utf-8")
    assert 'import { BringInWizard, TakeOutWizard } from "./ImportWizards";' in sheets
    assert '⬇ Bring data in</button>' in sheets and '⬆ Take data out</button>' in sheets
    assert 'if (onDone) onDone(out.load);' in sheets                               # the upload closes the wizard
    assert 'export function Download({ model, m, format = "xlsx", empty = false })' in sheets
    for name, text in (("Discovery.jsx", "export function SourcePanel("), ("Deliveries.jsx", "export function SourceDialog("),
                       ("GuidedWizards.jsx", "export function Steps(")):
        assert text in (WEB / name).read_text(encoding="utf-8"), name
