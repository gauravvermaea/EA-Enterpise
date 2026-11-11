"""The industry packs' files (phase 39; owner 10 Nov 2026, D546 to D549).

Each industry reference model has a **pack**: the files the owner wrote for that industry (the read-me, the book (learner
guide), the workbook, the metamodel Excel to study (the populated worked example the model was built from) and the empty
metamodel template, the Excel templates, the PowerPoints, and the worked example's ArchiMate 4 views). They are kept in
the repository under library/industry-packs/<Industry>/ (D546), mounted read-only into the API at /data/industry-packs,
and stored in Documents (Mayan) at start-up: one cabinet "EA Explorer industry packs" with a cabinet per industry, one
Mayan document per file. A file whose checksum is unchanged is skipped; a changed one becomes a new version of its
document. The library's Pack tab shows them as tiles to download, through the API (anyone signed in: the library is
everyone's). `eax packs load [folder]` or System admin loads another folder the same way.

Rules kept here (D248): which industry a folder is, what kind each file is (by its name), the AI-use check (a file
marked "NOT FOR AI USE OR AUTOMATED PROCESSING" or with an AI USE RESTRICTION clause is never loaded, D547), joining files
split into parts (a file over 50 MB is kept as `<name>.part01`, `.part02`... with `<name>.parts.json`, D546), the
checksum skip, and the tiles.
"""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .metamodel_edit import EditError

PACKS_DIR = Path(os.environ.get("EAX_INDUSTRY_PACKS_DIR", "/data/industry-packs"))
EXTRA_DIR = Path(os.environ.get("EAX_PACKS_EXTRA_DIR", "/data/packs-extra"))
CABINET = "EA Explorer industry packs"

# (code, display name, folder names it may have, the reference model's industry code in seed/industries.py)
INDUSTRIES = [
    ("banking", "Banking", ("banking",), ("banking",)),
    ("government", "Government", ("government",), ("government",)),
    ("healthcare", "Healthcare", ("healthcare", "health care", "health"), ("healthcare",)),
    ("insurance", "Insurance", ("insurance",), ("meridian",)),
    ("logistics", "Logistics", ("logistics",), ("logistics",)),
    ("manufacturing", "Manufacturing", ("manufacturing", "manufacturing starter pack"), ("manufacturing",)),
    ("minerals-and-mining", "Minerals and Mining", ("minerals_and_mining", "minerals and mining", "minerals_mining",
                                                     "mining"), ("minerals_mining",)),
    ("pharmaceuticals", "Pharmaceuticals", ("pharmaceuticals", "pharma", "pharmaceuticals starter pack"), ("pharmaceuticals",)),
    ("retail", "Retail", ("retail", "retail starter pack"), ("retail",)),
    ("telecommunications", "Telecommunications", ("telecommunications", "telecoms", "telecom"), ("telecommunications",)),
]
BY_CODE = {c: (c, n, f, m) for c, n, f, m in INDUSTRIES}

# the tiles, in order: (kind, tile title, what it is)
KINDS = [
    ("readme", "Read me first", "What is in the pack and where to start"),
    ("book", "The book", "The learner guide: a starter pack for enterprise architects in this industry"),
    ("workbook", "The workbook", "Exercises and worked answers to go with the book"),
    ("metamodel", "Metamodel Excel to study", "The populated worked example this reference model was built from"),
    ("metamodel_template", "Metamodel template", "The same workbook, empty, to fill in for your own organisation"),
    ("example_views", "ArchiMate 4 views", "The worked example's views, as PowerPoint"),
    ("template", "Excel templates", "Comparison tool, maturity assessment, principles and standards, transcription forms, "
                                    "workshop capture"),
    ("powerpoint", "PowerPoints", "Executive briefing, view templates, workshop pack and how-to-use decks"),
]
KIND_TITLES = {k: t for k, t, _ in KINDS}
BOOK_KINDS = ("book", "workbook")      # the starter packs have these; the metamodel-only industries do not (D548)
AI_MARK = re.compile(r"NOT\s+FOR\s+AI\s+USE|AI\s+USE\s+RESTRICTION", re.I)
SPLIT_LIMIT = 50 * 1024 * 1024        # a file above this is kept in parts (no Git LFS, D546)
PART_SIZE = 45 * 1024 * 1024


