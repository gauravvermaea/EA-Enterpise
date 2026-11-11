"""The industry packs' files (phase 39; owner 10 Nov 2026, D546 to D549): classifying, zips and parts, the AI-use check,
the checksum skip, the tiles, the collect step of `eax packs`, the API's rights and the shipped folder."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

from eax import industry_packs as ip

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = ROOT / "library" / "industry-packs"


def _xlsx(text: str) -> bytes:
    """A tiny Office-like file (a zip of XML), enough for the checks."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst><si><t>{text}</t></si></sst>")
    return b.getvalue()


def test_classify_by_name():
    c = ip.classify
    assert c("Retail - a starter pack for enterprise architects.pdf") == "book"
    assert c("Retail - the architecture workbook.pdf") == "workbook"
    assert c("00 READ ME FIRST - what is in this set.pdf") == "readme"
    assert c("Banking - read me first.pdf") == "readme"
    assert c("Retail_TOGAF_Metamodel.xlsx") == "metamodel"
    assert c("Retail_EA_Metamodel_TEMPLATE.xlsx") == "metamodel_template"
    assert c("Retail_ArchiMate4_Views.pptx") == "example_views"
    assert c("Retail_EA_Maturity_Assessment.xlsx") == "template"
    assert c("Meridian_Architecture_Comparison_Tool.xlsx") == "template"
    assert c("Retail_EA_Workshop_Pack.pptx") == "powerpoint"
    assert c("Meridian_Metamodel_How_To_Use.pptx") == "powerpoint"
    for skip in ("Banking starter pack - complete set.zip", "big.pdf.part01", "big.pdf.parts.json", "notes.txt", "x.docx"):
        assert c(skip) is None, skip
    assert ip.industry_of("Health Care") == "healthcare" and ip.industry_of("Minerals_and_Mining") == "minerals-and-mining"
    assert ip.industry_of("Retail starter pack") == "retail" and ip.industry_of("Somewhere else") is None
    assert ip.title_of("Healthcare_EA_Maturity_Assessment.xlsx", "Healthcare") == "Maturity Assessment"
    assert ip.title_of("Banking - read me first.pdf", "Banking") == "Read me first"


def test_scan_opens_zips_joins_parts_and_keeps_duplicates_once(tmp_path, monkeypatch):
    retail = tmp_path / "Retail"
    (retail / "sub").mkdir(parents=True)
    book = b"%PDF-1.4 the retail book"
    (retail / "Retail - a starter pack for enterprise architects.pdf").write_bytes(book)
    (retail / "sub" / "Retail - a starter pack for enterprise architects.pdf").write_bytes(book)      # the same file again
    (retail / "notes.txt").write_text("not a pack file")
    with zipfile.ZipFile(retail / "Retail starter pack - complete set.zip", "w") as z:
        z.writestr("set/Retail_TOGAF_Metamodel.xlsx", _xlsx("Halverson Stores Group"))
        z.writestr("set/Retail - a starter pack for enterprise architects.pdf", book)                # and in the zip
    big = retail / "Retail - the architecture workbook.pdf"
    big.write_bytes(b"W" * 2500)
    monkeypatch.setattr(ip, "SPLIT_LIMIT", 1000)
    monkeypatch.setattr(ip, "PART_SIZE", 900)
    written = ip.split_file(big)
    big.unlink()
    assert [p.name for p in written][-1].endswith(".parts.json") and len(written) == 4
    found = {(f["industry"], f["kind"]): f for f in ip.scan(tmp_path)}
    assert set(found) == {("retail", "book"), ("retail", "metamodel"), ("retail", "workbook")}
    assert found[("retail", "workbook")]["content"] == b"W" * 2500
    # a part changed: the parts no longer join up
    (retail / "Retail - the architecture workbook.pdf.part02").write_bytes(b"X" * 900)
    with pytest.raises(Exception, match="do not join up"):
        ip.scan(tmp_path)


def test_the_ai_use_check():
    assert ip.restricted("x.xlsx", _xlsx("NOT FOR AI USE OR AUTOMATED PROCESSING"))
    assert ip.restricted("x.pptx", _xlsx("This document carries an AI use restriction clause"))
    assert ip.restricted("x.txt", b"Not for AI use")
    assert not ip.restricted("x.xlsx", _xlsx("Halverson Stores Group: capabilities"))


