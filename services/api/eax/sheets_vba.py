"""The macro version of the import and export sheets (.xlsm, D197): the same workbook with a small VBA project whose
ThisWorkbook module writes a GUID into a new row as soon as it has a name. Built to the published Office formats
([MS-OVBA] for the VBA project, [MS-CFB] for the compound file holding it): the project carries source code only
(its version says "no compiled code"), so Excel compiles it when the file is opened. Macros run only when the person
enables them; the .xlsx works without.
"""

from __future__ import annotations

import io
import random
import re
import struct
import uuid
import zipfile

MACRO = r'''Private Sub Workbook_SheetChange(ByVal Sh As Object, ByVal Target As Range)
    ' EA Explorer: a new row (a name, or a relationship type, and no GUID yet) gets a GUID.
    Dim c As Range, r As Long
    If LCase(CStr(Sh.Cells(2, 1).Value)) <> "guid" Then Exit Sub
    On Error GoTo Done
    Application.EnableEvents = False
    For Each c In Target.Cells
        r = c.Row
        If r >= 3 And c.Column > 1 Then
            If Len(CStr(Sh.Cells(r, 1).Value)) = 0 And Len(CStr(Sh.Cells(r, 3).Value)) > 0 Then
                Sh.Cells(r, 1).Value = NewGuid()
            End If
        End If
    Next c
Done:
    Application.EnableEvents = True
End Sub

Private Function NewGuid() As String
    Static seeded As Boolean
    Dim s As String, i As Integer, h As String
    If Not seeded Then Randomize: seeded = True
    h = "0123456789abcdef"
    For i = 1 To 32
        s = s & Mid$(h, Int(Rnd() * 16) + 1, 1)
    Next i
    NewGuid = Mid$(s, 1, 8) & "-" & Mid$(s, 9, 4) & "-4" & Mid$(s, 14, 3) & "-" & Mid$(h, 9 + Int(Rnd() * 4), 1) _
        & Mid$(s, 18, 3) & "-" & Mid$(s, 21, 12)
End Function
'''

WORKBOOK_BASE = "0{00020819-0000-0000-C000-000000000046}"
SHEET_BASE = "0{00020820-0000-0000-C000-000000000046}"


def _document_source(name: str, base: str, code: str = "") -> bytes:
    head = (f'Attribute VB_Name = "{name}"\r\nAttribute VB_Base = "{base}"\r\nAttribute VB_GlobalNameSpace = False\r\n'
            "Attribute VB_Creatable = False\r\nAttribute VB_PredeclaredId = True\r\nAttribute VB_Exposed = True\r\n"
            "Attribute VB_TemplateDerived = False\r\nAttribute VB_Customizable = True\r\n")
    return (head + code.replace("\r\n", "\n").replace("\n", "\r\n")).encode("cp1252")


# ---------------------------------------------------------------- [MS-OVBA] 2.4.1 compression
def compress(data: bytes) -> bytes:
    """The VBA compression (LZ77 in 4096-byte chunks, copy tokens whose bit split depends on the position)."""
    out = bytearray(b"\x01")
    for start in range(0, len(data), 4096) if data else [0]:
        chunk = data[start:start + 4096]
        body = _compress_chunk(chunk)
        if len(body) > 4096 or (len(body) + 2) > 4098:
            body = None
        if body is None:   # store it raw: only allowed for a full 4096-byte chunk
            raw = chunk.ljust(4096, b"\x00") if len(chunk) == 4096 else None
            if raw is None:
                raise ValueError("chunk does not compress")
            out += struct.pack("<H", (4096 - 1) | 0x3000) + raw
        else:
            out += struct.pack("<H", ((len(body) + 2 - 3) & 0x0FFF) | 0x3000 | 0x8000) + body
    return bytes(out)


def _compress_chunk(chunk: bytes) -> bytes:
    out = bytearray()
    pos = 0
    n = len(chunk)
    while pos < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if pos >= n:
                break
            # bit split of a copy token at this position
            diff = pos
            bitcount = max((diff - 1).bit_length(), 4) if diff > 1 else 4
            length_mask = 0xFFFF >> bitcount
            max_len = length_mask + 3
            best_len, best_off = 0, 0
            lo = max(0, pos - (1 << bitcount))
            for cand in range(pos - 1, lo - 1, -1):
                ln = 0
                while ln < max_len and pos + ln < n and chunk[cand + ln] == chunk[pos + ln]:
                    ln += 1
                if ln > best_len:
                    best_len, best_off = ln, pos - cand
                    if ln == max_len:
                        break
            if best_len >= 3:
                token = ((best_off - 1) << (16 - bitcount)) | (best_len - 3)
                out += struct.pack("<H", token)
                flags |= 1 << bit
                pos += best_len
            else:
                out.append(chunk[pos])
                pos += 1
        out[flag_at] = flags
    return bytes(out)