# ---------------------------------------------------------------- reading a folder
def industry_of(folder_name: str) -> str | None:
    n = folder_name.strip().lower().replace("-", " ").replace("_", " ")
    for code, _name, names, _m in INDUSTRIES:
        if n in {x.replace("_", " ") for x in names} or n == code.replace("-", " "):
            return code
    return None


def classify(file_name: str) -> str | None:
    """The kind of a pack file, from its name; None for anything that is not part of a pack."""
    n = file_name.lower()
    if n.endswith((".parts.json", ".zip")) or re.search(r"\.part\d+$", n):
        return None
    ext = n.rpartition(".")[2]
    if "read me first" in n or "read_me_first" in n or "readme" in n:
        return "readme" if ext in ("pdf", "md", "txt", "docx") else None
    if "a starter pack for enterprise architects" in n and ext == "pdf":
        return "book"
    if "the architecture workbook" in n and ext == "pdf":
        return "workbook"
    if ext == "xlsx" and "_togaf_metamodel" in n:
        return "metamodel"
    if ext == "xlsx" and "metamodel_template" in n:
        return "metamodel_template"
    if ext == "pptx" and "_archimate4_views" in n:
        return "example_views"
    if ext in ("xlsx", "xlsm"):
        return "template"
    if ext == "pptx":
        return "powerpoint"
    return None


def title_of(file_name: str, industry_name: str) -> str:
    """A readable title: "Healthcare EA Maturity Assessment" -> "Maturity Assessment"."""
    stem = file_name.rpartition(".")[0] or file_name
    stem = re.sub(r"^\d+\s+", "", stem).replace("_", " ")
    for prefix in (industry_name, industry_name.replace(" and ", " "), industry_name.split()[0]):
        if stem.lower().startswith(prefix.lower() + " "):
            stem = stem[len(prefix) + 1:]
            break
    stem = re.sub(r"^(EA|-)\s+", "", stem).strip(" -")
    stem = re.sub(r"\bTOGAF Metamodel\b", "TOGAF content metamodel (populated)", stem)
    stem = re.sub(r"\bArchiMate4\b", "ArchiMate 4", stem)
    return (stem[:1].upper() + stem[1:]) or file_name


def text_for_check(name: str, content: bytes) -> str:
    """The words in a file, for the AI-use check: Office files' XML, a PDF's text, anything else as text."""
    ext = name.lower().rpartition(".")[2]
    try:
        if ext in ("xlsx", "xlsm", "pptx", "docx"):
            out = []
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for n in z.namelist():
                    if n.endswith(".xml"):
                        out.append(z.read(n).decode("utf-8", "ignore"))
            return re.sub(r"<[^>]+>", " ", " ".join(out))
        if ext == "pdf":
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            return " ".join((p.extract_text() or "") for p in reader.pages)
    except Exception:     # noqa: BLE001 - an unreadable file is checked as raw text
        pass
    return content.decode("utf-8", "ignore")


def restricted(name: str, content: bytes) -> bool:
    """D547: a file marked not for AI use or automated processing is never loaded."""
    return bool(AI_MARK.search(text_for_check(name, content)))


def split_file(path: Path) -> list[Path]:
    """Keep a file over 50 MB as parts below 45 MB with a manifest (name, parts, sha256), so no Git LFS is needed (D546).
    Returns the files written (the parts and the manifest); the original is left for the caller to remove."""
    data = path.read_bytes()
    if len(data) <= SPLIT_LIMIT:
        return []
    parts = []
    for i in range(0, len(data), PART_SIZE):
        part = path.with_name(f"{path.name}.part{i // PART_SIZE + 1:02d}")
        part.write_bytes(data[i:i + PART_SIZE])
        parts.append(part)
    manifest = path.with_name(path.name + ".parts.json")
    manifest.write_text(json.dumps({"name": path.name, "parts": [p.name for p in parts], "size": len(data),
                                    "sha256": hashlib.sha256(data).hexdigest()}, indent=1), encoding="utf-8")
    return parts + [manifest]


