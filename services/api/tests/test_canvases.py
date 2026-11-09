"""Business Model Canvases (D344): what they promise, without a database."""
import io
import zipfile
from pathlib import Path

from eax import canvases as cv
from eax import project_backup

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def _i(i, block, text, lineage, note=""):
    return {"id": f"i{i}", "block": block, "text": text, "note": note, "lineage": lineage, "sort_order": i}


def test_nine_blocks_in_the_classic_layout():
    assert len(cv.BLOCKS) == 9 and set(cv._boxes()) == set(cv.BLOCK_KEYS)
    assert set(cv.KINDS) == {"current", "target", "working", "scenario"}


def test_diff_by_lineage_then_text():
    a = [_i(1, "channels", "Branches", "L1"), _i(2, "channels", "Call centre", "L2"), _i(3, "value_propositions", "Paid in 20 days", "L3"),
         _i(4, "customer_segments", "Brokers", "L4")]
    b = [_i(5, "channels", "Call centre", "L2"), _i(6, "channels", "Mobile app", "L9"), _i(7, "value_propositions", "Paid in 5 days", "L3"),
         _i(8, "customer_segments", "Brokers", "other lineage")]
    d = cv.diff(a, b)
    states = {(r["text"], r["state"]) for rows in d.values() for r in rows}
    assert ("Branches", "removed") in states and ("Mobile app", "added") in states and ("Call centre", "same") in states
    assert ("Brokers", "same") in states                         # matched by its text in the same block
    changed = next(r for r in d["value_propositions"] if r["state"] == "changed")
    assert changed["text"] == "Paid in 5 days" and changed["was_text"] == "Paid in 20 days"


def _view():
    return {"title": "Claims <today>", "subtitle": "Working copy", "blocks": {
        "channels": [{"state": "removed", "text": "Branches", "note": "", "was_text": ""},
                     {"state": "added", "text": "Mobile app & web", "note": "photos", "was_text": ""}],
        "value_propositions": [{"state": "changed", "text": "5 days", "note": "", "was_text": "20 days"}]}}


def test_exports_are_files():
    pdf = cv._pdf(_view())
    assert pdf.startswith(b"%PDF")
    pptx = cv._pptx(_view())
    z = zipfile.ZipFile(io.BytesIO(pptx))
    slide = z.read("ppt/slides/slide1.xml").decode()
    assert 'strike="sngStrike"' in slide and "Mobile app &amp; web" in slide and "Claims &lt;today&gt;" in slide
    xml = cv._drawio(_view())
    assert xml.startswith("<mxfile") and "fontStyle=8" in xml and "&lt;s&gt;20 days&lt;/s&gt;" in xml


def test_tables_backup_and_tab():
    sql = (ROOT / "migrations" / "sql" / "0032_repository_tags.sql").read_text()
    for t in ("canvases", "canvas_items", "canvas_events", "canvas_documents"):
        assert f"CREATE TABLE proj.{t} " in sql
        assert t in [x for x, _w, _m in project_backup.TABLES]
    tabs = [x for x, _w, _m in project_backup.TABLES]
    assert tabs.index("canvas_documents") > tabs.index("documents")
    assert '["canvas", "Business model canvas"]' in (WEB / "Projects.jsx").read_text()


def test_sample_canvases_show_every_kind():
    src = (ROOT / "eax" / "seed" / "sample_canvases.py").read_text()
    for kind in ('"kind": "current"', '"kind": "target"', '"kind": "working"', '"kind": "scenario"', "from_compare", "clean_up",
                 "remove_item", "change_item", "add_document", '"status": "agreed"'):
        assert kind in src, kind