def decompress(data: bytes) -> bytes:
    """The reverse (used by the tests to check what is written)."""
    assert data[0] == 1
    out = bytearray()
    i = 1
    while i < len(data):
        header = struct.unpack_from("<H", data, i)[0]
        size = (header & 0x0FFF) + 3
        compressed = bool(header & 0x8000)
        body = data[i + 2:i + size]
        i += size
        start = len(out)
        if not compressed:
            out += body[:4096]
            continue
        j = 0
        while j < len(body):
            flags = body[j]
            j += 1
            for bit in range(8):
                if j >= len(body):
                    break
                if flags & (1 << bit):
                    token = struct.unpack_from("<H", body, j)[0]
                    j += 2
                    diff = len(out) - start
                    bitcount = max((diff - 1).bit_length(), 4) if diff > 1 else 4
                    length = (token & (0xFFFF >> bitcount)) + 3
                    off = (token >> (16 - bitcount)) + 1
                    for _ in range(length):
                        out.append(out[-off])
                else:
                    out.append(body[j])
                    j += 1
    return bytes(out)


# ---------------------------------------------------------------- [MS-OVBA] 2.3.4.2 the dir stream
def _rec(rid: int, data: bytes) -> bytes:
    return struct.pack("<HI", rid, len(data)) + data


def _dir_stream(modules: list[tuple[str, bool]]) -> bytes:
    """modules: (name, is_document)."""
    name = b"VBAProject"
    out = bytearray()
    out += _rec(0x0001, struct.pack("<I", 1))          # SysKind: 32-bit Windows (Office recompiles for 64-bit)
    out += _rec(0x0002, struct.pack("<I", 0x0409))     # Lcid
    out += _rec(0x0014, struct.pack("<I", 0x0409))     # LcidInvoke
    out += _rec(0x0003, struct.pack("<H", 1252))       # CodePage
    out += _rec(0x0004, name)                          # Name
    out += _rec(0x0005, b"") + _rec(0x0040, b"")       # DocString and its Unicode
    out += _rec(0x0006, b"") + _rec(0x003D, b"")       # HelpFile and HelpFile2
    out += _rec(0x0007, struct.pack("<I", 0))          # HelpContext
    out += _rec(0x0008, struct.pack("<I", 0))          # LibFlags
    out += struct.pack("<HI", 0x0009, 4) + struct.pack("<IH", 1, 0)   # Version: major 1, minor 0
    out += _rec(0x000C, b"") + _rec(0x003C, b"")       # Constants and their Unicode
    out += _rec(0x000F, struct.pack("<H", len(modules)))
    out += _rec(0x0013, struct.pack("<H", 0xFFFF))     # ProjectCookie
    for mod, document in modules:
        b = mod.encode("cp1252")
        u = mod.encode("utf-16-le")
        out += _rec(0x0019, b) + _rec(0x0047, u)       # ModuleName, ModuleNameUnicode
        out += _rec(0x001A, b) + _rec(0x0032, u)       # ModuleStreamName and its Unicode
        out += _rec(0x001C, b"") + _rec(0x0048, b"")   # ModuleDocString and its Unicode
        out += _rec(0x0031, struct.pack("<I", 0))      # ModuleOffset: the source starts at once (no compiled code)
        out += _rec(0x001E, struct.pack("<I", 0))      # ModuleHelpContext
        out += _rec(0x002C, struct.pack("<H", 0xFFFF))  # ModuleCookie
        out += struct.pack("<HI", 0x0022 if document else 0x0021, 0)   # ModuleType: document/class or procedural
        out += struct.pack("<HI", 0x002B, 0)           # module terminator
    out += struct.pack("<HI", 0x0010, 0)               # end of the dir stream
    return bytes(out)