def join_parts(manifest: Path) -> tuple[str, bytes]:
    m = json.loads(manifest.read_text(encoding="utf-8"))
    data = b"".join((manifest.parent / p).read_bytes() for p in m["parts"])
    if hashlib.sha256(data).hexdigest() != m["sha256"]:
        raise EditError(f"{m['name']}: its parts do not join up (checksum differs); copy the pack again.", 422)
    return m["name"], data


def scan(root: Path) -> list[dict]:
    """Every pack file under root: {industry, kind, name, title, content, checksum}. Folders are industries; zips are
    opened (a starter pack's "complete set"); parts are joined; anything that is not a pack file is left out."""
    found: dict[tuple[str, str], dict] = {}
    if not root.is_dir():
        return []

    def keep(code: str, name: str, content: bytes):
        kind = classify(name)
        if not kind or not content:
            return
        title = title_of(name, BY_CODE[code][1])
        sha = hashlib.sha256(content).hexdigest()
        if any(f["checksum"] == sha and f["industry"] == code for f in found.values()):
            return                                   # the same file twice (e.g. a learner guide in two folders)
        found[(code, name)] = {"industry": code, "kind": kind, "name": name, "title": title, "content": content,
                               "checksum": sha}

    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        code = industry_of(folder.name)
        if not code:
            continue
        for f in sorted(folder.rglob("*")):
            if not f.is_file():
                continue
            low = f.name.lower()
            if low.endswith(".parts.json"):
                name, data = join_parts(f)
                keep(code, name, data)
            elif low.endswith(".zip"):
                with zipfile.ZipFile(f) as z:
                    for info in z.infolist():
                        if not info.is_dir():
                            keep(code, Path(info.filename).name, z.read(info))
            else:
                keep(code, f.name, f.read_bytes())
    return list(found.values())


# ---------------------------------------------------------------- loading into Documents
def _cabinet(code: str) -> int:
    from . import mayan
    return mayan.cabinet(BY_CODE[code][1], mayan.cabinet(CABINET))