class FakeConn:
    """Enough of a connection for load_folder: the pack files table in a dict."""
    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}
        self.audit: list = []

    def execute(self, stmt, params=None):
        sql, p = str(stmt), params or {}
        conn = self

        class Res:
            def __init__(self, row=None):
                self.row = row

            def mappings(self):
                return self

            def first(self):
                return self.row
        if sql.lstrip().startswith("SELECT id, checksum"):
            return Res(conn.rows.get((p["i"], p["n"])))
        if sql.lstrip().startswith("INSERT INTO core.industry_pack_files"):
            conn.rows[(p["i"], p["n"])] = {"id": len(conn.rows) + 1, "checksum": p["c"], "mayan_document_id": p["m"], "versions": 1}
        elif sql.lstrip().startswith("UPDATE core.industry_pack_files"):
            row = next(r for r in conn.rows.values() if r["id"] == p["id"])
            row.update(checksum=p["c"], versions=row["versions"] + 1)
        return Res()


def test_load_skips_unchanged_files_replaces_changed_ones_and_refuses_marked_ones(tmp_path, monkeypatch):
    from eax import audit, mayan
    calls = []
    monkeypatch.setattr(mayan, "upload", lambda name, content, ctype, label=None: calls.append(("upload", name)) or {"id": len(calls)})
    monkeypatch.setattr(mayan, "add_to_cabinet", lambda c, d: None)
    monkeypatch.setattr(mayan, "cabinet", lambda label, parent=None: 7)
    monkeypatch.setattr(mayan, "new_version", lambda d, name, content, comment, ctype: calls.append(("version", name)))
    monkeypatch.setattr(audit, "record", lambda conn, **kw: conn.audit.append(kw))
    pack = tmp_path / "Banking"
    pack.mkdir()
    (pack / "Banking_TOGAF_Metamodel.xlsx").write_bytes(_xlsx("Ardent Union Bank"))
    (pack / "Banking_EA_Secret.xlsx").write_bytes(_xlsx("NOT FOR AI USE OR AUTOMATED PROCESSING"))
    conn = FakeConn()
    out = ip.load_folder(conn, tmp_path, "tester")
    assert out["loaded"] == ["Banking: Banking_TOGAF_Metamodel.xlsx"] and out["refused"] == ["Banking: Banking_EA_Secret.xlsx"]
    assert ("upload", "Banking_EA_Secret.xlsx") not in calls
    again = ip.load_folder(conn, tmp_path, "tester")
    assert again["unchanged"] == ["Banking: Banking_TOGAF_Metamodel.xlsx"] and not again["loaded"] and not again["replaced"]
    (pack / "Banking_TOGAF_Metamodel.xlsx").write_bytes(_xlsx("Ardent Union Bank, version 2"))
    third = ip.load_folder(conn, tmp_path, "tester")
    assert third["replaced"] == ["Banking: Banking_TOGAF_Metamodel.xlsx"] and calls[-1] == ("version", "Banking_TOGAF_Metamodel.xlsx")
    dry = ip.load_folder(FakeConn(), tmp_path, "tester", dry_run=True)
    assert dry["loaded"] and len([c for c in calls if c[0] == "upload"]) == 1
    assert conn.audit and conn.audit[0]["action"] == "industry_packs.loaded"


