"""Phase 10.1 import and export sheets (D197): reading files, matching values, the macro workbook's VBA project."""

from __future__ import annotations

import io
import random
import struct
import zipfile
from pathlib import Path

import pytest

from eax import loads as ld
from eax import sheets as sh
from eax import sheets_vba as vba
from eax.metamodel_edit import EditError

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
WEB = ROOT.parent / "web" / "src"


def test_csv_dialects_and_bom():
    for body in ("name;Owner\nCRM;Sales\n", "﻿name,Owner\nCRM,Sales\n", "name\tOwner\nCRM\tSales\n"):
        s = sh.read(body.encode("utf-8"), "apps.csv")["sheets"][0]
        assert s["codes"] == ["name", "Owner"] and s["rows"][0]["name"] == "CRM" and s["rows"][0]["Owner"] == "Sales"
    s = sh.read("Application;Life\nCRM;Live\n".encode("cp1252"), "other.csv")["sheets"][0]
    assert s["headers"] == ["Application", "Life"] and not s["ours"]          # another system's file: mapped first
    with pytest.raises(EditError):
        sh.read(b"x", "notes.pdf")


def test_sample_csv_reads():
    s = sh.read((REPO / "deploy/samples/cmdb-applications.csv").read_bytes(), "cmdb-applications.csv")["sheets"][0]
    assert len(s["rows"]) == 5 and s["delimiter"] == ";"


def test_sheet_names_fit_excel():
    taken: set[str] = set()
    a = sh.sheet_name("A very long entity type name that Excel would refuse", taken)
    b = sh.sheet_name("A very long entity type name that Excel would refuse", taken)
    assert len(a) <= 31 and len(b) <= 31 and a != b
    assert sh.sheet_name("Data/Object: [x]", set()) == "Data Object   x"


def test_values_compare_by_type():
    assert ld._same("5", "5.00", "decimal") and ld._same("Yes", "true", "boolean") and ld._same("2026-01-02", "2026-01-02T00:00", "date")
    assert not ld._same("5", "6", "decimal") and not ld._same("", "0", "integer")
    num = {"name": "Cost", "data_type": "decimal"}
    assert ld._check_value(num, "12,5") is None and ld._check_value(num, "twelve")
    assert ld._check_value({"name": "Go-live", "data_type": "date"}, "next week")
    assert ld._check_value({"name": "Count", "data_type": "integer"}, "2.5")


def test_vba_compression_round_trip():
    src = vba._document_source("ThisWorkbook", vba.WORKBOOK_BASE, vba.MACRO)
    assert vba.decompress(vba.compress(src)) == src
    rnd = random.Random(7)
    for n in (0, 1, 7, 4095, 4096, 4097, 12000):
        data = bytes(rnd.randrange(4) for _ in range(n))
        assert vba.decompress(vba.compress(data)) == data, n


def _cfb_streams(blob: bytes) -> dict[str, bytes]:
    """A small [MS-CFB] reader: follows the FAT, the directory and the mini stream, to check what the writer made."""
    assert blob[:8] == bytes.fromhex("D0CF11E0A1B11AE1")
    n_fat, first_dir, cutoff, first_minifat, n_minifat = struct.unpack_from("<4xIIxxxxIII", blob, 40)[0:5]
    difat = struct.unpack_from("<109I", blob, 76)[:n_fat]
    sector = lambda i: blob[512 + i * 512: 1024 + i * 512]  # noqa: E731
    fat = []
    for s in difat:
        fat += struct.unpack("<128I", sector(s))

    def chain(start):
        out = []
        while start < 0xFFFFFFFA:
            out.append(start)
            start = fat[start]
        return out
    directory = b"".join(sector(s) for s in chain(first_dir))
    entries = []
    for i in range(len(directory) // 128):
        e = directory[i * 128:(i + 1) * 128]
        nlen, typ = struct.unpack_from("<HB", e, 64)
        left, right, child = struct.unpack_from("<III", e, 68)
        start, size = struct.unpack_from("<IQ", e, 116)
        entries.append({"name": e[:max(nlen - 2, 0)].decode("utf-16-le"), "type": typ, "left": left, "right": right, "child": child,
                        "start": start, "size": size})
    root = entries[0]
    mini = b"".join(sector(s) for s in chain(root["start"]))
    minifat = []
    for s in chain(first_minifat) if n_minifat else []:
        minifat += struct.unpack("<128I", sector(s))
    out = {}

    def walk(i, path):
        if i == 0xFFFFFFFF:
            return
        e = entries[i]
        walk(e["left"], path)
        walk(e["right"], path)
        p = f"{path}/{e['name']}" if path else e["name"]
        if e["type"] == 1:
            walk(e["child"], p)
        elif e["type"] == 2:
            assert e["size"] < cutoff
            data, s = b"", e["start"]
            while s < 0xFFFFFFFA:
                data += mini[s * 64:(s + 1) * 64]
                s = minifat[s]
            out[p] = data[:e["size"]]
    walk(root["child"], "")
    return out


def test_vba_project_is_a_valid_compound_file():
    blob = vba.vba_project(["Sheet1", "Sheet2"], random.Random(3))
    streams = _cfb_streams(blob)
    assert set(streams) == {"PROJECT", "PROJECTwm", "VBA/_VBA_PROJECT", "VBA/dir", "VBA/ThisWorkbook", "VBA/Sheet1", "VBA/Sheet2"}
    assert streams["VBA/_VBA_PROJECT"] == b"\xcc\x61\xff\xff\x00\x00\x00"           # source only: Excel compiles it
    assert b"Workbook_SheetChange" in vba.decompress(streams["VBA/ThisWorkbook"])
    project = streams["PROJECT"].decode("cp1252")
    assert "Document=ThisWorkbook/&H00000000" in project and 'CMG="' in project and 'GC="' in project
    d = vba.decompress(streams["VBA/dir"])
    assert d.endswith(struct.pack("<HI", 0x0010, 0)) and b"ThisWorkbook" in d


def test_macro_workbook_parts():
    from openpyxl import Workbook
    wb = Workbook()
    wb.create_sheet("Two")
    buf = io.BytesIO()
    wb.save(buf)
    z = zipfile.ZipFile(io.BytesIO(vba.add_macro(buf.getvalue())))
    assert b"macroEnabled.main+xml" in z.read("[Content_Types].xml") and b'Extension="bin"' in z.read("[Content_Types].xml")
    assert b"vbaProject.bin" in z.read("xl/_rels/workbook.xml.rels")
    assert b'codeName="ThisWorkbook"' in z.read("xl/workbook.xml") and b'codeName="Sheet2"' in z.read("xl/worksheets/sheet2.xml")
    assert set(_cfb_streams(z.read("xl/vbaProject.bin"))) >= {"VBA/Sheet1", "VBA/Sheet2"}


def test_api_and_screens():
    api = (ROOT / "eax" / "api" / "sheets.py").read_text()
    for route in ('"/models/<uuid:model_id>/sheets"', '"/models/<uuid:model_id>/loads"', '"/loads/<load_id>/add"', '"/loads/<load_id>/undo"'):
        assert route in api, route
    web = (WEB / "Sheets.jsx").read_text(encoding="utf-8")
    assert "Build and download" in web and "Upload and preview" in web and "Map the columns" in web
    assert '["import", "Import and export", null]' in (WEB / "Metamodel.jsx").read_text(encoding="utf-8")
    assert "collection-sets" not in api and "feeds" not in api     # their own phase, designed first (D198)