def load_folder(conn, root: Path, actor: str, dry_run: bool = False) -> dict:
    """Load every pack file under root into Documents: new files uploaded, changed ones a new version, unchanged ones
    skipped, restricted ones refused (D547). Returns what happened, file by file."""
    from . import mayan
    loaded, replaced, skipped, refused = [], [], [], []
    for f in scan(root):
        label = f"{BY_CODE[f['industry']][1]}: {f['name']}"
        if restricted(f["name"], f["content"]):
            refused.append(label)
            continue
        row = conn.execute(text("""SELECT id, checksum, mayan_document_id, versions FROM core.industry_pack_files
                                    WHERE industry = :i AND file_name = :n"""), {"i": f["industry"], "n": f["name"]}).mappings().first()
        if row and row["checksum"] == f["checksum"] and row["mayan_document_id"]:
            skipped.append(label)
            continue
        if dry_run:
            (replaced if row else loaded).append(label)
            continue
        ctype = mimetypes.guess_type(f["name"])[0] or "application/octet-stream"
        if row and row["mayan_document_id"]:
            mayan.new_version(row["mayan_document_id"], f["name"], f["content"], f"{actor}: the pack file changed", ctype)
            conn.execute(text("""UPDATE core.industry_pack_files SET checksum = :c, file_size = :s, kind = :k, title = :t,
                                        content_type = :ct, versions = versions + 1, loaded_by = :u, updated_at = now(),
                                        sample = false, sample_content = NULL WHERE id = :id"""),
                         {"c": f["checksum"], "s": len(f["content"]), "k": f["kind"], "t": f["title"], "ct": ctype,
                          "u": actor, "id": row["id"]})
            replaced.append(label)
        else:
            doc = mayan.upload(f["name"], f["content"], ctype, label=f"{BY_CODE[f['industry']][1]} pack: {f['title']}")
            mayan.add_to_cabinet(_cabinet(f["industry"]), doc["id"])
            conn.execute(text("""INSERT INTO core.industry_pack_files (industry, kind, title, file_name, content_type, file_size,
                                                                        checksum, mayan_document_id, loaded_by)
                                 VALUES (:i, :k, :t, :n, :ct, :s, :c, :m, :u)
                                 ON CONFLICT (industry, file_name) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title,
                                     content_type = EXCLUDED.content_type, file_size = EXCLUDED.file_size,
                                     checksum = EXCLUDED.checksum, mayan_document_id = EXCLUDED.mayan_document_id,
                                     loaded_by = EXCLUDED.loaded_by, updated_at = now(), sample = false,
                                     sample_content = NULL"""),
                         {"i": f["industry"], "k": f["kind"], "t": f["title"], "n": f["name"], "ct": ctype,
                          "s": len(f["content"]), "c": f["checksum"], "m": doc["id"], "u": actor})
            loaded.append(label)
    if not dry_run and (loaded or replaced or refused):
        from . import audit
        audit.record(conn, actor=actor, action="industry_packs.loaded", object_type="industry_packs", object_id=str(root),
                     details={"loaded": len(loaded), "replaced": len(replaced), "skipped": len(skipped),
                              "refused": refused})
    return {"folder": str(root), "loaded": loaded, "replaced": replaced, "unchanged": skipped, "refused": refused,
            "message": (f"{len(loaded)} loaded, {len(replaced)} replaced, {len(skipped)} unchanged"
                        + (f", {len(refused)} refused (marked not for AI use)" if refused else "") + ".")}


# ---------------------------------------------------------------- the tiles
def _code_for_model(conn, model: Any) -> str | None:
    """The pack of a reference model: by the model's industry code (seed/industries.py), else its industry name."""
    from .seed import build, industries
    row = conn.execute(text("SELECT guid::text AS guid, industry FROM core.models WHERE guid::text = :m OR id::text = :m"),
                       {"m": str(model)}).mappings().first()
    if not row:
        return None
    for code, *_rest in industries.MODELS:
        if build.gid("model", industries.key(code)) == row["guid"]:
            return next((c for c, _n, _f, models in INDUSTRIES if code in models), None)
    return industry_of(row["industry"] or "") if row["industry"] else None


def pack(conn, industry: str) -> dict:
    """The tiles of one industry's pack: one per kind, with its files; a kind the pack has no file for shows as not
    loaded yet, except the book and workbook for an industry that has none (metamodel-only packs, D548)."""
    if industry not in BY_CODE:
        raise EditError(f"No industry pack '{industry}'.", 404)
    rows = conn.execute(text("""SELECT guid::text AS id, kind, title, file_name, content_type, file_size, versions, sample,
                                       loaded_at, updated_at, mayan_document_id IS NOT NULL OR sample_content IS NOT NULL AS ready
                                  FROM core.industry_pack_files WHERE industry = :i ORDER BY kind, title"""),
                        {"i": industry}).mappings().all()
    files = [dict(r) for r in rows]
    for f in files:
        f["type"] = f["file_name"].rpartition(".")[2].upper()
        f["download"] = f"/api/v1/industry-packs/files/{f['id']}/download"
    starter = industry in STARTER_PACKS
    tiles = []
    for kind, title, about in KINDS:
        mine = [f for f in files if f["kind"] == kind]
        if not mine and not starter and kind not in ("metamodel", "example_views"):
            continue                                  # a metamodel-only pack has no book, workbook or templates (D548)
        tiles.append({"kind": kind, "title": title, "about": about, "files": mine,
                      "state": "loaded" if mine else "not loaded"})
    return {"industry": industry, "name": BY_CODE[industry][1], "tiles": tiles,
            "files": len(files), "size": sum(f["file_size"] for f in files)}


