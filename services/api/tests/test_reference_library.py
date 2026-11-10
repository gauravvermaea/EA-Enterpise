"""Phase 13.0.8 (D300): the organisation's reference library."""

import io
import zipfile
from pathlib import Path

import pytest

from eax import reference_library as rl
from eax.metamodel_edit import EditError
from eax.text_extract import text_of

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT.parent / "web" / "src"


def _docx(words: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{words}</w:t></w:r></w:p></w:body></w:document>")
    return b.getvalue()


def test_text_is_read_from_office_and_plain_files():
    assert text_of("a.docx", _docx("solvency &amp; capital")) == "solvency & capital"
    assert text_of("a.html", b"<p>x<script>bad()</script> y</p>") == "x y"
    assert text_of("a.md", b"# Title\nbody") == "# Title body"
    assert text_of("a.bin", b"zz") == "" and text_of("broken.docx", b"not a zip") == ""


def test_rules():
    class U:
        username = "x"
        roles = ("user",)

    class S:
        username = "sa"
        roles = ("super-admin",)
    assert not rl.may_write(U()) and rl.may_write(S())
    with pytest.raises(EditError):
        rl._need_write(U())
    assert rl.clean_folder("Regulation\\\\Prudential/../x") == "Regulation/Prudential/x"
    assert rl._tags("a, b, A, ") == ["a", "b"]
    with pytest.raises(EditError):
        rl._url("javascript:alert(1)")


def test_migration_api_and_screens():
    sql = (ROOT / "migrations" / "sql" / "0030_reference_library.sql").read_text()
    for t in ("proj.org_ref_folders", "proj.org_ref_entries", "proj.org_ref_versions", "to_tsvector('english'"):
        assert t in sql
    api = (ROOT / "eax" / "api" / "projects.py").read_text()
    for r in ('"/reference-library"', '"/reference-library/pick"', '"/reference-library/files"', '"/reference-library/<string:eid>/versions"'):
        assert r in api
    assert "pypdf" in (ROOT / "requirements.txt").read_text()
    assert "<ReferenceLibraryPage route={route} />" in (WEB / "App.jsx").read_text()
    r = (WEB / "References.jsx").read_text()
    assert "<EnterprisePicker" in r
    assert "Enterprise reference library" in (WEB / "Projects.jsx").read_text()      # a sub-tab of the project's Library (D400)