def test_collect_copies_dedupes_refuses_and_splits(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from eaxcli import packs
    src = tmp_path / "Industry Specific Guidance"
    (src / "Pharma" / "Pharmaceuticals starter pack" / "01 Learner guide").mkdir(parents=True)
    guide = src / "Pharma" / "Pharmaceuticals starter pack" / "01 Learner guide" / "Pharmaceuticals - a starter pack for enterprise architects.pdf"
    guide.write_bytes(b"%PDF the guide " + b"G" * 3000)
    (src / "Pharma" / "Pharmaceuticals - a starter pack for enterprise architects.pdf").write_bytes(guide.read_bytes())
    (src / "Pharma" / "00 READ ME FIRST - what is in this set.pdf").write_bytes(b"%PDF read me")
    with zipfile.ZipFile(src / "Pharma" / "complete set.zip", "w") as z:
        z.writestr("x/Pharmaceuticals_EA_Hidden.xlsx", _xlsx("NOT FOR AI USE OR AUTOMATED PROCESSING"))
        z.writestr("x/Pharmaceuticals_TOGAF_Metamodel.xlsx", _xlsx("Calderon Therapeutics"))
    flat = tmp_path / "Metamodels_And_Views_by_Industry"
    flat.mkdir()
    (flat / "Telecommunications_TOGAF_Metamodel.xlsx").write_bytes(_xlsx("Northwind Telecom"))
    dest = tmp_path / "industry-packs"
    monkeypatch.setattr(packs, "SPLIT_LIMIT", 1000)
    monkeypatch.setattr(packs, "PART_SIZE", 900)
    out = packs.collect([src, flat], dest)
    names = sorted(str(p.relative_to(dest)).replace("\\", "/") for p in dest.rglob("*") if p.is_file())
    assert "Pharmaceuticals/Pharmaceuticals - read me first (what is in this set).pdf" in names
    assert "Telecommunications/Telecommunications_TOGAF_Metamodel.xlsx" in names
    assert "Pharmaceuticals/Pharmaceuticals_TOGAF_Metamodel.xlsx" in names
    assert not any("Hidden" in n for n in names) and out["refused"] == ["Pharmaceuticals/Pharmaceuticals_EA_Hidden.xlsx"]
    assert len(out["duplicates"]) == 1 and len(out["split"]) == 1
    assert "Pharmaceuticals/Pharmaceuticals - a starter pack for enterprise architects.pdf.parts.json" in names
    # the parts join up again in the API's scan
    found = {(f["industry"], f["kind"]) for f in ip.scan(dest)}
    assert ("pharmaceuticals", "book") in found and ("telecommunications", "metamodel") in found
    # running it again copies nothing new
    assert not packs.collect([src, flat], dest)["copied"]


def test_the_shipped_packs():
    """library/industry-packs (D546): every industry folder is known, every file is a pack file, none is marked not for
    AI use, none is over 50 MB (larger ones are kept in parts), and each reference model's industry has its metamodel."""
    files = [p for p in SHIPPED.rglob("*") if p.is_file()]
    assert files, "the packs are in the repository"
    shas = set()
    for f in files:
        assert ip.industry_of(f.parent.name), f
        assert f.stat().st_size <= 50 * 1024 * 1024, f
        name = f.name[:-len(".parts.json")] if f.name.endswith(".parts.json") else f.name
        if not re.search(r"\.part\d+$", f.name):
            assert ip.classify(name), f
        if not f.name.endswith(".parts.json") and not re.search(r"\.part\d+$", f.name):
            assert not ip.restricted(f.name, f.read_bytes()), f
            sha = hashlib.sha256(f.read_bytes()).hexdigest()
            assert sha not in shas, f"{f} is stored twice"
            shas.add(sha)
    kinds = {(ip.industry_of(f.parent.name), ip.classify(f.name)) for f in files}
    for code in ("banking", "government", "healthcare", "insurance", "logistics", "manufacturing", "minerals-and-mining",
                 "pharmaceuticals", "retail", "telecommunications"):
        assert (code, "metamodel") in kinds, code


def test_tiles_follow_the_pack_kind():
    """A starter pack shows every tile (missing ones as not loaded); a metamodel-only pack shows only its two."""
    class C:
        def execute(self, *_a, **_k):
            class R:
                def mappings(self):
                    return self

                def all(self):
                    return [{"id": "g1", "kind": "metamodel", "title": "TOGAF content metamodel (populated)",
                             "file_name": "Logistics_TOGAF_Metamodel.xlsx", "content_type": "x", "file_size": 10,
                             "versions": 1, "sample": False, "loaded_at": None, "updated_at": None, "ready": True}]
            return R()
    lg = ip.pack(C(), "logistics")
    assert [t["kind"] for t in lg["tiles"]] == ["metamodel", "example_views"]
    assert lg["tiles"][0]["state"] == "loaded" and lg["tiles"][1]["state"] == "not loaded"
    rt = ip.pack(C(), "retail")
    assert [t["kind"] for t in rt["tiles"]] == [k for k, *_ in ip.KINDS]
    with pytest.raises(ip.EditError, match="No industry pack"):
        ip.pack(C(), "nowhere")


def test_api_rights_migration_and_mounts():
    api = (ROOT / "services" / "api" / "eax" / "api" / "industry_packs.py").read_text(encoding="utf-8")
    load = api[api.index('@blp.route("/industry-packs/load")'):]
    assert '@require_auth("library.curate")' in load            # loading: Library Admins and Super Admins
    assert api.count("@require_auth()") == 4                    # reading and downloading: anyone signed in
    sql = (ROOT / "services" / "api" / "migrations" / "sql" / "0046_industry_packs.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE core.industry_pack_files" in sql and "TRIGGER" not in sql.upper() and "FUNCTION" not in sql.upper()
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./library/industry-packs:/data/industry-packs:ro" in compose and "/data/packs-extra:ro" in compose
    later = (ROOT / "services" / "api" / "eax" / "seed" / "later.py").read_text(encoding="utf-8")
    assert '"Industry packs into Documents' in later
    help_txt = (ROOT / "eaxcli" / "help.txt").read_text(encoding="utf-8")
    assert "### packs " in help_txt
    assert json.loads((ROOT / "services" / "web" / "src" / "help" / "catalogue.json").read_text(encoding="utf-8"))["tab:Pack"]