# the industries whose packs are full starter packs (the owner's Industry Specific Guidance, D546); the others have only
# the metamodel Excel and the ArchiMate 4 views (D548)
STARTER_PACKS = {"banking", "healthcare", "insurance", "manufacturing", "pharmaceuticals", "retail"}


def for_model(conn, model: Any) -> dict:
    code = _code_for_model(conn, model)
    if not code:
        return {"industry": None, "tiles": [], "message": "This library model has no industry pack."}
    return pack(conn, code)


def listing(conn) -> list[dict]:
    rows = conn.execute(text("""SELECT industry, count(*) AS files, sum(file_size) AS size FROM core.industry_pack_files
                                 GROUP BY industry""")).mappings().all()
    have = {r["industry"]: r for r in rows}
    return [{"industry": c, "name": n, "files": int(have[c]["files"]) if c in have else 0,
             "size": int(have[c]["size"] or 0) if c in have else 0} for c, n, _f, _m in INDUSTRIES]


def download(conn, file_id: str) -> tuple[bytes, str, str]:
    from . import mayan
    row = conn.execute(text("""SELECT file_name, content_type, mayan_document_id, sample_content FROM core.industry_pack_files
                                WHERE guid::text = :g"""), {"g": file_id}).mappings().first()
    if not row:
        raise EditError("No such pack file.", 404)
    if row["sample_content"] is not None and not row["mayan_document_id"]:
        return bytes(row["sample_content"]), row["content_type"], row["file_name"]
    if not row["mayan_document_id"]:
        raise EditError("This pack file is not in Documents yet: ask an admin to run `eax packs load`.", 409)
    content, _ctype, _name = mayan.download(row["mayan_document_id"])
    return content, row["content_type"], row["file_name"]


def missing_shipped(conn) -> list[str]:
    """Names of shipped pack files not in Documents yet (a quick look by name, no checksums): for the job that loads them
    once Documents answers, when the start-up step ran before it was up."""
    if not PACKS_DIR.is_dir():
        return []
    have = {(r[0], r[1]) for r in conn.execute(text(
        "SELECT industry, file_name FROM core.industry_pack_files WHERE mayan_document_id IS NOT NULL")).all()}
    out = []
    for folder in PACKS_DIR.iterdir():
        code = industry_of(folder.name) if folder.is_dir() else None
        for f in (folder.iterdir() if code else []):
            name = f.name[:-len(".parts.json")] if f.name.endswith(".parts.json") else f.name
            if f.is_file() and classify(name) and (code, name) not in have:
                out.append(f"{code}/{name}")
    return out


def load_shipped(conn, actor: str = "system:seed") -> dict:
    """At start-up: the packs shipped in the repository, into Documents when missing or changed."""
    return load_folder(conn, PACKS_DIR, actor)


def main(argv: list[str]) -> int:
    """`python -m eax.industry_packs load [folder] [--dry-run]` (eax packs load / reload): load a folder of packs (the
    shipped ones by default, or the extra folder EAX_PACKS_DIR mounts) into Documents."""
    from .db import get_engine
    args = [a for a in argv if not a.startswith("--")]
    if not args or args[0] not in ("load", "reload", "status"):
        print("Usage: python -m eax.industry_packs load [shipped|extra|<folder in the container>] [--dry-run] | status")
        return 2
    with get_engine().begin() as conn:
        if args[0] == "status":
            for p in listing(conn):
                print(f"{p['name']:<22} {p['files']:>3} files  {p['size'] / 1048576:7.1f} MB")
            return 0
        where = args[1] if len(args) > 1 else "shipped"
        root = PACKS_DIR if where == "shipped" else EXTRA_DIR if where == "extra" else Path(where)
        out = load_folder(conn, root, os.environ.get("EAX_ACTOR", "eax packs"), dry_run="--dry-run" in argv)
        for k in ("loaded", "replaced", "refused"):
            for x in out[k]:
                print(f"  {k}: {x}")
        print(out["message"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