# ---------------------------------------------------------------- [MS-OVBA] 2.4.3 data encryption (CMG, DPB, GC)
def _encrypt(project_id: str, data: bytes, rnd: random.Random) -> str:
    seed = rnd.randrange(256)
    version = 2
    key = sum(project_id.encode("cp1252")) & 0xFF
    venc, kenc = seed ^ version, seed ^ key
    out = [seed, venc, kenc]
    unenc1, enc1, enc2 = key, kenc, venc
    for _ in range((seed & 6) // 2):
        temp = rnd.randrange(256)
        b = ((enc2 + unenc1) & 0xFF) ^ temp
        out.append(b)
        enc2, enc1, unenc1 = enc1, b, temp
    for byte in struct.pack("<I", len(data)) + data:
        b = byte ^ ((enc2 + unenc1) & 0xFF)
        out.append(b)
        enc2, enc1, unenc1 = enc1, b, byte
    return "".join(f"{x:02X}" for x in out)


def _project_stream(modules: list[tuple[str, bool]], rnd: random.Random) -> bytes:
    pid = "{" + str(uuid.UUID(int=rnd.getrandbits(128))).upper() + "}"
    lines = [f'ID="{pid}"']
    lines += [f"Document={n}/&H00000000" for n, doc in modules if doc]
    lines += [f"Module={n}" for n, doc in modules if not doc]
    lines += ['Name="VBAProject"', 'HelpContextID="0"', 'VersionCompatible32="393222000"',
              'CMG="' + _encrypt(pid, struct.pack("<I", 0), rnd) + '"', 'DPB="' + _encrypt(pid, bytes([0]), rnd) + '"',
              'GC="' + _encrypt(pid, bytes([255]), rnd) + '"', "", "[Host Extender Info]",
              "&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;&H00000000", "", "[Workspace]"]
    lines += [f"{n}=0, 0, 0, 0, C" for n, _ in modules]
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


def _project_wm(modules: list[tuple[str, bool]]) -> bytes:
    out = bytearray()
    for n, _ in modules:
        out += n.encode("cp1252") + b"\x00" + n.encode("utf-16-le") + b"\x00\x00"
    return bytes(out + b"\x00\x00")


def vba_project(sheet_code_names: list[str], rnd: random.Random | None = None) -> bytes:
    """The vbaProject.bin: ThisWorkbook (with the macro) and a document module per worksheet."""
    rnd = rnd or random.Random()
    modules = [("ThisWorkbook", True)] + [(n, True) for n in sheet_code_names]
    streams = {"ThisWorkbook": compress(_document_source("ThisWorkbook", WORKBOOK_BASE, MACRO))}
    for n in sheet_code_names:
        streams[n] = compress(_document_source(n, SHEET_BASE))
    vba = {"_VBA_PROJECT": b"\xcc\x61\xff\xff\x00\x00\x00",   # version 0xFFFF: no compiled code, Office compiles the source
           "dir": compress(_dir_stream(modules)), **streams}
    return cfb({"PROJECT": _project_stream(modules, rnd), "PROJECTwm": _project_wm(modules), "VBA": vba})


# ---------------------------------------------------------------- [MS-CFB] a compound file (version 3, 512-byte sectors)
FREE, END, FATSECT, NOSTREAM = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
CUTOFF = 4096


def _key(name: str) -> tuple[int, str]:
    return (len(name), name.upper())


def cfb(tree: dict) -> bytes:
    """tree: {name: bytes (a stream) or dict (a storage)}. Every stream here is under 4096 bytes, so all sit in the
    mini stream; larger ones go in ordinary sectors."""
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "children": []}]

    def add(node: dict, parent: int):
        for name, v in node.items():
            e = {"name": name, "type": 1 if isinstance(v, dict) else 2, "children": [], "data": None if isinstance(v, dict) else v}
            entries.append(e)
            i = len(entries) - 1
            entries[parent]["children"].append(i)
            if isinstance(v, dict):
                add(v, i)
    add(tree, 0)

    mini = bytearray()
    minifat: list[int] = []
    big: list[tuple[int, bytes]] = []
    for i, e in enumerate(entries):
        if e["type"] != 2:
            continue
        d = e["data"]
        if len(d) < CUTOFF:
            first = len(minifat)
            n = max(1, -(-len(d) // 64))
            minifat += [first + k + 1 for k in range(n - 1)] + [END]
            e["start"] = first if d else END
            if not d:
                minifat = minifat[:-1]
            mini += d.ljust(n * 64, b"\x00") if d else b""
        else:
            big.append((i, d))
        e["size"] = len(d)

    def sectors(n_bytes: int) -> int:
        return -(-n_bytes // 512)
    n_dir = sectors(len(entries) * 128)
    n_minifat = sectors(len(minifat) * 4) if minifat else 0
    n_mini = sectors(len(mini))
    n_big = sum(sectors(len(d)) for _, d in big)
    n_fat = 1
    while True:
        total = n_fat + n_dir + n_minifat + n_mini + n_big
        if sectors(total * 4) <= n_fat:
            break
        n_fat += 1
    if n_fat > 109:
        raise ValueError("compound file too large for this writer")
    fat = [FATSECT] * n_fat
    at = n_fat

    def chain(count: int) -> int:
        nonlocal at
        if count == 0:
            return END
        first = at
        for k in range(count):
            fat.append(at + 1 if k < count - 1 else END)
            at += 1
        return first
    dir_start = chain(n_dir)
    minifat_start = chain(n_minifat)
    mini_start = chain(n_mini)
    for i, d in big:
        entries[i]["start"] = chain(sectors(len(d)))
    entries[0]["start"] = mini_start if n_mini else END
    entries[0]["size"] = len(mini)
    while len(fat) % 128:
        fat.append(FREE)

    # each storage's children as a balanced binary tree by name (all black)
    for e in entries:
        e.setdefault("left", NOSTREAM)
        e.setdefault("right", NOSTREAM)
        e["child"] = NOSTREAM
    for e in entries:
        kids = sorted(e["children"], key=lambda i: _key(entries[i]["name"]))

        def build(lo: int, hi: int, kids=kids) -> int:
            if lo > hi:
                return NOSTREAM
            mid = (lo + hi) // 2
            node = kids[mid]
            entries[node]["left"] = build(lo, mid - 1)
            entries[node]["right"] = build(mid + 1, hi)
            return node
        e["child"] = build(0, len(kids) - 1)

    def entry_bytes(e: dict | None) -> bytes:
        if e is None:
            return b"\x00" * 64 + struct.pack("<HBBIII", 0, 0, 0, NOSTREAM, NOSTREAM, NOSTREAM) + b"\x00" * 16 + \
                struct.pack("<IQQIQ", 0, 0, 0, 0, 0)
        name = e["name"].encode("utf-16-le") + b"\x00\x00"
        return (name.ljust(64, b"\x00") + struct.pack("<HBBIII", len(name), e["type"], 1, e["left"], e["right"], e["child"])
                + b"\x00" * 16 + struct.pack("<IQQIQ", 0, 0, 0, e.get("start", 0) if e["type"] != 1 else 0,
                                             e.get("size", 0) if e["type"] != 1 else 0))
    directory = b"".join(entry_bytes(e) for e in entries)
    directory += entry_bytes(None) * ((n_dir * 4) - len(entries))

    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x003E, 0x0003, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 0, n_fat, dir_start, 0, CUTOFF,
                     minifat_start if n_minifat else END, n_minifat, END, 0)
    difat = list(range(n_fat)) + [FREE] * (109 - n_fat)
    struct.pack_into("<109I", header, 76, *difat)

    body = bytearray()
    body += struct.pack(f"<{len(fat)}I", *fat)[: n_fat * 512]
    body += directory
    if n_minifat:
        mf = minifat + [FREE] * ((n_minifat * 128) - len(minifat))
        body += struct.pack(f"<{len(mf)}I", *mf)
    body += bytes(mini).ljust(n_mini * 512, b"\x00")
    for _, d in big:
        body += d.ljust(sectors(len(d)) * 512, b"\x00")
    return bytes(header) + bytes(body)


# ---------------------------------------------------------------- into the workbook
def add_macro(xlsx: bytes) -> bytes:
    """Turns an .xlsx (made by openpyxl) into an .xlsm with the VBA project: code names for the workbook and its
    sheets, the macro-enabled content type, and xl/vbaProject.bin with its relationship."""
    src = zipfile.ZipFile(io.BytesIO(xlsx))
    files = {n: src.read(n) for n in src.namelist()}
    wb = files["xl/workbook.xml"].decode("utf-8")
    sheets = sorted(n for n in files if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    code_names = []
    for k, n in enumerate(sorted(sheets, key=lambda x: int(re.search(r"(\d+)", x.rsplit("/", 1)[1]).group(1))), start=1):
        cn = f"Sheet{k}"
        code_names.append(cn)
        x = files[n].decode("utf-8")
        if "<sheetPr" in x:
            x = re.sub(r"<sheetPr(?![^>]*codeName)", f'<sheetPr codeName="{cn}"', x, count=1)
        else:
            x = re.sub(r"(<worksheet[^>]*>)", rf'\1<sheetPr codeName="{cn}"/>', x, count=1)
        files[n] = x.encode("utf-8")
    if "<workbookPr" in wb:
        wb = re.sub(r"<workbookPr(?![^>]*codeName)", '<workbookPr codeName="ThisWorkbook"', wb, count=1)
    else:
        wb = re.sub(r"(<workbook[^>]*>)", r'\1<workbookPr codeName="ThisWorkbook"/>', wb, count=1)
    files["xl/workbook.xml"] = wb.encode("utf-8")
    ct = files["[Content_Types].xml"].decode("utf-8")
    ct = ct.replace("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                    "application/vnd.ms-excel.sheet.macroEnabled.main+xml")
    if 'Extension="bin"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/><Default ', 1)
    files["[Content_Types].xml"] = ct.encode("utf-8")
    rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    rels = rels.replace("</Relationships>", '<Relationship Id="rIdVBA1" Type="http://schemas.microsoft.com/office/2006/'
                                            'relationships/vbaProject" Target="vbaProject.bin"/></Relationships>')
    files["xl/_rels/workbook.xml.rels"] = rels.encode("utf-8")
    files["xl/vbaProject.bin"] = vba_project(code_names)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", files.pop("[Content_Types].xml"))
        for n, d in files.items():
            z.writestr(n, d)
    return out.getvalue()
